from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ssh_transport_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionSshTransportDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ssh_transport_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ssh_transport_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "ssh_config_state": "RESOLVED",
        "route": "DIRECT",
        "name_resolution": "PASS",
        "tcp_connectivity": "PASS",
        "ssh_authentication": "PASS",
        "noninteractive_sudo": "PASS",
    }
    values.update(overrides)
    return values


def test_contract_preserves_one_shot_noninteractive_and_no_mutation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    assert boundary["interactive_authentication_permitted"] is False
    assert boundary["local_known_hosts_modified"] is False
    assert boundary["remote_config_runtime_env_or_secret_read"] is False
    assert boundary["unit_created_enabled_or_started"] is False


def test_direct_transport_ready_is_diagnosed_but_never_authorizes_core_start() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["transport_diagnosed"] is True
    assert result["transport_ready"] is True
    assert result["core_start_authorized"] is False
    assert result["transport_state"] == "SSH_TRANSPORT_READY"


@pytest.mark.parametrize(
    ("tcp_connectivity", "transport_state"),
    [
        ("CONNECT_TIMEOUT_REDACTED", "SSH_TCP_CONNECT_TIMEOUT_REDACTED"),
        ("CONNECTION_REFUSED_REDACTED", "SSH_TCP_CONNECTION_REFUSED_REDACTED"),
        ("OTHER_FAILED_REDACTED", "SSH_TCP_OTHER_FAILED_REDACTED"),
    ],
)
def test_direct_tcp_failure_is_complete_diagnostic_without_ssh_retry(tcp_connectivity: str, transport_state: str) -> None:
    facts = _facts(
        tcp_connectivity=tcp_connectivity,
        ssh_authentication="NOT_ATTEMPTED",
        noninteractive_sudo="NOT_ATTEMPTED",
    )
    result = evaluate_diagnostic(_contract(), facts)

    assert result["status"] == PASS_STATUS
    assert result["transport_diagnosed"] is True
    assert result["transport_ready"] is False
    assert result["transport_state"] == transport_state
    assert result["core_start_authorized"] is False


@pytest.mark.parametrize(
    ("ssh_authentication", "transport_state"),
    [
        ("AUTH_FAILED_REDACTED", "SSH_AUTH_FAILED_REDACTED"),
        ("HOST_KEY_FAILED_REDACTED", "SSH_HOST_KEY_FAILED_REDACTED"),
        ("TRANSPORT_FAILED_REDACTED", "SSH_TRANSPORT_FAILED_REDACTED"),
    ],
)
def test_ssh_terminal_failures_are_classified_without_sudo(ssh_authentication: str, transport_state: str) -> None:
    result = evaluate_diagnostic(_contract(), _facts(ssh_authentication=ssh_authentication, noninteractive_sudo="NOT_ATTEMPTED"))

    assert result["status"] == PASS_STATUS
    assert result["transport_ready"] is False
    assert result["transport_state"] == transport_state


def test_name_resolution_failure_stops_before_tcp_or_ssh() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        name_resolution="FAILED_REDACTED",
        tcp_connectivity="NOT_ATTEMPTED",
        ssh_authentication="NOT_ATTEMPTED",
        noninteractive_sudo="NOT_ATTEMPTED",
    ))

    assert result["status"] == PASS_STATUS
    assert result["transport_state"] == "SSH_NAME_RESOLUTION_UNAVAILABLE"


def test_unavailable_ssh_config_fails_closed() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        ssh_config_state="UNAVAILABLE_REDACTED",
        route="UNKNOWN",
        name_resolution="NOT_ATTEMPTED",
        tcp_connectivity="NOT_ATTEMPTED",
        ssh_authentication="NOT_ATTEMPTED",
        noninteractive_sudo="NOT_ATTEMPTED",
    ))

    assert result["status"] == FAIL_STATUS
    assert result["transport_diagnosed"] is False
    assert result["transport_ready"] is False


def test_facts_reject_target_or_error_text_leakage() -> None:
    facts = _facts()
    facts["hostname"] = "not retained"

    with pytest.raises(CurrentProductionSshTransportDiagnosticError, match="field set"):
        validate_facts(facts)


def test_receipt_is_redacted_and_never_claims_core_start() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["transport_ready"] is True
    assert receipt["core_start_authorized"] is False
    assert '"hostname":' not in serialized
    assert '"port":' not in serialized
    assert '"ssh_authentication":' not in serialized


def test_contract_cannot_relax_interactive_authentication_or_host_mutation() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["interactive_authentication_permitted"] = True

    with pytest.raises(CurrentProductionSshTransportDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_has_no_raw_output_or_runtime_mutation_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert "StrictHostKeyChecking=yes" in source
    assert "PasswordAuthentication=no" in source
    assert "KbdInteractiveAuthentication=no" in source
    assert "socket.create_connection" in source
    assert "print(message)" not in source
    for forbidden in (
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "curl ",
        "wget ",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in source
