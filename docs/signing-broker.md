# Signing broker (`shuttle-signer`)

Ruling B of aegis-za4f.19 (sattler, 2026-11-27): an ephemeral job signs its
workflow transitions with **its own** key, and that key never enters a place
the job's uid can read. Recorded as
`docs/decisions/2026-11-27-shuttle-signing-broker.md` in aegis, which
supersedes decision 3 of 2026-09-12 for broker-held keys only.

## Custody

- Keys are generated per capability and held **only in memory** — no state
  directory. A broker restart destroys every key.
- The process sets `PR_SET_DUMPABLE=0` at start and refuses to serve if the
  kernel will not: `/proc/<pid>/{mem,environ,fd}` become root-owned and no
  core is written, even to a same-uid reader.
- Deployed as its own system user `shuttle-signer`
  (goldblum role draft, the single unit template, in
  `deploy/goldblum/roles/shuttle_signer`). Socket
  `/run/shuttle-signer/signer.sock`, 0660 in a 0750 dir; clients join group
  `shuttle-signer`.

## API (one JSON line per connection)

| op | who | request | answer |
|---|---|---|---|
| `create` | admin uid (st at spawn) | `agent` (`eph-task-*`), `job`, `item`, `spawner`, `run_iri`, `definition`, `expires_at` (epoch, the job deadline), optional `allowed_steps`, `state` | `token`, `public_key`, `registration` {verifier, publicKey, attests, spawnedBy, item, job} |
| `sign` | token holder | `token`, `step` | the signed transition: `run_iri, step, from_state, to_state, at, agent, signature` |
| `destroy` | admin uid (st at teardown) | `token` | `destroyed`, `signed` count |
| `ping` | anyone | — | `live` count |

`sign` refuses a step outside `allowed_steps`, a step not legal from the
run's current state (the broker owns the state and the clock, so a token
cannot skip, replay or backdate), an expired capability, and a terminal run.
Expiry and reaching a terminal state both drop the key. Signatures are the
unchanged `shuttle-transition-v1` message, so `signing.verify_transition`
checks them against the registered public key.

The broker mints only `eph-task-*` identities and never re-keys a name it
issued, so a token can never yield a crew signature.

## Residual

st and its jobs share uid braino, so the admin gate cannot tell them apart:
a job could mint a *fresh* `eph-task-*` identity (never crew, never a live
job's). The registration's spawner/item links make that visible; a distinct
uid for st closes it. Crew keys moving into the broker is slice S4.

## Verify on the host

`scripts/signer-negative-control.sh`, run as braino: every probe of the
broker's memory, environment, fds and files must be refused.

## Connection bounds

Each connection gets 5 seconds in total to deliver its one request line. An
idle or trickling client is answered `no request within 5.0s` and dropped.
At most `--max-connections` (default 64) are served at once. Past that, a
connection is answered `broker busy; retry` and closed, so it never holds a
thread. Residual: a client in group shuttle-signer that keeps the cap full
can delay every run's signing by up to one deadline per refill. It cannot
read or forge anything. `--max-ttl`, `--max-live` and `--max-connections`
refuse values <= 0 rather than silently falling back to the default.
