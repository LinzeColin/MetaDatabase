from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_008",
    PROJECT_ROOT / "scripts/verify_skeleton_008.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Skeleton008Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(verify_worktree=False, allow_external_main_dirty=False, run_external=False)
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.008")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S008")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.5")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "17f1988b309fe62071c273369f7088b7f6cc6046")
        self.assertEqual(VERIFY.FINAL_COMMIT, "7e8a3dbf3c4c27643330489353ed162130fba506")
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertNotIn("taobao", rendered.lower())
        self.assertNotIn("apps/companion/src/", rendered)

    def test_manifest_native_contract_and_locks_are_unchanged(self) -> None:
        self.assertEqual(
            json.loads(VERIFY.MANIFEST.read_text(encoding="utf-8")),
            VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.MANIFEST),
        )
        self.assertEqual(
            json.loads(VERIFY.NATIVE_POLICY.read_text(encoding="utf-8")),
            VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.NATIVE_POLICY),
        )
        self.assertEqual(
            json.loads((PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8")),
            VERIFY._load_json_at(VERIFY.FINAL_COMMIT, PROJECT_ROOT / "package-lock.json"),
        )
        self.assertEqual(
            (PROJECT_ROOT / "uv.lock").read_bytes(),
            VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, PROJECT_ROOT / "uv.lock"),
        )

    def test_real_pages_api_cli_dom_and_paid_tier_remain_disabled(self) -> None:
        policy = VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.WEIBO_POLICY)
        self.assertFalse(policy["feature_flag"]["real_page_execution"])
        self.assertFalse(policy["production_api_transport"])
        self.assertEqual(
            policy["platform_policy_state"],
            "blocked_budget_real_page_unknown_disabled_api_and_dom_fallback",
        )
        self.assertEqual(policy["budget_gate"]["default_budget_units"], 0)
        self.assertFalse(policy["budget_gate"]["approved_paid_tier"])
        self.assertEqual(policy["budget_gate"]["application_quota_state"], "unknown")
        self.assertFalse(policy["official_first_gate"]["official_cli_installed_or_executed"])
        self.assertEqual(
            policy["official_first_gate"]["authorized_status_show_scope"],
            "status_authored_by_authorized_user_only",
        )
        self.assertEqual(policy["official_first_gate"]["arbitrary_public_current_page_read_capability"], "not_found")

    def test_fixture_matrix_is_synthetic_complete_and_media_free(self) -> None:
        fixture = VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.FIXTURE_MANIFEST)
        self.assertEqual(len(fixture["cases"]), 8)
        self.assertEqual(len(fixture["policy_cases"]), 12)
        self.assertEqual(len(fixture["redirect_ssrf_cases"]), 16)
        self.assertEqual(sum(item["expected"].get("status") == "ready" for item in fixture["cases"]), 4)
        self.assertEqual(
            sum(item["expected"].get("status") == "platform_changed" for item in fixture["cases"]),
            4,
        )
        self.assertEqual(fixture["budget_contract"]["default_budget_units"], 0)
        self.assertFalse(fixture["budget_contract"]["arbitrary_url_preview_proxy"])
        for field in (
            "contains_cookies",
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
            "contains_real_accounts",
            "real_accounts",
        ):
            self.assertFalse(fixture[field])

    def test_arbitrary_url_redirect_and_synthetic_identity_have_double_gates(self) -> None:
        support = (PROJECT_ROOT / "apps/extension/src/page-support.js").read_text(encoding="utf-8")
        extractor = (PROJECT_ROOT / "apps/extension/src/weibo-current-page.js").read_text(encoding="utf-8")
        for source in (support, extractor):
            self.assertIn("synthetic-wb-status-", source)
        self.assertIn("weibo_arbitrary_url_control_rejected", support)
        self.assertIn("weibo_budget_zero_quota_unknown_disabled", support)
        self.assertIn("weibo_query_fragment_unsupported", support)
        self.assertNotIn('["weibo.com", "www.weibo.com"]', extractor)
        self.assertGreaterEqual(extractor.count('!== "www.weibo.com"'), 2)
        self.assertIn("data-mid", extractor)
        self.assertNotIn('.getAttribute("src")', extractor)
        self.assertNotIn(".src", extractor)
        self.assertNotIn("fetch(", extractor)

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s008-env-") as value:
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
                "member_count": 59,
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
                "overall_combined_percent": 70.95,
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
        with tempfile.TemporaryDirectory(prefix="x2n-s008-lane-") as value:
            path = Path(value) / "software-lane.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            check = VERIFY.validate_full_lane_report(path)
            self.assertEqual(check.name, "full_lane_replay")
            self.assertEqual(check.status, "PASS")

            report["platform_calls"] = 1
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(VERIFY.VerificationError, "forbidden external surface"):
                VERIFY.validate_full_lane_report(path)

    def test_evidence_never_claims_real_execution(self) -> None:
        if not VERIFY.EVIDENCE.is_file():
            self.assertFalse(VERIFY.EVIDENCE.exists())
            return
        evidence = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(VERIFY.EVIDENCE.read_bytes(), VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, VERIFY.EVIDENCE))
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["production_network_transport"], "DISABLED")
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
