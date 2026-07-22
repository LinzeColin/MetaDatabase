from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_005",
    PROJECT_ROOT / "scripts/verify_skeleton_005.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)

ACCEPTANCE_SPEC = importlib.util.spec_from_file_location(
    "run_skeleton_005_acceptance_for_tests",
    PROJECT_ROOT / "scripts/run_skeleton_005_acceptance.py",
)
assert ACCEPTANCE_SPEC and ACCEPTANCE_SPEC.loader
ACCEPTANCE = importlib.util.module_from_spec(ACCEPTANCE_SPEC)
sys.modules[ACCEPTANCE_SPEC.name] = ACCEPTANCE
ACCEPTANCE_SPEC.loader.exec_module(ACCEPTANCE)


class Skeleton005Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task_and_routes_to_stage_review(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.005")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S005")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.9")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "36bd12133f402321b160292ea13ca51272c63e93")
        self.assertEqual(VERIFY.FINAL_COMMIT, "c133e1d4c1cbc17a3165e19fa5dbb2368da6b32b")
        rendered = "\n".join(sorted(VERIFY.ALLOWED_CHANGED_EXACT | set(VERIFY.ALLOWED_CHANGED_PREFIXES)))
        self.assertIn("markdown_sink.py", rendered)
        self.assertIn("notion_sink.py", rendered)
        self.assertNotIn("adapters.001", rendered)

    def test_task_is_frozen_to_exact_final_commit_for_descendant_review(self) -> None:
        self.assertEqual(VERIFY.PREVIOUS.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        self.assertNotEqual(VERIFY.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        self.assertEqual(
            VERIFY.EVIDENCE.read_bytes(),
            VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, VERIFY.EVIDENCE),
        )
        previous = VERIFY.validate_previous_history()
        self.assertEqual(previous.status, "PASS")
        self.assertFalse(previous.details["history_rewritten"])

    def test_previous_task_is_fixed_to_exact_final_commit(self) -> None:
        self.assertEqual(VERIFY.PREVIOUS.FINAL_COMMIT, VERIFY.TASK_BASE_COMMIT)
        previous = VERIFY.validate_previous_history()
        self.assertEqual(previous.status, "PASS")
        self.assertFalse(previous.details["history_rewritten"])

    def test_policy_is_fixed_path_default_deny_and_real_notion_disabled(self) -> None:
        policy = VERIFY._load_json(VERIFY.SINK_POLICY)
        self.assertEqual(policy["default"], "deny")
        self.assertEqual(
            policy["markdown"]["canonical_path_template"],
            "runtime/library/content/<platform>/<content_id>.md",
        )
        self.assertFalse(policy["markdown"]["path_uses_title"])
        self.assertFalse(policy["markdown"]["path_uses_category"])
        self.assertFalse(policy["category_fallback"]["creates_taxonomy_row"])
        self.assertEqual(policy["notion"]["api_version"], "2026-03-11")
        self.assertEqual(policy["notion"]["default_requests_per_second"], 2)
        self.assertEqual(policy["notion"]["real_api_calls"], 0)
        self.assertEqual(policy["notion"]["credential_access"], "NOT_RUN")

    def test_fixture_is_public_safe_and_complete(self) -> None:
        fixture = VERIFY._load_json(VERIFY.FIXTURE_MANIFEST)
        self.assertEqual(fixture["case_count"], 80)
        self.assertEqual(fixture["replay_rounds"], 2)
        self.assertEqual(len(fixture["notion_mock"]["faults"]), 7)
        self.assertEqual(
            set(fixture["generation"]["platform_cycle"]),
            {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"},
        )
        for field in (
            "contains_credentials",
            "contains_media_urls",
            "contains_private_owner_content",
            "contains_local_absolute_paths",
        ):
            self.assertFalse(fixture[field])

    def test_implementation_has_atomic_markdown_mock_notion_and_no_transport(self) -> None:
        markdown = VERIFY.MARKDOWN_SOURCE.read_text(encoding="utf-8")
        notion = VERIFY.NOTION_SOURCE.read_text(encoding="utf-8")
        projection = VERIFY.PROJECTION_SOURCE.read_text(encoding="utf-8")
        self.assertIn("os.replace(", markdown)
        self.assertIn("os.fsync(", markdown)
        self.assertIn("class NotionMockServer", notion)
        self.assertIn("category_page_refs", notion)
        self.assertIn("UNCLASSIFIED_SLUG", projection)
        for source in (markdown, notion, projection):
            for forbidden in ("import requests", "import httpx", "import aiohttp", "urllib.request", "import socket"):
                self.assertNotIn(forbidden, source)

    def test_acceptance_has_zero_partial_duplicate_dead_link_or_real_call(self) -> None:
        result = ACCEPTANCE.run()
        self.assertEqual(result["status"], "PASS_CI_SYNTH_MOCK_SCOPED")
        self.assertEqual(result["case_count"], 80)
        end_to_end = result["end_to_end"]
        self.assertEqual(end_to_end["replay_rounds"], 2)
        self.assertEqual(end_to_end["markdown_frontmatter_invalid"], 0)
        self.assertEqual(end_to_end["markdown_partial_files"], 0)
        self.assertEqual(end_to_end["markdown_cdn_findings"], 0)
        self.assertEqual(end_to_end["index_dead_links"], 0)
        self.assertEqual(end_to_end["notion_duplicate_pages"], 0)
        self.assertEqual(end_to_end["notion_projection_hash_replay_requests"], 0)
        self.assertLessEqual(end_to_end["rate_maximum_average_requests_per_second"], 2.0)
        self.assertEqual(result["notion_real_api_calls"], 0)
        self.assertEqual(result["owner_notion_canary"], "NOT_RUN")

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s005-env-") as value:
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
        with tempfile.TemporaryDirectory(prefix="x2n-s005-lane-") as value:
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
