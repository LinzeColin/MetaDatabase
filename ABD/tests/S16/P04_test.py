"""Targeted frozen tests for the S16/P04 model-system card and dual gate."""

from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path

import pytest

from abd_acceptance.model_release_engine import (
    CLAIM_BOUNDARY,
    RELEASE_GATE_PATH,
    SYSTEM_CARD_PATH,
    ModelReleaseInputError,
    build_artifacts,
    canonical_json_bytes,
    load_fixture,
    strict_json_load,
    validate_fixture,
)
from abd_acceptance.model_release_gate import (
    EXTERNAL_EFFECT_BOUNDARY,
    FEATURE_FLAG_ID,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)


ROOT = Path(__file__).resolve().parents[2]
RAW_FIXTURE = strict_json_load(ROOT / "machine/tests/fixtures/S16_P04.json")
STATE = load_fixture(ROOT)
ARTIFACTS = build_artifacts(ROOT, RAW_FIXTURE)
CARD = ARTIFACTS[SYSTEM_CARD_PATH.as_posix()]
GATE = ARTIFACTS[RELEASE_GATE_PATH.as_posix()]


def test_fixture_identity_and_scope_are_frozen() -> None:
    fixture = STATE["fixture"]
    assert fixture["contract_id"] == "AC-S16-P04"
    assert fixture["requirement_id"] == "REQ-S16-P04"
    assert fixture["expected_next"] == "S16/STAGE_REVIEW_READY_NOT_STARTED"
    assert fixture["claim_boundary"] == CLAIM_BOUNDARY


@pytest.mark.parametrize("index,stage", list(enumerate(("ALPHA", "BETA", "GA"))))
def test_lifecycle_profiles_are_bound_to_frozen_risk_stages(index: int, stage: str) -> None:
    profile = CARD["lifecycle_profiles"][index]
    assert profile["stage"] == stage
    assert profile["current_status"] != "ACTIVATED"
    assert "authorized release path" in profile["required_before_any_operational_transition"]


