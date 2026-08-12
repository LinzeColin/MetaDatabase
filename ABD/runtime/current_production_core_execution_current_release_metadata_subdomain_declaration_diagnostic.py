#!/usr/bin/env python3
"""Declare fixed current-release metadata subdomains for one canonical non-ready receipt."""

from __future__ import annotations

import argparse
import json
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

from current_production_core_execution_canonical_nonready_failure_domain_declaration_diagnostic import (
    CHECK_IDENTIFIERS,
    CANONICAL_FIELDS,
    CORE_FAIL_STATUS,
    CORE_PASS_STATUS,
    CORE_RECEIPT_TYPE,
    CORE_SPEC,
    _core_candidate_from_manifest,
)
from current_production_private_redacted_prerequisite_receipt_continuity_attestation import (
    PRIVATE_DOMAIN,
    _private_read,
    _receipt_filename,
    load_private_client,
)


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC"
MAX_PRIVATE_DATABASE_READ_REQUESTS = 2
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
CURRENT_RELEASE_CHECK_IDENTIFIERS = (
    "CURRENT_RELEASE_LINK_MANAGED",
    "CURRENT_RELEASE_COMPOSE_FILE_REGULAR",
    "CURRENT_RELEASE_REBUILD_FILE_REGULAR",
)
CURRENT_RELEASE_SUBDOMAIN = {
    "CURRENT_RELEASE_LINK_MANAGED": "CURRENT_RELEASE_LINK_METADATA_INCOMPLETE_REDACTED",
    "CURRENT_RELEASE_COMPOSE_FILE_REGULAR": "CURRENT_RELEASE_COMPOSE_METADATA_INCOMPLETE_REDACTED",
    "CURRENT_RELEASE_REBUILD_FILE_REGULAR": "CURRENT_RELEASE_REBUILD_METADATA_INCOMPLETE_REDACTED",
}
CURRENT_RELEASE_SUBDOMAINS = frozenset(CURRENT_RELEASE_SUBDOMAIN.values())
SUBDOMAIN_STATES = {
    "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
    "PRIVATE_MANIFEST_REJECTED_REDACTED",
    "CANDIDATE_NOT_OBSERVED_REDACTED",
    "CANDIDATE_AMBIGUOUS_REDACTED",
    "CANDIDATE_REJECTED_REDACTED",
    "REDACTED_RECEIPT_UNAVAILABLE_REDACTED",
    "CANONICAL_READY_NOT_APPLICABLE_REDACTED",
    "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED",
    "CANONICAL_NONREADY_CURRENT_RELEASE_FAILURE_NOT_OBSERVED_REDACTED",
    "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED",
}


class CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError(ValueError):
    """Raised when the constrained current-release declaration is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError) as exc:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "current-release metadata subdomain declaration diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "current-release metadata subdomain declaration facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-CURRENT-RELEASE-METADATA-SUBDOMAIN-DECLARATION-DIAGNOSTIC-001":
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("diagnostic must remain read-only")
    expected = {
        "private_area": "Private-MetaDatabase",
        "private_domain": PRIVATE_DOMAIN,
        "core_execution_receipt_type": CORE_RECEIPT_TYPE,
        "maximum_private_database_read_requests": MAX_PRIVATE_DATABASE_READ_REQUESTS,
        "canonical_current_receipt_field_set": sorted(CANONICAL_FIELDS),
        "canonical_check_identifiers": list(CHECK_IDENTIFIERS),
        "current_release_check_identifiers": list(CURRENT_RELEASE_CHECK_IDENTIFIERS),
        "current_release_metadata_subdomains": sorted(CURRENT_RELEASE_SUBDOMAINS),
        "provider_api_requests": 0,
        "product_github_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "private_database_client_read_only": True,
        "single_private_manifest_metadata_stream_read_in_memory_only": True,
        "at_most_one_current_core_execution_candidate_read_in_memory": True,
        "only_canonical_nonready_schema_status_and_authorization_shape_used_in_memory": True,
        "only_prewhitelisted_nonsecret_check_identifiers_and_boolean_passed_states_used_in_memory": True,
        "only_exact_prewhitelisted_failure_code_shape_used_in_memory": True,
        "private_receipt_check_identifier_or_value_emitted_copied_or_persisted": False,
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
        "product_github_api_request_sent": False,
        "provider_api_request_sent": False,
        "ssh_connection_attempted": False,
        "browser_login_submitted": False,
        "workflow_dispatched_or_pushed": False,
        "provider_resource_network_cloudflare_host_or_service_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_ONLY_NOT_FAILURE_ROOT_CAUSE_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PRIVATE_DATA_PROVIDER_WORKFLOW_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "private_manifest_state",
        "private_manifest_metadata_read_in_memory_only",
        "core_execution_receipt_content_read_in_memory_only",
        "private_database_read_requests",
        "current_release_metadata_subdomain_state",
        "current_release_metadata_subdomains",
        "current_release_metadata_subdomains_declared",
        "private_receipt_check_identifier_or_value_emitted_copied_or_persisted",
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "product_github_api_requests",
        "provider_api_requests",
        "ssh_connections_attempted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC":
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES or facts.get("private_manifest_state") not in {"OBSERVED_IN_MEMORY", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("facts state is invalid")
    if facts.get("current_release_metadata_subdomain_state") not in SUBDOMAIN_STATES or type(facts.get("current_release_metadata_subdomains_declared")) is not bool:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("subdomain declaration state is invalid")
    for field in ("private_manifest_metadata_read_in_memory_only", "core_execution_receipt_content_read_in_memory_only"):
        if type(facts.get(field)) is not bool:
            raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("facts boolean state is invalid")
    if type(facts.get("private_database_read_requests")) is not int or not 0 <= facts["private_database_read_requests"] <= MAX_PRIVATE_DATABASE_READ_REQUESTS:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("private database request count is invalid")
    subdomains = facts.get("current_release_metadata_subdomains")
    if not isinstance(subdomains, list) or any(item not in CURRENT_RELEASE_SUBDOMAINS for item in subdomains) or subdomains != sorted(set(subdomains)):
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("subdomain list is invalid")
    declared = facts["current_release_metadata_subdomain_state"] == "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED"
    if facts["current_release_metadata_subdomains_declared"] is not declared or (declared and not subdomains) or (not declared and subdomains):
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("subdomain declaration is inconsistent")
    for field in (
        "private_receipt_check_identifier_or_value_emitted_copied_or_persisted",
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("redaction boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("outbound operation count is invalid")
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        if facts["private_manifest_state"] != "NOT_ATTEMPTED" or facts["private_database_read_requests"] != 0 or facts["private_manifest_metadata_read_in_memory_only"] or facts["core_execution_receipt_content_read_in_memory_only"]:
            raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("unavailable root facts are inconsistent")
    elif facts["private_manifest_state"] == "OBSERVED_IN_MEMORY":
        if not facts["private_manifest_metadata_read_in_memory_only"] or facts["private_database_read_requests"] < 1:
            raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("observed manifest facts are inconsistent")
    elif facts["private_manifest_metadata_read_in_memory_only"]:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("unavailable manifest facts are inconsistent")
    candidate_states = {
        "REDACTED_RECEIPT_UNAVAILABLE_REDACTED",
        "CANONICAL_READY_NOT_APPLICABLE_REDACTED",
        "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED",
        "CANONICAL_NONREADY_CURRENT_RELEASE_FAILURE_NOT_OBSERVED_REDACTED",
        "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED",
    }
    if facts["current_release_metadata_subdomain_state"] in candidate_states and facts["private_database_read_requests"] != 2:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("candidate-read facts are inconsistent")
    if facts["core_execution_receipt_content_read_in_memory_only"] and facts["private_database_read_requests"] != 2:
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("receipt-read facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "private_manifest_state": "NOT_ATTEMPTED",
        "private_manifest_metadata_read_in_memory_only": False,
        "core_execution_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 0,
        "current_release_metadata_subdomain_state": "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
        "current_release_metadata_subdomains": [],
        "current_release_metadata_subdomains_declared": False,
        "private_receipt_check_identifier_or_value_emitted_copied_or_persisted": False,
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }


def _subdomains_from_receipt(raw: bytes, observed_on: str) -> tuple[str, list[str]]:
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    if not isinstance(receipt, dict) or set(receipt) != CANONICAL_FIELDS:
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    if receipt.get("schema_version") != "1.0.0" or receipt.get("receipt_type") != CORE_RECEIPT_TYPE or not isinstance(receipt.get("decision"), str) or receipt.get("observed_on") != observed_on:
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    if receipt.get("execution_authorized") is not False or type(receipt.get("input_ready")) is not bool or not isinstance(receipt.get("source_boundary"), dict) or not isinstance(receipt.get("claim_boundary"), str):
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    if receipt.get("status") == CORE_PASS_STATUS and receipt["input_ready"] is True:
        return "CANONICAL_READY_NOT_APPLICABLE_REDACTED", []
    if receipt.get("status") != CORE_FAIL_STATUS or receipt["input_ready"] is not False:
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    checks = receipt.get("checks")
    if not isinstance(checks, list) or len(checks) != len(CHECK_IDENTIFIERS):
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    identifiers: list[str] = []
    expected_failure_codes: list[str] = []
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "passed"} or not isinstance(check.get("id"), str) or type(check.get("passed")) is not bool:
            return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
        identifier = check["id"]
        identifiers.append(identifier)
        if not check["passed"]:
            expected_failure_codes.append(identifier)
    if tuple(identifiers) != CHECK_IDENTIFIERS or not expected_failure_codes or receipt.get("failure_codes") != expected_failure_codes:
        return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAIN_REJECTED_REDACTED", []
    failed_current_release = [identifier for identifier in CURRENT_RELEASE_CHECK_IDENTIFIERS if identifier in expected_failure_codes]
    if not failed_current_release:
        return "CANONICAL_NONREADY_CURRENT_RELEASE_FAILURE_NOT_OBSERVED_REDACTED", []
    return "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED", sorted(CURRENT_RELEASE_SUBDOMAIN[identifier] for identifier in failed_current_release)


def discover_current_release_metadata_subdomains(repo_root: Path, client: ModuleType, observed_on: str | None = None) -> dict[str, Any]:
    """Read one manifest and at most one current receipt without exposing it."""

    target_date = observed_on or datetime.now(timezone.utc).date().isoformat()
    facts = _base_facts(target_date)
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    facts["private_database_read_requests"] = 1
    try:
        manifest_raw = _private_read(client, "manifest.jsonl")
    except (RuntimeError, OSError, ValueError, CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError):
        facts["private_manifest_state"] = "UNAVAILABLE_REDACTED"
        return facts
    candidates, valid_manifest, candidate_rejected = _core_candidate_from_manifest(manifest_raw, target_date)
    if not valid_manifest:
        facts["private_manifest_state"] = "REJECTED_REDACTED"
        facts["current_release_metadata_subdomain_state"] = "PRIVATE_MANIFEST_REJECTED_REDACTED"
        return facts
    facts["private_manifest_state"] = "OBSERVED_IN_MEMORY"
    facts["private_manifest_metadata_read_in_memory_only"] = True
    if candidate_rejected:
        facts["current_release_metadata_subdomain_state"] = "CANDIDATE_REJECTED_REDACTED"
        return facts
    if not candidates:
        facts["current_release_metadata_subdomain_state"] = "CANDIDATE_NOT_OBSERVED_REDACTED"
        return facts
    if len(candidates) != 1:
        facts["current_release_metadata_subdomain_state"] = "CANDIDATE_AMBIGUOUS_REDACTED"
        return facts
    facts["private_database_read_requests"] += 1
    try:
        raw = _private_read(client, candidates[0])
    except (RuntimeError, OSError, ValueError, CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError):
        facts["current_release_metadata_subdomain_state"] = "REDACTED_RECEIPT_UNAVAILABLE_REDACTED"
        return facts
    facts["core_execution_receipt_content_read_in_memory_only"] = True
    state, subdomains = _subdomains_from_receipt(raw, target_date)
    facts["current_release_metadata_subdomain_state"] = state
    facts["current_release_metadata_subdomains"] = subdomains
    facts["current_release_metadata_subdomains_declared"] = state == "CANONICAL_NONREADY_CURRENT_RELEASE_SUBDOMAINS_DECLARED_REDACTED"
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    declared = bool(facts["current_release_metadata_subdomains_declared"])
    checks = [
        {"id": "PRIVATE_CORE_EXECUTION_MANIFEST_OBSERVED", "passed": facts["private_manifest_state"] == "OBSERVED_IN_MEMORY"},
        {"id": "CURRENT_RELEASE_METADATA_SUBDOMAINS_DECLARED", "passed": declared},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAINS_DECLARED_NO_CORE_ACTION_AUTHORIZED" if declared else "CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAINS_NOT_DECLARED_NO_CORE_ACTION_AUTHORIZED",
        "current_release_metadata_subdomains_declared": declared,
        "current_release_metadata_subdomain_state": facts["current_release_metadata_subdomain_state"],
        "current_release_metadata_subdomains": list(facts["current_release_metadata_subdomains"]),
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["current_release_metadata_subdomains_declared"], bool):
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "current_release_metadata_subdomains_declared": result["current_release_metadata_subdomains_declared"],
        "current_release_metadata_subdomain_state": result["current_release_metadata_subdomain_state"],
        "current_release_metadata_subdomains": list(result["current_release_metadata_subdomains"]),
        "product_outbound_operations_not_attempted": result["product_outbound_operations_not_attempted"],
        "core_start_authorized": False,
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
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "current_release_metadata_subdomains_declared": False,
        "current_release_metadata_subdomain_state": "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
        "current_release_metadata_subdomains": [],
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CORE_EXECUTION_CURRENT_RELEASE_METADATA_SUBDOMAIN_DECLARATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "private_data_provider_workflow_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--private-client", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        client = load_private_client(args.private_client)
        receipt = build_receipt(load_contract(args.contract), discover_current_release_metadata_subdomains(args.repo_root, client))
    except (CurrentProductionCoreExecutionCurrentReleaseMetadataSubdomainDeclarationDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
