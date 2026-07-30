"""Deterministic line-movement, staleness, and time-desynchronization gates.

ABD S08/P04 consumes only frozen synthetic observations. This module never
contacts a market, creates advice, accesses an account, submits an order, or
waits for elapsed wall time.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping


_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{1,79}")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_MICROSECONDS_PER_SECOND = 1_000_000


class LineMovementError(ValueError):
    """Raised when frozen line observations cannot safely support a gate."""


def decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise LineMovementError("%s must be an uppercase stable identifier" % label)
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise LineMovementError("%s must be an ISO-8601 timestamp" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LineMovementError("%s is not ISO-8601" % label) from exc
    if parsed.tzinfo is None:
        raise LineMovementError("%s must include an explicit timezone" % label)
    return parsed


def _positive_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LineMovementError("%s must be a positive integer" % label)
    return value


def _odds(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise LineMovementError("%s must be a decimal-string odds value" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise LineMovementError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or parsed <= _ONE:
        raise LineMovementError("%s must be finite decimal odds above one" % label)
    return parsed


def _elapsed_microseconds(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    return ((delta.days * 86_400 + delta.seconds) * _MICROSECONDS_PER_SECOND) + delta.microseconds


def _seconds_text(microseconds: int) -> str:
    return decimal_text(Decimal(microseconds) / Decimal(_MICROSECONDS_PER_SECOND))


def evaluate_line_movement(case: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate confirmation, freshness, and synchronization for one quote set."""

    if not isinstance(case, Mapping):
        raise LineMovementError("line movement case must be an object")
    as_of = _timestamp(case.get("as_of"), label="as_of")
    quote_usable_seconds = _positive_integer(case.get("quote_usable_seconds"), label="quote_usable_seconds")
    max_time_skew_seconds = _positive_integer(case.get("max_time_skew_seconds"), label="max_time_skew_seconds")
    minimum_confirming_sources = _positive_integer(case.get("minimum_confirming_sources"), label="minimum_confirming_sources")
    if minimum_confirming_sources < 2:
        raise LineMovementError("minimum_confirming_sources must preserve independent confirmation")
    raw_events = case.get("line_observations")
    if not isinstance(raw_events, list) or len(raw_events) < 3:
        raise LineMovementError("at least three frozen line observations are required")

    rendered_events: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    current_times: list[datetime] = []
    stale_source_ids: list[str] = []
    up_count = 0
    down_count = 0
    for index, raw in enumerate(raw_events):
        if not isinstance(raw, Mapping):
            raise LineMovementError("line_observations[%d] must be an object" % index)
        source_id = _identifier(raw.get("source_id"), label="line_observations[%d].source_id" % index)
        if source_id in source_ids:
            raise LineMovementError("line observation source_id values must be unique")
        source_ids.add(source_id)
        previous_odds = _odds(raw.get("previous_odds"), label="line_observations[%d].previous_odds" % index)
        current_odds = _odds(raw.get("current_odds"), label="line_observations[%d].current_odds" % index)
        previous_at = _timestamp(raw.get("previous_observed_at"), label="line_observations[%d].previous_observed_at" % index)
        current_at = _timestamp(raw.get("current_observed_at"), label="line_observations[%d].current_observed_at" % index)
        if current_at < previous_at:
            raise LineMovementError("line observation timestamps must be monotonic")
        if current_at > as_of:
            raise LineMovementError("line observation cannot be after as_of")
        age_microseconds = _elapsed_microseconds(as_of, current_at)
        stale = age_microseconds > quote_usable_seconds * _MICROSECONDS_PER_SECOND
        if stale:
            stale_source_ids.append(source_id)
        delta = current_odds - previous_odds
        direction = "UP" if delta > _ZERO else "DOWN" if delta < _ZERO else "FLAT"
        if direction == "UP":
            up_count += 1
        elif direction == "DOWN":
            down_count += 1
        current_times.append(current_at)
        rendered_events.append(
            {
                "source_id": source_id,
                "previous_odds": decimal_text(previous_odds),
                "current_odds": decimal_text(current_odds),
                "delta_odds": decimal_text(delta),
                "direction": direction,
                "age_seconds": _seconds_text(age_microseconds),
                "stale": stale,
            }
        )

    earliest = min(current_times)
    latest = max(current_times)
    observed_skew_microseconds = _elapsed_microseconds(latest, earliest)
    time_desynchronized = observed_skew_microseconds > max_time_skew_seconds * _MICROSECONDS_PER_SECOND
    if stale_source_ids:
        status = "BLOCK_STALE_QUOTES"
        confirmed_direction = None
        movement_confirmed = False
    elif time_desynchronized:
        status = "BLOCK_TIME_DESYNCHRONIZED"
        confirmed_direction = None
        movement_confirmed = False
    elif not up_count and not down_count:
        status = "NO_LINE_MOVEMENT"
        confirmed_direction = None
        movement_confirmed = False
    elif up_count >= minimum_confirming_sources and not down_count:
        status = "CONFIRMED_UP"
        confirmed_direction = "UP"
        movement_confirmed = True
    elif down_count >= minimum_confirming_sources and not up_count:
        status = "CONFIRMED_DOWN"
        confirmed_direction = "DOWN"
        movement_confirmed = True
    else:
        status = "BLOCK_UNCONFIRMED_LINE_MOVEMENT"
        confirmed_direction = None
        movement_confirmed = False

    return {
        "status": status,
        "source_count": len(rendered_events),
        "quote_usable_seconds": quote_usable_seconds,
        "max_time_skew_seconds": max_time_skew_seconds,
        "minimum_confirming_sources": minimum_confirming_sources,
        "observed_time_skew_seconds": _seconds_text(observed_skew_microseconds),
        "time_desynchronized": time_desynchronized,
        "stale_source_ids": sorted(stale_source_ids),
        "movement_confirmed": movement_confirmed,
        "confirmed_direction": confirmed_direction,
        "events": sorted(rendered_events, key=lambda item: item["source_id"]),
        "decision_boundary": "LINE_MOVEMENT_GATE_ONLY_NO_ADVICE_OR_ORDER",
    }
