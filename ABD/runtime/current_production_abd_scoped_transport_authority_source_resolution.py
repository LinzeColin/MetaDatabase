#!/usr/bin/env python3
"""Adjudicate redacted current ABD transport-authority source observations."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION"
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
PROTECTED_STATES = {
    "NO_QUALIFYING_AUTH_KEYSET_OBSERVED_REDACTED",
    "QUALIFIED_ABD_SCOPED_CURRENT_AUTHORITY_SOURCE_RESOLVED_IN_MEMORY",
    "NOT_ATTEMPTED",
}
GITHUB_STATES = {
    "NO_ABD_SCOPED_SOURCE_OBSERVED_REDACTED",
    "QUALIFIED_ABD_SCOPED_CURRENT_AUTHORITY_SOURCE_RESOLVED_IN_MEMORY",
    "NOT_ATTEMPTED",
}
BROWSER_STATES = {
    "MANAGEMENT_SURFACE_UNAVAILABLE_REDACTED",
    "QUALIFIED_ABD_SCOPED_CURRENT_AUTHORITY_SOURCE_RESOLVED_IN_MEMORY",
    "NOT_ATTEMPTED",
}
QUALIFIED_STATE = "QUALIFIED_ABD_SCOPED_CURRENT_AUTHORITY_SOURCE_RESOLVED_IN_MEMORY"
AUTHORITY_STATES = {"RESOLVED_IN_MEMORY", "NOT_PROVEN_REDACTED"}


class CurrentProductionAbdScopedTransportAuthoritySourceResolutionError(ValueError):
    """Raised when a source-resolution input breaks the read-only contract."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionAbdScopedTransportAuthoritySourceResolutionError) as exc:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "ABD-scoped transport-authority source-resolution contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted ABD-scoped transport-authority source observations")


def _expected_contract() -> dict[str, Any]:
    return {
        "required_authority_properties": [
            "ABD_SCOPE",
            "SAME_UTC_DATE",
            "NONINTERACTIVE_BOUNDARY",
            "CONTROLLED_TARGET_AUTHORITY",
        ],
        "source_surfaces": [
            "PROTECTED_EXACT_OVH_AUTH_KEYSET",
            "GITHUB_REPOSITORY_VARIABLE_NAMES",
            "GITHUB_REPOSITORY_ENVIRONMENT_NAMES",
            "OVH_EXISTING_BROWSER_SESSION",
        ],
        "maximum_github_api_requests": 2,
        "maximum_browser_navigation_attempts": 1,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }


def _contract_boundary() -> dict[str, Any]:
    return {
        "owner_task_authorization_observed": True,
        "protected_root_read_only": True,
        "protected_exact_json_keysets_read_in_memory_only": True,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "github_variable_or_environment_values_read_emitted_or_persisted": False,
        "browser_existing_session_state_only": True,
        "browser_login_submitted": False,
        "provider_api_request_sent": False,
        "ssh_connection_attempted": False,
        "host_runtime_or_configuration_changed": False,
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }


