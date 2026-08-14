from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.robustness_gate import (
    RobustnessGateAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from robustness_gate import (
    RobustnessGateError,
    build_report,
    evaluate_vector,
    report_sha256,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S10_P04.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "boundary_vectors.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _prepare_required_reports(clone: Path) -> None:
    junit = clone / "machine/evidence/S10/P04/pytest.xml"
    junit.parent.mkdir(parents=True, exist_ok=True)
    cases = "".join('<testcase classname="S10.P04" name="case%d" time="0.000" />' % number for number in range(18))
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest" tests="18" failures="0" errors="0" skipped="0" timestamp="2026-07-19T00:00:00+10:00" time="0.000">%s</testsuite></testsuites>\n'
        % cases,
        encoding="utf-8",
    )
    scan = clone / "machine/evidence/S10/P04/paid_dependency_scan.txt"
    scan.write_text("STATUS: PASS\nPAID_OR_UNKNOWN_DEPENDENCIES: 0\n", encoding="utf-8")
    source_report = ROOT / "machine/evidence/validation_report.json"
    (clone / "machine/evidence/validation_report.json").write_bytes(source_report.read_bytes())


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S10-P04"
    assert result["next"] == "S10/STAGE_REVIEW_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 24
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_frozen_robustness_report_is_exact_replay() -> None:
    report = build_report(REGISTRY, PARAMETERS)
    assert report_sha256(report) == FIXTURE["expected_report_sha256"]
    assert report["report_sha256"] == FIXTURE["expected_report_sha256"]
    assert report["decision"] == "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED"
    assert report["next"] == "S10/STAGE_REVIEW_READY_NOT_STARTED"


def test_all_frozen_hard_boundary_cases_match_their_expected_result() -> None:
    report = build_report(REGISTRY, PARAMETERS)
    assert report["all_hard_boundary_expectations_match"] is True
    assert report["all_adverse_action_flips_force_no_recommendation"] is True
    assert report["base_no_recommendations_remain_closed"] is True
    assert len(report["results"]) == 12
    assert all(row["all_expected_matches"] is True for row in report["results"])


@pytest.mark.parametrize(
    ("vector_id", "dimension"),
    [
        ("V02-PROBABILITY-MINUS-FLIPS", "probability_minus"),
        ("V04-THRESHOLD-PLUS-FLIPS", "threshold_plus"),
        ("V05-FRICTION-PLUS-FLIPS", "friction_plus"),
        ("V06-TIME-PLUS-FLIPS", "time_plus"),
        ("V08-ODDS-TICK-FLIPS", "odds_adverse"),
    ],
)
def test_each_required_adverse_dimension_forces_no_recommendation(vector_id: str, dimension: str) -> None:
    results = {row["vector_id"]: row for row in build_report(REGISTRY, PARAMETERS)["results"]}
    row = results[vector_id]
    assert dimension in row["adverse_flip_dimensions"]
    assert row["baseline"]["action"] == "NO_ORDER_NUMERIC_CANDIDATE"
    assert row["gate_action"] == "NO_RECOMMENDATION"


@pytest.mark.parametrize(
    "vector_id",
    [
        "V01-ROBUST-ALL-MARGINS",
        "V07-TIME-PLUS-BOUNDARY-STABLE",
        "V09-ODDS-TICK-BOUNDARY-STABLE",
    ],
)
def test_stable_boundary_cases_remain_candidates_when_no_adverse_action_flips(vector_id: str) -> None:
    results = {row["vector_id"]: row for row in build_report(REGISTRY, PARAMETERS)["results"]}
    row = results[vector_id]
    assert row["adverse_flip_dimensions"] == []
    assert row["gate_action"] == "NO_ORDER_NUMERIC_CANDIDATE"


def test_combined_adverse_scenario_catches_joint_boundary_failure() -> None:
    results = {row["vector_id"]: row for row in build_report(REGISTRY, PARAMETERS)["results"]}
    row = results["V11-COMBINED-ONLY-FLIPS"]
    assert row["adverse_flip_dimensions"] == ["all_adverse"]
    assert row["scenarios"]["probability_minus"]["action"] == "NO_ORDER_NUMERIC_CANDIDATE"
    assert row["scenarios"]["friction_plus"]["action"] == "NO_ORDER_NUMERIC_CANDIDATE"
    assert row["scenarios"]["all_adverse"]["action"] == "NO_RECOMMENDATION"
    assert row["gate_action"] == "NO_RECOMMENDATION"


def test_favourable_diagnostics_never_enable_a_baseline_no_recommendation() -> None:
    results = {row["vector_id"]: row for row in build_report(REGISTRY, PARAMETERS)["results"]}
    row = results["V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES"]
    assert row["baseline"]["action"] == "NO_RECOMMENDATION"
    assert row["scenarios"]["probability_plus"]["action"] == "NO_ORDER_NUMERIC_CANDIDATE"
    assert row["scenarios"]["threshold_minus"]["action"] == "NO_ORDER_NUMERIC_CANDIDATE"
    assert row["gate_action"] == "NO_RECOMMENDATION"


def test_fixed_input_replay_is_identical() -> None:
    first = build_report(REGISTRY, PARAMETERS)
    second = build_report(deepcopy(REGISTRY), deepcopy(PARAMETERS))
    assert first == second
    assert report_sha256(first) == report_sha256(second)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda registry, parameters: registry.update({"contract_id": "AC-S10-P05"}),
        lambda registry, parameters: registry.update({"unexpected": True}),
        lambda registry, parameters: registry["vectors"][0].update({"conservative_probability": 0}),
        lambda registry, parameters: registry["vectors"].__setitem__(1, deepcopy(registry["vectors"][0])),
        lambda registry, parameters: parameters["numeric_determinism"].update({"odds_rounding": "UP"}),
    ],
)
def test_malformed_or_drifted_registry_or_parameters_fail_closed(mutate) -> None:
    registry = deepcopy(REGISTRY)
    parameters = deepcopy(PARAMETERS)
    mutate(registry, parameters)
    with pytest.raises(RobustnessGateError):
        validate_registry(registry, parameters)


