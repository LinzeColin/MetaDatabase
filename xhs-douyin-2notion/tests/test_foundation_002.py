from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_foundation_002",
    PROJECT_ROOT / "scripts/verify_foundation_002.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Foundation002Tests(unittest.TestCase):
    def test_static_task_checks_pass(self) -> None:
        checks = VERIFY.run_checks(
            verify_worktree=False,
            allow_external_main_dirty=False,
            run_external=False,
        )
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_run_is_exactly_one_task(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.foundation.002")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S01-F002")
        self.assertEqual(VERIFY.TASK_BASE_COMMIT, "69130c1db9946850b23e1c78f771129eb094eea2")
        self.assertEqual(VERIFY.FINAL_COMMIT, "ae17e377090ef3bc1123d2512cda0daef9efe1cb")
        self.assertNotIn("apps/extension/", VERIFY.ALLOWED_CHANGED_PREFIXES)
        self.assertNotIn("apps/companion/", VERIFY.ALLOWED_CHANGED_PREFIXES)

    def test_acceptance_scope_does_not_claim_downstream_products(self) -> None:
        state = json.loads((PROJECT_ROOT / "machine/facts/task_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["current_stage_gate"], "pass")
        self.assertEqual(state["current_stage_remote_upload"], "authorized_after_g1_pass")
        self.assertEqual(
            state["acceptance_status"]["ACC.x2n.ext.003"],
            "pass_temp_native_host_contract_idempotency_injection",
        )
        self.assertIn("downstream_not_run", state["acceptance_status"]["ACC.x2n.data.003"])
        self.assertEqual(
            state["acceptance_status"]["ACC.x2n.data.001"],
            "pass_sqlite_store_scope_schema_fk_unique_integrity",
        )

    def test_contract_dependency_sbom_is_reproducible(self) -> None:
        result = subprocess.run(
            (sys.executable, "-B", "scripts/generate_foundation_002_sbom.py", "--check"),
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, {"components": 26, "status": "PASS"})

    def test_fixture_suite_is_synthetic_and_complete(self) -> None:
        suite = json.loads(
            (PROJECT_ROOT / "packages/test-fixtures/contracts/v1/fixture_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(suite["case_count"], 144)
        self.assertEqual(suite["generated_fuzz_case_count"], 106)
        self.assertTrue(suite["synthetic_only"])
        self.assertFalse(suite["real_accounts"])
        self.assertFalse(suite["contains_credentials"])
        self.assertFalse(suite["contains_media_urls"])

    def test_external_environment_is_minimal_and_keyring_disabled(self) -> None:
        env = VERIFY._isolated_env(Path("isolated-home"), pythonpath=True)
        self.assertEqual(env["UV_KEYRING_PROVIDER"], "disabled")
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("GH_TOKEN", env)


if __name__ == "__main__":
    unittest.main()
