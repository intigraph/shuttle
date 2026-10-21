"""Private policy tests: no real keys, graph or child commands."""
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout

from shuttle import scheduled_cli as cli
from shuttle.scheduled import ScheduledRefused


def epoch(value):
    return int(datetime.fromisoformat(value).timestamp())


def config():
    return dict(binding={}, host='urn:host', public_key='synthetic',
                registration='urn:registration', identity_graph='urn:identity',
                state_root='/unused', declaration_graph='urn:jobs',
                eligibility_query='SELECT ?eligible WHERE {} LIMIT 2',
                anchor_s=epoch('2026-10-26T13:17:00+00:00'),
                effective_from_s=epoch('2026-10-26T13:17:00+00:00'),
                max_lateness_s=60, weekday=0, local_time='09:17', timezone='America/New_York')


class CalendarTests(unittest.TestCase):
    def test_actual_process_paired_dst_admission(self):
        policy = config()
        scope = dict(job='urn:job', revision='v1', host='urn:host',
                     manifest_sha256='a'*64, agent='urn:agent', workflow='urn:workflow')
        queries = []

        class Port:
            def __init__(self, *args, eligible, **kwargs):
                self.eligible = eligible

            def admit(self, scope, slot):
                if not self.eligible(scope, slot):
                    raise ScheduledRefused('cadence refused')

        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'config.json'
            path.write_text(json.dumps(policy))
            for slot in (policy['anchor_s'], epoch('2026-11-02T14:17:00+00:00')):
                packet = dict(scope=scope, scheduled_at=slot)
                with mock.patch.object(cli, 'ScheduledRunPort', Port), \
                        mock.patch.object(cli.qc, 'query', side_effect=lambda *a, **k: queries.append(1) or {
                            'rows': [{'eligible': True}], 'count': 1, 'truncated': False}), \
                        mock.patch('sys.stdin', io.StringIO(json.dumps(packet))), redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.run(type('Args', (), dict(action='admit', config=path))()), 0)
        self.assertEqual(len(queries), 2)

    def test_fall_and_spring_no_fixed_seconds(self):
        policy = config()
        policy['anchor_s'] = policy['effective_from_s'] = epoch('2026-03-02T14:17:00+00:00')
        matches = cli.cadence(policy)
        for value in ('2026-03-02T14:17:00+00:00', '2026-03-09T13:17:00+00:00',
                      '2026-10-26T13:17:00+00:00', '2026-11-02T14:17:00+00:00'):
            self.assertTrue(matches(epoch(value)))
        for value in ('2026-11-02T13:17:00+00:00', '2026-11-03T14:17:00+00:00',
                      '2026-11-02T14:17:01+00:00'):
            self.assertFalse(matches(epoch(value)))

    def test_gap_and_both_fold_occurrences_refused(self):
        for time, anchor, slots in (
                ('01:30', '2026-10-25T05:30:00+00:00',
                 ('2026-11-01T05:30:00+00:00', '2026-11-01T06:30:00+00:00')),
                ('02:30', '2026-03-01T07:30:00+00:00',
                 ('2026-03-08T06:30:00+00:00', '2026-03-08T07:30:00+00:00'))):
            policy = config()
            policy.update(weekday=6, local_time=time, anchor_s=epoch(anchor), effective_from_s=epoch(anchor))
            matches = cli.cadence(policy)
            self.assertTrue(matches(epoch(anchor)))
            for value in slots:
                self.assertFalse(matches(epoch(value)))
            policy['anchor_s'] = policy['effective_from_s'] = epoch(slots[0])
            with self.assertRaises(ScheduledRefused):
                cli.cadence(policy)

    def test_fixed_unchanged_and_invalid_forms(self):
        policy = config()
        for key in ('weekday', 'local_time', 'timezone'):
            policy.pop(key)
        policy['interval_s'] = 604800
        matches = cli.cadence(policy)
        self.assertTrue(matches(policy['anchor_s']))
        self.assertFalse(matches(epoch('2026-11-02T14:17:00+00:00')))
        mutations = [dict(interval_s=604800), dict(weekday=True), dict(weekday=7),
                     dict(local_time='09:17:00'), dict(timezone='Not/AZone'),
                     dict(anchor_s=True), dict(effective_from_s=-1), dict(extra=1)]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(ScheduledRefused):
                cli.cadence(dict(config(), **change))
        self.assertFalse(cli.cadence(config())(True))


if __name__ == '__main__':
    unittest.main()
