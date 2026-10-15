"""Real signed export fixtures, explicit read-only remote transport doubles."""
from dataclasses import asdict
import re
import unittest
from unittest import mock

from shuttle import export, signing, windows
from shuttle.scheduled_history import ScheduledHistory
from tests import test_scheduled as fixtures


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ScheduledPortTests()
        self.fixture.query = self.query
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.truncated = False
        self.extra = []
        self.failure = None
        self.fixture.start()
        outcome = self.fixture.finish()
        self.fixture.port.publish(self.fixture.run, self.fixture.scope, outcome)
        self.control = self.fixture.slot
        self.history = ScheduledHistory(asdict(self.fixture.scope), public_key=self.fixture.pk,
            registration='urn:example:registration', identity_graph='urn:example:identity',
            anchor_s=self.control, interval_s=60, effective_from_s=self.control,
            deadline_s=20, max_lateness_s=10, eligible=lambda *_: self.fixture.eligible,
            query=self.query)

    def query(self, text, graph):
        f = self.fixture
        f.queries.append((text, graph))
        if self.failure:
            raise self.failure
        if '?verifier' in text:
            self.assertEqual(graph, 'urn:example:identity')
            rows = [dict(f.registration)]
        else:
            self.assertEqual(graph, windows.window_iri('2026-10'))
            requested = set(re.findall(r'<(urn:shuttle:run:[^>]+)>', text))
            events = {row['ev'] for row in f.facts.values()
                      if row['p'] == export.AEGIS+'inRun' and row['value'] in requested}
            rows = [dict(row) for row in f.facts.values() if row['ev'] in events]
            rows += self.extra
        return {'rows': rows, 'count': len(rows), 'truncated': self.truncated}

    def measure(self, **kwargs):
        posts = len(self.fixture.posts)
        with (mock.patch.object(signing, 'load_or_generate', side_effect=AssertionError('private key')),
              mock.patch.object(signing, 'load_existing', side_effect=AssertionError('private key'))):
            result = self.history.measure(now=self.control+80, positive_slot=self.control, **kwargs)
        self.assertEqual(posts, len(self.fixture.posts))
        return result

    def due(self, outcome='succeeded', *, end_offset=2):
        f = self.fixture
        f.slot = self.control+60
        f.run = self.history._run(f.slot)
        f.now = f.slot+1
        f.start()
        f.now = f.slot+end_offset-1
        result = f.finish(outcome, 1 if outcome == 'failed' else 0)
        f.port.publish(f.run, f.scope, result)

    def test_missing_target_with_signed_same_scope_control_is_missed(self):
        result = self.measure()
        self.assertEqual(result['verdict'], 'MISSED')
        self.assertEqual(result['slot'], self.control+60)
        self.assertIn('VALUES ?run', self.fixture.queries[-1][0])

    def test_all_signed_terminal_outcomes_and_late_are_distinct(self):
        for outcome, expected, offset in [('succeeded', 'SUCCEEDED', 2),
                                          ('failed', 'FAILED', 2),
                                          ('skipped-by-hold', 'HELD', 2),
                                          ('succeeded', 'LATE', 21)]:
            with self.subTest(outcome=outcome, offset=offset):
                if len(self.fixture.facts) > 18:
                    self.fixture.facts = dict(list(self.fixture.facts.items())[:18])
                # Each local outbox belongs to one run, never erase it to rerun.
                self.fixture.port.root = self.fixture.base/('runs-'+expected)
                self.due(outcome, end_offset=offset)
                now = self.control+81 if offset == 21 else self.control+80
                result = self.history.measure(now=now, positive_slot=self.control)
                self.assertEqual(result['verdict'], expected)

    def test_running_only_at_deadline_is_missed(self):
        self.due()
        end = export.event_iri(self.history._run(self.control+60), 3)
        self.fixture.facts = {k: v for k, v in self.fixture.facts.items() if v['ev'] != end}
        self.assertEqual(self.measure()['verdict'], 'MISSED')

    def test_empty_history_is_unknown_not_a_healthy_zero(self):
        self.fixture.facts.clear()
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_every_control_fact_is_required_and_integrity_checked(self):
        original = dict(self.fixture.facts)
        for key, row in original.items():
            for mode in ('missing', 'value', 'type', 'duplicate'):
                with self.subTest(predicate=key[1], mode=mode):
                    self.fixture.facts = {k: dict(v) for k, v in original.items()}
                    self.extra = []
                    if mode == 'missing':
                        del self.fixture.facts[key]
                    elif mode == 'value':
                        self.fixture.facts[key]['value'] = 'tampered'
                    elif mode == 'type':
                        self.fixture.facts[key]['iri'] = 1
                    else:
                        self.extra = [dict(row)]
                    self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.fixture.facts, self.extra = original, []

    def test_tampered_due_is_unknown_not_failed(self):
        self.due()
        event = export.event_iri(self.history._run(self.control+60), 3)
        self.fixture.facts[(event, export.AEGIS+'signature')]['value'] = '0'*128
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_failed_positive_control_is_not_coverage(self):
        event = export.event_iri(self.history._run(self.control), 3)
        self.fixture.facts[(event, export.AEGIS+'toState')]['value'] = 'failed'
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_truncated_transport_and_current_eligibility_unknown(self):
        self.truncated = True
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.truncated = False
        self.failure = TimeoutError('credential must not leak')
        self.assertEqual(self.measure(), {'verdict': 'UNKNOWN', 'slot': self.control+60,
                                         'reason': 'TimeoutError'})
        self.failure = None
        for value in (False, None, 1, 'true'):
            self.fixture.eligible = value
            self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_scope_registration_mismatch_unknown(self):
        for field in self.fixture.registration:
            old = self.fixture.registration[field]
            self.fixture.registration[field] = 'wrong'
            self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
            self.fixture.registration[field] = old
        self.fixture.registration['scopeIRI'] = 1
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_partial_target_cannot_be_reported_missing(self):
        self.due()
        event = export.event_iri(self.history._run(self.control+60), 3)
        del self.fixture.facts[(event, export.AEGIS+'sourceKind')]
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_start_outside_window_unknown_even_with_valid_signature(self):
        self.due()
        event = export.event_iri(self.history._run(self.control+60), 2)
        from datetime import datetime, timezone
        at = datetime.fromtimestamp(self.control+71, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        run = export.run_iri(self.history._run(self.control+60))
        sig = signing.sign_transition(self.fixture.scope.agent, run, 'started', 'queued',
                                      'running', at, require_existing_key=True)
        self.fixture.facts[(event, export.PROV+'endedAtTime')]['value'] = at
        self.fixture.facts[(event, export.AEGIS+'signature')]['value'] = sig
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_future_or_reversed_end_unknown_even_with_valid_signature(self):
        self.due()
        from datetime import datetime, timezone
        event = export.event_iri(self.history._run(self.control+60), 3)
        for offset in (59, 81):
            at = datetime.fromtimestamp(self.control+offset, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            sig = signing.sign_transition(self.fixture.scope.agent,
                export.run_iri(self.history._run(self.control+60)), 'succeeded',
                'running', 'succeeded', at, require_existing_key=True)
            self.fixture.facts[(event, export.PROV+'endedAtTime')]['value'] = at
            self.fixture.facts[(event, export.AEGIS+'signature')]['value'] = sig
            self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_clock_and_positive_slot_types_are_strict(self):
        for now, control in ((True, self.control), (1.5, self.control),
                             (self.control+80, True), (self.control+80, self.control+1),
                             (self.control+80, self.control-60)):
            with self.subTest(now=now, control=control):
                self.assertEqual(self.history.measure(now=now, positive_slot=control)['verdict'],
                                 'UNKNOWN')

    def test_month_control_gap_refused_before_query(self):
        count = len(self.fixture.queries)
        result = self.history.measure(now=self.control+32*86400, positive_slot=self.control)
        self.assertEqual(result['verdict'], 'UNKNOWN')
        self.assertEqual(count, len(self.fixture.queries))

    def test_not_due_has_no_query_and_no_healthy_claim(self):
        count = len(self.fixture.queries)
        result = self.history.measure(now=self.control+19, positive_slot=self.control)
        self.assertEqual(result, {'verdict': 'NOT_DUE', 'slot': None})
        self.assertEqual(count, len(self.fixture.queries))

    def test_latest_deadline_passed_slot_derived_locally(self):
        for elapsed, expected in ((79, 'UNKNOWN'), (80, 'MISSED'), (139, 'MISSED'),
                                  (140, 'MISSED')):
            with self.subTest(elapsed=elapsed):
                result = self.history.measure(now=self.control+elapsed, positive_slot=self.control)
                self.assertEqual(result['verdict'], expected)
                self.assertEqual(result['slot'], self.control+((elapsed-20)//60)*60)

    def test_namespace_change_unknown(self):
        with mock.patch.object(export, 'entity_ns', return_value='urn:different:'):
            self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
