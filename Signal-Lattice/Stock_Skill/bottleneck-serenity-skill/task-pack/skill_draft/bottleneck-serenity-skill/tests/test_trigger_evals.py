#!/usr/bin/env python3
"""Fail-closed tests for the frozen Stage 3 trigger-eval evidence."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_trigger_evals.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_trigger_evals", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load trigger-eval validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class TriggerEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "bottleneck-serenity-skill"
        shutil.copytree(SKILL_ROOT, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def results_path(self) -> Path:
        return self.root / "evals" / "trigger_eval_results.json"

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
            self.root / "evals" / "prompts.csv",
            self.root / "evals" / "capability_oracles.csv",
            self.root / "SKILL.md",
        )

    def test_frozen_trigger_evidence_passes(self) -> None:
        self.assertEqual(
            self.validate(),
            {
                "case_total": 13,
                "routing_pass": 13,
                "case_pass": 13,
                "oracle_total": 18,
                "oracle_pass": 18,
                "judge_count": 2,
                "guaranteed_alpha_claims": 0,
            },
        )

    def test_route_mutation_fails_closed(self) -> None:
        result = self.load_results()
        case = next(
            item
            for item in result["executor"]["cases"]
            if item["id"] == "trigger-01"
        )
        case["observed_route"] = "respond_without_skill"
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.TriggerEvalError,
            "embedded executor cases drift",
        ):
            self.validate()

    def test_missing_case_fails_closed(self) -> None:
        result = self.load_results()
        result["executor"]["cases"].pop()
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.TriggerEvalError,
            "embedded executor cases drift",
        ):
            self.validate()

    def test_missing_oracle_verdict_fails_closed(self) -> None:
        result = self.load_results()
        result["judges"][0]["oracle_verdicts"].pop()
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.TriggerEvalError,
            "embedded judges drift",
        ):
            self.validate()

    def test_non_verbatim_evidence_quote_fails_closed(self) -> None:
        result = self.load_results()
        result["judges"][0]["oracle_verdicts"][0]["evidence_quote"] = (
            "not present in the raw response"
        )
        self.write_results(result)
        with self.assertRaisesRegex(
            VALIDATOR.TriggerEvalError,
            "embedded judges drift",
        ):
            self.validate()

    def test_noncanonical_csv_whitespace_fails_closed(self) -> None:
        prompts = self.root / "evals" / "prompts.csv"
        content = prompts.read_text(encoding="utf-8")
        prompts.write_text(
            content.replace("robust-03,true,compare,", "robust-03, true,compare,"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.TriggerEvalError,
            "non-canonical surrounding whitespace/quote",
        ):
            self.validate()

    def test_skill_artifact_drift_fails_closed(self) -> None:
        skill = self.root / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(VALIDATOR.TriggerEvalError, "artifact SHA"):
            self.validate()

    def test_current_binding_task_hash_mutation_fails_closed(self) -> None:
        path = self.root / "evals" / "current_eval_binding.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["executions"][0]["task_sha256"] = "0" * 64
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            VALIDATOR.TriggerEvalError,
            "execution receipt drift",
        ):
            self.validate()


if __name__ == "__main__":
    unittest.main()
