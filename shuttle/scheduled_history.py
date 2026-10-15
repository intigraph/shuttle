"""Read-only deadline evidence for one pinned fixed-interval schedule.

# arming: library; caller owns polling, alert delivery and current eligibility.
No key access, execution, mutation or implicit default-graph search. A retained
prior successful slot is the positive control, in the same explicit month.
Caller must establish that control came from the intended natural schedule.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re

from . import export, quipu_client, signing, windows
from .scheduled import ScheduledRefused, _FIELDS, _RDF, _XSD, _iri, _rows


class ScheduledHistory:
    """Verify remote transitions using only an operator-pinned public key.

    Deadline is the signed completion budget, measured from slot UTC. Missing
    published completion at polling time is MISSED; graph ingestion timestamps
    are unavailable, so a late publication of an on-time end cannot be dated.
    Calendar schedules are unsupported. UNKNOWN is never an empty success.
    Shared-uid verifiability does not establish isolated authorship.
    """

    def __init__(self, binding, *, public_key, registration, identity_graph,
                 anchor_s, interval_s, effective_from_s, deadline_s,
                 max_lateness_s, eligible, query=None):
        if (type(binding) is not dict or set(binding) != _FIELDS or
                any(type(v) is not str or not v or len(v) > 256
                    for v in binding.values()) or
                not re.fullmatch('[0-9a-f]{64}', binding['manifest_sha256'])):
            raise ScheduledRefused('complete bounded immutable scope required')
        if (type(public_key) is not str or
                not re.fullmatch('[0-9a-f]{64}', public_key)):
            raise ScheduledRefused('pinned Ed25519 public key required')
        prefix = export.workflow_iri('')
        if (not binding['workflow'].startswith(prefix) or
                not re.fullmatch('[A-Za-z0-9_-]+', binding['workflow'][len(prefix):])):
            raise ScheduledRefused('workflow outside configured namespace')
        for value in (anchor_s, interval_s, effective_from_s, deadline_s, max_lateness_s):
            if type(value) is not int or not 0 <= value <= 253402214400:
                raise ScheduledRefused('bounded integer timing required')
        if not 1 <= interval_s <= 31536000 or not 1 <= deadline_s <= 604800:
            raise ScheduledRefused('bounded positive interval and deadline required')
        if not 0 <= max_lateness_s <= min(deadline_s, 86400) or not callable(eligible):
            raise ScheduledRefused('current eligibility and bounded lateness required')
        self.binding = dict(binding)
        self.public_key = public_key
        self.registration, self.identity_graph = _iri(registration), _iri(identity_graph)
        self.anchor, self.interval = anchor_s, interval_s
        self.effective, self.deadline = effective_from_s, deadline_s
        self.lateness, self.eligible = max_lateness_s, eligible
        self.query = query or quipu_client.query
        self.namespace, self.window_namespace = export.entity_ns(), windows.window_ns()

    def _run(self, slot):
        raw = json.dumps({**self.binding, 'scheduled_at': slot, 'version': 1},
                         sort_keys=True, separators=(',', ':')).encode()
        return 'scheduled-v1-' + base64.urlsafe_b64encode(raw).decode().rstrip('=')

    @staticmethod
    def _at(value):
        if type(value) is not str:
            raise ScheduledRefused('UTC timestamp required')
        stamp = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        if stamp.strftime('%Y-%m-%dT%H:%M:%SZ') != value:
            raise ScheduledRefused('canonical UTC timestamp required')
        return int(stamp.timestamp())

    def _month(self, slot):
        return datetime.fromtimestamp(slot, timezone.utc).strftime('%Y-%m')

    def _event(self, rows, run, seq, step, old, new):
        event = export.event_iri(run, seq)
        values = {row['p']: row['value'] for row in rows}
        a = export.AEGIS
        at, signature = values.get(export.PROV+'endedAtTime'), values.get(a+'signature')
        expected = [(_RDF+'type', a+'TransitionEvent', True),
                    (a+'inRun', export.run_iri(run), True),
                    (a+'atStep', self.binding['workflow']+'/step/'+step, True),
                    (a+'fromState', old, False), (a+'toState', new, False),
                    (export.PROV+'endedAtTime', at, False),
                    (a+'performedBy', self.namespace+'agent:'+self.binding['agent'], True),
                    (a+'signature', signature, False), (a+'sourceKind', 'observed', False)]
        actual = set()
        for row in rows:
            if (set(row) - {'ev', 'p', 'value', 'iri', 'datatype'} or
                    type(row.get('iri')) is not bool or
                    any(type(row.get(k)) is not str for k in ('ev', 'p', 'value'))):
                raise ScheduledRefused('typed transition facts required')
            actual.add((row['ev'], row['p'], row['value'], row['iri'],
                        None if row['iri'] else row.get('datatype')))
        wanted = {(event, p, value, iri, None if iri else _XSD+'string')
                  for p, value, iri in expected}
        if len(rows) != 9 or actual != wanted:
            raise ScheduledRefused('exact transition facts unavailable')
        if not signing.verify_transition(self.public_key, signature, export.run_iri(run),
                                         step, old, new, at, self.binding['agent']):
            raise ScheduledRefused('remote signature invalid')
        return self._at(at)

    def _outcome(self, rows, slot, now):
        if not rows:
            return 'MISSED'
        run = self._run(slot)
        start = [r for r in rows if r.get('ev') == export.event_iri(run, 2)]
        end = [r for r in rows if r.get('ev') == export.event_iri(run, 3)]
        if len(rows) != len(start) + len(end):
            raise ScheduledRefused('unexpected event in exact run history')
        started = self._event(start, run, 2, 'started', 'queued', 'running')
        if not slot <= started <= min(now, slot+self.lateness):
            raise ScheduledRefused('signed start outside admitted slot')
        if not end:
            return 'MISSED'
        terminal = next((r.get('value') for r in end
                         if r.get('p') == export.AEGIS+'toState'), None)
        if terminal not in ('succeeded', 'failed', 'skipped-by-hold'):
            raise ScheduledRefused('unknown signed terminal')
        ended = self._event(end, run, 3, terminal, 'running', terminal)
        if not started <= ended <= now:
            raise ScheduledRefused('signed terminal chronology invalid')
        if ended > slot+self.deadline:
            return 'LATE'
        return {'succeeded': 'SUCCEEDED', 'failed': 'FAILED', 'skipped-by-hold': 'HELD'}[terminal]

    def measure(self, *, now, positive_slot):
        """Return verdict and exact target. Any incomplete instrument is UNKNOWN."""
        slot = None
        try:
            if (type(now) is not int or not 0 <= now <= 253402214400 or
                    type(positive_slot) is not int or positive_slot < 0):
                raise ScheduledRefused('explicit bounded UTC clock and control required')
            if (export.entity_ns(), windows.window_ns()) != (self.namespace, self.window_namespace):
                raise ScheduledRefused('namespace changed during measurement')
            slot = self.anchor + ((now-self.deadline-self.anchor)//self.interval)*self.interval
            first = self.anchor + max(0, (self.effective-self.anchor+self.interval-1)//self.interval)*self.interval
            if slot < first:
                return {'verdict': 'NOT_DUE', 'slot': None}
            if (positive_slot < first or positive_slot >= slot or
                    (positive_slot-self.anchor) % self.interval):
                raise ScheduledRefused('prior aligned eligible control required')
            month = self._month(slot)
            if any(self._month(s) != month or self._month(s+self.lateness) != month
                   for s in (positive_slot, slot)):
                raise ScheduledRefused('positive control must cover the same unambiguous month')
            if any(self.eligible(dict(self.binding), s) is not True for s in (positive_slot, slot)):
                raise ScheduledRefused('current declaration eligibility unavailable')
            a = export.AEGIS
            registration = _rows(self.query(
                f'SELECT ?verifier ?pk ?workflow (isIRI(?workflow) AS ?scopeIRI) WHERE {{ '
                f'<{self.registration}> a ?type ; <{a}verifier> ?verifier ; '
                f'<{a}publicKey> ?pk ; <{a}attests> ?workflow . '
                f'FILTER(?type = <{a}VerifierRegistration>) }} LIMIT 8',
                graph=self.identity_graph), 8)
            if (len(registration) != 1 or registration[0].get('scopeIRI') is not True or
                    registration != [{'verifier': self.binding['agent'], 'pk': self.public_key,
                                  'workflow': self.binding['workflow'], 'scopeIRI': True}]):
                raise ScheduledRefused('exact public registration unavailable')
            runs = [self._run(s) for s in (positive_slot, slot)]
            iris = [export.run_iri(run) for run in runs]
            rows = _rows(self.query(
                'SELECT (STR(?event) AS ?ev) (STR(?predicate) AS ?p) '
                '(STR(?raw) AS ?value) (isIRI(?raw) AS ?iri) '
                '(STR(DATATYPE(?raw)) AS ?datatype) WHERE { VALUES ?run { '
                + ' '.join('<'+iri+'>' for iri in iris) + ' } '
                + f'?event <{a}inRun> ?run ; ?predicate ?raw }} LIMIT 64',
                graph=windows.window_iri(month)), 64)
            grouped = [[r for r in rows if r.get('ev') in
                        (export.event_iri(run, 2), export.event_iri(run, 3))] for run in runs]
            if sum(map(len, grouped)) != len(rows):
                raise ScheduledRefused('unexpected event outside exact target coverage')
            if self._outcome(grouped[0], positive_slot, now) != 'SUCCEEDED':
                raise ScheduledRefused('same-scope successful signed positive control unavailable')
            return {'verdict': self._outcome(grouped[1], slot, now), 'slot': slot,
                    'positive_slot': positive_slot, 'graph': windows.window_iri(month)}
        except Exception as exc:
            # Transport/parser/crypto/callback failures all preserve UNKNOWN.
            # Do not copy exception text, which may contain remote credentials.
            return {'verdict': 'UNKNOWN', 'slot': slot, 'reason': type(exc).__name__}