def test_system_card_preserves_analysis_only_and_final_owner_order_boundary() -> None:
    assert CARD["operational_boundary"] == {
        "product_role": "ANALYSIS_AND_ADVICE_ONLY",
        "order_submission_module_present": False,
        "normal_owner_action": "FINAL_ORDER_ONLY",
        "paid_data_api_required": False,
        "single_host_zero_downtime_guaranteed": False,
        "actual_return_requires_verified_execution_evidence": True,
    }
    assert "30%月复利不能被保证" in CARD["known_limitations"]
    assert CARD["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"


def test_actual_software_pass_does_not_turn_the_model_gate_into_a_pass() -> None:
    assert GATE["software_gate"]["passed"] is True
    assert GATE["software_gate"]["status"] == "PASS_LOCAL_SOFTWARE_EVIDENCE_ONLY"
    assert GATE["model_gate"]["passed"] is False
    assert GATE["model_gate"]["status"] == "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT"
    assert GATE["model_gate"]["activation_allowed"] is False
    assert GATE["gate_independence"]["software_pass_can_replace_model_pass"] is False
    assert GATE["summary"]["deployment_allowed"] is False


@pytest.mark.parametrize(
    "field",
    [
        "external_network_accessed",
        "real_market_or_odds_observed",
        "order_submission_enabled",
        "production_deployed_or_activated",
        "model_activation_enabled",
    ],
)
def test_claim_boundary_prohibits_external_effects(field: str) -> None:
    assert CARD["claim_boundary"][field] is False
    assert GATE["claim_boundary"][field] is False
    assert EXTERNAL_EFFECT_BOUNDARY[field] is False


@pytest.mark.parametrize("case", GATE["frozen_control_cases"])
def test_each_frozen_control_case_remains_release_blocked(case: dict[str, object]) -> None:
    assert case["release_allowed"] is False
    assert case["classification"] == "FROZEN_LOGICAL_CONTROL_CASE_NOT_MODEL_OR_RELEASE_EVIDENCE"


@pytest.mark.parametrize("index", list(range(7)))
def test_each_gate_case_has_the_expected_fail_closed_reason(index: int) -> None:
    assert GATE["frozen_control_cases"][index]["reason_code"] == RAW_FIXTURE["gate_cases"][index]["expected_reason"]


def test_adverse_one_in_ten_thousand_boundary_does_not_authorize_release() -> None:
    first, fifth = GATE["frozen_control_cases"][0], GATE["frozen_control_cases"][4]
    assert first["adverse_probability_delta"] == fifth["adverse_probability_delta"] == "-0.0001"
    assert first["release_allowed"] is fifth["release_allowed"] is False


def test_plus_or_minus_one_in_ten_thousand_configuration_drift_fails_closed() -> None:
    market_prior_case = GATE["frozen_control_cases"][5]
    residual_case = GATE["frozen_control_cases"][6]
    assert market_prior_case["market_prior_weight"] == "0.4999"
    assert market_prior_case["reason_code"] == "MARKET_PRIOR_WEIGHT_BELOW_MIN"
    assert residual_case["residual_weight"] == "0.3501"
    assert residual_case["reason_code"] == "RESIDUAL_WEIGHT_ABOVE_STAGE_CAP"


def test_hypothetical_all_gate_true_control_is_still_not_a_deployment_authorization() -> None:
    control = GATE["frozen_control_cases"][3]
    assert control["software_gate_passed"] is True
    assert control["model_empirical_increment_verified"] is True
    assert control["stage_review_passed"] is True
    assert control["reason_code"] == "P04_PHASE_NOT_A_DEPLOYMENT_AUTHORIZATION"
    assert control["release_allowed"] is False


def test_replay_is_byte_stable_for_identical_inputs() -> None:
    first = build_artifacts(ROOT, copy.deepcopy(RAW_FIXTURE))
    second = build_artifacts(ROOT, copy.deepcopy(RAW_FIXTURE))
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert hashlib.sha256(canonical_json_bytes(first)).hexdigest() == hashlib.sha256(canonical_json_bytes(second)).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("contract_id", "AC-S16-P03"),
        lambda value: value["p03_evidence"].__setitem__("evidence_sha256", "f" * 64),
        lambda value: value["software_evidence"].__setitem__("status", "FAIL"),
        lambda value: value["lifecycle_profiles"][1].__setitem__("configured_single_ticket_cap", "0.0151"),
        lambda value: value["gate_cases"][6].__setitem__("expected_reason", "MODEL_GATE_NOT_PASSED"),
    ],
)
def test_fixture_identity_predecessor_and_boundary_mutations_fail_closed(mutation: object) -> None:
    raw = copy.deepcopy(RAW_FIXTURE)
    mutation(raw)
    with pytest.raises(ModelReleaseInputError):
        validate_fixture(ROOT, raw)


def test_oracle_static_boundary_has_no_network_or_process_imports() -> None:
    imports: set[str] = set()
    for relative in ("model_release_gate.py", "abd_acceptance/model_release_engine.py", "abd_acceptance/model_release_gate.py"):
        for node in ast.walk(ast.parse((ROOT / relative).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"})


def test_candidate_preflight_passes_before_report_signing() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS"
    assert result["decision"] == RAW_FIXTURE["expected_decision"]
    assert result["next"] == RAW_FIXTURE["expected_next"]


def test_contract_evaluation_remains_phase_scoped_before_report_signing() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False)
    assert result["summary"]["failed"] == 0
    assert result["execution_policy"]["phase_test_only"] is True
    assert result["execution_policy"]["full_regression_or_real_time_soak_allowed"] is False


def test_rollback_is_local_and_keeps_model_and_release_blocked() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["model_activation_enabled"] is False
    assert rollback["order_submission_enabled"] is False


def test_generator_wrapper_is_a_local_engine_entrypoint() -> None:
    source = (ROOT / "model_release_gate.py").read_text(encoding="utf-8")
    assert "abd_acceptance.model_release_engine" in source
    assert "main" in source
