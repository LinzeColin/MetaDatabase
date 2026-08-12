#!/usr/bin/env python3
"""Evaluate one redacted current-production SSH local route-policy diagnostic."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shutil
import socket
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC"
SSH_CONFIG_STATES = {
    "RESOLVED",
    "SSH_CONFIG_UNAVAILABLE_REDACTED",
    "CANDIDATE_ALIAS_UNAVAILABLE_REDACTED",
    "CANDIDATE_ALIAS_AMBIGUOUS_REDACTED",
    "SSH_CONFIG_METADATA_UNAVAILABLE_REDACTED",
    "SSH_CONFIG_EFFECTIVE_POLICY_UNAVAILABLE_REDACTED",
}
ROUTE_SHAPES = {"DIRECT", "PROXY_COMMAND", "PROXY_JUMP", "PROXY_BOTH", "UNKNOWN"}
DEFAULT_ROUTE_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED", "ROUTE_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}
TARGET_ROUTE_STATES = {
    "AVAILABLE",
    "UNAVAILABLE_REDACTED",
    "ROUTE_TOOL_UNAVAILABLE_REDACTED",
    "NONNUMERIC_NOT_EVALUATED_REDACTED",
    "NOT_APPLICABLE_PROXY",
    "NOT_ATTEMPTED",
}
SOCKET_PRECHECK_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}
ALIAS_TOKEN_PATTERN = re.compile(r"(?:^|[-_.])(ovh|vps)(?:$|[-_.])", re.IGNORECASE)
TIMEOUT_SECONDS = 2


class CurrentProductionSshLocalRoutePolicyDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshLocalRoutePolicyDiagnosticError) as exc:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "SSH local route-policy diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted SSH local route-policy facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-SSH-LOCAL-ROUTE-POLICY-DIAGNOSTIC-001":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("diagnostic must remain read-only")
    expected = {
        "candidate_alias_selector": "UNIQUE_OVH_OR_VPS_HOST_DECLARATION",
        "maximum_local_command_timeout_seconds": 2,
        "route_queries": ["default", "numeric_target_only"],
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "only_host_declaration_aliases_and_ssh_g_transport_metadata_read": True,
        "alias_address_port_user_identity_proxy_or_route_values_emitted_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "socket_connection_attempted": False,
        "ssh_connection_attempted": False,
        "interactive_authentication_permitted": False,
        "local_known_hosts_modified": False,
        "provider_api_request_sent": False,
        "github_api_request_sent": False,
        "provider_resource_created_deleted_rebuilt_or_restarted": False,
        "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_ONLY_NOT_DNS_PROBE_SOCKET_CONNECTION_SSH_AUTHENTICATION_HOST_RECOVERY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_LOCAL_NETWORK_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "ssh_config_state",
        "route_shape",
        "default_route_state",
        "target_route_state",
        "socket_precheck_state",
        "local_route_policy_ready",
        "ssh_config_value_emitted_or_persisted",
        "route_output_emitted_or_persisted",
        "socket_connection_attempts",
        "ssh_connection_attempts",
        "provider_api_requests",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("facts observation date is invalid") from exc
    if facts.get("ssh_config_state") not in SSH_CONFIG_STATES:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("SSH config state is invalid")
    if facts.get("route_shape") not in ROUTE_SHAPES:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("route shape is invalid")
    if facts.get("default_route_state") not in DEFAULT_ROUTE_STATES:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("default route state is invalid")
    if facts.get("target_route_state") not in TARGET_ROUTE_STATES:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("target route state is invalid")
    if facts.get("socket_precheck_state") not in SOCKET_PRECHECK_STATES:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("socket precheck state is invalid")
    if type(facts.get("local_route_policy_ready")) is not bool:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("local route readiness is invalid")
    for field in ("ssh_config_value_emitted_or_persisted", "route_output_emitted_or_persisted", "browser_login_submitted"):
        if facts.get(field) is not False:
            raise CurrentProductionSshLocalRoutePolicyDiagnosticError("redaction boundary is invalid")
    for field in ("socket_connection_attempts", "ssh_connection_attempts", "provider_api_requests", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionSshLocalRoutePolicyDiagnosticError("outbound operation count is invalid")

    resolved = facts["ssh_config_state"] == "RESOLVED"
    ready = facts["local_route_policy_ready"]
    if not resolved:
        expected = {
            "route_shape": "UNKNOWN",
            "default_route_state": "NOT_ATTEMPTED",
            "target_route_state": "NOT_ATTEMPTED",
            "socket_precheck_state": "NOT_ATTEMPTED",
        }
        if {key: facts[key] for key in expected} != expected or ready:
            raise CurrentProductionSshLocalRoutePolicyDiagnosticError("unresolved SSH config facts are inconsistent")
        return
    if facts["socket_precheck_state"] == "NOT_ATTEMPTED" or facts["default_route_state"] == "NOT_ATTEMPTED":
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("resolved local precheck facts are incomplete")
    if facts["route_shape"] == "DIRECT":
        if facts["target_route_state"] in {"NOT_ATTEMPTED", "NOT_APPLICABLE_PROXY"}:
            raise CurrentProductionSshLocalRoutePolicyDiagnosticError("direct local target-route facts are incomplete")
        expected_ready = facts["socket_precheck_state"] == "AVAILABLE" and facts["default_route_state"] == "AVAILABLE" and facts["target_route_state"] == "AVAILABLE"
        if ready != expected_ready:
            raise CurrentProductionSshLocalRoutePolicyDiagnosticError("direct local route policy readiness is inconsistent")
    else:
        if facts["target_route_state"] != "NOT_APPLICABLE_PROXY" or ready:
            raise CurrentProductionSshLocalRoutePolicyDiagnosticError("proxy local route policy facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC",
        "observed_on": observed_on,
        "ssh_config_state": "SSH_CONFIG_UNAVAILABLE_REDACTED",
        "route_shape": "UNKNOWN",
        "default_route_state": "NOT_ATTEMPTED",
        "target_route_state": "NOT_ATTEMPTED",
        "socket_precheck_state": "NOT_ATTEMPTED",
        "local_route_policy_ready": False,
        "ssh_config_value_emitted_or_persisted": False,
        "route_output_emitted_or_persisted": False,
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }


def _candidate_aliases(ssh_config: Path) -> set[str] | None:
    try:
        text = _read_text(ssh_config)
    except (OSError, UnicodeDecodeError, CurrentProductionSshLocalRoutePolicyDiagnosticError):
        return None
    aliases: set[str] = set()
    for line in text.splitlines():
        fields = line.strip().split()
        if len(fields) < 2 or fields[0].lower() != "host":
            continue
        for alias in fields[1:]:
            if any(marker in alias for marker in ("*", "?", "!")):
                continue
            if ALIAS_TOKEN_PATTERN.search(alias):
                aliases.add(alias)
    return aliases


def _ssh_g_is_locally_safe(ssh_config: Path) -> bool | None:
    """Reject effective-config expansion or command predicates before ssh -G."""

    try:
        text = _read_text(ssh_config)
    except (OSError, UnicodeDecodeError, CurrentProductionSshLocalRoutePolicyDiagnosticError):
        return None
    for line in text.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        key = fields[0].lower()
        if key == "include":
            return False
        if key == "match" and any(field.lower() == "exec" for field in fields[1:]):
            return False
    return True


def _ssh_g_metadata(alias: str) -> tuple[str, int, str, str] | None:
    ssh = shutil.which("ssh")
    if ssh is None:
        return None
    try:
        result = subprocess.run(
            [ssh, "-G", alias],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(" ")
        if separator and key in {"hostname", "port", "proxycommand", "proxyjump"}:
            values[key] = value.strip()
    hostname = values.get("hostname", "")
    try:
        port = int(values.get("port", "0"))
    except ValueError:
        return None
    if not hostname or not 1 <= port <= 65535:
        return None
    return hostname, port, values.get("proxycommand", "none"), values.get("proxyjump", "none")


def _route_state(destination: str) -> str:
    route = shutil.which("route")
    if route is None:
        return "ROUTE_TOOL_UNAVAILABLE_REDACTED"
    try:
        result = subprocess.run(
            [route, "-n", "get", destination],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNAVAILABLE_REDACTED"
    if result.returncode != 0:
        return "UNAVAILABLE_REDACTED"
    return "AVAILABLE" if any(line.strip().lower().startswith("interface:") for line in result.stdout.splitlines()) else "UNAVAILABLE_REDACTED"


def _socket_precheck() -> str:
    try:
        value = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return "UNAVAILABLE_REDACTED"
    value.close()
    return "AVAILABLE"


def discover_local_route_policy(ssh_config: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Classify local SSH route policy without DNS, socket, or SSH connections."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    aliases = _candidate_aliases(ssh_config)
    if aliases is None:
        return facts
    if not aliases:
        facts["ssh_config_state"] = "CANDIDATE_ALIAS_UNAVAILABLE_REDACTED"
        return facts
    if len(aliases) != 1:
        facts["ssh_config_state"] = "CANDIDATE_ALIAS_AMBIGUOUS_REDACTED"
        return facts
    if _ssh_g_is_locally_safe(ssh_config) is not True:
        facts["ssh_config_state"] = "SSH_CONFIG_EFFECTIVE_POLICY_UNAVAILABLE_REDACTED"
        return facts
    metadata = _ssh_g_metadata(next(iter(aliases)))
    if metadata is None:
        facts["ssh_config_state"] = "SSH_CONFIG_METADATA_UNAVAILABLE_REDACTED"
        return facts

    hostname, _port, proxycommand, proxyjump = metadata
    facts["ssh_config_state"] = "RESOLVED"
    facts["socket_precheck_state"] = _socket_precheck()
    facts["default_route_state"] = _route_state("default")
    command_configured = proxycommand != "none"
    jump_configured = proxyjump != "none"
    if command_configured and jump_configured:
        facts["route_shape"] = "PROXY_BOTH"
    elif command_configured:
        facts["route_shape"] = "PROXY_COMMAND"
    elif jump_configured:
        facts["route_shape"] = "PROXY_JUMP"
    else:
        facts["route_shape"] = "DIRECT"
    if facts["route_shape"] != "DIRECT":
        facts["target_route_state"] = "NOT_APPLICABLE_PROXY"
        return facts
    try:
        numeric_target = str(ipaddress.ip_address(hostname))
    except ValueError:
        facts["target_route_state"] = "NONNUMERIC_NOT_EVALUATED_REDACTED"
        return facts
    facts["target_route_state"] = _route_state(numeric_target)
    facts["local_route_policy_ready"] = (
        facts["socket_precheck_state"] == "AVAILABLE"
        and facts["default_route_state"] == "AVAILABLE"
        and facts["target_route_state"] == "AVAILABLE"
    )
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    diagnosed = facts["ssh_config_state"] == "RESOLVED"
    ready = bool(facts["local_route_policy_ready"])
    checks = [
        {"id": "SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_COMPLETED", "passed": diagnosed},
        {"id": "SSH_LOCAL_ROUTE_POLICY_READY", "passed": ready},
        {"id": "SOCKET_SSH_PROVIDER_GITHUB_CONNECTIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if diagnosed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_READY_SEPARATE_TRANSPORT_DIAGNOSTIC_REQUIRED" if ready else "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_NOT_READY_NO_SOCKET_OR_REMOTE_ACTION_AUTHORIZED",
        "local_route_policy_diagnosed": diagnosed,
        "local_route_policy_ready": ready,
        "core_start_authorized": False,
        "local_route_policy_state": _policy_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def _policy_state(facts: Mapping[str, Any]) -> str:
    if facts["ssh_config_state"] != "RESOLVED":
        return str(facts["ssh_config_state"])
    if facts["route_shape"] != "DIRECT":
        return "SSH_LOCAL_ROUTE_PROXY_UNEVALUATED"
    if facts["socket_precheck_state"] != "AVAILABLE":
        return "SSH_LOCAL_SOCKET_PRECHECK_UNAVAILABLE"
    if facts["default_route_state"] != "AVAILABLE":
        return "SSH_LOCAL_DEFAULT_ROUTE_%s" % facts["default_route_state"]
    if facts["target_route_state"] != "AVAILABLE":
        return "SSH_LOCAL_TARGET_ROUTE_%s" % facts["target_route_state"]
    return "SSH_LOCAL_ROUTE_POLICY_READY"


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not isinstance(result["local_route_policy_diagnosed"], bool) or not isinstance(result["local_route_policy_ready"], bool) or result["core_start_authorized"] is not False:
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionSshLocalRoutePolicyDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "local_route_policy_diagnosed": result["local_route_policy_diagnosed"],
        "local_route_policy_ready": result["local_route_policy_ready"],
        "core_start_authorized": False,
        "local_route_policy_state": result["local_route_policy_state"],
        "checks": list(checks),
        "failure_codes": list(result["failure_codes"]),
        "source_boundary": dict(_object(contract["source_boundary"], "source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "local_route_policy_diagnosed": False,
        "local_route_policy_ready": False,
        "core_start_authorized": False,
        "local_route_policy_state": "SSH_LOCAL_ROUTE_POLICY_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "local_network_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), discover_local_route_policy(args.ssh_config))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshLocalRoutePolicyDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
