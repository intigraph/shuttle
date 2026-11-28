"""The signing broker (aegis-za4f.19.2, ruling B).

Acceptance, one test each: the caller's uid cannot read the key material
(negative control against a live broker process, run as the test's own uid —
braino on the fleet); an illegal step is refused; an expired token is
refused; destroy removes the key; a signature verifies against the public key
the broker hands out for registration.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from shuttle import signing
from shuttle.broker import Broker, BrokerError
from shuttle.broker_server import call

REPO = Path(__file__).resolve().parent.parent

TASK_WORKFLOW = {
    "name": "eph-task",
    "initial": "spawned",
    "terminal": ["reported"],
    "transitions": [
        {"step": "claim", "from": "spawned", "to": "claimed"},
        {"step": "work", "from": "claimed", "to": "worked"},
        {"step": "open-pr", "from": "worked", "to": "pr-open"},
        {"step": "report", "from": "pr-open", "to": "reported"},
        {"step": "report", "from": "worked", "to": "reported"},
    ],
}


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def create_req(clock_t, **over):
    req = {
        "agent": "eph-task-abc123", "job": "eph-task-abc123", "item": "aegis-x.1",
        "spawner": "sattler", "run_iri": "urn:shuttle:run:eph-task-abc123",
        "definition": TASK_WORKFLOW, "expires_at": clock_t + 3600,
    }
    req.update(over)
    return req


def verifies(cap, signed):
    return signing.verify_transition(
        cap["public_key"], signed["signature"], signed["run_iri"], signed["step"],
        signed["from_state"], signed["to_state"], signed["at"], signed["agent"])


class BrokerCore(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.b = Broker(clock=self.clock)
        self.cap = self.b.create(create_req(self.clock.t))

    def test_signature_verifies_against_registered_public_key(self):
        signed = self.b.sign(self.cap["token"], "claim")
        self.assertEqual((signed["from_state"], signed["to_state"]), ("spawned", "claimed"))
        self.assertTrue(verifies(self.cap, signed))
        reg = self.cap["registration"]
        self.assertEqual(reg["verifier"], "eph-task-abc123")
        self.assertEqual(reg["publicKey"], self.cap["public_key"])
        self.assertEqual((reg["spawnedBy"], reg["item"]), ("sattler", "aegis-x.1"))
        # Tampering with any signed field breaks it.
        self.assertFalse(verifies(self.cap, {**signed, "agent": "dearing"}))

    def test_illegal_step_refused_and_names_what_was_legal(self):
        with self.assertRaisesRegex(BrokerError, r"not legal from state 'spawned'.*\['claim'\]"):
            self.b.sign(self.cap["token"], "report")
        with self.assertRaisesRegex(BrokerError, "not allowed"):
            self.b.sign(self.cap["token"], "merge")
        # The refusal did not advance the run.
        self.assertEqual(self.b.sign(self.cap["token"], "claim")["from_state"], "spawned")

    def test_allowed_steps_narrow_the_definition(self):
        cap = self.b.create(create_req(self.clock.t, agent="eph-task-narrow",
                                       allowed_steps=["claim", "work", "report"]))
        self.b.sign(cap["token"], "claim")
        self.b.sign(cap["token"], "work")
        with self.assertRaisesRegex(BrokerError, "not allowed by this capability"):
            self.b.sign(cap["token"], "open-pr")
        with self.assertRaisesRegex(BrokerError, "not steps of"):
            self.b.create(create_req(self.clock.t, agent="eph-task-y", allowed_steps=["x"]))

    def test_expired_token_refused_and_key_destroyed(self):
        self.clock.t += 3600
        with self.assertRaisesRegex(BrokerError, "expired"):
            self.b.sign(self.cap["token"], "claim")
        self.assertFalse(self.b.holds_key("eph-task-abc123"))
        with self.assertRaisesRegex(BrokerError, "unknown, expired or destroyed"):
            self.b.sign(self.cap["token"], "claim")

    def test_reap_destroys_expired_without_a_request(self):
        self.clock.t += 7200
        self.assertEqual(self.b.reap(), ["eph-task-abc123"])
        self.assertEqual(self.b.live_count(), 0)

    def test_destroy_removes_the_key(self):
        self.assertTrue(self.b.holds_key("eph-task-abc123"))
        out = self.b.destroy(self.cap["token"])
        self.assertEqual(out["destroyed"], "eph-task-abc123")
        self.assertFalse(self.b.holds_key("eph-task-abc123"))
        self.assertEqual(self.b.live_count(), 0)
        with self.assertRaises(BrokerError):
            self.b.sign(self.cap["token"], "claim")
        with self.assertRaises(BrokerError):
            self.b.destroy(self.cap["token"])

    def test_terminal_run_drops_its_key(self):
        for step in ("claim", "work", "report"):
            self.b.sign(self.cap["token"], step)
        self.assertFalse(self.b.holds_key("eph-task-abc123"))
        with self.assertRaisesRegex(BrokerError, "terminal"):
            self.b.sign(self.cap["token"], "report")

    def test_crew_identity_and_rekey_refused(self):
        with self.assertRaisesRegex(BrokerError, "not an ephemeral job identity"):
            self.b.create(create_req(self.clock.t, agent="dearing"))
        with self.assertRaisesRegex(BrokerError, "never re-keyed"):
            self.b.create(create_req(self.clock.t))
        self.b.destroy(self.cap["token"])
        with self.assertRaisesRegex(BrokerError, "never re-keyed"):
            self.b.create(create_req(self.clock.t))

    def test_bad_expiry_refused(self):
        for exp, msg in ((self.clock.t - 1, "not in the future"),
                         (self.clock.t + 10 * 86400, "max lifetime"),
                         ("soon", "expires_at"),
                         (float("nan"), "finite"), (float("inf"), "finite")):
            with self.assertRaisesRegex(BrokerError, msg):
                self.b.create(create_req(self.clock.t, agent="eph-task-e", expires_at=exp))


class Limits(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def test_live_capabilities_are_capped(self):
        b = Broker(clock=self.clock, max_live=2)
        for n in range(2):
            b.create(create_req(self.clock.t, agent=f"eph-task-l{n}"))
        with self.assertRaisesRegex(BrokerError, "live capabilities"):
            b.create(create_req(self.clock.t, agent="eph-task-l2"))
        self.assertEqual(b.live_count(), 2)

    def test_issued_identities_are_capped(self):
        b = Broker(clock=self.clock, max_issued=1)
        b.destroy(b.create(create_req(self.clock.t, agent="eph-task-i0"))["token"])
        with self.assertRaisesRegex(BrokerError, "issued"):
            b.create(create_req(self.clock.t, agent="eph-task-i1"))


class Handler(unittest.TestCase):
    def test_malformed_create_gets_a_refusal_not_silence(self):
        from shuttle.broker_server import handle
        bad = dict(TASK_WORKFLOW, terminal=[["unhashable"]])
        resp = handle(Broker(), frozenset({7}), 7,
                      json.dumps({"op": "create", **create_req(time.time(), definition=bad)}).encode())
        self.assertFalse(resp["ok"])
        self.assertTrue(resp["error"])


    def test_non_finite_expiry_refused_at_the_wire(self):
        from shuttle.broker_server import handle
        b = Broker()
        good = json.dumps({"op": "create", **create_req(time.time())})
        for const in ("NaN", "Infinity", "-Infinity"):
            line = re.sub(r'"expires_at": [0-9.e+]+', f'"expires_at": {const}', good)
            self.assertIn(const, line)
            resp = handle(b, frozenset({7}), 7, line.encode())
            self.assertFalse(resp["ok"], const)
            self.assertEqual(b.live_count(), 0, const)
        # The same request with a real deadline still mints: the agent name
        # was not burned by the refused attempts.
        self.assertTrue(handle(b, frozenset({7}), 7, good.encode())["ok"])
        self.assertEqual(b.live_count(), 1)


class BrokerProcess(unittest.TestCase):
    """A live `shuttle-signer serve`, probed from this (the client's) uid."""

    def start(self, *admin):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(tmp)]))
        sock = tmp / "signer.sock"
        home = tmp / "home"
        home.mkdir()
        args = [sys.executable, "-m", "shuttle.broker_server", "serve", "--socket", str(sock)]
        for uid in admin:
            args += ["--admin-uid", str(uid)]
        args += getattr(self, "_extra", [])
        env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(REPO),
               "BROKER_CANARY": "secret-in-env"}
        proc = subprocess.Popen(args, cwd=home, env=env, stderr=subprocess.PIPE)
        self.addCleanup(lambda: (proc.kill(), proc.wait(), proc.stderr.close()))
        for _ in range(200):
            if sock.exists():
                break
            time.sleep(0.02)
        self.assertTrue(sock.exists(), "broker did not come up")
        return proc, sock, home

    def test_round_trip_and_admin_gate(self):
        _proc, sock, _home = self.start(os.getuid())
        cap = call({"op": "create", **create_req(time.time())}, sock)
        self.assertTrue(cap["ok"], cap)
        signed = call({"op": "sign", "token": cap["token"], "step": "claim"}, sock)
        self.assertTrue(signed["ok"], signed)
        self.assertTrue(verifies(cap, signed))
        refused = call({"op": "sign", "token": cap["token"], "step": "report"}, sock)
        self.assertFalse(refused["ok"])
        self.assertIn("not legal", refused["error"])
        self.assertTrue(call({"op": "destroy", "token": cap["token"]}, sock)["ok"])
        self.assertFalse(call({"op": "sign", "token": cap["token"], "step": "work"}, sock)["ok"])
        self.assertEqual(stat.S_IMODE(sock.stat().st_mode), 0o660)

    def test_non_admin_uid_cannot_create_or_destroy(self):
        _proc, sock, _home = self.start()
        for op in ("create", "destroy"):
            resp = call({"op": op, **create_req(time.time())}, sock)
            self.assertFalse(resp["ok"])
            self.assertIn("admin operation", resp["error"])

    @unittest.skipIf(os.geteuid() == 0, "root reads any process; the control must run as braino")
    def test_negative_control_caller_cannot_read_key_material(self):
        proc, sock, home = self.start(os.getuid())
        cap = call({"op": "create", **create_req(time.time())}, sock)
        self.assertTrue(cap["ok"], cap)
        # The broker is non-dumpable: its memory, environment and fds are
        # root-owned, so even a SAME-uid reader is refused. Across uids
        # (deployment) ptrace rules refuse it independently.
        for name in ("mem", "environ"):
            with self.assertRaises(PermissionError, msg=f"/proc/<pid>/{name} was readable"):
                with open(f"/proc/{proc.pid}/{name}", "rb") as f:
                    f.read(1)
        with self.assertRaises(PermissionError):
            os.listdir(f"/proc/{proc.pid}/fd")
        # A user namespace can leave root unmapped: procfs then exposes
        # overflowuid while the same access-denial controls above still hold.
        mappings = [tuple(map(int, line.split()))
                    for line in Path('/proc/self/uid_map').read_text().splitlines()]
        root_mapped = any(inside == 0 and count > 0 for inside, outside, count in mappings)
        owner = 0 if root_mapped else int(Path('/proc/sys/kernel/overflowuid').read_text())
        self.assertEqual(os.stat(f"/proc/{proc.pid}/mem").st_uid, owner)
        # Nothing was written to disk: the key lives only in memory.
        self.assertEqual(sorted(p.name for p in home.iterdir()), [])
        self.assertEqual(sorted(p.name for p in sock.parent.iterdir()), ["home", "signer.sock"])
        # The token buys a signature, never the key: no response carries it.
        signed = call({"op": "sign", "token": cap["token"], "step": "claim"}, sock)
        self.assertNotIn("private", json.dumps(signed).lower())


