#!/usr/bin/env python3
"""Statically reconcile a fixed rebuild-metadata subdomain with a repair source declaration."""

from __future__ import annotations

import argparse
import ast
import json
import stat
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC"
REBUILD_METADATA_SUBDOMAIN = "CURRENT_RELEASE_REBUILD_METADATA_INCOMPLETE_REDACTED"
REPAIR_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-BLUE-RELEASE-REPAIR-001"
REPAIR_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_NO_CORE_ACTIVATION"
REPAIR_RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR"
REPAIR_SOURCE_CONSTANTS = {
    "RECEIPT_TYPE": REPAIR_RECEIPT_TYPE,
    "INFRA_SOURCE_PATHS": ["infra/config.schema.json", "infra/rebuild.sh"],
}
REPAIR_SOURCE_FUNCTIONS = frozenset({"source_bundle_paths", "validate_contract", "evaluate_repair", "build_receipt"})
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
PROVENANCE_STATES = {
    "REPAIR_CONTRACT_UNAVAILABLE_REDACTED",
    "REPAIR_CONTRACT_REJECTED_REDACTED",
    "REPAIR_SOURCE_UNAVAILABLE_REDACTED",
    "REPAIR_SOURCE_REJECTED_REDACTED",
    "SOURCE_PROVENANCE_NOT_DECLARED_REDACTED",
    "SOURCE_PROVENANCE_DECLARED_REDACTED",
}


class CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError(ValueError):
    """Raised when the static provenance reconciliation input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("%s must be an object" % name)
    return value


def _safe_regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _read_text(path: Path) -> str:
    if not _safe_regular_file(path):
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError) as exc:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "rebuild metadata source-repair provenance reconciliation diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "rebuild metadata source-repair provenance reconciliation facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-SOURCE-REPAIR-PROVENANCE-RECONCILIATION-DIAGNOSTIC-001":
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC_STATIC_READ_ONLY":
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("diagnostic must remain static read-only")
    expected = {
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "repair_contract_id": REPAIR_CONTRACT_ID,
        "repair_contract_status": REPAIR_CONTRACT_STATUS,
        "repair_receipt_type": REPAIR_RECEIPT_TYPE,
        "repair_source_constant_names": sorted(REPAIR_SOURCE_CONSTANTS),
        "repair_source_function_names": sorted(REPAIR_SOURCE_FUNCTIONS),
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "fixed_local_repair_contract_read_only": True,
        "fixed_local_repair_source_ast_read_only": True,
        "repair_source_executed": False,
        "rebuild_script_content_read": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_request_sent": False,
        "provider_api_request_sent": False,
        "ssh_connection_attempted": False,
        "browser_login_submitted": False,
        "workflow_dispatched_or_pushed": False,
        "provider_resource_network_cloudflare_host_or_service_changed": False,
        "repair_deployment_or_core_start_attempted": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_ONLY_NOT_HOST_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_SOURCE_EXECUTION_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "repair_contract_state",
        "repair_source_state",
        "rebuild_metadata_source_repair_provenance_state",
        "source_provenance_declared",
        "repair_source_executed",
        "rebuild_script_content_read",
        "config_runtime_or_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_repair_command_read_or_persisted",
        "private_object_path_hash_or_raw_content_read_or_persisted",
        "product_github_api_requests",
        "provider_api_requests",
        "ssh_connections_attempted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC":
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("repository root state is invalid")
    if facts.get("repair_contract_state") not in {"OBSERVED_STATIC", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("repair contract state is invalid")
    if facts.get("repair_source_state") not in {"OBSERVED_STATIC", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("repair source state is invalid")
    if facts.get("rebuild_metadata_source_repair_provenance_state") not in PROVENANCE_STATES or type(facts.get("source_provenance_declared")) is not bool:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("provenance state is invalid")
    declared = facts["rebuild_metadata_source_repair_provenance_state"] == "SOURCE_PROVENANCE_DECLARED_REDACTED"
    if facts["source_provenance_declared"] is not declared:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("provenance declaration is inconsistent")
    for field in (
        "repair_source_executed",
        "rebuild_script_content_read",
        "config_runtime_or_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_repair_command_read_or_persisted",
        "private_object_path_hash_or_raw_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("static boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("outbound operation count is invalid")
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        if facts["repair_contract_state"] != "NOT_ATTEMPTED" or facts["repair_source_state"] != "NOT_ATTEMPTED":
            raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("unavailable root facts are inconsistent")
    if declared and (facts["repair_contract_state"] != "OBSERVED_STATIC" or facts["repair_source_state"] != "OBSERVED_STATIC"):
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("declared provenance source state is inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "repair_contract_state": "NOT_ATTEMPTED",
        "repair_source_state": "NOT_ATTEMPTED",
        "rebuild_metadata_source_repair_provenance_state": "REPAIR_CONTRACT_UNAVAILABLE_REDACTED",
        "source_provenance_declared": False,
        "repair_source_executed": False,
        "rebuild_script_content_read": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }


def _repair_contract_declares_rebuild_metadata_repair(contract: Mapping[str, Any]) -> bool:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required or contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != REPAIR_CONTRACT_ID or contract.get("product_version") != "0.0.0.1" or contract.get("status") != REPAIR_CONTRACT_STATUS:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("repair contract identity is invalid")
    expected = _object(contract.get("expected"), "repair expected")
    source_profile = _object(expected.get("source_bundle_profile"), "source bundle profile")
    missing_before = _object(expected.get("missing_before_repair"), "missing before repair")
    boundary = _object(contract.get("source_boundary"), "repair source boundary")
    rollback = _object(contract.get("rollback"), "repair rollback")
    if source_profile.get("infra_paths") != REPAIR_SOURCE_CONSTANTS["INFRA_SOURCE_PATHS"] or missing_before.get("rebuild_file_kind") != "missing":
        return False
    return boundary.get("local_nonsecret_source_bundle_read") is True and boundary.get("release_nonsecret_files_added") is True and boundary.get("unit_created_enabled_or_started") is False and rollback.get("current_symlink_preserved") is True and rollback.get("shadow_runtime_preserved") is True


def _literal_assignments_and_functions(source: str) -> tuple[dict[str, object], set[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("repair source AST is invalid") from exc
    values: dict[str, object] = {}
    functions: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in REPAIR_SOURCE_CONSTANTS:
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                values[node.targets[0].id] = None
    return values, functions


def _repair_source_declares_rebuild_metadata_repair(source: str) -> bool:
    assignments, functions = _literal_assignments_and_functions(source)
    return assignments == REPAIR_SOURCE_CONSTANTS and REPAIR_SOURCE_FUNCTIONS <= functions


def discover_static_provenance(repo_root: Path, repair_contract_path: Path, repair_source_path: Path, observed_on: str) -> dict[str, Any]:
    """Read only fixed local contract and source declaration surfaces."""

    facts = _base_facts(observed_on)
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    try:
        repair_contract = _load(repair_contract_path, "repair contract")
    except CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError:
        facts["repair_contract_state"] = "UNAVAILABLE_REDACTED"
        return facts
    try:
        contract_declared = _repair_contract_declares_rebuild_metadata_repair(repair_contract)
    except CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError:
        facts["repair_contract_state"] = "REJECTED_REDACTED"
        facts["rebuild_metadata_source_repair_provenance_state"] = "REPAIR_CONTRACT_REJECTED_REDACTED"
        return facts
    facts["repair_contract_state"] = "OBSERVED_STATIC"
    try:
        source = _read_text(repair_source_path)
    except (OSError, UnicodeDecodeError, CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError):
        facts["repair_source_state"] = "UNAVAILABLE_REDACTED"
        facts["rebuild_metadata_source_repair_provenance_state"] = "REPAIR_SOURCE_UNAVAILABLE_REDACTED"
        return facts
    try:
        source_declared = _repair_source_declares_rebuild_metadata_repair(source)
    except CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError:
        facts["repair_source_state"] = "REJECTED_REDACTED"
        facts["rebuild_metadata_source_repair_provenance_state"] = "REPAIR_SOURCE_REJECTED_REDACTED"
        return facts
    facts["repair_source_state"] = "OBSERVED_STATIC"
    if contract_declared and source_declared:
        facts["rebuild_metadata_source_repair_provenance_state"] = "SOURCE_PROVENANCE_DECLARED_REDACTED"
        facts["source_provenance_declared"] = True
    else:
        facts["rebuild_metadata_source_repair_provenance_state"] = "SOURCE_PROVENANCE_NOT_DECLARED_REDACTED"
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    declared = bool(facts["source_provenance_declared"])
    checks = [
        {"id": "REPAIR_CONTRACT_STATICLY_OBSERVED", "passed": facts["repair_contract_state"] == "OBSERVED_STATIC"},
        {"id": "REPAIR_SOURCE_STATICLY_OBSERVED", "passed": facts["repair_source_state"] == "OBSERVED_STATIC"},
        {"id": "REBUILD_METADATA_SOURCE_PROVENANCE_DECLARED", "passed": declared},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_PROVENANCE_DECLARED_NO_HOST_REPAIR_OR_CORE_ACTION_AUTHORIZED" if declared else "CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_PROVENANCE_NOT_DECLARED_NO_HOST_REPAIR_OR_CORE_ACTION_AUTHORIZED",
        "source_provenance_declared": declared,
        "source_provenance_state": facts["rebuild_metadata_source_repair_provenance_state"],
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["source_provenance_declared"], bool):
        raise CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError("diagnostic authorization state is invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "source_provenance_declared": result["source_provenance_declared"],
        "source_provenance_state": result["source_provenance_state"],
        "product_outbound_operations_not_attempted": True,
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
        "decision": "CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "source_provenance_declared": False,
        "source_provenance_state": "REPAIR_CONTRACT_UNAVAILABLE_REDACTED",
        "product_outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "source_or_external_state_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--repair-contract", type=Path, required=True)
    parser.add_argument("--repair-source", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), discover_static_provenance(args.repo_root, args.repair_contract, args.repair_source, args.observed_on))
    except (CurrentProductionRebuildMetadataSourceRepairProvenanceReconciliationDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
