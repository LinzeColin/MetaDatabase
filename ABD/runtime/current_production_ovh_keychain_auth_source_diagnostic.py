#!/usr/bin/env python3
"""Evaluate one redacted macOS Keychain OVH authorization-source diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC"
KEYCHAIN_ACCESS_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED"}
SOURCE_STATES = {
    "CANONICAL_SOURCE_RESOLVED_IN_MEMORY",
    "CANONICAL_SOURCE_UNSTRUCTURED_REDACTED",
    "PROVIDER_KEYCHAIN_ENTRY_PRESENT_UNSCOPED_REDACTED",
    "CANONICAL_SOURCE_NOT_RESOLVED_REDACTED",
    "KEYCHAIN_UNAVAILABLE_REDACTED",
}


class CurrentProductionOvhKeychainAuthSourceDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted Keychain fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhKeychainAuthSourceDiagnosticError) as exc:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH Keychain authorization-source diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH Keychain authorization-source facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-KEYCHAIN-AUTH-SOURCE-DIAGNOSTIC-001":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("diagnostic must remain read-only")
    expected = {
        "canonical_generic_password_services": [
            "ABD_OVH_CURRENT_PRODUCTION_AUTH_TARGET",
            "ABD_OVH_CURRENT_PRODUCTION_API",
            "OVH_CURRENT_PRODUCTION_AUTH_TARGET",
            "OVH_CURRENT_PRODUCTION_API",
        ],
        "provider_internet_password_hosts": ["api.ovh.com", "eu.api.ovh.com", "sg.api.ovh.com"],
        "maximum_keychain_command_timeout_seconds": 3,
        "provider_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "keychain_metadata_read_in_memory_only": True,
        "canonical_structured_credential_read_in_memory_only": True,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "browser_login_submitted": False,
        "provider_api_request_sent": False,
        "provider_resource_created_deleted_rebuilt_or_restarted": False,
        "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC_ONLY_NOT_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_KEYCHAIN_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "keychain_access",
        "auth_target_source_state",
        "auth_target_source_ready",
        "provider_api_requests",
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("facts observation date is invalid") from exc
    if facts.get("keychain_access") not in KEYCHAIN_ACCESS_STATES:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("Keychain access state is invalid")
    if facts.get("auth_target_source_state") not in SOURCE_STATES:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("authorization source state is invalid")
    if type(facts.get("auth_target_source_ready")) is not bool:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("authorization source readiness is invalid")
    if type(facts.get("provider_api_requests")) is not int or facts["provider_api_requests"] != 0:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("provider API request count is invalid")
    for field in (
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("redaction boundary is invalid")
    source_state = facts["auth_target_source_state"]
    if facts["keychain_access"] == "UNAVAILABLE_REDACTED":
        if source_state != "KEYCHAIN_UNAVAILABLE_REDACTED" or facts["auth_target_source_ready"] is not False:
            raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("unavailable Keychain facts are inconsistent")
    elif source_state == "KEYCHAIN_UNAVAILABLE_REDACTED":
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("available Keychain facts are inconsistent")
    elif facts["auth_target_source_ready"] != (source_state == "CANONICAL_SOURCE_RESOLVED_IN_MEMORY"):
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("authorization source facts are inconsistent")


def _source_state(facts: Mapping[str, Any]) -> str:
    if facts["auth_target_source_ready"]:
        return "OVH_KEYCHAIN_AUTH_TARGET_READY_FOR_SEPARATE_GET_PHASE"
    return "OVH_KEYCHAIN_%s" % facts["auth_target_source_state"]


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["auth_target_source_ready"])
    checks = [
        {"id": "OVH_KEYCHAIN_DIAGNOSTIC_COMPLETED", "passed": True},
        {"id": "OVH_KEYCHAIN_AUTH_TARGET_SOURCE_READY", "passed": ready},
        {"id": "OVH_PROVIDER_API_REQUEST_NOT_SENT", "passed": facts["provider_api_requests"] == 0},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "OVH_KEYCHAIN_AUTH_TARGET_READY_SEPARATE_PROVIDER_API_GET_REQUIRED" if ready else "OVH_KEYCHAIN_AUTH_TARGET_NOT_READY_NO_PROVIDER_REQUEST_OR_MUTATION_AUTHORIZED",
        "keychain_diagnosed": True,
        "auth_target_source_ready": ready,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "keychain_auth_source_state": _source_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("keychain_diagnosed", "auth_target_source_ready", "provider_api_request_not_sent")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhKeychainAuthSourceDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "keychain_diagnosed": result["keychain_diagnosed"],
        "auth_target_source_ready": result["auth_target_source_ready"],
        "provider_api_request_not_sent": result["provider_api_request_not_sent"],
        "core_start_authorized": False,
        "keychain_auth_source_state": result["keychain_auth_source_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "keychain_diagnosed": False,
        "auth_target_source_ready": False,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "keychain_auth_source_state": "OVH_KEYCHAIN_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_KEYCHAIN_AUTH_SOURCE_DIAGNOSTIC_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "keychain_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.facts))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhKeychainAuthSourceDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