class ConnectionBounds(BrokerProcess):
    """An idle client cannot hold a handler, and past the cap a connection is
    answered "busy" instead of queuing a thread."""

    def start(self, *admin, extra=()):
        self._extra = list(extra)
        return super().start(*admin)

    def test_idle_connection_is_dropped_at_the_deadline(self):
        import socket
        _proc, sock, _home = self.start(os.getuid())
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as idle:
            idle.settimeout(15)
            idle.connect(str(sock))
            t0 = time.monotonic()
            resp = json.loads(idle.makefile("rb").readline())
            self.assertLess(time.monotonic() - t0, 12)
        self.assertFalse(resp["ok"])
        self.assertIn("no request within", resp["error"])
        self.assertTrue(call({"op": "ping"}, sock)["ok"])

    def test_connections_past_the_cap_are_refused_busy(self):
        import socket
        _proc, sock, _home = self.start(os.getuid(), extra=["--max-connections", "2"])
        held = []
        for _ in range(2):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(s.close)
            s.connect(str(sock))
            held.append(s)
        time.sleep(0.3)
        resp = call({"op": "ping"}, sock)
        self.assertFalse(resp["ok"])
        self.assertIn("busy", resp["error"])
        for s in held:
            s.close()
        for _ in range(100):
            resp = call({"op": "ping"}, sock)
            if resp["ok"]:
                break
            time.sleep(0.05)
        self.assertTrue(resp["ok"], resp)

    test_round_trip_and_admin_gate = None
    test_non_admin_uid_cannot_create_or_destroy = None
    test_negative_control_caller_cannot_read_key_material = None


class Flags(unittest.TestCase):
    def test_zero_limits_are_refused_not_dropped(self):
        from shuttle.broker_server import main
        for flag in ("--max-ttl", "--max-live", "--max-connections"):
            with self.assertRaises(SystemExit) as ctx, \
                    unittest.mock.patch("sys.stderr"):
                main(["serve", flag, "0"])
            self.assertEqual(ctx.exception.code, 2, flag)


if __name__ == "__main__":
    unittest.main()
