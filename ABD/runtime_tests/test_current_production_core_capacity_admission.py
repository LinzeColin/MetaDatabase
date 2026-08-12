from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_core_capacity_admission import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionCoreCapacityAdmissionError,
    build_receipt,
    evaluate_admission,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "current_production_core_capacity_admission_contract.json"
VALIDATOR_PATH = RUNTIME / "current_production_core_capacity_admission.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: int) -> dict[str, int]:
    values = {
        "vcpu": 6,
        "memory_kib": 11956724,
        "physical_disk_bytes": 107374182400,
        "swap_entries": 0,
    }
    values.update(overrides)
    return values


def test_contract_preserves_read_only_capacity_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["live_host_capacity_metadata_read"] is True
    assert boundary["remote_script_written"] is False
    assert boundary["unit_created_enabled_or_started"] is False
    assert boundary["host_runtime_or_configuration_changed"] is False
    assert boundary["real_time_soak_waited"] is False


def test_current_capacity_passes_but_cannot_authorize_core_start() -> None:
    result = evaluate_admission(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["capacity_admitted"] is True
    assert result["core_start_authorized"] is False
    assert result["failure_codes"] == []


@pytest.mark.parametrize(
    ("key", "value", "failure_code"),
    [
        ("vcpu", 1, "MIN_VCPU"),
        ("memory_kib", 4194303, "MIN_MEMORY_KIB"),
        ("physical_disk_bytes", 42949672959, "MIN_PHYSICAL_DISK_BYTES"),
        ("swap_entries", 1, "SWAP_ENTRIES_ZERO"),
    ],
)
def test_each_capacity_or_swap_failure_fails_closed(key: str, value: int, failure_code: str) -> None:
    result = evaluate_admission(_contract(), _facts(**{key: value}))

    assert result["status"] == FAIL_STATUS
    assert result["capacity_admitted"] is False
    assert result["core_start_authorized"] is False
    assert result["failure_codes"] == [failure_code]


def test_contract_cannot_authorize_a_unit_start() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["unit_created_enabled_or_started"] = True

    with pytest.raises(CurrentProductionCoreCapacityAdmissionError, match="source boundary"):
        validate_contract(contract)


def test_receipt_redacts_raw_host_capacity_and_keeps_start_unauthorized() -> None:
    contract = _contract()
    receipt = build_receipt(contract, evaluate_admission(contract, _facts()), "2026-08-12")
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["capacity_admitted"] is True
    assert receipt["core_start_authorized"] is False
    assert all(set(check) == {"id", "passed"} for check in receipt["checks"])
    assert "11956724" not in serialized
    assert "107374182400" not in serialized


def test_source_has_no_network_or_runtime_mutation_capability() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "import subprocess",
        "import requests",
        "import urllib",
        "time.sleep(",
        "docker load",
        "docker tag",
        "systemctl start",
        "systemctl enable",
        "cloudflared tunnel",
    ):
        assert forbidden not in source
