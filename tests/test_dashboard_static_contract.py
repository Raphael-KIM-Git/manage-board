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
        self.assertIn("extra.append(liveWrap)", card)
        self.assertNotIn("card.append(renderSeedWorkflow(task))", card)
        self.assertNotIn("card.append(liveWrap)", card)
        self.assertIn("extra.append(renderStageChips(task, compactHideGateDetails))", card)

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


if __name__ == "__main__":
    unittest.main()
