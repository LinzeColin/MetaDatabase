"""Offline, fail-closed GA and reconciliation control for ABD S19/P03.

The frozen task pack asks for GA reporting and actual reconciliation artifacts,
but its acceptance environment expressly has no external network or account.
This module therefore verifies only a zero-row local schema/control.  It never
turns that control into execution evidence, a recommendation, an order, or a
deployment.  Any attempt to represent empirical execution inside this local
evaluator closes the gate.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Dict, Mapping, Sequence


FIXED_CLOCK = "2026-08-10T08:00:00+10:00"
FEATURE_FLAG_ID = "model:s19_p03_ga_reconciliation_control_local_only"
GA_MIN_DAYS = 90
GA_MIN_SIGNALS = 1000
GA_MIN_ACTUAL_RECORDS = 200
SAFE_GA_CONFIG = {
    "stage_schema": "GA",
    "kelly_fraction": "0.25",
    "residual_weight_cap": "0.50",
    "target_shortfall_may_relax_gate": False,
    "owner_final_order_only": True,
    "order_submission_module_present": False,
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "market_or_provider_runtime_accessed": False,
    "real_account_balance_read_or_written": False,
    "real_fund_fact_or_ledger_mutated": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "gmail_account_or_api_accessed": False,
    "gmail_message_sent": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "synthetic_evidence_promoted_to_empirical": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "incremental_cash_spent_aud": "0.00",
    "owner_final_order_only": True,
}


class GAReconciliationInputError(ValueError):
    """Raised when an S19/P03 input drifts from the frozen local schema."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def artifact_sha256(value: Mapping[str, Any], field: str) -> str:
    unsigned = dict(value)
    unsigned.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GAReconciliationInputError("%s must be an object" % name)
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise GAReconciliationInputError("%s must be a boolean" % name)
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GAReconciliationInputError("%s must be a non-negative integer" % name)
    return value


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GAReconciliationInputError("%s must be an integer" % name)
    return value


