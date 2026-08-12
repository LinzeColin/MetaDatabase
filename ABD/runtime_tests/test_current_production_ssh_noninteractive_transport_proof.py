from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_ssh_noninteractive_transport_proof as proof
from current_production_ssh_noninteractive_transport_proof import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionSshNoninteractiveTransportProofError,
    _classify_ssh_result,
    _run_noninteractive_sudo_true,
    build_receipt,
    discover_noninteractive_transport_proof,
    evaluate_transport_proof,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ssh_noninteractive_transport_proof_contract.json"
LOCAL_ROUTE_CONTRACT_PATH = RUNTIME / "current_production_ssh_local_route_policy_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ssh_noninteractive_transport_proof.sh"
MODULE_PATH = RUNTIME / "current_production_ssh_noninteractive_transport_proof.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _route_facts(**overrides: object) -> dict[str, object]:
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


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF",
        "observed_on": "2026-08-12",
        "local_route_policy_contract_state": "OBSERVED_STATIC",
        "ssh_config_state": "RESOLVED",
        "route_shape": "DIRECT",
        "local_route_policy_ready": True,
        "candidate_alias_state": "RESOLVED_IN_MEMORY",
        "transport_state": "SSH_NONINTERACTIVE_SUDO_READY",
        "ssh_connection_attempts": 1,
        "remote_command_attempts": 1,
        "current_host_metadata_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "credential_material_read_or_persisted": False,
        "candidate_alias_or_target_value_read_or_persisted": False,
        "local_known_hosts_modified": False,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_one_connection_noninteractive_no_known_hosts_write_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["maximum_ssh_connection_attempts"] == 1
    assert expected["remote_command"] == "sudo -n true"
    assert expected["password_authentication_permitted"] is False
    assert expected["keyboard_interactive_authentication_permitted"] is False
    assert expected["local_known_hosts_modified"] is False
    assert boundary["ssh_connection_attempted_at_most_once"] is True
    assert boundary["remote_command_limited_to_noninteractive_sudo_true"] is True
    assert boundary["host_runtime_or_configuration_changed"] is False


def test_ready_candidate_executes_exactly_once_without_exposing_alias_or_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(proof, "_canonical_ssh_config", lambda _: True)
    monkeypatch.setattr(proof.local_route, "discover_local_route_policy", lambda _: _route_facts())
    monkeypatch.setattr(proof.local_route, "_candidate_aliases", lambda _: {"candidate-not-retained"})
    monkeypatch.setattr(proof, "_run_noninteractive_sudo_true", lambda alias, _: calls.append(alias) or "SSH_NONINTERACTIVE_SUDO_READY")

    facts = discover_noninteractive_transport_proof(LOCAL_ROUTE_CONTRACT_PATH, config, "2026-08-12")
    receipt = build_receipt(_contract(), facts)
    serialized = json.dumps(receipt, sort_keys=True)

    assert calls == ["candidate-not-retained"]
    assert facts["ssh_connection_attempts"] == 1
    assert facts["remote_command_attempts"] == 1
    assert receipt["transport_proof_ready"] is True
    assert receipt["current_host_metadata_collection_authorized"] is False
    assert '"route_shape":' not in serialized
    assert "candidate-not-retained" not in serialized


def test_nonready_local_policy_makes_zero_remote_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(proof, "_canonical_ssh_config", lambda _: True)
    monkeypatch.setattr(
        proof.local_route,
        "discover_local_route_policy",
        lambda _: _route_facts(socket_precheck_state="UNAVAILABLE_REDACTED", local_route_policy_ready=False),
    )
    monkeypatch.setattr(proof, "_run_noninteractive_sudo_true", lambda alias, _: calls.append(alias) or "SSH_NONINTERACTIVE_SUDO_READY")

    facts = discover_noninteractive_transport_proof(LOCAL_ROUTE_CONTRACT_PATH, config, "2026-08-12")

    assert calls == []
    assert facts["ssh_connection_attempts"] == 0
    assert facts["transport_state"] == "SSH_TRANSPORT_NOT_ATTEMPTED_LOCAL_POLICY_NOT_READY_REDACTED"


def test_ambiguous_or_unavailable_alias_makes_zero_remote_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(proof, "_canonical_ssh_config", lambda _: True)
    monkeypatch.setattr(proof.local_route, "discover_local_route_policy", lambda _: _route_facts())
    monkeypatch.setattr(proof.local_route, "_candidate_aliases", lambda _: {"one", "two"})
    monkeypatch.setattr(proof, "_run_noninteractive_sudo_true", lambda alias, _: calls.append(alias) or "SSH_NONINTERACTIVE_SUDO_READY")

    facts = discover_noninteractive_transport_proof(LOCAL_ROUTE_CONTRACT_PATH, config, "2026-08-12")

    assert calls == []
    assert facts["candidate_alias_state"] == "UNAVAILABLE_REDACTED"
    assert facts["ssh_connection_attempts"] == 0
    assert facts["transport_state"] == "SSH_TRANSPORT_NOT_ATTEMPTED_CANDIDATE_ALIAS_UNAVAILABLE_REDACTED"


