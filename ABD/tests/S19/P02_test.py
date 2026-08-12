from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.shadow_beta import (
    EXTERNAL_EFFECT_BOUNDARY,
    SAFE_MODEL_CONFIG,
    ShadowBetaInputError,
    build_model_beta_gate,
    build_shadow_report,
    evaluate_shadow_beta,
)
from abd_acceptance.shadow_beta_acceptance import (
    CONTRACT_ID,
    CORE_PATH,
    FIXTURE_PATH,
    MODEL_BETA_GATE_PATH,
    SHADOW_REPORT_PATH,
    ShadowBetaAcceptanceError,
    build_evidence,
    evaluate_contract,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
    verify_existing_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def test_fixture_is_exact_s19_p02_contract() -> None:
    assert validate_fixture(FIXTURE) == FIXTURE
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S19/P03_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S19_P02.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_scenario_has_its_pinned_no_order_result(scenario: dict) -> None:
    result = evaluate_shadow_beta(scenario["shadow_input"])
    assert {key: result[key] for key in scenario["expected"]} == scenario["expected"]
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["model_config_before"] == result["model_config_after"] == SAFE_MODEL_CONFIG
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["model_beta_eligible"] is False
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_golden_fixture_passes_all_five_local_quality_gates_but_not_model_beta() -> None:
    result = evaluate_shadow_beta(_scenario("GOLDEN_SYNTHETIC_ALL_METRICS_PASS_BETA_BLOCKED")["shadow_input"])
    assert result["status"] == "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT"
    assert [item["gate_id"] for item in result["quality_gates"]] == ["CALIBRATION", "NET_GROWTH", "FRESHNESS", "CAPACITY", "DRIFT"]
    assert all(item["passed"] for item in result["quality_gates"])
    assert result["synthetic_window"]["beta_thresholds_met_in_fixture_only"] is True
    assert result["synthetic_window"]["target_plausibility_thresholds_met_in_fixture_only"] is True
    assert result["empirical_observation"]["observed_realtime_shadow_days"] == 0
    assert result["empirical_observation"]["observed_realtime_qualified_signals"] == 0
    assert result["empirical_observation"]["synthetic_fixture_counts_may_substitute"] is False
    assert result["model_beta_status"] == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"


def test_one_in_ten_thousand_adverse_vector_remains_stable_and_no_order() -> None:
    result = evaluate_shadow_beta(_scenario("ADVERSE_ONE_IN_TEN_THOUSAND_METRICS_STABLE_BETA_BLOCKED")["shadow_input"])
    calibration = result["quality_gates"][0]
    assert calibration["adjusted_slope"] == "0.9000"
    assert calibration["passed"] is True
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["model_beta_eligible"] is False


def test_insufficient_synthetic_window_cannot_count_as_empirical_realtime_shadow() -> None:
    result = evaluate_shadow_beta(_scenario("INSUFFICIENT_SYNTHETIC_WINDOW_CANNOT_COUNT_AS_EMPIRICAL")["shadow_input"])
    assert result["synthetic_window"]["beta_thresholds_met_in_fixture_only"] is False
    assert result["empirical_observation"]["observed_realtime_shadow_days"] == 0
    assert result["empirical_observation"]["observed_realtime_qualified_signals"] == 0
    assert result["model_beta_status"] == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"


def test_hard_metric_boundaries_and_empirical_promotion_attempt_fail_closed() -> None:
    calibration = evaluate_shadow_beta(_scenario("CALIBRATION_BOUNDARY_FAILS_CLOSED")["shadow_input"])
    net_growth = evaluate_shadow_beta(_scenario("NET_GROWTH_BOUNDARY_FAILS_CLOSED")["shadow_input"])
    other = evaluate_shadow_beta(_scenario("FRESHNESS_CAPACITY_DRIFT_FAILURES_CLOSE_GATE")["shadow_input"])
    promotion = evaluate_shadow_beta(_scenario("EMPIRICAL_PROMOTION_ATTEMPT_FAILS_CLOSED")["shadow_input"])
    assert calibration["failure_codes"] == ["CALIBRATION_GATE_FAILED"]
    assert net_growth["failure_codes"] == ["NET_GROWTH_GATE_FAILED"]
    assert other["failure_codes"] == ["FRESHNESS_GATE_FAILED", "CAPACITY_GATE_FAILED", "DRIFT_GATE_FAILED"]
    assert promotion["failure_codes"] == ["EMPIRICAL_EVIDENCE_NOT_VERIFIABLE_IN_FROZEN_LOCAL_EVALUATOR"]
    assert promotion["model_beta_status"] == "BLOCKED_EMPIRICAL_EVIDENCE_NOT_VERIFIABLE_IN_LOCAL_FIXTURE"


@pytest.mark.parametrize("mutation", FIXTURE["malformed_inputs"], ids=lambda item: item["case_id"])
def test_malformed_or_relaxed_inputs_are_rejected(mutation: dict) -> None:
    payload = deepcopy(_scenario("GOLDEN_SYNTHETIC_ALL_METRICS_PASS_BETA_BLOCKED")["shadow_input"])
    if mutation["mutation"] == "float_metric":
        payload["metric_snapshot"]["calibration_slope"] = 1.0
    elif mutation["mutation"] == "unknown_evidence_kind":
        payload["evidence_kind"] = "UNKNOWN"
    elif mutation["mutation"] == "relaxed_model_config":
        payload["model_config"]["target_shortfall_may_relax_gate"] = True
    else:
        raise AssertionError("unknown frozen mutation")
    with pytest.raises(ShadowBetaInputError):
        evaluate_shadow_beta(payload)


def test_artifacts_are_deterministic_and_keep_beta_blocked() -> None:
    evaluation = evaluate_shadow_beta(_scenario("GOLDEN_SYNTHETIC_ALL_METRICS_PASS_BETA_BLOCKED")["shadow_input"])
    report = build_shadow_report(
        evaluation,
        fixture_sha256=sha256_file(ROOT / FIXTURE_PATH),
        predecessor_evidence_sha256=FIXTURE["predecessor_evidence_sha256"],
        source_evidence_sha256=FIXTURE["source_evidence_sha256"],
    )
    beta = build_model_beta_gate(report)
    assert report["artifact_id"] == "ART-S19-P02-01"
    assert report["empirical_observation"]["evidence_status"] == "NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
    assert beta["artifact_id"] == "ART-S19-P02-02"
    assert beta["status"] == "PASS_LOCAL_CONTRACT_MODEL_BETA_BLOCKED"
    assert beta["model_beta_status"] == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
    assert beta["model_activation_allowed"] is False
    assert beta["recommendation_generation_allowed"] is False
    assert beta["order_submission_allowed"] is False


def test_core_has_no_runtime_network_process_mail_or_sleep_capability() -> None:
    source = (ROOT / CORE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "smtplib", "time", "asyncio", "os", "random"})
    for forbidden in ("sleep(", "submit_order", "retry_order", "http://", "https://", "smtplib"):
        assert forbidden not in source


