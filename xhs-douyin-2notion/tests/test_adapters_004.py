from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_004",
    PROJECT_ROOT / "scripts/verify_adapters_004.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Adapters004VerifierTests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task_and_unpinned_until_next_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.adapters.004")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S03-A004")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.3.4")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "0939d78303f5e96ddedf9c8ef8a01a8dce03574a")
        self.assertFalse(hasattr(VERIFY, "FINAL_COMMIT"))
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("douyin_upstream", rendered)
        self.assertNotIn("migrations.py", rendered)
        self.assertNotIn("apps/extension/src", rendered)

    def test_predecessor_and_security_surfaces_are_immutable(self) -> None:
        self.assertEqual(
            VERIFY.PREVIOUS.EVIDENCE.read_bytes(),
            VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, VERIFY.PREVIOUS.EVIDENCE),
        )
        for path in VERIFY.UNCHANGED_SECURITY_SURFACES:
            self.assertEqual(path.read_bytes(), VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, path))

    def test_exact_integration_lock_is_disabled_and_synthetic_digests_are_real(self) -> None:
        lock = VERIFY._load_json(VERIFY.INTEGRATION_LOCK)
        self.assertEqual(lock["upstream"]["commit"], VERIFY.UPSTREAM_COMMIT)
        self.assertEqual(lock["upstream"]["tree"], VERIFY.UPSTREAM_TREE)
        self.assertEqual(lock["integration_contract"]["sha256"], VERIFY.INTEGRATION_CONTRACT_SHA256)
        runtime = lock["runtime_integration"]
        self.assertFalse(runtime["enabled"])
        self.assertFalse(runtime["bundled"])
        self.assertFalse(runtime["runtime_dependency"])
        self.assertFalse(runtime["raw_cli_allowed"])
        self.assertFalse(runtime["raw_rest_allowed"])
        attestation = lock["ci_synthetic_attestation"]
        expected = {
            "executable_sha256": VERIFY.FIXTURE_WORKER,
            "resolved_lock_sha256": VERIFY.SYNTHETIC_LOCK,
            "transitive_license_report_sha256": VERIFY.SYNTHETIC_LICENSES,
            "sbom_sha256": VERIFY.SYNTHETIC_SBOM,
        }
        for field, path in expected.items():
            self.assertEqual(attestation[field], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(attestation["production_accepted"])

    def test_policy_keeps_owner_and_real_features_disabled(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)
        flags = policy["feature_gate"]
        self.assertFalse(flags["owner_canary_enabled"])
        self.assertFalse(flags["production_enabled"])
        self.assertEqual(flags["official_personal_likes_api"], "unknown_disabled")
        self.assertEqual(flags["official_personal_favorites_api"], "unknown_disabled")
        action = policy["owner_action"]
        self.assertEqual(action["max_items"], 20)
        self.assertFalse(action["automatic_pagination"])
        self.assertFalse(action["automatic_retry"])
        self.assertFalse(action["account_state_change"])

    def test_fixture_is_public_synthetic_and_maps_twenty_plus_twenty(self) -> None:
        fixture = VERIFY._load_json(VERIFY.FIXTURE)
        self.assertTrue(fixture["synthetic"])
        self.assertEqual(len(fixture["cases"]), 38)
        self.assertEqual(len(set(fixture["cases"])), 38)
        mapping = fixture["mapping"]
        self.assertEqual(mapping["favorites_items"], 20)
        self.assertEqual(mapping["likes_items"], 20)
        self.assertEqual(mapping["expected_content_rows"], 40)
        self.assertEqual(mapping["expected_upstream_paths_in_canonical"], 0)
        self.assertEqual(mapping["expected_upstream_database_primary_keys_in_canonical"], 0)
        for field in (
            "contains_accounts",
            "contains_cookies",
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
        ):
            self.assertFalse(fixture[field])

    def test_full_lane_report_is_independently_fail_closed(self) -> None:
        report = {
            "artifact_deterministic": True,
            "artifact_report": {
                "allowlist_findings": 0,
                "member_count": 90,
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
                for gate in VERIFY.PREVIOUS.PREVIOUS.PREVIOUS.FULL_LANE_GATES
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
        with tempfile.TemporaryDirectory(prefix="x2n-a004-lane-") as value:
            path = Path(value) / "software-lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(VERIFY.validate_full_lane_report(path).status, "PASS")
            report["platform_calls"] = 1
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.VerificationError, "forbidden external surface"):
                VERIFY.validate_full_lane_report(path)

    def test_evidence_never_claims_owner_upstream_or_real_execution(self) -> None:
        if not VERIFY.EVIDENCE.is_file():
            self.assertFalse(VERIFY.EVIDENCE.exists())
            return
        evidence = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(evidence["owner_profile_login"], "NOT_RUN")
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["owner_private_sidecar"], "NOT_INSTALLED")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertFalse(evidence["private_content_included"])
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
