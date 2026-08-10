#!/usr/bin/env python3
"""Describe static historical 1X2 calibration residuals without changing a model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from io import StringIO
from pathlib import Path
from typing import Any, Mapping


class StaticCalibrationResidualError(ValueError):
    """Raised when static descriptive calibration inputs do not satisfy the contract."""


_ZERO = Decimal("0")
_ONE = Decimal("1")
_BIN_UPPERS = (Decimal("0.20"), Decimal("0.40"), Decimal("0.60"), Decimal("0.80"), _ONE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise StaticCalibrationResidualError("%s must be an object" % name)
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise StaticCalibrationResidualError("%s must be a lowercase SHA-256 digest" % name)
    return value


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise StaticCalibrationResidualError("%s must be a non-empty decimal string" % name)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise StaticCalibrationResidualError("%s is not a decimal" % name) from exc
    if not parsed.is_finite():
        raise StaticCalibrationResidualError("%s must be finite" % name)
    return parsed


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise StaticCalibrationResidualError("output decimal must be finite")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StaticCalibrationResidualError("contract is unreadable") from exc
    return _object(value, "contract")


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != "1.0.0":
        raise StaticCalibrationResidualError("unsupported schema version")
    if contract.get("contract_id") != "ABD-POST-FREEZE-STATIC-CALIBRATION-RESIDUAL-004":
        raise StaticCalibrationResidualError("unexpected contract identifier")
    if contract.get("status") != "PRIVATE_STATIC_DESCRIPTIVE_CALIBRATION_ONLY":
        raise StaticCalibrationResidualError("calibration residual must remain private and descriptive only")

    inputs = _object(contract.get("inputs"), "inputs")
    if set(inputs) != {"football_data", "historical_crosscheck_receipt"}:
        raise StaticCalibrationResidualError("input set is not exact")
    football = _object(inputs["football_data"], "inputs.football_data")
    expected_columns = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    if football.get("source_id") != "FOOTBALL_DATA_E0_2025_26" or football.get("required_columns") != expected_columns:
        raise StaticCalibrationResidualError("football-data input contract is not exact")
    _digest(football.get("raw_sha256"), "football-data raw_sha256")
    _digest(football.get("source_contract_sha256"), "football-data source_contract_sha256")

    crosscheck = _object(inputs["historical_crosscheck_receipt"], "inputs.historical_crosscheck_receipt")
    expected_crosscheck = {
        "expected_status": "PASS_STATIC_HISTORICAL_RESULT_CROSSCHECK_READY_FOR_PRIVATE_ARCHIVE",
        "expected_matched_fixture_count": 380,
        "expected_zero_count_fields": [
            "missing_from_openfootball_count",
            "missing_from_football_data_count",
            "final_score_disagreement_count",
        ],
    }
    if {key: crosscheck.get(key) for key in expected_crosscheck} != expected_crosscheck:
        raise StaticCalibrationResidualError("crosscheck receipt contract is not exact")
    _digest(crosscheck.get("raw_sha256"), "crosscheck raw_sha256")
    _digest(crosscheck.get("crosscheck_contract_sha256"), "crosscheck contract_sha256")

    schema = _object(contract.get("schema"), "schema")
    expected_schema = {
        "division": "E0",
        "season_start": "2025-08-15",
        "season_end": "2026-05-24",
        "expected_fixture_count": 380,
        "outcomes": ["H", "D", "A"],
        "odds_columns": {"H": "B365H", "D": "B365D", "A": "B365A"},
        "probability_formula": "inverse_decimal_odds_divided_by_sum_of_all_three_inverse_decimal_odds",
        "probability_bins": ["0.00-0.20", "0.20-0.40", "0.40-0.60", "0.60-0.80", "0.80-1.00"],
    }
    if dict(schema) != expected_schema:
        raise StaticCalibrationResidualError("calibration schema is not exact")

    boundary = _object(contract.get("runtime_boundary"), "runtime_boundary")
    expected_boundary = {
        "network_collection_enabled": False,
        "external_market_or_account_accessed": False,
        "odds_or_price_truth_claimed": False,
        "model_parameter_or_calibration_update_enabled": False,
        "model_beta_or_ga_enabled": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if dict(boundary) != expected_boundary:
        raise StaticCalibrationResidualError("runtime boundary is not exact")


def _validate_crosscheck_receipt(data: bytes, contract: Mapping[str, Any]) -> None:
    try:
        receipt = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StaticCalibrationResidualError("crosscheck receipt is unreadable") from exc
    receipt = _object(receipt, "crosscheck receipt")
    crosscheck_contract = _object(_object(contract["inputs"], "inputs")["historical_crosscheck_receipt"], "crosscheck contract")
    if receipt.get("status") != crosscheck_contract["expected_status"]:
        raise StaticCalibrationResidualError("crosscheck receipt status is not accepted")
    if receipt.get("contract_sha256") != crosscheck_contract["crosscheck_contract_sha256"]:
        raise StaticCalibrationResidualError("crosscheck receipt contract provenance is not accepted")
    comparison = _object(receipt.get("comparison"), "crosscheck comparison")
    if comparison.get("matched_fixture_count") != crosscheck_contract["expected_matched_fixture_count"]:
        raise StaticCalibrationResidualError("crosscheck fixture count is not accepted")
    for field in crosscheck_contract["expected_zero_count_fields"]:
        if comparison.get(field) != 0:
            raise StaticCalibrationResidualError("crosscheck %s is not zero" % field)


def _bucket(probability: Decimal, labels: list[str]) -> str:
    for upper, label in zip(_BIN_UPPERS, labels):
        if probability < upper or upper == _ONE:
            return label
    raise StaticCalibrationResidualError("normalized probability is outside [0, 1]")


def _new_accumulator(labels: list[str]) -> dict[str, dict[str, Decimal | int]]:
    result: dict[str, dict[str, Decimal | int]] = {}
    for label in labels:
        result[label] = {"count": 0, "probability_sum": _ZERO, "outcome_sum": _ZERO, "absolute_residual_sum": _ZERO}
    return result


def _record_rows(data: bytes, contract: Mapping[str, Any]) -> tuple[dict[str, dict[str, Decimal | int]], dict[str, dict[str, dict[str, Decimal | int]]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StaticCalibrationResidualError("football-data CSV is not UTF-8") from exc
    reader = csv.DictReader(StringIO(text, newline=""))
    inputs = _object(contract["inputs"], "inputs")
    football = _object(inputs["football_data"], "football input")
    required_columns = football["required_columns"]
    if not reader.fieldnames or not set(required_columns).issubset(reader.fieldnames):
        raise StaticCalibrationResidualError("football-data CSV is missing required fields")
    schema = _object(contract["schema"], "schema")
    labels = list(schema["probability_bins"])
    outcomes = list(schema["outcomes"])
    odds_columns = _object(schema["odds_columns"], "odds_columns")
    overall = {outcome: _new_accumulator(["ALL"])["ALL"] for outcome in outcomes}
    bins = {outcome: _new_accumulator(labels) for outcome in outcomes}
    start = date.fromisoformat(str(schema["season_start"]))
    end = date.fromisoformat(str(schema["season_end"]))
    identities: set[tuple[date, str, str]] = set()
    row_count = 0
    with localcontext() as context:
        context.prec = 50
        for line_number, row in enumerate(reader, start=2):
            if row.get("Div") != schema["division"]:
                raise StaticCalibrationResidualError("football-data line %d has an unexpected division" % line_number)
            try:
                match_date = datetime.strptime(str(row.get("Date")), "%d/%m/%Y").date()
            except ValueError as exc:
                raise StaticCalibrationResidualError("football-data line %d has an invalid date" % line_number) from exc
            if not start <= match_date <= end:
                raise StaticCalibrationResidualError("football-data line %d is outside the contracted season" % line_number)
            home, away = row.get("HomeTeam"), row.get("AwayTeam")
            if not isinstance(home, str) or not home or not isinstance(away, str) or not away or home == away:
                raise StaticCalibrationResidualError("football-data line %d has invalid team identity" % line_number)
            identity = (match_date, home, away)
            if identity in identities:
                raise StaticCalibrationResidualError("football-data line %d duplicates a fixture identity" % line_number)
            identities.add(identity)
            try:
                home_goals, away_goals = int(str(row.get("FTHG"))), int(str(row.get("FTAG")))
            except (TypeError, ValueError) as exc:
                raise StaticCalibrationResidualError("football-data line %d has invalid final scores" % line_number) from exc
            if home_goals < 0 or away_goals < 0:
                raise StaticCalibrationResidualError("football-data line %d has negative final scores" % line_number)
            actual_outcome = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
            if row.get("FTR") != actual_outcome:
                raise StaticCalibrationResidualError("football-data line %d result code disagrees with score" % line_number)
            odds = {outcome: _decimal(row.get(str(odds_columns[outcome])), "football-data line %d %s" % (line_number, odds_columns[outcome])) for outcome in outcomes}
            if any(value <= _ONE for value in odds.values()):
                raise StaticCalibrationResidualError("football-data line %d has non-decimal 1X2 odds" % line_number)
            inverse_total = sum((_ONE / odds[outcome] for outcome in outcomes), _ZERO)
            if inverse_total <= _ZERO:
                raise StaticCalibrationResidualError("football-data line %d has invalid odds normalization" % line_number)
            for outcome in outcomes:
                probability = (_ONE / odds[outcome]) / inverse_total
                observed = _ONE if outcome == actual_outcome else _ZERO
                residual = observed - probability
                aggregate = overall[outcome]
                aggregate["count"] = int(aggregate["count"]) + 1
                aggregate["probability_sum"] = Decimal(aggregate["probability_sum"]) + probability
                aggregate["outcome_sum"] = Decimal(aggregate["outcome_sum"]) + observed
                aggregate["absolute_residual_sum"] = Decimal(aggregate["absolute_residual_sum"]) + abs(residual)
                bin_aggregate = bins[outcome][_bucket(probability, labels)]
                bin_aggregate["count"] = int(bin_aggregate["count"]) + 1
                bin_aggregate["probability_sum"] = Decimal(bin_aggregate["probability_sum"]) + probability
                bin_aggregate["outcome_sum"] = Decimal(bin_aggregate["outcome_sum"]) + observed
                bin_aggregate["absolute_residual_sum"] = Decimal(bin_aggregate["absolute_residual_sum"]) + abs(residual)
            row_count += 1
    if row_count != int(schema["expected_fixture_count"]):
        raise StaticCalibrationResidualError("football-data fixture count does not match the contract")
    return overall, bins


def _render_aggregate(aggregate: Mapping[str, Decimal | int]) -> dict[str, int | str | None]:
    count = int(aggregate["count"])
    if count == 0:
        return {"observation_count": 0, "mean_normalized_implied_probability": None, "empirical_outcome_rate": None, "mean_signed_residual": None, "mean_absolute_residual": None}
    probability = Decimal(aggregate["probability_sum"]) / Decimal(count)
    observed = Decimal(aggregate["outcome_sum"]) / Decimal(count)
    return {
        "observation_count": count,
        "mean_normalized_implied_probability": _decimal_text(probability),
        "empirical_outcome_rate": _decimal_text(observed),
        "mean_signed_residual": _decimal_text(observed - probability),
        "mean_absolute_residual": _decimal_text(Decimal(aggregate["absolute_residual_sum"]) / Decimal(count)),
    }


def build_receipt(
    football_data: bytes,
    crosscheck_receipt: bytes,
    contract: Mapping[str, Any],
    contract_sha256: str,
    validator_sha256: str,
    observed_on: str,
) -> dict[str, Any]:
    validate_contract(contract)
    _digest(contract_sha256, "contract_sha256")
    _digest(validator_sha256, "validator_sha256")
    try:
        observed_date = date.fromisoformat(observed_on)
    except ValueError as exc:
        raise StaticCalibrationResidualError("observation date is invalid") from exc
    inputs = _object(contract["inputs"], "inputs")
    football = _object(inputs["football_data"], "football input")
    crosscheck = _object(inputs["historical_crosscheck_receipt"], "crosscheck input")
    if _sha256(football_data) != football["raw_sha256"]:
        raise StaticCalibrationResidualError("football-data raw SHA-256 does not match the contract")
    if _sha256(crosscheck_receipt) != crosscheck["raw_sha256"]:
        raise StaticCalibrationResidualError("crosscheck receipt SHA-256 does not match the contract")
    _validate_crosscheck_receipt(crosscheck_receipt, contract)
    overall, bins = _record_rows(football_data, contract)
    schema = _object(contract["schema"], "schema")
    outcomes = list(schema["outcomes"])
    labels = list(schema["probability_bins"])
    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_POST_FREEZE_STATIC_CALIBRATION_RESIDUAL_DESCRIPTION",
        "status": "PASS_STATIC_DESCRIPTIVE_CALIBRATION_RESIDUAL_READY_FOR_PRIVATE_ARCHIVE",
        "observed_on": observed_date.isoformat(),
        "calibration_scope": {
            "probability_formula": schema["probability_formula"],
            "fixture_count": schema["expected_fixture_count"],
            "outcome_rows": int(schema["expected_fixture_count"]) * len(outcomes),
            "evidence_status": "STATIC_SINGLE_SEASON_DESCRIPTION_NOT_ELIGIBLE_FOR_MODEL_UPDATE",
        },
        "overall_by_outcome": {outcome: _render_aggregate(overall[outcome]) for outcome in outcomes},
        "bins_by_outcome": {outcome: {label: _render_aggregate(bins[outcome][label]) for label in labels} for outcome in outcomes},
        "inputs": {
            "football_data_raw_sha256": football["raw_sha256"],
            "football_data_source_contract_sha256": football["source_contract_sha256"],
            "historical_crosscheck_receipt_sha256": crosscheck["raw_sha256"],
            "historical_crosscheck_contract_sha256": crosscheck["crosscheck_contract_sha256"],
        },
        "contract_sha256": contract_sha256,
        "validator_sha256": validator_sha256,
        "boundaries": dict(_object(contract["runtime_boundary"], "runtime_boundary")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--football-data", type=Path, required=True)
    parser.add_argument("--crosscheck-receipt", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    receipt = build_receipt(
        args.football_data.read_bytes(),
        args.crosscheck_receipt.read_bytes(),
        contract,
        _sha256(args.contract.read_bytes()),
        _sha256(Path(__file__).read_bytes()),
        args.observed_on,
    )
    args.receipt_out.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "fixture_count": receipt["calibration_scope"]["fixture_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
