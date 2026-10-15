# Signed scheduled-run history

`shuttle.scheduled_history.ScheduledHistory` is a read-only library. It does
not poll, alert, run jobs, register identities, generate keys or retire cron.
Callers own those actions and their acceptance checks.

Construct it with the six-field scope used by `ScheduledRunPort`, the approved
public key and registration graph, a fixed UTC cadence, first eligible time,
signed completion deadline, maximum start lateness, and a callback checking
current declaration/revision/enablement. The callback must return exactly
`True` and must have retained catalogue coverage; an unconditional callback is
appropriate only in an explicitly synthetic fixture.

`measure(now=utc_integer, positive_slot=prior_slot)` derives the latest slot
whose deadline has passed. It queries only the identity graph and the explicit
monthly run graph, for the deterministic control and target run identities.
The positive slot must be a retained successful natural run of this exact scope
in the same month. The library verifies signatures; the operator must establish
the control's natural origin. It cannot infer naturalness from a signature.
Refresh the control each month. A month boundary that could split the admitted
start window produces `UNKNOWN`, rather than querying a different graph and
claiming an empty success.

Results distinguish `SUCCEEDED`, `FAILED`, `HELD`, `LATE`, `MISSED`, `UNKNOWN`
and `NOT_DUE`. Missing target publication or a running-only target at polling
time is `MISSED` only after the positive control passes. Partial/malformed,
duplicated, invalidly signed, truncated or unavailable results are `UNKNOWN`.
The full transition fact set, registered scope, agent, chronology and Ed25519
signatures are checked. Local numeric exit metadata is not evidence here.

This is the latest eligible slot, not an audit of every previous deadline.
Clock correctness is a caller responsibility. Calendar schedules and DST are
unsupported; do not encode a local weekly schedule as 604800 elapsed seconds.
No graph ingestion timestamp is available: a newly published on-time terminal
transition can resolve a missing-publication result, but its actual arrival time
cannot be reconstructed. The caller must retain dated observations to assess
publication timeliness. Shared Unix uid custody does not prove isolated authorship.

## Source demonstration

Run `python docs/demos/scheduled-history.py --source .`. The recording uses real
temporary fixture keys and signatures, with an explicitly mocked remote graph.
It shows an empty history as UNKNOWN, a valid positive control plus missing
target as MISSED, a valid target as SUCCEEDED, and a damaged signature as UNKNOWN.
It proves source behavior, not installation, live graph admission, alert delivery
or a natural scheduled run. Retain the small recording with the source demo.

Base: `5bd02df0a389e661637eed345950888c47b1599e`. Demonstrated module SHA256: `76dce9197d0828bb44f91e93c6f823978b8f708d452dc7ad450f4283eb579e5b`. Exact proposal commit is recorded in the PR.

Download the [after output](demos/scheduled-history-after.log) and [timing](demos/scheduled-history-after.timing), then replay with `scriptreplay --log-out scheduled-history-after.log --log-timing scheduled-history-after.timing`. The [before recording](demos/scheduled-history-before.log) uses the same probe against an isolated base checkout. These are terminal recordings, not inline video.
