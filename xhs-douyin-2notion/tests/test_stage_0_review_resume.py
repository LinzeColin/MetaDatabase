from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_stage_0_review_resume", PROJECT_ROOT / "scripts/verify_stage_0_review_resume.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage0ReviewResumeTests(unittest.TestCase):
    def test_owner_change_and_isolation_policy_pass(self) -> None:
        check = VERIFY.validate_owner_change_and_policy()
        self.assertEqual(check.status, "PASS")
        self.assertFalse(check.details["secret_presence_waiver"])

    def test_all_x2n_material_controls_are_zero_contact(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)
        self.assertTrue(policy["not_a_secret_presence_waiver"])
        self.assertTrue(all(value is False for value in policy["x2n_controls"].values()))
        self.assertEqual(policy["future_secret_hit_action"], "fail_closed_incident_no_waiver")

    def test_repository_zero_contact_passes(self) -> None:
        check = VERIFY.validate_repository_zero_contact()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(sum(check.details.values()), 0)

    def test_authenticated_remote_detector_is_fail_closed(self) -> None:
        self.assertEqual(VERIFY._authenticated_remote_hit_count(("https://github.com/example/project.git",)), 0)
        shaped = "https://" + "synthetic-user" + "@github.com/example/project.git"
        self.assertEqual(VERIFY._authenticated_remote_hit_count((shaped,)), 1)

    def test_sensitive_detector_catches_synthetic_shape_without_literal_fixture(self) -> None:
        shaped = "github" + "_pat_" + "synthetic"
        self.assertEqual(VERIFY._sensitive_hit_count((shaped,)), 1)
        self.assertEqual(VERIFY._sensitive_hit_count(("ordinary governance text",)), 0)

    def test_generated_dependency_and_build_trees_are_not_source_scan_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-zero-contact-scope-") as value:
            root = Path(value)
            source = root / "source.py"
            source.write_text("ordinary source", encoding="utf-8")
            for directory in VERIFY.GENERATED_TREE_PARTS:
                ignored = root / directory / "ignored.py"
                ignored.parent.mkdir(parents=True, exist_ok=True)
                ignored.write_text("generated dependency content", encoding="utf-8")
            self.assertEqual(list(VERIFY._text_files(root)), [source])

    def test_public_evidence_rejects_private_metadata_and_paths(self) -> None:
        VERIFY._assert_public_evidence_safe({"status": "PASS", "secret_presence_waiver": False})
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._assert_public_evidence_safe({"receipt_id": "synthetic"})
        local_path = "/" + "Users/" + "example/private"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._assert_public_evidence_safe({"value": local_path})

    def test_private_attestation_when_explicitly_supplied(self) -> None:
        value = os.environ.get("X2N_DATA_ROOT")
        if not value:
            self.skipTest("owner-private root is intentionally absent in public CI")
        check = VERIFY.validate_owner_attestation(Path(value))
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["recovery_action"], VERIFY.OWNER_ACTION)

    def test_resume_evidence_when_present(self) -> None:
        if not VERIFY.EVIDENCE_DIR.exists():
            self.skipTest("Resume evidence has not been issued yet")
        check = VERIFY.validate_evidence()
        self.assertEqual(check.status, "PASS")
        self.assertEqual(check.details["g0"], "PASS")

    def test_historical_review_receipt_remains_blocked(self) -> None:
        historical = json.loads((PROJECT_ROOT / "machine/evidence/stage_0/review/G0.json").read_text(encoding="utf-8"))
        self.assertEqual(historical["status"], "BLOCKED_OWNER_ACTION")
        self.assertEqual(historical["decision"], "FAIL_CLOSED")


if __name__ == "__main__":
    unittest.main()
