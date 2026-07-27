from __future__ import annotations

import copy
import re
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any

from .canonical import canonical_decimal, canonical_json_bytes, decimal_from, sha256_hex, strict_json_loads
from .dataset import MAX_DATASET_BYTES, PIT_DATASET_SCHEMA, validate_pit_dataset
from .errors import EFSError

TRAINING_CONFIG_SCHEMA = "efs.deterministic_training_config.v1"
TRAINING_RUN_SCHEMA = "efs.deterministic_training_run.v1"
DIRECTION_ARTIFACT_SCHEMA = "efs.linear_logit_artifact.v1"
CALIBRATION_ARTIFACT_SCHEMA = "efs.platt_calibration_artifact.v1"
OOS_RECORD_SCHEMA = "efs.oos_forecast_record.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_CONFIG_KEYS = {
    "schema",
    "config_id",
    "feature_names",
    "iterations",
    "learning_rate",
    "l2",
    "calibration_iterations",
    "calibration_learning_rate",
    "score_clip",
    "probability_clip",
    "config_sha256",
}


def _load_mapping(value: dict[str, Any] | str | bytes, field: str, max_bytes: int) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = canonical_json_bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object or JSON payload")
    parsed = strict_json_loads(raw, max_bytes=max_bytes)
    if not isinstance(parsed, dict):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
    return parsed


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise EFSError("CONTRACT_INVALID", f"{field} contains unknown keys: {', '.join(unknown)}")


def _int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (minimum <= value <= maximum):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _probability(value: Any, field: str) -> Decimal:
    result = decimal_from(value, field)
    if result <= 0 or result >= 1:
        raise EFSError("CONTRACT_INVALID", f"{field} must be strictly between zero and one")
    return result


def validate_training_config(config: dict[str, Any] | str | bytes) -> dict[str, Any]:
    value = _load_mapping(config, "training config", 128_000)
    _reject_unknown(value, _CONFIG_KEYS, "training config")
    if value.get("schema") != TRAINING_CONFIG_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported training config schema")
    config_id = value.get("config_id")
    if not isinstance(config_id, str) or not config_id:
        raise EFSError("CONTRACT_INVALID", "training config.config_id must be a non-empty string")
    features = value.get("feature_names")
    if not isinstance(features, list) or not features:
        raise EFSError("CONTRACT_INVALID", "training config.feature_names must be unique and sorted")
    if any(not isinstance(item, str) or not item for item in features):
        raise EFSError("CONTRACT_INVALID", "training config feature names must be non-empty strings")
    if features != sorted(features) or len(features) != len(set(features)):
        raise EFSError("CONTRACT_INVALID", "training config.feature_names must be unique and sorted")
    _int(value.get("iterations"), "training config.iterations", 1, 10_000)
    _int(value.get("calibration_iterations"), "training config.calibration_iterations", 1, 10_000)
    learning_rate = decimal_from(value.get("learning_rate"), "training config.learning_rate")
    calibration_rate = decimal_from(value.get("calibration_learning_rate"), "training config.calibration_learning_rate")
    l2 = decimal_from(value.get("l2"), "training config.l2")
    score_clip = decimal_from(value.get("score_clip"), "training config.score_clip")
    probability_clip = _probability(value.get("probability_clip"), "training config.probability_clip")
    if learning_rate <= 0 or learning_rate > 1 or calibration_rate <= 0 or calibration_rate > 1:
        raise EFSError("CONTRACT_INVALID", "training learning rates must be in (0, 1]")
    if l2 < 0 or l2 > 100:
        raise EFSError("CONTRACT_INVALID", "training config.l2 is outside the allowed range")
    if score_clip < 5 or score_clip > 100:
        raise EFSError("CONTRACT_INVALID", "training config.score_clip must be from 5 to 100")
    if probability_clip >= Decimal("0.1"):
        raise EFSError("CONTRACT_INVALID", "training probability clip must be below 0.1")
    claimed = value.get("config_sha256")
    if not isinstance(claimed, str) or not SHA256_PATTERN.fullmatch(claimed):
        raise EFSError("CONTRACT_INVALID", "training config.config_sha256 must be a lowercase SHA-256")
    payload = dict(value)
    payload.pop("config_sha256")
    if claimed != sha256_hex(payload):
        raise EFSError("HASH_MISMATCH", "training config SHA-256 mismatch")
    return value


