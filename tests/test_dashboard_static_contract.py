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


if __name__ == "__main__":
    unittest.main()