def test_candidate_preflight_is_passed_without_generated_reports_or_external_effects() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == CONTRACT_ID
    assert result["next"] == "S19/P03_READY_NOT_STARTED"
    assert result["model_beta_status"] == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
    assert result["execution_policy"]["full_regression_or_real_time_soak_allowed"] is False
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_generated_artifact_paths_are_stable_before_and_after_signing() -> None:
    assert SHADOW_REPORT_PATH.as_posix() == "shadow_report.json"
    assert MODEL_BETA_GATE_PATH.as_posix() == "model_beta_gate.json"


def test_evidence_build_is_deterministic_before_signing() -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False, require_generated_artifacts=False)
    assert evidence["decision"] == "S19_P02_SHADOW_BETA_CONTROL_PASS_P03_REQUIRED_NOT_MODEL_BETA"
    assert evidence["model_beta_status"] == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S19-P01.json"


def test_cli_and_legacy_successor_chain_are_exact() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S19-P02": verify_shadow_beta_phase_evidence,' in source
    assert '"AC-S19-P02": write_shadow_beta_phase_evidence,' in source
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / "abd_acceptance/__main__.py")


def test_rollback_drill_is_local_and_preserves_s19_p01_receipt() -> None:
    rollback = perform_rollback_drill(ROOT)
    expected = "PASS" if all((ROOT / path).is_file() for path in (SHADOW_REPORT_PATH, MODEL_BETA_GATE_PATH)) else "FAIL"
    assert rollback["status"] == expected
    assert rollback["feature_flag_id"] == "model:s19_p02_shadow_beta_local_only"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S19-P01.json"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_existing_evidence_verifier_fails_closed_when_no_signed_evidence_exists() -> None:
    with pytest.raises((ShadowBetaAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
