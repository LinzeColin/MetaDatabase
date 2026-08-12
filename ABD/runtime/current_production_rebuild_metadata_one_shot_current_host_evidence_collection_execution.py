#!/usr/bin/env python3
"""Execute the local-only admission step for one-shot current-host metadata collection."""

from __future__ import annotations

import argparse
import json
import stat
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import current_production_rebuild_metadata_current_host_evidence_collection_run_contract_diagnostic as collection_contract
import current_production_ssh_local_route_policy_diagnostic as local_route


PASS_STATUS = "PASS_CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION"
REBUILD_METADATA_SUBDOMAIN = "CURRENT_RELEASE_REBUILD_METADATA_INCOMPLETE_REDACTED"
COLLECTION_RUN_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-CURRENT-HOST-EVIDENCE-COLLECTION-RUN-CONTRACT-DIAGNOSTIC-001"
COLLECTION_RUN_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_RUN_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY"
ACQUISITION_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-CURRENT-HOST-EVIDENCE-ACQUISITION-CONTRACT-DIAGNOSTIC-001"
ACQUISITION_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_ACQUISITION_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY"
ADMISSION_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-REPAIR-EXECUTION-ADMISSION-CONTRACT-DIAGNOSTIC-001"
ADMISSION_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_REPAIR_EXECUTION_ADMISSION_CONTRACT_DIAGNOSTIC_STATIC_READ_ONLY"
CORE_PREFLIGHT_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-EXECUTION-PREFLIGHT-001"
CORE_PREFLIGHT_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT_READ_ONLY"
LOCAL_ROUTE_POLICY_CONTRACT_ID = "ABD-POST-FREEZE-CURRENT-PRODUCTION-SSH-LOCAL-ROUTE-POLICY-DIAGNOSTIC-001"
LOCAL_ROUTE_POLICY_CONTRACT_STATUS = "ONE_SHOT_CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_READ_ONLY"

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
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
STATIC_CONTRACT_STATES = {"OBSERVED_STATIC", "UNAVAILABLE_REDACTED", "REJECTED_REDACTED", "NOT_ATTEMPTED"}
ROUTE_RECEIPT_STATES = {
    "OBSERVED_CURRENT_LOCAL_POLICY_ONLY_REDACTED",
    "ROUTE_NOT_PROVEN_REDACTED",
    "UNAVAILABLE_REDACTED",
    "STALE_REDACTED",
    "SCHEMA_REJECTED_REDACTED",
    "NOT_ATTEMPTED",
}
TRANSPORT_ELIGIBILITY_STATES = {
    "LOCAL_ROUTE_POLICY_ONLY_TRANSPORT_NOT_PROVEN_REDACTED",
    "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED",
    "TRANSPORT_ROUTE_EVIDENCE_STALE_REDACTED",
    "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED",
    "NOT_ATTEMPTED",
}
COLLECTION_STATES = {
    "STATIC_INPUT_REJECTED_REDACTED",
    "CURRENT_HOST_METADATA_REQUIRED_REDACTED",
    "CURRENT_HOST_METADATA_STALE_REDACTED",
    "CURRENT_HOST_METADATA_SCHEMA_REJECTED_REDACTED",
}

