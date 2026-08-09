"""Frozen S11/P02 evidence-tier and minimum-odds decision gate.

The module evaluates synthetic, deterministic threshold vectors only.  A
passing result is still only a candidate for later platform and risk gates;
it cannot recommend, submit, confirm, or retry a real order.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_UP, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from decimal_math import (
    DECIMAL_PRECISION,
    ODDS_STEP,
    PROBABILITY_STEP,
    NumericContractError,
    decimal_text,
    normalize_friction,
    normalize_odds,
    normalize_probability,
)


CONTRACT_ID = "AC-S11-P02"
REQUIREMENT_ID = "REQ-S11-P02"
STAGE_ID = "S11"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
TIERS_ID = "TIER-S11-P02-EVIDENCE"
VECTORS_ID = "VEC-S11-P02-THRESHOLDS"
REPORT_ID = "RPT-S11-P02-DECISION-GATE"

_ZERO = Decimal("0")
_ONE = Decimal("1")
_STAGE_RANK = {"ALPHA": 0, "BETA": 1, "GA": 2}
_TIER_ORDER = ("E4", "E3", "E2", "E1")
_ADVERSE_SCENARIOS = ("probability_minus", "threshold_plus", "friction_plus", "odds_adverse", "all_adverse")
_CANDIDATE_ACTION = "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES"
_NO_RECOMMENDATION = "NO_RECOMMENDATION"
_CORE_NUMERIC_FIELDS = {
    "authoritative_decimal_precision_digits",
    "binary_float_for_authoritative_decision",
    "money_storage",
    "probability_storage_scale",
    "odds_storage_scale",
    "probability_rounding",
    "odds_rounding",
    "friction_rounding",
    "stake_rounding",
    "independent_implementation_absolute_tolerance",
    "action_must_match_across_implementations",
}
_NUMERIC_DETERMINISM = {
    "authoritative_decimal_precision_digits": 50,
    "money_storage": "INTEGER_CENTS",
    "probability_storage_scale": "1e-9",
    "odds_storage_scale": "1e-6",
    "binary_float_for_authoritative_decision": False,
    "probability_rounding": "DOWN",
    "odds_rounding": "DOWN",
    "friction_rounding": "UP",
    "stake_rounding": "DOWN_TO_PROVIDER_INCREMENT",
    "independent_implementation_absolute_tolerance": "1e-12",
    "action_must_match_across_implementations": True,
    "boundary_perturbation_absolute_probability": "0.0001",
    "boundary_perturbation_absolute_threshold": "0.0001",
    "boundary_perturbation_friction_up": "0.0001",
    "boundary_perturbation_time_adverse_seconds": 2,
    "odds_perturbation": "ONE_PROVIDER_TICK_ADVERSE",
    "unstable_action": "NO_RECOMMENDATION",
}
_VECTOR_IDS = (
    "V01-E4-STABLE-PASS",
    "V02-E4-EXACT-MINIMUM-ODDS-ADVERSE-FLIP",
    "V03-E3-BOUNDARY-STABLE-PASS",
    "V04-E2-BOUNDARY-STABLE-PASS",
    "V05-E1-BOUNDARY-STABLE-PASS",
    "V06-E0-NONPRICE-SOURCES-BELOW-MINIMUM",
    "V07-E4-MODEL-STAGE-BELOW-MINIMUM",
    "V08-E2-DISAGREEMENT-PLUS-POINT-0001",
    "V09-IDENTITY-BELOW-THRESHOLD",
    "V10-FEATURE-COMPLETENESS-BELOW-THRESHOLD",
    "V11-ODDS-ONE-TICK-BELOW-MINIMUM",
    "V12-SOURCE-CONTRACT-FAILS-CLOSED",
)
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "actual_market_or_odds_observed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class DecisionGateError(ValueError):
    """Raised when a S11/P02 gate input is malformed or unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DecisionGateError("%s has an unexpected shape" % label)
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DecisionGateError("%s must be a non-empty string" % label)
    return value


