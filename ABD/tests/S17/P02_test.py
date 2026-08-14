from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.concurrency_idempotency import (
    CLI_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXTURE_PATH as ACCEPTANCE_FIXTURE_PATH,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from abd_acceptance.concurrency_idempotency_engine import (
    CLAIM_BOUNDARY,
    CONCURRENCY_TEST_PATH,
    EXECUTION_POLICY,
    FIXTURE_PATH,
    IDEMPOTENCY_POLICY,
    IDEMPOTENCY_REPORT_PATH,
    ConcurrencyIdempotencyInputError,
    artifact_sha256,
    build_artifacts,
    load_fixture,
    replay_scenario,
    sha256_file,
    strict_json_load,
    validate_artifacts,
    validate_fixture,
)
from abd_acceptance.load_test import verify_existing_phase_evidence as verify_s17_p01_phase_evidence
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.stage8_review import PINNED_REVIEW_ARTIFACT_HASHES


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)


def _report() -> dict:
    return build_artifacts(ROOT, FIXTURE)[IDEMPOTENCY_REPORT_PATH.as_posix()]


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def test_fixture_is_exact_s17_p02_contract() -> None:
    assert FIXTURE["contract_id"] == "AC-S17-P02"
    assert FIXTURE["expected_next"] == "S17/P03_READY_NOT_STARTED"
    assert ACCEPTANCE_FIXTURE_PATH == FIXTURE_PATH


def test_policy_keeps_both_duplicate_gates_at_zero() -> None:
    assert IDEMPOTENCY_POLICY["duplicate_suggestion_max"] == 0
    assert IDEMPOTENCY_POLICY["duplicate_ledger_event_max"] == 0


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_scenario_replays_to_its_pinned_summary(scenario: dict) -> None:
    result = replay_scenario(scenario)
    assert result["summary"] == scenario["expected"]
    assert result["action"] == "NO_RECOMMENDATION_NO_ORDER"
    assert result["real_runtime_concurrency_used"] is False


def test_out_of_order_input_is_reduced_to_stable_logical_order() -> None:
    result = replay_scenario(_scenario("OUT_OF_ORDER_DELAYED"))
    assert result["input_order_operation_ids"] == ["S17P02_OOO_002", "S17P02_OOO_001", "S17P02_OOO_003"]
    assert result["scheduled_order_operation_ids"] == ["S17P02_OOO_001", "S17P02_OOO_002", "S17P02_OOO_003"]


def test_fan_in_concurrency_vector_suppresses_seven_duplicates() -> None:
    result = replay_scenario(_scenario("FAN_IN_DUPLICATE_8"))
    assert result["summary"]["accepted_local_projection_count"] == 1
    assert result["summary"]["suppressed_duplicate_attempt_count"] == 7
    assert len(result["local_synthetic_ledger_projections"]) == 1


def test_timeout_attempt_has_no_state_change_and_retry_commits_once() -> None:
    result = replay_scenario(_scenario("TIMEOUT_RETRY"))
    assert result["summary"] == {
        "input_attempt_count": 3,
        "accepted_local_projection_count": 1,
        "suppressed_duplicate_attempt_count": 1,
        "timeout_no_state_change_count": 1,
        "quarantined_key_conflict_count": 0,
    }
    assert [record["disposition"] for record in result["records"]] == [
        "TIMEOUT_NO_STATE_CHANGE",
        "ACCEPTED_LOCAL_PROJECTION",
        "SUPPRESSED_DUPLICATE",
    ]


def test_conflicting_payload_is_quarantined_without_duplicate_projection() -> None:
    result = replay_scenario(_scenario("CONFLICT_QUARANTINE"))
    assert result["summary"]["quarantined_key_conflict_count"] == 1
    assert len(result["local_synthetic_ledger_projections"]) == 1
    assert result["records"][-1]["disposition"] == "QUARANTINED_KEY_CONFLICT"


def test_plus_minus_one_in_ten_thousand_boundary_keeps_actions_disabled() -> None:
    result = replay_scenario(_scenario("BOUNDARY_PLUS_MINUS_0001"))
    values = [operation["payload"]["probability_delta"] for operation in _scenario("BOUNDARY_PLUS_MINUS_0001")["operations"]]
    assert values == ["-0.0001", "0.0001"]
    assert all(record["action"] == "NO_RECOMMENDATION_NO_ORDER" for record in result["records"])


def test_report_aggregate_is_exact() -> None:
    report = _report()
    assert report["aggregate"] == {
        "input_attempt_count": 19,
        "accepted_local_projection_count": 8,
        "suppressed_duplicate_attempt_count": 9,
        "timeout_no_state_change_count": 1,
        "quarantined_key_conflict_count": 1,
    }


def test_report_idempotency_gate_is_strictly_zero_duplicate() -> None:
    gate = _report()["idempotency_gate"]
    assert gate["duplicate_suggestion_count"] == 0
    assert gate["duplicate_ledger_event_count"] == 0
    assert gate["input_attempts_accounted"] is True
    assert gate["projection_identity_unique"] is True
    assert gate["passed"] is True


def test_local_projection_identifiers_are_unique() -> None:
    report = _report()
    projections = [projection for scenario in report["scenarios"] for projection in scenario["local_synthetic_ledger_projections"]]
    assert len(projections) == 8
    assert len({item["projection_id"] for item in projections}) == 8


def test_fault_log_contains_only_fail_closed_non_action_dispositions() -> None:
    fault_log = _report()["structured_fault_log"]
    assert len(fault_log) == 11
    assert {item["fault_or_control_disposition"] for item in fault_log} == {
        "SUPPRESSED_DUPLICATE",
        "TIMEOUT_NO_STATE_CHANGE",
        "QUARANTINED_KEY_CONFLICT",
    }
    assert {item["action"] for item in fault_log} == {"NO_RECOMMENDATION_NO_ORDER"}


