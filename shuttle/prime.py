"""Bounded read-only agent orientation; never bootstrap a run or key."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import threading
import time

from . import __version__
from .primer import PRIMER

DEADLINE = 0.650


def section(name):
    blocks = PRIMER.split('\n## ')[1:]
    headings = [block.split('\n', 1)[0] for block in blocks]
    if name is None:
        return PRIMER, headings
    for heading, block in zip(headings, blocks):
        if name.strip() and heading.casefold().startswith(name.strip().casefold()):
            return '## ' + block, headings
    raise ValueError(f'unknown section {name!r}; sections: ' + ', '.join(headings))


def summarize(args, reader=None):
    from .prime_state import inspect
    started = time.monotonic()
    paths = {'state_path': str(args.state_dir or os.environ.get('SHUTTLE_STATE_DIR') or Path.home() / '.local/state/shuttle'),
             'key_path': str(args.key_dir or os.environ.get('SHUTTLE_KEY_DIR') or Path.home() / '.config/shuttle/keys')}
    result = queue.Queue(maxsize=1)

    def read():
        try:
            value = (reader or inspect)(args)
        except Exception:
            value = {'status': 'unreadable', 'summary': {**paths, 'reason': 'reader_failed', 'next': 'shuttle prime --static'}}
        result.put(value)

    threading.Thread(target=read, daemon=True).start()
    try:
        live = result.get(timeout=DEADLINE)
    except queue.Empty:
        live = {'status': 'partial', 'summary': {'reason': 'deadline',
                'next': 'shuttle prime --static',
                **paths}}
    live['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    return live


def lines(live):
    s = live['summary']
    store, keys = s.get('store', {}), s.get('keys', {})

    def show(value):
        return 'unknown' if value is None else str(value)

    result = [
        f"State: {live['status']}",
        f"Local workflows: {show(store.get('workflows'))}; runs: {show(store.get('runs'))}; open: {show(store.get('open_runs'))}",
        f"Unexported tail: {show(store.get('unexported_tail'))} (delivery and quarantine not measured)",
        f"Signing files: {keys.get('status', 'unknown')}; metadata candidates: {show(keys.get('metadata_candidates'))}; validity/registration not measured",
        f"State path: {store.get('path', s.get('state_path', 'unknown'))}",
        f"Key path: {keys.get('path', s.get('key_path', 'unknown'))}",
        f"Next: {s.get('next', 'shuttle status')}",
    ]
    return [line.replace('\r', '\\r').replace('\n', '\\n') for line in result]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='shuttle prime', description=__doc__)
    parser.add_argument('--static', action='store_true', dest='static_only')
    parser.add_argument('--brief', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--section')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--key-dir', type=Path)
    parser.add_argument('--agent', help='inspect one existing signing-file name; never load its bytes')
    args = parser.parse_args(argv)
    if args.brief and args.section is not None:
        parser.error('--brief and --section cannot be combined')
    if args.agent is not None and (not args.agent or '/' in args.agent or '\\' in args.agent or args.agent.startswith('.')):
        parser.error('--agent must be a safe signing filename')
    try:
        text, headings = section(args.section)
    except ValueError as exc:
        parser.error(str(exc))
    live = {'status': 'skipped', 'elapsed_ms': 0, 'summary': {}} if args.static_only else summarize(args)
    primer = {'sections': headings}
    if not args.brief:
        primer['text'] = text
    if args.json:
        print(json.dumps({'schema': 'stack-prime/1', 'tool': 'shuttle', 'version': __version__,
                         'primer': primer, 'live': live,
                         'status': 'ok' if live['status'] in {'ok', 'skipped'} else 'degraded'}))
    elif args.brief:
        out = [f'shuttle {__version__}: signed append-only workflow runs exported to Quipu']
        if args.static_only:
            what, _ = section('What shuttle is')
            out.extend(line for line in what.splitlines()[1:] if line.strip())
        else:
            out.extend(lines(live))
        out.append('Run `shuttle prime` for the full primer.')
        print('\n'.join(out))
    else:
        print(text.rstrip())
        if not args.static_only:
            print('\n## Live state\n\n' + '\n'.join(lines(live)))
    return 0
