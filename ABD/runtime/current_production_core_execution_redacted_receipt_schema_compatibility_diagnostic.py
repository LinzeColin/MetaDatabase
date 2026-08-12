#!/usr/bin/env python3
"""Classify one current private redacted core-execution receipt without exposing it."""

from __future__ import annotations

import argparse
import json
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

from current_production_core_activation_prerequisite_static_evidence_classification_diagnostic import PREREQUISITES, Prerequisite
from current_production_private_redacted_prerequisite_receipt_continuity_attestation import (
    MANIFEST_RECORD_FIELDS,
    PRIVATE_DOMAIN,
    _manifest_candidate,
    _private_read,
    _receipt_filename,
    load_private_client,
)


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC"
MAX_PRIVATE_DATABASE_READ_REQUESTS = 2
CANONICAL_FIELDS = frozenset({"schema_version", "receipt_type", "status", "decision", "observed_on", "input_ready", "execution_authorized", "checks", "failure_codes", "source_boundary", "claim_boundary"})
FAIL_CLOSED_FIELDS = frozenset({"schema_version", "receipt_type", "status", "decision", "observed_on", "input_ready", "execution_authorized", "checks", "failure_codes", "error_type", "host_runtime_or_configuration_changed", "real_time_soak_waited"})
CANONICAL_READY_STATE = "CANONICAL_READY_EVIDENCE_OBSERVED_REDACTED"
CANONICAL_NON_READY_STATE = "CANONICAL_NON_READY_EVIDENCE_OBSERVED_REDACTED"
OFFICIAL_FAIL_CLOSED_STATE = "OFFICIAL_FAIL_CLOSED_EVIDENCE_OBSERVED_REDACTED"
SCHEMA_STATES = {
    "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
    "PRIVATE_MANIFEST_REJECTED_REDACTED",
    "CANDIDATE_NOT_OBSERVED_REDACTED",
    "CANDIDATE_AMBIGUOUS_REDACTED",
    "CANDIDATE_REJECTED_REDACTED",
    "REDACTED_RECEIPT_UNAVAILABLE_REDACTED",
    CANONICAL_READY_STATE,
    CANONICAL_NON_READY_STATE,
    OFFICIAL_FAIL_CLOSED_STATE,
    "NONCANONICAL_REJECTED_REDACTED",
}
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
CORE_SPEC = next(spec for spec in PREREQUISITES if spec.identifier == "CORE_EXECUTION_CONTRACT")
CORE_RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT"
CORE_PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT"
CORE_FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT"
FAIL_CLOSED_DECISION = "CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_INPUT_FAILED_CLOSED"
FAIL_CLOSED_CODE = "CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_INPUT_FAILED"


class CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError(ValueError):
    """Raised when the tightly scoped private receipt classification is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError) as exc:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "core execution redacted receipt schema compatibility diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "core execution redacted receipt schema compatibility facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-REDACTED-RECEIPT-SCHEMA-COMPATIBILITY-DIAGNOSTIC-001":
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("diagnostic must remain read-only")
    expected = {
        "private_area": "Private-MetaDatabase",
        "private_domain": PRIVATE_DOMAIN,
        "core_execution_receipt_type": CORE_RECEIPT_TYPE,
        "maximum_private_database_read_requests": MAX_PRIVATE_DATABASE_READ_REQUESTS,
        "canonical_current_receipt_field_set": sorted(CANONICAL_FIELDS),
        "official_fail_closed_receipt_field_set": sorted(FAIL_CLOSED_FIELDS),
        "provider_api_requests": 0,
        "product_github_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "private_database_client_read_only": True,
        "single_private_manifest_metadata_stream_read_in_memory_only": True,
        "at_most_one_current_core_execution_candidate_read_in_memory": True,
        "only_core_execution_schema_status_fields_used_in_memory": True,
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
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_ONLY_NOT_ACTUAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PRIVATE_DATA_PROVIDER_WORKFLOW_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("rollback boundary is not exact")


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
        "core_execution_receipt_schema_state",
        "core_execution_current_ready_evidence",
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
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC":
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES or facts.get("private_manifest_state") not in {"OBSERVED_IN_MEMORY", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("facts state is invalid")
    if facts.get("core_execution_receipt_schema_state") not in SCHEMA_STATES or type(facts.get("core_execution_current_ready_evidence")) is not bool:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("schema classification is invalid")
    for field in ("private_manifest_metadata_read_in_memory_only", "core_execution_receipt_content_read_in_memory_only"):
        if type(facts.get(field)) is not bool:
            raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("facts boolean state is invalid")
    if type(facts.get("private_database_read_requests")) is not int or not 0 <= facts["private_database_read_requests"] <= MAX_PRIVATE_DATABASE_READ_REQUESTS:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("private database request count is invalid")
    for field in (
        "private_object_path_hash_or_raw_content_emitted_copied_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("redaction boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("outbound operation count is invalid")
    if facts["core_execution_current_ready_evidence"] is not (facts["core_execution_receipt_schema_state"] == CANONICAL_READY_STATE):
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("core execution readiness is inconsistent")
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        if facts["private_manifest_state"] != "NOT_ATTEMPTED" or facts["private_database_read_requests"] != 0 or facts["private_manifest_metadata_read_in_memory_only"] or facts["core_execution_receipt_content_read_in_memory_only"]:
            raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("unavailable root facts are inconsistent")
    elif facts["private_manifest_state"] == "OBSERVED_IN_MEMORY":
        if not facts["private_manifest_metadata_read_in_memory_only"] or facts["private_database_read_requests"] < 1:
            raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("observed manifest facts are inconsistent")
    elif facts["private_manifest_metadata_read_in_memory_only"]:
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("unavailable manifest facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_EXECUTION_RECEIPT_SCHEMA_COMPATIBILITY_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "private_manifest_state": "NOT_ATTEMPTED",
        "private_manifest_metadata_read_in_memory_only": False,
        "core_execution_receipt_content_read_in_memory_only": False,
        "private_database_read_requests": 0,
        "core_execution_receipt_schema_state": "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
        "core_execution_current_ready_evidence": False,
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


def _checks_shape(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) and set(item) == {"id", "passed"} for item in value)


def _failure_codes_shape(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(code, str) for code in value)


def _classify_receipt(raw: bytes, observed_on: str) -> str:
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "NONCANONICAL_REJECTED_REDACTED"
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "1.0.0" or receipt.get("receipt_type") != CORE_RECEIPT_TYPE:
        return "NONCANONICAL_REJECTED_REDACTED"
    if set(receipt) == CANONICAL_FIELDS:
        if not isinstance(receipt.get("decision"), str) or receipt.get("observed_on") != observed_on or not isinstance(receipt.get("source_boundary"), dict) or not isinstance(receipt.get("claim_boundary"), str) or not _checks_shape(receipt.get("checks")) or not _failure_codes_shape(receipt.get("failure_codes")):
            return "NONCANONICAL_REJECTED_REDACTED"
        if receipt.get("execution_authorized") is not False or type(receipt.get("input_ready")) is not bool:
            return "NONCANONICAL_REJECTED_REDACTED"
        if receipt.get("status") == CORE_PASS_STATUS and receipt["input_ready"] is True:
            return CANONICAL_READY_STATE
        if receipt.get("status") == CORE_FAIL_STATUS and receipt["input_ready"] is False:
            return CANONICAL_NON_READY_STATE
        return "NONCANONICAL_REJECTED_REDACTED"
    if set(receipt) == FAIL_CLOSED_FIELDS:
        if receipt.get("status") != CORE_FAIL_STATUS or receipt.get("decision") != FAIL_CLOSED_DECISION or receipt.get("observed_on") not in {"INVALID", observed_on} or receipt.get("input_ready") is not False or receipt.get("execution_authorized") is not False:
            return "NONCANONICAL_REJECTED_REDACTED"
        if receipt.get("checks") != [] or receipt.get("failure_codes") != [FAIL_CLOSED_CODE] or not isinstance(receipt.get("error_type"), str) or receipt.get("host_runtime_or_configuration_changed") is not False or receipt.get("real_time_soak_waited") is not False:
            return "NONCANONICAL_REJECTED_REDACTED"
        return OFFICIAL_FAIL_CLOSED_STATE
    return "NONCANONICAL_REJECTED_REDACTED"


def discover_schema_compatibility(repo_root: Path, client: ModuleType, observed_on: str | None = None) -> dict[str, Any]:
    """Read one private manifest and at most one exact current core receipt."""

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
    except (RuntimeError, OSError, ValueError, CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError):
        facts["private_manifest_state"] = "UNAVAILABLE_REDACTED"
        return facts
    candidates, valid_manifest, candidate_rejected = _core_candidate_from_manifest(manifest_raw, target_date)
    if not valid_manifest:
        facts["private_manifest_state"] = "REJECTED_REDACTED"
        facts["core_execution_receipt_schema_state"] = "PRIVATE_MANIFEST_REJECTED_REDACTED"
        return facts
    facts["private_manifest_state"] = "OBSERVED_IN_MEMORY"
    facts["private_manifest_metadata_read_in_memory_only"] = True
    if candidate_rejected:
        facts["core_execution_receipt_schema_state"] = "CANDIDATE_REJECTED_REDACTED"
        return facts
    if not candidates:
        facts["core_execution_receipt_schema_state"] = "CANDIDATE_NOT_OBSERVED_REDACTED"
        return facts
    if len(candidates) != 1:
        facts["core_execution_receipt_schema_state"] = "CANDIDATE_AMBIGUOUS_REDACTED"
        return facts
    facts["private_database_read_requests"] += 1
    try:
        raw = _private_read(client, candidates[0])
    except (RuntimeError, OSError, ValueError, CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError):
        facts["core_execution_receipt_schema_state"] = "REDACTED_RECEIPT_UNAVAILABLE_REDACTED"
        return facts
    facts["core_execution_receipt_content_read_in_memory_only"] = True
    state = _classify_receipt(raw, target_date)
    facts["core_execution_receipt_schema_state"] = state
    facts["core_execution_current_ready_evidence"] = state == CANONICAL_READY_STATE
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["core_execution_current_ready_evidence"])
    checks = [
        {"id": "PRIVATE_CORE_EXECUTION_MANIFEST_OBSERVED", "passed": facts["private_manifest_state"] == "OBSERVED_IN_MEMORY"},
        {"id": "CORE_EXECUTION_CANONICAL_CURRENT_READY_EVIDENCE_OBSERVED", "passed": ready},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_CANONICAL_READY_EVIDENCE_OBSERVED_SEPARATE_CORE_ACTION_AUTHORIZATION_REQUIRED" if ready else "CURRENT_PRODUCTION_CORE_EXECUTION_SCHEMA_NOT_CURRENT_READY_NO_CORE_ACTION_AUTHORIZED",
        "core_execution_current_ready_evidence": ready,
        "core_execution_receipt_schema_state": facts["core_execution_receipt_schema_state"],
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["core_execution_current_ready_evidence"], bool):
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "core_execution_current_ready_evidence": result["core_execution_current_ready_evidence"],
        "core_execution_receipt_schema_state": result["core_execution_receipt_schema_state"],
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
        "decision": "CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "core_execution_current_ready_evidence": False,
        "core_execution_receipt_schema_state": "PRIVATE_MANIFEST_UNAVAILABLE_REDACTED",
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CORE_EXECUTION_REDACTED_RECEIPT_SCHEMA_COMPATIBILITY_INPUT_FAILED"],
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
        receipt = build_receipt(load_contract(args.contract), discover_schema_compatibility(args.repo_root, client))
    except (CurrentProductionCoreExecutionRedactedReceiptSchemaCompatibilityDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
