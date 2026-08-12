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

from current_production_control_plane_remediation import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionRemediationError,
    build_receipt,
    evaluate_baseline,
    validate_contract,
)


CONTRACT_PATH = RUNTIME / "current_production_control_plane_remediation_contract.json"
VALIDATOR_PATH = RUNTIME / "current_production_control_plane_remediation.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _baseline() -> dict[str, object]:
    unit = {"load_state": "not-found", "active_state": "inactive", "unit_file_state": ""}
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CONTROL_PLANE_METADATA",
        "observed_on": "2026-08-12",
        "prior_image": {
            "host_inventory": "ABSENT",
            "private_source_catalog": "UNKNOWN_PRIVATE_CATALOG_NOT_READABLE",
        },
        "core_units": {"abd.service": deepcopy(unit), "abd-cloudflared.service": deepcopy(unit)},
        "connector_config": {"kind": "missing", "hostname_configured": "UNKNOWN"},
    }


def test_contract_preserves_non_mutating_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["host_runtime_or_configuration_changed"] is False
    assert boundary["image_loaded_or_retagged"] is False
    assert boundary["unit_created_enabled_or_started"] is False
    assert boundary["real_time_soak_waited"] is False
    assert boundary["order_submission_enabled"] is False


def test_exact_baseline_passes_contract_without_authorizing_execution() -> None:
    result = evaluate_baseline(_contract(), _baseline())

    assert result["status"] == PASS_STATUS
    assert result["contract_valid"] is True
    assert result["execution_authorized"] is False
    assert result["failure_codes"] == []
    assert result["unresolved_prerequisites"] == [
        "PRIVATE_RECOVERABLE_OCI_ARCHIVE_VERIFIED",
        "SEPARATE_CORE_CAPACITY_AND_EXECUTION_CONTRACT",
        "SEPARATE_CONNECTOR_NONSECRET_CONFIG_AND_SECRET_BINDING_CONTRACT",
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["prior_image"].update({"host_inventory": "PRESENT"}),
        lambda value: value["core_units"]["abd.service"].update({"load_state": "loaded"}),
        lambda value: value["connector_config"].update({"kind": "regular"}),
    ],
)
def test_baseline_divergence_is_rejected_before_execution(mutate) -> None:
    baseline = _baseline()
    mutate(baseline)

    with pytest.raises(CurrentProductionRemediationError):
        evaluate_baseline(_contract(), baseline)


def test_contract_mutation_is_rejected() -> None:
    contract = _contract()
    targets = contract["remediation_targets"]
    assert isinstance(targets, dict)
    rollback_asset = targets["rollback_asset"]
    assert isinstance(rollback_asset, dict)
    rollback_asset["image_load_authorized_by_this_contract"] = True

    with pytest.raises(CurrentProductionRemediationError, match="rollback asset"):
        validate_contract(contract)


def test_receipt_is_redacted_and_cannot_claim_host_remediation() -> None:
    contract = _contract()
    receipt = build_receipt(contract, _baseline())
    serialized = json.dumps(receipt, sort_keys=True)
    targets = contract["remediation_targets"]
    assert isinstance(targets, dict)
    rollback_asset = targets["rollback_asset"]
    assert isinstance(rollback_asset, dict)

    assert receipt["status"] == PASS_STATUS
    assert receipt["execution_authorized"] is False
    assert receipt["observed"]["prior_image_present"] is False
    assert receipt["observed"]["connector_hostname_state"] == "UNKNOWN"
    assert str(rollback_asset["prior_image_id"]) not in serialized
    assert "current_candidate_shadow_changed" not in serialized


def test_source_has_no_host_mutation_or_external_network_capability() -> None:
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
