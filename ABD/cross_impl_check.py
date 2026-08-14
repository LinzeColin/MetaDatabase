"""Independent Decimal replay for the ABD S10/P03 fixed-point contract.

The module compares two local implementations over frozen synthetic vectors.
It has no provider, account, order, network, or wall-clock dependency.  A
numeric candidate is deliberately not an instruction to act on any market.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from decimal_math import evaluate_vector as authoritative_evaluate_vector


DECIMAL_PRECISION = 50
_I_PROBABILITY_STEP = Decimal("0.000000001")
_I_ODDS_STEP = Decimal("0.000001")
_I_FRACTION_STEP = Decimal("0.000000000001")
_I_ZERO = Decimal("0")
_I_ONE = Decimal("1")
_TOLERANCE = Decimal("0.000000000001")

VECTORS_ID = "VEC-S10-P03-FIXED-POINT"
CONTRACT_ID = "AC-S10-P03"
REQUIREMENT_ID = "REQ-S10-P03"
STAGE_ID = "S10"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
_VECTOR_IDS = (
    "V01-POSITIVE-CAPPED",
    "V02-NONPOSITIVE-ROUND-UP-FRICTION",
    "V03-PROBABILITY-ODDS-SCALE-DOWN",
    "V04-POSITIVE-INCREMENT-ROUND-DOWN",
    "V05-BOUNDARY-MINUS-ONE-IN-TEN-THOUSAND",
    "V06-BOUNDARY-PLUS-ONE-IN-TEN-THOUSAND",
)
_CONTRACT_FIELDS = {
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
_PARAMETER_NUMERIC_DETERMINISM = {
    "authoritative_decimal_precision_digits": 50,
    "money_storage": "INTEGER_CENTS",
    "probability_storage_scale": "1e-9",
    "odds_storage_scale": "1e-6",
    "binary_float_for_authoritative_decision": False,
    "probability_rounding": "DOWN",
    "odds_rounding": "DOWN",
    "friction_rounding": "UP",
    "stake_rounding": "DOWN_TO_PROVIDER_INCREMENT",
    "independent_implementation_absolute_tolerance": "1e-12",
    "action_must_match_across_implementations": True,
    "boundary_perturbation_absolute_probability": "0.0001",
    "boundary_perturbation_absolute_threshold": "0.0001",
    "boundary_perturbation_friction_up": "0.0001",
    "boundary_perturbation_time_adverse_seconds": 2,
    "odds_perturbation": "ONE_PROVIDER_TICK_ADVERSE",
    "unstable_action": "NO_RECOMMENDATION",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "actual_market_or_odds_observed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class CrossImplementationError(ValueError):
    """Raised when a frozen S10/P03 input is malformed or diverges."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CrossImplementationError("%s has an unexpected shape" % label)
    return value


def _i_decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise CrossImplementationError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CrossImplementationError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise CrossImplementationError("%s must be finite" % label)
    return parsed


