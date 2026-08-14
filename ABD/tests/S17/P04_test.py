from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.chaos import verify_existing_phase_evidence as verify_s17_p03_phase_evidence
from abd_acceptance.concurrency_idempotency import verify_existing_phase_evidence as verify_s17_p02_phase_evidence
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.load_test import verify_existing_phase_evidence as verify_s17_p01_phase_evidence
from abd_acceptance.recovery import (
    CLI_PATH,
    DISASTER_DRILL_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXTURE_PATH as ACCEPTANCE_FIXTURE_PATH,
    RECOVERY_REPORT_PATH,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from abd_acceptance.recovery_engine import (
    CLAIM_BOUNDARY,
    EXECUTION_POLICY,
    FIXTURE_PATH,
    RECOVERY_POLICY,
    RECOVERY_TEST_PATH,
    RecoveryInputError,
    artifact_sha256,
    build_artifacts,
    load_fixture,
    replay_scenario,
    sha256_file,
    strict_json_load,
    validate_artifacts,
    validate_fixture,
)
from abd_acceptance.stage8_review import PINNED_REVIEW_ARTIFACT_HASHES


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)


def _artifacts() -> dict:
    return build_artifacts(ROOT, FIXTURE)


def _report() -> dict:
    return _artifacts()[RECOVERY_REPORT_PATH.as_posix()]


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def test_fixture_is_exact_s17_p04_contract() -> None:
    assert FIXTURE["contract_id"] == "AC-S17-P04"
    assert FIXTURE["expected_next"] == "S17/STAGE_REVIEW_READY_NOT_STARTED"
    assert ACCEPTANCE_FIXTURE_PATH == FIXTURE_PATH


def test_recovery_policy_keeps_the_two_fixed_gates_and_actions_disabled() -> None:
    assert RECOVERY_POLICY["ledger_recovery_point_seconds_max"] == 60
    assert RECOVERY_POLICY["advice_service_recovery_seconds_max"] == 900
    assert RECOVERY_POLICY["recommendation_enabled"] is False
    assert RECOVERY_POLICY["order_submission_enabled"] is False


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_recovery_vector_replays_to_its_pinned_result(scenario: dict) -> None:
    result = replay_scenario(scenario)
    assert {
        "restoration_eligible": result["restoration_eligible"],
        "rpo_pass": result["rpo_pass"],
        "rto_pass": result["rto_pass"],
        "advice_service_state": result["advice_service_state"],
        "action": result["action"],
        "reason_code": result["reason_code"],
    } == scenario["expected"]
    assert result["real_runtime_state_changed"] is False
    assert result["real_time_wait_performed"] is False


def test_all_required_recovery_operations_are_covered() -> None:
    operations = {scenario["operation"] for scenario in FIXTURE["scenarios"]}
    assert operations == {"PROCESS_RESTART", "LEDGER_REPLAY", "BACKUP_RESTORE", "DUAL_ENVIRONMENT_ROLLBACK", "EXPIRED_TICKET_CLEANUP"}


def test_positive_boundary_vectors_meet_fixed_rpo_and_rto_limits() -> None:
    ledger = replay_scenario(_scenario("LEDGER_REPLAY_RPO_BOUNDARY"))
    backup = replay_scenario(_scenario("BACKUP_RESTORE_RTO_BOUNDARY"))
    assert ledger["logical_rpo_seconds"] == 60
    assert backup["logical_rto_seconds"] == 900
    assert ledger["restoration_eligible"] is True
    assert backup["restoration_eligible"] is True


def test_one_second_over_each_limit_degrades_fail_closed() -> None:
    rpo = replay_scenario(_scenario("LEDGER_REPLAY_RPO_61_FAIL_CLOSED"))
    rto = replay_scenario(_scenario("DUAL_ENVIRONMENT_ROLLBACK_RTO_901_FAIL_CLOSED"))
    assert rpo["logical_rpo_seconds"] == 61
    assert rpo["reason_code"] == "RPO_EXCEEDED_FAIL_CLOSED"
    assert rto["logical_rto_seconds"] == 901
    assert rto["reason_code"] == "RTO_EXCEEDED_FAIL_CLOSED"
    assert rpo["action"] == rto["action"] == "NO_RECOMMENDATION_NO_ORDER"


