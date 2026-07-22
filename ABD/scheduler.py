"""ABD S05/P03 deterministic refresh planning.

This module plans read-only collection times.  It never performs network I/O,
enables advice, or submits an order.  Current real provider capabilities remain
disabled by the signed S05/P02 source-capability contract.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Mapping, Sequence


CADENCE_ORDER = (
    "more_than_24h",
    "2h_to_24h",
    "15m_to_2h",
    "0_to_15m",
    "live",
)
REFRESH_SECONDS = {
    "more_than_24h": 1800,
    "2h_to_24h": 300,
    "15m_to_2h": 60,
    "0_to_15m": 20,
    "live": 10,
}
QUOTE_USABLE_SECONDS = {
    "more_than_24h": 2100,
    "2h_to_24h": 420,
    "15m_to_2h": 90,
    "0_to_15m": 30,
    "live": 12,
}
ADVICE_USABLE_SECONDS = {
    "more_than_24h": 1500,
    "2h_to_24h": 240,
    "15m_to_2h": 45,
    "0_to_15m": 15,
    "live": 8,
}
MAX_DISPATCH_DEVIATION_MICROSECONDS = 2_000_000
DISTANCE_RECALCULATION_SECONDS = 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SchedulerContractError(ValueError):
    """Raised when a scheduling input cannot be interpreted safely."""


def _deny(reason_code: str, detail: Any = None) -> Dict[str, Any]:
    return {
        "decision": "NO_DISPATCH_NO_ADVICE",
        "reason_code": reason_code,
        "detail": detail,
        "collection_performed": False,
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SchedulerContractError("timestamp must be an offset-aware ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SchedulerContractError("invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchedulerContractError("timestamp must include a UTC offset")
    return parsed


def _timedelta_microseconds(value: timedelta) -> int:
    return ((value.days * 86_400 + value.seconds) * 1_000_000) + value.microseconds


def _seconds_string(microseconds: int) -> str:
    sign = "-" if microseconds < 0 else ""
    absolute = abs(microseconds)
    return f"{sign}{absolute // 1_000_000}.{absolute % 1_000_000:06d}"


def classify_cadence(
    time_to_start_seconds: Any,
    *,
    status: str = "PREMATCH",
    source_live_supported: bool = False,
) -> Dict[str, Any]:
    """Classify a market using adverse (more urgent) boundary semantics."""
    if status == "LIVE":
        if source_live_supported is not True:
            return _deny("LIVE_REFRESH_UNSUPPORTED", "OBSERVE_OR_NO_RECOMMENDATION")
        band = "live"
    elif status != "PREMATCH":
        return _deny("UNKNOWN_EVENT_STATUS")
    else:
        if isinstance(time_to_start_seconds, bool) or not isinstance(time_to_start_seconds, int):
            return _deny("INVALID_TIME_TO_START")
        if time_to_start_seconds <= 0:
            return _deny("EVENT_STARTED_WITHOUT_VERIFIED_LIVE_STATE")
        if time_to_start_seconds > 86_400:
            band = "more_than_24h"
        elif time_to_start_seconds > 7_200:
            band = "2h_to_24h"
        elif time_to_start_seconds > 900:
            band = "15m_to_2h"
        else:
            band = "0_to_15m"
    return {
        "decision": "CADENCE_CLASSIFIED",
        "reason_code": "ADVERSE_BOUNDARY_CLASSIFICATION",
        "band": band,
        "refresh_seconds": REFRESH_SECONDS[band],
        "quote_usable_seconds": QUOTE_USABLE_SECONDS[band],
        "advice_usable_seconds": ADVICE_USABLE_SECONDS[band],
        "distance_recalculation_seconds": DISTANCE_RECALCULATION_SECONDS,
        "collection_performed": False,
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


def dispatch_timing(scheduled_at: Any, actual_dispatch_at: Any) -> Dict[str, Any]:
    try:
        scheduled = parse_timestamp(scheduled_at)
        actual = parse_timestamp(actual_dispatch_at)
    except SchedulerContractError as exc:
        return _deny("INVALID_DISPATCH_TIMESTAMP", str(exc))
    deviation = abs(_timedelta_microseconds(actual - scheduled))
    passed = deviation <= MAX_DISPATCH_DEVIATION_MICROSECONDS
    return {
        "decision": "DISPATCH_TIMING_PASS" if passed else "NO_DISPATCH_NO_ADVICE",
        "reason_code": "WITHIN_TWO_SECOND_GATE" if passed else "DISPATCH_DEVIATION_EXCEEDED",
        "scheduled_at": scheduled_at,
        "actual_dispatch_at": actual_dispatch_at,
        "deviation_microseconds": deviation,
        "deviation_seconds": _seconds_string(deviation),
        "max_deviation_microseconds": MAX_DISPATCH_DEVIATION_MICROSECONDS,
        "collection_performed": False,
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


def calculate_backoff_seconds(failure_count: Any, policy: Mapping[str, Any]) -> int:
    if isinstance(failure_count, bool) or not isinstance(failure_count, int) or failure_count < 0:
        raise SchedulerContractError("failure_count must be a non-negative integer")
    required = {"initial_seconds", "multiplier", "maximum_seconds", "jitter_seconds"}
    if not isinstance(policy, Mapping) or not required.issubset(policy):
        raise SchedulerContractError("backoff policy is incomplete")
    values = [policy[key] for key in required]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise SchedulerContractError("backoff policy values must be integers")
    initial = policy["initial_seconds"]
    multiplier = policy["multiplier"]
    maximum = policy["maximum_seconds"]
    jitter = policy["jitter_seconds"]
    if initial <= 0 or multiplier < 1 or maximum < initial or jitter != 0:
        raise SchedulerContractError("backoff policy violates deterministic bounds")
    if failure_count == 0:
        return 0
    return min(initial * (multiplier ** (failure_count - 1)), maximum)


def next_due_at(
    last_scheduled_at: Any,
    refresh_seconds: Any,
    *,
    actual_dispatch_at: Any | None = None,
    failure_count: int = 0,
    backoff_policy: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    try:
        last = parse_timestamp(last_scheduled_at)
        if isinstance(refresh_seconds, bool) or not isinstance(refresh_seconds, int) or refresh_seconds <= 0:
            raise SchedulerContractError("refresh_seconds must be a positive integer")
        cadence_due = last + timedelta(seconds=refresh_seconds)
        backoff_seconds = 0
        due = cadence_due
        if failure_count:
            if actual_dispatch_at is None or backoff_policy is None:
                raise SchedulerContractError("failure backoff requires dispatch time and policy")
            actual = parse_timestamp(actual_dispatch_at)
            backoff_seconds = calculate_backoff_seconds(failure_count, backoff_policy)
            backoff_due = actual + timedelta(seconds=backoff_seconds)
            due = max(cadence_due, backoff_due)
    except SchedulerContractError as exc:
        return _deny("INVALID_NEXT_DUE_INPUT", str(exc))
    return {
        "decision": "NEXT_DUE_PLANNED",
        "reason_code": "FIXED_CADENCE" if backoff_seconds == 0 else "DETERMINISTIC_BACKOFF",
        "next_due_at": due.isoformat(),
        "cadence_due_at": cadence_due.isoformat(),
        "refresh_seconds": refresh_seconds,
        "backoff_seconds": backoff_seconds,
        "collection_performed": False,
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


def evaluate_freshness(
    *,
    now: Any,
    band: str,
    source_timestamp: Any,
    observed_timestamp: Any,
    content_sha256: Any,
    source_clock_trusted: Any,
    advice_created_at: Any | None = None,
) -> Dict[str, Any]:
    """Return whether a quote may enter later advice evaluation.

    The older of source time and observation time controls freshness.  Passing
    this function does not generate or enable a recommendation.
    """
    if band not in CADENCE_ORDER:
        return _deny("UNKNOWN_CADENCE_BAND")
    if source_clock_trusted is not True:
        return _deny("SOURCE_CLOCK_UNTRUSTED")
    if not isinstance(content_sha256, str) or not SHA256_RE.fullmatch(content_sha256):
        return _deny("CONTENT_HASH_MISSING_OR_INVALID")
    try:
        current = parse_timestamp(now)
        source = parse_timestamp(source_timestamp)
        observed = parse_timestamp(observed_timestamp)
        advice = parse_timestamp(advice_created_at) if advice_created_at is not None else None
    except SchedulerContractError as exc:
        return _deny("INVALID_FRESHNESS_TIMESTAMP", str(exc))
    ages = [_timedelta_microseconds(current - source), _timedelta_microseconds(current - observed)]
    if any(age < 0 for age in ages):
        return _deny("FUTURE_QUOTE_TIMESTAMP")
    effective_age = max(ages)
    quote_limit = QUOTE_USABLE_SECONDS[band] * 1_000_000
    advice_limit = ADVICE_USABLE_SECONDS[band] * 1_000_000
    advice_age = 0
    if advice is not None:
        advice_age = _timedelta_microseconds(current - advice)
        if advice_age < 0:
            return _deny("FUTURE_ADVICE_TIMESTAMP")
    quote_usable = effective_age <= quote_limit
    advice_input_eligible = quote_usable and effective_age <= advice_limit and advice_age <= advice_limit
    if not quote_usable:
        reason = "STALE_QUOTE_BLOCKED"
    elif not advice_input_eligible:
        reason = "STALE_FOR_ADVICE_BLOCKED"
    else:
        reason = "FRESH_INPUT_MAY_ENTER_ADVICE_EVALUATION"
    return {
        "decision": "ALLOW_ADVICE_INPUT_EVALUATION" if advice_input_eligible else "NO_ADVICE",
        "reason_code": reason,
        "band": band,
        "effective_quote_age_microseconds": effective_age,
        "effective_quote_age_seconds": _seconds_string(effective_age),
        "advice_age_microseconds": advice_age,
        "quote_usable_seconds": QUOTE_USABLE_SECONDS[band],
        "advice_usable_seconds": ADVICE_USABLE_SECONDS[band],
        "quote_usable": quote_usable,
        "advice_input_eligible": advice_input_eligible,
        "recommendation_generated": False,
        "collection_performed": False,
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


def _all_budget_rows(rate_budget: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    rows = rate_budget.get("capability_budgets", []) if isinstance(rate_budget, Mapping) else []
    synthetic = rate_budget.get("frozen_test_only_budget") if isinstance(rate_budget, Mapping) else None
    return [*rows, *([synthetic] if isinstance(synthetic, Mapping) else [])]


def plan_refresh(request: Mapping[str, Any], rate_budget: Mapping[str, Any]) -> Dict[str, Any]:
    """Plan a refresh without collecting data or changing any external state."""
    required = {
        "capability_id",
        "capability_decision",
        "execution_environment",
        "incremental_cash_aud",
        "event_status",
        "time_to_start_seconds",
        "source_live_supported",
        "last_scheduled_at",
        "actual_dispatch_at",
        "window_dispatch_count",
        "failure_count",
    }
    if not isinstance(request, Mapping):
        return _deny("MALFORMED_SCHEDULE_REQUEST")
    missing = sorted(required - set(request))
    if missing:
        return _deny("MALFORMED_SCHEDULE_REQUEST", {"missing": missing})
    if request.get("incremental_cash_aud") != "0.00":
        return _deny("INCREMENTAL_CASH_NOT_ZERO")
    rows = [row for row in _all_budget_rows(rate_budget) if row.get("capability_id") == request.get("capability_id")]
    if len(rows) != 1:
        return _deny("UNKNOWN_OR_DUPLICATE_CAPABILITY_BUDGET")
    budget = rows[0]
    is_fixture = budget.get("test_fixture_only") is True
    if is_fixture:
        if request.get("execution_environment") != "FROZEN_TEST":
            return _deny("TEST_BUDGET_PROHIBITED_IN_PRODUCTION")
        if request.get("capability_decision") != "ALLOW_FROZEN_TEST_READ_ONLY":
            return _deny("SOURCE_CAPABILITY_GATE_NOT_PASSED")
    else:
        if request.get("capability_decision") != "ALLOW_VERIFIED_READ_ONLY":
            return _deny("SOURCE_CAPABILITY_GATE_NOT_PASSED")
    if budget.get("production_collection_enabled") is not True:
        return _deny("CAPABILITY_BUDGET_DISABLED")
    maximum = budget.get("max_dispatches_per_window")
    count = request.get("window_dispatch_count")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
        return _deny("INVALID_OR_ZERO_RATE_BUDGET")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return _deny("INVALID_WINDOW_DISPATCH_COUNT")
    if count >= maximum:
        return _deny("RATE_BUDGET_EXHAUSTED")
    cadence = classify_cadence(
        request.get("time_to_start_seconds"),
        status=request.get("event_status"),
        source_live_supported=request.get("source_live_supported"),
    )
    if cadence.get("decision") != "CADENCE_CLASSIFIED":
        return cadence
    timing = dispatch_timing(request.get("last_scheduled_at"), request.get("actual_dispatch_at"))
    if timing.get("decision") != "DISPATCH_TIMING_PASS":
        return timing
    due = next_due_at(
        request.get("last_scheduled_at"),
        cadence["refresh_seconds"],
        actual_dispatch_at=request.get("actual_dispatch_at"),
        failure_count=request.get("failure_count"),
        backoff_policy=rate_budget.get("backoff_policy"),
    )
    if due.get("decision") != "NEXT_DUE_PLANNED":
        return due
    return {
        "decision": "PLAN_FROZEN_TEST_REFRESH" if is_fixture else "PLAN_VERIFIED_READ_ONLY_REFRESH",
        "reason_code": "SOURCE_RATE_AND_CADENCE_GATES_PASS",
        "capability_id": request.get("capability_id"),
        "band": cadence["band"],
        "refresh_seconds": cadence["refresh_seconds"],
        "quote_usable_seconds": cadence["quote_usable_seconds"],
        "advice_usable_seconds": cadence["advice_usable_seconds"],
        "distance_recalculation_seconds": cadence["distance_recalculation_seconds"],
        "dispatch_deviation_microseconds": timing["deviation_microseconds"],
        "next_due_at": due["next_due_at"],
        "backoff_seconds": due["backoff_seconds"],
        "remaining_dispatches_in_window": maximum - count - 1,
        "collection_performed": False,
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


__all__ = [
    "ADVICE_USABLE_SECONDS",
    "CADENCE_ORDER",
    "DISTANCE_RECALCULATION_SECONDS",
    "MAX_DISPATCH_DEVIATION_MICROSECONDS",
    "QUOTE_USABLE_SECONDS",
    "REFRESH_SECONDS",
    "SchedulerContractError",
    "calculate_backoff_seconds",
    "classify_cadence",
    "dispatch_timing",
    "evaluate_freshness",
    "next_due_at",
    "parse_timestamp",
    "plan_refresh",
]
