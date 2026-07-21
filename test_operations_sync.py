import unittest

import operations_sync as sync


class ResearchStageCompletionTests(unittest.TestCase):
    def test_failed_results_do_not_complete_research(self):
        task = {
            "task_id": "T-TEST-FAILED",
            "assigned_workers": ["HermesResearcher", "researcher-co"],
            "stages": [
                {
                    "id": "research",
                    "agents": ["HermesResearcher", "researcher-co"],
                    "dispatched_workers": ["HermesResearcher", "researcher-co"],
                }
            ],
        }
        result_map = {
            task["task_id"]: [
                {"worker_key": "hermesresearcher", "status": "failed"},
                {"worker_key": "researcher-co", "status": "failed"},
            ]
        }

        completed, status = sync.research_stage_complete(task, result_map)

        self.assertFalse(completed)
        self.assertEqual(status, "results_received")

    def test_gate_selected_single_worker_can_complete_research(self):
        task = {
            "task_id": "T-TEST-SINGLE",
            "assigned_workers": ["HermesResearcher", "researcher-co", "researcher_agent"],
            "stages": [
                {
                    "id": "research",
                    "agents": ["HermesResearcher", "researcher-co", "researcher_agent"],
                    "dispatched_workers": ["HermesResearcher"],
                }
            ],
        }
        result_map = {
            task["task_id"]: [
                {"worker_key": "hermesresearcher", "status": "completed"},
            ]
        }

        completed, status = sync.research_stage_complete(task, result_map)

        self.assertTrue(completed)
        self.assertEqual(status, "waiting_verification")

    def test_partial_completed_results_remain_partial(self):
        task = {
            "task_id": "T-TEST-PARTIAL",
            "assigned_workers": ["HermesResearcher", "researcher-co"],
            "stages": [{"id": "research", "dispatched_workers": ["HermesResearcher", "researcher-co"]}],
        }
        result_map = {
            task["task_id"]: [
                {"worker_key": "HermesResearcher", "status": "completed"},
                {"worker_key": "researcher-co", "status": "failed"},
            ]
        }

        completed, status = sync.research_stage_complete(task, result_map)

        self.assertFalse(completed)
        self.assertEqual(status, "partial_results")

    def test_all_selected_workers_must_be_completed(self):
        task = {
            "task_id": "T-TEST-ALL",
            "assigned_workers": ["HermesResearcher", "researcher-co"],
            "stages": [{"id": "research", "dispatched_workers": ["HermesResearcher", "researcher-co"]}],
        }
        result_map = {
            task["task_id"]: [
                {"worker_key": "HermesResearcher", "status": "completed"},
                {"worker_key": "researcher-co", "status": "completed"},
            ]
        }

        completed, status = sync.research_stage_complete(task, result_map)

        self.assertTrue(completed)
        self.assertEqual(status, "waiting_verification")


if __name__ == "__main__":
    unittest.main()
