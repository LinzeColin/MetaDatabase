from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_github_actions_environment_name_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_github_actions_environment_name_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ovh_github_actions_environment_name_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "github_actions_access": "AVAILABLE",
        "environment_name_scope_state": "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT",
        "canonical_production_environment_observed": True,
        "github_graphql_query_requests": 1,
        "environment_names_read_in_memory_only": True,
        "environment_values_read_or_emitted": False,
        "github_actions_environment_secret_name_or_value_read_or_emitted": False,
        "github_graphql_mutation_executed": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "provider_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_name_only_graphql_query_zero_provider_request_and_no_workflow_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["repository"] == "LinzeColin/MetaDatabase"
    assert expected["github_graphql_operation_type"] == "query"
    assert expected["graphql_selection"] == "repository.environment.name"
    assert expected["canonical_environment_name"] == "production"
    assert expected["maximum_github_graphql_query_requests"] == 1
    assert expected["maximum_github_query_timeout_seconds"] == 10
    assert boundary["environment_values_read_or_emitted"] is False
    assert boundary["github_actions_environment_secret_name_or_value_read_or_emitted"] is False
    assert boundary["github_graphql_mutation_executed"] is False
    assert boundary["github_actions_workflow_created_updated_or_dispatched"] is False
    assert boundary["provider_api_request_sent"] is False


def test_observed_canonical_environment_requires_a_separate_secret_name_phase() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["github_actions_environment_diagnosed"] is True
    assert result["canonical_production_environment_observed"] is True
    assert result["environment_secret_name_diagnostic_requires_separate_phase"] is True
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False
    assert result["github_actions_environment_name_state"] == "OVH_GITHUB_ACTIONS_CANONICAL_ENVIRONMENT_OBSERVED"


def test_not_observed_environment_is_a_complete_zero_provider_request_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        environment_name_scope_state="CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_REDACTED",
        canonical_production_environment_observed=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["canonical_production_environment_observed"] is False
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False


def test_unavailable_github_actions_fails_closed_without_workflow_or_provider_request() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        github_actions_access="UNAVAILABLE_REDACTED",
        environment_name_scope_state="GITHUB_ACTIONS_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED",
        canonical_production_environment_observed=False,
        github_graphql_query_requests=0,
    ))

    assert result["status"] == PASS_STATUS
    assert result["canonical_production_environment_observed"] is False
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True


def test_invalid_environment_response_is_not_promoted_to_an_observation() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        environment_name_scope_state="GITHUB_ACTIONS_ENVIRONMENT_RESPONSE_INVALID_REDACTED",
        canonical_production_environment_observed=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["canonical_production_environment_observed"] is False
    assert result["decision"] == "GITHUB_ACTIONS_ENVIRONMENT_SCOPE_NOT_CONFIRMED_NO_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_AUTHORIZED"


def test_facts_reject_environment_name_or_value_leakage() -> None:
    facts = _facts()
    facts["environment_name"] = "not retained"

    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_mutation_workflow_or_provider_request() -> None:
    facts = _facts(github_graphql_mutation_executed=True)
    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError, match="source boundary"):
        validate_facts(facts)

    facts = _facts(github_actions_workflow_created_updated_or_dispatched=True)
    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError, match="source boundary"):
        validate_facts(facts)

    facts = _facts(provider_api_requests=1)
    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError, match="request count"):
        validate_facts(facts)


def test_receipt_redacts_access_scope_and_environment_name_details() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["canonical_production_environment_observed"] is True
    assert receipt["environment_secret_name_diagnostic_requires_separate_phase"] is True
    assert receipt["workflow_not_dispatched"] is True
    assert receipt["provider_api_request_not_sent"] is True
    assert receipt["core_start_authorized"] is False
    assert '"github_actions_access":' not in serialized
    assert '"environment_name_scope_state":' not in serialized
    assert '"production"' not in serialized


def test_contract_cannot_relax_environment_value_or_graphql_mutation_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["environment_values_read_or_emitted"] = True

    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_has_one_name_only_graphql_query_and_no_secret_or_workflow_write_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'OWNER = "LinzeColin"' in source
    assert 'REPOSITORY = "MetaDatabase"' in source
    assert 'CANONICAL_ENVIRONMENT_NAME = "production"' in source
    assert '"graphql",' in source
    assert 'query($owner: String!, $repository: String!, $environmentName: String!)' in source
    assert 'environment(name: $environmentName)' in source
    assert '".data.repository.environment.name // empty"' in source
    assert "TIMEOUT_SECONDS = 10" in source
    assert "print(query.stdout)" not in source
    assert "print(environment_name)" not in source
    assert "--paginate" not in source
    for forbidden in (
        "mutation {",
        "workflow run",
        "secret list",
        "secret set",
        "secret remove",
        "secret delete",
        '"-X", "POST"',
        '"-X", "PUT"',
        '"-X", "PATCH"',
        '"-X", "DELETE"',
        "push ",
        "curl ",
        "wget ",
        "urllib.request",
        "http.client",
        "import requests",
        "requests.",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
        "/etc/abd/config.json",
        "/etc/abd/runtime.env",
        "/etc/abd/secrets/runtime",
    ):
        assert forbidden not in source


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentNameDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_NAME_DIAGNOSTIC"
