#!/usr/bin/env python3
"""Durable positive and fail-closed Oracles for the BSS completion audit."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "Stock_Skill/bottleneck-serenity-skill"
SCRIPT = PROJECT_ROOT / "scripts/validate_completion_audit.py"
AUDIT = PROJECT_ROOT / "COMPLETION_AUDIT.json"
ACCEPTANCE = PROJECT_ROOT / "task-pack/04_ACCEPTANCE_VALIDATION_STOP.md"
TASKS = PROJECT_ROOT / "task-pack/03_STAGE_PHASE_TASKS.md"

SPEC = importlib.util.spec_from_file_location("bss_completion_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CompletionAuditTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.expected = MODULE.build_expected(REPO_ROOT)

    def test_committed_audit_is_canonical_and_current(self) -> None:
        self.assertEqual(
            MODULE.validate_serialized(AUDIT.read_bytes(), REPO_ROOT),
            self.expected,
        )
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--check"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "sources=32/39 (partial=7); acceptance=39/44 (pending=5)",
            result.stdout,
        )
        self.assertIn("evidence=C/MISSING:0", result.stdout)
        readiness = self.expected["release_readiness"]
        self.assertEqual(readiness["task_id"], "BSS-S4-P1-T002")
        self.assertEqual(readiness["status"], "PASS_CANDIDATE_NOT_PUBLISHED")
        self.assertEqual(readiness["candidate_overlay"]["path_count"], 39)
        self.assertTrue(
            readiness["verification"]["clean_restore_git_porcelain_empty"]
        )
        self.assertFalse(
            readiness["verification"]["current_release_sha256_stored"]
        )
        self.assertEqual(len(readiness["release_sha_consumer_paths"]), 3)
        gate = self.expected["mechanical_final_gate"]
        self.assertEqual(gate["task_id"], "BSS-S4-P2-T001")
        self.assertEqual(gate["status"], "PASS")
        self.assertEqual(gate["candidate_overlay"]["path_count"], 39)
        self.assertEqual(gate["verification"]["finding_closed"], 36)
        self.assertTrue(gate["verification"]["changed_paths_allowlisted"])
        self.assertFalse(gate["verification"]["current_release_sha256_stored"])
        self.assertFalse(gate["policy"]["reviewer_used"])
        self.assertFalse(gate["policy"]["live_provider_run"])
        self.assertFalse(gate["policy"]["conditional_remediation_activated"])

    def test_missing_source_item_fails_closed(self) -> None:
        mutant = copy.deepcopy(self.expected)
        mutant["source_items"].pop()
        with self.assertRaisesRegex(MODULE.AuditError, "Source ID.*drift"):
            MODULE.validate_document(mutant, REPO_ROOT)

    def test_missing_acceptance_item_fails_closed(self) -> None:
        mutant = copy.deepcopy(self.expected)
        mutant["acceptance_items"].pop()
        with self.assertRaisesRegex(MODULE.AuditError, "Acceptance ID.*drift"):
            MODULE.validate_document(mutant, REPO_ROOT)

    def test_c_or_missing_evidence_grade_fails_closed(self) -> None:
        for forbidden in ("C", "MISSING"):
            with self.subTest(forbidden=forbidden):
                mutant = copy.deepcopy(self.expected)
                mutant["evidence_catalog"][0]["grade"] = forbidden
                with self.assertRaisesRegex(
                    MODULE.AuditError, "forbidden/unknown evidence grade"
                ):
                    MODULE.validate_document(mutant, REPO_ROOT)

    def test_missing_evidence_path_fails_closed(self) -> None:
        mutant = copy.deepcopy(self.expected)
        mutant["evidence_catalog"][0]["paths"] = [
            "Stock_Skill/bottleneck-serenity-skill/does-not-exist"
        ]
        with self.assertRaisesRegex(MODULE.AuditError, "missing evidence path"):
            MODULE.validate_document(mutant, REPO_ROOT)

    def test_traceability_drift_fails_closed(self) -> None:
        original = ACCEPTANCE.read_text(encoding="utf-8")
        needle = "| `ACC-S0-001` | `REQ-005,REQ-018,NG-007` |"
        replacement = "| `ACC-S0-001` | `REQ-004,REQ-018,NG-007` |"
        self.assertIn(needle, original)
        altered = original.replace(needle, replacement, 1)

        def reader(path: Path) -> str:
            if path.resolve() == ACCEPTANCE.resolve():
                return altered
            return path.read_text(encoding="utf-8")

        with self.assertRaisesRegex(
            MODULE.AuditError, "differs from canonical derived state"
        ):
            MODULE.validate_document(self.expected, REPO_ROOT, reader)

    def test_stage4_review_phase_drift_fails_closed(self) -> None:
        original = TASKS.read_text(encoding="utf-8")
        needle = "| `BSS-S4-P2-T001` | Mechanical final gate |"
        replacement = "| `BSS-S4-P2-T001` | Review |"
        self.assertIn(needle, original)
        altered = original.replace(needle, replacement, 1)

        def reader(path: Path) -> str:
            if path.resolve() == TASKS.resolve():
                return altered
            return path.read_text(encoding="utf-8")

        with self.assertRaisesRegex(MODULE.AuditError, "routing drift"):
            MODULE.validate_document(self.expected, REPO_ROOT, reader)

    def test_pending_set_and_count_drift_fails_closed(self) -> None:
        mutant = copy.deepcopy(self.expected)
        item = next(
            row
            for row in mutant["acceptance_items"]
            if row["id"] == "ACC-S4-005"
        )
        item["status"] = "SATISFIED"
        item["evidence_grade"] = "A"
        item["pending_task_ids"] = []
        with self.assertRaisesRegex(MODULE.AuditError, "pending Acceptance set drift"):
            MODULE.validate_document(mutant, REPO_ROOT)

    def test_unknown_evidence_reference_fails_closed(self) -> None:
        mutant = copy.deepcopy(self.expected)
        mutant["source_items"][0]["evidence_refs"].append("E-UNKNOWN")
        with self.assertRaisesRegex(MODULE.AuditError, "unknown evidence refs"):
            MODULE.validate_document(mutant, REPO_ROOT)

    def test_noncanonical_json_fails_closed(self) -> None:
        payload = json.dumps(self.expected, ensure_ascii=False).encode("utf-8")
        with self.assertRaisesRegex(MODULE.AuditError, "not canonical"):
            MODULE.validate_serialized(payload, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
