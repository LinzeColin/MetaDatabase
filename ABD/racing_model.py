"""Deterministic racing and niche market-only fallback for ABD S09/P04.

The racing calculation consumes frozen feature histories only.  It selects the
latest value known at or before the decision time, derives Plackett-Luce win
probabilities and Harville exacta probabilities, and then lets the generic
market residual gate decide whether a bounded residual is allowed.  Missing,
future-only, unconfirmed, or unproven inputs remain market-only.  This module
has no network, account, recommendation, order, deployment, or waiting path.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from generic_residual import (
    GenericResidualInputError,
    calculate_market_anchored_residual,
    canonical_json_bytes,
    decimal_text,
)


MODEL_ID = "RACING_PLACKETT_LUCE_HARVILLE_RESIDUAL"
MODEL_KEY = "racing"
NICHE_MODEL_ID = "NICHE_MARKET_ONLY_FALLBACK"
DECIMAL_PRECISION = 50
FUTURE_INFORMATION_TOLERANCE = 0
RACING_FEATURE_IDS = ("runner_strengths", "participation_status")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_CASE_ID = re.compile(r"[A-Z][A-Z0-9_:-]{1,47}")
_OUTCOME_ID = re.compile(r"[A-Z][A-Z0-9_:-]{0,79}")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$")


class RacingModelInputError(ValueError):
    """Raised when a racing or niche fallback input is not safe to replay."""


def _identifier(value: Any, *, label: str, pattern: re.Pattern[str] = _OUTCOME_ID) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise RacingModelInputError("%s is not a stable identifier" % label)
    return value


def _timestamp(value: Any, *, label: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise RacingModelInputError("%s must include an explicit timezone" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RacingModelInputError("%s is not an ISO timestamp" % label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RacingModelInputError("%s must include an explicit timezone" % label)
    return parsed, value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise RacingModelInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RacingModelInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise RacingModelInputError("%s must be finite" % label)
    return parsed


def _select_known_observation(value: Any, decision_at: datetime, *, label: str) -> tuple[Any, str] | None:
    if not isinstance(value, list):
        raise RacingModelInputError("%s must be an observation list" % label)
    eligible: list[tuple[datetime, Any, str]] = []
    for index, observation in enumerate(value):
        if not isinstance(observation, Mapping) or set(observation) != {"known_at", "value"}:
            raise RacingModelInputError("%s[%d] must contain only known_at and value" % (label, index))
        known_at, rendered = _timestamp(observation["known_at"], label="%s[%d].known_at" % (label, index))
        if known_at <= decision_at:
            eligible.append((known_at, observation["value"], rendered))
    if not eligible:
        return None
    newest_time = max(item[0] for item in eligible)
    newest = [item for item in eligible if item[0] == newest_time]
    if len(newest) != 1:
        raise RacingModelInputError("%s has ambiguous observations at the same known_at" % label)
    return newest[0][1], newest[0][2]


def _model_row(registry: Mapping[str, Any], model_id: str) -> Mapping[str, Any]:
    models = registry.get("models")
    if not isinstance(models, list):
        raise RacingModelInputError("niche fallback models are missing")
    matches = [row for row in models if isinstance(row, Mapping) and row.get("model_id") == model_id]
    if len(matches) != 1:
        raise RacingModelInputError("niche fallback model declaration is missing or duplicated")
    return matches[0]


def validate_niche_fallback_registry(value: Any) -> Mapping[str, Any]:
    """Validate the complete S09/P04 policy and fail closed on policy drift."""

    if not isinstance(value, Mapping):
        raise RacingModelInputError("niche fallback registry must be an object")
    expected_root = {
        "schema_version": "1.0.0",
        "product_version": "0.0.0.1",
        "registry_id": "NICHES-S09-P04-MARKET-ONLY",
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
    }
    if any(value.get(key) != expected for key, expected in expected_root.items()):
        raise RacingModelInputError("niche fallback registry identity is invalid")
    policy = value.get("policy")
    expected_policy = {
        "future_information_tolerance": 0,
        "timezone_required": True,
        "unproven_domain_model_action": "MARKET_ONLY_OR_NO_ADVICE",
        "unavailable_domain_model_action": "MARKET_ONLY_OR_NO_ADVICE",
        "niche_default_action": "MARKET_ONLY_OR_NO_ADVICE",
        "external_network_accessed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
    }
    if not isinstance(policy, Mapping) or any(policy.get(key) != expected for key, expected in expected_policy.items()):
        raise RacingModelInputError("niche fallback policy drifted")
    expected_models = {
        "RACING_PLACKETT_LUCE_HARVILLE_RESIDUAL": {
            "id": "racing",
            "market_family": "futures",
            "required_snapshot_keys": ["runner_strengths", "participation_status"],
        },
        "BASKETBALL_PACE_EFFICIENCY_RESIDUAL": {
            "id": "basketball",
            "market_family": "binary",
            "required_snapshot_keys": [
                "home_pace",
                "away_pace",
                "home_offensive_rating",
                "home_defensive_rating",
                "away_offensive_rating",
                "away_defensive_rating",
                "home_advantage_points",
                "participation_status",
            ],
        },
        "BASEBALL_PITCHER_BULLPEN_RESIDUAL": {
            "id": "baseball",
            "market_family": "binary",
            "required_snapshot_keys": [
                "home_offense_index",
                "away_offense_index",
                "home_starter_ra",
                "away_starter_ra",
                "home_bullpen_ra",
                "away_bullpen_ra",
                "park_factor",
                "participation_status",
            ],
        },
    }
    models = value.get("models")
    if not isinstance(models, list) or len(models) != len(expected_models):
        raise RacingModelInputError("niche fallback must declare exactly three scoped models")
    for model_id, expected in expected_models.items():
        row = _model_row(value, model_id)
        if any(row.get(key) != item for key, item in expected.items()) or row.get("unproven_action") != "MARKET_ONLY_OR_NO_ADVICE":
            raise RacingModelInputError("niche fallback model policy drifted: %s" % model_id)
    niche = value.get("niche_market_only")
    expected_niche = {
        "default_action": "MARKET_ONLY_OR_NO_ADVICE",
        "unknown_domain_action": "MARKET_ONLY_OR_NO_ADVICE",
        "prohibited_actions": ["MODEL_ONLY", "RECOMMENDATION", "ORDER_SUBMISSION"],
        "examples": ["RUGBY", "CRICKET", "ESPORTS", "OTHER"],
    }
    if not isinstance(niche, Mapping) or any(niche.get(key) != expected for key, expected in expected_niche.items()):
        raise RacingModelInputError("niche market-only policy drifted")
    return value


def load_niche_fallback_registry(path: Path | str) -> Mapping[str, Any]:
    """Load a local frozen policy only; it has no external lookup path."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RacingModelInputError("niche fallback registry cannot be read") from exc
    return validate_niche_fallback_registry(value)


