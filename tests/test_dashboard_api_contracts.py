import json
import tempfile
import unittest
from pathlib import Path

import operations_dashboard_server as server


class DashboardAPIContractTests(unittest.TestCase):
    """Contract-level checks; this sandbox disallows loopback TCP sockets."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.original = {name: getattr(server, name) for name in (
            "BRIEFS_DIR", "RESULTS_DIR", "VERIFICATIONS_DIR", "DIGESTS_DIR", "DISPATCHES_DIR", "INTERVIEWS_DIR", "SEEDS_DIR"
        )}
        for name in self.original:
            value = root / name.lower()
            value.mkdir(parents=True, exist_ok=True)
            setattr(server, name, value)
        self.task = {
            "task_id": "T-API-001", "title": "API contract", "objective": "preserve writes",
            "status": "needs_pm_review", "pipeline_shape": "full", "stages": [
                {"id": "research", "status": "entry_hold", "entry_gate": {"decision": "hold"}},
                {"id": "writing", "status": "planned"},
            ],
        }
        (server.BRIEFS_DIR / "T-API-001.json").write_text(json.dumps(self.task), encoding="utf-8")

    def tearDown(self):
        for name, value in self.original.items():
            setattr(server, name, value)
        self.tmp.cleanup()

    def test_additive_task_view_and_overview(self):
        view = server.build_task_view(self.task)
        self.assertEqual(view["status"], "needs_pm_review")
        self.assertEqual(view["dashboard_projection"]["schema_version"], 1)
        overview = server.build_overview()
        self.assertEqual(overview["dashboard_summary"]["schema_version"], 1)
        self.assertIn("status_counts", overview)

    def test_gate_override_contract(self):
        result = server.set_gate_override("T-API-001", "writing", "revise")
        self.assertEqual(result, {"task_id": "T-API-001", "stage_id": "writing", "override": "revise"})
        with self.assertRaises(ValueError):
            server.set_gate_override("T-API-001", "writing", "invalid")
        stored = json.loads((server.BRIEFS_DIR / "T-API-001.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["stages"][1]["gate_override"], "revise")

    def test_final_review_and_live_note_contract(self):
        result = server.set_final_review_override("T-API-001", "accept")
        self.assertEqual(result["final_review_override"], "accept")
        with self.assertRaises(ValueError):
            server.set_final_review_override("T-API-001", "invalid")
        result = server.add_live_note("T-API-001", "맥락 메모")
        self.assertEqual(result["count"], 1)
        stored = json.loads((server.BRIEFS_DIR / "T-API-001.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["pm_live_notes"][0]["note"], "맥락 메모")
        self.assertNotIn("normalized_decision", stored)

    def test_completed_and_cancelled_live_note_contract(self):
        for status in ("completed", "cancelled"):
            task = dict(self.task, task_id=f"T-API-{status}", status=status)
            path = server.BRIEFS_DIR / f"{task['task_id']}.json"
            path.write_text(json.dumps(task), encoding="utf-8")
            with self.assertRaises(ValueError):
                server.add_live_note(task["task_id"], "should fail")

    def test_completed_renderer_uses_projection_compact_control(self):
        app = (Path(__file__).parents[1] / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("compact_hide_gate_details", app)
        self.assertIn("renderStageChips(task, compactHideGateDetails)", app)


if __name__ == "__main__":
    unittest.main()
