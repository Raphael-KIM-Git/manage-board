import copy
import unittest

from operations_dashboard_projection import (
    build_dashboard_summary,
    classify_raw,
    project_task,
)


class DashboardProjectionTests(unittest.TestCase):
    def task(self, **overrides):
        task = {
            "task_id": "T-TEST",
            "title": "Projection test",
            "objective": "Keep raw state safe",
            "status": "waiting_verification",
            "pipeline_shape": "research_verify",
            "updated_at": "2026-07-21T10:00:00",
            "stages": [
                {"id": "research", "status": "completed", "gate": {"decision": "proceed", "at": "2026-07-21T09:00:00"}},
                {"id": "verification", "status": "in_progress", "agents": ["verify-co"]},
            ],
            "result_files": [{"name": "T-TEST-result.md", "size": 10, "modified_at": "2026-07-21T09:30:00"}],
            "verification_files": [],
        }
        task.update(overrides)
        return task

    def test_missing_null_unknown_are_distinct(self):
        self.assertEqual(classify_raw({}, "pipeline_shape")["state"], "missing")
        self.assertEqual(classify_raw({"pipeline_shape": None}, "pipeline_shape")["state"], "null")
        self.assertEqual(classify_raw({"pipeline_shape": "future"}, "pipeline_shape", {"full"})["state"], "unknown")

    def test_all_five_pipeline_shapes_are_description_only(self):
        for shape in {"full", "write_verify", "research_verify", "analyze_verify", "research_only"}:
            projection = project_task(self.task(pipeline_shape=shape))
            self.assertEqual(projection["pipeline_shape"]["raw"], shape)
            self.assertNotIn("decision", projection["pipeline_shape"])

    def test_unknown_pipeline_keeps_raw_value(self):
        projection = project_task(self.task(pipeline_shape="custom_pipeline"))
        self.assertEqual(projection["pipeline_shape"]["raw"], "custom_pipeline")
        self.assertTrue(projection["data_quality"])

    def test_mid_gate_proceed_is_not_final_approved(self):
        projection = project_task(self.task(status="in_progress", stages=[{"id": "writing", "status": "completed", "gate": {"decision": "proceed"}}], result_files=[]))
        self.assertFalse(projection["authority_summary"]["effective_final_approved"])
        self.assertEqual(projection["audit_rows"][0]["scope"], "gate:writing")

    def test_single_artifact_positive_final_review_is_unbound_and_not_approved(self):
        for review in ({"verdict": "meets"}, {"verdict": "partial"}):
            projection = project_task(self.task(status="completed", pm_final_review=review))
            self.assertFalse(projection["authority_summary"]["effective_final_approved"])
            self.assertTrue(any(item["kind"] == "artifact_ambiguous" for item in projection["data_quality"]))

    def test_single_artifact_accept_override_is_unbound_and_not_approved(self):
        projection = project_task(self.task(status="completed", final_review_override="accept"))
        self.assertFalse(projection["authority_summary"]["effective_final_approved"])
        self.assertTrue(any(item["kind"] == "artifact_ambiguous" for item in projection["data_quality"]))

    def test_matching_artifact_id_meets_creates_final_approval(self):
        projection = project_task(self.task(
            status="completed",
            pm_final_review={"verdict": "meets", "artifact_id": "T-TEST-result.md"},
        ))
        self.assertTrue(projection["authority_summary"]["effective_final_approved"])

    def test_matching_artifact_id_partial_creates_final_approval(self):
        projection = project_task(self.task(
            status="completed",
            pm_final_review={"verdict": "partial", "artifact_id": "T-TEST-result.md"},
        ))
        self.assertTrue(projection["authority_summary"]["effective_final_approved"])

    def test_matching_artifact_version_creates_final_approval(self):
        projection = project_task(self.task(
            status="completed",
            result_files=[{"name": "result.md", "version": "v2", "size": 10}],
            pm_final_review={"verdict": "meets", "artifact_version": "v2"},
        ))
        self.assertTrue(projection["authority_summary"]["effective_final_approved"])

    def test_matching_bound_review_accept_override_creates_final_approval(self):
        projection = project_task(self.task(
            status="completed",
            pm_final_review={"verdict": "not_meets", "artifact_id": "T-TEST-result.md"},
            final_review_override="accept",
        ))
        self.assertTrue(projection["authority_summary"]["effective_final_approved"])

    def test_gate_without_stage_id_preserves_unknown_scope_and_quality(self):
        projection = project_task(self.task(
            stages=[{"status": "completed", "gate": {"decision": "proceed"}}],
            result_files=[],
        ))
        self.assertTrue(any(item["kind"] == "scope_missing" for item in projection["data_quality"]))
        self.assertTrue(any(
            row["source_mechanism"] == "hermes_gate" and row["scope"] == "gate:unknown"
            for row in projection["audit_rows"]
        ))

    def test_missing_null_unknown_final_review_are_fail_safe(self):
        for review in (None, {}, {"verdict": "future"}, {"verdict": None}):
            projection = project_task(self.task(status="completed", pm_final_review=review))
            self.assertFalse(projection["authority_summary"]["effective_final_approved"])
            self.assertTrue(projection["audit_rows"])

    def test_final_not_meets_projects_hold(self):
        projection = project_task(self.task(status="needs_pm_review", pm_final_review={"verdict": "not_meets", "gaps": "CTA"}))
        self.assertEqual(projection["decision_queue_item"]["kind"], "final_review")
        self.assertEqual(projection["audit_rows"][-1]["normalized_decision"], "hold")

    def test_active_hold_blocks_positive_final_review(self):
        projection = project_task(self.task(status="completed", pm_final_review={"verdict": "meets"}, stages=[{"id": "verification", "status": "gate_hold", "gate_hold_reason": "needs evidence"}]))
        self.assertEqual(projection["work_group"], "blocked")
        self.assertFalse(projection["authority_summary"]["effective_final_approved"])
        self.assertTrue(any(item["kind"] == "conflict" for item in projection["data_quality"]))

    def test_live_note_never_creates_decision(self):
        projection = project_task(self.task(pm_live_notes=[{"note": "승인해 주세요", "at": "2026-07-21T10:00:00"}], status="in_progress"))
        self.assertTrue(any(row["source_mechanism"] == "pm_live_notes" and row["normalized_decision"] is None for row in projection["audit_rows"]))

    def test_unblock_and_scope_changed_are_not_invented(self):
        projection = project_task(self.task(status="in_progress"))
        normalized = {row["normalized_decision"] for row in projection["audit_rows"]}
        self.assertNotIn("unblock", normalized)
        self.assertNotIn("scope_changed", normalized)

    def test_ambiguous_artifacts_prevent_final_approval(self):
        projection = project_task(self.task(pm_final_review={"verdict": "meets"}, result_files=[{"name": "a"}, {"name": "b"}], status="completed"))
        self.assertEqual(projection["artifact_summary"]["state"], "ambiguous")
        self.assertFalse(projection["authority_summary"]["effective_final_approved"])

    def test_completed_compact_hides_raw_gate_details(self):
        projection = project_task(self.task(status="completed"))
        self.assertTrue(projection["compact"])
        self.assertTrue(projection["compact_hide_gate_details"])
        self.assertEqual(projection["audit_rows"][0]["source_value"], "proceed")

    def test_completed_detail_audit_preserves_gate_final_and_live_note_evidence(self):
        projection = project_task(self.task(status="completed", pm_final_review={"verdict": "meets"}, final_review_override="accept", pm_live_notes=[{"note": "context"}]))
        sources = {row["source_mechanism"] for row in projection["audit_rows"]}
        self.assertEqual(sources, {"hermes_gate", "pm_final_review", "final_review_override", "pm_live_notes"})

    def test_projection_does_not_mutate_raw_task(self):
        raw = self.task()
        before = copy.deepcopy(raw)
        project_task(raw)
        self.assertEqual(raw, before)

    def test_summary_counts_unknown_separately(self):
        views = [self.task(status="completed"), self.task(status="future_status")]
        summary = build_dashboard_summary(views)
        self.assertEqual(summary["counts"]["done"], 1)
        self.assertEqual(summary["counts"]["unknown"], 1)


if __name__ == "__main__":
    unittest.main()
