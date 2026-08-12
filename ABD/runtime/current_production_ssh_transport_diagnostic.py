#!/usr/bin/env python3
"""Evaluate one redacted current-production SSH transport diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC"
ROUTES = {"DIRECT", "PROXY"}
SSH_FAILURE_STATES = {
    "AUTH_FAILED_REDACTED",
    "HOST_KEY_FAILED_REDACTED",
    "TRANSPORT_FAILED_REDACTED",
    "OTHER_FAILED_REDACTED",
}
TCP_FAILURE_STATES = {
    "CONNECT_TIMEOUT_REDACTED",
    "CONNECTION_REFUSED_REDACTED",
    "OTHER_FAILED_REDACTED",
}


class CurrentProductionSshTransportDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted fact payload is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionSshTransportDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionSshTransportDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshTransportDiagnosticError) as exc:
        raise CurrentProductionSshTransportDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "SSH transport diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted SSH transport diagnostic facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionSshTransportDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionSshTransportDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-SSH-TRANSPORT-DIAGNOSTIC-001":
        raise CurrentProductionSshTransportDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionSshTransportDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionSshTransportDiagnosticError("diagnostic must remain read-only")
    if _object(contract.get("expected"), "expected") != {
        "allowed_routes": ["DIRECT", "PROXY"],
        "direct_tcp_timeout_seconds": 3,
        "ssh_connect_timeout_seconds": 10,
        "remote_commands": ["true", "sudo -n true"],
    }:
        raise CurrentProductionSshTransportDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "local_ssh_config_metadata_read": True,
        "configured_identity_material_directly_inspected": False,
        "credential_material_emitted_or_persisted": False,
        "interactive_authentication_permitted": False,
        "local_known_hosts_modified": False,
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
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionSshTransportDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC_ONLY_NOT_HOST_RECOVERY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionSshTransportDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionSshTransportDiagnosticError("rollback boundary is not exact")


def _validate_terminal_facts(facts: Mapping[str, Any]) -> None:
    if facts["ssh_config_state"] != "RESOLVED":
        expected = {
            "route": "UNKNOWN",
            "name_resolution": "NOT_ATTEMPTED",
            "tcp_connectivity": "NOT_ATTEMPTED",
            "ssh_authentication": "NOT_ATTEMPTED",
            "noninteractive_sudo": "NOT_ATTEMPTED",
        }
        if {key: facts[key] for key in expected} != expected:
            raise CurrentProductionSshTransportDiagnosticError("unresolved SSH config facts are inconsistent")
        return
    route = facts["route"]
    if route not in ROUTES:
        raise CurrentProductionSshTransportDiagnosticError("SSH route is invalid")
    if route == "PROXY":
        expected = {"name_resolution": "NOT_APPLICABLE_PROXY", "tcp_connectivity": "NOT_APPLICABLE_PROXY"}
        if {key: facts[key] for key in expected} != expected or facts["ssh_authentication"] == "NOT_ATTEMPTED":
            raise CurrentProductionSshTransportDiagnosticError("proxy facts are inconsistent")
        if facts["ssh_authentication"] == "PASS" and facts["noninteractive_sudo"] == "NOT_ATTEMPTED":
            raise CurrentProductionSshTransportDiagnosticError("successful proxy SSH requires sudo observation")
        if facts["ssh_authentication"] != "PASS" and facts["noninteractive_sudo"] != "NOT_ATTEMPTED":
            raise CurrentProductionSshTransportDiagnosticError("failed proxy SSH cannot observe sudo")
        return
    if facts["name_resolution"] == "FAILED_REDACTED":
        expected = {"tcp_connectivity": "NOT_ATTEMPTED", "ssh_authentication": "NOT_ATTEMPTED", "noninteractive_sudo": "NOT_ATTEMPTED"}
        if {key: facts[key] for key in expected} != expected:
            raise CurrentProductionSshTransportDiagnosticError("name resolution failure facts are inconsistent")
        return
    if facts["name_resolution"] != "PASS":
        raise CurrentProductionSshTransportDiagnosticError("name resolution state is invalid")
    if facts["tcp_connectivity"] in TCP_FAILURE_STATES:
        expected = {"ssh_authentication": "NOT_ATTEMPTED", "noninteractive_sudo": "NOT_ATTEMPTED"}
        if {key: facts[key] for key in expected} != expected:
            raise CurrentProductionSshTransportDiagnosticError("TCP failure facts are inconsistent")
        return
    if facts["tcp_connectivity"] != "PASS" or facts["ssh_authentication"] == "NOT_ATTEMPTED":
        raise CurrentProductionSshTransportDiagnosticError("direct SSH facts are inconsistent")
    if facts["ssh_authentication"] == "PASS" and facts["noninteractive_sudo"] == "NOT_ATTEMPTED":
        raise CurrentProductionSshTransportDiagnosticError("successful SSH requires sudo observation")
    if facts["ssh_authentication"] != "PASS" and facts["noninteractive_sudo"] != "NOT_ATTEMPTED":
        raise CurrentProductionSshTransportDiagnosticError("failed SSH cannot observe sudo")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {"schema_version", "observation_type", "observed_on", "ssh_config_state", "route", "name_resolution", "tcp_connectivity", "ssh_authentication", "noninteractive_sudo"}
    if set(facts) != required:
        raise CurrentProductionSshTransportDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC":
        raise CurrentProductionSshTransportDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionSshTransportDiagnosticError("facts observation date is invalid") from exc
    if facts.get("ssh_config_state") not in {"RESOLVED", "UNAVAILABLE_REDACTED"}:
        raise CurrentProductionSshTransportDiagnosticError("SSH config state is invalid")
    if facts.get("route") not in {"DIRECT", "PROXY", "UNKNOWN"}:
        raise CurrentProductionSshTransportDiagnosticError("route state is invalid")
    if facts.get("name_resolution") not in {"PASS", "FAILED_REDACTED", "NOT_APPLICABLE_PROXY", "NOT_ATTEMPTED"}:
        raise CurrentProductionSshTransportDiagnosticError("name resolution state is invalid")
    if facts.get("tcp_connectivity") not in {"PASS", *TCP_FAILURE_STATES, "NOT_APPLICABLE_PROXY", "NOT_ATTEMPTED"}:
        raise CurrentProductionSshTransportDiagnosticError("TCP state is invalid")
    if facts.get("ssh_authentication") not in {"PASS", *SSH_FAILURE_STATES, "NOT_ATTEMPTED"}:
        raise CurrentProductionSshTransportDiagnosticError("SSH authentication state is invalid")
    if facts.get("noninteractive_sudo") not in {"PASS", "UNAVAILABLE_REDACTED", "NOT_ATTEMPTED"}:
        raise CurrentProductionSshTransportDiagnosticError("sudo state is invalid")
    _validate_terminal_facts(facts)


def _transport_state(facts: Mapping[str, Any]) -> str:
    if facts["ssh_config_state"] != "RESOLVED":
        return "SSH_CONFIG_UNAVAILABLE"
    if facts["route"] == "DIRECT" and facts["name_resolution"] != "PASS":
        return "SSH_NAME_RESOLUTION_UNAVAILABLE"
    if facts["route"] == "DIRECT" and facts["tcp_connectivity"] != "PASS":
        return "SSH_TCP_%s" % facts["tcp_connectivity"]
    if facts["ssh_authentication"] != "PASS":
        return "SSH_%s" % facts["ssh_authentication"]
    if facts["noninteractive_sudo"] != "PASS":
        return "SSH_NONINTERACTIVE_SUDO_UNAVAILABLE"
    return "SSH_TRANSPORT_READY"


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    diagnosed = facts["ssh_config_state"] == "RESOLVED"
    ready = diagnosed and facts["ssh_authentication"] == "PASS" and facts["noninteractive_sudo"] == "PASS"
    checks = [
        {"id": "SSH_CONFIG_RESOLVED", "passed": diagnosed},
        {"id": "SSH_ROUTE_CLASSIFIED", "passed": facts["route"] in ROUTES},
        {"id": "SSH_PROBE_SEQUENCE_COHERENT", "passed": True},
        {"id": "SSH_TRANSPORT_READY", "passed": ready},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS if diagnosed else FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_SSH_TRANSPORT_READY_SEPARATE_CONFIG_SEMANTIC_PREFLIGHT_REQUIRED" if ready else "CURRENT_PRODUCTION_SSH_TRANSPORT_NOT_READY_NO_REMOTE_MUTATION_AUTHORIZED",
        "transport_diagnosed": diagnosed,
        "transport_ready": ready,
        "core_start_authorized": False,
        "transport_state": _transport_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not isinstance(result["transport_diagnosed"], bool) or not isinstance(result["transport_ready"], bool) or result["core_start_authorized"] is not False:
        raise CurrentProductionSshTransportDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionSshTransportDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "transport_diagnosed": result["transport_diagnosed"],
        "transport_ready": result["transport_ready"],
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
        "decision": "CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "transport_diagnosed": False,
        "transport_ready": False,
        "core_start_authorized": False,
        "transport_state": "SSH_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_SSH_TRANSPORT_DIAGNOSTIC_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.facts))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionSshTransportDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