def validate_contract(contract: Mapping[str, Any]) -> None:
    if set(contract) != CONTRACT_FIELDS:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-ABD-SCOPED-CURRENT-TRANSPORT-AUTHORITY-SOURCE-RESOLUTION-001":
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract identity is invalid")
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION_READ_ONLY":
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract status is invalid")
    if _object(contract.get("expected"), "contract expected") != _expected_contract():
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract expectations are invalid")
    if _object(contract.get("source_boundary"), "contract boundary") != _contract_boundary():
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract boundary is invalid")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_ABD_SCOPED_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION_ONLY_NOT_TARGET_VALUE_DISCLOSURE_PROVIDER_RESOURCE_STATE_SSH_RETRY_HOST_METADATA_READ_REPAIR_DEPLOYMENT_CORE_START_CLOUDFLARE_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract claim boundary is invalid")
    if _object(contract.get("rollback"), "contract rollback") != {
        "action": "NO_PROVIDER_BROWSER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("contract rollback is invalid")


def _qualified_sources(facts: Mapping[str, Any]) -> int:
    return sum(
        facts[field] == QUALIFIED_STATE
        for field in (
            "protected_exact_ovh_auth_keyset_state",
            "github_variable_scope_state",
            "github_environment_scope_state",
            "ovh_existing_browser_session_state",
        )
    )


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "owner_task_authorization_observed",
        "protected_exact_ovh_auth_keyset_state",
        "github_variable_scope_state",
        "github_environment_scope_state",
        "ovh_existing_browser_session_state",
        "qualified_authority_source_state",
        "source_authority_ready",
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "github_variable_or_environment_values_read_emitted_or_persisted",
        "browser_login_submitted",
        "provider_api_requests",
        "ssh_connections_attempted",
        "github_api_requests",
        "browser_navigation_attempts",
    }
    if set(facts) != required:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION":
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("facts identity is invalid")
    try:
        observed_on = date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("facts observation date is invalid") from exc
    if observed_on != _today_utc():
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("facts observation date is not current UTC")
    if facts.get("owner_task_authorization_observed") is not True:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("owner task authorization state is invalid")
    if facts.get("protected_exact_ovh_auth_keyset_state") not in PROTECTED_STATES:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("protected source state is invalid")
    if facts.get("github_variable_scope_state") not in GITHUB_STATES or facts.get("github_environment_scope_state") not in GITHUB_STATES:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("GitHub source state is invalid")
    if facts.get("ovh_existing_browser_session_state") not in BROWSER_STATES:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("browser source state is invalid")
    if facts.get("qualified_authority_source_state") not in AUTHORITY_STATES or type(facts.get("source_authority_ready")) is not bool:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("authority state is invalid")
    for field in (
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "github_variable_or_environment_values_read_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("redaction boundary is invalid")
    exact_counts = {
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    for field, expected in exact_counts.items():
        if type(facts.get(field)) is not int or facts[field] != expected:
            raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("outbound operation count is invalid")
    if type(facts.get("github_api_requests")) is not int or not 0 <= facts["github_api_requests"] <= 2:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("GitHub request count is invalid")
    if type(facts.get("browser_navigation_attempts")) is not int or not 0 <= facts["browser_navigation_attempts"] <= 1:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("browser navigation count is invalid")
    source_count = _qualified_sources(facts)
    expected_ready = source_count > 0
    if facts["source_authority_ready"] != expected_ready:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("authority readiness is inconsistent")
    expected_state = "RESOLVED_IN_MEMORY" if expected_ready else "NOT_PROVEN_REDACTED"
    if facts["qualified_authority_source_state"] != expected_state:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("qualified authority state is inconsistent")
    if facts["ovh_existing_browser_session_state"] == "NOT_ATTEMPTED" and facts["browser_navigation_attempts"] != 0:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("unattempted browser source is inconsistent")
    if facts["ovh_existing_browser_session_state"] != "NOT_ATTEMPTED" and facts["browser_navigation_attempts"] != 1:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("observed browser source is inconsistent")


def evaluate_source_resolution(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    completed = all(
        facts[field] != "NOT_ATTEMPTED"
        for field in (
            "protected_exact_ovh_auth_keyset_state",
            "github_variable_scope_state",
            "github_environment_scope_state",
            "ovh_existing_browser_session_state",
        )
    )
    ready = facts["source_authority_ready"]
    checks = [
        {"id": "OWNER_TASK_AUTHORIZATION_OBSERVED", "passed": facts["owner_task_authorization_observed"] is True},
        {"id": "ALL_DEFINED_SOURCE_SURFACES_OBSERVED", "passed": completed},
        {"id": "ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_READY", "passed": ready},
        {"id": "PROVIDER_AND_SSH_ACTIONS_NOT_ATTEMPTED", "passed": facts["provider_api_requests"] == 0 and facts["ssh_connections_attempted"] == 0},
    ]
    return {
        "status": PASS_STATUS if completed else FAIL_STATUS,
        "decision": "ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_READY_FOR_SEPARATE_TARGET_MAPPING_PHASE" if ready else "ABD_SCOPED_CURRENT_TRANSPORT_AUTHORITY_SOURCE_NOT_PROVEN_NO_TARGET_OR_TRANSPORT_ACTION_AUTHORIZED",
        "source_resolution_completed": completed,
        "source_authority_ready": ready,
        "qualified_authority_source_state": facts["qualified_authority_source_state"],
        "provider_api_requests": facts["provider_api_requests"],
        "ssh_connections_attempted": facts["ssh_connections_attempted"],
        "target_mapping_authorized": False,
        "transport_retry_authorized": False,
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_source_resolution(contract, facts)
    required = {
        "status",
        "decision",
        "source_resolution_completed",
        "source_authority_ready",
        "qualified_authority_source_state",
        "provider_api_requests",
        "ssh_connections_attempted",
        "target_mapping_authorized",
        "transport_retry_authorized",
        "current_host_metadata_collection_authorized",
        "repair_execution_authorized",
        "core_start_authorized",
        "checks",
        "failure_codes",
    }
    if set(result) != required:
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("source-resolution result field set is not exact")
    if any(result[field] is not False for field in (
        "target_mapping_authorized",
        "transport_retry_authorized",
        "current_host_metadata_collection_authorized",
        "repair_execution_authorized",
        "core_start_authorized",
    )):
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("source-resolution authorization state is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionAbdScopedTransportAuthoritySourceResolutionError("source-resolution checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "source_resolution_completed": result["source_resolution_completed"],
        "source_authority_ready": result["source_authority_ready"],
        "qualified_authority_source_state": result["qualified_authority_source_state"],
        "source_surfaces": {
            "protected_exact_ovh_auth_keyset_state": facts["protected_exact_ovh_auth_keyset_state"],
            "github_variable_scope_state": facts["github_variable_scope_state"],
            "github_environment_scope_state": facts["github_environment_scope_state"],
            "ovh_existing_browser_session_state": facts["ovh_existing_browser_session_state"],
        },
        "github_api_requests": facts["github_api_requests"],
        "browser_navigation_attempts": facts["browser_navigation_attempts"],
        "provider_api_requests": result["provider_api_requests"],
        "ssh_connections_attempted": result["ssh_connections_attempted"],
        "target_mapping_authorized": False,
        "transport_retry_authorized": False,
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
        "decision": "CURRENT_PRODUCTION_ABD_SCOPED_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION_INPUT_FAILED_CLOSED",
        "observed_on": safe_observed_on,
        "source_resolution_completed": False,
        "source_authority_ready": False,
        "qualified_authority_source_state": "NOT_PROVEN_REDACTED",
        "target_mapping_authorized": False,
        "transport_retry_authorized": False,
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_ABD_SCOPED_TRANSPORT_AUTHORITY_SOURCE_RESOLUTION_INPUT_FAILED"],
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
    except (
        CurrentProductionAbdScopedTransportAuthoritySourceResolutionError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        receipt = _failure_receipt(exc, "INVALID")
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
