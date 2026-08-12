from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import current_production_ci_deployment_route_static_declaration_diagnostic as diagnostic
from current_production_ci_deployment_route_static_declaration_diagnostic import (
    FAIL_STATUS,
    PASS_STATUS,
    CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError,
    build_receipt,
    discover_static_declaration,
    evaluate_diagnostic,
    validate_contract,
    validate_facts,
)


CONTRACT_PATH = RUNTIME / "current_production_ci_deployment_route_static_declaration_diagnostic_contract.json"
RUNNER_PATH = RUNTIME / "run_current_production_ci_deployment_route_static_declaration_diagnostic.sh"
MODULE_PATH = RUNTIME / "current_production_ci_deployment_route_static_declaration_diagnostic.py"


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _facts(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "observation_type": "ABD_REDACTED_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC",
        "observed_on": "2026-08-12",
        "repository_root_state": "AVAILABLE_READ_ONLY",
        "workflow_header_state": "OBSERVED_REDACTED",
        "workflow_trigger_surface_observed": True,
        "workflow_managed_branch_or_ref_trigger_observed": True,
        "workflow_explicit_current_production_route_observed": False,
        "release_recovery_static_surface_state": "OBSERVED_REDACTED",
        "release_recovery_static_surface_observed": True,
        "current_production_ci_deployment_route_state": "NOT_DECLARED_REDACTED",
        "current_production_ci_deployment_route_declared": False,
        "workflow_job_command_content_read_or_persisted": False,
        "workflow_secret_value_read_or_persisted": False,
        "credential_config_or_runtime_secret_read_or_persisted": False,
        "address_port_or_target_mapping_read_or_persisted": False,
        "static_source_path_or_raw_content_emitted_or_persisted": False,
        "github_api_requests": 0,
        "provider_api_requests": 0,
        "ssh_connections_attempted": 0,
        "browser_login_submitted": False,
    }
    values.update(overrides)
    return values


def _write_json(path: Path, payload: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(mode)


def _write_static_surface(root: Path, workflow_name: str = "ABD Current Production Deploy Recovery") -> None:
    workflow = root / ".github/workflows/abd-stage0-validation.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "\n".join(
            [
                f"name: {workflow_name}",
                "on:",
                "  push:",
                "    branches: [main]",
                "  workflow_dispatch:",
                "jobs:",
                "  ignored:",
                "    steps:",
                "      - run: current production deploy recovery must not be inspected",
            ]
        ),
        encoding="utf-8",
    )
    workflow.chmod(0o600)
    _write_json(root / "ABD/release_pipeline.yml", {
        "candidate_slots": {"ignored": "value"},
        "entry_conditions": {},
        "stages": [],
        "rollback_policy": {},
        "external_effect_boundary": {},
    })
    _write_json(root / "ABD/release_slots.json", {
        "production_activation": {},
        "routing": {"public_origin": "must-not-appear.example:9999"},
        "promotion_protocol": {},
        "rollback": {},
        "external_effect_boundary": {},
    })
    _write_json(root / "ABD/recovery_actions.json", {
        "claim_boundary": "static only",
        "actions": [{"target": "must-not-appear.example:9999"}],
    })


def test_contract_preserves_static_only_zero_external_boundary() -> None:
    contract = _contract()

    validate_contract(contract)
    expected = contract["expected"]
    boundary = contract["source_boundary"]
    assert isinstance(expected, dict)
    assert isinstance(boundary, dict)
    assert expected["workflow_relative_path"] == ".github/workflows/abd-stage0-validation.yml"
    assert expected["maximum_workflow_header_lines"] == 96
    assert expected["github_api_requests"] == 0
    assert expected["provider_api_requests"] == 0
    assert boundary["workflow_header_and_branch_ref_triggers_only"] is True
    assert boundary["workflow_job_command_content_read_or_persisted"] is False
    assert boundary["address_port_or_target_mapping_read_or_persisted"] is False


