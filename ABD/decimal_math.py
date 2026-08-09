"""Authoritative Decimal fixed-point primitives for ABD S10/P03.

This module evaluates frozen research vectors only.  It does not fetch prices,
access an account, submit an order, or make a performance guarantee.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, localcontext
from typing import Any, Mapping


DECIMAL_PRECISION = 50
PROBABILITY_STEP = Decimal("0.000000001")
ODDS_STEP = Decimal("0.000001")
FRACTION_STEP = Decimal("0.000000000001")
_ZERO = Decimal("0")
_ONE = Decimal("1")


class NumericContractError(ValueError):
    """Raised when a fixed-point vector violates the authoritative contract."""


def decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise NumericContractError("value must be a finite Decimal")
    if value == _ZERO:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise NumericContractError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise NumericContractError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise NumericContractError("%s must be finite" % label)
    return parsed


def _integer(value: Any, *, label: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise NumericContractError("%s must be an integer at least %d" % (label, minimum))
    return value


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise NumericContractError("%s has an unexpected shape" % label)
    return value


def _quantize(value: Decimal, step: Decimal, rounding: str, *, label: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            return value.quantize(step, rounding=rounding)
    except InvalidOperation as exc:
        raise NumericContractError("%s cannot be represented at the required scale" % label) from exc


def validate_numeric_contract(value: Any) -> Mapping[str, Any]:
    fields = {
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
    contract = _strict_object(value, fields, label="numeric_contract")
    exact = (
        contract["authoritative_decimal_precision_digits"] == 50
        and contract["binary_float_for_authoritative_decision"] is False
        and contract["money_storage"] == "INTEGER_CENTS"
        and contract["probability_storage_scale"] == "1e-9"
        and contract["odds_storage_scale"] == "1e-6"
        and contract["probability_rounding"] == "DOWN"
        and contract["odds_rounding"] == "DOWN"
        and contract["friction_rounding"] == "UP"
        and contract["stake_rounding"] == "DOWN_TO_PROVIDER_INCREMENT"
        and contract["independent_implementation_absolute_tolerance"] == "1e-12"
        and contract["action_must_match_across_implementations"] is True
    )
    if not exact:
        raise NumericContractError("numeric contract differs from frozen task-pack invariants")
    return contract


def normalize_probability(value: Any, *, label: str = "probability") -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed <= _ONE:
        raise NumericContractError("%s must be in [0, 1]" % label)
    return _quantize(parsed, PROBABILITY_STEP, ROUND_DOWN, label=label)


def normalize_odds(value: Any, *, label: str = "odds") -> Decimal:
    parsed = _decimal(value, label=label)
    if parsed <= _ONE:
        raise NumericContractError("%s must be greater than one" % label)
    return _quantize(parsed, ODDS_STEP, ROUND_DOWN, label=label)


def normalize_friction(value: Any, *, label: str = "friction") -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed < _ONE:
        raise NumericContractError("%s must be in [0, 1)" % label)
    return _quantize(parsed, PROBABILITY_STEP, ROUND_UP, label=label)


def normalize_fraction(value: Any, *, label: str = "risk_fraction_cap") -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed <= _ONE:
        raise NumericContractError("%s must be in [0, 1]" % label)
    return _quantize(parsed, FRACTION_STEP, ROUND_DOWN, label=label)


def _round_stake_cents(raw_cents: Decimal, increment_cents: int) -> int:
    if not raw_cents.is_finite() or raw_cents < _ZERO:
        raise NumericContractError("raw stake cents are invalid")
    rounded = int(raw_cents.to_integral_value(rounding=ROUND_DOWN))
    return (rounded // increment_cents) * increment_cents


def validate_vector(value: Any) -> Mapping[str, Any]:
    fields = {
        "vector_id",
        "conservative_probability",
        "odds",
        "friction",
        "bankroll_cents",
        "risk_fraction_cap",
        "stake_increment_cents",
    }
    vector = _strict_object(value, fields, label="numeric vector")
    if not isinstance(vector["vector_id"], str) or not vector["vector_id"]:
        raise NumericContractError("vector_id is invalid")
    normalize_probability(vector["conservative_probability"], label="conservative_probability")
    normalize_odds(vector["odds"], label="odds")
    normalize_friction(vector["friction"], label="friction")
    _integer(vector["bankroll_cents"], label="bankroll_cents", minimum=0)
    normalize_fraction(vector["risk_fraction_cap"], label="risk_fraction_cap")
    _integer(vector["stake_increment_cents"], label="stake_increment_cents", minimum=1)
    return vector


def evaluate_vector(vector: Any, numeric_contract: Any) -> Mapping[str, Any]:
    """Evaluate one research-only fixed-point vector with authoritative rounding."""

    validate_numeric_contract(numeric_contract)
    row = validate_vector(vector)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        probability = normalize_probability(row["conservative_probability"], label="conservative_probability")
        odds = normalize_odds(row["odds"], label="odds")
        friction = normalize_friction(row["friction"], label="friction")
        risk_cap = normalize_fraction(row["risk_fraction_cap"], label="risk_fraction_cap")
        bankroll_cents = _integer(row["bankroll_cents"], label="bankroll_cents", minimum=0)
        stake_increment_cents = _integer(row["stake_increment_cents"], label="stake_increment_cents", minimum=1)
        net_edge = probability * odds - _ONE - friction
        if net_edge <= _ZERO or bankroll_cents == 0 or risk_cap == _ZERO:
            kelly_fraction = _ZERO
            stake_cents = 0
            action = "NO_RECOMMENDATION_NUMERIC_GUARD"
        else:
            raw_fraction = net_edge / (odds - _ONE)
            kelly_fraction = min(max(raw_fraction, _ZERO), risk_cap).quantize(FRACTION_STEP, rounding=ROUND_DOWN)
            stake_cents = _round_stake_cents(Decimal(bankroll_cents) * kelly_fraction, stake_increment_cents)
            action = "NO_ORDER_NUMERIC_CANDIDATE" if stake_cents > 0 else "NO_RECOMMENDATION_BELOW_INCREMENT"
    return {
        "vector_id": row["vector_id"],
        "conservative_probability": decimal_text(probability),
        "odds": decimal_text(odds),
        "friction": decimal_text(friction),
        "net_edge": decimal_text(net_edge),
        "kelly_fraction": decimal_text(kelly_fraction),
        "stake_cents": stake_cents,
        "action": action,
    }
