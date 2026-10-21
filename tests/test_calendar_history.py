"""Real temporary signatures; remote transport explicitly mocked."""
from dataclasses import asdict, replace
from datetime import datetime
import re
import unittest
from unittest import mock

from shuttle import export, signing, windows
from shuttle.calendar_history import CalendarOccurrence, CalendarScheduledHistory
from tests import test_scheduled as fixtures


def at(value):
    return int(datetime.fromisoformat(value).timestamp())


class CalendarHistoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ScheduledPortTests()
        self.f.query = self.query
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.truncated, self.extra, self.failure = False, [], None
        self.control = at('2026-10-19T13:17:00+00:00')
        self.slot = at('2026-10-26T13:17:00+00:00')
        self.next = at('2026-11-02T14:17:00+00:00')
        self.reader = CalendarScheduledHistory(asdict(self.f.scope), weekday=0,
            local_time='09:17', zone='America/New_York', effective_from_s=self.control,
            public_key=self.f.pk, registration='urn:example:registration',
            identity_graph='urn:example:identity', deadline_s=20, max_lateness_s=10,
            eligible=lambda *_: self.f.eligible, query=self.query)
        self.positive = CalendarOccurrence(self.control, self.slot, 'America/New_York')
        self.target = CalendarOccurrence(self.slot, self.next, 'America/New_York')
        self.publish(self.control)

    def publish(self, slot, outcome='succeeded', offset=2):
        f = self.f
        f.slot, f.run = slot, self.reader.verifier._run(slot)
        f.now = slot + 1
        f.port.root = f.base/('run-'+str(slot)+'-'+outcome+'-'+str(offset))
        f.start()
        f.now = slot + offset - 1
        result = f.finish(outcome, 1 if outcome == 'failed' else 0)
        f.port.publish(f.run, f.scope, result)

    def query(self, text, graph):
        f = self.f
        f.queries.append((text, graph))
        if self.failure:
            raise self.failure
        if '?verifier' in text:
            self.assertEqual(graph, 'urn:example:identity')
            rows = [dict(f.registration)]
        else:
            self.assertEqual(graph, windows.window_iri('2026-10'))
            requested = set(re.findall(r'<(urn:shuttle:run:[^>]+)>', text))
            events = {r['ev'] for r in f.facts.values()
                      if r['p'] == export.AEGIS+'inRun' and r['value'] in requested}
            rows = [dict(r) for r in f.facts.values() if r['ev'] in events] + self.extra
        return {'rows': rows, 'count': len(rows), 'truncated': self.truncated}

    def measure(self, **changes):
        args = dict(now=self.slot+20, occurrence=self.target, positive=self.positive)
        args.update(changes)
        posts = len(self.f.posts)
        with mock.patch.object(signing, 'load_or_generate', side_effect=AssertionError('private key')), \
                mock.patch.object(signing, 'load_existing', side_effect=AssertionError('private key')):
            result = self.reader.measure(**args)
        self.assertEqual(len(self.f.posts), posts)
        return result

    def test_paired_missing_and_signed_target(self):
        self.assertEqual(self.measure()['verdict'], 'MISSED')
        self.publish(self.slot)
        result = self.measure()
        self.assertEqual(result['verdict'], 'SUCCEEDED')
        self.assertEqual(result['next_deadline']-result['slot'], 608400)

    def test_failed_held_late_and_running(self):
        for outcome, offset, expected in [('failed', 2, 'FAILED'),
                ('skipped-by-hold', 2, 'HELD'), ('succeeded', 21, 'LATE')]:
            with self.subTest(outcome=outcome):
                self.publish(self.slot, outcome, offset)
                self.assertEqual(self.measure(now=self.slot+22)['verdict'], expected)
        end = export.event_iri(self.reader.verifier._run(self.slot), 3)
        self.f.facts = {k:v for k,v in self.f.facts.items() if v['ev'] != end}
        self.assertEqual(self.measure()['verdict'], 'MISSED')

    def test_empty_partial_tampered_duplicate_truncated_and_transport(self):
        original = dict(self.f.facts)
        for key in original:
            with self.subTest(key=key):
                self.f.facts = dict(original)
                del self.f.facts[key]
                self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.f.facts = dict(original)
        key = next(k for k in original if k[1] == export.AEGIS+'signature')
        self.f.facts[key] = dict(original[key], value='0'*128)
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.f.facts = original
        self.extra = [dict(next(iter(original.values())))]
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.extra, self.truncated = [], True
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.truncated, self.failure = False, TimeoutError('secret must not leak')
        self.assertNotIn('secret', str(self.measure()))
        self.failure = None
        self.f.facts = {}
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_eligibility_registration_and_namespace(self):
        for value in (False, None, 1, 'true'):
            self.f.eligible = value
            self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.f.eligible = True
        self.f.registration['scopeIRI'] = 1
        self.assertEqual(self.measure()['verdict'], 'UNKNOWN')
        self.f.registration['scopeIRI'] = True
        with mock.patch.object(export, 'entity_ns', return_value='urn:changed:'):
            self.assertEqual(self.measure()['verdict'], 'UNKNOWN')

    def test_invalid_or_stale_occurrences_refuse_without_queries(self):
        count = len(self.f.queries)
        for target in (replace(self.target, zone='UTC'), replace(self.target, scheduled_at=True),
                       replace(self.target, next_deadline=self.slot+604800),
                       replace(self.target, scheduled_at=self.slot+1)):
            self.assertEqual(self.measure(occurrence=target)['verdict'], 'UNKNOWN')
        self.assertEqual(self.measure(now=self.next+20)['verdict'], 'UNKNOWN')
        self.assertEqual(self.measure(positive=self.target)['verdict'], 'UNKNOWN')
        self.assertEqual(self.measure(now=True)['verdict'], 'UNKNOWN')
        self.assertEqual(self.measure(now=self.slot-1)['verdict'], 'UNKNOWN')
        self.assertEqual(len(self.f.queries), count)
        self.assertEqual(self.measure(now=self.slot+19)['verdict'], 'NOT_DUE')
        self.assertEqual(len(self.f.queries), count)

    def test_cross_month_and_completion_window_unknown(self):
        count = len(self.f.queries)
        nov = CalendarOccurrence(self.next, at('2026-11-09T14:17:00+00:00'), self.target.zone)
        self.assertEqual(self.measure(now=self.next+20, occurrence=nov, positive=self.target)['verdict'], 'UNKNOWN')
        self.reader.verifier.deadline = 604800
        self.assertEqual(self.measure(now=self.slot+604800)['verdict'], 'UNKNOWN')
        self.assertEqual(len(self.f.queries), count)

    def test_dst_gap_both_fold_and_spring(self):
        # Validate explicit source occurrences independently of graph month coverage.
        self.reader.effective = 0
        spring = CalendarOccurrence(at('2026-03-02T14:17:00+00:00'),
                                    at('2026-03-09T13:17:00+00:00'), self.target.zone)
        self.assertEqual(self.reader._occurrence(spring), spring.scheduled_at)
        self.assertEqual(spring.next_deadline-spring.scheduled_at, 601200)
        self.reader.weekday, self.reader.hour, self.reader.minute = 6, 1, 30
        for stamp in ('2026-11-01T05:30:00+00:00', '2026-11-01T06:30:00+00:00'):
            with self.assertRaises(Exception):
                self.reader._occurrence(CalendarOccurrence(at(stamp), at('2026-11-08T06:30:00+00:00'), self.target.zone))
        self.reader.hour = 2
        for stamp in ('2026-03-08T06:30:00+00:00', '2026-03-08T07:30:00+00:00'):
            with self.assertRaises(Exception):
                self.reader._occurrence(CalendarOccurrence(at(stamp), at('2026-03-15T06:30:00+00:00'), self.target.zone))


if __name__ == '__main__':
    unittest.main()
