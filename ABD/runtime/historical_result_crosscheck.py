#!/usr/bin/env python3
"""Cross-check two private static football result sources without network access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Mapping


class HistoricalResultCrosscheckError(ValueError):
    """Raised when a static historical cross-check cannot be proven exactly."""


_OPEN_DATE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"(?P<day>[1-9]|[12]\d|3[01])(?: (?P<year>\d{4}))?$"
)
_OPEN_RESULT_PREFIX = re.compile(r"^\s*(?:[01]\d|2[0-3]):[0-5]\d\b")
_OPEN_RESULT = re.compile(
    r"^\s*(?:[01]\d|2[0-3]):[0-5]\d\s+"
    r"(?P<home>.+?)\s+(?P<home_goals>\d+)-(?P<away_goals>\d+)\s+"
    r"\((?P<home_half>\d+)-(?P<away_half>\d+)\)\s+(?P<away>.+?)\s*$"
)
_MONTHS = {name: number for number, name in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise HistoricalResultCrosscheckError("%s must be an object" % name)
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise HistoricalResultCrosscheckError("%s must be a lowercase SHA-256 digest" % name)
    return value


def _alias_map(value: object, name: str) -> Mapping[str, str]:
    mapping = _object(value, name)
    if len(mapping) != 20 or any(not isinstance(raw, str) or not raw or not isinstance(canonical, str) or not canonical for raw, canonical in mapping.items()):
        raise HistoricalResultCrosscheckError("%s must contain exactly 20 non-empty aliases" % name)
    if len(set(mapping.values())) != 20:
        raise HistoricalResultCrosscheckError("%s must map to exactly 20 canonical teams" % name)
    return mapping  # type: ignore[return-value]


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoricalResultCrosscheckError("contract is unreadable") from exc
    return _object(value, "contract")


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != "1.0.0":
        raise HistoricalResultCrosscheckError("unsupported schema version")
    if contract.get("contract_id") != "ABD-POST-FREEZE-HISTORICAL-RESULT-CROSSCHECK-003":
        raise HistoricalResultCrosscheckError("unexpected contract identifier")
    if contract.get("status") != "PRIVATE_STATIC_SOURCE_CROSSCHECK_ONLY":
        raise HistoricalResultCrosscheckError("cross-check must remain private static only")

    sources = _object(contract.get("sources"), "sources")
    if set(sources) != {"football_data", "openfootball"}:
        raise HistoricalResultCrosscheckError("source set is not exact")
    expected_ids = {
        "football_data": "FOOTBALL_DATA_E0_2025_26",
        "openfootball": "OPENFOOTBALL_ENGLAND_PREMIER_LEAGUE_2025_26_RESULTS",
    }
    for source_name, expected_id in expected_ids.items():
        source = _object(sources[source_name], "sources.%s" % source_name)
        if source.get("source_id") != expected_id or source.get("expected_fixture_count") != 380:
            raise HistoricalResultCrosscheckError("%s source identity is not exact" % source_name)
        _digest(source.get("raw_sha256"), "%s raw_sha256" % source_name)
        _digest(source.get("source_contract_sha256"), "%s source_contract_sha256" % source_name)
        _alias_map(source.get("team_aliases"), "%s team_aliases" % source_name)

    schema = _object(contract.get("schema"), "schema")
    expected_schema = {
        "division": "E0",
        "competition_header": "= England | Premier League 2025/26",
        "season_start": "2025-08-15",
        "season_end": "2026-05-24",
        "expected_team_count": 20,
        "expected_fixture_count": 380,
        "identity_key": "MATCH_DATE_PLUS_CANONICAL_HOME_PLUS_CANONICAL_AWAY",
        "comparison_scope": "FINAL_SCORE_ONLY",
    }
    if dict(schema) != expected_schema:
        raise HistoricalResultCrosscheckError("cross-check schema is not exact")

    boundary = _object(contract.get("runtime_boundary"), "runtime_boundary")
    expected_boundary = {
        "network_collection_enabled": False,
        "external_market_or_account_accessed": False,
        "odds_or_price_truth_claimed": False,
        "model_parameter_or_calibration_update_enabled": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if dict(boundary) != expected_boundary:
        raise HistoricalResultCrosscheckError("runtime boundary is not exact")


def _canonical(raw_name: object, aliases: Mapping[str, str], source_name: str, line_number: int) -> str:
    if not isinstance(raw_name, str) or not raw_name:
        raise HistoricalResultCrosscheckError("%s line %d has empty team identity" % (source_name, line_number))
    try:
        return aliases[raw_name]
    except KeyError as exc:
        raise HistoricalResultCrosscheckError("%s line %d has an unknown team alias" % (source_name, line_number)) from exc


def _score(value: object, source_name: str, field: str, line_number: int) -> int:
    try:
        result = int(str(value))
    except (TypeError, ValueError) as exc:
        raise HistoricalResultCrosscheckError("%s line %d %s is not an integer" % (source_name, line_number, field)) from exc
    if result < 0:
        raise HistoricalResultCrosscheckError("%s line %d %s is negative" % (source_name, line_number, field))
    return result


def _insert_record(
    records: dict[tuple[date, str, str], tuple[int, int]],
    teams: set[str],
    match_date: date,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    source_name: str,
    line_number: int,
) -> None:
    if home == away:
        raise HistoricalResultCrosscheckError("%s line %d has identical teams" % (source_name, line_number))
    key = (match_date, home, away)
    if key in records:
        raise HistoricalResultCrosscheckError("%s line %d duplicates a fixture identity" % (source_name, line_number))
    records[key] = (home_goals, away_goals)
    teams.update((home, away))


def _parse_football_data(data: bytes, source: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[tuple[date, str, str], tuple[int, int]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HistoricalResultCrosscheckError("football-data source is not UTF-8") from exc
    reader = csv.DictReader(StringIO(text, newline=""))
    required = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise HistoricalResultCrosscheckError("football-data CSV is missing result fields")

    aliases = _alias_map(source["team_aliases"], "football_data team_aliases")
    start = date.fromisoformat(str(schema["season_start"]))
    end = date.fromisoformat(str(schema["season_end"]))
    records: dict[tuple[date, str, str], tuple[int, int]] = {}
    teams: set[str] = set()
    for line_number, row in enumerate(reader, start=2):
        if row.get("Div") != schema["division"]:
            raise HistoricalResultCrosscheckError("football-data line %d has an unexpected division" % line_number)
        try:
            match_date = datetime.strptime(str(row.get("Date")), "%d/%m/%Y").date()
        except ValueError as exc:
            raise HistoricalResultCrosscheckError("football-data line %d has an invalid date" % line_number) from exc
        if not start <= match_date <= end:
            raise HistoricalResultCrosscheckError("football-data line %d date is outside the season" % line_number)
        home_goals = _score(row.get("FTHG"), "football-data", "FTHG", line_number)
        away_goals = _score(row.get("FTAG"), "football-data", "FTAG", line_number)
        expected_ftr = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
        if row.get("FTR") != expected_ftr:
            raise HistoricalResultCrosscheckError("football-data line %d result code disagrees with score" % line_number)
        _insert_record(
            records,
            teams,
            match_date,
            _canonical(row.get("HomeTeam"), aliases, "football-data", line_number),
            _canonical(row.get("AwayTeam"), aliases, "football-data", line_number),
            home_goals,
            away_goals,
            "football-data",
            line_number,
        )
    if len(records) != int(source["expected_fixture_count"]) or len(teams) != int(schema["expected_team_count"]):
        raise HistoricalResultCrosscheckError("football-data source does not have the contracted fixture or team count")
    return records


def _parse_openfootball(data: bytes, source: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[tuple[date, str, str], tuple[int, int]]:
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise HistoricalResultCrosscheckError("openfootball source is not UTF-8") from exc
    if not lines or lines[0].strip() != schema["competition_header"]:
        raise HistoricalResultCrosscheckError("openfootball competition header is not exact")

    aliases = _alias_map(source["team_aliases"], "openfootball team_aliases")
    start = date.fromisoformat(str(schema["season_start"]))
    end = date.fromisoformat(str(schema["season_end"]))
    current_year: int | None = None
    previous_month: int | None = None
    current_date: date | None = None
    records: dict[tuple[date, str, str], tuple[int, int]] = {}
    teams: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        date_match = _OPEN_DATE.match(line)
        if date_match is not None:
            month = _MONTHS[date_match.group("month")]
            explicit_year = date_match.group("year")
            if explicit_year is not None:
                current_year = int(explicit_year)
            elif current_year is None:
                raise HistoricalResultCrosscheckError("openfootball line %d has a date without a year anchor" % line_number)
            elif previous_month is not None and month < previous_month:
                current_year += 1
            previous_month = month
            try:
                current_date = date(current_year, month, int(date_match.group("day")))
            except ValueError as exc:
                raise HistoricalResultCrosscheckError("openfootball line %d has an invalid date" % line_number) from exc
            if not start <= current_date <= end:
                raise HistoricalResultCrosscheckError("openfootball line %d date is outside the season" % line_number)
            continue
        if not _OPEN_RESULT_PREFIX.match(line):
            continue
        if current_date is None:
            raise HistoricalResultCrosscheckError("openfootball line %d result has no date context" % line_number)
        match = _OPEN_RESULT.match(line)
        if match is None:
            raise HistoricalResultCrosscheckError("openfootball line %d result syntax is invalid" % line_number)
        home_goals = _score(match.group("home_goals"), "openfootball", "home goals", line_number)
        away_goals = _score(match.group("away_goals"), "openfootball", "away goals", line_number)
        home_half = _score(match.group("home_half"), "openfootball", "home half-time", line_number)
        away_half = _score(match.group("away_half"), "openfootball", "away half-time", line_number)
        if home_half > home_goals or away_half > away_goals:
            raise HistoricalResultCrosscheckError("openfootball line %d has an impossible half-time score" % line_number)
        _insert_record(
            records,
            teams,
            current_date,
            _canonical(match.group("home").strip(), aliases, "openfootball", line_number),
            _canonical(match.group("away").strip(), aliases, "openfootball", line_number),
            home_goals,
            away_goals,
            "openfootball",
            line_number,
        )
    if len(records) != int(source["expected_fixture_count"]) or len(teams) != int(schema["expected_team_count"]):
        raise HistoricalResultCrosscheckError("openfootball source does not have the contracted fixture or team count")
    return records


def build_receipt(
    football_data: bytes,
    openfootball: bytes,
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
        raise HistoricalResultCrosscheckError("observation date is invalid") from exc

    sources = _object(contract["sources"], "sources")
    football_source = _object(sources["football_data"], "sources.football_data")
    open_source = _object(sources["openfootball"], "sources.openfootball")
    if _sha256(football_data) != football_source["raw_sha256"]:
        raise HistoricalResultCrosscheckError("football-data raw SHA-256 does not match the contract")
    if _sha256(openfootball) != open_source["raw_sha256"]:
        raise HistoricalResultCrosscheckError("openfootball raw SHA-256 does not match the contract")

    schema = _object(contract["schema"], "schema")
    football_records = _parse_football_data(football_data, football_source, schema)
    open_records = _parse_openfootball(openfootball, open_source, schema)
    football_keys = set(football_records)
    open_keys = set(open_records)
    missing_from_openfootball = football_keys - open_keys
    missing_from_football_data = open_keys - football_keys
    score_disagreements = [key for key in football_keys & open_keys if football_records[key] != open_records[key]]
    if missing_from_openfootball or missing_from_football_data or score_disagreements:
        raise HistoricalResultCrosscheckError("static source identity or final-score cross-check failed")

    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_POST_FREEZE_HISTORICAL_RESULT_CROSSCHECK",
        "status": "PASS_STATIC_HISTORICAL_RESULT_CROSSCHECK_READY_FOR_PRIVATE_ARCHIVE",
        "observed_on": observed_date.isoformat(),
        "comparison": {
            "identity_key": schema["identity_key"],
            "comparison_scope": schema["comparison_scope"],
            "matched_fixture_count": len(football_keys),
            "missing_from_openfootball_count": 0,
            "missing_from_football_data_count": 0,
            "final_score_disagreement_count": 0,
        },
        "sources": {
            "football_data": {
                "source_id": football_source["source_id"],
                "raw_sha256": football_source["raw_sha256"],
                "source_contract_sha256": football_source["source_contract_sha256"],
            },
            "openfootball": {
                "source_id": open_source["source_id"],
                "raw_sha256": open_source["raw_sha256"],
                "source_contract_sha256": open_source["source_contract_sha256"],
            },
        },
        "contract_sha256": contract_sha256,
        "validator_sha256": validator_sha256,
        "boundaries": dict(_object(contract["runtime_boundary"], "runtime_boundary")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--football-data", type=Path, required=True)
    parser.add_argument("--openfootball", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    receipt = build_receipt(
        args.football_data.read_bytes(),
        args.openfootball.read_bytes(),
        contract,
        _sha256(args.contract.read_bytes()),
        _sha256(Path(__file__).read_bytes()),
        args.observed_on,
    )
    args.receipt_out.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "matched_fixture_count": receipt["comparison"]["matched_fixture_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
