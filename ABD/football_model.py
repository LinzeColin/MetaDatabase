"""Deterministic hierarchical football residual model for ABD S09/P03.

Only frozen observations known at or before the supplied decision timestamp are
eligible.  League-level rates and team-level effects produce score-distribution
inputs; any missing, future-only, unconfirmed, or tail-unsafe increment falls
back to the untouched market vector with zero residual weight.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from generic_residual import (
    GenericResidualInputError,
    calculate_market_anchored_residual,
    canonical_json_bytes,
    decimal_text,
)
from score_models import ScoreModelInputError, build_score_projection, validate_distribution_test_registry


MODEL_ID = "FOOTBALL_HIERARCHICAL_SCORE_RESIDUAL"
MODEL_KEY = "football"
DECIMAL_PRECISION = 50
FUTURE_INFORMATION_TOLERANCE = 0
FEATURE_IDS = (
    "league_home_goal_rate",
    "league_away_goal_rate",
    "home_attack_effect",
    "home_defense_effect",
    "away_attack_effect",
    "away_defense_effect",
    "home_advantage_effect",
    "dixon_coles_rho",
    "goal_dispersion",
    "participation_status",
)
_ZERO = Decimal("0")
_ONE = Decimal("1")
_CASE_ID = re.compile(r"[A-Z][A-Z0-9_:-]{1,47}")
_OUTCOME_ID = re.compile(r"[A-Z][A-Z0-9_:-]{0,79}")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$")
_REQUIRED_OUTCOMES = ("HOME", "DRAW", "AWAY")


class FootballModelInputError(ValueError):
    """Raised when a football residual input is not time-safe or deterministic."""


def _identifier(value: Any, *, label: str, pattern: re.Pattern[str] = _OUTCOME_ID) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise FootballModelInputError("%s is not a stable identifier" % label)
    return value


def _timestamp(value: Any, *, label: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise FootballModelInputError("%s must include an explicit timezone" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FootballModelInputError("%s is not an ISO timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FootballModelInputError("%s must include an explicit timezone" % label)
    return parsed, value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise FootballModelInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise FootballModelInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise FootballModelInputError("%s must be finite" % label)
    return parsed


def _probability(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO < parsed < _ONE:
        raise FootballModelInputError("%s must be strictly between zero and one" % label)
    return parsed


def load_distribution_registry(path: Path | str) -> Mapping[str, Any]:
    """Read the local frozen score-model policy without any external access."""

    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FootballModelInputError("distribution registry cannot be read") from exc
    try:
        return validate_distribution_test_registry(registry)
    except ScoreModelInputError as exc:
        raise FootballModelInputError("distribution registry drifted: %s" % exc) from exc


def _select_known_observation(value: Any, decision_at: datetime, *, label: str) -> tuple[Any, str] | None:
    if not isinstance(value, list):
        raise FootballModelInputError("%s must be an observation list" % label)
    eligible: list[tuple[datetime, Any, str]] = []
    for index, observation in enumerate(value):
        if not isinstance(observation, Mapping) or set(observation) != {"known_at", "value"}:
            raise FootballModelInputError("%s[%d] must contain only known_at and value" % (label, index))
        known_at, rendered = _timestamp(observation["known_at"], label="%s[%d].known_at" % (label, index))
        if known_at <= decision_at:
            eligible.append((known_at, observation["value"], rendered))
    if not eligible:
        return None
    newest_time = max(item[0] for item in eligible)
    newest = [item for item in eligible if item[0] == newest_time]
    if len(newest) != 1:
        raise FootballModelInputError("%s has ambiguous observations at the same known_at" % label)
    return newest[0][1], newest[0][2]


def _validate_feature_value(feature_id: str, value: Any, *, label: str) -> str:
    if feature_id == "participation_status":
        if not isinstance(value, str):
            raise FootballModelInputError("%s participation status must be text" % label)
        return value
    parsed = _decimal(value, label=label)
    if feature_id in {"league_home_goal_rate", "league_away_goal_rate"} and not _ZERO < parsed <= Decimal("3"):
        raise FootballModelInputError("%s goal-rate baseline is outside (0, 3]" % label)
    if feature_id in {
        "home_attack_effect",
        "home_defense_effect",
        "away_attack_effect",
        "away_defense_effect",
        "home_advantage_effect",
    } and not Decimal("-1") <= parsed <= _ONE:
        raise FootballModelInputError("%s hierarchy effect is outside [-1, 1]" % label)
    if feature_id == "dixon_coles_rho" and not Decimal("-0.10") <= parsed <= Decimal("0.10"):
        raise FootballModelInputError("%s Dixon-Coles rho is outside [-0.10, 0.10]" % label)
    if feature_id == "goal_dispersion" and not Decimal("0.1") <= parsed <= Decimal("100"):
        raise FootballModelInputError("%s negative-binomial dispersion is outside [0.1, 100]" % label)
    return decimal_text(parsed)


def _market(case: Mapping[str, Any], competitors: tuple[str, str, str]) -> dict[str, Decimal]:
    value = case.get("market_probabilities")
    if not isinstance(value, Mapping) or set(value) != set(competitors):
        raise FootballModelInputError("market probabilities must exactly match HOME, DRAW and AWAY")
    probabilities = {
        outcome_id: _probability(value[outcome_id], label="market_probabilities.%s" % outcome_id) for outcome_id in competitors
    }
    if sum(probabilities.values(), _ZERO) != _ONE:
        raise FootballModelInputError("market probabilities must sum exactly to one")
    return probabilities


def _feature_snapshot(case: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_distribution_test_registry(registry)
    except ScoreModelInputError as exc:
        raise FootballModelInputError("distribution registry drifted: %s" % exc) from exc
    identifier = _identifier(case.get("id"), label="case.id", pattern=_CASE_ID)
    decision_at, decision_text = _timestamp(case.get("decision_at"), label="decision_at")
    event_at, event_text = _timestamp(case.get("event_at"), label="event_at")
    if event_at <= decision_at:
        raise FootballModelInputError("event_at must be strictly after decision_at")
    raw_competitors = case.get("competitors")
    if raw_competitors != list(_REQUIRED_OUTCOMES):
        raise FootballModelInputError("competitors must be exactly HOME, DRAW, AWAY in canonical order")
    competitors = _REQUIRED_OUTCOMES
    market = _market(case, competitors)
    features = case.get("features")
    if not isinstance(features, Mapping) or set(features) != set(FEATURE_IDS):
        raise FootballModelInputError("football case must declare every required feature")
    availability = []
    selected: dict[str, str] = {}
    reasons: list[str] = []
    for feature_id in FEATURE_IDS:
        observation = _select_known_observation(features[feature_id], decision_at, label="features.%s" % feature_id)
        if observation is None:
            availability.append({"feature_id": feature_id, "status": "UNAVAILABLE_AT_DECISION"})
            reasons.append("FEATURE_UNAVAILABLE_AT_DECISION:%s" % feature_id)
            continue
        raw_value, known_at = observation
        value = _validate_feature_value(feature_id, raw_value, label="features.%s.value" % feature_id)
        if feature_id == "participation_status" and value != "CONFIRMED":
            availability.append({"feature_id": feature_id, "status": "UNCONFIRMED_AT_DECISION", "selected_known_at": known_at})
            reasons.append("PARTICIPATION_UNCONFIRMED_AT_DECISION")
            continue
        selected[feature_id] = value
        availability.append({"feature_id": feature_id, "status": "AVAILABLE_AT_DECISION", "selected_known_at": known_at})
    return {
        "id": identifier,
        "decision_at": decision_text,
        "event_at": event_text,
        "competitors": competitors,
        "market": market,
        "availability": availability,
        "selected": selected,
        "temporal_safe": not reasons,
        "reason_codes": sorted(set(reasons)),
    }


def _derived_rates(selected: Mapping[str, str]) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        home = Decimal(selected["league_home_goal_rate"]) * (
            Decimal(selected["home_attack_effect"])
            - Decimal(selected["away_defense_effect"])
            + Decimal(selected["home_advantage_effect"])
        ).exp()
        away = Decimal(selected["league_away_goal_rate"]) * (
            Decimal(selected["away_attack_effect"]) - Decimal(selected["home_defense_effect"])
        ).exp()
    if not _ZERO < home <= Decimal("3") or not _ZERO < away <= Decimal("3"):
        raise FootballModelInputError("hierarchical rates exceed score-model bounds")
    return home, away


def build_football_market_anchored_prediction(
    case: Mapping[str, Any],
    distribution_registry: Mapping[str, Any],
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a frozen football residual only when all score-model gates pass."""

    if not isinstance(case, Mapping):
        raise FootballModelInputError("football case must be an object")
    snapshot = _feature_snapshot(case, distribution_registry)
    requested_weight = case.get("requested_residual_weight")
    if not isinstance(requested_weight, str):
        raise FootballModelInputError("requested_residual_weight must be a decimal string")
    residual_input: dict[str, Any] = {
        "id": snapshot["id"],
        "market_family": "multinomial",
        "market_probabilities": {outcome: decimal_text(snapshot["market"][outcome]) for outcome in snapshot["competitors"]},
        "requested_residual_weight": requested_weight,
    }
    projection: dict[str, Any] | None = None
    feature_bundle_sha256: str | None = None
    derived_rates: dict[str, str] | None = None
    reason_codes = list(snapshot["reason_codes"])
    if snapshot["temporal_safe"]:
        home_rate, away_rate = _derived_rates(snapshot["selected"])
        derived_rates = {"home_goal_rate": decimal_text(home_rate), "away_goal_rate": decimal_text(away_rate)}
        try:
            projection = build_score_projection(
                derived_rates["home_goal_rate"],
                derived_rates["away_goal_rate"],
                snapshot["selected"]["dixon_coles_rho"],
                snapshot["selected"]["goal_dispersion"],
                distribution_registry,
            )
        except ScoreModelInputError as exc:
            raise FootballModelInputError("score projection failed: %s" % exc) from exc
        mapping = projection["market_mappings"]["ONE_X_TWO"]
        if projection["mapping_status"] == "COMPLETE_WITHIN_TAIL_TOLERANCE" and mapping["status"] == "COMPLETE_WITHIN_TAIL_TOLERANCE":
            candidate = mapping["outcomes"]
            if set(candidate) != set(snapshot["competitors"]):
                raise FootballModelInputError("score mapping outcomes do not match the market")
            feature_bundle = {
                "model_id": MODEL_ID,
                "case_id": snapshot["id"],
                "decision_at": snapshot["decision_at"],
                "selected_features": snapshot["selected"],
                "derived_goal_rates": derived_rates,
                "market_mapping": candidate,
                "tail_tolerance": projection["tail_tolerance"],
            }
            feature_bundle_sha256 = hashlib.sha256(canonical_json_bytes(feature_bundle)).hexdigest()
            residual_input["candidate_residual_probabilities"] = candidate
            residual_input["domain_increment"] = {
                "status": "VERIFIED",
                "reproducible": True,
                "evidence_sha256": feature_bundle_sha256,
                "frozen_window_id": "FOOTBALL_%s_ASOF" % snapshot["id"],
            }
        else:
            reason_codes.append("SCORE_TAIL_ABOVE_TOLERANCE")
            residual_input["domain_increment"] = {"status": "UNAVAILABLE", "reproducible": False}
    else:
        residual_input["domain_increment"] = {"status": "UNAVAILABLE", "reproducible": False}
    try:
        market_prediction = calculate_market_anchored_residual(residual_input, market_family_registry, parameters)
    except GenericResidualInputError as exc:
        raise FootballModelInputError("market anchoring failed: %s" % exc) from exc
    return {
        "id": snapshot["id"],
        "model_id": MODEL_ID,
        "decision_at": snapshot["decision_at"],
        "event_at": snapshot["event_at"],
        "temporal_safe": snapshot["temporal_safe"],
        "future_information_tolerance": FUTURE_INFORMATION_TOLERANCE,
        "feature_availability": snapshot["availability"],
        "reason_codes": sorted(set(reason_codes)),
        "derived_goal_rates": derived_rates,
        "score_projection": projection,
        "feature_bundle_sha256": feature_bundle_sha256,
        "market_anchored_prediction": market_prediction,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }
