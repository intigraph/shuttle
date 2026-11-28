"""Phase zero acceptance and negative controls against the exported record."""
import json
from pathlib import Path
from unittest import mock

from shuttle import export, quipu_client as qc, signing, state
from tests import test_export_and_cli as base


class CompleteRecord(base.EnvIsolatedCase):
    _define = base.CliFlowTests._define

    def flow(self):
        path = Path(self._define())
        raw = json.loads(path.read_text())
        raw['evidence'] = {'review': 'https://example.org/review', 'note': 'a "quote"\nnext'}
        raw['transitions'][0]['seed'] = {'title': 'Work', 'labels': ['build']}
        path.write_text(json.dumps(raw))
        self.assertEqual(0, self.run_cli('define', str(path))[0])
        self.assertEqual(0, self.run_cli('start', 'triage', 'r1', '--agent', 'agent-a')[0])
        from shuttle import cli
        defs, runs = cli._index()
        cli._advance(defs['triage'], runs['r1'], 'r1', 'open', 'claim', 'agent-a',
                     '2026-11-28T06:00:00Z', {'seed': 'example-1', 'outcome': 'done'})
        return raw

    def export_records(self):
        self.assertEqual([], export.export()['quarantined'])
        records = []
        marker = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#value> '
        for path, body in self.posts:
            if path == '/knot':
                for line in body['turtle'].splitlines():
                    if marker in line:
                        records.append(json.loads(json.loads(line.split(marker)[1][:-2])))
        return records

    def test_whole_definition_and_evidence_round_trip_through_turtle(self):
        raw = self.flow()
        records = self.export_records()
        definition = next(r for r in records if r['type'] == 'define')
        for key, value in raw.items():
            self.assertEqual(value, definition[key])
        event = next(r for r in records if r['type'] == 'transition')
        self.assertEqual({'seed': 'example-1', 'outcome': 'done'}, event['evidence'])

    def test_redefinition_refuses_without_changing_log(self):
        self.flow()
        before = state.records()
        self.assertEqual(2, self.run_cli('define', self._define())[0])
        self.assertEqual(before, state.records())

    def test_start_signature_binds_each_start_field_and_export_refuses_tampering(self):
        self.flow()
        start = next(r for r in state.records() if r['type'] == 'start')
        pk = signing.public_key_hex('agent-a')
        self.assertTrue(signing.verify_start(pk, start, export.run_iri('r1')))
        for key in ('definition', 'state', 'at', 'agent', 'signature'):
            self.assertFalse(signing.verify_start(pk, {**start, key: 'tampered'}, export.run_iri('r1')))
        self.assertFalse(signing.verify_start(pk, start, export.run_iri('other')))
        log = Path(self._state.name) / 'runs.jsonl'
        log.write_text(log.read_text().replace('"state": "open"', '"state": "done"'))
        with self.assertRaises(export.ExportError):
            export.export()
        self.assertEqual(1, state.watermark())

    def test_verify_survives_deleted_local_log_and_keys_then_rejects_remote_tamper(self):
        self.flow()
        records = self.export_records()
        start = next(r for r in records if r['type'] == 'start')
        event = next(r for r in records if r['type'] == 'transition')
        pk = signing.public_key_hex('agent-a')
        (Path(self._state.name) / 'runs.jsonl').unlink()
        (Path(self._keys.name) / 'agent-a.pk8').unlink()
        calls = []

        def query(sparql, **scope):
            calls.append(scope)
            if 'SELECT DISTINCT ?at' in sparql:
                return {'rows': [{'at': start['at']}]}
            if 'SELECT ?record' in sparql:
                return {'rows': [{'record': json.dumps(start)}]}
            if '?verifier ?pk' in sparql:
                return {'rows': [{'verifier': 'agent-a', 'pk': pk}]}
            return {'rows': [{'ev': 'urn:shuttle:event:r1:2',
                'step': 'urn:shuttle:workflow:triage/step/claim', 'from': event['from'],
                'to': event['to'], 'at': event['at'], 'agent': 'urn:shuttle:agent:agent-a',
                'sig': event['signature']}]}

        with mock.patch.object(qc, 'query', side_effect=query), \
             mock.patch.object(state, 'records', side_effect=AssertionError('local read')), \
             mock.patch.object(signing, 'load_or_generate', side_effect=AssertionError('key read')):
            self.assertEqual(0, self.run_cli('verify', 'r1')[0])
            event['to'] = 'done'
            self.assertEqual(1, self.run_cli('verify', 'r1')[0])
            start['state'] = 'changed'
            self.assertEqual(1, self.run_cli('verify', 'r1')[0])
        self.assertEqual(['operational', 'archive'], calls[0]['include_kinds'])

    def test_verify_refuses_missing_start_and_truncated_discovery(self):
        for result in ({'rows': []}, {'rows': [], 'truncated': True}):
            with mock.patch.object(qc, 'query', return_value=result):
                self.assertEqual(2, self.run_cli('verify', 'missing')[0])

    def test_imported_start_is_signed_by_importer(self):
        at = '2026-11-28T06:00:00Z'
        definition = json.loads(Path(self._define()).read_text())
        path = Path(self._state.name) / 'foreign.jsonl'
        path.write_text(json.dumps({**definition, 'type': 'define', 'at': at}) + '\n' +
                        json.dumps({'type': 'start', 'run': 'imported', 'definition': 'triage',
                                    'state': 'open', 'agent': 'original', 'at': at}) + '\n')
        self.assertEqual(0, self.run_cli('import-run', str(path), '--agent', 'importer')[0])
        start = state.records()[-1]
        self.assertTrue(signing.verify_start(signing.public_key_hex('importer'), start,
                                            export.run_iri('imported')))
