"""Deterministic market-anchored residual baseline for ABD S09/P01.

The module consumes only caller-provided frozen inputs.  It does not fetch
prices, make a recommendation, access an account, or submit an order.  A
candidate residual is ignored unless its domain increment is explicitly
verified and reproducible; otherwise the market vector remains authoritative.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
DECIMAL_PRECISION = 50
PROBABILITY_SUM_TOLERANCE = Decimal("0.000000000001")
MINIMUM_MARKET_PRIOR_WEIGHT = Decimal("0.50")
MAXIMUM_GENERIC_RESIDUAL_WEIGHT = Decimal("0.35")
FAMILY_IDS = ("binary", "multinomial", "spread", "total", "futures")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{0,79}")
_SHA256 = re.compile(r"[0-9a-f]{64}")

_FAMILY_REQUIREMENTS = {
    "binary": {
        "distribution": "BERNOULLI",
        "outcome_count": {"exact": 2},
        "settlement_line_required": False,
    },
    "multinomial": {
        "distribution": "CATEGORICAL",
        "outcome_count": {"minimum": 3},
        "settlement_line_required": False,
    },
    "spread": {
        "distribution": "BERNOULLI_SPREAD",
        "outcome_count": {"exact": 2},
        "settlement_line_required": True,
    },
    "total": {
        "distribution": "BERNOULLI_TOTAL",
        "outcome_count": {"exact": 2},
        "settlement_line_required": True,
    },
    "futures": {
        "distribution": "CATEGORICAL_FUTURES",
        "outcome_count": {"minimum": 2},
        "settlement_line_required": False,
    },
}


class GenericResidualInputError(ValueError):
    """Raised when a generic residual calculation cannot be made safely."""


def canonical_json_bytes(value: Any) -> bytes:
    """Render deterministic JSON used by tests and evidence hashes."""

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decimal_text(value: Decimal) -> str:
    """Render a finite Decimal without exponent notation or trailing zeroes."""

    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise GenericResidualInputError("%s must be an uppercase stable identifier" % label)
    return value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise GenericResidualInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise GenericResidualInputError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise GenericResidualInputError("%s must be finite" % label)
    return parsed


def _probability(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO < parsed < _ONE:
        raise GenericResidualInputError("%s must be strictly between zero and one" % label)
    return parsed


def _unit_interval(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed <= _ONE:
        raise GenericResidualInputError("%s must be in [0, 1]" % label)
    return parsed


def _probability_vector(value: Any, *, label: str) -> dict[str, Decimal]:
    if not isinstance(value, Mapping) or not value:
        raise GenericResidualInputError("%s must be a non-empty probability object" % label)
    parsed: dict[str, Decimal] = {}
    for raw_outcome_id, raw_probability in value.items():
        outcome_id = _identifier(raw_outcome_id, label="%s outcome" % label)
        if outcome_id in parsed:
            raise GenericResidualInputError("%s has duplicate outcome identifiers" % label)
        parsed[outcome_id] = _probability(raw_probability, label="%s.%s" % (label, outcome_id))
    total = sum(parsed.values(), _ZERO)
    if abs(total - _ONE) > PROBABILITY_SUM_TOLERANCE:
        raise GenericResidualInputError("%s must sum to one within tolerance" % label)
    return parsed


def _validate_outcome_count(probabilities: Mapping[str, Decimal], specification: Mapping[str, Any]) -> None:
    count = len(probabilities)
    outcome_count = specification["outcome_count"]
    if "exact" in outcome_count and count != outcome_count["exact"]:
        raise GenericResidualInputError("market family requires exactly %d outcomes" % outcome_count["exact"])
    if "minimum" in outcome_count and count < outcome_count["minimum"]:
        raise GenericResidualInputError("market family requires at least %d outcomes" % outcome_count["minimum"])


def validate_market_family_registry(registry: Any) -> Mapping[str, Any]:
    """Validate the complete S09/P01 registry, failing closed on drift."""

    if not isinstance(registry, Mapping):
        raise GenericResidualInputError("market family registry must be an object")
    if registry.get("schema_version") != "1.0.0" or registry.get("product_version") != "0.0.0.1":
        raise GenericResidualInputError("market family registry version is invalid")
    if registry.get("family_ids") != list(FAMILY_IDS):
        raise GenericResidualInputError("market family registry ids are invalid")
    families = registry.get("families")
    if not isinstance(families, list) or len(families) != len(FAMILY_IDS):
        raise GenericResidualInputError("market family registry must contain every generic family exactly once")
    rows = {row.get("id"): row for row in families if isinstance(row, Mapping)}
    if set(rows) != set(FAMILY_IDS) or len(rows) != len(families):
        raise GenericResidualInputError("market family registry identifiers are invalid or duplicated")
    for family_id in FAMILY_IDS:
        row = rows[family_id]
        expected = _FAMILY_REQUIREMENTS[family_id]
        if row.get("distribution") != expected["distribution"]:
            raise GenericResidualInputError("%s distribution is invalid" % family_id)
        if row.get("outcome_count") != expected["outcome_count"]:
            raise GenericResidualInputError("%s outcome count is invalid" % family_id)
        if row.get("settlement_line_required") is not expected["settlement_line_required"]:
            raise GenericResidualInputError("%s settlement-line requirement is invalid" % family_id)
        if row.get("residual_weight_cap_parameter") != "residual_weight_alpha_beta_max":
            raise GenericResidualInputError("%s must use the bounded generic residual parameter" % family_id)
        if row.get("fallback") != "MARKET_ONLY_OR_NO_ADVICE":
            raise GenericResidualInputError("%s fallback must remain market-only or no-advice" % family_id)
    return registry


def load_market_family_registry(path: Path | str) -> Mapping[str, Any]:
    """Read a local registry only; no network or external runtime is used."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenericResidualInputError("market family registry cannot be read") from exc
    return validate_market_family_registry(value)


