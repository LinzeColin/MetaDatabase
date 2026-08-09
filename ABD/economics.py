"""Frozen economics sensitivity replay for ABD S12/P03.

The module deliberately operates only on the signed S12/P01--P02 synthetic
artifacts and the frozen Task Pack fixture.  Its return bands are scenario
disclosures, never a market forecast, an order, or a return guarantee.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
SYNTHETIC_EVIDENCE_STATUS = "SYNTHETIC_VERIFIED_FOR_TEST_ONLY"
P01_CONTRACT_ID = "AC-S12-P01"
P01_DECISION = "TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"
P02_CONTRACT_ID = "AC-S12-P02"
P02_DECISION = "CAPACITY_CORRELATION_READY_DOWNSTREAM_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_provider_capacity_observed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class EconomicsError(ValueError):
    """Raised when frozen sensitivity facts could overstate economic evidence."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _no_binary_number(value: Any) -> bool:
    if type(value) is float:
        return False
    if isinstance(value, Mapping):
        return all(_no_binary_number(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(_no_binary_number(item) for item in value)
    return True


def _strict_object(value: Any, required: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not required.issubset(value) or not _no_binary_number(value):
        raise EconomicsError("%s is malformed" % label)
    return value


def require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EconomicsError("%s must be a non-empty string" % label)
    return value


def require_int(value: Any, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomicsError("%s must be an integer" % label)
    if minimum is not None and value < minimum:
        raise EconomicsError("%s is below its minimum" % label)
    return value


def require_decimal(value: Any, *, label: str, minimum: Decimal | None = None, maximum: Decimal | None = None) -> Decimal:
    if not isinstance(value, str):
        raise EconomicsError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise EconomicsError("%s is not a decimal" % label) from exc
    if not parsed.is_finite():
        raise EconomicsError("%s must be finite" % label)
    if minimum is not None and parsed < minimum:
        raise EconomicsError("%s is below its minimum" % label)
    if maximum is not None and parsed > maximum:
        raise EconomicsError("%s is above its maximum" % label)
    return parsed


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def floor_cents(value: Decimal, *, label: str) -> int:
    if not value.is_finite():
        raise EconomicsError("%s must be finite" % label)
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def cents_to_aud(cents: int) -> str:
    return decimal_text(Decimal(cents) / Decimal("100"))


def _validate_evidence(
    value: Any,
    expected_sha256: str,
    actual_sha256: str,
    *,
    contract_id: str,
    decision: str,
    next_state: str,
) -> Mapping[str, Any]:
    evidence = _strict_object(
        value,
        {"contract_id", "status", "decision", "next", "financial_target_status", "external_effect_boundary", "release_status"},
        label="signed_predecessor_evidence",
    )
    boundary = evidence.get("external_effect_boundary")
    if (
        evidence.get("contract_id") != contract_id
        or evidence.get("status") != "PASS"
        or evidence.get("decision") != decision
        or evidence.get("next") != next_state
        or evidence.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or evidence.get("release_status") != "%s_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD" % contract_id.replace("AC-", "").replace("-", "_")
        or not isinstance(boundary, Mapping)
        or boundary.get("order_submission_enabled") is not False
        or expected_sha256 != actual_sha256
    ):
        raise EconomicsError("predecessor evidence is not the exact signed synthetic prerequisite")
    return evidence


def _validate_parameters(value: Any) -> Mapping[str, Any]:
    parameters = _strict_object(value, {"numeric_determinism", "target_30pct", "risk"}, label="parameters")
    numeric = parameters.get("numeric_determinism")
    target = parameters.get("target_30pct")
    risk = parameters.get("risk")
    if (
        not isinstance(numeric, Mapping)
        or numeric.get("authoritative_decimal_precision_digits") != 50
        or numeric.get("money_storage") != "INTEGER_CENTS"
        or numeric.get("binary_float_for_authoritative_decision") is not False
        or not isinstance(target, Mapping)
        or target.get("monthly_return") != "0.30"
        or target.get("guaranteed") is not False
        or target.get("shortfall_behavior") != "REPORT_ONLY_NO_GATE_RELAXATION"
        or target.get("shadow_min_independent_equivalent_signals") != 1000
        or not isinstance(risk, Mapping)
        or risk.get("target_shortfall_may_relax_gate") is not False
    ):
        raise EconomicsError("canonical numeric or target safety facts differ from the frozen contract")
    return parameters


def _validate_costs(value: Any) -> Mapping[str, Any]:
    costs = _strict_object(value, {"cost_semantics", "incremental_cash_budget", "incremental_cash_gate", "development_effort_hours"}, label="costs")
    semantics = costs.get("cost_semantics")
    budget = costs.get("incremental_cash_budget")
    gate = costs.get("incremental_cash_gate")
    effort = costs.get("development_effort_hours")
    if (
        not isinstance(semantics, Mapping)
        or semantics.get("total_system_cost_is_zero") is not False
        or not isinstance(budget, Mapping)
        or budget.get("low") != "0.00"
        or budget.get("likely") != "0.00"
        or budget.get("high") != "0.00"
        or not isinstance(gate, Mapping)
        or gate.get("maximum_aud") != "0.00"
        or gate.get("automatic_purchase_allowed") is not False
        or gate.get("automatic_paid_upgrade_allowed") is not False
        or not isinstance(effort, Mapping)
        or effort.get("low") != 240
        or effort.get("likely") != 320
        or effort.get("high") != 480
    ):
        raise EconomicsError("zero-new-cash and opportunity-cost facts are not intact")
    return costs


def _validate_capacity_report(value: Any, expected_sha256: str, actual_sha256: str) -> Mapping[str, Any]:
    report = _strict_object(
        value,
        {"summary", "target_plausibility", "decision", "external_effect_boundary", "report_sha256"},
        label="capacity_report",
    )
    summary = report.get("summary")
    target = report.get("target_plausibility")
    if (
        actual_sha256 != expected_sha256
        or not isinstance(summary, Mapping)
        or summary.get("final_platform_and_executable_capacity_cents") != 4000
        or summary.get("independent_equivalent_signals") != 5
        or not isinstance(target, Mapping)
        or target.get("independent_equivalent_signals_required") != 1000
        or target.get("status") != "INSUFFICIENT_INDEPENDENT_EQUIVALENT_SIGNALS_TARGET_UNVERIFIED"
        or target.get("capacity_is_not_return_or_30_PERCENT_COVERAGE") is not True
        or report.get("decision") != "CAPACITY_CORRECTED_SYNTHETIC_ONLY_NOT_TARGET_COVERAGE"
        or target.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or report.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
    ):
        raise EconomicsError("capacity report cannot support a return or target claim")
    return report


def _validate_return_scenarios(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) != 3:
        raise EconomicsError("return_band_scenarios must contain exactly three frozen scenarios")
    rows: list[Dict[str, Any]] = []
    identifiers: set[str] = set()
    for raw in value:
        row = _strict_object(
            raw,
            {
                "scenario_id",
                "executed_capacity_fraction",
                "return_rate_low",
                "return_rate_central",
                "return_rate_high",
                "confidence",
                "failure_probability",
                "evidence_status",
            },
            label="return_band_scenario",
        )
        scenario_id = require_text(row["scenario_id"], label="scenario_id")
        if scenario_id in identifiers or row.get("evidence_status") != SYNTHETIC_EVIDENCE_STATUS:
            raise EconomicsError("return scenario identity or evidence status is invalid")
        identifiers.add(scenario_id)
        capacity_fraction = require_decimal(row["executed_capacity_fraction"], label="executed_capacity_fraction", minimum=Decimal("0"), maximum=Decimal("1"))
        low = require_decimal(row["return_rate_low"], label="return_rate_low")
        central = require_decimal(row["return_rate_central"], label="return_rate_central")
        high = require_decimal(row["return_rate_high"], label="return_rate_high")
        confidence = require_decimal(row["confidence"], label="confidence", minimum=Decimal("0"), maximum=Decimal("1"))
        failure = require_decimal(row["failure_probability"], label="failure_probability", minimum=Decimal("0"), maximum=Decimal("1"))
        if low > central or central > high or high >= Decimal("0.30"):
            raise EconomicsError("return band ordering or target-boundary guard is invalid")
        rows.append(
            {
                "scenario_id": scenario_id,
                "executed_capacity_fraction": capacity_fraction,
                "return_rate_low": low,
                "return_rate_central": central,
                "return_rate_high": high,
                "confidence": confidence,
                "failure_probability": failure,
            }
        )
    return rows


def _validate_opportunity_cost_rates(value: Any) -> list[Decimal]:
    if not isinstance(value, list) or value != ["30.00", "50.00", "100.00", "150.00"]:
        raise EconomicsError("opportunity-cost illustrative rates differ from the frozen disclosure grid")
    return [require_decimal(item, label="illustrative_hourly_value_aud", minimum=Decimal("0")) for item in value]


def _validate_fixture(
    fixture: Any,
    parameters: Any,
    costs: Any,
    capacity_report: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    capacity_report_sha256: str,
    *,
    require_expected_hash: bool,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], list[Dict[str, Any]], list[Decimal]]:
    row = _strict_object(
        fixture,
        {
            "schema_version",
            "fixture_id",
            "contract_id",
            "requirement_id",
            "stage_id",
            "phase_id",
            "product_version",
            "fixed_clock",
            "input_mode",
            "p01_evidence_sha256",
            "p02_evidence_sha256",
            "capacity_report_sha256",
            "bankroll_cents",
            "target_increment_cents",
            "incremental_cash_budget_cents",
            "return_band_scenarios",
            "illustrative_hourly_value_aud",
        },
        label="fixture",
    )
    expected_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "S12-P03-ECONOMICS-SENSITIVITY-FROZEN",
        "contract_id": "AC-S12-P03",
        "requirement_id": "REQ-S12-P03",
        "stage_id": "S12",
        "phase_id": "P03",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
    }
    if any(row.get(key) != value for key, value in expected_identity.items()):
        raise EconomicsError("fixture identity differs from the frozen P03 contract")
    if require_expected_hash and (
        not isinstance(row.get("expected_sensitivity_grid_sha256"), str)
        or len(row["expected_sensitivity_grid_sha256"]) != 64
        or not isinstance(row.get("expected_opportunity_cost_sha256"), str)
        or len(row["expected_opportunity_cost_sha256"]) != 64
    ):
        raise EconomicsError("fixture must pin both P03 output hashes")
    if require_int(row["bankroll_cents"], label="bankroll_cents", minimum=1) != 30000:
        raise EconomicsError("P03 must preserve the A$300 principal")
    if require_int(row["target_increment_cents"], label="target_increment_cents", minimum=1) != 9000:
        raise EconomicsError("P03 must preserve the A$90 monthly target increment")
    if require_int(row["incremental_cash_budget_cents"], label="incremental_cash_budget_cents", minimum=0) != 0:
        raise EconomicsError("P03 permits no new cash")
    params = _validate_parameters(parameters)
    frozen_costs = _validate_costs(costs)
    _validate_evidence(
        p01_evidence,
        require_text(row["p01_evidence_sha256"], label="p01_evidence_sha256"),
        p01_sha256,
        contract_id=P01_CONTRACT_ID,
        decision=P01_DECISION,
        next_state="S12/P02_READY_NOT_STARTED",
    )
    _validate_evidence(
        p02_evidence,
        require_text(row["p02_evidence_sha256"], label="p02_evidence_sha256"),
        p02_sha256,
        contract_id=P02_CONTRACT_ID,
        decision=P02_DECISION,
        next_state="S12/P03_READY_NOT_STARTED",
    )
    frozen_capacity = _validate_capacity_report(
        capacity_report,
        require_text(row["capacity_report_sha256"], label="capacity_report_sha256"),
        capacity_report_sha256,
    )
    return_scenarios = _validate_return_scenarios(row["return_band_scenarios"])
    hourly_rates = _validate_opportunity_cost_rates(row["illustrative_hourly_value_aud"])
    return row, params, frozen_costs, frozen_capacity, return_scenarios, hourly_rates


def build_sensitivity_grid(
    fixture: Any,
    parameters: Any,
    costs: Any,
    capacity_report: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    capacity_report_sha256: str,
    *,
    require_expected_hash: bool = True,
) -> Dict[str, Any]:
    """Build frozen scenario return bands without projecting a real return."""

    row, _, _, frozen_capacity, scenarios, _ = _validate_fixture(
        fixture,
        parameters,
        costs,
        capacity_report,
        p01_evidence,
        p02_evidence,
        p01_sha256,
        p02_sha256,
        capacity_report_sha256,
        require_expected_hash=require_expected_hash,
    )
    available_capacity = frozen_capacity["summary"]["final_platform_and_executable_capacity_cents"]
    target_increment = row["target_increment_cents"]
    bands: list[Dict[str, Any]] = []
    with localcontext() as context:
        context.prec = 50
        for scenario in scenarios:
            executable_capacity = floor_cents(
                Decimal(available_capacity) * scenario["executed_capacity_fraction"],
                label="executable_capacity_cents",
            )
            low = floor_cents(Decimal(executable_capacity) * scenario["return_rate_low"], label="return_band_low_cents")
            central = floor_cents(Decimal(executable_capacity) * scenario["return_rate_central"], label="return_band_central_cents")
            high = floor_cents(Decimal(executable_capacity) * scenario["return_rate_high"], label="return_band_high_cents")
            bands.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "evidence_status": SYNTHETIC_EVIDENCE_STATUS,
                    "executed_capacity_fraction": decimal_text(scenario["executed_capacity_fraction"]),
                    "executable_capacity_cents": executable_capacity,
                    "return_rate_band": {
                        "low": decimal_text(scenario["return_rate_low"]),
                        "central": decimal_text(scenario["return_rate_central"]),
                        "high": decimal_text(scenario["return_rate_high"]),
                    },
                    "return_band_cents": {"low": low, "central": central, "high": high},
                    "confidence": decimal_text(scenario["confidence"]),
                    "failure_probability": decimal_text(scenario["failure_probability"]),
                    "target_increment_shortfall_cents_at_upper_band": max(0, target_increment - high),
                    "target_covered": False,
                    "action": "SYNTHETIC_SENSITIVITY_NOT_ACTIONABLE",
                }
            )
    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S12-P03-02",
        "contract_id": "AC-S12-P03",
        "requirement_id": "REQ-S12-P03",
        "stage_id": "S12",
        "phase_id": "P03",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "return_bands": bands,
        "summary": {
            "available_capacity_cents_from_signed_p02": available_capacity,
            "independent_equivalent_signals_from_signed_p02": frozen_capacity["summary"]["independent_equivalent_signals"],
            "target_increment_cents": target_increment,
            "highest_upper_band_cents": max(item["return_band_cents"]["high"] for item in bands),
            "lowest_upper_band_target_shortfall_cents": min(item["target_increment_shortfall_cents_at_upper_band"] for item in bands),
            "all_scenarios_leave_target_unverified": True,
            "return_bands_are_synthetic_sensitivity_not_revenue": True,
        },
        "decision": "SYNTHETIC_ECONOMICS_SENSITIVITY_TARGET_UNVERIFIED_NO_RECOMMENDATION",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    report["sensitivity_grid_sha256"] = artifact_sha256(report)
    if require_expected_hash and report["sensitivity_grid_sha256"] != row["expected_sensitivity_grid_sha256"]:
        raise EconomicsError("sensitivity grid differs from its frozen expected hash")
    return report


