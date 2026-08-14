#!/usr/bin/env python3
"""Locate one redacted protected OVH management recovery-route source."""

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


PASS_STATUS = "PASS_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER"
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_ROOT_REJECTED_REDACTED"}
SCAN_STATES = {"COMPLETED", "TRUNCATED_REDACTED", "NOT_ATTEMPTED"}
SOURCE_STATES = {
    "RESOLVED_IN_MEMORY",
    "NOT_AVAILABLE_REDACTED",
    "AMBIGUOUS_REDACTED",
    "SCHEMA_REJECTED_REDACTED",
    "PERMISSION_BOUNDARY_REJECTED_REDACTED",
    "SCAN_LIMIT_REACHED_REDACTED",
    "UNAVAILABLE_REDACTED",
}
MAX_TREE_DEPTH = 8
MAX_TREE_ENTRIES = 16384
MAX_SCHEMA_FILES_CHECKED = 64
MAX_AUTH_VALUE_CANDIDATES_OPENED = 12
MAX_CANDIDATE_BYTES = 32768
ROUTE_TOKENS = {"abd", "current", "deploy", "deployment", "ovh", "prod", "production", "recovery", "route", "vps"}
REQUIRED_AUTH_KEYS = {"endpoint", "application_key", "application_secret", "consumer_key", "service_name"}
SAFE_SERVICE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SAFE_OVH_ENDPOINT = re.compile(r"https://(?:[A-Za-z0-9-]+\.)?api\.ovh\.com/1\.0/?\Z")
SKIPPED_DIRECTORY_NAMES = {".git", ".mypy_cache", ".pytest_cache", ".venv", "__pycache__", "node_modules", "site-packages", "venv"}