def _canonical(value: Decimal) -> str:
    """Round computed Decimal values before the shared precision guard."""
    with localcontext() as context:
        context.prec = 64
        rounded = value.quantize(Decimal("0.00000001"))
    return canonical_decimal(rounded)


def _sigmoid(value: Decimal, score_clip: Decimal) -> Decimal:
    clipped = max(-score_clip, min(score_clip, value))
    with localcontext() as context:
        context.prec = 50
        return Decimal(1) / (Decimal(1) + (-clipped).exp())


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        raise EFSError("CONTRACT_INVALID", "training split must not be empty")
    return sum(values, Decimal(0)) / Decimal(len(values))


def _quantile(values: list[Decimal], numerator: int, denominator: int) -> Decimal:
    if not values:
        raise EFSError("CONTRACT_INVALID", "quantile requires observations")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * Decimal(numerator) / Decimal(denominator)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] * (Decimal(1) - fraction) + ordered[upper] * fraction


def _fit_scaler(rows: list[dict[str, Any]], features: list[str]) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    means: dict[str, Decimal] = {}
    scales: dict[str, Decimal] = {}
    with localcontext() as context:
        context.prec = 50
        for name in features:
            values = [decimal_from(row["features"][name], f"row feature {name}") for row in rows]
            mean = _mean(values)
            variance = _mean([(item - mean) * (item - mean) for item in values])
            scale = variance.sqrt() if variance > 0 else Decimal(1)
            if scale < Decimal("0.000000000001"):
                scale = Decimal(1)
            means[name] = mean
            scales[name] = scale
    return means, scales


def _standardized(row: dict[str, Any], features: list[str], means: dict[str, Decimal], scales: dict[str, Decimal]) -> list[Decimal]:
    return [(decimal_from(row["features"][name], f"row feature {name}") - means[name]) / scales[name] for name in features]


def _fit_logit(
    vectors: list[list[Decimal]],
    labels: list[int],
    *,
    iterations: int,
    learning_rate: Decimal,
    l2: Decimal,
    score_clip: Decimal,
    initial_weights: list[Decimal] | None = None,
    initial_intercept: Decimal | None = None,
) -> tuple[list[Decimal], Decimal]:
    if not vectors or len(vectors) != len(labels):
        raise EFSError("CONTRACT_INVALID", "training vectors and labels are invalid")
    width = len(vectors[0])
    if width == 0 or any(len(vector) != width for vector in vectors):
        raise EFSError("CONTRACT_INVALID", "training vectors have inconsistent width")
    weights = list(initial_weights) if initial_weights is not None else [Decimal(0)] * width
    intercept = initial_intercept if initial_intercept is not None else Decimal(0)
    count = Decimal(len(vectors))
    with localcontext() as context:
        context.prec = 50
        for _ in range(iterations):
            grad_weights = [Decimal(0)] * width
            grad_intercept = Decimal(0)
            for vector, label in zip(vectors, labels):
                score = intercept + sum((weight * value for weight, value in zip(weights, vector)), Decimal(0))
                error = _sigmoid(score, score_clip) - Decimal(label)
                grad_intercept += error
                for index, value in enumerate(vector):
                    grad_weights[index] += error * value
            intercept -= learning_rate * grad_intercept / count
            for index in range(width):
                regularized = grad_weights[index] / count + l2 * weights[index]
                weights[index] -= learning_rate * regularized
    return weights, intercept


def _raw_linear_parameters(
    features: list[str],
    weights: list[Decimal],
    intercept: Decimal,
    means: dict[str, Decimal],
    scales: dict[str, Decimal],
) -> tuple[dict[str, Decimal], Decimal]:
    raw_weights = {name: weight / scales[name] for name, weight in zip(features, weights)}
    raw_intercept = intercept - sum((raw_weights[name] * means[name] for name in features), Decimal(0))
    return raw_weights, raw_intercept


