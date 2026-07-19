from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
ASSETS = SKILL_DIR / "assets"


def remove_caches() -> None:
    for cache in SKILL_DIR.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    for compiled in SKILL_DIR.rglob("*.py[co]"):
        try:
            compiled.unlink()
        except FileNotFoundError:
            pass


def setUpModule() -> None:
    remove_caches()


def tearDownModule() -> None:
    remove_caches()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


score_stock = load_module(
    "score_stock_opportunities", SCRIPTS / "score_stock_opportunities.py"
)
validate_deliverable = load_module(
    "validate_deliverable", SCRIPTS / "validate_deliverable.py"
)
validate_skill = load_module("validate_skill", SCRIPTS / "validate_skill.py")


class ScoreStockOpportunityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(
            (ASSETS / "stock-opportunity-score-input.example.json").read_text(
                encoding="utf-8"
            )
        )

    def test_example_exercises_advance_diligence_and_reject(self) -> None:
        rows = score_stock.score_payload(self.payload)
        by_id = {row["id"]: row for row in rows}
        self.assertEqual([row["id"] for row in rows], ["S001", "S002", "S003"])
        self.assertEqual(by_id["S001"]["maturity_code"], "E5")
        self.assertEqual(by_id["S001"]["status"], "ADVANCE_RESEARCH")
        self.assertEqual(by_id["S002"]["maturity_code"], "E3")
        self.assertEqual(by_id["S002"]["status"], "DILIGENCE_NEXT")
        self.assertEqual(by_id["S003"]["status"], "REJECT")

    def test_e1_ceiling_overrides_high_score(self) -> None:
        candidate = self.payload["candidates"][0]
        candidate["evidence_signals"].update(
            company_filings=0,
            quantified_exposure_metrics=0,
            commercial_capture_signals=0,
            current_valuation_observations=0,
            confirmed_catalysts=0,
            liquidity_checks=0,
        )
        row = score_stock.score_payload({"fixture": True, "candidates": [candidate]})[0]
        self.assertEqual(row["maturity_code"], "E1")
        self.assertEqual(row["status"], "SCREEN_FLAG")

    def test_hard_stop_overrides_high_score(self) -> None:
        candidate = self.payload["candidates"][0]
        candidate["hard_stops"] = ["Security identity is unresolved"]
        row = score_stock.score_payload({"fixture": True, "candidates": [candidate]})[0]
        self.assertEqual(row["status"], "REJECT")

    def test_empty_candidate_set_is_valid(self) -> None:
        rows = score_stock.score_payload({"candidates": []})
        self.assertEqual(rows, [])
        self.assertIn("NO_QUALIFIED_CANDIDATE", score_stock.format_markdown(rows))

    def test_invalid_score_is_rejected(self) -> None:
        self.payload["candidates"][0]["dimensions"]["commercial_value_pool"] = 11
        with self.assertRaises(score_stock.InputError):
            score_stock.score_payload(self.payload)

    def test_missing_dimension_is_rejected(self) -> None:
        del self.payload["candidates"][0]["dimensions"]["issuer_exposure_attribution"]
        with self.assertRaises(score_stock.InputError):
            score_stock.score_payload(self.payload)

    def test_missing_evidence_signal_is_rejected(self) -> None:
        del self.payload["candidates"][0]["evidence_signals"]["company_filings"]
        with self.assertRaises(score_stock.InputError):
            score_stock.score_payload(self.payload)

    def test_markdown_exposes_score_risk_confidence_maturity_and_gate(self) -> None:
        rendered = score_stock.format_markdown(score_stock.score_payload(self.payload))
        for token in ("Decision score", "Risk", "Confidence", "E-level", "ADVANCE_RESEARCH"):
            self.assertIn(token, rendered)


class DeliverableValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(
            (ASSETS / "deliverable.example.json").read_text(encoding="utf-8")
        )

    def findings(self):
        return validate_deliverable.validate(copy.deepcopy(self.payload))

    def assert_has(self, code: str, severity: str = "error") -> None:
        findings = self.findings()
        self.assertTrue(
            any(f.code == code and f.severity == severity for f in findings),
            msg="\n".join(
                f"{f.severity} {f.code} {f.path}: {f.message}" for f in findings
            ),
        )

    def test_example_passes_without_findings(self) -> None:
        self.assertEqual(self.findings(), [])

    def test_zero_qualified_candidate_is_valid(self) -> None:
        self.payload["candidates"] = []
        self.payload["assumptions"] = []
        self.payload["diligence"] = []
        self.payload["decision"].update(
            outcome="NO_QUALIFIED_CANDIDATE",
            selected_candidate_id=None,
            evidence_maturity="E0",
            reason="No supplied candidate crossed the evidence gate.",
            why_not_stronger="No filing-backed exposure exists.",
            first_rejection="No real security identity.",
            next_diligence_workflow="Stop until a real issuer and filing are supplied.",
        )
        self.assertEqual(self.findings(), [])

    def test_unsupported_fact_fails(self) -> None:
        self.payload["claims"][0]["source_ids"] = []
        self.assert_has("UNSUPPORTED_CLAIM")

    def test_unregistered_url_fails(self) -> None:
        self.payload["decision"]["next_diligence_workflow"] += " https://example.com/unregistered"
        self.assert_has("UNREGISTERED_URL")

    def test_snippet_only_cannot_support_core_fact(self) -> None:
        self.payload["sources"][0]["access_level"] = "snippet_only"
        self.assert_has("CORE_WEAK_ACCESS")

    def test_synthetic_only_cannot_support_core_fact(self) -> None:
        source = self.payload["sources"][0]
        source.update(
            source_type="synthetic",
            origin="synthetic",
            access_level="synthetic",
            evidence_class="risk_falsifier",
        )
        self.assert_has("CORE_WEAK_ACCESS")

    def test_declared_maturity_must_match_signals(self) -> None:
        self.payload["candidates"][0]["maturity_code"] = "E2"
        self.assert_has("MATURITY_MISMATCH")

    def test_high_score_does_not_bypass_exposure_gate(self) -> None:
        candidate = self.payload["candidates"][0]
        candidate.update(
            decision_score=95,
            evidence_confidence=95,
            status="ADVANCE_RESEARCH",
        )
        self.payload["decision"].update(outcome="ADVANCE_RESEARCH")
        self.assert_has("ADVANCE_GATE")

    def test_synthetic_fixture_cannot_be_advanced(self) -> None:
        candidate = self.payload["candidates"][0]
        candidate["status"] = "DILIGENCE_NEXT"
        self.payload["decision"]["outcome"] = "DILIGENCE_NEXT"
        self.assert_has("FIXTURE_OVERCLAIM")

    def test_private_source_in_public_output_requires_redaction(self) -> None:
        source = self.payload["sources"][0]
        source.update(origin="private", access_level="internal_private", redacted=False)
        self.assert_has("PRIVATE_NOT_REDACTED")

    def test_completed_diligence_requires_evidence(self) -> None:
        self.payload["diligence"][0]["status"] = "passed"
        self.assert_has("UNRUN_DILIGENCE")

    def test_guarantee_language_fails(self) -> None:
        self.payload["decision"]["reason"] += " 保证收益。"
        self.assert_has("GUARANTEE_LANGUAGE")

    def test_personal_trade_instruction_fails(self) -> None:
        self.payload["decision"]["reason"] += " 建议你马上买入。"
        self.assert_has("PERSONAL_ACTION")

    def test_local_private_path_fails(self) -> None:
        synthetic_path = str(
            Path("/").joinpath("Users", "example", ".codex", "sessions", "fixture.jsonl")
        )
        self.payload["decision"]["reason"] += f" {synthetic_path}"
        self.assert_has("LOCAL_USER_PATH")

    def test_high_stakes_requires_opened_primary_source(self) -> None:
        for source in self.payload["sources"]:
            source["source_type"] = "reputable_media"
        self.assert_has("HIGH_STAKES_SOURCE")

    def test_decision_must_match_selected_candidate_status(self) -> None:
        self.payload["decision"]["outcome"] = "REJECT"
        self.assert_has("DECISION_STATUS_MISMATCH")


class SkillValidatorTests(unittest.TestCase):
    def test_current_skill_passes_strictly(self) -> None:
        remove_caches()
        self.assertEqual(validate_skill.validate_skill(SKILL_DIR), [])

    def test_extra_frontmatter_field_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_skill = Path(tmp) / "demo-skill"
            temp_skill.mkdir()
            (temp_skill / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: Use for testing. Do not use elsewhere.\nversion: 1\n---\n# Demo\n",
                encoding="utf-8",
            )
            findings = validate_skill.validate_skill(temp_skill)
            self.assertTrue(any("Unsupported frontmatter" in f.message for f in findings))


class CliSmokeTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=SKILL_DIR,
            text=True,
            capture_output=True,
            check=False,
            env={**dict(), "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_score_cli(self) -> None:
        result = self.run_cli(
            str(SCRIPTS / "score_stock_opportunities.py"),
            "--input",
            str(ASSETS / "stock-opportunity-score-input.example.json"),
            "--format",
            "markdown",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ADVANCE_RESEARCH", result.stdout)

    def test_deliverable_cli_strict(self) -> None:
        result = self.run_cli(
            str(SCRIPTS / "validate_deliverable.py"),
            "--input",
            str(ASSETS / "deliverable.example.json"),
            "--strict",
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_skill_cli_strict(self) -> None:
        remove_caches()
        result = self.run_cli(
            str(SCRIPTS / "validate_skill.py"), str(SKILL_DIR), "--strict"
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
