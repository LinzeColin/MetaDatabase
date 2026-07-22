from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_002",
    PROJECT_ROOT / "scripts/verify_skeleton_002.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Skeleton002Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(verify_worktree=False, allow_external_main_dirty=False, run_external=False)
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.skeleton.002")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S02-S002")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.2.2")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "894553c6d15c3c73315e54429c8bd26588b6f83a")
        self.assertEqual(VERIFY.FINAL_COMMIT, "2a91efbc899aaaf3f6191ba3fb93ac825e3a9a0d")
        self.assertNotIn("apps/companion/", VERIFY.ALLOWED_CHANGED_PREFIXES)

    def test_real_pages_and_network_transport_remain_disabled(self) -> None:
        policy = VERIFY._load_json_at(VERIFY.FINAL_COMMIT, VERIFY.DOUYIN_POLICY)
        self.assertFalse(policy["feature_flag"]["real_page_execution"])
        self.assertFalse(policy["production_network_transport"])
        self.assertEqual(policy["real_short_link_resolution"], "unknown_disabled")
        manifest = json.loads(VERIFY.MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["permissions"], VERIFY.CURRENT_PERMISSIONS)
        self.assertNotIn("host_permissions", manifest)
        self.assertNotIn("content_scripts", manifest)

    def test_fixture_matrix_is_synthetic_and_complete(self) -> None:
        fixture = json.loads(VERIFY.FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 8)
        self.assertEqual(len(fixture["short_link_cases"]), 16)
        self.assertEqual(sum(item["expected"].get("status") == "ready" for item in fixture["cases"]), 4)
        self.assertEqual(sum("expected_error" in item for item in fixture["short_link_cases"]), 13)
        for field in (
            "contains_credentials",
            "contains_local_absolute_paths",
            "contains_media_urls",
            "contains_private_content",
            "contains_real_accounts",
            "real_accounts",
        ):
            self.assertFalse(fixture[field])

    def test_short_link_core_is_not_product_network_transport(self) -> None:
        source = (PROJECT_ROOT / "apps/extension/src/douyin-short-link.js").read_text(encoding="utf-8")
        worker = (PROJECT_ROOT / "apps/extension/src/service-worker.js").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\bfetch\s*\(")
        self.assertNotIn("XMLHttpRequest", source)
        self.assertIn("requestHop", source)
        self.assertNotIn("douyin-short-link", worker)
        self.assertIn('startsWith("synthetic-")', source)

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-s002-env-") as value:
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
        self.assertEqual(VERIFY.EVIDENCE.read_bytes(), VERIFY._read_blob_at(VERIFY.FINAL_COMMIT, VERIFY.EVIDENCE))
        self.assertEqual(evidence["acceptance_input_sha256"], VERIFY._acceptance_input_receipt())
        self.assertEqual(evidence["owner_canary"], "NOT_RUN")
        self.assertEqual(evidence["real_account_execution"], "NOT_RUN")
        self.assertEqual(evidence["production_network_transport"], "DISABLED")
        self.assertEqual(evidence["platform_calls"], 0)


if __name__ == "__main__":
    unittest.main()
