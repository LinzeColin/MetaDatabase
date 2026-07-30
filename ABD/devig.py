"""Deterministic, decimal-only bookmaker-margin removal for ABD S08/P01.

The module is deliberately pure: inputs must be explicitly marked complete and
are limited to supplied decimal odds.  It does not fetch prices, make a
recommendation, interact with an account, or execute an order.  Its only job
is to turn one frozen complete market into four transparent market-prior
probability vectors and to expose their disagreement for downstream gates.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence


DECIMAL_PRECISION = 50
PROBABILITY_SUM_TOLERANCE = Decimal("0.000000001")
METHODS = ("MULTIPLICATIVE", "POWER", "SHIN", "ODDS_RATIO")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")


class DevigInputError(ValueError):
    """Raised when a market cannot be safely interpreted as a complete book."""


class DevigConvergenceError(ValueError):
    """Raised when a deterministic root finder cannot prove convergence."""


def _decimal(value: Any, *, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, Decimal)):
        raise DevigInputError("%s must be a decimal string or Decimal, never binary float" % label)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise DevigInputError("%s is not a decimal" % label) from exc
    if not parsed.is_finite():
        raise DevigInputError("%s must be finite" % label)
    return parsed


def decimal_text(value: Decimal) -> str:
    """Render a canonical non-exponent decimal string for evidence payloads."""

    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _validate_market(odds: Sequence[Any], *, market_complete: bool) -> tuple[Decimal, ...]:
    if market_complete is not True:
        raise DevigInputError("market_complete must be explicitly true")
    if isinstance(odds, (str, bytes)) or not isinstance(odds, Sequence) or len(odds) < 2:
        raise DevigInputError("a complete market needs at least two ordered decimal odds")
    parsed = tuple(_decimal(value, label="odds[%d]" % index) for index, value in enumerate(odds))
    if any(value <= _ONE for value in parsed):
        raise DevigInputError("decimal odds must be strictly greater than one")
    if len(set(parsed)) != len(parsed):
        # A duplicate price is a valid market state, so this is intentionally not an error.
        return parsed
    return parsed


def implied_probabilities(odds: Sequence[Any], *, market_complete: bool = True) -> tuple[Decimal, ...]:
    """Return raw implied probabilities after strict complete-market validation."""

    parsed = _validate_market(odds, market_complete=market_complete)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        implied = tuple(_ONE / value for value in parsed)
    if sum(implied, _ZERO) < _ONE:
        raise DevigInputError("booksum below one: incomplete or invalid market")
    return implied


def _assert_probability_vector(values: Sequence[Decimal], *, label: str) -> tuple[Decimal, ...]:
    if not values or any(value <= _ZERO or value >= _ONE for value in values):
        raise DevigConvergenceError("%s produced a probability outside (0, 1)" % label)
    total = sum(values, _ZERO)
    if abs(total - _ONE) > PROBABILITY_SUM_TOLERANCE:
        raise DevigConvergenceError("%s probability sum is not one within tolerance" % label)
    return tuple(values)


def _bisect_monotone(
    function: Callable[[Decimal], Decimal],
    *,
    lower: Decimal,
    upper: Decimal,
    increasing: bool,
    label: str,
    iterations: int = 192,
) -> Decimal:
    """Find a signed monotone root without float arithmetic or clock-based waits."""

    lower_value = function(lower)
    upper_value = function(upper)
    if increasing:
        bracketed = lower_value <= _ZERO <= upper_value
    else:
        bracketed = lower_value >= _ZERO >= upper_value
    if not bracketed:
        raise DevigConvergenceError("%s root is not bracketed" % label)
    for _ in range(iterations):
        midpoint = (lower + upper) / _TWO
        value = function(midpoint)
        if value == _ZERO:
            return midpoint
        if increasing:
            if value < _ZERO:
                lower = midpoint
            else:
                upper = midpoint
        else:
            if value > _ZERO:
                lower = midpoint
            else:
                upper = midpoint
    root = (lower + upper) / _TWO
    if abs(function(root)) > Decimal("1e-36"):
        raise DevigConvergenceError("%s did not converge to the deterministic tolerance" % label)
    return root


def _bracket_above_one(function: Callable[[Decimal], Decimal], *, label: str) -> Decimal:
    upper = _TWO
    for _ in range(64):
        if function(upper) <= _ZERO:
            return upper
        upper *= _TWO
    raise DevigConvergenceError("%s could not find an upper root bracket" % label)


def multiplicative_probabilities(raw: Sequence[Decimal]) -> tuple[tuple[Decimal, ...], Decimal]:
    booksum = sum(raw, _ZERO)
    if booksum < _ONE:
        raise DevigInputError("booksum below one")
    probabilities = tuple(value / booksum for value in raw)
    return _assert_probability_vector(probabilities, label="MULTIPLICATIVE"), booksum


def power_probabilities(raw: Sequence[Decimal]) -> tuple[tuple[Decimal, ...], Decimal]:
    booksum = sum(raw, _ZERO)
    if booksum == _ONE:
        return _assert_probability_vector(tuple(raw), label="POWER"), _ONE

    def residual(exponent: Decimal) -> Decimal:
        return sum((value**exponent for value in raw), _ZERO) - _ONE

    exponent = _bisect_monotone(
        residual,
        lower=_ONE,
        upper=_bracket_above_one(residual, label="POWER"),
        increasing=False,
        label="POWER",
    )
    probabilities = tuple(value**exponent for value in raw)
    return _assert_probability_vector(probabilities, label="POWER"), exponent


def _shin_probability(raw_value: Decimal, booksum: Decimal, insider_proportion: Decimal) -> Decimal:
    # This rationalised form is stable at z=0 and as z approaches one.
    radicand = insider_proportion * insider_proportion + (
        Decimal("4") * (_ONE - insider_proportion) * raw_value * raw_value / booksum
    )
    root = radicand.sqrt()
    return _TWO * raw_value * raw_value / (booksum * (root + insider_proportion))


def shin_probabilities(raw: Sequence[Decimal]) -> tuple[tuple[Decimal, ...], Decimal]:
    booksum = sum(raw, _ZERO)
    if booksum == _ONE:
        return _assert_probability_vector(tuple(raw), label="SHIN"), _ZERO

    def residual(insider_proportion: Decimal) -> Decimal:
        return sum((_shin_probability(value, booksum, insider_proportion) for value in raw), _ZERO) - _ONE

    insider_proportion = _bisect_monotone(
        residual,
        lower=_ZERO,
        upper=_ONE,
        increasing=False,
        label="SHIN",
    )
    probabilities = tuple(_shin_probability(value, booksum, insider_proportion) for value in raw)
    return _assert_probability_vector(probabilities, label="SHIN"), insider_proportion


def odds_ratio_probabilities(raw: Sequence[Decimal]) -> tuple[tuple[Decimal, ...], Decimal]:
    booksum = sum(raw, _ZERO)
    if booksum == _ONE:
        return _assert_probability_vector(tuple(raw), label="ODDS_RATIO"), _ONE

    def transform(raw_value: Decimal, odds_ratio: Decimal) -> Decimal:
        return raw_value / (odds_ratio + raw_value - odds_ratio * raw_value)

    def residual(odds_ratio: Decimal) -> Decimal:
        return sum((transform(value, odds_ratio) for value in raw), _ZERO) - _ONE

    odds_ratio = _bisect_monotone(
        residual,
        lower=_ONE,
        upper=_bracket_above_one(residual, label="ODDS_RATIO"),
        increasing=False,
        label="ODDS_RATIO",
    )
    probabilities = tuple(transform(value, odds_ratio) for value in raw)
    return _assert_probability_vector(probabilities, label="ODDS_RATIO"), odds_ratio


def calculate_market(odds: Sequence[Any], *, market_complete: bool = True) -> dict[str, Any]:
    """Calculate all four de-vig methods for one frozen complete market."""

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        parsed_odds = _validate_market(odds, market_complete=market_complete)
        raw = implied_probabilities(parsed_odds, market_complete=True)
        booksum = sum(raw, _ZERO)
        method_values = {
            "MULTIPLICATIVE": multiplicative_probabilities(raw),
            "POWER": power_probabilities(raw),
            "SHIN": shin_probabilities(raw),
            "ODDS_RATIO": odds_ratio_probabilities(raw),
        }
        methods = {
            name: {
                "probabilities": [decimal_text(value) for value in probabilities],
                "parameter": decimal_text(parameter),
            }
            for name, (probabilities, parameter) in method_values.items()
        }
        spans = []
        for index in range(len(raw)):
            values = [method_values[name][0][index] for name in METHODS]
            spans.append(max(values) - min(values))
        result = {
            "input_odds": [decimal_text(value) for value in parsed_odds],
            "raw_implied_probabilities": [decimal_text(value) for value in raw],
            "booksum": decimal_text(booksum),
            "overround": decimal_text(booksum - _ONE),
            "methods": methods,
            "method_disagreement": {
                "selection_probability_spans": [decimal_text(value) for value in spans],
                "max_abs_probability_span": decimal_text(max(spans)),
                "mean_abs_probability_span": decimal_text(sum(spans, _ZERO) / Decimal(len(spans))),
            },
        }
    return result


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build_report(vectors: Mapping[str, Any]) -> dict[str, Any]:
    """Build the deterministic public-safe report for the frozen synthetic vectors."""

    if not isinstance(vectors, Mapping) or vectors.get("input_mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT":
        raise DevigInputError("vectors must be frozen synthetic inputs")
    cases = vectors.get("cases")
    if not isinstance(cases, list) or not cases:
        raise DevigInputError("vectors must contain at least one case")
    rendered_cases = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise DevigInputError("vector case must be an object")
        identifier = case.get("id")
        odds = case.get("odds")
        if not isinstance(identifier, str) or not identifier:
            raise DevigInputError("vector case id must be a non-empty string")
        result = calculate_market(odds, market_complete=case.get("market_complete") is True)
        rendered_cases.append({"id": identifier, **result})
    spans = [Decimal(case["method_disagreement"]["max_abs_probability_span"]) for case in rendered_cases]
    vector_hash = hashlib.sha256(canonical_json_bytes(dict(vectors))).hexdigest()
    return {
        "schema_version": "1.0.0",
        "product_version": "0.0.0.1",
        "contract_id": "AC-S08-P01",
        "stage_id": "S08",
        "phase_id": "P01",
        "fixed_clock": "2026-07-30T00:00:00+10:00",
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "vectors_sha256": vector_hash,
        "methods": list(METHODS),
        "cases": rendered_cases,
        "summary": {
            "case_count": len(rendered_cases),
            "all_probability_sums_within": decimal_text(PROBABILITY_SUM_TOLERANCE),
            "maximum_method_disagreement": decimal_text(max(spans)),
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
