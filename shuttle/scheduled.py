"""Concrete signed-run port for an admitted scheduled delivery.

No listener, scheduler, command execution or identity registration. The caller
owns its durable slot claim and supplies a current declaration eligibility
check. Each run has a separate local outbox; preserve it across rollback.
"""
from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable

from . import export, quipu_client as qc, signing, state, windows

_FIELDS = {'job', 'revision', 'host', 'manifest_sha256', 'agent', 'workflow'}
_IRI = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:[^\s<>"{}|^`\\]+$')
_XSD = 'http://www.w3.org/2001/XMLSchema#'
_RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'


class ScheduledRefused(RuntimeError):
    """Admission or exact signed acceptance is unavailable; never success."""


def _iri(value):
    if type(value) is not str or not _IRI.fullmatch(value):
        raise ScheduledRefused('expected an expanded absolute IRI')
    return value


def _rows(body, limit):
    if (not isinstance(body, dict) or body.get('error') or
            body.get('truncated') is not False or
            not isinstance(body.get('rows'), list) or
            type(body.get('count')) is not int or
            body['count'] != len(body['rows']) or body['count'] > limit or
            any(not isinstance(row, dict) for row in body['rows'])):
        raise ScheduledRefused('bounded complete query result unavailable')
    return body['rows']


class ScheduledRunPort:
    """A pinned local scope and public registration, never graph command text.

    `eligible` must check current declaration/revision/enablement and retained
    catalogue coverage. It must return exactly True, never truthy UNKNOWN.
    Local custody and remote registered-key integrity do not prove isolated
    authorship under a shared Unix uid. Exit code is unsigned local metadata.
    """
    def __init__(self, binding: dict, root: Path, *, host: str, public_key: str,
                 registration: str, identity_graph: str,
                 eligible: Callable[[dict, int], bool],
                 max_lateness_s: int = 90, clock=time.time, query=None):
        if (not isinstance(binding, dict) or set(binding) != _FIELDS or
                any(type(v) is not str or not v or len(v) > 256 for v in binding.values())):
            raise ScheduledRefused('complete bounded pinned scope required')
        if not re.fullmatch('[0-9a-f]{64}', binding['manifest_sha256']):
            raise ScheduledRefused('immutable manifest SHA256 required')
        if not re.fullmatch('[0-9a-f]{64}', public_key):
            raise ScheduledRefused('approved Ed25519 public key required')
        if binding['host'] != host:
            raise ScheduledRefused('manifest targets another host')
        prefix = export.workflow_iri('')
        if not binding['workflow'].startswith(prefix):
            raise ScheduledRefused('workflow differs from the configured entity namespace')
        self.definition = binding['workflow'][len(prefix):]
        if not re.fullmatch('[A-Za-z0-9_-]+', self.definition):
            raise ScheduledRefused('unsafe workflow name')
        self.binding = dict(binding)
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ScheduledRefused('absolute persistent outbox root required')
        self.public_key = public_key
        self.registration, self.identity_graph = _iri(registration), _iri(identity_graph)
        self.eligible, self.clock = eligible, clock
        if type(max_lateness_s) is not int or not 0 <= max_lateness_s <= 86400:
            raise ScheduledRefused('bounded execution lateness required')
        self.max_lateness_s = max_lateness_s
        self.query = query or qc.query
        self.keys = signing.key_dir()
        self.namespace = export.entity_ns()
        self.admitted = set()

    def _scope(self, scope):
        try:
            value = asdict(scope)
        except TypeError as exc:
            raise ScheduledRefused('typed immutable execution scope required') from exc
        if value != self.binding or any(type(v) is not str for v in value.values()):
            raise ScheduledRefused('execution scope differs from the local manifest')
        if signing.key_dir() != self.keys or export.entity_ns() != self.namespace:
            raise ScheduledRefused('key or entity namespace changed during the operation')

    def admit(self, scope, scheduled_at):
        self._scope(scope)
        if type(scheduled_at) is not int or scheduled_at < 0:
            raise ScheduledRefused('nonnegative UTC slot required')
        if self.eligible(dict(self.binding), scheduled_at) is not True:
            raise ScheduledRefused('current declaration eligibility is not proven')
        a = export.AEGIS
        rows = _rows(self.query(
            f'SELECT ?verifier ?pk ?workflow (isIRI(?workflow) AS ?scopeIRI) WHERE {{ '
            f'<{self.registration}> a ?type ; <{a}verifier> ?verifier ; '
            f'<{a}publicKey> ?pk ; <{a}attests> ?workflow . '
            f'FILTER(?type = <{a}VerifierRegistration>) }} LIMIT 8',
            graph=self.identity_graph), 8)
        if len(rows) != 1 or rows[0].get('scopeIRI') is not True or rows[0] != {
                'verifier': self.binding['agent'], 'pk': self.public_key,
                'workflow': self.binding['workflow'], 'scopeIRI': True}:
            raise ScheduledRefused('exact scoped verifier registration unavailable')
        with signing.existing_keys_only():
            local = signing.public_key_hex(self.binding['agent'])
        if local != self.public_key:
            raise ScheduledRefused('existing local key differs from the registered key')
        self.admitted.add(scheduled_at)

    def _run(self, run, scope):
        self._scope(scope)
        if type(run) is not str or not run.startswith('scheduled-v1-') or len(run) > 2048:
            raise ScheduledRefused('bounded scheduled run identifier required')
        encoded = run[len('scheduled-v1-'):]
        try:
            raw = base64.b64decode(encoded + '='*(-len(encoded) % 4), altchars=b'-_', validate=True)
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ScheduledRefused('invalid signed run binding') from exc
        if not isinstance(value, dict):
            raise ScheduledRefused('invalid signed run binding')
        slot = value.get('scheduled_at')
        expected = {**self.binding, 'scheduled_at': slot, 'version': 1}
        canonical = json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()
        if (value != expected or raw != canonical or type(slot) is not int or
                slot not in self.admitted or
                encoded != base64.urlsafe_b64encode(raw).decode().rstrip('=')):
            raise ScheduledRefused('run binding differs from admitted scope or slot')
        return self.root / hashlib.sha256(run.encode()).hexdigest(), slot

    def _definition(self, at):
        return {'type': 'define', 'name': self.definition, 'initial': 'queued',
                'terminal': ['succeeded', 'failed', 'skipped-by-hold'],
                'transitions': [
                    {'step': 'started', 'from': 'queued', 'to': 'running'},
                    *[{'step': name, 'from': 'running', 'to': name}
                      for name in ('succeeded', 'failed', 'skipped-by-hold')]], 'at': at}

    def _transition(self, run, step, old, new, at, window):
        signature = signing.sign_transition(
            self.binding['agent'], export.run_iri(run), step, old, new, at,
            require_existing_key=True)
        if not signing.verify_transition(self.public_key, signature, export.run_iri(run),
                                         step, old, new, at, self.binding['agent']):
            raise ScheduledRefused('key changed after registration admission')
        return {'type': 'transition', 'run': run, 'definition': self.definition,
                'window': window, 'step': step, 'from': old, 'to': new, 'at': at,
                'agent': self.binding['agent'], 'signature': signature}

    def _sync(self, root):
        # Signatures must survive a crash before the caller may execute work.
        for path, flags in ((root/'runs.jsonl', os.O_RDONLY),
                            (root, os.O_RDONLY | os.O_DIRECTORY),
                            (self.root, os.O_RDONLY | os.O_DIRECTORY),
                            (self.root.parent, os.O_RDONLY | os.O_DIRECTORY)):
            fd = os.open(path, flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def started(self, run, scope):
        root, slot = self._run(run, scope)
        now = self.clock()
        if not slot <= now <= slot + self.max_lateness_s:
            raise ScheduledRefused('new execution is early or outside its admitted slot window')
        self.root.mkdir(exist_ok=True, mode=0o700)
        root.mkdir(mode=0o700)  # existing outbox is UNKNOWN, never a second execution
        at = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        rec = self._transition(run, 'started', 'queued', 'running', at, windows.month_of(at))
        state.append(self._definition(at), root)
        state.append({'type': 'start', 'run': run, 'definition': self.definition,
                      'state': 'queued', 'agent': self.binding['agent'], 'at': at}, root)
        state.append(rec, root)
        self._sync(root)

    def _records(self, root, run, count):
        recs = state.records(root)
        if len(recs) != count or recs[0] != self._definition(recs[0].get('at')):
            raise ScheduledRefused('unexpected local run history')
        start = recs[1]
        if start != {'type': 'start', 'run': run, 'definition': self.definition,
                     'state': 'queued', 'agent': self.binding['agent'], 'at': recs[2]['at']}:
            raise ScheduledRefused('unsigned start does not match the signed start')
        for rec in recs[2:]:
            if (rec.get('run') != run or rec.get('agent') != self.binding['agent'] or
                    rec.get('definition') != self.definition or
                    rec.get('window') != windows.month_of(start['at']) or
                    not signing.verify_transition(self.public_key, rec['signature'],
                        export.run_iri(run), rec['step'], rec['from'], rec['to'], rec['at'], rec['agent'])):
                raise ScheduledRefused('local transition does not verify against the admitted key')
        if (recs[2]['step'], recs[2]['from'], recs[2]['to']) != ('started', 'queued', 'running'):
            raise ScheduledRefused('signed started transition missing')
        return recs

    def finished(self, run, scope, outcome):
        root, _ = self._run(run, scope)
        recs = self._records(root, run, 3)
        name, code = outcome.get('outcome'), outcome.get('exit_code')
        if (name not in ('succeeded', 'failed', 'skipped-by-hold') or type(code) is not int or
                not 0 <= code <= 255 or (name == 'failed') != (code != 0)):
            raise ScheduledRefused('actual terminal outcome is invalid')
        at = datetime.fromtimestamp(self.clock(), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if at < recs[2]['at']:
            raise ScheduledRefused('terminal clock precedes the signed started time')
        state.append(self._transition(run, name, 'running', name, at, recs[2]['window']), root)
        self._sync(root)

    def publish(self, run, scope, outcome):
        root, _ = self._run(run, scope)
        recs = self._records(root, run, 4)
        terminal = recs[3]
        name, code = outcome.get('outcome'), outcome.get('exit_code')
        if (name not in ('succeeded', 'failed', 'skipped-by-hold') or type(code) is not int or
                not 0 <= code <= 255 or (name == 'failed') != (code != 0)):
            raise ScheduledRefused('actual terminal receipt is invalid')
        if (terminal['step'], terminal['from'], terminal['to']) != (
                outcome['outcome'], 'running', outcome['outcome']):
            raise ScheduledRefused('signed terminal differs from the execution receipt')
        self.admit(scope, self._run(run, scope)[1])
        qc.probe_graph_kinds()
        with signing.existing_keys_only():
            summary = export.export(root=root, strict=True)
        if summary['total'] != 4 or summary['quarantined']:
            raise ScheduledRefused('complete export unavailable')
        graph = windows.window_iri(recs[2]['window'])
        rows = _rows(self.query(
            'SELECT (STR(?event) AS ?ev) (STR(?predicate) AS ?p) '
            '(STR(?raw) AS ?value) (isIRI(?raw) AS ?iri) '
            '(STR(DATATYPE(?raw)) AS ?datatype) WHERE { '
            f'?event <{export.AEGIS}inRun> <{export.run_iri(run)}> ; ?predicate ?raw '
            '} LIMIT 64', graph=graph), 64)
        expected = set()
        for seq, rec in enumerate(recs[2:], 2):
            ev = export.event_iri(run, seq)
            facts = [(_RDF+'type', export.AEGIS+'TransitionEvent', True),
                     (export.AEGIS+'inRun', export.run_iri(run), True),
                     (export.AEGIS+'atStep', self.binding['workflow']+'/step/'+rec['step'], True),
                     (export.AEGIS+'fromState', rec['from'], False),
                     (export.AEGIS+'toState', rec['to'], False),
                     (export.PROV+'endedAtTime', rec['at'], False),
                     (export.AEGIS+'performedBy', self.namespace+'agent:'+rec['agent'], True),
                     (export.AEGIS+'signature', rec['signature'], False),
                     (export.AEGIS+'sourceKind', 'observed', False)]
            expected.update((ev, p, value, iri, None if iri else _XSD+'string')
                            for p, value, iri in facts)
        observed = set()
        for row in rows:
            if type(row.get('iri')) is not bool:
                raise ScheduledRefused('typed read-back capability unavailable')
            observed.add((row.get('ev'), row.get('p'), row.get('value'), row['iri'],
                          None if row['iri'] else row.get('datatype')))
        if len(rows) != len(expected) or observed != expected:
            raise ScheduledRefused('exact signed transition read-back unavailable')