def build_opportunity_cost_report(
    fixture: Any,
    parameters: Any,
    costs: Any,
    capacity_report: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    capacity_report_sha256: str,
    sensitivity_grid: Any,
    *,
    require_expected_hash: bool = True,
) -> Dict[str, Any]:
    """Disclose operating and opportunity costs without treating either as return."""

    row, _, frozen_costs, _, _, hourly_rates = _validate_fixture(
        fixture,
        parameters,
        costs,
        capacity_report,
        p01_evidence,
        p02_evidence,
        p01_sha256,
        p02_sha256,
        capacity_report_sha256,
        require_expected_hash=require_expected_hash,
    )
    grid = _strict_object(sensitivity_grid, {"sensitivity_grid_sha256", "summary", "return_bands", "decision"}, label="sensitivity_grid")
    rebuilt_grid = build_sensitivity_grid(
        fixture,
        parameters,
        costs,
        capacity_report,
        p01_evidence,
        p02_evidence,
        p01_sha256,
        p02_sha256,
        capacity_report_sha256,
        require_expected_hash=require_expected_hash,
    )
    if grid != rebuilt_grid:
        raise EconomicsError("opportunity cost report requires the exact frozen sensitivity grid")
    effort = frozen_costs["development_effort_hours"]
    opportunity_bands = []
    with localcontext() as context:
        context.prec = 50
        for hourly_value in hourly_rates:
            opportunity_bands.append(
                {
                    "illustrative_hourly_value_aud": decimal_text(hourly_value),
                    "low_aud": decimal_text(Decimal(effort["low"]) * hourly_value),
                    "likely_aud": decimal_text(Decimal(effort["likely"]) * hourly_value),
                    "high_aud": decimal_text(Decimal(effort["high"]) * hourly_value),
                    "classification": "SENSITIVITY_ONLY_NOT_OWNER_TIME_VALUATION",
                }
            )
    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S12-P03-03",
        "contract_id": "AC-S12-P03",
        "requirement_id": "REQ-S12-P03",
        "stage_id": "S12",
        "phase_id": "P03",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "operating_cost": {
            "incremental_cash_budget_cents": row["incremental_cash_budget_cents"],
            "incremental_cash_spent_cents": 0,
            "incremental_cash_status": "ZERO_NEW_CASH_ONLY_NOT_TOTAL_SYSTEM_COST",
            "existing_recurring_cost_status": "UNKNOWN_ACCOUNT_SPECIFIC_NO_BILLING_ACCESS",
            "existing_resources_are_not_relabelled_zero": True,
            "bankroll_principal_cents": row["bankroll_cents"],
        },
        "opportunity_cost_bands": opportunity_bands,
        "return_cost_boundary": {
            "sensitivity_grid_sha256": grid["sensitivity_grid_sha256"],
            "return_bands_are_not_realized_revenue": True,
            "actual_return_requires_verified_execution_and_reconciliation": True,
            "roi_reported": False,
            "target_curve_or_sensitivity_may_substitute_for_actual_return": False,
            "loss_or_drawdown_may_be_hidden": False,
        },
        "decision": "SYNTHETIC_COST_DISCLOSURE_ONLY_DO_NOT_REPORT_ROI_OR_TARGET_SUCCESS",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    report["opportunity_cost_sha256"] = artifact_sha256(report)
    if require_expected_hash and report["opportunity_cost_sha256"] != row["expected_opportunity_cost_sha256"]:
        raise EconomicsError("opportunity cost report differs from its frozen expected hash")
    return report


