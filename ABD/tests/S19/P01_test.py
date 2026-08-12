from __future__ import annotations

import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256
from abd_acceptance.walking_skeleton import (
    EXTERNAL_EFFECT_BOUNDARY,
    LIFECYCLE_STEPS,
    SAFE_FUND_FACTS,
    SAFE_RISK_GATE,
    WalkingSkeletonInputError,
    build_software_alpha_artifact,
    build_walking_skeleton_artifact,
    evaluate_walking_skeleton,
)
from abd_acceptance.walking_skeleton_acceptance import (
    ALPHA_ARTIFACT_PATH,
    CONTRACT_ID,
    CORE_PATH,
    FIXTURE_PATH,
    WALKING_ARTIFACT_PATH,
    WalkingSkeletonAcceptanceError,
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


def test_fixture_is_exact_s19_p01_contract() -> None:
    assert validate_fixture(FIXTURE) == FIXTURE
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S19/P02_READY_NOT_STARTED"
    assert FIXTURE_PATH.as_posix() == "machine/tests/fixtures/S19_P01.json"


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda item: item["scenario_id"])
def test_each_frozen_scenario_has_its_pinned_no_order_result(scenario: dict) -> None:
    plan = evaluate_walking_skeleton(scenario["cycle_input"])
    assert {key: plan[key] for key in scenario["expected"]} == scenario["expected"]
    assert plan["action"] == "NO_RECOMMENDATION"
    assert plan["fund_facts_before"] == plan["fund_facts_after"] == SAFE_FUND_FACTS
    assert plan["risk_gate_before"] == plan["risk_gate_after"] == SAFE_RISK_GATE
    assert plan["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert plan["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"


def test_golden_lifecycle_closes_discovery_to_recovery_locally_only() -> None:
    plan = evaluate_walking_skeleton(_scenario("GOLDEN_LOCAL_CLOSED_LOOP")["cycle_input"])
    assert plan["status"] == "PASS"
    assert plan["decision"] == "LOCAL_ALPHA_CLOSED_LOOP_NO_ORDER"
    assert [item["step"] for item in plan["lifecycle"]] == list(LIFECYCLE_STEPS)
    assert plan["lifecycle"][1]["status"] == "ADVICE_PROJECTION_NO_ORDER"
    assert plan["lifecycle"][2]["status"] == "INVALIDATED_TO_NO_RECOMMENDATION"
    assert plan["lifecycle"][5]["status"] == "LOCAL_EVIDENCE_PROJECTION_NOT_SENT"


def test_one_in_ten_thousand_adverse_vector_keeps_the_no_order_gate() -> None:
    plan = evaluate_walking_skeleton(_scenario("ADVERSE_ONE_IN_TEN_THOUSAND_PRESERVES_NO_ORDER")["cycle_input"])
    assert plan["status"] == "PASS"
    assert plan["probability_delta"] == "-0.0001"
    assert plan["odds_tick_delta"] == -1
    assert plan["action"] == "NO_RECOMMENDATION"
    assert plan["risk_gate_after"] == SAFE_RISK_GATE


@pytest.mark.parametrize("mutation", ["duplicate_step", "float_delta", "unknown_market"], ids=lambda item: item)
def test_malformed_cycle_input_fails_before_it_can_be_interpreted(mutation: str) -> None:
    payload = deepcopy(_scenario("GOLDEN_LOCAL_CLOSED_LOOP")["cycle_input"])
    if mutation == "duplicate_step":
        payload["lifecycle_steps"][-1] = "REPLAY"
    elif mutation == "float_delta":
        payload["probability_delta"] = 0.0
    else:
        payload["market"]["market_id"] = "UNFROZEN"
    with pytest.raises(WalkingSkeletonInputError):
        evaluate_walking_skeleton(payload)


def test_plan_replay_is_content_addressed_and_deterministic() -> None:
    payload = _scenario("GOLDEN_LOCAL_CLOSED_LOOP")["cycle_input"]
    first = evaluate_walking_skeleton(payload)
    second = evaluate_walking_skeleton(payload)
    assert first == second
    assert first["walking_skeleton_plan_sha256"] == second["walking_skeleton_plan_sha256"]


def test_software_alpha_artifacts_remain_local_and_not_a_return_claim() -> None:
    plan = evaluate_walking_skeleton(_scenario("GOLDEN_LOCAL_CLOSED_LOOP")["cycle_input"])
    first_walking = build_walking_skeleton_artifact(plan, fixture_sha256=sha256_file(ROOT / FIXTURE_PATH), predecessor_evidence_sha256=FIXTURE["predecessors"])
    second_walking = build_walking_skeleton_artifact(plan, fixture_sha256=sha256_file(ROOT / FIXTURE_PATH), predecessor_evidence_sha256=FIXTURE["predecessors"])
    assert first_walking == second_walking
    alpha = build_software_alpha_artifact(first_walking)
    assert first_walking["artifact_id"] == "ART-S19-P01-01"
    assert alpha["artifact_id"] == "ART-S19-P01-02"
    assert alpha["alpha_status"] == "SOFTWARE_ALPHA_LOCAL_ONLY_NOT_DEPLOYED"
    assert alpha["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert alpha["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert alpha["activation_conditions"]["actual_order_submission_enabled"] is False


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
    assert result["next"] == "S19/P02_READY_NOT_STARTED"
    assert result["execution_policy"]["full_regression_or_real_time_soak_allowed"] is False
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY


def test_generated_artifact_paths_are_stable_before_and_after_signing() -> None:
    assert WALKING_ARTIFACT_PATH.as_posix() == "walking_skeleton_evidence.json"
    assert ALPHA_ARTIFACT_PATH.as_posix() == "software_alpha_gate.json"


def test_evidence_build_is_deterministic_before_signing() -> None:
    first = build_evidence(ROOT, require_test_reports=False, require_generated_artifacts=False)
    assert first[0]["decision"] == "S19_P01_WALKING_SKELETON_AND_SOFTWARE_ALPHA_PASS_P02_REQUIRED"
    assert first[0]["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"


def test_cli_and_legacy_successor_chain_are_exact() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S19-P01": verify_walking_skeleton_phase_evidence,' in source
    assert '"AC-S19-P01": write_walking_skeleton_phase_evidence,' in source
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / "abd_acceptance/__main__.py")


def test_rollback_drill_is_local_and_preserves_s18_receipt() -> None:
    rollback = perform_rollback_drill(ROOT)
    expected = "PASS" if all((ROOT / path).is_file() for path in (WALKING_ARTIFACT_PATH, ALPHA_ARTIFACT_PATH)) else "FAIL"
    assert rollback["status"] == expected
    assert rollback["feature_flag_id"] == "walking_skeleton:s19_p01_local_only"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S18-P04.json"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_existing_evidence_verifier_fails_closed_when_no_signed_evidence_exists() -> None:
    with pytest.raises((WalkingSkeletonAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