class CurrentProductionProtectedProviderAuthRouteResolverError(ValueError):
    """Raised when a resolver contract or redacted fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionProtectedProviderAuthRouteResolverError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionProtectedProviderAuthRouteResolverError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionProtectedProviderAuthRouteResolverError) as exc:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "protected provider-auth recovery-route resolver contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted protected provider-auth recovery-route facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-PROTECTED-PROVIDER-AUTH-ROUTE-RESOLVER-001":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER_READ_ONLY":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("resolver must remain read-only")
    expected = {
        "required_auth_source_keys": ["application_key", "application_secret", "consumer_key", "endpoint", "service_name"],
        "required_path_tokens": ["abd"],
        "route_hint_tokens": ["current", "deploy", "deployment", "ovh", "prod", "production", "recovery", "route", "vps"],
        "maximum_tree_depth": 8,
        "maximum_tree_entries": 16384,
        "maximum_json_schema_files_checked": 64,
        "maximum_auth_value_candidates_opened": 12,
        "maximum_candidate_bytes": 32768,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("resolver expectations are not exact")
    boundary = {
        "protected_root_read_only": True,
        "only_bounded_route_related_json_candidates_read": True,
        "candidate_json_schema_keys_read_in_memory_only": True,
        "candidate_credential_values_used_in_memory_only": True,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
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
        raise CurrentProductionProtectedProviderAuthRouteResolverError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER_ONLY_NOT_PROVIDER_API_QUERY_TARGET_OWNERSHIP_PROOF_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROTECTED_SOURCE_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "protected_root_state",
        "bounded_scan_state",
        "provider_auth_route_source_state",
        "provider_auth_route_source_ready",
        "candidate_credential_values_used_in_memory_only",
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "protected_path_or_filename_emitted_or_persisted",
        "provider_api_requests",
        "ssh_connections_attempted",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("facts observation date is invalid") from exc
    if facts.get("protected_root_state") not in ROOT_STATES:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("protected root state is invalid")
    if facts.get("bounded_scan_state") not in SCAN_STATES:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("bounded scan state is invalid")
    if facts.get("provider_auth_route_source_state") not in SOURCE_STATES:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("provider auth-route source state is invalid")
    if type(facts.get("provider_auth_route_source_ready")) is not bool or type(facts.get("candidate_credential_values_used_in_memory_only")) is not bool:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("resolver boolean state is invalid")
    for field in (
        "credential_material_emitted_or_persisted",
        "target_mapping_emitted_or_persisted",
        "protected_path_or_filename_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionProtectedProviderAuthRouteResolverError("redaction boundary is invalid")
    for field in ("provider_api_requests", "ssh_connections_attempted", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionProtectedProviderAuthRouteResolverError("outbound operation count is invalid")

    root_state = facts["protected_root_state"]
    scan_state = facts["bounded_scan_state"]
    source_state = facts["provider_auth_route_source_state"]
    ready = facts["provider_auth_route_source_ready"]
    if root_state != "AVAILABLE_READ_ONLY":
        if scan_state != "NOT_ATTEMPTED" or source_state != "UNAVAILABLE_REDACTED" or ready or facts["candidate_credential_values_used_in_memory_only"]:
            raise CurrentProductionProtectedProviderAuthRouteResolverError("unavailable root facts are inconsistent")
        return
    if scan_state == "NOT_ATTEMPTED" or source_state == "UNAVAILABLE_REDACTED":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("available root facts are inconsistent")
    if ready != (source_state == "RESOLVED_IN_MEMORY"):
        raise CurrentProductionProtectedProviderAuthRouteResolverError("auth-route readiness is inconsistent")
    if source_state == "SCAN_LIMIT_REACHED_REDACTED" and scan_state != "TRUNCATED_REDACTED":
        raise CurrentProductionProtectedProviderAuthRouteResolverError("scan limit facts are inconsistent")
    if scan_state == "TRUNCATED_REDACTED" and ready:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("truncated scan cannot authorize a source")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER",
        "observed_on": observed_on,
        "protected_root_state": "UNAVAILABLE_REDACTED",
        "bounded_scan_state": "NOT_ATTEMPTED",
        "provider_auth_route_source_state": "UNAVAILABLE_REDACTED",
        "provider_auth_route_source_ready": False,
        "candidate_credential_values_used_in_memory_only": False,
        "credential_material_emitted_or_persisted": False,
        "target_mapping_emitted_or_persisted": False,
        "protected_path_or_filename_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }


def _tokens(root: Path, path: Path) -> set[str]:
    tokens: set[str] = set()
    for part in path.relative_to(root).parts:
        tokens.update(token for token in re.split(r"[^a-z0-9]+", part.lower()) if token)
    return tokens


def _route_related(root: Path, path: Path) -> bool:
    tokens = _tokens(root, path)
    return "abd" in tokens and bool(tokens & (ROUTE_TOKENS - {"abd"}))


def _safe_candidate(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and (info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)) == 0 and 0 < info.st_size <= MAX_CANDIDATE_BYTES


def _valid_auth_target(raw: object) -> bool:
    if not isinstance(raw, dict) or set(raw) != REQUIRED_AUTH_KEYS:
        return False
    values = raw
    if any(not isinstance(value, str) or not value for value in values.values()):
        return False
    if SAFE_OVH_ENDPOINT.fullmatch(str(values["endpoint"])) is None:
        return False
    return SAFE_SERVICE_NAME.fullmatch(str(values["service_name"])) is not None


def _read_candidate_auth_target(path: Path) -> bool | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return _valid_auth_target(raw)


def _candidate_has_auth_keyset(path: Path) -> bool | None:
    try:
        return _top_level_json_keys(path) == REQUIRED_AUTH_KEYS
    except KeyOnlyJsonError:
        return None


def _sorted_entries(directory: Path) -> list[os.DirEntry[str]] | None:
    try:
        with os.scandir(directory) as listing:
            return sorted(list(listing), key=lambda entry: entry.name.lower())
    except OSError:
        return None


def locate_provider_auth_recovery_route(root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Locate exactly one strict protected auth source without emitting values or paths."""

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
    schema_files_checked = 0
    auth_value_candidates_opened = 0
    scan_truncated = False
    saw_permission_rejection = False
    saw_schema_rejection = False
    matched_sources = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and not scan_truncated:
        directory, depth = stack.pop()
        if depth >= MAX_TREE_DEPTH:
            scan_truncated = True
            break
        entries = _sorted_entries(directory)
        if entries is None:
            saw_permission_rejection = True
            continue
        directories: list[tuple[Path, int]] = []
        for entry in entries:
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
                if entry.name.lower() in SKIPPED_DIRECTORY_NAMES:
                    continue
                directories.append((path, depth + 1))
                continue
            if path.suffix.lower() != ".json" or not _route_related(root, path):
                continue
            if not _safe_candidate(info):
                saw_permission_rejection = True
                continue
            if schema_files_checked >= MAX_SCHEMA_FILES_CHECKED:
                scan_truncated = True
                break
            schema_files_checked += 1
            has_auth_keyset = _candidate_has_auth_keyset(path)
            if has_auth_keyset is None:
                saw_permission_rejection = True
                continue
            if not has_auth_keyset:
                saw_schema_rejection = True
                continue
            if auth_value_candidates_opened >= MAX_AUTH_VALUE_CANDIDATES_OPENED:
                scan_truncated = True
                break
            auth_value_candidates_opened += 1
            facts["candidate_credential_values_used_in_memory_only"] = True
            match = _read_candidate_auth_target(path)
            if match is True:
                matched_sources += 1
            elif match is False:
                saw_schema_rejection = True
            else:
                saw_permission_rejection = True
        for child, child_depth in reversed(sorted(directories, key=lambda item: (not _route_related(root, item[0]), item[0].name.lower()))):
            stack.append((child, child_depth))

    facts["bounded_scan_state"] = "TRUNCATED_REDACTED" if scan_truncated else "COMPLETED"
    if scan_truncated:
        facts["provider_auth_route_source_state"] = "SCAN_LIMIT_REACHED_REDACTED"
    elif matched_sources == 1:
        facts["provider_auth_route_source_state"] = "RESOLVED_IN_MEMORY"
        facts["provider_auth_route_source_ready"] = True
    elif matched_sources > 1:
        facts["provider_auth_route_source_state"] = "AMBIGUOUS_REDACTED"
    elif saw_schema_rejection:
        facts["provider_auth_route_source_state"] = "SCHEMA_REJECTED_REDACTED"
    elif saw_permission_rejection:
        facts["provider_auth_route_source_state"] = "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    else:
        facts["provider_auth_route_source_state"] = "NOT_AVAILABLE_REDACTED"
    return facts


