# Strict scheduled-run port

`shuttle.scheduled.ScheduledRunPort` implements a concrete signing port for an
external durable slot receiver. It runs no child command and starts no daemon,
listener, schedule or identity-registration ceremony. Keep the external claim
ledger and every per-run outbox across rollback.

The caller supplies one pinned immutable scope: job, revision, verified host
identity, command-manifest SHA256, executing agent and workflow. It supplies an
approved public key and exact named identity-graph registration, plus a trusted
current-declaration eligibility check. The host argument must come from the
runtime owner's verified host mapping, independently of the delivery packet.
A valid key under a shared Unix uid proves integrity and registration, not
isolated agent authorship. Parent-directory custody remains the operator's
responsibility; strict key loading rejects the final symlink.

Admission refuses anything except one exact scoped registration, a matching
existing local key and explicitly true declaration eligibility. Missing,
truncated, malformed, ambiguous or differently typed results are UNKNOWN or
refused. No missing key is generated. New execution must be inside the
configured lateness window. Historic redelivery may publish an existing result,
but it cannot call started a second time.

The concrete port caps each scope field at256 characters and the complete
run name at2048 characters. The generic receiver may represent larger scopes;
those are refused by this port before execution.

The run name must reversibly encode the complete scope and UTC scheduled slot
using the external receiver's `scheduled-v1-` canonical JSON/base64url contract.
Started signs queued-to-running and persists the log and its directories with
fsync before returning. Finished signs succeeded, failed or skipped-by-hold.
Contradictory process results refuse; the numeric exit code is unsigned local
receipt metadata under the current Shuttle signature format.

Publication rechecks registration and eligibility, uses the existing windowed
export path, and then requires all eighteen exact typed triples for the two
signed transition events in the correct window. Missing or extra events,
altered values or datatype loss refuse acceptance. Local signatures are
verified against the admitted registered key before export. Re-publication
can drain the same outbox; it never signs a second run or executes work.

## Process interface

`shuttle scheduled admit|started|finished|publish --config FILE` reads one
bounded JSON object from stdin. It exposes the same port without requiring the
receiver and Shuttle to share a Python environment. Old installations reject
the subcommand before work. Unknown fields, duplicate JSON keys and oversized
input refuse. Nothing in a delivery supplies a command, query or credential.

The packet has `scope` (the six fields above) and integer `scheduled_at`.
Actions after admit also require `run`; finished and publish require
`outcome` with the actual outcome name and exit_code. Successful output names
the action: admission or local signed persistence does not mean publication.
Only successful publish includes exact governed transition read-back.

The trusted local config has exactly `binding`, `host`, `public_key`,
`registration`, `identity_graph`, `state_root`, `declaration_graph`,
`eligibility_query`, `interval_s`, `anchor_s`, `effective_from_s` and
`max_lateness_s`. State root must be absolute and persistent, with a provisioned existing parent.
The port creates at most the root itself and fsyncs its parent entry as well. Cadence is a
fixed interval of at least sixty seconds with an explicit activation boundary.
Alternatively, replace only `interval_s` with `weekday` (Monday=0..Sunday=6),
`local_time` (HH:MM) and `timezone` (IANA identifier). These two exact field
sets cannot be mixed. Calendar anchors must match the pinned weekday/time and
be unambiguous. Each integer UTC slot is converted into that zone, checked
against the local weekday/time, and round-tripped with both fold values.
Gaps and both occurrences of an overlap refuse; no time shifting or first-fold
selection. The activation boundary is inclusive. For Monday09:17 New York,
October26 2026 is13:17Z and November2 is14:17Z,608400 seconds later.
The runtime owner must bind those exact calendar qualifiers in the eligibility
query as well as the pinned configuration. This adds admission, not a timer or
a calendar-aware history/deadline reader; those remain receiver/reader contracts.
No past-slot bootstrap is implied.

The eligibility SELECT is compiled and reviewed by the runtime owner, stored
in the pinned local configuration, scoped to declaration_graph, and bounded by
LIMIT 2. It must bind the exact job/revision/host/target/enablement and validated
Schedule, detect conflicting declarations, and return exactly one boolean
`eligible=true`. The port is not a generic SHACL validator and cannot certify
that an arbitrary operator-written query implements those policies. Runtime
admission therefore requires a validated Quechua profile, retained catalogue
membership controls and review of this exact query/configuration. An empty or
uncertain catalogue is never a healthy empty schedule. Do not substitute a
constant-true query.

This source capability does not load profiles, declare jobs, install software,
change cron, authorize a release or prove a natural scheduled execution.
Tests use real temporary Ed25519 keys and durable local outboxes with explicitly
mocked remote transport. Live export and natural pilot proof remain separate.

## Source demonstration

[Recording](demos/scheduled-port.log) and [timing](demos/scheduled-port.timing)
use actual temporary Ed25519 signatures and local outbox persistence. Remote
transport is explicitly a test double and no child process runs. The source
base6637866 has no scheduled port; its existing strict-signing positive control
already verifies synthetic signatures. Implementation91423b0 adds the displayed signed
lifecycle, exact eighteen-triple read-back, publication-only replay, and a
negative control that refuses an altered remote-fixture triple.

From a full source clone with cryptography installed, run
`python scripts/demo-scheduled-port.py`. The small recording is retained with
the source proposal and was replayed with
`scriptreplay --log-out scheduled-port.log --log-timing scheduled-port.timing`.
Download both artifacts for replay; no inline video or installed/live proof is
claimed. This script imports the repository's isolated test fixture.
