"""Single occurrence admission must reject every other slot before graph/key access."""
import io
import json
from unittest import mock

import pytest

from shuttle import scheduled_cli as cli
from shuttle.scheduled import ScheduledRefused
def config():
    return dict(binding={}, host='urn:host', public_key='synthetic', registration='urn:registration',
                identity_graph='urn:identity', state_root='/unused', declaration_graph='urn:jobs',
                eligibility_query='SELECT ?eligible WHERE {} LIMIT 2', anchor_s=600,
                effective_from_s=600, max_lateness_s=60, weekday=0,
                local_time='09:17', timezone='America/New_York')


def policy():
    value = config()
    for key in ('weekday', 'local_time', 'timezone'):
        value.pop(key)
    value['repeat_count'] = 1
    return value


def test_one_exact_integer_slot_and_no_activation_rebase():
    value = policy(); anchor = value['anchor_s']; matches = cli.cadence(value)
    assert matches(anchor)
    for slot in (anchor-60, anchor-1, anchor+1, anchor+60, anchor+86400, True, float(anchor)):
        assert not matches(slot)
    for change in (dict(repeat_count=True), dict(repeat_count=2), dict(repeat_count='1'),
                   dict(interval_s=60), dict(effective_from_s=anchor+60)):
        with pytest.raises(ScheduledRefused): cli.cadence(dict(value, **change))


def test_actual_admission_binds_only_original_slot_before_eligibility_read(tmp_path):
    value = policy(); path = tmp_path/'policy.json'; path.write_text(json.dumps(value))
    scope = dict(job='urn:job', revision='v1', host='urn:host', manifest_sha256='a'*64,
                 agent='agent', workflow='urn:workflow')
    seen = []
    class Port:
        def __init__(self, *args, **kwargs): self.eligible = kwargs['eligible']
        def admit(self, scope, slot):
            if not self.eligible(scope, slot): raise ScheduledRefused('not eligible')
    for slot in (value['anchor_s'], value['anchor_s']+60):
        packet = dict(scope=scope, scheduled_at=slot)
        with mock.patch.object(cli, 'ScheduledRunPort', Port), \
             mock.patch.object(cli.qc, 'query', side_effect=lambda *a, **k: seen.append(1) or
                 dict(rows=[dict(eligible=True)], count=1, truncated=False)), \
             mock.patch('sys.stdin', io.StringIO(json.dumps(packet))):
            args = type('Args', (), dict(action='admit', config=path))()
            if slot == value['anchor_s']: assert cli.run(args) == 0
            else:
                with pytest.raises(ScheduledRefused): cli.run(args)
    assert len(seen) == 1
