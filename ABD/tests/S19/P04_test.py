from __future__ import annotations

import ast
import io
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.final_delivery_acceptance import (
    BUNDLE_MEMBERS,
    CONTRACT_ID,
    EVIDENCE_PATH,
    FINAL_ACCEPTANCE_PATH,
    FIXTURE_PATH,
    HANDOFF_BUNDLE_PATH,
    ORACLE_PATH,
    RELEASE_MANIFEST_PATH,
    FinalDeliveryAcceptanceError,
    FinalDeliveryInputError,
    build_evidence,
    evaluate_contract,
    evaluate_final_delivery,
    load_fixture,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_fixture,
    verify_existing_phase_evidence,
    write_core_artifacts,
)
from abd_acceptance.canonical_facts import sha256_file
from abd_acceptance.legacy_receipt_compatibility import approved_successor_sha256


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = validate_fixture(load_fixture(ROOT / FIXTURE_PATH))


def _scenario(identifier: str) -> dict:
    return deepcopy(next(item for item in FIXTURE["scenarios"] if item["scenario_id"] == identifier))


def test_fixture_identity_and_expected_bundle_are_frozen() -> None:
    assert FIXTURE["contract_id"] == CONTRACT_ID
    assert FIXTURE["expected_next"] == "S19/STAGE_REVIEW_READY_NOT_STARTED"
    assert FIXTURE["expected_bundle_members"] == [path.as_posix() for path in BUNDLE_MEMBERS]


def test_all_frozen_scenarios_replay_deterministically() -> None:
    for scenario in FIXTURE["scenarios"]:
        first = evaluate_final_delivery(scenario["final_input"])
        second = evaluate_final_delivery(scenario["final_input"])
        assert first == second
        assert all(first[key] == value for key, value in scenario["expected"].items())
        assert first["action"] == "NO_RECOMMENDATION"
        assert first["order_submission_allowed"] is False


def test_one_in_ten_thousand_adverse_vector_remains_stable_and_no_recommendation() -> None:
    result = evaluate_final_delivery(_scenario("ADVERSE_ONE_IN_TEN_THOUSAND_STABLE")["final_input"])
    assert result["status"] == "PASS_LOCAL_FINAL_DELIVERY_GATE"
    assert result["adverse_probability_delta"] == "-0.0001"
    assert result["adverse_odds_tick_delta"] == -1
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["production_deployment_allowed"] is False


def test_failure_vectors_are_fail_closed_without_runtime_or_order_effects() -> None:
    version = evaluate_final_delivery(_scenario("VERSION_CONFLICT_FAILS_CLOSED")["final_input"])
    source = evaluate_final_delivery(_scenario("SOURCE_HASH_CONFLICT_FAILS_CLOSED")["final_input"])
    empirical = evaluate_final_delivery(_scenario("EMPIRICAL_RUNTIME_CLAIM_FAILS_CLOSED")["final_input"])
    stopped = evaluate_final_delivery(_scenario("STOP_CONDITION_FAILS_CLOSED")["final_input"])
    unsafe = evaluate_final_delivery(_scenario("UNSAFE_RUNTIME_REQUESTS_FAIL_CLOSED")["final_input"])
    relaxed = evaluate_final_delivery(_scenario("RISK_RELAXATION_ATTEMPT_FAILS_CLOSED")["final_input"])
    assert version["failure_codes"] == ["VERSION_CONFLICT"]
    assert source["failure_codes"] == ["SOURCE_HASH_CONFLICT"]
    assert empirical["failure_codes"] == ["EMPIRICAL_OR_RUNTIME_CLAIM_NOT_VERIFIABLE_IN_FROZEN_LOCAL_EVALUATOR"]
    assert stopped["failure_codes"] == ["STOP_CONDITION_TRIGGERED"]
    assert unsafe["failure_codes"] == [
        "EXTERNAL_RUNTIME_REQUESTED",
        "ACTUAL_ORDER_REQUESTED",
        "REAL_FUND_MUTATION_REQUESTED",
        "REAL_MAIL_SEND_REQUESTED",
        "PRODUCTION_DEPLOY_REQUESTED",
    ]
    assert relaxed["failure_codes"] == ["RISK_GATE_RELAXATION_ATTEMPT", "PRODUCTION_EQUIVALENT_CONFIG_CONFLICT"]
    assert all(result["action"] == "NO_RECOMMENDATION" for result in (version, source, empirical, stopped, unsafe, relaxed))


