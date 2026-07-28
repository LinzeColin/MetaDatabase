from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_010",
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


class Adapters010VerifierTests(unittest.TestCase):
    def test_task_identity_and_historical_receipt_boundary_are_exact(self) -> None:
        self.assertEqual(VERIFY.TASK_ID, "TSK.x2n.adapters.010")
        self.assertEqual(VERIFY.RUN_ID, "RUN-X2N-S03-A010")
        self.assertEqual(VERIFY.PHASE, "PH.X2N.3.10")
        self.assertEqual(VERIFY.TASK010_FINAL_COMMIT, "c528ff14836f116f624fa8b1ea63472a7f4b678f")
        task = VERIFY._load_task()
        self.assertEqual(task["status"], "completed")
        state = json.loads(VERIFY.TASK_STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["stage_gate"], "pass")
        self.assertFalse(state["stage_3_remote_upload_authorized"])
        self.assertTrue(state["stage_4_authorized"])

    def test_static_contract_checks_pass_without_external_execution(self) -> None:
        checks = VERIFY.run_checks(verify_worktree=False, run_external=False, require_evidence=False)
        self.assertEqual([item.status for item in checks], ["PASS"] * len(checks))

    def test_historical_resume_remains_planned_while_current_task_is_complete(self) -> None:
        resume = json.loads(VERIFY.RESUME_FACT.read_text(encoding="utf-8"))
        self.assertEqual(resume["next_task"]["id"], VERIFY.TASK_ID)
        self.assertEqual(resume["next_task"]["status"], "PLANNED")
        self.assertFalse(resume["authorization"]["new_dag_task_executed"])

    def test_evidence_is_safe_and_bound_to_pinned_task_inputs_when_present(self) -> None:
        if not VERIFY.EVIDENCE.exists():
            self.skipTest("Task010 evidence is emitted after acceptance")
        self.assertEqual(VERIFY.verify_evidence().status, "PASS")

    def test_source_receipt_is_pinned_to_task010_final_commit(self) -> None:
        self.assertEqual(
            VERIFY._source_receipt(),
            json.loads(VERIFY.EVIDENCE.read_text(encoding="utf-8"))["acceptance_input_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
