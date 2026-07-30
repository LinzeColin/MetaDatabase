from __future__ import annotations

from decimal import Decimal, localcontext
from itertools import islice
from typing import Any, Iterable

from .canonical import canonical_decimal, canonical_json_bytes, decimal_from, sha256_hex, strict_json_loads
from .engine import _parse_time, _require_int, _require_machine_id, _require_sha256
from .errors import EFSError

OOS_RECORD_SCHEMA = "efs.oos_forecast_record.v1"
VALIDATION_POLICY_SCHEMA = "efs.validation_policy.v1"
VALIDATION_REPORT_SCHEMA = "efs.validation_report.v1"
EVALUATION_ROLES = {"DISCOVERY", "OOS", "UNTOUCHED_HOLDOUT"}
REALIZED_EVENTS = {"UP", "DOWN", "TIMEOUT"}
MAX_OOS_RECORDS = 1_000_000
RECORD_KEYS = {
    "schema", "record_id", "forecast_as_of", "label_matured_at", "instrument_id",
    "horizon", "cluster_id", "prob_up", "baseline_prob", "gross_return", "cost_return",
    "p10", "p50", "p90", "timing_up", "timing_down", "timing_timeout",
    "realized_event", "source_record_sha256",
}
POLICY_KEYS = {
    "schema", "policy_id", "evaluation_role", "evaluation_as_of", "horizon", "hurdle",
    "calibration_bins", "minimum_records", "minimum_clusters", "minimum_brier_skill",
    "minimum_auc", "maximum_ece", "minimum_interval_coverage", "maximum_interval_coverage",
    "maximum_timing_brier", "cost_stress_multiplier", "minimum_mean_stressed_return",
    "maximum_monotonicity_violations", "subject_model_set_sha256",
    "trial_manifest_sha256", "dataset_snapshot_sha256", "policy_sha256",
}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
    return value


def _load_mapping(value: dict[str, Any] | str | bytes, field: str, limit: int) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = canonical_json_bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object or JSON payload")
    parsed = strict_json_loads(raw, max_bytes=limit)
    return _mapping(parsed, field)


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise EFSError("CONTRACT_INVALID", f"{field} contains unknown keys: {', '.join(unknown)}")


def _probability(value: Any, field: str) -> Decimal:
    result = decimal_from(value, field)
    if result < 0 or result > 1:
        raise EFSError("CONTRACT_INVALID", f"{field} must be between zero and one")
    return result


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        raise EFSError("CONTRACT_INVALID", "metric requires observations")
    return sum(values, Decimal(0)) / Decimal(len(values))


def _square(value: Decimal) -> Decimal:
    return value * value


def _auc(probabilities: list[Decimal], outcomes: list[int]) -> Decimal | None:
    positive = sum(outcomes)
    negative = len(outcomes) - positive
    if positive == 0 or negative == 0:
        return None
    ordered = sorted(zip(probabilities, outcomes), key=lambda item: item[0])
    rank_sum = Decimal(0)
    position = 1
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = (Decimal(position) + Decimal(position + (end - index) - 1)) / Decimal(2)
        rank_sum += average_rank * sum(item[1] for item in ordered[index:end])
        position += end - index
        index = end
    return (rank_sum - Decimal(positive * (positive + 1)) / Decimal(2)) / Decimal(positive * negative)


def _pinball(actual: Decimal, predicted: Decimal, quantile: Decimal) -> Decimal:
    error = actual - predicted
    return quantile * error if error >= 0 else (quantile - Decimal(1)) * error


