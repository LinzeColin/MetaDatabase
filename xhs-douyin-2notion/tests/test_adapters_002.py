from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_002",
    PROJECT_ROOT / "scripts/verify_adapters_002.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Adapters002VerifierTests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task_and_unpinned_until_next_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.adapters.002")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S03-A002")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.3.2")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "ea44053528a6cdec342fff946a35a525e8daf385")
        self.assertFalse(hasattr(VERIFY, "FINAL_COMMIT"))
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("xhs_favorites", rendered)
        self.assertNotIn("douyin", rendered)
        self.assertNotIn("migrations.py", rendered)

    def test_predecessor_evidence_and_security_surfaces_are_immutable(self) -> None:
        self.assertEqual(
            VERIFY.PREVIOUS.EVIDENCE.read_bytes(),
            VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, VERIFY.PREVIOUS.EVIDENCE),
        )
        for path in VERIFY.UNCHANGED_SECURITY_SURFACES:
            self.assertEqual(path.read_bytes(), VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, path))

    def test_policy_keeps_real_feature_disabled_and_requires_explicit_visible_batch(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)
        self.assertFalse(policy["feature_gate"]["production_enabled"])
        self.assertFalse(policy["feature_gate"]["owner_canary_enabled"])
        clean = policy["clean_room"]
        self.assertEqual(clean["chrome_permission"], "activeTab_after_explicit_owner_action")
        self.assertEqual(clean["max_visible_items_per_action"], 20)
        self.assertFalse(clean["network_transport"])
        self.assertFalse(clean["automatic_scroll"])
        self.assertFalse(clean["automatic_pagination"])
        self.assertFalse(clean["cookie_or_credential_access"])

    def test_checkpoint_never_promotes_unknown_or_canary_to_full_scan(self) -> None:
        checkpoint = VERIFY._load_json(VERIFY.POLICY)["checkpoint"]
        self.assertFalse(checkpoint["unknown_or_partial_advances_cursor"])
        self.assertFalse(checkpoint["bounded_canary_is_full_scan"])
        self.assertTrue(checkpoint["full_scan_requires_authoritative_visible_end"])
        self.assertEqual(checkpoint["false_full_scan_allowed"], 0)

    def test_full_lane_report_is_independently_fail_closed(self) -> None:
        report = {
            "artifact_deterministic": True,
            "artifact_report": {
                "allowlist_findings": 0,
                "member_count": 80,
                "runtime_data_files": 0,
                "status": "PASS",
            },
            "blocking_commands": 12,
            "blocking_executions": 24,
            "blocking_failures": 0,
            "blocking_repetitions": 2,
            "blocking_results": [
                {
                    "blocking": True,
                    "gate": gate,
                    "label": f"{gate}_r{repetition}",
                    "repetition": repetition,
                    "status": "PASS",
                }
                for repetition in (1, 2)
                for gate in VERIFY.PREVIOUS.FULL_LANE_GATES
            ],
            "coverage": {"branch_mode": True, "overall_combined_percent": 78.0, "status": "PASS"},
            "explicit_nonblocking_skips": 6,
            "flaky_blocking_tests": 0,
            "lane": "full",
            "model_calls": 0,
            "osv": {
                "critical_high_unresolved": 0,
                "dependencies_queried": 33,
                "status": "PASS",
                "vulnerabilities_reported": 0,
            },
            "platform_calls": 0,
            "real_accounts": 0,
            "silent_blocking_skips": 0,
            "status": "PASS",
        }
        with tempfile.TemporaryDirectory(prefix="x2n-a002-lane-") as value:
            path = Path(value) / "software-lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(VERIFY.validate_full_lane_report(path).status, "PASS")
            report["platform_calls"] = 1
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.VerificationError, "forbidden external surface"):
                VERIFY.validate_full_lane_report(path)

    def test_evidence_never_claims_owner_or_real_execution(self) -> None:
        if not VERIFY.EVIDENCE.is_file():
            self.assertFalse(VERIFY.EVIDENCE.exists())
            return
        evidence = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(evidence["owner_profile_login"], "NOT_RUN")
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertFalse(evidence["private_content_included"])
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
