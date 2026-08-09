"""Deterministic score-distribution primitives for ABD S09/P03.

The module operates only on caller-provided frozen Decimal inputs.  It exposes
Poisson, Dixon--Coles, Skellam and negative-binomial probability mass with
explicit finite-support tail accounting.  It neither fetches data nor creates
recommendations, accounts, orders, or real-time waiting paths.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
from typing import Any, Mapping

from generic_residual import decimal_text


MODEL_REGISTRY_ID = "DIST-S09-P03-SCORE-MODELS"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
DECIMAL_PRECISION = 50
PROBABILITY_TOLERANCE = Decimal("0.000000000001")
SERIES_TERMINATION = Decimal("1E-45")
MAX_SERIES_TERMS = 256
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_REQUIRED_DISTRIBUTIONS = (
    "POISSON",
    "DIXON_COLES",
    "SKELLAM",
    "NEGATIVE_BINOMIAL",
    "HIERARCHICAL_RESIDUAL",
)
_REQUIRED_MARKET_MAPPINGS = ("ONE_X_TWO", "TOTALS_2_5", "BOTH_TEAMS_TO_SCORE")


class ScoreModelInputError(ValueError):
    """Raised when a score distribution cannot be computed safely."""


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ScoreModelInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ScoreModelInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise ScoreModelInputError("%s must be finite" % label)
    return parsed


def _positive_decimal(value: Any, *, label: str, allow_zero: bool = False) -> Decimal:
    parsed = _decimal(value, label=label)
    if parsed < _ZERO or (parsed == _ZERO and not allow_zero):
        raise ScoreModelInputError("%s must be positive" % label)
    return parsed


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ScoreModelInputError("%s must be an integer >= %d" % (label, minimum))
    return value


def _factorial(value: int) -> int:
    result = 1
    for factor in range(2, value + 1):
        result *= factor
    return result


def _tail_from_mass(mass: Decimal, *, label: str) -> Decimal:
    if mass > _ONE + PROBABILITY_TOLERANCE:
        raise ScoreModelInputError("%s finite probability mass exceeds one" % label)
    tail = _ONE - mass
    return _ZERO if tail < _ZERO else tail


def _probability_map(values: Mapping[str, Decimal], *, finite_mass: Decimal, tail: Decimal, label: str) -> dict[str, Any]:
    if tail > PROBABILITY_TOLERANCE:
        return {
            "status": "TAIL_ABOVE_TOLERANCE_MARKET_ONLY",
            "finite_mass": decimal_text(finite_mass),
            "tail_probability": decimal_text(tail),
            "outcomes": {},
        }
    if finite_mass <= _ZERO:
        raise ScoreModelInputError("%s finite mass is not positive" % label)
    normalized = {outcome: value / finite_mass for outcome, value in values.items()}
    total = sum(normalized.values(), _ZERO)
    if abs(total - _ONE) > PROBABILITY_TOLERANCE:
        raise ScoreModelInputError("%s normalized mapping is incomplete" % label)
    if any(value <= _ZERO or value >= _ONE for value in normalized.values()):
        raise ScoreModelInputError("%s has non-interior mapped probability" % label)
    return {
        "status": "COMPLETE_WITHIN_TAIL_TOLERANCE",
        "finite_mass": decimal_text(finite_mass),
        "tail_probability": decimal_text(tail),
        "outcomes": {outcome: decimal_text(normalized[outcome]) for outcome in sorted(normalized)},
    }


def validate_distribution_test_registry(value: Any) -> Mapping[str, Any]:
    """Validate the frozen S09/P03 distribution and safety contract."""

    if not isinstance(value, Mapping):
        raise ScoreModelInputError("distribution registry must be an object")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("product_version") != "0.0.0.1"
        or value.get("registry_id") != MODEL_REGISTRY_ID
        or value.get("input_mode") != INPUT_MODE
    ):
        raise ScoreModelInputError("distribution registry identity is invalid")
    expected_policy = {
        "decimal_precision": 50,
        "probability_tolerance": "0.000000000001",
        "series_termination": "1E-45",
        "max_goal_rate": "3",
        "max_goals": 18,
        "max_goal_difference": 18,
        "max_negative_binomial_count": 40,
        "tail_tolerance": "0.000000000001",
        "dixon_coles_rho_min": "-0.10",
        "dixon_coles_rho_max": "0.10",
        "unavailable_action": "MARKET_ONLY_ZERO_RESIDUAL",
        "external_network_accessed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_required": False,
    }
    if value.get("policy") != expected_policy:
        raise ScoreModelInputError("distribution policy drifted")
    if value.get("required_distributions") != list(_REQUIRED_DISTRIBUTIONS):
        raise ScoreModelInputError("required distributions drifted")
    if value.get("required_market_mappings") != list(_REQUIRED_MARKET_MAPPINGS):
        raise ScoreModelInputError("required market mappings drifted")
    return value


def load_distribution_test_registry(path: Path | str) -> Mapping[str, Any]:
    """Read a local frozen registry only; no network access is performed."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoreModelInputError("distribution registry cannot be read") from exc
    return validate_distribution_test_registry(value)


