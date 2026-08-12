from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_github_actions_environment_rest_name_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_github_actions_environment_rest_name_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ovh_github_actions_environment_rest_name_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "github_actions_rest_access": "AVAILABLE",
        "environment_name_page_state": "CANONICAL_PRODUCTION_ENVIRONMENT_PRESENT_IN_FIRST_PAGE",
        "canonical_production_environment_observed_in_first_page": True,
        "github_rest_get_requests": 1,
        "environment_names_read_in_memory_only": True,
        "github_rest_non_name_response_fields_emitted_or_persisted": False,
        "github_actions_environment_secret_name_or_value_read_or_emitted": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "provider_api_requests": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_single_get_name_only_zero_provider_request_and_no_workflow_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["repository"] == "LinzeColin/MetaDatabase"
    assert expected["github_rest_method"] == "GET"
    assert expected["github_rest_endpoint"] == "repos/LinzeColin/MetaDatabase/environments?per_page=100&page=1"
    assert expected["github_cli_name_selection"] == ".environments | map(.name)"
    assert expected["canonical_environment_name"] == "production"
    assert expected["maximum_environment_page_size"] == 100
    assert expected["maximum_github_rest_get_requests"] == 1
    assert expected["maximum_github_query_timeout_seconds"] == 10
    assert boundary["github_rest_get_only"] is True
    assert boundary["github_rest_response_reduced_to_environment_names_in_cli"] is True
    assert boundary["github_rest_non_name_response_fields_emitted_or_persisted"] is False
    assert boundary["github_actions_environment_secret_name_or_value_read_or_emitted"] is False
    assert boundary["github_actions_workflow_created_updated_or_dispatched"] is False
    assert boundary["provider_api_request_sent"] is False


def test_observed_canonical_environment_requires_a_separate_secret_name_phase() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["github_actions_rest_environment_diagnosed"] is True
    assert result["canonical_production_environment_observed_in_first_page"] is True
    assert result["environment_secret_name_diagnostic_separate_phase_only"] is True
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False
    assert result["github_actions_rest_environment_name_state"] == "OVH_GITHUB_ACTIONS_REST_CANONICAL_ENVIRONMENT_OBSERVED_IN_FIRST_PAGE"


def test_not_observed_first_page_is_a_complete_zero_provider_request_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        environment_name_page_state="CANONICAL_PRODUCTION_ENVIRONMENT_NOT_OBSERVED_IN_FIRST_PAGE_REDACTED",
        canonical_production_environment_observed_in_first_page=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["canonical_production_environment_observed_in_first_page"] is False
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False


def test_unavailable_github_rest_fails_closed_without_workflow_or_provider_request() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        github_actions_rest_access="UNAVAILABLE_REDACTED",
        environment_name_page_state="GITHUB_ACTIONS_REST_ENVIRONMENT_LOOKUP_UNAVAILABLE_REDACTED",
        canonical_production_environment_observed_in_first_page=False,
        github_rest_get_requests=0,
    ))

    assert result["status"] == PASS_STATUS
    assert result["canonical_production_environment_observed_in_first_page"] is False
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True


def test_invalid_rest_response_is_not_promoted_to_an_observation() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        environment_name_page_state="GITHUB_ACTIONS_REST_ENVIRONMENT_RESPONSE_INVALID_REDACTED",
        canonical_production_environment_observed_in_first_page=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["canonical_production_environment_observed_in_first_page"] is False
    assert result["decision"] == "GITHUB_ACTIONS_REST_ENVIRONMENT_SCOPE_NOT_CONFIRMED_NO_ENVIRONMENT_SECRET_NAME_DIAGNOSTIC_AUTHORIZED"


def test_facts_reject_environment_name_leakage() -> None:
    facts = _facts()
    facts["environment_name"] = "not retained"

    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_non_name_response_emission_workflow_or_provider_request() -> None:
    facts = _facts(github_rest_non_name_response_fields_emitted_or_persisted=True)
    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError, match="source boundary"):
        validate_facts(facts)

    facts = _facts(github_actions_workflow_created_updated_or_dispatched=True)
    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError, match="source boundary"):
        validate_facts(facts)

    facts = _facts(provider_api_requests=1)
    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError, match="request count"):
        validate_facts(facts)


def test_receipt_redacts_access_page_and_environment_name_details() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["canonical_production_environment_observed_in_first_page"] is True
    assert receipt["environment_secret_name_diagnostic_separate_phase_only"] is True
    assert receipt["workflow_not_dispatched"] is True
    assert receipt["provider_api_request_not_sent"] is True
    assert receipt["core_start_authorized"] is False
    assert '"github_actions_rest_access":' not in serialized
    assert '"environment_name_page_state":' not in serialized
    assert '"production"' not in serialized


def test_contract_cannot_relax_get_or_non_name_response_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["github_rest_get_only"] = False

    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_has_one_bounded_get_name_query_and_no_secret_or_workflow_write_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'REPOSITORY = "LinzeColin/MetaDatabase"' in source
    assert 'ENDPOINT = "repos/LinzeColin/MetaDatabase/environments?per_page=100&page=1"' in source
    assert 'CANONICAL_ENVIRONMENT_NAME = "production"' in source
    assert 'NAME_SELECTION = ".environments | map(.name)"' in source
    assert '[gh, "api", "--method", "GET", ENDPOINT, "--jq", NAME_SELECTION]' in source
    assert "TIMEOUT_SECONDS = 10" in source
    assert "print(query.stdout)" not in source
    assert "print(names)" not in source
    assert "--paginate" not in source
    for forbidden in (
        "secret list",
        "secret set",
        "secret remove",
        "secret delete",
        '"--method", "POST"',
        '"--method", "PUT"',
        '"--method", "PATCH"',
        '"--method", "DELETE"',
        "workflow run",
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

    with pytest.raises(CurrentProductionOvhGithubActionsEnvironmentRestNameDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_ENVIRONMENT_REST_NAME_DIAGNOSTIC"
