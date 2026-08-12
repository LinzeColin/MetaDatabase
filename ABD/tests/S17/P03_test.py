from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.chaos import (
    CHAOS_SCENARIOS_PATH,
    CLI_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXTURE_PATH as ACCEPTANCE_FIXTURE_PATH,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from abd_acceptance.chaos_engine import (
    CHAOS_POLICY,
    CHAOS_RUNNER_PATH,
    CLAIM_BOUNDARY,
    EXECUTION_POLICY,
    FIXTURE_PATH,
    ChaosInputError,
    artifact_sha256,
    build_artifacts,
    load_fixture,
    replay_scenario,
    sha256_file,
    strict_json_load,
    validate_artifacts,
    validate_fixture,
)
from abd_acceptance.concurrency_idempotency import verify_existing_phase_evidence as verify_s17_p02_phase_evidence
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.load_test import verify_existing_phase_evidence as verify_s17_p01_phase_evidence
from abd_acceptance.stage8_review import PINNED_REVIEW_ARTIFACT_HASHES


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)


def _report() -> dict:
    return build_artifacts(ROOT, FIXTURE)[CHAOS_SCENARIOS_PATH.as_posix()]


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def test_fixture_is_exact_s17_p03_contract() -> None:
    assert FIXTURE["contract_id"] == "AC-S17-P03"
    assert FIXTURE["expected_next"] == "S17/P04_READY_NOT_STARTED"
    assert ACCEPTANCE_FIXTURE_PATH == FIXTURE_PATH


def test_chaos_policy_keeps_stale_data_and_actions_disabled() -> None:
    assert CHAOS_POLICY["stale_data_policy"] == "REJECT_STALE_DATA_ON_ANY_ERROR"
    assert CHAOS_POLICY["degradation_policy"] == "AUTO_DEGRADE_NO_RECOMMENDATION_NO_ORDER"
    assert CHAOS_POLICY["recommendation_enabled"] is False
    assert CHAOS_POLICY["order_submission_enabled"] is False


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_scenario_replays_to_its_pinned_result(scenario: dict) -> None:
    result = replay_scenario(scenario)
    assert {
        "degraded": result["degraded"],
        "selected_data": result["selected_data"],
        "stale_data_used": result["stale_data_used"],
        "stale_data_disposition": result["stale_data_disposition"],
        "action": result["action"],
    } == scenario["expected"]
    assert result["real_fault_injected"] is False


def test_all_required_fault_classes_are_included_once() -> None:
    faults = {scenario["fault"] for scenario in FIXTURE["scenarios"] if scenario["fault"] != "NONE"}
    assert faults == {
        "PROCESS_EXIT",
        "DNS_FAILURE",
        "NETWORK_FAILURE",
        "PAGE_SCHEMA_CHANGE",
        "DISK_PRESSURE",
        "MEMORY_PRESSURE",
        "CLOCK_SKEW",
        "MODEL_ARTIFACT_CORRUPTION",
    }


def test_every_error_auto_degrades_and_rejects_stale_data() -> None:
    results = [replay_scenario(scenario) for scenario in FIXTURE["scenarios"] if scenario["fault"] != "NONE"]
    assert len(results) == 8
    assert all(result["degraded"] is True for result in results)
    assert all(result["selected_data"] == "NONE" for result in results)
    assert all(result["stale_data_used"] is False for result in results)
    assert all(result["stale_data_disposition"] == "REJECTED_STALE_DATA" for result in results)


def test_healthy_frozen_current_snapshot_never_turns_on_action() -> None:
    result = replay_scenario(_scenario("BASELINE_HEALTHY_CURRENT"))
    assert result["degraded"] is False
    assert result["selected_data"] == "CURRENT_FROZEN_SNAPSHOT"
    assert result["action"] == "NO_RECOMMENDATION_NO_ORDER"


def test_plus_minus_one_in_ten_thousand_and_adverse_tick_stay_fail_closed() -> None:
    clock = replay_scenario(_scenario("CLOCK_SKEW_FAIL_CLOSED"))
    model = replay_scenario(_scenario("MODEL_ARTIFACT_CORRUPTION_FAIL_CLOSED"))
    assert clock["current_snapshot"]["probability_delta"] == "-0.0001"
    assert model["current_snapshot"]["probability_delta"] == "0.0001"
    assert clock["current_snapshot"]["odds_tick_delta"] == -1
    assert model["current_snapshot"]["odds_tick_delta"] == -1
    assert clock["action"] == model["action"] == "NO_RECOMMENDATION_NO_ORDER"


def test_report_aggregate_and_stale_gate_are_exact() -> None:
    report = _report()
    assert report["aggregate"] == {
        "scenario_count": 9,
        "error_scenario_count": 8,
        "degraded_count": 8,
        "rejected_stale_data_count": 8,
        "stale_data_used_count": 0,
        "no_recommendation_no_order_count": 9,
    }
    assert report["stale_data_gate"] == {
        "error_scenario_count": 8,
        "auto_degraded_count": 8,
        "rejected_stale_data_count": 8,
        "stale_data_used_count": 0,
        "passed": True,
    }


