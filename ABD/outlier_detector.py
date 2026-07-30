"""Deterministic MAD outlier and downstream market-prior safety gate for S08/P04.

Only frozen synthetic quotes are processed. The result is a data-integrity
gate, not an advice, order, price feed, or account operation.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from line_movement import LineMovementError, evaluate_line_movement


FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
MAD_MULTIPLIER = Decimal("3.5")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{1,79}")
_ZERO = Decimal("0")
_ONE = Decimal("1")


class OutlierDetectorError(ValueError):
    """Raised when a frozen quote set cannot safely pass the integrity gate."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise OutlierDetectorError("%s must be an uppercase stable identifier" % label)
    return value


def _odds(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise OutlierDetectorError("%s must be a decimal-string odds value" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OutlierDetectorError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or parsed <= _ONE:
        raise OutlierDetectorError("%s must be finite decimal odds above one" % label)
    return parsed


def _mad_multiplier(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise OutlierDetectorError("mad_multiplier must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OutlierDetectorError("mad_multiplier is not decimal") from exc
    if not parsed.is_finite() or parsed <= _ZERO:
        raise OutlierDetectorError("mad_multiplier must be positive")
    return parsed


def lower_median(values: Sequence[Decimal]) -> Decimal:
    """Return the deterministic lower median without binary floating point."""

    if not values:
        raise OutlierDetectorError("median requires at least one value")
    return sorted(values)[(len(values) - 1) // 2]


def detect_outliers(quotes: Sequence[Mapping[str, Any]], *, mad_multiplier: Decimal) -> dict[str, Any]:
    """Detect strict 3.5×MAD quote outliers from one synchronized quote vector."""

    if len(quotes) < 3:
        raise OutlierDetectorError("at least three quotes are required for MAD detection")
    normalized: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for index, raw in enumerate(quotes):
        if not isinstance(raw, Mapping):
            raise OutlierDetectorError("quotes[%d] must be an object" % index)
        source_id = _identifier(raw.get("source_id"), label="quotes[%d].source_id" % index)
        if source_id in source_ids:
            raise OutlierDetectorError("quote source_id values must be unique")
        source_ids.add(source_id)
        normalized.append({"source_id": source_id, "odds": _odds(raw.get("odds"), label="quotes[%d].odds" % index)})
    median_odds = lower_median([item["odds"] for item in normalized])
    deviations = [abs(item["odds"] - median_odds) for item in normalized]
    mad = lower_median(deviations)
    threshold = mad_multiplier * mad
    rendered = []
    outlier_ids = []
    long_outlier_ids = []
    for item in sorted(normalized, key=lambda item: item["source_id"]):
        deviation = abs(item["odds"] - median_odds)
        outlier = deviation > threshold
        if outlier:
            outlier_ids.append(item["source_id"])
            if item["odds"] > median_odds:
                long_outlier_ids.append(item["source_id"])
        rendered.append(
            {
                "source_id": item["source_id"],
                "odds": decimal_text(item["odds"]),
                "absolute_deviation": decimal_text(deviation),
                "outlier": outlier,
                "long_odds_outlier": outlier and item["odds"] > median_odds,
            }
        )
    return {
        "median_odds": decimal_text(median_odds),
        "median_absolute_deviation": decimal_text(mad),
        "mad_multiplier": decimal_text(mad_multiplier),
        "outlier_threshold": decimal_text(threshold),
        "outlier_source_ids": outlier_ids,
        "long_outlier_source_ids": long_outlier_ids,
        "quotes": rendered,
    }


def evaluate_market_integrity(case: Mapping[str, Any]) -> dict[str, Any]:
    """Apply quote outlier, line, stale, and time-desynchronization gates."""

    if not isinstance(case, Mapping):
        raise OutlierDetectorError("integrity case must be an object")
    identifier = _identifier(case.get("id"), label="case.id")
    raw_quotes = case.get("quotes")
    if not isinstance(raw_quotes, list):
        raise OutlierDetectorError("quotes must be a list")
    mad_multiplier = _mad_multiplier(case.get("mad_multiplier"))
    outliers = detect_outliers(raw_quotes, mad_multiplier=mad_multiplier)
    try:
        movement = evaluate_line_movement(case)
    except LineMovementError as exc:
        raise OutlierDetectorError("line movement prerequisite failed: %s" % exc) from exc

    quote_odds = {
        _identifier(raw.get("source_id"), label="quote.source_id"): _odds(raw.get("odds"), label="quote.odds")
        for raw in raw_quotes
        if isinstance(raw, Mapping)
    }
    movement_odds = {
        _identifier(raw.get("source_id"), label="line.source_id"): _odds(raw.get("current_odds"), label="line.current_odds")
        for raw in case.get("line_observations", [])
        if isinstance(raw, Mapping)
    }
    if set(quote_odds) != set(movement_odds):
        raise OutlierDetectorError("quote and line observation source sets must match exactly")
    if any(quote_odds[source_id] != movement_odds[source_id] for source_id in quote_odds):
        raise OutlierDetectorError("quote odds must equal corresponding current line odds")

    block_reasons: list[str] = []
    if outliers["long_outlier_source_ids"]:
        block_reasons.append("LONG_ODDS_OUTLIER")
    elif outliers["outlier_source_ids"]:
        block_reasons.append("NON_LONG_ODDS_OUTLIER")
    if movement["status"] == "BLOCK_STALE_QUOTES":
        block_reasons.append("STALE_QUOTE")
    elif movement["status"] == "BLOCK_TIME_DESYNCHRONIZED":
        block_reasons.append("TIME_DESYNCHRONIZED")
    elif movement["status"] == "BLOCK_UNCONFIRMED_LINE_MOVEMENT":
        block_reasons.append("UNCONFIRMED_LINE_MOVEMENT")
    downstream_allowed = not block_reasons
    return {
        "id": identifier,
        "outlier_detection": outliers,
        "line_movement": movement,
        "downstream_market_prior_allowed": downstream_allowed,
        "gate": "ALLOW_DOWNSTREAM_MARKET_PRIOR" if downstream_allowed else "BLOCK_NO_RECOMMENDATION",
        "block_reasons": block_reasons,
        "recommendation_generated": False,
        "recommendation_permitted": False,
        "decision_boundary": "OUTLIER_AND_LINE_GATE_ONLY_NO_ADVICE_OR_ORDER",
    }


def build_report(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical P04 outlier/line artifact from frozen synthetic cases."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != INPUT_MODE:
        raise OutlierDetectorError("fixture must be frozen synthetic input with no network or account")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise OutlierDetectorError("fixture must contain integrity cases")
    rendered_cases = [evaluate_market_integrity(case) for case in cases]
    rendered_cases.sort(key=lambda case: case["id"])
    blocked_cases = [case for case in rendered_cases if case["gate"] == "BLOCK_NO_RECOMMENDATION"]
    return {
        "schema_version": "1.0.0",
        "product_version": "0.0.0.1",
        "contract_id": "AC-S08-P04",
        "stage_id": "S08",
        "phase_id": "P04",
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "fixture_sha256": hashlib.sha256(canonical_json_bytes(dict(fixture))).hexdigest(),
        "predecessor_contract_id": "AC-S08-P03",
        "cases": rendered_cases,
        "summary": {
            "case_count": len(rendered_cases),
            "blocked_case_count": len(blocked_cases),
            "allowed_case_count": len(rendered_cases) - len(blocked_cases),
            "mad_multiplier": decimal_text(MAD_MULTIPLIER),
        },
        "external_effect_boundary": {
            "external_network_accessed": False,
            "real_market_or_odds_observed": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        },
    }
