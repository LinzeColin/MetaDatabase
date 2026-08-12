#!/usr/bin/env python3
"""Resolve one redacted target-metadata pointer from protected nonsecret documents."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from current_production_protected_target_metadata_locator import (
    BLOCKED_NAME_TOKENS,
    MAX_CANDIDATE_BYTES,
    _candidate_schema_is_nonsecret_target_metadata,
    _top_level_json_keys,
)
from current_production_readme_protected_source_pointer_resolver import POINTER_PATTERN, _safe_pointed_source


PASS_STATUS = "PASS_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER"
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_ROOT_REJECTED_REDACTED"}
SCAN_STATES = {"COMPLETED", "TRUNCATED_REDACTED", "NOT_ATTEMPTED"}
POINTER_STATES = {
    "RESOLVED_IN_MEMORY",
    "NOT_DECLARED_REDACTED",
    "AMBIGUOUS_REDACTED",
    "INVALID_DECLARATION_REDACTED",
    "PERMISSION_BOUNDARY_REJECTED_REDACTED",
    "SCAN_LIMIT_REACHED_REDACTED",
    "NOT_ATTEMPTED",
}
SOURCE_STATES = {"RESOLVED_IN_MEMORY", "NOT_ATTEMPTED", "UNAVAILABLE_REDACTED", "PERMISSION_BOUNDARY_REJECTED_REDACTED", "SCHEMA_INCOMPLETE_REDACTED"}
DOCUMENT_TOKENS = {"architecture", "deployment", "handoff", "inventory", "operations", "readme", "runbook", "topology"}
DOCUMENT_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}
MAX_TREE_DEPTH = 8
MAX_TREE_ENTRIES = 10000
MAX_DOCUMENTS_OPENED = 16
MAX_DOCUMENT_BYTES = 65536


class CurrentProductionProtectedDocumentationPointerResolverError(ValueError):
    """Raised when a resolver contract or redacted fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionProtectedDocumentationPointerResolverError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionProtectedDocumentationPointerResolverError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionProtectedDocumentationPointerResolverError) as exc:
        raise CurrentProductionProtectedDocumentationPointerResolverError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "protected documentation pointer resolver contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted protected documentation pointer facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionProtectedDocumentationPointerResolverError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionProtectedDocumentationPointerResolverError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-PROTECTED-DOCUMENTATION-POINTER-RESOLVER-001":
        raise CurrentProductionProtectedDocumentationPointerResolverError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionProtectedDocumentationPointerResolverError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER_READ_ONLY":
        raise CurrentProductionProtectedDocumentationPointerResolverError("resolver must remain read-only")
    expected = {
        "allowed_document_name_tokens": ["architecture", "deployment", "handoff", "inventory", "operations", "readme", "runbook", "topology"],
        "allowed_document_suffixes": [".md", ".markdown", ".rst", ".txt"],
        "maximum_tree_depth": 8,
        "maximum_tree_entries": 10000,
        "maximum_documents_opened": 16,
        "maximum_document_bytes": 65536,
        "document_file_permission_rule": "NO_GROUP_OR_WORLD_WRITE",
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionProtectedDocumentationPointerResolverError("resolver expectations are not exact")
    boundary = {
        "protected_root_read_only": True,
        "only_fixed_nonsecret_document_name_set_opened": True,
        "only_single_inline_nonsecret_relative_pointer_form_accepted": True,
        "protected_source_opened_only_after_unique_document_pointer": True,
        "document_text_pointer_or_protected_path_emitted_or_persisted": False,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "browser_login_submitted": False,
        "provider_api_request_sent": False,
        "ssh_connection_attempted": False,
        "github_api_request_sent": False,
        "provider_resource_created_deleted_rebuilt_or_restarted": False,
        "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionProtectedDocumentationPointerResolverError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER_ONLY_NOT_CREDENTIAL_DISCOVERY_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionProtectedDocumentationPointerResolverError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROTECTED_DOCUMENT_SOURCE_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionProtectedDocumentationPointerResolverError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "protected_root_state",
        "document_scan_state",
        "documentation_pointer_state",
        "protected_metadata_source_state",
        "documentation_target_source_ready",
        "document_text_read_in_memory_only",
        "candidate_schema_keys_read_in_memory_only",
        "document_text_pointer_or_protected_path_emitted_or_persisted",
        "candidate_json_values_parsed_or_persisted",
        "credential_material_read_emitted_or_persisted",
        "target_value_read_emitted_or_persisted",
        "provider_api_requests",
        "ssh_connections_attempted",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionProtectedDocumentationPointerResolverError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER":
        raise CurrentProductionProtectedDocumentationPointerResolverError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionProtectedDocumentationPointerResolverError("facts observation date is invalid") from exc
    if facts.get("protected_root_state") not in ROOT_STATES:
        raise CurrentProductionProtectedDocumentationPointerResolverError("protected root state is invalid")
    if facts.get("document_scan_state") not in SCAN_STATES:
        raise CurrentProductionProtectedDocumentationPointerResolverError("document scan state is invalid")
    if facts.get("documentation_pointer_state") not in POINTER_STATES:
        raise CurrentProductionProtectedDocumentationPointerResolverError("documentation pointer state is invalid")
    if facts.get("protected_metadata_source_state") not in SOURCE_STATES:
        raise CurrentProductionProtectedDocumentationPointerResolverError("protected source state is invalid")
    if type(facts.get("documentation_target_source_ready")) is not bool or type(facts.get("document_text_read_in_memory_only")) is not bool or type(facts.get("candidate_schema_keys_read_in_memory_only")) is not bool:
        raise CurrentProductionProtectedDocumentationPointerResolverError("resolver boolean state is invalid")
    for field in (
        "document_text_pointer_or_protected_path_emitted_or_persisted",
        "candidate_json_values_parsed_or_persisted",
        "credential_material_read_emitted_or_persisted",
        "target_value_read_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionProtectedDocumentationPointerResolverError("redaction boundary is invalid")
    for field in ("provider_api_requests", "ssh_connections_attempted", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionProtectedDocumentationPointerResolverError("outbound operation count is invalid")

    root_state = facts["protected_root_state"]
    scan_state = facts["document_scan_state"]
    pointer_state = facts["documentation_pointer_state"]
    source_state = facts["protected_metadata_source_state"]
    ready = facts["documentation_target_source_ready"]
    if root_state != "AVAILABLE_READ_ONLY":
        if scan_state != "NOT_ATTEMPTED" or pointer_state != "NOT_ATTEMPTED" or source_state != "NOT_ATTEMPTED" or ready or facts["document_text_read_in_memory_only"] or facts["candidate_schema_keys_read_in_memory_only"]:
            raise CurrentProductionProtectedDocumentationPointerResolverError("unavailable root facts are inconsistent")
    elif pointer_state == "RESOLVED_IN_MEMORY":
        if ready != (source_state == "RESOLVED_IN_MEMORY"):
            raise CurrentProductionProtectedDocumentationPointerResolverError("resolved pointer facts are inconsistent")
    else:
        if source_state != "NOT_ATTEMPTED" or ready or facts["candidate_schema_keys_read_in_memory_only"]:
            raise CurrentProductionProtectedDocumentationPointerResolverError("unresolved pointer facts are inconsistent")
        if pointer_state == "SCAN_LIMIT_REACHED_REDACTED" and scan_state != "TRUNCATED_REDACTED":
            raise CurrentProductionProtectedDocumentationPointerResolverError("scan limit facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER",
        "observed_on": observed_on,
        "protected_root_state": "UNAVAILABLE_REDACTED",
        "document_scan_state": "NOT_ATTEMPTED",
        "documentation_pointer_state": "NOT_ATTEMPTED",
        "protected_metadata_source_state": "NOT_ATTEMPTED",
        "documentation_target_source_ready": False,
        "document_text_read_in_memory_only": False,
        "candidate_schema_keys_read_in_memory_only": False,
        "document_text_pointer_or_protected_path_emitted_or_persisted": False,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }


def _tokens(root: Path, path: Path) -> set[str]:
    tokens: set[str] = set()
    for part in path.relative_to(root).parts:
        tokens.update(value for value in re.split(r"[^a-z0-9]+", part.lower()) if value)
    return tokens


def _is_nonsecret_document(root: Path, path: Path) -> bool:
    if path.suffix.lower() not in DOCUMENT_SUFFIXES:
        return False
    tokens = _tokens(root, path)
    return not bool(tokens & BLOCKED_NAME_TOKENS) and bool(tokens & DOCUMENT_TOKENS)


def _resolve_document_pointer(root: Path, pointers: set[str], facts: dict[str, Any]) -> None:
    if len(pointers) != 1:
        facts["documentation_pointer_state"] = "AMBIGUOUS_REDACTED" if pointers else "NOT_DECLARED_REDACTED"
        return
    pointer = next(iter(pointers))
    source, source_state = _safe_pointed_source(root, pointer)
    if source is None:
        if source_state == "INVALID_DECLARATION_REDACTED":
            facts["documentation_pointer_state"] = "INVALID_DECLARATION_REDACTED"
        else:
            facts["documentation_pointer_state"] = "RESOLVED_IN_MEMORY"
            facts["protected_metadata_source_state"] = source_state or "UNAVAILABLE_REDACTED"
        return
    facts["documentation_pointer_state"] = "RESOLVED_IN_MEMORY"
    facts["candidate_schema_keys_read_in_memory_only"] = True
    try:
        keys = _top_level_json_keys(source)
    except ValueError:
        facts["protected_metadata_source_state"] = "SCHEMA_INCOMPLETE_REDACTED"
        return
    if not _candidate_schema_is_nonsecret_target_metadata(keys):
        facts["protected_metadata_source_state"] = "SCHEMA_INCOMPLETE_REDACTED"
        return
    facts["protected_metadata_source_state"] = "RESOLVED_IN_MEMORY"
    facts["documentation_target_source_ready"] = True


def resolve_protected_documentation_pointer(root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Resolve one target-metadata pointer from a bounded nonsecret document set."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    try:
        root_info = root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["protected_root_state"] = "UNSAFE_ROOT_REJECTED_REDACTED"
        return facts

    facts["protected_root_state"] = "AVAILABLE_READ_ONLY"
    entries_seen = 0
    documents_opened = 0
    scan_truncated = False
    saw_permission_rejection = False
    pointers: set[str] = set()
    stack: list[tuple[Path, int]] = [(root, 0)]

    while stack and not scan_truncated and len(pointers) < 2:
        directory, depth = stack.pop()
        if depth >= MAX_TREE_DEPTH:
            continue
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
                    if _tokens(root, path) & BLOCKED_NAME_TOKENS:
                        continue
                    stack.append((path, depth + 1))
                    continue
                if not stat.S_ISREG(info.st_mode) or not _is_nonsecret_document(root, path):
                    continue
                if (info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)) != 0 or info.st_size > MAX_DOCUMENT_BYTES:
                    saw_permission_rejection = True
                    continue
                if documents_opened >= MAX_DOCUMENTS_OPENED:
                    scan_truncated = True
                    break
                documents_opened += 1
                facts["document_text_read_in_memory_only"] = True
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    saw_permission_rejection = True
                    continue
                pointers.update(POINTER_PATTERN.findall(text))
                if len(pointers) >= 2:
                    break

    facts["document_scan_state"] = "TRUNCATED_REDACTED" if scan_truncated else "COMPLETED"
    if scan_truncated:
        facts["documentation_pointer_state"] = "SCAN_LIMIT_REACHED_REDACTED"
    elif len(pointers) >= 2:
        facts["documentation_pointer_state"] = "AMBIGUOUS_REDACTED"
    elif saw_permission_rejection and not pointers:
        facts["documentation_pointer_state"] = "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    else:
        _resolve_document_pointer(root, pointers, facts)
    return facts


def evaluate_resolver(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["documentation_target_source_ready"])
    checks = [
        {"id": "PROTECTED_DOCUMENTATION_POINTER_RESOLVER_COMPLETED", "passed": True},
        {"id": "DOCUMENT_DECLARED_PROTECTED_TARGET_SOURCE_READY", "passed": ready},
        {"id": "OUTBOUND_PROVIDER_SSH_GITHUB_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "DOCUMENT_DECLARED_TARGET_SOURCE_READY_FOR_SEPARATE_COMBINED_SOURCE_COMPATIBILITY_PHASE" if ready else "DOCUMENT_DECLARED_TARGET_SOURCE_NOT_READY_NO_TRANSPORT_PROVIDER_OR_HOST_ACTION_AUTHORIZED",
        "document_declared_target_source_located": ready,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "document_declared_target_source_state": facts["protected_metadata_source_state"] if facts["documentation_pointer_state"] == "RESOLVED_IN_MEMORY" else facts["documentation_pointer_state"],
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_resolver(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("document_declared_target_source_located", "outbound_operations_not_attempted")) or result["core_start_authorized"] is not False:
        raise CurrentProductionProtectedDocumentationPointerResolverError("resolver authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionProtectedDocumentationPointerResolverError("resolver checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "document_declared_target_source_located": result["document_declared_target_source_located"],
        "outbound_operations_not_attempted": result["outbound_operations_not_attempted"],
        "core_start_authorized": False,
        "document_declared_target_source_state": result["document_declared_target_source_state"],
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
        "decision": "CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "document_declared_target_source_located": False,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "document_declared_target_source_state": "INPUT_INVALID_REDACTED",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_PROTECTED_DOCUMENTATION_POINTER_RESOLVER_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "protected_document_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--protected-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        facts = resolve_protected_documentation_pointer(args.protected_root)
        receipt = build_receipt(load_contract(args.contract), facts)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionProtectedDocumentationPointerResolverError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
