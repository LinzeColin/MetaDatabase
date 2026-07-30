from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .canonical import canonical_decimal, canonical_json_bytes, decimal_from, sha256_hex, strict_json_loads
from .errors import EFSError

PIT_DATASET_SCHEMA = "efs.pit_training_dataset.v1"
PIT_DATASET_RECEIPT_SCHEMA = "efs.pit_dataset_validation_receipt.v1"
SPLITS = ("TRAIN", "CALIBRATION", "HOLDOUT")
SCOPE_TYPES = {"single_instrument_v1", "universe_snapshot_v1"}
MAX_DATASET_BYTES = 50_000_000
MAX_ROWS = 100_000
MAX_FEATURES = 128
MACHINE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_DATASET_KEYS = {
    "schema",
    "dataset_id",
    "created_at",
    "calendar_id",
    "horizon",
    "label_contract_id",
    "cost_contract_sha256",
    "label_hurdle",
    "scope",
    "feature_names",
    "rows",
    "payload_sha256",
}
_ROW_KEYS = {
    "row_id",
    "instrument_id",
    "signal_as_of",
    "label_matured_at",
    "split",
    "label",
    "net_return_1x",
    "net_return_2x",
    "net_return_3x",
    "features",
    "source_snapshot_sha256",
    "row_payload_sha256",
}


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EFSError("CONTRACT_INVALID", f"{field} must be a non-empty RFC3339 UTC string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} is not RFC3339") from exc
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise EFSError("CONTRACT_INVALID", f"{field} must be UTC")
    return result.astimezone(timezone.utc)