def _score(row: dict[str, Any], features: list[str], raw_weights: dict[str, Decimal], raw_intercept: Decimal) -> Decimal:
    return raw_intercept + sum(
        (raw_weights[name] * decimal_from(row["features"][name], f"row feature {name}") for name in features),
        Decimal(0),
    )


def _build_oos_record(
    row: dict[str, Any],
    *,
    horizon: int,
    prob: Decimal,
    baseline: Decimal,
    p10: Decimal,
    p50: Decimal,
    p90: Decimal,
) -> dict[str, Any]:
    net_1x = decimal_from(row["net_return_1x"], "row net_return_1x")
    net_2x = decimal_from(row["net_return_2x"], "row net_return_2x")
    incremental_cost = net_1x - net_2x
    if incremental_cost < 0:
        raise EFSError("CONTRACT_INVALID", "cost stress implies negative incremental cost")
    gross = net_1x + incremental_cost
    up = prob * Decimal("0.95")
    down = (Decimal(1) - prob) * Decimal("0.95")
    timeout = Decimal("0.05")
    realized_event = "UP" if net_1x > 0 else "DOWN"
    year = datetime.fromisoformat(row["signal_as_of"].replace("Z", "+00:00")).year
    record: dict[str, Any] = {
        "schema": OOS_RECORD_SCHEMA,
        "record_id": f"training_{row['row_id']}",
        "forecast_as_of": row["signal_as_of"],
        "label_matured_at": row["label_matured_at"],
        "instrument_id": row["instrument_id"],
        "horizon": horizon,
        "cluster_id": f"year_{year}",
        "prob_up": _canonical(prob),
        "baseline_prob": _canonical(baseline),
        "gross_return": _canonical(gross),
        "cost_return": _canonical(incremental_cost),
        "p10": _canonical(p10),
        "p50": _canonical(p50),
        "p90": _canonical(p90),
        "timing_up": _canonical(up),
        "timing_down": _canonical(down),
        "timing_timeout": _canonical(timeout),
        "realized_event": realized_event,
    }
    record["source_record_sha256"] = sha256_hex(record)
    return record


