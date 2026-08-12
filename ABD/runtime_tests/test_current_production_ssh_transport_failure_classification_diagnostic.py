from __future__ import annotations

import errno
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_ssh_transport_failure_classification_diagnostic as diagnostic
from current_production_ssh_transport_failure_classification_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionSshTransportFailureClassificationDiagnosticError,
    _candidate_aliases,
    _classify_connect_result,
    _ssh_g_is_locally_safe,
    build_receipt,
    discover_transport_failure_classification,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ssh_transport_failure_classification_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ssh_transport_failure_classification_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_ssh_transport_failure_classification_diagnostic.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "ssh_config_state": "RESOLVED",
        "route_shape": "DIRECT",
        "target_address_shape": "NUMERIC",
        "tcp_connectivity": "CONNECTED",
        "socket_connection_attempts": 1,
        "ssh_connection_attempts": 0,
        "dns_resolution_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
        "ssh_config_value_emitted_or_persisted": False,
        "socket_error_emitted_or_persisted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_single_numeric_tcp_attempt_and_zero_ssh_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["tcp_connect_timeout_seconds"] == 3
    assert expected["dns_resolution_attempts"] == 0
    assert expected["socket_connection_attempts_at_most"] == 1
    assert expected["ssh_connection_attempts"] == 0
    assert expected["remote_command_attempts"] == 0
    assert boundary["socket_connection_attempted_at_most_once"] is True
    assert boundary["ssh_connection_attempted"] is False
    assert boundary["remote_command_or_sudo_attempted"] is False


def test_connected_tcp_is_diagnosed_but_requires_a_separate_auth_phase() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["transport_failure_classification_completed"] is True
    assert result["tcp_reachable"] is True
    assert result["core_start_authorized"] is False
    assert result["transport_state"] == "SSH_TCP_CONNECTED_AUTH_NOT_ATTEMPTED"
    assert result["decision"] == "CURRENT_PRODUCTION_SSH_TCP_CONNECTED_SEPARATE_NONINTERACTIVE_AUTH_DIAGNOSTIC_REQUIRED"


@pytest.mark.parametrize(
    ("tcp_connectivity", "transport_state"),
    [
        ("CONNECT_TIMEOUT_REDACTED", "SSH_TCP_CONNECT_TIMEOUT_REDACTED"),
        ("CONNECTION_REFUSED_REDACTED", "SSH_TCP_CONNECTION_REFUSED_REDACTED"),
        ("ROUTE_UNREACHABLE_REDACTED", "SSH_TCP_ROUTE_UNREACHABLE_REDACTED"),
        ("OTHER_SOCKET_FAILURE_REDACTED", "SSH_TCP_OTHER_SOCKET_FAILURE_REDACTED"),
    ],
)
def test_terminal_tcp_failure_is_a_completed_classification_without_ssh_authentication(tcp_connectivity: str, transport_state: str) -> None:
    result = evaluate_diagnostic(_contract(), _facts(tcp_connectivity=tcp_connectivity))

    assert result["status"] == PASS_STATUS
    assert result["transport_failure_classification_completed"] is True
    assert result["tcp_reachable"] is False
    assert result["core_start_authorized"] is False
    assert result["transport_state"] == transport_state
    assert result["decision"] == "CURRENT_PRODUCTION_SSH_TCP_FAILURE_CLASSIFIED_NO_SSH_AUTHORIZATION"


def test_proxy_configuration_fails_closed_without_tcp_attempt() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        route_shape="PROXY_COMMAND",
        target_address_shape="NOT_ATTEMPTED",
        tcp_connectivity="NOT_APPLICABLE_PROXY",
        socket_connection_attempts=0,
    ))

    assert result["status"] == FAIL_STATUS
    assert result["transport_failure_classification_completed"] is False
    assert result["tcp_reachable"] is False
    assert result["core_start_authorized"] is False


def test_nonnumeric_target_fails_closed_without_dns_or_tcp_attempt() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        target_address_shape="NONNUMERIC_NOT_CONNECTED_REDACTED",
        tcp_connectivity="NOT_ATTEMPTED",
        socket_connection_attempts=0,
    ))

    assert result["status"] == FAIL_STATUS
    assert result["transport_failure_classification_completed"] is False
    assert result["core_start_authorized"] is False


