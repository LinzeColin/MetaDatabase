"""Frozen constrained-Kelly and correlated-portfolio gate for ABD S11/P04.

This module evaluates only deterministic synthetic vectors.  It implements the
task-pack Kelly fraction, stage coefficients, exposure caps, loss/drawdown
controls, and one-in-ten-thousand adverse checks.  It never reads a market or
account, sends an order, waits for real time, or makes a return claim.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from decimal_math import (
    DECIMAL_PRECISION,
    FRACTION_STEP,
    ODDS_STEP,
    PROBABILITY_STEP,
    NumericContractError,
    decimal_text,
    normalize_fraction,
    normalize_odds,
    normalize_probability,
)


CONTRACT_ID = "AC-S11-P04"
REQUIREMENT_ID = "REQ-S11-P04"
STAGE_ID = "S11"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
GRAPH_ID = "GRAPH-S11-P04-CORRELATION"
VECTORS_ID = "VEC-S11-P04-CONSTRAINED-KELLY"
REPORT_ID = "RPT-S11-P04-CONSTRAINED-KELLY"

_ZERO = Decimal("0")
_ONE = Decimal("1")
_CANDIDATE_ACTION = "RISK_GATED_SYNTHETIC_CANDIDATE_PENDING_FINAL_ADVICE"
_NO_RECOMMENDATION = "NO_RECOMMENDATION"
_UPSTREAM_ROUTE_ACTION = "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES"
_ADVERSE_SCENARIOS = (
    "probability_minus",
    "risk_threshold_tightened",
    "odds_adverse",
    "all_adverse",
)
_VECTOR_IDS = (
    "K01-GA-P03-ROUTE-STABLE",
    "K02-BETA-SINGLE-TICKET-CAP",
    "K03-ALPHA-COEFFICIENT-ZERO",
    "K04-EVENT-CAP-REMAINING-CAPACITY",
    "K05-CLUSTER-CAP-REMAINING-CAPACITY",
    "K06-OPEN-CAP-REMAINING-CAPACITY",
    "K07-BELOW-PROVIDER-MINIMUM-NO-UPROUND",
    "K08-DAILY-LOSS-SOFT-STOP",
    "K09-STRATEGY-SLICE-DRAWDOWN-KILL",
    "K10-LEDGER-DIFFERENCE-HARD-STOP",
    "K11-RISK-THRESHOLD-POINT-0001-FLIP",
    "K12-TARGET-SHORTFALL-DIAGNOSTIC-ONLY",
)
_REQUIRED_CLUSTER_CATEGORIES = (
    "same_event_different_markets",
    "same_participant_or_team_time_window",
    "same_league_weather_or_lineup_shock",
    "futures_and_single_event_outcome",
    "same_source_anomaly",
    "shared_model_feature_or_data_failure",
)
_RISK_PARAMETERS = {
    "kelly_fraction_alpha": "0.00",
    "kelly_fraction_beta": "0.20",
    "kelly_fraction_ga": "0.25",
    "single_ticket_cap_beta": "0.015",
    "single_ticket_cap_ga": "0.020",
    "event_cap": "0.050",
    "correlation_cluster_cap": "0.050",
    "total_open_exposure_cap": "0.150",
    "daily_loss_soft_stop": "0.030",
    "seven_day_drawdown_diagnostic": "0.075",
    "strategy_slice_kill_drawdown": "0.100",
    "absolute_disaster_line": "0.700",
    "chase_loss_prohibited": True,
    "target_shortfall_may_relax_gate": False,
}
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


class RiskEngineError(ValueError):
    """Raised when a constrained-Kelly input is malformed or unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RiskEngineError("%s has an unexpected shape" % label)
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RiskEngineError("%s must be a non-empty string" % label)
    return value


