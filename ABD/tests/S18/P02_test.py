from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.diagnostic_bundle import (
    ALERT_DECISION,
    DiagnosticInputError,
    EXTERNAL_EFFECT_BOUNDARY,
    HEALTHY_DECISION,
    MALFORMED_ALERT_ID,
    SAFE_ACTION,
    evaluate_diagnostic_input,
    validate_documents,
)
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.observability_alerts import (
    ALERTS_PATH,
    CLI_PATH,
    CONTRACT_ID,
    DASHBOARDS_PATH,
    FEATURE_FLAG_ID,
    FIXTURE_PATH,
    ObservabilityAcceptanceError,
    RUNNER_PATH,
    build_evidence,
    evaluate_contract,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)
DASHBOARDS = json.loads((ROOT / DASHBOARDS_PATH).read_text(encoding="utf-8"))
ALERTS = json.loads((ROOT / ALERTS_PATH).read_text(encoding="utf-8"))


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def _result(identifier: str) -> dict:
    return evaluate_diagnostic_input(_scenario(identifier)["diagnostic_input"], DASHBOARDS, ALERTS)


def test_fixture_is_exact_s18_p02_contract() -> None:
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S18/P03_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S18_P02.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_vector_has_its_pinned_fail_closed_result(scenario: dict) -> None:
    result = evaluate_diagnostic_input(scenario["diagnostic_input"], DASHBOARDS, ALERTS)
    assert {key: result[key] for key in scenario["expected"]} == scenario["expected"]
    assert len(result["action_ids"]) == len(set(result["action_ids"]))
    assert len(result["action_ids"]) == len(result["triggered_alert_ids"])
    assert result["safe_action"] == SAFE_ACTION
    assert result["recommendation_generated_or_enabled"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_runtime_accessed"] is False
    assert result["production_state_changed"] is False


def test_all_high_priority_alerts_have_one_unique_configured_action() -> None:
    _, policy, alert_by_id = validate_documents(DASHBOARDS, ALERTS)
    assert tuple(alert_by_id) == (
        "HP-LIVE-ADVICE-FRESHNESS",
        "HP-SILENT-COVERAGE-GAP",
        "HP-MODEL-PSI-STOP",
        "HP-RESOURCE-ENVELOPE",
        "HP-EMAIL-VERIFICATION",
        "HP-EVIDENCE-INTEGRITY",
        MALFORMED_ALERT_ID,
    )
    action_ids = [alert_by_id[identifier]["action"]["action_id"] for identifier in alert_by_id]
    assert len(action_ids) == len(set(action_ids))
    assert {alert_by_id[identifier]["action"]["mode"] for identifier in alert_by_id} == {"AUTOMATIC_LOGICAL", "MANUAL_LOGICAL"}
    assert policy["safe_action"] == SAFE_ACTION


def test_live_advice_boundary_is_exactly_eight_seconds() -> None:
    golden = _result("GOLDEN_ALL_SIGNALS_HEALTHY")
    stale = _result("LIVE_ADVICE_FRESHNESS_EXCEEDED")
    assert golden["decision"] == HEALTHY_DECISION
    assert stale["decision"] == ALERT_DECISION
    assert stale["triggered_alert_ids"] == ["HP-LIVE-ADVICE-FRESHNESS"]


def test_population_stability_stop_boundary_and_one_in_ten_thousand_vectors_are_exact() -> None:
    below = _result("MODEL_PSI_MINUS_ONE_IN_TEN_THOUSAND_STABLE")
    exact = _result("MODEL_PSI_EXACT_STOP")
    above = _result("MODEL_PSI_PLUS_ONE_IN_TEN_THOUSAND_STOPS")
    assert below["decision"] == HEALTHY_DECISION
    assert exact["triggered_alert_ids"] == ["HP-MODEL-PSI-STOP"]
    assert above["triggered_alert_ids"] == ["HP-MODEL-PSI-STOP"]
    assert below["recommendation_generated_or_enabled"] is False
    assert below["order_submission_enabled"] is False


def test_multiple_alerts_preserve_one_action_per_alert() -> None:
    result = _result("MULTIPLE_HIGH_PRIORITY_ALERTS_REMAIN_UNIQUE")
    assert result["decision"] == ALERT_DECISION
    assert len(result["triggered_alert_ids"]) == 6
    assert len(result["action_ids"]) == 6
    assert len(set(result["action_ids"])) == 6


def test_malformed_probability_delta_and_float_payload_both_fail_closed() -> None:
    malformed = _result("MALFORMED_PROBABILITY_DELTA_FAILS_CLOSED")
    float_payload = deepcopy(_scenario("GOLDEN_ALL_SIGNALS_HEALTHY")["diagnostic_input"])
    float_payload["signal_snapshot"]["population_stability_index"] = 0.2
    float_result = evaluate_diagnostic_input(float_payload, DASHBOARDS, ALERTS)
    assert malformed["triggered_alert_ids"] == [MALFORMED_ALERT_ID]
    assert float_result["triggered_alert_ids"] == [MALFORMED_ALERT_ID]
    assert malformed["action_ids"] == float_result["action_ids"]


def test_unknown_signal_field_fails_closed_without_order_enablement() -> None:
    payload = deepcopy(_scenario("GOLDEN_ALL_SIGNALS_HEALTHY")["diagnostic_input"])
    payload["signal_snapshot"]["unexpected"] = "PASS"
    result = evaluate_diagnostic_input(payload, DASHBOARDS, ALERTS)
    assert result["triggered_alert_ids"] == [MALFORMED_ALERT_ID]
    assert result["order_submission_enabled"] is False


def test_duplicate_configured_action_is_rejected_before_evaluation() -> None:
    policy = deepcopy(ALERTS)
    policy["high_priority_alerts"][1]["action"]["action_id"] = policy["high_priority_alerts"][0]["action"]["action_id"]
    with pytest.raises(DiagnosticInputError):
        validate_documents(DASHBOARDS, policy)


def test_diagnostic_replay_hash_is_deterministic() -> None:
    payload = _scenario("MULTIPLE_HIGH_PRIORITY_ALERTS_REMAIN_UNIQUE")["diagnostic_input"]
    first = evaluate_diagnostic_input(payload, DASHBOARDS, ALERTS)
    second = evaluate_diagnostic_input(payload, DASHBOARDS, ALERTS)
    assert first == second
    assert first["diagnostic_bundle_sha256"] == second["diagnostic_bundle_sha256"]


def test_runner_has_no_runtime_network_or_process_dependencies() -> None:
    source = (ROOT / RUNNER_PATH).read_text(encoding="utf-8") + (ROOT / "abd_acceptance/diagnostic_bundle.py").read_text(encoding="utf-8")
    for forbidden in ("import socket", "import subprocess", "import requests", "http://", "https://"):
        assert forbidden not in source


def test_cli_has_exact_s18_p02_writer_and_verifier_mappings() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S18-P02": verify_observability_phase_evidence,' in source
    assert '"AC-S18-P02": write_observability_phase_evidence,' in source


def test_legacy_successor_chain_allows_only_the_current_dispatcher_hash() -> None:
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / CLI_PATH)


def test_candidate_preflight_covers_current_taskpack_and_signed_p01_dependency() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S18/P03_READY_NOT_STARTED"
    assert result["summary"]["failed"] == 0


def test_preflight_has_no_external_effects() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_evidence_build_is_deterministic_before_signing() -> None:
    first = build_evidence(ROOT, require_test_reports=False)
    second = build_evidence(ROOT, require_test_reports=False)
    assert first == second
    assert first[0]["decision"] == "S18_P02_OBSERVABILITY_CONTROL_PASS_P03_REQUIRED"


def test_fixture_rejects_wrong_predecessor_hash_and_reordered_scenarios() -> None:
    wrong = deepcopy(FIXTURE)
    wrong["predecessors"][0]["evidence_sha256"] = "0" * 64
    with pytest.raises(ObservabilityAcceptanceError):
        validate_fixture(wrong)
    reordered = deepcopy(FIXTURE)
    reordered["scenarios"] = list(reversed(reordered["scenarios"]))
    with pytest.raises(ObservabilityAcceptanceError):
        validate_fixture(reordered)


def test_rollback_drill_only_disables_local_observability_control() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["logical_fail_closed_actions_verified"] is True
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
