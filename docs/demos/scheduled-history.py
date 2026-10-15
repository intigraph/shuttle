"""Source fixture demonstration: no production graph, keys or scheduler."""
import argparse
import importlib.util
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
args = parser.parse_args()
sys.path.insert(0, str(Path(args.source).resolve()))
from shuttle import signing  # noqa: E402

print('Target: source fixture, real Ed25519 signatures, mocked remote graph')
print('Signing control:', callable(signing.verify_transition))
available = importlib.util.find_spec('shuttle.scheduled_history') is not None
print('Signed history reader available:', available)
if available:
    from tests.test_scheduled_history import HistoryTests
    from shuttle import export
    fixture = HistoryTests()
    fixture.setUp()
    try:
        positive = dict(fixture.fixture.facts)
        fixture.fixture.facts.clear()
        print('Empty history:', fixture.measure()['verdict'])
        fixture.fixture.facts = positive
        print('Signed control, missing due run:', fixture.measure()['verdict'])
        fixture.due()
        print('Signed control and completed due run:', fixture.measure()['verdict'])
        event = export.event_iri(fixture.history._run(fixture.control+60), 3)
        fixture.fixture.facts[(event, export.AEGIS+'signature')]['value'] = '0'*128
        print('Damaged target signature:', fixture.measure()['verdict'])
    finally:
        fixture.doCleanups()
else:
    print('Before: no signed-history reader; no deadline verdict available')
