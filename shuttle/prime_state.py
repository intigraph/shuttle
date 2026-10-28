"""Local bounded snapshots: no signing-key contents, locks or network calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

LIMIT = 1024 * 1024
MAX_RECORDS = 5000
MAX_KEYS = 128


class Capped(ValueError):
    pass


def read_file(path, limit=LIMIT):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('not_regular')
        if before.st_size > limit:
            raise Capped('size_limit')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            data = handle.read(limit + 1)
        after = os.fstat(fd)
        if len(data) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise Capped('size_limit_or_changed')
        return data
    finally:
        os.close(fd)


def store_summary(root):
    path = root / 'runs.jsonl'
    out = {'path': str(path), 'watermark_path': str(root / 'export-watermark.json'),
           'workflows': None, 'runs': None, 'open_runs': None, 'records': None,
           'exported_watermark': None, 'unexported_tail': None,
           'delivery': 'not_measured', 'historical_quarantine': 'not_measured'}
    try:
        from .cli import _index, _run_state
        records = []
        started_runs = set()
        for line in read_file(path).decode('utf-8').splitlines():
            if not line.strip():
                continue
            if len(records) >= MAX_RECORDS:
                raise Capped('record_limit')
            rec = json.loads(line)
            if not isinstance(rec, dict) or rec.get('type') not in {'define', 'start', 'transition'}:
                raise ValueError('unknown_record')
            # The ordinary index replaces duplicate run starts. Prime refuses
            # that ambiguous history rather than presenting a clean run count.
            if rec['type'] == 'start':
                if rec['run'] in started_runs:
                    raise ValueError('duplicate_start')
                started_runs.add(rec['run'])
            records.append(rec)
        defs, runs = _index(records=records)
        open_runs = 0
        for run_id in runs:
            defn, _, current = _run_state(defs, runs, run_id)
            open_runs += current not in defn.terminal
        out.update(status='ok', workflows=len(defs), runs=len(runs), open_runs=open_runs, records=len(records))
    except FileNotFoundError:
        out.update(status='absent', reason='log_absent')
        return out
    except Capped:
        out.update(status='partial', reason='log_limit_or_changed')
        return out
    except Exception:
        out.update(status='unreadable', reason='log_invalid_or_unreadable')
        return out
    try:
        value = json.loads(read_file(root / 'export-watermark.json', 4096))
        count = value['exported']
        if type(count) is not int or not 0 <= count <= len(records):
            raise ValueError('invalid_watermark')
        out.update(exported_watermark=count, unexported_tail=len(records) - count)
    except FileNotFoundError:
        out.update(status='partial', reason='watermark_absent')
    except Capped:
        out.update(status='partial', reason='watermark_limit_or_changed')
    except Exception:
        out.update(status='unreadable', reason='watermark_invalid_or_unreadable')
    return out


def key_summary(root, agent):
    path = root / f'{agent}.pk8' if agent else root
    out = {'path': str(path), 'metadata_candidates': None, 'unsafe_files': None,
           'validation': 'metadata_only', 'cryptographic_validity': 'not_measured',
           'registration': 'not_measured', 'agent_attribution': 'not_measured'}
    candidates = unsafe = 0
    try:
        if agent:
            metadata = [path.lstat()]
        else:
            metadata = []
            with os.scandir(root) as entries:
                for scanned, entry in enumerate(entries):
                    if scanned >= MAX_KEYS:
                        raise Capped('directory_entry_limit')
                    if not entry.name.endswith('.pk8'):
                        continue
                    if len(metadata) >= MAX_KEYS:
                        raise Capped('key_limit')
                    metadata.append(entry.stat(follow_symlinks=False))
        for info in metadata:
            if stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid():
                candidates += 1
            else:
                unsafe += 1
        out.update(status='partial' if unsafe else 'ok', metadata_candidates=candidates, unsafe_files=unsafe)
        if not metadata:
            out.update(status='absent', reason='no_key_files')
    except FileNotFoundError:
        out.update(status='absent', reason='key_path_absent')
    except Capped:
        out.update(status='partial', reason='key_limit')
    except OSError:
        out.update(status='unreadable', reason='key_metadata_unreadable')
    return out


def inspect(args):
    root = args.state_dir or Path(os.environ.get('SHUTTLE_STATE_DIR') or Path.home() / '.local/state/shuttle')
    keys = args.key_dir or Path(os.environ.get('SHUTTLE_KEY_DIR') or Path.home() / '.config/shuttle/keys')
    store = store_summary(root)
    signing = key_summary(keys, args.agent)
    statuses = {store['status'], signing['status']}
    if 'unreadable' in statuses:
        status = 'unreadable'
    elif statuses == {'absent'}:
        status = 'absent'
    elif statuses == {'ok'}:
        status = 'ok'
    else:
        status = 'partial'
    next_command = 'shuttle status'
    if store['status'] == 'absent':
        next_command = 'shuttle define --help'
    elif signing['status'] != 'ok':
        next_command = 'shuttle keys --help'
    return {'status': status, 'summary': {'store': store, 'keys': signing, 'next': next_command}}
