from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from football_data_static_source import FootballDataSourceError, build_receipt, validate_contract


CONTRACT_PATH = RUNTIME / "football_data_static_source_contract.json"
VALIDATOR_PATH = RUNTIME / "football_data_static_source.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _csv(*, rows: int = 300, division: str = "E0", odds: str = "1.50", include_b365: bool = True, result: str = "H") -> bytes:
    columns = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    if not include_b365:
        columns.remove("B365A")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for _ in range(rows):
        row = {
            "Div": division,
            "Date": "15/08/2025",
            "HomeTeam": "Home",
            "AwayTeam": "Away",
            "FTHG": "1",
            "FTAG": "0",
            "FTR": result,
            "B365H": odds,
            "B365D": "3.00",
            "B365A": "7.00",
        }
        writer.writerow({key: row[key] for key in columns})
    return stream.getvalue().encode("utf-8")


def test_contract_is_one_shot_internal_only_and_runtime_disabled() -> None:
    contract = _contract()

    validate_contract(contract)
    assert contract["collection"]["automatic_scheduler_allowed"] is False
    assert contract["collection"]["maximum_network_fetches_for_this_contract"] == 2
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


def test_valid_static_csv_builds_a_non_advisory_private_archive_receipt() -> None:
    data = _csv()
    contract = _contract()
    receipt = build_receipt(
        data,
        contract,
        hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest(),
        "2026-08-10",
        2,
    )

    assert receipt["status"] == "PASS_STATIC_HISTORICAL_SOURCE_READY_FOR_PRIVATE_ARCHIVE"
    assert receipt["source_file"]["row_count"] == 300
    assert receipt["source_file"]["division"] == "E0"
    assert receipt["network_fetches_observed"] == 2
    assert receipt["validator_sha256"] == hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest()
    assert receipt["boundaries"]["recommendation_generated_or_enabled"] is False
    assert receipt["boundaries"]["order_submission_enabled"] is False


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_csv(rows=299), "fewer rows"),
        (_csv(division="E1"), "division"),
        (_csv(odds="1.00"), "decimal-odds"),
        (_csv(include_b365=False), "missing required columns"),
        (_csv(result="A"), "full-time result"),
    ],
)
def test_invalid_csv_fails_closed(data: bytes, message: str) -> None:
    with pytest.raises(FootballDataSourceError, match=message):
        build_receipt(data, _contract(), "0" * 64, "1" * 64, "2026-08-10", 2)


def test_excess_network_fetch_count_fails_closed() -> None:
    with pytest.raises(FootballDataSourceError, match="network fetch count"):
        build_receipt(_csv(), _contract(), "0" * 64, "1" * 64, "2026-08-10", 3)


def test_invalid_provenance_digest_fails_closed() -> None:
    with pytest.raises(FootballDataSourceError, match="validator_sha256"):
        build_receipt(_csv(), _contract(), "0" * 64, "not-a-digest", "2026-08-10", 2)


def test_adapter_has_no_network_client_or_scheduler_dependency() -> None:
    source = (RUNTIME / "football_data_static_source.py").read_text(encoding="utf-8")

    for forbidden in ("import requests", "import urllib", "import socket", "import subprocess", "time.sleep("):
        assert forbidden not in source
