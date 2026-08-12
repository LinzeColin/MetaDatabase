#!/usr/bin/env python3
"""Intake one bounded explicit ABD current-production authority record safely."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from current_production_protected_target_metadata_locator import KeyOnlyJsonError, _top_level_json_keys


PASS_STATUS = "PASS_CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE"
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
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_ROOT_REJECTED_REDACTED"}
SCAN_STATES = {"COMPLETED", "TRUNCATED_REDACTED", "NOT_ATTEMPTED"}
AUTHORITY_RECORD_STATES = {
    "RESOLVED_IN_MEMORY",
    "AMBIGUOUS_EXPLICIT_AUTHORITY_RECORD_REDACTED",
    "NO_EXPLICIT_AUTHORITY_RECORD_REDACTED",
    "SCHEMA_INCOMPLETE_REDACTED",
    "PERMISSION_BOUNDARY_REJECTED_REDACTED",
    "SCAN_LIMIT_REACHED_REDACTED",
    "UNAVAILABLE_REDACTED",
}
MAX_TREE_DEPTH = 12
MAX_TREE_ENTRIES = 512
MAX_CANDIDATE_RECORDS = 16
MAX_CANDIDATE_BYTES = 32768
MAX_CONTROLLED_TARGET_REFERENCE_CHARACTERS = 128
REQUIRED_FILENAME_TOKENS = {"authority", "record"}
BLOCKED_NAME_TOKENS = {
    "account",
    "cert",
    "credential",
    "identity",
    "key",
    "password",
    "pem",
    "private",
    "secret",
    "ssh",
    "token",
}
FORBIDDEN_TARGET_REFERENCE_CHARACTERS = frozenset(":/@?#[\\]=\r\n\t")
SKIPPED_DIRECTORY_TOKENS = {"archive", "build", "cache", "node", "node_modules", "vendor"}
RECORD_FIELDS = {
    "schema_version",
    "record_type",
    "product",
    "product_version",
    "observed_on",
    "noninteractive_only",
    "controlled_target_reference",
    "owner_task_authorization",
}


class CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError(ValueError):
    """Raised when the authority-record intake contract is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("%s must be an object" % name)
    return value


def _read_object(path: Path, name: str) -> Mapping[str, Any]:
    try:
        if not path.is_file() or path.is_symlink():
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("%s is not a regular file" % name)
        return _object(json.loads(path.read_text(encoding="utf-8")), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError) as exc:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("%s is unreadable" % name) from exc


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _expected_contract() -> dict[str, Any]:
    return {
        "allowed_candidate_suffixes": [".json"],
        "required_filename_tokens": ["authority", "record"],
        "maximum_tree_depth": MAX_TREE_DEPTH,
        "maximum_tree_entries": MAX_TREE_ENTRIES,
        "maximum_candidate_records_opened": MAX_CANDIDATE_RECORDS,
        "maximum_candidate_bytes": MAX_CANDIDATE_BYTES,
        "require_exactly_one_valid_authority_record": True,
        "controlled_target_reference_must_be_nonsecret_opaque_identifier": True,
        "required_record_fields": sorted(RECORD_FIELDS),
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
    }


def _source_boundary() -> dict[str, Any]:
    return {
        "protected_root_read_only": True,
        "only_private_permission_nonsecret_json_filename_candidates_opened": True,
        "candidate_json_key_set_checked_before_value_parse": True,
        "candidate_target_reference_parsed_in_memory_only": True,
        "only_one_valid_authority_record_may_authorize_source": True,
        "controlled_target_reference_must_remain_nonsecret_opaque": True,
        "credential_material_read_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
        "browser_login_submitted": False,
        "provider_api_request_sent": False,
        "ssh_connection_attempted": False,
        "github_api_request_sent": False,
        "provider_resource_or_network_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }


def validate_contract(contract: Mapping[str, Any]) -> None:
    if set(contract) != CONTRACT_FIELDS:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract schema is invalid")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-ABD-SCOPED-EXPLICIT-AUTHORITY-RECORD-INTAKE-002":
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract identifier is invalid")
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE_READ_ONLY":
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract status is invalid")
    if _object(contract.get("expected"), "contract expected") != _expected_contract():
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract expected boundary is invalid")
    if _object(contract.get("source_boundary"), "contract source boundary") != _source_boundary():
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract source boundary is invalid")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE_ONLY_NOT_TARGET_VALUE_DISCLOSURE_PROVIDER_RESOURCE_STATE_SSH_RETRY_HOST_METADATA_READ_REPAIR_DEPLOYMENT_CORE_START_CLOUDFLARE_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract claim boundary is invalid")
    if _object(contract.get("rollback"), "contract rollback") != {
        "action": "NO_PROTECTED_SOURCE_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("contract rollback is invalid")


def _tokens(path: Path) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", path.name.lower()) if token}


def _safe_candidate(path: Path, info: os.stat_result) -> bool:
    tokens = _tokens(path)
    return (
        _is_named_candidate(path)
        and not (tokens & BLOCKED_NAME_TOKENS)
        and stat.S_ISREG(info.st_mode)
        and (info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)) == 0
        and info.st_size <= MAX_CANDIDATE_BYTES
    )


