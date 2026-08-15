import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "operations_dashboard" / "index.html"


class DashboardStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_decision_first_section_order(self):
        ids = [
            "missionControlHeader",
            "decisionQueue",
            "activeWorkBoard",
            "reviewableArtifacts",
            "recentAudit",
        ]
        positions = [self.source.index(f'id="{section_id}"') for section_id in ids]
        self.assertEqual(positions, sorted(positions))
        recent_audit_label = '<p class="section-kicker">Recent Audit</p>'
        recent_audit_section = re.search(
            r'<section\b[^>]*id="recentAudit"[^>]*>.*?</section>',
            self.source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(recent_audit_section)
        assert recent_audit_section is not None
        self.assertIn(recent_audit_label, recent_audit_section.group(0))

    def test_dashboard_only_surface_has_required_hooks(self):
        for section_id in (
            "missionControlHeader",
            "decisionQueue",
            "activeWorkBoard",
            "reviewableArtifacts",
            "recentAudit",
            "taskBoard",
        ):
            self.assertIn(f'id="{section_id}"', self.source)
        self.assertIn('id="briefModal"', self.source)
        self.assertIn('id="detailModal"', self.source)

    def test_agent_stage_surface_is_absent(self):
        self.assertNotIn('id="agentActivitySnapshot"', self.source)
        self.assertNotIn('id="agentBoard"', self.source)
        self.assertNotIn("Agent Activity Snapshot", self.source)

    def test_forbidden_cross_surface_copy_is_absent(self):
        lowered = self.source.lower()
        for text in ("discord", "channel", "sync", "deep-link"):
            self.assertNotIn(text, lowered)

    def test_decision_queue_precedes_board_in_dom(self):
        queue = self.source.index('id="decisionQueue"')
        board = self.source.index('id="activeWorkBoard"')
        self.assertLess(queue, board)

    def test_render_contract_and_safe_pipeline_label_exist(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        for name in ("renderMissionControl", "renderDecisionQueue", "createDecisionQueueItem", "dataQualityLabel", "authorityPresentation"):
            self.assertRegex(js, rf"function {name}\(")
        self.assertIn("조사→작성→검증→최종본", js)
        self.assertNotIn("full: '전체 공정'", js)

    def test_active_work_card_is_outcome_first_and_detail_driven(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        card = js[js.index("function createTaskCard(task)"):js.index("function renderTasks(tasks)")]
        order = [
            "const outcome =",
            "const progress =",
            "const artifact =",
            "const trust =",
            "const authority = authorityPresentation",
            "const actionRow = el('div', 'task-actions task-card-primary-action')",
        ]
        positions = [card.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("extra.append(renderSeedWorkflow(task))", card)
        self.assertNotIn("live-note-row", card)
        self.assertNotIn("card.append(renderSeedWorkflow(task))", card)
        self.assertNotIn("card.append(liveWrap)", card)
        self.assertIn("extra.append(renderStageChips(task, compactHideGateDetails))", card)

    def test_task_cards_only_expose_read_only_detail_actions(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        card = js[js.index("function createTaskCard(task)"):js.index("function renderTasks(tasks)")]
        self.assertIn("cardDetailActionLabel(task)", card)
        self.assertIn("openTaskDetail(task, taskDetailBtn)", card)
        for forbidden in ("재전송", "다시 전송", "live-note", "라이브 노트", "final review", "최종 검토", "gateOverride(", "finalReviewOverride("):
            self.assertNotIn(forbidden, card.lower() if forbidden.isascii() else card)
        helper = js[js.index("function cardDetailActionLabel"):js.index("function humanStatus")]
        self.assertIn("업무 상세", helper)
        self.assertRegex(helper, r"재전송|다시\\s\\*전송")

    def test_card_projection_helpers_fail_safe_without_projection(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("return task.dashboard_projection || fallbackProjection(task);", js)
        self.assertIn("return '진행 단계 확인 불가';", js)
        self.assertIn("return '아직 확인 가능한 산출물 없음';", js)

    def test_reviewable_artifacts_are_projection_tiles_without_mtime_or_version_copy(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        renderer = js[js.index("function renderReviewableArtifacts(tasks)"):js.index("function renderTaskSummary(tasks)")]
        self.assertIn("artifact_summary?.items", renderer)
        self.assertIn("verification_summary?.items", renderer)
        self.assertIn("읽기 전용 근거", renderer)
        self.assertNotIn("modified_at", renderer)
        self.assertNotIn("version", renderer)

    def test_recent_audit_uses_current_projection_evidence_and_labels_live_context(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        renderer = js[js.index("function renderRecentFlow(tasks)"):js.index("function renderSimpleList")]
        self.assertIn("taskProjection(task)", renderer)
        self.assertIn("projection.audit_rows", renderer)
        self.assertIn("pm_live_notes: '비결정 맥락'", js)
        self.assertNotIn("modified_at", renderer)
        self.assertNotIn("mergeFlow(", renderer)

    def test_secondary_agent_context_is_collapsed_and_after_recent_audit(self):
        recent = self.source.index('id="recentAudit"')
        secondary = self.source.index('id="secondaryAgentContext"')
        self.assertLess(recent, secondary)
        self.assertIn('<details id="secondaryAgentContext"', self.source)
        self.assertNotIn('<details id="secondaryAgentContext" open', self.source)

    def test_task_detail_dialog_is_semantic_and_accessible(self):
        self.assertIn('id="taskDetailModal"', self.source)
        self.assertIn('role="dialog"', self.source)
        self.assertIn('aria-labelledby="taskDetailTitle"', self.source)
        self.assertIn('aria-describedby="taskDetailStatus"', self.source)
        self.assertIn('id="closeTaskDetailBtn"', self.source)
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        for hook in ("openTaskDetail", "closeTaskDetail", "taskDetailReturnFocus", "data-close-task-detail"):
            self.assertIn(hook, self.source + js)

    def test_all_task_entry_paths_use_same_detail_opening(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        card = js[js.index("function createTaskCard(task)"):js.index("function renderTasks(tasks)")]
        queue = js[js.index("function createDecisionQueueItem"):js.index("function renderMissionControl")]
        artifacts = js[js.index("function renderReviewableArtifacts"):js.index("function renderTaskSummary")]
        self.assertIn("openTaskDetail(task, taskDetailBtn)", card)
        self.assertIn("openTaskDetail(task, action)", queue)
        self.assertIn("openTaskDetail(task, row)", artifacts)

    def test_task_detail_sections_are_ordered_and_read_only(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        renderer = js[js.index("function renderTaskDetail(task)"):js.index("function openTaskDetail")]
        markers = ["'Outcome'", "'Stage timeline'", "'Artifacts'", "'Verification'", "'Authority / Audit'"]
        self.assertEqual([renderer.index(marker) for marker in markers], sorted(renderer.index(marker) for marker in markers))
        self.assertIn("taskProjection(task)", renderer)
        self.assertIn("선택된 업무 정보를 확인할 수 없습니다.", renderer)

    def test_stage_detail_separates_summary_timeline_from_raw_gate_disclosure(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        renderer = js[js.index("function renderTaskDetail(task)"):js.index("function openTaskDetail")]
        self.assertIn("renderTaskStageTimeline(task)", renderer)
        self.assertIn("renderRawGateAudit(projection)", renderer)
        timeline = js[js.index("function renderTaskStageTimeline"):js.index("function rawGateValue")]
        self.assertIn("stage.status", timeline)
        self.assertIn("stage.agents", timeline)
        self.assertNotIn("gateOverride", timeline)
        self.assertNotIn("승인", timeline)

    def test_raw_gate_audit_has_required_fields_and_safe_semantics(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        raw = js[js.index("function rawGateValue"):js.index("function renderScopedGateControls")]
        gate_label = js[js.index("function rawGateLabel"):js.index("function rawGateDecisionLabel")]
        audit = js[js.index("function renderRawGateAudit"):js.index("function renderTaskDetail")]
        for field in ("source", "value", "scope", "reason", "time", "actor", "correlation", "version"):
            self.assertIn(f"['{field}'", raw + audit)
        self.assertIn("원시 게이트 이력", audit)
        self.assertNotIn("GATE1.5", audit)
        self.assertIn("결정 없음", js)
        self.assertNotIn("normalized_decision", audit)
        self.assertNotIn("승인·진행", audit)
        self.assertNotIn("gate_id", audit)
        self.assertIn("근거 ${index + 1}", gate_label)
        self.assertIn("현재 원시 게이트 근거 없음", audit)
        self.assertIn("audit.source_mechanism || audit.source", audit)

    def test_raw_gate_and_authority_classifiers_do_not_infer_unsupported_evidence(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        gate = js[js.index("function rawGateLabel"):js.index("function rawGateDecisionLabel")]
        authority = js[js.index("function authorityStatus"):js.index("function authorityPresentation")]
        self.assertIn("원시 게이트 근거 ${index + 1}", gate)
        self.assertNotIn("GATE1.5", gate)
        self.assertNotIn("source_mechanism === 'hermes_gate'", gate)
        self.assertIn("return 'history-unavailable';", authority)
        self.assertNotIn("authority_summary", authority)
        self.assertNotIn("if (!rows.length) return 'decision-none'", authority)

    def test_authority_status_is_raw_only_and_audit_notice_is_present(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        detail = js[js.index("function renderTaskDetail(task)"):js.index("function openTaskDetail")]
        self.assertIn("function authorityStatus(projection)", js)
        for status in ("decision-none", "unknown", "history-unavailable"):
            self.assertIn(status, js)
        self.assertIn("audit-top-notice", detail)
        self.assertIn("현재 raw 상태에서 복구할 수 있는 내용으로 제한", detail)
        self.assertNotIn("effective_final_approved", js)
        self.assertNotIn("현재 raw 근거로 검토 완료", js)

    def test_task_detail_keeps_file_viewer_and_escape_focus_return(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function openDetail(dir, name)", js)
        self.assertIn("closeTaskDetail();", js[js.index("function setupModal"):js.index("function setupConversationMirror")])
        closer = js[js.index("function closeTaskDetail"):js.index("// 진행 상황")]
        self.assertIn("taskDetailReturnFocus.focus()", closer)

    def test_artifact_viewer_uses_named_top_layer_coordinator(self):
        self.assertIn('data-modal-layer="artifact-viewer"', self.source)
        self.assertIn('data-modal-layer="task-detail"', self.source)
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        for hook in ("modalStack", "syncModalCoordinator", "pushModal", "popModal", "topModal", "trapTopModal"):
            self.assertIn(hook, js)
        self.assertIn("if (top === 'detailModal') closeDetail();", js)
        self.assertIn("if (top === 'taskDetailModal') closeTaskDetail();", js)
        self.assertIn("event.isComposing", js)

    def test_viewer_preserves_read_only_iframe_security_and_mobile_fullscreen(self):
        html = self.source
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "operations_dashboard" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('aria-describedby="detailBody"', html)
        self.assertIn('iframe.setAttribute(\'sandbox\', \'allow-downloads\')', js)
        self.assertIn("iframe.setAttribute('referrerpolicy', 'no-referrer')", js)
        self.assertIn(".modal-layer-viewer .modal-panel", css)
        self.assertIn("height: 100vh", css)
        self.assertIn("data-modal-lock-count", js)

    def test_artifact_review_panel_is_evidence_first_and_fail_safe(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        panel = js[js.index("function renderArtifactReviewPanel"):js.index("function renderTaskDetail")]
        for marker in ("Artifacts", "Verification", "Target scope", "artifactBindingPresentation", "최종본 연결 확인 불가"):
            self.assertIn(marker, panel)
        self.assertLess(panel.index("artifact-review-binding"), panel.index("artifact-review-actions"))
        self.assertIn("검증 근거를 사용할 수 없습니다", panel)

    def test_final_review_uses_exact_honest_override_ctas_and_contract(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/final-review'", js)
        self.assertIn("JSON.stringify({ task_id: taskId, action })", js)
        self.assertEqual(js.count("최종 검토 override 요청"), 1)
        self.assertEqual(js.count("재작업 override 요청"), 1)
        self.assertIn("await loadDashboard();", js[js.index("async function finalReviewOverride"):js.index("async function gateOverride")])
        self.assertNotIn("이대로 승인", js)

    def test_scoped_controls_are_rendered_only_in_task_detail(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        chips = js[js.index("function renderStageChips"):js.index("const RESULT_WORKER_ORDER")]
        detail = js[js.index("function renderTaskStageTimeline"):js.index("function rawGateValue")]
        self.assertNotIn("gateOverride(", chips)
        self.assertIn("renderScopedGateControls(task, stage)", detail)
        self.assertIn("stage.status === 'entry_hold'", js)
        self.assertIn("stage.status === 'gate_hold'", js)

    def test_live_note_is_detail_context_not_decision_chip(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        card = js[js.index("function createTaskCard(task)"):js.index("function renderTasks(tasks)")]
        detail = js[js.index("function renderTaskLiveNoteContext"):js.index("function rawGateLabel")]
        self.assertNotIn("live-note-row", card)
        self.assertIn("task-detail-live-context", detail)
        self.assertIn("live-note-context-item", detail)
        self.assertNotIn("chip live-note-chip", detail)

    def test_responsive_layout_contract_has_three_density_tiers(self):
        css = (ROOT / "operations_dashboard" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("@media (min-width: 1200px)", css)
        self.assertIn("@media (min-width: 768px) and (max-width: 1199px)", css)
        self.assertIn("@media (max-width: 767px)", css)
        wide = css[css.index("@media (min-width: 1200px)"):css.index("@media (min-width: 768px)")]
        medium = css[css.index("@media (min-width: 768px)"):css.index("@media (max-width: 767px)")]
        narrow = css[css.index("@media (max-width: 767px)"):]
        self.assertIn(".flow-grid { grid-template-columns: repeat(2", wide)
        self.assertIn(".task-board { grid-template-columns: repeat(3", wide)
        self.assertIn(".task-board { grid-template-columns: repeat(2", medium)
        self.assertIn(".flow-grid,", medium)
        self.assertIn(".task-board,", narrow)
        self.assertIn(".decision-queue-item", narrow)

    def test_artifact_review_essentials_and_raw_context_have_static_hooks(self):
        css = (ROOT / "operations_dashboard" / "styles.css").read_text(encoding="utf-8")
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        for hook in ("artifact-review-panel", "artifact-review-block", "artifact-review-binding", "artifact-review-actions"):
            self.assertIn(hook, css + js)
        self.assertIn("raw-gate-disclosure", js)
        self.assertIn('<details id="secondaryAgentContext"', self.source)

    def test_touch_targets_and_status_cues_are_explicit(self):
        css = (ROOT / "operations_dashboard" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("button,", css)
        self.assertIn("min-height: 44px", css)
        for status in (".badge.ok::before", ".badge.wait::before", ".badge.warn::before", ".badge.danger::before"):
            self.assertIn(status, css)

    def test_legacy_write_contracts_and_refresh_semantics_are_preserved(self):
        js = (ROOT / "operations_dashboard" / "app.js").read_text(encoding="utf-8")
        gate = js[js.index("async function gateOverride"):js.index("async function createInterview")]
        final = js[js.index("async function finalReviewOverride"):js.index("async function gateOverride")]
        live = js[js.index("async function submitLiveNote"):js.index("function shortPreview")]
        self.assertIn("fetch('/api/gate-override'", gate)
        self.assertIn("{ task_id: taskId, stage_id: stageId, action }", gate)
        self.assertIn("await loadDashboard();", gate)
        self.assertIn("fetch('/api/final-review'", final)
        self.assertIn("{ task_id: taskId, action }", final)
        self.assertIn("await loadDashboard();", final)
        self.assertIn("fetch('/api/live-note'", live)
        self.assertIn("{ task_id: taskId, note }", live)
        self.assertNotIn("approved =", js)
        self.assertNotIn("final = true", js)


if __name__ == "__main__":
    unittest.main()
