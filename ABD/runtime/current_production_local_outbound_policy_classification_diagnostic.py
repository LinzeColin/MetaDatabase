#!/usr/bin/env python3
"""Classify local outbound policy without target, DNS, socket, or SSH activity."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC"
ROUTE_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED", "ROUTE_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}
PROXY_STATES = {"DIRECT_OR_DISABLED", "PROXY_CONFIGURED", "UNAVAILABLE_REDACTED", "PROXY_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}
PACKET_FILTER_STATES = {"ENABLED", "DISABLED", "UNAVAILABLE_REDACTED", "PF_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}
POLICY_STATES = {
    "NO_LOCAL_POLICY_CAUSE_OBSERVED_REDACTED",
    "PROXY_CONFIGURATION_PRESENT_NONCAUSAL_REDACTED",
    "PACKET_FILTER_ENABLED_NONCAUSAL_REDACTED",
    "PROXY_AND_PACKET_FILTER_PRESENT_NONCAUSAL_REDACTED",
    "LOCAL_POLICY_UNKNOWN_REDACTED",
}
LOCAL_COMMAND_TIMEOUT_SECONDS = 2
ROUTE_COMMAND = (Path("/sbin/route"), ("-n", "get", "default"))
PROXY_COMMAND = (Path("/usr/sbin/scutil"), ("--proxy",))
PACKET_FILTER_COMMAND = (Path("/sbin/pfctl"), ("-s", "info"))
PROXY_ENABLE_KEYS = {"HTTPEnable", "HTTPSEnable", "SOCKSEnable", "ProxyAutoConfigEnable", "ProxyAutoDiscoveryEnable"}


class CurrentProductionLocalOutboundPolicyClassificationDiagnosticError(ValueError):
    """Raised when a contract or redacted local policy fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionLocalOutboundPolicyClassificationDiagnosticError) as exc:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "local outbound-policy classification contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted local outbound-policy facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-LOCAL-OUTBOUND-POLICY-CLASSIFICATION-001":
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_READ_ONLY":
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("diagnostic must remain read-only")
    expected = {
        "local_commands": ["route -n get default", "scutil --proxy", "pfctl -s info"],
        "maximum_each_local_command_timeout_seconds": 2,
        "route_command_attempts_at_most": 1,
        "proxy_command_attempts_at_most": 1,
        "packet_filter_command_attempts_at_most": 1,
        "dns_resolution_attempts": 0,
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "target_address_port_alias_or_route_values_emitted_or_persisted": False,
        "proxy_or_packet_filter_rule_values_emitted_or_persisted": False,
        "credential_config_runtime_env_or_secret_read": False,
        "packet_filter_rules_read": False,
        "dns_resolution_attempted": False,
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
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_ONLY_NOT_TARGET_CAUSE_PROOF_DNS_PROBE_SOCKET_CONNECTION_SSH_AUTHENTICATION_HOST_RECOVERY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_LOCAL_NETWORK_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("rollback boundary is not exact")


def _policy_state(facts: Mapping[str, Any]) -> str:
    if facts["default_route_state"] in {"UNAVAILABLE_REDACTED", "ROUTE_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}:
        return "LOCAL_POLICY_UNKNOWN_REDACTED"
    if facts["proxy_policy_state"] in {"UNAVAILABLE_REDACTED", "PROXY_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}:
        return "LOCAL_POLICY_UNKNOWN_REDACTED"
    if facts["packet_filter_state"] in {"UNAVAILABLE_REDACTED", "PF_TOOL_UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}:
        return "LOCAL_POLICY_UNKNOWN_REDACTED"
    proxy_configured = facts["proxy_policy_state"] == "PROXY_CONFIGURED"
    filter_enabled = facts["packet_filter_state"] == "ENABLED"
    if proxy_configured and filter_enabled:
        return "PROXY_AND_PACKET_FILTER_PRESENT_NONCAUSAL_REDACTED"
    if proxy_configured:
        return "PROXY_CONFIGURATION_PRESENT_NONCAUSAL_REDACTED"
    if filter_enabled:
        return "PACKET_FILTER_ENABLED_NONCAUSAL_REDACTED"
    return "NO_LOCAL_POLICY_CAUSE_OBSERVED_REDACTED"


def _expected_attempt(state: str, unavailable_states: set[str]) -> int:
    if state == "NOT_ATTEMPTED" or state in unavailable_states:
        return 0
    return 1


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "default_route_state",
        "proxy_policy_state",
        "packet_filter_state",
        "local_outbound_policy_state",
        "policy_diagnosed",
        "current_tcp_failure_explained",
        "route_command_attempts",
        "proxy_command_attempts",
        "packet_filter_command_attempts",
        "dns_resolution_attempts",
        "socket_connection_attempts",
        "ssh_connection_attempts",
        "provider_api_requests",
        "github_api_requests",
        "browser_login_submitted",
        "route_proxy_or_packet_filter_value_emitted_or_persisted",
    }
    if set(facts) != required:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC":
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("default_route_state") not in ROUTE_STATES:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("default route state is invalid")
    if facts.get("proxy_policy_state") not in PROXY_STATES:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("proxy policy state is invalid")
    if facts.get("packet_filter_state") not in PACKET_FILTER_STATES:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("packet filter state is invalid")
    if facts.get("local_outbound_policy_state") not in POLICY_STATES:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("local policy state is invalid")
    if type(facts.get("policy_diagnosed")) is not bool or facts.get("current_tcp_failure_explained") is not False:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("causal claim boundary is invalid")
    for field, state, unavailable in (
        ("route_command_attempts", facts["default_route_state"], {"ROUTE_TOOL_UNAVAILABLE_REDACTED"}),
        ("proxy_command_attempts", facts["proxy_policy_state"], {"PROXY_TOOL_UNAVAILABLE_REDACTED"}),
        ("packet_filter_command_attempts", facts["packet_filter_state"], {"PF_TOOL_UNAVAILABLE_REDACTED"}),
    ):
        if facts.get(field) not in {0, 1} or facts[field] != _expected_attempt(state, unavailable):
            raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("local command attempt count is invalid")
    for field in ("dns_resolution_attempts", "socket_connection_attempts", "ssh_connection_attempts", "provider_api_requests", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("outbound operation count is invalid")
    for field in ("browser_login_submitted", "route_proxy_or_packet_filter_value_emitted_or_persisted"):
        if facts.get(field) is not False:
            raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("redaction boundary is invalid")
    diagnosed = all(facts[field] != "NOT_ATTEMPTED" for field in ("default_route_state", "proxy_policy_state", "packet_filter_state"))
    if facts["policy_diagnosed"] != diagnosed:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("policy diagnosis state is inconsistent")
    if facts["local_outbound_policy_state"] != _policy_state(facts):
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("local policy classification is inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "default_route_state": "NOT_ATTEMPTED",
        "proxy_policy_state": "NOT_ATTEMPTED",
        "packet_filter_state": "NOT_ATTEMPTED",
        "local_outbound_policy_state": "LOCAL_POLICY_UNKNOWN_REDACTED",
        "policy_diagnosed": False,
        "current_tcp_failure_explained": False,
        "route_command_attempts": 0,
        "proxy_command_attempts": 0,
        "packet_filter_command_attempts": 0,
        "dns_resolution_attempts": 0,
        "socket_connection_attempts": 0,
        "ssh_connection_attempts": 0,
        "provider_api_requests": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
        "route_proxy_or_packet_filter_value_emitted_or_persisted": False,
    }


def _tool_available(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _run_local_command(path: Path, args: tuple[str, ...]) -> str | None:
    try:
        result = subprocess.run(
            [str(path), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=LOCAL_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _route_state(output: str | None) -> str:
    if output is None:
        return "UNAVAILABLE_REDACTED"
    return "AVAILABLE" if any(line.strip().lower().startswith("interface:") for line in output.splitlines()) else "UNAVAILABLE_REDACTED"


def _proxy_state(output: str | None) -> str:
    if output is None:
        return "UNAVAILABLE_REDACTED"
    enabled_keys = set()
    for line in output.splitlines():
        match = re.match(r"^\s*([A-Za-z]+)\s*:\s*([01])\s*$", line)
        if match and match.group(1) in PROXY_ENABLE_KEYS and match.group(2) == "1":
            enabled_keys.add(match.group(1))
    return "PROXY_CONFIGURED" if enabled_keys else "DIRECT_OR_DISABLED"


def _packet_filter_state(output: str | None) -> str:
    if output is None:
        return "UNAVAILABLE_REDACTED"
    if re.search(r"^Status:\s+Enabled\b", output, re.IGNORECASE | re.MULTILINE):
        return "ENABLED"
    if re.search(r"^Status:\s+Disabled\b", output, re.IGNORECASE | re.MULTILINE):
        return "DISABLED"
    return "UNAVAILABLE_REDACTED"


def _observe_command(path: Path, args: tuple[str, ...], unavailable_state: str, classify: Any) -> tuple[str, int]:
    if not _tool_available(path):
        return unavailable_state, 0
    return classify(_run_local_command(path, args)), 1


def discover_local_outbound_policy(observed_on: str | None = None) -> dict[str, Any]:
    """Classify local route, proxy, and PF state without any external activity."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    facts["default_route_state"], facts["route_command_attempts"] = _observe_command(
        *ROUTE_COMMAND, "ROUTE_TOOL_UNAVAILABLE_REDACTED", _route_state
    )
    facts["proxy_policy_state"], facts["proxy_command_attempts"] = _observe_command(
        *PROXY_COMMAND, "PROXY_TOOL_UNAVAILABLE_REDACTED", _proxy_state
    )
    facts["packet_filter_state"], facts["packet_filter_command_attempts"] = _observe_command(
        *PACKET_FILTER_COMMAND, "PF_TOOL_UNAVAILABLE_REDACTED", _packet_filter_state
    )
    facts["policy_diagnosed"] = all(facts[field] != "NOT_ATTEMPTED" for field in ("default_route_state", "proxy_policy_state", "packet_filter_state"))
    facts["local_outbound_policy_state"] = _policy_state(facts)
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    diagnosed = bool(facts["policy_diagnosed"])
    checks = [
        {"id": "LOCAL_ROUTE_PROXY_PACKET_FILTER_CLASSIFIED", "passed": diagnosed},
        {"id": "DNS_SOCKET_SSH_PROVIDER_GITHUB_CONNECTIONS_NOT_ATTEMPTED", "passed": True},
        {"id": "CURRENT_TCP_FAILURE_CAUSE_NOT_CLAIMED", "passed": facts["current_tcp_failure_explained"] is False},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if diagnosed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFIED_NO_CAUSAL_ATTRIBUTION_OR_REMOTE_ACTION_AUTHORIZED" if diagnosed else "CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_NOT_COMPLETED_NO_REMOTE_ACTION_AUTHORIZED",
        "policy_diagnosed": diagnosed,
        "current_tcp_failure_explained": False,
        "core_start_authorized": False,
        "local_outbound_policy_state": facts["local_outbound_policy_state"],
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not isinstance(result["policy_diagnosed"], bool) or result["current_tcp_failure_explained"] is not False or result["core_start_authorized"] is not False:
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionLocalOutboundPolicyClassificationDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "policy_diagnosed": result["policy_diagnosed"],
        "current_tcp_failure_explained": False,
        "core_start_authorized": False,
        "local_outbound_policy_state": result["local_outbound_policy_state"],
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
        "decision": "CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "policy_diagnosed": False,
        "current_tcp_failure_explained": False,
        "core_start_authorized": False,
        "local_outbound_policy_state": "LOCAL_POLICY_UNKNOWN_REDACTED",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_LOCAL_OUTBOUND_POLICY_CLASSIFICATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "local_network_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), discover_local_outbound_policy())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionLocalOutboundPolicyClassificationDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
