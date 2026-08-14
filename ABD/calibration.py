"""Deterministic, decimal-only calibration primitives for ABD S10/P01.

The functions in this module are deliberately local and side-effect free.  They
operate only on already-frozen probability/outcome observations and are not a
recommendation, market-data, account, or order interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext
import json
from typing import Any, Iterable, Mapping, Sequence


DECIMAL_PRECISION = 50
PROBABILITY_EPSILON = Decimal("0.000000001")
LOGIT_LIMIT = Decimal("20")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")


class CalibrationInputError(ValueError):
    """Raised when calibration input cannot be evaluated safely."""


@dataclass(frozen=True)
class BinaryObservation:
    """One binary outcome known at a deterministic, monotonically ordered index."""

    event_index: int
    probability: Decimal
    outcome: int


@dataclass(frozen=True)
class MulticlassObservation:
    """One categorical outcome with an exact probability vector."""

    event_index: int
    probabilities: Mapping[str, Decimal]
    outcome_id: str


@dataclass(frozen=True)
class IsotonicBlock:
    """A pooled-adjacent-violators block, inclusive through ``upper``."""

    upper: Decimal
    total: Decimal
    weight: Decimal

    @property
    def value(self) -> Decimal:
        return self.total / self.weight


def canonical_json_bytes(value: Any) -> bytes:
    """Render deterministic JSON used by the S10 fixture and evidence paths."""

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decimal_text(value: Decimal) -> str:
    """Render a finite decimal without an exponent or redundant trailing zeros."""

    if not value.is_finite():
        raise CalibrationInputError("decimal value must be finite")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise CalibrationInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CalibrationInputError("%s is not a decimal" % label) from exc
    if not parsed.is_finite():
        raise CalibrationInputError("%s must be finite" % label)
    return parsed


def _probability(value: Any, *, label: str, strict: bool = True) -> Decimal:
    parsed = _decimal(value, label=label)
    valid = _ZERO < parsed < _ONE if strict else _ZERO <= parsed <= _ONE
    if not valid:
        relation = "strictly between zero and one" if strict else "in [0, 1]"
        raise CalibrationInputError("%s must be %s" % (label, relation))
    return parsed


def _event_index(value: Any, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CalibrationInputError("%s must be a nonnegative integer" % label)
    return value


def _outcome(value: Any, *, label: str) -> int:
    if type(value) is not int or value not in {0, 1}:
        raise CalibrationInputError("%s must be exactly 0 or 1" % label)
    return value


def binary_observation(value: Mapping[str, Any], *, label: str) -> BinaryObservation:
    if not isinstance(value, Mapping) or set(value) != {"event_index", "probability", "outcome"}:
        raise CalibrationInputError("%s must contain event_index, probability, and outcome only" % label)
    return BinaryObservation(
        event_index=_event_index(value["event_index"], label="%s.event_index" % label),
        probability=_probability(value["probability"], label="%s.probability" % label),
        outcome=_outcome(value["outcome"], label="%s.outcome" % label),
    )


def multiclass_observation(value: Mapping[str, Any], *, label: str) -> MulticlassObservation:
    required = {"event_index", "probabilities", "outcome_id"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise CalibrationInputError("%s must contain event_index, probabilities, and outcome_id only" % label)
    probabilities_raw = value["probabilities"]
    if not isinstance(probabilities_raw, Mapping) or len(probabilities_raw) < 3:
        raise CalibrationInputError("%s.probabilities must contain at least three outcomes" % label)
    parsed: dict[str, Decimal] = {}
    for outcome_id, probability in probabilities_raw.items():
        if not isinstance(outcome_id, str) or not outcome_id or outcome_id in parsed:
            raise CalibrationInputError("%s.probabilities has an invalid outcome id" % label)
        parsed[outcome_id] = _probability(probability, label="%s.probabilities.%s" % (label, outcome_id))
    if abs(sum(parsed.values(), _ZERO) - _ONE) > Decimal("0.000000000001"):
        raise CalibrationInputError("%s.probabilities must sum to one" % label)
    outcome_id = value["outcome_id"]
    if not isinstance(outcome_id, str) or outcome_id not in parsed:
        raise CalibrationInputError("%s.outcome_id must name a probability outcome" % label)
    return MulticlassObservation(
        event_index=_event_index(value["event_index"], label="%s.event_index" % label),
        probabilities=parsed,
        outcome_id=outcome_id,
    )


def validate_temporal_order(observations: Sequence[BinaryObservation | MulticlassObservation]) -> None:
    """Require a strict, duplicate-free historical order before fitting anything."""

    indices = [item.event_index for item in observations]
    if not indices or indices != sorted(indices) or len(indices) != len(set(indices)):
        raise CalibrationInputError("observations must have strictly increasing unique event_index values")


def _bounded_logit(probability: Decimal) -> Decimal:
    bounded = min(max(probability, PROBABILITY_EPSILON), _ONE - PROBABILITY_EPSILON)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        result = (bounded / (_ONE - bounded)).ln()
    return min(max(result, -LOGIT_LIMIT), LOGIT_LIMIT)


def _sigmoid(value: Decimal) -> Decimal:
    bounded = min(max(value, -LOGIT_LIMIT), LOGIT_LIMIT)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if bounded >= _ZERO:
            return _ONE / (_ONE + (-bounded).exp())
        numerator = bounded.exp()
        return numerator / (_ONE + numerator)


def fit_isotonic_binary(observations: Sequence[BinaryObservation]) -> tuple[IsotonicBlock, ...]:
    """Fit pooled-adjacent-violators isotonic regression without binary floats."""

    validate_temporal_order(observations)
    ordered = sorted(observations, key=lambda item: (item.probability, item.event_index))
    tied_blocks: list[IsotonicBlock] = []
    for observation in ordered:
        if tied_blocks and tied_blocks[-1].upper == observation.probability:
            previous = tied_blocks[-1]
            tied_blocks[-1] = IsotonicBlock(
                previous.upper,
                previous.total + Decimal(observation.outcome),
                previous.weight + _ONE,
            )
        else:
            tied_blocks.append(IsotonicBlock(observation.probability, Decimal(observation.outcome), _ONE))
    blocks: list[IsotonicBlock] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for block in tied_blocks:
            blocks.append(block)
            while len(blocks) >= 2 and blocks[-2].value > blocks[-1].value:
                left, right = blocks[-2], blocks[-1]
                blocks[-2:] = [IsotonicBlock(right.upper, left.total + right.total, left.weight + right.weight)]
    return tuple(blocks)


def apply_isotonic_binary(model: Sequence[IsotonicBlock], probability: Decimal) -> Decimal:
    """Apply an isotonic model, extending its terminal blocks conservatively."""

    if not model:
        raise CalibrationInputError("isotonic model is empty")
    checked = _probability(decimal_text(probability), label="probability")
    previous_upper: Decimal | None = None
    previous_value: Decimal | None = None
    for block in model:
        if block.weight <= _ZERO or block.total < _ZERO or block.total > block.weight:
            raise CalibrationInputError("isotonic block is invalid")
        if previous_upper is not None and block.upper < previous_upper:
            raise CalibrationInputError("isotonic blocks are unordered")
        if previous_value is not None and block.value < previous_value:
            raise CalibrationInputError("isotonic blocks decrease")
        if checked <= block.upper:
            return block.value
        previous_upper, previous_value = block.upper, block.value
    return model[-1].value


def isotonic_payload(model: Sequence[IsotonicBlock]) -> list[dict[str, str]]:
    return [
        {"upper": decimal_text(block.upper), "total": decimal_text(block.total), "weight": decimal_text(block.weight), "value": decimal_text(block.value)}
        for block in model
    ]


def fit_logistic_binary(observations: Sequence[BinaryObservation], *, iterations: int = 48) -> dict[str, Decimal]:
    """Fit a regularized Platt/logistic calibrator with deterministic Newton steps."""

    validate_temporal_order(observations)
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1 or iterations > 256:
        raise CalibrationInputError("iterations must be an integer in [1, 256]")
    intercept = _ZERO
    slope = _ONE
    regularization = Decimal("0.01")
    max_step = Decimal("0.25")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for _ in range(iterations):
            gradient_intercept = -regularization * intercept
            gradient_slope = -regularization * (slope - _ONE)
            h00 = regularization
            h01 = _ZERO
            h11 = regularization
            for observation in observations:
                feature = _bounded_logit(observation.probability)
                predicted = _sigmoid(intercept + slope * feature)
                residual = Decimal(observation.outcome) - predicted
                curvature = predicted * (_ONE - predicted)
                gradient_intercept += residual
                gradient_slope += residual * feature
                h00 += curvature
                h01 += curvature * feature
                h11 += curvature * feature * feature
            determinant = h00 * h11 - h01 * h01
            if determinant <= _ZERO:
                raise CalibrationInputError("logistic calibration Hessian is singular")
            step_intercept = (gradient_intercept * h11 - gradient_slope * h01) / determinant
            step_slope = (gradient_slope * h00 - gradient_intercept * h01) / determinant
            intercept += min(max(step_intercept, -max_step), max_step)
            slope += min(max(step_slope, -max_step), max_step)
    return {"intercept": intercept, "slope": slope, "iterations": Decimal(iterations)}


def apply_logistic_binary(model: Mapping[str, Decimal], probability: Decimal) -> Decimal:
    if set(model) != {"intercept", "slope", "iterations"}:
        raise CalibrationInputError("logistic model fields are invalid")
    intercept, slope = model["intercept"], model["slope"]
    if not isinstance(intercept, Decimal) or not isinstance(slope, Decimal) or not intercept.is_finite() or not slope.is_finite():
        raise CalibrationInputError("logistic model coefficients are invalid")
    checked = _probability(decimal_text(probability), label="probability")
    return _sigmoid(intercept + slope * _bounded_logit(checked))


def logistic_payload(model: Mapping[str, Decimal]) -> dict[str, str]:
    return {key: decimal_text(value) for key, value in model.items()}


def _temperature_candidates() -> tuple[Decimal, ...]:
    return tuple(Decimal(value) / Decimal("100") for value in range(80, 121))


def apply_temperature_multiclass(probabilities: Mapping[str, Decimal], temperature: Decimal) -> dict[str, Decimal]:
    """Apply a temperature transform in log space, retaining every outcome exactly."""

    if not isinstance(temperature, Decimal) or not temperature.is_finite() or temperature <= _ZERO:
        raise CalibrationInputError("temperature must be a positive finite Decimal")
    if not isinstance(probabilities, Mapping) or len(probabilities) < 3:
        raise CalibrationInputError("multiclass probabilities must contain at least three outcomes")
    parsed = {key: _probability(decimal_text(value), label="probabilities.%s" % key) for key, value in probabilities.items()}
    if abs(sum(parsed.values(), _ZERO) - _ONE) > Decimal("0.000000000001"):
        raise CalibrationInputError("multiclass probabilities must sum to one")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        weights = {key: (value.ln() / temperature).exp() for key, value in parsed.items()}
        total = sum(weights.values(), _ZERO)
        if total <= _ZERO:
            raise CalibrationInputError("temperature normalization is invalid")
        return {key: value / total for key, value in weights.items()}


def _temperature_loss(observations: Sequence[MulticlassObservation], temperature: Decimal) -> Decimal:
    total = _ZERO
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for observation in observations:
            calibrated = apply_temperature_multiclass(observation.probabilities, temperature)
            total -= calibrated[observation.outcome_id].ln()
    return total


def fit_temperature_multiclass(observations: Sequence[MulticlassObservation]) -> Decimal:
    """Choose the deterministic grid temperature with the lowest frozen-data log loss."""

    validate_temporal_order(observations)
    ranked = sorted((_temperature_loss(observations, candidate), candidate) for candidate in _temperature_candidates())
    if not ranked:
        raise CalibrationInputError("temperature candidates are unavailable")
    return ranked[0][1]


def binary_calibration_metrics(pairs: Iterable[tuple[Decimal, int]]) -> dict[str, Decimal]:
    rows = list(pairs)
    if len(rows) < 2:
        raise CalibrationInputError("at least two binary calibration pairs are required")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        probabilities = [probability for probability, _ in rows]
        outcomes = [Decimal(outcome) for _, outcome in rows]
        if any(probability <= _ZERO or probability >= _ONE for probability in probabilities):
            raise CalibrationInputError("calibration probabilities must be strictly within (0, 1)")
        mean_probability = sum(probabilities, _ZERO) / Decimal(len(probabilities))
        mean_outcome = sum(outcomes, _ZERO) / Decimal(len(outcomes))
        variance = sum((value - mean_probability) * (value - mean_probability) for value in probabilities)
        if variance <= _ZERO:
            raise CalibrationInputError("calibration probabilities have zero variance")
        covariance = sum((probability - mean_probability) * (outcome - mean_outcome) for probability, outcome in zip(probabilities, outcomes))
        slope = covariance / variance
        intercept = mean_outcome - slope * mean_probability
        grouped: dict[int, list[tuple[Decimal, Decimal]]] = {}
        for probability, outcome in zip(probabilities, outcomes):
            bucket = int((probability * Decimal("10")).to_integral_value(rounding=ROUND_FLOOR))
            grouped.setdefault(min(bucket, 9), []).append((probability, outcome))
        calibration_error = sum(
            (Decimal(len(group)) / Decimal(len(rows)))
            * abs(
                (sum((outcome for _, outcome in group), _ZERO) / Decimal(len(group)))
                - (sum((probability for probability, _ in group), _ZERO) / Decimal(len(group)))
            )
            for group in grouped.values()
        )
    return {"slope": slope, "intercept": intercept, "mean_absolute_error": calibration_error}


def multiclass_calibration_metrics(rows: Iterable[tuple[Mapping[str, Decimal], str]]) -> dict[str, Decimal]:
    pairs: list[tuple[Decimal, int]] = []
    for probabilities, outcome_id in rows:
        for candidate_id, probability in probabilities.items():
            pairs.append((probability, 1 if candidate_id == outcome_id else 0))
    return binary_calibration_metrics(pairs)


def metric_payload(metrics: Mapping[str, Decimal], *, slope_min: Decimal, slope_max: Decimal, intercept_abs_max: Decimal) -> dict[str, str | bool]:
    expected = {"slope", "intercept", "mean_absolute_error"}
    if set(metrics) != expected:
        raise CalibrationInputError("calibration metrics fields are invalid")
    slope = metrics["slope"]
    intercept = metrics["intercept"]
    return {
        "slope": decimal_text(slope),
        "intercept": decimal_text(intercept),
        "mean_absolute_error": decimal_text(metrics["mean_absolute_error"]),
        "eligible": slope_min <= slope <= slope_max and abs(intercept) <= intercept_abs_max,
    }
