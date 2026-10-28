"""Native CLI conformance; included by ordinary unittest discovery."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from shuttle import __version__, prime, prime_state
from shuttle.primer import PRIMER

ROOT = Path(__file__).resolve().parents[1]
REGEN = 'python3 scripts/sync-primer.py'
DEFINITION = {'type': 'define', 'name': 'review', 'initial': 'new', 'terminal': ['done'],
              'transitions': [{'step': 'finish', 'from': 'new', 'to': 'done'}]}
START = {'type': 'start', 'run': 'one', 'definition': 'review', 'at': '2026-10-28T00:00:00Z'}
TRANSITION = {'type': 'transition', 'run': 'one', 'step': 'finish', 'from': 'new', 'to': 'done',
              'at': '2026-10-28T00:01:00Z', 'agent': 'synthetic', 'signature': 'not-verified-by-prime'}


def snapshot(root):
    out = {}
    for path in [root, *root.rglob('*')]:
        s = path.lstat()
        out[str(path.relative_to(root))] = (s.st_mode, s.st_size, s.st_mtime_ns,
                                           path.read_bytes() if path.is_file() and not path.is_symlink() else None)
    return out


class Prime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.cwd = self.root / 'cwd'
        self.home.mkdir()
        self.cwd.mkdir()
        self.state = self.home / 'state'
        self.keys = self.home / 'keys'

    def command(self, *args):
        env = {'HOME': str(self.home), 'PATH': os.environ.get('PATH', ''),
               'PYTHONPATH': str(ROOT), 'SHUTTLE_STATE_DIR': str(self.state),
               'SHUTTLE_KEY_DIR': str(self.keys)}
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-m', 'shuttle.cli', 'prime', *args],
                                cwd=self.cwd, env=env, capture_output=True, text=True, timeout=3)
        self.assertLess(time.monotonic() - started, 1.0)
        return result

    def decoded(self, *args):
        result = self.command('--json', *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads(result.stdout)
        self.assertEqual(obj['schema'], 'stack-prime/1')
        self.assertEqual(obj['tool'], 'shuttle')
        self.assertEqual(obj['version'], __version__)
        self.assertIsInstance(obj['primer']['sections'], list)
        self.assertLess(obj['live']['elapsed_ms'], 1000)
        self.assertEqual(obj['status'], 'ok' if obj['live']['status'] in {'ok', 'skipped'} else 'degraded')
        return obj

    def fixture(self, records=None):
        self.state.mkdir()
        records = [DEFINITION, START, TRANSITION] if records is None else records
        (self.state / 'runs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
        (self.state / 'export-watermark.json').write_text(json.dumps({'exported': len(records)}))
        self.keys.mkdir()
        key = self.keys / 'synthetic.pk8'
        key.write_text('synthetic invalid private key: prime must never load it')
        key.chmod(0o600)

    def test_missing_store_formats_readonly_and_usage(self):
        before = snapshot(self.root)
        obj = self.decoded()
        self.assertEqual(obj['live']['status'], 'absent')
        self.assertIsNone(obj['live']['summary']['store']['workflows'])
        for args in [(), ('--static',), ('--section', 'cOrE'), ('--brief',), ('--brief', '--static')]:
            out = self.command(*args)
            self.assertEqual(out.returncode, 0, out.stderr)
            if '--brief' in args:
                lines = out.stdout.splitlines()
                self.assertTrue(5 <= len(lines) <= 10)
                self.assertTrue(lines[0].startswith(f'shuttle {__version__}:'))
                self.assertEqual(lines[-1], 'Run `shuttle prime` for the full primer.')
            elif '--section' in args:
                self.assertTrue(out.stdout.startswith('## Core commands'))
                self.assertNotIn('## Next steps', out.stdout)
            else:
                self.assertIn('# Shuttle agent primer', out.stdout)
                self.assertIn('## Next steps', out.stdout)
                self.assertEqual('## Live state' in out.stdout, '--static' not in args)
        self.assertNotIn('text', self.decoded('--brief')['primer'])
        self.assertEqual(self.decoded('--static')['live']['status'], 'skipped')
        for args in [('--unknown',), ('--section', 'not-found'), ('--brief', '--section', 'Core'),
                     ('--agent', '../unsafe')]:
            out = self.command(*args)
            self.assertEqual(out.returncode, 2)
            if args[:2] == ('--section', 'not-found'):
                self.assertIn('Next steps', out.stderr)
        self.assertEqual(before, snapshot(self.root))

    def test_fold_metadata_and_no_state_or_key_operations(self):
        self.fixture()
        before = snapshot(self.root)
        obj = self.decoded('--agent', 'synthetic')
        s = obj['live']['summary']
        self.assertEqual(obj['live']['status'], 'ok')
        self.assertEqual((s['store']['workflows'], s['store']['runs'], s['store']['open_runs']), (1, 1, 0))
        self.assertEqual(s['store']['unexported_tail'], 0)
        self.assertEqual(s['keys']['metadata_candidates'], 1)
        self.assertEqual(s['keys']['cryptographic_validity'], 'not_measured')
        self.assertEqual(s['keys']['registration'], 'not_measured')
        args = SimpleNamespace(state_dir=self.state, key_dir=self.keys, agent=None)
        original_open = os.open
        def log_only_open(path, *args, **kwargs):
            self.assertNotEqual(Path(path).parent, self.keys, 'prime opened a signing key')
            return original_open(path, *args, **kwargs)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch('shuttle.prime_state.os.open', side_effect=log_only_open))
            for target in ['shuttle.signing.load_existing', 'shuttle.signing.load_or_generate',
                           'shuttle.state.append', 'shuttle.state.records', 'shuttle.state.locked',
                           'shuttle.quipu_client.query', 'shuttle.quipu_client.post']:
                stack.enter_context(patch(target, side_effect=AssertionError(target)))
            self.assertEqual(prime_state.inspect(args)['status'], 'ok')
        self.assertEqual(before, snapshot(self.root))

    def test_empty_measured_zero_differs_from_absent(self):
        self.fixture([])
        s = self.decoded()['live']['summary']['store']
        self.assertEqual((s['workflows'], s['runs'], s['records']), (0, 0, 0))
        (self.state / 'runs.jsonl').unlink()
        self.assertIsNone(self.decoded()['live']['summary']['store']['runs'])

    def test_log_and_watermark_errors_are_not_empty(self):
        self.fixture()
        log = self.state / 'runs.jsonl'
        valid = log.read_bytes()
        for bad in [b'not-json\n', b'{}\n', b'[]\n', b'\xff', b'x' * (prime_state.LIMIT + 1),
                    (json.dumps(START) + '\n').encode(),
                    ''.join(json.dumps(r) + '\n' for r in [DEFINITION, START, START]).encode(),
                    ''.join(json.dumps(r) + '\n' for r in [DEFINITION, START, {**TRANSITION, 'to': 'wrong'}]).encode()]:
            log.write_bytes(bad)
            before = snapshot(self.root)
            live = self.decoded()['live']
            self.assertIn(live['status'], {'unreadable', 'partial'})
            self.assertIsNone(live['summary']['store']['workflows'])
            self.assertEqual(before, snapshot(self.root))
        log.write_bytes(valid)
        mark = self.state / 'export-watermark.json'
        for bad in ['nope', '{"exported": true}', '{"exported": -1}', '{"exported": 4}', '{}']:
            mark.write_text(bad)
            live = self.decoded()['live']
            self.assertEqual(live['status'], 'unreadable')
            self.assertIsNone(live['summary']['store']['unexported_tail'])
        mark.unlink()
        self.assertEqual(self.decoded()['live']['status'], 'partial')
        self.assertIsNone(self.decoded()['live']['summary']['store']['unexported_tail'])
        self.assertEqual(self.decoded('--static')['live']['status'], 'skipped')

    def test_key_metadata_unsafe_cap_and_explicit_paths(self):
        self.fixture()
        key = self.keys / 'synthetic.pk8'
        key.chmod(0o644)
        self.assertEqual(self.decoded()['live']['status'], 'partial')
        key.unlink()
        key.symlink_to(self.state / 'runs.jsonl')
        self.assertEqual(self.decoded()['live']['summary']['keys']['unsafe_files'], 1)
        key.unlink()
        for i in range(prime_state.MAX_KEYS + 1):
            (self.keys / f'unrelated-{i}').touch()
        keys = self.decoded()['live']['summary']['keys']
        self.assertEqual(keys['status'], 'partial')
        self.assertIsNone(keys['metadata_candidates'])
        obj = self.decoded('--state-dir', str(self.root / 'missing-state'), '--key-dir', str(self.root / 'missing-keys'))
        self.assertEqual(obj['live']['status'], 'absent')
        self.assertFalse((self.root / 'missing-state').exists())

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'Unix file-type control')
    def test_special_log_does_not_block(self):
        self.state.mkdir()
        os.mkfifo(self.state / 'runs.jsonl')
        self.assertEqual(self.decoded()['live']['status'], 'unreadable')

    def test_entire_worker_deadline_and_cleanup(self):
        release, finished = threading.Event(), threading.Event()
        def slow(_):
            try:
                release.wait(3)
                return {'status': 'ok', 'summary': {}}
            finally:
                finished.set()
        started = time.monotonic()
        try:
            live = prime.summarize(SimpleNamespace(state_dir=self.state, key_dir=self.keys), slow)
            self.assertEqual(live['status'], 'partial')
            self.assertLess(live['elapsed_ms'], 1000)
            self.assertLess(time.monotonic() - started, 1)
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_source_and_generated_copies(self):
        source = (ROOT / 'shuttle/primer.md').read_text()
        self.assertEqual(PRIMER, source, REGEN)
        self.assertEqual((ROOT / 'docs/agent-primer.md').read_text(), source, REGEN)
        skill = (ROOT / 'skills/shuttle/SKILL.md').read_text()
        self.assertIn('<!-- BEGIN shuttle prime -->\n' + source + '<!-- END shuttle prime -->', skill, REGEN)
        required = ['# Shuttle agent primer', '## What shuttle is', '## Agent workflow',
                    '## Core commands', '## MCP tools', '## Next steps']
        self.assertEqual([source.index(s) for s in required], sorted(source.index(s) for s in required))
