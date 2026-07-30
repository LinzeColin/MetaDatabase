"""Frozen acceptance-facing tests for ABD S08/P03 weighted median consensus."""

from __future__ import annotations

import ast
from decimal import Decimal
import json
from pathlib import Path

import pytest

from abd_acceptance.market_consensus import build_evidence, evaluate_contract
from market_consensus import (
    MarketConsensusError,
    build_report,
    calculate_consensus,
    inverse_logit,
    weighted_median_logit,
)
from source_independence import cluster_sources


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "machine/tests/fixtures/S08_P03.json"
REPORT_PATH = ROOT / "consensus_vectors.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _case(identifier: str) -> dict:
    for candidate in _fixture()["cases"]:
        if candidate["id"] == identifier:
            return candidate
    raise AssertionError("fixture case missing: %s" % identifier)


def test_report_replays_exactly() -> None:
    assert json.loads(REPORT_PATH.read_text(encoding="utf-8")) == build_report(_fixture())


@pytest.mark.parametrize("identifier", [
    "BASELINE_THREE_INDEPENDENT",
    "COPIED_SOURCE_INVARIANCE",
    "SHARED_SUPPLY_CHAIN_INVARIANCE",
    "FRESHNESS_BOUNDARY_COPY",
])
def test_frozen_cases_match_expected_consensus(identifier: str) -> None:
    case = _case(identifier)
    result = calculate_consensus(case)
    assert result["consensus_probability"] == case["expected"]["consensus_probability"]
    assert result["eligible_independent_cluster_count"] == case["expected"]["eligible_independent_cluster_count"]
    assert result["effective_independent_weight"] == case["expected"]["effective_independent_weight"]
    assert result["consensus_space"] == "LOGIT"
    assert result["consensus_estimator"] == "SOURCE_INDEPENDENCE_WEIGHTED_MEDIAN"


@pytest.mark.parametrize("baseline_id,copy_id", [
    ("BASELINE_THREE_INDEPENDENT", "COPIED_SOURCE_INVARIANCE"),
    ("BASELINE_THREE_INDEPENDENT", "SHARED_SUPPLY_CHAIN_INVARIANCE"),
])
def test_copies_and_shared_supply_chain_do_not_change_consensus(baseline_id: str, copy_id: str) -> None:
    baseline = calculate_consensus(_case(baseline_id))
    copy_variant = calculate_consensus(_case(copy_id))
    assert copy_variant["consensus_probability"] == baseline["consensus_probability"]
    assert copy_variant["weighted_median_logit"] == baseline["weighted_median_logit"]
    assert copy_variant["effective_independent_weight"] == baseline["effective_independent_weight"]


@pytest.mark.parametrize("identifier", [
    "BASELINE_THREE_INDEPENDENT",
    "COPIED_SOURCE_INVARIANCE",
    "SHARED_SUPPLY_CHAIN_INVARIANCE",
    "FRESHNESS_BOUNDARY_COPY",
])
def test_logit_round_trip_stays_within_independent_tolerance(identifier: str) -> None:
    result = calculate_consensus(_case(identifier))
    restored = inverse_logit(Decimal(result["weighted_median_logit"]))
    assert abs(restored - Decimal(result["consensus_probability"])) <= Decimal("0.000000000001")


@pytest.mark.parametrize("invalid_index", [0, 1, 2, 3])
def test_invalid_consensus_inputs_fail_closed(invalid_index: int) -> None:
    with pytest.raises(MarketConsensusError):
        calculate_consensus(_fixture()["invalid_cases"][invalid_index])


def test_weighted_median_uses_lower_logit_at_exact_half_weight() -> None:
    assert weighted_median_logit([
        {"logit": Decimal("-1"), "weight": Decimal("1"), "tie_key": "A"},
        {"logit": Decimal("1"), "weight": Decimal("1"), "tie_key": "B"},
    ]) == Decimal("-1")


def test_copy_cluster_weight_is_one_not_two() -> None:
    clusters = cluster_sources(_case("COPIED_SOURCE_INVARIANCE"))
    copied_cluster = next(cluster for cluster in clusters["clusters"] if cluster["eligible_member_count"] == 2)
    assert copied_cluster["independent_weight"] == "1"
    assert sum(Decimal(member["weight"]) for member in copied_cluster["members"]) == Decimal("1")


def test_freshness_boundary_is_inclusive_and_still_deduplicated() -> None:
    result = calculate_consensus(_case("FRESHNESS_BOUNDARY_COPY"))
    assert result["consensus_probability"] == "0.6"
    assert result["eligible_independent_cluster_count"] == 3


def test_one_hundred_replays_are_identical() -> None:
    fixture = _fixture()
    expected = build_report(fixture)
    assert all(build_report(fixture) == expected for _ in range(fixture["replay_count"]))


def test_ten_thousand_adverse_probability_perturbations_do_not_change_middle_consensus() -> None:
    base = _case("COPIED_SOURCE_INVARIANCE")
    for iteration in range(10_000):
        case = json.loads(json.dumps(base))
        low = "0.3999" if iteration % 2 == 0 else "0.4001"
        high = "0.6999" if iteration % 2 == 0 else "0.7001"
        for source in case["sources"]:
            if source["source_id"].startswith("SRC_ALPHA"):
                source["probability"] = low
            if source["source_id"] == "SRC_GAMMA_DIRECT":
                source["probability"] = high
        assert calculate_consensus(case)["consensus_probability"] == "0.55"


def test_wrong_input_mode_fails_closed() -> None:
    fixture = _fixture()
    fixture["input_mode"] = "LIVE"
    with pytest.raises(MarketConsensusError):
        build_report(fixture)


def test_core_has_no_network_process_or_soak_surface() -> None:
    source = (ROOT / "market_consensus.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.append(node.func.attr)
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"})
    assert not set(calls).intersection({"sleep", "run", "Popen"})


def test_core_contains_no_binary_float_literal() -> None:
    source = (ROOT / "market_consensus.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "float(" not in source
    assert not [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]


def test_preflight_acceptance_passes_before_evidence_write() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["status"] == "PASS", result["summary"]
    assert result["summary"]["checks"] >= _fixture()["expected_oracle_check_minimum"]


def test_preflight_evidence_is_json_serializable() -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False)
    assert evidence["status"] == "PASS"
    assert rollback["status"] == "PASS"
    json.dumps(evidence, ensure_ascii=False, sort_keys=True)


def test_report_has_no_advice_or_order_boundary_breach() -> None:
    boundary = json.loads(REPORT_PATH.read_text(encoding="utf-8"))["external_effect_boundary"]
    assert boundary == {
        "external_network_accessed": False,
        "real_market_or_odds_observed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