def build_asof_snapshot(
    case: Mapping[str, Any],
    *,
    required_feature_ids: tuple[str, ...],
    required_competitors: tuple[str, ...] | None,
    market_family: str,
) -> dict[str, Any]:
    """Select a model-independent frozen snapshot bounded by ``decision_at``."""

    if not isinstance(case, Mapping):
        raise RacingModelInputError("model case must be an object")
    identifier = _identifier(case.get("id"), label="case.id", pattern=_CASE_ID)
    decision_at, decision_text = _timestamp(case.get("decision_at"), label="decision_at")
    event_at, event_text = _timestamp(case.get("event_at"), label="event_at")
    if event_at <= decision_at:
        raise RacingModelInputError("event_at must be strictly after decision_at")
    competitors_raw = case.get("competitors")
    if not isinstance(competitors_raw, list) or not competitors_raw:
        raise RacingModelInputError("competitors must be a non-empty ordered list")
    competitors = tuple(_identifier(item, label="competitor") for item in competitors_raw)
    if len(set(competitors)) != len(competitors):
        raise RacingModelInputError("competitors must be unique")
    if required_competitors is not None and competitors != required_competitors:
        raise RacingModelInputError("competitors do not match the canonical market order")
    if market_family == "binary" and len(competitors) != 2:
        raise RacingModelInputError("binary market must contain exactly HOME and AWAY")
    if market_family == "futures" and len(competitors) < 2:
        raise RacingModelInputError("futures market must contain at least two runners")
    market = case.get("market_probabilities")
    if not isinstance(market, Mapping) or set(market) != set(competitors):
        raise RacingModelInputError("market probabilities must exactly match competitors")
    requested_weight = case.get("requested_residual_weight")
    if not isinstance(requested_weight, str):
        raise RacingModelInputError("requested_residual_weight must be a decimal string")
    features = case.get("features")
    if not isinstance(features, Mapping) or set(features) != set(required_feature_ids):
        raise RacingModelInputError("case must declare every required feature and no extras")
    availability: list[dict[str, Any]] = []
    selected: dict[str, Any] = {}
    reasons: list[str] = []
    for feature_id in required_feature_ids:
        observation = _select_known_observation(features[feature_id], decision_at, label="features.%s" % feature_id)
        if observation is None:
            availability.append({"feature_id": feature_id, "status": "UNAVAILABLE_AT_DECISION"})
            reasons.append("FEATURE_UNAVAILABLE_AT_DECISION:%s" % feature_id)
            continue
        raw_value, known_at = observation
        if feature_id == "participation_status" and raw_value != "CONFIRMED":
            availability.append(
                {"feature_id": feature_id, "status": "UNCONFIRMED_AT_DECISION", "selected_known_at": known_at}
            )
            reasons.append("PARTICIPATION_UNCONFIRMED_AT_DECISION")
            continue
        selected[feature_id] = raw_value
        availability.append({"feature_id": feature_id, "status": "AVAILABLE_AT_DECISION", "selected_known_at": known_at})
    return {
        "id": identifier,
        "decision_at": decision_text,
        "event_at": event_text,
        "competitors": competitors,
        "market": dict(market),
        "requested_residual_weight": requested_weight,
        "availability": availability,
        "selected": selected,
        "temporal_safe": not reasons,
        "reason_codes": sorted(set(reasons)),
    }