def test_expired_ticket_cleanup_is_only_a_frozen_projection() -> None:
    result = replay_scenario(_scenario("EXPIRED_TICKET_CLEANUP_WITHIN_GATE"))
    assert result["frozen_ticket_count"] == 3
    assert result["restoration_eligible"] is True
    assert result["real_runtime_state_changed"] is False


def test_plus_minus_one_in_ten_thousand_and_adverse_tick_stay_non_actioning() -> None:
    minus = replay_scenario(_scenario("LEDGER_REPLAY_RPO_BOUNDARY"))
    plus = replay_scenario(_scenario("BACKUP_RESTORE_RTO_BOUNDARY"))
    assert minus["probability_delta"] == "-0.0001"
    assert plus["probability_delta"] == "0.0001"
    assert minus["odds_tick_delta"] == plus["odds_tick_delta"] == -1
    assert minus["action"] == plus["action"] == "NO_RECOMMENDATION_NO_ORDER"


def test_report_aggregate_and_gate_are_exact() -> None:
    report = _report()
    assert report["aggregate"] == {
        "scenario_count": 7,
        "eligible_restore_count": 5,
        "rpo_within_gate_count": 5,
        "rto_within_gate_count": 5,
        "rpo_exceeded_fail_closed_count": 1,
        "rto_exceeded_fail_closed_count": 1,
        "frozen_expired_ticket_projection_count": 3,
        "recommendation_or_order_enabled_count": 0,
    }
    assert report["recovery_gate"] == {
        "ledger_recovery_point_seconds_max": 60,
        "advice_service_recovery_seconds_max": 900,
        "eligible_max_logical_rpo_seconds": 60,
        "eligible_max_logical_rto_seconds": 900,
        "eligible_rpo_gate_passed": True,
        "eligible_rto_gate_passed": True,
        "over_limit_vectors_fail_closed": True,
        "passed": True,
    }


def test_structured_failure_log_contains_only_local_non_actions() -> None:
    failures = _report()["structured_failure_log"]
    assert len(failures) == 2
    assert {item["reason_code"] for item in failures} == {"RPO_EXCEEDED_FAIL_CLOSED", "RTO_EXCEEDED_FAIL_CLOSED"}
    assert all(item["action"] == "NO_RECOMMENDATION_NO_ORDER" for item in failures)
    assert all(item["real_runtime_state_changed"] is False for item in failures)


def test_disaster_drill_document_states_the_local_only_boundary() -> None:
    drill = _artifacts()[DISASTER_DRILL_PATH.as_posix()]
    assert "账本恢复点逻辑门：`<=60` 秒" in drill
    assert "建议服务恢复逻辑门：`<=900` 秒" in drill
    assert "不重启进程、不读写账本、不恢复备份、不切换环境、不删除票据" in drill


def test_artifacts_are_deterministic_across_two_builds() -> None:
    first = _artifacts()
    second = _artifacts()
    assert first == second
    assert artifact_sha256(first[RECOVERY_REPORT_PATH.as_posix()]) == artifact_sha256(second[RECOVERY_REPORT_PATH.as_posix()])


def test_current_generated_artifacts_replay_exactly() -> None:
    actual = validate_artifacts(ROOT, FIXTURE)
    assert actual == _artifacts()


def test_generator_source_hash_is_bound_into_report() -> None:
    source = _report()["source_generator"]
    assert source["path"] == RECOVERY_TEST_PATH.as_posix()
    assert source["sha256"] == sha256_file(ROOT / RECOVERY_TEST_PATH)


def test_current_report_is_machine_readable() -> None:
    assert strict_json_load(ROOT / RECOVERY_REPORT_PATH) == _report()


def test_invalid_product_version_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["product_version"] = "0.0.0.2"
    with pytest.raises(RecoveryInputError):
        validate_fixture(mutated)


def test_missing_scenario_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["scenarios"] = mutated["scenarios"][:-1]
    with pytest.raises(RecoveryInputError):
        validate_fixture(mutated)


def test_wrong_recovery_policy_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["recovery_policy"]["ledger_recovery_point_seconds_max"] = 61
    with pytest.raises(RecoveryInputError):
        validate_fixture(mutated)


