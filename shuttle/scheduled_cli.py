"""Bounded process interface to the strict scheduled-run signing port.

The local configuration, including its declaration-eligibility SELECT, must be
reviewed and pinned by the runtime owner. None of it comes from a delivery.
No child command, scheduler, registration or automatic key creation is provided.
"""
from dataclasses import dataclass
import json
import re
from pathlib import Path
import sys

from . import quipu_client as qc
from .scheduled import ScheduledRefused, ScheduledRunPort, _iri, _rows


@dataclass(frozen=True)
class Scope:
    job: str
    revision: str
    host: str
    manifest_sha256: str
    agent: str
    workflow: str


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ScheduledRefused('duplicate JSON key refused')
        result[key] = value
    return result


def _json(raw):
    if len(raw.encode()) > 65536:
        raise ScheduledRefused('bounded JSON input exceeded')
    value = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(value, dict):
        raise ScheduledRefused('JSON object required')
    return value


def run(args):
    # Read bounded input first; an invalid delivery cannot touch the config,
    # a key, a local outbox, or the graph. No credentials are printed.
    packet = _json(sys.stdin.read(65537))
    required = {'scope', 'scheduled_at'}
    if args.action != 'admit':
        required.add('run')
    if args.action in ('finished', 'publish'):
        required.add('outcome')
    if set(packet) != required or not isinstance(packet['scope'], dict):
        raise ScheduledRefused('unexpected delivery fields')
    scope = Scope(**packet['scope'])
    slot = packet['scheduled_at']
    with Path(args.config).open() as config_file:
        config = _json(config_file.read(65537))
    fields = {'binding', 'host', 'public_key', 'registration', 'identity_graph',
              'state_root', 'declaration_graph', 'eligibility_query',
              'interval_s', 'anchor_s', 'effective_from_s', 'max_lateness_s'}
    if set(config) != fields:
        raise ScheduledRefused('complete pinned local configuration required')
    graph = _iri(config['declaration_graph'])
    query = config['eligibility_query']
    if (type(query) is not str or not query.lstrip().upper().startswith('SELECT ') or
            not re.search(r'\bLIMIT\s+2\s*$', query, re.IGNORECASE)):
        raise ScheduledRefused('reviewed declaration SELECT required')
    interval, anchor, effective = (config[k] for k in ('interval_s', 'anchor_s', 'effective_from_s'))
    if (type(interval) is not int or interval < 60 or type(anchor) is not int or anchor < 0 or
            type(effective) is not int or effective < anchor):
        raise ScheduledRefused('explicit fixed cadence and activation boundary required')

    def eligible(binding, scheduled_at):
        if (scheduled_at < effective or (scheduled_at-anchor) % interval != 0):
            return False
        rows = _rows(qc.query(query, graph=graph), 2)
        return (len(rows) == 1 and set(rows[0]) == {'eligible'} and
                rows[0]['eligible'] is True)

    port = ScheduledRunPort(config['binding'], Path(config['state_root']),
        host=config['host'], public_key=config['public_key'],
        registration=config['registration'], identity_graph=config['identity_graph'],
        eligible=eligible, max_lateness_s=config['max_lateness_s'])
    port.admit(scope, slot)
    if args.action == 'started':
        port.started(packet['run'], scope)
    elif args.action == 'finished':
        port.finished(packet['run'], scope, packet['outcome'])
    elif args.action == 'publish':
        port.publish(packet['run'], scope, packet['outcome'])
    print(json.dumps({'action': args.action, 'result': 'verified'}))
    return 0
