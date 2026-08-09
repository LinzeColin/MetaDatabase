from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.operations_automation import (
    EXPECTED_JOB_IDS,
    EXTERNAL_EFFECT_BOUNDARY,
    NORMAL_ACTION,
    NORMAL_DECISION,
    OperationsInputError,
    PAUSE_DECISION,
    SAFE_ACTION,
    SAFE_FUND_FACTS,
    SAFE_RISK_GATE,
    evaluate_operations_cycle,
    validate_maintenance_calendar,
    validate_runbook,
    validate_scheduled_jobs,
)
from abd_acceptance.operations_automation_acceptance import (
    CALENDAR_PATH,
    CLI_PATH,
    CONTRACT_ID,
    FEATURE_FLAG_ID,
    FIXTURE_PATH,
    OperationsAutomationAcceptanceError,
    RUNBOOK_PATH,
    SCHEDULE_PATH,
    build_evidence,
    evaluate_contract,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)
SCHEDULE = json.loads((ROOT / SCHEDULE_PATH).read_text(encoding="utf-8"))
CALENDAR = json.loads((ROOT / CALENDAR_PATH).read_text(encoding="utf-8"))


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def _plan(identifier: str) -> dict:
    return evaluate_operations_cycle(_scenario(identifier)["cycle_input"], SCHEDULE, CALENDAR)


def test_fixture_is_exact_s18_p04_contract() -> None:
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S18/STAGE_REVIEW_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S18_P04.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_cycle_has_its_pinned_pause_contract_result(scenario: dict) -> None:
    plan = evaluate_operations_cycle(scenario["cycle_input"], SCHEDULE, CALENDAR)
    assert {key: plan[key] for key in scenario["expected"]} == scenario["expected"]
    assert plan["fund_facts_before"] == plan["fund_facts_after"] == SAFE_FUND_FACTS
    assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
    assert plan["fund_facts_changed"] is False
    assert plan["risk_gate_relaxed"] is False
    assert plan["safe_action"] == SAFE_ACTION
    assert plan["recommendation_generated_or_enabled"] is False
    assert plan["order_submission_enabled"] is False
    assert plan["external_runtime_accessed"] is False
    assert plan["production_state_changed"] is False
    assert plan["owner_outbox_projection"]["external_delivery_attempted"] is False
    assert plan["owner_outbox_projection"]["external_network_accessed"] is False


def test_normal_cycle_needs_no_owner_maintenance_or_real_scheduler() -> None:
    plan = _plan("GOLDEN_ALL_LOGICAL_JOBS_PASS")
    assert plan["decision"] == NORMAL_DECISION
    assert plan["action"] == NORMAL_ACTION
    assert plan["pause_contract"] is False
    assert plan["owner_maintenance_required"] is False
    assert plan["actual_scheduler_or_cron_installed"] is False
    assert plan["actual_patch_or_backup_performed"] is False
    assert plan["actual_disaster_recovery_executed"] is False


def test_all_daily_weekly_and_monthly_job_failures_pause_exactly_once() -> None:
    failed = set()
    for scenario in FIXTURE["scenarios"]:
        if scenario["scenario_id"].endswith("FAILURE_PAUSES"):
            plan = evaluate_operations_cycle(scenario["cycle_input"], SCHEDULE, CALENDAR)
            assert plan["decision"] == PAUSE_DECISION
            assert plan["pause_contract"] is True
            assert plan["owner_maintenance_required"] is True
            assert plan["owner_outbox_projection"]["status"] == "LOCAL_OWNER_ESCALATION_NOT_SENT"
            failed.update(plan["failed_job_ids"])
    assert failed == set(EXPECTED_JOB_IDS)


def test_adverse_one_in_ten_thousand_vector_preserves_the_gates() -> None:
    plan = _plan("ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_PRESERVES_GATES")
    assert plan["decision"] == NORMAL_DECISION
    assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
    assert plan["risk_gate_relaxed"] is False