def _i_integer(value: Any, *, label: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise CrossImplementationError("%s must be an integer at least %d" % (label, minimum))
    return value


def _i_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise CrossImplementationError("independent result must be finite Decimal")
    if value == _I_ZERO:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _i_quantize(value: Decimal, step: Decimal, rounding: str, *, label: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            return value.quantize(step, rounding=rounding)
    except InvalidOperation as exc:
        raise CrossImplementationError("%s cannot be represented at the required scale" % label) from exc


def _independent_validate_contract(value: Any) -> Mapping[str, Any]:
    contract = _strict_object(value, _CONTRACT_FIELDS, label="numeric_contract")
    expected = {key: _PARAMETER_NUMERIC_DETERMINISM[key] for key in _CONTRACT_FIELDS}
    if dict(contract) != expected:
        raise CrossImplementationError("numeric contract differs from frozen task-pack invariants")
    return contract


def _independent_validate_vector(value: Any) -> Mapping[str, Any]:
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
        raise CrossImplementationError("vector_id is invalid")
    probability = _i_decimal(vector["conservative_probability"], label="conservative_probability")
    odds = _i_decimal(vector["odds"], label="odds")
    friction = _i_decimal(vector["friction"], label="friction")
    cap = _i_decimal(vector["risk_fraction_cap"], label="risk_fraction_cap")
    if not _I_ZERO <= probability <= _I_ONE:
        raise CrossImplementationError("conservative_probability must be in [0, 1]")
    if odds <= _I_ONE:
        raise CrossImplementationError("odds must be greater than one")
    if not _I_ZERO <= friction < _I_ONE:
        raise CrossImplementationError("friction must be in [0, 1)")
    if not _I_ZERO <= cap <= _I_ONE:
        raise CrossImplementationError("risk_fraction_cap must be in [0, 1]")
    _i_integer(vector["bankroll_cents"], label="bankroll_cents", minimum=0)
    _i_integer(vector["stake_increment_cents"], label="stake_increment_cents", minimum=1)
    return vector


def independent_evaluate_vector(vector: Any, numeric_contract: Any) -> Mapping[str, Any]:
    """A separately written Decimal calculation used only for cross-checking."""

    _independent_validate_contract(numeric_contract)
    row = _independent_validate_vector(vector)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        probability = _i_quantize(
            _i_decimal(row["conservative_probability"], label="conservative_probability"),
            _I_PROBABILITY_STEP,
            ROUND_DOWN,
            label="conservative_probability",
        )
        odds = _i_quantize(_i_decimal(row["odds"], label="odds"), _I_ODDS_STEP, ROUND_DOWN, label="odds")
        friction = _i_quantize(
            _i_decimal(row["friction"], label="friction"),
            _I_PROBABILITY_STEP,
            ROUND_UP,
            label="friction",
        )
        risk_cap = _i_quantize(
            _i_decimal(row["risk_fraction_cap"], label="risk_fraction_cap"),
            _I_FRACTION_STEP,
            ROUND_DOWN,
            label="risk_fraction_cap",
        )
        bankroll_cents = _i_integer(row["bankroll_cents"], label="bankroll_cents", minimum=0)
        increment_cents = _i_integer(row["stake_increment_cents"], label="stake_increment_cents", minimum=1)
        # Deliberately use an algebraically equivalent form to the authority:
        # p * (odds - 1) - (1 - p) - friction.  This keeps the comparison
        # independent of the authority's expression and helper boundaries.
        net_edge = probability * (odds - _I_ONE) - (_I_ONE - probability) - friction
        if net_edge <= _I_ZERO or bankroll_cents == 0 or risk_cap == _I_ZERO:
            kelly_fraction = _I_ZERO
            stake_cents = 0
            action = "NO_RECOMMENDATION_NUMERIC_GUARD"
        else:
            raw_fraction = probability - ((_I_ONE - probability + friction) / (odds - _I_ONE))
            capped_fraction = min(max(raw_fraction, _I_ZERO), risk_cap)
            kelly_fraction = _i_quantize(capped_fraction, _I_FRACTION_STEP, ROUND_DOWN, label="kelly_fraction")
            whole_cents = int((Decimal(bankroll_cents) * kelly_fraction).to_integral_value(rounding=ROUND_DOWN))
            stake_cents = (whole_cents // increment_cents) * increment_cents
            action = "NO_ORDER_NUMERIC_CANDIDATE" if stake_cents > 0 else "NO_RECOMMENDATION_BELOW_INCREMENT"
    return {
        "vector_id": row["vector_id"],
        "conservative_probability": _i_text(probability),
        "odds": _i_text(odds),
        "friction": _i_text(friction),
        "net_edge": _i_text(net_edge),
        "kelly_fraction": _i_text(kelly_fraction),
        "stake_cents": stake_cents,
        "action": action,
    }


def _parameter_numeric_contract(parameters: Any) -> Mapping[str, Any]:
    if not isinstance(parameters, Mapping) or not isinstance(parameters.get("numeric_determinism"), Mapping):
        raise CrossImplementationError("numeric_determinism parameters are unavailable")
    numeric = parameters["numeric_determinism"]
    if dict(numeric) != _PARAMETER_NUMERIC_DETERMINISM:
        raise CrossImplementationError("numeric_determinism differs from frozen task-pack values")
    return {key: numeric[key] for key in _CONTRACT_FIELDS}


def validate_registry(registry: Any, parameters: Any) -> Mapping[str, Any]:
    """Validate the frozen registry before either implementation evaluates it."""

    fields = {
        "schema_version",
        "vectors_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "numeric_contract",
        "vectors",
    }
    row = _strict_object(registry, fields, label="numeric vectors registry")
    identity_ok = (
        row["schema_version"] == "1.0.0"
        and row["vectors_id"] == VECTORS_ID
        and row["contract_id"] == CONTRACT_ID
        and row["requirement_id"] == REQUIREMENT_ID
        and row["stage_id"] == STAGE_ID
        and row["phase_id"] == PHASE_ID
        and row["product_version"] == VERSION
        and row["fixed_clock"] == FIXED_CLOCK
        and row["input_mode"] == INPUT_MODE
    )
    if not identity_ok:
        raise CrossImplementationError("numeric vectors registry identity is invalid")
    parameter_contract = _parameter_numeric_contract(parameters)
    if dict(row["numeric_contract"]) != dict(parameter_contract):
        raise CrossImplementationError("registry numeric contract does not match frozen parameters")
    _independent_validate_contract(row["numeric_contract"])
    vectors = row["vectors"]
    if not isinstance(vectors, list) or [item.get("vector_id") if isinstance(item, Mapping) else None for item in vectors] != list(_VECTOR_IDS):
        raise CrossImplementationError("numeric vectors must be the exact frozen ordered set")
    for vector in vectors:
        _independent_validate_vector(vector)
    below = _i_decimal(vectors[-2]["conservative_probability"], label="boundary below probability")
    above = _i_decimal(vectors[-1]["conservative_probability"], label="boundary above probability")
    boundary = _i_decimal(_PARAMETER_NUMERIC_DETERMINISM["boundary_perturbation_absolute_probability"], label="boundary perturbation")
    if Decimal("0.600000000") - below != boundary or above - Decimal("0.600000000") != boundary:
        raise CrossImplementationError("one-in-ten-thousand probability boundary is invalid")
    return row


def _numeric_differences(authoritative: Mapping[str, Any], independent: Mapping[str, Any]) -> Mapping[str, str]:
    fields = ("conservative_probability", "odds", "friction", "net_edge", "kelly_fraction")
    return {
        field: _i_text(abs(_i_decimal(authoritative[field], label="authoritative.%s" % field) - _i_decimal(independent[field], label="independent.%s" % field)))
        for field in fields
    }


def _max_difference(differences: Mapping[str, str]) -> Decimal:
    return max((_i_decimal(value, label="difference") for value in differences.values()), default=_I_ZERO)


def report_sha256(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_report(registry: Any, parameters: Any) -> Mapping[str, Any]:
    """Replay all frozen vectors and report whether the two results coincide."""

    row = validate_registry(registry, parameters)
    contract = row["numeric_contract"]
    results: list[dict[str, Any]] = []
    for vector in row["vectors"]:
        authoritative = authoritative_evaluate_vector(vector, contract)
        independent = independent_evaluate_vector(vector, contract)
        differences = _numeric_differences(authoritative, independent)
        maximum = _max_difference(differences)
        results.append(
            {
                "vector_id": vector["vector_id"],
                "authoritative": authoritative,
                "independent": independent,
                "numeric_differences": differences,
                "max_abs_difference": _i_text(maximum),
                "within_tolerance": maximum <= _TOLERANCE,
                "actions_match": authoritative["action"] == independent["action"],
                "stakes_match": authoritative["stake_cents"] == independent["stake_cents"],
            }
        )
    overall_maximum = max((_i_decimal(item["max_abs_difference"], label="result difference") for item in results), default=_I_ZERO)
    all_within_tolerance = all(item["within_tolerance"] for item in results)
    actions_all_match = all(item["actions_match"] for item in results)
    stakes_all_match = all(item["stakes_match"] for item in results)
    passed = all_within_tolerance and actions_all_match and stakes_all_match
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "report_id": "RPT-S10-P03-DECIMAL-CROSS-IMPLEMENTATION",
        "vectors_id": VECTORS_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "numeric_contract": dict(contract),
        "tolerance": _i_text(_TOLERANCE),
        "results": results,
        "max_abs_difference": _i_text(overall_maximum),
        "all_within_tolerance": all_within_tolerance,
        "actions_all_match": actions_all_match,
        "stakes_all_match": stakes_all_match,
        "decision": "DECIMAL_FIXED_POINT_READY_DOWNSTREAM_ROBUSTNESS_GATE_REQUIRED" if passed else "NO_RECOMMENDATION_NUMERIC_DIVERGENCE",
        "next": "S10/P04_READY_NOT_STARTED" if passed else "S10/P03_BLOCKED",
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    report["report_sha256"] = report_sha256(report)
    return report


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CrossImplementationError("cannot read JSON: %s" % path) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD S10/P03 independent Decimal cross-check")
    parser.add_argument("--vectors", default="numeric_vectors.json")
    parser.add_argument("--parameters", default="machine/facts/parameters.json")
    args = parser.parse_args()
    report = build_report(load_json(Path(args.vectors)), load_json(Path(args.parameters)))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["decision"] == "DECIMAL_FIXED_POINT_READY_DOWNSTREAM_ROBUSTNESS_GATE_REQUIRED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
