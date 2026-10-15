"""Real temporary signatures and outbox; remote transport is a test double."""
from pathlib import Path
from dataclasses import asdict
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_scheduled import ScheduledPortTests  # noqa: E402
from shuttle import export, signing, state  # noqa: E402
from shuttle.scheduled import ScheduledRefused, ScheduledRunPort  # noqa: E402

warnings.simplefilter('ignore', ResourceWarning)
fixture = ScheduledPortTests(methodName='test_real_signed_lifecycle_export_exact_readback_and_idempotent_republish')
fixture.setUp()
try:
    print('Actual temporary Ed25519 signatures; mocked remote transport; no child process.')
    fixture.start()
    root = next((fixture.base/'runs').iterdir())
    started = state.records(root)[-1]
    verified = signing.verify_transition(fixture.pk, started['signature'], export.run_iri(fixture.run),
        'started', 'queued', 'running', started['at'], fixture.scope.agent)
    print('Signed started persisted and independently verifies:', verified)
    outcome = fixture.finish('skipped-by-hold')
    fixture.port.publish(fixture.run, fixture.scope, outcome)
    print('Signed hold terminal, exact remote-fixture triples:', len(fixture.facts))
    posted = len([x for x in fixture.posts if x[0] == '/knot'])
    fixture.port.publish(fixture.run, fixture.scope, outcome)
    print('Repeat publication adds signatures:', len(state.records(root)) != 4)
    print('Repeat publication adds knot writes:', len([x for x in fixture.posts if x[0] == '/knot']) != posted)
    fixture.corrupt = True
    try:
        fixture.port.publish(fixture.run, fixture.scope, outcome)
    except ScheduledRefused:
        print('Altered remote-fixture triple: REFUSED')
    else:
        raise AssertionError('altered read-back accepted')
    binding = asdict(fixture.scope)
    binding['job'] = 'urn:example:' + 'x'*512
    try:
        ScheduledRunPort(binding, fixture.base/'oversized', host='host-a',
            public_key=fixture.pk, registration='urn:example:registration',
            identity_graph='urn:example:identity', eligible=lambda *_: True)
    except ScheduledRefused:
        print('Oversized real-port scope: REFUSED')
    else:
        raise AssertionError('oversized scope accepted')
    assert verified and len(fixture.facts) == 18
finally:
    fixture.doCleanups()
