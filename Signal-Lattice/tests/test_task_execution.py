from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TaskExecutionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.contract = json.loads((cls.root / "machine/facts/task_execution_contract.json").read_text())
        cls.dag = json.loads((cls.root / "machine/facts/task_dag.json").read_text())

    def run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged = os.environ.copy()
        merged["PYTHONPATH"] = str(self.root / "src")
        if env:
            merged.update(env)
        return subprocess.run(
            [os.sys.executable, "scripts/run_task.py", *args],
            cwd=self.root,
            env=merged,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )

    def test_contract_is_single_canonical_set(self):
        self.assertFalse((self.root / "machine/facts/environment_task_contracts.json").exists())
        self.assertFalse((self.root / "schemas/environment_task_contracts.schema.json").exists())
        contract_ids = {row["task_id"] for row in self.contract["tasks"]}
        dag_ids = {row["id"] for row in self.dag["tasks"]}
        self.assertEqual(contract_ids, dag_ids)
        self.assertEqual(len(contract_ids), len(self.contract["tasks"]))
        self.assertEqual(self.contract["version"], "0.0.0.1.39")

    def test_every_task_validates(self):
        result = self.run_cli("--validate-all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "PASS")
        self.assertEqual(payload["task_count"], len(self.contract["tasks"]))
        self.assertFalse(payload["developer_research_required"])

    def test_authorized_side_effect_requires_explicit_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            artifacts = Path(temp) / "artifacts"
            repo = Path(temp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            result = self.run_cli(
                "--task", "T-005", "--execute", "--ignore-dependencies",
                env={"SIGNAL_LATTICE_ARTIFACT_DIR": str(artifacts), "SIGNAL_LATTICE_TARGET_REPO": str(repo)},
            )
            self.assertEqual(result.returncode, 2)
            receipt = json.loads((artifacts / "tasks/T-005.json").read_text())
            claimed = receipt.pop("receipt_sha256")
            expected = hashlib.sha256(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(claimed, expected)
            self.assertEqual(receipt["reason"], "EXPLICIT_SIDE_EFFECT_AUTHORIZATION_REQUIRED")

    def test_dependency_receipt_must_be_self_hashed(self):
        with tempfile.TemporaryDirectory() as temp:
            artifacts = Path(temp)
            tasks = artifacts / "tasks"
            tasks.mkdir()
            (tasks / "T-001.json").write_text(json.dumps({"state": "PASS", "receipt_sha256": "0" * 64}))
            result = self.run_cli(
                "--task", "T-002", "--execute",
                env={"SIGNAL_LATTICE_ARTIFACT_DIR": str(artifacts)},
            )
            self.assertEqual(result.returncode, 2)
            receipt = json.loads((tasks / "T-002.json").read_text())
            self.assertEqual(receipt["reason"], "DEPENDENCY_RECEIPT_NOT_PASS")
            self.assertEqual(receipt["dependencies"][0]["reason"], "RECEIPT_INVALID")

    def test_plan_is_low_entropy_and_complete(self):
        result = self.run_cli("--task", "T-029", "--plan")
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        for key in ("mode", "required_env", "commands", "expected", "failure_branch", "rollback", "evidence_path", "input_sha256"):
            self.assertIn(key, payload)
        self.assertTrue(payload["authorization_required"])
        self.assertEqual(payload["authorization_env"], "SIGNAL_LATTICE_APPLY")


if __name__ == "__main__":
    unittest.main()
