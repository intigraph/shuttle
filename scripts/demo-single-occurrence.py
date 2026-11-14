"""Pure one-slot cadence demo; --before points to the base scheduled_cli source."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from shuttle import scheduled_cli as current
from shuttle.scheduled import ScheduledRefused
args=argparse.ArgumentParser();args.add_argument('--before',type=Path);args=args.parse_args()
policy=dict(binding={},host='urn:test:host',public_key='synthetic',registration='urn:test:key',
    identity_graph='urn:test:identity',state_root='/unused',declaration_graph='urn:test:jobs',
    eligibility_query='SELECT ?eligible WHERE {} LIMIT 2',anchor_s=600,effective_from_s=600,
    max_lateness_s=59,repeat_count=1)
if args.before:
    spec=importlib.util.spec_from_file_location('shuttle.scheduled_cli_before',args.before)
    before=importlib.util.module_from_spec(spec);sys.modules[spec.name]=before;spec.loader.exec_module(before)
    try:before.cadence(policy)
    except ScheduledRefused as exc:print('BASE: REFUSED',str(exc))
    else:raise AssertionError('base unexpectedly accepted single occurrence')
matches=current.cadence(policy)
for slot in (599,600,601,660,86400):print('CANDIDATE slot',slot,'eligible cadence',matches(slot))
assert matches(600) and not any(matches(slot) for slot in (599,601,660,86400))
print('Local cadence only; no graph, key, signing, process or scheduler access.')
