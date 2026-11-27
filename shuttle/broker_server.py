"""The signing broker on a unix socket — `shuttle-signer serve`.

Wire protocol: one JSON object per connection, newline-terminated, answered
by one JSON object: `{"ok": true, ...}` or `{"ok": false, "error": "..."}`.
Operations: `create`, `destroy` (admin: the peer's SO_PEERCRED uid must be
in `--admin-uid`), `sign` (any peer the socket's mode admits; the token is
the authority), `ping`.

Custody, in the order a reader would attack it:
  - the keys exist only in this process's memory (no state directory);
  - the process is PR_SET_DUMPABLE=0, so /proc/<pid>/{mem,environ,fd} are
    root-owned and no core is written, even to a same-uid reader;
  - in deployment the process runs as its own system user (shuttle-signer),
    so braino cannot ptrace it or signal it either
    (deploy/systemd/shuttle-signer.service);
  - the socket is created 0660 under a 0750 runtime dir; group membership
    is what admits a client.

Residual, stated rather than hidden: st and its jobs share uid braino today,
so `--admin-uid` cannot tell st from a job. A job could therefore mint a
FRESH `eph-task-*` identity (never a crew one, never a live job's, never a
re-key), and the registration's spawner/item links are what make such a mint
visible. A distinct uid for st closes it; that is not this slice.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import socketserver
import struct
import sys
import threading
from pathlib import Path

from .broker import Broker, BrokerError

MAX_REQUEST = 256 * 1024
PR_SET_DUMPABLE = 4
ADMIN_OPS = {"create", "destroy"}


def default_socket() -> Path:
    return Path(os.environ.get("SHUTTLE_SIGNER_SOCKET", "/run/shuttle-signer/signer.sock"))


def make_undumpable() -> None:
    """Refuse loudly if the kernel will not mark us non-dumpable: a broker
    whose memory a same-uid process can read holds keys that are theatre."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE, 0) failed")


def peer_uid(sock: socket.socket) -> int:
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", creds)
    return uid


def handle(broker: Broker, admin_uids: frozenset[int], uid: int, raw: bytes) -> dict:
    try:
        req = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"ok": False, "error": "request is not one JSON object"}
    if not isinstance(req, dict):
        return {"ok": False, "error": "request is not one JSON object"}
    op = req.get("op")
    if op in ADMIN_OPS and uid not in admin_uids:
        return {"ok": False, "error": f"'{op}' is an admin operation; uid {uid} is not admitted"}
    try:
        if op == "create":
            return {"ok": True, **broker.create(req)}
        if op == "sign":
            return {"ok": True, **broker.sign(req.get("token"), req.get("step"))}
        if op == "destroy":
            return {"ok": True, **broker.destroy(req.get("token"))}
        if op == "ping":
            return {"ok": True, "live": broker.live_count()}
    except BrokerError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"unknown op {op!r}. Legal: create, sign, destroy, ping"}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        srv = self.server
        line = self.rfile.readline(MAX_REQUEST + 1)
        if len(line) > MAX_REQUEST:
            resp = {"ok": False, "error": f"request exceeds {MAX_REQUEST} bytes"}
        else:
            resp = handle(srv.broker, srv.admin_uids, peer_uid(self.connection), line)
        self.wfile.write(json.dumps(resp).encode() + b"\n")


class SignerServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path: Path, broker: Broker, admin_uids, mode: int = 0o660):
        self.broker = broker
        self.admin_uids = frozenset(admin_uids)
        if path.exists() or path.is_symlink():
            if not path.is_socket():
                raise OSError(f"{path} exists and is not a socket; refusing to replace it")
            path.unlink()
        old = os.umask(0o177)
        try:
            super().__init__(str(path), _Handler)
        finally:
            os.umask(old)
        os.chmod(path, mode)
        self._stop = threading.Event()
        threading.Thread(target=self._reaper, daemon=True).start()

    def _reaper(self):
        while not self._stop.wait(5):
            self.broker.reap()

    def server_close(self):
        self._stop.set()
        super().server_close()


def call(request: dict, path: Path | None = None, timeout: float = 10.0) -> dict:
    """One request to the broker. Unreachable is an exception, never a soft
    refusal; a refusal comes back as {"ok": false, "error": ...}."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(path or default_socket()))
        s.sendall(json.dumps(request).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="shuttle-signer", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the broker on a unix socket")
    s.add_argument("--socket", type=Path, default=None)
    s.add_argument("--admin-uid", type=int, action="append", default=[],
                   help="uid admitted to create/destroy (repeatable; none = no admin)")
    s.add_argument("--mode", type=lambda v: int(v, 8), default=0o660)
    s.add_argument("--max-ttl", type=float, default=None)
    c = sub.add_parser("call", help="send one JSON request read from stdin")
    c.add_argument("--socket", type=Path, default=None)
    args = p.parse_args(argv)

    if args.cmd == "call":
        resp = call(json.load(sys.stdin), args.socket)
        print(json.dumps(resp))
        return 0 if resp.get("ok") else 1

    make_undumpable()
    broker = Broker(**({"max_ttl": args.max_ttl} if args.max_ttl else {}))
    path = args.socket or default_socket()
    with SignerServer(path, broker, args.admin_uid, args.mode) as srv:
        print(f"shuttle-signer: serving on {path}", file=sys.stderr, flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
