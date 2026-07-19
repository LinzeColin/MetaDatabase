from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.budget import (
    COSTS_PATH,
    LOCK_PATH,
    SCAN_REPORT_PATH,
    build_evidence,
    evaluate_contract,
    perform_rollback_drill,
    render_scan_report,
    scan_dependency_budget,
    write_scan_report,
)
from abd_acceptance.canonical_facts import strict_json_load


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / "machine/tests/fixtures/S00_P03.json")


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _resource(costs, resource_id: str):
    return next(item for item in costs["resource_costs"] if item["id"] == resource_id)


def _provider(lock, resource_id: str):
    return next(item for item in lock["providers"] if item["resource_id"] == resource_id)


def _package(lock, package_name: str):
    return next(item for item in lock["python_environment"]["registry_packages"] if item["name"] == package_name)


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_zero_budget_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["next"] == "S00/P04_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 40


@pytest.mark.parametrize("case", FIXTURE["cash_boundary_cases"], ids=lambda case: case["id"])
def test_incremental_cash_resource_boundary_fails_closed(tmp_path: Path, case) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    _resource(costs, "RES-OVH-EXISTING-VPS1")["incremental_cash_cost_aud"] = case["value"]
    _write_json(path, costs)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == case["expected_status"]
    assert "COST-RESOURCES-ZERO-AND-FAIL-CLOSED" in result["summary"]["failed_check_ids"]