def _machine_id(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise EFSError("CONTRACT_INVALID", f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value)
    if not MACHINE_ID_PATTERN.fullmatch(normalized):
        raise EFSError("CONTRACT_INVALID", f"{field} is not a valid machine id")
    return normalized


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise EFSError("CONTRACT_INVALID", f"{field} must be a lowercase SHA-256")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise EFSError("CONTRACT_INVALID", f"{field} contains unknown keys: {', '.join(unknown)}")


def _normalize(value: dict[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = canonical_json_bytes(value)
        if len(raw) > MAX_DATASET_BYTES:
            raise EFSError("RESOURCE_LIMIT", "dataset exceeds byte limit")
        parsed = strict_json_loads(raw, max_bytes=MAX_DATASET_BYTES)
    elif isinstance(value, (str, bytes)):
        parsed = strict_json_loads(value, max_bytes=MAX_DATASET_BYTES)
    else:
        raise EFSError("CONTRACT_INVALID", "dataset must be an object or JSON payload")
    if not isinstance(parsed, dict):
        raise EFSError("CONTRACT_INVALID", "dataset must be an object")
    return parsed


def _validate_scope(scope: Any) -> tuple[str, set[str]]:
    if not isinstance(scope, dict):
        raise EFSError("CONTRACT_INVALID", "dataset.scope must be an object")
    scope_type = _machine_id(scope.get("type"), "dataset.scope.type")
    if scope_type not in SCOPE_TYPES:
        raise EFSError("CONTRACT_INVALID", "unsupported dataset scope")
    if scope_type == "single_instrument_v1":
        _reject_unknown(scope, {"type", "instrument_id"}, "dataset.scope")
        instrument = _machine_id(scope.get("instrument_id"), "dataset.scope.instrument_id")
        return scope_type, {instrument}
    _reject_unknown(scope, {"type", "members", "snapshot_sha256"}, "dataset.scope")
    members = scope.get("members")
    if not isinstance(members, list) or not members:
        raise EFSError("CONTRACT_INVALID", "dataset.scope.members must be a non-empty array")
    if len(members) > MAX_ROWS:
        raise EFSError("RESOURCE_LIMIT", "dataset.scope.members exceeds limit")
    normalized = [_machine_id(item, "dataset.scope.members[]") for item in members]
    if normalized != sorted(normalized) or len(normalized) != len(set(normalized)):
        raise EFSError("CONTRACT_INVALID", "dataset.scope.members must be unique and canonically sorted")
    _sha(scope.get("snapshot_sha256"), "dataset.scope.snapshot_sha256")
    if scope["snapshot_sha256"] != sha256_hex(normalized):
        raise EFSError("HASH_MISMATCH", "dataset universe snapshot hash mismatch")
    return scope_type, set(normalized)


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("row_payload_sha256", None)
    return result


def validate_pit_dataset(dataset: dict[str, Any] | str | bytes) -> dict[str, Any]:
    """Validate a fully matured point-in-time training/evaluation dataset.

    This validates chronology and integrity only. It does not claim that the data
    source is economically useful, licensed beyond the declared scope, or capable
    of producing alpha.
    """
    value = _normalize(dataset)
    _reject_unknown(value, _DATASET_KEYS, "dataset")
    if value.get("schema") != PIT_DATASET_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported PIT dataset schema")
    dataset_id = _machine_id(value.get("dataset_id"), "dataset.dataset_id")
    created_at = _parse_time(value.get("created_at"), "dataset.created_at")
    calendar_id = _machine_id(value.get("calendar_id"), "dataset.calendar_id")
    horizon = value.get("horizon")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not (1 <= horizon <= 2520):
        raise EFSError("CONTRACT_INVALID", "dataset.horizon must be an integer from 1 to 2520")
    label_contract_id = _machine_id(value.get("label_contract_id"), "dataset.label_contract_id")
    cost_sha = _sha(value.get("cost_contract_sha256"), "dataset.cost_contract_sha256")
    hurdle = decimal_from(value.get("label_hurdle"), "dataset.label_hurdle")
    _scope_type, allowed_instruments = _validate_scope(value.get("scope"))

    feature_names = value.get("feature_names")
    if not isinstance(feature_names, list) or not feature_names:
        raise EFSError("CONTRACT_INVALID", "dataset.feature_names must be a non-empty array")
    if len(feature_names) > MAX_FEATURES:
        raise EFSError("RESOURCE_LIMIT", "dataset feature count exceeds limit")
    normalized_features = [_machine_id(item, "dataset.feature_names[]") for item in feature_names]
    if normalized_features != sorted(normalized_features) or len(normalized_features) != len(set(normalized_features)):
        raise EFSError("CONTRACT_INVALID", "dataset.feature_names must be unique and canonically sorted")
    expected_feature_set = set(normalized_features)

    rows = value.get("rows")
    if not isinstance(rows, list) or not rows:
        raise EFSError("CONTRACT_INVALID", "dataset.rows must be a non-empty array")
    if len(rows) > MAX_ROWS:
        raise EFSError("RESOURCE_LIMIT", "dataset row count exceeds limit")

    seen_rows: set[str] = set()
    canonical_order: list[tuple[str, str, str]] = []
    split_times: dict[str, list[datetime]] = {name: [] for name in SPLITS}
    split_counts: dict[str, int] = {name: 0 for name in SPLITS}
    positives = 0

    for index, raw_row in enumerate(rows):
        field = f"dataset.rows[{index}]"
        if not isinstance(raw_row, dict):
            raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
        _reject_unknown(raw_row, _ROW_KEYS, field)
        row_id = _machine_id(raw_row.get("row_id"), f"{field}.row_id")
        if row_id in seen_rows:
            raise EFSError("CONTRACT_INVALID", "dataset row_id values must be unique")
        seen_rows.add(row_id)
        instrument = _machine_id(raw_row.get("instrument_id"), f"{field}.instrument_id")
        if instrument not in allowed_instruments:
            raise EFSError("SCOPE_MISMATCH", f"{field}.instrument_id is outside dataset scope")
        signal = _parse_time(raw_row.get("signal_as_of"), f"{field}.signal_as_of")
        matured = _parse_time(raw_row.get("label_matured_at"), f"{field}.label_matured_at")
        if matured <= signal:
            raise EFSError("LOOKAHEAD_RISK", f"{field}.label_matured_at must be after signal_as_of")
        if matured > created_at:
            raise EFSError("LOOKAHEAD_RISK", f"{field} label was not matured when dataset was created")
        split = _machine_id(raw_row.get("split"), f"{field}.split")
        if split not in SPLITS:
            raise EFSError("CONTRACT_INVALID", f"{field}.split is unsupported")
        label = raw_row.get("label")
        if isinstance(label, bool) or label not in (0, 1):
            raise EFSError("CONTRACT_INVALID", f"{field}.label must be 0 or 1")
        net_1x = decimal_from(raw_row.get("net_return_1x"), f"{field}.net_return_1x")
        net_2x = decimal_from(raw_row.get("net_return_2x"), f"{field}.net_return_2x")
        net_3x = decimal_from(raw_row.get("net_return_3x"), f"{field}.net_return_3x")
        if not (net_3x <= net_2x <= net_1x):
            raise EFSError("CONTRACT_INVALID", f"{field} cost-stress returns must be non-increasing")
        expected_label = 1 if net_1x > hurdle else 0
        if label != expected_label:
            raise EFSError("LABEL_MISMATCH", f"{field}.label does not match net_return_1x and hurdle")
        features = raw_row.get("features")
        if not isinstance(features, dict) or set(features) != expected_feature_set:
            raise EFSError("CONTRACT_INVALID", f"{field}.features must exactly match dataset.feature_names")
        for name in normalized_features:
            decimal_from(features[name], f"{field}.features.{name}")
        _sha(raw_row.get("source_snapshot_sha256"), f"{field}.source_snapshot_sha256")
        row_sha = _sha(raw_row.get("row_payload_sha256"), f"{field}.row_payload_sha256")
        if row_sha != sha256_hex(_row_payload(raw_row)):
            raise EFSError("HASH_MISMATCH", f"{field} payload hash mismatch")
        canonical_order.append((raw_row["signal_as_of"], instrument, row_id))
        split_times[split].append(signal)
        split_counts[split] += 1
        positives += label

    if canonical_order != sorted(canonical_order):
        raise EFSError("CONTRACT_INVALID", "dataset rows must be canonically sorted by signal_as_of, instrument_id, row_id")
    for split in SPLITS:
        if split_counts[split] == 0:
            raise EFSError("CONTRACT_INVALID", f"dataset split {split} must not be empty")
    if max(split_times["TRAIN"]) >= min(split_times["CALIBRATION"]):
        raise EFSError("LOOKAHEAD_RISK", "TRAIN and CALIBRATION periods overlap or are out of order")
    if max(split_times["CALIBRATION"]) >= min(split_times["HOLDOUT"]):
        raise EFSError("LOOKAHEAD_RISK", "CALIBRATION and HOLDOUT periods overlap or are out of order")

    payload_sha = _sha(value.get("payload_sha256"), "dataset.payload_sha256")
    payload = dict(value)
    payload.pop("payload_sha256", None)
    if payload_sha != sha256_hex(payload):
        raise EFSError("HASH_MISMATCH", "dataset payload hash mismatch")

    receipt: dict[str, Any] = {
        "schema": PIT_DATASET_RECEIPT_SCHEMA,
        "status": "PASS",
        "dataset_id": dataset_id,
        "dataset_sha256": payload_sha,
        "calendar_id": calendar_id,
        "horizon": horizon,
        "label_contract_id": label_contract_id,
        "cost_contract_sha256": cost_sha,
        "row_count": len(rows),
        "feature_count": len(normalized_features),
        "split_counts": split_counts,
        "positive_count": positives,
        "positive_rate": canonical_decimal(Decimal(positives) / Decimal(len(rows))),
        "evaluation_start": rows[0]["signal_as_of"],
        "evaluation_end": rows[-1]["label_matured_at"],
        "point_in_time_checks": {
            "labels_matured_before_dataset_creation": True,
            "split_chronology_strict": True,
            "row_hashes_verified": True,
            "source_snapshots_bound": True,
            "universe_membership_bound": True,
        },
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    receipt["receipt_sha256"] = sha256_hex(receipt)
    return receipt
