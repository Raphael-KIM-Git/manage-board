import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import operations_followup_requests as followups


class FollowUpRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, **extra):
        value = {
            "target": {"kind": "task", "id": "T-20260729-001"},
            "request_type": "verification",
            "title": "모바일 검증 추가",
            "desired_outcome": "390px 브라우저 결과와 이슈 목록",
            "context": "기존 결과의 미검증 항목",
            "constraints": "production 변경 금지",
            "priority_requested": "medium",
            "verification_requested": ["browser_390px"],
        }
        value.update(extra)
        return value

    def test_valid_submit_is_auditable_and_parent_is_not_touched(self):
        parent = {"task_id": "T-20260729-001", "status": "completed", "stages": [{"id": "writing", "status": "completed"}]}
        before = copy.deepcopy(parent)
        record, created = followups.submit_request(parent["task_id"], self.payload(), "key-1", requests_dir=self.root, task_exists=lambda _: True)
        self.assertTrue(created)
        self.assertEqual(record["state"], "pending_pm_review")
        self.assertEqual(record["version"], 1)
        self.assertEqual(record["submitted_by"]["actor_id"], "Raphael")
        self.assertEqual(parent, before)
        stored = list((self.root / parent["task_id"]).glob("*.json"))
        self.assertEqual(len(stored), 1)
        self.assertEqual(json.loads(stored[0].read_text())["parent_task_id"], parent["task_id"])

    def test_idempotency_retry_and_conflict(self):
        first, created = followups.submit_request("T-1", self.payload(target={"kind": "task", "id": "T-1"}), "same", requests_dir=self.root, task_exists=lambda _: True)
        retry, created_again = followups.submit_request("T-1", self.payload(target={"kind": "task", "id": "T-1"}), "same", requests_dir=self.root, task_exists=lambda _: True)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["request_id"], retry["request_id"])
        with self.assertRaises(followups.FollowUpConflict):
            followups.submit_request("T-1", self.payload(target={"kind": "task", "id": "T-1"}, title="다른 요청"), "same", requests_dir=self.root, task_exists=lambda _: True)

    def test_completed_parent_remains_valid_and_concurrent_submit_deduplicates(self):
        results = []
        payload = self.payload(target={"kind": "task", "id": "T-1"})
        def submit():
            results.append(followups.submit_request("T-1", payload, "concurrent", requests_dir=self.root, task_exists=lambda _: True))
        threads = [threading.Thread(target=submit) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len(list((self.root / "T-1").glob("*.json"))), 1)

    def test_write_failure_leaves_no_partial_sidecar(self):
        with patch.object(followups, "_atomic_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                followups.submit_request("T-1", self.payload(target={"kind": "task", "id": "T-1"}), "fail", requests_dir=self.root, task_exists=lambda _: True)
        self.assertFalse(list(self.root.rglob("*.json")))
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_validation_and_unknown_parent_fail_closed(self):
        with self.assertRaises(followups.FollowUpError):
            followups.submit_request("T-1", self.payload(title=""), "key", requests_dir=self.root, task_exists=lambda _: True)
        with self.assertRaises(FileNotFoundError):
            followups.submit_request("T-unknown", self.payload(target={"kind": "task", "id": "T-unknown"}), "key", requests_dir=self.root, task_exists=lambda _: False)


if __name__ == "__main__":
    unittest.main()
