from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.load_test import (
    CORE_PATH,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    FIXTURE_PATH,
    GENERATOR_PATH,
    ORACLE_PATH,
    LoadTestAcceptanceError,
    perform_rollback_drill,
    validate_candidate_preflight,
    write_phase_evidence,
)
from abd_acceptance.load_test_engine import (
    CAPACITY_EVIDENCE_PATH,
    CLAIM_BOUNDARY,
    COSTS_PATH,
    EXPECTED_LOAD_DEFINITION,
    LOAD_PROFILE_PATH,
    RESOURCE_CONTRACT,
    LoadTestInputError,
    artifact_sha256,
    build_artifacts,
    load_fixture,
    strict_json_load,
    validate_artifacts,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))
PROFILE = strict_json_load(ROOT / LOAD_PROFILE_PATH)
CAPACITY = strict_json_load(ROOT / CAPACITY_EVIDENCE_PATH)


def test_candidate_preflight_replays_the_exact_local_load_contract() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["execution_policy"] == EXECUTION_POLICY
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_artifacts_replay_byte_for_value_from_the_frozen_fixture() -> None:
    fixture = load_fixture(ROOT / FIXTURE_PATH)
    expected = build_artifacts(ROOT, fixture)
    assert validate_artifacts(ROOT, fixture) == expected
    assert expected[LOAD_PROFILE_PATH.as_posix()] == PROFILE
    assert expected[CAPACITY_EVIDENCE_PATH.as_posix()] == CAPACITY


@pytest.mark.parametrize("scenario", PROFILE["scenarios"], ids=lambda row: row["scenario_id"])
def test_every_replay_scenario_preserves_every_input_disposition(scenario: dict[str, object]) -> None:
    assert scenario["accounted_count"] == scenario["ingress_count"]
    assert scenario["dropped_count"] == 0
    assert scenario["missing_disposition_count"] == 0
    assert scenario["replay_status"] == "PASS_COUNT_CONSERVING_NO_ACTION"
    assert scenario["action"] == "NO_RECOMMENDATION_NO_ORDER"


@pytest.mark.parametrize("scenario", PROFILE["scenarios"], ids=lambda row: row["scenario_id"])
def test_every_replay_identity_digest_is_deterministic(scenario: dict[str, object]) -> None:
    regenerated = build_artifacts(ROOT, load_fixture(ROOT / FIXTURE_PATH))[LOAD_PROFILE_PATH.as_posix()]
    expected = next(row for row in regenerated["scenarios"] if row["scenario_id"] == scenario["scenario_id"])
    assert scenario["identity_digest"] == expected["identity_digest"]


def test_profile_preserves_frozen_full_history_and_exact_ten_x_load() -> None:
    assert PROFILE["input_mode"] == "FROZEN_SYNTHETIC_FULL_HISTORY_10X_LOAD_NOT_LIVE_VPS"
    assert PROFILE["load_definition"] == EXPECTED_LOAD_DEFINITION
    ten_x = next(row for row in PROFILE["scenarios"] if row["scenario_id"] == "TEN_X_FULL_HISTORY")
    assert ten_x["ingress_count"] == PROFILE["load_definition"]["ten_x_event_count"]
    assert ten_x["load_multiplier"] == PROFILE["load_definition"]["load_multiplier"]


def test_boundary_and_fault_cases_keep_reserve_and_track_quarantine() -> None:
    boundary = next(row for row in PROFILE["scenarios"] if row["scenario_id"] == "TEN_X_BOUNDARY_0_9999")
    fault = next(row for row in PROFILE["scenarios"] if row["scenario_id"] == "TEN_X_TRACKED_FAULT")
    assert boundary["resource_units"] == 9999
    assert boundary["queue_high_water"] == 12000
    assert fault["quarantined_count"] == 1
    assert fault["dropped_count"] == 0
    assert CAPACITY["no_silent_data_loss"] == {
        "all_inputs_accounted": True,
        "silent_drop_count": 0,
        "silent_drop_max": 0,
        "tracked_quarantine_count": 1,
        "missing_disposition_count": 0,
        "passed": True,
    }


def test_vps_gate_is_local_only_and_never_claims_real_measurement_or_deployment() -> None:
    assert CAPACITY["resource_gate"] == {
        "declared_resource_id": "RES-OVH-EXISTING-VPS1",
        "local_envelope_passed": True,
        "actual_vps_capacity_measured": False,
        "actual_vps_capacity_claimed": False,
        "runtime_deployment_allowed": False,
        "on_resource_unavailable_or_limit": "BLOCK_RUNTIME_DEPLOYMENT_KEEP_LOCAL_DEVELOPMENT_AND_EVIDENCE",
        "effective_resource_unit_cap": 9999,
        "maximum_observed_resource_units": 9999,
        "queue_cap": 12000,
        "maximum_observed_queue_high_water": 12000,
    }


