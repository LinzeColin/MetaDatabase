"""Offline, fail-closed shadow and Model Beta control for ABD S19/P02.

This module evaluates only a frozen synthetic metric fixture.  It deliberately
does not observe a market, account, mailbox, provider, server, or database.
Consequently a synthetically passing metric vector can prove the local gate
logic, but can never become empirical real-time shadow evidence or activate a
Model Beta release.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Dict, Mapping, Sequence


FIXED_CLOCK = "2026-08-10T07:00:00+10:00"
FEATURE_FLAG_ID = "model:s19_p02_shadow_beta_local_only"
BETA_MIN_DAYS = 60
BETA_MIN_SIGNALS = 500
TARGET_MIN_DAYS = 90
TARGET_MIN_SIGNALS = 1000
SAFE_MODEL_CONFIG = {
    "stage": "BETA",
    "kelly_fraction": "0.20",
    "residual_weight_cap": "0.35",
    "target_shortfall_may_relax_gate": False,
    "unstable_action": "NO_RECOMMENDATION",
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


class ShadowBetaInputError(ValueError):
    """Raised when a S19/P02 input cannot be interpreted safely."""


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
        raise ShadowBetaInputError("%s must be an object" % name)
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ShadowBetaInputError("%s must be a boolean" % name)
    return value


def _int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShadowBetaInputError("%s must be a non-negative integer" % name)
    return value


def _decimal(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ShadowBetaInputError("%s must be a decimal string" % name)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ShadowBetaInputError("%s is not a decimal" % name) from exc
    if not result.is_finite():
        raise ShadowBetaInputError("%s must be finite" % name)
    return result


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def validate_shadow_input(value: Any) -> Mapping[str, Any]:
    """Validate the production-shaped but fully frozen local schema."""

    if not isinstance(value, Mapping) or _contains_float(value):
        raise ShadowBetaInputError("shadow input must be a non-float object")
    required = {
        "schema_version",
        "fixed_clock",
        "evaluation_id",
        "evidence_kind",
        "runtime_evidence_receipt_present",
        "synthetic_window",
        "metric_snapshot",
        "model_config",
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    }
    if set(value) != required:
        raise ShadowBetaInputError("shadow input keys do not match the frozen schema")
    if value["schema_version"] != "1.0.0" or value["fixed_clock"] != FIXED_CLOCK:
        raise ShadowBetaInputError("schema version or fixed clock changed")
    if not isinstance(value["evaluation_id"], str) or not value["evaluation_id"].startswith("S19-P02-"):
        raise ShadowBetaInputError("evaluation id is outside S19/P02")
    if value["evidence_kind"] not in {"FROZEN_SYNTHETIC_TEST_ONLY", "SIGNED_EMPIRICAL_REALTIME_SHADOW"}:
        raise ShadowBetaInputError("evidence kind is not recognized")
    receipt = _bool(value["runtime_evidence_receipt_present"], "runtime_evidence_receipt_present")
    if value["evidence_kind"] == "FROZEN_SYNTHETIC_TEST_ONLY" and receipt:
        raise ShadowBetaInputError("synthetic fixtures cannot carry a runtime receipt")
    window = _mapping(value["synthetic_window"], "synthetic_window")
    if set(window) != {"logical_shadow_days", "logical_qualified_signals"}:
        raise ShadowBetaInputError("synthetic window keys changed")
    _int(window["logical_shadow_days"], "logical_shadow_days")
    _int(window["logical_qualified_signals"], "logical_qualified_signals")
    metrics = _mapping(value["metric_snapshot"], "metric_snapshot")
    expected_metrics = {
        "calibration_slope",
        "calibration_intercept",
        "calibration_error_main",
        "calibration_error_niche",
        "brier_skill_95_lcb",
        "logloss_skill_95_lcb",
        "closing_price_advantage_95_lcb",
        "net_log_growth_95_lcb",
        "quote_age_seconds",
        "advice_age_seconds",
        "capacity_gate_passed",
        "population_stability_index",
        "jensen_shannon",
        "probability_delta",
        "odds_tick_delta",
    }
    if set(metrics) != expected_metrics:
        raise ShadowBetaInputError("metric snapshot keys changed")
    for key in (
        "calibration_slope",
        "calibration_intercept",
        "calibration_error_main",
        "calibration_error_niche",
        "brier_skill_95_lcb",
        "logloss_skill_95_lcb",
        "closing_price_advantage_95_lcb",
        "net_log_growth_95_lcb",
        "population_stability_index",
        "jensen_shannon",
        "probability_delta",
    ):
        _decimal(metrics[key], key)
    if metrics["probability_delta"] not in {"0", "-0.0001"}:
        raise ShadowBetaInputError("probability delta is outside the frozen boundary vectors")
    if metrics["odds_tick_delta"] not in {-1, 0}:
        raise ShadowBetaInputError("odds tick delta is outside the frozen boundary vectors")
    _int(metrics["quote_age_seconds"], "quote_age_seconds")
    _int(metrics["advice_age_seconds"], "advice_age_seconds")
    _bool(metrics["capacity_gate_passed"], "capacity_gate_passed")
    if dict(_mapping(value["model_config"], "model_config")) != SAFE_MODEL_CONFIG:
        raise ShadowBetaInputError("model configuration changed or relaxed")
    for key in (
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    ):
        _bool(value[key], key)
    return value


def _quality_gates(payload: Mapping[str, Any]) -> list[Dict[str, Any]]:
    metrics = _mapping(payload["metric_snapshot"], "metric_snapshot")
    slope = _decimal(metrics["calibration_slope"], "calibration_slope") + _decimal(metrics["probability_delta"], "probability_delta")
    intercept = _decimal(metrics["calibration_intercept"], "calibration_intercept")
    error_main = _decimal(metrics["calibration_error_main"], "calibration_error_main")
    error_niche = _decimal(metrics["calibration_error_niche"], "calibration_error_niche")
    brier = _decimal(metrics["brier_skill_95_lcb"], "brier_skill_95_lcb")
    logloss = _decimal(metrics["logloss_skill_95_lcb"], "logloss_skill_95_lcb")
    closing = _decimal(metrics["closing_price_advantage_95_lcb"], "closing_price_advantage_95_lcb")
    net_growth = _decimal(metrics["net_log_growth_95_lcb"], "net_log_growth_95_lcb")
    psi = _decimal(metrics["population_stability_index"], "population_stability_index")
    js = _decimal(metrics["jensen_shannon"], "jensen_shannon")
    calibration = (
        Decimal("0.90") <= slope <= Decimal("1.10")
        and abs(intercept) <= Decimal("0.02")
        and error_main <= Decimal("0.025")
        and error_niche <= Decimal("0.04")
        and brier > 0
        and logloss > 0
        and closing > 0
    )
    freshness = metrics["quote_age_seconds"] <= 12 and metrics["advice_age_seconds"] <= 8
    drift = psi < Decimal("0.20") and js < Decimal("0.10")
    return [
        {
            "gate_id": "CALIBRATION",
            "passed": calibration,
            "adjusted_slope": _decimal_text(slope),
            "intercept": _decimal_text(intercept),
            "main_error": _decimal_text(error_main),
            "niche_error": _decimal_text(error_niche),
            "confidence_lower_bounds_strictly_positive": brier > 0 and logloss > 0 and closing > 0,
        },
        {
            "gate_id": "NET_GROWTH",
            "passed": net_growth > 0,
            "net_log_growth_95_lcb": _decimal_text(net_growth),
            "rule": "STRICTLY_GREATER_THAN_0",
        },
        {
            "gate_id": "FRESHNESS",
            "passed": freshness,
            "quote_age_seconds": metrics["quote_age_seconds"],
            "quote_usable_seconds": 12,
            "advice_age_seconds": metrics["advice_age_seconds"],
            "advice_usable_seconds": 8,
        },
        {
            "gate_id": "CAPACITY",
            "passed": metrics["capacity_gate_passed"],
            "classification": "FROZEN_SYNTHETIC_CAPACITY_ASSERTION_NOT_REAL_PROVIDER_CAPACITY",
        },
        {
            "gate_id": "DRIFT",
            "passed": drift,
            "population_stability_index": _decimal_text(psi),
            "population_stability_index_stop": "0.20",
            "jensen_shannon": _decimal_text(js),
            "jensen_shannon_stop": "0.10",
            "rule": "STRICTLY_BELOW_STOP_LINES",
        },
    ]


def _unsafe_request_codes(payload: Mapping[str, Any]) -> list[str]:
    fields = {
        "requested_external_execution": "EXTERNAL_RUNTIME_REQUESTED",
        "requested_actual_order": "ACTUAL_ORDER_REQUESTED",
        "requested_real_fund_mutation": "REAL_FUND_MUTATION_REQUESTED",
        "requested_real_mail_send": "REAL_MAIL_SEND_REQUESTED",
        "requested_production_deploy": "PRODUCTION_DEPLOY_REQUESTED",
    }
    return [code for field, code in fields.items() if payload[field]]


def evaluate_shadow_beta(value: Any) -> Dict[str, Any]:
    """Evaluate frozen metric gates and always keep unverified Beta blocked."""

    payload = validate_shadow_input(value)
    gates = _quality_gates(payload)
    gate_map = {item["gate_id"]: item["passed"] for item in gates}
    quality_passed = all(gate_map.values())
    unsafe = _unsafe_request_codes(payload)
    synthetic_window = _mapping(payload["synthetic_window"], "synthetic_window")
    synthetic_beta_thresholds_met = (
        synthetic_window["logical_shadow_days"] >= BETA_MIN_DAYS
        and synthetic_window["logical_qualified_signals"] >= BETA_MIN_SIGNALS
    )
    synthetic_target_thresholds_met = (
        synthetic_window["logical_shadow_days"] >= TARGET_MIN_DAYS
        and synthetic_window["logical_qualified_signals"] >= TARGET_MIN_SIGNALS
    )
    promotion_attempt = payload["evidence_kind"] == "SIGNED_EMPIRICAL_REALTIME_SHADOW"
    failure_codes = list(unsafe)
    if promotion_attempt:
        failure_codes.append("EMPIRICAL_EVIDENCE_NOT_VERIFIABLE_IN_FROZEN_LOCAL_EVALUATOR")
    failure_codes.extend("%s_GATE_FAILED" % gate for gate, passed in gate_map.items() if not passed)
    local_passed = quality_passed and not unsafe and not promotion_attempt and payload["evidence_kind"] == "FROZEN_SYNTHETIC_TEST_ONLY"
    if unsafe:
        model_beta_status = "FAIL_CLOSED_UNSAFE_RUNTIME_REQUEST"
    elif promotion_attempt:
        model_beta_status = "BLOCKED_EMPIRICAL_EVIDENCE_NOT_VERIFIABLE_IN_LOCAL_FIXTURE"
    elif not quality_passed:
        model_beta_status = "BLOCKED_QUALITY_GATE_FAILURE"
    else:
        model_beta_status = "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE"
    result: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "fixed_clock": FIXED_CLOCK,
        "evaluation_id": payload["evaluation_id"],
        "status": "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT" if local_passed else "FAIL_CLOSED",
        "decision": "LOCAL_SHADOW_METRIC_GATES_PASS_EMPIRICAL_RUNTIME_REQUIRED" if local_passed else "NO_RECOMMENDATION_QUALITY_OR_EVIDENCE_GATE_FAILED",
        "action": "NO_RECOMMENDATION",
        "quality_gates": gates,
        "all_quality_gates_pass": quality_passed,
        "synthetic_window": {
            "evidence_status": "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL",
            "logical_shadow_days": synthetic_window["logical_shadow_days"],
            "logical_qualified_signals": synthetic_window["logical_qualified_signals"],
            "beta_thresholds_met_in_fixture_only": synthetic_beta_thresholds_met,
            "target_plausibility_thresholds_met_in_fixture_only": synthetic_target_thresholds_met,
        },
        "empirical_observation": {
            "evidence_status": "NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE",
            "observed_realtime_shadow_days": 0,
            "observed_realtime_qualified_signals": 0,
            "model_beta_required_days": BETA_MIN_DAYS,
            "model_beta_required_qualified_signals": BETA_MIN_SIGNALS,
            "target_plausibility_required_days": TARGET_MIN_DAYS,
            "target_plausibility_required_independent_equivalent_signals": TARGET_MIN_SIGNALS,
            "synthetic_fixture_counts_may_substitute": False,
        },
        "model_beta_status": model_beta_status,
        "model_beta_eligible": False,
        "failure_codes": failure_codes,
        "model_config_before": SAFE_MODEL_CONFIG,
        "model_config_after": SAFE_MODEL_CONFIG,
        "feature_flag_id": FEATURE_FLAG_ID,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    result["shadow_beta_evaluation_sha256"] = artifact_sha256(result, "shadow_beta_evaluation_sha256")
    return result


def build_shadow_report(
    evaluation: Mapping[str, Any],
    *,
    fixture_sha256: str,
    predecessor_evidence_sha256: str,
    source_evidence_sha256: Mapping[str, str],
) -> Dict[str, Any]:
    if evaluation.get("status") != "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT":
        raise ShadowBetaInputError("a failed evaluation cannot become a signed local shadow report")
    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S19-P02-01",
        "contract_id": "AC-S19-P02",
        "requirement_id": "REQ-S19-P02",
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT",
        "scope": "FROZEN_SYNTHETIC_METRIC_GATE_REPLAY_ONLY",
        "quality_gates": evaluation["quality_gates"],
        "synthetic_window": evaluation["synthetic_window"],
        "empirical_observation": evaluation["empirical_observation"],
        "model_beta_status": evaluation["model_beta_status"],
        "model_beta_eligible": False,
        "fixture_sha256": fixture_sha256,
        "predecessor_evidence_sha256": predecessor_evidence_sha256,
        "source_evidence_sha256": dict(source_evidence_sha256),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    report["shadow_report_sha256"] = artifact_sha256(report, "shadow_report_sha256")
    return report


def build_model_beta_gate(shadow_report: Mapping[str, Any]) -> Dict[str, Any]:
    if shadow_report.get("status") != "PASS_LOCAL_SYNTHETIC_METRIC_CONTRACT":
        raise ShadowBetaInputError("Model Beta gate needs a passed local metric report")
    gate: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S19-P02-02",
        "contract_id": "AC-S19-P02",
        "requirement_id": "REQ-S19-P02",
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS_LOCAL_CONTRACT_MODEL_BETA_BLOCKED",
        "local_contract_validation_status": "PASS_ALL_SYNTHETIC_QUALITY_GATES",
        "model_beta_status": "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE",
        "model_beta_eligible": False,
        "model_activation_allowed": False,
        "recommendation_generation_allowed": False,
        "order_submission_allowed": False,
        "promotion_basis": "SYNTHETIC_METRIC_GATE_REPLAY_IS_NOT_EMPIRICAL_REALTIME_SHADOW",
        "required_before_model_beta": {
            "realtime_shadow_days": BETA_MIN_DAYS,
            "realtime_qualified_signals": BETA_MIN_SIGNALS,
            "signed_empirical_evidence_required": True,
            "all_quality_gates_must_pass": True,
        },
        "required_for_target_plausibility": {
            "realtime_shadow_days": TARGET_MIN_DAYS,
            "independent_equivalent_signals": TARGET_MIN_SIGNALS,
            "capacity_gate": "EMPIRICAL_SOURCE_PLATFORM_CORRELATION_ADJUSTED",
        },
        "shadow_report_sha256": shadow_report["shadow_report_sha256"],
        "next_required_gate": "S19/P03_READY_NOT_STARTED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    gate["model_beta_gate_sha256"] = artifact_sha256(gate, "model_beta_gate_sha256")
    return gate


__all__ = [
    "BETA_MIN_DAYS", "BETA_MIN_SIGNALS", "EXTERNAL_EFFECT_BOUNDARY", "FEATURE_FLAG_ID", "FIXED_CLOCK",
    "SAFE_MODEL_CONFIG", "TARGET_MIN_DAYS", "TARGET_MIN_SIGNALS", "ShadowBetaInputError", "artifact_sha256",
    "build_model_beta_gate", "build_shadow_report", "canonical_json_bytes", "evaluate_shadow_beta", "validate_shadow_input",
]
