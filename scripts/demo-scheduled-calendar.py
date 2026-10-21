#!/usr/bin/env python3
"""Private policy demonstration; no keys, graph, registration or children."""
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shuttle.scheduled_cli import cadence

anchor = int(datetime.fromisoformat('2026-10-26T13:17:00+00:00').timestamp())
common = dict(binding={}, host='urn:host', public_key='synthetic', registration='urn:registration',
              identity_graph='urn:identity', state_root='/unused', declaration_graph='urn:jobs',
              eligibility_query='SELECT ?eligible WHERE {} LIMIT 2', anchor_s=anchor,
              effective_from_s=anchor, max_lateness_s=60)
fixed = cadence(dict(common, interval_s=604800))
weekly = cadence(dict(common, weekday=0, local_time='09:17', timezone='America/New_York'))
for value in ('2026-10-26T13:17:00+00:00', '2026-11-02T14:17:00+00:00',
              '2026-11-02T13:17:00+00:00'):
    slot = int(datetime.fromisoformat(value).timestamp())
    print(value, 'old-fixed-policy=', fixed(slot), 'calendar-policy=', weekly(slot))
print('Synthetic local policy only; not installed admission or runtime acceptance.')
