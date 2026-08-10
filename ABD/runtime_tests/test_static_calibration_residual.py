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

from static_calibration_residual import StaticCalibrationResidualError, build_receipt, validate_contract


CONTRACT_PATH = RUNTIME / "static_calibration_residual_contract.json"
VALIDATOR_PATH = RUNTIME / "static_calibration_residual.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _football_data(*, rows: int = 380, home_odds: str = "2.00", result: str = "H") -> bytes:
    stream = io.StringIO(newline="")
    fields = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for index in range(rows):
        writer.writerow(
            {
                "Div": "E0",
                "Date": "15/08/2025",
                "HomeTeam": "Home%03d" % index,
                "AwayTeam": "Away%03d" % index,
                "FTHG": "1" if result == "H" else "0",
                "FTAG": "1" if result == "A" else "0",
                "FTR": result,
                "B365H": home_odds,
                "B365D": "3.00",
                "B365A": "6.00",
            }
        )
    return stream.getvalue().encode("utf-8")


def _crosscheck_receipt() -> bytes:
    return json.dumps(
        {
            "status": "PASS_STATIC_HISTORICAL_RESULT_CROSSCHECK_READY_FOR_PRIVATE_ARCHIVE",
            "contract_sha256": "2" * 64,
            "comparison": {
                "matched_fixture_count": 380,
                "missing_from_openfootball_count": 0,
                "missing_from_football_data_count": 0,
                "final_score_disagreement_count": 0,
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def _bound_contract(football_data: bytes, crosscheck_receipt: bytes) -> dict[str, object]:
    contract = deepcopy(_contract())
    contract["inputs"]["football_data"]["raw_sha256"] = hashlib.sha256(football_data).hexdigest()
    contract["inputs"]["historical_crosscheck_receipt"]["raw_sha256"] = hashlib.sha256(crosscheck_receipt).hexdigest()
    contract["inputs"]["historical_crosscheck_receipt"]["crosscheck_contract_sha256"] = "2" * 64
    return contract


def _valid_inputs() -> tuple[bytes, bytes, dict[str, object]]:
    football_data = _football_data()
    crosscheck_receipt = _crosscheck_receipt()
    return football_data, crosscheck_receipt, _bound_contract(football_data, crosscheck_receipt)


def test_contract_keeps_model_and_orders_disabled() -> None:
    contract = _contract()

    validate_contract(contract)
    assert contract["status"] == "PRIVATE_STATIC_DESCRIPTIVE_CALIBRATION_ONLY"
    assert contract["runtime_boundary"]["model_parameter_or_calibration_update_enabled"] is False
    assert contract["runtime_boundary"]["model_beta_or_ga_enabled"] is False
    assert contract["runtime_boundary"]["order_submission_enabled"] is False


def test_static_decimal_projection_is_descriptive_and_aggregated() -> None:
    football_data, crosscheck_receipt, contract = _valid_inputs()
    receipt = build_receipt(
        football_data,
        crosscheck_receipt,
        contract,
        hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        hashlib.sha256(VALIDATOR_PATH.read_bytes()).hexdigest(),
        "2026-08-10",
    )

    assert receipt["status"] == "PASS_STATIC_DESCRIPTIVE_CALIBRATION_RESIDUAL_READY_FOR_PRIVATE_ARCHIVE"
    assert receipt["calibration_scope"] == {
        "probability_formula": "inverse_decimal_odds_divided_by_sum_of_all_three_inverse_decimal_odds",
        "fixture_count": 380,
        "outcome_rows": 1140,
        "evidence_status": "STATIC_SINGLE_SEASON_DESCRIPTION_NOT_ELIGIBLE_FOR_MODEL_UPDATE",
    }
    assert receipt["overall_by_outcome"]["H"]["observation_count"] == 380
    assert receipt["overall_by_outcome"]["H"]["empirical_outcome_rate"] == "1"
    assert receipt["boundaries"]["model_parameter_or_calibration_update_enabled"] is False
    assert receipt["boundaries"]["recommendation_generated_or_enabled"] is False


@pytest.mark.parametrize(
    ("football_data", "crosscheck_receipt", "contract_mutator", "message"),
    [
        (_football_data(rows=379), _crosscheck_receipt(), lambda contract: contract, "fixture count"),
        (_football_data(home_odds="1.00"), _crosscheck_receipt(), lambda contract: contract, "non-decimal"),
        (_football_data(), json.dumps({"status": "FAIL"}).encode("utf-8"), lambda contract: contract, "status"),
        (_football_data(), _crosscheck_receipt(), lambda contract: {**contract, "inputs": {**contract["inputs"], "football_data": {**contract["inputs"]["football_data"], "raw_sha256": "0" * 64}}}, "raw SHA-256"),
    ],
)
def test_invalid_input_or_provenance_fails_closed(football_data: bytes, crosscheck_receipt: bytes, contract_mutator, message: str) -> None:
    contract = _bound_contract(football_data, crosscheck_receipt)
    with pytest.raises(StaticCalibrationResidualError, match=message):
        build_receipt(football_data, crosscheck_receipt, contract_mutator(contract), "0" * 64, "1" * 64, "2026-08-10")


def test_invalid_observation_date_fails_closed() -> None:
    football_data, crosscheck_receipt, contract = _valid_inputs()
    with pytest.raises(StaticCalibrationResidualError, match="observation date"):
        build_receipt(football_data, crosscheck_receipt, contract, "0" * 64, "1" * 64, "not-a-date")


def test_adapter_has_no_network_scheduler_or_model_execution_dependency() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in ("import requests", "import urllib", "import socket", "import subprocess", "time.sleep(", "sklearn", "numpy"):
        assert forbidden not in source
