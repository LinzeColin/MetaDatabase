from __future__ import annotations

from pathlib import Path

import validate_assurance_reviews as assurance_reviews
from pytest import MonkeyPatch
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


def test_rmd06_stage3_pdf_runtime_is_in_its_cumulative_hash_lock() -> None:
    lock = (PROJECT_ROOT / "requirements/stage2.lock").read_text(encoding="utf-8")
    assert "\npikepdf==10.10.0 \\" in lock
    assert "\npillow==12.3.0 \\" in lock

    repository_root = PROJECT_ROOT.parents[1]
    workflow = (repository_root / ".github/workflows/moomooau-stage3-ci.yml").read_text(
        encoding="utf-8"
    )
    container = (PROJECT_ROOT / "container/Dockerfile.stage3-ci").read_text(encoding="utf-8")
    assert "pip install --require-hashes -r requirements/stage2.lock" in workflow
    assert "pip install --no-cache-dir --require-hashes -r requirements/stage2.lock" in container


def test_rmd06_cloud_assurance_uses_the_immutable_predecessor_mode(
    monkeypatch: MonkeyPatch,
) -> None:
    def reject_git_object_lookup(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("immutable predecessor validation must not inspect old Git objects")

    monkeypatch.setattr(
        assurance_reviews,
        "validate_stage6_receipt_anchor",
        reject_git_object_lookup,
    )
    monkeypatch.setattr(
        assurance_reviews,
        "_validate_git_subject",
        reject_git_object_lookup,
    )
    result = assurance_reviews.evaluate_immutable_predecessor(
        PROJECT_ROOT,
        PROJECT_ROOT.parents[1],
    )
    assert result["status"] == "PASS", result["errors"]
    assert result["validation_mode"] == "IMMUTABLE_PACKAGE_PREDECESSOR"
    assert result["git_objects_required"] is False

    workflow = (
        PROJECT_ROOT.parents[1] / ".github/workflows/moomooau-stage6-model-assurance.yml"
    ).read_text(encoding="utf-8")
    assert "python machine/tools/validate_assurance_reviews.py --immutable-predecessor" in workflow


def test_rmd06_immutable_predecessor_mode_rejects_manifest_drift(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    predecessor = root / assurance_reviews.RMD05_PREDECESSOR_MANIFEST_PATH
    predecessor.parent.mkdir(parents=True)
    predecessor.write_bytes(
        (PROJECT_ROOT / assurance_reviews.RMD05_PREDECESSOR_MANIFEST_PATH).read_bytes()
    )
    monkeypatch.setattr(
        assurance_reviews,
        "evaluate_assurance_reviews",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "history_integrity": "PASS",
            "errors": [],
        },
    )

    assert assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)["status"] == "PASS"
    predecessor.write_text("{}\n", encoding="utf-8")
    result = assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["immutable RMD-05 predecessor manifest differs"]


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
