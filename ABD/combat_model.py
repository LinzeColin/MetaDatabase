"""Deterministic, time-safe combat-sport residual model for ABD S09/P02.

This model has the same fail-closed temporal contract as the tennis model: it
uses only the latest feature observation known at or before ``decision_at``.
Missing readiness or participation evidence returns the untouched market
baseline and never creates a recommendation or order capability.
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


MODEL_ID = "COMBAT_RATING_STYLE_READINESS_RESIDUAL"
MODEL_KEY = "combat"
DECIMAL_PRECISION = 50
FUTURE_INFORMATION_TOLERANCE = 0
FEATURE_IDS = (
    "dynamic_rating",
    "strike_defense_index",
    "rest_hours",
    "travel_km",
    "participation_status",
)
_ZERO = Decimal("0")
_ONE = Decimal("1")
_MIN_CANDIDATE_PROBABILITY = Decimal("0.000001")
_MAX_CANDIDATE_PROBABILITY = Decimal("0.999999")
_CASE_ID = re.compile(r"[A-Z][A-Z0-9_:-]{1,47}")
_OUTCOME_ID = re.compile(r"[A-Z][A-Z0-9_:-]{0,79}")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$")


class CombatModelInputError(ValueError):
    """Raised when a combat residual input is not time-safe or deterministic."""


def _identifier(value: Any, *, label: str, pattern: re.Pattern[str] = _OUTCOME_ID) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise CombatModelInputError("%s is not a stable identifier" % label)
    return value


def _timestamp(value: Any, *, label: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise CombatModelInputError("%s must include an explicit timezone" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CombatModelInputError("%s is not an ISO timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CombatModelInputError("%s must include an explicit timezone" % label)
    return parsed, value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise CombatModelInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CombatModelInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise CombatModelInputError("%s must be finite" % label)
    return parsed


def _probability(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO < parsed < _ONE:
        raise CombatModelInputError("%s must be strictly between zero and one" % label)
    return parsed


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return min(max(value, lower), upper)


def _registry_model(registry: Any) -> Mapping[str, Any]:
    if not isinstance(registry, Mapping):
        raise CombatModelInputError("feature availability registry must be an object")
    if registry.get("schema_version") != "1.0.0" or registry.get("product_version") != "0.0.0.1":
        raise CombatModelInputError("feature availability registry version is invalid")
    expected_policy = {
        "future_information_tolerance": 0,
        "timezone_required": True,
        "selection_rule": "LATEST_KNOWN_AT_OR_BEFORE_DECISION",
        "missing_required_feature_action": "MARKET_ONLY_ZERO_RESIDUAL",
        "unconfirmed_participation_action": "MARKET_ONLY_ZERO_RESIDUAL",
        "external_network_accessed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
    }
    if registry.get("policy") != expected_policy:
        raise CombatModelInputError("feature availability policy drifted")
    models = registry.get("models")
    if not isinstance(models, list) or len(models) != 2 or not all(isinstance(row, Mapping) for row in models):
        raise CombatModelInputError("feature availability models are invalid")
    if [row.get("id") for row in models] != ["tennis", "combat"]:
        raise CombatModelInputError("feature availability model order is invalid")
    row = models[1]
    if (
        row.get("id") != MODEL_KEY
        or row.get("model_id") != MODEL_ID
        or row.get("market_family") != "binary"
        or row.get("required_feature_ids") != list(FEATURE_IDS)
        or row.get("residual_weight_cap_parameter") != "residual_weight_alpha_beta_max"
        or row.get("unavailable_action") != "MARKET_ONLY_ZERO_RESIDUAL"
    ):
        raise CombatModelInputError("combat feature model contract drifted")
    return row


def load_feature_availability_registry(path: Path | str) -> Mapping[str, Any]:
    """Read and validate the local frozen feature-availability registry."""

    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CombatModelInputError("feature availability registry cannot be read") from exc
    _registry_model(registry)
    return registry


def _select_known_observation(value: Any, decision_at: datetime, *, label: str) -> tuple[Any, str] | None:
    if not isinstance(value, list):
        raise CombatModelInputError("%s must be an observation list" % label)
    eligible: list[tuple[datetime, Any, str]] = []
    for index, observation in enumerate(value):
        if not isinstance(observation, Mapping) or set(observation) != {"known_at", "value"}:
            raise CombatModelInputError("%s[%d] must contain only known_at and value" % (label, index))
        known_at, rendered = _timestamp(observation["known_at"], label="%s[%d].known_at" % (label, index))
        if known_at <= decision_at:
            eligible.append((known_at, observation["value"], rendered))
    if not eligible:
        return None
    newest_time = max(item[0] for item in eligible)
    newest = [item for item in eligible if item[0] == newest_time]
    if len(newest) != 1:
        raise CombatModelInputError("%s has ambiguous observations at the same known_at" % label)
    return newest[0][1], newest[0][2]


def _validate_feature_value(feature_id: str, value: Any, *, label: str) -> str:
    if feature_id == "participation_status":
        if not isinstance(value, str):
            raise CombatModelInputError("%s participation status must be text" % label)
        return value
    parsed = _decimal(value, label=label)
    if feature_id == "dynamic_rating" and not _ZERO <= parsed <= Decimal("3000"):
        raise CombatModelInputError("%s dynamic rating is outside the bounded range" % label)
    if feature_id == "strike_defense_index" and not _ZERO < parsed < _ONE:
        raise CombatModelInputError("%s must be strictly between zero and one" % label)
    if feature_id == "rest_hours" and not _ZERO <= parsed <= Decimal("720"):
        raise CombatModelInputError("%s rest hours are outside the bounded range" % label)
    if feature_id == "travel_km" and not _ZERO <= parsed <= Decimal("40000"):
        raise CombatModelInputError("%s travel distance is outside the bounded range" % label)
    return decimal_text(parsed)


def _market(case: Mapping[str, Any], competitors: tuple[str, str]) -> dict[str, Decimal]:
    value = case.get("market_probabilities")
    if not isinstance(value, Mapping) or set(value) != set(competitors):
        raise CombatModelInputError("market probabilities must exactly match the two competitors")
    probabilities = {outcome_id: _probability(value[outcome_id], label="market_probabilities.%s" % outcome_id) for outcome_id in competitors}
    if sum(probabilities.values(), _ZERO) != _ONE:
        raise CombatModelInputError("market probabilities must sum exactly to one")
    return probabilities


def _feature_snapshot(case: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    _registry_model(registry)
    identifier = _identifier(case.get("id"), label="case.id", pattern=_CASE_ID)
    decision_at, decision_text = _timestamp(case.get("decision_at"), label="decision_at")
    event_at, event_text = _timestamp(case.get("event_at"), label="event_at")
    if event_at <= decision_at:
        raise CombatModelInputError("event_at must be strictly after decision_at")
    raw_competitors = case.get("competitors")
    if not isinstance(raw_competitors, list) or len(raw_competitors) != 2:
        raise CombatModelInputError("competitors must contain exactly two outcome identifiers")
    competitors = tuple(_identifier(item, label="competitors") for item in raw_competitors)
    if len(set(competitors)) != 2:
        raise CombatModelInputError("competitors must be unique")
    market = _market(case, competitors)
    fighters = case.get("fighters")
    if not isinstance(fighters, Mapping) or set(fighters) != set(competitors):
        raise CombatModelInputError("fighters must exactly match competitors")
    availability = []
    selected: dict[str, dict[str, str]] = {}
    reasons: list[str] = []
    for outcome_id in competitors:
        fighter = fighters[outcome_id]
        if not isinstance(fighter, Mapping) or set(fighter) != set(FEATURE_IDS):
            raise CombatModelInputError("fighter %s must declare every required feature" % outcome_id)
        selected[outcome_id] = {}
        for feature_id in FEATURE_IDS:
            observation = _select_known_observation(fighter[feature_id], decision_at, label="fighters.%s.%s" % (outcome_id, feature_id))
            if observation is None:
                availability.append({"outcome_id": outcome_id, "feature_id": feature_id, "status": "UNAVAILABLE_AT_DECISION"})
                reasons.append("FEATURE_UNAVAILABLE_AT_DECISION:%s:%s" % (outcome_id, feature_id))
                continue
            raw_value, known_at = observation
            value = _validate_feature_value(feature_id, raw_value, label="fighters.%s.%s.value" % (outcome_id, feature_id))
            if feature_id == "participation_status" and value != "CONFIRMED":
                availability.append(
                    {
                        "outcome_id": outcome_id,
                        "feature_id": feature_id,
                        "status": "UNCONFIRMED_AT_DECISION",
                        "selected_known_at": known_at,
                    }
                )
                reasons.append("PARTICIPATION_UNCONFIRMED_AT_DECISION:%s" % outcome_id)
                continue
            selected[outcome_id][feature_id] = value
            availability.append(
                {
                    "outcome_id": outcome_id,
                    "feature_id": feature_id,
                    "status": "AVAILABLE_AT_DECISION",
                    "selected_known_at": known_at,
                }
            )
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


def _residual_signal(selected: Mapping[str, Mapping[str, str]], competitors: tuple[str, str]) -> Decimal:
    first, second = competitors
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        first_values = selected[first]
        second_values = selected[second]
        rating = _clamp(
            (Decimal(first_values["dynamic_rating"]) - Decimal(second_values["dynamic_rating"])) / Decimal("400"),
            Decimal("-1"),
            _ONE,
        )
        style = _clamp(
            Decimal(first_values["strike_defense_index"]) - Decimal(second_values["strike_defense_index"]),
            Decimal("-1"),
            _ONE,
        )
        readiness = _clamp(
            ((Decimal(first_values["rest_hours"]) - Decimal(second_values["rest_hours"])) / Decimal("96"))
            - ((Decimal(first_values["travel_km"]) - Decimal(second_values["travel_km"])) / Decimal("2000")),
            Decimal("-1"),
            _ONE,
        )
        return _clamp((rating * Decimal("0.55")) + (style * Decimal("0.30")) + (readiness * Decimal("0.15")), Decimal("-1"), _ONE)


def build_combat_market_anchored_prediction(
    case: Mapping[str, Any],
    feature_registry: Mapping[str, Any],
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one combat residual result without accepting future information."""

    if not isinstance(case, Mapping):
        raise CombatModelInputError("combat case must be an object")
    snapshot = _feature_snapshot(case, feature_registry)
    competitors = snapshot["competitors"]
    market = snapshot["market"]
    requested_weight = case.get("requested_residual_weight")
    if not isinstance(requested_weight, str):
        raise CombatModelInputError("requested_residual_weight must be a decimal string")
    residual_input: dict[str, Any] = {
        "id": snapshot["id"],
        "market_family": "binary",
        "market_probabilities": {outcome_id: decimal_text(market[outcome_id]) for outcome_id in competitors},
        "requested_residual_weight": requested_weight,
    }
    feature_bundle_sha256: str | None = None
    residual_signal = _ZERO
    if snapshot["temporal_safe"]:
        residual_signal = _residual_signal(snapshot["selected"], competitors)
        first, second = competitors
        candidate_first = _clamp(market[first] + (residual_signal * Decimal("0.05")), _MIN_CANDIDATE_PROBABILITY, _MAX_CANDIDATE_PROBABILITY)
        candidate_second = _ONE - candidate_first
        feature_bundle = {
            "model_id": MODEL_ID,
            "case_id": snapshot["id"],
            "decision_at": snapshot["decision_at"],
            "competitors": [
                {"outcome_id": outcome_id, "features": snapshot["selected"][outcome_id]}
                for outcome_id in competitors
            ],
        }
        feature_bundle_sha256 = hashlib.sha256(canonical_json_bytes(feature_bundle)).hexdigest()
        residual_input["candidate_residual_probabilities"] = {
            first: decimal_text(candidate_first),
            second: decimal_text(candidate_second),
        }
        residual_input["domain_increment"] = {
            "status": "VERIFIED",
            "reproducible": True,
            "evidence_sha256": feature_bundle_sha256,
            "frozen_window_id": "COMBAT_%s_ASOF" % snapshot["id"],
        }
    else:
        residual_input["domain_increment"] = {"status": "UNAVAILABLE", "reproducible": False}
    try:
        market_prediction = calculate_market_anchored_residual(residual_input, market_family_registry, parameters)
    except GenericResidualInputError as exc:
        raise CombatModelInputError("market anchoring failed: %s" % exc) from exc
    return {
        "id": snapshot["id"],
        "model_id": MODEL_ID,
        "decision_at": snapshot["decision_at"],
        "event_at": snapshot["event_at"],
        "temporal_safe": snapshot["temporal_safe"],
        "future_information_tolerance": FUTURE_INFORMATION_TOLERANCE,
        "feature_availability": snapshot["availability"],
        "reason_codes": snapshot["reason_codes"],
        "feature_bundle_sha256": feature_bundle_sha256,
        "residual_signal": decimal_text(residual_signal),
        "market_anchored_prediction": market_prediction,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }
