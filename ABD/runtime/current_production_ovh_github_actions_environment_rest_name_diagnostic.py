#!/usr/bin/env python3
"""Evaluate one redacted GitHub Actions OVH REST environment-name diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS_STATUS = "PASS_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC"
FAIL_STATUS = "FAIL_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC"
RECEIPT_TYPE = "ABD_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC"
GITHUB_REST_ACCESS_STATES = {"AVAILABLE", "UNAVAILABLE_REDACTED"}
ENVIRONMENT_PAGE_STATES = {
    "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT_IN_FIRST_PAGE",
    "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_IN_FIRST_PAGE_REDACTED",
    "GITHUB_ACTIONS_REST_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED",
    "GITHUB_ACTIONS_REST_ENVIRONMENT_RESPONSE_INVALID_REDACTED",
}


class CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError(ValueError):
    """Raised when a diagnostic contract or redacted REST environment fact is malformed."""


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("%s must be an object" % name)
    return value


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("input must be a regular file")
    return path.read_text(encoding="utf-8")


def _load(path: Path, name: str) -> Mapping[str, Any]:
    try:
        return _object(json.loads(_read_text(path)), name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError) as exc:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("%s is unreadable" % name) from exc


def load_contract(path: Path) -> Mapping[str, Any]:
    return _load(path, "OVH GitHub Actions REST environment-name diagnostic contract")


def load_facts(path: Path) -> Mapping[str, Any]:
    return _load(path, "redacted OVH GitHub Actions REST environment-name facts")


def validate_contract(contract: Mapping[str, Any]) -> None:
    required = {"schema_version", "contract_id", "product_version", "status", "expected", "source_boundary", "claim_boundary", "rollback"}
    if set(contract) != required:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("contract field set is not exact")
    if contract.get("schema_version") != "1.0.0":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("contract schema is not supported")
    if contract.get("contract_id") != "ABD-POST-FREEZE-CURRENT-PRODUCTION-OVH-GITHUB-ACTIONS-ENVIRONMENT-REST-NAME-DIAGNOSTIC-001":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("contract identifier is not exact")
    if contract.get("product_version") != "0.0.0.1":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("product version is not exact")
    if contract.get("status") != "ONE_SHOT_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC_READ_ONLY":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("diagnostic must remain read-only")
    expected = {
        "repository": "LinzeColin/MetaDatabase",
        "github_rest_method": "GET",
        "github_rest_endpoint": "repos/LinzeColin/MetaDatabase/environments?per_page=100&page=1",
        "github_cli_name_selection": ".environments | map(.name)",
        "canonical_environment_name": "production",
        "maximum_environment_page_size": 100,
        "maximum_github_rest_get_requests": 1,
        "maximum_github_query_timeout_seconds": 10,
        "provider_api_requests": 0,
    }
    if _object(contract.get("expected"), "expected") != expected:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("diagnostic expectations are not exact")
    boundary = {
        "github_rest_get_only": True,
        "github_rest_response_reduced_to_environment_names_in_cli": True,
        "environment_names_read_in_memory_only": True,
        "github_rest_non_name_response_fields_emitted_or_persisted": False,
        "github_actions_environment_secret_name_or_value_read_or_emitted": False,
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
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("source boundary is not exact")
    if contract.get("claim_boundary") != "CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC_ONLY_NOT_SECRET_INSPECTION_WORKFLOW_CREATION_WORKFLOW_DISPATCH_PROVIDER_API_QUERY_HOST_RECOVERY_SSH_TRANSPORT_RETRY_CONFIG_SEMANTIC_CHECK_UNIT_INSTALL_CORE_START_CONNECTOR_ACTIVATION_OR_PUBLIC_RELEASE":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("claim boundary is not exact")
    if _object(contract.get("rollback"), "rollback") != {
        "action": "NO_GITHUB_PROVIDER_OR_HOST_MUTATION_NO_RUNTIME_ROLLBACK_REQUIRED",
        "current_candidate_shadow_changed": False,
        "private_evidence_deleted_automatically": False,
    }:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("rollback boundary is not exact")


def validate_facts(facts: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "observation_type",
        "observed_on",
        "github_actions_rest_access",
        "environment_name_page_state",
        "canonical_production_environment_observed_in_first_page",
        "github_rest_get_requests",
        "environment_names_read_in_memory_only",
        "github_rest_non_name_response_fields_emitted_or_persisted",
        "github_actions_environment_secret_name_or_value_read_or_emitted",
        "github_actions_workflow_created_updated_or_dispatched",
        "provider_api_requests",
        "browser_login_submitted",
    }
    if set(facts) != required:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("facts field set is not exact")
    if facts.get("schema_version") != "1.0.0" or facts.get("observation_type") != "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("facts identity is not exact")
    try:
        date.fromisoformat(str(facts.get("observed_on")))
    except ValueError as exc:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("facts observation date is invalid") from exc
    if facts.get("github_actions_rest_access") not in GITHUB_REST_ACCESS_STATES:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("GitHub REST access state is invalid")
    if facts.get("environment_name_page_state") not in ENVIRONMENT_PAGE_STATES:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("environment-name page state is invalid")
    if type(facts.get("canonical_production_environment_observed_in_first_page")) is not bool:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("canonical environment observation is invalid")
    if type(facts.get("github_rest_get_requests")) is not int or facts["github_rest_get_requests"] not in {0, 1}:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("GitHub REST request count is invalid")
    if type(facts.get("provider_api_requests")) is not int or facts["provider_api_requests"] != 0:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("provider API request count is invalid")
    if facts.get("environment_names_read_in_memory_only") is not True:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("environment-name boundary is invalid")
    for field in (
        "github_rest_non_name_response_fields_emitted_or_persisted",
        "github_actions_environment_secret_name_or_value_read_or_emitted",
        "github_actions_workflow_created_updated_or_dispatched",
        "browser_login_submitted",
    ):
        if facts.get(field) is not False:
            raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("source boundary is invalid")
    state = facts["environment_name_page_state"]
    observed = facts["canonical_production_environment_observed_in_first_page"]
    if facts["github_actions_rest_access"] == "UNAVAILABLE_REDACTED":
        if state != "GITHUB_ACTIONS_REST_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED" or observed is not False:
            raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("unavailable GitHub REST facts are inconsistent")
    elif state == "GITHUB_ACTIONS_REST_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED":
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("available GitHub REST facts are inconsistent")
    elif observed != (state == "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT_IN_FIRST_PAGE"):
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("canonical environment facts are inconsistent")


def _environment_source_state(facts: Mapping[str, Any]) -> str:
    if facts["canonical_production_environment_observed_in_first_page"]:
        return "OVH_GITHUB_ACTIONS_REST_CANONICAL_ENVIRONMENT_OBSERVED_IN_FIRST_PAGE"
    return "OVH_GITHUB_ACTIONS_REST_%s" % facts["environment_name_page_state"]


def evaluate_diagnostic(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    validate_facts(facts)
    observed = bool(facts["canonical_production_environment_observed_in_first_page"])
    page_state = str(facts["environment_name_page_state"])
    if observed:
        decision = "CANONICAL_PRODUCTION_ENVIRONMENT_OBSERVED_IN_FIRST_PAGE_SEPARATE_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_REQUIRED"
    elif page_state == "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_IN_FIRST_PAGE_REDACTED":
        decision = "CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_IN_FIRST_PAGE_NO_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_AUTHORIZED"
    else:
        decision = "GITHUB_ACTIONS_REST_ENVIRONMENT_SCOPE_NOT_CONFIRMED_NO_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_AUTHORIZED"
    checks = [
        {"id": "OVH_GITHUB_ACTIONS_REST_ENVIRONMENT_NAME_DIAGNOSTIC_COMPLETED", "passed": True},
        {"id": "OVH_GITHUB_ACTIONS_REST_CANONICAL_PRODUCTION_ENVIRONMENT_OBSERVED_IN_FIRST_PAGE", "passed": observed},
        {"id": "OVH_GITHUB_REST_GET_AT_MOST_ONCE", "passed": facts["github_rest_get_requests"] <= 1},
        {"id": "OVH_GITHUB_ACTIONS_WORKFLOW_NOT_DISPATCHED", "passed": facts["github_actions_workflow_created_updated_or_dispatched"] is False},
        {"id": "OVH_PROVIDER_API_REQUEST_NOT_SENT", "passed": facts["provider_api_requests"] == 0},
    ]
    return {
        "status": PASS_STATUS,
        "decision": decision,
        "github_actions_rest_environment_diagnosed": True,
        "canonical_production_environment_observed_in_first_page": observed,
        "environment_secret_name_diagnostic_separate_phase_only": True,
        "workflow_not_dispatched": True,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "github_actions_rest_environment_name_state": _environment_source_state(facts),
        "checks": checks,
        "failure_codes": [str(check["id"]) for check in checks if not check["passed"]],
    }


def build_receipt(contract: Mapping[str, Any], facts: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_diagnostic(contract, facts)
    checks = result["checks"]
    if not all(isinstance(result[key], bool) for key in ("github_actions_rest_environment_diagnosed", "canonical_production_environment_observed_in_first_page", "environment_secret_name_diagnostic_separate_phase_only", "workflow_not_dispatched", "provider_api_request_not_sent")) or result["core_start_authorized"] is not False:
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("diagnostic authorization state is invalid")
    if not isinstance(checks, list) or any(not isinstance(check, dict) or set(check) != {"id", "passed"} for check in checks):
        raise CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError("diagnostic checks are invalid")
    return {
        "schema_version": "1.0.0",
        "receipt_type": RECEIPT_TYPE,
        "status": result["status"],
        "decision": result["decision"],
        "observed_on": facts["observed_on"],
        "github_actions_rest_environment_diagnosed": result["github_actions_rest_environment_diagnosed"],
        "canonical_production_environment_observed_in_first_page": result["canonical_production_environment_observed_in_first_page"],
        "environment_secret_name_diagnostic_separate_phase_only": result["environment_secret_name_diagnostic_separate_phase_only"],
        "workflow_not_dispatched": result["workflow_not_dispatched"],
        "provider_api_request_not_sent": result["provider_api_request_not_sent"],
        "core_start_authorized": False,
        "github_actions_rest_environment_name_state": result["github_actions_rest_environment_name_state"],
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
        "decision": "CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC_INPUT_FAILED_CLOSED",
        "observed_on": "INVALID",
        "github_actions_rest_environment_diagnosed": False,
        "canonical_production_environment_observed_in_first_page": False,
        "environment_secret_name_diagnostic_separate_phase_only": True,
        "workflow_not_dispatched": True,
        "provider_api_request_not_sent": True,
        "core_start_authorized": False,
        "github_actions_rest_environment_name_state": "OVH_GITHUB_ACTIONS_REST_ENVIRONMENT_NAME_DIAGNOSTIC_INPUT_INVALID",
        "checks": [],
        "failure_codes": ["CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC_INPUT_FAILED"],
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError, ValueError) as exc:
        receipt = _failure_receipt(exc)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