def poisson_pmf(mean: Any, goals: Any) -> Decimal:
    """Return a Poisson probability using 50-digit Decimal arithmetic."""

    rate = _positive_decimal(mean, label="poisson mean", allow_zero=True)
    score = _integer(goals, label="poisson goals")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if rate == _ZERO:
            return _ONE if score == 0 else _ZERO
        return (-rate).exp() * (rate**score) / Decimal(_factorial(score))


def poisson_distribution(mean: Any, maximum_goal: Any) -> dict[str, Any]:
    """Render finite Poisson mass and an explicit right-tail probability."""

    rate = _positive_decimal(mean, label="poisson mean", allow_zero=True)
    maximum = _integer(maximum_goal, label="maximum_goal")
    probabilities = [poisson_pmf(decimal_text(rate), score) for score in range(maximum + 1)]
    finite_mass = sum(probabilities, _ZERO)
    tail = _tail_from_mass(finite_mass, label="poisson")
    return {
        "distribution": "POISSON",
        "mean": decimal_text(rate),
        "maximum_goal": maximum,
        "probabilities": [{"goals": score, "probability": decimal_text(probabilities[score])} for score in range(maximum + 1)],
        "finite_mass": decimal_text(finite_mass),
        "tail_probability": decimal_text(tail),
    }


def negative_binomial_pmf(mean: Any, dispersion: Any, goals: Any) -> Decimal:
    """Return NB2 mass with mean and dispersion in a Decimal-safe form."""

    expected = _positive_decimal(mean, label="negative binomial mean", allow_zero=True)
    shape = _positive_decimal(dispersion, label="negative binomial dispersion")
    score = _integer(goals, label="negative binomial goals")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if expected == _ZERO:
            return _ONE if score == 0 else _ZERO
        probability = shape / (shape + expected)
        complement = expected / (shape + expected)
        coefficient = _ONE
        for index in range(score):
            coefficient *= (shape + Decimal(index)) / Decimal(index + 1)
        return coefficient * (probability.ln() * shape).exp() * (complement**score)


def negative_binomial_distribution(mean: Any, dispersion: Any, maximum_goals: Any) -> dict[str, Any]:
    """Render NB2 finite mass and an explicit right tail."""

    expected = _positive_decimal(mean, label="negative binomial mean", allow_zero=True)
    shape = _positive_decimal(dispersion, label="negative binomial dispersion")
    maximum = _integer(maximum_goals, label="maximum negative binomial goals")
    probabilities = [negative_binomial_pmf(decimal_text(expected), decimal_text(shape), score) for score in range(maximum + 1)]
    finite_mass = sum(probabilities, _ZERO)
    tail = _tail_from_mass(finite_mass, label="negative binomial")
    return {
        "distribution": "NEGATIVE_BINOMIAL",
        "mean": decimal_text(expected),
        "dispersion": decimal_text(shape),
        "maximum_goals": maximum,
        "probabilities": [{"goals": score, "probability": decimal_text(probabilities[score])} for score in range(maximum + 1)],
        "finite_mass": decimal_text(finite_mass),
        "tail_probability": decimal_text(tail),
    }


