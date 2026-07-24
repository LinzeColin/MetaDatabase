#!/usr/bin/env python3
"""Positive and mutation tests for the immutable Historical E2E case."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_historical_e2e.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_bss_test_historical_e2e", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class HistoricalE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="bss-historical-e2e-")
        self.root = Path(self._temporary.name) / "skill"
        scripts = self.root / "scripts"
        scripts.mkdir(parents=True)
        for name in (
            "analyze_portfolio_clusters.py",
            "presentation_contract.py",
            "score_opportunity.py",
            "validate_evidence.py",
            "validate_historical_e2e.py",
        ):
            shutil.copy2(SKILL_ROOT / "scripts" / name, scripts / name)
        self.case = self.root / "evals" / "historical_e2e"
        shutil.copytree(SKILL_ROOT / "evals" / "historical_e2e", self.case)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def read_json(self, name: str) -> dict[str, Any]:
        return json.loads((self.case / name).read_text(encoding="utf-8"))

    def write_json(self, name: str, payload: dict[str, Any]) -> None:
        (self.case / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def mutate(
        self,
        name: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        payload = self.read_json(name)
        change(payload)
        self.write_json(name, payload)

    def assert_invalid(self, pattern: str) -> None:
        with self.assertRaisesRegex(VALIDATOR.HistoricalE2EError, pattern):
            VALIDATOR.validate_case(self.case, self.root)

    def test_frozen_case_passes_with_exact_summary(self) -> None:
        self.assertEqual(
            VALIDATOR.validate_case(self.case, self.root),
            {
                "case_id": "historical-ai-data-center-power-transformers-20241231",
                "source_cutoff": "2024-12-31",
                "claim_count": 14,
                "fact_count": 8,
                "source_count": 12,
                "latest_source_date": "2024-12-20",
                "all_source_dates_lte_cutoff": True,
                "decision_label": "BOTTLENECK_NOT_EQUITY",
                "final_score": 55.215,
                "role_count": 6,
                "system_node_count": 6,
                "kill_switch_count": 3,
                "portfolio_pair_count": 1,
                "portfolio_jaccard": 0.857,
                "rubric_total": 23,
                "rubric_maximum": 24,
                "rubric_verdict": "PASS",
                "post_cutoff_outcomes_used": False,
                "expected_answer_in_input": False,
            },
        )

    def test_post_cutoff_source_date_fails(self) -> None:
        self.mutate(
            "evidence.json",
            lambda payload: payload["claims"][0]["sources"][0].__setitem__(
                "date", "2025-01-01"
            ),
        )
        self.assert_invalid("later than source_cutoff")

    def test_missing_source_date_fails(self) -> None:
        self.mutate(
            "evidence.json",
            lambda payload: payload["claims"][0]["sources"][0].pop("date"),
        )
        self.assert_invalid("date is required|canonical YYYY-MM-DD")

    def test_missing_artifact_fails(self) -> None:
        (self.case / "memo.md").unlink()
        self.assert_invalid("file set mismatch")

    def test_wrong_envelope_fails(self) -> None:
        self.mutate(
            "decision.json",
            lambda payload: payload.__setitem__("source_cutoff", "2024-12-30"),
        )
        self.assert_invalid("source_cutoff must equal")

    def test_expected_answer_in_frozen_query_fails(self) -> None:
        self.mutate(
            "frozen_input.json",
            lambda payload: payload.__setitem__(
                "query", payload["query"] + " Expected: BOTTLENECK_NOT_EQUITY."
            ),
        )
        self.assert_invalid("expected decision label leaked")

    def test_missing_role_fails(self) -> None:
        self.mutate(
            "decision.json",
            lambda payload: payload["role_screening"].pop(),
        )
        self.assert_invalid("six-role screening")

    def test_gate_flip_fails(self) -> None:
        self.mutate(
            "decision.json",
            lambda payload: payload["non_compensating_gates"][2].__setitem__(
                "verdict", "PASS"
            ),
        )
        self.assert_invalid("gate verdicts changed")

    def test_hard_flag_removal_fails(self) -> None:
        self.mutate(
            "opportunity.json",
            lambda payload: payload["hard_flags"].__setitem__(
                "no_material_revenue_bridge", False
            ),
        )
        self.assert_invalid(
            "computed decision label changed|active hard flags changed|"
            "incomplete equity_bridge requires hard_flags.no_material_revenue_bridge=true"
        )

    def test_portfolio_causal_overlap_mutation_fails(self) -> None:
        self.mutate(
            "portfolio.json",
            lambda payload: payload["positions"][1]["risk_factors"].pop(),
        )
        self.assert_invalid("causal overlap changed")

    def test_rubric_total_tamper_fails(self) -> None:
        self.mutate(
            "rubric.json",
            lambda payload: payload.__setitem__("total_score", 24),
        )
        self.assert_invalid("total_score must recompute")

    def test_post_cutoff_outcome_key_fails(self) -> None:
        self.mutate(
            "decision.json",
            lambda payload: payload.__setitem__("actual_return", 99),
        )
        self.assert_invalid("prohibited post-cutoff outcome key")

    def test_memo_heading_removal_fails(self) -> None:
        path = self.case / "memo.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("## 10. Red team", "### 10. Red team"),
            encoding="utf-8",
        )
        self.assert_invalid("section headings or order changed")

    def test_issuer_before_security_map_fails(self) -> None:
        path = self.case / "memo.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "The payer test passes at the downstream layer.",
                "The payer test passes at the downstream layer for GEV.",
            ),
            encoding="utf-8",
        )
        self.assert_invalid("appears before Security map")

    def test_unregistered_issuer_shapes_before_security_map_fail_closed(self) -> None:
        path = self.case / "memo.md"
        original = path.read_text(encoding="utf-8")
        presentation_oracles = json.loads(
            (SKILL_ROOT / "evals/presentation_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        issuer_shapes = (
            "ABB",
            "Acme",
            "Acme Holdings",
            "Acme supplies equipment",
            "Blue Origin",
            "$ZZZ",
            "1234.T",
            "Example Exchange",
            "Acme plc",
            "nvidia",
            "acme supplies equipment",
            "www.acme.com/research",
            "ftp://acme.com/file",
            "acme.com/research",
            "research@acme.com",
            "The constrained node is controlled by Acme under current rules",
            "A single source, nvidia, controls qualification under current rules",
            "Acme's qualified line controls supply under current rules",
            "The issuer is nvidia",
            "The selected security is nvidia",
            "Our benchmark is acme global",
            "A candidate supplier is nvidia",
            "One listed issuer, acme, may capture the rent",
            "Demand from nvidia remains funded",
            "The system depends on acme for supply",
            "The critical supplier is `nvidia`",
            "A supplier called acme builds equipment",
            "nvidia is the supplier",
            "The manufacturer is nvidia",
            "nvidia may supply qualified equipment",
            "Procurement relies on nvidia",
            "The bottleneck owner named nvidia controls supply",
            "We shortlisted nvidia for the role",
            "Capacity at nvidia remains constrained",
            "The primary vendor, nvidia, has spare slots",
            "nvidia remains the only qualified source",
            "The winner was nvidia",
            "Source: nvidia annual report",
            "Demand is routed through nvidia",
            "Critical capacity belongs to nvidia",
            "Funding is supplied by acme",
            "This leaves nvidia as the only listed exposure",
            *presentation_oracles["negative_issuer_slots"],
        )
        for issuer_shape in issuer_shapes:
            with self.subTest(issuer_shape=issuer_shape):
                path.write_text(
                    original.replace(
                        "The payer test passes at the downstream layer.",
                        f"The payer test passes at the downstream layer. {issuer_shape}.",
                        1,
                    ),
                    encoding="utf-8",
                )
                self.assert_invalid("appears before Security map")
        path.write_text(original, encoding="utf-8")

    def test_role_neutral_generic_prose_remains_valid(self) -> None:
        path = self.case / "memo.md"
        original = path.read_text(encoding="utf-8")
        presentation_oracles = json.loads(
            (SKILL_ROOT / "evals/presentation_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        reviewed_positive_prose = " ".join(
            presentation_oracles["positive_role_neutral_statements"]
        )
        path.write_text(
            original.replace(
                "The payer test passes at the downstream layer.",
                (
                    "The payer test passes at the downstream layer. "
                    "Demand is funded through committed procurement. "
                    "Capacity may expand before monetization. "
                    "Suppliers can add generic production lines. "
                    "Owner controls the constrained node. "
                    "Unlocker supplies missing capacity. "
                    "Substitute provides an alternative architecture. "
                    "Tollbooth operates the qualification gate. "
                    "Absorber owns compatible spare slots. "
                    "Public proxy offers liquid exposure. "
                    "Manufacturer may supply qualified equipment. "
                    "Vendor provides generic capacity. "
                    "Fragile. Uncertain. Qualified. Constrained. Funded. "
                    "Substitutable. "
                    "The mandatory roles are Factory Testing and Specialized Logistics. "
                    f"{reviewed_positive_prose}"
                ),
                1,
            ),
            encoding="utf-8",
        )
        VALIDATOR.validate_case(self.case, self.root)

    def test_role_neutral_rejections_preserve_full_entity_witness(self) -> None:
        presentation_oracles = json.loads(
            (SKILL_ROOT / "evals/presentation_oracles.json").read_text(
                encoding="utf-8"
            )
        )
        helper_path = self.root / "scripts/presentation_contract.py"
        spec = importlib.util.spec_from_file_location(
            "_bss_historical_presentation_contract",
            helper_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)

        def normalized(value: str) -> str:
            return " ".join(re.findall(r"[^\W_]+", value.casefold()))

        for witness in presentation_oracles["negative_entity_witnesses"]:
            with self.subTest(statement=witness["statement"]):
                violations = helper.find_role_neutral_violations(
                    f"{witness['statement']}\n\n## Security map",
                    "## Security map",
                )
                expected = normalized(witness["entity"])
                self.assertTrue(
                    any(expected in normalized(value) for value in violations),
                    msg=(
                        f"full entity witness missing: {witness['entity']!r}; "
                        f"violations={violations!r}"
                    ),
                )

    def test_security_map_order_swap_fails(self) -> None:
        path = self.case / "memo.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("## 4. Constraint proof", "## __SWAP__", 1)
        text = text.replace("## 5. Security map", "## 4. Constraint proof", 1)
        text = text.replace("## __SWAP__", "## 5. Security map", 1)
        path.write_text(text, encoding="utf-8")
        self.assert_invalid("section headings or order changed")

    def test_missing_source_url_fails(self) -> None:
        self.mutate(
            "evidence.json",
            lambda payload: payload["claims"][0]["sources"][0].pop("url"),
        )
        self.assert_invalid("url is required|valid HTTPS URL")

    def test_unknown_dependency_fails(self) -> None:
        self.mutate(
            "evidence.json",
            lambda payload: payload["claims"][8].__setitem__(
                "depends_on", ["C-999"]
            ),
        )
        self.assert_invalid("unknown dependency")

    def test_forward_dependency_fails(self) -> None:
        self.mutate(
            "evidence.json",
            lambda payload: payload["claims"][8].__setitem__(
                "depends_on", ["C-014"]
            ),
        )
        self.assert_invalid("must precede inference")

    def test_fcf_arithmetic_tamper_fails(self) -> None:
        self.mutate(
            "decision.json",
            lambda payload: payload["rent_capture"]["sensitivity_only"]["base"].__setitem__(
                "incremental_fcf_millions", 999
            ),
        )
        self.assert_invalid("base incremental FCF arithmetic changed")


if __name__ == "__main__":
    unittest.main()
