# Opt-in calendar signed history

`shuttle.calendar_history.CalendarScheduledHistory` is separate from the fixed
`ScheduledHistory` path. It adds no CLI, timer, polling, dispatch, private-key
access, graph mutation, profile or runtime activation. The fixed reader and its
9l1 contract are unchanged.

Pin immutable scope, public key/registration/identity graph, weekday (Monday=0),
HH:MM local time, IANA zone, activation boundary, signed completion budget and
maximum start lateness. Supply current declaration eligibility through the same
bounded reader contract. The caller must establish declaration coverage and the
natural origin of its successful control; signatures cannot establish those.

Construct `CalendarOccurrence(scheduled_at, next_deadline, zone)` from the
admitted Chaski WeeklyProjection seam: decode the exact `event_id` run slot,
use `next_checks[job]`, and retain the pinned projection timezone. The current
projection JSON does not itself expose a flat occurrence object. `scheduled_at` is the integer UTC slot;
`next_deadline` is the next **occurrence**, not the completion deadline. Chaski
selects occurrences. This reader checks each supplied occurrence against pinned
local weekday/time and verifies the next local-week date, without deriving a
604800-second cadence. Both sides of a DST overlap and nonexistent local times
refuse. An occurrence whose following date is ambiguous also refuses.

Call `measure(now=utc_integer, occurrence=target, positive=prior_occurrence)`.
A stale target at or beyond next occurrence plus completion budget is UNKNOWN.
Before the target completion budget expires, it returns NOT_DUE. At the exact
budget boundary it reads only the pinned identity graph and explicit monthly
run graph for two deterministic run identities. A successful signed control is
required before a missing target can be MISSED. SUCCEEDED/FAILED/HELD/LATE remain
separate; malformed, partial, duplicated, truncated or unavailable evidence is
UNKNOWN. Exceptions report only their class, never remote text.

Target and control must cover the same month, including their start and
completion windows. October26 to November2 crosses months and is UNKNOWN,
even though the UTC occurrence arithmetic is valid. Refresh the retained
control each month. Never broaden a query or substitute another graph after a
zero. The reader reuses existing public registration/signature/event verification
through composition; it never calls the fixed reader's cadence-based measure.
A private compatibility interval used for verifier construction is not evidence
of calendar coverage and is never used for slot selection.

The seam is explicit input, not authenticated producer provenance. Runtime
admission must bind the actual Chaski projection, zone database, declaration,
config and scope. Query and local clocks are caller responsibilities. There is
no ingestion timestamp: newly published on-time signed completion can resolve
MISSED but cannot reconstruct when publication arrived. This is the latest
supplied deadline window, not an audit of every historic slot.

## Demonstration

Run `python scripts/demo-calendar-history.py`. It uses temporary fixture keys
and explicitly mocked graph transport. Watch missing target become MISSED only
with a valid signed control, then SUCCEEDED after signed publication; damaged
control becomes UNKNOWN. The October26 occurrence has a next UTC difference of
608400 seconds across DST. This proves source behavior, not installation,
natural firing or alert delivery. The recording and timing live in
`docs/demos/calendar-history.log` and `.timing`; download and use `scriptreplay`.
