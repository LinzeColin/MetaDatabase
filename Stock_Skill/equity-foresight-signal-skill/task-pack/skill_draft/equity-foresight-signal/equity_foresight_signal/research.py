from __future__ import annotations

from datetime import timedelta
from itertools import islice
from typing import Any, Iterable

from .canonical import canonical_json_bytes, sha256_hex, strict_json_loads
from .engine import _parse_time, _require_int, _require_machine_id, _require_sha256
from .errors import EFSError

WALK_FORWARD_CONFIG_SCHEMA = "efs.walk_forward_config.v1"
WALK_FORWARD_PLAN_SCHEMA = "efs.walk_forward_plan.v1"
TRIAL_MANIFEST_SCHEMA = "efs.trial_manifest.v1"
TRIAL_SCHEMA = "efs.trial_registration.v1"
MAX_WALK_FORWARD_RECORDS = 1_000_000
MAX_TRIALS = 100_000
CONFIG_KEYS = {
    "schema", "config_id", "horizon", "minimum_train_records", "test_block_records",
    "embargo_calendar_days", "maximum_folds", "config_sha256",
}
RECORD_KEYS = {"record_id", "forecast_as_of", "label_matured_at", "instrument_id", "record_sha256"}
TRIAL_KEYS = {
    "schema", "trial_id", "hypothesis_id", "created_at", "feature_set_sha256",
    "model_spec_sha256", "walk_forward_plan_sha256", "validation_policy_sha256",
    "dataset_snapshot_sha256", "parent_trial_id", "registration_sha256",
}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
    return value


def _load(value: dict[str, Any] | str | bytes, field: str, limit: int) -> dict[str, Any]:
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


def _validate_config(value: dict[str, Any] | str | bytes) -> dict[str, Any]:
    config = _load(value, "walk-forward config", 64_000)
    _reject_unknown(config, CONFIG_KEYS, "walk-forward config")
    if config.get("schema") != WALK_FORWARD_CONFIG_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported walk-forward config schema")
    _require_machine_id(config.get("config_id"), "walk-forward config.config_id")
    _require_int(config.get("horizon"), "walk-forward config.horizon", minimum=1, maximum=2520)
    _require_int(config.get("minimum_train_records"), "walk-forward config.minimum_train_records", minimum=10, maximum=100_000_000)
    _require_int(config.get("test_block_records"), "walk-forward config.test_block_records", minimum=1, maximum=1_000_000)
    _require_int(config.get("embargo_calendar_days"), "walk-forward config.embargo_calendar_days", minimum=0, maximum=3650)
    _require_int(config.get("maximum_folds"), "walk-forward config.maximum_folds", minimum=1, maximum=10_000)
    claimed = _require_sha256(config.get("config_sha256"), "walk-forward config.config_sha256")
    payload = dict(config)
    payload.pop("config_sha256")
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", "walk-forward config SHA-256 mismatch")
    return config


def _validate_record(value: Any) -> dict[str, Any]:
    record = _mapping(value, "walk-forward record")
    _reject_unknown(record, RECORD_KEYS, "walk-forward record")
    _require_machine_id(record.get("record_id"), "walk-forward record.record_id")
    _require_machine_id(record.get("instrument_id"), "walk-forward record.instrument_id")
    forecast = _parse_time(record.get("forecast_as_of"), "walk-forward record.forecast_as_of")
    matured = _parse_time(record.get("label_matured_at"), "walk-forward record.label_matured_at")
    if matured <= forecast:
        raise EFSError("POINT_IN_TIME_VIOLATION", "walk-forward label must mature after forecast")
    claimed = _require_sha256(record.get("record_sha256"), "walk-forward record.record_sha256")
    payload = dict(record)
    payload.pop("record_sha256")
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", "walk-forward record SHA-256 mismatch")
    return {**record, "_forecast": forecast, "_matured": matured}


