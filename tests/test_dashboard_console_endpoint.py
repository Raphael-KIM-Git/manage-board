import copy
import unittest

import operations_dashboard_server as server
from operations_dashboard_console import project_console_snapshot


class DashboardConsoleEndpointTests(unittest.TestCase):
    def task(self, **overrides):
        value = {
            "task_id": "T-CONSOLE-1",
            "title": "Console task",
            "objective": "read-only evidence",
            "status": "in_progress",
            "updated_at": "2026-07-31T10:00:00Z",
            "project_ref": {"project_id": "proj-a", "name": "Project A"},
            "stages": [{"id": "writing", "status": "in_progress", "agents": ["writer-co"]}],
            "dispatches": {"writer-co": "dispatched"},
            "result_files": [],
            "result_metadata": [],
            "verification_files": [],
        }
        value.update(overrides)
        return value

    def test_route_returns_documented_snapshot_without_mutating_task(self):
        raw = self.task()
        original_load_tasks = server.load_tasks
        server.load_tasks = lambda: [raw]
        try:
            response = {}

            class FakeHandler:
                path = "/api/dashboard-console"

                def _send_json(self, payload):
                    response["payload"] = payload

            server.Handler.do_GET(FakeHandler())
        finally:
            server.load_tasks = original_load_tasks

        payload = response["payload"]
        self.assertEqual(payload["schema_version"], 2)
        self.assertIsInstance(payload["snapshot_id"], str)
        self.assertIsInstance(payload["generated_at"], str)
        self.assertIsInstance(payload["limitations"], list)
        self.assertEqual(set(payload["panes"]), {"pm_instruction", "agents", "projects", "mission_control"})
        self.assertIn("T-CONSOLE-1", payload["tasks_by_id"])
        self.assertEqual(raw, self.task())

    def test_projection_is_non_mutating_and_has_read_only_panes(self):
        raw = self.task()
        before = copy.deepcopy(raw)
        snapshot = project_console_snapshot([raw], generated_at="2026-07-31T10:01:00Z")
        self.assertEqual(snapshot["source_freshness"]["sync"], None)
        self.assertEqual(raw, before)
        self.assertNotIn("instruction_records", snapshot)


if __name__ == "__main__":
    unittest.main()