def build_reports(
    fixture: Any,
    parameters: Any,
    costs: Any,
    capacity_report: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    capacity_report_sha256: str,
    *,
    require_expected_hash: bool = True,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    grid = build_sensitivity_grid(
        fixture,
        parameters,
        costs,
        capacity_report,
        p01_evidence,
        p02_evidence,
        p01_sha256,
        p02_sha256,
        capacity_report_sha256,
        require_expected_hash=require_expected_hash,
    )
    opportunity_cost = build_opportunity_cost_report(
        fixture,
        parameters,
        costs,
        capacity_report,
        p01_evidence,
        p02_evidence,
        p01_sha256,
        p02_sha256,
        capacity_report_sha256,
        grid,
        require_expected_hash=require_expected_hash,
    )
    return grid, opportunity_cost


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EconomicsError("cannot load %s" % path) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build frozen ABD S12/P03 economics sensitivity artifacts")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--costs", type=Path, required=True)
    parser.add_argument("--capacity-report", type=Path, required=True)
    parser.add_argument("--p01-evidence", type=Path, required=True)
    parser.add_argument("--p02-evidence", type=Path, required=True)
    parser.add_argument("--sensitivity-grid", type=Path, required=True)
    parser.add_argument("--opportunity-cost", type=Path, required=True)
    parser.add_argument("--allow-unpinned-output", action="store_true")
    args = parser.parse_args(argv)
    grid, opportunity_cost = build_reports(
        _load_json(args.fixture),
        _load_json(args.parameters),
        _load_json(args.costs),
        _load_json(args.capacity_report),
        _load_json(args.p01_evidence),
        _load_json(args.p02_evidence),
        sha256_file(args.p01_evidence),
        sha256_file(args.p02_evidence),
        sha256_file(args.capacity_report),
        require_expected_hash=not args.allow_unpinned_output,
    )
    args.sensitivity_grid.write_bytes(canonical_json_bytes(grid))
    args.opportunity_cost.write_bytes(canonical_json_bytes(opportunity_cost))
    print(
        json.dumps(
            {
                "status": "PASS",
                "sensitivity_grid": args.sensitivity_grid.as_posix(),
                "sensitivity_grid_sha256": grid["sensitivity_grid_sha256"],
                "opportunity_cost": args.opportunity_cost.as_posix(),
                "opportunity_cost_sha256": opportunity_cost["opportunity_cost_sha256"],
                "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
