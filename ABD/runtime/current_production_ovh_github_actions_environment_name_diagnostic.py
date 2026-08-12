#!/usr/bin/env python3
"""Evaluate one redacted GitHub Actions OVH environment-name diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC"
GITHUB_ACCESS_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED"}
ENVIRONMENT_STATES = {
    "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT",
    "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_REDACTED",
    "GITHUB_ACTIONS_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED",
    "GITHUB_ACTIONS_ENVIRONMENT_RESPONSE_INVALID_REDACTED",
}


class CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted environment fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError) as exc:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH GitHub Actions environment-name diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH GitHub Actions environment-name facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-GITHUB-ACTIONS-ENVIRONMENT-NAME-DIAGNOSTIC-001":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("diagnostic must remain read-only")
    expected = {
        "repository": "LinzeColin/MetaDatabase",
        "github_graphql_operation_type": "query",
        "graphql_selection": "repository.environment.name",
        "canonical_environment_name": "production",
        "maximum_github_graphql_query_requests": 1,
        "maximum_github_query_timeout_seconds": 10,
        "provider_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "environment_names_read_in_memory_only": True,
        "environment_values_read_or_emitted": False,
        "github_actions_environment_secret_name_or_value_read_or_emitted": False,
        "github_graphql_mutation_executed": False,
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
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC_ONLY_NOT_ENVIRONMENT_VALUE_OR_SECRET_INSPECTION_GRAPHQL_MUTATION_WORKFLOW_CREATION_WORKFLOW_DISPATCH_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_GITHUB_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "github_actions_access",
        "environment_name_scope_state",
        "canonical_production_environment_observed",
        "github_graphql_query_requests",
        "environment_names_read_in_memory_only",
        "environment_values_read_or_emitted",
        "github_actions_environment_secret_name_or_value_read_or_emitted",
        "github_graphql_mutation_executed",
        "github_actions_workflow_created_updated_or_dispatched",
        "provider_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("facts observation date is invalid") from exc
    if facts.get("github_actions_access") not in GITHUB_ACCESS_STATES:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("GitHub Actions access state is invalid")
    if facts.get("environment_name_scope_state") not in ENVIRONMENT_STATES:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("environment-name scope state is invalid")
    if type(facts.get("canonical_production_environment_observed")) is not bool:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("canonical environment observation is invalid")
    if type(facts.get("github_graphql_query_requests")) is not int or facts["github_graphql_query_requests"] not in {0, 1}:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("GitHub GraphQL query count is invalid")
    if type(facts.get("provider_api_requests")) is not int or facts["provider_api_requests"] != 0:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("provider API request count is invalid")
    if facts.get("environment_names_read_in_memory_only") is not True:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("environment-name boundary is invalid")
    for field in (
        "environment_values_read_or_emitted",
        "github_actions_environment_secret_name_or_value_read_or_emitted",
        "github_graphql_mutation_executed",
        "github_actions_workflow_created_updated_or_dispatched",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("source boundary is invalid")
    state = facts["environment_name_scope_state"]
    observed = facts["canonical_production_environment_observed"]
    if facts["github_actions_access"] == "UNAVAILABLE_REDACTED":
        if state != "GITHUB_ACTIONS_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED" or observed is not False:
            raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("unavailable GitHub Actions facts are inconsistent")
    elif state == "GITHUB_ACTIONS_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED":
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("available GitHub Actions facts are inconsistent")
    elif observed != (state == "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT"):
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("canonical environment facts are inconsistent")


def _environment_source_state(facts: Mapping[str, Any]) -> str:
    if facts["canonical_production_environment_observed"]:
        return "OVH_GITHUB_ACTIONS_CANONICAL_ENVIRONMENT_OBSERVED"
    return "OVH_GITHUB_ACTIONS_%s" % facts["environment_name_scope_state"]


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    observed = bool(facts["canonical_production_environment_observed"])
    scope_state = str(facts["environment_name_scope_state"])
    if observed:
        decision = "CANONICAL_PRODUCTION_ENVIRONMENT_OBSERVED_SEPARATE_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_REQUIRED"
    elif scope_state == "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_REDACTED":
        decision = "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_NO_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_AUTHORIZED"
    else:
        decision = "GITHUB_ACTIONS_ENVIRONMENT_SCOPE_NOT_CONFIRMED_NO_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_AUTHORIZED"
    checks = [
        {"id": "OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC_COMPLETED", "passed": True},
        {"id": "OVH_GITHUB_ACTIONS_CANONICAL_PRODUCTION_ENVIRONMENT_OBSERVED", "passed": observed},
        {"id": "OVH_GITHUB_GRAPHQL_QUERY_AT_MOST_ONCE", "passed": facts["github_graphql_query_requests"] <= 1},
        {"id": "OVH_GITHUB_ACTIONS_WORKFLOW_NOT_DISPATCHED", "passed": facts["github_actions_workflow_created_updated_or_dispatched"] is False},
        {"id": "OVH_PROVIDER_API_REQUEST_NOT_SENT", "passed": facts["provider_api_requests"] == 0},
    ]
    return {
        "status": PASS_STATUS,
        "decision": decision,
        "github_actions_environment_diagnosed": True,
        "canonical_production_environment_observed": observed,
        "environment_secret_name_diagnostic_requires_separate_phase": True,
        "workflow_not_dispatched": True,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "github_actions_environment_name_state": _environment_source_state(facts),
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("github_actions_environment_diagnosed", "canonical_production_environment_observed", "environment_secret_name_diagnostic_requires_separate_phase", "workflow_not_dispatched", "provider_api_request_not_sent")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "github_actions_environment_diagnosed": result["github_actions_environment_diagnosed"],
        "canonical_production_environment_observed": result["canonical_production_environment_observed"],
        "environment_secret_name_diagnostic_requires_separate_phase": result["environment_secret_name_diagnostic_requires_separate_phase"],
        "workflow_not_dispatched": result["workflow_not_dispatched"],
        "provider_api_request_not_sent": result["provider_api_request_not_sent"],
        "core_start_authorized": False,
        "github_actions_environment_name_state": result["github_actions_environment_name_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "github_actions_environment_diagnosed": False,
        "canonical_production_environment_observed": False,
        "environment_secret_name_diagnostic_requires_separate_phase": True,
        "workflow_not_dispatched": True,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "github_actions_environment_name_state": "OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC_INPUT_FAILED"],
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
