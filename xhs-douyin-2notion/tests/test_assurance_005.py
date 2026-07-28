from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "scripts/run_assurance_005_acceptance.py"
VERIFIER = PROJECT_ROOT / "scripts/verify_assurance_005.py"
SCHEMA = PROJECT_ROOT / "machine/schemas/stage_6_assurance_005_go_live_receipt.schema.json"


class Assurance005Tests(unittest.TestCase):
    def _isolated_environment(self, home: Path) -> dict[str, str]:
        return {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(PROJECT_ROOT / "apps/companion/src")
            + os.pathsep
            + str(PROJECT_ROOT / "packages/contracts/src"),
        }

    def test_owner_acceptance_runner_fails_closed_without_private_runtime_and_emits_no_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="x2n-a005-runner-") as temporary:
            result = subprocess.run(
                [sys.executable, "-B", str(RUNNER)],
                cwd=PROJECT_ROOT,
                env=self._isolated_environment(Path(temporary)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        receipt = json.loads(result.stderr.strip())
        self.assertEqual(receipt["status"], "FAIL_CLOSED")
        self.assertFalse(receipt["paths_emitted"])
        self.assertNotIn("/" + "Users/", result.stderr)
        self.assertNotIn("github" + "_pat_", result.stderr)

    def test_public_receipt_verifier_requires_real_immutable_receipt(self) -> None:
        self.assertFalse((PROJECT_ROOT / "evidence/release/TSK.x2n.assurance.005.json").exists())
        result = subprocess.run(
            [sys.executable, "-B", str(VERIFIER)],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr.strip())["status"], "FAIL_CLOSED")

    def test_public_schema_is_aggregate_only_and_binds_the_exact_direct_release(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        rendered = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        self.assertEqual(schema["$id"], "urn:x2n:stage-6-assurance-005-go-live-receipt:1.0")
        self.assertIn("PASS_OWNER_MVP_DIRECT_RELEASE_CORE", rendered)
        self.assertIn("private_manifest_item_count", rendered)
        self.assertNotIn("/" + "Users/", rendered)
        self.assertNotIn("credential", rendered.lower())
        self.assertNotIn("cdn", rendered.lower())

    def test_acceptance_runner_is_read_only_and_has_no_prerelease_gate(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn(".arm(", source)
        self.assertNotIn(".deploy(", source)
        self.assertNotIn("online_smoke(", source)
        self.assertNotIn("Alpha", source)
        self.assertNotIn("Beta", source)
        self.assertNotIn("soak", source.lower())


if __name__ == "__main__":
    unittest.main()
