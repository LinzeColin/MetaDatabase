from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import build_delivery_status as delivery_status
import pytest
import validate_assurance_reviews as assurance_reviews
import validate_package as package_validation
import validate_production_composition as composition_validation
from pytest import MonkeyPatch
from validate_evidence import PROJECT_ROOT
from validate_workflow_matrix import (
    GOVERNANCE_DEPLOY_KEY_EXPRESSION,
    validate_governance_dependency_auth,
    validate_repository_workflow_contexts,
    validate_workflow_expression_contexts,
)

from machine.acceptance import evidence as acceptance_evidence
from machine.stages.S6.tools import validate_stage6 as stage6_validation


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
    assert result["immutable_authority_files"] > 0

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
    monkeypatch.setattr(assurance_reviews, "RMD05_IMMUTABLE_AUTHORITY_PATHS", set())
    monkeypatch.setattr(
        assurance_reviews,
        "RMD05_IMMUTABLE_AUTHORITY_PREFIX",
        Path("no-synthetic-authorities"),
    )

    assert assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)["status"] == "PASS"
    predecessor.write_text("{}\n", encoding="utf-8")
    result = assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["immutable RMD-05 predecessor manifest differs"]


def test_rmd06_immutable_predecessor_mode_rejects_authority_drift(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    authority_relative = Path("evidence/stage6/latest.json")
    authority = root / authority_relative
    authority.parent.mkdir(parents=True)
    authority.write_text('{"status":"PASS"}\n', encoding="utf-8")
    authority_sha256 = assurance_reviews._sha256_bytes(authority.read_bytes())

    manifest_relative = Path("taskpack/predecessor.json")
    manifest = root / manifest_relative
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        (f'{{"files":[{{"path":"evidence/stage6/latest.json","sha256":"{authority_sha256}"}}]}}\n'),
        encoding="utf-8",
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
    monkeypatch.setattr(
        assurance_reviews,
        "RMD05_PREDECESSOR_MANIFEST_PATH",
        manifest_relative,
    )
    monkeypatch.setattr(
        assurance_reviews,
        "RMD05_PREDECESSOR_MANIFEST_SHA256",
        assurance_reviews._sha256_bytes(manifest.read_bytes()),
    )
    monkeypatch.setattr(
        assurance_reviews,
        "RMD05_IMMUTABLE_AUTHORITY_PATHS",
        {authority_relative},
    )
    monkeypatch.setattr(
        assurance_reviews,
        "RMD05_IMMUTABLE_AUTHORITY_PREFIX",
        Path("machine/synthetic-reviews"),
    )

    assert assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)["status"] == "PASS"
    review_root = root / "machine/synthetic-reviews"
    review_root.mkdir(parents=True)
    extra_symlink = review_root / "unexpected.json"
    extra_symlink.symlink_to(authority)
    result = assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["immutable RMD-05 assurance authorities differ"]
    extra_symlink.unlink()

    authority.write_text('{"status":"DRIFT"}\n', encoding="utf-8")
    result = assurance_reviews.evaluate_immutable_predecessor(root, tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["immutable RMD-05 assurance authorities differ"]


def test_rmd06_delivery_status_uses_portable_stage6_binding_validation(
    monkeypatch: MonkeyPatch,
) -> None:
    records = {
        f"T060{index}": delivery_status._load(PROJECT_ROOT / f"evidence/tasks/T060{index}.json")
        for index in range(1, 9)
    }
    repository_root = PROJECT_ROOT.parents[1]
    observed_roots: list[Path | None] = []

    def record_bundle_validation(
        _root: Path,
        candidate_repository_root: Path | None = None,
    ) -> list[str]:
        observed_roots.append(candidate_repository_root)
        return []

    monkeypatch.setattr(
        delivery_status,
        "validate_stage6_candidate_bundle",
        record_bundle_validation,
    )

    delivery_status._validate_stage6_evidence_transition(
        PROJECT_ROOT,
        {"package_version": "1.0.6"},
        records,
        repository_root=repository_root,
    )
    delivery_status._validate_stage6_evidence_transition(
        PROJECT_ROOT,
        {"package_version": "1.0.5"},
        records,
        repository_root=repository_root,
    )
    assert observed_roots == [None, repository_root]


def test_rmd06_delivery_status_uses_static_composition_only_for_v106(
    monkeypatch: MonkeyPatch,
) -> None:
    observed: list[bool] = []

    def record_validation(
        _root: Path,
        *,
        verify_contract_cli: bool = True,
    ) -> dict[str, object]:
        observed.append(verify_contract_cli)
        return {"status": "PASS"}

    monkeypatch.setattr(delivery_status, "validate_composition", record_validation)
    assert delivery_status._validate_composition_for_state(
        PROJECT_ROOT,
        {"package_version": "1.0.6"},
    ) == {"status": "PASS"}
    assert delivery_status._validate_composition_for_state(
        PROJECT_ROOT,
        {"package_version": "1.0.5"},
    ) == {"status": "PASS"}
    assert observed == [False, True]


def test_rmd06_static_composition_validation_does_not_import_later_runtime(
    monkeypatch: MonkeyPatch,
) -> None:
    def reject_subprocess(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("static composition validation must not import the runtime")

    monkeypatch.setattr(composition_validation.subprocess, "run", reject_subprocess)
    assert (
        composition_validation.validate(
            PROJECT_ROOT,
            verify_contract_cli=False,
        )["status"]
        == "PASS"
    )


def test_rmd06_stage6_closure_uses_portable_candidate_bundle(
    monkeypatch: MonkeyPatch,
) -> None:
    observed_roots: list[Path | None] = []

    def record_bundle_validation(
        _root: Path,
        candidate_repository_root: Path | None = None,
    ) -> list[str]:
        observed_roots.append(candidate_repository_root)
        return []

    monkeypatch.setattr(
        stage6_validation,
        "validate_stage6_candidate_bundle",
        record_bundle_validation,
    )
    assert stage6_validation._validate_evidence(PROJECT_ROOT) == []
    assert observed_roots == [None]


def test_rmd06_stage6_workflow_uses_the_structured_secret_scanner() -> None:
    workflow = (PROJECT_ROOT.parents[1] / ".github/workflows/moomooau-stage6-ci.yml").read_text(
        encoding="utf-8"
    )
    assert "python machine/tools/validate_stage6_secret_scan.py" in workflow
    assert "detect-secrets scan --all-files" not in workflow


def test_rmd06_stage7_secret_scan_excludes_exact_public_predecessor_digests() -> None:
    workflow = (PROJECT_ROOT.parents[1] / ".github/workflows/moomooau-stage7-ci.yml").read_text(
        encoding="utf-8"
    )
    for digest in (
        "24b24ce8bd25b85f6c4dce3f7fbf6c8770b24e88be13f52be1d8d6a87b0c6e15",
        "301fa1c6f5c46760c4aa3a7092bf0be77ca1a2e974e7b65e8b53dcf90db9925e",
        "6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3",
        "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f",
    ):
        assert digest in workflow


def test_rmd06_shallow_acceptance_base_requires_the_exact_provenance_pin(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    provenance_path = root / acceptance_evidence.PORTABLE_SOURCE_PROVENANCE
    provenance_path.parent.mkdir(parents=True)
    provenance: dict[str, Any] = {
        "schema_version": acceptance_evidence.PORTABLE_SOURCE_PROVENANCE_SCHEMA,
        "effective_package": {"version": acceptance_evidence.PORTABLE_PACKAGE_VERSION},
        "candidate_snapshot": {
            "repository": "LinzeColin/MetaDatabase",
            "mainline_base_commit": acceptance_evidence.CURRENT_MAINLINE_BASE_COMMIT,
            "acceptance_remediation_base_commit": (
                acceptance_evidence.ACCEPTANCE_REMEDIATION_BASE_COMMIT
            ),
            "shallow_checkout_fallback": "EXACT_PIN_ONLY",
        },
    }
    provenance_path.write_text(
        json.dumps(provenance, indent=2) + "\n",
        encoding="utf-8",
    )

    def reject_missing_ancestor(_root: Path, _value: str, _field: str) -> None:
        raise acceptance_evidence.AcceptanceEvidenceError("missing shallow object")

    monkeypatch.setattr(
        acceptance_evidence,
        "_validate_commit_ancestor",
        reject_missing_ancestor,
    )
    monkeypatch.setattr(acceptance_evidence, "_is_shallow_repository", lambda _root: True)

    acceptance_evidence._validate_remediation_base(
        root,
        acceptance_evidence.ACCEPTANCE_REMEDIATION_BASE_COMMIT,
    )
    with pytest.raises(acceptance_evidence.AcceptanceEvidenceError):
        acceptance_evidence._validate_remediation_base(root, "0" * 40)

    provenance["candidate_snapshot"]["shallow_checkout_fallback"] = "UNPINNED"
    provenance_path.write_text(
        json.dumps(provenance, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(acceptance_evidence.AcceptanceEvidenceError):
        acceptance_evidence._validate_remediation_base(
            root,
            acceptance_evidence.ACCEPTANCE_REMEDIATION_BASE_COMMIT,
        )


def test_rmd06_package_and_acceptance_use_current_provenance_pins() -> None:
    assert package_validation.CANDIDATE_SNAPSHOT == {
        "repository": "LinzeColin/MetaDatabase",
        "mainline_base_commit": acceptance_evidence.CURRENT_MAINLINE_BASE_COMMIT,
        "acceptance_remediation_base_commit": (
            acceptance_evidence.ACCEPTANCE_REMEDIATION_BASE_COMMIT
        ),
        "shallow_checkout_fallback": "EXACT_PIN_ONLY",
    }
    assert (
        package_validation.build_provenance()["candidate_snapshot"]
        == package_validation.CANDIDATE_SNAPSHOT
    )


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