def _family_specification(registry: Mapping[str, Any], family_id: Any) -> Mapping[str, Any]:
    validate_market_family_registry(registry)
    if not isinstance(family_id, str) or family_id not in FAMILY_IDS:
        raise GenericResidualInputError("market_family is unsupported")
    rows = {row["id"]: row for row in registry["families"]}
    return rows[family_id]


def _domain_increment(value: Any) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        raise GenericResidualInputError("domain_increment must be an object")
    status = value.get("status")
    if status in {"NONE", "UNVERIFIED", "UNAVAILABLE"}:
        if value.get("reproducible") is not False and "reproducible" in value:
            raise GenericResidualInputError("unverified domain increment cannot be reproducible")
        return False, str(status)
    if status != "VERIFIED" or value.get("reproducible") is not True:
        raise GenericResidualInputError("domain increment must be explicitly verified or explicitly unavailable")
    evidence_hash = value.get("evidence_sha256")
    if not isinstance(evidence_hash, str) or not _SHA256.fullmatch(evidence_hash):
        raise GenericResidualInputError("verified domain increment requires a SHA-256 evidence hash")
    _identifier(value.get("frozen_window_id"), label="domain_increment.frozen_window_id")
    return True, "VERIFIED"


def _market_parameters(value: Any, *, cap_parameter: str) -> tuple[Decimal, Decimal, Decimal]:
    if not isinstance(value, Mapping):
        raise GenericResidualInputError("market model parameters must be an object")
    market_model = value.get("market_model")
    if not isinstance(market_model, Mapping):
        raise GenericResidualInputError("market_model parameters are missing")
    market_prior_min = _unit_interval(market_model.get("market_prior_weight_min"), label="market_prior_weight_min")
    residual_cap = _unit_interval(market_model.get(cap_parameter), label=cap_parameter)
    no_increment_weight = _unit_interval(
        market_model.get("residual_weight_when_no_increment"), label="residual_weight_when_no_increment"
    )
    if market_prior_min < MINIMUM_MARKET_PRIOR_WEIGHT:
        raise GenericResidualInputError("market prior cannot be lowered below 0.50")
    if residual_cap > MAXIMUM_GENERIC_RESIDUAL_WEIGHT:
        raise GenericResidualInputError("generic residual cap cannot exceed 0.35")
    if no_increment_weight != _ZERO:
        raise GenericResidualInputError("no-domain-increment residual weight must remain zero")
    return market_prior_min, residual_cap, no_increment_weight


