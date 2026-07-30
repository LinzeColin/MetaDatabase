"""Deterministic pitcher-bullpen baseball residual model for ABD S09/P04.

The projection is calculated from frozen offense, starter, bullpen and park
features known at the supplied decision time.  It always remains market
anchored and fails closed to market-only/no-advice when the domain increment is
unavailable, unconfirmed or future-only.
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


MODEL_ID = "BASEBALL_PITCHER_BULLPEN_RESIDUAL"
MODEL_KEY = "baseball"
FEATURE_IDS = (
    "home_offense_index",
    "away_offense_index",
    "home_starter_ra",
    "away_starter_ra",
    "home_bullpen_ra",
    "away_bullpen_ra",
    "park_factor",
    "participation_status",
)
_ZERO = Decimal("0")
_ONE = Decimal("1")


class BaseballModelInputError(ValueError):
    """Raised when a baseball residual input is malformed or unsafe."""


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise BaseballModelInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise BaseballModelInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise BaseballModelInputError("%s must be finite" % label)
    return parsed


def _validated_features(selected: Mapping[str, Any]) -> dict[str, Decimal]:
    parsed = {feature: _decimal(selected[feature], label="features.%s" % feature) for feature in FEATURE_IDS if feature != "participation_status"}
    for feature in ("home_offense_index", "away_offense_index", "park_factor"):
        if not Decimal("0.25") <= parsed[feature] <= Decimal("2.50"):
            raise BaseballModelInputError("%s is outside the frozen plausible index range" % feature)
    for feature in ("home_starter_ra", "away_starter_ra", "home_bullpen_ra", "away_bullpen_ra"):
        if not _ZERO < parsed[feature] <= Decimal("15"):
            raise BaseballModelInputError("%s is outside the frozen plausible run-allowance range" % feature)
    return parsed


def _projection(selected: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    values = _validated_features(selected)
    with localcontext() as context:
        context.prec = 50
        home_opponent_ra = (values["away_starter_ra"] * Decimal("0.65")) + (values["away_bullpen_ra"] * Decimal("0.35"))
        away_opponent_ra = (values["home_starter_ra"] * Decimal("0.65")) + (values["home_bullpen_ra"] * Decimal("0.35"))
        home_runs = values["home_offense_index"] * values["park_factor"] * home_opponent_ra
        away_runs = values["away_offense_index"] * values["park_factor"] * away_opponent_ra
        home_probability = _ONE / (_ONE + (-((home_runs - away_runs) / Decimal("1.5"))).exp())
        away_probability = _ONE - home_probability
    return (
        {"HOME": decimal_text(home_probability), "AWAY": decimal_text(away_probability)},
        {
            "home_opponent_pitching_ra": decimal_text(home_opponent_ra),
            "away_opponent_pitching_ra": decimal_text(away_opponent_ra),
            "home_projected_runs": decimal_text(home_runs),
            "away_projected_runs": decimal_text(away_runs),
        },
    )


def build_baseball_market_anchored_prediction(
    case: Mapping[str, Any],
    niche_registry: Mapping[str, Any],
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a baseball residual only after the time-safe feature gate passes."""

    try:
        validate_niche_fallback_registry(niche_registry)
        snapshot = build_asof_snapshot(
            case,
            required_feature_ids=FEATURE_IDS,
            required_competitors=("HOME", "AWAY"),
            market_family="binary",
        )
    except RacingModelInputError as exc:
        raise BaseballModelInputError(str(exc)) from exc
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
        raise BaseballModelInputError(str(exc)) from exc
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
        "pitcher_bullpen_projection": projection,
        "market_anchored_prediction": prediction,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }
