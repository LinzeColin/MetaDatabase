from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_abd_scoped_transport_authority_source_resolution import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionAbdScopedTransportAuthoritySourceResolutionError,
    build_receipt,
    evaluate_source_resolution,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_abd_scoped_transport_authority_source_resolution_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_abd_scoped_transport_authority_source_resolution.sh"
MODULE_PATH = RUNTIME / "current_production_abd_scoped_transport_authority_source_resolution.py"
UTC_TODAY = datetime.now(timezone.utc).date().isoformat()


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION",
        "observed_on": UTC_TODAY,
        "owner_task_authorization_observed": True,
        "protected_exact_ovh_auth_keyset_state": "NO_QUALIFYING_AUTH_KEYSET_OBSERVED_REDACTED",
        "github_variable_scope_state": "NO_ABD_SCOPED_SOURCE_OBSERVED_REDACTED",
        "github_environment_scope_state": "NO_ABD_SCOPED_SOURCE_OBSERVED_REDACTED",
        "ovh_existing_browser_session_state": "MANAGEMENT_SURFACE_UNAVAILABLE_REDACTED",
        "qualified_authority_source_state": "NOT_PROVEN_REDACTED",
        "source_authority_ready": False,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "github_variable_or_environment_values_read_emitted_or_persisted": False,
        "browser_login_submitted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 2,
        "browser_navigation_attempts": 1,
    }
    values.update(overrides)
    return values


def test_contract_preserves_only_source_observation_and_no_transport_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_github_api_requests"] == 2
    assert expected["maximum_browser_navigation_attempts"] == 1
    assert expected["provider_api_requests"] == 0
    assert expected["ssh_connections_attempted"] == 0
    assert boundary["credential_material_emitted_or_persisted"] is False
    assert boundary["target_mapping_emitted_or_persisted"] is False
    assert boundary["browser_login_submitted"] is False
    assert boundary["ssh_connection_attempted"] is False


def test_all_observed_sources_without_authority_is_completed_but_not_ready() -> None:
    result = evaluate_source_resolution(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["source_resolution_completed"] is True
    assert result["source_authority_ready"] is False
    assert result["qualified_authority_source_state"] == "NOT_PROVEN_REDACTED"
    assert result["decision"] == "ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_NOT_PROVEN_NO_TARGET_OR_TRANSPORT_ACTION_AUTHORIZED"
    assert result["target_mapping_authorized"] is False
    assert result["transport_retry_authorized"] is False


def test_qualified_source_is_ready_only_for_separate_target_mapping_phase() -> None:
    facts = _facts(
        protected_exact_ovh_auth_keyset_state="QUALIFIED_ABD_SCOPED_CURRENT_AUTHORITY_SOURCE_RESOLVED_IN_MEMORY",
        qualified_authority_source_state="RESOLVED_IN_MEMORY",
        source_authority_ready=True,
    )

    result = evaluate_source_resolution(_contract(), facts)

    assert result["status"] == PASS_STATUS
    assert result["source_authority_ready"] is True
    assert result["decision"] == "ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_READY_FOR_SEPARATE_TARGET_MAPPING_PHASE"
    assert result["target_mapping_authorized"] is False
    assert result["current_host_metadata_collection_authorized"] is False
    assert result["core_start_authorized"] is False


def test_unobserved_source_surface_is_incomplete() -> None:
    facts = _facts(
        github_environment_scope_state="NOT_ATTEMPTED",
        github_api_requests=1,
    )

    result = evaluate_source_resolution(_contract(), facts)

    assert result["status"] == FAIL_STATUS
    assert result["source_resolution_completed"] is False
    assert result["source_authority_ready"] is False


def test_authority_cannot_be_marked_ready_without_a_qualified_source() -> None:
    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="authority readiness"):
        validate_facts(_facts(source_authority_ready=True))


def test_facts_reject_noncurrent_utc_observation_date() -> None:
    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="not current UTC"):
        validate_facts(_facts(observed_on="2000-01-01"))


def test_facts_reject_values_leakage_provider_or_ssh_action() -> None:
    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="redaction boundary"):
        validate_facts(_facts(credential_material_emitted_or_persisted=True))

    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="outbound operation count"):
        validate_facts(_facts(provider_api_requests=1))

    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="outbound operation count"):
        validate_facts(_facts(ssh_connections_attempted=1))


def test_facts_reject_excess_github_or_browser_attempts() -> None:
    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="GitHub request count"):
        validate_facts(_facts(github_api_requests=3))

    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="browser navigation count"):
        validate_facts(_facts(browser_navigation_attempts=2))


def test_receipt_keeps_only_redacted_source_states() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["source_authority_ready"] is False
    assert receipt["provider_api_requests"] == 0
    assert receipt["ssh_connections_attempted"] == 0
    assert '"credential":' not in serialized
    assert '"target":' not in serialized
    assert '"hostname":' not in serialized
    assert '"variable_value":' not in serialized


def test_contract_cannot_relax_source_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["browser_login_submitted"] = True

    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="contract boundary"):
        validate_contract(contract)


def test_owner_authorization_observation_is_required_but_not_provider_proof() -> None:
    with pytest.raises(CurrentProductionAbdScopedTransportAuthoritySourceResolutionError, match="owner task authorization"):
        validate_facts(_facts(owner_task_authorization_observed=False))

    receipt = build_receipt(_contract(), _facts())
    assert receipt["source_authority_ready"] is False


def test_runner_and_module_have_no_network_or_mutation_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--facts" in runner
    assert "current_production_abd_scoped_transport_authority_source_resolution.py" in runner
    for forbidden in (
        "import socket",
        "import subprocess",
        "import requests",
        "import urllib",
        "ssh ",
        "curl ",
        "wget ",
        "gh ",
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
        assert forbidden not in module
