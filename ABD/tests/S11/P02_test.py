from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.decision_gate import (
    DecisionGateAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from decision_gate import (
    DecisionGateError,
    artifact_sha256,
    build_evidence_tiers,
    build_report,
    evaluate_vector,
    validate_registry,
    validate_vector,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S11_P02.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
TIERS = json.loads((ROOT / "evidence_tiers.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "threshold_vectors.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S11-P02"
    assert result["next"] == "S11/P03_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 25
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_evidence_tiers_and_vectors_are_exact_frozen_replays() -> None:
    rebuilt_tiers = build_evidence_tiers(PARAMETERS)
    report = build_report(TIERS, VECTORS, PARAMETERS)
    assert rebuilt_tiers == TIERS
    assert artifact_sha256(rebuilt_tiers) == FIXTURE["expected_evidence_tiers_sha256"]
    assert artifact_sha256(VECTORS) == FIXTURE["expected_threshold_vectors_sha256"]
    assert report["report_sha256"] == FIXTURE["expected_report_sha256"]
    assert VECTORS["expected_report_sha256"] == report["report_sha256"]


@pytest.mark.parametrize(
    ("vector_id", "expected_tier", "expected_minimum_odds"),
    [
        ("V01-E4-STABLE-PASS", "E4", "1.733334"),
        ("V03-E3-BOUNDARY-STABLE-PASS", "E3", "1.766667"),
        ("V04-E2-BOUNDARY-STABLE-PASS", "E2", "1.8"),
        ("V05-E1-BOUNDARY-STABLE-PASS", "E1", "1.816667"),
    ],
)
def test_minimum_odds_formula_is_conservatively_rounded_up(
    vector_id: str, expected_tier: str, expected_minimum_odds: str
) -> None:
    vector = next(row for row in VECTORS["vectors"] if row["vector_id"] == vector_id)
    result = evaluate_vector(vector, TIERS, PARAMETERS)
    baseline = result["baseline"]
    assert baseline["tier"] == expected_tier
    assert baseline["minimum_acceptable_odds"] == expected_minimum_odds
    assert baseline["action"] == "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES"


@pytest.mark.parametrize(
    ("vector_id", "expected_tier", "expected_action", "expected_reason"),
    [
        ("V01-E4-STABLE-PASS", "E4", "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES", "ALL_EVIDENCE_AND_PRICE_GATES_STABLE"),
        ("V02-E4-EXACT-MINIMUM-ODDS-ADVERSE-FLIP", "E4", "NO_RECOMMENDATION", "ADVERSE_STABILITY_FLIP"),
        ("V03-E3-BOUNDARY-STABLE-PASS", "E3", "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES", "ALL_EVIDENCE_AND_PRICE_GATES_STABLE"),
        ("V04-E2-BOUNDARY-STABLE-PASS", "E2", "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES", "ALL_EVIDENCE_AND_PRICE_GATES_STABLE"),
        ("V05-E1-BOUNDARY-STABLE-PASS", "E1", "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES", "ALL_EVIDENCE_AND_PRICE_GATES_STABLE"),
        ("V06-E0-NONPRICE-SOURCES-BELOW-MINIMUM", "E0", "NO_RECOMMENDATION", "EVIDENCE_TIER_E0"),
        ("V07-E4-MODEL-STAGE-BELOW-MINIMUM", "E0", "NO_RECOMMENDATION", "EVIDENCE_TIER_E0"),
        ("V08-E2-DISAGREEMENT-PLUS-POINT-0001", "E0", "NO_RECOMMENDATION", "EVIDENCE_TIER_E0"),
        ("V09-IDENTITY-BELOW-THRESHOLD", "E0", "NO_RECOMMENDATION", "IDENTITY_CONFIDENCE_BELOW_THRESHOLD"),
        ("V10-FEATURE-COMPLETENESS-BELOW-THRESHOLD", "E0", "NO_RECOMMENDATION", "REQUIRED_FEATURE_COMPLETENESS_BELOW_THRESHOLD"),
        ("V11-ODDS-ONE-TICK-BELOW-MINIMUM", "E4", "NO_RECOMMENDATION", "ODDS_BELOW_MINIMUM"),
        ("V12-SOURCE-CONTRACT-FAILS-CLOSED", "E0", "NO_RECOMMENDATION", "SOURCE_CONTRACT_NOT_PASSED"),
    ],
)
def test_e4_to_e0_threshold_vectors_have_one_final_reason_code(
    vector_id: str, expected_tier: str, expected_action: str, expected_reason: str
) -> None:
    vector = next(row for row in VECTORS["vectors"] if row["vector_id"] == vector_id)
    result = evaluate_vector(vector, TIERS, PARAMETERS)
    assert result["baseline"]["tier"] == expected_tier
    assert result["action"] == expected_action
    assert result["reason_code"] == expected_reason
    assert result["all_expected_matches"] is True


def test_exact_minimum_odds_candidate_fails_every_adverse_dimension() -> None:
    vector = next(row for row in VECTORS["vectors"] if row["vector_id"] == FIXTURE["expected_adverse_flip_vector"])
    result = evaluate_vector(vector, TIERS, PARAMETERS)
    assert result["adverse_flip_dimensions"] == FIXTURE["expected_adverse_flip_dimensions"]
    assert set(result["scenarios"]) == set(FIXTURE["expected_adverse_flip_dimensions"])
    assert all(row["action"] == "NO_RECOMMENDATION" for row in result["scenarios"].values())
    assert result["action"] == "NO_RECOMMENDATION"
    assert result["reason_code"] == "ADVERSE_STABILITY_FLIP"


def test_candidate_output_remains_downstream_gated_and_never_an_order() -> None:
    report = build_report(TIERS, VECTORS, PARAMETERS)
    assert report["summary"]["candidate_pending_platform_and_risk_count"] == 4
    assert report["summary"]["no_recommendation_count"] == 8
    assert report["decision"] == "EVIDENCE_TIER_AND_MINIMUM_ODDS_GATE_READY_DOWNSTREAM_PLATFORM_AND_RISK_REQUIRED"
    assert report["external_effect_boundary"]["recommendation_generated_or_enabled"] is False
    assert report["external_effect_boundary"]["order_submission_enabled"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda registry: registry.update({"evidence_tiers_sha256": "f" * 64}),
        lambda registry: registry["vectors"].pop(),
        lambda registry: registry["vectors"][0].update({"observed_odds": 1.9}),
        lambda registry: registry["vectors"][0]["expected"].update({"adverse_flip_dimensions": ["all_adverse", "odds_adverse"]}),
    ],
)
def test_malformed_or_non_fixed_point_vectors_fail_closed(mutate) -> None:
    registry = deepcopy(VECTORS)
    mutate(registry)
    with pytest.raises(DecisionGateError):
        validate_registry(registry, TIERS, PARAMETERS)


def test_deterministic_replay_hash_is_identical_without_waiting() -> None:
    hashes = {
        build_report(TIERS, VECTORS, PARAMETERS)["report_sha256"]
        for _ in range(3)
    }
    assert hashes == {FIXTURE["expected_report_sha256"]}


def test_core_source_has_no_network_process_soak_float_or_order_capability() -> None:
    source = (ROOT / "decision_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection(prohibited)
    assert "sleep(" not in source
    assert "submit_order" not in source
    assert "retry_order" not in source
    assert "float(" not in source


def test_candidate_fails_closed_when_tier_artifact_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "evidence_tiers.json"
    tiers = json.loads(path.read_text(encoding="utf-8"))
    tiers["common_hard_gates"]["identity_confidence_min"] = "0.99"
    path.write_text(json.dumps(tiers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P02-TIERS-VECTORS-AND-REPORT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_fixture_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S11_P02.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_report_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P02-FROZEN-TIERS-VECTORS-AND-REPORT-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_predecessor_receipt_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S11-P01.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["next"] = "S11/P99_READY"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S11P02-PREDECESSOR-P01-SIGNED-AND-REPLAYABLE" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:evidence_tier_minimum_odds_gate"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S11-P02": write_decision_gate_phase_evidence' in source
    assert '"AC-S11-P02": verify_decision_gate_phase_evidence' in source
    with pytest.raises((DecisionGateAcceptanceError, FileNotFoundError)):
        from abd_acceptance.decision_gate import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")


def test_invalid_vector_boolean_and_negative_source_count_fail_closed() -> None:
    vector = deepcopy(VECTORS["vectors"][0])
    vector["quote_usable"] = "true"
    with pytest.raises(DecisionGateError):
        validate_vector(vector)
    vector = deepcopy(VECTORS["vectors"][0])
    vector["independent_price_sources"] = -1
    with pytest.raises(DecisionGateError):
        validate_vector(vector)