def test_artifact_is_deterministic_across_two_builds() -> None:
    first = _report()
    second = _report()
    assert first == second
    assert artifact_sha256(first) == artifact_sha256(second)


def test_current_generated_report_replays_exactly() -> None:
    actual = validate_artifacts(ROOT, FIXTURE)
    assert actual[IDEMPOTENCY_REPORT_PATH.as_posix()] == _report()


def test_generator_source_hash_is_bound_into_report() -> None:
    source = _report()["source_generator"]
    assert source["path"] == CONCURRENCY_TEST_PATH.as_posix()
    assert source["sha256"] == sha256_file(ROOT / CONCURRENCY_TEST_PATH)


def test_current_report_is_machine_readable() -> None:
    report = strict_json_load(ROOT / IDEMPOTENCY_REPORT_PATH)
    assert report == _report()


def test_invalid_product_version_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["product_version"] = "0.0.0.2"
    with pytest.raises(ConcurrencyIdempotencyInputError):
        validate_fixture(mutated)


def test_invalid_baseline_hash_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["baseline_hashes"]["VERSION"] = "0" * 64
    with pytest.raises(ConcurrencyIdempotencyInputError):
        validate_fixture(mutated)


def test_duplicate_operation_identifier_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["scenarios"][1]["operations"][1]["operation_id"] = mutated["scenarios"][1]["operations"][0]["operation_id"]
    with pytest.raises(ConcurrencyIdempotencyInputError):
        validate_fixture(mutated)


def test_out_of_range_probability_boundary_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["scenarios"][5]["operations"][0]["payload"]["probability_delta"] = "-0.0002"
    with pytest.raises(ConcurrencyIdempotencyInputError):
        validate_fixture(mutated)


def test_wrong_predecessor_hash_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["predecessor"]["evidence_sha256"] = "0" * 64
    with pytest.raises(ConcurrencyIdempotencyInputError):
        validate_fixture(mutated)


def test_mutated_scenario_cannot_be_replayed_as_approved_vector() -> None:
    mutated = deepcopy(_scenario("CONFLICT_QUARANTINE"))
    mutated["operations"][1]["payload"]["probability_delta"] = "0.0000"
    with pytest.raises(ConcurrencyIdempotencyInputError):
        replay_scenario(mutated)


def test_all_records_keep_recommendation_and_order_disabled() -> None:
    report = _report()
    assert report["action"] == "NO_RECOMMENDATION_NO_ORDER"
    assert all(record["action"] == "NO_RECOMMENDATION_NO_ORDER" for scenario in report["scenarios"] for record in scenario["records"])


def test_claim_boundary_excludes_real_runtime_and_ledger() -> None:
    assert CLAIM_BOUNDARY["real_runtime_concurrency_executed"] is False
    assert CLAIM_BOUNDARY["real_ledger_read_or_written"] is False
    assert CLAIM_BOUNDARY["real_time_soak_waited"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False


def test_execution_policy_excludes_threads_processes_and_soak() -> None:
    assert EXECUTION_POLICY["runtime_thread_or_process_concurrency_allowed"] is False
    assert EXECUTION_POLICY["full_regression_or_real_time_soak_allowed"] is False
    assert EXECUTION_POLICY["external_runtime_access_allowed"] is False


def test_p01_predecessor_is_bound_in_report() -> None:
    predecessor = _report()["predecessor"]
    assert predecessor["contract_id"] == "AC-S17-P01"
    assert predecessor["status"] == "PASS"
    assert predecessor["next"] == "S17/P02_READY_NOT_STARTED"


def test_p01_signed_receipt_remains_verifiable_after_shared_dispatcher_growth() -> None:
    result = verify_s17_p01_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["evidence_sha256"] == "2f8cc9265cea7eec0e28d6ae0608ba6548a75378d28b850e639509465bff2fa9"


def test_candidate_preflight_passes_before_signing() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S17/P03_READY_NOT_STARTED"


def test_full_acceptance_preflight_has_expected_number_of_checks() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["status"] == "PASS"
    assert result["summary"]["checks"] == 23
    assert result["summary"]["failed"] == 0


def test_rollback_drill_keeps_all_external_state_unchanged() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_runtime_concurrency_executed"] is False
    assert rollback["real_ledger_read_or_written"] is False


def test_cli_contains_only_the_required_s17_p02_writer_and_verifier_wiring() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S17-P02": verify_concurrency_idempotency_phase_evidence,' in source
    assert '"AC-S17-P02": write_concurrency_idempotency_phase_evidence,' in source


def test_existing_legacy_allowlist_tracks_the_exact_shared_dispatcher_successor() -> None:
    current = sha256_file(ROOT / CLI_PATH)
    assert current == "5fa1d508928e764117b5eb7e05705c9e738b760afb00355d3bc4f2303f8f3daf"
    assert approved_successor_sha256(ROOT, CLI_PATH.as_posix()) == current


def test_existing_stage8_pins_track_only_the_refreshed_compatibility_chain() -> None:
    for relative in (
        "machine/facts/stage8_review_contract.json",
        "machine/tests/fixtures/S08_STAGE_REVIEW.json",
        "machine/facts/s08_legacy_receipt_compatibility.json",
        "abd_acceptance/legacy_receipt_compatibility.py",
    ):
        assert PINNED_REVIEW_ARTIFACT_HASHES[relative] == sha256_file(ROOT / relative)


def test_fixture_minimum_is_covered_by_this_targeted_module() -> None:
    test_functions = [name for name, value in globals().items() if name.startswith("test_") and callable(value)]
    assert len(test_functions) >= FIXTURE["minimum_targeted_pytest_cases"]
