from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_001",
    PROJECT_ROOT / "scripts/verify_skeleton_001.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Skeleton001Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.001")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S001")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.1")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "6777c8fcce75a36741b70c2858c8bc5fff17d440")
        self.assertNotIn("apps/companion/", VERIFY.ALLOWED_CHANGED_PREFIXES)

    def test_permissions_are_minimal_and_mapped(self) -> None:
        manifest = json.loads(VERIFY.MANIFEST.read_text(encoding="utf-8"))
        policy = json.loads(VERIFY.PERMISSION_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(manifest["permissions"], VERIFY.CURRENT_PERMISSIONS)
        self.assertNotIn("host_permissions", manifest)
        self.assertNotIn("content_scripts", manifest)
        self.assertEqual([item["name"] for item in policy["permissions"]], VERIFY.CURRENT_PERMISSIONS)
        self.assertEqual(policy["feature_flag"]["value"], "ci_synth_only")
        self.assertFalse(policy["feature_flag"]["real_page_execution"])

    def test_fixture_matrix_is_synthetic_and_complete(self) -> None:
        fixture = json.loads(VERIFY.FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 5)
        self.assertEqual(
            [item["expected"]["status"] for item in fixture["cases"]].count("ready"),
            3,
        )
        self.assertEqual(
            [item["expected"]["status"] for item in fixture["cases"]].count("platform_changed"),
            2,
        )
        for field in (
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
            "contains_real_accounts",
            "real_accounts",
        ):
            self.assertFalse(fixture[field])

    def test_real_pages_and_owner_canary_remain_disabled(self) -> None:
        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        platform = json.loads(VERIFY.PLATFORM_FACT.read_text(encoding="utf-8"))
        xhs = next(item for item in platform["platforms"] if item["id"] == "xiaohongshu")
        self.assertEqual(state["current_stage_gate"], "not_run")
        self.assertEqual(state["current_stage_remote_upload"], "forbidden_until_g2_pass")
        self.assertEqual(state["real_account_execution"], "not_run")
        self.assertEqual(xhs["policy_state"], "unknown_disabled")
        self.assertIn("real_page_disabled", xhs["current_page_implementation_state"])

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s001-env-") as value:
            env = VERIFY._isolated_env(Path(value))
        for field in ("GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN"):
            self.assertNotIn(field, env)
        self.assertEqual(env["UV_KEYRING_PROVIDER"], "disabled")
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertEqual(env["npm_config_ignore_scripts"], "true")

    def test_evidence_never_claims_real_execution(self) -> None:
        if not VERIFY.EVIDENCE.is_file():
            self.skipTest("Task evidence is written only after full E2E")
        evidence = json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["feature_flag"], "CI_SYNTH_ONLY_REAL_PAGE_DISABLED")
        self.assertEqual(evidence["platform_calls"], 0)


if __name__ == "__main__":
    unittest.main()
