from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.decimal_math import (
    DecimalMathAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from cross_impl_check import (
    CrossImplementationError,
    build_report,
    independent_evaluate_vector,
    report_sha256,
    validate_registry,
)
from decimal_math import (
    NumericContractError,
    evaluate_vector,
    normalize_friction,
    normalize_odds,
    normalize_probability,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S10_P03.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "numeric_vectors.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _prepare_required_reports(clone: Path) -> None:
    junit = clone / "machine/evidence/S10/P03/pytest.xml"
    junit.parent.mkdir(parents=True, exist_ok=True)
    cases = "".join('<testcase classname="S10.P03" name="case%d" time="0.000" />' % number for number in range(18))
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest" tests="18" failures="0" errors="0" skipped="0" timestamp="2026-07-19T00:00:00+10:00" time="0.000">%s</testsuite></testsuites>\n'
        % cases,
        encoding="utf-8",
    )
    scan = clone / "machine/evidence/S10/P03/paid_dependency_scan.txt"
    scan.write_text("STATUS: PASS\nPAID_OR_UNKNOWN_DEPENDENCIES: 0\n", encoding="utf-8")
    source_report = ROOT / "machine/evidence/validation_report.json"
    (clone / "machine/evidence/validation_report.json").write_bytes(source_report.read_bytes())


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S10-P03"
    assert result["next"] == "S10/P04_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 23
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_frozen_cross_report_is_exact_replay() -> None:
    report = build_report(REGISTRY, PARAMETERS)
    assert report_sha256(report) == FIXTURE["expected_report_sha256"]
    assert report["report_sha256"] == FIXTURE["expected_report_sha256"]
    assert report["decision"] == "DECIMAL_FIXED_POINT_READY_DOWNSTREAM_ROBUSTNESS_GATE_REQUIRED"
    assert report["next"] == "S10/P04_READY_NOT_STARTED"


def test_all_vectors_are_within_tolerance_with_exact_actions_and_stakes() -> None:
    report = build_report(REGISTRY, PARAMETERS)
    assert report["max_abs_difference"] == "0"
    assert report["all_within_tolerance"] is True
    assert report["actions_all_match"] is True
    assert report["stakes_all_match"] is True
    for row in report["results"]:
        assert Decimal(row["max_abs_difference"]) <= Decimal("1e-12")
        assert row["actions_match"] is True
        assert row["stakes_match"] is True
        assert row["authoritative"]["action"] == row["independent"]["action"]
        assert row["authoritative"]["stake_cents"] == row["independent"]["stake_cents"]


def test_positive_and_guard_classifications_are_frozen() -> None:
    results = {row["vector_id"]: row["authoritative"] for row in build_report(REGISTRY, PARAMETERS)["results"]}
    assert results["V01-POSITIVE-CAPPED"] == {
        "vector_id": "V01-POSITIVE-CAPPED",
        "conservative_probability": "0.615",
        "odds": "1.9",
        "friction": "0.015000001",
        "net_edge": "0.153499999",
        "kelly_fraction": "0.02",
        "stake_cents": 600,
        "action": "NO_ORDER_NUMERIC_CANDIDATE",
    }
    assert results["V02-NONPOSITIVE-ROUND-UP-FRICTION"]["action"] == "NO_RECOMMENDATION_NUMERIC_GUARD"
    assert results["V03-PROBABILITY-ODDS-SCALE-DOWN"]["action"] == "NO_RECOMMENDATION_NUMERIC_GUARD"


def test_fixed_input_replay_is_identical() -> None:
    first = build_report(REGISTRY, PARAMETERS)
    second = build_report(deepcopy(REGISTRY), deepcopy(PARAMETERS))
    assert first == second
    assert report_sha256(first) == report_sha256(second)


def test_probability_odds_round_down_and_friction_round_up() -> None:
    assert normalize_probability("0.6150000004") == Decimal("0.615000000")
    assert normalize_odds("1.9000009") == Decimal("1.900000")
    assert normalize_friction("0.0150000001") == Decimal("0.015000001")


def test_integer_cents_and_provider_increment_round_down() -> None:
    vector = next(row for row in REGISTRY["vectors"] if row["vector_id"] == "V04-POSITIVE-INCREMENT-ROUND-DOWN")
    result = evaluate_vector(vector, REGISTRY["numeric_contract"])
    assert type(result["stake_cents"]) is int
    assert result["stake_cents"] == 450
    assert result["stake_cents"] % vector["stake_increment_cents"] == 0
    assert independent_evaluate_vector(vector, REGISTRY["numeric_contract"]) == result


def test_one_in_ten_thousand_probability_boundary_is_replayed_by_both_implementations() -> None:
    results = {row["vector_id"]: row for row in build_report(REGISTRY, PARAMETERS)["results"]}
    below = results["V05-BOUNDARY-MINUS-ONE-IN-TEN-THOUSAND"]
    above = results["V06-BOUNDARY-PLUS-ONE-IN-TEN-THOUSAND"]
    assert Decimal(below["authoritative"]["conservative_probability"]) == Decimal("0.6000") - Decimal("0.0001")
    assert Decimal(above["authoritative"]["conservative_probability"]) == Decimal("0.6000") + Decimal("0.0001")
    assert below["actions_match"] is above["actions_match"] is True
    assert below["authoritative"]["action"] == "NO_RECOMMENDATION_NUMERIC_GUARD"
    assert above["authoritative"]["action"] == "NO_ORDER_NUMERIC_CANDIDATE"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda registry, parameters: registry.update({"contract_id": "AC-S10-P04"}),
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
    with pytest.raises(CrossImplementationError):
        validate_registry(registry, parameters)


def test_invalid_authoritative_numeric_inputs_fail_closed() -> None:
    with pytest.raises(NumericContractError):
        normalize_probability("NaN")
    with pytest.raises(NumericContractError):
        normalize_odds("1.000000")
    with pytest.raises(NumericContractError):
        normalize_friction("1.000000000")
    invalid = deepcopy(REGISTRY["vectors"][0])
    invalid["bankroll_cents"] = -1
    with pytest.raises(NumericContractError):
        evaluate_vector(invalid, REGISTRY["numeric_contract"])


def test_report_hash_detects_any_result_tampering() -> None:
    report = deepcopy(build_report(REGISTRY, PARAMETERS))
    report["results"][0]["authoritative"]["stake_cents"] = 999
    assert report_sha256(report) != FIXTURE["expected_report_sha256"]


def test_core_source_has_no_network_process_soak_float_or_order_capability_and_independent_body_has_no_primary_call() -> None:
    sources = [(ROOT / "decimal_math.py").read_text(encoding="utf-8"), (ROOT / "cross_impl_check.py").read_text(encoding="utf-8")]
    trees = [ast.parse(source) for source in sources]
    imports = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    combined = "\n".join(sources)
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"})
    assert "sleep(" not in combined
    assert "submit_order" not in combined
    assert "retry_order" not in combined
    assert "float(" not in combined
    independent = next(node for node in ast.walk(trees[1]) if isinstance(node, ast.FunctionDef) and node.name == "independent_evaluate_vector")
    assert "authoritative_evaluate_vector" not in {node.id for node in ast.walk(independent) if isinstance(node, ast.Name)}
    assert "evaluate_vector" not in {node.attr for node in ast.walk(independent) if isinstance(node, ast.Attribute)}


def test_candidate_fails_closed_when_expected_report_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S10_P03.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_report_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P03-FROZEN-CROSS-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_frozen_vector_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "numeric_vectors.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["vectors"][0]["friction"] = "0.0350000001"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P03-FROZEN-CROSS-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_p02_predecessor_is_changed(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S10-P02.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["status"] = "FAIL"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P03-P02-PREDECESSOR-HASH" in result["summary"]["failed_check_ids"]


def test_existing_evidence_fails_closed_when_index_binding_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    _prepare_required_reports(clone)
    write_phase_evidence(clone, clone / "machine/evidence")
    path = clone / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["id"] == "INDEX-AC-S10-P03":
            row["artifact_sha256"] = "f" * 64
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(DecimalMathAcceptanceError):
        verify_existing_phase_evidence(clone)


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:decimal_fixed_point_authoritative_calculation"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S10-P03": write_decimal_math_phase_evidence' in source
    assert '"AC-S10-P03": verify_decimal_math_phase_evidence' in source
    with pytest.raises((DecimalMathAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
