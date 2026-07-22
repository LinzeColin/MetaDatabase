from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_foundation_004",
    PROJECT_ROOT / "scripts/verify_foundation_004.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Foundation004Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.foundation.004")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S01-F004")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "84731bde18495ab20af005bc70d59d5ce73cbe93")
        self.assertEqual(VERIFY.ORIGIN_CUTOFF, "baac314b7d97369496212ae89057ec107d187f23")
        self.assertEqual(VERIFY.ALLOWED_CHANGED_PREFIXES, (
            "apps/companion/native-host/",
            "apps/extension/styles/",
            "evidence/extension/",
            "packages/test-fixtures/extension/",
        ))

    def test_extension_permissions_and_origin_are_exact(self) -> None:
        manifest = json.loads(VERIFY.MANIFEST.read_text(encoding="utf-8"))
        policy = json.loads(VERIFY.HOST_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(manifest["permissions"], ["activeTab", "nativeMessaging", "sidePanel"])
        self.assertNotIn("host_permissions", manifest)
        self.assertNotIn("content_scripts", manifest)
        self.assertEqual(policy["allowed_origins"], [VERIFY.EXTENSION_ORIGIN])
        self.assertNotIn("*", json.dumps(policy, sort_keys=True))

    def test_installer_has_no_arbitrary_path_or_command_argument(self) -> None:
        source = (
            PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host_installer.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            set(VERIFY.re.findall(r'parser\.add_argument\("([^"]+)"', source)),
            {"action", "--browser", "--confirm"},
        )
        self.assertNotIn("shell=True", source)
        self.assertIn("x2n-staging", source)
        self.assertIn("x2n-backup", source)

    def test_fixture_is_public_synthetic_and_covers_six_platforms(self) -> None:
        fixture = json.loads(VERIFY.FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["cases"]), 20)
        self.assertEqual(
            {item["platform"] for item in fixture["cases"] if item["supported"]},
            {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"},
        )
        for field in (
            "real_accounts",
            "contains_credentials",
            "contains_private_content",
            "contains_media_urls",
            "contains_local_absolute_paths",
        ):
            self.assertFalse(fixture[field])

    def test_external_environment_does_not_inherit_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-f004-env-") as value:
            env = VERIFY._isolated_env(Path(value))
        for field in ("GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN"):
            self.assertNotIn(field, env)
        self.assertEqual(env["UV_KEYRING_PROVIDER"], "disabled")
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertEqual(env["npm_config_ignore_scripts"], "true")

    def test_extension_e2e_uses_an_environment_allowlist(self) -> None:
        source = (
            PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs"
        ).read_text(encoding="utf-8")
        self.assertNotIn("...process.env", source)
        self.assertIn('PATH: process.env.PATH ?? ""', source)

    def test_acceptance_scope_does_not_claim_owner_or_downstream_execution(self) -> None:
        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["current_stage_gate"], "pass")
        self.assertEqual(state["current_stage_remote_upload"], "authorized_after_g1_pass")
        self.assertEqual(state["native_host_execution"], "pass_isolated_synthetic_owner_install_not_run")
        self.assertIn("owner_canary_not_run", state["acceptance_status"]["ACC.x2n.ext.001"])
        for field in ("real_account_execution", "platform_calls", "notion_calls", "model_calls", "media_processing"):
            self.assertEqual(state[field], "not_run")

    def test_current_sbom_accounts_for_install_script_without_executing_it(self) -> None:
        sbom = json.loads(VERIFY.SBOM.read_text(encoding="utf-8"))
        self.assertEqual(len(sbom["components"]), 30)
        properties = {
            item["name"]: item["value"]
            for item in sbom["metadata"]["properties"]
        }
        self.assertEqual(properties["x2n:install-script-packages"], "fsevents")
        self.assertEqual(properties["x2n:install-scripts-executed"], "0")
        self.assertEqual(properties["x2n:npm-install-policy"], "ignore-scripts")


if __name__ == "__main__":
    unittest.main()
