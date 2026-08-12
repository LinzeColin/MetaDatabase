"""Deterministic S11/P01 friction and executable-net-expectation artifacts.

The module replays only frozen synthetic observations.  It has no provider,
account, order, network, clock, or wait capability.  A positive calculated
net expectation is deliberately not an instruction to place an order.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from decimal_math import (
    DECIMAL_PRECISION,
    ODDS_STEP,
    NumericContractError,
    decimal_text,
    normalize_friction,
    normalize_odds,
    normalize_probability,
    validate_numeric_contract,
)


CONTRACT_ID = "AC-S11-P01"
REQUIREMENT_ID = "REQ-S11-P01"
STAGE_ID = "S11"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
_TIME_BANDS = (
    ("MORE_THAN_2H", "more_than_2h_default"),
    ("15M_TO_2H", "15m_to_2h_default"),
    ("0_TO_15M", "0_to_15m_default"),
    ("LIVE", "live_default"),
)
_COMPONENTS = ("price_worsening", "rejection", "settlement", "operational")
_ZERO = Decimal("0")
_ONE = Decimal("1")


class FrictionInputError(ValueError):
    """Raised when a frozen S11/P01 fixture is malformed or unsafe."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise FrictionInputError("%s has an unexpected shape" % label)
    return value


def _nonempty_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise FrictionInputError("%s must be a non-empty string" % label)
    return value