def modified_bessel_i(order: Any, argument: Any) -> Decimal:
    """Compute integer-order modified Bessel I by a bounded Decimal series."""

    integer_order = _integer(order, label="bessel order")
    value = _positive_decimal(argument, label="bessel argument", allow_zero=True)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        half = value / _TWO
        term = (half**integer_order) / Decimal(_factorial(integer_order))
        total = term
        square = half * half
        for index in range(MAX_SERIES_TERMS):
            denominator = Decimal(index + 1) * Decimal(index + integer_order + 1)
            term = term * square / denominator
            if abs(term) <= SERIES_TERMINATION:
                return total
            total += term
    raise ScoreModelInputError("modified Bessel series did not converge")


def skellam_pmf(home_mean: Any, away_mean: Any, goal_difference: Any) -> Decimal:
    """Return Skellam mass for a home-minus-away integer goal difference."""

    home = _positive_decimal(home_mean, label="skellam home mean", allow_zero=True)
    away = _positive_decimal(away_mean, label="skellam away mean", allow_zero=True)
    if not isinstance(goal_difference, int) or isinstance(goal_difference, bool):
        raise ScoreModelInputError("goal_difference must be an integer")
    difference = goal_difference
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if home == _ZERO and away == _ZERO:
            return _ONE if difference == 0 else _ZERO
        if away == _ZERO:
            return _ZERO if difference < 0 else poisson_pmf(decimal_text(home), difference)
        if home == _ZERO:
            return _ZERO if difference > 0 else poisson_pmf(decimal_text(away), -difference)
        ratio_component = ((home / away).ln() * (Decimal(difference) / _TWO)).exp()
        argument = _TWO * (home * away).sqrt()
        return (-(home + away)).exp() * ratio_component * modified_bessel_i(abs(difference), decimal_text(argument))


def skellam_distribution(home_mean: Any, away_mean: Any, maximum_difference: Any) -> dict[str, Any]:
    """Render finite Skellam difference mass and a two-sided tail."""

    home = _positive_decimal(home_mean, label="skellam home mean", allow_zero=True)
    away = _positive_decimal(away_mean, label="skellam away mean", allow_zero=True)
    maximum = _integer(maximum_difference, label="maximum goal difference")
    values = {difference: skellam_pmf(decimal_text(home), decimal_text(away), difference) for difference in range(-maximum, maximum + 1)}
    finite_mass = sum(values.values(), _ZERO)
    tail = _tail_from_mass(finite_mass, label="skellam")
    return {
        "distribution": "SKELLAM",
        "home_mean": decimal_text(home),
        "away_mean": decimal_text(away),
        "maximum_difference": maximum,
        "probabilities": [
            {"goal_difference": difference, "probability": decimal_text(values[difference])}
            for difference in range(-maximum, maximum + 1)
        ],
        "finite_mass": decimal_text(finite_mass),
        "tail_probability": decimal_text(tail),
    }


def dixon_coles_tau(home_mean: Any, away_mean: Any, rho: Any, home_goals: Any, away_goals: Any) -> Decimal:
    """Return the bounded Dixon--Coles low-score correlation adjustment."""

    home = _positive_decimal(home_mean, label="dixon_coles home mean", allow_zero=True)
    away = _positive_decimal(away_mean, label="dixon_coles away mean", allow_zero=True)
    correlation = _decimal(rho, label="dixon_coles rho")
    home_score = _integer(home_goals, label="home goals")
    away_score = _integer(away_goals, label="away goals")
    if home_score == 0 and away_score == 0:
        adjustment = _ONE - (home * away * correlation)
    elif home_score == 0 and away_score == 1:
        adjustment = _ONE + (home * correlation)
    elif home_score == 1 and away_score == 0:
        adjustment = _ONE + (away * correlation)
    elif home_score == 1 and away_score == 1:
        adjustment = _ONE - correlation
    else:
        adjustment = _ONE
    if adjustment < _ZERO:
        raise ScoreModelInputError("dixon_coles adjustment would create negative mass")
    return adjustment


