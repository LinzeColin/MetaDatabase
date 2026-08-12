from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.limited_self_heal import (
    APPROVED_DECISION,
    ESCALATION_DECISION,
    EXPECTED_OPERATIONS,
    EXTERNAL_EFFECT_BOUNDARY,
    HEALTHY_DECISION,
    SAFE_ACTION,
    SAFE_FUND_FACTS,
    SAFE_RISK_GATE,
    evaluate_outbox_projection,
    evaluate_watchdog_event,
    validate_policy,
)
from abd_acceptance.limited_self_heal_acceptance import (
    CLI_PATH,
    CONTRACT_ID,
    FEATURE_FLAG_ID,
    FIXTURE_PATH,
    LimitedSelfHealAcceptanceError,
    OUTBOX_PATH,
    POLICY_PATH,
    WATCHDOG_PATH,
    build_evidence,
    evaluate_contract,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)
POLICY = json.loads((ROOT / POLICY_PATH).read_text(encoding="utf-8"))


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def _plan(identifier: str) -> dict:
    return evaluate_watchdog_event(_scenario(identifier)["watchdog_input"], POLICY)


def _hashed_plan(value: dict) -> dict:
    unsigned = deepcopy(value)
    unsigned.pop("watchdog_plan_sha256", None)
    value["watchdog_plan_sha256"] = hashlib.sha256(
        (json.dumps(unsigned, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    return value


def test_fixture_is_exact_s18_p03_contract() -> None:
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S18/P04_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S18_P03.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_vector_has_its_pinned_immutable_result(scenario: dict) -> None:
    plan = evaluate_watchdog_event(scenario["watchdog_input"], POLICY)
    outbox = evaluate_outbox_projection(plan, POLICY)
    assert {key: plan[key] for key in scenario["expected"]} == scenario["expected"]
    assert plan["fund_facts_before"] == plan["fund_facts_after"] == SAFE_FUND_FACTS
    assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
    assert plan["fund_facts_changed"] is False
    assert plan["risk_gate_relaxed"] is False
    assert plan["shared_ledger_written"] is False
    assert plan["safe_action"] == SAFE_ACTION
    assert plan["recommendation_generated_or_enabled"] is False
    assert plan["order_submission_enabled"] is False
    assert plan["external_runtime_accessed"] is False
    assert plan["production_state_changed"] is False
    assert outbox["delivery_status"] == "LOCAL_OUTBOX_NOT_SENT"
    assert outbox["external_delivery_attempted"] is False
    assert outbox["external_network_accessed"] is False


def test_policy_has_exactly_the_seven_bounded_logical_operations() -> None:
    _, operations = validate_policy(POLICY)
    assert tuple((fault_id, operation["operation_id"]) for fault_id, operation in operations.items()) == EXPECTED_OPERATIONS
    assert all(operation["derived_state_only"] is True for operation in operations.values())
    assert all(operation["writes_shared_ledger"] is False for operation in operations.values())


def test_healthy_input_performs_no_self_heal_action() -> None:
    plan = _plan("HEALTHY_NO_FAULT_KEEP_GATES")
    assert plan["decision"] == HEALTHY_DECISION
    assert plan["operation_ids"] == []
    assert plan["operation_plan"] == []


def test_unsafe_fund_risk_and_float_inputs_fail_closed_without_changing_gates() -> None:
    fund = _plan("UNSAFE_FUND_MUTATION_REQUEST_ESCALATES")
    risk = _plan("RISK_GATE_RELAXATION_ATTEMPT_ESCALATES")
    floating = deepcopy(_scenario("HEALTHY_NO_FAULT_KEEP_GATES")["watchdog_input"])
    floating["probability_delta"] = 0.0
    float_plan = evaluate_watchdog_event(floating, POLICY)
    for plan in (fund, risk, float_plan):
        assert plan["decision"] == ESCALATION_DECISION
        assert plan["operation_ids"] == ["LOGICAL_ESCALATE_OWNER_OUTBOX_ONLY"]
        assert plan["fund_facts_before"] == plan["fund_facts_after"] == SAFE_FUND_FACTS
        assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
        assert plan["risk_gate_relaxed"] is False
        assert plan["order_submission_enabled"] is False


def test_tampered_policy_cannot_leak_changed_fund_or_risk_values_into_fallback() -> None:
    unsafe = deepcopy(POLICY)
    unsafe["immutable_fund_facts"]["frozen_bankroll_reference_aud"] = "300.01"
    unsafe["immutable_risk_gate"]["target_shortfall_may_relax_gate"] = True
    plan = evaluate_watchdog_event(_scenario("CANDIDATE_PROCESS_UNHEALTHY_LOGICAL_RESTART_ONLY")["watchdog_input"], unsafe)
    assert plan["decision"] == ESCALATION_DECISION
    assert plan["fund_facts_before"] == plan["fund_facts_after"] == SAFE_FUND_FACTS
    assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE


def test_tampered_watchdog_operation_plan_only_creates_a_local_unsent_fallback() -> None:
    plan = _hashed_plan(deepcopy(_plan("MODEL_PSI_STOP_ROLLBACK_SIGNED_CANDIDATE_ONLY")))
    plan["operation_plan"][0]["writes_shared_ledger"] = True
    _hashed_plan(plan)
    outbox = evaluate_outbox_projection(plan, POLICY)
    assert outbox["delivery_status"] == "LOCAL_OUTBOX_FAIL_CLOSED_NOT_SENT"
    assert outbox["operation_ids"] == ["LOGICAL_ESCALATE_OWNER_OUTBOX_ONLY"]
    assert outbox["actual_fund_facts_changed"] is False
    assert outbox["risk_gate_relaxed"] is False
    assert outbox["order_submission_enabled"] is False


def test_adverse_one_in_ten_thousand_vector_keeps_the_risk_gate() -> None:
    plan = _plan("ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_PRESERVES_RISK_GATE")
    assert plan["decision"] == APPROVED_DECISION
    assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
    assert plan["risk_gate_relaxed"] is False


def test_watchdog_and_outbox_replays_are_deterministic() -> None:
    payload = _scenario("SILENT_COVERAGE_GAP_REPLAY_DERIVED_STATE_ONLY")["watchdog_input"]
    first = evaluate_watchdog_event(payload, POLICY)
    second = evaluate_watchdog_event(payload, POLICY)
    assert first == second
    assert first["watchdog_plan_sha256"] == second["watchdog_plan_sha256"]
    assert evaluate_outbox_projection(first, POLICY) == evaluate_outbox_projection(second, POLICY)


def test_runner_has_no_runtime_network_process_or_mail_dependencies() -> None:
    source = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in (WATCHDOG_PATH, OUTBOX_PATH, Path("abd_acceptance/limited_self_heal.py")))
    for forbidden in ("import socket", "import subprocess", "import requests", "import httpx", "import smtplib", "http://", "https://"):
        assert forbidden not in source


def test_cli_has_exact_s18_p03_writer_and_verifier_mappings() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S18-P03": verify_limited_self_heal_phase_evidence,' in source
    assert '"AC-S18-P03": write_limited_self_heal_phase_evidence,' in source


def test_legacy_successor_chain_allows_only_the_current_dispatcher_hash() -> None:
    assert approved_successor_sha256(ROOT, CLI_PATH.as_posix()) == sha256_file(ROOT / CLI_PATH)


def test_candidate_preflight_covers_current_taskpack_and_signed_p02_dependency() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S18/P04_READY_NOT_STARTED"
    assert result["summary"]["failed"] == 0


def test_preflight_has_no_external_effects_or_production_claim() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_evidence_build_is_deterministic_before_signing() -> None:
    first = build_evidence(ROOT, require_test_reports=False)
    second = build_evidence(ROOT, require_test_reports=False)
    assert first == second
    assert first[0]["decision"] == "S18_P03_LIMITED_SELF_HEAL_CONTROL_PASS_P04_REQUIRED"


def test_fixture_rejects_wrong_predecessor_hash_and_reordered_scenarios() -> None:
    wrong = deepcopy(FIXTURE)
    wrong["predecessors"][0]["evidence_sha256"] = "0" * 64
    with pytest.raises(LimitedSelfHealAcceptanceError):
        validate_fixture(wrong)
    reordered = deepcopy(FIXTURE)
    reordered["scenarios"] = list(reversed(reordered["scenarios"]))
    with pytest.raises(LimitedSelfHealAcceptanceError):
        validate_fixture(reordered)


def test_rollback_drill_only_disables_the_local_self_heal_policy() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["immutable_fund_and_risk_verified"] is True
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["outbox_sent"] is False