def _sha256_text(value: Any, *, label: str) -> str:
    text = _nonempty_text(value, label=label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise FrictionInputError("%s must be a lowercase SHA-256" % label)
    return text


def _integer(value: Any, *, label: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise FrictionInputError("%s must be an integer at least %d" % (label, minimum))
    return value


def _friction_parameters(parameters: Any) -> tuple[Mapping[str, Any], Mapping[str, Decimal], Decimal]:
    if not isinstance(parameters, Mapping):
        raise FrictionInputError("parameters must be an object")
    numeric = parameters.get("numeric_determinism")
    if not isinstance(numeric, Mapping):
        raise FrictionInputError("numeric_determinism must be an object")
    numeric_contract_keys = {
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
    try:
        validate_numeric_contract({key: numeric.get(key) for key in numeric_contract_keys})
    except NumericContractError as exc:
        raise FrictionInputError("numeric_determinism is not authoritative: %s" % exc) from exc
    friction = _strict_object(
        parameters.get("friction"),
        {
            "more_than_2h_default",
            "15m_to_2h_default",
            "0_to_15m_default",
            "live_default",
            "effective_rule",
        },
        label="friction parameters",
    )
    if friction["effective_rule"] != "MAX(DEFAULT, ROLLING_OBSERVED_P95)":
        raise FrictionInputError("friction effective rule is not frozen")
    defaults = {
        band: normalize_friction(friction[key], label="friction.%s" % key)
        for band, key in _TIME_BANDS
    }
    if (
        numeric.get("boundary_perturbation_friction_up") != "0.0001"
        or numeric.get("odds_perturbation") != "ONE_PROVIDER_TICK_ADVERSE"
        or numeric.get("unstable_action") != "NO_RECOMMENDATION"
    ):
        raise FrictionInputError("frozen adverse perturbation parameters differ")
    return friction, defaults, normalize_friction(
        numeric["boundary_perturbation_friction_up"], label="boundary_perturbation_friction_up"
    )


def _observation_total(value: Any, *, label: str) -> Decimal:
    observation = _strict_object(
        value,
        {"observation_index", *_COMPONENTS},
        label=label,
    )
    _integer(observation["observation_index"], label="%s.observation_index" % label, minimum=1)
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            total = sum(
                (
                    normalize_friction(observation[component], label="%s.%s" % (label, component))
                    for component in _COMPONENTS
                ),
                _ZERO,
            )
    except NumericContractError as exc:
        raise FrictionInputError("%s components are invalid: %s" % (label, exc)) from exc
    if total >= _ONE:
        raise FrictionInputError("%s total friction must be below one" % label)
    try:
        return normalize_friction(decimal_text(total), label="%s.total" % label)
    except NumericContractError as exc:
        raise FrictionInputError("%s total is invalid: %s" % (label, exc)) from exc


def _validate_band(value: Any, *, expected_band: str, rolling_window_size: int) -> tuple[list[Decimal], list[Decimal]]:
    band = _strict_object(value, {"time_band", "observations"}, label="time band")
    if band["time_band"] != expected_band:
        raise FrictionInputError("time bands must remain in frozen order")
    observations = band["observations"]
    if not isinstance(observations, list) or len(observations) < rolling_window_size:
        raise FrictionInputError("%s has too few observations" % expected_band)
    totals = [_observation_total(row, label="%s.observations[%d]" % (expected_band, index)) for index, row in enumerate(observations)]
    indexes = [row["observation_index"] for row in observations if isinstance(row, Mapping)]
    if indexes != list(range(1, len(observations) + 1)):
        raise FrictionInputError("%s observation indexes must be consecutive" % expected_band)
    return totals, totals[-rolling_window_size:]


def _rolling_p95(window: Sequence[Decimal]) -> Decimal:
    if not window:
        raise FrictionInputError("rolling window cannot be empty")
    # Conservative upper nearest-rank percentile: ceil(0.95 * n), zero based.
    rank = ((95 * len(window)) + 99) // 100
    return sorted(window)[rank - 1]


def validate_fixture(fixture: Any, parameters: Any) -> dict[str, Any]:
    """Validate a closed-world frozen fixture and return normalized state."""

    _friction_parameters(parameters)
    value = _strict_object(
        fixture,
        {
            "schema_version",
            "fixture_id",
            "contract_id",
            "requirement_id",
            "stage_id",
            "phase_id",
            "product_version",
            "fixed_clock",
            "input_mode",
            "rolling_window_size",
            "time_bands",
            "candidates",
            "claim_boundary",
            "expected_model_sha256",
            "expected_backtest_sha256",
        },
        label="S11/P01 fixture",
    )
    exact = (
        value["schema_version"] == "1.0.0"
        and value["fixture_id"] == "FIX-S11-P01-FRICTION"
        and value["contract_id"] == CONTRACT_ID
        and value["requirement_id"] == REQUIREMENT_ID
        and value["stage_id"] == STAGE_ID
        and value["phase_id"] == PHASE_ID
        and value["product_version"] == VERSION
        and value["fixed_clock"] == FIXED_CLOCK
        and value["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    )
    if not exact:
        raise FrictionInputError("fixture identity or input boundary differs")
    rolling_window_size = _integer(value["rolling_window_size"], label="rolling_window_size", minimum=1)
    if rolling_window_size != 5:
        raise FrictionInputError("rolling_window_size must be frozen at five")
    time_bands = value["time_bands"]
    if not isinstance(time_bands, list) or len(time_bands) != len(_TIME_BANDS):
        raise FrictionInputError("fixture must contain every time band exactly once")
    normalized_bands = []
    for row, (time_band, _) in zip(time_bands, _TIME_BANDS):
        totals, window = _validate_band(row, expected_band=time_band, rolling_window_size=rolling_window_size)
        normalized_bands.append({"time_band": time_band, "totals": totals, "window": window})
    candidates = value["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise FrictionInputError("fixture must contain at least one candidate")
    candidate_ids = []
    for index, candidate in enumerate(candidates):
        item = _strict_object(
            candidate,
            {"candidate_id", "time_band", "conservative_probability", "odds"},
            label="candidates[%d]" % index,
        )
        candidate_ids.append(_nonempty_text(item["candidate_id"], label="candidate_id"))
        if item["time_band"] not in dict(_TIME_BANDS):
            raise FrictionInputError("candidate time_band is unknown")
        try:
            normalize_probability(item["conservative_probability"], label="candidate probability")
            normalize_odds(item["odds"], label="candidate odds")
        except NumericContractError as exc:
            raise FrictionInputError("candidate numeric input is invalid: %s" % exc) from exc
    if len(candidate_ids) != len(set(candidate_ids)):
        raise FrictionInputError("candidate ids must be unique")
    boundary = _strict_object(
        value["claim_boundary"],
        {
            "network_accessed",
            "actual_market_or_odds_observed",
            "recommendation_generated",
            "order_submission_enabled",
            "real_time_soak_required",
            "incremental_cash_spent_aud",
        },
        label="claim_boundary",
    )
    expected_boundary = {
        "network_accessed": False,
        "actual_market_or_odds_observed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if boundary != expected_boundary:
        raise FrictionInputError("fixture external-effect boundary differs")
    _sha256_text(value["expected_model_sha256"], label="expected_model_sha256")
    _sha256_text(value["expected_backtest_sha256"], label="expected_backtest_sha256")
    return {"fixture": value, "bands": normalized_bands, "rolling_window_size": rolling_window_size}


def build_model(fixture: Mapping[str, Any], parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic conservative friction model from frozen data."""

    validated = validate_fixture(fixture, parameters)
    rule, defaults, _ = _friction_parameters(parameters)
    bands = []
    for source in validated["bands"]:
        observed_p95 = _rolling_p95(source["window"])
        effective = max(defaults[source["time_band"]], observed_p95)
        bands.append(
            {
                "time_band": source["time_band"],
                "default_friction": decimal_text(defaults[source["time_band"]]),
                "observation_count": len(source["totals"]),
                "rolling_window_observation_count": validated["rolling_window_size"],
                "rolling_observed_totals": [decimal_text(total) for total in source["window"]],
                "rolling_observed_p95": decimal_text(observed_p95),
                "effective_friction": decimal_text(effective),
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S11-P01-01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "methodology": {
            "observed_friction_components": list(_COMPONENTS),
            "rolling_window_selection": "LAST_ORDERED_SYNTHETIC_OBSERVATIONS",
            "rolling_percentile": "UPPER_NEAREST_RANK_P95",
            "effective_rule": rule["effective_rule"],
            "rounding": "DECIMAL_FRICTION_UP_1E-9",
        },
        "time_bands": bands,
        "decision": "FRICTION_MODEL_READY_DOWNSTREAM_THRESHOLD_AND_RISK_GATES_REQUIRED",
        "next": "S11/P02_READY_NOT_STARTED",
        "claim_boundary": dict(validated["fixture"]["claim_boundary"]),
    }


def _band_effective_friction(model: Mapping[str, Any], time_band: str) -> Decimal:
    rows = model.get("time_bands")
    if not isinstance(rows, list):
        raise FrictionInputError("model time bands are missing")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get("time_band") == time_band]
    if len(matches) != 1:
        raise FrictionInputError("model time band is missing or duplicate")
    try:
        return normalize_friction(matches[0].get("effective_friction"), label="model effective friction")
    except NumericContractError as exc:
        raise FrictionInputError("model effective friction is invalid: %s" % exc) from exc


def build_backtest(fixture: Mapping[str, Any], parameters: Mapping[str, Any], model: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Replay research-only net expectations; it never produces an order action."""

    validated = validate_fixture(fixture, parameters)
    _, _, adverse_friction_step = _friction_parameters(parameters)
    rebuilt_model = build_model(fixture, parameters)
    if model is not None and model != rebuilt_model:
        raise FrictionInputError("model must be the exact deterministic replay")
    candidate_results = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        for candidate in validated["fixture"]["candidates"]:
            probability = normalize_probability(candidate["conservative_probability"], label="candidate probability")
            odds = normalize_odds(candidate["odds"], label="candidate odds")
            effective = _band_effective_friction(rebuilt_model, candidate["time_band"])
            net_expected = (probability * odds) - _ONE - effective
            adverse_friction = normalize_friction(decimal_text(effective + adverse_friction_step), label="adverse friction")
            adverse_odds = normalize_odds(decimal_text(odds - ODDS_STEP), label="adverse odds")
            adverse_net_expected = (probability * adverse_odds) - _ONE - adverse_friction
            candidate_results.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "time_band": candidate["time_band"],
                    "conservative_probability": decimal_text(probability),
                    "odds": decimal_text(odds),
                    "effective_friction": decimal_text(effective),
                    "net_expected": decimal_text(net_expected),
                    "adverse_friction": decimal_text(adverse_friction),
                    "adverse_odds": decimal_text(adverse_odds),
                    "adverse_net_expected": decimal_text(adverse_net_expected),
                    "action": "NO_ORDER_RESEARCH_ONLY",
                }
            )
    return {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S11-P01-02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "model_sha256": artifact_sha256(rebuilt_model),
        "candidate_results": candidate_results,
        "summary": {
            "candidate_count": len(candidate_results),
            "positive_net_expected_count": sum(
                Decimal(row["net_expected"]) > _ZERO for row in candidate_results
            ),
            "order_actions_enabled": False,
            "recommendations_enabled": False,
        },
        "decision": "FRICTION_REPLAY_READY_DOWNSTREAM_MINIMUM_ODDS_AND_RISK_GATES_REQUIRED",
        "next": "S11/P02_READY_NOT_STARTED",
        "claim_boundary": dict(validated["fixture"]["claim_boundary"]),
    }


def build_artifacts(fixture: Mapping[str, Any], parameters: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    model = build_model(fixture, parameters)
    return model, build_backtest(fixture, parameters, model)


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise FrictionInputError("%s must contain a JSON object" % path)
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build frozen ABD S11/P01 friction artifacts")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--backtest", required=True)
    args = parser.parse_args()
    fixture = _load_json(Path(args.fixture))
    parameters = _load_json(Path(args.parameters))
    model, backtest = build_artifacts(fixture, parameters)
    _atomic_write(Path(args.model), canonical_json_bytes(model))
    _atomic_write(Path(args.backtest), canonical_json_bytes(backtest))
    print(
        json.dumps(
            {
                "contract_id": CONTRACT_ID,
                "status": "PASS",
                "model_sha256": artifact_sha256(model),
                "backtest_sha256": artifact_sha256(backtest),
                "next": "S11/P02_READY_NOT_STARTED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
