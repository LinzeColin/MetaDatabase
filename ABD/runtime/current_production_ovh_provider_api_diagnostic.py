#!/usr/bin/env python3
"""Evaluate one redacted current-production OVH provider API diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC"
ACCESS_STATES = {
    "QUERY_PASS",
    "CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED",
    "TARGET_MAPPING_UNAVAILABLE_REDACTED",
    "ACCESS_DENIED_REDACTED",
    "REQUEST_FAILED_REDACTED",
    "RESPONSE_INVALID_REDACTED",
}
PRESENCE_STATES = {"PRESENT", "ABSENT", "UNKNOWN", "NOT_OBSERVED"}
POWER_STATES = {"POWERED_ON", "POWERED_OFF", "UNKNOWN", "NOT_OBSERVED"}
NETWORK_STATES = {"NETWORK_READY", "NETWORK_DEGRADED", "UNKNOWN", "NOT_OBSERVED"}


class CurrentProductionOvhProviderApiDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted provider fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhProviderApiDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhProviderApiDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhProviderApiDiagnosticError) as exc:
        raise CurrentProductionOvhProviderApiDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH provider API diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH provider API facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhProviderApiDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhProviderApiDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-PROVIDER-API-DIAGNOSTIC-001":
        raise CurrentProductionOvhProviderApiDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhProviderApiDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhProviderApiDiagnosticError("diagnostic must remain read-only")
    expected = {
        "allowed_provider_api_access": [
            "QUERY_PASS",
            "CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED",
            "TARGET_MAPPING_UNAVAILABLE_REDACTED",
            "ACCESS_DENIED_REDACTED",
            "REQUEST_FAILED_REDACTED",
            "RESPONSE_INVALID_REDACTED",
        ],
        "allowed_resource_presence": ["PRESENT", "ABSENT", "UNKNOWN", "NOT_OBSERVED"],
        "allowed_power_states": ["POWERED_ON", "POWERED_OFF", "UNKNOWN", "NOT_OBSERVED"],
        "allowed_network_states": ["NETWORK_READY", "NETWORK_DEGRADED", "UNKNOWN", "NOT_OBSERVED"],
        "maximum_provider_api_requests": 1,
        "allowed_provider_api_methods": ["GET"],
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhProviderApiDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "protected_noninteractive_credential_source_permitted": True,
        "credential_material_used_in_memory_only": True,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "raw_provider_response_emitted_or_persisted": False,
        "browser_login_submitted": False,
        "provider_resource_created_deleted_rebuilt_or_restarted": False,
        "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionOvhProviderApiDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC_ONLY_NOT_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhProviderApiDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhProviderApiDiagnosticError("rollback boundary is not exact")


def _not_observed(facts: Mapping[str, Any]) -> bool:
    return all(facts[field] == "NOT_OBSERVED" for field in ("resource_presence", "power_state", "network_state"))


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "protected_credential_state",
        "current_production_target_state",
        "provider_api_access",
        "provider_api_requests",
        "resource_presence",
        "power_state",
        "network_state",
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "raw_provider_response_emitted_or_persisted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionOvhProviderApiDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC":
        raise CurrentProductionOvhProviderApiDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhProviderApiDiagnosticError("facts observation date is invalid") from exc
    if facts.get("protected_credential_state") not in {"AVAILABLE_IN_MEMORY", "UNAVAILABLE_REDACTED"}:
        raise CurrentProductionOvhProviderApiDiagnosticError("credential state is invalid")
    if facts.get("current_production_target_state") not in {"RESOLVED_IN_MEMORY", "UNAVAILABLE_REDACTED"}:
        raise CurrentProductionOvhProviderApiDiagnosticError("target state is invalid")
    if facts.get("provider_api_access") not in ACCESS_STATES:
        raise CurrentProductionOvhProviderApiDiagnosticError("provider API access state is invalid")
    if type(facts.get("provider_api_requests")) is not int or facts["provider_api_requests"] not in {0, 1}:
        raise CurrentProductionOvhProviderApiDiagnosticError("provider API request count is invalid")
    if facts.get("resource_presence") not in PRESENCE_STATES or facts.get("power_state") not in POWER_STATES or facts.get("network_state") not in NETWORK_STATES:
        raise CurrentProductionOvhProviderApiDiagnosticError("resource state is invalid")
    for field in (
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "raw_provider_response_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionOvhProviderApiDiagnosticError("redaction boundary is invalid")

    access = facts["provider_api_access"]
    if access == "QUERY_PASS":
        if facts["protected_credential_state"] != "AVAILABLE_IN_MEMORY" or facts["current_production_target_state"] != "RESOLVED_IN_MEMORY" or facts["provider_api_requests"] != 1 or _not_observed(facts):
            raise CurrentProductionOvhProviderApiDiagnosticError("successful provider query facts are inconsistent")
    elif access == "CREDENTIAL_SOURCE_UNAVAILABLE_REDACTED":
        if facts["protected_credential_state"] != "UNAVAILABLE_REDACTED" or facts["provider_api_requests"] != 0 or not _not_observed(facts):
            raise CurrentProductionOvhProviderApiDiagnosticError("unavailable credential facts are inconsistent")
    elif access == "TARGET_MAPPING_UNAVAILABLE_REDACTED":
        if facts["protected_credential_state"] != "AVAILABLE_IN_MEMORY" or facts["current_production_target_state"] != "UNAVAILABLE_REDACTED" or facts["provider_api_requests"] != 0 or not _not_observed(facts):
            raise CurrentProductionOvhProviderApiDiagnosticError("unavailable target facts are inconsistent")
    else:
        if facts["protected_credential_state"] != "AVAILABLE_IN_MEMORY" or facts["current_production_target_state"] != "RESOLVED_IN_MEMORY" or facts["provider_api_requests"] != 1 or not _not_observed(facts):
            raise CurrentProductionOvhProviderApiDiagnosticError("failed provider request facts are inconsistent")


def _provider_api_state(facts: Mapping[str, Any]) -> str:
    if facts["provider_api_access"] != "QUERY_PASS":
        return str(facts["provider_api_access"])
    if facts["resource_presence"] != "PRESENT":
        return "OVH_RESOURCE_%s" % facts["resource_presence"]
    if facts["power_state"] != "POWERED_ON":
        return "OVH_%s" % facts["power_state"]
    if facts["network_state"] != "NETWORK_READY":
        return "OVH_%s" % facts["network_state"]
    return "OVH_PROVIDER_API_READY"


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    resource_observed = facts["provider_api_access"] == "QUERY_PASS"
    ready = resource_observed and facts["resource_presence"] == "PRESENT" and facts["power_state"] == "POWERED_ON" and facts["network_state"] == "NETWORK_READY"
    checks = [
        {"id": "OVH_PROVIDER_API_DIAGNOSTIC_COMPLETED", "passed": True},
        {"id": "OVH_PROVIDER_RESOURCE_STATE_OBSERVED", "passed": resource_observed},
        {"id": "OVH_PROVIDER_API_READY", "passed": ready},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "OVH_PROVIDER_API_READY_SEPARATE_SSH_TRANSPORT_RETRY_REQUIRED" if ready else "OVH_PROVIDER_API_ACCESS_OR_RESOURCE_NOT_READY_NO_MUTATION_AUTHORIZED",
        "provider_api_diagnosed": True,
        "resource_state_observed": resource_observed,
        "provider_api_ready": ready,
        "core_start_authorized": False,
        "provider_api_state": _provider_api_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("provider_api_diagnosed", "resource_state_observed", "provider_api_ready")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhProviderApiDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhProviderApiDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "provider_api_diagnosed": result["provider_api_diagnosed"],
        "resource_state_observed": result["resource_state_observed"],
        "provider_api_ready": result["provider_api_ready"],
        "core_start_authorized": False,
        "provider_api_state": result["provider_api_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "provider_api_diagnosed": False,
        "resource_state_observed": False,
        "provider_api_ready": False,
        "core_start_authorized": False,
        "provider_api_state": "OVH_PROVIDER_API_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_PROVIDER_API_DIAGNOSTIC_INPUT_FAILED"],
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhProviderApiDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
