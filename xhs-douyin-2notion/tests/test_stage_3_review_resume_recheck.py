from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_stage_3_review_resume_recheck",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume_recheck.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage3ReviewResumeRecheckTests(unittest.TestCase):
    def test_static_checks_pass_without_external_execution(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            run_acceptance=False,
            require_evidence=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_g3_pass_requires_all_six_exact_conditions(self) -> None:
        fact = json.loads(VERIFY.RECHECK_FACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(fact)
        changed["gate"]["pass_conditions"]["zero_automatic_fallbacks"] = "NOT_RUN"
        with self.assertRaises(VERIFY.RecheckError):
            original = VERIFY._load_json
            try:
                VERIFY._load_json = lambda path: changed if path == VERIFY.RECHECK_FACT else original(path)
                VERIFY.validate_fact_and_historical_receipts()
            finally:
                VERIFY._load_json = original

    def test_historical_review_resume_and_task010_receipts_are_pinned(self) -> None:
        self.assertEqual(VERIFY._sha256(VERIFY.FIRST_REVIEW_FACT), VERIFY.FIRST_REVIEW_SHA256)
        self.assertEqual(VERIFY._sha256(VERIFY.RESUME_FACT), VERIFY.RESUME_FACT_SHA256)
        self.assertEqual(
            VERIFY._sha256_bytes(VERIFY._blob_at(VERIFY.TASK010_FINAL_COMMIT, VERIFY.TASK010_EVIDENCE)),
            VERIFY.TASK010_EVIDENCE_SHA256,
        )

    def test_g3_pass_allows_local_stage4_but_not_remote_upload_or_release(self) -> None:
        fact = json.loads(VERIFY.RECHECK_FACT.read_text(encoding="utf-8"))
        self.assertFalse(fact["authorization"]["stage_3_remote_upload"])
        self.assertTrue(fact["authorization"]["stage_4_local_task_start"])
        self.assertFalse(fact["authorization"]["public_release"])
        self.assertEqual(fact["next_task"]["id"], "TSK.x2n.multimodal.001")
        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        self.assertTrue(state["stage_4_authorized"])
        self.assertFalse(state["stage_3_remote_upload_authorized"])
        self.assertFalse(state["public_release_authorized"])

    def test_stage6_assurance004_completion_requires_assurance005_next(self) -> None:
        check = VERIFY.validate_taskpack_and_current_transition()
        self.assertEqual(check.details["completed_task"], "TSK.x2n.assurance.004")
        self.assertEqual(check.details["next_task"], "TSK.x2n.assurance.005")

        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        changed = copy.deepcopy(state)
        changed["next_task"] = "TSK.x2n.assurance.004"
        original = VERIFY._load_json
        try:
            VERIFY._load_json = lambda path: changed if path == VERIFY.TASK_STATE else original(path)
            with self.assertRaises(VERIFY.RecheckError):
                VERIFY.validate_taskpack_and_current_transition()
        finally:
            VERIFY._load_json = original

    def test_public_boundary_rejects_credentials_paths_cdn_and_urls_in_evidence(self) -> None:
        for unsafe in (
            {"path": "/" + "Users" + "/private"},
            {"token": "github" + "_pat_example"},
            {"credential": "Bearer" + " secret-value"},
            {"url": "https://example.invalid"},
            {"cdn": "byteimg.example.invalid"},
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(VERIFY.RecheckError):
                    VERIFY._safe_payload(unsafe)

    def test_release_policy_has_no_prerelease_fixed_observation_or_soak(self) -> None:
        policy = json.loads(VERIFY.RECHECK_FACT.read_text(encoding="utf-8"))["release_policy"]
        self.assertEqual(policy["alpha_beta"], "PROHIBITED")
        self.assertEqual(policy["fixed_health_observation"], "PROHIBITED")
        self.assertEqual(policy["fixed_soak"], "PROHIBITED")


if __name__ == "__main__":
    unittest.main()
