import tempfile
import unittest
from pathlib import Path

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


class ResearchEvidencePolicyTests(unittest.TestCase):
    def test_research_stage_brief_contains_versioned_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = sync.STAGE_BRIEFS
            sync.STAGE_BRIEFS = Path(tmp)
            try:
                task = {
                    'task_id': 'T-TEST-POLICY', 'title': 'Evidence task',
                    'assigned_workers': ['researcher-co'], 'constraints': 'GET only',
                }
                brief = sync.create_stage_brief(task, 'research', 'inspect public sources', derived_id=task['task_id'])
                self.assertEqual(brief['research_evidence_policy']['version'], '1.0')
                self.assertIn('직접 확인 기록 필드', Path(brief['artifacts']['markdown_brief']).read_text())
            finally:
                sync.STAGE_BRIEFS = old_dir

    def test_policy_is_not_added_for_non_research_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = sync.STAGE_BRIEFS
            sync.STAGE_BRIEFS = Path(tmp)
            try:
                task = {'task_id': 'T-TEST-WRITE', 'title': 'Write task', 'constraints': 'none'}
                brief = sync.create_stage_brief(task, 'writing', 'source text')
                self.assertNotIn('research_evidence_policy', brief)
                self.assertNotIn('Research Evidence Policy', Path(brief['artifacts']['markdown_brief']).read_text())
            finally:
                sync.STAGE_BRIEFS = old_dir


class DerivedStageEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_briefs = sync.BRIEFS
        self.old_results = sync.RESULTS
        sync.BRIEFS = Path(self.tmp.name) / 'briefs'
        sync.BRIEFS.mkdir()
        sync.RESULTS = Path(self.tmp.name)

    def tearDown(self):
        sync.BRIEFS = self.old_briefs
        sync.RESULTS = self.old_results
        self.tmp.cleanup()

    def task(self):
        return {
            'task_id': 'T-20260729-001',
            'stages': [
                {'id': 'writing', 'status': 'in_progress', 'derived_task_id': 'T-20260729-001-writing',
                 'dispatched_workers': ['writer-co']},
                {'id': 'verification', 'status': 'queued', 'agents': ['verify-co']},
            ],
        }

    def write_envelope(self, payload):
        report = payload.get('report_file')
        if report:
            (sync.RESULTS / report).write_text('report', encoding='utf-8')

    def test_completed_writer_envelope_correlates_to_parent_stage(self):
        envelope = {
            'task_id': 'T-20260729-001-writing', 'worker': 'writer-co', 'worker_key': 'writer-co',
            'status': 'completed', 'finished_at': '2026-07-29T13:03:52+09:00',
            'report_file': 'T-20260729-001-writing__writer-co.md',
        }
        self.write_envelope(envelope)
        accepted, rejected = sync.stage_result_envelopes(self.task(), 'writing', {envelope['task_id']: [envelope]})
        self.assertEqual(accepted, [envelope])
        self.assertEqual(rejected, [])

    def test_mismatch_failed_blocked_and_unparseable_never_correlate(self):
        task = self.task()
        cases = [
            {'task_id': 'T-20260729-001-writing', 'worker_key': 'verify-co', 'status': 'completed', 'report_file': 'x.md'},
            {'task_id': 'T-20260729-001-writing', 'worker_key': 'writer-co', 'status': 'failed', 'report_file': 'x.md'},
            {'task_id': 'T-20260729-001-writing', 'worker_key': 'writer-co', 'status': 'blocked', 'report_file': 'x.md'},
            {'task_id': 'T-20260729-001-writing', 'worker_key': 'writer-co', 'status': 'completed'},
        ]
        accepted, rejected = sync.stage_result_envelopes(task, 'writing', {'T-20260729-001-writing': cases + ['not-json']})
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 5)

    def test_cross_task_report_file_never_correlates(self):
        task = self.task()
        task['stages'][0]['derived_task_id'] = 'T-20260729-001-writing-r1'
        envelope = {
            'task_id': 'T-20260729-001-writing-r1', 'worker_key': 'writer-co', 'status': 'completed',
            'report_file': 'T-OTHER-final__writer-co.md',
        }
        self.write_envelope(envelope)
        accepted, rejected = sync.stage_result_envelopes(
            task, 'writing', {envelope['task_id']: [envelope]}
        )
        self.assertEqual(accepted, [])
        self.assertTrue(any('report_identity_mismatch' in reason for reason in rejected))

    def test_sync_task_statuses_keeps_stage_in_progress_for_cross_task_report(self):
        task = {
            'task_id': 'T-20260729-001',
            'pipeline_name': 'research-write-verify-finalize',
            'status': 'in_progress',
            'title': 'fixture',
            'objective': 'fixture',
            'stages': [
                {'id': 'research', 'status': 'completed', 'agents': ['researcher-co']},
                {'id': 'writing', 'status': 'in_progress',
                 'derived_task_id': 'T-20260729-001-writing-r1',
                 'dispatched_workers': ['writer-co']},
                {'id': 'verification', 'status': 'queued', 'agents': ['verify-co']},
                {'id': 'final_write', 'status': 'planned', 'agents': ['writer-co']},
            ],
        }
        envelope = {
            'task_id': 'T-20260729-001-writing-r1', 'worker_key': 'writer-co', 'status': 'completed',
            'report_file': 'T-OTHER-final__writer-co.md',
        }
        (sync.BRIEFS / 'T-20260729-001.json').write_text(__import__('json').dumps(task), encoding='utf-8')
        (sync.RESULTS / 'envelope.json').write_text(__import__('json').dumps(envelope), encoding='utf-8')
        notes = sync.sync_task_statuses()
        updated = __import__('json').loads((sync.BRIEFS / 'T-20260729-001.json').read_text(encoding='utf-8'))
        self.assertEqual(updated['stages'][1]['status'], 'in_progress')
        self.assertEqual(updated['status'], 'in_progress')
        self.assertTrue(any('writing evidence rejected=' in note for note in notes))

    def test_report_identity_must_match_derived_task_and_worker(self):
        for report_file in (
            'T-20260729-001-writing-r1.md',
            'T-20260729-001-writing-r1__verify-co.md',
            'arbitrary.md',
        ):
            with self.subTest(report_file=report_file):
                envelope = {
                    'task_id': 'T-20260729-001-writing-r1', 'worker_key': 'writer-co', 'status': 'completed',
                    'report_file': report_file,
                }
                self.write_envelope(envelope)
                accepted, _ = sync.stage_result_envelopes(
                    self.task(), 'writing', {envelope['task_id']: [envelope]}
                )
                self.assertEqual(accepted, [])

    def test_repeated_valid_sync_evidence_is_idempotent(self):
        envelope = {
            'task_id': 'T-20260729-001-writing', 'worker_key': 'writer-co', 'status': 'completed',
            'report_file': 'T-20260729-001-writing__writer-co.md',
        }
        self.write_envelope(envelope)
        result_map = {envelope['task_id']: [envelope]}
        self.assertEqual(sync.stage_result_envelopes(self.task(), 'writing', result_map),
                         sync.stage_result_envelopes(self.task(), 'writing', result_map))

    def test_duplicate_valid_sidecars_are_ambiguous_and_never_complete(self):
        task = self.task()
        first = {
            'task_id': 'T-20260729-001-writing', 'worker_key': 'writer-co', 'status': 'completed',
            'report_file': 'T-20260729-001-writing__writer-co.md',
        }
        second = {**first, 'report_file': 'T-20260729-001-writing__writer-co-v2.md'}
        self.write_envelope(first)
        self.write_envelope(second)
        accepted, rejected = sync.stage_result_envelopes(
            task, 'writing', {first['task_id']: [first, second]}
        )
        self.assertEqual(accepted, [])
        self.assertTrue(any('duplicate_or_ambiguous' in reason for reason in rejected))


if __name__ == "__main__":
    unittest.main()
