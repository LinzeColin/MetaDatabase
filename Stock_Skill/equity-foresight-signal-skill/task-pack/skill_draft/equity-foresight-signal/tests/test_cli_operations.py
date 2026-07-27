from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "equity_foresight_signal", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, json.loads(proc.stdout)


class CLIOperationTests(unittest.TestCase):
    def test_601_audit_runtime(self):
        code, result = run_cli("audit-runtime")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["agent_invocations_total"], 0)
        self.assertEqual(result["llm_requests_total"], 0)

    def test_602_validate_dataset(self):
        code, result = run_cli("validate-dataset", "fixtures/pit_dataset.json")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["agent_invocations_total"], 0)

    def test_603_train_direction_summary_is_deterministic_and_not_promoted(self):
        first_code, first = run_cli("train-direction", "fixtures/pit_dataset.json", "fixtures/training_config.json")
        second_code, second = run_cli("train-direction", "fixtures/pit_dataset.json", "fixtures/training_config.json")
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ENGINEERING_TRAINING_COMPLETE")
        self.assertFalse(first["automatic_promotion_permitted"])
        self.assertEqual(first["outcome_claim"], "NOT_PROVEN")
        self.assertEqual(first["llm_requests_total"], 0)

    def test_604_host_status_is_host_owned(self):
        code, result = run_cli("host-status", "--as-of", "2026-07-24T21:00:00Z", "--bundle", "fixtures/bundle.json")
        self.assertEqual(code, 0)
        self.assertFalse(result["self_network_transport"])
        self.assertFalse(result["self_persistence"])
        self.assertEqual(result["capability_state"], "RESEARCH_ONLY")

    def test_605_dataset_symlink_is_rejected(self):
        link = ROOT / "fixtures" / "unsafe_dataset_link.json"
        try:
            link.symlink_to(ROOT / "fixtures" / "pit_dataset.json")
            code, result = run_cli("validate-dataset", str(link))
            self.assertEqual(code, 2)
            self.assertEqual(result["reason_code"], "INPUT_IO_ERROR")
        finally:
            link.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
