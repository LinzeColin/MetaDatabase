from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_process_auth_source_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhProcessAuthSourceDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_process_auth_source_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ovh_process_auth_source_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "current_process_source_state": "COMPLETE_LEGACY_AUTH_TARGET_FIELDS",
        "user_launchd_source_state": "NO_COMPLETE_LEGACY_GROUP_REDACTED",
        "auth_target_source_ready": True,
        "provider_api_requests": 0,
        "environment_value_emitted_or_persisted": False,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_fixed_field_presence_only_zero_request_and_no_mutation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["legacy_auth_target_field_groups"] == ["OVH_STANDARD", "ABD_OVH_SCOPED"]
    assert expected["field_presence_planes"] == ["CURRENT_PROCESS", "USER_LAUNCHD"]
    assert expected["maximum_launchd_command_timeout_seconds"] == 3
    assert expected["provider_api_requests"] == 0
    assert boundary["current_process_environment_values_emitted_or_persisted"] is False
    assert boundary["user_launchd_environment_values_emitted_or_persisted"] is False
    assert boundary["provider_api_request_sent"] is False


@pytest.mark.parametrize(
    ("current_process_source_state", "user_launchd_source_state"),
    [
        ("COMPLETE_LEGACY_AUTH_TARGET_FIELDS", "NO_COMPLETE_LEGACY_GROUP_REDACTED"),
        ("NO_COMPLETE_LEGACY_GROUP_REDACTED", "COMPLETE_LEGACY_AUTH_TARGET_FIELDS"),
    ],
)
def test_one_complete_plane_is_ready_only_for_a_separate_provider_get_phase(current_process_source_state: str, user_launchd_source_state: str) -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        current_process_source_state=current_process_source_state,
        user_launchd_source_state=user_launchd_source_state,
    ))

    assert result["status"] == PASS_STATUS
    assert result["process_auth_source_diagnosed"] is True
    assert result["auth_target_source_ready"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False
    assert result["process_auth_source_state"] == "OVH_PROCESS_OR_LAUNCHD_AUTH_TARGET_READY_FOR_SEPARATE_GET_PHASE"


def test_no_complete_plane_is_a_complete_zero_request_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        current_process_source_state="NO_COMPLETE_LEGACY_GROUP_REDACTED",
        user_launchd_source_state="NO_COMPLETE_LEGACY_GROUP_REDACTED",
        auth_target_source_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["auth_target_source_ready"] is False
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False
    assert result["process_auth_source_state"] == "OVH_PROCESS_AND_USER_LAUNCHD_NO_COMPLETE_AUTH_TARGET"


def test_unavailable_user_launchd_is_redacted_and_fails_closed() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        current_process_source_state="NO_COMPLETE_LEGACY_GROUP_REDACTED",
        user_launchd_source_state="UNAVAILABLE_REDACTED",
        auth_target_source_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["auth_target_source_ready"] is False
    assert result["process_auth_source_state"] == "OVH_PROCESS_NO_COMPLETE_AUTH_TARGET_USER_LAUNCHD_UNAVAILABLE"


def test_facts_reject_environment_or_target_identifier_leakage() -> None:
    facts = _facts()
    facts["OVH_APPLICATION_KEY"] = "not retained"

    with pytest.raises(CurrentProductionOvhProcessAuthSourceDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_provider_request() -> None:
    facts = _facts(provider_api_requests=1)

    with pytest.raises(CurrentProductionOvhProcessAuthSourceDiagnosticError, match="request count"):
        validate_facts(facts)


def test_receipt_redacts_plane_details_and_never_authorizes_core_start() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["auth_target_source_ready"] is True
    assert receipt["provider_api_request_not_sent"] is True
    assert receipt["core_start_authorized"] is False
    assert '"current_process_source_state":' not in serialized
    assert '"user_launchd_source_state":' not in serialized
    assert '"OVH_APPLICATION_KEY":' not in serialized


def test_contract_cannot_relax_fixed_planes_or_zero_request_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["provider_api_requests"] = 1

    with pytest.raises(CurrentProductionOvhProcessAuthSourceDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_has_fixed_names_bounded_local_launchd_only_and_no_raw_output_or_network_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'TIMEOUT_SECONDS = 3' in source
    assert '"launchctl"' in source
    assert '[binary, "getenv", name]' in source
    assert '"OVH_APPLICATION_KEY"' in source
    assert '"ABD_OVH_APPLICATION_KEY"' in source
    assert "print(result" not in source
    assert "print(json.dumps(result" in source
    for forbidden in (
        "os.environ.items",
        "os.environ.keys",
        "launchctl setenv",
        "launchctl unsetenv",
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

    with pytest.raises(CurrentProductionOvhProcessAuthSourceDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC"