def test_structured_fault_log_is_complete_and_local_only() -> None:
    fault_log = _report()["structured_fault_log"]
    assert len(fault_log) == 8
    assert all(item["degraded"] is True for item in fault_log)
    assert all(item["stale_data_disposition"] == "REJECTED_STALE_DATA" for item in fault_log)
    assert all(item["real_fault_injected"] is False for item in fault_log)


def test_artifact_is_deterministic_across_two_builds() -> None:
    first = _report()
    second = _report()
    assert first == second
    assert artifact_sha256(first) == artifact_sha256(second)


def test_current_generated_report_replays_exactly() -> None:
    actual = validate_artifacts(ROOT, FIXTURE)
    assert actual[CHAOS_SCENARIOS_PATH.as_posix()] == _report()


def test_generator_source_hash_is_bound_into_report() -> None:
    source = _report()["source_generator"]
    assert source["path"] == CHAOS_RUNNER_PATH.as_posix()
    assert source["sha256"] == sha256_file(ROOT / CHAOS_RUNNER_PATH)


def test_current_report_is_machine_readable() -> None:
    report = strict_json_load(ROOT / CHAOS_SCENARIOS_PATH)
    assert report == _report()


def test_invalid_product_version_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["product_version"] = "0.0.0.2"
    with pytest.raises(ChaosInputError):
        validate_fixture(mutated)


def test_missing_fault_vector_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["scenarios"] = mutated["scenarios"][:-1]
    with pytest.raises(ChaosInputError):
        validate_fixture(mutated)


def test_wrong_stale_data_policy_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["chaos_policy"]["stale_data_policy"] = "ALLOW_STALE"
    with pytest.raises(ChaosInputError):
        validate_fixture(mutated)


def test_wrong_predecessor_hash_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["predecessor"]["evidence_sha256"] = "0" * 64
    with pytest.raises(ChaosInputError):
        validate_fixture(mutated)


def test_unapproved_fault_mutation_cannot_replay() -> None:
    mutated = deepcopy(_scenario("PROCESS_EXIT_FAIL_CLOSED"))
    mutated["fault"] = "NONE"
    with pytest.raises(ChaosInputError):
        replay_scenario(mutated)


def test_out_of_range_probability_boundary_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["scenarios"][7]["current_snapshot"]["probability_delta"] = "0.0002"
    with pytest.raises(ChaosInputError):
        validate_fixture(mutated)


def test_all_records_keep_recommendation_and_order_disabled() -> None:
    report = _report()
    assert report["action"] == "NO_RECOMMENDATION_NO_ORDER"
    assert all(item["action"] == "NO_RECOMMENDATION_NO_ORDER" for item in report["scenarios"])


def test_claim_boundary_excludes_live_faults_runtime_and_soak() -> None:
    assert CLAIM_BOUNDARY["real_process_exit_injected"] is False
    assert CLAIM_BOUNDARY["real_dns_or_network_fault_injected"] is False
    assert CLAIM_BOUNDARY["real_page_disk_memory_clock_or_model_mutated"] is False
    assert CLAIM_BOUNDARY["real_runtime_or_ledger_read_or_written"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False


def test_execution_policy_excludes_actual_faults_and_real_time_soak() -> None:
    assert EXECUTION_POLICY["actual_fault_injection_allowed"] is False
    assert EXECUTION_POLICY["full_regression_or_real_time_soak_allowed"] is False
    assert EXECUTION_POLICY["external_runtime_access_allowed"] is False


def test_p02_predecessor_is_bound_in_report() -> None:
    predecessor = _report()["predecessor"]
    assert predecessor["contract_id"] == "AC-S17-P02"
    assert predecessor["status"] == "PASS"
    assert predecessor["next"] == "S17/P03_READY_NOT_STARTED"


def test_p01_signed_receipt_remains_verifiable_after_shared_dispatcher_growth() -> None:
    result = verify_s17_p01_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["evidence_sha256"] == "2f8cc9265cea7eec0e28d6ae0608ba6548a75378d28b850e639509465bff2fa9"


def test_p02_signed_receipt_remains_verifiable_after_shared_dispatcher_growth() -> None:
    result = verify_s17_p02_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["evidence_sha256"] == "c417d9eb732c24969d11db52bd501438572a57e2b3eeef8791085e746aae2711"


def test_candidate_preflight_passes_before_signing() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S17/P04_READY_NOT_STARTED"


def test_full_acceptance_preflight_has_expected_number_of_checks() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["status"] == "PASS"
    assert result["summary"]["checks"] == 23
    assert result["summary"]["failed"] == 0


def test_cli_has_the_exact_p03_writer_and_verifier_mapping() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S17-P03": verify_chaos_phase_evidence,' in source
    assert '"AC-S17-P03": write_chaos_phase_evidence,' in source


def test_legacy_successor_chain_stays_exact_without_allow_list_expansion() -> None:
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / CLI_PATH)
    assert all(sha256_file(ROOT / path) == expected for path, expected in PINNED_REVIEW_ARTIFACT_HASHES.items())


def test_rollback_drill_is_local_and_preserves_predecessor() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_fault_injected"] is False
    assert rollback["artifacts"]["machine/evidence/EVD-S17-P02.json"]["status"] == "PASS"
