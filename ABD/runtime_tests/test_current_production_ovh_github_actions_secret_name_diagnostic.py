from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from current_production_ovh_github_actions_secret_name_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionOvhGithubActionsSecretNameDiagnosticError,
    build_receipt,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ovh_github_actions_secret_name_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ovh_github_actions_secret_name_diagnostic.sh"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "github_actions_access": "AVAILABLE",
        "secret_name_group_state": "COMPLETE_LEGACY_AUTH_TARGET_SECRET_GROUP",
        "secret_name_group_ready": True,
        "provider_api_requests": 0,
        "secret_value_read_or_emitted": False,
        "github_actions_workflow_created_updated_or_dispatched": False,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def test_contract_preserves_name_only_zero_request_no_workflow_and_no_mutation_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["repository"] == "LinzeColin/MetaDatabase"
    assert expected["github_secret_application"] == "actions"
    assert expected["legacy_auth_target_secret_groups"] == ["OVH_STANDARD", "ABD_OVH_SCOPED"]
    assert expected["maximum_github_query_timeout_seconds"] == 10
    assert boundary["github_secret_values_read_or_emitted"] is False
    assert boundary["github_actions_workflow_created_updated_or_dispatched"] is False
    assert boundary["branch_pr_or_repository_state_changed"] is False
    assert boundary["provider_api_request_sent"] is False


def test_complete_secret_name_group_requires_a_separate_workflow_contract() -> None:
    result = evaluate_diagnostic(_contract(), _facts())

    assert result["status"] == PASS_STATUS
    assert result["github_actions_diagnosed"] is True
    assert result["secret_name_group_ready"] is True
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False
    assert result["github_actions_secret_name_state"] == "OVH_GITHUB_ACTIONS_SECRET_NAME_GROUP_READY_FOR_SEPARATE_WORKFLOW_CONTRACT"


def test_incomplete_secret_name_group_is_a_complete_zero_request_diagnostic() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        secret_name_group_state="NO_COMPLETE_LEGACY_SECRET_GROUP_REDACTED",
        secret_name_group_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["secret_name_group_ready"] is False
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True
    assert result["core_start_authorized"] is False


def test_unavailable_github_actions_fails_closed_without_workflow_or_provider_request() -> None:
    result = evaluate_diagnostic(_contract(), _facts(
        github_actions_access="UNAVAILABLE_REDACTED",
        secret_name_group_state="GITHUB_ACTIONS_UNAVAILABLE_REDACTED",
        secret_name_group_ready=False,
    ))

    assert result["status"] == PASS_STATUS
    assert result["secret_name_group_ready"] is False
    assert result["workflow_not_dispatched"] is True
    assert result["provider_api_request_not_sent"] is True


def test_facts_reject_secret_name_or_value_leakage() -> None:
    facts = _facts()
    facts["secret_name"] = "not retained"

    with pytest.raises(CurrentProductionOvhGithubActionsSecretNameDiagnosticError, match="field set"):
        validate_facts(facts)


def test_facts_reject_any_workflow_dispatch_or_provider_request() -> None:
    facts = _facts(github_actions_workflow_created_updated_or_dispatched=True)

    with pytest.raises(CurrentProductionOvhGithubActionsSecretNameDiagnosticError, match="source boundary"):
        validate_facts(facts)

    facts = _facts(provider_api_requests=1)
    with pytest.raises(CurrentProductionOvhGithubActionsSecretNameDiagnosticError, match="request count"):
        validate_facts(facts)


def test_receipt_redacts_access_and_secret_name_details() -> None:
    receipt = build_receipt(_contract(), _facts())
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert receipt["secret_name_group_ready"] is True
    assert receipt["workflow_not_dispatched"] is True
    assert receipt["provider_api_request_not_sent"] is True
    assert receipt["core_start_authorized"] is False
    assert '"github_actions_access":' not in serialized
    assert '"secret_name_group_state":' not in serialized
    assert '"OVH_APPLICATION_KEY":' not in serialized


def test_contract_cannot_relax_secret_value_or_workflow_boundary() -> None:
    contract = _contract()
    boundary = contract["source_boundary"]
    assert isinstance(boundary, dict)
    boundary["github_actions_workflow_created_updated_or_dispatched"] = True

    with pytest.raises(CurrentProductionOvhGithubActionsSecretNameDiagnosticError, match="source boundary"):
        validate_contract(contract)


def test_runner_has_single_read_only_name_query_and_no_secret_or_workflow_write_capability() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")

    assert 'REPOSITORY = "LinzeColin/MetaDatabase"' in source
    assert '"secret", "list", "--repo", REPOSITORY, "--app", "actions", "--json", "name"' in source
    assert 'TIMEOUT_SECONDS = 10' in source
    assert "print(query.stdout)" not in source
    assert "print(names)" not in source
    assert "print(json.dumps(result" in source
    for forbidden in (
        "secret set",
        "secret remove",
        "secret delete",
        "workflow run",
        "gh api -X POST",
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

    with pytest.raises(CurrentProductionOvhGithubActionsSecretNameDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_OVH_GITHUB_ACTIONS_SECRET_NAME_DIAGNOSTIC"
