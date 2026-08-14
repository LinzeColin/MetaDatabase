"""Frozen S11/P03 dynamic-platform routing gate.

This module compares only frozen synthetic provider fixtures.  It neither
discovers a real platform nor creates a recommendation, order, account action,
network request, or real-time wait.  A routed result is still downstream-gated
by constrained Kelly and risk controls in S11/P04.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from decimal_math import (
    DECIMAL_PRECISION,
    FRACTION_STEP,
    ODDS_STEP,
    NumericContractError,
    decimal_text,
    normalize_fraction,
    normalize_friction,
    normalize_odds,
)


CONTRACT_ID = "AC-S11-P03"
REQUIREMENT_ID = "REQ-S11-P03"
STAGE_ID = "S11"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
PROVIDER_SCORE_ID = "SCORE-S11-P03-PLATFORM"
ROUTING_FIXTURES_ID = "FIX-S11-P03-PLATFORM-ROUTING"
REPORT_ID = "RPT-S11-P03-PLATFORM-ROUTING"

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TIME_BANDS = ("more_than_24h", "2h_to_24h", "15m_to_2h", "0_to_15m", "live")
_ADVERSE_SCENARIOS = (
    "return_minus",
    "stale_time_plus",
    "stale_penalty_plus",
    "settlement_penalty_plus",
    "minimum_stake_penalty_plus",
    "action_friction_plus",
    "odds_adverse",
    "all_adverse",
)
_ROUTED_CANDIDATE_ACTION = "ROUTED_PENDING_CONSTRAINED_KELLY_AND_RISK_GATES"
_NO_RECOMMENDATION = "NO_RECOMMENDATION"
_P02_CANDIDATE_ACTION = "CANDIDATE_PENDING_PLATFORM_AND_RISK_GATES"
_P02_VECTOR_ACTIONS = {
    "V01-E4-STABLE-PASS": _P02_CANDIDATE_ACTION,
    "V02-E4-EXACT-MINIMUM-ODDS-ADVERSE-FLIP": _NO_RECOMMENDATION,
    "V03-E3-BOUNDARY-STABLE-PASS": _P02_CANDIDATE_ACTION,
    "V04-E2-BOUNDARY-STABLE-PASS": _P02_CANDIDATE_ACTION,
    "V05-E1-BOUNDARY-STABLE-PASS": _P02_CANDIDATE_ACTION,
    "V06-E0-NONPRICE-SOURCES-BELOW-MINIMUM": _NO_RECOMMENDATION,
    "V07-E4-MODEL-STAGE-BELOW-MINIMUM": _NO_RECOMMENDATION,
    "V08-E2-DISAGREEMENT-PLUS-POINT-0001": _NO_RECOMMENDATION,
    "V09-IDENTITY-BELOW-THRESHOLD": _NO_RECOMMENDATION,
    "V10-FEATURE-COMPLETENESS-BELOW-THRESHOLD": _NO_RECOMMENDATION,
    "V11-ODDS-ONE-TICK-BELOW-MINIMUM": _NO_RECOMMENDATION,
    "V12-SOURCE-CONTRACT-FAILS-CLOSED": _NO_RECOMMENDATION,
}
_VECTOR_IDS = (
    "R01-UNIQUE-STABLE-SYNTHETIC-PLATFORM",
    "R02-TOP-SCORE-TIE-FAILS-CLOSED",
    "R03-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP",
    "R04-MINIMUM-ODDS-BOUNDARY-ADVERSE-FLIP",
    "R05-SOURCE-CONTRACT-FAILS-CLOSED",
    "R06-SETTLEMENT-RULES-FAIL-CLOSED",
    "R07-ACTION-CHANNEL-FAILS-CLOSED",
    "R08-MINIMUM-STAKE-EXCEEDS-ROUTING-STAKE",
    "R09-UPSTREAM-P02-CANDIDATE-REQUIRED",
    "R10-NONPOSITIVE-EXECUTABLE-SCORE",
    "R11-RETURN-POINT-0001-ADVERSE-FLIP",
    "R12-LIVE-QUOTE-AGE-BOUNDARY-ADVERSE-FLIP",
)
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


class PlatformRouterError(ValueError):
    """Raised when a frozen S11/P03 routing input is malformed or unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise PlatformRouterError("%s has an unexpected shape" % label)
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlatformRouterError("%s must be a non-empty string" % label)
    return value


