from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.ga_reconciliation import (
    EXTERNAL_EFFECT_BOUNDARY,
    SAFE_GA_CONFIG,
    GAReconciliationInputError,
    build_actual_reconciliation,
    build_ga_report,
    evaluate_ga_reconciliation,
)
from abd_acceptance.ga_reconciliation_acceptance import (
    ACTUAL_RECONCILIATION_PATH,
    CONTRACT_ID,
    CORE_PATH,
    EVIDENCE_PATH,
    FIXTURE_PATH,
    GA_REPORT_PATH,
    GAReconciliationAcceptanceError,
    build_evidence,
    evaluate_contract,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
    verify_existing_phase_evidence,
)
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def test_fixture_is_exact_s19_p03_contract() -> None:
    assert validate_fixture(FIXTURE) == FIXTURE
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S19/P04_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S19_P03.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_scenario_has_its_pinned_no_recommendation_result(scenario: dict) -> None:
    result = evaluate_ga_reconciliation(scenario["ga_input"])
    assert {key: result[key] for key in scenario["expected"]} == scenario["expected"]
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["model_gate"]["production_equivalent_config_schema"] == SAFE_GA_CONFIG
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["model_gate"]["recommendation_generation_allowed"] is False
    assert result["model_gate"]["order_submission_allowed"] is False


def test_golden_zero_row_control_passes_locally_but_actual_ga_remains_blocked() -> None:
    result = evaluate_ga_reconciliation(_scenario("GOLDEN_ZERO_ROW_CONTROL_GA_BLOCKED")["ga_input"])
    assert result["status"] == "PASS_LOCAL_GA_RECONCILIATION_CONTROL"
    assert result["local_control"]["local_reconciliation_difference_cents"] == 0
    assert result["actual_execution_observation"]["actual_record_count"] == 0
    assert result["actual_execution_observation"]["actual_reconciliation_difference_cents"] is None
    assert result["actual_execution_observation"]["actual_reconciliation_status"] == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
    assert result["ga_status"] == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
    assert result["required_before_actual_ga"]["actual_record_count"] == 200
    assert result["required_before_actual_ga"]["verified_days"] == 90


def test_one_in_ten_thousand_adverse_vector_remains_stable_and_no_recommendation() -> None:
    result = evaluate_ga_reconciliation(_scenario("ADVERSE_ONE_IN_TEN_THOUSAND_ZERO_ROW_CONTROL_STABLE")["ga_input"])
    assert result["status"] == "PASS_LOCAL_GA_RECONCILIATION_CONTROL"
    assert result["local_control"]["adverse_probability_delta"] == "-0.0001"
    assert result["local_control"]["adverse_odds_tick_delta"] == -1
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["ga_status"] == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"


def test_nonzero_difference_empirical_claim_stop_and_unsafe_requests_fail_closed() -> None:
    nonzero = evaluate_ga_reconciliation(_scenario("NONZERO_LOCAL_DIFFERENCE_FAILS_CLOSED")["ga_input"])
    empirical = evaluate_ga_reconciliation(_scenario("EMPIRICAL_EXECUTION_CLAIM_FAILS_CLOSED")["ga_input"])
    stopped = evaluate_ga_reconciliation(_scenario("STOP_CONDITION_FAILS_CLOSED")["ga_input"])
    unsafe = evaluate_ga_reconciliation(_scenario("UNSAFE_RUNTIME_REQUESTS_FAIL_CLOSED")["ga_input"])
    assert nonzero["failure_codes"] == ["LOCAL_RECONCILIATION_DIFFERENCE_NONZERO"]
    assert empirical["failure_codes"] == ["EMPIRICAL_EXECUTION_CLAIM_NOT_VERIFIABLE_IN_FROZEN_LOCAL_EVALUATOR"]
    assert stopped["failure_codes"] == ["STOP_CONDITION_TRIGGERED"]
    assert unsafe["failure_codes"] == [
        "EXTERNAL_RUNTIME_REQUESTED",
        "ACTUAL_ORDER_REQUESTED",
        "REAL_FUND_MUTATION_REQUESTED",
        "REAL_MAIL_SEND_REQUESTED",
        "PRODUCTION_DEPLOY_REQUESTED",
    ]
    assert all(result["action"] == "NO_RECOMMENDATION" for result in (nonzero, empirical, stopped, unsafe))


