from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import shutil

import pytest

from abd_acceptance.economics_sensitivity import (
    EconomicsSensitivityAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from economics import EconomicsError, artifact_sha256, build_reports


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S12_P03.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
COSTS = json.loads((ROOT / "machine/facts/costs.json").read_text(encoding="utf-8"))
CAPACITY = json.loads((ROOT / "capacity_report.json").read_text(encoding="utf-8"))
P01_PATH = ROOT / "machine/evidence/EVD-S12-P01.json"
P02_PATH = ROOT / "machine/evidence/EVD-S12-P02.json"
P01 = json.loads(P01_PATH.read_text(encoding="utf-8"))
P02 = json.loads(P02_PATH.read_text(encoding="utf-8"))
P01_SHA256 = hashlib.sha256(P01_PATH.read_bytes()).hexdigest()
P02_SHA256 = hashlib.sha256(P02_PATH.read_bytes()).hexdigest()
CAPACITY_SHA256 = hashlib.sha256((ROOT / "capacity_report.json").read_bytes()).hexdigest()


def _reports(
    fixture: dict | None = None,
    capacity: dict | None = None,
    p01: dict | None = None,
    p02: dict | None = None,
    *,
    require_expected_hash: bool = True,
) -> tuple[dict, dict]:
    return build_reports(
        FIXTURE if fixture is None else fixture,
        PARAMETERS,
        COSTS,
        CAPACITY if capacity is None else capacity,
        P01 if p01 is None else p01,
        P02 if p02 is None else p02,
        P01_SHA256,
        P02_SHA256,
        CAPACITY_SHA256,
        require_expected_hash=require_expected_hash,
    )


def test_frozen_economics_outputs_are_exact_replays() -> None:
    grid, opportunity_cost = _reports()
    assert grid["sensitivity_grid_sha256"] == FIXTURE["expected_sensitivity_grid_sha256"]
    assert opportunity_cost["opportunity_cost_sha256"] == FIXTURE["expected_opportunity_cost_sha256"]
    assert json.loads((ROOT / "sensitivity_grid.json").read_text(encoding="utf-8")) == grid
    assert json.loads((ROOT / "opportunity_cost.json").read_text(encoding="utf-8")) == opportunity_cost


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S12-P03"
    assert result["next"] == "S12/P04_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 20
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_return_bands_contain_interval_confidence_and_failure_probability() -> None:
    grid, _ = _reports()
    assert grid["summary"] == {
        "available_capacity_cents_from_signed_p02": 4000,
        "independent_equivalent_signals_from_signed_p02": 5,
        "target_increment_cents": 9000,
        "highest_upper_band_cents": 800,
        "lowest_upper_band_target_shortfall_cents": 8200,
        "all_scenarios_leave_target_unverified": True,
        "return_bands_are_synthetic_sensitivity_not_revenue": True,
    }
    assert [(row["scenario_id"], row["return_band_cents"], row["confidence"], row["failure_probability"]) for row in grid["return_bands"]] == [
        ("S12-P03-BASELINE-SYNTHETIC", {"low": -400, "central": 100, "high": 800}, "0.2000", "0.8000"),
        ("S12-P03-ADVERSE-ONE-IN-TEN-THOUSAND", {"low": -401, "central": 99, "high": 799}, "0.1999", "0.8001"),
        ("S12-P03-NO-EXECUTION-SYNTHETIC", {"low": 0, "central": 0, "high": 0}, "0.0000", "1.0000"),
    ]


def test_no_return_band_can_become_a_target_or_order_claim() -> None:
    grid, opportunity_cost = _reports()
    assert all(row["target_covered"] is False for row in grid["return_bands"])
    assert all(row["action"] == "SYNTHETIC_SENSITIVITY_NOT_ACTIONABLE" for row in grid["return_bands"])
    assert grid["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert grid["external_effect_boundary"]["order_submission_enabled"] is False
    assert grid["external_effect_boundary"]["financial_return_verified_or_guaranteed"] is False
    assert opportunity_cost["return_cost_boundary"]["roi_reported"] is False
    assert opportunity_cost["return_cost_boundary"]["return_bands_are_not_realized_revenue"] is True


def test_zero_new_cash_does_not_hide_existing_or_opportunity_cost() -> None:
    _, opportunity_cost = _reports()
    assert opportunity_cost["operating_cost"] == {
        "incremental_cash_budget_cents": 0,
        "incremental_cash_spent_cents": 0,
        "incremental_cash_status": "ZERO_NEW_CASH_ONLY_NOT_TOTAL_SYSTEM_COST",
        "existing_recurring_cost_status": "UNKNOWN_ACCOUNT_SPECIFIC_NO_BILLING_ACCESS",
        "existing_resources_are_not_relabelled_zero": True,
        "bankroll_principal_cents": 30000,
    }
    assert opportunity_cost["opportunity_cost_bands"][0] == {
        "illustrative_hourly_value_aud": "30.00",
        "low_aud": "7200.00",
        "likely_aud": "9600.00",
        "high_aud": "14400.00",
        "classification": "SENSITIVITY_ONLY_NOT_OWNER_TIME_VALUATION",
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture["return_band_scenarios"][1].update({"scenario_id": "S12-P03-BASELINE-SYNTHETIC"}),
        lambda fixture: fixture["return_band_scenarios"][0].update({"return_rate_high": "0.3000"}),
        lambda fixture: fixture["return_band_scenarios"][0].update({"failure_probability": "1.0001"}),
        lambda fixture: fixture.update({"incremental_cash_budget_cents": 1}),
        lambda fixture: fixture["return_band_scenarios"][0].update({"evidence_status": "UNVERIFIED"}),
        lambda fixture: fixture.update({"p02_evidence_sha256": "f" * 64}),
    ],
)
def test_malformed_or_unsafe_inputs_fail_closed(mutate) -> None:
    fixture = deepcopy(FIXTURE)
    mutate(fixture)
    with pytest.raises(EconomicsError):
        _reports(fixture, require_expected_hash=False)


@pytest.mark.parametrize("target", ["p01", "p02", "capacity"])
def test_signed_predecessor_or_capacity_tampering_fails_closed(target: str) -> None:
    if target == "p01":
        p01 = deepcopy(P01)
        p01["decision"] = "TARGET_GUARANTEED"
        with pytest.raises(EconomicsError):
            _reports(p01=p01, require_expected_hash=False)
    elif target == "p02":
        p02 = deepcopy(P02)
        p02["next"] = "S12/P04_READY_NOT_STARTED"
        with pytest.raises(EconomicsError):
            _reports(p02=p02, require_expected_hash=False)
    else:
        capacity = deepcopy(CAPACITY)
        capacity["summary"]["final_platform_and_executable_capacity_cents"] = 9000
        with pytest.raises(EconomicsError):
            _reports(capacity=capacity, require_expected_hash=False)


@pytest.mark.parametrize("delta", [Decimal("-0.0001"), Decimal("0.0001")])
def test_one_in_ten_thousand_return_rate_perturbation_stays_unverified(delta: Decimal) -> None:
    fixture = deepcopy(FIXTURE)
    scenario = fixture["return_band_scenarios"][0]
    scenario["return_rate_high"] = format(Decimal(scenario["return_rate_high"]) + delta, "f")
    grid, _ = _reports(fixture, require_expected_hash=False)
    assert grid["summary"]["highest_upper_band_cents"] < grid["summary"]["target_increment_cents"]
    assert all(row["target_covered"] is False for row in grid["return_bands"])
    assert grid["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"


def test_core_source_has_no_network_soak_order_or_binary_float_capability() -> None:
    source = (ROOT / "economics.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"})
    for forbidden in ("sleep(", "submit_order", "retry_order", "float("):
        assert forbidden not in source


def test_candidate_fails_closed_when_generated_grid_is_tampered(tmp_path: Path) -> None:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    grid_path = clone / "sensitivity_grid.json"
    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    grid["summary"]["highest_upper_band_cents"] = 9000
    grid_path.write_text(json.dumps(grid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S12P03-FROZEN-ECONOMICS-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_rollback_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "economics:sensitivity_disclosure"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_acceptance_cli_is_wired_to_the_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S12-P03": write_economics_sensitivity_phase_evidence' in source
    assert '"AC-S12-P03": verify_economics_sensitivity_phase_evidence' in source
    with pytest.raises((EconomicsSensitivityAcceptanceError, FileNotFoundError)):
        from abd_acceptance.economics_sensitivity import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")


def test_artifact_hashes_remain_content_addressed() -> None:
    grid, opportunity_cost = _reports()
    grid_without_hash = deepcopy(grid)
    cost_without_hash = deepcopy(opportunity_cost)
    assert grid_without_hash.pop("sensitivity_grid_sha256") == artifact_sha256(grid_without_hash)
    assert cost_without_hash.pop("opportunity_cost_sha256") == artifact_sha256(cost_without_hash)
