"""Frozen temporal cross-validation runner for ABD S10/P01.

This runner has no provider, account, clock, process, or order dependency.  It
compares isotonic, logistic, and multiclass temperature calibration only over
the compact synthetic fixture committed with this phase.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from calibration import (
    BinaryObservation,
    CalibrationInputError,
    MulticlassObservation,
    apply_isotonic_binary,
    apply_logistic_binary,
    apply_temperature_multiclass,
    binary_calibration_metrics,
    canonical_json_bytes,
    decimal_text,
    fit_isotonic_binary,
    fit_logistic_binary,
    fit_temperature_multiclass,
    isotonic_payload,
    logistic_payload,
    metric_payload,
    multiclass_calibration_metrics,
)


FIXTURE_ID = "FIX-S10-P01-TEMPORAL-CALIBRATION"
CONTRACT_ID = "AC-S10-P01"
REQUIREMENT_ID = "REQ-S10-P01"
STAGE_ID = "S10"
PHASE_ID = "P01"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
METHOD_IDS = ("ISOTONIC_BINARY", "LOGISTIC_BINARY", "TEMPERATURE_MULTICLASS")
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "actual_market_or_odds_observed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class TemporalCalibrationError(ValueError):
    """Raised when a frozen temporal calibration input is unsafe or malformed."""


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise TemporalCalibrationError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise TemporalCalibrationError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise TemporalCalibrationError("%s must be finite" % label)
    return parsed


def _strict_object(value: Any, keys: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise TemporalCalibrationError("%s has an unexpected shape" % label)
    return value


def _strict_fold_ids(folds: Any, *, temporal_folds: int, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(folds, list) or len(folds) != temporal_folds:
        raise TemporalCalibrationError("%s must contain exactly temporal_folds entries" % label)
    expected = ["F%02d" % value for value in range(1, temporal_folds + 1)]
    parsed: list[Mapping[str, Any]] = []
    for expected_id, fold in zip(expected, folds):
        row = _strict_object(fold, {"fold_id", "groups"}, label="%s.%s" % (label, expected_id))
        if row["fold_id"] != expected_id or not isinstance(row["groups"], list) or not row["groups"]:
            raise TemporalCalibrationError("%s fold identity or groups are invalid" % label)
        parsed.append(row)
    return parsed


def _expand_binary_groups(groups: Any, *, start_index: int, label: str) -> tuple[list[BinaryObservation], int]:
    if not isinstance(groups, list) or not groups:
        raise TemporalCalibrationError("%s groups are required" % label)
    observations: list[BinaryObservation] = []
    event_index = start_index
    for group_index, group in enumerate(groups):
        row = _strict_object(group, {"probability", "outcomes"}, label="%s[%d]" % (label, group_index))
        probability = _decimal(row["probability"], label="%s[%d].probability" % (label, group_index))
        outcomes = row["outcomes"]
        if not isinstance(outcomes, str) or not outcomes or set(outcomes) - {"0", "1"}:
            raise TemporalCalibrationError("%s[%d].outcomes must be a nonempty binary string" % (label, group_index))
        for outcome in outcomes:
            observations.append(BinaryObservation(event_index=event_index, probability=probability, outcome=int(outcome)))
            event_index += 1
    return observations, event_index


def _expand_multiclass_groups(groups: Any, *, start_index: int, label: str) -> tuple[list[MulticlassObservation], int]:
    if not isinstance(groups, list) or not groups:
        raise TemporalCalibrationError("%s groups are required" % label)
    observations: list[MulticlassObservation] = []
    event_index = start_index
    for group_index, group in enumerate(groups):
        row = _strict_object(group, {"probabilities", "outcomes"}, label="%s[%d]" % (label, group_index))
        raw_probabilities = row["probabilities"]
        if not isinstance(raw_probabilities, Mapping) or len(raw_probabilities) < 3:
            raise TemporalCalibrationError("%s[%d].probabilities must contain at least three values" % (label, group_index))
        probabilities = {key: _decimal(value, label="%s[%d].probabilities.%s" % (label, group_index, key)) for key, value in raw_probabilities.items()}
        if any(not isinstance(key, str) or len(key) != 1 for key in probabilities):
            raise TemporalCalibrationError("%s[%d] outcome ids must be single characters" % (label, group_index))
        if any(value <= Decimal("0") or value >= Decimal("1") for value in probabilities.values()) or abs(sum(probabilities.values()) - Decimal("1")) > Decimal("0.000000000001"):
            raise TemporalCalibrationError("%s[%d].probabilities are invalid" % (label, group_index))
        outcomes = row["outcomes"]
        if not isinstance(outcomes, str) or not outcomes or set(outcomes) - set(probabilities):
            raise TemporalCalibrationError("%s[%d].outcomes are invalid" % (label, group_index))
        for outcome_id in outcomes:
            observations.append(MulticlassObservation(event_index=event_index, probabilities=probabilities, outcome_id=outcome_id))
            event_index += 1
    return observations, event_index


def _series(value: Any, *, temporal_folds: int, kind: str) -> tuple[list[Any], list[tuple[str, list[Any]]]]:
    row = _strict_object(value, {"warmup_groups", "folds"}, label=kind)
    expand = _expand_binary_groups if kind == "binary" else _expand_multiclass_groups
    warmup, next_index = expand(row["warmup_groups"], start_index=0, label="%s.warmup_groups" % kind)
    if len(warmup) < 8:
        raise TemporalCalibrationError("%s warmup must contain at least eight frozen observations" % kind)
    folds: list[tuple[str, list[Any]]] = []
    for fold in _strict_fold_ids(row["folds"], temporal_folds=temporal_folds, label="%s.folds" % kind):
        observations, next_index = expand(fold["groups"], start_index=next_index, label="%s.%s.groups" % (kind, fold["fold_id"]))
        folds.append((str(fold["fold_id"]), observations))
    return warmup, folds


def _parameters(value: Any) -> tuple[int, Decimal, Decimal, Decimal]:
    if not isinstance(value, Mapping):
        raise TemporalCalibrationError("parameters must be an object")
    market_model = value.get("market_model")
    calibration = value.get("calibration")
    if not isinstance(market_model, Mapping) or not isinstance(calibration, Mapping):
        raise TemporalCalibrationError("calibration parameters are missing")
    folds = market_model.get("temporal_folds_min")
    if type(folds) is not int or folds < 8:
        raise TemporalCalibrationError("temporal_folds_min must be at least eight")
    slope_min = _decimal(calibration.get("slope_min"), label="calibration.slope_min")
    slope_max = _decimal(calibration.get("slope_max"), label="calibration.slope_max")
    intercept_abs_max = _decimal(calibration.get("intercept_abs_max"), label="calibration.intercept_abs_max")
    if slope_min != Decimal("0.90") or slope_max != Decimal("1.10") or intercept_abs_max != Decimal("0.02"):
        raise TemporalCalibrationError("frozen calibration pass gate has drifted")
    return folds, slope_min, slope_max, intercept_abs_max


def validate_fixture(fixture: Any, parameters: Any) -> dict[str, Any]:
    """Validate shape, frozen no-external boundary, and temporal fold count."""

    required = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "temporal_folds",
        "binary",
        "multiclass",
        "claim_boundary",
        "expected_report_sha256",
    }
    if not isinstance(fixture, Mapping) or set(fixture) != required:
        raise TemporalCalibrationError("fixture has an unexpected shape")
    folds_min, _, _, _ = _parameters(parameters)
    expected = {
        "schema_version": "1.0.0",
        "fixture_id": FIXTURE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": "0.0.0.1",
        "input_mode": INPUT_MODE,
        "temporal_folds": folds_min,
    }
    if any(fixture.get(key) != expected_value for key, expected_value in expected.items()):
        raise TemporalCalibrationError("fixture identity or frozen fold count is invalid")
    if not isinstance(fixture["fixed_clock"], str) or not fixture["fixed_clock"].endswith("+10:00"):
        raise TemporalCalibrationError("fixture fixed_clock is invalid")
    if not isinstance(fixture["expected_report_sha256"], str) or len(fixture["expected_report_sha256"]) != 64:
        raise TemporalCalibrationError("fixture expected_report_sha256 is invalid")
    boundary = fixture["claim_boundary"]
    if not isinstance(boundary, Mapping) or boundary != {
        "network_accessed": False,
        "actual_market_or_odds_observed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
        "incremental_cash_spent_aud": "0.00",
    }:
        raise TemporalCalibrationError("fixture claim boundary is invalid")
    binary_warmup, binary_folds = _series(fixture["binary"], temporal_folds=folds_min, kind="binary")
    multiclass_warmup, multiclass_folds = _series(fixture["multiclass"], temporal_folds=folds_min, kind="multiclass")
    if [fold_id for fold_id, _ in binary_folds] != [fold_id for fold_id, _ in multiclass_folds]:
        raise TemporalCalibrationError("binary and multiclass fold identities must match")
    return {
        "temporal_folds": folds_min,
        "binary_warmup": binary_warmup,
        "binary_folds": binary_folds,
        "multiclass_warmup": multiclass_warmup,
        "multiclass_folds": multiclass_folds,
    }


def _method_row(identifier: str, metrics: Mapping[str, Decimal], *, slope_min: Decimal, slope_max: Decimal, intercept_abs_max: Decimal, family: str) -> dict[str, Any]:
    return {
        "method_id": identifier,
        "family": family,
        "metrics": metric_payload(metrics, slope_min=slope_min, slope_max=slope_max, intercept_abs_max=intercept_abs_max),
    }


def _select_binary(rows: Sequence[Mapping[str, Any]]) -> str | None:
    eligible = [row for row in rows if row["metrics"]["eligible"] is True]
    if not eligible:
        return None
    ranked = sorted(eligible, key=lambda row: (Decimal(str(row["metrics"]["mean_absolute_error"])), str(row["method_id"])))
    return str(ranked[0]["method_id"])


def build_report(fixture: Mapping[str, Any], parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Run expanding-window temporal CV and return a deterministic report object."""

    validated = validate_fixture(fixture, parameters)
    temporal_folds, slope_min, slope_max, intercept_abs_max = _parameters(parameters)
    binary_history = list(validated["binary_warmup"])
    multiclass_history = list(validated["multiclass_warmup"])
    isotonic_pairs: list[tuple[Decimal, int]] = []
    logistic_pairs: list[tuple[Decimal, int]] = []
    temperature_rows: list[tuple[Mapping[str, Decimal], str]] = []
    fold_rows: list[dict[str, Any]] = []
    for (binary_fold_id, binary_validation), (multiclass_fold_id, multiclass_validation) in zip(validated["binary_folds"], validated["multiclass_folds"]):
        if binary_fold_id != multiclass_fold_id:
            raise TemporalCalibrationError("temporal fold alignment changed during evaluation")
        try:
            isotonic_model = fit_isotonic_binary(binary_history)
            logistic_model = fit_logistic_binary(binary_history)
            temperature = fit_temperature_multiclass(multiclass_history)
        except CalibrationInputError as exc:
            raise TemporalCalibrationError("cannot fit %s" % binary_fold_id) from exc
        for observation in binary_validation:
            isotonic_pairs.append((apply_isotonic_binary(isotonic_model, observation.probability), observation.outcome))
            logistic_pairs.append((apply_logistic_binary(logistic_model, observation.probability), observation.outcome))
        calibrated_multiclass = []
        for observation in multiclass_validation:
            calibrated = apply_temperature_multiclass(observation.probabilities, temperature)
            calibrated_multiclass.append((calibrated, observation.outcome_id))
            temperature_rows.append((calibrated, observation.outcome_id))
        fold_rows.append(
            {
                "fold_id": binary_fold_id,
                "binary_training_count": len(binary_history),
                "binary_validation_count": len(binary_validation),
                "multiclass_training_count": len(multiclass_history),
                "multiclass_validation_count": len(multiclass_validation),
                "isotonic_model": isotonic_payload(isotonic_model),
                "logistic_model": logistic_payload(logistic_model),
                "temperature": decimal_text(temperature),
                "multiclass_validation_probability_sum": [
                    decimal_text(sum(probabilities.values(), Decimal("0"))) for probabilities, _ in calibrated_multiclass
                ],
            }
        )
        binary_history.extend(binary_validation)
        multiclass_history.extend(multiclass_validation)
    isotonic_metrics = binary_calibration_metrics(isotonic_pairs)
    logistic_metrics = binary_calibration_metrics(logistic_pairs)
    temperature_metrics = multiclass_calibration_metrics(temperature_rows)
    comparison = [
        _method_row("ISOTONIC_BINARY", isotonic_metrics, slope_min=slope_min, slope_max=slope_max, intercept_abs_max=intercept_abs_max, family="BINARY"),
        _method_row("LOGISTIC_BINARY", logistic_metrics, slope_min=slope_min, slope_max=slope_max, intercept_abs_max=intercept_abs_max, family="BINARY"),
        _method_row("TEMPERATURE_MULTICLASS", temperature_metrics, slope_min=slope_min, slope_max=slope_max, intercept_abs_max=intercept_abs_max, family="MULTICLASS"),
    ]
    binary_rows = [row for row in comparison if row["family"] == "BINARY"]
    multiclass_rows = [row for row in comparison if row["family"] == "MULTICLASS"]
    selected_binary = _select_binary(binary_rows)
    selected_multiclass = _select_binary(multiclass_rows)
    all_eligible = len(comparison) == len(METHOD_IDS) and all(row["metrics"]["eligible"] is True for row in comparison)
    report = {
        "schema_version": "1.0.0",
        "report_id": "RPT-S10-P01-TEMPORAL-CALIBRATION",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": fixture["product_version"],
        "fixed_clock": fixture["fixed_clock"],
        "input_mode": INPUT_MODE,
        "temporal_folds": temporal_folds,
        "folds": fold_rows,
        "method_comparison": comparison,
        "selected_methods": {"binary": selected_binary, "multiclass": selected_multiclass},
        "summary": {
            "all_methods_eligible": all_eligible,
            "binary_validation_count": len(isotonic_pairs),
            "multiclass_validation_count": len(temperature_rows),
            "pass_gate": "斜率0.90–1.10、截距绝对值≤0.02。",
        },
        "decision": "TEMPORAL_CALIBRATION_READY_DOWNSTREAM_UNCERTAINTY_GATES_REQUIRED" if all_eligible and selected_binary and selected_multiclass else "NO_ADVICE_CALIBRATION_GATE_BLOCKED",
        "next": "S10/P02_READY_NOT_STARTED" if all_eligible and selected_binary and selected_multiclass else "S10/P01_BLOCKED",
        "external_effect_boundary": deepcopy(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    return report


def report_sha256(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(report)).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemporalCalibrationError("cannot read JSON: %s" % path) from exc


def write_report(fixture_path: Path, parameters_path: Path, output_path: Path) -> dict[str, Any]:
    fixture = load_json(fixture_path)
    parameters = load_json(parameters_path)
    report = build_report(fixture, parameters)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_bytes(canonical_json_bytes(report))
    temporary.replace(output_path)
    return {"status": "PASS", "report": output_path.as_posix(), "report_sha256": report_sha256(report)}


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD S10/P01 frozen temporal calibration report")
    parser.add_argument("--fixture", default="machine/tests/fixtures/S10_P01.json")
    parser.add_argument("--parameters", default="machine/facts/parameters.json")
    parser.add_argument("--output", default="calibration_report.json")
    args = parser.parse_args()
    result = write_report(Path(args.fixture), Path(args.parameters), Path(args.output))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