def _sha256_text(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise PlatformRouterError("%s must be a lowercase SHA-256" % label)
    return text


def _integer(value: Any, *, label: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise PlatformRouterError("%s must be an integer at least %d" % (label, minimum))
    return value


def _fixed_return(value: Any, *, label: str) -> Decimal:
    """Accept the P02 net-return scale without introducing a new threshold."""

    if not isinstance(value, str):
        raise PlatformRouterError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PlatformRouterError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or not _ZERO <= parsed <= _ONE:
        raise PlatformRouterError("%s must be a finite fraction in [0, 1]" % label)
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            quantized = parsed.quantize(FRACTION_STEP)
    except InvalidOperation as exc:
        raise PlatformRouterError("%s cannot be represented at the fixed return scale" % label) from exc
    if quantized != parsed:
        raise PlatformRouterError("%s is not aligned to the fixed return scale" % label)
    return normalize_fraction(decimal_text(parsed), label=label)


def _parameters(parameters: Any) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(parameters, Mapping):
        raise PlatformRouterError("parameters must be an object")
    numeric = parameters.get("numeric_determinism")
    coverage = parameters.get("coverage_and_freshness")
    if not isinstance(numeric, Mapping) or not isinstance(coverage, Mapping):
        raise PlatformRouterError("frozen numeric or freshness parameters are unavailable")
    if dict(numeric) != _NUMERIC_DETERMINISM:
        raise PlatformRouterError("numeric_determinism differs from frozen task-pack values")
    quote = coverage.get("quote_usable_seconds")
    advice = coverage.get("advice_usable_seconds")
    if not isinstance(quote, Mapping) or not isinstance(advice, Mapping) or set(quote) != set(_TIME_BANDS) or set(advice) != set(_TIME_BANDS):
        raise PlatformRouterError("frozen freshness bands differ")
    for band in _TIME_BANDS:
        _integer(quote[band], label="quote usable seconds %s" % band, minimum=1)
        _integer(advice[band], label="advice usable seconds %s" % band, minimum=1)
    return numeric, coverage


def build_provider_score(parameters: Any) -> dict[str, Any]:
    """Materialize the frozen P03 scoring and hard-gate policy."""

    numeric, coverage = _parameters(parameters)
    quote = coverage["quote_usable_seconds"]
    advice = coverage["advice_usable_seconds"]
    return {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S11-P03-01",
        "provider_score_id": PROVIDER_SCORE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "score_formula": "S_platform = r_L - P_stale - P_settlement - P_minimum_stake - P_action_friction",
        "penalty_policy": "ALL_PENALTIES_ARE_FROZEN_SYNTHETIC_CONSERVATIVE_UPPER_BOUNDS",
        "quote_usable_seconds": {band: quote[band] for band in _TIME_BANDS},
        "advice_usable_seconds": {band: advice[band] for band in _TIME_BANDS},
        "hard_gates": {
            "p02_candidate_action_required": _P02_CANDIDATE_ACTION,
            "source_contract_must_pass": True,
            "settlement_rules_must_be_clear": True,
            "action_channel_must_be_available": True,
            "observed_odds_must_meet_minimum": True,
            "minimum_stake_must_not_exceed_routing_stake": True,
            "routing_stake_must_align_to_provider_increment": True,
            "score_must_be_strictly_positive": True,
            "unique_highest_score_required": True,
            "adverse_stability_must_preserve_action_and_provider": True,
        },
        "numeric_determinism": {
            "decimal_precision_digits": numeric["authoritative_decimal_precision_digits"],
            "score_scale": "1e-12",
            "money_storage": numeric["money_storage"],
            "odds_storage_scale": numeric["odds_storage_scale"],
            "return_perturbation": numeric["boundary_perturbation_absolute_probability"],
            "penalty_perturbation": numeric["boundary_perturbation_absolute_threshold"],
            "time_perturbation_seconds": numeric["boundary_perturbation_time_adverse_seconds"],
            "odds_perturbation": numeric["odds_perturbation"],
            "unstable_action": numeric["unstable_action"],
        },
        "decision": "FROZEN_SYNTHETIC_PLATFORM_SCORE_POLICY_READY",
        "next": "S11/P03_ROUTING_REPLAY_REQUIRED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }


def validate_provider_score(value: Any, parameters: Any) -> Mapping[str, Any]:
    expected = build_provider_score(parameters)
    if value != expected:
        raise PlatformRouterError("provider score artifact is not the exact frozen replay")
    return expected


def _expected_shape(value: Any) -> Mapping[str, Any]:
    expected = _strict_object(
        value,
        {"baseline_action", "selected_provider_id", "reason_code", "adverse_flip_dimensions"},
        label="routing expected",
    )
    if expected["baseline_action"] not in {_ROUTED_CANDIDATE_ACTION, _NO_RECOMMENDATION}:
        raise PlatformRouterError("expected baseline action is invalid")
    selected = expected["selected_provider_id"]
    if selected is not None and (not isinstance(selected, str) or not selected.startswith("SYNTHETIC_PROVIDER_")):
        raise PlatformRouterError("expected selected provider is invalid")
    _text(expected["reason_code"], label="expected reason_code")
    flips = expected["adverse_flip_dimensions"]
    if not isinstance(flips, list) or flips != sorted(set(flips), key=_ADVERSE_SCENARIOS.index) or any(item not in _ADVERSE_SCENARIOS for item in flips):
        raise PlatformRouterError("expected adverse_flip_dimensions is invalid")
    return expected


def validate_provider(value: Any) -> Mapping[str, Any]:
    provider = _strict_object(
        value,
        {
            "provider_id",
            "p02_vector_id",
            "p02_candidate_action",
            "time_band",
            "quote_age_seconds",
            "settlement_rules_clear",
            "source_contract_pass",
            "action_channel_available",
            "minimum_stake_cents",
            "routing_stake_cents",
            "stake_increment_cents",
            "observed_odds",
            "minimum_acceptable_odds",
            "robust_net_expected_return",
            "stale_penalty",
            "settlement_penalty",
            "minimum_stake_penalty",
            "action_friction_penalty",
        },
        label="synthetic provider",
    )
    provider_id = _text(provider["provider_id"], label="provider_id")
    if not provider_id.startswith("SYNTHETIC_PROVIDER_"):
        raise PlatformRouterError("provider_id must be synthetic-only")
    vector_id = _text(provider["p02_vector_id"], label="p02_vector_id")
    if vector_id not in _P02_VECTOR_ACTIONS:
        raise PlatformRouterError("p02_vector_id is not a frozen P02 vector")
    action = provider["p02_candidate_action"]
    if action not in {_P02_CANDIDATE_ACTION, _NO_RECOMMENDATION} or action != _P02_VECTOR_ACTIONS[vector_id]:
        raise PlatformRouterError("p02 candidate action is not bound to its frozen P02 vector")
    if provider["time_band"] not in _TIME_BANDS:
        raise PlatformRouterError("time_band is invalid")
    _integer(provider["quote_age_seconds"], label="quote_age_seconds", minimum=0)
    for field in ("settlement_rules_clear", "source_contract_pass", "action_channel_available"):
        if type(provider[field]) is not bool:
            raise PlatformRouterError("%s must be boolean" % field)
    _integer(provider["minimum_stake_cents"], label="minimum_stake_cents", minimum=0)
    _integer(provider["routing_stake_cents"], label="routing_stake_cents", minimum=0)
    _integer(provider["stake_increment_cents"], label="stake_increment_cents", minimum=1)
    try:
        normalize_odds(provider["observed_odds"], label="observed_odds")
        normalize_odds(provider["minimum_acceptable_odds"], label="minimum_acceptable_odds")
        _fixed_return(provider["robust_net_expected_return"], label="robust_net_expected_return")
        for field in ("stale_penalty", "settlement_penalty", "minimum_stake_penalty", "action_friction_penalty"):
            normalize_friction(provider[field], label=field)
    except NumericContractError as exc:
        raise PlatformRouterError("synthetic provider violates fixed-point contract: %s" % exc) from exc
    return provider


def validate_registry(registry: Any, provider_score: Any, parameters: Any) -> Mapping[str, Any]:
    validate_provider_score(provider_score, parameters)
    row = _strict_object(
        registry,
        {
            "schema_version",
            "artifact_id",
            "routing_fixtures_id",
            "contract_id",
            "requirement_id",
            "stage_id",
            "phase_id",
            "product_version",
            "fixed_clock",
            "input_mode",
            "provider_score_sha256",
            "vectors",
            "expected_report_sha256",
        },
        label="routing fixtures registry",
    )
    identity_ok = (
        row["schema_version"] == "1.0.0"
        and row["artifact_id"] == "ART-S11-P03-02"
        and row["routing_fixtures_id"] == ROUTING_FIXTURES_ID
        and row["contract_id"] == CONTRACT_ID
        and row["requirement_id"] == REQUIREMENT_ID
        and row["stage_id"] == STAGE_ID
        and row["phase_id"] == PHASE_ID
        and row["product_version"] == VERSION
        and row["fixed_clock"] == FIXED_CLOCK
        and row["input_mode"] == INPUT_MODE
    )
    if not identity_ok:
        raise PlatformRouterError("routing fixtures registry identity is invalid")
    if _sha256_text(row["provider_score_sha256"], label="provider_score_sha256") != artifact_sha256(provider_score):
        raise PlatformRouterError("routing fixtures are not bound to exact provider score policy")
    _sha256_text(row["expected_report_sha256"], label="expected_report_sha256")
    vectors = row["vectors"]
    if not isinstance(vectors, list) or [item.get("vector_id") if isinstance(item, Mapping) else None for item in vectors] != list(_VECTOR_IDS):
        raise PlatformRouterError("routing vectors must be the exact frozen ordered set")
    for vector in vectors:
        validate_vector(vector)
    return row


def validate_vector(value: Any) -> Mapping[str, Any]:
    vector = _strict_object(value, {"vector_id", "providers", "expected"}, label="routing vector")
    if _text(vector["vector_id"], label="vector_id") not in _VECTOR_IDS:
        raise PlatformRouterError("vector_id is not a frozen routing vector")
    providers = vector["providers"]
    if not isinstance(providers, list) or not 1 <= len(providers) <= 4:
        raise PlatformRouterError("routing vector must contain one to four providers")
    ids = []
    for provider in providers:
        validate_provider(provider)
        ids.append(provider["provider_id"])
    if len(ids) != len(set(ids)):
        raise PlatformRouterError("routing vector provider ids must be unique")
    _expected_shape(vector["expected"])
    return vector


def _normalized_provider(provider: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "provider_id": provider["provider_id"],
        "p02_vector_id": provider["p02_vector_id"],
        "p02_candidate_action": provider["p02_candidate_action"],
        "time_band": provider["time_band"],
        "quote_age_seconds": _integer(provider["quote_age_seconds"], label="quote_age_seconds", minimum=0),
        "settlement_rules_clear": provider["settlement_rules_clear"],
        "source_contract_pass": provider["source_contract_pass"],
        "action_channel_available": provider["action_channel_available"],
        "minimum_stake_cents": _integer(provider["minimum_stake_cents"], label="minimum_stake_cents", minimum=0),
        "routing_stake_cents": _integer(provider["routing_stake_cents"], label="routing_stake_cents", minimum=0),
        "stake_increment_cents": _integer(provider["stake_increment_cents"], label="stake_increment_cents", minimum=1),
        "observed_odds": normalize_odds(provider["observed_odds"], label="observed_odds"),
        "minimum_acceptable_odds": normalize_odds(provider["minimum_acceptable_odds"], label="minimum_acceptable_odds"),
        "robust_net_expected_return": _fixed_return(provider["robust_net_expected_return"], label="robust_net_expected_return"),
        "stale_penalty": normalize_friction(provider["stale_penalty"], label="stale_penalty"),
        "settlement_penalty": normalize_friction(provider["settlement_penalty"], label="settlement_penalty"),
        "minimum_stake_penalty": normalize_friction(provider["minimum_stake_penalty"], label="minimum_stake_penalty"),
        "action_friction_penalty": normalize_friction(provider["action_friction_penalty"], label="action_friction_penalty"),
    }


def _score(inputs: Mapping[str, Any]) -> Decimal:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return (
            inputs["robust_net_expected_return"]
            - inputs["stale_penalty"]
            - inputs["settlement_penalty"]
            - inputs["minimum_stake_penalty"]
            - inputs["action_friction_penalty"]
        ).quantize(FRACTION_STEP)


def _evaluate_provider(provider: Mapping[str, Any], policy: Mapping[str, Any]) -> Mapping[str, Any]:
    inputs = _normalized_provider(provider)
    score = _score(inputs)
    quote_limit = policy["quote_usable_seconds"][inputs["time_band"]]
    if inputs["p02_candidate_action"] != _P02_CANDIDATE_ACTION:
        reason = "UPSTREAM_P02_CANDIDATE_GATE_NOT_PASSED"
    elif inputs["quote_age_seconds"] > quote_limit:
        reason = "QUOTE_STALE_BY_TIME_BAND"
    elif not inputs["settlement_rules_clear"]:
        reason = "SETTLEMENT_RULES_UNCLEAR"
    elif not inputs["source_contract_pass"]:
        reason = "SOURCE_CONTRACT_NOT_PASSED"
    elif not inputs["action_channel_available"]:
        reason = "ACTION_CHANNEL_UNAVAILABLE"
    elif inputs["observed_odds"] < inputs["minimum_acceptable_odds"]:
        reason = "OBSERVED_ODDS_BELOW_MINIMUM"
    elif inputs["routing_stake_cents"] <= 0:
        reason = "ROUTING_STAKE_NOT_POSITIVE"
    elif inputs["routing_stake_cents"] % inputs["stake_increment_cents"]:
        reason = "ROUTING_STAKE_NOT_ALIGNED_TO_INCREMENT"
    elif inputs["minimum_stake_cents"] > inputs["routing_stake_cents"]:
        reason = "MINIMUM_STAKE_EXCEEDS_ROUTING_STAKE"
    elif score <= _ZERO:
        reason = "NON_POSITIVE_EXECUTABLE_PLATFORM_SCORE"
    else:
        reason = "ALL_PLATFORM_GATES_PASS"
    return {
        "provider_id": inputs["provider_id"],
        "p02_vector_id": inputs["p02_vector_id"],
        "quote_usable_limit_seconds": quote_limit,
        "score": decimal_text(score),
        "eligible": reason == "ALL_PLATFORM_GATES_PASS",
        "reason_code": reason,
    }


def route_once(providers: Any, provider_score: Any, parameters: Any) -> Mapping[str, Any]:
    """Route one frozen provider set; a result is never a final recommendation."""

    policy = validate_provider_score(provider_score, parameters)
    if not isinstance(providers, list) or not providers:
        raise PlatformRouterError("providers must be a non-empty list")
    evaluations = [_evaluate_provider(validate_provider(provider), policy) for provider in providers]
    eligible = [row for row in evaluations if row["eligible"]]
    if not eligible:
        return {
            "action": _NO_RECOMMENDATION,
            "selected_provider_id": None,
            "reason_code": "NO_PLATFORM_PASSES_ALL_HARD_GATES",
            "providers": evaluations,
        }
    top_score = max(Decimal(row["score"]) for row in eligible)
    top = [row for row in eligible if Decimal(row["score"]) == top_score]
    if len(top) != 1:
        return {
            "action": _NO_RECOMMENDATION,
            "selected_provider_id": None,
            "reason_code": "TOP_PLATFORM_SCORE_TIED",
            "providers": evaluations,
        }
    return {
        "action": _ROUTED_CANDIDATE_ACTION,
        "selected_provider_id": top[0]["provider_id"],
        "reason_code": "UNIQUE_HIGHEST_PLATFORM_SCORE_PENDING_CONSTRAINED_KELLY_AND_RISK",
        "providers": evaluations,
    }


def _scenario_provider(provider: Mapping[str, Any], scenario: str, numeric: Mapping[str, Any]) -> Mapping[str, Any]:
    row = dict(provider)
    return_delta = Decimal(numeric["boundary_perturbation_absolute_probability"])
    penalty_delta = Decimal(numeric["boundary_perturbation_absolute_threshold"])
    time_delta = _integer(numeric["boundary_perturbation_time_adverse_seconds"], label="time perturbation", minimum=1)
    if scenario in {"return_minus", "all_adverse"}:
        current = _fixed_return(row["robust_net_expected_return"], label="scenario robust_net_expected_return")
        row["robust_net_expected_return"] = decimal_text(max(_ZERO, current - return_delta))
    if scenario in {"stale_time_plus", "all_adverse"}:
        row["quote_age_seconds"] = _integer(row["quote_age_seconds"], label="scenario quote_age_seconds", minimum=0) + time_delta
    for scenario_name, field in (
        ("stale_penalty_plus", "stale_penalty"),
        ("settlement_penalty_plus", "settlement_penalty"),
        ("minimum_stake_penalty_plus", "minimum_stake_penalty"),
        ("action_friction_plus", "action_friction_penalty"),
    ):
        if scenario in {scenario_name, "all_adverse"}:
            current = normalize_friction(row[field], label="scenario %s" % field)
            if current + penalty_delta >= _ONE:
                raise PlatformRouterError("adverse penalty leaves executable numeric domain")
            row[field] = decimal_text(current + penalty_delta)
    if scenario in {"odds_adverse", "all_adverse"}:
        current_odds = normalize_odds(row["observed_odds"], label="scenario observed_odds")
        if current_odds - ODDS_STEP <= _ONE:
            raise PlatformRouterError("adverse odds leave executable numeric domain")
        row["observed_odds"] = decimal_text(current_odds - ODDS_STEP)
    return row


def evaluate_vector(vector: Any, provider_score: Any, parameters: Any) -> Mapping[str, Any]:
    """Replay a frozen provider set across every relevant adverse scenario."""

    row = validate_vector(vector)
    numeric, _ = _parameters(parameters)
    policy = validate_provider_score(provider_score, parameters)
    baseline = route_once(row["providers"], policy, parameters)
    scenarios = {
        scenario: route_once([_scenario_provider(provider, scenario, numeric) for provider in row["providers"]], policy, parameters)
        for scenario in _ADVERSE_SCENARIOS
    }
    adverse_flips = [
        scenario
        for scenario in _ADVERSE_SCENARIOS
        if baseline["action"] == _ROUTED_CANDIDATE_ACTION
        and (
            scenarios[scenario]["action"] != baseline["action"]
            or scenarios[scenario]["selected_provider_id"] != baseline["selected_provider_id"]
        )
    ]
    if baseline["action"] != _ROUTED_CANDIDATE_ACTION:
        action = _NO_RECOMMENDATION
        reason_code = baseline["reason_code"]
    elif adverse_flips:
        action = _NO_RECOMMENDATION
        reason_code = "ADVERSE_PLATFORM_ROUTING_STABILITY_FLIP"
    else:
        action = _ROUTED_CANDIDATE_ACTION
        reason_code = "ALL_PLATFORM_GATES_AND_UNIQUE_ROUTE_STABLE"
    expected = row["expected"]
    expected_matches = {
        "baseline_action": expected["baseline_action"] == baseline["action"],
        "selected_provider_id": expected["selected_provider_id"] == baseline["selected_provider_id"],
        "reason_code": expected["reason_code"] == reason_code,
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
    payload = dict(registry)
    payload.pop("expected_report_sha256", None)
    return artifact_sha256(payload)


def build_report(provider_score: Any, registry: Any, parameters: Any) -> Mapping[str, Any]:
    row = validate_registry(registry, provider_score, parameters)
    results = [evaluate_vector(vector, provider_score, parameters) for vector in row["vectors"]]
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "report_id": REPORT_ID,
        "provider_score_id": PROVIDER_SCORE_ID,
        "routing_fixtures_id": ROUTING_FIXTURES_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "provider_score_sha256": artifact_sha256(provider_score),
        "routing_fixtures_input_sha256": registry_input_sha256(row),
        "results": results,
        "summary": {
            "vector_count": len(results),
            "expected_match_count": sum(result["all_expected_matches"] for result in results),
            "routed_candidate_pending_constrained_kelly_and_risk_count": sum(result["action"] == _ROUTED_CANDIDATE_ACTION for result in results),
            "no_recommendation_count": sum(result["action"] == _NO_RECOMMENDATION for result in results),
            "unique_baseline_route_count": sum(result["baseline"]["selected_provider_id"] is not None for result in results),
        },
        "decision": "UNIQUE_SYNTHETIC_PLATFORM_CANDIDATE_READY_DOWNSTREAM_CONSTRAINED_KELLY_AND_RISK_REQUIRED",
        "next": "S11/P04_READY_NOT_STARTED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
    }
    report["report_sha256"] = report_sha256(report)
    return report


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay frozen ABD S11/P03 synthetic platform-routing vectors")
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--provider-score", required=True)
    parser.add_argument("--routing-fixtures", required=True)
    args = parser.parse_args()
    parameters = _load_json(Path(args.parameters))
    provider_score = _load_json(Path(args.provider_score))
    routing_fixtures = _load_json(Path(args.routing_fixtures))
    report = build_report(provider_score, routing_fixtures, parameters)
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