def _sha256_text(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise RiskEngineError("%s must be a lowercase SHA-256" % label)
    return text


def _integer(value: Any, *, label: str, minimum: int, allow_negative: bool = False) -> int:
    if type(value) is not int or (not allow_negative and value < minimum):
        raise RiskEngineError("%s must be an integer%s" % (label, "" if allow_negative else " at least %d" % minimum))
    return value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise RiskEngineError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RiskEngineError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise RiskEngineError("%s must be finite" % label)
    return parsed


def _quantize_down(value: Decimal, step: Decimal, *, label: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            return value.quantize(step, rounding=ROUND_DOWN)
    except InvalidOperation as exc:
        raise RiskEngineError("%s cannot be represented at the required scale" % label) from exc


def _risk_fraction(value: Any, *, label: str) -> Decimal:
    try:
        return normalize_fraction(value, label=label)
    except NumericContractError as exc:
        raise RiskEngineError("%s is not a valid risk fraction: %s" % (label, exc)) from exc


def _risk_policy(parameters: Any) -> Mapping[str, Any]:
    if not isinstance(parameters, Mapping) or parameters.get("risk") != _RISK_PARAMETERS:
        raise RiskEngineError("risk parameters differ from the frozen task-pack values")
    numeric = parameters.get("numeric_determinism")
    if not isinstance(numeric, Mapping) or numeric.get("authoritative_decimal_precision_digits") != DECIMAL_PRECISION:
        raise RiskEngineError("numeric determinism parameters are unavailable")
    return {
        "kelly_coefficients": {
            "ALPHA": _risk_fraction(_RISK_PARAMETERS["kelly_fraction_alpha"], label="kelly_fraction_alpha"),
            "BETA": _risk_fraction(_RISK_PARAMETERS["kelly_fraction_beta"], label="kelly_fraction_beta"),
            "GA": _risk_fraction(_RISK_PARAMETERS["kelly_fraction_ga"], label="kelly_fraction_ga"),
        },
        "single_ticket_caps": {
            "ALPHA": _ZERO,
            "BETA": _risk_fraction(_RISK_PARAMETERS["single_ticket_cap_beta"], label="single_ticket_cap_beta"),
            "GA": _risk_fraction(_RISK_PARAMETERS["single_ticket_cap_ga"], label="single_ticket_cap_ga"),
        },
        "event_cap": _risk_fraction(_RISK_PARAMETERS["event_cap"], label="event_cap"),
        "cluster_cap": _risk_fraction(_RISK_PARAMETERS["correlation_cluster_cap"], label="correlation_cluster_cap"),
        "open_cap": _risk_fraction(_RISK_PARAMETERS["total_open_exposure_cap"], label="total_open_exposure_cap"),
        "daily_loss_soft_stop": _risk_fraction(_RISK_PARAMETERS["daily_loss_soft_stop"], label="daily_loss_soft_stop"),
        "seven_day_drawdown_diagnostic": _risk_fraction(_RISK_PARAMETERS["seven_day_drawdown_diagnostic"], label="seven_day_drawdown_diagnostic"),
        "strategy_slice_kill_drawdown": _risk_fraction(_RISK_PARAMETERS["strategy_slice_kill_drawdown"], label="strategy_slice_kill_drawdown"),
        "absolute_disaster_line": _risk_fraction(_RISK_PARAMETERS["absolute_disaster_line"], label="absolute_disaster_line"),
    }


def build_correlation_graph(parameters: Any) -> dict[str, Any]:
    """Materialize the frozen correlation policy from canonical risk parameters."""

    policy = _risk_policy(parameters)
    clusters = [
        {
            "cluster_id": "C01-SAME-EVENT-MARKETS",
            "category": "same_event_different_markets",
            "cap_fraction": decimal_text(policy["cluster_cap"]),
        },
        {
            "cluster_id": "C02-PARTICIPANT-OR-TEAM-WINDOW",
            "category": "same_participant_or_team_time_window",
            "cap_fraction": decimal_text(policy["cluster_cap"]),
        },
        {
            "cluster_id": "C03-LEAGUE-WEATHER-LINEUP",
            "category": "same_league_weather_or_lineup_shock",
            "cap_fraction": decimal_text(policy["cluster_cap"]),
        },
        {
            "cluster_id": "C04-FUTURES-SINGLE-EVENT",
            "category": "futures_and_single_event_outcome",
            "cap_fraction": decimal_text(policy["cluster_cap"]),
        },
        {
            "cluster_id": "C05-SOURCE-ANOMALY",
            "category": "same_source_anomaly",
            "cap_fraction": decimal_text(policy["cluster_cap"]),
        },
        {
            "cluster_id": "C06-SHARED-MODEL-OR-DATA",
            "category": "shared_model_feature_or_data_failure",
            "cap_fraction": decimal_text(policy["cluster_cap"]),
        },
    ]
    return {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S11-P04-01",
        "graph_id": GRAPH_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "required_cluster_categories": list(_REQUIRED_CLUSTER_CATEGORIES),
        "clusters": clusters,
        "hard_caps": {
            "single_ticket_cap_by_stage": {stage: decimal_text(value) for stage, value in policy["single_ticket_caps"].items()},
            "event_cap": decimal_text(policy["event_cap"]),
            "correlation_cluster_cap": decimal_text(policy["cluster_cap"]),
            "total_open_exposure_cap": decimal_text(policy["open_cap"]),
        },
        "risk_controls": {
            "daily_loss_soft_stop": decimal_text(policy["daily_loss_soft_stop"]),
            "seven_day_drawdown_diagnostic": decimal_text(policy["seven_day_drawdown_diagnostic"]),
            "strategy_slice_kill_drawdown": decimal_text(policy["strategy_slice_kill_drawdown"]),
            "absolute_disaster_line": decimal_text(policy["absolute_disaster_line"]),
            "chase_loss_prohibited": True,
            "target_shortfall_may_relax_gate": False,
        },
        "decision": "CONSTRAINED_KELLY_CORRELATION_POLICY_READY",
        "next": "S11/P04_RISK_REPLAY_REQUIRED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }


def validate_correlation_graph(value: Any, parameters: Any) -> Mapping[str, Any]:
    expected = build_correlation_graph(parameters)
    if value != expected:
        raise RiskEngineError("correlation graph is not the exact frozen replay")
    return expected


def _expected_shape(value: Any) -> Mapping[str, Any]:
    expected = _strict_object(
        value,
        {"baseline_action", "action", "reason_code", "stake_cents", "adverse_flip_dimensions"},
        label="vector expected",
    )
    if expected["baseline_action"] not in {_CANDIDATE_ACTION, _NO_RECOMMENDATION} or expected["action"] not in {_CANDIDATE_ACTION, _NO_RECOMMENDATION}:
        raise RiskEngineError("expected action is invalid")
    _text(expected["reason_code"], label="expected reason_code")
    _integer(expected["stake_cents"], label="expected stake_cents", minimum=0)
    flips = expected["adverse_flip_dimensions"]
    if not isinstance(flips, list) or flips != sorted(set(flips), key=_ADVERSE_SCENARIOS.index) or any(item not in _ADVERSE_SCENARIOS for item in flips):
        raise RiskEngineError("expected adverse_flip_dimensions is invalid")
    return expected


def validate_vector(value: Any, graph: Mapping[str, Any]) -> Mapping[str, Any]:
    row = _strict_object(
        value,
        {
            "vector_id",
            "upstream_route_vector_id",
            "upstream_route_action",
            "upstream_provider_id",
            "model_stage",
            "conservative_probability",
            "odds",
            "bankroll_cents",
            "stake_increment_cents",
            "minimum_stake_cents",
            "event_id",
            "correlation_cluster_id",
            "existing_event_exposure_cents",
            "existing_cluster_exposure_cents",
            "existing_open_exposure_cents",
            "daily_loss_fraction",
            "seven_day_drawdown_fraction",
            "strategy_slice_drawdown_fraction",
            "absolute_drawdown_fraction",
            "ledger_difference_cents",
            "target_shortfall",
            "expected",
        },
        label="risk vector",
    )
    _text(row["vector_id"], label="vector_id")
    _text(row["upstream_route_vector_id"], label="upstream_route_vector_id")
    _text(row["upstream_provider_id"], label="upstream_provider_id")
    if row["upstream_route_action"] != _UPSTREAM_ROUTE_ACTION:
        raise RiskEngineError("upstream_route_action must be the frozen P03 pending-risk action")
    if row["model_stage"] not in {"ALPHA", "BETA", "GA"}:
        raise RiskEngineError("model_stage is invalid")
    try:
        normalize_probability(row["conservative_probability"], label="conservative_probability")
        normalize_odds(row["odds"], label="odds")
    except NumericContractError as exc:
        raise RiskEngineError("risk vector fixed-point input is invalid: %s" % exc) from exc
    _integer(row["bankroll_cents"], label="bankroll_cents", minimum=1)
    _integer(row["stake_increment_cents"], label="stake_increment_cents", minimum=1)
    _integer(row["minimum_stake_cents"], label="minimum_stake_cents", minimum=1)
    _text(row["event_id"], label="event_id")
    cluster_ids = {item["cluster_id"] for item in graph["clusters"]}
    if row["correlation_cluster_id"] not in cluster_ids:
        raise RiskEngineError("correlation_cluster_id is unknown")
    for field in ("existing_event_exposure_cents", "existing_cluster_exposure_cents", "existing_open_exposure_cents"):
        _integer(row[field], label=field, minimum=0)
    for field in ("daily_loss_fraction", "seven_day_drawdown_fraction", "strategy_slice_drawdown_fraction", "absolute_drawdown_fraction"):
        _risk_fraction(row[field], label=field)
    _integer(row["ledger_difference_cents"], label="ledger_difference_cents", minimum=0, allow_negative=True)
    if type(row["target_shortfall"]) is not bool:
        raise RiskEngineError("target_shortfall must be boolean")
    _expected_shape(row["expected"])
    return row


def validate_registry(registry: Any, graph: Any, parameters: Any) -> Mapping[str, Any]:
    expected_graph = validate_correlation_graph(graph, parameters)
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
            "correlation_graph_sha256",
            "numeric_determinism",
            "vectors",
            "expected_report_sha256",
        },
        label="risk vectors registry",
    )
    identity_ok = (
        row["schema_version"] == "1.0.0"
        and row["artifact_id"] == "ART-S11-P04-02"
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
        raise RiskEngineError("risk vectors registry identity is invalid")
    if row["correlation_graph_sha256"] != artifact_sha256(expected_graph):
        raise RiskEngineError("risk vectors do not bind the frozen correlation graph")
    if row["numeric_determinism"] != parameters.get("numeric_determinism"):
        raise RiskEngineError("risk vectors numeric determinism differs from canonical parameters")
    _sha256_text(row["expected_report_sha256"], label="expected_report_sha256")
    vectors = row["vectors"]
    if not isinstance(vectors, list) or [item.get("vector_id") if isinstance(item, Mapping) else None for item in vectors] != list(_VECTOR_IDS):
        raise RiskEngineError("risk vectors must be the exact frozen ordered set")
    for vector in vectors:
        validate_vector(vector, expected_graph)
    return row


def _normalized_inputs(vector: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        return {
            "vector_id": vector["vector_id"],
            "upstream_route_vector_id": vector["upstream_route_vector_id"],
            "upstream_route_action": vector["upstream_route_action"],
            "upstream_provider_id": vector["upstream_provider_id"],
            "model_stage": vector["model_stage"],
            "conservative_probability": normalize_probability(vector["conservative_probability"], label="conservative_probability"),
            "odds": normalize_odds(vector["odds"], label="odds"),
            "bankroll_cents": vector["bankroll_cents"],
            "stake_increment_cents": vector["stake_increment_cents"],
            "minimum_stake_cents": vector["minimum_stake_cents"],
            "event_id": vector["event_id"],
            "correlation_cluster_id": vector["correlation_cluster_id"],
            "existing_event_exposure_cents": vector["existing_event_exposure_cents"],
            "existing_cluster_exposure_cents": vector["existing_cluster_exposure_cents"],
            "existing_open_exposure_cents": vector["existing_open_exposure_cents"],
            "daily_loss_fraction": _risk_fraction(vector["daily_loss_fraction"], label="daily_loss_fraction"),
            "seven_day_drawdown_fraction": _risk_fraction(vector["seven_day_drawdown_fraction"], label="seven_day_drawdown_fraction"),
            "strategy_slice_drawdown_fraction": _risk_fraction(vector["strategy_slice_drawdown_fraction"], label="strategy_slice_drawdown_fraction"),
            "absolute_drawdown_fraction": _risk_fraction(vector["absolute_drawdown_fraction"], label="absolute_drawdown_fraction"),
            "ledger_difference_cents": vector["ledger_difference_cents"],
            "target_shortfall": vector["target_shortfall"],
        }
    except NumericContractError as exc:
        raise RiskEngineError("cannot normalize risk vector: %s" % exc) from exc


def _remaining_fraction(cap: Decimal, exposure_cents: int, bankroll_cents: int) -> Decimal:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        exposure_fraction = Decimal(exposure_cents) / Decimal(bankroll_cents)
        return max(_ZERO, cap - exposure_fraction)


def _round_stake_cents(raw_cents: Decimal, increment_cents: int) -> int:
    rounded = int(raw_cents.to_integral_value(rounding=ROUND_DOWN))
    return max(0, (rounded // increment_cents) * increment_cents)


def _tighter(value: Decimal, adjustment: Decimal) -> Decimal:
    return max(_ZERO, value - adjustment)


def _evaluate(inputs: Mapping[str, Any], policy: Mapping[str, Any], *, threshold_adjustment: Decimal) -> Mapping[str, Any]:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        stage = inputs["model_stage"]
        bankroll = inputs["bankroll_cents"]
        coefficient = policy["kelly_coefficients"][stage]
        single_cap = _tighter(policy["single_ticket_caps"][stage], threshold_adjustment)
        event_cap = _tighter(policy["event_cap"], threshold_adjustment)
        cluster_cap = _tighter(policy["cluster_cap"], threshold_adjustment)
        open_cap = _tighter(policy["open_cap"], threshold_adjustment)
        daily_loss_limit = _tighter(policy["daily_loss_soft_stop"], threshold_adjustment)
        diagnostic_limit = _tighter(policy["seven_day_drawdown_diagnostic"], threshold_adjustment)
        strategy_limit = _tighter(policy["strategy_slice_kill_drawdown"], threshold_adjustment)
        disaster_limit = _tighter(policy["absolute_disaster_line"], threshold_adjustment)
        probability = inputs["conservative_probability"]
        odds = inputs["odds"]
        full_kelly = max(_ZERO, (probability * odds - _ONE) / (odds - _ONE))
        scaled_kelly = coefficient * full_kelly
        event_remaining = _remaining_fraction(event_cap, inputs["existing_event_exposure_cents"], bankroll)
        cluster_remaining = _remaining_fraction(cluster_cap, inputs["existing_cluster_exposure_cents"], bankroll)
        open_remaining = _remaining_fraction(open_cap, inputs["existing_open_exposure_cents"], bankroll)
        effective_fraction = _quantize_down(min(scaled_kelly, single_cap, event_remaining, cluster_remaining, open_remaining), FRACTION_STEP, label="effective_fraction")
        raw_stake_cents = Decimal(bankroll) * effective_fraction
        stake_cents = _round_stake_cents(raw_stake_cents, inputs["stake_increment_cents"])

    diagnostics: list[str] = []
    if inputs["target_shortfall"]:
        diagnostics.append("TARGET_SHORTFALL_DIAGNOSTIC_ONLY_NO_GATE_RELAXATION")
    if inputs["upstream_route_action"] != _UPSTREAM_ROUTE_ACTION:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "UPSTREAM_PLATFORM_ROUTE_GATE_NOT_PASSED", 0
    elif inputs["ledger_difference_cents"] != 0:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "LEDGER_DIFFERENCE_HARD_STOP", 0
    elif inputs["absolute_drawdown_fraction"] >= disaster_limit:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "ABSOLUTE_DISASTER_LINE_HARD_STOP", 0
    elif inputs["strategy_slice_drawdown_fraction"] >= strategy_limit:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "STRATEGY_SLICE_DRAWDOWN_KILL", 0
    elif inputs["daily_loss_fraction"] >= daily_loss_limit:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "DAILY_LOSS_SOFT_STOP", 0
    elif inputs["seven_day_drawdown_fraction"] >= diagnostic_limit:
        diagnostics.append("SEVEN_DAY_DRAWDOWN_DIAGNOSTIC_REDUCE_SCOPE_NO_PARAMETER_RELAXATION")
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "SEVEN_DAY_DRAWDOWN_DIAGNOSTIC", 0
    elif coefficient == _ZERO:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "STAGE_COEFFICIENT_ZERO", 0
    elif full_kelly <= _ZERO:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "NON_POSITIVE_FULL_KELLY", 0
    elif effective_fraction <= _ZERO:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "NO_REMAINING_RISK_CAPACITY", 0
    elif stake_cents < inputs["minimum_stake_cents"]:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "STAKE_BELOW_PROVIDER_MINIMUM", 0
    else:
        action, reason_code = _CANDIDATE_ACTION, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_PASS"

    remaining_caps = {
        "single_ticket": single_cap,
        "event": event_remaining,
        "cluster": cluster_remaining,
        "open": open_remaining,
    }
    capacity_cents = {name: _round_stake_cents(Decimal(bankroll) * fraction, inputs["stake_increment_cents"]) for name, fraction in remaining_caps.items()}
    invariants = {
        "within_single_ticket_cap": stake_cents <= capacity_cents["single_ticket"],
        "within_event_cap": stake_cents <= capacity_cents["event"],
        "within_cluster_cap": stake_cents <= capacity_cents["cluster"],
        "within_open_exposure_cap": stake_cents <= capacity_cents["open"],
        "stake_aligned_to_provider_increment": stake_cents % inputs["stake_increment_cents"] == 0,
        "stake_not_rounded_up_to_provider_minimum": stake_cents == 0 or stake_cents >= inputs["minimum_stake_cents"],
    }
    return {
        "action": action,
        "reason_code": reason_code,
        "stake_cents": stake_cents,
        "diagnostics": diagnostics,
        "fractions": {
            "full_kelly": decimal_text(full_kelly),
            "stage_coefficient": decimal_text(coefficient),
            "scaled_kelly": decimal_text(scaled_kelly),
            "single_ticket_cap": decimal_text(single_cap),
            "event_remaining_cap": decimal_text(event_remaining),
            "cluster_remaining_cap": decimal_text(cluster_remaining),
            "open_remaining_cap": decimal_text(open_remaining),
            "effective_fraction": decimal_text(effective_fraction),
        },
        "capacity_cents": capacity_cents,
        "risk_invariants": invariants,
    }


def _scenario_inputs(inputs: Mapping[str, Any], scenario: str) -> tuple[Mapping[str, Any], Decimal]:
    if scenario not in _ADVERSE_SCENARIOS:
        raise RiskEngineError("unknown adverse scenario")
    result = dict(inputs)
    threshold_adjustment = _ZERO
    if scenario in {"probability_minus", "all_adverse"}:
        result["conservative_probability"] = result["conservative_probability"] - Decimal("0.0001")
    if scenario in {"risk_threshold_tightened", "all_adverse"}:
        threshold_adjustment = Decimal("0.0001")
    if scenario in {"odds_adverse", "all_adverse"}:
        result["odds"] = result["odds"] - ODDS_STEP
    if result["conservative_probability"] <= _ZERO or result["odds"] <= _ONE:
        raise RiskEngineError("adverse scenario leaves the executable numeric domain")
    return result, threshold_adjustment


def evaluate_vector(vector: Any, graph: Any, parameters: Any) -> Mapping[str, Any]:
    """Replay a single frozen vector and fail closed on any adverse action flip."""

    frozen_graph = validate_correlation_graph(graph, parameters)
    row = validate_vector(vector, frozen_graph)
    policy = _risk_policy(parameters)
    baseline_inputs = _normalized_inputs(row)
    baseline = _evaluate(baseline_inputs, policy, threshold_adjustment=_ZERO)
    scenarios: dict[str, Mapping[str, Any]] = {}
    for scenario in _ADVERSE_SCENARIOS:
        scenario_inputs, adjustment = _scenario_inputs(baseline_inputs, scenario)
        scenarios[scenario] = _evaluate(scenario_inputs, policy, threshold_adjustment=adjustment)
    adverse_flips = [
        scenario
        for scenario in _ADVERSE_SCENARIOS
        if baseline["action"] == _CANDIDATE_ACTION and scenarios[scenario]["action"] != _CANDIDATE_ACTION
    ]
    if baseline["action"] != _CANDIDATE_ACTION:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, baseline["reason_code"], 0
    elif adverse_flips:
        action, reason_code, stake_cents = _NO_RECOMMENDATION, "ADVERSE_RISK_STABILITY_FLIP", 0
    else:
        action, reason_code, stake_cents = _CANDIDATE_ACTION, "ALL_CONSTRAINED_KELLY_AND_RISK_GATES_STABLE", baseline["stake_cents"]
    expected = row["expected"]
    expected_matches = {
        "baseline_action": expected["baseline_action"] == baseline["action"],
        "action": expected["action"] == action,
        "reason_code": expected["reason_code"] == reason_code,
        "stake_cents": expected["stake_cents"] == stake_cents,
        "adverse_flip_dimensions": expected["adverse_flip_dimensions"] == adverse_flips,
    }
    return {
        "vector_id": row["vector_id"],
        "upstream_route_vector_id": row["upstream_route_vector_id"],
        "upstream_provider_id": row["upstream_provider_id"],
        "baseline": baseline,
        "scenarios": scenarios,
        "adverse_flip_dimensions": adverse_flips,
        "action": action,
        "reason_code": reason_code,
        "stake_cents": stake_cents,
        "expected": expected,
        "expected_matches": expected_matches,
        "all_expected_matches": all(expected_matches.values()),
    }


def report_sha256(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_sha256", None)
    return artifact_sha256(payload)


def registry_input_sha256(registry: Mapping[str, Any]) -> str:
    payload = dict(registry)
    payload.pop("expected_report_sha256", None)
    return artifact_sha256(payload)


def build_report(graph: Any, registry: Any, parameters: Any) -> Mapping[str, Any]:
    frozen_graph = validate_correlation_graph(graph, parameters)
    row = validate_registry(registry, frozen_graph, parameters)
    results = [evaluate_vector(vector, frozen_graph, parameters) for vector in row["vectors"]]
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "report_id": REPORT_ID,
        "graph_id": GRAPH_ID,
        "vectors_id": VECTORS_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "correlation_graph_sha256": artifact_sha256(frozen_graph),
        "risk_vectors_input_sha256": registry_input_sha256(row),
        "results": results,
        "summary": {
            "vectors": len(results),
            "risk_gated_synthetic_candidate_count": sum(item["action"] == _CANDIDATE_ACTION for item in results),
            "no_recommendation_count": sum(item["action"] == _NO_RECOMMENDATION for item in results),
            "unstable_vector_ids": [item["vector_id"] for item in results if item["adverse_flip_dimensions"]],
            "all_risk_invariants_hold": all(all(scenario["risk_invariants"].values()) for item in results for scenario in [item["baseline"], *item["scenarios"].values()]),
        },
        "decision": "RISK_GATED_SYNTHETIC_CANDIDATES_ONLY_NO_FINAL_ADVICE_OR_ORDER",
        "next": "S11/STAGE_REVIEW_READY_NOT_STARTED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    report["report_sha256"] = report_sha256(report)
    return report


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD S11/P04 constrained-Kelly risk replay")
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--correlation-graph", type=Path, required=True)
    parser.add_argument("--risk-vectors", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(_load_json(args.correlation_graph), _load_json(args.risk_vectors), _load_json(args.parameters))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