@pytest.mark.parametrize("mutation", FIXTURE["malformed_inputs"], ids=lambda item: item["case_id"])
def test_malformed_or_relaxed_inputs_are_rejected(mutation: dict) -> None:
    payload = deepcopy(_scenario("GOLDEN_ZERO_ROW_CONTROL_GA_BLOCKED")["ga_input"])
    if mutation["mutation"] == "float_local_difference":
        payload["local_reconciliation_control"]["local_reconciliation_difference_cents"] = 0.0
    elif mutation["mutation"] == "unknown_evidence_mode":
        payload["evidence_mode"] = "UNKNOWN"
    elif mutation["mutation"] == "relaxed_ga_config":
        payload["model_gate"]["production_equivalent_config_schema"]["target_shortfall_may_relax_gate"] = True
    else:
        raise AssertionError("unknown frozen mutation")
    with pytest.raises(GAReconciliationInputError):
        evaluate_ga_reconciliation(payload)


def test_artifacts_are_deterministic_and_do_not_claim_actual_reconciliation() -> None:
    evaluation = evaluate_ga_reconciliation(_scenario("GOLDEN_ZERO_ROW_CONTROL_GA_BLOCKED")["ga_input"])
    report = build_ga_report(
        evaluation,
        fixture_sha256=sha256_file(ROOT / FIXTURE_PATH),
        predecessor_evidence_sha256=FIXTURE["predecessor_evidence_sha256"],
        source_evidence_sha256=FIXTURE["source_evidence_sha256"],
    )
    reconciliation = build_actual_reconciliation(report)
    assert report["artifact_id"] == "ART-S19-P03-01"
    assert report["status"] == "PASS_LOCAL_GA_RECONCILIATION_CONTROL_ACTUAL_GA_BLOCKED"
    assert report["ga_status"] == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
    assert reconciliation["artifact_id"] == "ART-S19-P03-02"
    assert reconciliation["status"] == "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE"
    assert reconciliation["actual_reconciliation_difference_cents"] is None
    assert reconciliation["local_zero_row_reconciliation_difference_cents"] == 0
    assert reconciliation["ga_activation_allowed"] is False
    assert reconciliation["recommendation_generation_allowed"] is False
    assert reconciliation["order_submission_allowed"] is False


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


def test_candidate_preflight_passes_but_marks_actual_ga_as_blocked() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == CONTRACT_ID
    assert result["next"] == "S19/P04_READY_NOT_STARTED"
    assert result["actual_ga_status"] == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
    assert result["execution_policy"]["full_regression_or_real_time_soak_allowed"] is False
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_generated_artifact_paths_are_stable_before_and_after_signing() -> None:
    assert GA_REPORT_PATH.as_posix() == "ga_report.json"
    assert ACTUAL_RECONCILIATION_PATH.as_posix() == "actual_reconciliation.json"


def test_evidence_build_is_deterministic_before_signing() -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False, require_generated_artifacts=False)
    assert evidence["decision"] == "S19_P03_LOCAL_GA_RECONCILIATION_CONTROL_PASS_P04_REQUIRED_ACTUAL_GA_BLOCKED"
    assert evidence["actual_ga_status"] == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S19-P02.json"


def test_cli_and_legacy_successor_chain_are_exact() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S19-P03": verify_ga_reconciliation_phase_evidence,' in source
    assert '"AC-S19-P03": write_ga_reconciliation_phase_evidence,' in source
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / "abd_acceptance/__main__.py")


def test_rollback_drill_is_local_and_preserves_s19_p02_receipt() -> None:
    rollback = perform_rollback_drill(ROOT)
    expected = "PASS" if all((ROOT / path).is_file() for path in (GA_REPORT_PATH, ACTUAL_RECONCILIATION_PATH)) else "FAIL"
    assert rollback["status"] == expected
    assert rollback["feature_flag_id"] == "model:s19_p03_ga_reconciliation_control_local_only"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S19-P02.json"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["actual_ga_activation_enabled"] is False
    assert rollback["real_time_soak_waited"] is False


def test_existing_evidence_verifier_fails_closed_when_no_signed_evidence_exists() -> None:
    with pytest.raises((GAReconciliationAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")


def test_oracle_reports_all_local_preflight_checks_before_signing() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False, require_generated_artifacts=False)
    assert result["status"] == "PASS", result
    assert all(item["passed"] for item in result["checks"])
