import hashlib
import tempfile
import unittest
from pathlib import Path

from artifact_contract import emit_artifact_manifest, validate_artifact_manifest
from operations_dashboard_projection import project_final_deliverable


class ArtifactContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "deliverable.md"
        self.path.write_bytes(b"primary bytes")

    def tearDown(self):
        self.tmp.cleanup()

    def envelope(self):
        emitted = emit_artifact_manifest(self.path, "art-1")
        return {
            "task_id": "T-V2-writing", "worker": "writer-co", "worker_key": "writer-co",
            "status": "completed", "report_file": self.path.name, **emitted,
        }

    def test_emission_is_sha256_and_validation_checks_bytes(self):
        envelope = self.envelope()
        digest = hashlib.sha256(b"primary bytes").hexdigest()
        self.assertEqual(envelope["artifact_manifest"]["primary_artifact_version"], "sha256:" + digest)
        self.assertTrue(validate_artifact_manifest(envelope, self.root)["valid"])
        self.path.write_bytes(b"tampered")
        self.assertEqual(validate_artifact_manifest(envelope, self.root)["reason"], "content_digest_mismatch")

    def test_duplicate_primary_missing_pair_and_traversal_are_rejected(self):
        envelope = self.envelope()
        items = envelope["artifact_manifest"]["artifacts"]
        envelope["artifact_manifest"]["artifacts"] = items + [dict(items[0], file_name="other.md")]
        self.assertEqual(validate_artifact_manifest(envelope, self.root)["reason"], "primary_count_invalid")
        envelope = self.envelope()
        envelope["artifact_manifest"]["primary_artifact_version"] = "sha256:" + "0" * 64
        self.assertEqual(validate_artifact_manifest(envelope, self.root)["reason"], "top_level_primary_mismatch")
        envelope = self.envelope()
        envelope["artifact_manifest"]["artifacts"][0]["file_name"] = "../deliverable.md"
        self.assertEqual(validate_artifact_manifest(envelope, self.root)["reason"], "file_name_invalid")

    def test_v2_final_write_rule_a_confirms_without_bindings(self):
        envelope = self.envelope()
        task = {
            "task_id": "T-V2", "status": "completed",
            "stages": [
                {"id": "final_write", "status": "completed", "agents": ["writer-co"], "derived_task_id": "T-V2-final_write"},
            ],
            "result_files": [{"name": self.path.name, "path": str(self.path)}],
            "result_metadata": [{"name": "envelope.json", "metadata": {**envelope, "task_id": "T-V2-final_write"}}],
        }
        result = project_final_deliverable(task)
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(result["artifact"]["artifact_id"], "art-1")

    def test_v2_skipped_requires_exact_positive_bindings(self):
        envelope = self.envelope()
        target = {"artifact_id": "art-1", "artifact_version": envelope["artifact_manifest"]["primary_artifact_version"]}
        task = {
            "task_id": "T-V2", "status": "completed", "pipeline_shape": "write_verify",
            "stages": [
                {"id": "writing", "status": "completed", "agents": ["writer-co"], "derived_task_id": "T-V2-writing"},
                {"id": "verification", "status": "completed", "agents": ["verify-co"], "derived_task_id": "T-V2-verify"},
                {"id": "final_write", "status": "skipped"},
            ],
            "result_files": [{"name": self.path.name, "path": str(self.path)}],
            "result_metadata": [{"name": "envelope.json", "metadata": {**envelope, "task_id": "T-V2-writing"}}],
            "verification_metadata": [{"name": "verify.json", "metadata": {"status": "passed", "target_artifact": target}}],
            "pm_final_review": {"verdict": "meets", "target_artifact": target},
        }
        self.assertEqual(project_final_deliverable(task)["state"], "confirmed")
        task["pm_final_review"] = {"verdict": "meets"}
        self.assertEqual(project_final_deliverable(task)["state"], "candidate_unconfirmed")

    def test_v2_final_write_conflicting_binding_downgrades_to_conflict(self):
        envelope = self.envelope()
        task = {
            "task_id": "T-V2", "status": "completed",
            "stages": [{"id": "final_write", "status": "completed", "agents": ["writer-co"], "derived_task_id": "T-V2-final_write"}],
            "result_files": [{"name": self.path.name, "path": str(self.path)}],
            "result_metadata": [{"name": "envelope.json", "metadata": {**envelope, "task_id": "T-V2-final_write"}}],
            "pm_final_review": {"verdict": "meets", "target_artifact": {"artifact_id": "other", "artifact_version": "sha256:" + "0" * 64}},
        }
        self.assertEqual(project_final_deliverable(task)["state"], "conflict")


if __name__ == "__main__":
    unittest.main()
