#!/usr/bin/env python3
"""Perform one bounded, noninteractive SSH transport proof without host mutation."""

from __future__ import annotations

import argparse
import json
import stat
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import current_production_ssh_local_route_policy_diagnostic as local_route


PASS_STATUS = "PASS_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF"
LOCAL_ROUTE_POLICY_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-SSH-LOCAL-ROUTE-POLICY-DIAGNOSTIC-001"
LOCAL_ROUTE_POLICY_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_READ_ONLY"
CONTRACT_FIELDS = {
    "schema_version",
    "contract_id",
    "product_version",
    "status",
    "expected",
    "source_boundary",
    "claim_boundary",
    "rollback",
}
STATIC_CONTRACT_STATES = {"OBSERVED_STATIC", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}
SSH_CONFIG_STATES = {"RESOLVED", "UNAVAILABLE_REDACTED", "NONCANONICAL_REDACTED", "NOT_ATTEMPTED"}
ROUTE_SHAPES = {"DIRECT", "PROXY_COMMAND", "PROXY_JUMP", "PROXY_BOTH", "UNKNOWN", "NOT_ATTEMPTED"}
CANDIDATE_ALIAS_STATES = {"RESOLVED_IN_MEMORY", "UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}
TRANSPORT_STATES = {
    "SSH_NONINTERACTIVE_SUDO_READY",
    "SSH_AUTH_FAILED_REDACTED",
    "SSH_HOST_KEY_FAILED_REDACTED",
    "SSH_TRANSPORT_FAILED_REDACTED",
    "SSH_CONNECT_TIMEOUT_REDACTED",
    "SSH_OTHER_FAILURE_REDACTED",
    "SSH_TRANSPORT_NOT_ATTEMPTED_STATIC_INPUT_REJECTED",
    "SSH_TRANSPORT_NOT_ATTEMPTED_LOCAL_POLICY_NOT_READY_REDACTED",
    "SSH_TRANSPORT_NOT_ATTEMPTED_CANDIDATE_ALIAS_UNAVAILABLE_REDACTED",
}


class CurrentProductionSshNoninteractiveTransportProofError(ValueError):
    """Raised when a one-shot noninteractive transport-proof input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionSshNoninteractiveTransportProofError("%s must be an object" % name)
    return value


def _safe_regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _read_text(path: Path) -> str:
    if not _safe_regular_file(path):
        raise CurrentProductionSshNoninteractiveTransportProofError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshNoninteractiveTransportProofError) as exc:
        raise CurrentProductionSshNoninteractiveTransportProofError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "noninteractive SSH transport-proof contract")


def _expected_contract() -> dict[str, Any]:
    return {
        "local_route_policy_contract_id": LOCAL_ROUTE_POLICY_CONTRACT_ID,
        "local_route_policy_contract_status": LOCAL_ROUTE_POLICY_CONTRACT_STATUS,
        "accepted_route_shape": "DIRECT",
        "maximum_ssh_connection_attempts": 1,
        "connect_timeout_seconds": 10,
        "remote_command": "sudo -n true",
        "password_authentication_permitted": False,
        "keyboard_interactive_authentication_permitted": False,
        "local_known_hosts_modified": False,
        "provider_api_requests": 0,
        "github_api_requests": 0,
    }


def _contract_boundary() -> dict[str, Any]:
    return {
        "fixed_local_route_policy_contract_read_only": True,
        "local_ssh_config_metadata_read": True,
        "configured_identity_material_directly_inspected": False,
        "credential_material_emitted_or_persisted": False,
        "candidate_alias_or_target_value_emitted_or_persisted": False,
        "interactive_authentication_permitted": False,
        "local_known_hosts_modified": False,
        "ssh_connection_attempted_at_most_once": True,
        "remote_command_limited_to_noninteractive_sudo_true": True,
        "remote_config_runtime_env_or_secret_read": False,
        "remote_script_written": False,
        "host_runtime_or_configuration_changed": False,
        "image_loaded_or_retagged": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }


def validate_contract(contract: Mapping[str, Any]) -> None:
    if set(contract) != CONTRACT_FIELDS:
        raise CurrentProductionSshNoninteractiveTransportProofError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-SSH-NONINTERACTIVE-TRANSPORT-PROOF-001":
        raise CurrentProductionSshNoninteractiveTransportProofError("contract identity is invalid")
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_READ_ONLY":
        raise CurrentProductionSshNoninteractiveTransportProofError("contract status is invalid")
    if _object(contract.get("expected"), "contract expected") != _expected_contract():
        raise CurrentProductionSshNoninteractiveTransportProofError("contract expectations are invalid")
    if _object(contract.get("source_boundary"), "contract boundary") != _contract_boundary():
        raise CurrentProductionSshNoninteractiveTransportProofError("contract boundary is invalid")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_ONLY_NOT_CURRENT_HOST_METADATA_CONFIG_SEMANTIC_CHECK_HOST_RECOVERY_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionSshNoninteractiveTransportProofError("contract claim boundary is invalid")
    if _object(contract.get("rollback"), "contract rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionSshNoninteractiveTransportProofError("contract rollback is invalid")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF",
        "observed_on": observed_on,
        "local_route_policy_contract_state": "NOT_ATTEMPTED",
        "ssh_config_state": "NOT_ATTEMPTED",
        "route_shape": "NOT_ATTEMPTED",
        "local_route_policy_ready": False,
        "candidate_alias_state": "NOT_ATTEMPTED",
        "transport_state": "SSH_TRANSPORT_NOT_ATTEMPTED_STATIC_INPUT_REJECTED",
        "ssh_connection_attempts": 0,
        "remote_command_attempts": 0,
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


def _canonical_ssh_config(path: Path) -> bool:
    expected = Path.home() / ".ssh" / "config"
    try:
        return path.absolute() == expected.absolute() and _safe_regular_file(path)
    except OSError:
        return False


def _observe_local_route_policy_contract(path: Path) -> str:
    try:
        candidate = local_route.load_contract(path)
    except local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError:
        return "UNAVAILABLE_REDACTED"
    try:
        local_route.validate_contract(candidate)
    except local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError:
        return "REJECTED_REDACTED"
    return "OBSERVED_STATIC"


def _classify_ssh_result(result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode == 0:
        return "SSH_NONINTERACTIVE_SUDO_READY"
    message = result.stderr.lower()
    if "permission denied" in message:
        return "SSH_AUTH_FAILED_REDACTED"
    if "host key verification failed" in message or "no hostkey" in message:
        return "SSH_HOST_KEY_FAILED_REDACTED"
    if any(token in message for token in ("connection timed out", "operation timed out", "connection refused", "no route to host", "network is unreachable", "could not resolve")):
        return "SSH_TRANSPORT_FAILED_REDACTED"
    return "SSH_OTHER_FAILURE_REDACTED"


def _run_noninteractive_sudo_true(alias: str, ssh_config: Path) -> str:
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    command = [
        "ssh",
        "-F", str(ssh_config),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ConnectionAttempts=1",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "GlobalKnownHostsFile=" + str(known_hosts),
        "-o", "UpdateHostKeys=no",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "NumberOfPasswordPrompts=0",
        "-o", "PreferredAuthentications=publickey",
        "-o", "IdentitiesOnly=yes",
        "-o", "ForwardAgent=no",
        "-o", "ClearAllForwardings=yes",
        "-o", "PermitLocalCommand=no",
        "-o", "ControlMaster=no",
        "-o", "ControlPath=none",
        "-o", "RequestTTY=no",
        "-o", "LogLevel=ERROR",
        alias,
        "sudo -n true",
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "SSH_CONNECT_TIMEOUT_REDACTED"
    except OSError:
        return "SSH_OTHER_FAILURE_REDACTED"
    return _classify_ssh_result(result)


def _static_inputs_ready(facts: Mapping[str, Any]) -> bool:
    return facts.get("local_route_policy_contract_state") == "OBSERVED_STATIC" and facts.get("ssh_config_state") == "RESOLVED"


def discover_noninteractive_transport_proof(
    local_route_policy_contract_path: Path,
    ssh_config_path: Path,
    observed_on: str,
) -> dict[str, Any]:
    """Use the existing local policy diagnostic, then make at most one remote sudo true call."""

    facts = _base_facts(observed_on)
    facts["local_route_policy_contract_state"] = _observe_local_route_policy_contract(local_route_policy_contract_path)
    if facts["local_route_policy_contract_state"] != "OBSERVED_STATIC":
        return facts
    if not _canonical_ssh_config(ssh_config_path):
        facts["ssh_config_state"] = "NONCANONICAL_REDACTED"
        return facts
    try:
        route_facts = local_route.discover_local_route_policy(ssh_config_path)
        local_route.validate_facts(route_facts)
    except (OSError, UnicodeDecodeError, ValueError, local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError):
        facts["ssh_config_state"] = "UNAVAILABLE_REDACTED"
        return facts
    facts["ssh_config_state"] = "RESOLVED" if route_facts["ssh_config_state"] == "RESOLVED" else "UNAVAILABLE_REDACTED"
    facts["route_shape"] = str(route_facts["route_shape"])
    facts["local_route_policy_ready"] = bool(route_facts["local_route_policy_ready"])
    if facts["ssh_config_state"] != "RESOLVED" or facts["route_shape"] != "DIRECT" or facts["local_route_policy_ready"] is not True:
        facts["transport_state"] = "SSH_TRANSPORT_NOT_ATTEMPTED_LOCAL_POLICY_NOT_READY_REDACTED"
        return facts
    aliases = local_route._candidate_aliases(ssh_config_path)
    if aliases is None or len(aliases) != 1:
        facts["candidate_alias_state"] = "UNAVAILABLE_REDACTED"
        facts["transport_state"] = "SSH_TRANSPORT_NOT_ATTEMPTED_CANDIDATE_ALIAS_UNAVAILABLE_REDACTED"
        return facts
    facts["candidate_alias_state"] = "RESOLVED_IN_MEMORY"
    facts["ssh_connection_attempts"] = 1
    facts["remote_command_attempts"] = 1
    facts["transport_state"] = _run_noninteractive_sudo_true(next(iter(aliases)), ssh_config_path)
    return facts


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "local_route_policy_contract_state",
        "ssh_config_state",
        "route_shape",
        "local_route_policy_ready",
        "candidate_alias_state",
        "transport_state",
        "ssh_connection_attempts",
        "remote_command_attempts",
        "current_host_metadata_read",
        "repair_execution_authorized",
        "core_start_authorized",
        "credential_material_read_or_persisted",
        "candidate_alias_or_target_value_read_or_persisted",
        "local_known_hosts_modified",
        "provider_api_requests",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionSshNoninteractiveTransportProofError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF":
        raise CurrentProductionSshNoninteractiveTransportProofError("facts identity is invalid")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionSshNoninteractiveTransportProofError("facts observation date is invalid") from exc
    if facts.get("local_route_policy_contract_state") not in STATIC_CONTRACT_STATES:
        raise CurrentProductionSshNoninteractiveTransportProofError("route-policy contract state is invalid")
    if facts.get("ssh_config_state") not in SSH_CONFIG_STATES:
        raise CurrentProductionSshNoninteractiveTransportProofError("SSH config state is invalid")
    if facts.get("route_shape") not in ROUTE_SHAPES or type(facts.get("local_route_policy_ready")) is not bool:
        raise CurrentProductionSshNoninteractiveTransportProofError("local route-policy facts are invalid")
    if facts.get("candidate_alias_state") not in CANDIDATE_ALIAS_STATES or facts.get("transport_state") not in TRANSPORT_STATES:
        raise CurrentProductionSshNoninteractiveTransportProofError("transport state is invalid")
    for field in ("ssh_connection_attempts", "remote_command_attempts"):
        if type(facts.get(field)) is not int or facts[field] not in {0, 1}:
            raise CurrentProductionSshNoninteractiveTransportProofError("transport attempt count is invalid")
    for field in (
        "current_host_metadata_read",
        "repair_execution_authorized",
        "core_start_authorized",
        "credential_material_read_or_persisted",
        "candidate_alias_or_target_value_read_or_persisted",
        "local_known_hosts_modified",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionSshNoninteractiveTransportProofError("transport boundary is invalid")
    for field in ("provider_api_requests", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionSshNoninteractiveTransportProofError("outbound operation count is invalid")
    static_ready = _static_inputs_ready(facts)
    if not static_ready:
        if facts["candidate_alias_state"] != "NOT_ATTEMPTED" or facts["ssh_connection_attempts"] != 0 or facts["remote_command_attempts"] != 0 or facts["transport_state"] != "SSH_TRANSPORT_NOT_ATTEMPTED_STATIC_INPUT_REJECTED":
            raise CurrentProductionSshNoninteractiveTransportProofError("static-input transport facts are inconsistent")
        return
    route_ready = facts["route_shape"] == "DIRECT" and facts["local_route_policy_ready"] is True
    if not route_ready:
        if facts["candidate_alias_state"] != "NOT_ATTEMPTED" or facts["ssh_connection_attempts"] != 0 or facts["remote_command_attempts"] != 0 or facts["transport_state"] != "SSH_TRANSPORT_NOT_ATTEMPTED_LOCAL_POLICY_NOT_READY_REDACTED":
            raise CurrentProductionSshNoninteractiveTransportProofError("route-policy transport facts are inconsistent")
        return
    if facts["candidate_alias_state"] == "UNAVAILABLE_REDACTED":
        if facts["ssh_connection_attempts"] != 0 or facts["remote_command_attempts"] != 0 or facts["transport_state"] != "SSH_TRANSPORT_NOT_ATTEMPTED_CANDIDATE_ALIAS_UNAVAILABLE_REDACTED":
            raise CurrentProductionSshNoninteractiveTransportProofError("candidate-alias transport facts are inconsistent")
        return
    if facts["candidate_alias_state"] != "RESOLVED_IN_MEMORY" or facts["ssh_connection_attempts"] != 1 or facts["remote_command_attempts"] != 1:
        raise CurrentProductionSshNoninteractiveTransportProofError("one-shot transport facts are inconsistent")
    if facts["transport_state"].startswith("SSH_TRANSPORT_NOT_ATTEMPTED"):
        raise CurrentProductionSshNoninteractiveTransportProofError("executed transport state is inconsistent")


def evaluate_transport_proof(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    proof_ready = facts["transport_state"] == "SSH_NONINTERACTIVE_SUDO_READY"
    diagnosed = facts["local_route_policy_contract_state"] == "OBSERVED_STATIC" and facts["ssh_config_state"] == "RESOLVED"
    checks = [
        {"id": "LOCAL_ROUTE_POLICY_CONTRACT_STATICALLY_OBSERVED", "passed": facts["local_route_policy_contract_state"] == "OBSERVED_STATIC"},
        {"id": "LOCAL_DIRECT_ROUTE_POLICY_READY", "passed": facts["route_shape"] == "DIRECT" and facts["local_route_policy_ready"] is True},
        {"id": "SSH_CONNECTION_ATTEMPT_LIMIT_RESPECTED", "passed": facts["ssh_connection_attempts"] <= 1},
        {"id": "NONINTERACTIVE_SSH_TRANSPORT_PROOF_READY", "passed": proof_ready},
        {"id": "CURRENT_HOST_METADATA_NOT_READ", "passed": facts["current_host_metadata_read"] is False},
        {"id": "REPAIR_EXECUTION_NOT_AUTHORIZED", "passed": facts["repair_execution_authorized"] is False},
        {"id": "CORE_START_NOT_AUTHORIZED", "passed": facts["core_start_authorized"] is False},
    ]
    return {
        "status": PASS_STATUS if diagnosed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_READY_SEPARATE_CURRENT_HOST_METADATA_COLLECTION_REQUIRED" if proof_ready else "CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_NOT_READY_NO_HOST_MUTATION_AUTHORIZED",
        "transport_diagnosed": diagnosed,
        "transport_attempted": facts["ssh_connection_attempts"] == 1,
        "transport_proof_ready": proof_ready,
        "transport_state": facts["transport_state"],
        "ssh_connection_attempts": facts["ssh_connection_attempts"],
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_transport_proof(contract, facts)
    required = {
        "status",
        "decision",
        "transport_diagnosed",
        "transport_attempted",
        "transport_proof_ready",
        "transport_state",
        "ssh_connection_attempts",
        "current_host_metadata_collection_authorized",
        "repair_execution_authorized",
        "core_start_authorized",
        "checks",
        "failure_codes",
    }
    if set(result) != required:
        raise CurrentProductionSshNoninteractiveTransportProofError("transport result field set is not exact")
    if any(result[field] is not False for field in ("current_host_metadata_collection_authorized", "repair_execution_authorized", "core_start_authorized")):
        raise CurrentProductionSshNoninteractiveTransportProofError("transport authorization state is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionSshNoninteractiveTransportProofError("transport checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "transport_diagnosed": result["transport_diagnosed"],
        "transport_attempted": result["transport_attempted"],
        "transport_proof_ready": result["transport_proof_ready"],
        "transport_state": result["transport_state"],
        "ssh_connection_attempts": result["ssh_connection_attempts"],
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": list(checks),
        "failure_codes": list(result["failure_codes"]),
        "source_boundary": dict(_object(contract["source_boundary"], "contract boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        safe_observed_on = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        safe_observed_on = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_INPUT_FAILED_CLOSED",
        "observed_on": safe_observed_on,
        "transport_diagnosed": False,
        "transport_attempted": False,
        "transport_proof_ready": False,
        "transport_state": "SSH_TRANSPORT_NOT_ATTEMPTED_STATIC_INPUT_REJECTED",
        "ssh_connection_attempts": 0,
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_SSH_NONINTERACTIVE_TRANSPORT_PROOF_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--local-route-policy-contract", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(
            load_contract(args.contract),
            discover_noninteractive_transport_proof(
                args.local_route_policy_contract,
                args.ssh_config,
                args.observed_on,
            ),
        )
    except (
        CurrentProductionSshNoninteractiveTransportProofError,
        local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError,
        OSError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
