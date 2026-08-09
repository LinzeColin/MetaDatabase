"""Targeted frozen acceptance tests for ABD S16/P02 model evaluation."""

from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.model_eval import (
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from abd_acceptance.model_eval_engine import (
    CLAIM_BOUNDARY,
    EVAL_CATALOG_PATH,
    EVAL_REPORT_PATH,
    FIXTURE_PATH,
    LOWER_BOUND_METRICS,
    ModelEvalInputError,
    build_artifacts,
    load_fixture,
    strict_json_load,
    validate_artifacts,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
RAW_FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
CATALOG = strict_json_load(ROOT / EVAL_CATALOG_PATH)
REPORT = strict_json_load(ROOT / EVAL_REPORT_PATH)


def _mutated_fixture(kind: str) -> dict[str, object]:
    fixture = deepcopy(RAW_FIXTURE)
    templates = fixture["block_templates"]
    assert isinstance(templates, list)
    if kind == "market_equals_candidate":
        for row in templates:
            row["market_probability"] = row["candidate_probability"]
    elif kind == "negative_closing_line":
        for row in templates:
            row["closing_odds"] = str(float(str(row["recommended_odds"])) + 0.10)
    elif kind == "negative_log_growth":
        for row in templates:
            row["friction_log_penalty"] = "0.01000"
    elif kind == "intercept_outside_gate":
        for row in templates:
            row["candidate_probability"] = str(float(str(row["candidate_probability"])) - 0.10)
    else:
        raise AssertionError(kind)
    return fixture


def test_candidate_preflight_replays_the_exact_frozen_s16_p02_contract() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["decision"] == RAW_FIXTURE["expected_decision"]
    assert result["next"] == RAW_FIXTURE["expected_next"]


def test_artifacts_replay_byte_for_value_from_the_frozen_fixture() -> None:
    fixture = load_fixture(ROOT)
    expected = build_artifacts(ROOT, fixture)
    assert validate_artifacts(ROOT, fixture) == expected
    assert expected[EVAL_CATALOG_PATH.as_posix()] == CATALOG
    assert expected[EVAL_REPORT_PATH.as_posix()] == REPORT


def test_artifact_identity_and_source_contracts_are_exact() -> None:
    assert CATALOG["artifact_id"] == "ART-S16-P02-02"
    assert CATALOG["source_artifact_id"] == "ART-S16-P02-01"
    assert REPORT["artifact_id"] == "ART-S16-P02-03"
    assert CATALOG["formula_contract"]["ticket_log_growth"] == "g=p_L*ln(1+f*(odds-1))+(1-p_L)*ln(1-f)"
    assert set(CATALOG["source_hashes"]) == {
        "metrics.json",
        "machine/facts/strategy_spec.json",
        "machine/evidence/EVD-S16-P01.json",
        "model_registry.json",
        "baseline_report.json",
        "challenger_report.json",
    }


@pytest.mark.parametrize("metric_name", LOWER_BOUND_METRICS)
def test_every_95_percent_lower_confidence_bound_is_positive(metric_name: str) -> None:
    gate = REPORT["lower_confidence_bound_gates"][metric_name]
    assert gate["threshold"] == ">0"
    assert gate["passed"] is True
    assert float(gate["value"]) > 0.0


@pytest.mark.parametrize(
    "metric_name,threshold",
    [
        ("calibration_slope", "[0.90,1.10]"),
        ("calibration_intercept_absolute", "<=0.02"),
        ("calibration_error_main_market", "<=0.025"),
        ("calibration_error_niche_market", "<=0.04"),
    ],
)
def test_every_calibration_gate_is_strictly_bound_to_the_frozen_threshold(metric_name: str, threshold: str) -> None:
    gate = REPORT["calibration_gates"][metric_name]
    assert gate["threshold"] == threshold
    assert gate["passed"] is True


def test_synthetic_scope_has_eight_folds_and_exactly_two_thousand_observations() -> None:
    scope = REPORT["evaluation_scope"]
    assert scope == {
        "classification": "FROZEN_SYNTHETIC_EVALUATION_NOT_EMPIRICAL",
        "temporal_fold_count": 8,
        "synthetic_observation_count": 2000,
        "real_market_or_execution_observation_count": 0,
        "confidence_level": "0.95",
        "lower_tail_quantile": "0.05",
        "bootstrap_iterations": 2000,
    }


def test_p01_market_champion_and_all_challenger_weights_remain_unchanged() -> None:
    promotion = REPORT["model_promotion"]
    assert promotion["model_id"] == "GENERIC_RESIDUAL_CHALLENGER"
    assert promotion["weight_before"] == promotion["weight_after"] == "0.00"
    assert promotion["weight_change_allowed"] is False
    assert promotion["activation_status"] == "NOT_ACTIVATED_PENDING_S16_P03_AND_S16_P04"


@pytest.mark.parametrize(
    "kind",
    ("market_equals_candidate", "negative_closing_line", "negative_log_growth", "intercept_outside_gate"),
)
def test_metric_gate_failures_are_reported_without_relaxing_the_contract(kind: str) -> None:
    artifacts = build_artifacts(ROOT, _mutated_fixture(kind))
    mutated_report = artifacts[EVAL_REPORT_PATH.as_posix()]
    assert mutated_report["gate_summary"]["all_s16_p02_gates_pass"] is False
    assert mutated_report["model_promotion"]["weight_after"] == "0.00"
    assert mutated_report["model_promotion"]["weight_change_allowed"] is False


@pytest.mark.parametrize("kind", ("bad_iteration_count", "empirical_classification", "bad_p01_hash", "bad_outcome_delta"))
def test_contract_boundary_mutations_fail_closed(kind: str) -> None:
    fixture = deepcopy(RAW_FIXTURE)
    if kind == "bad_iteration_count":
        fixture["evaluation_protocol"]["bootstrap_iterations"] = 1999
    elif kind == "empirical_classification":
        fixture["evaluation_blocks"][0]["classification"] = "EMPIRICAL_LIVE_MARKET"
    elif kind == "bad_p01_hash":
        fixture["p01_evidence"]["evidence_sha256"] = "0" * 64
    elif kind == "bad_outcome_delta":
        fixture["evaluation_blocks"][0]["outcome_success_deltas"][0] = 2
    else:
        raise AssertionError(kind)
    with pytest.raises(ModelEvalInputError):
        validate_fixture(ROOT, fixture)


def test_taskpack_contract_and_evidence_index_are_checked_by_the_independent_oracle() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["summary"]["checks"] >= 26
    assert result["summary"]["failed"] == 0


def test_core_and_oracle_have_no_network_process_sleep_or_order_capability() -> None:
    paths = ("model_eval.py", "abd_acceptance/model_eval_engine.py", "abd_acceptance/model_eval.py")
    imports: set[str] = set()
    source = ""
    for path in paths:
        content = (ROOT / path).read_text(encoding="utf-8")
        source += content
        for node in ast.walk(ast.parse(content)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"})
    for token in ("slee" "p(", "submit" "_order", "retry" "_order", "http" "://", "https" "://"):
        assert token not in source


def test_rollback_is_local_only_and_preserves_the_p01_safe_surface() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["mode"] == "DISABLE_S16_P02_EVALUATION_KEEP_S16_P01_CHAMPION_AND_ZERO_WEIGHT_CHALLENGERS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["model_weight_changed"] is False
    assert rollback["order_submission_enabled"] is False


def test_execution_policy_excludes_full_regression_real_time_soak_and_external_runtime() -> None:
    assert EXECUTION_POLICY["phase_test_only"] is True
    assert EXECUTION_POLICY["full_regression_or_real_time_soak_allowed"] is False
    assert EXECUTION_POLICY["external_runtime_access_allowed"] is False
    assert EXECUTION_POLICY["bootstrap_iterations"] == 2000


def test_claim_boundary_never_converts_a_synthetic_fixture_to_empirical_or_financial_evidence() -> None:
    assert CATALOG["claim_boundary"] == CLAIM_BOUNDARY
    assert REPORT["claim_boundary"] == CLAIM_BOUNDARY
    assert REPORT["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert EXTERNAL_EFFECT_BOUNDARY["model_weight_changed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["financial_return_verified_or_guaranteed"] is False
