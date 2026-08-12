#!/usr/bin/env python3
"""Resolve one redacted README-declared protected target-metadata pointer."""

from __future__ import annotations

import argparse
import json
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from current_production_protected_target_metadata_locator import (
    MAX_CANDIDATE_BYTES,
    _candidate_schema_is_nonsecret_target_metadata,
    _is_candidate,
    _top_level_json_keys,
)


PASS_STATUS = "PASS_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER"
README_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_README_REJECTED_REDACTED"}
POINTER_STATES = {"RESOLVED_IN_MEMORY", "NOT_DECLARED_REDACTED", "AMBIGUOUS_REDACTED", "INVALID_DECLARATION_REDACTED", "NOT_ATTEMPTED"}
SOURCE_STATES = {"RESOLVED_IN_MEMORY", "NOT_ATTEMPTED", "UNAVAILABLE_REDACTED", "PERMISSION_BOUNDARY_REJECTED_REDACTED", "SCHEMA_INCOMPLETE_REDACTED"}
POINTER_PATTERN = re.compile(r"`(_protected/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*\.json)`")


class CurrentProductionReadmeProtectedSourcePointerResolverError(ValueError):
    """Raised when a resolver contract or redacted fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionReadmeProtectedSourcePointerResolverError) as exc:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "README protected source pointer resolver contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted README protected source pointer facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-README-PROTECTED-SOURCE-POINTER-RESOLVER-001":
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER_READ_ONLY":
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("resolver must remain read-only")
    expected = {
        "pointer_encoding": "SINGLE_INLINE_CODE_RELATIVE_PROTECTED_JSON_PATH",
        "maximum_declared_pointers": 1,
        "maximum_candidate_bytes": 65536,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("resolver expectations are not exact")
    boundary = {
        "root_readme_read_only": True,
        "only_single_inline_nonsecret_relative_pointer_form_accepted": True,
        "protected_source_opened_only_after_exact_readme_pointer": True,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "readme_text_pointer_or_protected_path_emitted_or_persisted": False,
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
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER_ONLY_NOT_CREDENTIAL_DISCOVERY_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_README_PROTECTED_SOURCE_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "root_readme_state",
        "pointer_declaration_state",
        "protected_metadata_source_state",
        "pointer_target_source_ready",
        "candidate_schema_keys_read_in_memory_only",
        "candidate_json_values_parsed_or_persisted",
        "credential_material_read_emitted_or_persisted",
        "target_value_read_emitted_or_persisted",
        "readme_text_pointer_or_protected_path_emitted_or_persisted",
        "provider_api_requests",
        "ssh_connections_attempted",
        "github_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER":
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("facts observation date is invalid") from exc
    if facts.get("root_readme_state") not in README_STATES:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("README state is invalid")
    if facts.get("pointer_declaration_state") not in POINTER_STATES:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("pointer declaration state is invalid")
    if facts.get("protected_metadata_source_state") not in SOURCE_STATES:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("protected source state is invalid")
    if type(facts.get("pointer_target_source_ready")) is not bool or type(facts.get("candidate_schema_keys_read_in_memory_only")) is not bool:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("resolver boolean state is invalid")
    for field in (
        "candidate_json_values_parsed_or_persisted",
        "credential_material_read_emitted_or_persisted",
        "target_value_read_emitted_or_persisted",
        "readme_text_pointer_or_protected_path_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionReadmeProtectedSourcePointerResolverError("redaction boundary is invalid")
    for field in ("provider_api_requests", "ssh_connections_attempted", "github_api_requests"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionReadmeProtectedSourcePointerResolverError("outbound operation count is invalid")

    root_state = facts["root_readme_state"]
    pointer_state = facts["pointer_declaration_state"]
    source_state = facts["protected_metadata_source_state"]
    ready = facts["pointer_target_source_ready"]
    if root_state != "AVAILABLE_READ_ONLY":
        if pointer_state != "NOT_ATTEMPTED" or source_state != "NOT_ATTEMPTED" or ready or facts["candidate_schema_keys_read_in_memory_only"]:
            raise CurrentProductionReadmeProtectedSourcePointerResolverError("unavailable README facts are inconsistent")
    elif pointer_state == "RESOLVED_IN_MEMORY":
        if ready != (source_state == "RESOLVED_IN_MEMORY"):
            raise CurrentProductionReadmeProtectedSourcePointerResolverError("resolved pointer facts are inconsistent")
    else:
        if source_state != "NOT_ATTEMPTED" or ready or facts["candidate_schema_keys_read_in_memory_only"]:
            raise CurrentProductionReadmeProtectedSourcePointerResolverError("unresolved pointer facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER",
        "observed_on": observed_on,
        "root_readme_state": "UNAVAILABLE_REDACTED",
        "pointer_declaration_state": "NOT_ATTEMPTED",
        "protected_metadata_source_state": "NOT_ATTEMPTED",
        "pointer_target_source_ready": False,
        "candidate_schema_keys_read_in_memory_only": False,
        "candidate_json_values_parsed_or_persisted": False,
        "credential_material_read_emitted_or_persisted": False,
        "target_value_read_emitted_or_persisted": False,
        "readme_text_pointer_or_protected_path_emitted_or_persisted": False,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "github_api_requests": 0,
        "browser_login_submitted": False,
    }


def _safe_pointed_source(protected_root: Path, pointer: str) -> tuple[Path | None, str | None]:
    relative = Path(pointer)
    if relative.parts[:1] != ("_protected",) or ".." in relative.parts:
        return None, "INVALID_DECLARATION_REDACTED"
    source = protected_root.joinpath(*relative.parts[1:])
    if not _is_candidate(protected_root, source):
        return None, "INVALID_DECLARATION_REDACTED"
    ancestor = protected_root
    for part in relative.parts[1:]:
        ancestor = ancestor / part
        try:
            info = ancestor.lstat()
        except OSError:
            return None, "UNAVAILABLE_REDACTED"
        if stat.S_ISLNK(info.st_mode):
            return None, "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    try:
        info = source.lstat()
    except OSError:
        return None, "UNAVAILABLE_REDACTED"
    if not stat.S_ISREG(info.st_mode):
        return None, "UNAVAILABLE_REDACTED"
    if (info.st_mode & (stat.S_IRWXG | stat.S_IRWXO)) != 0 or info.st_size > MAX_CANDIDATE_BYTES:
        return None, "PERMISSION_BOUNDARY_REJECTED_REDACTED"
    return source, None


def resolve_readme_protected_source_pointer(readme: Path, protected_root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Resolve exactly one README-declared nonsecret protected metadata source."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    try:
        readme_info = readme.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(readme_info.st_mode) or not stat.S_ISREG(readme_info.st_mode):
        facts["root_readme_state"] = "UNSAFE_README_REJECTED_REDACTED"
        return facts
    expected_root = readme.parent / "_protected"
    if protected_root.absolute() != expected_root.absolute():
        facts["root_readme_state"] = "UNSAFE_README_REJECTED_REDACTED"
        return facts
    try:
        readme_text = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        facts["root_readme_state"] = "UNSAFE_README_REJECTED_REDACTED"
        return facts

    facts["root_readme_state"] = "AVAILABLE_READ_ONLY"
    pointers = set(POINTER_PATTERN.findall(readme_text))
    if not pointers:
        facts["pointer_declaration_state"] = "NOT_DECLARED_REDACTED"
        return facts
    if len(pointers) != 1:
        facts["pointer_declaration_state"] = "AMBIGUOUS_REDACTED"
        return facts
    pointer = next(iter(pointers))
    try:
        root_info = protected_root.lstat()
    except OSError:
        facts["pointer_declaration_state"] = "RESOLVED_IN_MEMORY"
        facts["protected_metadata_source_state"] = "UNAVAILABLE_REDACTED"
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["root_readme_state"] = "UNSAFE_README_REJECTED_REDACTED"
        facts["pointer_declaration_state"] = "NOT_ATTEMPTED"
        return facts
    source, source_state = _safe_pointed_source(protected_root, pointer)
    if source is None:
        if source_state == "INVALID_DECLARATION_REDACTED":
            facts["pointer_declaration_state"] = "INVALID_DECLARATION_REDACTED"
        else:
            facts["pointer_declaration_state"] = "RESOLVED_IN_MEMORY"
            facts["protected_metadata_source_state"] = source_state or "UNAVAILABLE_REDACTED"
        return facts

    facts["pointer_declaration_state"] = "RESOLVED_IN_MEMORY"
    facts["candidate_schema_keys_read_in_memory_only"] = True
    try:
        keys = _top_level_json_keys(source)
    except ValueError:
        facts["protected_metadata_source_state"] = "SCHEMA_INCOMPLETE_REDACTED"
        return facts
    if not _candidate_schema_is_nonsecret_target_metadata(keys):
        facts["protected_metadata_source_state"] = "SCHEMA_INCOMPLETE_REDACTED"
        return facts
    facts["protected_metadata_source_state"] = "RESOLVED_IN_MEMORY"
    facts["pointer_target_source_ready"] = True
    return facts


def evaluate_resolver(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["pointer_target_source_ready"])
    checks = [
        {"id": "README_PROTECTED_SOURCE_POINTER_RESOLVER_COMPLETED", "passed": True},
        {"id": "README_DECLARED_PROTECTED_TARGET_SOURCE_READY", "passed": ready},
        {"id": "OUTBOUND_PROVIDER_SSH_GITHUB_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "README_DECLARED_TARGET_SOURCE_READY_FOR_SEPARATE_COMBINED_SOURCE_COMPATIBILITY_PHASE" if ready else "README_DECLARED_TARGET_SOURCE_NOT_READY_NO_TRANSPORT_PROVIDER_OR_HOST_ACTION_AUTHORIZED",
        "readme_declared_target_source_located": ready,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "readme_declared_target_source_state": facts["protected_metadata_source_state"] if facts["pointer_declaration_state"] == "RESOLVED_IN_MEMORY" else facts["pointer_declaration_state"],
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_resolver(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("readme_declared_target_source_located", "outbound_operations_not_attempted")) or result["core_start_authorized"] is not False:
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("resolver authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionReadmeProtectedSourcePointerResolverError("resolver checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "readme_declared_target_source_located": result["readme_declared_target_source_located"],
        "outbound_operations_not_attempted": result["outbound_operations_not_attempted"],
        "core_start_authorized": False,
        "readme_declared_target_source_state": result["readme_declared_target_source_state"],
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
        "decision": "CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "readme_declared_target_source_located": False,
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "readme_declared_target_source_state": "INPUT_INVALID_REDACTED",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_README_PROTECTED_SOURCE_POINTER_RESOLVER_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "readme_protected_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--protected-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        facts = resolve_readme_protected_source_pointer(args.readme, args.protected_root)
        receipt = build_receipt(load_contract(args.contract), facts)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionReadmeProtectedSourcePointerResolverError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