def _validate_policy(value: dict[str, Any] | str | bytes) -> dict[str, Any]:
    policy = _load_mapping(value, "validation policy", 128_000)
    _reject_unknown(policy, POLICY_KEYS, "validation policy")
    if policy.get("schema") != VALIDATION_POLICY_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported validation policy schema")
    _require_machine_id(policy.get("policy_id"), "validation policy.policy_id")
    role = _require_machine_id(policy.get("evaluation_role"), "validation policy.evaluation_role")
    if role not in EVALUATION_ROLES:
        raise EFSError("CONTRACT_INVALID", "unsupported evaluation role")
    _parse_time(policy.get("evaluation_as_of"), "validation policy.evaluation_as_of")
    _require_sha256(policy.get("subject_model_set_sha256"), "validation policy.subject_model_set_sha256")
    _require_sha256(policy.get("trial_manifest_sha256"), "validation policy.trial_manifest_sha256")
    _require_sha256(policy.get("dataset_snapshot_sha256"), "validation policy.dataset_snapshot_sha256")
    _require_int(policy.get("horizon"), "validation policy.horizon", minimum=1, maximum=2520)
    decimal_from(policy.get("hurdle"), "validation policy.hurdle")
    bins = _require_int(policy.get("calibration_bins"), "validation policy.calibration_bins", minimum=2, maximum=50)
    _require_int(policy.get("minimum_records"), "validation policy.minimum_records", minimum=10, maximum=100_000_000)
    _require_int(policy.get("minimum_clusters"), "validation policy.minimum_clusters", minimum=2, maximum=1_000_000)
    _require_int(policy.get("maximum_monotonicity_violations"), "validation policy.maximum_monotonicity_violations", minimum=0, maximum=bins - 1)
    for key in (
        "minimum_brier_skill", "minimum_auc", "maximum_ece", "minimum_interval_coverage",
        "maximum_interval_coverage", "maximum_timing_brier", "cost_stress_multiplier",
        "minimum_mean_stressed_return",
    ):
        decimal_from(policy.get(key), f"validation policy.{key}")
    if _probability(policy["minimum_auc"], "validation policy.minimum_auc") < Decimal("0.5"):
        raise EFSError("CONTRACT_INVALID", "minimum AUC must be at least 0.5")
    if _probability(policy["maximum_ece"], "validation policy.maximum_ece") > Decimal("0.5"):
        raise EFSError("CONTRACT_INVALID", "maximum ECE is unreasonably large")
    low = _probability(policy["minimum_interval_coverage"], "validation policy.minimum_interval_coverage")
    high = _probability(policy["maximum_interval_coverage"], "validation policy.maximum_interval_coverage")
    if low > high:
        raise EFSError("CONTRACT_INVALID", "interval coverage bounds are inverted")
    _probability(policy["maximum_timing_brier"], "validation policy.maximum_timing_brier")
    if decimal_from(policy["cost_stress_multiplier"], "validation policy.cost_stress_multiplier") < 1:
        raise EFSError("CONTRACT_INVALID", "cost stress multiplier must be at least one")
    claimed = _require_sha256(policy.get("policy_sha256"), "validation policy.policy_sha256")
    payload = dict(policy)
    payload.pop("policy_sha256")
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", "validation policy SHA-256 mismatch")
    return policy


def _validate_record(value: Any, policy: dict[str, Any], evaluation_as_of) -> dict[str, Any]:
    record = _mapping(value, "OOS record")
    _reject_unknown(record, RECORD_KEYS, "OOS record")
    if record.get("schema") != OOS_RECORD_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported OOS record schema")
    _require_machine_id(record.get("record_id"), "OOS record.record_id")
    _require_machine_id(record.get("instrument_id"), "OOS record.instrument_id")
    _require_machine_id(record.get("cluster_id"), "OOS record.cluster_id")
    horizon = _require_int(record.get("horizon"), "OOS record.horizon", minimum=1, maximum=2520)
    if horizon != policy["horizon"]:
        raise EFSError("HORIZON_UNSUPPORTED", "OOS record horizon does not match validation policy")
    forecast_at = _parse_time(record.get("forecast_as_of"), "OOS record.forecast_as_of")
    matured_at = _parse_time(record.get("label_matured_at"), "OOS record.label_matured_at")
    if matured_at <= forecast_at:
        raise EFSError("POINT_IN_TIME_VIOLATION", "label must mature after the forecast")
    if matured_at > evaluation_as_of:
        raise EFSError("POINT_IN_TIME_VIOLATION", "label was not mature at evaluation_as_of")
    prob = _probability(record.get("prob_up"), "OOS record.prob_up")
    baseline = _probability(record.get("baseline_prob"), "OOS record.baseline_prob")
    gross = decimal_from(record.get("gross_return"), "OOS record.gross_return")
    cost = decimal_from(record.get("cost_return"), "OOS record.cost_return")
    if cost < 0:
        raise EFSError("CONTRACT_INVALID", "OOS record cost_return must be non-negative")
    p10 = decimal_from(record.get("p10"), "OOS record.p10")
    p50 = decimal_from(record.get("p50"), "OOS record.p50")
    p90 = decimal_from(record.get("p90"), "OOS record.p90")
    if not p10 <= p50 <= p90:
        raise EFSError("CONTRACT_INVALID", "OOS record quantiles cross")
    timing = {
        "UP": _probability(record.get("timing_up"), "OOS record.timing_up"),
        "DOWN": _probability(record.get("timing_down"), "OOS record.timing_down"),
        "TIMEOUT": _probability(record.get("timing_timeout"), "OOS record.timing_timeout"),
    }
    if abs(sum(timing.values(), Decimal(0)) - Decimal(1)) > Decimal("0.00000001"):
        raise EFSError("CONTRACT_INVALID", "OOS timing probabilities must sum to one")
    event = _require_machine_id(record.get("realized_event"), "OOS record.realized_event")
    if event not in REALIZED_EVENTS:
        raise EFSError("CONTRACT_INVALID", "unsupported realized event")
    claimed = _require_sha256(record.get("source_record_sha256"), "OOS record.source_record_sha256")
    payload = dict(record)
    payload.pop("source_record_sha256")
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", "OOS record SHA-256 mismatch")
    return {
        **record,
        "_forecast_at": forecast_at,
        "_matured_at": matured_at,
        "_prob": prob,
        "_baseline": baseline,
        "_gross": gross,
        "_cost": cost,
        "_p10": p10,
        "_p50": p50,
        "_p90": p90,
        "_timing": timing,
    }


