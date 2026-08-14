#!/usr/bin/env python3
"""Evaluate one redacted OVH management-plane diagnostic for ABD."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC"
LOGIN_STATES = {"EXISTING_SESSION", "LOGIN_REQUIRED", "UNAVAILABLE"}
ACCESS_STATES = {"ACCESS_AVAILABLE", "ACCESS_UNAVAILABLE_WITHOUT_CREDENTIAL_REUSE", "BROWSER_UNAVAILABLE"}
PRESENCE_STATES = {"PRESENT", "ABSENT", "UNKNOWN", "NOT_OBSERVED"}
POWER_STATES = {"POWERED_ON", "POWERED_OFF", "UNKNOWN", "NOT_OBSERVED"}
NETWORK_STATES = {"NETWORK_READY", "NETWORK_DEGRADED", "UNKNOWN", "NOT_OBSERVED"}


class CurrentProductionOvhManagementPlaneDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted provider fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhManagementPlaneDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhManagementPlaneDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhManagementPlaneDiagnosticError) as exc:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH management-plane diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH management-plane facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhManagementPlaneDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-MANAGEMENT-PLANE-DIAGNOSTIC-001":
        raise CurrentProductionOvhManagementPlaneDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhManagementPlaneDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhManagementPlaneDiagnosticError("diagnostic must remain read-only")
    expected = {
        "browser_surfaces": ["IN_APP", "CHROME"],
        "allowed_management_plane_access": ["ACCESS_AVAILABLE", "ACCESS_UNAVAILABLE_WITHOUT_CREDENTIAL_REUSE", "BROWSER_UNAVAILABLE"],
        "allowed_resource_presence": ["PRESENT", "ABSENT", "UNKNOWN", "NOT_OBSERVED"],
        "allowed_power_states": ["POWERED_ON", "POWERED_OFF", "UNKNOWN", "NOT_OBSERVED"],
        "allowed_network_states": ["NETWORK_READY", "NETWORK_DEGRADED", "UNKNOWN", "NOT_OBSERVED"],
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "existing_browser_sessions_observed": True,
        "credential_material_directly_read_or_entered": False,
        "api_token_directly_read_or_inspected": False,
        "account_identifier_emitted_or_persisted": False,
        "address_or_resource_identifier_emitted_or_persisted": False,
        "billing_database_or_configuration_read": False,
        "provider_resource_created_deleted_rebuilt_or_restarted": False,
        "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC_ONLY_NOT_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhManagementPlaneDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {"schema_version", "observation_type", "observed_on", "in_app_login_state", "chrome_login_state", "management_plane_access", "resource_presence", "power_state", "network_state", "credential_material_directly_read_or_entered"}
    if set(facts) != required:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC":
        raise CurrentProductionOvhManagementPlaneDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("facts observation date is invalid") from exc
    if facts.get("in_app_login_state") not in LOGIN_STATES or facts.get("chrome_login_state") not in LOGIN_STATES:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("browser login state is invalid")
    if facts.get("management_plane_access") not in ACCESS_STATES:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("management-plane access state is invalid")
    if facts.get("resource_presence") not in PRESENCE_STATES or facts.get("power_state") not in POWER_STATES or facts.get("network_state") not in NETWORK_STATES:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("resource state is invalid")
    if facts.get("credential_material_directly_read_or_entered") is not False:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("credential boundary is invalid")
    access = facts["management_plane_access"]
    resource_fields = ("resource_presence", "power_state", "network_state")
    if access == "ACCESS_AVAILABLE":
        if "EXISTING_SESSION" not in {facts["in_app_login_state"], facts["chrome_login_state"]} or any(facts[field] == "NOT_OBSERVED" for field in resource_fields):
            raise CurrentProductionOvhManagementPlaneDiagnosticError("available management-plane facts are inconsistent")
    elif access == "ACCESS_UNAVAILABLE_WITHOUT_CREDENTIAL_REUSE":
        if {facts["in_app_login_state"], facts["chrome_login_state"]} != {"LOGIN_REQUIRED"} or any(facts[field] != "NOT_OBSERVED" for field in resource_fields):
            raise CurrentProductionOvhManagementPlaneDiagnosticError("credential-free access facts are inconsistent")
    else:
        if {facts["in_app_login_state"], facts["chrome_login_state"]} != {"UNAVAILABLE"} or any(facts[field] != "NOT_OBSERVED" for field in resource_fields):
            raise CurrentProductionOvhManagementPlaneDiagnosticError("browser unavailable facts are inconsistent")


def _management_plane_state(facts: Mapping[str, Any]) -> str:
    if facts["management_plane_access"] != "ACCESS_AVAILABLE":
        return str(facts["management_plane_access"])
    if facts["resource_presence"] != "PRESENT":
        return "OVH_RESOURCE_%s" % facts["resource_presence"]
    if facts["power_state"] != "POWERED_ON":
        return "OVH_%s" % facts["power_state"]
    if facts["network_state"] != "NETWORK_READY":
        return "OVH_%s" % facts["network_state"]
    return "OVH_MANAGEMENT_PLANE_READY"


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    access_observed = True
    resource_observed = facts["management_plane_access"] == "ACCESS_AVAILABLE"
    ready = resource_observed and facts["resource_presence"] == "PRESENT" and facts["power_state"] == "POWERED_ON" and facts["network_state"] == "NETWORK_READY"
    checks = [
        {"id": "OVH_MANAGEMENT_PLANE_ACCESS_OBSERVED", "passed": access_observed},
        {"id": "OVH_RESOURCE_STATE_OBSERVED", "passed": resource_observed},
        {"id": "OVH_MANAGEMENT_PLANE_READY", "passed": ready},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "OVH_MANAGEMENT_PLANE_READY_SEPARATE_SSH_TRANSPORT_RETRY_REQUIRED" if ready else "OVH_MANAGEMENT_PLANE_ACCESS_OR_RESOURCE_NOT_READY_NO_MUTATION_AUTHORIZED",
        "management_plane_access_observed": access_observed,
        "resource_state_observed": resource_observed,
        "management_plane_ready": ready,
        "core_start_authorized": False,
        "management_plane_state": _management_plane_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("management_plane_access_observed", "resource_state_observed", "management_plane_ready")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhManagementPlaneDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhManagementPlaneDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "management_plane_access_observed": result["management_plane_access_observed"],
        "resource_state_observed": result["resource_state_observed"],
        "management_plane_ready": result["management_plane_ready"],
        "core_start_authorized": False,
        "management_plane_state": result["management_plane_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "management_plane_access_observed": False,
        "resource_state_observed": False,
        "management_plane_ready": False,
        "core_start_authorized": False,
        "management_plane_state": "OVH_MANAGEMENT_PLANE_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.facts))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhManagementPlaneDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
