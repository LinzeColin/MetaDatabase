#!/usr/bin/env python3
"""Classify one redacted SSH TCP transport observation without SSH authentication."""

from __future__ import annotations

import argparse
import errno
import ipaddress
import json
import re
import shutil
import socket
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC"
SSH_CONFIG_STATES = {
    "RESOLVED",
    "SSH_CONFIG_UNAVAILABLE_REDACTED",
    "CANDIDATE_ALIAS_UNAVAILABLE_REDACTED",
    "CANDIDATE_ALIAS_AMBIGUOUS_REDACTED",
    "SSH_CONFIG_EFFECTIVE_POLICY_UNAVAILABLE_REDACTED",
    "SSH_CONFIG_METADATA_UNAVAILABLE_REDACTED",
}
ROUTE_SHAPES = {"DIRECT", "PROXY_COMMAND", "PROXY_JUMP", "PROXY_BOTH", "UNKNOWN"}
TARGET_ADDRESS_SHAPES = {"NUMERIC", "NONNUMERIC_NOT_CONNECTED_REDACTED", "NOT_ATTEMPTED"}
TCP_CONNECTIVITY_STATES = {
    "CONNECTED",
    "CONNECT_TIMEOUT_REDACTED",
    "CONNECTION_REFUSED_REDACTED",
    "ROUTE_UNREACHABLE_REDACTED",
    "SOCKET_UNAVAILABLE_REDACTED",
    "OTHER_SOCKET_FAILURE_REDACTED",
    "NOT_APPLICABLE_PROXY",
    "NOT_ATTEMPTED",
}
ACTIVE_TCP_OBSERVATION_STATES = TCP_CONNECTIVITY_STATES - {"NOT_APPLICABLE_PROXY", "NOT_ATTEMPTED"}
ALIAS_TOKEN_PATTERN = re.compile(r"(?:^|[-_.])(ovh|vps)(?:$|[-_.])", re.IGNORECASE)
SAFE_ALIAS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
LOCAL_COMMAND_TIMEOUT_SECONDS = 2
TCP_CONNECT_TIMEOUT_SECONDS = 3