def dixon_coles_scoreline_distribution(home_mean: Any, away_mean: Any, rho: Any, maximum_goal: Any) -> dict[str, Any]:
    """Render finite Dixon--Coles scoreline mass and an explicit tail."""

    home = _positive_decimal(home_mean, label="dixon_coles home mean", allow_zero=True)
    away = _positive_decimal(away_mean, label="dixon_coles away mean", allow_zero=True)
    correlation = _decimal(rho, label="dixon_coles rho")
    maximum = _integer(maximum_goal, label="maximum score")
    rows = []
    finite_mass = _ZERO
    for home_goals in range(maximum + 1):
        for away_goals in range(maximum + 1):
            probability = (
                poisson_pmf(decimal_text(home), home_goals)
                * poisson_pmf(decimal_text(away), away_goals)
                * dixon_coles_tau(decimal_text(home), decimal_text(away), decimal_text(correlation), home_goals, away_goals)
            )
            if probability < _ZERO:
                raise ScoreModelInputError("dixon_coles scoreline probability is negative")
            finite_mass += probability
            rows.append({"home_goals": home_goals, "away_goals": away_goals, "probability": probability})
    tail = _tail_from_mass(finite_mass, label="dixon_coles")
    return {
        "distribution": "DIXON_COLES",
        "home_mean": decimal_text(home),
        "away_mean": decimal_text(away),
        "rho": decimal_text(correlation),
        "maximum_goal": maximum,
        "scorelines": [
            {"home_goals": row["home_goals"], "away_goals": row["away_goals"], "probability": decimal_text(row["probability"])}
            for row in rows
        ],
        "finite_mass": decimal_text(finite_mass),
        "tail_probability": decimal_text(tail),
    }


def _scoreline_mappings(distribution: Mapping[str, Any]) -> dict[str, Any]:
    if distribution.get("distribution") != "DIXON_COLES":
        raise ScoreModelInputError("scoreline mapping requires a Dixon-Coles distribution")
    try:
        finite_mass = Decimal(str(distribution["finite_mass"]))
        tail = Decimal(str(distribution["tail_probability"]))
    except (InvalidOperation, KeyError) as exc:
        raise ScoreModelInputError("scoreline distribution is malformed") from exc
    one_x_two = {"HOME": _ZERO, "DRAW": _ZERO, "AWAY": _ZERO}
    totals = {"OVER": _ZERO, "UNDER": _ZERO}
    btts = {"YES": _ZERO, "NO": _ZERO}
    scorelines = distribution.get("scorelines")
    if not isinstance(scorelines, list):
        raise ScoreModelInputError("scoreline distribution rows are missing")
    for row in scorelines:
        if not isinstance(row, Mapping):
            raise ScoreModelInputError("scoreline row is malformed")
        home_goals = _integer(row.get("home_goals"), label="scoreline home goals")
        away_goals = _integer(row.get("away_goals"), label="scoreline away goals")
        probability = _decimal(row.get("probability"), label="scoreline probability")
        if home_goals > away_goals:
            one_x_two["HOME"] += probability
        elif home_goals == away_goals:
            one_x_two["DRAW"] += probability
        else:
            one_x_two["AWAY"] += probability
        if home_goals + away_goals >= 3:
            totals["OVER"] += probability
        else:
            totals["UNDER"] += probability
        if home_goals > 0 and away_goals > 0:
            btts["YES"] += probability
        else:
            btts["NO"] += probability
    return {
        "ONE_X_TWO": _probability_map(one_x_two, finite_mass=finite_mass, tail=tail, label="one_x_two"),
        "TOTALS_2_5": _probability_map(totals, finite_mass=finite_mass, tail=tail, label="totals_2_5"),
        "BOTH_TEAMS_TO_SCORE": _probability_map(btts, finite_mass=finite_mass, tail=tail, label="both_teams_to_score"),
    }


def _skellam_one_x_two(distribution: Mapping[str, Any]) -> dict[str, Any]:
    try:
        finite_mass = Decimal(str(distribution["finite_mass"]))
        tail = Decimal(str(distribution["tail_probability"]))
    except (InvalidOperation, KeyError) as exc:
        raise ScoreModelInputError("skellam distribution is malformed") from exc
    outcomes = {"HOME": _ZERO, "DRAW": _ZERO, "AWAY": _ZERO}
    for row in distribution.get("probabilities", []):
        if not isinstance(row, Mapping):
            raise ScoreModelInputError("skellam row is malformed")
        difference = row.get("goal_difference")
        probability = _decimal(row.get("probability"), label="skellam probability")
        if difference > 0:
            outcomes["HOME"] += probability
        elif difference == 0:
            outcomes["DRAW"] += probability
        else:
            outcomes["AWAY"] += probability
    return _probability_map(outcomes, finite_mass=finite_mass, tail=tail, label="skellam_one_x_two")