def _is_named_candidate(path: Path) -> bool:
    return path.suffix.lower() == ".json" and REQUIRED_FILENAME_TOKENS.issubset(_tokens(path))


def _is_nonsecret_opaque_target_reference(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_CONTROLLED_TARGET_REFERENCE_CHARACTERS
        and value == value.strip()
        and value.isprintable()
        and not any(character.isspace() for character in value)
        and not any(character in FORBIDDEN_TARGET_REFERENCE_CHARACTERS for character in value)
    )


def _record_is_valid(record: Mapping[str, Any], observed_on: str) -> bool:
    target_reference = record.get("controlled_target_reference")
    return (
        set(record) == RECORD_FIELDS
        and record.get("schema_version") == "1.0.0"
        and record.get("record_type") == "ABD_CURRENT_PRODUCTION_AUTHORITY_RECORD"
        and record.get("product") == "ABD"
        and record.get("product_version") == "0.0.0.1"
        and record.get("observed_on") == observed_on
        and record.get("noninteractive_only") is True
        and _is_nonsecret_opaque_target_reference(target_reference)
        and record.get("owner_task_authorization") == "CURRENT_TASK_AUTHORIZED"
    )


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE",
        "observed_on": observed_on,
        "protected_root_state": "UNAVAILABLE_REDACTED",
        "bounded_scan_state": "NOT_ATTEMPTED",
        "authority_record_state": "UNAVAILABLE_REDACTED",
        "authority_record_ready": False,
        "candidate_record_key_set_checked_in_memory_only": False,
        "candidate_target_reference_parsed_in_memory_only": False,
        "unique_valid_authority_record_checked_in_memory_only": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }


def intake_explicit_authority_record(root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Read one explicitly named, nonsecret authority record only in memory."""

    observed = observed_on or _today_utc().isoformat()
    facts = _base_facts(observed)
    try:
        root_info = root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["protected_root_state"] = "UNSAFE_ROOT_REJECTED_REDACTED"
        return facts

    facts["protected_root_state"] = "AVAILABLE_READ_ONLY"
    entries_seen = 0
    candidates_opened = 0
    scan_truncated = False
    saw_permission_rejection = False
    saw_schema_incomplete = False
    valid_record_count = 0
    stack: list[tuple[Path, int]] = [(root, 0)]

    while stack and not scan_truncated:
        directory, depth = stack.pop()
        if depth >= MAX_TREE_DEPTH:
            scan_truncated = True
            break
        try:
            listing = os.scandir(directory)
        except OSError:
            saw_permission_rejection = True
            continue
        with listing:
            for entry in listing:
                entries_seen += 1
                if entries_seen > MAX_TREE_ENTRIES:
                    scan_truncated = True
                    break
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    saw_permission_rejection = True
                    continue
                if stat.S_ISLNK(info.st_mode):
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if not (_tokens(path) & (BLOCKED_NAME_TOKENS | SKIPPED_DIRECTORY_TOKENS)):
                        stack.append((path, depth + 1))
                    continue
                if not _is_named_candidate(path):
                    continue
                if not _safe_candidate(path, info):
                    if not (_tokens(path) & BLOCKED_NAME_TOKENS):
                        saw_permission_rejection = True
                    continue
                if candidates_opened >= MAX_CANDIDATE_RECORDS:
                    scan_truncated = True
                    break
                candidates_opened += 1
                facts["candidate_record_key_set_checked_in_memory_only"] = True
                try:
                    keys = _top_level_json_keys(path)
                except (KeyOnlyJsonError, OSError, UnicodeDecodeError):
                    saw_schema_incomplete = True
                    continue
                if keys != RECORD_FIELDS:
                    saw_schema_incomplete = True
                    continue
                try:
                    record = _read_object(path, "authority record")
                except CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError:
                    saw_schema_incomplete = True
                    continue
                facts["candidate_target_reference_parsed_in_memory_only"] = True
                if _record_is_valid(record, observed):
                    valid_record_count += 1
                    continue
                saw_schema_incomplete = True

    facts["bounded_scan_state"] = "TRUNCATED_REDACTED" if scan_truncated else "COMPLETED"
    facts["unique_valid_authority_record_checked_in_memory_only"] = not scan_truncated
    if scan_truncated:
        facts["authority_record_state"] = "SCAN_LIMIT_REACHED_REDACTED"
    elif valid_record_count == 1:
        facts["authority_record_state"] = "RESOLVED_IN_MEMORY"
        facts["authority_record_ready"] = True
    elif valid_record_count > 1:
        facts["authority_record_state"] = "AMBIGUOUS_EXPLICIT_AUTHORITY_RECORD_REDACTED"
    elif saw_schema_incomplete:
        facts["authority_record_state"] = "SCHEMA_INCOMPLETE_REDACTED"
    elif saw_permission_rejection:
        facts["authority_record_state"] = "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    else:
        facts["authority_record_state"] = "NO_EXPLICIT_AUTHORITY_RECORD_REDACTED"
    return facts


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "protected_root_state",
        "bounded_scan_state",
        "authority_record_state",
        "authority_record_ready",
        "candidate_record_key_set_checked_in_memory_only",
        "candidate_target_reference_parsed_in_memory_only",
        "unique_valid_authority_record_checked_in_memory_only",
        "credential_material_read_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "protected_path_or_filename_emitted_or_persisted",
        "provider_api_requests",
        "ssh_connections_attempted",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE":
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("facts identity is invalid")
    try:
        observed_on = date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("facts observation date is invalid") from exc
    if observed_on != _today_utc():
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("facts observation date is not current UTC")
    if facts.get("protected_root_state") not in ROOT_STATES:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("protected root state is invalid")
    if facts.get("bounded_scan_state") not in SCAN_STATES:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("scan state is invalid")
    if facts.get("authority_record_state") not in AUTHORITY_RECORD_STATES:
        raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("authority record state is invalid")
    for field in (
        "authority_record_ready",
        "candidate_record_key_set_checked_in_memory_only",
        "candidate_target_reference_parsed_in_memory_only",
        "unique_valid_authority_record_checked_in_memory_only",
    ):
        if type(facts.get(field)) is not bool:
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("authority record boolean is invalid")
    for field in (
        "credential_material_read_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "protected_path_or_filename_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("redaction boundary is invalid")
    for field in ("provider_api_requests", "ssh_connections_attempted", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("outbound operation count is invalid")

    root_state = facts["protected_root_state"]
    scan_state = facts["bounded_scan_state"]
    record_state = facts["authority_record_state"]
    ready = facts["authority_record_ready"]
    if root_state != "AVAILABLE_READ_ONLY":
        if (
            scan_state != "NOT_ATTEMPTED"
            or record_state != "UNAVAILABLE_REDACTED"
            or ready
            or facts["unique_valid_authority_record_checked_in_memory_only"]
        ):
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("unavailable root facts are inconsistent")
    elif record_state == "RESOLVED_IN_MEMORY":
        if (
            not ready
            or scan_state != "COMPLETED"
            or not facts["candidate_record_key_set_checked_in_memory_only"]
            or not facts["candidate_target_reference_parsed_in_memory_only"]
            or not facts["unique_valid_authority_record_checked_in_memory_only"]
        ):
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("resolved record facts are inconsistent")
    else:
        if ready:
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("unresolved record cannot be ready")
        if record_state == "SCAN_LIMIT_REACHED_REDACTED":
            if scan_state != "TRUNCATED_REDACTED" or facts["unique_valid_authority_record_checked_in_memory_only"]:
                raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("scan limit facts are inconsistent")
        elif scan_state != "COMPLETED" or not facts["unique_valid_authority_record_checked_in_memory_only"]:
            raise CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError("completed scan facts are inconsistent")


def evaluate_intake(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    executed = facts["protected_root_state"] == "AVAILABLE_READ_ONLY" and facts["bounded_scan_state"] != "NOT_ATTEMPTED"
    ready = facts["authority_record_ready"]
    checks = [
        {"id": "EXPLICIT_AUTHORITY_RECORD_INTAKE_EXECUTED", "passed": executed},
        {
            "id": "UNIQUE_VALID_AUTHORITY_RECORD_CHECKED",
            "passed": facts["unique_valid_authority_record_checked_in_memory_only"],
        },
        {"id": "ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_READY", "passed": ready},
        {"id": "PROVIDER_SSH_GITHUB_ACTIONS_NOT_ATTEMPTED", "passed": True},
    ]
    return {
        "status": PASS_STATUS if executed else FAIL_STATUS,
        "decision": "ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_READY_FOR_SEPARATE_TARGET_MAPPING_PHASE" if ready else "ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_NOT_PROVEN_NO_TARGET_OR_TRANSPORT_ACTION_AUTHORIZED",
        "authority_record_intake_executed": executed,
        "source_authority_ready": ready,
        "authority_record_state": facts["authority_record_state"],
        "target_mapping_authorized": False,
        "transport_retry_authorized": False,
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_intake(contract, facts)
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "authority_record_intake_executed": result["authority_record_intake_executed"],
        "source_authority_ready": result["source_authority_ready"],
        "authority_record_state": result["authority_record_state"],
        "target_mapping_authorized": False,
        "transport_retry_authorized": False,
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "provider_api_requests": facts["provider_api_requests"],
        "ssh_connections_attempted": facts["ssh_connections_attempted"],
        "github_api_requests": facts["github_api_requests"],
        "checks": list(result["checks"]),
        "failure_codes": list(result["failure_codes"]),
        "source_boundary": dict(_object(contract["source_boundary"], "contract source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "authority_record_intake_executed": False,
        "source_authority_ready": False,
        "authority_record_state": "UNAVAILABLE_REDACTED",
        "target_mapping_authorized": False,
        "transport_retry_authorized": False,
        "current_host_metadata_collection_authorized": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_ABD_SCOPED_EXPLICIT_AUTHORITY_RECORD_INTAKE_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--protected-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(_read_object(args.contract, "authority record intake contract"), intake_explicit_authority_record(args.protected_root))
    except (CurrentProductionAbdScopedExplicitAuthorityRecordIntakeError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