def build_purged_walk_forward_plan(
    records: Iterable[dict[str, Any]],
    config: dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    frozen = _validate_config(config)
    try:
        source_items = list(islice(iter(records), MAX_WALK_FORWARD_RECORDS + 1))
    except TypeError as exc:
        raise EFSError("CONTRACT_INVALID", "walk-forward records must be iterable") from exc
    if len(source_items) > MAX_WALK_FORWARD_RECORDS:
        raise EFSError("RESOURCE_LIMIT", "walk-forward record limit exceeded")
    items = [_validate_record(item) for item in source_items]
    items.sort(key=lambda item: (item["forecast_as_of"], item["instrument_id"], item["record_id"]))
    ids = [item["record_id"] for item in items]
    if len(ids) != len(set(ids)):
        raise EFSError("CONTRACT_INVALID", "walk-forward records contain duplicate record_id")
    minimum_train = int(frozen["minimum_train_records"])
    test_block = int(frozen["test_block_records"])
    maximum_folds = int(frozen["maximum_folds"])
    if len(items) < minimum_train + test_block:
        raise EFSError("INSUFFICIENT_SUPPORT", "not enough records for one walk-forward fold")

    embargo = timedelta(days=int(frozen["embargo_calendar_days"]))
    folds: list[dict[str, Any]] = []
    test_start_index = minimum_train
    while test_start_index < len(items) and len(folds) < maximum_folds:
        test = items[test_start_index:test_start_index + test_block]
        if not test:
            break
        test_start = test[0]["_forecast"]
        cutoff = test_start - embargo
        train = [item for item in items[:test_start_index] if item["_matured"] < cutoff]
        if len(train) < minimum_train:
            test_start_index += test_block
            continue
        train_ids = [item["record_id"] for item in train]
        test_ids = [item["record_id"] for item in test]
        fold: dict[str, Any] = {
            "fold_id": f"fold_{len(folds) + 1:04d}",
            "train_record_ids": train_ids,
            "test_record_ids": test_ids,
            "train_count": len(train_ids),
            "test_count": len(test_ids),
            "train_last_label_matured_at": max(item["label_matured_at"] for item in train),
            "test_first_forecast_as_of": test[0]["forecast_as_of"],
            "test_last_forecast_as_of": test[-1]["forecast_as_of"],
            "embargo_calendar_days": int(frozen["embargo_calendar_days"]),
        }
        fold["fold_sha256"] = sha256_hex(fold)
        folds.append(fold)
        test_start_index += test_block
    if not folds:
        raise EFSError("INSUFFICIENT_SUPPORT", "purge and embargo leave no valid walk-forward fold")

    source_payload = [
        {key: item[key] for key in sorted(RECORD_KEYS)}
        for item in items
    ]
    plan: dict[str, Any] = {
        "schema": WALK_FORWARD_PLAN_SCHEMA,
        "config_id": frozen["config_id"],
        "config_sha256": frozen["config_sha256"],
        "horizon": frozen["horizon"],
        "record_count": len(items),
        "records_sha256": sha256_hex(source_payload),
        "fold_count": len(folds),
        "folds": folds,
        "leakage_contract": "TRAIN_LABEL_MATURED_STRICTLY_BEFORE_TEST_START_MINUS_EMBARGO",
        "automatic_model_selection_permitted": False,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    plan["plan_sha256"] = sha256_hex(plan)
    return plan


def _validate_trial(value: Any) -> dict[str, Any]:
    trial = _mapping(value, "trial registration")
    _reject_unknown(trial, TRIAL_KEYS, "trial registration")
    if trial.get("schema") != TRIAL_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported trial registration schema")
    for field in ("trial_id", "hypothesis_id"):
        _require_machine_id(trial.get(field), f"trial registration.{field}")
    parent = trial.get("parent_trial_id")
    if parent is not None:
        _require_machine_id(parent, "trial registration.parent_trial_id")
    _parse_time(trial.get("created_at"), "trial registration.created_at")
    for field in (
        "feature_set_sha256", "model_spec_sha256", "walk_forward_plan_sha256",
        "validation_policy_sha256", "dataset_snapshot_sha256",
    ):
        _require_sha256(trial.get(field), f"trial registration.{field}")
    claimed = _require_sha256(trial.get("registration_sha256"), "trial registration.registration_sha256")
    payload = dict(trial)
    payload.pop("registration_sha256")
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", "trial registration SHA-256 mismatch")
    return trial


def build_trial_manifest(trials: Iterable[dict[str, Any]]) -> dict[str, Any]:
    try:
        source_items = list(islice(iter(trials), MAX_TRIALS + 1))
    except TypeError as exc:
        raise EFSError("CONTRACT_INVALID", "trials must be iterable") from exc
    if not source_items:
        raise EFSError("CONTRACT_INVALID", "trial manifest must contain at least one trial")
    if len(source_items) > MAX_TRIALS:
        raise EFSError("RESOURCE_LIMIT", "trial manifest exceeds trial limit")
    validated = [_validate_trial(item) for item in source_items]
    validated.sort(key=lambda item: (item["created_at"], item["trial_id"]))
    ids = [item["trial_id"] for item in validated]
    if len(ids) != len(set(ids)):
        raise EFSError("CONTRACT_INVALID", "trial manifest contains duplicate trial_id")
    known: set[str] = set()
    for trial in validated:
        parent = trial.get("parent_trial_id")
        if parent is not None and parent not in known:
            raise EFSError("CONTRACT_INVALID", "trial parent must precede and exist in the manifest")
        known.add(trial["trial_id"])
    manifest: dict[str, Any] = {
        "schema": TRIAL_MANIFEST_SCHEMA,
        "trial_count": len(validated),
        "trials": validated,
        "multiple_testing_semantics": "ALL_TRIALS_COUNT_TOWARD_SELECTION_BIAS_CONTROL",
        "automatic_candidate_selection_permitted": False,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    manifest["manifest_sha256"] = sha256_hex(manifest)
    return manifest
