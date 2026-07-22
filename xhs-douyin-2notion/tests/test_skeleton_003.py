from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_003",
    PROJECT_ROOT / "scripts/verify_skeleton_003.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)

ACCEPTANCE_SPEC = importlib.util.spec_from_file_location(
    "run_skeleton_003_acceptance_for_tests",
    PROJECT_ROOT / "scripts/run_skeleton_003_acceptance.py",
)
assert ACCEPTANCE_SPEC and ACCEPTANCE_SPEC.loader
ACCEPTANCE = importlib.util.module_from_spec(ACCEPTANCE_SPEC)
sys.modules[ACCEPTANCE_SPEC.name] = ACCEPTANCE
ACCEPTANCE_SPEC.loader.exec_module(ACCEPTANCE)


class Skeleton003Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.003")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S003")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.7")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "0af2d3b269e7d5631257cb49f41f75cc79438f70")
        self.assertEqual(VERIFY.FINAL_COMMIT, "d5f61f30657ac6aa1bc7be3f7942d4b77df5b8ae")
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("media_safety.py", rendered)
        self.assertNotIn("skeleton.004", rendered)
        self.assertNotIn("apps/extension/src/", rendered)

    def test_previous_task_is_fixed_to_its_final_commit(self) -> None:
        self.assertEqual(VERIFY.PREVIOUS.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        self.assertNotEqual(VERIFY.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        previous = VERIFY.validate_previous_history()
        self.assertEqual(previous.status, "PASS")
        self.assertFalse(previous.details["history_rewritten"])

    def test_policy_is_six_platform_default_deny_and_network_disabled(self) -> None:
        policy = VERIFY._load_json(VERIFY.MEDIA_POLICY)
        self.assertEqual(policy["default"], "deny")
        self.assertEqual(
            set(policy["platform_cdn_suffixes"]),
            {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"},
        )
        self.assertEqual(policy["url_firewall"]["schemes"], ["https"])
        self.assertEqual(policy["url_firewall"]["ports"], [443])
        self.assertFalse(policy["url_firewall"]["production_transport_implemented"])
        self.assertEqual(policy["url_firewall"]["real_media_network_execution"], "NOT_RUN")
        self.assertEqual(policy["lease_lifecycle"]["crash_orphan_maximum_seconds"], 86_400)
        self.assertFalse(policy["lease_lifecycle"]["unexpired_active_delete_allowed"])

    def test_fixture_matrix_is_public_safe_and_complete(self) -> None:
        fixture = VERIFY._load_json(VERIFY.FIXTURE_MANIFEST)
        self.assertEqual(fixture["url_fuzz"]["cases"], 512)
        self.assertEqual(fixture["ssrf"]["cases"], 32)
        self.assertEqual(fixture["cleanup_chaos"]["cases"], 8)
        self.assertEqual(fixture["resource_limits"]["cases"], 8)
        self.assertFalse(fixture["raw_url_literals_present"])
        self.assertFalse(fixture["real_account_data_present"])
        self.assertFalse(fixture["real_media_present"])
        self.assertEqual(
            fixture["resource_limits"]["processor_cases_downstream_not_run"],
            ["ffmpeg_hang", "image_bomb_decode", "repeated_key_frame"],
        )

    def test_implementation_has_no_production_network_or_url_column(self) -> None:
        source = VERIFY.MEDIA_SOURCE.read_text(encoding="utf-8")
        self.assertIn("class EphemeralMediaSource", source)
        self.assertIn("class MediaLeaseCleaner", source)
        self.assertIn("transport_must_connect", VERIFY.MEDIA_POLICY.read_text(encoding="utf-8"))
        for forbidden in ("import requests", "import httpx", "import aiohttp", "urllib.request"):
            self.assertNotIn(forbidden, source)
        migrations = VERIFY.MIGRATION_SOURCE.read_text(encoding="utf-8")
        media_schema = migrations.split("CREATE TABLE media_lease", 1)[1].split(") STRICT", 1)[0]
        self.assertNotIn("url", media_schema.lower())

    def test_acceptance_matrix_has_zero_forbidden_success_or_residue(self) -> None:
        result = ACCEPTANCE.run()
        self.assertEqual(result["status"], "PASS_CI_SYNTH_SCOPED")
        self.assertEqual(result["url_fuzz"]["cases"], 512)
        self.assertEqual(result["url_fuzz"]["oracle_mismatches"], 0)
        self.assertEqual(result["ssrf"]["forbidden_target_successes"], 0)
        self.assertEqual(result["ssrf"]["local_file_reads"], 0)
        self.assertEqual(result["cleanup"]["success_residual_files"], 0)
        self.assertEqual(result["cleanup"]["expired_residual_files"], 0)
        self.assertEqual(result["cleanup"]["active_lease_misdeletes"], 0)
        self.assertEqual(result["processor_acceptance"]["status"], "DOWNSTREAM_NOT_RUN")

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s003-env-") as value:
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
                "member_count": 61,
                "runtime_data_files": 0,
                "allowlist_findings": 0,
            },
        }
        with tempfile.TemporaryDirectory(prefix="x2n-s003-lane-") as value:
            path = Path(value) / "lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(VERIFY.validate_full_lane_report(path).status, "PASS")
            report["artifact_report"]["member_count"] = 62
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_full_lane_report(path)
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY._safe_evidence({"unsafe": "https:" + "//example.invalid"})


if __name__ == "__main__":
    unittest.main()