def _decimal(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise GAReconciliationInputError("%s must be a decimal string" % name)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise GAReconciliationInputError("%s is not a decimal" % name) from exc
    if not result.is_finite():
        raise GAReconciliationInputError("%s must be finite" % name)
    return result


def _validate_actual_execution(value: Any) -> Mapping[str, Any]:
    actual = _mapping(value, "actual_execution_evidence")
    expected = {
        "evidence_status",
        "actual_record_count",
        "verified_days",
        "signed_execution_receipt_present",
        "evidence_complete",
        "reconciliation_difference_cents",
    }
    if set(actual) != expected:
        raise GAReconciliationInputError("actual execution evidence schema changed")
    if actual["evidence_status"] not in {"NO_EMPIRICAL_EXECUTION_EVIDENCE", "CLAIMS_EMPIRICAL_EXECUTION"}:
        raise GAReconciliationInputError("actual execution evidence status is not recognized")
    _non_negative_int(actual["actual_record_count"], "actual_record_count")
    _non_negative_int(actual["verified_days"], "verified_days")
    _bool(actual["signed_execution_receipt_present"], "signed_execution_receipt_present")
    _bool(actual["evidence_complete"], "evidence_complete")
    if actual["reconciliation_difference_cents"] is not None:
        _integer(actual["reconciliation_difference_cents"], "reconciliation_difference_cents")
    if actual["evidence_status"] == "NO_EMPIRICAL_EXECUTION_EVIDENCE" and (
        actual["actual_record_count"] != 0
        or actual["verified_days"] != 0
        or actual["signed_execution_receipt_present"]
        or actual["evidence_complete"]
        or actual["reconciliation_difference_cents"] is not None
    ):
        raise GAReconciliationInputError("no-empirical state cannot contain actual execution claims")
    return actual


def validate_ga_input(value: Any) -> Mapping[str, Any]:
    """Validate the production-shaped, zero-row local control schema."""

    if not isinstance(value, Mapping) or _contains_float(value):
        raise GAReconciliationInputError("GA input must be a non-float object")
    required = {
        "schema_version",
        "fixed_clock",
        "evaluation_id",
        "evidence_mode",
        "local_reconciliation_control",
        "actual_execution_evidence",
        "model_gate",
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    }
    if set(value) != required:
        raise GAReconciliationInputError("GA input keys do not match the frozen schema")
    if value["schema_version"] != "1.0.0" or value["fixed_clock"] != FIXED_CLOCK:
        raise GAReconciliationInputError("schema version or fixed clock changed")
    if not isinstance(value["evaluation_id"], str) or not value["evaluation_id"].startswith("S19-P03-"):
        raise GAReconciliationInputError("evaluation id is outside S19/P03")
    if value["evidence_mode"] not in {"FROZEN_LOCAL_ZERO_ROW_CONTROL", "CLAIMS_EMPIRICAL_EXECUTION"}:
        raise GAReconciliationInputError("evidence mode is not recognized")
    local = _mapping(value["local_reconciliation_control"], "local_reconciliation_control")
    if set(local) != {
        "local_ledger_row_count",
        "local_reconciliation_difference_cents",
        "evidence_artifact_complete",
        "stop_conditions_triggered",
        "probability_delta",
        "odds_tick_delta",
    }:
        raise GAReconciliationInputError("local reconciliation schema changed")
    _non_negative_int(local["local_ledger_row_count"], "local_ledger_row_count")
    _integer(local["local_reconciliation_difference_cents"], "local_reconciliation_difference_cents")
    _bool(local["evidence_artifact_complete"], "evidence_artifact_complete")
    _bool(local["stop_conditions_triggered"], "stop_conditions_triggered")
    probability_delta = _decimal(local["probability_delta"], "probability_delta")
    if probability_delta not in {Decimal("-0.0001"), Decimal("0"), Decimal("0.0001")}:
        raise GAReconciliationInputError("probability delta is outside the frozen boundary vectors")
    if local["odds_tick_delta"] not in {-1, 0}:
        raise GAReconciliationInputError("odds tick delta is outside the frozen boundary vectors")
    _validate_actual_execution(value["actual_execution_evidence"])
    model = _mapping(value["model_gate"], "model_gate")
    if set(model) != {
        "model_beta_status",
        "model_activation_allowed",
        "recommendation_generation_allowed",
        "order_submission_allowed",
        "production_equivalent_config_schema",
    }:
        raise GAReconciliationInputError("model gate schema changed")
    if not isinstance(model["model_beta_status"], str):
        raise GAReconciliationInputError("model beta status must be text")
    _bool(model["model_activation_allowed"], "model_activation_allowed")
    _bool(model["recommendation_generation_allowed"], "recommendation_generation_allowed")
    _bool(model["order_submission_allowed"], "order_submission_allowed")
    if dict(_mapping(model["production_equivalent_config_schema"], "production_equivalent_config_schema")) != SAFE_GA_CONFIG:
        raise GAReconciliationInputError("production-equivalent configuration changed or relaxed")
    for field in (
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    ):
        _bool(value[field], field)
    return value


def _unsafe_request_codes(payload: Mapping[str, Any]) -> list[str]:
    fields = {
        "requested_external_execution": "EXTERNAL_RUNTIME_REQUESTED",
        "requested_actual_order": "ACTUAL_ORDER_REQUESTED",
        "requested_real_fund_mutation": "REAL_FUND_MUTATION_REQUESTED",
        "requested_real_mail_send": "REAL_MAIL_SEND_REQUESTED",
        "requested_production_deploy": "PRODUCTION_DEPLOY_REQUESTED",
    }
    return [code for field, code in fields.items() if payload[field]]


def evaluate_ga_reconciliation(value: Any) -> Dict[str, Any]:
    """Evaluate local control completeness while keeping actual GA blocked."""

    payload = validate_ga_input(value)
    local = _mapping(payload["local_reconciliation_control"], "local_reconciliation_control")
    actual = _mapping(payload["actual_execution_evidence"], "actual_execution_evidence")
    model = _mapping(payload["model_gate"], "model_gate")
    failure_codes = _unsafe_request_codes(payload)
    local_zero_row = local["local_ledger_row_count"] == 0
    local_difference_zero = local["local_reconciliation_difference_cents"] == 0
    if not local_zero_row:
        failure_codes.append("LOCAL_CONTROL_MUST_NOT_CONTAIN_ACTUAL_LEDGER_ROWS")
    if not local_difference_zero:
        failure_codes.append("LOCAL_RECONCILIATION_DIFFERENCE_NONZERO")
    if not local["evidence_artifact_complete"]:
        failure_codes.append("LOCAL_EVIDENCE_ARTIFACT_INCOMPLETE")
    if local["stop_conditions_triggered"]:
        failure_codes.append("STOP_CONDITION_TRIGGERED")
    empirical_claim = (
        payload["evidence_mode"] != "FROZEN_LOCAL_ZERO_ROW_CONTROL"
        or actual["evidence_status"] != "NO_EMPIRICAL_EXECUTION_EVIDENCE"
        or actual["actual_record_count"] != 0
        or actual["verified_days"] != 0
        or actual["signed_execution_receipt_present"]
        or actual["evidence_complete"]
        or actual["reconciliation_difference_cents"] is not None
    )
    if empirical_claim:
        failure_codes.append("EMPIRICAL_EXECUTION_CLAIM_NOT_VERIFIABLE_IN_FROZEN_LOCAL_EVALUATOR")
    model_blocked = (
        model["model_beta_status"] == "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
        and model["model_activation_allowed"] is False
        and model["recommendation_generation_allowed"] is False
        and model["order_submission_allowed"] is False
    )
    if not model_blocked:
        failure_codes.append("MODEL_GATE_NOT_SAFELY_BLOCKED")
    local_passed = not failure_codes
    if local_passed:
        ga_status = "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE"
        decision = "LOCAL_ZERO_ROW_RECONCILIATION_CONTROL_PASS_ACTUAL_GA_BLOCKED"
    elif _unsafe_request_codes(payload):
        ga_status = "FAIL_CLOSED_UNSAFE_RUNTIME_REQUEST"
        decision = "NO_RECOMMENDATION_UNSAFE_RUNTIME_REQUEST"
    elif empirical_claim:
        ga_status = "BLOCKED_EMPIRICAL_EXECUTION_NOT_VERIFIABLE_IN_LOCAL_FIXTURE"
        decision = "NO_RECOMMENDATION_EMPIRICAL_EVIDENCE_REQUIRES_SEPARATE_SIGNED_RUNTIME_PATH"
    else:
        ga_status = "FAIL_CLOSED_LOCAL_RECONCILIATION_OR_STOP_GATE"
        decision = "NO_RECOMMENDATION_LOCAL_CONTROL_GATE_FAILED"
    result: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "fixed_clock": FIXED_CLOCK,
        "evaluation_id": payload["evaluation_id"],
        "status": "PASS_LOCAL_GA_RECONCILIATION_CONTROL" if local_passed else "FAIL_CLOSED",
        "decision": decision,
        "action": "NO_RECOMMENDATION",
        "ga_status": ga_status,
        "local_control": {
            "scope": "FROZEN_ZERO_ROW_SCHEMA_AND_RECONCILIATION_CONTROL_ONLY",
            "local_ledger_row_count": local["local_ledger_row_count"],
            "local_reconciliation_difference_cents": local["local_reconciliation_difference_cents"],
            "local_evidence_artifact_complete": local["evidence_artifact_complete"],
            "stop_conditions_triggered": local["stop_conditions_triggered"],
            "adverse_probability_delta": local["probability_delta"],
            "adverse_odds_tick_delta": local["odds_tick_delta"],
        },
        "actual_execution_observation": {
            "evidence_status": actual["evidence_status"],
            "actual_record_count": actual["actual_record_count"],
            "verified_days": actual["verified_days"],
            "actual_execution_evidence_complete": actual["evidence_complete"],
            "actual_reconciliation_difference_cents": actual["reconciliation_difference_cents"],
            "actual_reconciliation_status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
            "unresolved_reconciliation_differences": 0,
            "synthetic_or_local_control_may_substitute_for_actual": False,
        },
        "required_before_actual_ga": {
            "actual_record_count": GA_MIN_ACTUAL_RECORDS,
            "verified_days": GA_MIN_DAYS,
            "independent_qualified_signals": GA_MIN_SIGNALS,
            "signed_execution_evidence_required": True,
            "actual_reconciliation_difference_cents_required": 0,
            "model_gate_must_be_independently_eligible": True,
        },
        "model_gate": {
            "model_beta_status": model["model_beta_status"],
            "model_activation_allowed": False,
            "recommendation_generation_allowed": False,
            "order_submission_allowed": False,
            "production_equivalent_config_schema": SAFE_GA_CONFIG,
        },
        "failure_codes": failure_codes,
        "feature_flag_id": FEATURE_FLAG_ID,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    result["ga_reconciliation_evaluation_sha256"] = artifact_sha256(result, "ga_reconciliation_evaluation_sha256")
    return result


def build_ga_report(
    evaluation: Mapping[str, Any],
    *,
    fixture_sha256: str,
    predecessor_evidence_sha256: str,
    source_evidence_sha256: Mapping[str, str],
) -> Dict[str, Any]:
    if evaluation.get("status") != "PASS_LOCAL_GA_RECONCILIATION_CONTROL":
        raise GAReconciliationInputError("a failed local control cannot become a GA report")
    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S19-P03-01",
        "contract_id": "AC-S19-P03",
        "requirement_id": "REQ-S19-P03",
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS_LOCAL_GA_RECONCILIATION_CONTROL_ACTUAL_GA_BLOCKED",
        "ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
        "scope": "FROZEN_ZERO_ROW_LOCAL_CONTROL_NOT_AN_ACTUAL_GA_RELEASE",
        "local_control": evaluation["local_control"],
        "actual_execution_observation": evaluation["actual_execution_observation"],
        "required_before_actual_ga": evaluation["required_before_actual_ga"],
        "model_gate": evaluation["model_gate"],
        "fixture_sha256": fixture_sha256,
        "predecessor_evidence_sha256": predecessor_evidence_sha256,
        "source_evidence_sha256": dict(source_evidence_sha256),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    report["ga_report_sha256"] = artifact_sha256(report, "ga_report_sha256")
    return report


def build_actual_reconciliation(ga_report: Mapping[str, Any]) -> Dict[str, Any]:
    if ga_report.get("status") != "PASS_LOCAL_GA_RECONCILIATION_CONTROL_ACTUAL_GA_BLOCKED":
        raise GAReconciliationInputError("actual reconciliation artifact needs the passed local GA control")
    local = _mapping(ga_report.get("local_control"), "ga report local control")
    actual = _mapping(ga_report.get("actual_execution_observation"), "ga report actual observation")
    reconciliation: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S19-P03-02",
        "contract_id": "AC-S19-P03",
        "requirement_id": "REQ-S19-P03",
        "fixed_clock": FIXED_CLOCK,
        "status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
        "reconciliation_scope": "FROZEN_LOCAL_ZERO_ROW_SCHEMA_CONTROL_ONLY",
        "actual_execution_evidence_complete": False,
        "actual_record_count": actual["actual_record_count"],
        "verified_days": actual["verified_days"],
        "actual_reconciliation_difference_cents": None,
        "actual_reconciliation_difference_is_known": False,
        "unresolved_reconciliation_differences": actual["unresolved_reconciliation_differences"],
        "zero_difference_requirement_status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
        "local_zero_row_reconciliation_difference_cents": local["local_reconciliation_difference_cents"],
        "local_control_evidence_complete": local["local_evidence_artifact_complete"],
        "stop_conditions_triggered": local["stop_conditions_triggered"],
        "ga_activation_allowed": False,
        "recommendation_generation_allowed": False,
        "order_submission_allowed": False,
        "ga_report_sha256": ga_report["ga_report_sha256"],
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    reconciliation["actual_reconciliation_sha256"] = artifact_sha256(reconciliation, "actual_reconciliation_sha256")
    return reconciliation


__all__ = [
    "EXTERNAL_EFFECT_BOUNDARY",
    "FEATURE_FLAG_ID",
    "FIXED_CLOCK",
    "GA_MIN_ACTUAL_RECORDS",
    "GA_MIN_DAYS",
    "GA_MIN_SIGNALS",
    "GAReconciliationInputError",
    "SAFE_GA_CONFIG",
    "artifact_sha256",
    "build_actual_reconciliation",
    "build_ga_report",
    "canonical_json_bytes",
    "evaluate_ga_reconciliation",
    "validate_ga_input",
]
