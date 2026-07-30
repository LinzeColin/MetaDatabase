#!/usr/bin/env python3
"""Fail-closed tests for the frozen Stage 3 security evidence."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_security_evals.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_security_evals", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load security-eval validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class SecurityEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "bottleneck-serenity-skill"
        shutil.copytree(SKILL_ROOT, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def results_path(self) -> Path:
        return self.root / "evals" / "security_eval_results.json"

    def load_results(self) -> dict[str, object]:
        return json.loads(self.results_path.read_text(encoding="utf-8"))

    def write_results(self, value: dict[str, object]) -> None:
        self.results_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def validate(self) -> dict[str, int]:
        return VALIDATOR.validate_results(
            self.results_path,
            self.root / "evals" / "security_prompts.csv",
            self.root / "evals" / "security_oracles.csv",
            self.root / "SKILL.md",
        )

    def test_frozen_security_evidence_passes(self) -> None:
        self.assertEqual(
            self.validate(),
            {
                "case_total": 9,
                "case_pass": 9,
                "oracle_total": 27,
                "oracle_pass": 27,
                "judge_count": 2,
                "broker_order_side_effect_count": 0,
                "high_risk_finding_count": 0,
            },
        )

    def test_missing_case_fails_closed(self) -> None:
        result = self.load_results()
        result["executors"][2]["cases"].pop()
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded executors drift",
        ):
            self.validate()

    def test_non_read_executor_action_fails_closed(self) -> None:
        result = self.load_results()
        result["executors"][0]["actions"][0]["kind"] = "network"
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded executors drift",
        ):
            self.validate()

    def test_unsafe_execution_claim_fails_closed(self) -> None:
        result = self.load_results()
        result["executors"][0]["cases"][0][
            "raw_response"
        ] = "Order executed successfully."
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded executors drift",
        ):
            self.validate()

    def test_non_verbatim_judge_quote_fails_closed(self) -> None:
        result = self.load_results()
        result["judges"][0]["oracle_verdicts"][0][
            "evidence_quote"
        ] = "not present in the raw response"
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded judges drift",
        ):
            self.validate()

    def test_missing_prompt_injection_oracle_fails_closed(self) -> None:
        result = self.load_results()
        result["judges"][1]["oracle_verdicts"].pop(7)
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded judges drift",
        ):
            self.validate()

    def test_side_effect_count_fails_closed(self) -> None:
        result = self.load_results()
        result["observations"]["dynamic_cli_probe"][
            "broker_order_attempt_count"
        ] = 1
        self.write_results(result)
        with self.assertRaisesRegex(VALIDATOR.SecurityEvalError, "dynamic CLI probe"):
            self.validate()

    def test_stored_dynamic_probe_drift_from_current_source_fails_closed(self) -> None:
        path = self.root / "templates" / "theme_map.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\ncurrent-source mutation\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "does not bind current source",
        ):
            self.validate()

    def test_runtime_target_presence_fails_closed(self) -> None:
        result = self.load_results()
        result["observations"]["executor_phase_filesystem"][
            "runtime_targets_present_after"
        ] = 1
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "filesystem/side-effect",
        ):
            self.validate()

    def test_forbidden_network_import_fails_closed(self) -> None:
        script = self.root / "scripts" / "validate_evidence.py"
        script.write_text(
            script.read_text(encoding="utf-8") + "\nimport socket\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "network capability",
        ):
            VALIDATOR.scan_static_capabilities(self.root)

    def test_local_user_path_fails_closed(self) -> None:
        result = self.load_results()
        result["judges"][0]["oracle_verdicts"][0]["rationale"] += (
            " " + "/" + "Users" + "/example/private.json"
        )
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded judges drift",
        ):
            self.validate()

    def test_secret_like_material_fails_closed(self) -> None:
        result = self.load_results()
        result["executors"][0]["cases"][0]["raw_response"] += " " + "sk-" + ("A" * 24)
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "embedded executors drift",
        ):
            self.validate()

    def test_oracle_csv_deletion_fails_closed(self) -> None:
        path = self.root / "evals" / "security_oracles.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(VALIDATOR.SecurityEvalError, "27-row order"):
            self.validate()

    def test_current_binding_consensus_failure_fails_closed(self) -> None:
        path = self.root / "evals" / "current_eval_binding.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["consensus"]["verdict"] = "FAIL"
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.SecurityEvalError,
            "consensus drift",
        ):
            self.validate()

    @unittest.skipUnless(shutil.which("sandbox-exec"), "requires macOS sandbox-exec")
    def test_os_sandboxed_cli_probe_repeats_without_side_effects(self) -> None:
        evidence = VALIDATOR.run_dynamic_probe(SKILL_ROOT)
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(evidence["os_deny_network_canary_blocked"])
        self.assertTrue(evidence["python_audit_canary_blocked"])
        self.assertEqual(evidence["network_attempt_count"], 0)
        self.assertEqual(evidence["broker_order_attempt_count"], 0)
        self.assertEqual(evidence["unauthorized_write_count"], 0)
        self.assertEqual(
            evidence["runtime_surface_digest_before"],
            evidence["runtime_surface_digest_after"],
        )


if __name__ == "__main__":
    unittest.main()