def evaluate_oos_records(
    records: Iterable[dict[str, Any]],
    policy: dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    frozen_policy = _validate_policy(policy)
    evaluation_as_of = _parse_time(frozen_policy["evaluation_as_of"], "validation policy.evaluation_as_of")
    try:
        source_items = list(islice(iter(records), MAX_OOS_RECORDS + 1))
    except TypeError as exc:
        raise EFSError("CONTRACT_INVALID", "OOS records must be iterable") from exc
    if not source_items:
        raise EFSError("CONTRACT_INVALID", "OOS evaluation requires records")
    if len(source_items) > MAX_OOS_RECORDS:
        raise EFSError("RESOURCE_LIMIT", "OOS evaluation record limit exceeded")
    validated = [_validate_record(item, frozen_policy, evaluation_as_of) for item in source_items]
    validated.sort(key=lambda item: (item["forecast_as_of"], item["instrument_id"], item["record_id"]))
    ids = [item["record_id"] for item in validated]
    if len(ids) != len(set(ids)):
        raise EFSError("CONTRACT_INVALID", "OOS records contain duplicate record_id")

    hurdle = decimal_from(frozen_policy["hurdle"], "validation policy.hurdle")
    multiplier = decimal_from(frozen_policy["cost_stress_multiplier"], "validation policy.cost_stress_multiplier")
    outcomes = [1 if item["_gross"] - item["_cost"] > hurdle else 0 for item in validated]
    probabilities = [item["_prob"] for item in validated]
    baselines = [item["_baseline"] for item in validated]
    realized_1x = [item["_gross"] - item["_cost"] for item in validated]
    realized_stressed = [item["_gross"] - multiplier * item["_cost"] for item in validated]

    model_brier = _mean([_square(prob - Decimal(y)) for prob, y in zip(probabilities, outcomes)])
    baseline_brier = _mean([_square(prob - Decimal(y)) for prob, y in zip(baselines, outcomes)])
    brier_skill = None if baseline_brier == 0 else Decimal(1) - model_brier / baseline_brier
    auc = _auc(probabilities, outcomes)

    bin_count = int(frozen_policy["calibration_bins"])
    bins: list[dict[str, Any]] = []
    calibration_weighted_error = Decimal(0)
    for index in range(bin_count):
        lower = Decimal(index) / Decimal(bin_count)
        upper = Decimal(index + 1) / Decimal(bin_count)
        indices = [i for i, prob in enumerate(probabilities) if prob >= lower and (prob < upper or index == bin_count - 1)]
        if not indices:
            continue
        mean_pred = _mean([probabilities[i] for i in indices])
        observed = _mean([Decimal(outcomes[i]) for i in indices])
        gap = abs(mean_pred - observed)
        calibration_weighted_error += gap * Decimal(len(indices)) / Decimal(len(validated))
        bins.append({
            "lower": canonical_decimal(lower),
            "upper": canonical_decimal(upper),
            "count": len(indices),
            "mean_prediction": canonical_decimal(mean_pred),
            "observed_rate": canonical_decimal(observed),
            "absolute_gap": canonical_decimal(gap),
        })
    monotonicity_violations = sum(
        Decimal(current["observed_rate"]) < Decimal(previous["observed_rate"])
        for previous, current in zip(bins, bins[1:])
    )

    coverage = _mean([Decimal(item["_p10"] <= actual <= item["_p90"]) for item, actual in zip(validated, realized_1x)])
    pinball = {
        "p10": _mean([_pinball(actual, item["_p10"], Decimal("0.1")) for item, actual in zip(validated, realized_1x)]),
        "p50": _mean([_pinball(actual, item["_p50"], Decimal("0.5")) for item, actual in zip(validated, realized_1x)]),
        "p90": _mean([_pinball(actual, item["_p90"], Decimal("0.9")) for item, actual in zip(validated, realized_1x)]),
    }
    timing_brier = _mean([
        sum(_square(item["_timing"][event] - Decimal(event == item["realized_event"])) for event in ("UP", "DOWN", "TIMEOUT")) / Decimal(3)
        for item in validated
    ])

    minimum_records = int(frozen_policy["minimum_records"])
    minimum_clusters = int(frozen_policy["minimum_clusters"])
    cluster_count = len({item["cluster_id"] for item in validated})
    support_pass = len(validated) >= minimum_records and cluster_count >= minimum_clusters
    direction_checks = {
        "support": support_pass,
        "brier_skill": brier_skill is not None and brier_skill >= decimal_from(frozen_policy["minimum_brier_skill"], "minimum_brier_skill"),
        "auc": auc is not None and auc >= decimal_from(frozen_policy["minimum_auc"], "minimum_auc"),
        "ece": calibration_weighted_error <= decimal_from(frozen_policy["maximum_ece"], "maximum_ece"),
        "monotonicity": monotonicity_violations <= int(frozen_policy["maximum_monotonicity_violations"]),
    }
    magnitude_checks = {
        "support": support_pass,
        "coverage_lower": coverage >= decimal_from(frozen_policy["minimum_interval_coverage"], "minimum_interval_coverage"),
        "coverage_upper": coverage <= decimal_from(frozen_policy["maximum_interval_coverage"], "maximum_interval_coverage"),
    }
    timing_checks = {
        "support": support_pass,
        "brier": timing_brier <= decimal_from(frozen_policy["maximum_timing_brier"], "maximum_timing_brier"),
    }
    economic_checks = {
        "support": support_pass,
        "stressed_mean": _mean(realized_stressed) >= decimal_from(frozen_policy["minimum_mean_stressed_return"], "minimum_mean_stressed_return"),
    }

    def status(checks: dict[str, bool]) -> str:
        if not support_pass:
            return "INSUFFICIENT_SUPPORT"
        return "PASS" if all(checks.values()) else "FAIL"

    source_payload = [
        {key: item[key] for key in sorted(RECORD_KEYS)}
        for item in validated
    ]
    report: dict[str, Any] = {
        "schema": VALIDATION_REPORT_SCHEMA,
        "policy_id": frozen_policy["policy_id"],
        "policy_sha256": frozen_policy["policy_sha256"],
        "subject_model_set_sha256": frozen_policy["subject_model_set_sha256"],
        "trial_manifest_sha256": frozen_policy["trial_manifest_sha256"],
        "dataset_snapshot_sha256": frozen_policy["dataset_snapshot_sha256"],
        "evaluation_role": frozen_policy["evaluation_role"],
        "evaluation_as_of": frozen_policy["evaluation_as_of"],
        "horizon": frozen_policy["horizon"],
        "record_count": len(validated),
        "cluster_count": cluster_count,
        "evaluation_start": validated[0]["forecast_as_of"],
        "evaluation_end": validated[-1]["label_matured_at"],
        "records_sha256": sha256_hex(source_payload),
        "direction": {
            "status": status(direction_checks),
            "checks": direction_checks,
            "model_brier": canonical_decimal(model_brier),
            "baseline_brier": canonical_decimal(baseline_brier),
            "brier_skill": canonical_decimal(brier_skill) if brier_skill is not None else None,
            "auc": canonical_decimal(auc) if auc is not None else None,
            "ece": canonical_decimal(calibration_weighted_error),
            "monotonicity_violations": monotonicity_violations,
            "calibration_bins": bins,
        },
        "magnitude": {
            "status": status(magnitude_checks),
            "checks": magnitude_checks,
            "p10_p90_coverage": canonical_decimal(coverage),
            "pinball_loss": {key: canonical_decimal(value) for key, value in pinball.items()},
        },
        "timing": {
            "status": status(timing_checks),
            "checks": timing_checks,
            "multiclass_brier": canonical_decimal(timing_brier),
        },
        "economic_edge": {
            "status": status(economic_checks),
            "checks": economic_checks,
            "mean_net_return_1x_cost": canonical_decimal(_mean(realized_1x)),
            "mean_net_return_stressed_cost": canonical_decimal(_mean(realized_stressed)),
            "cost_stress_multiplier": canonical_decimal(multiplier),
        },
        "automatic_promotion_permitted": False,
        "promotion_semantics": "EVIDENCE_REPORT_ONLY_REQUIRES_SEPARATE_LIFECYCLE_DECISION",
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    report["overall_status"] = "PASS" if all(report[key]["status"] == "PASS" for key in ("direction", "magnitude", "timing", "economic_edge")) else "FAIL"
    report["report_sha256"] = sha256_hex(report)
    return report