def test_noncanonical_config_stops_before_route_or_remote_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(proof, "_canonical_ssh_config", lambda _: False)
    monkeypatch.setattr(proof.local_route, "discover_local_route_policy", lambda _: (_ for _ in ()).throw(AssertionError("must not read route")))
    monkeypatch.setattr(proof, "_run_noninteractive_sudo_true", lambda alias, _: calls.append(alias) or "SSH_NONINTERACTIVE_SUDO_READY")

    facts = discover_noninteractive_transport_proof(LOCAL_ROUTE_CONTRACT_PATH, config, "2026-08-12")

    assert calls == []
    assert facts["ssh_config_state"] == "NONCANONICAL_REDACTED"
    assert facts["ssh_connection_attempts"] == 0


@pytest.mark.parametrize(
    ("returncode", "stderr", "expected"),
    [
        (0, "", "SSH_NONINTERACTIVE_SUDO_READY"),
        (255, "Permission denied", "SSH_AUTH_FAILED_REDACTED"),
        (255, "Host key verification failed", "SSH_HOST_KEY_FAILED_REDACTED"),
        (255, "Connection timed out", "SSH_TRANSPORT_FAILED_REDACTED"),
        (255, "opaque", "SSH_OTHER_FAILURE_REDACTED"),
    ],
)
def test_ssh_failure_text_is_classified_without_retention(returncode: int, stderr: str, expected: str) -> None:
    assert _classify_ssh_result(subprocess.CompletedProcess(["ssh"], returncode, stderr=stderr)) == expected


def test_subprocess_uses_one_hardened_noninteractive_sudo_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    observed: list[object] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.extend([command, kwargs])
        return subprocess.CompletedProcess(command, 0, stderr="")

    monkeypatch.setattr(proof.subprocess, "run", fake_run)

    state = _run_noninteractive_sudo_true("candidate-not-retained", config)

    assert state == "SSH_NONINTERACTIVE_SUDO_READY"
    assert len(observed) == 2
    command = observed[0]
    kwargs = observed[1]
    assert isinstance(command, list)
    assert isinstance(kwargs, dict)
    assert command.count("candidate-not-retained") == 1
    assert command[-1] == "sudo -n true"
    for option in (
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "IdentitiesOnly=yes",
        "ForwardAgent=no",
        "UpdateHostKeys=no",
        "ControlMaster=no",
        "RequestTTY=no",
    ):
        assert option in command
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["timeout"] == 12


def test_timeout_is_redacted_without_second_attempt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    calls: list[list[str]] = []

    def timeout(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 12)

    monkeypatch.setattr(proof.subprocess, "run", timeout)

    assert _run_noninteractive_sudo_true("candidate-not-retained", config) == "SSH_CONNECT_TIMEOUT_REDACTED"
    assert len(calls) == 1


def test_facts_reject_multiple_attempts_or_metadata_read() -> None:
    with pytest.raises(CurrentProductionSshNoninteractiveTransportProofError, match="attempt count"):
        validate_facts(_facts(ssh_connection_attempts=2))

    with pytest.raises(CurrentProductionSshNoninteractiveTransportProofError, match="transport boundary"):
        validate_facts(_facts(current_host_metadata_read=True))


def test_contract_cannot_relax_interactive_or_host_mutation_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["interactive_authentication_permitted"] = True

    with pytest.raises(CurrentProductionSshNoninteractiveTransportProofError, match="contract boundary"):
        validate_contract(contract)


def test_receipt_never_authorizes_metadata_repair_or_core_start() -> None:
    receipt = build_receipt(_contract(), _facts())

    assert receipt["status"] == PASS_STATUS
    assert receipt["transport_proof_ready"] is True
    assert receipt["current_host_metadata_collection_authorized"] is False
    assert receipt["repair_execution_authorized"] is False
    assert receipt["core_start_authorized"] is False


def test_not_ready_transport_is_diagnosed_but_never_reported_as_ready() -> None:
    result = evaluate_transport_proof(_contract(), _facts(transport_state="SSH_AUTH_FAILED_REDACTED"))

    assert result["status"] == PASS_STATUS
    assert result["transport_diagnosed"] is True
    assert result["transport_proof_ready"] is False
    assert result["decision"] == "CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_NOT_READY_NO_HOST_MUTATION_AUTHORIZED"


def test_runner_and_module_confine_remote_action_to_hardened_ssh_sudo_true() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--ssh-config" in runner
    assert "current_production_ssh_noninteractive_transport_proof.py" in runner
    assert "sudo -n true" in module
    assert "import socket" not in module
    for forbidden in (
        "sshpass",
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


def test_failed_static_contract_is_zero_connection_failure_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config"
    config.write_text("Host ignored\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(proof, "_observe_local_route_policy_contract", lambda _: "REJECTED_REDACTED")
    monkeypatch.setattr(proof, "_run_noninteractive_sudo_true", lambda alias, _: calls.append(alias) or "SSH_NONINTERACTIVE_SUDO_READY")

    facts = discover_noninteractive_transport_proof(LOCAL_ROUTE_CONTRACT_PATH, config, "2026-08-12")

    assert calls == []
    assert facts["local_route_policy_contract_state"] == "REJECTED_REDACTED"
    assert facts["transport_state"] == "SSH_TRANSPORT_NOT_ATTEMPTED_STATIC_INPUT_REJECTED"
    assert evaluate_transport_proof(_contract(), facts)["status"] == FAIL_STATUS
