#!/usr/bin/env python3
"""Classify redacted, local evidence for the fixed core-activation prerequisites."""

from __future__ import annotations

import argparse
import json
import stat
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from current_production_protected_target_metadata_locator import KeyOnlyJsonError, _top_level_json_keys


PASS_STATUS = "PASS_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC"
MAX_CONTRACT_BYTES = 32768
MAX_REDACTED_RECEIPT_BYTES = 16384
CONTRACT_FIELDS = frozenset({"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"})
ROOT_STATES = {"AVAILABLE_READ_ONLY", "UNAVAILABLE_REDACTED", "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"}
PREREQUISITE_STATES = {
    "CONTRACT_NOT_OBSERVED_REDACTED",
    "LOCAL_REDACTED_RECEIPT_NOT_OBSERVED_REDACTED",
    "REDACTED_RECEIPT_REJECTED_REDACTED",
    "NOT_READY_EVIDENCE_OBSERVED_REDACTED",
    "READY_EVIDENCE_OBSERVED_REDACTED",
}


@dataclass(frozen=True)
class Prerequisite:
    identifier: str
    contract_relative_path: Path
    receipt_relative_path: Path
    receipt_type: str
    pass_status: str
    ready_field: str
    authorization_field: str
    receipt_fields: frozenset[str]


def _receipt_fields(*additional: str) -> frozenset[str]:
    return frozenset({
        "schema_version",
        "receipt_type",
        "status",
        "decision",
        "observed_on",
        "checks",
        "failure_codes",
        "source_boundary",
        "claim_boundary",
        *additional,
    })


PREREQUISITES = (
    Prerequisite(
        "CONTROLLED_ENTRY",
        Path("ABD/runtime/current_production_protected_provider_auth_route_resolver_contract.json"),
        Path("ABD/machine/evidence/current-production/controlled-entry.json"),
        "ABD_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER",
        "PASS_CURRENT_PRODUCTION_PROTECTED_PROVIDER_AUTH_ROUTE_RESOLVER",
        "provider_auth_route_resolved",
        "core_start_authorized",
        _receipt_fields("provider_auth_route_resolved", "outbound_operations_not_attempted", "core_start_authorized", "provider_auth_route_state"),
    ),
    Prerequisite(
        "MANAGEMENT_PLANE",
        Path("ABD/runtime/current_production_ovh_management_plane_diagnostic_contract.json"),
        Path("ABD/machine/evidence/current-production/management-plane.json"),
        "ABD_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC",
        "PASS_CURRENT_PRODUCTION_OVH_MANAGEMENT_PLANE_DIAGNOSTIC",
        "management_plane_ready",
        "core_start_authorized",
        _receipt_fields("management_plane_access_observed", "resource_state_observed", "management_plane_ready", "core_start_authorized", "management_plane_state"),
    ),
    Prerequisite(
        "SSH_TRANSPORT",
        Path("ABD/runtime/current_production_ssh_transport_failure_classification_diagnostic_contract.json"),
        Path("ABD/machine/evidence/current-production/ssh-transport.json"),
        "ABD_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC",
        "PASS_CURRENT_PRODUCTION_SSH_TRANSPORT_FAILURE_CLASSIFICATION_DIAGNOSTIC",
        "tcp_reachable",
        "core_start_authorized",
        _receipt_fields("transport_failure_classification_completed", "tcp_reachable", "core_start_authorized", "transport_state"),
    ),
    Prerequisite(
        "FROZEN_CONFIG_SEMANTIC_CHECK",
        Path("ABD/runtime/current_production_core_config_semantic_preflight_contract.json"),
        Path("ABD/machine/evidence/current-production/frozen-config-semantic-check.json"),
        "ABD_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT",
        "PASS_CURRENT_PRODUCTION_CORE_CONFIG_SEMANTIC_PREFLIGHT",
        "config_semantic_valid",
        "core_start_authorized",
        _receipt_fields("config_semantic_valid", "core_start_authorized", "activation_gate"),
    ),
    Prerequisite(
        "CORE_EXECUTION_CONTRACT",
        Path("ABD/runtime/current_production_core_execution_preflight_contract.json"),
        Path("ABD/machine/evidence/current-production/core-execution-contract.json"),
        "ABD_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT",
        "PASS_CURRENT_PRODUCTION_CORE_EXECUTION_PREFLIGHT",
        "input_ready",
        "execution_authorized",
        _receipt_fields("input_ready", "execution_authorized"),
    ),
)


class CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError(ValueError):
    """Raised when a static evidence classification input is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError) as exc:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "core activation prerequisite static evidence classification contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "core activation prerequisite static evidence facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-CORE-ACTIVATION-PREREQUISITE-STATIC-EVIDENCE-CLASSIFICATION-DIAGNOSTIC-001":
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("diagnostic must remain read-only")
    expected = {
        "prerequisite_ids": [spec.identifier for spec in PREREQUISITES],
        "contract_relative_paths": [str(spec.contract_relative_path) for spec in PREREQUISITES],
        "redacted_receipt_relative_paths": [str(spec.receipt_relative_path) for spec in PREREQUISITES],
        "maximum_contract_bytes": MAX_CONTRACT_BYTES,
        "maximum_redacted_receipt_bytes": MAX_REDACTED_RECEIPT_BYTES,
        "github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "worktree_static_text_read_only": True,
        "fixed_contract_key_sets_read_in_memory_only": True,
        "only_fixed_local_redacted_receipt_status_fields_used_in_memory": True,
        "private_object_content_read": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
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
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_ONLY_NOT_ACTUAL_CI_AUTHORIZATION_PROVIDER_RESOURCE_STATE_SSH_CONFIG_SEMANTIC_CHECK_CORE_EXECUTION_DEPLOYMENT_PUBLIC_ENDPOINT_CORE_START_OR_PRODUCTION_RELEASE":
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_PROVIDER_WORKFLOW_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "repository_root_state",
        "contract_set_observed",
        "prerequisite_states",
        "core_activation_prerequisites_ready",
        "private_object_content_read",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "static_source_path_or_raw_content_emitted_or_persisted",
        "github_api_requests",
        "provider_api_requests",
        "ssh_connections_attempted",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC":
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("facts observation date is invalid") from exc
    if facts.get("repository_root_state") not in ROOT_STATES or type(facts.get("contract_set_observed")) is not bool or type(facts.get("core_activation_prerequisites_ready")) is not bool:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("facts state is invalid")
    states = _object(facts.get("prerequisite_states"), "prerequisite states")
    expected_ids = {spec.identifier for spec in PREREQUISITES}
    if set(states) != expected_ids or any(state not in PREREQUISITE_STATES for state in states.values()):
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("prerequisite state set is invalid")
    for field in (
        "private_object_content_read",
        "credential_config_or_runtime_secret_read_or_persisted",
        "workflow_secret_value_read_or_persisted",
        "address_port_or_target_mapping_read_or_persisted",
        "raw_command_content_read_or_persisted",
        "static_source_path_or_raw_content_emitted_or_persisted",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("redaction boundary is invalid")
    for field in ("github_api_requests", "provider_api_requests", "ssh_connections_attempted"):
        if type(facts.get(field)) is not int or facts[field] != 0:
            raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("outbound operation count is invalid")
    ready = all(states[spec.identifier] == "READY_EVIDENCE_OBSERVED_REDACTED" for spec in PREREQUISITES)
    if facts["core_activation_prerequisites_ready"] is not ready:
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("core activation readiness is inconsistent")
    if facts["repository_root_state"] != "AVAILABLE_READ_ONLY":
        if facts["contract_set_observed"] or ready or any(state != "CONTRACT_NOT_OBSERVED_REDACTED" for state in states.values()):
            raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("unavailable root facts are inconsistent")


def _base_facts(observed_on: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_DIAGNOSTIC",
        "observed_on": observed_on,
        "repository_root_state": "UNAVAILABLE_REDACTED",
        "contract_set_observed": False,
        "prerequisite_states": {spec.identifier: "CONTRACT_NOT_OBSERVED_REDACTED" for spec in PREREQUISITES},
        "core_activation_prerequisites_ready": False,
        "private_object_content_read": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "raw_command_content_read_or_persisted": False,
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


def _contract_observed(path: Path) -> bool:
    if _safe_regular_file_state(path, MAX_CONTRACT_BYTES) != "AVAILABLE_READ_ONLY":
        return False
    try:
        return _top_level_json_keys(path) == CONTRACT_FIELDS
    except (OSError, KeyOnlyJsonError):
        return False


def _valid_redacted_receipt(raw: object, spec: Prerequisite) -> bool:
    if not isinstance(raw, dict) or set(raw) != spec.receipt_fields:
        return False
    if raw.get("schema_version") != "1.0.0" or raw.get("receipt_type") != spec.receipt_type or raw.get("status") != spec.pass_status:
        return False
    try:
        date.fromisoformat(str(raw.get("observed_on")))
    except ValueError:
        return False
    if type(raw.get(spec.ready_field)) is not bool or raw.get(spec.authorization_field) is not False:
        return False
    if not isinstance(raw.get("decision"), str) or not isinstance(raw.get("claim_boundary"), str) or not isinstance(raw.get("source_boundary"), dict):
        return False
    checks = raw.get("checks")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        return False
    failure_codes = raw.get("failure_codes")
    return isinstance(failure_codes, list) and all(isinstance(code, str) for code in failure_codes)


def _receipt_state(path: Path, spec: Prerequisite) -> str:
    state = _safe_regular_file_state(path, MAX_REDACTED_RECEIPT_BYTES)
    if state == "UNAVAILABLE_REDACTED":
        return "LOCAL_REDACTED_RECEIPT_NOT_OBSERVED_REDACTED"
    if state != "AVAILABLE_READ_ONLY":
        return "REDACTED_RECEIPT_REJECTED_REDACTED"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "REDACTED_RECEIPT_REJECTED_REDACTED"
    if not _valid_redacted_receipt(raw, spec):
        return "REDACTED_RECEIPT_REJECTED_REDACTED"
    return "READY_EVIDENCE_OBSERVED_REDACTED" if raw[spec.ready_field] else "NOT_READY_EVIDENCE_OBSERVED_REDACTED"


def discover_static_evidence(repo_root: Path, observed_on: str | None = None) -> dict[str, Any]:
    """Read only fixed contracts and optional local redacted receipt status fields."""

    facts = _base_facts(observed_on or datetime.now(timezone.utc).date().isoformat())
    try:
        root_info = repo_root.lstat()
    except OSError:
        return facts
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        facts["repository_root_state"] = "UNSAFE_REPOSITORY_ROOT_REJECTED_REDACTED"
        return facts
    facts["repository_root_state"] = "AVAILABLE_READ_ONLY"
    states: dict[str, str] = {}
    contracts: dict[str, bool] = {}
    for spec in PREREQUISITES:
        contracts[spec.identifier] = _contract_observed(repo_root / spec.contract_relative_path)
    facts["contract_set_observed"] = all(contracts.values())
    for spec in PREREQUISITES:
        states[spec.identifier] = _receipt_state(repo_root / spec.receipt_relative_path, spec) if contracts[spec.identifier] else "CONTRACT_NOT_OBSERVED_REDACTED"
    facts["prerequisite_states"] = states
    facts["core_activation_prerequisites_ready"] = all(state == "READY_EVIDENCE_OBSERVED_REDACTED" for state in states.values())
    return facts


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    states = _object(facts["prerequisite_states"], "prerequisite states")
    checks = [
        {"id": "CORE_ACTIVATION_CONTRACT_SET_OBSERVED", "passed": facts["contract_set_observed"]},
        *[{"id": "%s_READY_EVIDENCE_OBSERVED" % spec.identifier, "passed": states[spec.identifier] == "READY_EVIDENCE_OBSERVED_REDACTED"} for spec in PREREQUISITES],
        {"id": "OUTBOUND_OPERATIONS_NOT_ATTEMPTED", "passed": True},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    ready = bool(facts["core_activation_prerequisites_ready"])
    return {
        "status": PASS_STATUS,
        "decision": "CURRENT_PRODUCTION_CORE_ACTIVATION_STATIC_EVIDENCE_COMPLETE_SEPARATE_CORE_ACTION_AUTHORIZATION_REQUIRED" if ready else "CURRENT_PRODUCTION_CORE_ACTIVATION_STATIC_EVIDENCE_INCOMPLETE_NO_CORE_ACTION_AUTHORIZED",
        "core_activation_prerequisites_ready": ready,
        "prerequisite_states": dict(states),
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if result["core_start_authorized"] is not False or not isinstance(result["core_activation_prerequisites_ready"], bool):
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "core_activation_prerequisites_ready": result["core_activation_prerequisites_ready"],
        "prerequisite_states": result["prerequisite_states"],
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
        "decision": "CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "core_activation_prerequisites_ready": False,
        "prerequisite_states": {spec.identifier: "CONTRACT_NOT_OBSERVED_REDACTED" for spec in PREREQUISITES},
        "outbound_operations_not_attempted": True,
        "core_start_authorized": False,
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_CORE_ACTIVATION_PREREQUISITE_STATIC_EVIDENCE_CLASSIFICATION_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "provider_workflow_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), discover_static_evidence(args.repo_root))
    except (CurrentProductionCoreActivationPrerequisiteStaticEvidenceClassificationDiagnosticError, OSError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
