#!/usr/bin/env python3
"""Evaluate one redacted GitHub Actions OVH secret-name diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC"
GITHUB_ACCESS_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED"}
SECRET_GROUP_STATES = {"COMPLETE_LEGACY_AUTH_TARGET_SECRET_GROUP", "NO_COMPLETE_LEGACY_SECRET_GROUP_REDACTED", "GITHUB_ACTIONS_UNAVAILABLE_REDACTED"}


class CurrentProductionOvhGithubActionsSecretNameDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted GitHub Actions fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhGithubActionsSecretNameDiagnosticError) as exc:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH GitHub Actions secret-name diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH GitHub Actions secret-name facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-GITHUB-ACTIONS-SECRET-NAME-DIAGNOSTIC-001":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("diagnostic must remain read-only")
    expected = {
        "repository": "LinzeColin/MetaDatabase",
        "github_secret_application": "actions",
        "legacy_auth_target_secret_groups": ["OVH_STANDARD", "ABD_OVH_SCOPED"],
        "maximum_github_query_timeout_seconds": 10,
        "provider_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "github_secret_names_read_in_memory_only": True,
        "github_secret_values_read_or_emitted": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "branch_pr_or_repository_state_changed": False,
        "browser_login_submitted": False,
        "provider_api_request_sent": False,
        "provider_resource_created_deleted_rebuilt_or_restarted": False,
        "provider_network_security_group_ip_dns_or_cloudflare_changed": False,
        "host_runtime_or_configuration_changed": False,
        "real_time_soak_waited": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if _object(contract.get("source_boundary"), "source boundary") != boundary:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC_ONLY_NOT_SECRET_VALUE_VALIDATION_WORKFLOW_CREATION_WORKFLOW_DISPATCH_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_GITHUB_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "github_actions_access",
        "secret_name_group_state",
        "secret_name_group_ready",
        "provider_api_requests",
        "secret_value_read_or_emitted",
        "github_actions_workflow_created_updated_or_dispatched",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("facts observation date is invalid") from exc
    if facts.get("github_actions_access") not in GITHUB_ACCESS_STATES:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("GitHub Actions access state is invalid")
    if facts.get("secret_name_group_state") not in SECRET_GROUP_STATES:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("secret-name group state is invalid")
    if type(facts.get("secret_name_group_ready")) is not bool:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("secret-name group readiness is invalid")
    if type(facts.get("provider_api_requests")) is not int or facts["provider_api_requests"] != 0:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("provider API request count is invalid")
    for field in ("secret_value_read_or_emitted", "github_actions_workflow_created_updated_or_dispatched", "browser_login_submitted"):
        if facts.get(field) is not False:
            raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("source boundary is invalid")
    if facts["github_actions_access"] == "UNAVAILABLE_REDACTED":
        if facts["secret_name_group_state"] != "GITHUB_ACTIONS_UNAVAILABLE_REDACTED" or facts["secret_name_group_ready"] is not False:
            raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("unavailable GitHub Actions facts are inconsistent")
    elif facts["secret_name_group_state"] == "GITHUB_ACTIONS_UNAVAILABLE_REDACTED":
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("available GitHub Actions facts are inconsistent")
    elif facts["secret_name_group_ready"] != (facts["secret_name_group_state"] == "COMPLETE_LEGACY_AUTH_TARGET_SECRET_GROUP"):
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("secret-name group facts are inconsistent")


def _secret_name_source_state(facts: Mapping[str, Any]) -> str:
    if facts["secret_name_group_ready"]:
        return "OVH_GITHUB_ACTIONS_SECRET_NAME_GROUP_READY_FOR_SEPARATE_WORKFLOW_CONTRACT"
    return "OVH_GITHUB_ACTIONS_%s" % facts["secret_name_group_state"]


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    ready = bool(facts["secret_name_group_ready"])
    checks = [
        {"id": "OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC_COMPLETED", "passed": True},
        {"id": "OVH_GITHUB_ACTIONS_SECRET_NAME_GROUP_READY", "passed": ready},
        {"id": "OVH_GITHUB_ACTIONS_WORKFLOW_NOT_DISPATCHED", "passed": facts["github_actions_workflow_created_updated_or_dispatched"] is False},
        {"id": "OVH_PROVIDER_API_REQUEST_NOT_SENT", "passed": facts["provider_api_requests"] == 0},
    ]
    failure_codes = [str(check["id"]) for check in checks if not check["passed"]]
    return {
        "status": PASS_STATUS,
        "decision": "OVH_GITHUB_ACTIONS_SECRET_NAME_GROUP_READY_SEPARATE_WORKFLOW_CONTRACT_REQUIRED" if ready else "OVH_GITHUB_ACTIONS_SECRET_NAME_GROUP_NOT_READY_NO_WORKFLOW_OR_PROVIDER_REQUEST_AUTHORIZED",
        "github_actions_diagnosed": True,
        "secret_name_group_ready": ready,
        "workflow_not_dispatched": True,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "github_actions_secret_name_state": _secret_name_source_state(facts),
        "checks": checks,
        "failure_codes": failure_codes,
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("github_actions_diagnosed", "secret_name_group_ready", "workflow_not_dispatched", "provider_api_request_not_sent")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhGithubActionsSecretNameDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "github_actions_diagnosed": result["github_actions_diagnosed"],
        "secret_name_group_ready": result["secret_name_group_ready"],
        "workflow_not_dispatched": result["workflow_not_dispatched"],
        "provider_api_request_not_sent": result["provider_api_request_not_sent"],
        "core_start_authorized": False,
        "github_actions_secret_name_state": result["github_actions_secret_name_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "github_actions_diagnosed": False,
        "secret_name_group_ready": False,
        "workflow_not_dispatched": True,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "github_actions_secret_name_state": "OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC_INPUT_FAILED"],
        "error_type": type(error).__name__,
        "github_provider_or_host_changed": False,
        "real_time_soak_waited": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_contract(args.contract), load_facts(args.facts))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhGithubActionsSecretNameDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