def calculate_market_anchored_residual(
    case: Mapping[str, Any], registry: Mapping[str, Any], parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """Fuse a verified residual into an eligible market vector.

    Any unavailable or unverified domain increment returns the untouched market
    vector with a zero residual weight.  This is a decision support primitive,
    not a recommendation or order function.
    """

    if not isinstance(case, Mapping):
        raise GenericResidualInputError("generic residual case must be an object")
    identifier = _identifier(case.get("id"), label="case.id")
    family_id = case.get("market_family")
    specification = _family_specification(registry, family_id)
    market_probabilities = _probability_vector(case.get("market_probabilities"), label="market_probabilities")
    _validate_outcome_count(market_probabilities, specification)
    settlement_line: str | None = None
    if specification["settlement_line_required"]:
        settlement_line = decimal_text(_decimal(case.get("settlement_line"), label="settlement_line"))
    elif "settlement_line" in case:
        raise GenericResidualInputError("settlement_line is only permitted for line-based market families")

    increment_proven, increment_status = _domain_increment(case.get("domain_increment"))
    requested_weight = _unit_interval(case.get("requested_residual_weight"), label="requested_residual_weight")
    market_prior_min, residual_cap, no_increment_weight = _market_parameters(
        parameters, cap_parameter=str(specification["residual_weight_cap_parameter"])
    )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        if increment_proven:
            residual_probabilities = _probability_vector(
                case.get("candidate_residual_probabilities"), label="candidate_residual_probabilities"
            )
            if set(residual_probabilities) != set(market_probabilities):
                raise GenericResidualInputError("candidate residual outcomes must exactly match market outcomes")
            residual_weight = min(requested_weight, residual_cap, _ONE - market_prior_min)
            decision = "MARKET_ANCHORED_VERIFIED_RESIDUAL"
        else:
            residual_probabilities = market_probabilities
            residual_weight = no_increment_weight
            decision = "MARKET_ONLY_NO_DOMAIN_INCREMENT"
        market_weight = _ONE - residual_weight
        if market_weight < market_prior_min:
            raise GenericResidualInputError("market prior minimum would be violated")
        outcomes = []
        final_total = _ZERO
        for outcome_id in sorted(market_probabilities):
            market_probability = market_probabilities[outcome_id]
            final_probability = (market_weight * market_probability) + (residual_weight * residual_probabilities[outcome_id])
            if not _ZERO < final_probability < _ONE:
                raise GenericResidualInputError("fused probability is not strictly interior")
            final_total += final_probability
            outcomes.append(
                {
                    "outcome_id": outcome_id,
                    "market_probability": decimal_text(market_probability),
                    "fused_probability": decimal_text(final_probability),
                }
            )
        if abs(final_total - _ONE) > PROBABILITY_SUM_TOLERANCE:
            raise GenericResidualInputError("fused probability vector is not complete")
    result: dict[str, Any] = {
        "id": identifier,
        "market_family": family_id,
        "distribution": specification["distribution"],
        "domain_increment_status": increment_status,
        "domain_increment_applied": increment_proven,
        "requested_residual_weight": decimal_text(requested_weight),
        "residual_weight": decimal_text(residual_weight),
        "market_prior_weight": decimal_text(market_weight),
        "outcomes": outcomes,
        "decision": decision,
        "recommendation_generated": False,
        "order_submission_enabled": False,
    }
    if settlement_line is not None:
        result["settlement_line"] = settlement_line
    return result


def build_report(
    fixture: Mapping[str, Any], registry: Mapping[str, Any], parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the canonical frozen S09/P01 residual report in memory."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != INPUT_MODE:
        raise GenericResidualInputError("fixture must be frozen synthetic input with no network or account")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise GenericResidualInputError("fixture must contain generic residual cases")
    results = [calculate_market_anchored_residual(case, registry, parameters) for case in cases]
    identifiers = [result["id"] for result in results]
    if len(set(identifiers)) != len(identifiers):
        raise GenericResidualInputError("fixture case identifiers must be unique")
    results.sort(key=lambda result: result["id"])
    no_increment = [result for result in results if result["domain_increment_applied"] is False]
    market_weights = [Decimal(result["market_prior_weight"]) for result in results]
    fixture_without_expected_hash = dict(fixture)
    fixture_without_expected_hash.pop("expected_report_sha256", None)
    return {
        "schema_version": "1.0.0",
        "product_version": "0.0.0.1",
        "contract_id": "AC-S09-P01",
        "stage_id": "S09",
        "phase_id": "P01",
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "fixture_sha256": hashlib.sha256(canonical_json_bytes(fixture_without_expected_hash)).hexdigest(),
        "registry_sha256": hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest(),
        "cases": results,
        "summary": {
            "case_count": len(results),
            "family_ids": sorted({result["market_family"] for result in results}),
            "no_domain_increment_case_count": len(no_increment),
            "all_no_domain_increment_weights_zero": all(Decimal(result["residual_weight"]) == _ZERO for result in no_increment),
            "minimum_market_prior_weight": decimal_text(min(market_weights)),
            "maximum_market_prior_weight": decimal_text(max(market_weights)),
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
