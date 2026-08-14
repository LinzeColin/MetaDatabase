from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from historical_result_crosscheck import HistoricalResultCrosscheckError, build_receipt, validate_contract


CONTRACT_PATH = RUNTIME / "historical_result_crosscheck_contract.json"
VALIDATOR_PATH = RUNTIME / "historical_result_crosscheck.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _entries() -> list[tuple[str, str, str, int, int]]:
    teams = list(_contract()["sources"]["football_data"]["team_aliases"].values())
    return [("15/08/2025", home, away, 1, 0) for home in teams for away in teams if home != away]


def _inverse_aliases(source: str) -> dict[str, str]:
    aliases = _contract()["sources"][source]["team_aliases"]
    return {canonical: raw for raw, canonical in aliases.items()}


def _football_data(entries: list[tuple[str, str, str, int, int]]) -> bytes:
    inverse = _inverse_aliases("football_data")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"])
    writer.writeheader()
    for match_date, home, away, home_goals, away_goals in entries:
        writer.writerow(
            {
                "Div": "E0",
                "Date": match_date,
                "HomeTeam": inverse[home],
                "AwayTeam": inverse[away],
                "FTHG": home_goals,
                "FTAG": away_goals,
                "FTR": "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D",
            }
        )
    return stream.getvalue().encode("utf-8")


def _openfootball(entries: list[tuple[str, str, str, int, int]]) -> bytes:
    contract = _contract()
    inverse = _inverse_aliases("openfootball")
    lines = [contract["schema"]["competition_header"], "", "Fri Aug 15 2025"]
    for _, home, away, home_goals, away_goals in entries:
        lines.append("  19:00   %s  %d-%d (0-0)  %s" % (inverse[home], home_goals, away_goals, inverse[away]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _bound_contract(football_data: bytes, openfootball: bytes) -> dict[str, object]:
    contract = deepcopy(_contract())
    contract["sources"]["football_data"]["raw_sha256"] = hashlib.sha256(football_data).hexdigest()
    contract["sources"]["openfootball"]["raw_sha256"] = hashlib.sha256(openfootball).hexdigest()
    return contract


def _valid_inputs() -> tuple[bytes, bytes, dict[str, object]]:
    entries = _entries()
    football_data = _football_data(entries)
    openfootball = _openfootball(entries)
    return football_data, openfootball, _bound_contract(football_data, openfootball)


def test_contract_is_private_static_and_disables_model_and_orders() -> None:
    contract = _contract()

    validate_contract(contract)
    assert contract["status"] == "PRIVATE_STATIC_SOURCE_CROSSCHECK_ONLY"
    assert contract["runtime_boundary"]["network_collection_enabled"] is False
    assert contract["runtime_boundary"]["model_parameter_or_calibration_update_enabled"] is False
    assert contract["runtime_boundary"]["order_submission_enabled"] is False


def test_matching_historical_sources_emit_only_aggregate_receipt() -> None:
    football_data, openfootball, contract = _valid_inputs()
    receipt = build_receipt(
        football_data,
        openfootball,
        contract,
        hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest(),
        "2026-08-10",
    )

    assert receipt["status"] == "PASS_STATIC_HISTORICAL_RESULT_CROSSCHECK_READY_FOR_PRIVATE_ARCHIVE"
    assert receipt["comparison"] == {
        "identity_key": "MATCH_DATE_PLUS_CANONICAL_HOME_PLUS_CANONICAL_AWAY",
        "comparison_scope": "FINAL_SCORE_ONLY",
        "matched_fixture_count": 380,
        "missing_from_openfootball_count": 0,
        "missing_from_football_data_count": 0,
        "final_score_disagreement_count": 0,
    }
    assert receipt["boundaries"]["model_parameter_or_calibration_update_enabled"] is False
    assert receipt["boundaries"]["recommendation_generated_or_enabled"] is False


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda football, openfootball, contract: (_football_data(_entries()[:-1]), openfootball, contract), "raw SHA-256"),
        (lambda football, openfootball, contract: (football, openfootball.replace(b"  1-0 (0-0)", b"  0-1 (0-0)", 1), _bound_contract(football, openfootball.replace(b"  1-0 (0-0)", b"  0-1 (0-0)", 1))), "cross-check failed"),
        (lambda football, openfootball, contract: (football, openfootball.replace(b"Arsenal", b"Unknown Team", 1), _bound_contract(football, openfootball.replace(b"Arsenal", b"Unknown Team", 1))), "unknown team alias"),
        (lambda football, openfootball, contract: (football, openfootball, {**contract, "sources": {**contract["sources"], "football_data": {**contract["sources"]["football_data"], "raw_sha256": "0" * 64}}}), "raw SHA-256"),
    ],
)
def test_source_mismatch_or_unrecognized_data_fails_closed(mutator, message: str) -> None:
    football_data, openfootball, contract = _valid_inputs()
    mutated_football, mutated_openfootball, mutated_contract = mutator(football_data, openfootball, contract)
    with pytest.raises(HistoricalResultCrosscheckError, match=message):
        build_receipt(mutated_football, mutated_openfootball, mutated_contract, "0" * 64, "1" * 64, "2026-08-10")


def test_invalid_observation_date_fails_closed() -> None:
    football_data, openfootball, contract = _valid_inputs()
    with pytest.raises(HistoricalResultCrosscheckError, match="observation date"):
        build_receipt(football_data, openfootball, contract, "0" * 64, "1" * 64, "not-a-date")


def test_adapter_has_no_network_scheduler_or_model_execution_dependency() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in ("import requests", "import urllib", "import socket", "import subprocess", "time.sleep(", "sklearn", "numpy"):
        assert forbidden not in source
