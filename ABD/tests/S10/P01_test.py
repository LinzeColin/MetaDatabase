from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.temporal_calibration import (
    TemporalCalibrationAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from calibration import (
    BinaryObservation,
    CalibrationInputError,
    MulticlassObservation,
    apply_isotonic_binary,
    apply_logistic_binary,
    apply_temperature_multiclass,
    binary_calibration_metrics,
    canonical_json_bytes,
    fit_isotonic_binary,
    fit_logistic_binary,
    fit_temperature_multiclass,
)
from temporal_cv import TemporalCalibrationError, build_report, report_sha256, validate_fixture


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S10_P01.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S10-P01"
    assert result["next"] == "S10/P02_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 30
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_report_is_exact_frozen_replay_with_three_eligible_calibrators() -> None:
    report = build_report(FIXTURE, PARAMETERS)
    assert report_sha256(report) == FIXTURE["expected_report_sha256"]
    assert report["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert [row["method_id"] for row in report["method_comparison"]] == [
        "ISOTONIC_BINARY",
        "LOGISTIC_BINARY",
        "TEMPERATURE_MULTICLASS",
    ]
    assert all(row["metrics"]["eligible"] is True for row in report["method_comparison"])
    assert all(Decimal(row["metrics"]["mean_absolute_error"]) <= Decimal("0.025") for row in report["method_comparison"])
    assert report["selected_methods"] == {"binary": "LOGISTIC_BINARY", "multiclass": "TEMPERATURE_MULTICLASS"}
    assert report["decision"] == "TEMPORAL_CALIBRATION_READY_DOWNSTREAM_UNCERTAINTY_GATES_REQUIRED"


def test_eight_temporal_folds_are_expanding_and_not_real_time_waits() -> None:
    report = build_report(FIXTURE, PARAMETERS)
    folds = report["folds"]
    assert len(folds) == 8
    assert [row["fold_id"] for row in folds] == ["F%02d" % number for number in range(1, 9)]
    assert all(row["binary_training_count"] >= 72 and row["binary_validation_count"] == 30 for row in folds)
    assert all(row["multiclass_training_count"] >= 30 and row["multiclass_validation_count"] == 10 for row in folds)
    assert all(later["binary_training_count"] > earlier["binary_training_count"] for earlier, later in zip(folds, folds[1:]))
    assert report["external_effect_boundary"]["real_time_soak_waited"] is False


def test_isotonic_pooled_adjacent_violators_is_monotone() -> None:
    observations = [
        BinaryObservation(0, Decimal("0.20"), 1),
        BinaryObservation(1, Decimal("0.30"), 0),
        BinaryObservation(2, Decimal("0.70"), 1),
        BinaryObservation(3, Decimal("0.80"), 1),
    ]
    model = fit_isotonic_binary(observations)
    values = [block.value for block in model]
    assert values == sorted(values)
    assert apply_isotonic_binary(model, Decimal("0.20")) <= apply_isotonic_binary(model, Decimal("0.80"))


def test_isotonic_pools_equal_prediction_values_before_adjacent_merges() -> None:
    observations = [
        BinaryObservation(0, Decimal("0.40"), 0),
        BinaryObservation(1, Decimal("0.40"), 1),
        BinaryObservation(2, Decimal("0.40"), 1),
        BinaryObservation(3, Decimal("0.80"), 1),
    ]
    model = fit_isotonic_binary(observations)
    assert len([block for block in model if block.upper == Decimal("0.40")]) == 1
    assert apply_isotonic_binary(model, Decimal("0.40")) == Decimal("2") / Decimal("3")


def test_logistic_calibration_is_decimal_deterministic() -> None:
    observations = [
        BinaryObservation(0, Decimal("0.20"), 0),
        BinaryObservation(1, Decimal("0.40"), 0),
        BinaryObservation(2, Decimal("0.60"), 1),
        BinaryObservation(3, Decimal("0.80"), 1),
    ]
    first = fit_logistic_binary(observations)
    second = fit_logistic_binary(observations)
    assert first == second
    applied = apply_logistic_binary(first, Decimal("0.60"))
    assert Decimal("0") < applied < Decimal("1")


def test_multiclass_temperature_preserves_all_outcomes_and_total() -> None:
    observations = [
        MulticlassObservation(0, {"A": Decimal("0.20"), "B": Decimal("0.30"), "C": Decimal("0.50")}, "A"),
        MulticlassObservation(1, {"A": Decimal("0.20"), "B": Decimal("0.30"), "C": Decimal("0.50")}, "B"),
        MulticlassObservation(2, {"A": Decimal("0.20"), "B": Decimal("0.30"), "C": Decimal("0.50")}, "C"),
    ]
    temperature = fit_temperature_multiclass(observations)
    calibrated = apply_temperature_multiclass(observations[0].probabilities, temperature)
    assert set(calibrated) == {"A", "B", "C"}
    assert sum(calibrated.values(), Decimal("0")) == Decimal("1")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture.update({"temporal_folds": 7}),
        lambda fixture: fixture["binary"]["folds"].pop(),
        lambda fixture: fixture["claim_boundary"].update({"network_accessed": True}),
        lambda fixture: fixture["multiclass"]["folds"][0]["groups"][0].update({"outcomes": "Z"}),
    ],
)
def test_malformed_or_unsafe_fixture_fails_closed(mutate) -> None:
    mutated = deepcopy(FIXTURE)
    mutate(mutated)
    with pytest.raises(TemporalCalibrationError):
        validate_fixture(mutated, PARAMETERS)


def test_binary_metrics_reject_zero_variance() -> None:
    with pytest.raises(CalibrationInputError):
        binary_calibration_metrics([(Decimal("0.50"), 0), (Decimal("0.50"), 1)])


def test_frozen_replay_hash_is_identical_without_waiting() -> None:
    hashes = {hashlib.sha256(canonical_json_bytes(build_report(FIXTURE, PARAMETERS))).hexdigest() for _ in range(3)}
    assert hashes == {FIXTURE["expected_report_sha256"]}


def test_core_sources_have_no_network_process_soak_or_order_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    for relative in ("calibration.py", "temporal_cv.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
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


def test_candidate_fails_closed_when_expected_report_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S10_P01.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_report_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P01-REPORT-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_report_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "calibration_report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["next"] = "S10/P99_READY"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S10P01-REPORT-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "model:temporal_calibration"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_cli_is_wired_to_exact_contract_and_phase_boundaries() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S10-P01": write_temporal_calibration_phase_evidence' in source
    assert '"AC-S10-P01": verify_temporal_calibration_phase_evidence' in source
    with pytest.raises((TemporalCalibrationAcceptanceError, FileNotFoundError)):
        from abd_acceptance.temporal_calibration import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
