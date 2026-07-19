from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_foundation_001",
    PROJECT_ROOT / "scripts/verify_foundation_001.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Foundation001Tests(unittest.TestCase):
    def test_core_checks_pass(self) -> None:
        checks = VERIFY.run_checks(verify_worktree=False, allow_external_main_dirty=False)
        self.assertEqual([check.status for check in checks], ["PASS"] * len(checks))

    def test_declared_task_scope_is_exact(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.foundation.001")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S01-F001")
        self.assertNotIn("packages/contracts/src", VERIFY.ALLOWED_CHANGED_PREFIXES)

    def test_scaffold_remains_permission_free_with_only_registered_contract_dependencies(self) -> None:
        lock = json.loads((PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8"))
        registry_packages = [
            key
            for key, metadata in lock["packages"].items()
            if key.startswith("node_modules/") and metadata.get("link") is not True
        ]
        registry_names = {key.removeprefix("node_modules/") for key in registry_packages}
        self.assertEqual(len(registry_names), 21)
        self.assertIn("typescript", registry_names)
        self.assertTrue(all(name == "typescript" or name.startswith("@typescript/typescript-") for name in registry_names))
        self.assertTrue(all("hasInstallScript" not in lock["packages"][key] for key in registry_packages))
        manifest = json.loads((PROJECT_ROOT / "apps/extension/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["permissions"], [])
        self.assertNotIn("host_permissions", manifest)
        self.assertNotIn("side_panel", manifest)

    def test_real_canary_fails_with_minimum_decision_question(self) -> None:
        python = sys.executable if sys.version_info >= (3, 12) else VERIFY.shutil.which("python3.12")
        self.assertTrue(python)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "apps/companion/src",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        result = subprocess.run(
            (str(python), "-B", "-m", "x2n_companion.scaffold", "canary"),
            cwd=PROJECT_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "FAIL_CLOSED")
        self.assertTrue(payload["minimum_decision_question"])

    def test_current_acceptance_does_not_claim_product_lifecycle(self) -> None:
        state = json.loads((PROJECT_ROOT / "machine/facts/task_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["current_stage_gate"], "not_run")
        self.assertEqual(state["current_stage_remote_upload"], "forbidden_until_g1_pass")
        self.assertIn("downstream_not_run", state["acceptance_status"]["ACC.x2n.rel.008"])


if __name__ == "__main__":
    unittest.main()