LOCAL_ROUTE_RECEIPT_FIELDS = {
    "schema_version",
    "receipt_type",
    "status",
    "decision",
    "observed_on",
    "local_route_policy_diagnosed",
    "local_route_policy_ready",
    "core_start_authorized",
    "local_route_policy_state",
    "checks",
    "failure_codes",
    "source_boundary",
    "claim_boundary",
}
LOCAL_ROUTE_FAILURE_RECEIPT_FIELDS = {
    "schema_version",
    "receipt_type",
    "status",
    "decision",
    "observed_on",
    "local_route_policy_diagnosed",
    "local_route_policy_ready",
    "core_start_authorized",
    "local_route_policy_state",
    "checks",
    "failure_codes",
    "error_type",
    "local_network_or_host_changed",
    "real_time_soak_waited",
}
LOCAL_ROUTE_SOURCE_BOUNDARY = {
    "only_host_declaration_aliases_and_ssh_g_transport_metadata_read": True,
    "alias_address_port_user_identity_proxy_or_route_values_emitted_or_persisted": False,
    "credential_material_read_emitted_or_persisted": False,
    "socket_connection_attempted": False,
    "ssh_connection_attempted": False,
    "interactive_authentication_permitted": False,
    "local_known_hosts_modified": False,
    "provider_api_request_sent": False,
    "github_api_request_sent": False,
    "provider_resource_created_deleted_rebuilt_or_restarted": False,
    "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
    "host_runtime_or_configuration_changed": False,
    "real_time_soak_waited": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "incremental_cash_spent_aud": "0.00",
}
LOCAL_ROUTE_CLAIM_BOUNDARY = "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_ONLY_NOT_DNS_PROBE_SOCKET_CONNECTION_SSH_AUTHENTICATION_HOST_RECOVERY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE"


class CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError(ValueError):
    """Raised when local-only collection admission inputs are malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("%s must be an object" % name)
    return value


def _safe_regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _read_text(path: Path) -> str:
    if not _safe_regular_file(path):
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError) as exc:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "one-shot current-host collection execution contract")


def _expected_contract() -> dict[str, Any]:
    return {
        "collection_run_contract_id": COLLECTION_RUN_CONTRACT_ID,
        "collection_run_contract_status": COLLECTION_RUN_CONTRACT_STATUS,
        "acquisition_contract_id": ACQUISITION_CONTRACT_ID,
        "acquisition_contract_status": ACQUISITION_CONTRACT_STATUS,
        "admission_contract_id": ADMISSION_CONTRACT_ID,
        "admission_contract_status": ADMISSION_CONTRACT_STATUS,
        "core_preflight_contract_id": CORE_PREFLIGHT_CONTRACT_ID,
        "core_preflight_contract_status": CORE_PREFLIGHT_CONTRACT_STATUS,
        "local_route_policy_contract_id": LOCAL_ROUTE_POLICY_CONTRACT_ID,
        "local_route_policy_contract_status": LOCAL_ROUTE_POLICY_CONTRACT_STATUS,
        "maximum_current_host_metadata_collection_attempts": 1,
        "same_utc_date_required": True,
        "independent_noninteractive_transport_proof_required": True,
        "local_route_policy_only_is_transport_proof": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "socket_connections_attempted": 0,
        "ssh_connections_attempted": 0,
    }


def _contract_boundary() -> dict[str, Any]:
    return {
        "fixed_local_collection_run_contract_read_only": True,
        "fixed_local_acquisition_contract_read_only": True,
        "fixed_local_admission_contract_read_only": True,
        "fixed_local_core_preflight_contract_read_only": True,
        "fixed_local_route_policy_contract_read_only": True,
        "existing_local_route_policy_diagnostic_reused_read_only": True,
        "current_host_metadata_collection_executed": False,
        "current_host_metadata_read": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_request_sent": False,
        "provider_api_request_sent": False,
        "socket_connection_attempted": False,
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
    if set(contract) != CONTRACT_FIELDS:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-REBUILD-METADATA-ONE-SHOT-CURRENT-HOST-EVIDENCE-COLLECTION-EXECUTION-001":
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract identity is invalid")
    if contract.get("product_version") != "0.0.0.1" or contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_REBUILD_METADATA_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION_LOCAL_ROUTE_ADMISSION_ONLY":
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract status is invalid")
    if _object(contract.get("expected"), "contract expected") != _expected_contract():
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract expectations are invalid")
    if _object(contract.get("source_boundary"), "contract source boundary") != _contract_boundary():
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract boundary is invalid")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION_LOCAL_ROUTE_ADMISSION_ONLY_NOT_CURRENT_HOST_METADATA_COLLECTION_TRANSPORT_SUCCESS_REPAIR_CONFIG_VALUE_COMMAND_TARGET_CREDENTIAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract claim boundary is invalid")
    if _object(contract.get("rollback"), "contract rollback") != {
        "action": "NO_CURRENT_HOST_COLLECTION_OR_EXTERNAL_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("contract rollback is invalid")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "collection_run_contract_state": "NOT_ATTEMPTED",
        "acquisition_contract_state": "NOT_ATTEMPTED",
        "admission_contract_state": "NOT_ATTEMPTED",
        "core_preflight_contract_state": "NOT_ATTEMPTED",
        "local_route_policy_contract_state": "NOT_ATTEMPTED",
        "transport_route_receipt_state": "NOT_ATTEMPTED",
        "transport_eligibility_state": "NOT_ATTEMPTED",
        "current_host_metadata_collection_state": "STATIC_INPUT_REJECTED_REDACTED",
        "current_host_metadata_collection_attempts": 0,
        "current_host_metadata_read": False,
        "privileged_metadata_read": False,
        "runtime_prerequisites_read": False,
        "core_unit_read": False,
        "connector_unit_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "config_runtime_or_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_repair_command_read_or_persisted": False,
        "private_object_path_hash_or_raw_content_read_or_persisted": False,
        "product_github_api_requests": 0,
        "provider_api_requests": 0,
        "socket_connections_attempted": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }


def _observe_collection_run_contract(path: Path) -> str:
    try:
        candidate = collection_contract.load_contract(path)
    except collection_contract.CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError:
        return "UNAVAILABLE_REDACTED"
    try:
        collection_contract.validate_contract(candidate)
    except collection_contract.CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError:
        return "REJECTED_REDACTED"
    return "OBSERVED_STATIC"


def _observe_local_route_policy_contract(path: Path) -> str:
    try:
        candidate = local_route.load_contract(path)
    except local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError:
        return "UNAVAILABLE_REDACTED"
    try:
        local_route.validate_contract(candidate)
    except local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError:
        return "REJECTED_REDACTED"
    return "OBSERVED_STATIC"


def _build_current_local_route_receipt(route_contract_path: Path, ssh_config_path: Path) -> Mapping[str, Any]:
    return local_route.build_receipt(
        local_route.load_contract(route_contract_path),
        local_route.discover_local_route_policy(ssh_config_path),
    )


def _route_receipt_outcome(receipt: Mapping[str, Any], observed_on: str) -> tuple[str, str]:
    if receipt.get("receipt_type") != local_route.RECEIPT_TYPE:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if receipt.get("status") == local_route.FAIL_STATUS:
        if set(receipt) != LOCAL_ROUTE_FAILURE_RECEIPT_FIELDS:
            return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
        if receipt.get("decision") != "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_INPUT_FAILED_CLOSED":
            return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
        if receipt.get("local_route_policy_diagnosed") is not False or receipt.get("local_route_policy_ready") is not False:
            return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
        if receipt.get("core_start_authorized") is not False or receipt.get("local_network_or_host_changed") is not False:
            return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
        if receipt.get("real_time_soak_waited") is not False or not isinstance(receipt.get("error_type"), str):
            return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
        return "UNAVAILABLE_REDACTED", "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED"
    if set(receipt) != LOCAL_ROUTE_RECEIPT_FIELDS:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if receipt.get("schema_version") != "1.0.0" or receipt.get("status") != local_route.PASS_STATUS:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if _object(receipt.get("source_boundary"), "local route receipt boundary") != LOCAL_ROUTE_SOURCE_BOUNDARY:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if receipt.get("claim_boundary") != LOCAL_ROUTE_CLAIM_BOUNDARY:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if receipt.get("local_route_policy_diagnosed") is not True or receipt.get("core_start_authorized") is not False:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if not isinstance(receipt.get("local_route_policy_ready"), bool) or not isinstance(receipt.get("local_route_policy_state"), str):
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    checks = receipt.get("checks")
    if not isinstance(checks, list) or [check.get("id") for check in checks if isinstance(check, dict)] != [
        "SSH_LOCAL_ROUTE_POLICY_DIAGNOSTIC_COMPLETED",
        "SSH_LOCAL_ROUTE_POLICY_READY",
        "SOCKET_SSH_PROVIDER_GITHUB_CONNECTIONS_NOT_ATTEMPTED",
    ]:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if any(not isinstance(check, dict) or set(check) != {"id", "passed"} or not isinstance(check["passed"], bool) for check in checks):
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    expected_failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    if receipt.get("failure_codes") != expected_failure_codes:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    try:
        receipt_date = date.fromisoformat(str(receipt.get("observed_on"))).isoformat()
        expected_date = date.fromisoformat(observed_on).isoformat()
    except ValueError:
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    if receipt_date != expected_date:
        return "STALE_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_STALE_REDACTED"
    if receipt.get("local_route_policy_ready") is True:
        if receipt.get("decision") != "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_READY_SEPARATE_TRANSPORT_DIAGNOSTIC_REQUIRED":
            return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
        return "OBSERVED_CURRENT_LOCAL_POLICY_ONLY_REDACTED", "LOCAL_ROUTE_POLICY_ONLY_TRANSPORT_NOT_PROVEN_REDACTED"
    if receipt.get("decision") != "CURRENT_PRODUCTION_SSH_LOCAL_ROUTE_POLICY_NOT_READY_NO_SOCKET_OR_REMOTE_ACTION_AUTHORIZED":
        return "SCHEMA_REJECTED_REDACTED", "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED"
    return "ROUTE_NOT_PROVEN_REDACTED", "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED"


def discover_current_host_evidence_collection_execution(
    repo_root: Path,
    collection_run_contract_path: Path,
    acquisition_contract_path: Path,
    admission_contract_path: Path,
    core_preflight_contract_path: Path,
    local_route_policy_contract_path: Path,
    ssh_config_path: Path,
    observed_on: str,
) -> dict[str, Any]:
    """Read fixed contracts, reuse a local-only route diagnostic, and never collect host metadata."""

    facts = _base_facts(observed_on)
    static_facts = collection_contract.discover_current_host_evidence_collection_run_contract(
        repo_root,
        acquisition_contract_path,
        admission_contract_path,
        core_preflight_contract_path,
        observed_on,
    )
    facts["repository_root_state"] = static_facts["repository_root_state"]
    facts["acquisition_contract_state"] = static_facts["acquisition_contract_state"]
    facts["admission_contract_state"] = static_facts["admission_contract_state"]
    facts["core_preflight_contract_state"] = static_facts["core_preflight_contract_state"]
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        return facts
    facts["collection_run_contract_state"] = _observe_collection_run_contract(collection_run_contract_path)
    if not _static_inputs_ready(facts):
        return facts
    facts["local_route_policy_contract_state"] = _observe_local_route_policy_contract(local_route_policy_contract_path)
    if facts["local_route_policy_contract_state"] != "OBSERVED_STATIC":
        return facts
    try:
        route_receipt = _build_current_local_route_receipt(local_route_policy_contract_path, ssh_config_path)
    except (OSError, UnicodeDecodeError, ValueError, local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError):
        facts["transport_route_receipt_state"] = "UNAVAILABLE_REDACTED"
        facts["transport_eligibility_state"] = "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED"
    else:
        route_state, transport_state = _route_receipt_outcome(route_receipt, observed_on)
        facts["transport_route_receipt_state"] = route_state
        facts["transport_eligibility_state"] = transport_state
    facts["current_host_metadata_collection_state"] = _collection_state(facts)
    return facts


def _static_inputs_ready(facts: Mapping[str, Any]) -> bool:
    return facts.get("repository_root_state") == "AVAILABLE_READ_ONLY" and all(
        facts.get(field) == "OBSERVED_STATIC"
        for field in (
            "collection_run_contract_state",
            "acquisition_contract_state",
            "admission_contract_state",
            "core_preflight_contract_state",
        )
    )


def _collection_state(facts: Mapping[str, Any]) -> str:
    if not _static_inputs_ready(facts) or facts.get("local_route_policy_contract_state") != "OBSERVED_STATIC":
        return "STATIC_INPUT_REJECTED_REDACTED"
    route_state = facts.get("transport_route_receipt_state")
    if route_state == "STALE_REDACTED":
        return "CURRENT_HOST_METADATA_STALE_REDACTED"
    if route_state == "SCHEMA_REJECTED_REDACTED":
        return "CURRENT_HOST_METADATA_SCHEMA_REJECTED_REDACTED"
    return "CURRENT_HOST_METADATA_REQUIRED_REDACTED"


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "collection_run_contract_state",
        "acquisition_contract_state",
        "admission_contract_state",
        "core_preflight_contract_state",
        "local_route_policy_contract_state",
        "transport_route_receipt_state",
        "transport_eligibility_state",
        "current_host_metadata_collection_state",
        "current_host_metadata_collection_attempts",
        "current_host_metadata_read",
        "privileged_metadata_read",
        "runtime_prerequisites_read",
        "core_unit_read",
        "connector_unit_read",
        "repair_execution_authorized",
        "core_start_authorized",
        "config_runtime_or_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_repair_command_read_or_persisted",
        "private_object_path_hash_or_raw_content_read_or_persisted",
        "product_github_api_requests",
        "provider_api_requests",
        "socket_connections_attempted",
        "ssh_connections_attempted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION":
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("facts identity is invalid")
    if not isinstance(facts.get("observed_on"), str):
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("facts observation date is invalid")
    try:
        date.fromisoformat(facts["observed_on"])
    except ValueError as exc:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("repository root state is invalid")
    for field in (
        "collection_run_contract_state",
        "acquisition_contract_state",
        "admission_contract_state",
        "core_preflight_contract_state",
        "local_route_policy_contract_state",
    ):
        if facts.get(field) not in STATIC_CONTRACT_STATES:
            raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("static contract state is invalid")
    if facts.get("transport_route_receipt_state") not in ROUTE_RECEIPT_STATES:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("route receipt state is invalid")
    if facts.get("transport_eligibility_state") not in TRANSPORT_ELIGIBILITY_STATES:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("transport eligibility state is invalid")
    if facts.get("current_host_metadata_collection_state") not in COLLECTION_STATES:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("collection state is invalid")
    if type(facts.get("current_host_metadata_collection_attempts")) is not int or facts["current_host_metadata_collection_attempts"] != 0:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("collection attempt boundary is invalid")
    for field in (
        "current_host_metadata_read",
        "privileged_metadata_read",
        "runtime_prerequisites_read",
        "core_unit_read",
        "connector_unit_read",
        "repair_execution_authorized",
        "core_start_authorized",
        "config_runtime_or_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_repair_command_read_or_persisted",
        "private_object_path_hash_or_raw_content_read_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("collection boundary is invalid")
    for field in ("product_github_api_requests", "provider_api_requests", "socket_connections_attempted", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("outbound operation count is invalid")
    expected_collection_state = _collection_state(facts)
    if facts["current_host_metadata_collection_state"] != expected_collection_state:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("collection state is inconsistent")
    if not _static_inputs_ready(facts):
        if facts["local_route_policy_contract_state"] != "NOT_ATTEMPTED" or facts["transport_route_receipt_state"] != "NOT_ATTEMPTED" or facts["transport_eligibility_state"] != "NOT_ATTEMPTED":
            raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("static rejection route facts are inconsistent")
        return
    if facts["local_route_policy_contract_state"] != "OBSERVED_STATIC":
        if facts["transport_route_receipt_state"] != "NOT_ATTEMPTED" or facts["transport_eligibility_state"] != "NOT_ATTEMPTED":
            raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("route contract rejection facts are inconsistent")
        return
    route_state = facts["transport_route_receipt_state"]
    expected_transport_state = {
        "OBSERVED_CURRENT_LOCAL_POLICY_ONLY_REDACTED": "LOCAL_ROUTE_POLICY_ONLY_TRANSPORT_NOT_PROVEN_REDACTED",
        "ROUTE_NOT_PROVEN_REDACTED": "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED",
        "UNAVAILABLE_REDACTED": "TRANSPORT_ROUTE_NOT_PROVEN_REDACTED",
        "STALE_REDACTED": "TRANSPORT_ROUTE_EVIDENCE_STALE_REDACTED",
        "SCHEMA_REJECTED_REDACTED": "TRANSPORT_ROUTE_EVIDENCE_SCHEMA_REJECTED_REDACTED",
    }
    if route_state not in expected_transport_state or facts["transport_eligibility_state"] != expected_transport_state[route_state]:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("route receipt facts are inconsistent")


def evaluate_execution(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    static_ready = _static_inputs_ready(facts) and facts["local_route_policy_contract_state"] == "OBSERVED_STATIC"
    route_proof_not_promoted = (
        facts["transport_route_receipt_state"] != "OBSERVED_CURRENT_LOCAL_POLICY_ONLY_REDACTED"
        or facts["transport_eligibility_state"] == "LOCAL_ROUTE_POLICY_ONLY_TRANSPORT_NOT_PROVEN_REDACTED"
    )
    checks = [
        {"id": "COLLECTION_RUN_CONTRACT_STATICLY_OBSERVED", "passed": facts["collection_run_contract_state"] == "OBSERVED_STATIC"},
        {"id": "ACQUISITION_CONTRACT_STATICLY_OBSERVED", "passed": facts["acquisition_contract_state"] == "OBSERVED_STATIC"},
        {"id": "ADMISSION_CONTRACT_STATICLY_OBSERVED", "passed": facts["admission_contract_state"] == "OBSERVED_STATIC"},
        {"id": "CORE_PREFLIGHT_CONTRACT_STATICLY_OBSERVED", "passed": facts["core_preflight_contract_state"] == "OBSERVED_STATIC"},
        {"id": "LOCAL_ROUTE_POLICY_CONTRACT_STATICLY_OBSERVED", "passed": facts["local_route_policy_contract_state"] == "OBSERVED_STATIC"},
        {"id": "STATIC_COLLECTION_INPUT_ACCEPTED", "passed": static_ready},
        {"id": "INDEPENDENT_TRANSPORT_PROOF_NOT_INFERRED_FROM_LOCAL_POLICY", "passed": route_proof_not_promoted},
        {"id": "ONE_SHOT_COLLECTION_ATTEMPT_LIMIT_RESPECTED", "passed": facts["current_host_metadata_collection_attempts"] <= 1},
        {"id": "CURRENT_HOST_METADATA_NOT_READ_WITHOUT_INDEPENDENT_TRANSPORT_PROOF", "passed": facts["current_host_metadata_read"] is False},
        {"id": "REPAIR_EXECUTION_NOT_AUTHORIZED", "passed": facts["repair_execution_authorized"] is False},
        {"id": "CORE_START_NOT_AUTHORIZED", "passed": facts["core_start_authorized"] is False},
        {"id": "PRODUCT_OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    collection_state = facts["current_host_metadata_collection_state"]
    decision_suffix = {
        "STATIC_INPUT_REJECTED_REDACTED": "STATIC_INPUT_REJECTED_NO_COLLECTION_OR_REPAIR_ACTION_AUTHORIZED",
        "CURRENT_HOST_METADATA_REQUIRED_REDACTED": "CURRENT_HOST_METADATA_REQUIRED_NO_COLLECTION_OR_REPAIR_ACTION_AUTHORIZED",
        "CURRENT_HOST_METADATA_STALE_REDACTED": "CURRENT_HOST_METADATA_STALE_NO_COLLECTION_OR_REPAIR_ACTION_AUTHORIZED",
        "CURRENT_HOST_METADATA_SCHEMA_REJECTED_REDACTED": "CURRENT_HOST_METADATA_SCHEMA_REJECTED_NO_COLLECTION_OR_REPAIR_ACTION_AUTHORIZED",
    }[collection_state]
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_" + decision_suffix,
        "current_host_metadata_collection_state": collection_state,
        "transport_route_receipt_state": facts["transport_route_receipt_state"],
        "transport_eligibility_state": facts["transport_eligibility_state"],
        "current_host_metadata_collection_attempts": facts["current_host_metadata_collection_attempts"],
        "current_host_metadata_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_execution(contract, facts)
    required = {
        "status",
        "decision",
        "current_host_metadata_collection_state",
        "transport_route_receipt_state",
        "transport_eligibility_state",
        "current_host_metadata_collection_attempts",
        "current_host_metadata_read",
        "repair_execution_authorized",
        "core_start_authorized",
        "product_outbound_operations_not_attempted",
        "checks",
        "failure_codes",
    }
    if set(result) != required:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("execution result field set is not exact")
    if any(result[field] is not False for field in ("current_host_metadata_read", "repair_execution_authorized", "core_start_authorized")):
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("execution authorization state is invalid")
    if result["current_host_metadata_collection_attempts"] != 0:
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("execution attempt boundary is invalid")
    checks = result["checks"]
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError("execution checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "current_host_metadata_collection_state": result["current_host_metadata_collection_state"],
        "transport_route_receipt_state": result["transport_route_receipt_state"],
        "transport_eligibility_state": result["transport_eligibility_state"],
        "current_host_metadata_collection_attempts": result["current_host_metadata_collection_attempts"],
        "current_host_metadata_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": list(checks),
        "failure_codes": list(result["failure_codes"]),
        "source_boundary": dict(_object(contract["source_boundary"], "contract source boundary")),
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
        "decision": "CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION_INPUT_FAILED_CLOSED",
        "observed_on": safe_observed_on,
        "rebuild_metadata_subdomain": REBUILD_METADATA_SUBDOMAIN,
        "current_host_metadata_collection_state": "STATIC_INPUT_REJECTED_REDACTED",
        "transport_route_receipt_state": "NOT_ATTEMPTED",
        "transport_eligibility_state": "NOT_ATTEMPTED",
        "current_host_metadata_collection_attempts": 0,
        "current_host_metadata_read": False,
        "repair_execution_authorized": False,
        "core_start_authorized": False,
        "product_outbound_operations_not_attempted": True,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_REBUILD_METADATA_ONE_SHOT_CURRENT_HOST_EVIDENCE_COLLECTION_EXECUTION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "source_or_external_state_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--collection-run-contract", type=Path, required=True)
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--admission-contract", type=Path, required=True)
    parser.add_argument("--core-preflight-contract", type=Path, required=True)
    parser.add_argument("--local-route-policy-contract", type=Path, required=True)
    parser.add_argument("--ssh-config", type=Path, required=True)
    parser.add_argument("--observed-on", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(
            load_contract(args.contract),
            discover_current_host_evidence_collection_execution(
                args.repo_root,
                args.collection_run_contract,
                args.acquisition_contract,
                args.admission_contract,
                args.core_preflight_contract,
                args.local_route_policy_contract,
                args.ssh_config,
                args.observed_on,
            ),
        )
    except (
        CurrentProductionRebuildMetadataOneShotCurrentHostEvidenceCollectionExecutionError,
        collection_contract.CurrentProductionRebuildMetadataCurrentHostEvidenceCollectionRunContractDiagnosticError,
        local_route.CurrentProductionSshLocalRoutePolicyDiagnosticError,
        OSError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        receipt = _failure_receipt(exc, args.observed_on)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