def test_wrong_predecessor_hash_fixture_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["predecessor"]["evidence_sha256"] = "0" * 64
    with pytest.raises(RecoveryInputError):
        validate_fixture(mutated)


def test_mutated_boundary_vector_cannot_replay() -> None:
    mutated = deepcopy(_scenario("LEDGER_REPLAY_RPO_61_FAIL_CLOSED"))
    mutated["logical_rpo_seconds"] = 60
    with pytest.raises(RecoveryInputError):
        replay_scenario(mutated)


def test_out_of_range_probability_vector_fails_closed() -> None:
    mutated = deepcopy(FIXTURE)
    mutated["scenarios"][1]["probability_delta"] = "0.0002"
    with pytest.raises(RecoveryInputError):
        validate_fixture(mutated)


def test_all_records_keep_recommendation_and_order_disabled() -> None:
    report = _report()
    assert report["action"] == "NO_RECOMMENDATION_NO_ORDER"
    assert all(item["action"] == "NO_RECOMMENDATION_NO_ORDER" for item in report["scenarios"])


def test_claim_boundary_excludes_live_restore_and_soak() -> None:
    assert CLAIM_BOUNDARY["real_process_restarted"] is False
    assert CLAIM_BOUNDARY["real_ledger_read_or_written"] is False
    assert CLAIM_BOUNDARY["real_backup_restored"] is False
    assert CLAIM_BOUNDARY["real_dual_environment_rolled_back"] is False
    assert CLAIM_BOUNDARY["real_ticket_deleted_or_changed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["production_deployed_or_activated"] is False


def test_execution_policy_excludes_actual_restore_and_real_time_soak() -> None:
    assert EXECUTION_POLICY["actual_restart_or_restore_allowed"] is False
    assert EXECUTION_POLICY["full_regression_or_real_time_soak_allowed"] is False
    assert EXECUTION_POLICY["external_runtime_access_allowed"] is False


def test_p03_predecessor_is_bound_in_report() -> None:
    predecessor = _report()["predecessor"]
    assert predecessor["contract_id"] == "AC-S17-P03"
    assert predecessor["status"] == "PASS"
    assert predecessor["next"] == "S17/P04_READY_NOT_STARTED"


def test_p01_signed_receipt_remains_verifiable_after_shared_dispatcher_growth() -> None:
    result = verify_s17_p01_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["evidence_sha256"] == "2f8cc9265cea7eec0e28d6ae0608ba6548a75378d28b850e639509465bff2fa9"


def test_p02_signed_receipt_remains_verifiable_after_shared_dispatcher_growth() -> None:
    result = verify_s17_p02_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["evidence_sha256"] == "c417d9eb732c24969d11db52bd501438572a57e2b3eeef8791085e746aae2711"


def test_p03_signed_receipt_remains_verifiable_after_shared_dispatcher_growth() -> None:
    result = verify_s17_p03_phase_evidence(ROOT)
    assert result["status"] == "PASS"
    assert result["evidence_sha256"] == "2f40bd1eed62a0b1ed14347507d497fa54cc63db56c4f31112c631fe48beef97"


def test_candidate_preflight_passes_before_signing() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S17/STAGE_REVIEW_READY_NOT_STARTED"


def test_full_acceptance_preflight_has_expected_number_of_checks() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["status"] == "PASS"
    assert result["summary"]["checks"] == 23
    assert result["summary"]["failed"] == 0


def test_cli_has_the_exact_p04_writer_and_verifier_mapping() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S17-P04": verify_recovery_phase_evidence,' in source
    assert '"AC-S17-P04": write_recovery_phase_evidence,' in source


def test_legacy_successor_chain_stays_exact_without_allow_list_expansion() -> None:
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / CLI_PATH)
    assert all(sha256_file(ROOT / path) == expected for path, expected in PINNED_REVIEW_ARTIFACT_HASHES.items())


def test_rollback_drill_is_local_and_preserves_predecessor() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_restart_or_restore_performed"] is False
    assert rollback["artifacts"]["machine/evidence/EVD-S17-P03.json"]["status"] == "PASS"