def test_artifact_identity_and_hash_links_are_closed() -> None:
    assert PROFILE["artifact_id"] == "ART-S17-P01-02"
    assert PROFILE["source_generator"]["artifact_id"] == "ART-S17-P01-01"
    assert PROFILE["source_generator"]["path"] == "load_test.py"
    assert CAPACITY["artifact_id"] == "ART-S17-P01-03"
    assert CAPACITY["profile_sha256"] == artifact_sha256(PROFILE)
    assert PROFILE["resource_contract"] == RESOURCE_CONTRACT


@pytest.mark.parametrize(
    "mutation",
    [
        lambda fixture: fixture["scenarios"][1].update({"load_multiplier": 9}),
        lambda fixture: fixture["scenarios"][2].update({"resource_units": 10000}),
        lambda fixture: fixture["scenarios"][3].update({"accepted_count": 11998}),
        lambda fixture: fixture["scenarios"][0].update({"action": "RECOMMEND"}),
    ],
    ids=["NOT_TEN_X", "PLUS_0_0001_RESOURCE", "SILENT_DISPOSITION_LOSS", "ACTION_ENABLED"],
)
def test_invalid_load_or_action_mutations_fail_closed(mutation) -> None:
    candidate = deepcopy(FIXTURE)
    mutation(candidate)
    with pytest.raises(LoadTestInputError):
        validate_fixture(candidate)


def test_cost_hash_drift_fails_before_any_capacity_artifact_is_accepted() -> None:
    candidate = deepcopy(FIXTURE)
    candidate["costs_sha256"] = "0" * 64
    with pytest.raises(LoadTestInputError):
        build_artifacts(ROOT, validate_fixture(candidate))


@pytest.mark.parametrize("contract_id", sorted(FIXTURE["predecessors"]))
def test_signed_predecessor_metadata_remains_exact(contract_id: str) -> None:
    expected = FIXTURE["predecessors"][contract_id]
    row = next(item for item in PROFILE["signed_predecessors"] if item["contract_id"] == contract_id)
    assert row == {
        "contract_id": contract_id,
        "evidence_path": expected["evidence_path"],
        "evidence_sha256": expected["evidence_sha256"],
        "status": "PASS",
        "next": expected["next"],
    }


def test_load_outputs_preserve_the_no_runtime_and_no_return_claim_boundary() -> None:
    for artifact in (PROFILE, CAPACITY):
        assert artifact["claim_boundary"] == CLAIM_BOUNDARY
        assert artifact["claim_boundary"]["real_vps_resource_observed_or_measured"] is False
        assert artifact["claim_boundary"]["order_submission_enabled"] is False
        assert artifact["claim_boundary"]["production_deployed_or_activated"] is False
        assert artifact["claim_boundary"]["real_time_soak_waited"] is False
    assert CAPACITY["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert CAPACITY["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_rollback_is_local_only_and_keeps_runtime_blocked() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["feature_flag_id"] == FEATURE_FLAG_ID
    assert result["external_state_changed"] is False
    assert result["production_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_vps_resource_observed_or_measured"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


def test_execution_policy_blocks_full_regression_soak_and_external_runtime() -> None:
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "phase_test_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "real_vps_load_or_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "incremental_cash_spent_aud": "0.00",
    }


def test_core_oracle_and_generator_have_no_network_process_wait_or_order_capability() -> None:
    imports: set[str] = set()
    call_names: set[str] = set()
    for path in (CORE_PATH, ORACLE_PATH, GENERATOR_PATH):
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
                call_names.add(node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "smtplib"})
    assert not call_names.intersection({"sleep", "Popen", "submit_order", "retry_order"})


def test_acceptance_cli_is_wired_to_the_exact_phase_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S17-P01": write_load_test_phase_evidence' in source
    assert '"AC-S17-P01": verify_load_test_phase_evidence' in source


def test_writer_refuses_noncanonical_evidence_directory_without_writing() -> None:
    with pytest.raises(LoadTestAcceptanceError, match="canonical machine/evidence"):
        write_phase_evidence(ROOT, ROOT / "machine/not-evidence")


def test_input_paths_are_current_local_artifacts() -> None:
    assert (ROOT / COSTS_PATH).is_file()
    assert (ROOT / LOAD_PROFILE_PATH).is_file()
    assert (ROOT / CAPACITY_EVIDENCE_PATH).is_file()
