#!/usr/bin/env python3
"""Declare a one-shot read-only current-host metadata collection run contract."""

from __future__ import annotations

import argparse
import json
import stat
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC"
REBUILD_METADATA_SUBDOMAIN = "CURRENT_RELEASE_REBUILD_METADATA_INCOMPLETE_REDACTED"
ACQUISITION_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-CURRENT-HOST-EVIDENCE-ACQUISITION-CONTRACT-DIAGNOSTIC-001"
ACQUISITION_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_ACQUISITION_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY"
ADMISSION_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-REPAIR-EXECUTION-ADMISSION-CONTRACT-DIAGNOSTIC-001"
ADMISSION_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY"
CORE_PREFLIGHT_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-PREFLIGHT-001"
CORE_PREFLIGHT_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_READ_ONLY"
HOST_METADATA_INPUT_SURFACE = (
    "PRIVILEGED_METADATA_READ",
    "RUNTIME_PREREQUISITES",
    "CORE_UNIT_STATE",
    "CONNECTOR_UNIT_STATE",
)
FUTURE_COLLECTION_REQUEST_FIELDS = (
    "schema_version",
    "collection_id",
    "requested_on",
    "requested_observed_on",
    "collection_mode",
)
FUTURE_COLLECTION_REQUEST_DEFAULTS = {
    "collection_mode": "ONE_SHOT_CURRENT_HOST_METADATA_READ_ONLY",
    "maximum_collection_attempts": 1,
    "same_utc_date_required": True,
    "historical_or_static_evidence_accepted": False,
}
FUTURE_COLLECTION_RECEIPT_FIELDS = (
    "schema_version",
    "receipt_type",
    "observed_on",
    "acquired_on",
    "metadata_freshness_state",
    "privileged_metadata_read",
    "runtime_prerequisites",
    "core_unit",
    "connector_unit",
    "repair_execution_authorized",
    "core_start_authorized",
)
FUTURE_COLLECTION_FAILURE_STATES = (
    "STATIC_INPUT_REJECTED_REDACTED",
    "CURRENT_HOST_METADATA_REQUIRED_REDACTED",
    "CURRENT_HOST_METADATA_STALE_REDACTED",
    "CURRENT_HOST_METADATA_SCHEMA_REJECTED_REDACTED",
)
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
STATIC_CONTRACT_STATES = {"OBSERVED_STATIC", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}
RUN_CONTRACT_STATES = {"STATIC_INPUT_REJECTED_REDACTED", "CURRENT_HOST_METADATA_REQUIRED_REDACTED"}
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


class CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError(ValueError):
    """Raised when a static one-shot collection run-contract input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s must be an object" % name)
    return value


def _safe_regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _read_text(path: Path) -> str:
    if not _safe_regular_file(path):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError) as exc:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "current-host evidence collection run contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "current-host evidence collection run facts")


def _new_contract_expected() -> dict[str, Any]:
    return {
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "acquisition_contract_id": ACQUISITION_CONTRACT_ID,
        "acquisition_contract_status": ACQUISITION_CONTRACT_STATUS,
        "admission_contract_id": ADMISSION_CONTRACT_ID,
        "admission_contract_status": ADMISSION_CONTRACT_STATUS,
        "core_preflight_contract_id": CORE_PREFLIGHT_CONTRACT_ID,
        "core_preflight_contract_status": CORE_PREFLIGHT_CONTRACT_STATUS,
        "future_collection_request_fields": list(FUTURE_COLLECTION_REQUEST_FIELDS),
        "future_collection_request_defaults": dict(FUTURE_COLLECTION_REQUEST_DEFAULTS),
        "future_collection_receipt_fields": list(FUTURE_COLLECTION_RECEIPT_FIELDS),
        "future_collection_failure_states": list(FUTURE_COLLECTION_FAILURE_STATES),
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }


def _new_contract_boundary() -> dict[str, Any]:
    return {
        "fixed_local_acquisition_contract_read_only": True,
        "fixed_local_admission_contract_read_only": True,
        "fixed_local_core_preflight_contract_read_only": True,
        "future_current_host_metadata_collection_contract_declared_only": True,
        "future_current_host_metadata_collection_executed": False,
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


def _validate_exact_contract(
    contract: Mapping[str, Any],
    name: str,
    contract_id: str,
    status: str,
    expected: Mapping[str, Any],
    boundary: Mapping[str, Any],
    claim_boundary: str,
    rollback_action: str,
) -> None:
    if set(contract) != CONTRACT_FIELDS:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s field set is not exact" % name)
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != contract_id:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s identity is invalid" % name)
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != status:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s status is invalid" % name)
    if _object(contract.get("expected"), "%s expected" % name) != expected:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s expectations are invalid" % name)
    if _object(contract.get("source_boundary"), "%s source boundary" % name) != boundary:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s boundary is invalid" % name)
    if contract.get("claim_boundary") != claim_boundary:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s claim boundary is invalid" % name)
    if _object(contract.get("rollback"), "%s rollback" % name) != {
        "action": rollback_action,
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("%s rollback is invalid" % name)


def validate_contract(contract: Mapping[str, Any]) -> None:
    _validate_exact_contract(
        contract,
        "collection run contract",
        "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-CURRENT-HOST-EVIDENCE-COLLECTION-RUN-CONTRACT-DIAGNOSTIC-001",
        "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY",
        _new_contract_expected(),
        _new_contract_boundary(),
        "CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC_ONLY_NOT_CURRENT_HOST_COLLECTION_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE",
        "NO_CURRENT_HOST_COLLECTION_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
    )


def _acquisition_contract_expected() -> dict[str, Any]:
    return {
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "admission_contract_id": ADMISSION_CONTRACT_ID,
        "admission_contract_status": ADMISSION_CONTRACT_STATUS,
        "core_preflight_contract_id": CORE_PREFLIGHT_CONTRACT_ID,
        "core_preflight_contract_status": CORE_PREFLIGHT_CONTRACT_STATUS,
        "future_current_host_metadata_input_surface": list(HOST_METADATA_INPUT_SURFACE),
        "evidence_freshness_policy": {
            "observation_date_required": True,
            "acquisition_date_required": True,
            "same_utc_date_as_acquisition_required": True,
            "historical_or_static_evidence_accepted": False,
            "stale_or_malformed_evidence_rejected": True,
        },
        "future_rejection_states": list(FUTURE_COLLECTION_FAILURE_STATES),
        "future_receipt_schema_fields": list(FUTURE_COLLECTION_RECEIPT_FIELDS),
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }


def _acquisition_contract_boundary() -> dict[str, Any]:
    return {
        "fixed_local_admission_contract_read_only": True,
        "fixed_local_core_preflight_contract_read_only": True,
        "future_current_host_metadata_contract_declared_only": True,
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


def _validate_acquisition_contract(contract: Mapping[str, Any]) -> None:
    _validate_exact_contract(
        contract,
        "acquisition contract",
        ACQUISITION_CONTRACT_ID,
        ACQUISITION_CONTRACT_STATUS,
        _acquisition_contract_expected(),
        _acquisition_contract_boundary(),
        "CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_ACQUISITION_CONTRACT_DIAGNOSTIC_ONLY_NOT_CURRENT_HOST_READ_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE",
        "NO_CURRENT_HOST_READ_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
    )


def _admission_contract_expected() -> dict[str, Any]:
    return {
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "provenance_contract_id": "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-SOURCE-REPAIR-PROVENANCE-RECONCILIATION-DIAGNOSTIC-001",
        "provenance_contract_status": "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_SOURCE_REPAIR_PROVENANCE_RECONCILIATION_DIAGNOSTIC_STATIC_READ_ONLY",
        "core_preflight_contract_id": CORE_PREFLIGHT_CONTRACT_ID,
        "core_preflight_contract_status": CORE_PREFLIGHT_CONTRACT_STATUS,
        "independent_evidence_ids": [
            "SOURCE_REPAIR_PROVENANCE_CURRENT",
            "CURRENT_HOST_METADATA_CURRENT",
            "FROZEN_CONFIG_SEMANTIC_CHECK_CURRENT",
            "ROLLBACK_INPUT_CURRENT",
            "CORE_CAPACITY_CURRENT",
            "CONTROLLED_ENTRY_CURRENT",
            "MANAGEMENT_PLANE_CURRENT",
            "SSH_TRANSPORT_CURRENT",
            "CORE_EXECUTION_CONTRACT_CURRENT",
        ],
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }


def _admission_contract_boundary() -> dict[str, Any]:
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


def _validate_admission_contract(contract: Mapping[str, Any]) -> None:
    _validate_exact_contract(
        contract,
        "admission contract",
        ADMISSION_CONTRACT_ID,
        ADMISSION_CONTRACT_STATUS,
        _admission_contract_expected(),
        _admission_contract_boundary(),
        "CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC_ONLY_NOT_CURRENT_HOST_EVIDENCE_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE",
        "NO_REPAIR_EXECUTION_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
    )


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
    _validate_exact_contract(
        contract,
        "core preflight contract",
        CORE_PREFLIGHT_CONTRACT_ID,
        CORE_PREFLIGHT_CONTRACT_STATUS,
        _core_preflight_contract_expected(),
        _core_preflight_contract_boundary(),
        "CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_ONLY_NOT_RELEASE_REPAIR_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE",
        "NO_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
    )


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "acquisition_contract_state",
        "admission_contract_state",
        "core_preflight_contract_state",
        "current_host_evidence_collection_run_contract_state",
        "future_collection_request_fields",
        "future_collection_request_defaults",
        "future_collection_receipt_fields",
        "future_collection_failure_states",
        "future_collection_executed",
        "current_host_metadata_read",
        "repair_execution_authorized",
        "core_start_authorized",
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
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC":
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("facts identity is not exact")
    if not isinstance(facts.get("observed_on"), str):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("facts observation date is invalid")
    try:
        date.fromisoformat(facts["observed_on"])
    except ValueError as exc:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("repository root state is invalid")
    for field in ("acquisition_contract_state", "admission_contract_state", "core_preflight_contract_state"):
        if facts.get(field) not in STATIC_CONTRACT_STATES:
            raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("static contract state is invalid")
    if facts.get("current_host_evidence_collection_run_contract_state") not in RUN_CONTRACT_STATES:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("collection run-contract state is invalid")
    if facts.get("future_collection_request_fields") != list(FUTURE_COLLECTION_REQUEST_FIELDS):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("future request fields are invalid")
    if facts.get("future_collection_request_defaults") != FUTURE_COLLECTION_REQUEST_DEFAULTS:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("future request defaults are invalid")
    if facts.get("future_collection_receipt_fields") != list(FUTURE_COLLECTION_RECEIPT_FIELDS):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("future receipt fields are invalid")
    if facts.get("future_collection_failure_states") != list(FUTURE_COLLECTION_FAILURE_STATES):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("future failure states are invalid")
    for field in (
        "future_collection_executed",
        "current_host_metadata_read",
        "repair_execution_authorized",
        "core_start_authorized",
        "config_runtime_or_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_repair_command_read_or_persisted",
        "private_object_path_hash_or_raw_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("collection boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("outbound operation count is invalid")
    root_available = facts["repository_root_state"] == "AVAILABLE_READ_ONLY"
    inputs_observed = all(
        facts[name] == "OBSERVED_STATIC"
        for name in ("acquisition_contract_state", "admission_contract_state", "core_preflight_contract_state")
    )
    metadata_required = facts["current_host_evidence_collection_run_contract_state"] == "CURRENT_HOST_METADATA_REQUIRED_REDACTED"
    if metadata_required != (root_available and inputs_observed):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("collection run-contract state is inconsistent")
    if not root_available and any(
        facts[name] != "NOT_ATTEMPTED"
        for name in ("acquisition_contract_state", "admission_contract_state", "core_preflight_contract_state")
    ):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("unavailable root facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "acquisition_contract_state": "NOT_ATTEMPTED",
        "admission_contract_state": "NOT_ATTEMPTED",
        "core_preflight_contract_state": "NOT_ATTEMPTED",
        "current_host_evidence_collection_run_contract_state": "STATIC_INPUT_REJECTED_REDACTED",
        "future_collection_request_fields": list(FUTURE_COLLECTION_REQUEST_FIELDS),
        "future_collection_request_defaults": dict(FUTURE_COLLECTION_REQUEST_DEFAULTS),
        "future_collection_receipt_fields": list(FUTURE_COLLECTION_RECEIPT_FIELDS),
        "future_collection_failure_states": list(FUTURE_COLLECTION_FAILURE_STATES),
        "future_collection_executed": False,
        "current_host_metadata_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
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
    except CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError:
        return "UNAVAILABLE_REDACTED"
    try:
        validator(contract)
    except CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError:
        return "REJECTED_REDACTED"
    return "OBSERVED_STATIC"


def discover_current_host_evidence_collection_run_contract(
    repo_root: Path,
    acquisition_contract_path: Path,
    admission_contract_path: Path,
    core_preflight_contract_path: Path,
    observed_on: str,
) -> dict[str, Any]:
    """Read only three fixed, nonsecret local contracts; never collect host metadata."""

    facts = _base_facts(observed_on)
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    facts["acquisition_contract_state"] = _observe_static_contract(
        acquisition_contract_path,
        "current-host evidence acquisition contract",
        _validate_acquisition_contract,
    )
    facts["admission_contract_state"] = _observe_static_contract(
        admission_contract_path,
        "rebuild metadata repair execution admission contract",
        _validate_admission_contract,
    )
    facts["core_preflight_contract_state"] = _observe_static_contract(
        core_preflight_contract_path,
        "core execution preflight contract",
        _validate_core_preflight_contract,
    )
    if all(
        facts[name] == "OBSERVED_STATIC"
        for name in ("acquisition_contract_state", "admission_contract_state", "core_preflight_contract_state")
    ):
        facts["current_host_evidence_collection_run_contract_state"] = "CURRENT_HOST_METADATA_REQUIRED_REDACTED"
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    inputs_ready = facts["current_host_evidence_collection_run_contract_state"] == "CURRENT_HOST_METADATA_REQUIRED_REDACTED"
    checks = [
        {"id": "ACQUISITION_CONTRACT_STATICLY_OBSERVED", "passed": facts["acquisition_contract_state"] == "OBSERVED_STATIC"},
        {"id": "ADMISSION_CONTRACT_STATICLY_OBSERVED", "passed": facts["admission_contract_state"] == "OBSERVED_STATIC"},
        {"id": "CORE_PREFLIGHT_CONTRACT_STATICLY_OBSERVED", "passed": facts["core_preflight_contract_state"] == "OBSERVED_STATIC"},
        {"id": "STATIC_COLLECTION_RUN_INPUT_ACCEPTED", "passed": inputs_ready},
        {"id": "ONE_SHOT_SAME_DATE_COLLECTION_RULE_DECLARED", "passed": facts["future_collection_request_defaults"] == FUTURE_COLLECTION_REQUEST_DEFAULTS},
        {"id": "CURRENT_HOST_METADATA_NOT_COLLECTED_BY_THIS_DIAGNOSTIC", "passed": facts["current_host_metadata_read"] is False},
        {"id": "REPAIR_EXECUTION_NOT_AUTHORIZED", "passed": facts["repair_execution_authorized"] is False},
        {"id": "CORE_START_NOT_AUTHORIZED", "passed": facts["core_start_authorized"] is False},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    decision = (
        "CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_METADATA_REQUIRED_NO_COLLECTION_OR_REPAIR_ACTION_AUTHORIZED"
        if inputs_ready
        else "CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_STATIC_INPUT_REJECTED_NO_COLLECTION_OR_REPAIR_ACTION_AUTHORIZED"
    )
    return {
        "status": PASS_STATUS,
        "decision": decision,
        "current_host_evidence_collection_run_contract_state": facts["current_host_evidence_collection_run_contract_state"],
        "future_collection_request_fields": list(facts["future_collection_request_fields"]),
        "future_collection_request_defaults": dict(facts["future_collection_request_defaults"]),
        "future_collection_receipt_fields": list(facts["future_collection_receipt_fields"]),
        "future_collection_failure_states": list(facts["future_collection_failure_states"]),
        "future_collection_executed": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    required = {
        "status",
        "decision",
        "current_host_evidence_collection_run_contract_state",
        "future_collection_request_fields",
        "future_collection_request_defaults",
        "future_collection_receipt_fields",
        "future_collection_failure_states",
        "future_collection_executed",
        "repair_execution_authorized",
        "core_start_authorized",
        "product_outbound_operations_not_attempted",
        "checks",
        "failure_codes",
    }
    if set(result) != required:
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("diagnostic result field set is not exact")
    if any(
        result[field] is not False
        for field in ("future_collection_executed", "repair_execution_authorized", "core_start_authorized")
    ):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("diagnostic authorization state is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "current_host_evidence_collection_run_contract_state": result["current_host_evidence_collection_run_contract_state"],
        "future_collection_request_fields": list(result["future_collection_request_fields"]),
        "future_collection_request_defaults": dict(result["future_collection_request_defaults"]),
        "future_collection_receipt_fields": list(result["future_collection_receipt_fields"]),
        "future_collection_failure_states": list(result["future_collection_failure_states"]),
        "future_collection_executed": False,
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
        "decision": "CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_INPUT_FAILED_CLOSED",
        "observed_on": safe_observed_on,
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "current_host_evidence_collection_run_contract_state": "STATIC_INPUT_REJECTED_REDACTED",
        "future_collection_request_fields": list(FUTURE_COLLECTION_REQUEST_FIELDS),
        "future_collection_request_defaults": dict(FUTURE_COLLECTION_REQUEST_DEFAULTS),
        "future_collection_receipt_fields": list(FUTURE_COLLECTION_RECEIPT_FIELDS),
        "future_collection_failure_states": list(FUTURE_COLLECTION_FAILURE_STATES),
        "future_collection_executed": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "source_or_external_state_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--admission-contract", type=Path, required=True)
    parser.add_argument("--core-preflight-contract", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(
            load_contract(args.contract),
            discover_current_host_evidence_collection_run_contract(
                args.repo_root,
                args.acquisition_contract,
                args.admission_contract,
                args.core_preflight_contract,
                args.observed_on,
            ),
        )
    except (CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
