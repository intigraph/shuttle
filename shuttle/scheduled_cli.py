"""Bounded process interface to the strict scheduled-run signing port.

The local configuration, including its declaration-eligibility SELECT, must be
reviewed and pinned by the runtime owner. None of it comes from a delivery.
No child command, scheduler, registration or automatic key creation is provided.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
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


def cadence(config):
    """Validate pinned local policy before any graph or key access.

    Existing fixed configurations retain their exact field contract. Calendar
    configurations replace interval_s with weekday/local_time/timezone.
    """
    common = {'binding', 'host', 'public_key', 'registration', 'identity_graph',
              'state_root', 'declaration_graph', 'eligibility_query',
              'anchor_s', 'effective_from_s', 'max_lateness_s'}
    fixed = set(config) == common | {'interval_s'}
    weekly = set(config) == common | {'weekday', 'local_time', 'timezone'}
    if not (fixed or weekly):
        raise ScheduledRefused('complete single-form pinned configuration required')
    anchor, effective = (config[k] for k in ('anchor_s', 'effective_from_s'))
    if (type(anchor) is not int or not 0 <= anchor <= 253402214400 or
            type(effective) is not int or not anchor <= effective <= 253402214400):
        raise ScheduledRefused('bounded cadence anchor and activation boundary required')
    if fixed:
        interval = config['interval_s']
        if type(interval) is not int or interval < 60:
            raise ScheduledRefused('explicit fixed cadence required')
        return lambda slot: (type(slot) is int and effective <= slot <= 253402214400 and
                             (slot-anchor) % interval == 0)
    weekday, local_time, zone_name = (config[k] for k in ('weekday', 'local_time', 'timezone'))
    if (type(weekday) is not int or not 0 <= weekday <= 6 or
            type(local_time) is not str or
            not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', local_time) or
            type(zone_name) is not str or not 0 < len(zone_name) <= 255):
        raise ScheduledRefused('weekly weekday/HH:MM/IANA zone required')
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScheduledRefused('valid IANA zone required') from exc
    hour, minute = map(int, local_time.split(':'))

    def matches(slot):
        if type(slot) is not int or not 0 <= slot <= 253402214400:
            return False
        try:
            local = datetime.fromtimestamp(slot, zone)
            if (local.weekday() != weekday or local.hour != hour or
                    local.minute != minute or local.second != 0 or local.microsecond != 0):
                return False
            naive = local.replace(tzinfo=None)
            candidates = set()
            for fold in (0, 1):
                utc = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                if utc.astimezone(zone).replace(tzinfo=None) == naive:
                    candidates.add(int(utc.timestamp()))
            # Neither gap shifting nor choosing one occurrence of a fold.
            return candidates == {slot}
        except (OverflowError, OSError, ValueError):
            return False

    if not matches(anchor):
        raise ScheduledRefused('anchor does not match unambiguous weekly policy')
    return lambda slot: type(slot) is int and slot >= effective and matches(slot)


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
    matches = cadence(config)
    graph = _iri(config['declaration_graph'])
    query = config['eligibility_query']
    if (type(query) is not str or not query.lstrip().upper().startswith('SELECT ') or
            not re.search(r'\bLIMIT\s+2\s*$', query, re.IGNORECASE)):
        raise ScheduledRefused('reviewed declaration SELECT required')
    def eligible(binding, scheduled_at):
        if not matches(scheduled_at):
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