def test_unsafe_fund_risk_external_and_float_requests_only_pause() -> None:
    plans = [
        _plan("FUND_MUTATION_ATTEMPT_PAUSES"),
        _plan("RISK_GATE_RELAXATION_ATTEMPT_PAUSES"),
        _plan("EXTERNAL_EXECUTION_ATTEMPT_PAUSES"),
        _plan("MALFORMED_JOB_STATUS_PAUSES"),
    ]
    floating = deepcopy(_scenario("GOLDEN_ALL_LOGICAL_JOBS_PASS")["cycle_input"])
    floating["probability_delta"] = 0.0
    plans.append(evaluate_operations_cycle(floating, SCHEDULE, CALENDAR))
    for plan in plans:
        assert plan["decision"] == PAUSE_DECISION
        assert plan["pause_contract"] is True
        assert plan["fund_facts_before"] == plan["fund_facts_after"] == SAFE_FUND_FACTS
        assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
        assert plan["order_submission_enabled"] is False


def test_schedule_calendar_and_runbook_are_exact_and_reject_gate_weakening() -> None:
    schedule = deepcopy(SCHEDULE)
    schedule["normal_operation"]["owner_maintenance_required"] = True
    with pytest.raises(OperationsInputError):
        validate_scheduled_jobs(schedule)
    calendar = deepcopy(CALENDAR)
    calendar["exception_escalation"]["external_delivery_enabled"] = True
    with pytest.raises(OperationsInputError):
        validate_maintenance_calendar(calendar)
    text = (ROOT / RUNBOOK_PATH).read_text(encoding="utf-8").replace(PAUSE_DECISION, "REMOVED", 1)
    with pytest.raises(OperationsInputError):
        validate_runbook(text)


def test_operations_replay_hash_is_deterministic() -> None:
    payload = _scenario("WEEKLY_BACKUP_FAILURE_PAUSES")["cycle_input"]
    first = evaluate_operations_cycle(payload, SCHEDULE, CALENDAR)
    second = evaluate_operations_cycle(payload, SCHEDULE, CALENDAR)
    assert first == second
    assert first["operations_plan_sha256"] == second["operations_plan_sha256"]


def test_runner_has_no_runtime_network_process_or_mail_dependencies() -> None:
    source = (ROOT / "abd_acceptance/operations_automation.py").read_text(encoding="utf-8")
    for forbidden in ("import socket", "import subprocess", "import requests", "import httpx", "import smtplib", "http://", "https://"):
        assert forbidden not in source


def test_cli_has_exact_s18_p04_writer_and_verifier_mappings() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S18-P04": verify_operations_automation_phase_evidence,' in source
    assert '"AC-S18-P04": write_operations_automation_phase_evidence,' in source


def test_legacy_successor_chain_allows_only_the_current_dispatcher_hash() -> None:
    assert approved_successor_sha256(ROOT, CLI_PATH.as_posix()) == sha256_file(ROOT / CLI_PATH)


def test_candidate_preflight_covers_current_taskpack_and_signed_p03_dependency() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S18/STAGE_REVIEW_READY_NOT_STARTED"
    assert result["summary"]["failed"] == 0


def test_preflight_has_no_external_effects_or_production_claim() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_evidence_build_is_deterministic_before_signing() -> None:
    first = build_evidence(ROOT, require_test_reports=False)
    second = build_evidence(ROOT, require_test_reports=False)
    assert first == second
    assert first[0]["decision"] == "S18_P04_OPERATIONS_AUTOMATION_PASS_STAGE_REVIEW_REQUIRED"


def test_fixture_rejects_wrong_predecessor_hash_and_reordered_scenarios() -> None:
    wrong = deepcopy(FIXTURE)
    wrong["predecessors"][0]["evidence_sha256"] = "0" * 64
    with pytest.raises(OperationsAutomationAcceptanceError):
        validate_fixture(wrong)
    reordered = deepcopy(FIXTURE)
    reordered["scenarios"] = list(reversed(reordered["scenarios"]))
    with pytest.raises(OperationsAutomationAcceptanceError):
        validate_fixture(reordered)


def test_rollback_drill_only_disables_local_operations_automation() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["pause_contract_preserved"] is True
    assert rollback["immutable_fund_and_risk_verified"] is True
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["outbox_sent"] is False
