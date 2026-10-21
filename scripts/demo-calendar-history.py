#!/usr/bin/env python3
"""Real temporary fixture signatures, mocked graph; no runtime action."""
from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_calendar_history import CalendarHistoryTests


def main():
    warnings.simplefilter('ignore', ResourceWarning)
    fixture = CalendarHistoryTests()
    fixture.setUp()
    try:
        print('Explicit occurrence:', fixture.target)
        print('UTC difference:', fixture.target.next_deadline-fixture.target.scheduled_at)
        print('Signed control, missing target:', fixture.measure()['verdict'])
        fixture.publish(fixture.slot)
        print('Signed target:', fixture.measure()['verdict'])
        fixture.f.facts.clear()
        print('Empty history:', fixture.measure()['verdict'])
        print('Temporary keys + mocked transport only; not natural/runtime acceptance.')
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
