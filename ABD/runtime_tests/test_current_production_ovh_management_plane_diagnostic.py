from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_management_plane_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhManagementPlaneDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_management_plane_diagnostic_contract.json"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "in_app_login_state": "EXISTING_SESSION",
        "chrome_login_state": "LOGIN_REQUIRED",
        "management_plane_access": "ACCESS_AVAILABLE",
        "resource_presence": "PRESENT",
        "power_state": "POWERED_ON",
        "network_state": "NETWORK_READY",
        "credential_material_directly_read_or_entered": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_browser_only_no_credential_no_mutation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["credential_material_directly_read_or_entered"] is False
    assert boundary["api_token_directly_read_or_inspected"] is False
    assert boundary["provider_resource_created_deleted_rebuilt_or_restarted"] is False
    assert boundary["provider_network_security_group_ip_dns_or_cloudflare_changed"] is False


def test_available_ready_management_plane_never_authorizes_core_start() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["resource_state_observed"] is True
    assert result["management_plane_ready"] is True
    assert result["core_start_authorized"] is False
    assert result["management_plane_state"] == "OVH_MANAGEMENT_PLANE_READY"


def test_login_required_on_both_surfaces_is_a_complete_access_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        in_app_login_state="LOGIN_REQUIRED",
        chrome_login_state="LOGIN_REQUIRED",
        management_plane_access="ACCESS_UNAVAILABLE_WITHOUT_CREDENTIAL_REUSE",
        resource_presence="NOT_OBSERVED",
        power_state="NOT_OBSERVED",
        network_state="NOT_OBSERVED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["management_plane_access_observed"] is True
    assert result["resource_state_observed"] is False
    assert result["management_plane_ready"] is False
    assert result["management_plane_state"] == "ACCESS_UNAVAILABLE_WITHOUT_CREDENTIAL_REUSE"
    assert result["core_start_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value", "state"),
    [
        ("resource_presence", "ABSENT", "OVH_RESOURCE_ABSENT"),
        ("power_state", "POWERED_OFF", "OVH_POWERED_OFF"),
        ("network_state", "NETWORK_DEGRADED", "OVH_NETWORK_DEGRADED"),
    ],
)
def test_observed_nonready_provider_states_fail_closed(field: str, value: str, state: str) -> None:
    result = evaluate_diagnostic(_contract(), _facts(**{field: value}))

    assert result["status"] == PASS_STATUS
    assert result["management_plane_ready"] is False
    assert result["management_plane_state"] == state


def test_browser_unavailable_is_diagnosed_without_resource_claims() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        in_app_login_state="UNAVAILABLE",
        chrome_login_state="UNAVAILABLE",
        management_plane_access="BROWSER_UNAVAILABLE",
        resource_presence="NOT_OBSERVED",
        power_state="NOT_OBSERVED",
        network_state="NOT_OBSERVED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["resource_state_observed"] is False
    assert result["management_plane_ready"] is False


def test_facts_reject_account_or_resource_identifier_leakage() -> None:
    facts = _facts()
    facts["account_id"] = "not retained"

    with pytest.raises(CurrentProductionOvhManagementPlaneDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_credential_reuse() -> None:
    facts = _facts(credential_material_directly_read_or_entered=True)

    with pytest.raises(CurrentProductionOvhManagementPlaneDiagnosticError, match="credential boundary"):
        validate_facts(facts)


def test_receipt_redacts_browser_login_and_never_authorizes_core_start() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert '"in_app_login_state":' not in serialized
    assert '"chrome_login_state":' not in serialized
    assert '"account_id":' not in serialized


def test_contract_cannot_relax_provider_mutation_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["provider_resource_created_deleted_rebuilt_or_restarted"] = True

    with pytest.raises(CurrentProductionOvhManagementPlaneDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_source_has_no_browser_credential_or_provider_action_capability() -> None:
    source = (RUNTIME / "current_production_ovh_management_plane_diagnostic.py").read_text(encoding="utf-8")

    for forbidden in (
        "selenium",
        "playwright",
        "import requests",
        "import urllib",
        "import subprocess",
        "subprocess.",
        "http.client",
    ):
        assert forbidden not in source
