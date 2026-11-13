#!/usr/bin/env python3
"""Private before/after RDF builder replay; no network, keys or graph writes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from shuttle import export, signing

BASE = '0b6b8492497c6f9e83027efb624f7e3a6dc13188'
OLD = 'http://aegis.gastown.local/ontology/'


def load(directory, name):
    path = directory / (name + '.py')
    path.write_bytes(subprocess.check_output(
        ['git', '-C', str(ROOT), 'show', BASE + ':shuttle/' + name + '.py']))
    spec = importlib.util.spec_from_file_location('shuttle._baseline_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def measure(label, writer, signer):
    record = {'run': 'example', 'definition': 'example', 'state': 'open',
              'at': '2026-11-13T00:00:00Z', 'agent': 'fixture', 'step': 'claim',
              'from': 'open', 'to': 'claimed', 'signature': 'ab' * 64}
    with mock.patch.object(signer, 'public_key_hex', return_value='cd' * 32):
        bodies = [writer.definition_turtle({'name': 'example', 'transitions': [{'step': 'claim'}]}),
                  writer.start_turtle(record), writer.transition_turtle(record, 3),
                  signer.registration_turtle('fixture', 'urn:shuttle:workflow:example')]
    old = sum(OLD in body for body in bodies)
    result = {'source': label, 'builders': len(bodies), 'builders_with_legacy_vocabulary': old,
              'run_identity': writer.run_iri('example'),
              'signature_hex_unchanged': record['signature'] in bodies[2]}
    print(json.dumps(result, sort_keys=True), flush=True)
    assert old == (4 if label == 'base' else 0)
    assert result['run_identity'] == 'urn:shuttle:run:example'
    assert result['signature_hex_unchanged']


with tempfile.TemporaryDirectory() as directory, \
        mock.patch.dict('os.environ', {'SHUTTLE_ENTITY_NS': 'urn:shuttle:'}):
    print('Same private records: definition, start, transition and registration builders.')
    measure('base', load(Path(directory), 'export'), load(Path(directory), 'signing'))
    measure('candidate', export, signing)
    from shuttle import vocabulary
    try:
        vocabulary.term('UnknownTerm')
    except KeyError:
        print('PASS: unknown vocabulary owner refuses; no legacy fallback.')
    else:
        raise AssertionError('unknown term accepted')