def test_explicit_static_declaration_remains_non_authorizing(tmp_path: Path) -> None:
    _write_static_surface(tmp_path)

    facts = discover_static_declaration(tmp_path, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["workflow_header_state"] == "OBSERVED_REDACTED"
    assert facts["release_recovery_static_surface_state"] == "OBSERVED_REDACTED"
    assert facts["current_production_ci_deployment_route_state"] == "DECLARED_REDACTED"
    assert result["status"] == PASS_STATUS
    assert result["current_production_ci_deployment_route_declared"] is True
    assert result["outbound_operations_not_attempted"] is True
    assert result["core_start_authorized"] is False


def test_actual_worktree_classifies_missing_explicit_ci_binding_as_not_declared() -> None:
    facts = discover_static_declaration(ROOT.parent, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["repository_root_state"] == "AVAILABLE_READ_ONLY"
    assert facts["workflow_header_state"] == "OBSERVED_REDACTED"
    assert facts["release_recovery_static_surface_state"] == "OBSERVED_REDACTED"
    assert facts["current_production_ci_deployment_route_state"] == "NOT_DECLARED_REDACTED"
    assert result["status"] == PASS_STATUS
    assert result["current_production_ci_deployment_route_declared"] is False
    assert result["core_start_authorized"] is False


def test_job_command_text_cannot_be_used_as_route_declaration(tmp_path: Path) -> None:
    _write_static_surface(tmp_path, workflow_name="ABD continuous validation")

    facts = discover_static_declaration(tmp_path, observed_on="2026-08-12")

    assert facts["workflow_trigger_surface_observed"] is True
    assert facts["workflow_explicit_current_production_route_observed"] is False
    assert facts["current_production_ci_deployment_route_declared"] is False
    assert facts["workflow_job_command_content_read_or_persisted"] is False


def test_receipt_omits_static_paths_command_and_target_values(tmp_path: Path) -> None:
    _write_static_surface(tmp_path)
    receipt = build_receipt(_contract(), discover_static_declaration(tmp_path, observed_on="2026-08-12"))
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == PASS_STATUS
    assert "must-not-appear.example:9999" not in serialized
    assert "current production deploy recovery must not be inspected" not in serialized
    assert ".github/workflows/abd-stage0-validation.yml" not in serialized


def test_missing_workflow_fails_closed_without_remote_authorization(tmp_path: Path) -> None:
    _write_static_surface(tmp_path)
    (tmp_path / ".github/workflows/abd-stage0-validation.yml").unlink()

    facts = discover_static_declaration(tmp_path, observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["workflow_header_state"] == "UNAVAILABLE_REDACTED"
    assert facts["current_production_ci_deployment_route_state"] == "UNAVAILABLE_REDACTED"
    assert result["current_production_ci_deployment_route_declared"] is False
    assert result["core_start_authorized"] is False


def test_unsafe_static_file_fails_closed(tmp_path: Path) -> None:
    _write_static_surface(tmp_path)
    unsafe = tmp_path / "ABD/release_slots.json"
    unsafe.chmod(0o666)
    assert unsafe.stat().st_mode & stat.S_IWOTH

    facts = discover_static_declaration(tmp_path, observed_on="2026-08-12")

    assert facts["release_recovery_static_surface_state"] == "UNSAFE_REJECTED_REDACTED"
    assert facts["current_production_ci_deployment_route_declared"] is False


def test_malformed_static_schema_fails_closed(tmp_path: Path) -> None:
    _write_static_surface(tmp_path)
    _write_json(tmp_path / "ABD/recovery_actions.json", {"actions": []})

    facts = discover_static_declaration(tmp_path, observed_on="2026-08-12")

    assert facts["release_recovery_static_surface_state"] == "SCHEMA_INCOMPLETE_REDACTED"
    assert facts["current_production_ci_deployment_route_state"] == "UNAVAILABLE_REDACTED"


def test_unavailable_root_fails_closed() -> None:
    facts = discover_static_declaration(Path("/definitely-not-present"), observed_on="2026-08-12")
    result = evaluate_diagnostic(_contract(), facts)

    assert facts["repository_root_state"] == "UNAVAILABLE_REDACTED"
    assert result["current_production_ci_deployment_route_declared"] is False
    assert result["core_start_authorized"] is False


def test_facts_reject_remote_counts_and_inconsistent_declaration() -> None:
    with pytest.raises(CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError, match="outbound operation count"):
        validate_facts(_facts(github_api_requests=1))

    with pytest.raises(CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError, match="declared route evidence"):
        validate_facts(_facts(
            workflow_explicit_current_production_route_observed=False,
            current_production_ci_deployment_route_state="DECLARED_REDACTED",
            current_production_ci_deployment_route_declared=True,
        ))


def test_contract_cannot_relax_static_only_boundary() -> None:
    contract = _contract()
    expected = contract["expected"]
    assert isinstance(expected, dict)
    expected["github_api_requests"] = 1

    with pytest.raises(CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError, match="diagnostic expectations"):
        validate_contract(contract)


def test_runner_and_module_have_no_network_or_command_execution_capability() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    module = MODULE_PATH.read_text(encoding="utf-8")

    assert "--repo-root" in runner
    assert "current_production_ci_deployment_route_static_declaration_diagnostic.py" in runner
    for forbidden in (
        "socket.",
        "urllib.request",
        "import requests",
        "requests.",
        "urlopen",
        "subprocess",
        "ssh ",
        "curl ",
        "wget ",
        "gh ",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "docker compose",
        "docker run",
        "cloudflared",
    ):
        assert forbidden not in runner
        assert forbidden not in module


def test_invalid_contract_is_not_accepted() -> None:
    bad_contract = _contract()
    bad_contract["status"] = "MUTATING"

    with pytest.raises(CurrentProductionCiDeploymentRouteStaticDeclarationDiagnosticError):
        evaluate_diagnostic(bad_contract, _facts())

    assert FAIL_STATUS == "FAIL_CURRENT_PRODUCTION_CI_DEPLOYMENT_ROUTE_STATIC_DECLARATION_DIAGNOSTIC"