def test_unresolved_ssh_config_fails_closed_without_connection() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        ssh_config_state="CANDIDATE_ALIAS_UNAVAILABLE_REDACTED",
        route_shape="UNKNOWN",
        target_address_shape="NOT_ATTEMPTED",
        tcp_connectivity="NOT_ATTEMPTED",
        socket_connection_attempts=0,
    ))

    assert result["status"] == FAIL_STATUS
    assert result["transport_failure_classification_completed"] is False
    assert result["tcp_reachable"] is False


def test_direct_numeric_facts_require_exactly_one_tcp_attempt() -> None:
    with pytest.raises(CurrentProductionSshTransportFailureClassificationDiagnosticError, match="direct TCP classification facts are incomplete"):
        validate_facts(_facts(socket_connection_attempts=0))


def test_facts_reject_any_ssh_dns_provider_or_raw_metadata_leakage() -> None:
    with pytest.raises(CurrentProductionSshTransportFailureClassificationDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(ssh_connection_attempts=1))

    leaking_facts = _facts()
    leaking_facts["hostname"] = "not retained"
    with pytest.raises(CurrentProductionSshTransportFailureClassificationDiagnosticError, match="field set"):
        validate_facts(leaking_facts)


def test_receipt_redacts_config_and_socket_outcome_values() -> None:
    receipt = build_receipt(_contract(), _facts(tcp_connectivity="CONNECTION_REFUSED_REDACTED"))
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["tcp_reachable"] is False
    assert receipt["core_start_authorized"] is False
    assert '"route_shape":' not in serialized
    assert '"target_address_shape":' not in serialized
    assert '"tcp_connectivity":' not in serialized
    assert '"socket_connection_attempts":' not in serialized


def test_contract_cannot_relax_one_attempt_or_ssh_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["ssh_connection_attempts"] = 1

    with pytest.raises(CurrentProductionSshTransportFailureClassificationDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_candidate_selection_and_ssh_g_preflight_are_local_only(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\nHost -ovh-prod ovh;unsafe ovh-prod\n", encoding="utf-8")
    assert _candidate_aliases(config) == {"ovh-prod"}
    assert _ssh_g_is_locally_safe(config) is True

    config.write_text("Include conf.d/*\nHost ovh-prod\n", encoding="utf-8")
    assert _ssh_g_is_locally_safe(config) is False


def test_discovery_makes_one_numeric_tcp_call_without_dns_or_ssh_authentication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.write_text("Host ovh-prod\n", encoding="utf-8")
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(diagnostic, "_ssh_g_metadata", lambda alias: ("203.0.113.20", 22, "none", "none"))

    def fake_connect(address: str, port: int) -> str:
        calls.append((address, port))
        return "CONNECTION_REFUSED_REDACTED"

    monkeypatch.setattr(diagnostic, "_connect_once", fake_connect)
    facts = discover_transport_failure_classification(config, observed_on="2026-08-12")

    assert len(calls) == 1
    assert facts["target_address_shape"] == "NUMERIC"
    assert facts["tcp_connectivity"] == "CONNECTION_REFUSED_REDACTED"
    assert facts["socket_connection_attempts"] == 1
    assert facts["dns_resolution_attempts"] == 0
    assert facts["ssh_connection_attempts"] == 0


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "CONNECTED"),
        (errno.ETIMEDOUT, "CONNECT_TIMEOUT_REDACTED"),
        (errno.ECONNREFUSED, "CONNECTION_REFUSED_REDACTED"),
        (getattr(errno, "EHOSTUNREACH", errno.ENETUNREACH), "ROUTE_UNREACHABLE_REDACTED"),
    ],
)
def test_connect_errno_mapping_is_redacted(code: int, expected: str) -> None:
    assert _classify_connect_result(code) == expected


def test_runner_and_module_forbid_dns_and_remote_ssh_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--ssh-config" in runner
    assert "current_production_ssh_transport_failure_classification_diagnostic.py" in runner
    assert "connect_ex" in module
    for forbidden in (
        "socket.getaddrinfo",
        "socket.create_connection",
        ".connect(",
        "sshpass",
        "BatchMode",
        "PasswordAuthentication",
        "KbdInteractiveAuthentication",
        "sudo -n",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "curl ",
        "wget ",
        "gh ",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in runner
        assert forbidden not in module


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionSshTransportFailureClassificationDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC"