def test_incremental_budget_high_cannot_exceed_zero(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["incremental_cash_budget"]["high"] = "0.0001"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-INCREMENTAL-CASH-EXACT-ZERO")


def test_total_system_cost_cannot_be_claimed_zero(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["cost_semantics"]["total_system_cost_is_zero"] = True
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-SEMANTICS-NO-ZERO-TOTAL-CLAIM")


def test_existing_ovh_cost_unknown_is_not_incremental_cost_unknown() -> None:
    costs = strict_json_load(ROOT / COSTS_PATH)
    ovh = _resource(costs, "RES-OVH-EXISTING-VPS1")
    assert ovh["existing_recurring_cash_cost_aud"] == "UNKNOWN_ACCOUNT_SPECIFIC"
    assert ovh["incremental_cash_cost_aud"] == "0.00"
    assert ovh["purchase_required"] is False
    assert ovh["public_reference_is_account_invoice"] is False


def test_external_capability_cannot_be_claimed_verified(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    _resource(costs, "RES-CLOUDFLARE-ZERO-TRUST-FREE")["capability_status"] = "VERIFIED_AVAILABLE"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-RESOURCES-ZERO-AND-FAIL-CLOSED")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("purchase_required", True),
        ("paid_tier_allowed", True),
        ("automatic_overage_allowed", True),
    ],
)
def test_resource_purchase_upgrade_and_overage_are_forbidden(tmp_path: Path, field: str, value) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    _resource(costs, "RES-GITHUB-EXISTING")[field] = value
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-RESOURCES-ZERO-AND-FAIL-CLOSED")


def test_optional_gmail_cannot_enter_critical_path(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    _resource(costs, "RES-GMAIL-EXISTING-OPTIONAL")["critical_path"] = True
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-CRITICAL-PATH-AND-EXISTING-COST-DISCLOSED")


def test_optional_gmail_failure_must_continue_core(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    _resource(costs, "RES-GMAIL-EXISTING-OPTIONAL")["on_unavailable_or_limit"] = "PAUSE_ALL"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-RESOURCES-ZERO-AND-FAIL-CLOSED")


def test_future_paid_market_source_cannot_be_auto_admitted(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["future_source_admission_policy"]["paid_source_action"] = "AUTO_PURCHASE"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-FUTURE-SOURCE-ADMISSION")


def test_non_first_party_cost_source_fails(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["official_cost_sources"][0]["url"] = "https://example.invalid/ovh-price"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-FIRST-PARTY-SOURCES-AND-FRESHNESS")


def test_stale_source_policy_cannot_auto_continue(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["freshness_policy"]["on_stale_or_changed"] = "IGNORE_AND_CONTINUE"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-FIRST-PARTY-SOURCES-AND-FRESHNESS")


def test_opportunity_cost_arithmetic_is_verified(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["opportunity_cost_sensitivity"][0]["likely"] += 1
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-OPPORTUNITY-COST-DISCLOSED")


def test_return_target_cannot_become_a_guarantee(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["benefit_model"]["return_guaranteed"] = True
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "COST-RETURN-NOT-GUARANTEED")


def test_lock_cannot_allow_paid_dependencies(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / LOCK_PATH
    lock = strict_json_load(path)
    lock["budget_policy"]["paid_dependency_allowed"] = True
    _write_json(path, lock)
    _failed(evaluate_contract(project, False), "LOCK-BUDGET-POLICY")


def test_provider_lock_nonzero_cost_fails_scan(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / LOCK_PATH
    lock = strict_json_load(path)
    _provider(lock, "RES-CLOUDFLARE-ZERO-TRUST-FREE")["incremental_cash_cost_aud"] = "0.0001"
    _write_json(path, lock)
    result = evaluate_contract(project, False)
    _failed(result, "SCAN-PROVIDER-COSTS-EXACT-ZERO")


def test_approval_bound_interface_cannot_enter_critical_path(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / LOCK_PATH
    lock = strict_json_load(path)
    lock["critical_path"][0]["paid_or_approval_bound_dependency"] = True
    _write_json(path, lock)
    result = evaluate_contract(project, False)
    _failed(result, "LOCK-CRITICAL-PATH-NO-PAID-INTERFACE")
    assert "SCAN-CRITICAL-PATH-NO-PAID-OR-APPROVAL-BOUND-INTERFACE" in result["summary"]["failed_check_ids"]


def test_unclassified_package_added_to_allowlist_still_fails_uv_parity(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / LOCK_PATH
    lock = strict_json_load(path)
    case = FIXTURE["paid_or_unclassified_package_cases"][0]
    lock["python_environment"]["registry_packages"].append(
        {
            "name": case["name"],
            "version": case["version"],
            "scope": "DEV_TRANSITIVE",
            "license_spdx": "MIT",
            "source": "https://pypi.org/project/unknown-package/1.0.0/",
        }
    )
    _write_json(path, lock)
    _failed(evaluate_contract(project, False), "SCAN-LOCKED-PACKAGE-ALLOWLIST")


def test_missing_locked_package_fails_uv_parity(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / LOCK_PATH
    lock = strict_json_load(path)
    lock["python_environment"]["registry_packages"] = [
        item for item in lock["python_environment"]["registry_packages"] if item["name"] != "attrs"
    ]
    _write_json(path, lock)
    _failed(evaluate_contract(project, False), "SCAN-LOCKED-PACKAGE-ALLOWLIST")


def test_unknown_package_license_fails(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / LOCK_PATH
    lock = strict_json_load(path)
    _package(lock, "attrs")["license_spdx"] = "UNKNOWN"
    _write_json(path, lock)
    result = evaluate_contract(project, False)
    _failed(result, "LOCK-OPEN-SOURCE-PACKAGE-ALLOWLIST")
    assert "SCAN-LICENSES-CLASSIFIED" in result["summary"]["failed_check_ids"]


def test_unknown_import_in_executable_surface_fails(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "abd_acceptance/injected.py").write_text("import unknown_paid_sdk\n", encoding="utf-8")
    _failed(evaluate_contract(project, False), "SCAN-IMPORTS-CLASSIFIED")


def test_prohibited_paid_service_literal_in_executable_surface_fails(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "abd_acceptance/injected.py").write_text(
        'ENDPOINT = "https://api.openai.com/v1"\n',
        encoding="utf-8",
    )
    _failed(evaluate_contract(project, False), "SCAN-NO-PROHIBITED-RUNTIME-IDENTIFIERS")


def test_unexpected_dependency_manifest_fails(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "package.json").write_text('{"dependencies": {}}\n', encoding="utf-8")
    _failed(evaluate_contract(project, False), "SCAN-MANIFEST-SET")


def test_undeclared_runtime_dependency_fails(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("dependencies = []", 'dependencies = ["unknown-runtime==1.0.0"]', 1), encoding="utf-8")
    _failed(evaluate_contract(project, False), "SCAN-DIRECT-DEPENDENCIES")


def test_duplicate_json_key_in_costs_fails_strict_parse(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('"schema_version": "1.1.0",', '"schema_version": "1.1.0",\n  "schema_version": "1.1.0",', 1),
        encoding="utf-8",
    )
    _failed(evaluate_contract(project, False), "INPUT-COSTS-PARSE")


def test_p02_prerequisite_must_remain_pass(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/EVD-S00-P02.json"
    evidence = strict_json_load(path)
    evidence["status"] = "FAIL"
    _write_json(path, evidence)
    _failed(evaluate_contract(project, False), "PREREQ-P02-PASS")


def test_malformed_evidence_index_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/evidence/evidence_index.jsonl").write_text("{\n", encoding="utf-8")
    _failed(evaluate_contract(project, False), "PREREQ-P02-PASS")


def test_second_costs_source_fails_single_source_rule(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    shadow = project / "shadow/costs.json"
    shadow.parent.mkdir(parents=True)
    shutil.copyfile(str(project / COSTS_PATH), str(shadow))
    _failed(evaluate_contract(project, False), "SOURCE-SINGLE-COSTS")


def test_local_user_path_cannot_enter_budget_evidence(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / COSTS_PATH
    costs = strict_json_load(path)
    costs["explicit_unknowns"].append("/" + "Users/example/private/account.json")
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "SECURITY-NO-SECRET-OR-LOCAL-PATH")


def test_scan_replay_is_deterministic() -> None:
    first = scan_dependency_budget(ROOT)
    second = scan_dependency_budget(ROOT)
    assert first == second
    assert first["status"] == "PASS"


def test_scan_report_is_exact_deterministic_render() -> None:
    scan = scan_dependency_budget(ROOT)
    assert (ROOT / SCAN_REPORT_PATH).read_text(encoding="utf-8") == render_scan_report(scan)


def test_scan_output_cannot_escape_project(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside the ABD project root"):
        write_scan_report(ROOT, tmp_path / "outside.txt")


def test_evidence_replay_is_deterministic_without_runtime_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback


def test_rollback_drill_restores_all_three_budget_artifacts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert len(result["artifacts"]) == 3
    for artifact in result["artifacts"].values():
        assert artifact["status"] == "PASS"
        assert artifact["signed_sha256"] == artifact["restored_sha256"]
        assert artifact["corrupted_sha256"] != artifact["restored_sha256"]
    assert result["production_state_changed"] is False


def test_cost_and_lock_objects_are_not_mutated_by_evaluation() -> None:
    costs_before = deepcopy(strict_json_load(ROOT / COSTS_PATH))
    lock_before = deepcopy(strict_json_load(ROOT / LOCK_PATH))
    evaluate_contract(ROOT, require_external_reports=False)
    assert strict_json_load(ROOT / COSTS_PATH) == costs_before
    assert strict_json_load(ROOT / LOCK_PATH) == lock_before
