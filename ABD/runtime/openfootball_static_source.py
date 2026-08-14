#!/usr/bin/env python3
"""Validate one CC0-scope OpenFootball historical result file without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping


class OpenFootballSourceError(ValueError):
    """Raised when the one-shot static OpenFootball source contract is not satisfied."""


_RESULT_PREFIX = re.compile(r"^\s*(?:[01]\d|2[0-3]):[0-5]\d\b")
_RESULT_LINE = re.compile(
    r"^\s*(?:[01]\d|2[0-3]):[0-5]\d\s+"
    r"(?P<home>.+?)\s+(?P<home_goals>\d+)-(?P<away_goals>\d+)\s+"
    r"\((?P<home_half>\d+)-(?P<away_half>\d+)\)\s+(?P<away>.+?)\s*$"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise OpenFootballSourceError("%s must be a lowercase SHA-256 digest" % name)
    return value


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise OpenFootballSourceError("%s must be an object" % name)
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise OpenFootballSourceError("%s must be a non-empty string" % name)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpenFootballSourceError("contract is unreadable") from exc
    return _object(value, "contract")


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != "1.0.0":
        raise OpenFootballSourceError("unsupported schema version")
    if contract.get("status") != "ONE_SHOT_MANUAL_INTERNAL_IMPORT_ONLY":
        raise OpenFootballSourceError("source contract must remain one-shot only")

    source = _object(contract.get("source"), "source")
    collection = _object(contract.get("collection"), "collection")
    schema = _object(contract.get("schema"), "schema")
    boundary = _object(contract.get("runtime_boundary"), "runtime_boundary")

    expected_source = {
        "source_id": "OPENFOOTBALL_ENGLAND_PREMIER_LEAGUE_2025_26_RESULTS",
        "publisher": "OpenFootball / football.db",
        "repository_url": "https://github.com/openfootball/england",
        "license_url": "https://github.com/openfootball/england/blob/master/LICENSE.md",
        "license_metadata_url": "https://api.github.com/repos/openfootball/england/license",
        "license_metadata_content_git_sha1": "670154e3538863b2d9891fd5483160fbdfc89164",
        "source_url": "https://raw.githubusercontent.com/openfootball/england/master/2025-26/1-premierleague.txt",
        "source_format": "Football.TXT",
        "formal_license_spdx": "CC0-1.0",
        "formal_license_name": "Creative Commons Zero v1.0 Universal",
        "permitted_use_here": "INTERNAL_HISTORICAL_RESULT_CALIBRATION_RESEARCH_ONLY",
        "data_scope": "HISTORICAL_MATCH_RESULTS_ONLY",
        "prohibited_claims": [
            "official_competition_record_equivalence",
            "market_price_feed",
            "current_provider_price_truth",
            "TAB_or_Sportsbet_equivalence",
            "real_time_market_coverage",
        ],
    }
    if dict(source) != expected_source:
        raise OpenFootballSourceError("source scope is not exact")

    expected_collection = {
        "automatic_scheduler_allowed": False,
        "automatic_retry_allowed": False,
        "maximum_network_fetches_for_this_contract": 3,
        "network_fetch_plan": [
            "github_license_metadata_check",
            "bounded_schema_preflight",
            "single_full_static_download",
        ],
        "collection_mode": "MANUAL_ONE_SHOT_STATIC_FILE",
        "raw_data_destination": "Private-MetaDatabase_only",
        "source_code_repository_raw_data_allowed": False,
        "source_data_republication_by_ABD_allowed": False,
    }
    if dict(collection) != expected_collection:
        raise OpenFootballSourceError("collection boundary is not exact")

    expected_schema = {
        "competition_header": "= England | Premier League 2025/26",
        "dates_header": "# Dates    Fri Aug 15 2025 - Sun May 24 2026 (282d)",
        "teams_header": "# Teams    20",
        "matches_header": "# Matches  380",
        "season_start": "2025-08-15",
        "season_end": "2026-05-24",
        "expected_team_count": 20,
        "expected_match_count": 380,
        "result_data_scope": "FINAL_SCORE_ONLY",
    }
    if dict(schema) != expected_schema:
        raise OpenFootballSourceError("source schema is not exact")

    expected_boundary = {
        "runtime_network_collection_enabled": False,
        "dynamic_platform_collection_enabled": False,
        "real_time_freshness_claimed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "market_account_TAB_or_Gmail_accessed": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if dict(boundary) != expected_boundary:
        raise OpenFootballSourceError("runtime boundary is not exact")


def _result_summary(data: bytes, schema: Mapping[str, Any]) -> tuple[int, int]:
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise OpenFootballSourceError("source bytes are not UTF-8 text") from exc
    if not lines or lines[0].strip() != schema["competition_header"]:
        raise OpenFootballSourceError("competition header is not exact")

    for header_name in ("dates_header", "teams_header", "matches_header"):
        if str(schema[header_name]) not in lines:
            raise OpenFootballSourceError("%s is missing" % header_name)

    fixtures: set[tuple[str, str]] = set()
    teams: set[str] = set()
    match_count = 0
    for line_number, line in enumerate(lines, start=1):
        if not _RESULT_PREFIX.match(line):
            continue
        match = _RESULT_LINE.match(line)
        if match is None:
            raise OpenFootballSourceError("result line %d is malformed" % line_number)
        home = match.group("home").strip()
        away = match.group("away").strip()
        if not home or not away or home == away:
            raise OpenFootballSourceError("result line %d has invalid team identity" % line_number)
        home_goals = int(match.group("home_goals"))
        away_goals = int(match.group("away_goals"))
        home_half = int(match.group("home_half"))
        away_half = int(match.group("away_half"))
        if home_half > home_goals or away_half > away_goals:
            raise OpenFootballSourceError("result line %d has impossible half-time score" % line_number)
        fixture = (home, away)
        if fixture in fixtures:
            raise OpenFootballSourceError("result line %d duplicates a home/away fixture" % line_number)
        fixtures.add(fixture)
        teams.update((home, away))
        match_count += 1

    if match_count != int(schema["expected_match_count"]):
        raise OpenFootballSourceError("match count does not match the static contract")
    if len(teams) != int(schema["expected_team_count"]):
        raise OpenFootballSourceError("team count does not match the static contract")
    return match_count, len(teams)


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
    try:
        observed_date = date.fromisoformat(observed_on)
    except ValueError as exc:
        raise OpenFootballSourceError("observation date is invalid") from exc
    if not data:
        raise OpenFootballSourceError("source file is empty")

    source = _object(contract["source"], "source")
    collection = _object(contract["collection"], "collection")
    schema = _object(contract["schema"], "schema")
    if isinstance(network_fetches, bool) or not isinstance(network_fetches, int) or network_fetches != int(collection["maximum_network_fetches_for_this_contract"]):
        raise OpenFootballSourceError("network fetch count is not the exact contract plan")
    match_count, team_count = _result_summary(data, schema)
    return {
        "schema_version": "1.0.0",
        "receipt_type": "ABD_POST_FREEZE_STATIC_SOURCE_IMPORT",
        "status": "PASS_STATIC_HISTORICAL_RESULT_SOURCE_READY_FOR_PRIVATE_ARCHIVE",
        "observed_on": observed_date.isoformat(),
        "source": {
            "source_id": source["source_id"],
            "publisher": source["publisher"],
            "repository_url": source["repository_url"],
            "source_url": source["source_url"],
            "license_url": source["license_url"],
            "formal_license_spdx": source["formal_license_spdx"],
            "permitted_use_here": source["permitted_use_here"],
            "data_scope": source["data_scope"],
        },
        "source_file": {
            "sha256": _sha256(data),
            "bytes": len(data),
            "match_count": match_count,
            "team_count": team_count,
            "season_start": schema["season_start"],
            "season_end": schema["season_end"],
            "result_data_scope": schema["result_data_scope"],
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
    print(json.dumps({"status": receipt["status"], "match_count": receipt["source_file"]["match_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