def _sha256_text(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise DecisionGateError("%s must be a lowercase SHA-256" % label)
    return text


def _integer(value: Any, *, label: str, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        maximum_text = " and at most %d" % maximum if maximum is not None else ""
        raise DecisionGateError("%s must be an integer at least %d%s" % (label, minimum, maximum_text))
    return value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise DecisionGateError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DecisionGateError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise DecisionGateError("%s must be finite" % label)
    return parsed


def _quantize(value: Decimal, step: Decimal, *, label: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            return value.quantize(step, rounding=ROUND_UP)
    except InvalidOperation as exc:
        raise DecisionGateError("%s cannot be represented at the required scale" % label) from exc


def _minimum_return(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed < _ONE:
        raise DecisionGateError("%s must be in [0, 1)" % label)
    return _quantize(parsed, PROBABILITY_STEP, label=label)


def _percentage_points(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed <= Decimal("100"):
        raise DecisionGateError("%s must be in [0, 100]" % label)
    return _quantize(parsed, PROBABILITY_STEP, label=label)


def _minimum_acceptable_odds(probability: Decimal, friction: Decimal, minimum_return: Decimal) -> Decimal:
    if probability <= _ZERO:
        raise DecisionGateError("conservative probability cannot be zero")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        raw = (_ONE + minimum_return + friction) / probability
    if raw <= _ONE:
        raise DecisionGateError("minimum acceptable odds must be greater than one")
    return _quantize(raw, ODDS_STEP, label="minimum_acceptable_odds")


def _parameters(parameters: Any) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(parameters, Mapping):
        raise DecisionGateError("parameters must be an object")
    numeric = parameters.get("numeric_determinism")
    coverage = parameters.get("coverage_and_freshness")
    market_model = parameters.get("market_model")
    tiers = parameters.get("evidence_tiers")
    if not all(isinstance(value, Mapping) for value in (numeric, coverage, market_model, tiers)):
        raise DecisionGateError("frozen S11/P02 parameter sections are unavailable")
    if dict(numeric) != _NUMERIC_DETERMINISM:
        raise DecisionGateError("numeric_determinism differs from frozen task-pack values")
    expected_tier_keys = {"E4", "E3", "E2", "E1", "E0"}
    if set(tiers) != expected_tier_keys:
        raise DecisionGateError("evidence_tiers differs from frozen task-pack values")
    return numeric, coverage, market_model, tiers


def _tier_rules(parameters: Any) -> tuple[dict[str, Mapping[str, Any]], Mapping[str, Any]]:
    _, coverage, market_model, tiers = _parameters(parameters)
    required_coverage = {"identity_confidence_min", "required_feature_completeness_min"}
    if not required_coverage <= set(coverage) or "future_leakage_tolerance" not in market_model:
        raise DecisionGateError("common hard-gate parameters are incomplete")
    rules: dict[str, Mapping[str, Any]] = {}
    expected_shapes = {
        "E4": {"independent_price_sources_min", "model_stage_min", "robust_net_expected_return_min", "model_disagreement_pp_max"},
        "E3": {"independent_price_sources_min", "independent_price_sources_max", "model_stage_min", "robust_net_expected_return_min", "model_disagreement_pp_max"},
        "E2": {"independent_price_sources_min", "independent_price_sources_max", "model_stage_min", "robust_net_expected_return_min", "model_disagreement_pp_max"},
        "E1": {"independent_price_sources_min", "independent_price_sources_max", "independent_non_price_sources_min", "model_stage_min", "robust_net_expected_return_min", "model_disagreement_pp_max"},
    }
    for tier in _TIER_ORDER:
        raw = tiers[tier]
        if not isinstance(raw, Mapping) or set(raw) != expected_shapes[tier]:
            raise DecisionGateError("%s evidence-tier shape differs" % tier)
        minimum_stage = raw["model_stage_min"]
        if minimum_stage not in _STAGE_RANK:
            raise DecisionGateError("%s model stage is invalid" % tier)
        price_min = _integer(raw["independent_price_sources_min"], label="%s price minimum" % tier, minimum=1)
        price_max = raw.get("independent_price_sources_max")
        if price_max is not None:
            price_max = _integer(price_max, label="%s price maximum" % tier, minimum=price_min)
        non_price_min = raw.get("independent_non_price_sources_min", 0)
        non_price_min = _integer(non_price_min, label="%s non-price minimum" % tier, minimum=0)
        rules[tier] = {
            "tier": tier,
            "independent_price_sources_min": price_min,
            "independent_price_sources_max": price_max,
            "independent_non_price_sources_min": non_price_min,
            "model_stage_min": minimum_stage,
            "robust_net_expected_return_min": _minimum_return(raw["robust_net_expected_return_min"], label="%s return minimum" % tier),
            "model_disagreement_pp_max": _percentage_points(raw["model_disagreement_pp_max"], label="%s disagreement maximum" % tier),
        }
    if tiers["E0"] != {"action": _NO_RECOMMENDATION}:
        raise DecisionGateError("E0 action differs from frozen task-pack value")
    common = {
        "identity_confidence_min": normalize_probability(coverage["identity_confidence_min"], label="identity_confidence_min"),
        "required_feature_completeness_min": normalize_probability(coverage["required_feature_completeness_min"], label="required_feature_completeness_min"),
        "future_leakage_tolerance": _integer(market_model["future_leakage_tolerance"], label="future_leakage_tolerance", minimum=0),
    }
    return rules, common


def build_evidence_tiers(parameters: Any) -> dict[str, Any]:
    """Materialize the frozen evidence-tier contract from canonical parameters."""

    rules, common = _tier_rules(parameters)
    tier_rows = []
    for tier in _TIER_ORDER:
        rule = rules[tier]
        tier_rows.append(
            {
                "tier": tier,
                "independent_price_sources_min": rule["independent_price_sources_min"],
                "independent_price_sources_max": rule["independent_price_sources_max"],
                "independent_non_price_sources_min": rule["independent_non_price_sources_min"],
                "model_stage_min": rule["model_stage_min"],
                "robust_net_expected_return_min": decimal_text(rule["robust_net_expected_return_min"]),
                "model_disagreement_pp_max": decimal_text(rule["model_disagreement_pp_max"]),
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S11-P02-01",
        "tiers_id": TIERS_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "model_stage_order": ["ALPHA", "BETA", "GA"],
        "tiers": tier_rows,
        "e0_action": _NO_RECOMMENDATION,
        "common_hard_gates": {
            "identity_confidence_min": decimal_text(common["identity_confidence_min"]),
            "required_feature_completeness_min": decimal_text(common["required_feature_completeness_min"]),
            "future_leakage_tolerance": common["future_leakage_tolerance"],
            "quote_must_be_usable": True,
            "settlement_rules_must_be_clear": True,
            "source_contract_must_pass": True,
            "adverse_stability_must_pass": True,
        },
        "decision": "EVIDENCE_TIER_AND_MINIMUM_ODDS_RULES_READY",
        "next": "S11/P02_THRESHOLD_REPLAY_REQUIRED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }


def validate_evidence_tiers(value: Any, parameters: Any) -> Mapping[str, Any]:
    expected = build_evidence_tiers(parameters)
    if value != expected:
        raise DecisionGateError("evidence tiers artifact is not the exact frozen replay")
    return expected


def _expected_shape(value: Any) -> Mapping[str, Any]:
    expected = _strict_object(
        value,
        {"tier", "base_action", "action", "reason_code", "minimum_acceptable_odds", "adverse_flip_dimensions"},
        label="vector expected",
    )
    if expected["tier"] not in {*_TIER_ORDER, "E0"}:
        raise DecisionGateError("expected tier is invalid")
    if expected["base_action"] not in {_CANDIDATE_ACTION, _NO_RECOMMENDATION} or expected["action"] not in {_CANDIDATE_ACTION, _NO_RECOMMENDATION}:
        raise DecisionGateError("expected action is invalid")
    _text(expected["reason_code"], label="expected reason_code")
    odds = expected["minimum_acceptable_odds"]
    if odds is not None:
        try:
            normalize_odds(odds, label="expected minimum_acceptable_odds")
        except NumericContractError as exc:
            raise DecisionGateError("expected minimum_acceptable_odds is invalid: %s" % exc) from exc
    flips = expected["adverse_flip_dimensions"]
    if not isinstance(flips, list) or flips != sorted(set(flips), key=_ADVERSE_SCENARIOS.index) or any(item not in _ADVERSE_SCENARIOS for item in flips):
        raise DecisionGateError("expected adverse_flip_dimensions is invalid")
    return expected


def validate_vector(value: Any) -> Mapping[str, Any]:
    vector = _strict_object(
        value,
        {
            "vector_id",
            "independent_price_sources",
            "independent_non_price_sources",
            "model_stage",
            "model_disagreement_pp",
            "identity_confidence",
            "required_feature_completeness",
            "quote_usable",
            "settlement_rules_clear",
            "source_contract_pass",
            "future_leakage_count",
            "stability_gate_pass",
            "conservative_probability",
            "effective_friction",
            "observed_odds",
            "expected",
        },
        label="threshold vector",
    )
    _text(vector["vector_id"], label="vector_id")
    _integer(vector["independent_price_sources"], label="independent_price_sources", minimum=0)
    _integer(vector["independent_non_price_sources"], label="independent_non_price_sources", minimum=0)
    if vector["model_stage"] not in _STAGE_RANK:
        raise DecisionGateError("model_stage is invalid")
    try:
        _percentage_points(vector["model_disagreement_pp"], label="model_disagreement_pp")
        normalize_probability(vector["identity_confidence"], label="identity_confidence")
        normalize_probability(vector["required_feature_completeness"], label="required_feature_completeness")
        normalize_probability(vector["conservative_probability"], label="conservative_probability")
        normalize_friction(vector["effective_friction"], label="effective_friction")
        normalize_odds(vector["observed_odds"], label="observed_odds")
    except NumericContractError as exc:
        raise DecisionGateError("threshold vector violates fixed-point contract: %s" % exc) from exc
    for field in ("quote_usable", "settlement_rules_clear", "source_contract_pass", "stability_gate_pass"):
        if type(vector[field]) is not bool:
            raise DecisionGateError("%s must be boolean" % field)
    _integer(vector["future_leakage_count"], label="future_leakage_count", minimum=0)
    _expected_shape(vector["expected"])
    return vector


def validate_registry(registry: Any, tiers: Any, parameters: Any) -> Mapping[str, Any]:
    validate_evidence_tiers(tiers, parameters)
    row = _strict_object(
        registry,
        {
            "schema_version",
            "artifact_id",
            "vectors_id",
            "contract_id",
            "requirement_id",
            "stage_id",
            "phase_id",
            "product_version",
            "fixed_clock",
            "input_mode",
            "evidence_tiers_sha256",
            "vectors",
            "expected_report_sha256",
        },
        label="threshold vectors registry",
    )
    identity_ok = (
        row["schema_version"] == "1.0.0"
        and row["artifact_id"] == "ART-S11-P02-02"
        and row["vectors_id"] == VECTORS_ID
        and row["contract_id"] == CONTRACT_ID
        and row["requirement_id"] == REQUIREMENT_ID
        and row["stage_id"] == STAGE_ID
        and row["phase_id"] == PHASE_ID
        and row["product_version"] == VERSION
        and row["fixed_clock"] == FIXED_CLOCK
        and row["input_mode"] == INPUT_MODE
    )
    if not identity_ok:
        raise DecisionGateError("threshold vectors registry identity is invalid")
    if _sha256_text(row["evidence_tiers_sha256"], label="evidence_tiers_sha256") != artifact_sha256(tiers):
        raise DecisionGateError("threshold vectors are not bound to exact evidence tiers")
    _sha256_text(row["expected_report_sha256"], label="expected_report_sha256")
    vectors = row["vectors"]
    if not isinstance(vectors, list) or [item.get("vector_id") if isinstance(item, Mapping) else None for item in vectors] != list(_VECTOR_IDS):
        raise DecisionGateError("threshold vectors must be the exact frozen ordered set")
    for vector in vectors:
        validate_vector(vector)
    return row


def _normalized_inputs(vector: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "independent_price_sources": _integer(vector["independent_price_sources"], label="independent_price_sources", minimum=0),
        "independent_non_price_sources": _integer(vector["independent_non_price_sources"], label="independent_non_price_sources", minimum=0),
        "model_stage": vector["model_stage"],
        "model_disagreement_pp": _percentage_points(vector["model_disagreement_pp"], label="model_disagreement_pp"),
        "identity_confidence": normalize_probability(vector["identity_confidence"], label="identity_confidence"),
        "required_feature_completeness": normalize_probability(vector["required_feature_completeness"], label="required_feature_completeness"),
        "quote_usable": vector["quote_usable"],
        "settlement_rules_clear": vector["settlement_rules_clear"],
        "source_contract_pass": vector["source_contract_pass"],
        "future_leakage_count": _integer(vector["future_leakage_count"], label="future_leakage_count", minimum=0),
        "stability_gate_pass": vector["stability_gate_pass"],
        "conservative_probability": normalize_probability(vector["conservative_probability"], label="conservative_probability"),
        "effective_friction": normalize_friction(vector["effective_friction"], label="effective_friction"),
        "observed_odds": normalize_odds(vector["observed_odds"], label="observed_odds"),
    }


def _common_failure(inputs: Mapping[str, Any], common: Mapping[str, Any]) -> str | None:
    if inputs["identity_confidence"] < common["identity_confidence_min"]:
        return "IDENTITY_CONFIDENCE_BELOW_THRESHOLD"
    if inputs["required_feature_completeness"] < common["required_feature_completeness_min"]:
        return "REQUIRED_FEATURE_COMPLETENESS_BELOW_THRESHOLD"
    if not inputs["quote_usable"]:
        return "QUOTE_NOT_USABLE"
    if not inputs["settlement_rules_clear"]:
        return "SETTLEMENT_RULES_UNCLEAR"
    if not inputs["source_contract_pass"]:
        return "SOURCE_CONTRACT_NOT_PASSED"
    if inputs["future_leakage_count"] > common["future_leakage_tolerance"]:
        return "FUTURE_LEAKAGE_DETECTED"
    if not inputs["stability_gate_pass"]:
        return "UPSTREAM_STABILITY_GATE_NOT_PASSED"
    return None


def _select_tier(inputs: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]]) -> str:
    for tier in _TIER_ORDER:
        rule = rules[tier]
        price_count = inputs["independent_price_sources"]
        maximum = rule["independent_price_sources_max"]
        if price_count < rule["independent_price_sources_min"] or (maximum is not None and price_count > maximum):
            continue
        if inputs["independent_non_price_sources"] < rule["independent_non_price_sources_min"]:
            continue
        if _STAGE_RANK[inputs["model_stage"]] < _STAGE_RANK[rule["model_stage_min"]]:
            continue
        if inputs["model_disagreement_pp"] > rule["model_disagreement_pp_max"]:
            continue
        return tier
    return "E0"


def _classify(inputs: Mapping[str, Any], rules: Mapping[str, Mapping[str, Any]], common: Mapping[str, Any], *, threshold_adjustment: Decimal) -> Mapping[str, Any]:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        net_return = (inputs["conservative_probability"] * inputs["observed_odds"]) - _ONE - inputs["effective_friction"]
    common_reason = _common_failure(inputs, common)
    if common_reason is not None:
        return {
            "tier": "E0",
            "action": _NO_RECOMMENDATION,
            "reason_code": common_reason,
            "robust_net_expected_return": decimal_text(net_return),
            "minimum_robust_net_expected_return": None,
            "minimum_acceptable_odds": None,
        }
    tier = _select_tier(inputs, rules)
    if tier == "E0":
        return {
            "tier": "E0",
            "action": _NO_RECOMMENDATION,
            "reason_code": "EVIDENCE_TIER_E0",
            "robust_net_expected_return": decimal_text(net_return),
            "minimum_robust_net_expected_return": None,
            "minimum_acceptable_odds": None,
        }
    minimum_return = rules[tier]["robust_net_expected_return_min"] + threshold_adjustment
    minimum_odds = _minimum_acceptable_odds(inputs["conservative_probability"], inputs["effective_friction"], minimum_return)
    if inputs["observed_odds"] < minimum_odds:
        action = _NO_RECOMMENDATION
        reason_code = "ODDS_BELOW_MINIMUM"
    elif net_return < minimum_return:
        action = _NO_RECOMMENDATION
        reason_code = "ROBUST_NET_EXPECTED_RETURN_BELOW_TIER_MINIMUM"
    else:
        action = _CANDIDATE_ACTION
        reason_code = "EVIDENCE_AND_PRICE_GATES_PASS_PENDING_PLATFORM_AND_RISK"
    return {
        "tier": tier,
        "action": action,
        "reason_code": reason_code,
        "robust_net_expected_return": decimal_text(net_return),
        "minimum_robust_net_expected_return": decimal_text(minimum_return),
        "minimum_acceptable_odds": decimal_text(minimum_odds),
    }


def _scenario_inputs(base: Mapping[str, Any], scenario: str, numeric: Mapping[str, Any]) -> tuple[Mapping[str, Any], Decimal]:
    probability_delta = _decimal(numeric["boundary_perturbation_absolute_probability"], label="boundary probability perturbation")
    threshold_delta = _decimal(numeric["boundary_perturbation_absolute_threshold"], label="boundary threshold perturbation")
    friction_delta = _decimal(numeric["boundary_perturbation_friction_up"], label="boundary friction perturbation")
    result = dict(base)
    threshold_adjustment = _ZERO
    if scenario in {"probability_minus", "all_adverse"}:
        result["conservative_probability"] = max(_ZERO, result["conservative_probability"] - probability_delta)
    if scenario in {"threshold_plus", "all_adverse"}:
        threshold_adjustment = threshold_delta
    if scenario in {"friction_plus", "all_adverse"}:
        result["effective_friction"] = result["effective_friction"] + friction_delta
    if scenario in {"odds_adverse", "all_adverse"}:
        result["observed_odds"] = result["observed_odds"] - ODDS_STEP
    if result["conservative_probability"] <= _ZERO or result["effective_friction"] >= _ONE or result["observed_odds"] <= _ONE:
        raise DecisionGateError("adverse scenario leaves the executable numeric domain")
    return (
        {
            **result,
            "conservative_probability": normalize_probability(decimal_text(result["conservative_probability"]), label="scenario probability"),
            "effective_friction": normalize_friction(decimal_text(result["effective_friction"]), label="scenario friction"),
            "observed_odds": normalize_odds(decimal_text(result["observed_odds"]), label="scenario odds"),
        },
        threshold_adjustment,
    )


def evaluate_vector(vector: Any, tiers: Any, parameters: Any) -> Mapping[str, Any]:
    """Replay one frozen candidate across every P02 adverse threshold scenario."""

    row = validate_vector(vector)
    numeric, _, _, _ = _parameters(parameters)
    validate_evidence_tiers(tiers, parameters)
    rules, common = _tier_rules(parameters)
    base_inputs = _normalized_inputs(row)
    baseline = _classify(base_inputs, rules, common, threshold_adjustment=_ZERO)
    scenarios = {}
    for scenario in _ADVERSE_SCENARIOS:
        scenario_inputs, adjustment = _scenario_inputs(base_inputs, scenario, numeric)
        scenarios[scenario] = _classify(scenario_inputs, rules, common, threshold_adjustment=adjustment)
    adverse_flips = [
        scenario
        for scenario in _ADVERSE_SCENARIOS
        if baseline["action"] == _CANDIDATE_ACTION and scenarios[scenario]["action"] != _CANDIDATE_ACTION
    ]
    if baseline["action"] != _CANDIDATE_ACTION:
        action = _NO_RECOMMENDATION
        reason_code = baseline["reason_code"]
    elif adverse_flips:
        action = _NO_RECOMMENDATION
        reason_code = "ADVERSE_STABILITY_FLIP"
    else:
        action = _CANDIDATE_ACTION
        reason_code = "ALL_EVIDENCE_AND_PRICE_GATES_STABLE"
    expected = row["expected"]
    expected_matches = {
        "tier": expected["tier"] == baseline["tier"],
        "base_action": expected["base_action"] == baseline["action"],
        "action": expected["action"] == action,
        "reason_code": expected["reason_code"] == reason_code,
        "minimum_acceptable_odds": expected["minimum_acceptable_odds"] == baseline["minimum_acceptable_odds"],
        "adverse_flip_dimensions": expected["adverse_flip_dimensions"] == adverse_flips,
    }
    return {
        "vector_id": row["vector_id"],
        "baseline": baseline,
        "scenarios": scenarios,
        "adverse_flip_dimensions": adverse_flips,
        "action": action,
        "reason_code": reason_code,
        "expected": expected,
        "expected_matches": expected_matches,
        "all_expected_matches": all(expected_matches.values()),
    }


def report_sha256(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_sha256", None)
    return artifact_sha256(payload)


def registry_input_sha256(registry: Mapping[str, Any]) -> str:
    """Hash immutable vector inputs without their expected replay assertion."""

    payload = dict(registry)
    payload.pop("expected_report_sha256", None)
    return artifact_sha256(payload)


def build_report(tiers: Any, registry: Any, parameters: Any) -> Mapping[str, Any]:
    row = validate_registry(registry, tiers, parameters)
    results = [evaluate_vector(vector, tiers, parameters) for vector in row["vectors"]]
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "report_id": REPORT_ID,
        "tiers_id": TIERS_ID,
        "vectors_id": VECTORS_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "evidence_tiers_sha256": artifact_sha256(tiers),
        "threshold_vectors_input_sha256": registry_input_sha256(row),
        "results": results,
        "summary": {
            "vector_count": len(results),
            "expected_match_count": sum(result["all_expected_matches"] for result in results),
            "candidate_pending_platform_and_risk_count": sum(result["action"] == _CANDIDATE_ACTION for result in results),
            "no_recommendation_count": sum(result["action"] == _NO_RECOMMENDATION for result in results),
            "unique_final_reason_code_per_vector": all(isinstance(result["reason_code"], str) and bool(result["reason_code"]) for result in results),
        },
        "decision": "EVIDENCE_TIER_AND_MINIMUM_ODDS_GATE_READY_DOWNSTREAM_PLATFORM_AND_RISK_REQUIRED",
        "next": "S11/P03_READY_NOT_STARTED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    report["report_sha256"] = report_sha256(report)
    return report


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay frozen ABD S11/P02 evidence-tier decision vectors")
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--tiers", required=True)
    parser.add_argument("--vectors", required=True)
    args = parser.parse_args()
    parameters = _load_json(Path(args.parameters))
    tiers = _load_json(Path(args.tiers))
    vectors = _load_json(Path(args.vectors))
    report = build_report(tiers, vectors, parameters)
    print(
        json.dumps(
            {
                "contract_id": CONTRACT_ID,
                "status": "PASS" if report["summary"]["expected_match_count"] == report["summary"]["vector_count"] else "FAIL",
                "report_sha256": report["report_sha256"],
                "next": report["next"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["summary"]["expected_match_count"] == report["summary"]["vector_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
