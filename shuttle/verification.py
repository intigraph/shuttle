"""Consumer verification using only Quipu, including frozen run windows."""
from __future__ import annotations

import json
import re

from . import export, quipu_client as qc, signing, vocabulary as v, windows


class VerificationError(RuntimeError):
    pass


def _rows(result):
    if result.get('truncated'):
        raise VerificationError('Quipu verification query truncated; cannot verify')
    if not isinstance(result.get('rows'), list):
        raise VerificationError('Quipu verification query returned no rows field')
    return result['rows']


def verify(run_id: str, identity_graph: str) -> int:
    r = export.run_iri(run_id)
    if not re.fullmatch(r'[^\s<>"{}|^`\\]+', r):
        raise VerificationError("unsafe run IRI")
    # The creation time lives on the run itself. Compose both live and frozen
    # graphs explicitly; local state and keys play no part in this consumer.
    starts = _rows(qc.query(
        f'SELECT DISTINCT ?at WHERE {{ {v.pattern("<"+r+">", "createdAt", "?at")} }}',
        include_kinds=['operational', 'archive'],
    ))
    if len(starts) != 1:
        raise VerificationError(f"run '{run_id}' needs exactly one exported start time")
    graph = windows.window_iri(windows.month_of(starts[0]['at']))
    start_rows = _rows(qc.query(
        f'SELECT ?record WHERE {{ <{r}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#value> ?record }}',
        graph=graph,
    ))
    if len(start_rows) != 1:
        raise VerificationError('run start has no unique signed record; re-export required')
    try:
        start = json.loads(start_rows[0]['record'])
        if (start['type'] != 'start' or start['run'] != run_id
                or start['at'] != starts[0]['at']):
            raise ValueError('start identity mismatch')
    except (ValueError, KeyError, TypeError) as exc:
        raise VerificationError('malformed exported start record') from exc
    rows = _rows(qc.query(
        f"SELECT ?ev ?step ?from ?to ?at ?agent ?sig WHERE {{ "
        f"{v.pattern('?ev', 'inRun', '<'+r+'>')} OPTIONAL {{ {v.pattern('?ev', 'atStep', '?step')} "
        f"{v.pattern('?ev', 'fromState', '?from')} {v.pattern('?ev', 'toState', '?to')} "
        f"?ev <{export.PROV}endedAtTime> ?at . "
        f"{v.pattern('?ev', 'performedBy', '?agent')} {v.pattern('?ev', 'signature', '?sig')} }} }}",
        graph=graph,
    ))
    regs = _rows(qc.query(
        f"SELECT ?verifier ?pk WHERE {{ ?reg a ?registrationType . "
        f"{v.pattern('?reg', 'verifier', '?verifier')} {v.pattern('?reg', 'publicKey', '?pk')} "
        f"{v.type_filter('?registrationType', 'VerifierRegistration')} }}",
        graph=identity_graph,
    ))
    keys = {}
    for row in regs:
        if row['verifier'] in keys and keys[row['verifier']] != row['pk']:
            raise VerificationError('ambiguous registered verifier key')
        keys[row['verifier']] = row['pk']
    bad = 0
    pk = keys.get(start.get('agent'))
    if pk is None or not signing.verify_start(pk, start, r):
        print('BAD OR UNREGISTERED START SIGNATURE')
        bad += 1
    for row in rows:
        if not {'ev', 'agent', 'step', 'sig', 'from', 'to', 'at'} <= row.keys():
            raise VerificationError('incomplete exported transition; cannot verify')
        agent = row['agent'].removeprefix(export.entity_ns() + 'agent:')
        step = row['step'].rsplit('/', 1)[-1]
        pk = keys.get(agent)
        if pk is None:
            print(f"UNREGISTERED: {row['ev']} performed by '{agent}' has no key in the identity graph")
            bad += 1
        elif not signing.verify_transition(
                pk, row['sig'], r, step, row['from'], row['to'], row['at'], agent):
            print(f"BAD SIGNATURE: {row['ev']}")
            bad += 1
    if bad:
        print(f'{bad} signature(s) FAILED verification')
        return 1
    print(f'all {len(rows)} exported transitions verify; signed start verifies')
    return 0
