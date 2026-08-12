#!/usr/bin/env python3
"""Evaluate one redacted process and user-launchd OVH authorization-source diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC"
PROCESS_SOURCE_STATES = {"COMPLETE_LEGACY_AUTH_TARGET_FIELDS", "NO_COMPLETE_LEGACY_GROUP_REDACTED"}
LAUNCHD_SOURCE_STATES = {"COMPLETE_LEGACY_AUTH_TARGET_FIELDS", "NO_COMPLETE_LEGACY_GROUP_REDACTED", "UNAVAILABLE_REDACTED"}


class CurrentProductionOvhProcessAuthSourceDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted process-source fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhProcessAuthSourceDiagnosticError) as exc:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH process authorization-source diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH process authorization-source facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-PROCESS-AUTH-SOURCE-DIAGNOSTIC-001":
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("diagnostic must remain read-only")
    expected = {
        "legacy_auth_target_field_groups": ["OVH_STANDARD", "ABD_OVH_SCOPED"],
        "field_presence_planes": ["CURRENT_PROCESS", "USER_LAUNCHD"],
        "maximum_launchd_command_timeout_seconds": 3,
        "provider_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "current_process_environment_values_emitted_or_persisted": False,
        "user_launchd_environment_values_emitted_or_persisted": False,
        "only_fixed_field_presence_checked": True,
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
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC_ONLY_NOT_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROCESS_LAUNCHD_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "current_process_source_state",
        "user_launchd_source_state",
        "auth_target_source_ready",
        "provider_api_requests",
        "environment_value_emitted_or_persisted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC":
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("facts observation date is invalid") from exc
    if facts.get("current_process_source_state") not in PROCESS_SOURCE_STATES:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("current process source state is invalid")
    if facts.get("user_launchd_source_state") not in LAUNCHD_SOURCE_STATES:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("user launchd source state is invalid")
    if type(facts.get("auth_target_source_ready")) is not bool:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("authorization source readiness is invalid")
    if type(facts.get("provider_api_requests")) is not int or facts["provider_api_requests"] != 0:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("provider API request count is invalid")
    if facts.get("environment_value_emitted_or_persisted") is not False or facts.get("browser_login_submitted") is not False:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("redaction boundary is invalid")
    complete = "COMPLETE_LEGACY_AUTH_TARGET_FIELDS"
    if facts["auth_target_source_ready"] != (complete in {facts["current_process_source_state"], facts["user_launchd_source_state"]}):
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("authorization source facts are inconsistent")


def _source_state(facts: Mapping[str, Any]) -> str:
    if facts["auth_target_source_ready"]:
        return "OVH_PROCESS_OR_LAUNCHD_AUTH_TARGET_READY_FOR_SEPARATE_GET_PHASE"
    if facts["user_launchd_source_state"] == "UNAVAILABLE_REDACTED":
        return "OVH_PROCESS_NO_COMPLETE_AUTH_TARGET_USER_LAUNCHD_UNAVAILABLE"
    return "OVH_PROCESS_AND_USER_LAUNCHD_NO_COMPLETE_AUTH_TARGET"


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["auth_target_source_ready"])
    checks = [
        {"id": "OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC_COMPLETED", "passed": True},
        {"id": "OVH_PROCESS_OR_LAUNCHD_AUTH_TARGET_SOURCE_READY", "passed": ready},
        {"id": "OVH_PROVIDER_API_REQUEST_NOT_SENT", "passed": facts["provider_api_requests"] == 0},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "OVH_PROCESS_OR_LAUNCHD_AUTH_TARGET_READY_SEPARATE_PROVIDER_API_GET_REQUIRED" if ready else "OVH_PROCESS_OR_LAUNCHD_AUTH_TARGET_NOT_READY_NO_PROVIDER_REQUEST_OR_MUTATION_AUTHORIZED",
        "process_auth_source_diagnosed": True,
        "auth_target_source_ready": ready,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "process_auth_source_state": _source_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("process_auth_source_diagnosed", "auth_target_source_ready", "provider_api_request_not_sent")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhProcessAuthSourceDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "process_auth_source_diagnosed": result["process_auth_source_diagnosed"],
        "auth_target_source_ready": result["auth_target_source_ready"],
        "provider_api_request_not_sent": result["provider_api_request_not_sent"],
        "core_start_authorized": False,
        "process_auth_source_state": result["process_auth_source_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "process_auth_source_diagnosed": False,
        "auth_target_source_ready": False,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "process_auth_source_state": "OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_PROCESS_AUTH_SOURCE_DIAGNOSTIC_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "process_launchd_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.facts))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhProcessAuthSourceDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
