from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_001",
    PROJECT_ROOT / "scripts/verify_adapters_001.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Adapters001VerifierTests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task_and_unpinned_until_next_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.adapters.001")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S03-A001")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.3.1")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "ee5d251ca30eab226c4df75c53965f312c2d9b05")
        self.assertFalse(hasattr(VERIFY, "FINAL_COMMIT"))
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("profile_session", rendered)
        self.assertNotIn("apps/extension/src/", rendered)
        self.assertNotIn("migrations.py", rendered)

    def test_stage_2_historical_evidence_and_security_contracts_are_immutable(self) -> None:
        for path in VERIFY.HISTORICAL_STAGE_2_EVIDENCE:
            self.assertEqual(path.read_bytes(), VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, path))
        for path in VERIFY.UNCHANGED_SECURITY_SURFACES:
            self.assertEqual(path.read_bytes(), VERIFY._read_blob_at(VERIFY.TASK_BASE_COMMIT, path))

    def test_policy_forbids_cookie_paths_urls_login_automation_and_concurrency(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)
        launcher = policy["profile_launcher"]
        for field in (
            "caller_supplied_executable",
            "caller_supplied_profile_path",
            "caller_supplied_url",
            "automated_login",
            "remote_debugging",
            "cookie_or_credential_input",
            "cookie_or_credential_export",
            "verification_bypass",
        ):
            self.assertFalse(launcher[field])
        execution = policy["adapter_execution"]
        self.assertEqual(execution["max_concurrent_adapters"], 1)
        self.assertFalse(execution["mutex_wait"])
        self.assertFalse(execution["automatic_retry_on_auth_verification_or_platform_change"])

    def test_batch_policy_never_auto_removes_or_physically_deletes(self) -> None:
        policy = VERIFY._load_json(VERIFY.POLICY)["batch_deletion_protection"]
        self.assertEqual(len(policy["non_authoritative_outcomes"]), 5)
        self.assertEqual(policy["removed_count_for_non_authoritative_outcome"], 0)
        self.assertEqual(policy["complete_successes_required_for_candidate"], 2)
        self.assertEqual(policy["maximum_automatic_state"], "tombstone_candidate")
        self.assertTrue(policy["owner_confirmation_required_for_physical_delete"])
        self.assertFalse(policy["automatic_content_delete"])

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a001-env-") as value:
            env = VERIFY._isolated_env(Path(value))
        for field in ("GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN"):
            self.assertNotIn(field, env)
        self.assertEqual(env["UV_KEYRING_PROVIDER"], "disabled")
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertEqual(env["npm_config_ignore_scripts"], "true")

    def test_full_lane_report_is_independently_fail_closed(self) -> None:
        report = {
            "artifact_deterministic": True,
            "artifact_report": {
                "allowlist_findings": 0,
                "member_count": 70,
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
                for gate in VERIFY.FULL_LANE_GATES
            ],
            "coverage": {
                "branch_mode": True,
                "overall_combined_percent": 76.0,
                "status": "PASS",
            },
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
        with tempfile.TemporaryDirectory(prefix="x2n-a001-lane-") as value:
            path = Path(value) / "software-lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            check = VERIFY.validate_full_lane_report(path)
            self.assertEqual(check.status, "PASS")
            report["real_accounts"] = 1
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
        self.assertFalse(evidence["profile_path_included"])
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