class CurrentProductionSshTransportFailureClassificationDiagnosticError(ValueError):
    """Raised when a contract or redacted classification fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshTransportFailureClassificationDiagnosticError) as exc:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "SSH transport failure-classification contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted SSH transport failure-classification facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-SSH-TRANSPORT-FAILURE-CLASSIFICATION-001":
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_READ_ONLY":
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("diagnostic must remain read-only")
    expected = {
        "candidate_alias_selector": "UNIQUE_OVH_OR_VPS_HOST_DECLARATION",
        "maximum_local_command_timeout_seconds": 2,
        "tcp_connect_timeout_seconds": 3,
        "dns_resolution_attempts": 0,
        "socket_connection_attempts_at_most": 1,
        "ssh_connection_attempts": 0,
        "remote_command_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "only_host_declaration_aliases_and_ssh_g_transport_metadata_read": True,
        "ssh_config_values_or_socket_error_emitted_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "dns_resolution_attempted": False,
        "socket_connection_attempted_at_most_once": True,
        "ssh_connection_attempted": False,
        "remote_command_or_sudo_attempted": False,
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
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_ONLY_NOT_DNS_PROBE_SSH_AUTHENTICATION_REMOTE_COMMAND_SUDO_HOST_RECOVERY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "ssh_config_state",
        "route_shape",
        "target_address_shape",
        "tcp_connectivity",
        "socket_connection_attempts",
        "ssh_connection_attempts",
        "dns_resolution_attempts",
        "provider_api_requests",
        "github_api_requests",
        "browser_login_submitted",
        "ssh_config_value_emitted_or_persisted",
        "socket_error_emitted_or_persisted",
    }
    if set(facts) != required:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC":
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("ssh_config_state") not in SSH_CONFIG_STATES:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("SSH config state is invalid")
    if facts.get("route_shape") not in ROUTE_SHAPES:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("route shape is invalid")
    if facts.get("target_address_shape") not in TARGET_ADDRESS_SHAPES:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("target address shape is invalid")
    if facts.get("tcp_connectivity") not in TCP_CONNECTIVITY_STATES:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("TCP connectivity state is invalid")
    if facts.get("socket_connection_attempts") not in {0, 1}:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("socket connection attempt count is invalid")
    for field in ("ssh_connection_attempts", "dns_resolution_attempts", "provider_api_requests", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionSshTransportFailureClassificationDiagnosticError("outbound operation count is invalid")
    for field in ("browser_login_submitted", "ssh_config_value_emitted_or_persisted", "socket_error_emitted_or_persisted"):
        if facts.get(field) is not False:
            raise CurrentProductionSshTransportFailureClassificationDiagnosticError("redaction boundary is invalid")

    if facts["ssh_config_state"] != "RESOLVED":
        expected = {
            "route_shape": "UNKNOWN",
            "target_address_shape": "NOT_ATTEMPTED",
            "tcp_connectivity": "NOT_ATTEMPTED",
            "socket_connection_attempts": 0,
        }
        if {key: facts[key] for key in expected} != expected:
            raise CurrentProductionSshTransportFailureClassificationDiagnosticError("unresolved SSH config facts are inconsistent")
        return
    if facts["route_shape"] != "DIRECT":
        expected = {
            "target_address_shape": "NOT_ATTEMPTED",
            "tcp_connectivity": "NOT_APPLICABLE_PROXY",
            "socket_connection_attempts": 0,
        }
        if {key: facts[key] for key in expected} != expected:
            raise CurrentProductionSshTransportFailureClassificationDiagnosticError("proxy transport facts are inconsistent")
        return
    if facts["target_address_shape"] == "NONNUMERIC_NOT_CONNECTED_REDACTED":
        expected = {"tcp_connectivity": "NOT_ATTEMPTED", "socket_connection_attempts": 0}
        if {key: facts[key] for key in expected} != expected:
            raise CurrentProductionSshTransportFailureClassificationDiagnosticError("nonnumeric transport facts are inconsistent")
        return
    if facts["target_address_shape"] != "NUMERIC" or facts["socket_connection_attempts"] != 1:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("direct TCP classification facts are incomplete")
    if facts["tcp_connectivity"] not in ACTIVE_TCP_OBSERVATION_STATES:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("direct TCP observation is invalid")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "ssh_config_state": "SSH_CONFIG_UNAVAILABLE_REDACTED",
        "route_shape": "UNKNOWN",
        "target_address_shape": "NOT_ATTEMPTED",
        "tcp_connectivity": "NOT_ATTEMPTED",
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "dns_resolution_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
        "ssh_config_value_emitted_or_persisted": False,
        "socket_error_emitted_or_persisted": False,
    }


def _candidate_aliases(ssh_config: Path) -> set[str] | None:
    try:
        text = _read_text(ssh_config)
    except (OSError, UnicodeDecodeError, CurrentProductionSshTransportFailureClassificationDiagnosticError):
        return None
    aliases: set[str] = set()
    for line in text.splitlines():
        fields = line.strip().split()
        if len(fields) < 2 or fields[0].lower() != "host":
            continue
        for alias in fields[1:]:
            if not SAFE_ALIAS_PATTERN.fullmatch(alias) or any(marker in alias for marker in ("*", "?", "!")):
                continue
            if ALIAS_TOKEN_PATTERN.search(alias):
                aliases.add(alias)
    return aliases


def _ssh_g_is_locally_safe(ssh_config: Path) -> bool | None:
    try:
        text = _read_text(ssh_config)
    except (OSError, UnicodeDecodeError, CurrentProductionSshTransportFailureClassificationDiagnosticError):
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
            timeout=LOCAL_COMMAND_TIMEOUT_SECONDS,
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


def _classify_connect_result(code: int) -> str:
    if code == 0:
        return "CONNECTED"
    if code == errno.ETIMEDOUT:
        return "CONNECT_TIMEOUT_REDACTED"
    if code == errno.ECONNREFUSED:
        return "CONNECTION_REFUSED_REDACTED"
    if code in {getattr(errno, "EHOSTUNREACH", -1), getattr(errno, "ENETUNREACH", -2)}:
        return "ROUTE_UNREACHABLE_REDACTED"
    return "OTHER_SOCKET_FAILURE_REDACTED"


def _connect_once(numeric_target: str, port: int) -> str:
    address = ipaddress.ip_address(numeric_target)
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    endpoint: tuple[object, ...] = (numeric_target, port, 0, 0) if family == socket.AF_INET6 else (numeric_target, port)
    value: socket.socket | None = None
    try:
        value = socket.socket(family, socket.SOCK_STREAM)
        value.settimeout(TCP_CONNECT_TIMEOUT_SECONDS)
        return _classify_connect_result(value.connect_ex(endpoint))
    except TimeoutError:
        return "CONNECT_TIMEOUT_REDACTED"
    except OSError as exc:
        return "SOCKET_UNAVAILABLE_REDACTED" if exc.errno is None else _classify_connect_result(exc.errno)
    finally:
        if value is not None:
            value.close()


def discover_transport_failure_classification(ssh_config: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Make at most one TCP connect to a direct numeric SSH target; never authenticate."""

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

    hostname, port, proxycommand, proxyjump = metadata
    facts["ssh_config_state"] = "RESOLVED"
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
        facts["tcp_connectivity"] = "NOT_APPLICABLE_PROXY"
        return facts
    try:
        numeric_target = str(ipaddress.ip_address(hostname))
    except ValueError:
        facts["target_address_shape"] = "NONNUMERIC_NOT_CONNECTED_REDACTED"
        return facts
    facts["target_address_shape"] = "NUMERIC"
    facts["socket_connection_attempts"] = 1
    facts["tcp_connectivity"] = _connect_once(numeric_target, port)
    return facts


