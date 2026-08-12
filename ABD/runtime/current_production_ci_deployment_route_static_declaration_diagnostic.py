#!/usr/bin/env python3
"""Classify whether a current-production CI deployment route is statically declared."""

from __future__ import annotations

import argparse
import json
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from current_production_protected_target_metadata_locator import KeyOnlyJsonError, _top_level_json_keys


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC"
WORKFLOW_RELATIVE_PATH = Path(".github/workflows/abd-stage0-validation.yml")
DECLARATION_SPECS = (
    (
        Path("ABD/release_pipeline.yml"),
        frozenset({"candidate_slots", "entry_conditions", "stages", "rollback_policy", "external_effect_boundary"}),
    ),
    (
        Path("ABD/release_slots.json"),
        frozenset({"production_activation", "routing", "promotion_protocol", "rollback", "external_effect_boundary"}),
    ),
    (
        Path("ABD/recovery_actions.json"),
        frozenset({"claim_boundary", "actions"}),
    ),
)
MAX_WORKFLOW_HEADER_BYTES = 32768
MAX_WORKFLOW_HEADER_LINES = 96
MAX_DECLARATION_FILE_BYTES = 32768

ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
WORKFLOW_STATES = {"OBSERVED_REDACTED", "UNAVAILABLE_REDACTED", "UNSAFE_REJECTED_REDACTED", "INCOMPLETE_REDACTED", "NOT_ATTEMPTED"}
DECLARATION_SURFACE_STATES = {"OBSERVED_REDACTED", "UNAVAILABLE_REDACTED", "UNSAFE_REJECTED_REDACTED", "SCHEMA_INCOMPLETE_REDACTED", "NOT_ATTEMPTED"}
ROUTE_STATES = {"DECLARED_REDACTED", "NOT_DECLARED_REDACTED", "UNAVAILABLE_REDACTED"}
TRIGGER_NAMES = {"push", "pull_request", "workflow_dispatch", "workflow_call", "schedule"}
REF_COLLECTION_NAMES = {"branches", "branches-ignore", "tags", "tags-ignore"}
CURRENT_PRODUCTION_NAME = re.compile(r"\bcurrent[-_ ]?production\b|\bproduction\b", re.IGNORECASE)
ROUTE_NAME = re.compile(r"\bdeploy(?:ment)?\b|\brecover(?:y)?\b|\brollback\b", re.IGNORECASE)


class CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError(ValueError):
    """Raised when diagnostic input or a redacted fact violates its contract."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError) as exc:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "CI deployment-route static declaration diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "CI deployment-route static declaration facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CI-DEPLOYMENT-ROUTE-STATIC-DECLARATION-DIAGNOSTIC-001":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("diagnostic must remain read-only")
    expected = {
        "workflow_relative_path": ".github/workflows/abd-stage0-validation.yml",
        "static_declaration_relative_paths": ["ABD/release_pipeline.yml", "ABD/release_slots.json", "ABD/recovery_actions.json"],
        "maximum_workflow_header_bytes": MAX_WORKFLOW_HEADER_BYTES,
        "maximum_workflow_header_lines": MAX_WORKFLOW_HEADER_LINES,
        "maximum_static_declaration_file_bytes": MAX_DECLARATION_FILE_BYTES,
        "github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "worktree_static_text_read_only": True,
        "workflow_header_and_branch_ref_triggers_only": True,
        "workflow_job_command_content_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "static_source_path_or_raw_content_emitted_or_persisted": False,
        "github_api_request_sent": False,
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
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_ONLY_NOT_ACTUAL_CI_AUTHORIZATION_GITHUB_PROVIDER_QUERY_RESOURCE_STATE_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_WORKFLOW_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "workflow_header_state",
        "workflow_trigger_surface_observed",
        "workflow_managed_branch_or_ref_trigger_observed",
        "workflow_explicit_current_production_route_observed",
        "release_recovery_static_surface_state",
        "release_recovery_static_surface_observed",
        "current_production_ci_deployment_route_state",
        "current_production_ci_deployment_route_declared",
        "workflow_job_command_content_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "static_source_path_or_raw_content_emitted_or_persisted",
        "github_api_requests",
        "provider_api_requests",
        "ssh_connections_attempted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("repository root state is invalid")
    if facts.get("workflow_header_state") not in WORKFLOW_STATES:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("workflow header state is invalid")
    if facts.get("release_recovery_static_surface_state") not in DECLARATION_SURFACE_STATES:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("release recovery surface state is invalid")
    if facts.get("current_production_ci_deployment_route_state") not in ROUTE_STATES:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("deployment route state is invalid")
    for field in (
        "workflow_trigger_surface_observed",
        "workflow_managed_branch_or_ref_trigger_observed",
        "workflow_explicit_current_production_route_observed",
        "release_recovery_static_surface_observed",
        "current_production_ci_deployment_route_declared",
    ):
        if type(facts.get(field)) is not bool:
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("diagnostic boolean state is invalid")
    for field in (
        "workflow_job_command_content_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "credential_config_or_runtime_secret_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "static_source_path_or_raw_content_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("redaction boundary is invalid")
    for field in ("github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("outbound operation count is invalid")

    root_state = facts["repository_root_state"]
    workflow_state = facts["workflow_header_state"]
    surface_state = facts["release_recovery_static_surface_state"]
    route_state = facts["current_production_ci_deployment_route_state"]
    declared = facts["current_production_ci_deployment_route_declared"]
    if root_state != "AVAILABLE_READ_ONLY":
        if workflow_state != "NOT_ATTEMPTED" or surface_state != "NOT_ATTEMPTED" or route_state != "UNAVAILABLE_REDACTED" or declared:
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("unavailable root facts are inconsistent")
        return
    if workflow_state == "NOT_ATTEMPTED" or surface_state == "NOT_ATTEMPTED":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("available root facts are inconsistent")
    if workflow_state != "OBSERVED_REDACTED" and (facts["workflow_trigger_surface_observed"] or facts["workflow_managed_branch_or_ref_trigger_observed"] or facts["workflow_explicit_current_production_route_observed"]):
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("unavailable workflow facts are inconsistent")
    if surface_state != "OBSERVED_REDACTED" and facts["release_recovery_static_surface_observed"]:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("unavailable declaration facts are inconsistent")
    if route_state == "DECLARED_REDACTED":
        if not declared or workflow_state != "OBSERVED_REDACTED" or surface_state != "OBSERVED_REDACTED":
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("declared route facts are inconsistent")
        if not (facts["workflow_trigger_surface_observed"] and facts["workflow_managed_branch_or_ref_trigger_observed"] and facts["workflow_explicit_current_production_route_observed"] and facts["release_recovery_static_surface_observed"]):
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("declared route evidence is incomplete")
    elif declared:
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("undeclared route cannot be authorized")
    elif workflow_state != "OBSERVED_REDACTED" or surface_state != "OBSERVED_REDACTED":
        if route_state != "UNAVAILABLE_REDACTED":
            raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("incomplete static evidence must remain unavailable")
    elif route_state != "NOT_DECLARED_REDACTED":
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("complete static evidence must be classified")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "workflow_header_state": "NOT_ATTEMPTED",
        "workflow_trigger_surface_observed": False,
        "workflow_managed_branch_or_ref_trigger_observed": False,
        "workflow_explicit_current_production_route_observed": False,
        "release_recovery_static_surface_state": "NOT_ATTEMPTED",
        "release_recovery_static_surface_observed": False,
        "current_production_ci_deployment_route_state": "UNAVAILABLE_REDACTED",
        "current_production_ci_deployment_route_declared": False,
        "workflow_job_command_content_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "static_source_path_or_raw_content_emitted_or_persisted": False,
        "github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }


def _safe_regular_file_state(path: Path, maximum_bytes: int) -> str:
    try:
        info = path.lstat()
    except OSError:
        return "UNAVAILABLE_REDACTED"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "UNSAFE_REJECTED_REDACTED"
    if (info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)) != 0 or info.st_size <= 0 or info.st_size > maximum_bytes:
        return "UNSAFE_REJECTED_REDACTED"
    return "AVAILABLE_READ_ONLY"


def _managed_ref_observed(text: str) -> bool:
    normalized = text.strip().strip("[]").replace('"', "").replace("'", "").lower()
    return any(token in normalized for token in ("main", "release", "refs/heads/", "refs/tags/", "v*"))


def _workflow_header_signals(path: Path) -> tuple[str, bool, bool, bool]:
    state = _safe_regular_file_state(path, MAX_WORKFLOW_HEADER_BYTES)
    if state != "AVAILABLE_READ_ONLY":
        return state, False, False, False
    saw_name = False
    saw_on = False
    saw_jobs = False
    trigger_names: set[str] = set()
    managed_ref = False
    explicit_route = False
    active_ref_collection = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if line_number > MAX_WORKFLOW_HEADER_LINES:
                    return "INCOMPLETE_REDACTED", False, False, False
                if raw_line.startswith("jobs:"):
                    saw_jobs = True
                    break
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                indent = len(raw_line) - len(raw_line.lstrip(" "))
                if indent == 0 and stripped.startswith("name:"):
                    saw_name = True
                    name = stripped.partition(":")[2].strip().strip("\"'")
                    explicit_route = bool("abd" in name.lower() and CURRENT_PRODUCTION_NAME.search(name) and ROUTE_NAME.search(name))
                    active_ref_collection = False
                    continue
                if indent == 0 and stripped == "on:":
                    saw_on = True
                    active_ref_collection = False
                    continue
                if indent == 2 and stripped.endswith(":") and stripped[:-1] in TRIGGER_NAMES:
                    trigger_names.add(stripped[:-1])
                    active_ref_collection = False
                    continue
                if stripped.split(":", 1)[0] in REF_COLLECTION_NAMES and ":" in stripped:
                    active_ref_collection = True
                    managed_ref = managed_ref or _managed_ref_observed(stripped.partition(":")[2])
                    continue
                if active_ref_collection and stripped.startswith("- "):
                    managed_ref = managed_ref or _managed_ref_observed(stripped[2:])
                    continue
                if indent <= 2:
                    active_ref_collection = False
    except (OSError, UnicodeDecodeError):
        return "INCOMPLETE_REDACTED", False, False, False
    if not (saw_name and saw_on and saw_jobs and trigger_names):
        return "INCOMPLETE_REDACTED", False, False, False
    return "OBSERVED_REDACTED", True, managed_ref, explicit_route


def _release_recovery_surface_state(repo_root: Path) -> tuple[str, bool]:
    for relative, required_keys in DECLARATION_SPECS:
        state = _safe_regular_file_state(repo_root / relative, MAX_DECLARATION_FILE_BYTES)
        if state == "UNAVAILABLE_REDACTED":
            return "UNAVAILABLE_REDACTED", False
        if state != "AVAILABLE_READ_ONLY":
            return "UNSAFE_REJECTED_REDACTED", False
        try:
            keys = _top_level_json_keys(repo_root / relative)
        except (OSError, KeyOnlyJsonError):
            return "SCHEMA_INCOMPLETE_REDACTED", False
        if not required_keys.issubset(keys):
            return "SCHEMA_INCOMPLETE_REDACTED", False
    return "OBSERVED_REDACTED", True


def discover_static_declaration(repo_root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Read only fixed static declaration surfaces, retaining no source values."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    workflow_state, trigger_observed, managed_ref_observed, explicit_route_observed = _workflow_header_signals(repo_root / WORKFLOW_RELATIVE_PATH)
    facts["workflow_header_state"] = workflow_state
    facts["workflow_trigger_surface_observed"] = trigger_observed
    facts["workflow_managed_branch_or_ref_trigger_observed"] = managed_ref_observed
    facts["workflow_explicit_current_production_route_observed"] = explicit_route_observed
    surface_state, surface_observed = _release_recovery_surface_state(repo_root)
    facts["release_recovery_static_surface_state"] = surface_state
    facts["release_recovery_static_surface_observed"] = surface_observed
    if workflow_state == "OBSERVED_REDACTED" and surface_state == "OBSERVED_REDACTED":
        declared = trigger_observed and managed_ref_observed and explicit_route_observed and surface_observed
        facts["current_production_ci_deployment_route_declared"] = declared
        facts["current_production_ci_deployment_route_state"] = "DECLARED_REDACTED" if declared else "NOT_DECLARED_REDACTED"
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    scope_completed = facts["repository_root_state"] == "AVAILABLE_READ_ONLY" and facts["workflow_header_state"] == "OBSERVED_REDACTED" and facts["release_recovery_static_surface_state"] == "OBSERVED_REDACTED"
    declared = bool(facts["current_production_ci_deployment_route_declared"])
    checks = [
        {"id": "STATIC_DECLARATION_SCOPE_COMPLETED", "passed": scope_completed},
        {"id": "ABD_CI_WORKFLOW_TRIGGER_SURFACE_OBSERVED", "passed": bool(facts["workflow_trigger_surface_observed"])},
        {"id": "ABD_RELEASE_RECOVERY_STATIC_SURFACE_OBSERVED", "passed": bool(facts["release_recovery_static_surface_observed"])},
        {"id": "EXPLICIT_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_DECLARED", "passed": declared},
        {"id": "OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATICALLY_DECLARED_SEPARATE_CI_AUTHORIZATION_EVIDENCE_REQUIRED" if declared else "CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_NOT_DECLARED_NO_REMOTE_ACTION_AUTHORIZED",
        "current_production_ci_deployment_route_declared": declared,
        "current_production_ci_deployment_route_state": facts["current_production_ci_deployment_route_state"],
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["current_production_ci_deployment_route_declared"], bool):
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "current_production_ci_deployment_route_declared": result["current_production_ci_deployment_route_declared"],
        "current_production_ci_deployment_route_state": result["current_production_ci_deployment_route_state"],
        "outbound_operations_not_attempted": result["outbound_operations_not_attempted"],
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
        "decision": "CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "current_production_ci_deployment_route_declared": False,
        "current_production_ci_deployment_route_state": "UNAVAILABLE_REDACTED",
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "workflow_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), discover_static_declaration(args.repo_root))
    except (CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
