"""Frozen acceptance-facing tests for ABD S08/P04 quote-integrity gates."""

from __future__ import annotations

import ast
from decimal import Decimal
import json
from pathlib import Path

import pytest

from abd_acceptance.outlier_line_movement import build_evidence, evaluate_contract
from outlier_detector import (
    OutlierDetectorError,
    build_report,
    detect_outliers,
    evaluate_market_integrity,
    lower_median,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "machine/tests/fixtures/S08_P04.json"
ARTIFACT_PATH = ROOT / "outlier_fixtures.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _case(identifier: str) -> dict:
    for candidate in _fixture()["cases"]:
        if candidate["id"] == identifier:
            return candidate
    raise AssertionError("fixture case missing: %s" % identifier)


def test_artifact_replays_exactly() -> None:
    assert json.loads(ARTIFACT_PATH.read_text(encoding="utf-8")) == build_report(_fixture())


@pytest.mark.parametrize("identifier", [
    "SINGLE_LONG_ODDS_OUTLIER",
    "CONFIRMED_LINE_MOVEMENT_FRESH",
    "UNCONFIRMED_LINE_MOVEMENT",
    "STALE_QUOTE",
    "TIME_DESYNCHRONIZED_QUOTES",
    "MAD_BOUNDARY_NOT_OUTLIER",
])
def test_frozen_cases_match_expected_gate(identifier: str) -> None:
    case = _case(identifier)
    result = evaluate_market_integrity(case)
    expected = case["expected"]
    assert result["gate"] == expected["gate"]
    assert result["outlier_detection"]["outlier_source_ids"] == expected["outlier_source_ids"]
    assert result["outlier_detection"]["long_outlier_source_ids"] == expected["long_outlier_source_ids"]
    assert result["line_movement"]["status"] == expected["line_status"]
    assert result["downstream_market_prior_allowed"] is expected["downstream_market_prior_allowed"]
    assert result["recommendation_generated"] is False
    assert result["recommendation_permitted"] is False


def test_single_abnormal_long_odds_cannot_create_recommendation() -> None:
    result = evaluate_market_integrity(_case("SINGLE_LONG_ODDS_OUTLIER"))
    assert result["gate"] == "BLOCK_NO_RECOMMENDATION"
    assert result["block_reasons"] == ["LONG_ODDS_OUTLIER"]
    assert result["outlier_detection"]["long_outlier_source_ids"] == ["SRC_LONG"]
    assert result["recommendation_generated"] is False


def test_exact_3_point_5_mad_boundary_is_not_an_outlier() -> None:
    result = evaluate_market_integrity(_case("MAD_BOUNDARY_NOT_OUTLIER"))
    detector = result["outlier_detection"]
    assert detector["median_absolute_deviation"] == "0.1"
    assert detector["outlier_threshold"] == "0.35"
    assert detector["outlier_source_ids"] == []
    assert result["gate"] == "ALLOW_DOWNSTREAM_MARKET_PRIOR"


def test_one_tick_past_boundary_becomes_outlier() -> None:
    detection = detect_outliers([
        {"source_id": "SRC_ALPHA", "odds": "2.00"},
        {"source_id": "SRC_BETA", "odds": "2.10"},
        {"source_id": "SRC_GAMMA", "odds": "2.20"},
        {"source_id": "SRC_BEYOND", "odds": "2.4501"},
    ], mad_multiplier=Decimal("3.5"))
    assert detection["outlier_source_ids"] == ["SRC_BEYOND"]
    assert detection["long_outlier_source_ids"] == ["SRC_BEYOND"]


def test_confirmed_line_movement_requires_two_independent_sources() -> None:
    result = evaluate_market_integrity(_case("CONFIRMED_LINE_MOVEMENT_FRESH"))
    assert result["line_movement"]["status"] == "CONFIRMED_UP"
    assert result["line_movement"]["movement_confirmed"] is True
    assert result["gate"] == "ALLOW_DOWNSTREAM_MARKET_PRIOR"


def test_unconfirmed_line_movement_blocks_downstream_market_prior() -> None:
    result = evaluate_market_integrity(_case("UNCONFIRMED_LINE_MOVEMENT"))
    assert result["line_movement"]["status"] == "BLOCK_UNCONFIRMED_LINE_MOVEMENT"
    assert result["gate"] == "BLOCK_NO_RECOMMENDATION"


def test_stale_quote_blocks_even_without_price_outlier() -> None:
    result = evaluate_market_integrity(_case("STALE_QUOTE"))
    assert result["line_movement"]["status"] == "BLOCK_STALE_QUOTES"
    assert result["line_movement"]["stale_source_ids"] == ["SRC_BETA"]
    assert result["gate"] == "BLOCK_NO_RECOMMENDATION"


def test_exact_freshness_boundary_is_usable_when_synchronized() -> None:
    case = json.loads(json.dumps(_case("STALE_QUOTE")))
    for observation in case["line_observations"]:
        observation["previous_observed_at"] = "2026-07-29T23:58:20+10:00"
        observation["current_observed_at"] = "2026-07-29T23:58:30+10:00"
    result = evaluate_market_integrity(case)
    assert result["line_movement"]["status"] == "NO_LINE_MOVEMENT"
    assert result["line_movement"]["stale_source_ids"] == []
    assert result["gate"] == "ALLOW_DOWNSTREAM_MARKET_PRIOR"


def test_time_desynchronization_blocks_fresh_quotes() -> None:
    result = evaluate_market_integrity(_case("TIME_DESYNCHRONIZED_QUOTES"))
    assert result["line_movement"]["status"] == "BLOCK_TIME_DESYNCHRONIZED"
    assert result["line_movement"]["observed_time_skew_seconds"] == "3"
    assert result["gate"] == "BLOCK_NO_RECOMMENDATION"


@pytest.mark.parametrize("invalid_index", [0, 1, 2, 3, 4])
def test_invalid_cases_fail_closed(invalid_index: int) -> None:
    with pytest.raises(OutlierDetectorError):
        evaluate_market_integrity(_fixture()["invalid_cases"][invalid_index])


def test_lower_median_is_deterministic_for_even_vectors() -> None:
    assert lower_median([Decimal("2.00"), Decimal("2.10"), Decimal("2.20"), Decimal("12.00")]) == Decimal("2.10")


def test_one_hundred_replays_are_identical() -> None:
    fixture = _fixture()
    expected = build_report(fixture)
    assert all(build_report(fixture) == expected for _ in range(fixture["replay_count"]))


def test_ten_thousand_adverse_long_odds_perturbations_remain_blocked() -> None:
    base = _case("SINGLE_LONG_ODDS_OUTLIER")
    for iteration in range(10_000):
        case = json.loads(json.dumps(base))
        long_odds = "11.9999" if iteration % 2 == 0 else "12.0001"
        for quote in case["quotes"]:
            if quote["source_id"] == "SRC_LONG":
                quote["odds"] = long_odds
        for observation in case["line_observations"]:
            if observation["source_id"] == "SRC_LONG":
                observation["previous_odds"] = long_odds
                observation["current_odds"] = long_odds
        result = evaluate_market_integrity(case)
        assert result["gate"] == "BLOCK_NO_RECOMMENDATION"
        assert result["recommendation_generated"] is False


def test_wrong_input_mode_fails_closed() -> None:
    fixture = _fixture()
    fixture["input_mode"] = "LIVE"
    with pytest.raises(OutlierDetectorError):
        build_report(fixture)


def test_core_modules_have_no_network_process_or_soak_surface() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    for name in ("outlier_detector.py", "line_movement.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
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
        assert not imports.intersection(prohibited)
        assert not set(calls).intersection({"sleep", "run", "Popen"})


def test_core_modules_contain_no_binary_float_literal() -> None:
    for name in ("outlier_detector.py", "line_movement.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
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


def test_artifact_has_no_advice_order_or_external_boundary_breach() -> None:
    boundary = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))["external_effect_boundary"]
    assert boundary == {
        "external_network_accessed": False,
        "real_market_or_odds_observed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
