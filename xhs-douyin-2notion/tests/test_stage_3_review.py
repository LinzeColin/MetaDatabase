from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_stage_3_review",
    PROJECT_ROOT / "scripts/verify_stage_3_review.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Stage3ReviewTests(unittest.TestCase):
    def test_static_review_checks_pass_without_external_execution(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_acceptance=False,
            lane_report=None,
            require_evidence=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_gate_is_fail_closed_and_cannot_authorize_upload_or_stage_4(self) -> None:
        fact = json.loads(VERIFY.G3_FACT.read_text(encoding="utf-8"))
        VERIFY._validate_gate_payload(fact)
        self.assertEqual(fact["gate_status"], "blocked_technical_and_owner_clarification")
        self.assertEqual(fact["gate_decision"], "resume_review")
        self.assertFalse(fact["upload"]["stage_3_remote_upload_authorized"])
        self.assertFalse(fact["upload"]["stage_4_authorized"])
        self.assertEqual(fact["next_action"], "STG.X2N.3.REVIEW.RESUME")

    def test_false_g3_pass_or_upload_claim_is_rejected(self) -> None:
        fact = json.loads(VERIFY.G3_FACT.read_text(encoding="utf-8"))
        promoted = copy.deepcopy(fact)
        promoted["gate_status"] = "pass"
        promoted["gate_decision"] = "pass"
        promoted["upload"]["stage_3_remote_upload_authorized"] = True
        promoted["upload"]["stage_4_authorized"] = True
        promoted["upload"]["remote_upload"] = "authorized_after_g3_pass"
        with self.assertRaises(VERIFY.ReviewError):
            VERIFY._validate_gate_payload(promoted)

    def test_all_nine_historical_task_receipts_are_pinned_and_immutable(self) -> None:
        fact = json.loads(VERIFY.G3_FACT.read_text(encoding="utf-8"))
        receipts = fact["required_task_receipts"]
        self.assertEqual([item["task_id"] for item in receipts], list(VERIFY.TASK_COMMITS))
        for receipt in receipts:
            task_id = receipt["task_id"]
            evidence = PROJECT_ROOT / receipt["evidence_path"]
            self.assertEqual(receipt["final_commit"], VERIFY.TASK_COMMITS[task_id])
            self.assertEqual(evidence.read_bytes(), VERIFY._blob_at(receipt["final_commit"], evidence))
            self.assertEqual(receipt["evidence_sha256"], VERIFY._sha256(evidence))

    def test_acceptance_union_and_canary_states_are_exact(self) -> None:
        fact = json.loads(VERIFY.G3_FACT.read_text(encoding="utf-8"))
        self.assertEqual({item["id"] for item in fact["acceptance_union"]}, VERIFY.EXPECTED_ACCEPTANCES)
        self.assertEqual({item["scope_id"] for item in fact["canaries"]}, VERIFY.EXPECTED_CANARIES)
        self.assertTrue(all(item["execution_status"] == "NOT_RUN" for item in fact["canaries"]))
        self.assertTrue(all(item["feature_enabled"] is False for item in fact["canaries"]))
        self.assertEqual({item["id"] for item in fact["blockers"]}, VERIFY.EXPECTED_BLOCKERS)

    def test_schema_is_strict_and_encodes_blocked_routing(self) -> None:
        schema = json.loads(VERIFY.G3_SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), VERIFY.EXPECTED_FACT_KEYS)
        self.assertIn(
            "blocked_technical_and_owner_clarification",
            schema["properties"]["gate_status"]["enum"],
        )
        self.assertEqual(
            schema["properties"]["next_action"]["enum"],
            ["STG.X2N.3.REVIEW.RESUME", "STG.X2N.4.NEXT_TASK"],
        )
        self.assertEqual(schema["properties"]["required_task_receipts"]["minItems"], 9)
        self.assertEqual(schema["properties"]["canaries"]["minItems"], 8)
        self.assertEqual(schema["properties"]["acceptance_union"]["minItems"], 19)

    def test_shared_external_auth_is_not_a_gate_blocker_or_input(self) -> None:
        findings = json.loads(VERIFY.FINDINGS.read_text(encoding="utf-8"))
        rendered = json.dumps(findings, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("token_exposure", rendered)
        self.assertNotIn("credential_rotation", rendered)
        self.assertNotIn("github" + "_pat_", rendered)
        self.assertNotIn("ghp_", rendered)


if __name__ == "__main__":
    unittest.main()
