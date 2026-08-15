import copy
import unittest

from operations_dashboard_projection import (
    build_dashboard_summary,
    classify_raw,
    project_progress,
    project_operations_evidence,
    project_final_deliverable,
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

    def test_operations_evidence_is_observational_and_stale_safe(self):
        task = self.task(task_id="T-SYNC", updated_at="2026-07-29T20:00:00+00:00", status="completed")
        sync = {"observed_at": "2026-07-29T20:01:00+00:00", "last_result": "success",
                "status_updates": ["T-SYNC:completed", "T-OTHER:failed"]}
        watchdog = {"observed_at": "2026-07-29T19:00:00+00:00", "active_tasks": [{"task_id": "T-SYNC", "status": "in_progress"}]}
        evidence = project_operations_evidence(task, sync, watchdog,
                                               now=__import__("datetime").datetime.fromisoformat("2026-07-29T20:02:00+00:00"),
                                               sync_freshness_seconds=900, watchdog_freshness_seconds=900)
        self.assertEqual(evidence["sync"]["state"], "success")
        self.assertEqual(evidence["sync"]["task_transition_evidence"], ["T-SYNC:completed"])
        self.assertEqual(evidence["watchdog"]["state"], "stale")
        self.assertEqual(evidence["watchdog"]["source_limitation"], "snapshot_older_than_task_raw")
        self.assertEqual(task["status"], "completed")

    def test_operations_evidence_missing_and_malformed_are_safe(self):
        task = self.task(task_id="T-SAFE")
        evidence = project_operations_evidence(task, "not-json", {})
        self.assertEqual(evidence["sync"]["state"], "unknown")
        self.assertEqual(evidence["watchdog"]["state"], "never_observed")
        malformed = project_operations_evidence(task, {"_malformed_snapshot": True}, None)
        self.assertEqual(malformed["sync"]["state"], "unknown")
        self.assertEqual(malformed["sync"]["source_limitation"], "malformed_snapshot")

    def test_operations_evidence_requires_exact_task_id_correlation(self):
        task = self.task(task_id="T-1")
        sync = {"observed_at": "2026-07-21T10:01:00+00:00", "last_result": "success",
                "status_updates": [
                    "T-10:completed",
                    "T-1:completed",
                    {"task_id": "T-10", "status": "completed"},
                    {"task_id": "T-1", "status": "completed"},
                ]}
        original = copy.deepcopy(sync)
        evidence = project_operations_evidence(
            task, sync, now=__import__("datetime").datetime.fromisoformat("2026-07-21T10:02:00+00:00")
        )
        self.assertEqual(evidence["sync"]["task_transition_evidence"], [
            "T-1:completed", {"task_id": "T-1", "status": "completed"}
        ])
        self.assertEqual(sync, original)

    def test_operations_evidence_rejects_ambiguous_transition_shapes(self):
        task = self.task(task_id="T-1")
        sync = {"observed_at": "2026-07-21T10:01:00+00:00", "last_result": "success",
                "status_updates": ["T-1", {"task_id": "T-1"}, {"task_id": 1, "status": "completed"},
                                    {"task_id": "T-1", "status": None}]}
        evidence = project_operations_evidence(
            task, sync, now=__import__("datetime").datetime.fromisoformat("2026-07-21T10:02:00+00:00")
        )
        self.assertEqual(evidence["sync"]["task_transition_evidence"], [])

    def progress_task(self, **overrides):
        task = {
            "task_id": "T-PROGRESS",
            "status": "in_progress",
            "stages": [{"id": "writing", "status": "in_progress", "agents": ["writer-co"]}],
            "dispatches": {"writer-co": "dispatched"},
            "result_files": [],
            "result_metadata": [],
            "verification_files": [],
        }
        task.update(overrides)
        return task

    def result(self, worker="writer-co", stage="writing", status="completed", report="T-PROGRESS-writing-worker.md"):
        return {
            "name": report,
            "metadata": {"task_id": "T-PROGRESS", "worker": worker, "stage_id": stage, "status": status, "report_file": report},
        }

    def test_progress_ten_prd_safety_scenarios(self):
        # 1: dispatch only never becomes a result.
        p = project_progress(self.progress_task())
        self.assertEqual(p["agent_states"]["writing"]["writer-co"], "dispatch_confirmed")
        self.assertEqual(p["next_pm_action"]["kind"], "wait_for_result")
        # 2: partial results stay partial and do not complete the stage.
        partial = self.progress_task(stages=[{"id": "writing", "status": "in_progress", "agents": ["a", "b", "c"]}], dispatches={"a": "dispatched", "b": "dispatched", "c": "dispatched"}, result_files=[{"name": "T-PROGRESS-writing-a.md"}], result_metadata=[self.result("a", report="T-PROGRESS-writing-a.md")])
        pp = project_progress(partial)
        self.assertEqual(pp["agent_states"]["writing"]["_maturity"], "partial_received")
        self.assertNotEqual(pp["agent_states"]["writing"]["_raw_status"], "completed")
        # 3: all results are reviewable while raw stage remains in progress.
        complete = self.progress_task(stages=[{"id": "writing", "status": "in_progress", "agents": ["writer-co"]}], result_files=[{"name": "T-PROGRESS-writing-worker.md"}], result_metadata=[self.result()])
        cp = project_progress(complete)
        self.assertEqual(cp["agent_states"]["writing"]["writer-co"], "result_received")
        self.assertEqual(cp["agent_states"]["writing"]["_maturity"], "reviewable")
        # 4: failed metadata wins over dispatched.
        failed = project_progress(self.progress_task(result_files=[{"name": "T-PROGRESS-writing-worker.md"}], result_metadata=[self.result(status="failed")]))
        self.assertEqual(failed["agent_states"]["writing"]["writer-co"], "failed_or_blocked")
        self.assertEqual(failed["next_pm_action"]["kind"], "blocked")
        # 5: unlinked worker/stage is unknown, not dispatch confirmed.
        unknown = self.progress_task(result_files=[{"name": "stray.md"}], result_metadata=[self.result(worker="other", stage="research", report="stray.md")])
        unknown_projection = project_progress(unknown)
        self.assertEqual(unknown_projection["agent_states"]["writing"]["writer-co"], "unknown")
        self.assertIn("귀속", unknown_projection["agent_states"]["writing"]["_limitations"]["writer-co"])
        self.assertEqual(unknown_projection["next_pm_action"]["kind"], "unknown")
        self.assertTrue(unknown_projection["ambiguous_files"])
        # Explicitly unrelated metadata must not downgrade a different stage's agents.
        unrelated = self.progress_task(
            stages=[
                {"id": "research", "status": "completed", "agents": ["researcher-co"]},
                {"id": "writing", "status": "in_progress", "agents": ["writer-co"]},
            ],
            result_files=[{"name": "research.md"}],
            result_metadata=[self.result(worker="other", stage="research", report="research.md")],
        )
        unrelated_projection = project_progress(unrelated)
        self.assertEqual(unrelated_projection["agent_states"]["research"]["researcher-co"], "not_dispatched")
        filename_only = project_progress(self.progress_task(result_files=[{"name": "filename-only.md"}]))
        self.assertEqual(filename_only["agent_states"]["writing"]["writer-co"], "unknown")
        self.assertEqual(filename_only["next_pm_action"]["kind"], "unknown")
        # 6: md/json sidecar is one bundle.
        bundle = project_progress(complete)
        self.assertEqual(len(bundle["bundles"]), 1)
        self.assertEqual(len(bundle["bundles"][0]["files"]), 2)
        # 7: verification file without binding is not verified.
        no_binding = self.progress_task(verification_files=[{"metadata": {"status": "completed"}}])
        self.assertEqual(project_progress(no_binding)["verification_state"], "available_unstructured")
        # 8: matching verdict and binding is verified.
        bound = self.progress_task(result_files=[{"name": "T-PROGRESS-writing-worker.md"}], result_metadata=[self.result()], verification_metadata=[{"metadata": {"status": "completed", "artifact_id": "T-PROGRESS-writing-worker.md"}}], verification_files=[{"name": "v.json"}])
        self.assertEqual(project_progress(bound)["verification_state"], "verified")
        # 9: live note is not consulted.
        noted = self.progress_task(pm_live_notes=[{"note": "승인 완료"}])
        self.assertEqual(project_progress(noted)["agent_states"]["writing"]["writer-co"], "dispatch_confirmed")
        # 10: missing/null/future status remains fail-safe.
        for raw in ({}, {"status": None}, {"status": "future"}):
            self.assertIn(project_progress(self.progress_task(**raw))["next_pm_action"]["kind"], {"wait_for_result", "progress"})

    def test_representative_task_contract(self):
        task = {
            "task_id": "T-20260729-001", "status": "dispatched",
            "stages": [
                {"id": "research", "status": "completed", "agents": ["HermesResearcher", "researcher-co", "researcher_agent"]},
                {"id": "writing", "status": "in_progress", "agents": ["writer-co"]},
                {"id": "verification", "status": "planned", "agents": ["verify-co"]},
                {"id": "final_write", "status": "skipped", "agents": ["writer-co"]},
            ],
            "dispatches": {"writer-co": "dispatched"},
            "result_files": [{"name": f"T-20260729-001__{w}.md"} for w in ("HermesResearcher", "researcher-co", "researcher_agent")],
            "result_metadata": [{"name": f"T-20260729-001__{w}.json", "metadata": {"task_id": "T-20260729-001", "worker": w, "stage_id": "research", "status": "completed", "report_file": f"T-20260729-001__{w}.md"}} for w in ("HermesResearcher", "researcher-co", "researcher_agent")],
            "verification_files": [],
        }
        projection = project_task(task)
        progress = projection["progress"]
        self.assertEqual(progress["current_stage"], "writing")
        self.assertEqual(progress["agent_states"]["research"]["_received"], 3)
        self.assertEqual(progress["agent_states"]["writing"]["writer-co"], "dispatch_confirmed")
        self.assertEqual(progress["next_pm_action"]["label"], "작성 결과 도착 확인")
        self.assertEqual(projection["verification_summary"]["state"], "not_run")

    def test_representative_skipped_final_write_never_promotes_html_candidate(self):
        task = {
            "task_id": "T-20260729-001", "status": "completed", "pipeline_shape": "write_verify",
            "stages": [
                {"id": "writing", "status": "completed", "agents": ["writer-co"], "derived_task_id": "T-20260729-001-writing-r1"},
                {"id": "verification", "status": "completed", "agents": ["verify-co"], "derived_task_id": "T-20260729-001-verify"},
                {"id": "final_write", "status": "skipped"},
            ],
            "result_files": [
                {"name": "T-20260729-001-writing-r1__writer-co.md"},
                {"name": "T-20260729-001-writing-r1__writer-co__130629.html"},
                {"name": "T-20260729-001-writing-r1__writer-co__165206.html"},
            ],
            "result_metadata": [{"name": "r1.json", "metadata": {
                "task_id": "T-20260729-001-writing-r1", "worker": "writer-co", "stage_id": "writing",
                "status": "completed", "report_file": "T-20260729-001-writing-r1__writer-co.md",
            }}],
            "verification_files": [{"name": "verify.json"}],
            "verification_metadata": [{"name": "verify.json", "metadata": {"status": "completed"}}],
            "pm_final_review": {"verdict": "meets"},
        }
        final = project_final_deliverable(task)
        self.assertEqual(final["state"], "ambiguous")
        self.assertEqual(final["reason_code"], "multiple_equal_candidates")
        self.assertIsNone(final["artifact"])

    def test_bound_skipped_final_write_confirms_report_artifact(self):
        task = self.task(
            task_id="T-BOUND", status="completed", pipeline_shape="write_verify",
            stages=[{"id": "writing", "status": "completed", "agents": ["writer-co"], "derived_task_id": "T-BOUND-writing-r1"}, {"id": "final_write", "status": "skipped"}],
            result_files=[{"name": "T-BOUND-writing-r1.md"}],
            result_metadata=[{"name": "r.json", "metadata": {"task_id": "T-BOUND-writing-r1", "worker": "writer-co", "stage_id": "writing", "status": "completed", "report_file": "T-BOUND-writing-r1.md", "artifact_id": "artifact-1", "artifact_version": "v1"}}],
            verification_files=[{"name": "verify.json"}],
            verification_metadata=[{"name": "verify.json", "metadata": {"status": "verified", "artifact_id": "artifact-1", "artifact_version": "v1"}}],
            pm_final_review={"verdict": "meets", "artifact_id": "artifact-1", "artifact_version": "v1"},
        )
        final = project_final_deliverable(task)
        self.assertEqual(final["state"], "confirmed")
        self.assertEqual(final["artifact"]["name"], "T-BOUND-writing-r1.md")

    def test_derived_attempts_project_to_parent_stage_without_filename_guessing(self):
        task = {
            "task_id": "T-20260729-001", "status": "completed",
            "stages": [
                {"id": "research", "status": "completed", "agents": ["researcher-co"]},
                {"id": "writing", "status": "completed", "agents": ["writer-co"],
                 "derived_task_id": "T-20260729-001-writing-r1"},
                {"id": "verification", "status": "completed", "agents": ["verify-co"],
                 "derived_task_id": "T-20260729-001-verify"},
            ],
            "result_files": [
                {"name": "T-20260729-001-writing__writer-co.md"},
                {"name": "T-20260729-001-writing-r1__writer-co.md"},
                {"name": "T-20260729-001-writing-r1__writer-co.html"},
                {"name": "T-20260729-001-verify__verify-co.md"},
            ],
            "result_metadata": [
                {"name": "old.json", "metadata": {"task_id": "T-20260729-001-writing", "worker": "writer-co", "stage_id": "writing", "status": "completed", "report_file": "T-20260729-001-writing__writer-co.md"}},
                {"name": "r1.json", "metadata": {"task_id": "T-20260729-001-writing-r1", "worker": "writer-co", "stage_id": "writing", "status": "completed", "report_file": "T-20260729-001-writing-r1__writer-co.md"}},
                {"name": "verify.json", "metadata": {"task_id": "T-20260729-001-verify", "worker": "verify-co", "stage_id": "verification", "status": "completed", "report_file": "T-20260729-001-verify__verify-co.md"}},
            ],
            "verification_files": [],
        }
        progress = project_progress(task)
        writing = progress["agent_states"]["writing"]
        self.assertEqual(writing["writer-co"], "result_received")
        self.assertEqual(writing["_bundles"][0]["derived_task_id"], "T-20260729-001-writing-r1")
        self.assertEqual(progress["agent_states"]["verification"]["verify-co"], "result_received")
        self.assertEqual(progress["agent_states"]["verification"]["_maturity"], "reviewable")
        self.assertTrue(any(bundle.get("history") for bundle in progress["bundles"]))

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
