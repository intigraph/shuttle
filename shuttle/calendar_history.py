"""Opt-in calendar signed history; no timer, private key or mutation.

Chaski owns occurrence selection. This reader validates explicit occurrence
coverage against pinned weekly policy, then reuses fixed-reader signature
verification without calling its fixed-cadence measure method.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from . import export, windows
from .scheduled import ScheduledRefused, _rows
from .scheduled_history import ScheduledHistory


@dataclass(frozen=True)
class CalendarOccurrence:
    scheduled_at: int
    next_deadline: int
    zone: str


class CalendarScheduledHistory:
    """Explicit Chaski WeeklyProjection seam; next_deadline is next occurrence.

    deadline_s is the separate signed completion budget. Supplied occurrences
    are not authenticated by this class; the caller must retain their admitted
    Chaski/declaration provenance and the control's natural origin.
    """
    def __init__(self, binding, *, weekday, local_time, zone, effective_from_s,
                 public_key, registration, identity_graph, deadline_s,
                 max_lateness_s, eligible, query=None):
        if (type(weekday) is not int or not 0 <= weekday <= 6 or
                type(local_time) is not str or
                not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', local_time) or
                type(zone) is not str or not 0 < len(zone) <= 255):
            raise ScheduledRefused('pinned weekday/HH:MM/IANA zone required')
        self.zone = ZoneInfo(zone)
        self.zone_name, self.weekday = zone, weekday
        self.hour, self.minute = map(int, local_time.split(':'))
        self.effective = effective_from_s
        # Only reuse exact public-key/registration/event verifiers. The fixed
        # cadence below is NEVER used to derive or validate calendar coverage.
        self.verifier = ScheduledHistory(binding, public_key=public_key,
            registration=registration, identity_graph=identity_graph,
            anchor_s=effective_from_s, interval_s=60, effective_from_s=effective_from_s,
            deadline_s=deadline_s, max_lateness_s=max_lateness_s,
            eligible=eligible, query=query)

    def _utc(self, day):
        local = datetime(day.year, day.month, day.day, self.hour, self.minute)
        candidates = set()
        for fold in (0, 1):
            utc = local.replace(tzinfo=self.zone, fold=fold).astimezone(timezone.utc)
            if utc.astimezone(self.zone).replace(tzinfo=None) == local:
                candidates.add(int(utc.timestamp()))
        if len(candidates) != 1:
            raise ScheduledRefused('gap or overlap in calendar occurrence')
        return candidates.pop()

    def _occurrence(self, value):
        if (type(value) is not CalendarOccurrence or value.zone != self.zone_name or
                any(type(s) is not int or not 0 <= s <= 253402214400
                    for s in (value.scheduled_at, value.next_deadline)) or
                value.scheduled_at < self.effective):
            raise ScheduledRefused('bounded pinned-zone occurrence required')
        day = datetime.fromtimestamp(value.scheduled_at, self.zone).date()
        if (day.weekday() != self.weekday or self._utc(day) != value.scheduled_at or
                self._utc(day + timedelta(days=7)) != value.next_deadline):
            raise ScheduledRefused('canonical occurrence and next local week required')
        return value.scheduled_at

    def measure(self, *, now, occurrence, positive):
        """Latest deadline-passed explicit occurrence, never fixed-week inference."""
        slot = None
        v = self.verifier
        try:
            if type(now) is not int or not 0 <= now <= 253402214400:
                raise ScheduledRefused('bounded integer UTC clock required')
            slot = self._occurrence(occurrence)
            control = self._occurrence(positive)
            if (export.entity_ns(), windows.window_ns()) != (v.namespace, v.window_namespace):
                raise ScheduledRefused('namespace changed during measurement')
            if now < slot:
                raise ScheduledRefused('future occurrence does not cover current time')
            if control >= slot:
                raise ScheduledRefused('prior natural signed positive control required')
            if now >= occurrence.next_deadline + v.deadline:
                raise ScheduledRefused('stale occurrence does not cover current deadline')
            month = v._month(slot)
            # Cover the entire signed start/completion windows, not merely the
            # scheduled instants. Never broaden into another graph on a zero.
            if any(v._month(s + offset) != month
                   for s in (control, slot) for offset in (0, v.lateness, v.deadline)):
                raise ScheduledRefused('same-month control and completion coverage required')
            if now < slot + v.deadline:
                return {'verdict': 'NOT_DUE', 'slot': None}
            if any(v.eligible(dict(v.binding), s) is not True for s in (control, slot)):
                raise ScheduledRefused('current declaration eligibility unavailable')
            a = export.AEGIS
            registration = _rows(v.query(
                f'SELECT ?verifier ?pk ?workflow (isIRI(?workflow) AS ?scopeIRI) WHERE {{ '
                f'<{v.registration}> a ?type ; <{a}verifier> ?verifier ; '
                f'<{a}publicKey> ?pk ; <{a}attests> ?workflow . '
                f'FILTER(?type = <{a}VerifierRegistration>) }} LIMIT 8',
                graph=v.identity_graph), 8)
            if registration != [{'verifier': v.binding['agent'], 'pk': v.public_key,
                                 'workflow': v.binding['workflow'], 'scopeIRI': True}] or \
                    registration[0].get('scopeIRI') is not True:
                raise ScheduledRefused('exact public registration unavailable')
            runs = [v._run(s) for s in (control, slot)]
            rows = _rows(v.query(
                'SELECT (STR(?event) AS ?ev) (STR(?predicate) AS ?p) '
                '(STR(?raw) AS ?value) (isIRI(?raw) AS ?iri) '
                '(STR(DATATYPE(?raw)) AS ?datatype) WHERE { VALUES ?run { '
                + ' '.join('<'+export.run_iri(run)+'>' for run in runs) + ' } '
                + f'?event <{a}inRun> ?run ; ?predicate ?raw }} LIMIT 64',
                graph=windows.window_iri(month)), 64)
            grouped = [[r for r in rows if r.get('ev') in
                        (export.event_iri(run, 2), export.event_iri(run, 3))] for run in runs]
            if sum(map(len, grouped)) != len(rows):
                raise ScheduledRefused('unexpected event outside exact coverage')
            if v._outcome(grouped[0], control, now) != 'SUCCEEDED':
                raise ScheduledRefused('successful signed positive control unavailable')
            return {'verdict': v._outcome(grouped[1], slot, now), 'slot': slot,
                    'positive_slot': control, 'graph': windows.window_iri(month),
                    'next_deadline': occurrence.next_deadline, 'zone': self.zone_name}
        except Exception as exc:
            return {'verdict': 'UNKNOWN', 'slot': slot, 'reason': type(exc).__name__}
