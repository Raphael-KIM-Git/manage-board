import copy
import json
import tempfile
import unittest
from pathlib import Path

from dashboard_instructions import InstructionConflict, submit_instruction
from operations_dashboard_console import project_console_snapshot


class ConsoleV2Tests(unittest.TestCase):
    def task(self, **overrides):
        value = {
            "task_id": "T-CONSOLE-1", "title": "Console task", "status": "in_progress",
            "updated_at": "2026-07-31T10:00:00Z", "project_ref": {"project_id": "proj-a", "name": "Project A"},
            "stages": [{"id": "writing", "status": "in_progress", "agents": ["writer-co"]}],
            "dispatches": {"writer-co": "dispatched"}, "result_files": [], "result_metadata": [], "verification_files": [],
        }
        value.update(overrides)
        return value

    def test_console_schema_single_snapshot_and_non_mutating(self):
        raw = self.task()
        before = copy.deepcopy(raw)
        snapshot = project_console_snapshot([raw], generated_at="2026-07-31T10:01:00Z")
        self.assertEqual(snapshot["schema_version"], 2)
        self.assertEqual(set(snapshot["panes"]), {"pm_instruction", "agents", "projects", "mission_control"})
        self.assertIn("T-CONSOLE-1", snapshot["tasks_by_id"])
        self.assertEqual(raw, before)
        self.assertEqual(snapshot["panes"]["agents"]["items"][0]["results"][0]["state"], "dispatch_confirmed")
        self.assertEqual(snapshot["panes"]["projects"]["items"][0]["project_id"], "proj-a")

    def test_registry_agents_are_visible_without_tasks(self):
        snapshot = project_console_snapshot([], availability={"HermesPM": "configured", "writer-co": "needs_config"},
                                            agent_registry={"HermesPM": "configured", "writer-co": "needs_config"},
                                            generated_at="2026-07-31T10:01:00Z")
        rows = {row["agent_id"]: row for row in snapshot["panes"]["agents"]["items"]}
        self.assertEqual(set(rows), {"HermesPM", "writer-co"})
        for row in rows.values():
            self.assertEqual(row["dispatch_state"], "not_dispatched")
            self.assertEqual(row["execution_state"], "idle")
            self.assertEqual(row["active_count"], 0)
            self.assertEqual(row["completed_count"], 0)
        self.assertEqual(rows["HermesPM"]["configuration_state"], "configured")
        self.assertEqual(rows["writer-co"]["configuration_state"], "needs_config")

    def test_registry_rows_merge_task_evidence_precedence(self):
        task = self.task()
        task["stages"][0]["agents"] = ["writer-co"]
        task["dashboard_projection"] = {"progress": {"agent_states": {"writing": {"writer-co": "result_received", "_dispatch": {"writer-co": "dispatch_confirmed"}}}}}
        snapshot = project_console_snapshot([task], availability={"writer-co": "configured"}, agent_registry=["writer-co"])
        row = snapshot["panes"]["agents"]["items"][0]
        self.assertEqual(row["dispatch_state"], "dispatch_confirmed")
        self.assertEqual(row["execution_state"], "result_received")
        self.assertEqual(row["completed_count"], 1)
        self.assertEqual(row["active_count"], 0)

    def test_project_identity_is_explicit_and_missing_is_unassigned(self):
        snapshot = project_console_snapshot([self.task(task_id="T-A"), self.task(task_id="T-B", title="Project A lookalike", project_ref=None)])
        projects = {row["project_id"]: row for row in snapshot["panes"]["projects"]["items"]}
        self.assertIn("proj-a", projects)
        self.assertIn("unassigned", projects)
        self.assertEqual(projects["unassigned"]["task_ids"], ["T-B"])

    def test_mission_dedupes_display_only_and_pending_instruction_is_decision(self):
        task = self.task(status="needs_pm_review", pm_final_review={"verdict": "not_meets", "gaps": "evidence"})
        instruction = {"instruction_id": "DI-1", "state": "submitted_pending_pm_review", "target_type": "task", "target_id": task["task_id"], "submitted_at": "2026-07-31T10:02:00Z", "text": "please investigate"}
        snapshot = project_console_snapshot([task], instruction_records=[instruction])
        rows = snapshot["panes"]["mission_control"]["items"]
        self.assertTrue(any(row["kind"] == "decision" and row.get("instruction_id") == "DI-1" for row in rows))
        self.assertEqual(len({row["dedupe_key"] for row in rows}), len(rows))

    def test_instruction_store_is_append_only_and_idempotent(self):
        root = Path(tempfile.mkdtemp())
        payload = {"instruction_type": "additional_instruction", "target_type": "task", "target_id": "T-1", "target_raw_status": "in_progress", "text": "<script>alert(1)</script>", "client_created_at": "2026-07-31T10:00:00Z"}
        original = copy.deepcopy(payload)
        first, created = submit_instruction(payload, "idempotency-1", root=root, task_exists=lambda _: True)
        retry, duplicate = submit_instruction(payload, "idempotency-1", root=root, task_exists=lambda _: True)
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first["instruction_id"], retry["instruction_id"])
        self.assertEqual(first["state"], "submitted_pending_pm_review")
        self.assertFalse(first["parent_changed"])
        self.assertEqual(payload, original)
        self.assertIn("<script>", json.loads(next(root.glob("*.json")).read_text())["text"])
        with self.assertRaises(InstructionConflict):
            submit_instruction({**payload, "text": "different"}, "idempotency-1", root=root, task_exists=lambda _: True)


if __name__ == "__main__":
    unittest.main()
