from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_provider_api_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhProviderApiDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_provider_api_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ovh_provider_api_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "protected_credential_state": "AVAILABLE_IN_MEMORY",
        "current_production_target_state": "RESOLVED_IN_MEMORY",
        "provider_api_access": "QUERY_PASS",
        "provider_api_requests": 1,
        "resource_presence": "PRESENT",
        "power_state": "POWERED_ON",
        "network_state": "NETWORK_READY",
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "raw_provider_response_emitted_or_persisted": False,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_one_get_no_credential_output_and_no_mutation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_provider_api_requests"] == 1
    assert expected["allowed_provider_api_methods"] == ["GET"]
    assert boundary["credential_material_emitted_or_persisted"] is False
    assert boundary["provider_resource_created_deleted_rebuilt_or_restarted"] is False
    assert boundary["provider_network_security_group_ip_dns_or_cloudflare_changed"] is False


def test_successful_ready_query_is_diagnosed_but_never_authorizes_core_start() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["provider_api_diagnosed"] is True
    assert result["resource_state_observed"] is True
    assert result["provider_api_ready"] is True
    assert result["core_start_authorized"] is False
    assert result["provider_api_state"] == "OVH_PROVIDER_API_READY"


def test_unavailable_credential_source_is_a_complete_zero_request_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        protected_credential_state="UNAVAILABLE_REDACTED",
        current_production_target_state="UNAVAILABLE_REDACTED",
        provider_api_access="CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED",
        provider_api_requests=0,
        resource_presence="NOT_OBSERVED",
        power_state="NOT_OBSERVED",
        network_state="NOT_OBSERVED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["resource_state_observed"] is False
    assert result["provider_api_ready"] is False
    assert result["provider_api_state"] == "CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED"
    assert result["core_start_authorized"] is False


def test_unavailable_target_mapping_is_a_complete_zero_request_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        current_production_target_state="UNAVAILABLE_REDACTED",
        provider_api_access="TARGET_MAPPING_UNAVAILABLE_REDACTED",
        provider_api_requests=0,
        resource_presence="NOT_OBSERVED",
        power_state="NOT_OBSERVED",
        network_state="NOT_OBSERVED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["resource_state_observed"] is False
    assert result["provider_api_ready"] is False


@pytest.mark.parametrize(
    "provider_api_access",
    ["ACCESS_DENIED_REDACTED", "REQUEST_FAILED_REDACTED", "RESPONSE_INVALID_REDACTED"],
)
def test_one_request_terminal_failures_are_redacted_and_fail_closed(provider_api_access: str) -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        provider_api_access=provider_api_access,
        resource_presence="NOT_OBSERVED",
        power_state="NOT_OBSERVED",
        network_state="NOT_OBSERVED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["provider_api_diagnosed"] is True
    assert result["resource_state_observed"] is False
    assert result["provider_api_ready"] is False
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
    assert result["provider_api_ready"] is False
    assert result["provider_api_state"] == state
    assert result["core_start_authorized"] is False


def test_facts_reject_identifier_or_raw_response_leakage() -> None:
    facts = _facts()
    facts["service_name"] = "not retained"

    with pytest.raises(CurrentProductionOvhProviderApiDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_nonzero_request_when_credential_is_unavailable() -> None:
    facts = _facts(
        protected_credential_state="UNAVAILABLE_REDACTED",
        current_production_target_state="UNAVAILABLE_REDACTED",
        provider_api_access="CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED",
        provider_api_requests=1,
        resource_presence="NOT_OBSERVED",
        power_state="NOT_OBSERVED",
        network_state="NOT_OBSERVED",
    )

    with pytest.raises(CurrentProductionOvhProviderApiDiagnosticError, match="unavailable credential"):
        validate_facts(facts)


def test_receipt_redacts_credential_target_and_raw_provider_response() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert '"protected_credential_state":' not in serialized
    assert '"current_production_target_state":' not in serialized
    assert '"raw_provider_response":' not in serialized


def test_contract_cannot_relax_get_only_or_provider_mutation_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["allowed_provider_api_methods"] = ["GET", "POST"]

    with pytest.raises(CurrentProductionOvhProviderApiDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_has_one_get_only_and_no_raw_output_or_mutation_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'method="GET"' in source
    assert source.count(".open(request, timeout=10)") == 1
    assert 'payload.get("networkState", "")' in source
    assert 'payload.get("ip"' not in source
    assert "print(payload)" not in source
    assert "print(secret)" not in source
    for forbidden in (
        'method="POST"',
        'method="PUT"',
        'method="DELETE"',
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in source


def test_invalid_input_builds_fail_closed_receipt() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionOvhProviderApiDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC"
