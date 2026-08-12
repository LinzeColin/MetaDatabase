from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ssh_local_route_policy_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionSshLocalRoutePolicyDiagnosticError,
    _candidate_aliases,
    _ssh_g_is_locally_safe,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ssh_local_route_policy_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ssh_local_route_policy_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "ssh_config_state": "RESOLVED",
        "route_shape": "DIRECT",
        "default_route_state": "AVAILABLE",
        "target_route_state": "AVAILABLE",
        "socket_precheck_state": "AVAILABLE",
        "local_route_policy_ready": True,
        "ssh_config_value_emitted_or_persisted": False,
        "route_output_emitted_or_persisted": False,
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_local_only_zero_connection_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["candidate_alias_selector"] == "UNIQUE_OVH_OR_VPS_HOST_DECLARATION"
    assert expected["maximum_local_command_timeout_seconds"] == 2
    assert expected["route_queries"] == ["default", "numeric_target_only"]
    assert expected["socket_connection_attempts"] == 0
    assert expected["ssh_connection_attempts"] == 0
    assert boundary["socket_connection_attempted"] is False
    assert boundary["ssh_connection_attempted"] is False
    assert boundary["alias_address_port_user_identity_proxy_or_route_values_emitted_or_persisted"] is False


def test_direct_local_policy_ready_requires_separate_transport_phase() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["local_route_policy_diagnosed"] is True
    assert result["local_route_policy_ready"] is True
    assert result["core_start_authorized"] is False
    assert result["decision"] == "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_READY_SEPARATE_TRANSPORT_DIAGNOSTIC_REQUIRED"


def test_proxy_configuration_is_diagnosed_but_never_ready_for_remote_action() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        route_shape="PROXY_COMMAND",
        target_route_state="NOT_APPLICABLE_PROXY",
        local_route_policy_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["local_route_policy_diagnosed"] is True
    assert result["local_route_policy_ready"] is False
    assert result["core_start_authorized"] is False
    assert result["local_route_policy_state"] == "SSH_LOCAL_ROUTE_PROXY_UNEVALUATED"


def test_unresolved_alias_fails_closed_without_local_route_queries() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        ssh_config_state="CANDIDATE_ALIAS_UNAVAILABLE_REDACTED",
        route_shape="UNKNOWN",
        default_route_state="NOT_ATTEMPTED",
        target_route_state="NOT_ATTEMPTED",
        socket_precheck_state="NOT_ATTEMPTED",
        local_route_policy_ready=False,
    ))

    assert result["status"] == FAIL_STATUS
    assert result["local_route_policy_diagnosed"] is False
    assert result["local_route_policy_ready"] is False


def test_candidate_alias_selector_reads_only_host_declarations(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host noncandidate\n  HostName ignored.example\nHost ovh-prod\n  HostName ignored.example\n", encoding="utf-8")

    aliases = _candidate_aliases(config)

    assert aliases == {"ovh-prod"}


def test_candidate_alias_selector_detects_ambiguity_without_exposing_aliases(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host ovh-prod\nHost vps-prod\n", encoding="utf-8")

    aliases = _candidate_aliases(config)

    assert aliases is not None
    assert len(aliases) == 2


def test_ssh_g_preflight_rejects_include_or_match_exec(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Include conf.d/*\nHost ovh-prod\n", encoding="utf-8")
    assert _ssh_g_is_locally_safe(config) is False

    config.write_text("Match host * exec local-command\nHost ovh-prod\n", encoding="utf-8")
    assert _ssh_g_is_locally_safe(config) is False


def test_facts_reject_alias_or_route_leakage() -> None:
    facts = _facts()
    facts["alias"] = "not retained"

    with pytest.raises(CurrentProductionSshLocalRoutePolicyDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_socket_ssh_or_provider_operation() -> None:
    facts = _facts(socket_connection_attempts=1)

    with pytest.raises(CurrentProductionSshLocalRoutePolicyDiagnosticError, match="outbound operation count"):
        validate_facts(facts)


def test_direct_facts_require_a_completed_numeric_target_route_evaluation() -> None:
    facts = _facts(target_route_state="NOT_ATTEMPTED", local_route_policy_ready=False)

    with pytest.raises(CurrentProductionSshLocalRoutePolicyDiagnosticError, match="target-route facts are incomplete"):
        validate_facts(facts)


def test_receipt_redacts_ssh_and_route_metadata() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["core_start_authorized"] is False
    assert '"route_shape":' not in serialized
    assert '"default_route_state":' not in serialized
    assert '"target_route_state":' not in serialized


def test_contract_cannot_relax_connection_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["socket_connection_attempts"] = 1

    with pytest.raises(CurrentProductionSshLocalRoutePolicyDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_has_no_socket_connection_or_remote_ssh_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "--ssh-config" in source
    assert "current_production_ssh_local_route_policy_diagnostic.py" in source
    for forbidden in (
        "ssh ",
        "socket.create_connection",
        "connect(",
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
        assert forbidden not in source


def test_module_has_no_dns_or_socket_connection_capability() -> None:
    source = (RUNTIME / "current_production_ssh_local_route_policy_diagnostic.py").read_text(encoding="utf-8")

    for forbidden in (
        "socket.create_connection",
        "socket.getaddrinfo",
        ".connect(",
        "sshpass",
        "StrictHostKeyChecking",
    ):
        assert forbidden not in source


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionSshLocalRoutePolicyDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC"
