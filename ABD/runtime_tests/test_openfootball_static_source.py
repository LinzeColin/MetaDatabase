from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from openfootball_static_source import OpenFootballSourceError, build_receipt, validate_contract


CONTRACT_PATH = RUNTIME / "openfootball_static_source_contract.json"
VALIDATOR_PATH = RUNTIME / "openfootball_static_source.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _data(*, match_count: int = 380, malformed: bool = False, impossible_half_time: bool = False, duplicate_fixture: bool = False) -> bytes:
    contract = _contract()
    schema = contract["schema"]
    teams = ["Team%02d" % number for number in range(1, 21)]
    matches = [
        "  19:00   %s  1-0 (1-0)  %s" % (home, away)
        for home in teams
        for away in teams
        if home != away
    ][:match_count]
    if malformed:
        matches[0] = "  19:00   Team01  Team02"
    if impossible_half_time:
        matches[0] = "  19:00   Team01  1-0 (2-0)  Team02"
    if duplicate_fixture:
        matches[-1] = matches[0]
    return (
        "\n".join(
            [
                schema["competition_header"],
                "",
                schema["dates_header"],
                schema["teams_header"],
                schema["matches_header"],
                "",
                "▪ Regular Season - 1",
                "Fri Aug 15 2025",
                *matches,
            ]
        )
        + "\n"
    ).encode("utf-8")


def test_contract_is_cc0_one_shot_internal_only_and_runtime_disabled() -> None:
    contract = _contract()

    validate_contract(contract)
    assert contract["source"]["formal_license_spdx"] == "CC0-1.0"
    assert contract["collection"]["maximum_network_fetches_for_this_contract"] == 3
    assert contract["collection"]["raw_data_destination"] == "Private-MetaDatabase_only"
    assert contract["runtime_boundary"] == {
        "runtime_network_collection_enabled": False,
        "dynamic_platform_collection_enabled": False,
        "real_time_freshness_claimed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "market_account_TAB_or_Gmail_accessed": False,
        "incremental_cash_spent_aud": "0.00",
    }


def test_valid_static_results_build_a_non_advisory_private_archive_receipt() -> None:
    data = _data()
    contract = _contract()
    receipt = build_receipt(
        data,
        contract,
        hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest(),
        "2026-08-10",
        3,
    )

    assert receipt["status"] == "PASS_STATIC_HISTORICAL_RESULT_SOURCE_READY_FOR_PRIVATE_ARCHIVE"
    assert receipt["source_file"]["match_count"] == 380
    assert receipt["source_file"]["team_count"] == 20
    assert receipt["network_fetches_observed"] == 3
    assert receipt["validator_sha256"] == hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest()
    assert receipt["boundaries"]["recommendation_generated_or_enabled"] is False
    assert receipt["boundaries"]["order_submission_enabled"] is False


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_data(match_count=379), "match count"),
        (_data(malformed=True), "malformed"),
        (_data(impossible_half_time=True), "impossible half-time"),
        (_data(duplicate_fixture=True), "duplicates"),
        (_data().replace(b"= England | Premier League 2025/26", b"= England | Premier League 2024/25", 1), "competition header"),
    ],
)
def test_invalid_results_fail_closed(data: bytes, message: str) -> None:
    with pytest.raises(OpenFootballSourceError, match=message):
        build_receipt(data, _contract(), "0" * 64, "1" * 64, "2026-08-10", 3)


def test_nonexact_network_fetch_count_fails_closed() -> None:
    with pytest.raises(OpenFootballSourceError, match="network fetch count"):
        build_receipt(_data(), _contract(), "0" * 64, "1" * 64, "2026-08-10", 2)


def test_invalid_provenance_digest_fails_closed() -> None:
    with pytest.raises(OpenFootballSourceError, match="validator_sha256"):
        build_receipt(_data(), _contract(), "0" * 64, "not-a-digest", "2026-08-10", 3)


def test_adapter_has_no_network_client_or_scheduler_dependency() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in ("import requests", "import urllib", "import socket", "import subprocess", "time.sleep("):
        assert forbidden not in source