@pytest.mark.parametrize("mutation", FIXTURE["malformed_inputs"], ids=lambda item: item["case_id"])
def test_malformed_inputs_are_rejected(mutation: dict) -> None:
    payload = _scenario("GOLDEN_LOCAL_FINAL_DELIVERY_STAGE_REVIEW_REQUIRED")["final_input"]
    if mutation["mutation"] == "float_probability_delta":
        payload["probability_delta"] = 0.0
    elif mutation["mutation"] == "unknown_artifact_hash":
        payload["artifact_hashes"]["unknown.json"] = "0" * 64
    elif mutation["mutation"] == "boolean_odds_tick":
        payload["odds_tick_delta"] = True
    elif mutation["mutation"] == "missing_runtime_field":
        del payload["actual_runtime_observation"]["return_status"]
    elif mutation["mutation"] == "non_boolean_config":
        payload["release_config"]["owner_final_order_only"] = "true"
    elif mutation["mutation"] == "unknown_delta":
        payload["probability_delta"] = "-0.0002"
    else:
        raise AssertionError("unknown frozen mutation")
    with pytest.raises(FinalDeliveryInputError):
        evaluate_final_delivery(payload)


def test_core_artifacts_and_non_secret_bundle_are_deterministic() -> None:
    final_one, manifest_one, bundle_one = write_core_artifacts(ROOT)
    final_two, manifest_two, bundle_two = write_core_artifacts(ROOT)
    assert final_one == final_two
    assert manifest_one == manifest_two
    assert bundle_one == bundle_two
    assert final_one["artifact_id"] == "ART-S19-P04-01"
    assert final_one["status"] == "PASS_LOCAL_FINAL_ACCEPTANCE_STAGE_REVIEW_REQUIRED"
    assert final_one["runtime_and_return_boundary"]["return_or_roi_verified"] is False
    assert manifest_one["artifact_id"] == "ART-S19-P04-02"
    assert manifest_one["version_and_hash_status"] == "UNAMBIGUOUS_NO_CONFLICT"
    assert FINAL_ACCEPTANCE_PATH.as_posix() == "final_acceptance.json"
    assert RELEASE_MANIFEST_PATH.as_posix() == "release_manifest.json"
    assert HANDOFF_BUNDLE_PATH.as_posix() == "handoff_bundle.zip"
    with zipfile.ZipFile(io.BytesIO(bundle_one), mode="r") as archive:
        assert archive.namelist() == [path.as_posix() for path in BUNDLE_MEMBERS]
        assert archive.testzip() is None
        for path in BUNDLE_MEMBERS:
            assert archive.read(path.as_posix()) == (ROOT / path).read_bytes()


def test_core_has_no_runtime_network_process_mail_or_sleep_capability() -> None:
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
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


def test_candidate_preflight_passes_but_marks_runtime_and_return_unverified() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == CONTRACT_ID
    assert result["next"] == "S19/STAGE_REVIEW_READY_NOT_STARTED"
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["execution_policy"]["full_regression_or_real_time_soak_allowed"] is False


def test_evidence_build_is_deterministic_before_signing() -> None:
    evidence, rollback = build_evidence(ROOT, require_test_reports=False, require_generated_artifacts=False)
    assert evidence["decision"] == "S19_P04_LOCAL_FINAL_DELIVERY_PASS_STAGE_REVIEW_REQUIRED"
    assert evidence["actual_ga_status"] == "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
    assert evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S19-P03.json"
    assert rollback["real_time_soak_waited"] is False


def test_cli_and_legacy_successor_chain_are_exact() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S19-P04": verify_final_delivery_phase_evidence,' in source
    assert '"AC-S19-P04": write_final_delivery_phase_evidence,' in source
    assert approved_successor_sha256(ROOT, "abd_acceptance/__main__.py") == sha256_file(ROOT / "abd_acceptance/__main__.py")


def test_rollback_drill_is_local_and_preserves_s19_p03_receipt() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "release:s19_p04_local_final_delivery_gate"
    assert rollback["previous_signed_artifact"] == "machine/evidence/EVD-S19-P03.json"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["actual_ga_activation_enabled"] is False
    assert rollback["real_time_soak_waited"] is False


def test_existing_evidence_verifier_fails_closed_when_no_signed_evidence_exists() -> None:
    with pytest.raises((FinalDeliveryAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")


def test_oracle_reports_all_local_preflight_checks_before_signing() -> None:
    result = evaluate_contract(ROOT, require_test_reports=False, require_generated_artifacts=False)
    assert result["status"] == "PASS", result
    assert all(item["passed"] for item in result["checks"])
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S19-P04.json"
