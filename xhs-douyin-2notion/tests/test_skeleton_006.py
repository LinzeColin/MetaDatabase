from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_006",
    PROJECT_ROOT / "scripts/verify_skeleton_006.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Skeleton006Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(verify_worktree=False, allow_external_main_dirty=False, run_external=False)
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.006")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S006")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.3")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "2a91efbc899aaaf3f6191ba3fb93ac825e3a9a0d")
        self.assertEqual(VERIFY.FINAL_COMMIT, "a314a1d049998eae6a052ea8900aa5ac448cb2ca")
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertNotIn("kuaishou", rendered.lower())
        self.assertNotIn("apps/companion/src/", rendered)

    def test_manifest_and_native_contract_are_unchanged(self) -> None:
        self.assertEqual(
            json.loads(VERIFY.MANIFEST.read_text(encoding="utf-8")),
            VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.MANIFEST),
        )
        self.assertEqual(
            json.loads(VERIFY.NATIVE_POLICY.read_text(encoding="utf-8")),
            VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.NATIVE_POLICY),
        )

    def test_real_pages_api_and_article_route_remain_disabled(self) -> None:
        policy = VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.BILIBILI_POLICY)
        self.assertFalse(policy["feature_flag"]["real_page_execution"])
        self.assertFalse(policy["production_network_transport"])
        self.assertEqual(policy["platform_policy_state"], "unknown_disabled")
        self.assertEqual(policy["route_evidence"]["article_read_route"], "unverified_route_assumption_ci_fixture_only")
        self.assertEqual(policy["official_first_gate"]["arbitrary_current_page_read_capability"], "not_found")
        self.assertEqual(policy["official_first_gate"]["likes_or_favorites_read_capability"], "not_found")

    def test_fixture_matrix_is_synthetic_complete_and_media_free(self) -> None:
        fixture = json.loads(VERIFY.FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 10)
        self.assertEqual(len(fixture["policy_cases"]), 8)
        self.assertEqual(sum(item["expected"].get("status") == "ready" for item in fixture["cases"]), 5)
        self.assertEqual(
            sum(item["expected"].get("status") == "platform_changed" for item in fixture["cases"]),
            5,
        )
        self.assertEqual(fixture["route_assumptions"]["article_read_cv_route"], "unverified_real_route_not_enabled")
        for field in (
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
            "contains_real_accounts",
            "real_accounts",
        ):
            self.assertFalse(fixture[field])

    def test_semantic_query_and_synthetic_identity_have_double_gates(self) -> None:
        support = (PROJECT_ROOT / "apps/extension/src/page-support.js").read_text(encoding="utf-8")
        extractor = (PROJECT_ROOT / "apps/extension/src/bilibili-current-page.js").read_text(encoding="utf-8")
        for source in (support, extractor):
            self.assertIn("synthetic-bili-video-", source)
            self.assertIn("synthetic-bili-article-", source)
            self.assertIn("semantic_query", source)
        self.assertNotIn('["bilibili.com", "www.bilibili.com"]', extractor)
        self.assertGreaterEqual(extractor.count('!== "www.bilibili.com"'), 2)
        self.assertNotIn('.getAttribute("src")', extractor)
        self.assertNotIn(".src", extractor)

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s006-env-") as value:
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
                "member_count": 57,
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
        with tempfile.TemporaryDirectory(prefix="x2n-s006-lane-") as value:
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
            self.skipTest("Task evidence is written only after full E2E")
        evidence = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(VERIFY.EVIDENCE.read_bytes(), VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, VERIFY.EVIDENCE))
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["production_network_transport"], "DISABLED")
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())


if __name__ == "__main__":
    unittest.main()