def train_direction_pipeline(
    dataset: dict[str, Any] | str | bytes,
    config: dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    """Fit one deterministic linear direction model and frozen Platt calibration.

    The function has no model search, randomness, network, Agent, LLM, online
    learning, automatic promotion, or hidden use of HOLDOUT labels during fit.
    """
    dataset_map = _load_mapping(dataset, "PIT dataset", MAX_DATASET_BYTES)
    dataset_receipt = validate_pit_dataset(dataset_map)
    if dataset_map.get("schema") != PIT_DATASET_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported PIT dataset schema")
    frozen_config = validate_training_config(config)
    features = list(frozen_config["feature_names"])
    if features != dataset_map["feature_names"]:
        raise EFSError("CONTRACT_INVALID", "training feature set must exactly match PIT dataset")

    rows_by_split = {
        split: [copy.deepcopy(row) for row in dataset_map["rows"] if row["split"] == split]
        for split in ("TRAIN", "CALIBRATION", "HOLDOUT")
    }
    train_rows = rows_by_split["TRAIN"]
    calibration_rows = rows_by_split["CALIBRATION"]
    holdout_rows = rows_by_split["HOLDOUT"]
    means, scales = _fit_scaler(train_rows, features)
    train_vectors = [_standardized(row, features, means, scales) for row in train_rows]
    train_labels = [int(row["label"]) for row in train_rows]
    score_clip = decimal_from(frozen_config["score_clip"], "training score clip")
    weights, intercept = _fit_logit(
        train_vectors,
        train_labels,
        iterations=int(frozen_config["iterations"]),
        learning_rate=decimal_from(frozen_config["learning_rate"], "training learning rate"),
        l2=decimal_from(frozen_config["l2"], "training l2"),
        score_clip=score_clip,
    )
    raw_weights, raw_intercept = _raw_linear_parameters(features, weights, intercept, means, scales)

    calibration_scores = [[_score(row, features, raw_weights, raw_intercept)] for row in calibration_rows]
    calibration_labels = [int(row["label"]) for row in calibration_rows]
    calibration_weights, calibration_intercept = _fit_logit(
        calibration_scores,
        calibration_labels,
        iterations=int(frozen_config["calibration_iterations"]),
        learning_rate=decimal_from(frozen_config["calibration_learning_rate"], "calibration learning rate"),
        l2=Decimal(0),
        score_clip=score_clip,
        initial_weights=[Decimal(1)],
        initial_intercept=Decimal(0),
    )
    calibration_a = calibration_weights[0]
    calibration_b = calibration_intercept
    clip = decimal_from(frozen_config["probability_clip"], "probability clip")
    baseline = _mean([Decimal(label) for label in train_labels])
    baseline = max(clip, min(Decimal(1) - clip, baseline))

    train_returns = [decimal_from(row["net_return_1x"], "training net return") for row in train_rows]
    p10 = _quantile(train_returns, 1, 10)
    p50 = _quantile(train_returns, 1, 2)
    p90 = _quantile(train_returns, 9, 10)

    direction_artifact: dict[str, Any] = {
        "schema": DIRECTION_ARTIFACT_SCHEMA,
        "model_type": "linear_logit_v1",
        "feature_names": features,
        "weights": {name: _canonical(raw_weights[name]) for name in features},
        "intercept": _canonical(raw_intercept),
        "dataset_id": dataset_map["dataset_id"],
        "fit_rows_sha256": sha256_hex(train_rows),
        "training_config_sha256": frozen_config["config_sha256"],
        "fit_split": "TRAIN",
        "fit_method": "deterministic_full_batch_logit_v1",
    }
    direction_artifact["artifact_sha256"] = sha256_hex(direction_artifact)
    calibration_artifact: dict[str, Any] = {
        "schema": CALIBRATION_ARTIFACT_SCHEMA,
        "type": "platt_v1",
        "a": _canonical(calibration_a),
        "b": _canonical(calibration_b),
        "fit_split": "CALIBRATION",
        "dataset_id": dataset_map["dataset_id"],
        "calibration_rows_sha256": sha256_hex(calibration_rows),
        "direction_artifact_sha256": direction_artifact["artifact_sha256"],
        "training_config_sha256": frozen_config["config_sha256"],
        "fit_method": "deterministic_full_batch_platt_v1",
    }
    calibration_artifact["artifact_sha256"] = sha256_hex(calibration_artifact)

    holdout_records: list[dict[str, Any]] = []
    for row in holdout_rows:
        raw_score = _score(row, features, raw_weights, raw_intercept)
        calibrated = _sigmoid(calibration_a * raw_score + calibration_b, score_clip)
        calibrated = max(clip, min(Decimal(1) - clip, calibrated))
        holdout_records.append(
            _build_oos_record(
                row,
                horizon=int(dataset_map["horizon"]),
                prob=calibrated,
                baseline=baseline,
                p10=p10,
                p50=p50,
                p90=p90,
            )
        )

    run: dict[str, Any] = {
        "schema": TRAINING_RUN_SCHEMA,
        "status": "ENGINEERING_TRAINING_COMPLETE",
        "dataset_id": dataset_map["dataset_id"],
        "dataset_sha256": dataset_receipt["dataset_sha256"],
        "dataset_validation_receipt_sha256": dataset_receipt["receipt_sha256"],
        "training_config_id": frozen_config["config_id"],
        "training_config_sha256": frozen_config["config_sha256"],
        "horizon": dataset_map["horizon"],
        "label_contract_id": dataset_map["label_contract_id"],
        "cost_contract_sha256": dataset_map["cost_contract_sha256"],
        "split_counts": dataset_receipt["split_counts"],
        "direction_artifact": direction_artifact,
        "calibration_artifact": calibration_artifact,
        "baseline_prob": _canonical(baseline),
        "magnitude_reference": {
            "p10": _canonical(p10),
            "p50": _canonical(p50),
            "p90": _canonical(p90),
            "semantics": "TRAIN_SPLIT_REFERENCE_ONLY_NOT_VALIDATED_MAGNITUDE_HEAD",
        },
        "holdout_records": holdout_records,
        "holdout_records_sha256": sha256_hex(holdout_records),
        "automatic_promotion_permitted": False,
        "outcome_claim": "NOT_PROVEN",
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
        "random_seed_dependency": 0,
    }
    run["run_sha256"] = sha256_hex(run)
    return run