def _validated_runner_strengths(value: Any, competitors: tuple[str, ...]) -> dict[str, Decimal]:
    if not isinstance(value, Mapping) or set(value) != set(competitors):
        raise RacingModelInputError("runner_strengths must exactly match the runner set")
    strengths = {runner: _decimal(value[runner], label="runner_strengths.%s" % runner) for runner in competitors}
    if any(not _ZERO < strength <= Decimal("100") for strength in strengths.values()):
        raise RacingModelInputError("runner strengths must be within (0, 100]")
    return strengths


def plackett_luce_win_probabilities(runner_strengths: Mapping[str, Any], runners: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Return a complete Decimal Plackett-Luce win vector for the runner order."""

    competitors = tuple(_identifier(item, label="runner") for item in runners)
    strengths = _validated_runner_strengths(runner_strengths, competitors)
    total = sum(strengths.values(), _ZERO)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return {runner: decimal_text(strengths[runner] / total) for runner in competitors}


def harville_exacta_probabilities(runner_strengths: Mapping[str, Any], runners: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    """Return ordered Harville exacta probabilities derived from the same strengths."""

    competitors = tuple(_identifier(item, label="runner") for item in runners)
    strengths = _validated_runner_strengths(runner_strengths, competitors)
    total = sum(strengths.values(), _ZERO)
    rows: list[dict[str, str]] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for first in competitors:
            first_probability = strengths[first] / total
            remaining = total - strengths[first]
            for second in competitors:
                if first == second:
                    continue
                probability = first_probability * strengths[second] / remaining
                rows.append({"first": first, "second": second, "probability": decimal_text(probability)})
    return rows


def _generic_prediction(
    snapshot: Mapping[str, Any],
    *,
    market_family: str,
    candidate_probabilities: Mapping[str, str] | None,
    feature_bundle: Mapping[str, Any] | None,
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    residual_input: dict[str, Any] = {
        "id": snapshot["id"],
        "market_family": market_family,
        "market_probabilities": snapshot["market"],
        "requested_residual_weight": snapshot["requested_residual_weight"],
    }
    if candidate_probabilities is None or feature_bundle is None:
        residual_input["domain_increment"] = {"status": "UNAVAILABLE", "reproducible": False}
    else:
        residual_input["candidate_residual_probabilities"] = dict(candidate_probabilities)
        residual_input["domain_increment"] = {
            "status": "VERIFIED",
            "reproducible": True,
            "evidence_sha256": hashlib.sha256(canonical_json_bytes(feature_bundle)).hexdigest(),
            "frozen_window_id": "%s_ASOF" % snapshot["id"],
        }
    try:
        return calculate_market_anchored_residual(residual_input, market_family_registry, parameters)
    except GenericResidualInputError as exc:
        raise RacingModelInputError("market anchoring failed: %s" % exc) from exc


def build_racing_market_anchored_prediction(
    case: Mapping[str, Any],
    niche_registry: Mapping[str, Any],
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a racing residual only from decision-time frozen and confirmed data."""

    validate_niche_fallback_registry(niche_registry)
    snapshot = build_asof_snapshot(
        case,
        required_feature_ids=RACING_FEATURE_IDS,
        required_competitors=None,
        market_family="futures",
    )
    feature_bundle: dict[str, Any] | None = None
    win_probabilities: dict[str, str] | None = None
    exacta_probabilities: list[dict[str, str]] | None = None
    if snapshot["temporal_safe"]:
        runner_strengths = snapshot["selected"]["runner_strengths"]
        win_probabilities = plackett_luce_win_probabilities(runner_strengths, snapshot["competitors"])
        exacta_probabilities = harville_exacta_probabilities(runner_strengths, snapshot["competitors"])
        feature_bundle = {
            "model_id": MODEL_ID,
            "case_id": snapshot["id"],
            "decision_at": snapshot["decision_at"],
            "runner_strengths": win_probabilities,
            "harville_exacta_probabilities": exacta_probabilities,
        }
    prediction = _generic_prediction(
        snapshot,
        market_family="futures",
        candidate_probabilities=win_probabilities,
        feature_bundle=feature_bundle,
        market_family_registry=market_family_registry,
        parameters=parameters,
    )
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
        "plackett_luce_win_probabilities": win_probabilities,
        "harville_exacta_probabilities": exacta_probabilities,
        "market_anchored_prediction": prediction,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }


def build_niche_market_only_prediction(
    case: Mapping[str, Any],
    niche_registry: Mapping[str, Any],
    market_family_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a strict market-only/no-advice result for any unsupported niche."""

    validate_niche_fallback_registry(niche_registry)
    if not isinstance(case, Mapping):
        raise RacingModelInputError("niche fallback case must be an object")
    identifier = _identifier(case.get("id"), label="case.id", pattern=_CASE_ID)
    domain = case.get("domain")
    if not isinstance(domain, str) or domain not in {"RUGBY", "CRICKET", "ESPORTS", "OTHER"}:
        raise RacingModelInputError("niche fallback domain is unsupported")
    market_family = case.get("market_family")
    if market_family not in {"binary", "multinomial", "futures"}:
        raise RacingModelInputError("niche fallback market family is unsupported")
    residual_input = {
        "id": identifier,
        "market_family": market_family,
        "market_probabilities": case.get("market_probabilities"),
        "requested_residual_weight": case.get("requested_residual_weight"),
        "domain_increment": {"status": "UNAVAILABLE", "reproducible": False},
    }
    try:
        prediction = calculate_market_anchored_residual(residual_input, market_family_registry, parameters)
    except GenericResidualInputError as exc:
        raise RacingModelInputError("niche market-only fallback failed: %s" % exc) from exc
    return {
        "id": identifier,
        "model_id": NICHE_MODEL_ID,
        "domain": domain,
        "action": "MARKET_ONLY_OR_NO_ADVICE",
        "reason_codes": ["UNPROVEN_DOMAIN_MODEL", "NICHE_MARKET_ONLY_POLICY"],
        "market_anchored_prediction": prediction,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }
