"""Frozen adverse-perturbation gate for ABD S10/P04.

This module evaluates only local, synthetic boundary vectors.  It takes the
worst result across probability, threshold, friction, elapsed-time, odds, and
declared model-parameter scenarios.  A candidate that flips in any adverse
scenario is downgraded to ``NO_RECOMMENDATION``.  It does not access a
provider, account, market, order channel, or wall clock.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from decimal_math import (
    DECIMAL_PRECISION,
    FRACTION_STEP,
    ODDS_STEP,
    PROBABILITY_STEP,
    NumericContractError,
    decimal_text,
    evaluate_vector as decimal_evaluate_vector,
    normalize_fraction,
    normalize_friction,
    normalize_odds,
    normalize_probability,
)


VECTORS_ID = "VEC-S10-P04-ADVERSE-ROBUSTNESS"
CONTRACT_ID = "AC-S10-P04"
REQUIREMENT_ID = "REQ-S10-P04"
STAGE_ID = "S10"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
REPORT_ID = "RPT-S10-P04-ADVERSE-ROBUSTNESS"
_ZERO = Decimal("0")
_ONE = Decimal("1")
_CANDIDATE_ACTION = "NO_ORDER_NUMERIC_CANDIDATE"
_NO_RECOMMENDATION = "NO_RECOMMENDATION"
_CORE_NUMERIC_FIELDS = {
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
_NUMERIC_DETERMINISM = {
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
_VECTOR_IDS = (
    "V01-ROBUST-ALL-MARGINS",
    "V02-PROBABILITY-MINUS-FLIPS",
    "V03-PROBABILITY-MINUS-BOUNDARY-STABLE",
    "V04-THRESHOLD-PLUS-FLIPS",
    "V05-FRICTION-PLUS-FLIPS",
    "V06-TIME-PLUS-FLIPS",
    "V07-TIME-PLUS-BOUNDARY-STABLE",
    "V08-ODDS-TICK-FLIPS",
    "V09-ODDS-TICK-BOUNDARY-STABLE",
    "V10-BASE-NO-RECOMMENDATION",
    "V11-COMBINED-ONLY-FLIPS",
    "V12-FAVOURABLE-DIAGNOSTIC-NEVER-ENABLES",
)
_ADVERSE_SCENARIOS = (
    "probability_minus",
    "threshold_plus",
    "friction_plus",
    "time_plus",
    "odds_adverse",
    "parameter_worst_case",
    "all_adverse",
)
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


class RobustnessGateError(ValueError):
    """Raised when the frozen P04 numeric-stability contract is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _strict_object(value: Any, fields: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RobustnessGateError("%s has an unexpected shape" % label)
    return value


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise RobustnessGateError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RobustnessGateError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise RobustnessGateError("%s must be finite" % label)
    return parsed


def _integer(value: Any, *, label: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise RobustnessGateError("%s must be an integer at least %d" % (label, minimum))
    return value


def _quantize(value: Decimal, step: Decimal, rounding: str, *, label: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            return value.quantize(step, rounding=rounding)
    except InvalidOperation as exc:
        raise RobustnessGateError("%s cannot be represented at the required scale" % label) from exc


def _minimum_net_edge(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if not _ZERO <= parsed <= _ONE:
        raise RobustnessGateError("%s must be in [0, 1]" % label)
    return _quantize(parsed, PROBABILITY_STEP, ROUND_UP, label=label)


def _minimum_acceptable_odds(value: Any, *, label: str) -> Decimal:
    parsed = _decimal(value, label=label)
    if parsed <= _ONE:
        raise RobustnessGateError("%s must be greater than one" % label)
    return _quantize(parsed, ODDS_STEP, ROUND_UP, label=label)


def _core_numeric_contract(numeric: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: numeric[key] for key in _CORE_NUMERIC_FIELDS}


def _numeric_parameters(parameters: Any) -> Mapping[str, Any]:
    if not isinstance(parameters, Mapping) or not isinstance(parameters.get("numeric_determinism"), Mapping):
        raise RobustnessGateError("numeric_determinism parameters are unavailable")
    numeric = parameters["numeric_determinism"]
    if dict(numeric) != _NUMERIC_DETERMINISM:
        raise RobustnessGateError("numeric_determinism differs from frozen task-pack values")
    return numeric


def _expected_shape(value: Any) -> Mapping[str, Any]:
    fields = {"base_action", "gate_action", "adverse_flip_dimensions"}
    expected = _strict_object(value, fields, label="expected")
    if expected["base_action"] not in {_CANDIDATE_ACTION, _NO_RECOMMENDATION}:
        raise RobustnessGateError("expected.base_action is invalid")
    if expected["gate_action"] not in {_CANDIDATE_ACTION, _NO_RECOMMENDATION}:
        raise RobustnessGateError("expected.gate_action is invalid")
    flips = expected["adverse_flip_dimensions"]
    if not isinstance(flips, list) or any(item not in _ADVERSE_SCENARIOS for item in flips) or flips != sorted(set(flips), key=_ADVERSE_SCENARIOS.index):
        raise RobustnessGateError("expected.adverse_flip_dimensions is invalid")
    return expected


def validate_vector(value: Any) -> Mapping[str, Any]:
    fields = {
        "vector_id",
        "conservative_probability",
        "model_parameter_worst_probability",
        "odds",
        "friction",
        "minimum_net_edge",
        "minimum_acceptable_odds",
        "elapsed_seconds",
        "maximum_elapsed_seconds",
        "bankroll_cents",
        "risk_fraction_cap",
        "stake_increment_cents",
        "expected",
    }
    vector = _strict_object(value, fields, label="boundary vector")
    if not isinstance(vector["vector_id"], str) or not vector["vector_id"]:
        raise RobustnessGateError("vector_id is invalid")
    try:
        probability = normalize_probability(vector["conservative_probability"], label="conservative_probability")
        parameter_worst = normalize_probability(vector["model_parameter_worst_probability"], label="model_parameter_worst_probability")
        if parameter_worst > probability:
            raise RobustnessGateError("model_parameter_worst_probability cannot improve the conservative probability")
        normalize_odds(vector["odds"], label="odds")
        normalize_friction(vector["friction"], label="friction")
        _minimum_net_edge(vector["minimum_net_edge"], label="minimum_net_edge")
        _minimum_acceptable_odds(vector["minimum_acceptable_odds"], label="minimum_acceptable_odds")
        _integer(vector["elapsed_seconds"], label="elapsed_seconds", minimum=0)
        _integer(vector["maximum_elapsed_seconds"], label="maximum_elapsed_seconds", minimum=0)
        _integer(vector["bankroll_cents"], label="bankroll_cents", minimum=0)
        normalize_fraction(vector["risk_fraction_cap"], label="risk_fraction_cap")
        _integer(vector["stake_increment_cents"], label="stake_increment_cents", minimum=1)
        _expected_shape(vector["expected"])
    except NumericContractError as exc:
        raise RobustnessGateError("boundary vector violates the fixed-point contract: %s" % exc) from exc
    return vector


def validate_registry(registry: Any, parameters: Any) -> Mapping[str, Any]:
    """Validate the exact frozen P04 vectors and numeric contract."""

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
        "numeric_determinism",
        "vectors",
    }
    row = _strict_object(registry, fields, label="boundary vectors registry")
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
        raise RobustnessGateError("boundary vectors registry identity is invalid")
    numeric = _numeric_parameters(parameters)
    if dict(row["numeric_determinism"]) != dict(numeric):
        raise RobustnessGateError("boundary vectors numeric contract does not match frozen parameters")
    vectors = row["vectors"]
    if not isinstance(vectors, list) or [item.get("vector_id") if isinstance(item, Mapping) else None for item in vectors] != list(_VECTOR_IDS):
        raise RobustnessGateError("boundary vectors must be the exact frozen ordered set")
    for vector in vectors:
        validate_vector(vector)
    return row


def _normalized_inputs(vector: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "probability": normalize_probability(vector["conservative_probability"], label="conservative_probability"),
        "parameter_worst_probability": normalize_probability(vector["model_parameter_worst_probability"], label="model_parameter_worst_probability"),
        "odds": normalize_odds(vector["odds"], label="odds"),
        "friction": normalize_friction(vector["friction"], label="friction"),
        "minimum_net_edge": _minimum_net_edge(vector["minimum_net_edge"], label="minimum_net_edge"),
        "minimum_acceptable_odds": _minimum_acceptable_odds(vector["minimum_acceptable_odds"], label="minimum_acceptable_odds"),
        "elapsed_seconds": _integer(vector["elapsed_seconds"], label="elapsed_seconds", minimum=0),
        "maximum_elapsed_seconds": _integer(vector["maximum_elapsed_seconds"], label="maximum_elapsed_seconds", minimum=0),
        "bankroll_cents": _integer(vector["bankroll_cents"], label="bankroll_cents", minimum=0),
        "risk_fraction_cap": normalize_fraction(vector["risk_fraction_cap"], label="risk_fraction_cap"),
        "stake_increment_cents": _integer(vector["stake_increment_cents"], label="stake_increment_cents", minimum=1),
    }


def _scenario_inputs(base: Mapping[str, Any], scenario: str, numeric: Mapping[str, Any]) -> Mapping[str, Any]:
    probability_delta = _decimal(numeric["boundary_perturbation_absolute_probability"], label="boundary probability perturbation")
    threshold_delta = _decimal(numeric["boundary_perturbation_absolute_threshold"], label="boundary threshold perturbation")
    friction_delta = _decimal(numeric["boundary_perturbation_friction_up"], label="boundary friction perturbation")
    odds_delta = ODDS_STEP
    result = dict(base)
    if scenario in {"probability_minus", "all_adverse"}:
        result["probability"] = max(_ZERO, result["probability"] - probability_delta)
    elif scenario == "probability_plus":
        result["probability"] = min(_ONE, result["probability"] + probability_delta)
    if scenario in {"threshold_plus", "all_adverse"}:
        result["minimum_net_edge"] = result["minimum_net_edge"] + threshold_delta
    elif scenario == "threshold_minus":
        result["minimum_net_edge"] = max(_ZERO, result["minimum_net_edge"] - threshold_delta)
    if scenario in {"friction_plus", "all_adverse"}:
        result["friction"] = result["friction"] + friction_delta
    if scenario in {"time_plus", "all_adverse"}:
        result["elapsed_seconds"] += _integer(numeric["boundary_perturbation_time_adverse_seconds"], label="boundary time perturbation", minimum=0)
    if scenario in {"odds_adverse", "all_adverse"}:
        result["odds"] = result["odds"] - odds_delta
    if scenario == "parameter_worst_case":
        result["probability"] = result["parameter_worst_probability"]
    if scenario == "all_adverse":
        result["probability"] = min(result["probability"], result["parameter_worst_probability"])
    if result["odds"] <= _ONE or result["friction"] >= _ONE:
        raise RobustnessGateError("adverse scenario leaves the executable numeric domain")
    return {
        **result,
        "probability": normalize_probability(decimal_text(result["probability"]), label="scenario probability"),
        "odds": normalize_odds(decimal_text(result["odds"]), label="scenario odds"),
        "friction": normalize_friction(decimal_text(result["friction"]), label="scenario friction"),
        "minimum_net_edge": _minimum_net_edge(decimal_text(result["minimum_net_edge"]), label="scenario minimum_net_edge"),
    }


def _classify(inputs: Mapping[str, Any], numeric: Mapping[str, Any]) -> Mapping[str, Any]:
    decimal_vector = {
        "vector_id": "P04-LOCAL-CLASSIFICATION",
        "conservative_probability": decimal_text(inputs["probability"]),
        "odds": decimal_text(inputs["odds"]),
        "friction": decimal_text(inputs["friction"]),
        "bankroll_cents": inputs["bankroll_cents"],
        "risk_fraction_cap": decimal_text(inputs["risk_fraction_cap"]),
        "stake_increment_cents": inputs["stake_increment_cents"],
    }
    try:
        numeric_result = decimal_evaluate_vector(decimal_vector, _core_numeric_contract(numeric))
    except NumericContractError as exc:
        raise RobustnessGateError("decimal authority rejected robustness input: %s" % exc) from exc
    net_edge = _decimal(numeric_result["net_edge"], label="authoritative net_edge")
    if numeric_result["action"] != _CANDIDATE_ACTION:
        action = _NO_RECOMMENDATION
        reason = "NUMERIC_GUARD"
    elif net_edge < inputs["minimum_net_edge"]:
        action = _NO_RECOMMENDATION
        reason = "NET_EDGE_BELOW_THRESHOLD"
    elif inputs["odds"] < inputs["minimum_acceptable_odds"]:
        action = _NO_RECOMMENDATION
        reason = "ODDS_BELOW_MINIMUM"
    elif inputs["elapsed_seconds"] > inputs["maximum_elapsed_seconds"]:
        action = _NO_RECOMMENDATION
        reason = "TIME_EXPIRED"
    else:
        action = _CANDIDATE_ACTION
        reason = "NUMERIC_AND_HARD_GATES_PASS"
    return {
        "action": action,
        "reason": reason,
        "conservative_probability": decimal_text(inputs["probability"]),
        "odds": decimal_text(inputs["odds"]),
        "friction": decimal_text(inputs["friction"]),
        "minimum_net_edge": decimal_text(inputs["minimum_net_edge"]),
        "minimum_acceptable_odds": decimal_text(inputs["minimum_acceptable_odds"]),
        "elapsed_seconds": inputs["elapsed_seconds"],
        "maximum_elapsed_seconds": inputs["maximum_elapsed_seconds"],
        "net_edge": numeric_result["net_edge"],
        "stake_cents": numeric_result["stake_cents"],
    }


def evaluate_vector(vector: Any, numeric: Any) -> Mapping[str, Any]:
    """Run all frozen hard-boundary scenarios for a single P04 vector."""

    if not isinstance(numeric, Mapping) or dict(numeric) != _NUMERIC_DETERMINISM:
        raise RobustnessGateError("numeric contract is invalid")
    row = validate_vector(vector)
    base = _normalized_inputs(row)
    scenario_names = (
        "baseline",
        "probability_minus",
        "probability_plus",
        "threshold_minus",
        "threshold_plus",
        "friction_plus",
        "time_plus",
        "odds_adverse",
        "parameter_worst_case",
        "all_adverse",
    )
    scenarios = {name: _classify(_scenario_inputs(base, name, numeric), numeric) for name in scenario_names}
    base_action = scenarios["baseline"]["action"]
    adverse_flips = [
        name
        for name in _ADVERSE_SCENARIOS
        if base_action == _CANDIDATE_ACTION and scenarios[name]["action"] != _CANDIDATE_ACTION
    ]
    gate_action = _CANDIDATE_ACTION if base_action == _CANDIDATE_ACTION and not adverse_flips else _NO_RECOMMENDATION
    reason_codes = (
        ["ALL_ADVERSE_SCENARIOS_STABLE"]
        if gate_action == _CANDIDATE_ACTION
        else (["BASE_ACTION_NOT_CANDIDATE", scenarios["baseline"]["reason"]] if base_action != _CANDIDATE_ACTION else ["ADVERSE_ACTION_FLIP", *adverse_flips])
    )
    expected = row["expected"]
    expected_matches = {
        "base_action": expected["base_action"] == base_action,
        "gate_action": expected["gate_action"] == gate_action,
        "adverse_flip_dimensions": expected["adverse_flip_dimensions"] == adverse_flips,
    }
    return {
        "vector_id": row["vector_id"],
        "baseline": scenarios["baseline"],
        "scenarios": scenarios,
        "adverse_flip_dimensions": adverse_flips,
        "gate_action": gate_action,
        "reason_codes": reason_codes,
        "expected": expected,
        "expected_matches": expected_matches,
        "all_expected_matches": all(expected_matches.values()),
    }


def report_sha256(report: Mapping[str, Any]) -> str:
    payload = dict(report)
    payload.pop("report_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_report(registry: Any, parameters: Any) -> Mapping[str, Any]:
    """Build the complete frozen P04 robustness report."""

    row = validate_registry(registry, parameters)
    numeric = row["numeric_determinism"]
    results = [evaluate_vector(vector, numeric) for vector in row["vectors"]]
    all_expected = all(result["all_expected_matches"] for result in results)
    all_flips_force_no_recommendation = all(
        not result["adverse_flip_dimensions"] or result["gate_action"] == _NO_RECOMMENDATION for result in results
    )
    all_base_no_recommendations_remain_closed = all(
        result["baseline"]["action"] == _CANDIDATE_ACTION or result["gate_action"] == _NO_RECOMMENDATION for result in results
    )
    passed = all_expected and all_flips_force_no_recommendation and all_base_no_recommendations_remain_closed
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "report_id": REPORT_ID,
        "vectors_id": VECTORS_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "numeric_determinism": dict(numeric),
        "hard_boundary_scenarios": [
            "probability_minus",
            "probability_plus",
            "threshold_minus",
            "threshold_plus",
            "friction_plus",
            "time_plus",
            "odds_adverse",
            "parameter_worst_case",
            "all_adverse",
        ],
        "results": results,
        "all_hard_boundary_expectations_match": all_expected,
        "all_adverse_action_flips_force_no_recommendation": all_flips_force_no_recommendation,
        "base_no_recommendations_remain_closed": all_base_no_recommendations_remain_closed,
        "scope_boundary": "Frozen synthetic numeric vectors only; no live provider, platform, account, order, market coverage, or financial-return claim.",
        "decision": "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED" if passed else "NO_RECOMMENDATION_ROBUSTNESS_GATE_BLOCKED",
        "next": "S10/STAGE_REVIEW_READY_NOT_STARTED" if passed else "S10/P04_BLOCKED",
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
        raise RobustnessGateError("cannot read JSON: %s" % path) from exc


def write_report(vectors_path: Path, parameters_path: Path, output_path: Path) -> Mapping[str, Any]:
    report = build_report(load_json(vectors_path), load_json(parameters_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_bytes(canonical_json_bytes(report))
    temporary.replace(output_path)
    return {
        "status": "PASS" if report["decision"] == "ROBUSTNESS_GATE_READY_STAGE_REVIEW_REQUIRED" else "FAIL",
        "report": output_path.as_posix(),
        "report_sha256": report["report_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD S10/P04 frozen adverse robustness gate")
    parser.add_argument("--vectors", default="boundary_vectors.json")
    parser.add_argument("--parameters", default="machine/facts/parameters.json")
    parser.add_argument("--output", default="robustness_report.json")
    args = parser.parse_args()
    result = write_report(Path(args.vectors), Path(args.parameters), Path(args.output))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
