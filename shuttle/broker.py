"""The signing broker: per-run capabilities over keys a job can never read.

Ruling B of aegis-za4f.19 (sattler, 2026-11-27), superseding decision 3 of
the 2026-09-12 "signatures are not attribution" record FOR BROKER-HELD KEYS
ONLY. That decision stays true for any key a same-uid process can read, so
the broker's whole point is that the private key never enters a place the
job's uid (braino) can reach: it lives only in this process's memory, the
process runs as its own system user, and it is marked non-dumpable so its
/proc/<pid>/mem, environ and fds are root-owned even to a same-uid reader.

This module is the pure core — no sockets. `broker_server` puts it on a
unix socket. The three operations of the capability API:

  create(agent, job, item, spawner, run_iri, definition, ...) -> token
      Generates a FRESH ed25519 key for `agent` (an `eph-task-<id>` name),
      held in memory only. Returns the bearer token and the PUBLIC key with
      the registration facts (spawner, item) a human/st registers. An agent
      name is never issued twice by one broker: reuse would let a second
      capability sign under an identity whose history already exists.
  sign(token, step) -> the signed transition
      Legal only if `step` is in the capability's allowed steps AND legal
      from the run's current state (model.validate_advance), and only
      before expiry. The broker owns the run's state and the timestamp, so
      a token cannot replay, skip, or backdate a step.
  destroy(token) -> drops the key. Expiry destroys too (`reap`).

What a stolen token buys, and no more: one run, its legal steps in order,
until the job's deadline. It never buys a crew key — the broker holds none
(crew keys moving in is slice S4).
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import model, signing

# The only identities a broker mints. A crew name ("dearing") is refused, so
# a token can never be minted into a signature that claims to be crew.
AGENT_PATTERN = re.compile(r"^eph-task-[a-z0-9][a-z0-9-]{0,62}$")
DEFAULT_MAX_TTL = 24 * 3600
# Any admitted caller can create, so live capabilities (each a key in
# memory) are capped; past the cap a create is refused, never queued.
DEFAULT_MAX_LIVE = 256
# Issued names are kept for the no-re-key rule; cap them too, so create spam
# cannot grow memory without bound. Past it the broker refuses until restart.
DEFAULT_MAX_ISSUED = 65536


class BrokerError(RuntimeError):
    """A capability request was refused. The message names the reason."""


def utc_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Capability:
    agent: str
    job: str
    item: str
    spawner: str
    run_iri: str
    definition: model.Definition
    allowed_steps: frozenset[str]
    expires_at: float
    state: str
    signer: Ed25519PrivateKey | None
    public_key: str
    signed: list[dict] = field(default_factory=list)


def _digest(token: str) -> str:
    # Only the digest is held, so a broker memory read (which non-dumpable
    # already blocks) would still not hand back a usable bearer token.
    return hashlib.sha256(token.encode()).hexdigest()


def _text(raw: dict, name: str) -> str:
    v = raw.get(name)
    if not isinstance(v, str) or not v or "|" in v or "\n" in v:
        raise BrokerError(f"create needs a non-empty single-line '{name}' without '|'")
    return v


class Broker:
    """Capabilities and their keys, in memory. Thread-safe."""

    def __init__(self, *, clock=time.time, max_ttl: float = DEFAULT_MAX_TTL,
                 max_live: int = DEFAULT_MAX_LIVE, max_issued: int = DEFAULT_MAX_ISSUED):
        self._clock = clock
        self._max_ttl = max_ttl
        self._max_live = max_live
        self._max_issued = max_issued
        self._caps: dict[str, Capability] = {}
        self._issued: set[str] = set()
        self._lock = threading.Lock()

    # -- create ---------------------------------------------------------
    def create(self, raw: dict) -> dict:
        agent = _text(raw, "agent")
        if not AGENT_PATTERN.match(agent):
            raise BrokerError(
                f"agent {agent!r} is not an ephemeral job identity; the broker "
                f"mints only names matching {AGENT_PATTERN.pattern}"
            )
        job, item, spawner, run_iri = (
            _text(raw, k) for k in ("job", "item", "spawner", "run_iri"))
        if not isinstance(raw.get("definition"), dict):
            raise BrokerError("create needs the run's workflow 'definition' object")
        try:
            defn = model.parse_definition(raw["definition"])
        except model.WorkflowError as exc:
            raise BrokerError(f"definition refused: {exc}") from exc
        legal = {t.step for t in defn.transitions}
        steps = raw.get("allowed_steps")
        if steps is None:
            allowed = frozenset(legal)
        elif isinstance(steps, list) and steps and all(isinstance(s, str) for s in steps):
            unknown = sorted(set(steps) - legal)
            if unknown:
                raise BrokerError(
                    f"allowed_steps {unknown} are not steps of '{defn.name}'. "
                    f"Its steps: {sorted(legal)}")
            allowed = frozenset(steps)
        else:
            raise BrokerError("allowed_steps must be a non-empty list of step names")
        state = raw.get("state", defn.initial)
        if not isinstance(state, str) or state not in defn.states():
            raise BrokerError(
                f"state {state!r} is not a state of '{defn.name}'. "
                f"Its states: {sorted(defn.states())}")
        expires_at = raw.get("expires_at")
        now = self._clock()
        if type(expires_at) not in (int, float):
            raise BrokerError("create needs 'expires_at' (epoch seconds: the job deadline)")
        if expires_at <= now:
            raise BrokerError(f"expires_at {utc_iso(expires_at)} is not in the future")
        if expires_at - now > self._max_ttl:
            raise BrokerError(
                f"expires_at is beyond the broker's max lifetime of {int(self._max_ttl)}s")

        key = Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._reap_locked()
            if agent in self._issued:
                raise BrokerError(
                    f"agent {agent!r} was already issued a key by this broker; "
                    f"an identity is never re-keyed")
            if len(self._caps) >= self._max_live:
                raise BrokerError(
                    f"broker holds {len(self._caps)} live capabilities (max "
                    f"{self._max_live}); destroy finished runs before creating more")
            if len(self._issued) >= self._max_issued:
                raise BrokerError(
                    f"broker has issued {len(self._issued)} identities (max "
                    f"{self._max_issued}); restart it to admit more")
            self._issued.add(agent)
            self._caps[_digest(token)] = Capability(
                agent=agent, job=job, item=item, spawner=spawner, run_iri=run_iri,
                definition=defn, allowed_steps=allowed, expires_at=float(expires_at),
                state=state, signer=key, public_key=pub)
        return {
            "token": token,
            "agent": agent,
            "public_key": pub,
            "run_iri": run_iri,
            "expires_at": utc_iso(expires_at),
            "registration": {
                "verifier": agent, "publicKey": pub, "attests": run_iri,
                "spawnedBy": spawner, "item": item, "job": job,
            },
        }

    # -- sign -----------------------------------------------------------
    def sign(self, token: str, step: str) -> dict:
        if not isinstance(step, str) or not step:
            raise BrokerError("sign needs a 'step'")
        with self._lock:
            cap = self._live_locked(token)
            if step not in cap.allowed_steps:
                raise BrokerError(
                    f"step '{step}' is not allowed by this capability. "
                    f"Allowed: {sorted(cap.allowed_steps)}")
            try:
                to_state = model.validate_advance(cap.definition, cap.state, step)
            except model.WorkflowError as exc:
                raise BrokerError(str(exc)) from exc
            at = utc_iso(self._clock())
            msg = signing.transition_message(
                cap.run_iri, step, cap.state, to_state, at, cap.agent)
            signed = {
                "run_iri": cap.run_iri, "step": step, "from_state": cap.state,
                "to_state": to_state, "at": at, "agent": cap.agent,
                "signature": cap.signer.sign(msg).hex(),
            }
            cap.state = to_state
            cap.signed.append(signed)
            if to_state in cap.definition.terminal:
                # A finished run needs no key; holding it is only exposure.
                cap.signer = None
            return signed

    # -- destroy / expiry -----------------------------------------------
    def destroy(self, token: str) -> dict:
        with self._lock:
            cap = self._caps.pop(_digest(token), None) if isinstance(token, str) else None
            if cap is None:
                raise BrokerError("unknown or already destroyed capability")
            cap.signer = None
            return {"destroyed": cap.agent, "signed": len(cap.signed)}

    def reap(self) -> list[str]:
        with self._lock:
            return self._reap_locked()

    def _reap_locked(self) -> list[str]:
        now = self._clock()
        gone = [d for d, c in self._caps.items() if c.expires_at <= now]
        out = []
        for d in gone:
            cap = self._caps.pop(d)
            cap.signer = None
            out.append(cap.agent)
        return out

    def _live_locked(self, token) -> Capability:
        if not isinstance(token, str) or not token:
            raise BrokerError("a capability 'token' is required")
        cap = self._caps.get(_digest(token))
        if cap is None:
            raise BrokerError("unknown, expired or destroyed capability")
        if cap.expires_at <= self._clock():
            self._caps.pop(_digest(token))
            cap.signer = None
            raise BrokerError(f"capability expired at {utc_iso(cap.expires_at)}; key destroyed")
        if cap.signer is None:
            raise BrokerError(f"run is terminal ('{cap.state}'); its key is destroyed")
        return cap

    # -- introspection (tests, status) ----------------------------------
    def holds_key(self, agent: str) -> bool:
        with self._lock:
            return any(c.agent == agent and c.signer is not None for c in self._caps.values())

    def live_count(self) -> int:
        with self._lock:
            return len(self._caps)
