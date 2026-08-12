#!/usr/bin/env python3
"""Validate one licensed-scope static Football-Data CSV without network access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Mapping


class FootballDataSourceError(ValueError):
    """Raised when the one-shot static source contract is not satisfied."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise FootballDataSourceError("%s must be a lowercase SHA-256 digest" % name)
    return value


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise FootballDataSourceError("%s must be an object" % name)
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise FootballDataSourceError("%s must be a non-empty string" % name)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FootballDataSourceError("contract is unreadable") from exc
    return _object(value, "contract")


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != "1.0.0":
        raise FootballDataSourceError("unsupported schema version")
    if contract.get("status") != "ONE_SHOT_MANUAL_INTERNAL_IMPORT_ONLY":
        raise FootballDataSourceError("source contract must remain one-shot only")

    source = _object(contract.get("source"), "source")
    collection = _object(contract.get("collection"), "collection")
    schema = _object(contract.get("schema"), "schema")
    boundary = _object(contract.get("runtime_boundary"), "runtime_boundary")

    if source.get("source_url") != "https://www.football-data.co.uk/mmz4281/2526/E0.csv":
        raise FootballDataSourceError("unexpected source URL")
    if source.get("terms_url") != "https://www.football-data.co.uk/data.php":
        raise FootballDataSourceError("unexpected terms URL")
    if source.get("publisher_usage_statement") != "FREE_DATA_FOR_LEAGUE_MATCH_PREDICTION":
        raise FootballDataSourceError("publisher usage scope is not exact")
    if source.get("permitted_use_here") != "INTERNAL_LEAGUE_MATCH_PREDICTION_RESEARCH_ONLY":
        raise FootballDataSourceError("internal-only scope is not exact")
    if source.get("formal_redistribution_license") != "NOT_STATED_ON_PUBLISHER_DATA_PAGE":
        raise FootballDataSourceError("redistribution boundary is not explicit")

    expected_collection = {
        "automatic_scheduler_allowed": False,
        "automatic_retry_allowed": False,
        "maximum_network_fetches_for_this_contract": 2,
        "collection_mode": "MANUAL_ONE_SHOT_STATIC_FILE",
        "raw_data_destination": "Private-MetaDatabase_only",
        "source_code_repository_raw_data_allowed": False,
        "source_page_or_csv_republication_allowed": False,
    }
    if {key: collection.get(key) for key in expected_collection} != expected_collection:
        raise FootballDataSourceError("collection boundary is not exact")
    if collection.get("network_fetch_plan") != ["bounded_schema_preflight", "single_full_static_download"]:
        raise FootballDataSourceError("network fetch plan is not exact")

    required_columns = schema.get("required_columns")
    expected_columns = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    if required_columns != expected_columns or schema.get("one_x_two_odds_columns") != ["B365H", "B365D", "B365A"]:
        raise FootballDataSourceError("required source schema is not exact")
    if schema.get("division") != "E0" or schema.get("minimum_rows") != 300:
        raise FootballDataSourceError("division or row threshold is not exact")
    for key in ("season_start", "season_end"):
        _string(schema.get(key), "schema.%s" % key)

    expected_boundary = {
        "runtime_network_collection_enabled": False,
        "dynamic_platform_collection_enabled": False,
        "real_time_freshness_claimed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "market_account_TAB_or_Gmail_accessed": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if {key: boundary.get(key) for key in expected_boundary} != expected_boundary:
        raise FootballDataSourceError("runtime boundary is not exact")


def _parse_odds(value: str, field: str, row_number: int) -> None:
    try:
        odds = float(value)
    except (TypeError, ValueError) as exc:
        raise FootballDataSourceError("row %d %s is not numeric" % (row_number, field)) from exc
    if not math.isfinite(odds) or odds <= 1.0:
        raise FootballDataSourceError("row %d %s is outside decimal-odds range" % (row_number, field))


def _parse_score(value: str, field: str, row_number: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise FootballDataSourceError("row %d %s is not an integer score" % (row_number, field)) from exc
    if score < 0:
        raise FootballDataSourceError("row %d %s is negative" % (row_number, field))
    return score


def build_receipt(
    data: bytes,
    contract: Mapping[str, Any],
    contract_sha256: str,
    validator_sha256: str,
    observed_on: str,
    network_fetches: int,
) -> dict[str, Any]:
    validate_contract(contract)
    _digest(contract_sha256, "contract_sha256")
    _digest(validator_sha256, "validator_sha256")
    if not data:
        raise FootballDataSourceError("source file is empty")
    try:
        observed_date = date.fromisoformat(observed_on)
        text = data.decode("utf-8-sig")
    except (UnicodeDecodeError, ValueError) as exc:
        raise FootballDataSourceError("source bytes or observation date are invalid") from exc

    reader = csv.DictReader(StringIO(text, newline=""))
    fields = reader.fieldnames
    if not fields or len(fields) != len(set(fields)):
        raise FootballDataSourceError("CSV headers are missing or duplicated")

    schema = _object(contract["schema"], "schema")
    required = list(schema["required_columns"])
    missing = [field for field in required if field not in fields]
    if missing:
        raise FootballDataSourceError("CSV is missing required columns: %s" % ",".join(missing))

    season_start = date.fromisoformat(_string(schema["season_start"], "schema.season_start"))
    season_end = date.fromisoformat(_string(schema["season_end"], "schema.season_end"))
    division = _string(schema["division"], "schema.division")
    row_count = 0
    dates: list[date] = []
    for row_number, row in enumerate(reader, start=2):
        row_count += 1
        if row.get("Div") != division:
            raise FootballDataSourceError("row %d division does not match contract" % row_number)
        match_date = datetime.strptime(_string(row.get("Date"), "row date"), "%d/%m/%Y").date()
        if match_date < season_start or match_date > season_end:
            raise FootballDataSourceError("row %d date is outside the contracted season" % row_number)
        if not _string(row.get("HomeTeam"), "row home team") or not _string(row.get("AwayTeam"), "row away team"):
            raise FootballDataSourceError("row %d team identity is empty" % row_number)
        home_goals = _parse_score(_string(row.get("FTHG"), "row FTHG"), "FTHG", row_number)
        away_goals = _parse_score(_string(row.get("FTAG"), "row FTAG"), "FTAG", row_number)
        expected_result = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
        if row.get("FTR") != expected_result:
            raise FootballDataSourceError("row %d full-time result disagrees with scores" % row_number)
        for field in schema["one_x_two_odds_columns"]:
            _parse_odds(_string(row.get(field), "row %s" % field), field, row_number)
        dates.append(match_date)

    if row_count < int(schema["minimum_rows"]):
        raise FootballDataSourceError("CSV has fewer rows than the contract threshold")

    source = _object(contract["source"], "source")
    collection = _object(contract["collection"], "collection")
    if isinstance(network_fetches, bool) or not isinstance(network_fetches, int) or not 1 <= network_fetches <= int(collection["maximum_network_fetches_for_this_contract"]):
        raise FootballDataSourceError("network fetch count exceeds the contract")
    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_POST_FREEZE_STATIC_SOURCE_IMPORT",
        "status": "PASS_STATIC_HISTORICAL_SOURCE_READY_FOR_PRIVATE_ARCHIVE",
        "observed_on": observed_date.isoformat(),
        "source": {
            "source_id": source["source_id"],
            "publisher": source["publisher"],
            "source_url": source["source_url"],
            "terms_url": source["terms_url"],
            "permitted_use_here": source["permitted_use_here"],
            "formal_redistribution_license": source["formal_redistribution_license"],
        },
        "source_file": {
            "sha256": _sha256(data),
            "bytes": len(data),
            "row_count": row_count,
            "division": division,
            "minimum_match_date": min(dates).isoformat(),
            "maximum_match_date": max(dates).isoformat(),
            "required_columns_present": required,
            "validated_odds_columns": list(schema["one_x_two_odds_columns"]),
        },
        "contract_sha256": contract_sha256,
        "validator_sha256": validator_sha256,
        "network_fetches_observed": network_fetches,
        "boundaries": dict(_object(contract["runtime_boundary"], "runtime_boundary")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    parser.add_argument("--network-fetches", type=int, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    receipt = build_receipt(
        args.input.read_bytes(),
        contract,
        _sha256(args.contract.read_bytes()),
        _sha256(Path(__file__).read_bytes()),
        args.observed_on,
        args.network_fetches,
    )
    args.receipt_out.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "row_count": receipt["source_file"]["row_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
