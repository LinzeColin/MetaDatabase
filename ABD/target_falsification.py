"""Deterministic S12/P04 target falsification and verification contract.

This module converts the frozen S12 synthetic evidence into explicit
plausibility, falsification, and verification gates.  It deliberately does
not treat a synthetic capacity or sensitivity result as an observed return.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence


VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
EMPIRICAL_EVIDENCE_STATUS = "EMPIRICAL_SIGNED_EXECUTION_RECONCILED"
SYNTHETIC_TEST_EVIDENCE_STATUS = "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL"
NO_EMPIRICAL_EVIDENCE_STATUS = "NO_EMPIRICAL_EXECUTION_EVIDENCE"

P01_CONTRACT_ID = "AC-S12-P01"
P01_DECISION = "TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"
P02_CONTRACT_ID = "AC-S12-P02"
P02_DECISION = "CAPACITY_CORRELATION_READY_DOWNSTREAM_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"
P03_CONTRACT_ID = "AC-S12-P03"
P03_DECISION = "ECONOMICS_SENSITIVITY_READY_DOWNSTREAM_FALSIFICATION_GATE_REQUIRED"

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


class TargetFalsificationError(ValueError):
    """Raised when a target gate could overstate synthetic evidence."""


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
        raise TargetFalsificationError("%s is malformed" % label)
    return value


def require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TargetFalsificationError("%s must be a non-empty string" % label)
    return value


def require_sha256(value: Any, *, label: str) -> str:
    text = require_text(value, label=label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise TargetFalsificationError("%s must be a lower-case SHA-256" % label)
    return text


def require_int(value: Any, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TargetFalsificationError("%s must be an integer" % label)
    if minimum is not None and value < minimum:
        raise TargetFalsificationError("%s is below its minimum" % label)
    return value


def require_decimal(value: Any, *, label: str, minimum: Decimal | None = None, maximum: Decimal | None = None) -> Decimal:
    if not isinstance(value, str):
        raise TargetFalsificationError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise TargetFalsificationError("%s is not a decimal" % label) from exc
    if not parsed.is_finite():
        raise TargetFalsificationError("%s must be finite" % label)
    if minimum is not None and parsed < minimum:
        raise TargetFalsificationError("%s is below its minimum" % label)
    if maximum is not None and parsed > maximum:
        raise TargetFalsificationError("%s is above its maximum" % label)
    return parsed


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _validate_signed_evidence(
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
    expected_release = "%s_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD" % contract_id.replace("AC-", "").replace("-", "_")
    if (
        expected_sha256 != actual_sha256
        or evidence.get("contract_id") != contract_id
        or evidence.get("status") != "PASS"
        or evidence.get("decision") != decision
        or evidence.get("next") != next_state
        or evidence.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or evidence.get("release_status") != expected_release
        or not isinstance(boundary, Mapping)
        or boundary.get("order_submission_enabled") is not False
        or boundary.get("financial_return_verified_or_guaranteed") is not False
    ):
        raise TargetFalsificationError("predecessor evidence is not the exact signed synthetic prerequisite")
    return evidence


def _validate_parameters(value: Any) -> Mapping[str, Any]:
    parameters = _strict_object(value, {"numeric_determinism", "target_30pct", "risk"}, label="parameters")
    numeric = parameters.get("numeric_determinism")
    target = parameters.get("target_30pct")
    risk = parameters.get("risk")
    expected_plausible = [
        "保守月度对数增长中位数 >= ln(1.3)",
        "月度对数增长第5百分位 > 0",
        "按来源、平台限额、机会数量和相关性校正后的容量通过",
    ]
    expected_falsification = ["至少6个完整自然月", "至少1000个独立等效信号", "月收益率的95%上界仍低于30%"]
    expected_verification = ["至少12个完整自然月", "按现金流调整后的月度几何收益 >= 30%", "证据完整", "未解决对账差异为0"]
    if (
        not isinstance(numeric, Mapping)
        or numeric.get("authoritative_decimal_precision_digits") != 50
        or numeric.get("money_storage") != "INTEGER_CENTS"
        or numeric.get("binary_float_for_authoritative_decision") is not False
        or numeric.get("boundary_perturbation_absolute_threshold") != "0.0001"
        or numeric.get("boundary_perturbation_friction_up") != "0.0001"
        or numeric.get("unstable_action") != "NO_RECOMMENDATION"
        or not isinstance(target, Mapping)
        or target.get("monthly_return") != "0.30"
        or target.get("monthly_log_growth") != "0.26236426446749106"
        or target.get("formula") != "B_n = 300 * 1.3^n"
        or target.get("shadow_min_days") != 90
        or target.get("shadow_min_independent_equivalent_signals") != 1000
        or target.get("plausible_gate") != expected_plausible
        or target.get("falsification_gate") != expected_falsification
        or target.get("verification_gate") != expected_verification
        or target.get("guaranteed") is not False
        or target.get("shortfall_behavior") != "REPORT_ONLY_NO_GATE_RELAXATION"
        or not isinstance(risk, Mapping)
        or risk.get("target_shortfall_may_relax_gate") is not False
    ):
        raise TargetFalsificationError("canonical numeric, target, or risk safety facts differ from the frozen contract")
    return parameters


def _validate_capacity_report(value: Any, expected_sha256: str, actual_sha256: str) -> Mapping[str, Any]:
    report = _strict_object(value, {"summary", "target_plausibility", "decision", "external_effect_boundary", "report_sha256"}, label="capacity_report")
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
        raise TargetFalsificationError("capacity report cannot support a target or return claim")
    return report


def _validate_sensitivity_grid(value: Any, expected_sha256: str, actual_sha256: str) -> Mapping[str, Any]:
    report = _strict_object(value, {"sensitivity_grid_sha256", "summary", "return_bands", "decision", "financial_target_status", "external_effect_boundary"}, label="sensitivity_grid")
    summary = report.get("summary")
    if (
        expected_sha256 != actual_sha256
        or report.get("sensitivity_grid_sha256") != artifact_sha256({key: item for key, item in report.items() if key != "sensitivity_grid_sha256"})
        or not isinstance(summary, Mapping)
        or summary.get("available_capacity_cents_from_signed_p02") != 4000
        or summary.get("independent_equivalent_signals_from_signed_p02") != 5
        or summary.get("target_increment_cents") != 9000
        or summary.get("highest_upper_band_cents") != 800
        or summary.get("lowest_upper_band_target_shortfall_cents") != 8200
        or summary.get("all_scenarios_leave_target_unverified") is not True
        or report.get("decision") != "SYNTHETIC_ECONOMICS_SENSITIVITY_TARGET_UNVERIFIED_NO_RECOMMENDATION"
        or report.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or report.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
    ):
        raise TargetFalsificationError("sensitivity grid cannot support a target or return claim")
    return report


def _validate_opportunity_cost(value: Any, expected_sha256: str, actual_sha256: str, grid: Mapping[str, Any]) -> Mapping[str, Any]:
    report = _strict_object(value, {"opportunity_cost_sha256", "operating_cost", "return_cost_boundary", "decision", "financial_target_status", "external_effect_boundary"}, label="opportunity_cost")
    operating = report.get("operating_cost")
    boundary = report.get("return_cost_boundary")
    if (
        expected_sha256 != actual_sha256
        or report.get("opportunity_cost_sha256") != artifact_sha256({key: item for key, item in report.items() if key != "opportunity_cost_sha256"})
        or not isinstance(operating, Mapping)
        or operating.get("incremental_cash_budget_cents") != 0
        or operating.get("incremental_cash_spent_cents") != 0
        or operating.get("bankroll_principal_cents") != 30000
        or not isinstance(boundary, Mapping)
        or boundary.get("sensitivity_grid_sha256") != grid.get("sensitivity_grid_sha256")
        or boundary.get("return_bands_are_not_realized_revenue") is not True
        or boundary.get("actual_return_requires_verified_execution_and_reconciliation") is not True
        or boundary.get("roi_reported") is not False
        or report.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or report.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
    ):
        raise TargetFalsificationError("opportunity-cost disclosure cannot support a target or return claim")
    return report


def _validate_fixture(
    fixture: Any,
    parameters: Any,
    capacity_report: Any,
    sensitivity_grid: Any,
    opportunity_cost: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p03_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    p03_sha256: str,
    capacity_sha256: str,
    grid_sha256: str,
    opportunity_sha256: str,
    *,
    require_expected_hash: bool,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
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
            "p03_evidence_sha256",
            "capacity_report_sha256",
            "sensitivity_grid_sha256",
            "opportunity_cost_sha256",
            "bankroll_cents",
            "incremental_cash_budget_cents",
            "target_monthly_return",
            "current_shadow_observed_days",
            "current_independent_equivalent_signals",
            "current_empirical_falsification_record",
            "current_empirical_verification_record",
            "synthetic_falsification_case",
        },
        label="fixture",
    )
    expected_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "S12-P04-TARGET-FALSIFICATION-FROZEN",
        "contract_id": "AC-S12-P04",
        "requirement_id": "REQ-S12-P04",
        "stage_id": "S12",
        "phase_id": "P04",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
    }
    if any(row.get(key) != item for key, item in expected_identity.items()):
        raise TargetFalsificationError("fixture identity differs from the frozen P04 contract")
    if require_expected_hash and (
        not isinstance(row.get("expected_target_acceptance_sha256"), str)
        or not isinstance(row.get("expected_kill_report_schema_sha256"), str)
    ):
        raise TargetFalsificationError("fixture must pin both P04 output hashes")
    if require_int(row["bankroll_cents"], label="bankroll_cents", minimum=1) != 30000:
        raise TargetFalsificationError("P04 must preserve the A$300 principal")
    if require_int(row["incremental_cash_budget_cents"], label="incremental_cash_budget_cents", minimum=0) != 0:
        raise TargetFalsificationError("P04 permits no new cash")
    if require_decimal(row["target_monthly_return"], label="target_monthly_return") != Decimal("0.30"):
        raise TargetFalsificationError("P04 must preserve the 30 percent monthly target threshold")
    if require_int(row["current_shadow_observed_days"], label="current_shadow_observed_days", minimum=0) != 0:
        raise TargetFalsificationError("the frozen fixture must not invent a 90-day observation history")
    if require_int(row["current_independent_equivalent_signals"], label="current_independent_equivalent_signals", minimum=0) != 5:
        raise TargetFalsificationError("P04 must preserve the signed P02 five-signal capacity fact")
    params = _validate_parameters(parameters)
    _validate_signed_evidence(p01_evidence, require_sha256(row["p01_evidence_sha256"], label="p01_evidence_sha256"), p01_sha256, contract_id=P01_CONTRACT_ID, decision=P01_DECISION, next_state="S12/P02_READY_NOT_STARTED")
    _validate_signed_evidence(p02_evidence, require_sha256(row["p02_evidence_sha256"], label="p02_evidence_sha256"), p02_sha256, contract_id=P02_CONTRACT_ID, decision=P02_DECISION, next_state="S12/P03_READY_NOT_STARTED")
    _validate_signed_evidence(p03_evidence, require_sha256(row["p03_evidence_sha256"], label="p03_evidence_sha256"), p03_sha256, contract_id=P03_CONTRACT_ID, decision=P03_DECISION, next_state="S12/P04_READY_NOT_STARTED")
    capacity = _validate_capacity_report(capacity_report, require_sha256(row["capacity_report_sha256"], label="capacity_report_sha256"), capacity_sha256)
    grid = _validate_sensitivity_grid(
        sensitivity_grid,
        require_sha256(row["sensitivity_grid_sha256"], label="sensitivity_grid_sha256"),
        require_sha256(sensitivity_grid.get("sensitivity_grid_sha256"), label="actual_sensitivity_grid_sha256") if isinstance(sensitivity_grid, Mapping) else "",
    )
    opportunity = _validate_opportunity_cost(
        opportunity_cost,
        require_sha256(row["opportunity_cost_sha256"], label="opportunity_cost_sha256"),
        require_sha256(opportunity_cost.get("opportunity_cost_sha256"), label="actual_opportunity_cost_sha256") if isinstance(opportunity_cost, Mapping) else "",
        grid,
    )
    return row, params, capacity, grid, opportunity


def classify_falsification(record: Any, *, target_monthly_return: Decimal) -> Dict[str, Any]:
    """Classify a six-month falsification record without treating a fixture as empirical."""

    row = _strict_object(
        record,
        {"evidence_status", "complete_calendar_months", "independent_equivalent_signals", "monthly_return_95_upper_bound"},
        label="falsification_record",
    )
    evidence_status = require_text(row["evidence_status"], label="falsification_evidence_status")
    months = require_int(row["complete_calendar_months"], label="complete_calendar_months", minimum=0)
    signals = require_int(row["independent_equivalent_signals"], label="independent_equivalent_signals", minimum=0)
    upper_bound = require_decimal(row["monthly_return_95_upper_bound"], label="monthly_return_95_upper_bound")
    base = {
        "complete_calendar_months": months,
        "independent_equivalent_signals": signals,
        "monthly_return_95_upper_bound": decimal_text(upper_bound),
        "target_monthly_return": decimal_text(target_monthly_return),
        "evidence_status": evidence_status,
    }
    if evidence_status != EMPIRICAL_EVIDENCE_STATUS:
        return {**base, "status": "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL" if evidence_status == SYNTHETIC_TEST_EVIDENCE_STATUS else "NOT_EVALUABLE_NO_EMPIRICAL_6_MONTH_DATA", "reason_code": "FALSIFICATION_REQUIRES_6_COMPLETE_MONTHS_AND_1000_SIGNALS"}
    if months < 6 or signals < 1000:
        return {**base, "status": "NOT_EVALUABLE_INSUFFICIENT_6_MONTHS_OR_1000_SIGNALS", "reason_code": "FALSIFICATION_REQUIRES_6_COMPLETE_MONTHS_AND_1000_SIGNALS"}
    if upper_bound < target_monthly_return:
        return {**base, "status": "FALSIFIED", "reason_code": "TARGET_FALSIFIED_95_PERCENT_UPPER_BOUND_BELOW_30_PERCENT"}
    return {**base, "status": "NOT_FALSIFIED_CONTINUE_EMPIRICAL_OBSERVATION", "reason_code": "TARGET_NOT_FALSIFIED_BY_CURRENT_EMPIRICAL_RECORD"}


def classify_verification(record: Any, *, target_monthly_return: Decimal) -> Dict[str, Any]:
    """Classify a twelve-month verification record without manufacturing execution evidence."""

    row = _strict_object(
        record,
        {"evidence_status", "complete_calendar_months", "cashflow_adjusted_geometric_monthly_return", "evidence_complete", "unresolved_reconciliation_differences"},
        label="verification_record",
    )
    evidence_status = require_text(row["evidence_status"], label="verification_evidence_status")
    months = require_int(row["complete_calendar_months"], label="verification_complete_calendar_months", minimum=0)
    return_rate = require_decimal(row["cashflow_adjusted_geometric_monthly_return"], label="cashflow_adjusted_geometric_monthly_return")
    complete = row["evidence_complete"] is True
    differences = require_int(row["unresolved_reconciliation_differences"], label="unresolved_reconciliation_differences", minimum=0)
    base = {
        "complete_calendar_months": months,
        "cashflow_adjusted_geometric_monthly_return": decimal_text(return_rate),
        "evidence_complete": complete,
        "unresolved_reconciliation_differences": differences,
        "target_monthly_return": decimal_text(target_monthly_return),
        "evidence_status": evidence_status,
    }
    if evidence_status != EMPIRICAL_EVIDENCE_STATUS:
        return {**base, "status": "NOT_VERIFIABLE_NO_ACTUAL_EXECUTION_AND_RECONCILIATION_EVIDENCE", "reason_code": "VERIFICATION_REQUIRES_12_MONTHS_EXECUTION_EVIDENCE_AND_ZERO_RECONCILIATION_DIFFERENCE"}
    if months < 12 or not complete or differences != 0:
        return {**base, "status": "NOT_VERIFIABLE_INSUFFICIENT_12_MONTHS_OR_EVIDENCE", "reason_code": "VERIFICATION_REQUIRES_12_MONTHS_EXECUTION_EVIDENCE_AND_ZERO_RECONCILIATION_DIFFERENCE"}
    if return_rate >= target_monthly_return:
        return {**base, "status": "VERIFIED_30_PERCENT_TARGET", "reason_code": "EMPIRICAL_VERIFICATION_GATES_MET"}
    return {**base, "status": "NOT_VERIFIED_EMPIRICAL_RETURN_BELOW_TARGET", "reason_code": "EMPIRICAL_RETURN_BELOW_30_PERCENT_TARGET"}


def build_target_acceptance(
    fixture: Any,
    parameters: Any,
    capacity_report: Any,
    sensitivity_grid: Any,
    opportunity_cost: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p03_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    p03_sha256: str,
    capacity_sha256: str,
    grid_sha256: str,
    opportunity_sha256: str,
    *,
    require_expected_hash: bool = True,
) -> Dict[str, Any]:
    """Build the P04 acceptance artifact from exact signed predecessor inputs."""

    row, params, capacity, grid, opportunity = _validate_fixture(
        fixture,
        parameters,
        capacity_report,
        sensitivity_grid,
        opportunity_cost,
        p01_evidence,
        p02_evidence,
        p03_evidence,
        p01_sha256,
        p02_sha256,
        p03_sha256,
        capacity_sha256,
        grid_sha256,
        opportunity_sha256,
        require_expected_hash=require_expected_hash,
    )
    target = params["target_30pct"]
    target_return = require_decimal(target["monthly_return"], label="canonical_target_monthly_return")
    current_falsification = classify_falsification(row["current_empirical_falsification_record"], target_monthly_return=target_return)
    current_verification = classify_verification(row["current_empirical_verification_record"], target_monthly_return=target_return)
    synthetic_case = classify_falsification(row["synthetic_falsification_case"], target_monthly_return=target_return)
    if (
        current_falsification["status"] != "NOT_EVALUABLE_NO_EMPIRICAL_6_MONTH_DATA"
        or current_verification["status"] != "NOT_VERIFIABLE_NO_ACTUAL_EXECUTION_AND_RECONCILIATION_EVIDENCE"
        or synthetic_case["status"] != "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL"
    ):
        raise TargetFalsificationError("fixture must preserve the absence of empirical falsification and verification evidence")
    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S12-P04-02",
        "contract_id": "AC-S12-P04",
        "requirement_id": "REQ-S12-P04",
        "stage_id": "S12",
        "phase_id": "P04",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "source_evidence": {
            "p01_evidence_sha256": p01_sha256,
            "p02_evidence_sha256": p02_sha256,
            "p03_evidence_sha256": p03_sha256,
            "capacity_report_sha256": capacity_sha256,
            "sensitivity_grid_content_sha256": grid["sensitivity_grid_sha256"],
            "opportunity_cost_content_sha256": opportunity["opportunity_cost_sha256"],
            "sensitivity_grid_file_sha256": grid_sha256,
            "opportunity_cost_file_sha256": opportunity_sha256,
        },
        "plausibility_gate": {
            "required_shadow_days": target["shadow_min_days"],
            "observed_shadow_days": row["current_shadow_observed_days"],
            "required_independent_equivalent_signals": target["shadow_min_independent_equivalent_signals"],
            "observed_independent_equivalent_signals": row["current_independent_equivalent_signals"],
            "source_capacity_independent_equivalent_signals": capacity["summary"]["independent_equivalent_signals"],
            "required_conditions": target["plausible_gate"],
            "status": "NOT_PLAUSIBLE_INSUFFICIENT_90D_OR_1000_SIGNALS",
            "reason_code": "PLAUSIBILITY_INSUFFICIENT_90D_OR_1000_SIGNALS",
        },
        "falsification_gate": {
            "required_conditions": target["falsification_gate"],
            "current_empirical_assessment": current_falsification,
            "synthetic_case_assessment": synthetic_case,
            "synthetic_case_is_not_empirical": True,
        },
        "verification_gate": {
            "required_conditions": target["verification_gate"],
            "current_empirical_assessment": current_verification,
        },
        "target_shortfall_report": {
            "bankroll_principal_cents": row["bankroll_cents"],
            "incremental_cash_budget_cents": row["incremental_cash_budget_cents"],
            "target_increment_cents": grid["summary"]["target_increment_cents"],
            "best_synthetic_upper_band_cents": grid["summary"]["highest_upper_band_cents"],
            "synthetic_upper_band_shortfall_cents": grid["summary"]["lowest_upper_band_target_shortfall_cents"],
            "status": "TARGET_SHORTFALL_REPORT_ONLY",
        },
        "hard_gate_invariants": {
            "shortfall_behavior": target["shortfall_behavior"],
            "risk_target_shortfall_may_relax_gate": params["risk"]["target_shortfall_may_relax_gate"],
            "threshold_or_position_or_evidence_may_be_relaxed": False,
            "synthetic_artifacts_may_substitute_for_actual_return": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "financial_return_verified_or_guaranteed": False,
        },
        "decision": "TARGET_FALSIFICATION_CONTRACT_READY_NO_EMPIRICAL_TARGET_VERIFICATION",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    report["target_acceptance_sha256"] = artifact_sha256(report)
    if require_expected_hash and report["target_acceptance_sha256"] != row["expected_target_acceptance_sha256"]:
        raise TargetFalsificationError("target acceptance differs from its frozen expected hash")
    return report


def build_kill_report_schema(
    fixture: Any,
    parameters: Any,
    capacity_report: Any,
    sensitivity_grid: Any,
    opportunity_cost: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p03_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    p03_sha256: str,
    capacity_sha256: str,
    grid_sha256: str,
    opportunity_sha256: str,
    *,
    require_expected_hash: bool = True,
) -> Dict[str, Any]:
    """Build the structured reason-code schema for target shortfall and gate outcomes."""

    row, params, _, _, _ = _validate_fixture(
        fixture,
        parameters,
        capacity_report,
        sensitivity_grid,
        opportunity_cost,
        p01_evidence,
        p02_evidence,
        p03_evidence,
        p01_sha256,
        p02_sha256,
        p03_sha256,
        capacity_sha256,
        grid_sha256,
        opportunity_sha256,
        require_expected_hash=require_expected_hash,
    )
    schema: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S12-P04-03",
        "contract_id": "AC-S12-P04",
        "requirement_id": "REQ-S12-P04",
        "stage_id": "S12",
        "phase_id": "P04",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "record_required_fields": ["reason_code", "status", "evidence_status", "observed_at_or_fixed_clock", "source_artifact_sha256", "recommended_action"],
        "reason_codes": [
            {"code": "TARGET_SHORTFALL_REPORT_ONLY", "meaning": "目标短缺仅报告，不修改阈值、仓位或证据门。", "safe_action": "KEEP_GATES_UNCHANGED_NO_RECOMMENDATION"},
            {"code": "PLAUSIBILITY_INSUFFICIENT_90D_OR_1000_SIGNALS", "meaning": "90天或1000独立等效信号未满足，不能宣称可行。", "safe_action": "CONTINUE_OBSERVATION_WITHOUT_GATE_RELAXATION"},
            {"code": "FALSIFICATION_REQUIRES_6_COMPLETE_MONTHS_AND_1000_SIGNALS", "meaning": "未有6个完整自然月和1000独立等效信号的经验数据，不得证伪。", "safe_action": "KEEP_UNVERIFIED"},
            {"code": "VERIFICATION_REQUIRES_12_MONTHS_EXECUTION_EVIDENCE_AND_ZERO_RECONCILIATION_DIFFERENCE", "meaning": "未有12个月实际执行、完整证据和零未解决对账差异，不得验证。", "safe_action": "KEEP_UNVERIFIED"},
            {"code": "NO_GATE_RELAXATION_FOR_TARGET_SHORTFALL", "meaning": "目标短缺不能放松风险、证据、来源、阈值或仓位控制。", "safe_action": "NO_RECOMMENDATION"},
        ],
        "hard_invariants": {
            "target_shortfall_behavior": params["target_30pct"]["shortfall_behavior"],
            "risk_target_shortfall_may_relax_gate": params["risk"]["target_shortfall_may_relax_gate"],
            "actual_return_required_for_verification": True,
            "synthetic_fixture_may_be_marked_empirical": False,
            "order_submission_enabled": False,
        },
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    schema["kill_report_schema_sha256"] = artifact_sha256(schema)
    if require_expected_hash and schema["kill_report_schema_sha256"] != row["expected_kill_report_schema_sha256"]:
        raise TargetFalsificationError("kill-report schema differs from its frozen expected hash")
    return schema


def build_artifacts(
    fixture: Any,
    parameters: Any,
    capacity_report: Any,
    sensitivity_grid: Any,
    opportunity_cost: Any,
    p01_evidence: Any,
    p02_evidence: Any,
    p03_evidence: Any,
    p01_sha256: str,
    p02_sha256: str,
    p03_sha256: str,
    capacity_sha256: str,
    grid_sha256: str,
    opportunity_sha256: str,
    *,
    require_expected_hash: bool = True,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    target_acceptance = build_target_acceptance(
        fixture, parameters, capacity_report, sensitivity_grid, opportunity_cost, p01_evidence, p02_evidence, p03_evidence,
        p01_sha256, p02_sha256, p03_sha256, capacity_sha256, grid_sha256, opportunity_sha256,
        require_expected_hash=require_expected_hash,
    )
    kill_schema = build_kill_report_schema(
        fixture, parameters, capacity_report, sensitivity_grid, opportunity_cost, p01_evidence, p02_evidence, p03_evidence,
        p01_sha256, p02_sha256, p03_sha256, capacity_sha256, grid_sha256, opportunity_sha256,
        require_expected_hash=require_expected_hash,
    )
    return target_acceptance, kill_schema


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TargetFalsificationError("cannot load %s" % path) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build frozen ABD S12/P04 target gate artifacts")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--capacity-report", type=Path, required=True)
    parser.add_argument("--sensitivity-grid", type=Path, required=True)
    parser.add_argument("--opportunity-cost", type=Path, required=True)
    parser.add_argument("--p01-evidence", type=Path, required=True)
    parser.add_argument("--p02-evidence", type=Path, required=True)
    parser.add_argument("--p03-evidence", type=Path, required=True)
    parser.add_argument("--target-acceptance", type=Path, required=True)
    parser.add_argument("--kill-report-schema", type=Path, required=True)
    parser.add_argument("--allow-unpinned-output", action="store_true")
    args = parser.parse_args(argv)
    target_acceptance, kill_schema = build_artifacts(
        _load_json(args.fixture),
        _load_json(args.parameters),
        _load_json(args.capacity_report),
        _load_json(args.sensitivity_grid),
        _load_json(args.opportunity_cost),
        _load_json(args.p01_evidence),
        _load_json(args.p02_evidence),
        _load_json(args.p03_evidence),
        sha256_file(args.p01_evidence),
        sha256_file(args.p02_evidence),
        sha256_file(args.p03_evidence),
        sha256_file(args.capacity_report),
        sha256_file(args.sensitivity_grid),
        sha256_file(args.opportunity_cost),
        require_expected_hash=not args.allow_unpinned_output,
    )
    args.target_acceptance.write_bytes(canonical_json_bytes(target_acceptance))
    args.kill_report_schema.write_bytes(canonical_json_bytes(kill_schema))
    print(json.dumps({"status": "PASS", "target_acceptance": args.target_acceptance.as_posix(), "target_acceptance_sha256": target_acceptance["target_acceptance_sha256"], "kill_report_schema": args.kill_report_schema.as_posix(), "kill_report_schema_sha256": kill_schema["kill_report_schema_sha256"], "financial_target_status": "UNVERIFIED_NOT_GUARANTEED"}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