def test_invalid_adverse_domain_fails_closed() -> None:
    vector = deepcopy(REGISTRY["vectors"][0])
    vector["odds"] = "1.000000"
    with pytest.raises(RobustnessGateError):
        evaluate_vector(vector, REGISTRY["numeric_determinism"])


def test_report_hash_detects_any_result_tampering() -> None:
    report = deepcopy(build_report(REGISTRY, PARAMETERS))
    report["results"][0]["scenarios"]["baseline"]["stake_cents"] = 999
    assert report_sha256(report) != FIXTURE["expected_report_sha256"]


def test_core_source_has_no_network_process_soak_float_or_order_capability() -> None:
    source = (ROOT / "robustness_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"})
    assert "sleep(" not in source
    assert "submit_order" not in source
    assert "retry_order" not in source
    assert "float(" not in source


def test_candidate_fails_closed_when_expected_report_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S10_P04.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_report_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P04-FROZEN-ROBUSTNESS-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_frozen_vector_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "boundary_vectors.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["vectors"][0]["friction"] = "0.0350000001"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P04-FROZEN-ROBUSTNESS-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p03_predecessor_is_changed(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S10-P03.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["status"] = "FAIL"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P04-P03-PREDECESSOR-HASH" in result["summary"]["failed_check_ids"]


def test_existing_evidence_fails_closed_when_index_binding_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    _prepare_required_reports(clone)
    write_phase_evidence(clone, clone / "machine/evidence")
    path = clone / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["id"] == "INDEX-AC-S10-P04":
            row["artifact_sha256"] = "f" * 64
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(RobustnessGateAcceptanceError):
        verify_existing_phase_evidence(clone)


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:adverse_perturbation_gate"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S10-P04": write_robustness_gate_phase_evidence' in source
    assert '"AC-S10-P04": verify_robustness_gate_phase_evidence' in source
    with pytest.raises((RobustnessGateAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
