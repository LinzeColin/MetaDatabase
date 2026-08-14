from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.safe_release import (
    CANARY_POLICY_PATH,
    CLI_PATH,
    CONTRACT_ID,
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXTURE_PATH,
    PIPELINE_PATH,
    PROBE_PATH,
    SafeReleaseAcceptanceError,
    build_evidence,
    evaluate_contract,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
)
from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.post_release_probe import (
    PROMOTE_DECISION,
    REQUIRED_PROBE_IDS,
    ROLLBACK_DECISION,
    SAFE_ACTION,
    UNKNOWN_TRIGGER,
    evaluate_probe_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = load_fixture(ROOT / FIXTURE_PATH)


def _scenario(identifier: str) -> dict:
    return next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier)


def test_fixture_is_exact_s18_p01_contract() -> None:
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S18/P02_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S18_P01.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_probe_vector_has_its_pinned_safe_result(scenario: dict) -> None:
    result = evaluate_probe_bundle(scenario["probe_bundle"])
    assert {key: result[key] for key in scenario["expected"]} == scenario["expected"]
    assert result["action"] == SAFE_ACTION
    assert result["recommendation_generated_or_enabled"] is False
    assert result["order_submission_enabled"] is False
    assert result["production_state_changed"] is False


def test_all_required_probes_are_covered_by_golden_vector() -> None:
    golden = _scenario("GOLDEN_ALL_PROBES_PASS")["probe_bundle"]
    assert tuple(golden["probe_results"]) == REQUIRED_PROBE_IDS


def test_health_failure_automatically_returns_the_previous_logical_slot() -> None:
    result = evaluate_probe_bundle(_scenario("HEALTH_PROBE_FAILED")["probe_bundle"])
    assert result["decision"] == ROLLBACK_DECISION
    assert result["logical_active_slot"] == "blue"
    assert result["logical_auto_rollback"] is True
    assert result["rollback_trigger"] == "HEALTH_PROBE"


def test_numeric_failure_automatically_returns_the_previous_logical_slot() -> None:
    result = evaluate_probe_bundle(_scenario("NUMERIC_CROSS_IMPLEMENTATION_FAILED")["probe_bundle"])
    assert result["decision"] == ROLLBACK_DECISION
    assert result["logical_active_slot"] == "green"
    assert result["rollback_trigger"] == "NUMERIC_CROSS_IMPLEMENTATION"


def test_unknown_or_missing_probe_fails_closed() -> None:
    unknown = evaluate_probe_bundle(_scenario("UNKNOWN_EXTRA_PROBE_FAILS_CLOSED")["probe_bundle"])
    missing = evaluate_probe_bundle(_scenario("MISSING_LEDGER_PROBE_FAILS_CLOSED")["probe_bundle"])
    assert unknown["rollback_trigger"] == missing["rollback_trigger"] == UNKNOWN_TRIGGER
    assert unknown["logical_auto_rollback"] is True
    assert missing["logical_auto_rollback"] is True


def test_one_in_ten_thousand_adverse_vector_never_enables_advice_or_order() -> None:
    result = evaluate_probe_bundle(_scenario("ADVERSE_MINUS_ONE_IN_TEN_THOUSAND_STABLE")["probe_bundle"])
    assert result["decision"] == PROMOTE_DECISION
    assert result["action"] == SAFE_ACTION
    assert result["recommendation_generated_or_enabled"] is False
    assert result["order_submission_enabled"] is False


def test_boolean_does_not_substitute_for_adverse_tick() -> None:
    bundle = deepcopy(_scenario("GOLDEN_ALL_PROBES_PASS")["probe_bundle"])
    bundle["odds_tick_delta"] = True
    result = evaluate_probe_bundle(bundle)
    assert result["decision"] == ROLLBACK_DECISION
    assert result["rollback_trigger"] == UNKNOWN_TRIGGER


def test_float_payload_fails_closed() -> None:
    bundle = deepcopy(_scenario("GOLDEN_ALL_PROBES_PASS")["probe_bundle"])
    bundle["probability_delta"] = -0.0001
    result = evaluate_probe_bundle(bundle)
    assert result["decision"] == ROLLBACK_DECISION
    assert result["rollback_trigger"] == UNKNOWN_TRIGGER


def test_pipeline_is_json_subset_of_yaml_with_exact_fail_closed_stages() -> None:
    pipeline = json.loads((ROOT / PIPELINE_PATH).read_text(encoding="utf-8"))
    assert pipeline["execution_mode"] == "OFFLINE_DETERMINISTIC_CONTRACT_ONLY"
    assert [item["id"] for item in pipeline["stages"]][-2:] == ["RUN_POST_RELEASE_PROBES", "PROMOTE_OR_ROLL_BACK"]
    assert {item["on_failure"] for item in pipeline["stages"]} == {"AUTO_ROLL_BACK_TO_PREVIOUS_SLOT_KEEP_ADVICE_DISABLED"}
    assert pipeline["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_canary_policy_is_bounded_and_keeps_actions_disabled() -> None:
    policy = json.loads((ROOT / CANARY_POLICY_PATH).read_text(encoding="utf-8"))
    assert [item["maximum_traffic_basis_points"] for item in policy["canary_profiles"]] == [0, 100, 500, 2500, 10000]
    assert all(item["live_recommendation"] is False for item in policy["canary_profiles"])
    assert all(item["order_submission_enabled"] is False for item in policy["canary_profiles"])
    assert policy["model_gate"] == "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT"


def test_candidate_preflight_covers_current_taskpack_and_signed_dependencies() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["next"] == "S18/P02_READY_NOT_STARTED"
    assert result["summary"]["failed"] == 0


def test_preflight_has_no_external_effects() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_evidence_build_is_deterministic_before_signing() -> None:
    first = build_evidence(ROOT, require_test_reports=False)
    second = build_evidence(ROOT, require_test_reports=False)
    assert first == second
    assert first[0]["decision"] == "S18_P01_SAFE_RELEASE_CONTROL_PASS_P02_REQUIRED"


def test_fixture_rejects_wrong_predecessor_hash() -> None:
    fixture = deepcopy(FIXTURE)
    fixture["predecessors"][0]["evidence_sha256"] = "0" * 64
    with pytest.raises(SafeReleaseAcceptanceError):
        validate_fixture(fixture)


def test_fixture_rejects_reordered_scenarios() -> None:
    fixture = deepcopy(FIXTURE)
    fixture["scenarios"] = list(reversed(fixture["scenarios"]))
    with pytest.raises(SafeReleaseAcceptanceError):
        validate_fixture(fixture)


def test_probe_runner_has_no_runtime_network_or_process_dependencies() -> None:
    source = (ROOT / PROBE_PATH).read_text(encoding="utf-8")
    assert "import socket" not in source
    assert "import subprocess" not in source
    assert "http://" not in source
    assert "https://" not in source


def test_cli_has_exact_s18_p01_writer_and_verifier_mappings() -> None:
    source = (ROOT / CLI_PATH).read_text(encoding="utf-8")
    assert '"AC-S18-P01": verify_safe_release_phase_evidence,' in source
    assert '"AC-S18-P01": write_safe_release_phase_evidence,' in source


def test_legacy_successor_chain_allows_only_the_current_dispatcher_hash() -> None:
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / CLI_PATH)


def test_rollback_drill_only_disables_local_candidate_control() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["logical_auto_rollback_verified"] is True
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_traffic_switched"] is False