def build_score_projection(
    home_mean: Any,
    away_mean: Any,
    rho: Any,
    negative_binomial_dispersion: Any,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Build frozen distribution evidence and gated score-market mappings."""

    validate_distribution_test_registry(registry)
    policy = registry["policy"]
    maximum_rate = _positive_decimal(policy["max_goal_rate"], label="max goal rate")
    home = _positive_decimal(home_mean, label="home goal rate")
    away = _positive_decimal(away_mean, label="away goal rate")
    if home > maximum_rate or away > maximum_rate:
        raise ScoreModelInputError("goal rate exceeds frozen maximum")
    correlation = _decimal(rho, label="dixon_coles rho")
    if correlation < _decimal(policy["dixon_coles_rho_min"], label="rho minimum") or correlation > _decimal(
        policy["dixon_coles_rho_max"], label="rho maximum"
    ):
        raise ScoreModelInputError("dixon_coles rho exceeds frozen bounds")
    dispersion = _positive_decimal(negative_binomial_dispersion, label="negative binomial dispersion")
    poisson_home = poisson_distribution(decimal_text(home), policy["max_goals"])
    poisson_away = poisson_distribution(decimal_text(away), policy["max_goals"])
    dixon_coles = dixon_coles_scoreline_distribution(decimal_text(home), decimal_text(away), decimal_text(correlation), policy["max_goals"])
    skellam = skellam_distribution(decimal_text(home), decimal_text(away), policy["max_goal_difference"])
    negative_binomial = negative_binomial_distribution(
        decimal_text(home + away), decimal_text(dispersion), policy["max_negative_binomial_count"]
    )
    mappings = _scoreline_mappings(dixon_coles)
    skellam_mapping = _skellam_one_x_two(skellam)
    tails = {
        "poisson_home": _decimal(poisson_home["tail_probability"], label="poisson home tail"),
        "poisson_away": _decimal(poisson_away["tail_probability"], label="poisson away tail"),
        "dixon_coles": _decimal(dixon_coles["tail_probability"], label="dixon_coles tail"),
        "skellam": _decimal(skellam["tail_probability"], label="skellam tail"),
        "negative_binomial": _decimal(negative_binomial["tail_probability"], label="negative binomial tail"),
    }
    tail_tolerance = _decimal(policy["tail_tolerance"], label="tail tolerance")
    mapping_status = (
        "COMPLETE_WITHIN_TAIL_TOLERANCE"
        if all(value <= tail_tolerance for value in tails.values()) and all(
            mapping["status"] == "COMPLETE_WITHIN_TAIL_TOLERANCE" for mapping in mappings.values()
        ) and skellam_mapping["status"] == "COMPLETE_WITHIN_TAIL_TOLERANCE"
        else "MARKET_ONLY_TAIL_ABOVE_TOLERANCE"
    )
    return {
        "model_registry_id": MODEL_REGISTRY_ID,
        "home_goal_rate": decimal_text(home),
        "away_goal_rate": decimal_text(away),
        "dixon_coles_rho": decimal_text(correlation),
        "negative_binomial_dispersion": decimal_text(dispersion),
        "poisson": {
            "home_finite_mass": poisson_home["finite_mass"],
            "home_tail_probability": poisson_home["tail_probability"],
            "away_finite_mass": poisson_away["finite_mass"],
            "away_tail_probability": poisson_away["tail_probability"],
        },
        "dixon_coles": {
            "finite_mass": dixon_coles["finite_mass"],
            "tail_probability": dixon_coles["tail_probability"],
            "maximum_goal": dixon_coles["maximum_goal"],
        },
        "skellam": {
            "finite_mass": skellam["finite_mass"],
            "tail_probability": skellam["tail_probability"],
            "maximum_difference": skellam["maximum_difference"],
            "one_x_two": skellam_mapping,
        },
        "negative_binomial": {
            "finite_mass": negative_binomial["finite_mass"],
            "tail_probability": negative_binomial["tail_probability"],
            "maximum_goals": negative_binomial["maximum_goals"],
        },
        "market_mappings": mappings,
        "mapping_status": mapping_status,
        "tail_tolerance": decimal_text(tail_tolerance),
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_accessed": False,
        "real_time_soak_waited": False,
    }
