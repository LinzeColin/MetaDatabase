#!/usr/bin/env python3
"""Declare fixed redacted failure domains for one canonical non-ready core receipt."""

from __future__ import annotations

import argparse
import json
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

from current_production_core_execution_redacted_receipt_schema_compatibility_diagnostic import (
    CANONICAL_FIELDS,
    CORE_FAIL_STATUS,
    CORE_PASS_STATUS,
    CORE_RECEIPT_TYPE,
    CORE_SPEC,
)
from current_production_private_redacted_prerequisite_receipt_continuity_attestation import (
    MANIFEST_RECORD_FIELDS,
    PRIVATE_DOMAIN,
    _manifest_candidate,
    _private_read,
    _receipt_filename,
    load_private_client,
)


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_DIAGNOSTIC"
MAX_PRIVATE_DATABASE_READ_REQUESTS = 2
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
FAILURE_DOMAIN_STATES = {
    "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
    "PRIVATE_MANIFEST_REJECTED_REDACTED",
    "CANDIDATE_NOT_OBSERVED_REDACTED",
    "CANDIDATE_AMBIGUOUS_REDACTED",
    "CANDIDATE_REJECTED_REDACTED",
    "REDACTED_RECEIPT_UNAVAILABLE_REDACTED",
    "CANONICAL_READY_NOT_APPLICABLE_REDACTED",
    "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED",
    "CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED_REDACTED",
}
CHECK_DOMAIN = {
    "PRIVILEGED_METADATA_READ": "PRIVILEGED_METADATA_INCOMPLETE_REDACTED",
    "CONFIG_FILE_REGULAR": "RUNTIME_FILE_METADATA_INCOMPLETE_REDACTED",
    "RUNTIME_ENV_FILE_REGULAR": "RUNTIME_FILE_METADATA_INCOMPLETE_REDACTED",
    "RUNTIME_SECRET_FILE_PRESENT": "RUNTIME_FILE_METADATA_INCOMPLETE_REDACTED",
    "CURRENT_RELEASE_LINK_MANAGED": "CURRENT_RELEASE_METADATA_INCOMPLETE_REDACTED",
    "CURRENT_RELEASE_COMPOSE_FILE_REGULAR": "CURRENT_RELEASE_METADATA_INCOMPLETE_REDACTED",
    "CURRENT_RELEASE_REBUILD_FILE_REGULAR": "CURRENT_RELEASE_METADATA_INCOMPLETE_REDACTED",
    "CORE_CAPACITY_DROPIN_FILE_REGULAR": "CORE_CAPACITY_METADATA_INCOMPLETE_REDACTED",
    "CURRENT_CANDIDATE_IMAGE_PRESENT": "CANDIDATE_IMAGE_METADATA_INCOMPLETE_REDACTED",
    "CORE_UNIT_NOT_FOUND_AND_INACTIVE": "CORE_UNIT_EXPECTATION_INCOMPLETE_REDACTED",
    "CONNECTOR_UNIT_NOT_FOUND_AND_INACTIVE": "CONNECTOR_UNIT_EXPECTATION_INCOMPLETE_REDACTED",
}
CHECK_IDENTIFIERS = tuple(CHECK_DOMAIN)
FAILURE_DOMAINS = frozenset(CHECK_DOMAIN.values())


class CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError(ValueError):
    """Raised when the constrained declaration input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError) as exc:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "core execution canonical non-ready failure-domain declaration diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "core execution canonical non-ready failure-domain declaration facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-CANONICAL-NONREADY-FAILURE-DOMAIN-DECLARATION-DIAGNOSTIC-001":
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("diagnostic must remain read-only")
    expected = {
        "private_area": "Private-MetaDatabase",
        "private_domain": PRIVATE_DOMAIN,
        "core_execution_receipt_type": CORE_RECEIPT_TYPE,
        "maximum_private_database_read_requests": MAX_PRIVATE_DATABASE_READ_REQUESTS,
        "canonical_current_receipt_field_set": sorted(CANONICAL_FIELDS),
        "prewhitelisted_check_identifiers": list(CHECK_IDENTIFIERS),
        "prewhitelisted_failure_domains": sorted(FAILURE_DOMAINS),
        "provider_api_requests": 0,
        "product_github_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "private_database_client_read_only": True,
        "single_private_manifest_metadata_stream_read_in_memory_only": True,
        "at_most_one_current_core_execution_candidate_read_in_memory": True,
        "only_canonical_nonready_schema_status_and_authorization_shape_used_in_memory": True,
        "only_prewhitelisted_nonsecret_check_identifiers_and_boolean_passed_states_used_in_memory": True,
        "only_prewhitelisted_failure_code_shape_used_in_memory": True,
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
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_ONLY_NOT_FAILURE_ROOT_CAUSE_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PRIVATE_DATA_PROVIDER_WORKFLOW_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("rollback boundary is not exact")


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
        "core_execution_failure_domain_state",
        "failure_domains",
        "failure_domains_declared",
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
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_DIAGNOSTIC":
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES or facts.get("private_manifest_state") not in {"OBSERVED_IN_MEMORY", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("facts state is invalid")
    if facts.get("core_execution_failure_domain_state") not in FAILURE_DOMAIN_STATES or type(facts.get("failure_domains_declared")) is not bool:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("failure-domain declaration state is invalid")
    for field in ("private_manifest_metadata_read_in_memory_only", "core_execution_receipt_content_read_in_memory_only"):
        if type(facts.get(field)) is not bool:
            raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("facts boolean state is invalid")
    if type(facts.get("private_database_read_requests")) is not int or not 0 <= facts["private_database_read_requests"] <= MAX_PRIVATE_DATABASE_READ_REQUESTS:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("private database request count is invalid")
    domains = facts.get("failure_domains")
    if not isinstance(domains, list) or any(domain not in FAILURE_DOMAINS for domain in domains) or domains != sorted(set(domains)):
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("failure-domain list is invalid")
    declared = facts["core_execution_failure_domain_state"] == "CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED_REDACTED"
    if facts["failure_domains_declared"] is not declared or (declared and not domains) or (not declared and domains):
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("failure-domain declaration is inconsistent")
    for field in (
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("redaction boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("outbound operation count is invalid")
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        if facts["private_manifest_state"] != "NOT_ATTEMPTED" or facts["private_database_read_requests"] != 0 or facts["private_manifest_metadata_read_in_memory_only"] or facts["core_execution_receipt_content_read_in_memory_only"]:
            raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("unavailable root facts are inconsistent")
    elif facts["private_manifest_state"] == "OBSERVED_IN_MEMORY":
        if not facts["private_manifest_metadata_read_in_memory_only"] or facts["private_database_read_requests"] < 1:
            raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("observed manifest facts are inconsistent")
    elif facts["private_manifest_metadata_read_in_memory_only"]:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("unavailable manifest facts are inconsistent")
    needs_candidate_read = facts["core_execution_failure_domain_state"] in {
        "REDACTED_RECEIPT_UNAVAILABLE_REDACTED",
        "CANONICAL_READY_NOT_APPLICABLE_REDACTED",
        "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED",
        "CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED_REDACTED",
    }
    if needs_candidate_read and facts["private_database_read_requests"] != 2:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("candidate-read facts are inconsistent")
    if facts["core_execution_receipt_content_read_in_memory_only"] and facts["private_database_read_requests"] != 2:
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("receipt-read facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "private_manifest_state": "NOT_ATTEMPTED",
        "private_manifest_metadata_read_in_memory_only": False,
        "core_execution_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 0,
        "core_execution_failure_domain_state": "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
        "failure_domains": [],
        "failure_domains_declared": False,
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


def _core_candidate_from_manifest(raw: bytes, observed_on: str) -> tuple[list[str], bool, bool]:
    expected_name = _receipt_filename(CORE_SPEC, observed_on)
    candidates: list[str] = []
    candidate_rejected = False
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return candidates, False, candidate_rejected
    for line in lines:
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return candidates, False, candidate_rejected
        if not isinstance(record, dict) or set(record) != MANIFEST_RECORD_FIELDS:
            return candidates, False, candidate_rejected
        if record.get("domain") != PRIVATE_DOMAIN or record.get("original_name") != expected_name:
            continue
        object_path = _manifest_candidate(record, expected_name)
        if object_path is None:
            candidate_rejected = True
            continue
        candidates.append(object_path)
    return candidates, True, candidate_rejected


def _failure_domains_from_receipt(raw: bytes, observed_on: str) -> tuple[str, list[str]]:
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    if not isinstance(receipt, dict) or set(receipt) != CANONICAL_FIELDS:
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    if receipt.get("schema_version") != "1.0.0" or receipt.get("receipt_type") != CORE_RECEIPT_TYPE or not isinstance(receipt.get("decision"), str) or receipt.get("observed_on") != observed_on:
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    if receipt.get("execution_authorized") is not False or type(receipt.get("input_ready")) is not bool or not isinstance(receipt.get("source_boundary"), dict) or not isinstance(receipt.get("claim_boundary"), str):
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    if receipt.get("status") != CORE_FAIL_STATUS or receipt["input_ready"] is not False:
        if receipt.get("status") == CORE_PASS_STATUS and receipt.get("input_ready") is True:
            return "CANONICAL_READY_NOT_APPLICABLE_REDACTED", []
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    checks = receipt.get("checks")
    if not isinstance(checks, list) or len(checks) != len(CHECK_IDENTIFIERS):
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    identifiers: list[str] = []
    expected_failure_codes: list[str] = []
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "passed"} or not isinstance(check.get("id"), str) or type(check.get("passed")) is not bool:
            return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
        identifier = check["id"]
        identifiers.append(identifier)
        if not check["passed"]:
            expected_failure_codes.append(identifier)
    if tuple(identifiers) != CHECK_IDENTIFIERS or not expected_failure_codes:
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    if receipt.get("failure_codes") != expected_failure_codes:
        return "CANONICAL_NONREADY_FAILURE_DOMAIN_REJECTED_REDACTED", []
    return "CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED_REDACTED", sorted({CHECK_DOMAIN[identifier] for identifier in expected_failure_codes})


def discover_failure_domain_declaration(repo_root: Path, client: ModuleType, observed_on: str | None = None) -> dict[str, Any]:
    """Read one manifest and at most one current core candidate without exposing it."""

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
    except (RuntimeError, OSError, ValueError, CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError):
        facts["private_manifest_state"] = "UNAVAILABLE_REDACTED"
        return facts
    candidates, valid_manifest, candidate_rejected = _core_candidate_from_manifest(manifest_raw, target_date)
    if not valid_manifest:
        facts["private_manifest_state"] = "REJECTED_REDACTED"
        facts["core_execution_failure_domain_state"] = "PRIVATE_MANIFEST_REJECTED_REDACTED"
        return facts
    facts["private_manifest_state"] = "OBSERVED_IN_MEMORY"
    facts["private_manifest_metadata_read_in_memory_only"] = True
    if candidate_rejected:
        facts["core_execution_failure_domain_state"] = "CANDIDATE_REJECTED_REDACTED"
        return facts
    if not candidates:
        facts["core_execution_failure_domain_state"] = "CANDIDATE_NOT_OBSERVED_REDACTED"
        return facts
    if len(candidates) != 1:
        facts["core_execution_failure_domain_state"] = "CANDIDATE_AMBIGUOUS_REDACTED"
        return facts
    facts["private_database_read_requests"] += 1
    try:
        raw = _private_read(client, candidates[0])
    except (RuntimeError, OSError, ValueError, CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError):
        facts["core_execution_failure_domain_state"] = "REDACTED_RECEIPT_UNAVAILABLE_REDACTED"
        return facts
    facts["core_execution_receipt_content_read_in_memory_only"] = True
    state, domains = _failure_domains_from_receipt(raw, target_date)
    facts["core_execution_failure_domain_state"] = state
    facts["failure_domains"] = domains
    facts["failure_domains_declared"] = state == "CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED_REDACTED"
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    declared = bool(facts["failure_domains_declared"])
    checks = [
        {"id": "PRIVATE_CORE_EXECUTION_MANIFEST_OBSERVED", "passed": facts["private_manifest_state"] == "OBSERVED_IN_MEMORY"},
        {"id": "CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED", "passed": declared},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAINS_DECLARED_NO_CORE_ACTION_AUTHORIZED" if declared else "CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAINS_NOT_DECLARED_NO_CORE_ACTION_AUTHORIZED",
        "failure_domains_declared": declared,
        "failure_domain_state": facts["core_execution_failure_domain_state"],
        "failure_domains": list(facts["failure_domains"]),
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["failure_domains_declared"], bool):
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "failure_domains_declared": result["failure_domains_declared"],
        "failure_domain_state": result["failure_domain_state"],
        "failure_domains": list(result["failure_domains"]),
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
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "failure_domains_declared": False,
        "failure_domain_state": "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
        "failure_domains": [],
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_NONREADY_FAILURE_DOMAIN_DECLARATION_INPUT_FAILED"],
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
        receipt = build_receipt(load_contract(args.contract), discover_failure_domain_declaration(args.repo_root, client))
    except (CurrentProductionCoreExecutionCanonicalNonreadyFailureDomainDeclarationDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
