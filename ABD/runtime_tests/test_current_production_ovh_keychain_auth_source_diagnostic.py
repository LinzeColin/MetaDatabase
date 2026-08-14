from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_keychain_auth_source_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhKeychainAuthSourceDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_keychain_auth_source_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ovh_keychain_auth_source_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "keychain_access": "AVAILABLE",
        "auth_target_source_state": "CANONICAL_SOURCE_RESOLVED_IN_MEMORY",
        "auth_target_source_ready": True,
        "provider_api_requests": 0,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_local_keychain_only_zero_request_and_no_mutation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_keychain_command_timeout_seconds"] == 3
    assert expected["provider_api_requests"] == 0
    assert boundary["credential_material_emitted_or_persisted"] is False
    assert boundary["provider_api_request_sent"] is False
    assert boundary["provider_resource_created_deleted_rebuilt_or_restarted"] is False


def test_structured_keychain_source_is_ready_only_for_a_separate_provider_get_phase() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["keychain_diagnosed"] is True
    assert result["auth_target_source_ready"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False
    assert result["keychain_auth_source_state"] == "OVH_KEYCHAIN_AUTH_TARGET_READY_FOR_SEPARATE_GET_PHASE"


@pytest.mark.parametrize(
    "auth_target_source_state",
    [
        "CANONICAL_SOURCE_UNSTRUCTURED_REDACTED",
        "PROVIDER_KEYCHAIN_ENTRY_PRESENT_UNSCOPED_REDACTED",
        "CANONICAL_SOURCE_NOT_RESOLVED_REDACTED",
    ],
)
def test_available_keychain_nonready_source_is_a_complete_zero_request_diagnostic(auth_target_source_state: str) -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        auth_target_source_state=auth_target_source_state,
        auth_target_source_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["keychain_diagnosed"] is True
    assert result["auth_target_source_ready"] is False
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False


def test_unavailable_keychain_fails_closed_without_provider_request() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        keychain_access="UNAVAILABLE_REDACTED",
        auth_target_source_state="KEYCHAIN_UNAVAILABLE_REDACTED",
        auth_target_source_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["auth_target_source_ready"] is False
    assert result["provider_api_request_not_sent"] is True


def test_facts_reject_secret_or_target_identifier_leakage() -> None:
    facts = _facts()
    facts["service_name"] = "not retained"

    with pytest.raises(CurrentProductionOvhKeychainAuthSourceDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_provider_request() -> None:
    facts = _facts(provider_api_requests=1)

    with pytest.raises(CurrentProductionOvhKeychainAuthSourceDiagnosticError, match="request count"):
        validate_facts(facts)


def test_receipt_redacts_keychain_credential_and_target_mapping() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["auth_target_source_ready"] is True
    assert receipt["provider_api_request_not_sent"] is True
    assert receipt["core_start_authorized"] is False
    assert '"keychain_access":' not in serialized
    assert '"service_name":' not in serialized
    assert '"consumer_key":' not in serialized


def test_contract_cannot_relax_zero_request_or_provider_mutation_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["provider_api_requests"] = 1

    with pytest.raises(CurrentProductionOvhKeychainAuthSourceDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_has_bounded_local_keychain_only_and_no_raw_output_or_network_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'TIMEOUT_SECONDS = 3' in source
    assert '"list-keychains", "-d", "user"' in source
    assert '"find-generic-password", "-s", service, "-w"' in source
    assert '"find-internet-password", "-s", host' in source
    assert "print(credential.stdout)" not in source
    assert "print(json.dumps(result" in source
    for forbidden in (
        "urllib.request",
        "http.client",
        "import requests",
        "requests.",
        "curl ",
        "wget ",
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


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionOvhKeychainAuthSourceDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC"
