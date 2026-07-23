from __future__ import annotations

from validate_evidence import PROJECT_ROOT
from validate_workflow_matrix import (
    GOVERNANCE_DEPLOY_KEY_EXPRESSION,
    validate_governance_dependency_auth,
    validate_repository_workflow_contexts,
    validate_workflow_expression_contexts,
)


def test_rmd06_rejects_runner_context_before_a_job_has_a_runner() -> None:
    workflow = {
        "jobs": {
            "invalid": {
                "runs-on": "ubuntu-24.04",
                "env": {
                    "CACHE": "${{ runner.temp }}/cache",
                    "DIGEST": "${{ hashFiles('requirements.lock') }}",
                },
                "steps": [{"run": "true"}],
            }
        }
    }

    assert validate_workflow_expression_contexts(workflow, label="fixture.yml") == [
        "fixture.yml.jobs.invalid.env.CACHE uses unavailable contexts: runner",
        "fixture.yml.jobs.invalid.env.DIGEST uses unavailable function: hashFiles",
    ]


def test_rmd06_allows_runner_context_after_step_dispatch() -> None:
    workflow = {
        "env": {"OWNER": "${{ github.repository_owner }}"},
        "jobs": {
            "valid": {
                "runs-on": "ubuntu-24.04",
                "env": {"REF": "${{ github.ref }}"},
                "steps": [
                    {
                        "env": {"CACHE": "${{ runner.temp }}/cache"},
                        "run": "true",
                    }
                ],
            }
        },
    }

    assert validate_workflow_expression_contexts(workflow, label="fixture.yml") == []


def test_rmd06_current_moomooau_workflows_use_available_contexts() -> None:
    repository_root = PROJECT_ROOT.parents[1]
    assert validate_repository_workflow_contexts(repository_root) == []


def test_rmd06_governance_deploy_key_is_checkout_only() -> None:
    workflow = {
        "on": {"pull_request": {}},
        "jobs": {
            "valid": {
                "runs-on": "ubuntu-24.04",
                "steps": [
                    {
                        "name": ("Reject fork pull requests before protected dependency checkout"),
                        "if": (
                            "github.event_name == 'pull_request' && "
                            "github.event.pull_request.head.repo.full_name "
                            "!= github.repository"
                        ),
                        "shell": "bash",
                        "run": (
                            'echo "::error::Fork pull requests cannot access '
                            "the protected read-only Governance dependency."
                            '"\nexit 1'
                        ),
                    },
                    {
                        "uses": ("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"),
                        "with": {
                            "repository": "LinzeColin/Governance",
                            "ref": ("ebc6c2e4884edc959118cfc56d0e18a86c49460f"),
                            "path": ".governance",
                            "persist-credentials": "false",
                            "ssh-key": GOVERNANCE_DEPLOY_KEY_EXPRESSION,
                        },
                    },
                ],
            }
        },
    }

    assert (
        validate_governance_dependency_auth(
            workflow,
            label="fixture.yml",
            required=True,
        )
        == []
    )

    workflow["jobs"]["valid"]["steps"].append(  # type: ignore[index]
        {"run": f"printf '%s' '{GOVERNANCE_DEPLOY_KEY_EXPRESSION}'"}
    )
    errors = validate_governance_dependency_auth(
        workflow,
        label="fixture.yml",
        required=True,
    )
    assert any("secret references must be checkout-only" in error for error in errors)


def test_rmd06_fork_rejection_and_pull_request_target_fail_closed() -> None:
    workflow = {
        "on": {"pull_request_target": {}},
        "jobs": {
            "invalid": {
                "runs-on": "ubuntu-24.04",
                "steps": [
                    {
                        "uses": ("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5"),
                        "with": {
                            "repository": "LinzeColin/Governance",
                            "ref": ("ebc6c2e4884edc959118cfc56d0e18a86c49460f"),
                            "path": ".governance",
                            "persist-credentials": "false",
                            "ssh-key": GOVERNANCE_DEPLOY_KEY_EXPRESSION,
                        },
                    }
                ],
            }
        },
    }

    errors = validate_governance_dependency_auth(
        workflow,
        label="fixture.yml",
        required=True,
    )
    assert "fixture.yml must not use pull_request_target" in errors
    assert "fixture.yml must retain the pull_request trigger" in errors
    assert any("fork rejection is not the first step" in error for error in errors)
