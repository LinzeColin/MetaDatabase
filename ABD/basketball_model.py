"""Deterministic pace-efficiency basketball residual model for ABD S09/P04.

Only frozen observations known by the supplied decision timestamp are eligible.
Any unavailable, future-only or unconfirmed input takes the market-only path.
The bounded result is decision support data, never a recommendation or order.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
import hashlib
from typing import Any, Mapping

from generic_residual import canonical_json_bytes, decimal_text
from racing_model import (
    FUTURE_INFORMATION_TOLERANCE,
    RacingModelInputError,
    _generic_prediction,
    build_asof_snapshot,
    validate_niche_fallback_registry,
)


MODEL_ID = "BASKETBALL_PACE_EFFICIENCY_RESIDUAL"
MODEL_KEY = "basketball"
FEATURE_IDS = (
    "home_pace",
    "away_pace",
    "home_offensive_rating",
    "home_defensive_rating",
    "away_offensive_rating",
    "away_defensive_rating",
    "home_advantage_points",
    "participation_status",
)
_ZERO = Decimal("0")
_ONE = Decimal("1")


class BasketballModelInputError(ValueError):
    """Raised when a basketball residual input is malformed or unsafe."""


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise BasketballModelInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise BasketballModelInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise BasketballModelInputError("%s must be finite" % label)
    return parsed


def _validated_features(selected: Mapping[str, Any]) -> dict[str, Decimal]:
    parsed = {feature: _decimal(selected[feature], label="features.%s" % feature) for feature in FEATURE_IDS if feature != "participation_status"}
    for feature in ("home_pace", "away_pace"):
        if not Decimal("70") <= parsed[feature] <= Decimal("130"):
            raise BasketballModelInputError("%s is outside the frozen plausible pace range" % feature)
    for feature in (
        "home_offensive_rating",
        "home_defensive_rating",
        "away_offensive_rating",
        "away_defensive_rating",
    ):
        if not Decimal("70") <= parsed[feature] <= Decimal("150"):
            raise BasketballModelInputError("%s is outside the frozen plausible efficiency range" % feature)
    if not Decimal("-20") <= parsed["home_advantage_points"] <= Decimal("20"):
        raise BasketballModelInputError("home_advantage_points is outside [-20, 20]")
    return parsed


def _projection(selected: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    values = _validated_features(selected)
    with localcontext() as context:
        context.prec = 50
        expected_pace = (values["home_pace"] + values["away_pace"]) / Decimal("2")
        home_points = expected_pace * (values["home_offensive_rating"] + values["away_defensive_rating"]) / Decimal("200")
        away_points = expected_pace * (values["away_offensive_rating"] + values["home_defensive_rating"]) / Decimal("200")
        margin = (home_points - away_points) + values["home_advantage_points"]
        home_probability = _ONE / (_ONE + (-(margin / Decimal("12"))).exp())
        away_probability = _ONE - home_probability
    return (
        {"HOME": decimal_text(home_probability), "AWAY": decimal_text(away_probability)},
        {
            "expected_pace": decimal_text(expected_pace),
            "home_expected_points": decimal_text(home_points),
            "away_expected_points": decimal_text(away_points),
            "home_expected_margin": decimal_text(margin),
        },
    )


def build_basketball_market_anchored_prediction(
    case: Mapping[str, Any],
    niche_registry: Mapping[str, Any],
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a basketball residual only after the time-safe feature gate passes."""

    try:
        validate_niche_fallback_registry(niche_registry)
        snapshot = build_asof_snapshot(
            case,
            required_feature_ids=FEATURE_IDS,
            required_competitors=("HOME", "AWAY"),
            market_family="binary",
        )
    except RacingModelInputError as exc:
        raise BasketballModelInputError(str(exc)) from exc
    candidate: dict[str, str] | None = None
    projection: dict[str, str] | None = None
    feature_bundle: dict[str, Any] | None = None
    if snapshot["temporal_safe"]:
        candidate, projection = _projection(snapshot["selected"])
        feature_bundle = {
            "model_id": MODEL_ID,
            "case_id": snapshot["id"],
            "decision_at": snapshot["decision_at"],
            "selected_features": snapshot["selected"],
            "projection": projection,
            "candidate_probabilities": candidate,
        }
    try:
        prediction = _generic_prediction(
            snapshot,
            market_family="binary",
            candidate_probabilities=candidate,
            feature_bundle=feature_bundle,
            market_family_registry=market_family_registry,
            parameters=parameters,
        )
    except RacingModelInputError as exc:
        raise BasketballModelInputError(str(exc)) from exc
    return {
        "id": snapshot["id"],
        "model_id": MODEL_ID,
        "decision_at": snapshot["decision_at"],
        "event_at": snapshot["event_at"],
        "temporal_safe": snapshot["temporal_safe"],
        "future_information_tolerance": FUTURE_INFORMATION_TOLERANCE,
        "feature_availability": snapshot["availability"],
        "reason_codes": snapshot["reason_codes"],
        "model_evidence_status": "FROZEN_REPLAY_VERIFIED" if feature_bundle is not None else "UNPROVEN_OR_UNAVAILABLE",
        "feature_bundle_sha256": None if feature_bundle is None else hashlib.sha256(canonical_json_bytes(feature_bundle)).hexdigest(),
        "pace_efficiency_projection": projection,
        "market_anchored_prediction": prediction,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }
