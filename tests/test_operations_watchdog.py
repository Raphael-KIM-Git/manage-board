import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = Path('/home/raphael/myproject/operations_watchdog.py')
spec = importlib.util.spec_from_file_location('operations_watchdog', MODULE_PATH)
watchdog = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(watchdog)


class OperationsWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.operations = Path(self.tmp.name) / 'operations'
        (self.operations / 'briefs').mkdir(parents=True)
        self.now = datetime(2026, 7, 23, 1, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def write_task(self, **overrides):
        task = {
            'task_id': 'T-20260723-001',
            'title': 'watchdog test',
            'status': 'dispatched',
            'updated_at': (self.now - timedelta(minutes=20)).isoformat(),
            'assigned_workers': ['writer-co'],
            'stages': [{'id': 'writing', 'status': 'in_progress'}],
        }
        task.update(overrides)
        path = self.operations / 'briefs' / 'T-20260723-001.json'
        path.write_text(json.dumps(task), encoding='utf-8')
        updated_at = datetime.fromisoformat(task['updated_at'])
        path.touch()
        import os
        os.utime(path, (updated_at.timestamp(), updated_at.timestamp()))

    def test_stall_alert_is_deduplicated_and_then_resolved(self):
        self.write_task()

        first = watchdog.run_watchdog(self.operations, now=self.now)
        self.assertEqual(first['event_count'], 1)
        self.assertEqual(first['events'][0]['kind'], 'stalled')
        self.assertEqual(first['events'][0]['severity'], 'warning')

        repeated = watchdog.run_watchdog(self.operations, now=self.now + timedelta(minutes=5))
        self.assertEqual(repeated['event_count'], 0)

        self.write_task(status='completed', updated_at=self.now.isoformat())
        resolved = watchdog.run_watchdog(self.operations, now=self.now + timedelta(minutes=6))
        self.assertEqual(resolved['event_count'], 1)
        self.assertEqual(resolved['events'][0]['kind'], 'resolved')

    def test_blocked_task_is_reported_immediately(self):
        self.write_task(status='dispatch_blocked', last_error='writer runner unavailable')
        outcome = watchdog.run_watchdog(self.operations, now=self.now)
        self.assertEqual(outcome['event_count'], 1)
        event = outcome['events'][0]
        self.assertEqual(event['kind'], 'blocked')
        self.assertEqual(event['severity'], 'critical')
        self.assertIn('writer runner unavailable', event['detail'])

    def test_rate_limited_assigned_worker_is_reported(self):
        self.write_task(updated_at=self.now.isoformat())
        (self.operations / 'worker-status.json').write_text(json.dumps({
            'updated_at': self.now.isoformat(),
            'workers': {'writer-co': {'status': 'rate_limited', 'message': 'session limit'}}
        }), encoding='utf-8')
        outcome = watchdog.run_watchdog(self.operations, now=self.now)
        self.assertEqual(outcome['event_count'], 1)
        event = outcome['events'][0]
        self.assertEqual(event['kind'], 'worker_unavailable')
        self.assertEqual(event['severity'], 'critical')


if __name__ == '__main__':
    unittest.main()
