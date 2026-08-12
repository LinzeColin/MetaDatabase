#!/usr/bin/env python3
"""Fail closed on independent current evidence before any rebuild-metadata repair execution."""

from __future__ import annotations

import argparse
import json
import stat
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC"
REBUILD_METADATA_SUBDOMAIN = "CURRENT_RELEASE_REBUILD_METADATA_INCOMPLETE_REDACTED"
PROVENANCE_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-SOURCE-REPAIR-PROVENANCE-RECONCILIATION-DIAGNOSTIC-001"
PROVENANCE_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC_STATIC_READ_ONLY"
CORE_PREFLIGHT_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-PREFLIGHT-001"
CORE_PREFLIGHT_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_READ_ONLY"
REQUIRED_INDEPENDENT_EVIDENCE_IDS = (
    "SOURCE_REPAIR_PROVENANCE_CURRENT",
    "CURRENT_HOST_METADATA_CURRENT",
    "FROZEN_CONFIG_SEMANTIC_CHECK_CURRENT",
    "ROLLBACK_INPUT_CURRENT",
    "CORE_CAPACITY_CURRENT",
    "CONTROLLED_ENTRY_CURRENT",
    "MANAGEMENT_PLANE_CURRENT",
    "SSH_TRANSPORT_CURRENT",
    "CORE_EXECUTION_CONTRACT_CURRENT",
)
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
STATIC_CONTRACT_STATES = {"OBSERVED_STATIC", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}
ADMISSION_STATES = {"STATIC_INPUT_REJECTED_REDACTED", "HOST_EVIDENCE_REQUIRED_REDACTED"}
REQUIREMENT_STATES = {"STATIC_INPUT_REJECTED_REDACTED", "ALL_INDEPENDENT_EVIDENCE_REQUIRED_REDACTED"}


class CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError(ValueError):
    """Raised when a static admission-contract input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("%s must be an object" % name)
    return value


def _safe_regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _read_text(path: Path) -> str:
    if not _safe_regular_file(path):
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError) as exc:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "rebuild metadata repair execution admission contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "rebuild metadata repair execution admission facts")


def _new_contract_expected() -> dict[str, Any]:
    return {
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "provenance_contract_id": PROVENANCE_CONTRACT_ID,
        "provenance_contract_status": PROVENANCE_CONTRACT_STATUS,
        "core_preflight_contract_id": CORE_PREFLIGHT_CONTRACT_ID,
        "core_preflight_contract_status": CORE_PREFLIGHT_CONTRACT_STATUS,
        "independent_evidence_ids": list(REQUIRED_INDEPENDENT_EVIDENCE_IDS),
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }


def _new_contract_boundary() -> dict[str, Any]:
    return {
        "fixed_local_provenance_contract_read_only": True,
        "fixed_local_core_preflight_contract_read_only": True,
        "current_host_metadata_read": False,
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


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-REPAIR-EXECUTION-ADMISSION-CONTRACT-DIAGNOSTIC-001":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("diagnostic must remain static read-only")
    if _object(contract.get("expected"), "expected") != _new_contract_expected():
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("diagnostic expectations are not exact")
    if _object(contract.get("source_boundary"), "source boundary") != _new_contract_boundary():
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC_ONLY_NOT_CURRENT_HOST_EVIDENCE_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_REPAIR_EXECUTION_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("rollback boundary is not exact")


def _provenance_contract_expected() -> dict[str, Any]:
    return {
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "repair_contract_id": "ABD-POST-FREEZE-CURRENT-PRODUCTION-BLUE-RELEASE-REPAIR-001",
        "repair_contract_status": "ONE_SHOT_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR_NO_CORE_ACTIVATION",
        "repair_receipt_type": "ABD_CURRENT_PRODUCTION_BLUE_RELEASE_REPAIR",
        "repair_source_constant_names": ["INFRA_SOURCE_PATHS", "RECEIPT_TYPE"],
        "repair_source_function_names": ["build_receipt", "evaluate_repair", "source_bundle_paths", "validate_contract"],
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }


def _provenance_contract_boundary() -> dict[str, Any]:
    return {
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


def _validate_provenance_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract field set is not exact")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != PROVENANCE_CONTRACT_ID:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract identity is invalid")
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != PROVENANCE_CONTRACT_STATUS:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract status is invalid")
    if _object(contract.get("expected"), "provenance expected") != _provenance_contract_expected():
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract expectations are invalid")
    if _object(contract.get("source_boundary"), "provenance source boundary") != _provenance_contract_boundary():
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract boundary is invalid")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_ONLY_NOT_HOST_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract claim boundary is invalid")
    if _object(contract.get("rollback"), "provenance rollback") != {
        "action": "NO_SOURCE_EXECUTION_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("provenance contract rollback is invalid")


def _core_preflight_contract_expected() -> dict[str, Any]:
    return {
        "candidate_image_present": True,
        "required_runtime_metadata": {
            "config_file_kind": "regular",
            "runtime_env_file_kind": "regular",
            "runtime_secret_file_kind": "regular",
            "current_release_link_kind": "symlink",
            "current_release_target_managed": True,
            "current_compose_file_kind": "regular",
            "current_rebuild_file_kind": "regular",
            "core_capacity_dropin_file_kind": "regular",
        },
        "core_unit": {"load_state": "not-found", "active_state": "inactive"},
        "connector_unit": {"load_state": "not-found", "active_state": "inactive"},
    }


def _core_preflight_contract_boundary() -> dict[str, Any]:
    return {
        "live_host_nonsecret_metadata_read": True,
        "privileged_metadata_read": True,
        "config_contents_read": False,
        "runtime_env_contents_read": False,
        "runtime_secret_contents_read": False,
        "release_file_contents_read": False,
        "remote_script_written": False,
        "host_runtime_or_configuration_changed": False,
        "image_loaded_or_retagged": False,
        "unit_created_enabled_or_started": False,
        "connector_config_written": False,
        "cloudflare_dns_access_or_tunnel_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _validate_core_preflight_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract field set is not exact")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != CORE_PREFLIGHT_CONTRACT_ID:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract identity is invalid")
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != CORE_PREFLIGHT_CONTRACT_STATUS:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract status is invalid")
    if _object(contract.get("expected"), "core preflight expected") != _core_preflight_contract_expected():
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract expectations are invalid")
    if _object(contract.get("source_boundary"), "core preflight source boundary") != _core_preflight_contract_boundary():
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract boundary is invalid")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_ONLY_NOT_RELEASE_REPAIR_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract claim boundary is invalid")
    if _object(contract.get("rollback"), "core preflight rollback") != {
        "action": "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("core preflight contract rollback is invalid")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "provenance_contract_state",
        "core_preflight_contract_state",
        "repair_execution_admission_state",
        "independent_evidence_requirement_state",
        "independent_evidence_required",
        "repair_execution_authorized",
        "core_start_authorized",
        "current_host_metadata_read",
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
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC":
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("facts identity is not exact")
    if not isinstance(facts.get("observed_on"), str):
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("facts observation date is invalid")
    try:
        date.fromisoformat(facts["observed_on"])
    except ValueError as exc:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("repository root state is invalid")
    for field in ("provenance_contract_state", "core_preflight_contract_state"):
        if facts.get(field) not in STATIC_CONTRACT_STATES:
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("static contract state is invalid")
    if facts.get("repair_execution_admission_state") not in ADMISSION_STATES:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("repair execution admission state is invalid")
    if facts.get("independent_evidence_requirement_state") not in REQUIREMENT_STATES:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("independent evidence requirement state is invalid")
    evidence_ids = facts.get("independent_evidence_required")
    if not isinstance(evidence_ids, list) or any(not isinstance(value, str) for value in evidence_ids):
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("independent evidence list is invalid")
    for field in (
        "repair_execution_authorized",
        "core_start_authorized",
        "current_host_metadata_read",
        "config_runtime_or_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_repair_command_read_or_persisted",
        "private_object_path_hash_or_raw_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("admission boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("outbound operation count is invalid")
    root_available = facts["repository_root_state"] == "AVAILABLE_READ_ONLY"
    static_inputs_observed = facts["provenance_contract_state"] == "OBSERVED_STATIC" and facts["core_preflight_contract_state"] == "OBSERVED_STATIC"
    host_evidence_required = facts["repair_execution_admission_state"] == "HOST_EVIDENCE_REQUIRED_REDACTED"
    if host_evidence_required:
        if not root_available or not static_inputs_observed:
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("host evidence requirement is inconsistent")
        if facts["independent_evidence_requirement_state"] != "ALL_INDEPENDENT_EVIDENCE_REQUIRED_REDACTED" or evidence_ids != list(REQUIRED_INDEPENDENT_EVIDENCE_IDS):
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("independent evidence requirement is incomplete")
    else:
        if facts["independent_evidence_requirement_state"] != "STATIC_INPUT_REJECTED_REDACTED" or evidence_ids:
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("static input rejection is inconsistent")
        if root_available and static_inputs_observed:
            raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("static input rejection is inconsistent")
    if not root_available and (facts["provenance_contract_state"] != "NOT_ATTEMPTED" or facts["core_preflight_contract_state"] != "NOT_ATTEMPTED"):
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("unavailable root facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "provenance_contract_state": "NOT_ATTEMPTED",
        "core_preflight_contract_state": "NOT_ATTEMPTED",
        "repair_execution_admission_state": "STATIC_INPUT_REJECTED_REDACTED",
        "independent_evidence_requirement_state": "STATIC_INPUT_REJECTED_REDACTED",
        "independent_evidence_required": [],
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "current_host_metadata_read": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }


def _observe_static_contract(path: Path, name: str, validator: Any) -> str:
    try:
        contract = _load(path, name)
    except CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError:
        return "UNAVAILABLE_REDACTED"
    try:
        validator(contract)
    except CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError:
        return "REJECTED_REDACTED"
    return "OBSERVED_STATIC"


def discover_execution_admission(repo_root: Path, provenance_contract_path: Path, core_preflight_contract_path: Path, observed_on: str) -> dict[str, Any]:
    """Read only two fixed, nonsecret local contract declarations."""

    facts = _base_facts(observed_on)
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    facts["provenance_contract_state"] = _observe_static_contract(
        provenance_contract_path,
        "rebuild metadata source-repair provenance contract",
        _validate_provenance_contract,
    )
    facts["core_preflight_contract_state"] = _observe_static_contract(
        core_preflight_contract_path,
        "core execution preflight contract",
        _validate_core_preflight_contract,
    )
    if facts["provenance_contract_state"] == "OBSERVED_STATIC" and facts["core_preflight_contract_state"] == "OBSERVED_STATIC":
        facts["repair_execution_admission_state"] = "HOST_EVIDENCE_REQUIRED_REDACTED"
        facts["independent_evidence_requirement_state"] = "ALL_INDEPENDENT_EVIDENCE_REQUIRED_REDACTED"
        facts["independent_evidence_required"] = list(REQUIRED_INDEPENDENT_EVIDENCE_IDS)
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    static_inputs_observed = facts["repair_execution_admission_state"] == "HOST_EVIDENCE_REQUIRED_REDACTED"
    checks = [
        {"id": "PROVENANCE_CONTRACT_STATICLY_OBSERVED", "passed": facts["provenance_contract_state"] == "OBSERVED_STATIC"},
        {"id": "CORE_PREFLIGHT_CONTRACT_STATICLY_OBSERVED", "passed": facts["core_preflight_contract_state"] == "OBSERVED_STATIC"},
        {"id": "STATIC_ADMISSION_INPUT_ACCEPTED", "passed": static_inputs_observed},
        {
            "id": "ALL_INDEPENDENT_EVIDENCE_REQUIRED",
            "passed": facts["independent_evidence_requirement_state"] == "ALL_INDEPENDENT_EVIDENCE_REQUIRED_REDACTED",
        },
        {"id": "CURRENT_HOST_EVIDENCE_NOT_READ_BY_THIS_DIAGNOSTIC", "passed": facts["current_host_metadata_read"] is False},
        {"id": "REPAIR_EXECUTION_NOT_AUTHORIZED", "passed": facts["repair_execution_authorized"] is False},
        {"id": "CORE_START_NOT_AUTHORIZED", "passed": facts["core_start_authorized"] is False},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    decision = (
        "CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_HOST_EVIDENCE_REQUIRED_NO_REPAIR_ACTION_AUTHORIZED"
        if static_inputs_observed
        else "CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_STATIC_INPUT_REJECTED_NO_REPAIR_ACTION_AUTHORIZED"
    )
    return {
        "status": PASS_STATUS,
        "decision": decision,
        "repair_execution_admission_state": facts["repair_execution_admission_state"],
        "independent_evidence_requirement_state": facts["independent_evidence_requirement_state"],
        "independent_evidence_required": list(facts["independent_evidence_required"]),
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    required = {
        "status",
        "decision",
        "repair_execution_admission_state",
        "independent_evidence_requirement_state",
        "independent_evidence_required",
        "repair_execution_authorized",
        "core_start_authorized",
        "product_outbound_operations_not_attempted",
        "checks",
        "failure_codes",
    }
    if set(result) != required:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("diagnostic result field set is not exact")
    if result["repair_execution_authorized"] is not False or result["core_start_authorized"] is not False:
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("diagnostic authorization state is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "repair_execution_admission_state": result["repair_execution_admission_state"],
        "independent_evidence_requirement_state": result["independent_evidence_requirement_state"],
        "independent_evidence_required": list(result["independent_evidence_required"]),
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": list(checks),
        "failure_codes": list(result["failure_codes"]),
        "source_boundary": dict(_object(contract["source_boundary"], "source boundary")),
        "claim_boundary": contract["claim_boundary"],
    }


def _failure_receipt(error: Exception, observed_on: str) -> dict[str, Any]:
    try:
        safe_observed_on = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        safe_observed_on = "INVALID"
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": FAIL_STATUS,
        "decision": "CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_INPUT_FAILED_CLOSED",
        "observed_on": safe_observed_on,
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "repair_execution_admission_state": "STATIC_INPUT_REJECTED_REDACTED",
        "independent_evidence_requirement_state": "STATIC_INPUT_REJECTED_REDACTED",
        "independent_evidence_required": [],
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "source_or_external_state_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--provenance-contract", type=Path, required=True)
    parser.add_argument("--core-preflight-contract", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(
            load_contract(args.contract),
            discover_execution_admission(
                args.repo_root,
                args.provenance_contract,
                args.core_preflight_contract,
                args.observed_on,
            ),
        )
    except (CurrentProductionRebuildMetadataRepairExecutionAdmissionContractDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
