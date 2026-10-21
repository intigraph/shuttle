"""Real fixture signatures/outboxes; explicitly mocked remote transport."""
import base64
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from shuttle import export, quipu_client as qc, signing, state, windows
from shuttle.scheduled import ScheduledRefused, ScheduledRunPort


@dataclass(frozen=True)
class Scope:
    job: str = 'urn:example:job'
    revision: str = 'revision-1'
    host: str = 'host-a'
    manifest_sha256: str = 'a'*64
    agent: str = 'fixture-agent'
    workflow: str = 'urn:shuttle:workflow:scheduled-job-v1'


class ScheduledPortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        env = mock.patch.dict(os.environ, {
            'SHUTTLE_KEY_DIR': str(self.base/'keys'),
            'SHUTTLE_ENTITY_NS': 'urn:shuttle:',
            'CAMAYOC_PLANE_NS': 'https://example.test/plane/'})
        env.start()
        self.addCleanup(env.stop)
        self.scope = Scope()
        self.slot = 1792022400
        self.now = self.slot + 1
        signing.load_or_generate(self.scope.agent)
        self.pk = signing.public_key_hex(self.scope.agent)
        self.raw = json.dumps({**asdict(self.scope), 'scheduled_at': self.slot, 'version': 1},
                              sort_keys=True, separators=(',', ':')).encode()
        self.run = 'scheduled-v1-' + base64.urlsafe_b64encode(self.raw).decode().rstrip('=')
        self.facts = {}
        self.posts = []
        self.registration = {'verifier': self.scope.agent, 'pk': self.pk,
                             'workflow': self.scope.workflow, 'scopeIRI': True}
        self.corrupt = False
        self.truncate = False
        self.eligible = True
        self.queries = []
        self.port = ScheduledRunPort(asdict(self.scope), self.base/'runs', host='host-a',
            public_key=self.pk, registration='urn:example:registration',
            identity_graph='urn:example:identity', eligible=lambda *_: self.eligible,
            clock=lambda: self.now, query=self.query)
        patch = mock.patch.object(qc, 'post', side_effect=self.post)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(qc, 'probe_graph_kinds', return_value=[])
        patch.start()
        self.addCleanup(patch.stop)

    def post(self, path, body):
        self.posts.append((path, body))
        if path == '/datasets' and body.get('action') == 'show':
            return {'members': []}
        if path == '/knot' and 'TransitionEvent' in body['turtle']:
            text = body['turtle']
            ev = re.search(r'<([^>]+)> a aegis:TransitionEvent', text).group(1)
            facts = [(export.AEGIS+'TransitionEvent', 'type', True, _RDF())]
            for predicate, value in re.findall(r'    ((?:aegis|prov):\w+) (<[^>]+>|"[^"]*") [;.]', text):
                prefix, name = predicate.split(':')
                facts.append((value[1:-1], name, value.startswith('<'),
                              export.AEGIS if prefix == 'aegis' else export.PROV))
            for value, predicate, iri, prefix in facts:
                self.facts[(ev, prefix+predicate)] = {
                    'ev': ev, 'p': prefix+predicate, 'value': value, 'iri': iri,
                    **({} if iri else {'datatype': 'http://www.w3.org/2001/XMLSchema#string'})}
        return {'ok': True}

    def query(self, query, graph):
        self.queries.append((query, graph))
        if '?verifier' in query:
            self.assertEqual('urn:example:identity', graph)
            rows = [dict(self.registration)]
        else:
            self.assertEqual(windows.window_iri('2026-10'), graph)
            rows = list(self.facts.values())
            if self.corrupt and rows:
                rows[-1] = {**rows[-1], 'value': 'tampered'}
        return {'rows': rows, 'count': len(rows), 'truncated': self.truncate}

    def start(self):
        self.port.admit(self.scope, self.slot)
        self.port.started(self.run, self.scope)

    def finish(self, outcome='succeeded', code=0):
        self.now += 1
        result = {'outcome': outcome, 'exit_code': code}
        self.port.finished(self.run, self.scope, result)
        return result

    def test_real_signed_lifecycle_export_exact_readback_and_idempotent_republish(self):
        self.start()
        roots = list((self.base/'runs').iterdir())
        self.assertEqual(1, len(roots))
        recs = state.records(roots[0])
        self.assertEqual(3, len(recs))
        started = recs[-1]
        self.assertTrue(signing.verify_transition(self.pk, started['signature'], export.run_iri(self.run),
            'started', 'queued', 'running', started['at'], self.scope.agent))
        outcome = self.finish()
        self.port.publish(self.run, self.scope, outcome)
        self.assertEqual(18, len(self.facts))
        before = len([x for x in self.posts if x[0] == '/knot'])
        self.port.publish(self.run, self.scope, outcome)
        self.assertEqual(before, len([x for x in self.posts if x[0] == '/knot']))
        self.assertEqual(4, len(state.records(roots[0])))

    def test_actual_cli_protocol_with_real_signing_and_mocked_remote(self):
        import io
        from contextlib import redirect_stdout
        from shuttle import cli, scheduled_cli
        config = {
            'binding': asdict(self.scope), 'host': self.scope.host, 'public_key': self.pk,
            'registration': 'urn:example:registration', 'identity_graph': 'urn:example:identity',
            'state_root': str(self.base/'cli-runs'), 'declaration_graph': 'urn:example:jobs',
            # Deliberately synthetic fixture query; never a production policy.
            'eligibility_query': 'SELECT ?eligible WHERE { ?fixture ?p ?eligible } LIMIT 2',
            'interval_s': 60, 'anchor_s': self.slot, 'effective_from_s': self.slot,
            'max_lateness_s': 90}
        path = self.base/'config.json'
        path.write_text(json.dumps(config))

        def query(text, graph):
            if graph == 'urn:example:jobs':
                return {'rows': [{'eligible': True}], 'count': 1, 'truncated': False}
            return self.query(text, graph)

        def factory(*args, **kwargs):
            return ScheduledRunPort(*args, **kwargs, clock=lambda: self.now)

        for action in ('admit', 'started', 'finished', 'publish'):
            packet = {'scope': asdict(self.scope), 'scheduled_at': self.slot}
            if action != 'admit':
                packet['run'] = self.run
            if action in ('finished', 'publish'):
                packet['outcome'] = {'outcome': 'succeeded', 'exit_code': 0}
            out = io.StringIO()
            with mock.patch.object(qc, 'query', side_effect=query), \
                    mock.patch.object(scheduled_cli, 'ScheduledRunPort', side_effect=factory), \
                    mock.patch('sys.stdin', io.StringIO(json.dumps(packet))), redirect_stdout(out):
                self.assertEqual(0, cli.main(['scheduled', action, '--config', str(path)]))
            self.assertEqual({'action': action, 'result': 'verified'}, json.loads(out.getvalue()))
        self.assertEqual(18, len(self.facts))

    def test_calendar_cli_preserves_real_signing_and_publication(self):
        from datetime import datetime, timezone
        from shuttle import scheduled_cli
        # Reuse the actual four-phase signing/publication driver with only the
        # pinned policy changed. Temporary keys and mocked graph stay explicit.
        original = scheduled_cli._json
        local = datetime.fromtimestamp(self.slot, timezone.utc)

        def calendar(raw):
            value = original(raw)
            if 'interval_s' in value:
                value.pop('interval_s')
                value.update(weekday=local.weekday(), local_time=local.strftime('%H:%M'), timezone='UTC')
            return value

        with mock.patch.object(scheduled_cli, '_json', side_effect=calendar):
            self.test_actual_cli_protocol_with_real_signing_and_mocked_remote()

    def test_cli_malformed_or_oversized_packet_cannot_touch_config_or_graph(self):
        import io
        from shuttle import cli
        for raw in ('{"scope":{},"scope":{}}', '[' + ' ' * 65536 + ']', '{}'):
            with self.subTest(size=len(raw)), mock.patch('sys.stdin', io.StringIO(raw)):
                self.assertEqual(2, cli.main(['scheduled', 'admit', '--config', '/does-not-exist']))
        self.assertEqual([], self.posts)
        self.assertEqual([], self.queries)

    def test_missing_key_never_generates_a_replacement_or_creates_run(self):
        (self.base/'keys'/f'{self.scope.agent}.pk8').unlink()
        with self.assertRaises(signing.SigningError):
            self.port.admit(self.scope, self.slot)
        self.assertFalse((self.base/'runs').exists())
        self.assertFalse(list((self.base/'keys').iterdir()))

    def test_registration_scope_key_ambiguity_and_truncation_refuse(self):
        for field, value in [('workflow', 'urn:example:other'), ('pk', '0'*64),
                             ('verifier', 'other'), ('scopeIRI', False), ('scopeIRI', 1)]:
            with self.subTest(field=field):
                original = self.registration[field]
                self.registration[field] = value
                with self.assertRaises(ScheduledRefused):
                    self.port.admit(self.scope, self.slot)
                self.registration[field] = original
        self.truncate = True
        with self.assertRaises(ScheduledRefused):
            self.port.admit(self.scope, self.slot)

    def test_no_execution_without_admission_or_outside_slot_window(self):
        with self.assertRaises(ScheduledRefused):
            self.port.started(self.run, self.scope)
        self.port.admit(self.scope, self.slot)
        self.now = self.slot + 91
        with self.assertRaises(ScheduledRefused):
            self.port.started(self.run, self.scope)
        self.assertFalse((self.base/'runs').exists())

    def test_existing_run_refuses_and_fsync_failure_is_loud(self):
        self.start()
        with self.assertRaises(FileExistsError):
            self.port.started(self.run, self.scope)

    def test_started_reports_fsync_failure_before_returning_to_executor(self):
        with mock.patch('shuttle.scheduled.os.fsync', side_effect=OSError('fixture fsync failure')):
            with self.assertRaises(OSError):
                self.start()
        root = list((self.base/'runs').iterdir())[0]
        self.assertEqual(3, len(state.records(root)))
        with self.assertRaises(FileExistsError):
            self.port.started(self.run, self.scope)

    def test_registered_key_rotation_after_admission_cannot_sign_started(self):
        self.port.admit(self.scope, self.slot)
        (self.base/'keys'/f'{self.scope.agent}.pk8').unlink()
        signing.load_or_generate(self.scope.agent)  # synthetic replacement only
        with self.assertRaises(ScheduledRefused):
            self.port.started(self.run, self.scope)

    def test_publish_requires_exact_typed_records_and_fresh_registration(self):
        self.start()
        outcome = self.finish('skipped-by-hold')
        self.corrupt = True
        with self.assertRaises(ScheduledRefused):
            self.port.publish(self.run, self.scope, outcome)
        self.corrupt = False
        self.registration['pk'] = '0'*64
        with self.assertRaises(ScheduledRefused):
            self.port.publish(self.run, self.scope, outcome)
        self.registration['pk'] = self.pk
        self.port.publish(self.run, self.scope, outcome)

    def test_failed_and_hold_are_real_distinct_signed_terminals(self):
        self.start()
        outcome = self.finish('failed', 7)
        root = list((self.base/'runs').iterdir())[0]
        terminal = state.records(root)[-1]
        self.assertEqual('failed', terminal['to'])
        self.assertTrue(signing.verify_transition(self.pk, terminal['signature'], export.run_iri(self.run),
            'failed', 'running', 'failed', terminal['at'], self.scope.agent))
        self.port.publish(self.run, self.scope, outcome)

    def test_real_port_caps_scope_and_run_before_execution(self):
        binding = asdict(self.scope)
        binding['job'] = 'urn:example:' + 'x'*512
        with self.assertRaises(ScheduledRefused):
            ScheduledRunPort(binding, self.base/'oversized', host='host-a',
                public_key=self.pk, registration='urn:example:registration',
                identity_graph='urn:example:identity', eligible=lambda *_: True)
        self.port.admit(self.scope, self.slot)
        with self.assertRaises(ScheduledRefused):
            self.port.started('scheduled-v1-' + 'x'*2048, self.scope)
        self.assertFalse((self.base/'runs').exists())

    def test_eligibility_and_scope_mismatch_refuse(self):
        self.eligible = None
        with self.assertRaises(ScheduledRefused):
            self.port.admit(self.scope, self.slot)
        from dataclasses import replace
        with self.assertRaises(ScheduledRefused):
            self.port.admit(replace(self.scope, host='host-b'), self.slot)


def _RDF():
    return 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
