#!/usr/bin/env python3
"""Locate one redacted nonsecret current-production target-metadata source."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR"
PROTECTED_ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_ROOT_REJECTED_REDACTED"}
SCAN_STATES = {"COMPLETED", "TRUNCATED_REDACTED", "NOT_ATTEMPTED"}
METADATA_STATES = {
    "RESOLVED_IN_MEMORY",
    "NO_MANAGED_NONSECRET_SOURCE_REDACTED",
    "SCHEMA_INCOMPLETE_REDACTED",
    "PERMISSION_BOUNDARY_REJECTED_REDACTED",
    "SCAN_LIMIT_REACHED_REDACTED",
    "UNAVAILABLE_REDACTED",
}
MAX_TREE_DEPTH = 8
MAX_TREE_ENTRIES = 4096
MAX_CANDIDATE_FILES = 8
MAX_CANDIDATE_BYTES = 65536
ALLOWED_SUFFIXES = {".json"}
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
SCOPE_TOKENS = {"current", "prod", "production"}
TARGET_TOKENS = {"alias", "mapping", "metadata", "resource", "server", "service", "target"}
ALLOWED_METADATA_KEYS = {
    "account_alias",
    "current_production",
    "current_production_target",
    "environment",
    "environment_name",
    "provider",
    "region",
    "resource_alias",
    "resource_id",
    "resource_name",
    "schema_version",
    "service_alias",
    "service_name",
    "ssh_alias",
    "target",
    "target_alias",
    "target_kind",
}
TARGET_METADATA_KEYS = {
    "current_production_target",
    "resource_alias",
    "resource_id",
    "resource_name",
    "service_alias",
    "service_name",
    "ssh_alias",
    "target",
    "target_alias",
}
NUMBER_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


class CurrentProductionProtectedTargetMetadataLocatorError(ValueError):
    """Raised when a locator contract or redacted fact is malformed."""


class KeyOnlyJsonError(ValueError):
    """Raised when a candidate is not a bounded JSON object with readable keys."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionProtectedTargetMetadataLocatorError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionProtectedTargetMetadataLocatorError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionProtectedTargetMetadataLocatorError) as exc:
        raise CurrentProductionProtectedTargetMetadataLocatorError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "protected target metadata locator contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted protected target metadata facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionProtectedTargetMetadataLocatorError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionProtectedTargetMetadataLocatorError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-PROTECTED-TARGET-METADATA-LOCATOR-001":
        raise CurrentProductionProtectedTargetMetadataLocatorError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionProtectedTargetMetadataLocatorError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR_READ_ONLY":
        raise CurrentProductionProtectedTargetMetadataLocatorError("locator must remain read-only")
    expected = {
        "allowed_candidate_suffixes": [".json"],
        "maximum_tree_depth": 8,
        "maximum_tree_entries": 4096,
        "maximum_candidate_files_opened": 8,
        "maximum_candidate_bytes": 65536,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionProtectedTargetMetadataLocatorError("locator expectations are not exact")
    boundary = {
        "protected_root_read_only": True,
        "only_nonsecret_filename_metadata_and_json_key_sets_checked": True,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
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
        raise CurrentProductionProtectedTargetMetadataLocatorError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR_ONLY_NOT_CREDENTIAL_DISCOVERY_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionProtectedTargetMetadataLocatorError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROTECTED_SOURCE_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionProtectedTargetMetadataLocatorError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "protected_root_state",
        "bounded_scan_state",
        "metadata_source_state",
        "metadata_source_ready",
        "candidate_schema_keys_read_in_memory_only",
        "candidate_json_values_parsed_or_persisted",
        "credential_material_read_emitted_or_persisted",
        "target_value_read_emitted_or_persisted",
        "protected_path_or_filename_emitted_or_persisted",
        "provider_api_requests",
        "ssh_connections_attempted",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionProtectedTargetMetadataLocatorError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR":
        raise CurrentProductionProtectedTargetMetadataLocatorError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionProtectedTargetMetadataLocatorError("facts observation date is invalid") from exc
    if facts.get("protected_root_state") not in PROTECTED_ROOT_STATES:
        raise CurrentProductionProtectedTargetMetadataLocatorError("protected root state is invalid")
    if facts.get("bounded_scan_state") not in SCAN_STATES:
        raise CurrentProductionProtectedTargetMetadataLocatorError("bounded scan state is invalid")
    if facts.get("metadata_source_state") not in METADATA_STATES:
        raise CurrentProductionProtectedTargetMetadataLocatorError("metadata source state is invalid")
    if type(facts.get("metadata_source_ready")) is not bool or type(facts.get("candidate_schema_keys_read_in_memory_only")) is not bool:
        raise CurrentProductionProtectedTargetMetadataLocatorError("locator boolean state is invalid")
    for field in (
        "candidate_json_values_parsed_or_persisted",
        "credential_material_read_emitted_or_persisted",
        "target_value_read_emitted_or_persisted",
        "protected_path_or_filename_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionProtectedTargetMetadataLocatorError("redaction boundary is invalid")
    for field in ("provider_api_requests", "ssh_connections_attempted", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionProtectedTargetMetadataLocatorError("outbound operation count is invalid")

    root_state = facts["protected_root_state"]
    scan_state = facts["bounded_scan_state"]
    metadata_state = facts["metadata_source_state"]
    ready = facts["metadata_source_ready"]
    if root_state != "AVAILABLE_READ_ONLY":
        if scan_state != "NOT_ATTEMPTED" or metadata_state != "UNAVAILABLE_REDACTED" or ready or facts["candidate_schema_keys_read_in_memory_only"]:
            raise CurrentProductionProtectedTargetMetadataLocatorError("unavailable root facts are inconsistent")
    else:
        if scan_state == "NOT_ATTEMPTED" or metadata_state == "UNAVAILABLE_REDACTED":
            raise CurrentProductionProtectedTargetMetadataLocatorError("available root facts are inconsistent")
        if ready != (metadata_state == "RESOLVED_IN_MEMORY"):
            raise CurrentProductionProtectedTargetMetadataLocatorError("metadata readiness is inconsistent")
        if metadata_state == "SCAN_LIMIT_REACHED_REDACTED" and scan_state != "TRUNCATED_REDACTED":
            raise CurrentProductionProtectedTargetMetadataLocatorError("scan limit facts are inconsistent")
        if scan_state == "TRUNCATED_REDACTED" and ready:
            raise CurrentProductionProtectedTargetMetadataLocatorError("truncated scan cannot authorize metadata readiness")


def _skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _parse_string(text: str, index: int, *, collect: bool) -> tuple[str, int]:
    if index >= len(text) or text[index] != '"':
        raise KeyOnlyJsonError("expected JSON string")
    pieces: list[str] = []
    index += 1
    while index < len(text):
        character = text[index]
        if character == '"':
            return "".join(pieces), index + 1
        if ord(character) < 0x20:
            raise KeyOnlyJsonError("control character in JSON string")
        if character == "\\":
            if index + 1 >= len(text):
                raise KeyOnlyJsonError("incomplete JSON escape")
            escape = text[index + 1]
            if escape == "u":
                if index + 5 >= len(text) or any(value not in "0123456789abcdefABCDEF" for value in text[index + 2:index + 6]):
                    raise KeyOnlyJsonError("invalid JSON unicode escape")
                if collect:
                    raise KeyOnlyJsonError("escaped candidate key is not permitted")
                index += 6
                continue
            if escape not in '"\\/bfnrt':
                raise KeyOnlyJsonError("invalid JSON escape")
            if collect:
                raise KeyOnlyJsonError("escaped candidate key is not permitted")
            index += 2
            continue
        if collect:
            pieces.append(character)
        index += 1
    raise KeyOnlyJsonError("unterminated JSON string")


def _token_ends(text: str, index: int) -> bool:
    return index >= len(text) or text[index] in " \t\r\n,]}"


def _skip_value(text: str, index: int, depth: int = 0) -> int:
    if depth > 64:
        raise KeyOnlyJsonError("candidate JSON nesting is too deep")
    index = _skip_whitespace(text, index)
    if index >= len(text):
        raise KeyOnlyJsonError("missing JSON value")
    character = text[index]
    if character == '"':
        _, index = _parse_string(text, index, collect=False)
        return index
    if character == "{":
        index = _skip_whitespace(text, index + 1)
        if index < len(text) and text[index] == "}":
            return index + 1
        while True:
            _, index = _parse_string(text, index, collect=False)
            index = _skip_whitespace(text, index)
            if index >= len(text) or text[index] != ":":
                raise KeyOnlyJsonError("missing JSON object separator")
            index = _skip_value(text, index + 1, depth + 1)
            index = _skip_whitespace(text, index)
            if index < len(text) and text[index] == "}":
                return index + 1
            if index >= len(text) or text[index] != ",":
                raise KeyOnlyJsonError("missing JSON object delimiter")
            index = _skip_whitespace(text, index + 1)
    if character == "[":
        index = _skip_whitespace(text, index + 1)
        if index < len(text) and text[index] == "]":
            return index + 1
        while True:
            index = _skip_value(text, index, depth + 1)
            index = _skip_whitespace(text, index)
            if index < len(text) and text[index] == "]":
                return index + 1
            if index >= len(text) or text[index] != ",":
                raise KeyOnlyJsonError("missing JSON array delimiter")
            index = _skip_whitespace(text, index + 1)
    for literal in ("true", "false", "null"):
        if text.startswith(literal, index) and _token_ends(text, index + len(literal)):
            return index + len(literal)
    match = NUMBER_PATTERN.match(text, index)
    if match is not None and _token_ends(text, match.end()):
        return match.end()
    raise KeyOnlyJsonError("invalid JSON value")


def _top_level_json_keys(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise KeyOnlyJsonError("candidate JSON is unreadable") from exc
    index = _skip_whitespace(text, 0)
    if index >= len(text) or text[index] != "{":
        raise KeyOnlyJsonError("candidate JSON is not an object")
    index = _skip_whitespace(text, index + 1)
    keys: set[str] = set()
    if index < len(text) and text[index] == "}":
        index += 1
    else:
        while True:
            key, index = _parse_string(text, index, collect=True)
            if key in keys:
                raise KeyOnlyJsonError("candidate JSON has duplicate key")
            keys.add(key)
            index = _skip_whitespace(text, index)
            if index >= len(text) or text[index] != ":":
                raise KeyOnlyJsonError("missing top-level JSON separator")
            index = _skip_value(text, index + 1)
            index = _skip_whitespace(text, index)
            if index < len(text) and text[index] == "}":
                index += 1
                break
            if index >= len(text) or text[index] != ",":
                raise KeyOnlyJsonError("missing top-level JSON delimiter")
            index = _skip_whitespace(text, index + 1)
    if _skip_whitespace(text, index) != len(text):
        raise KeyOnlyJsonError("trailing candidate JSON content")
    return keys


def _name_tokens(root: Path, path: Path) -> set[str]:
    tokens: set[str] = set()
    for part in path.relative_to(root).parts:
        tokens.update(token for token in re.split(r"[^a-z0-9]+", part.lower()) if token)
    return tokens


def _is_candidate(root: Path, path: Path) -> bool:
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return False
    tokens = _name_tokens(root, path)
    if tokens & BLOCKED_NAME_TOKENS:
        return False
    has_scope_and_target = bool(tokens & SCOPE_TOKENS) and bool(tokens & TARGET_TOKENS)
    has_abd_ovh_target = {"abd", "ovh"}.issubset(tokens) and bool(tokens & TARGET_TOKENS)
    return has_scope_and_target or has_abd_ovh_target


def _candidate_schema_is_nonsecret_target_metadata(keys: set[str]) -> bool:
    if not keys or not keys.issubset(ALLOWED_METADATA_KEYS):
        return False
    if "provider" not in keys or not (keys & TARGET_METADATA_KEYS):
        return False
    return not any(token in BLOCKED_NAME_TOKENS for key in keys for token in re.split(r"[^a-z0-9]+", key.lower()) if token)


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR",
        "observed_on": observed_on,
        "protected_root_state": "UNAVAILABLE_REDACTED",
        "bounded_scan_state": "NOT_ATTEMPTED",
        "metadata_source_state": "UNAVAILABLE_REDACTED",
        "metadata_source_ready": False,
        "candidate_schema_keys_read_in_memory_only": False,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }


def locate_protected_target_metadata(root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Inspect a bounded protected tree without retaining target or credential values."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    try:
        root_info = root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["protected_root_state"] = "UNSAFE_ROOT_REJECTED_REDACTED"
        return facts

    facts["protected_root_state"] = "AVAILABLE_READ_ONLY"
    candidates_opened = 0
    saw_permission_rejection = False
    saw_schema_incomplete = False
    scan_truncated = False
    entries_seen = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    source_resolved = False

    while stack and not scan_truncated and not source_resolved:
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
                    stack.append((path, depth + 1))
                    continue
                if not stat.S_ISREG(info.st_mode) or not _is_candidate(root, path):
                    continue
                if (info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)) != 0 or info.st_size > MAX_CANDIDATE_BYTES:
                    saw_permission_rejection = True
                    continue
                if candidates_opened >= MAX_CANDIDATE_FILES:
                    scan_truncated = True
                    break
                candidates_opened += 1
                facts["candidate_schema_keys_read_in_memory_only"] = True
                try:
                    keys = _top_level_json_keys(path)
                except KeyOnlyJsonError:
                    saw_schema_incomplete = True
                    continue
                if _candidate_schema_is_nonsecret_target_metadata(keys):
                    source_resolved = True
                    break
                saw_schema_incomplete = True

    facts["bounded_scan_state"] = "TRUNCATED_REDACTED" if scan_truncated else "COMPLETED"
    if source_resolved and not scan_truncated:
        facts["metadata_source_state"] = "RESOLVED_IN_MEMORY"
        facts["metadata_source_ready"] = True
    elif scan_truncated:
        facts["metadata_source_state"] = "SCAN_LIMIT_REACHED_REDACTED"
    elif saw_schema_incomplete:
        facts["metadata_source_state"] = "SCHEMA_INCOMPLETE_REDACTED"
    elif saw_permission_rejection:
        facts["metadata_source_state"] = "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    else:
        facts["metadata_source_state"] = "NO_MANAGED_NONSECRET_SOURCE_REDACTED"
    return facts


def evaluate_locator(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["metadata_source_ready"])
    checks = [
        {"id": "PROTECTED_TARGET_METADATA_LOCATOR_COMPLETED", "passed": True},
        {"id": "PROTECTED_TARGET_METADATA_SOURCE_READY", "passed": ready},
        {"id": "OUTBOUND_PROVIDER_SSH_GITHUB_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_TARGET_METADATA_READY_FOR_SEPARATE_COMBINED_SOURCE_COMPATIBILITY_PHASE" if ready else "CURRENT_PRODUCTION_TARGET_METADATA_NOT_READY_NO_TRANSPORT_PROVIDER_OR_HOST_ACTION_AUTHORIZED",
        "protected_target_metadata_located": ready,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "protected_target_metadata_state": facts["metadata_source_state"],
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_locator(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("protected_target_metadata_located", "outbound_operations_not_attempted")) or result["core_start_authorized"] is not False:
        raise CurrentProductionProtectedTargetMetadataLocatorError("locator authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionProtectedTargetMetadataLocatorError("locator checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "protected_target_metadata_located": result["protected_target_metadata_located"],
        "outbound_operations_not_attempted": result["outbound_operations_not_attempted"],
        "core_start_authorized": False,
        "protected_target_metadata_state": result["protected_target_metadata_state"],
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
        "decision": "CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "protected_target_metadata_located": False,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "protected_target_metadata_state": "INPUT_INVALID_REDACTED",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_PROTECTED_TARGET_METADATA_LOCATOR_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "protected_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--protected-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), locate_protected_target_metadata(args.protected_root))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionProtectedTargetMetadataLocatorError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