def evaluate_resolver(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["provider_auth_route_source_ready"])
    checks = [
        {"id": "PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER_COMPLETED", "passed": True},
        {"id": "PROTECTED_PROVIDER_AUTH_ROUTE_SOURCE_READY", "passed": ready},
        {"id": "OUTBOUND_PROVIDER_SSH_GITHUB_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_PROVIDER_AUTH_ROUTE_READY_FOR_SEPARATE_MANAGEMENT_PLANE_GET_PHASE" if ready else "CURRENT_PRODUCTION_PROVIDER_AUTH_ROUTE_NOT_AVAILABLE_NO_REMOTE_ACTION_AUTHORIZED",
        "provider_auth_route_resolved": ready,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "provider_auth_route_state": facts["provider_auth_route_source_state"],
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_resolver(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("provider_auth_route_resolved", "outbound_operations_not_attempted")) or result["core_start_authorized"] is not False:
        raise CurrentProductionProtectedProviderAuthRouteResolverError("resolver authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionProtectedProviderAuthRouteResolverError("resolver checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "provider_auth_route_resolved": result["provider_auth_route_resolved"],
        "outbound_operations_not_attempted": result["outbound_operations_not_attempted"],
        "core_start_authorized": False,
        "provider_auth_route_state": result["provider_auth_route_state"],
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
        "decision": "CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "provider_auth_route_resolved": False,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "provider_auth_route_state": "INPUT_INVALID_REDACTED",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER_INPUT_FAILED"],
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
        receipt = build_receipt(load_contract(args.contract), locate_provider_auth_recovery_route(args.protected_root))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionProtectedProviderAuthRouteResolverError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