def _transport_state(facts: Mapping[str, Any]) -> str:
    if facts["ssh_config_state"] != "RESOLVED":
        return str(facts["ssh_config_state"])
    if facts["route_shape"] != "DIRECT":
        return "SSH_TRANSPORT_PROXY_NOT_CONNECTED"
    if facts["target_address_shape"] != "NUMERIC":
        return "SSH_TRANSPORT_NONNUMERIC_NOT_CONNECTED"
    if facts["tcp_connectivity"] == "CONNECTED":
        return "SSH_TCP_CONNECTED_AUTH_NOT_ATTEMPTED"
    return "SSH_TCP_%s" % facts["tcp_connectivity"]


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    complete = facts["route_shape"] == "DIRECT" and facts["target_address_shape"] == "NUMERIC" and facts["socket_connection_attempts"] == 1 and facts["tcp_connectivity"] in ACTIVE_TCP_OBSERVATION_STATES
    reachable = complete and facts["tcp_connectivity"] == "CONNECTED"
    checks = [
        {"id": "SSH_CONFIG_RESOLVED", "passed": facts["ssh_config_state"] == "RESOLVED"},
        {"id": "DIRECT_NUMERIC_TARGET_ELIGIBLE", "passed": facts["route_shape"] == "DIRECT" and facts["target_address_shape"] == "NUMERIC"},
        {"id": "EXACTLY_ONE_TCP_CONNECT_ATTEMPT", "passed": facts["socket_connection_attempts"] == 1},
        {"id": "TCP_FAILURE_CLASSIFICATION_COMPLETED", "passed": complete},
        {"id": "SSH_AUTHENTICATION_NOT_ATTEMPTED", "passed": facts["ssh_connection_attempts"] == 0},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if complete else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_SSH_TCP_CONNECTED_SEPARATE_NONINTERACTIVE_AUTH_DIAGNOSTIC_REQUIRED" if reachable else "CURRENT_PRODUCTION_SSH_TCP_FAILURE_CLASSIFIED_NO_SSH_AUTHORIZATION" if complete else "CURRENT_PRODUCTION_SSH_TCP_CLASSIFICATION_NOT_COMPLETED_NO_CONNECTION_OR_REMOTE_ACTION_AUTHORIZED",
        "transport_failure_classification_completed": complete,
        "tcp_reachable": reachable,
        "core_start_authorized": False,
        "transport_state": _transport_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not isinstance(result["transport_failure_classification_completed"], bool) or not isinstance(result["tcp_reachable"], bool) or result["core_start_authorized"] is not False:
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionSshTransportFailureClassificationDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "transport_failure_classification_completed": result["transport_failure_classification_completed"],
        "tcp_reachable": result["tcp_reachable"],
        "core_start_authorized": False,
        "transport_state": result["transport_state"],
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
        "decision": "CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "transport_failure_classification_completed": False,
        "tcp_reachable": False,
        "core_start_authorized": False,
        "transport_state": "SSH_TRANSPORT_FAILURE_CLASSIFICATION_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), discover_transport_failure_classification(args.ssh_config))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshTransportFailureClassificationDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
