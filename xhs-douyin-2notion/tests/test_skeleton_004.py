from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_004",
    PROJECT_ROOT / "scripts/verify_skeleton_004.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)

ACCEPTANCE_SPEC = importlib.util.spec_from_file_location(
    "run_skeleton_004_acceptance_for_tests",
    PROJECT_ROOT / "scripts/run_skeleton_004_acceptance.py",
)
assert ACCEPTANCE_SPEC and ACCEPTANCE_SPEC.loader
ACCEPTANCE = importlib.util.module_from_spec(ACCEPTANCE_SPEC)
sys.modules[ACCEPTANCE_SPEC.name] = ACCEPTANCE
ACCEPTANCE_SPEC.loader.exec_module(ACCEPTANCE)


class Skeleton004Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.004")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S004")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.8")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "d5f61f30657ac6aa1bc7be3f7942d4b77df5b8ae")
        self.assertEqual(VERIFY.FINAL_COMMIT, "36bd12133f402321b160292ea13ca51272c63e93")
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("orchestrator.py", rendered)
        self.assertNotIn("skeleton.005", rendered)
        self.assertNotIn("notion", rendered.lower())

    def test_previous_task_is_fixed_to_exact_final_commit(self) -> None:
        self.assertEqual(VERIFY.PREVIOUS.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        self.assertNotEqual(VERIFY.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        previous = VERIFY.validate_previous_history()
        self.assertEqual(previous.status, "PASS")
        self.assertFalse(previous.details["history_rewritten"])

    def test_policy_is_two_transaction_schema_v2_and_downstream_closed(self) -> None:
        policy = VERIFY._load_json(VERIFY.ORCHESTRATOR_POLICY)
        self.assertEqual(policy["transaction_count"], 2)
        self.assertEqual(policy["migration"], "not_required_schema_v2_unchanged")
        self.assertFalse(policy["replay"]["original_payload_required_for_resume"])
        self.assertEqual(policy["replay"]["fixture_inputs"], 80)
        self.assertEqual(policy["replay"]["concurrent_duplicate_requests"], 100)
        self.assertEqual(set(policy["downstream"].values()), {"DOWNSTREAM_NOT_RUN"})

    def test_fixture_is_public_safe_and_complete(self) -> None:
        fixture = VERIFY._load_json(VERIFY.FIXTURE_MANIFEST)
        self.assertEqual(fixture["case_count"], 80)
        self.assertEqual(fixture["tests"]["replay_rounds"], 2)
        self.assertEqual(fixture["tests"]["concurrent_duplicate_count"], 100)
        self.assertEqual(len(fixture["tests"]["kill_points"]), 4)
        self.assertEqual(
            set(fixture["generation"]["platform_cycle"]),
            {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"},
        )
        for field in (
            "real_accounts",
            "contains_credentials",
            "contains_media_urls",
            "contains_private_content",
            "contains_local_absolute_paths",
        ):
            self.assertFalse(fixture[field])

    def test_acceptance_has_zero_duplicate_stuck_or_broken_trace(self) -> None:
        result = ACCEPTANCE.run()
        self.assertEqual(result["status"], "PASS_CI_SYNTH_SCOPED")
        self.assertEqual(result["idempotency"]["case_count"], 80)
        self.assertEqual(result["idempotency"]["duplicate_entities"], 0)
        self.assertEqual(result["idempotency"]["broken_provenance_traces"], 0)
        self.assertEqual(result["idempotency"]["stuck_runs"], 0)
        self.assertEqual(result["concurrency"]["requests"], 100)
        self.assertEqual(result["concurrency"]["job_count"], 1)
        self.assertEqual(result["kill_points"]["non_replayable_states"], 0)
        self.assertEqual(set(result["downstream"].values()), {"DOWNSTREAM_NOT_RUN"})

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s004-env-") as value:
            env = VERIFY._isolated_env(Path(value))
        for field in ("GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN"):
            self.assertNotIn(field, env)
        self.assertEqual(env["UV_KEYRING_PROVIDER"], "disabled")
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertEqual(env["npm_config_ignore_scripts"], "true")

    def test_full_lane_and_evidence_checks_fail_closed(self) -> None:
        report = {
            "status": "PASS",
            "lane": "full",
            "blocking_commands": 12,
            "blocking_repetitions": 2,
            "blocking_executions": 24,
            "blocking_failures": 0,
            "flaky_blocking_tests": 0,
            "silent_blocking_skips": 0,
            "explicit_nonblocking_skips": 6,
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
            "platform_calls": 0,
            "model_calls": 0,
            "real_accounts": 0,
            "coverage": {"status": "PASS", "branch_mode": True, "overall_combined_percent": 70.0},
            "osv": {
                "status": "PASS",
                "dependencies_queried": 33,
                "vulnerabilities_reported": 0,
                "critical_high_unresolved": 0,
            },
            "artifact_deterministic": True,
            "artifact_report": {
                "status": "PASS",
                "member_count": VERIFY.EXPECTED_ARTIFACT_MEMBERS,
                "runtime_data_files": 0,
                "allowlist_findings": 0,
            },
        }
        with tempfile.TemporaryDirectory(prefix="x2n-s004-lane-") as value:
            path = Path(value) / "lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(VERIFY.validate_full_lane_report(path).status, "PASS")
            report["artifact_report"]["member_count"] += 1
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_full_lane_report(path)
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._safe_evidence({"unsafe": "https:" + "//example.invalid"})


if __name__ == "__main__":
    unittest.main()
