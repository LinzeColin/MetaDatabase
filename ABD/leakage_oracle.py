"""Pure deterministic temporal-lineage gate for ABD S07/P02.

This module accepts only frozen, fully versioned lineage records. A record is
eligible only when every source, observation, availability, and feature cutoff
is available at or before the decision time. The permitted future-information
tolerance is exactly zero. Even an eligible record remains NO_ADVICE: this
phase never makes a recommendation, submits an order, accesses a network, or
waits for real-time soak.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"
FUTURE_INFORMATION_TOLERANCE = 0
LINEAGE_APPROVED_NO_ADVICE = "LINEAGE_APPROVED_NO_ADVICE"
NO_ADVICE = "NO_ADVICE"
SCHEMA_DRAFT_URI = "https:" + "//json-schema.org/draft/2020-12/schema"
SCHEMA_ID_URI = "https:" + "//abd.local/schemas/temporal_lineage/1.0.0"

REQUIRED_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "record_id",
        "source_id",
        "source_version_sha256",
        "source_payload_sha256",
        "source_time",
        "observed_time",
        "available_time",
        "feature_cutoff_time",
        "decision_time",
        "identity_key",
        "parameter_version_sha256",
        "model_id",
        "model_version_sha256",
        "feature_manifest_sha256",
        "reference_odds_decimal",
    }
)
REQUIRED_POLICY_FIELDS = frozenset(
    {
        "schema_content_sha256",
        "parameter_version_sha256",
        "source_versions",
        "model_versions",
        "future_information_tolerance",
    }
)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$"
)
RECORD_ID_RE = re.compile(r"^TLR-[A-Z0-9][A-Z0-9_-]{2,63}$")
SOURCE_ID_RE = re.compile(r"^SRC-[A-Z0-9_-]{3,64}$")
MODEL_ID_RE = re.compile(r"^MODEL-[A-Z0-9_-]{3,64}$")
IDENTITY_KEY_RE = re.compile(r"^IDK-S07P01-[A-Z0-9_-]{8,64}$")
ODDS_RE = re.compile(r"^[1-9][0-9]*(?:\.[0-9]+)?$")


class LineageValidationError(ValueError):
    """A fail-closed validation error with a stable structured code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PreparedLineagePolicy:
    schema_content_sha256: str
    parameter_version_sha256: str
    source_versions: tuple[tuple[str, str], ...]
    model_versions: tuple[tuple[str, str], ...]
    future_information_tolerance: int

    def source_version_for(self, source_id: str) -> str | None:
        return dict(self.source_versions).get(source_id)

    def model_version_for(self, model_id: str) -> str | None:
        return dict(self.model_versions).get(model_id)


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LineageValidationError("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def _reject_float(token: str) -> Any:
    raise LineageValidationError("BINARY_FLOAT_NOT_ALLOWED", token)


def _reject_constant(token: str) -> Any:
    raise LineageValidationError("NON_FINITE_JSON_NUMBER", token)


def strict_json_load(path: Path) -> Any:
    """Load JSON without duplicate keys, binary floats, or NaN values."""

    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical bytes after rejecting hidden binary floating-point data."""

    _reject_binary_float(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_binary_float(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise LineageValidationError("BINARY_FLOAT_NOT_ALLOWED", path)
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_binary_float(item, "%s.%s" % (path, key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_binary_float(item, "%s[%d]" % (path, index))


def _require_mapping(value: Any, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LineageValidationError(code, "%s must be an object" % label)
    return value


def _require_string(value: Any, code: str, label: str) -> str:
    if not isinstance(value, str):
        raise LineageValidationError(code, "%s must be a string" % label)
    return value


def _require_sha256(value: Any, label: str) -> str:
    rendered = _require_string(value, "HASH_INVALID", label)
    if not SHA256_RE.fullmatch(rendered):
        raise LineageValidationError("HASH_INVALID", label)
    return rendered


def _parse_time(value: Any, label: str) -> datetime:
    rendered = _require_string(value, "MALFORMED_TIMESTAMP", label)
    if not TIME_RE.fullmatch(rendered):
        raise LineageValidationError("TIMEZONE_REQUIRED", label)
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError as exc:
        raise LineageValidationError("MALFORMED_TIMESTAMP", "%s: %s" % (label, exc)) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LineageValidationError("TIMEZONE_REQUIRED", label)
    return parsed


def _parse_odds(value: Any) -> Decimal:
    rendered = _require_string(value, "ODDS_INVALID", "reference_odds_decimal")
    if not ODDS_RE.fullmatch(rendered):
        raise LineageValidationError("ODDS_INVALID", rendered)
    try:
        odds = Decimal(rendered)
    except InvalidOperation as exc:
        raise LineageValidationError("ODDS_INVALID", rendered) from exc
    if not odds.is_finite() or odds <= Decimal("1"):
        raise LineageValidationError("ODDS_INVALID", rendered)
    return odds


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise LineageValidationError("UNKNOWN_FIELD", "%s: %s" % (label, ",".join(unknown)))
    if missing:
        raise LineageValidationError("MISSING_FIELD", "%s: %s" % (label, ",".join(missing)))


def validate_schema_document(schema: Any) -> Mapping[str, Any]:
    """Validate the subset of the production schema used by this zero-leak gate."""

    payload = _require_mapping(schema, "SCHEMA_INVALID", "schema")
    expected_top_level = {
        "$id",
        "$schema",
        "additionalProperties",
        "properties",
        "required",
        "title",
        "type",
        "x_abd_artifact_id",
        "x_abd_contract_id",
        "x_abd_future_information_tolerance",
        "x_abd_production_equivalent",
    }
    if set(payload) != expected_top_level:
        raise LineageValidationError("SCHEMA_INVALID", "unexpected schema keys")
    if payload.get("$schema") != SCHEMA_DRAFT_URI:
        raise LineageValidationError("SCHEMA_INVALID", "draft")
    if payload.get("$id") != SCHEMA_ID_URI:
        raise LineageValidationError("SCHEMA_INVALID", "identifier")
    if payload.get("type") != "object" or payload.get("additionalProperties") is not False:
        raise LineageValidationError("SCHEMA_INVALID", "object boundary")
    if payload.get("x_abd_artifact_id") != "ART-S07-P02-01":
        raise LineageValidationError("SCHEMA_INVALID", "artifact")
    if payload.get("x_abd_contract_id") != "AC-S07-P02":
        raise LineageValidationError("SCHEMA_INVALID", "contract")
    if payload.get("x_abd_future_information_tolerance") != FUTURE_INFORMATION_TOLERANCE:
        raise LineageValidationError("SCHEMA_INVALID", "future-information tolerance")
    if payload.get("x_abd_production_equivalent") is not True:
        raise LineageValidationError("SCHEMA_INVALID", "production-equivalent marker")
    required = payload.get("required")
    properties = payload.get("properties")
    if not isinstance(required, list) or frozenset(required) != REQUIRED_RECORD_FIELDS or len(required) != len(REQUIRED_RECORD_FIELDS):
        raise LineageValidationError("SCHEMA_INVALID", "required fields")
    if not isinstance(properties, Mapping) or frozenset(properties) != REQUIRED_RECORD_FIELDS:
        raise LineageValidationError("SCHEMA_INVALID", "properties")
    if properties.get("schema_version", {}).get("const") != SCHEMA_VERSION:
        raise LineageValidationError("SCHEMA_INVALID", "schema version")
    for field in REQUIRED_RECORD_FIELDS - {"schema_version"}:
        definition = properties.get(field)
        if not isinstance(definition, Mapping) or definition.get("type") != "string":
            raise LineageValidationError("SCHEMA_INVALID", "property %s" % field)
    return payload


def prepare_policy(schema: Any, policy: Any) -> PreparedLineagePolicy:
    """Pin a schema, parameter version, source versions, and model versions."""

    validated_schema = validate_schema_document(schema)
    payload = _require_mapping(policy, "POLICY_INVALID", "policy")
    _require_exact_keys(payload, REQUIRED_POLICY_FIELDS, "policy")
    schema_content_sha256 = _require_sha256(payload["schema_content_sha256"], "schema_content_sha256")
    if schema_content_sha256 != sha256_json(validated_schema):
        raise LineageValidationError("SCHEMA_HASH_MISMATCH", schema_content_sha256)
    parameter_version_sha256 = _require_sha256(payload["parameter_version_sha256"], "parameter_version_sha256")
    tolerance = payload["future_information_tolerance"]
    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance != FUTURE_INFORMATION_TOLERANCE:
        raise LineageValidationError("FUTURE_INFORMATION_TOLERANCE_INVALID", str(tolerance))
    source_versions = _version_mapping(payload["source_versions"], SOURCE_ID_RE, "source_versions")
    model_versions = _version_mapping(payload["model_versions"], MODEL_ID_RE, "model_versions")
    return PreparedLineagePolicy(
        schema_content_sha256=schema_content_sha256,
        parameter_version_sha256=parameter_version_sha256,
        source_versions=tuple(sorted(source_versions.items())),
        model_versions=tuple(sorted(model_versions.items())),
        future_information_tolerance=tolerance,
    )


def _version_mapping(value: Any, identifier_re: re.Pattern[str], label: str) -> dict[str, str]:
    payload = _require_mapping(value, "POLICY_INVALID", label)
    if not payload:
        raise LineageValidationError("POLICY_INVALID", "%s empty" % label)
    result: dict[str, str] = {}
    for identifier, version in payload.items():
        if not isinstance(identifier, str) or not identifier_re.fullmatch(identifier):
            raise LineageValidationError("POLICY_INVALID", "%s identifier %r" % (label, identifier))
        result[identifier] = _require_sha256(version, "%s.%s" % (label, identifier))
    return result


def _validate_record(record: Any) -> tuple[Mapping[str, Any], dict[str, datetime], Decimal]:
    payload = _require_mapping(record, "RECORD_INVALID", "record")
    _reject_binary_float(payload)
    _require_exact_keys(payload, REQUIRED_RECORD_FIELDS, "record")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise LineageValidationError("SCHEMA_VERSION_MISMATCH", str(payload["schema_version"]))
    for field, pattern in (
        ("record_id", RECORD_ID_RE),
        ("source_id", SOURCE_ID_RE),
        ("model_id", MODEL_ID_RE),
        ("identity_key", IDENTITY_KEY_RE),
    ):
        value = _require_string(payload[field], "RECORD_INVALID", field)
        if not pattern.fullmatch(value):
            raise LineageValidationError("RECORD_INVALID", field)
    for field in (
        "source_version_sha256",
        "source_payload_sha256",
        "parameter_version_sha256",
        "model_version_sha256",
        "feature_manifest_sha256",
    ):
        _require_sha256(payload[field], field)
    times = {
        field: _parse_time(payload[field], field)
        for field in ("source_time", "observed_time", "available_time", "feature_cutoff_time", "decision_time")
    }
    odds = _parse_odds(payload["reference_odds_decimal"])
    return payload, times, odds


def _lineage_error_codes(policy: PreparedLineagePolicy, record: Mapping[str, Any], times: Mapping[str, datetime]) -> list[str]:
    errors: list[str] = []
    expected_source_version = policy.source_version_for(str(record["source_id"]))
    if expected_source_version is None:
        errors.append("SOURCE_NOT_PINNED")
    elif record["source_version_sha256"] != expected_source_version:
        errors.append("SOURCE_VERSION_MISMATCH")
    expected_model_version = policy.model_version_for(str(record["model_id"]))
    if expected_model_version is None:
        errors.append("MODEL_NOT_PINNED")
    elif record["model_version_sha256"] != expected_model_version:
        errors.append("MODEL_VERSION_MISMATCH")
    if record["parameter_version_sha256"] != policy.parameter_version_sha256:
        errors.append("PARAMETER_VERSION_MISMATCH")
    if times["source_time"] > times["observed_time"]:
        errors.append("SOURCE_TIME_AFTER_OBSERVED")
    if times["observed_time"] > times["available_time"]:
        errors.append("OBSERVED_TIME_AFTER_AVAILABLE")
    if times["available_time"] > times["feature_cutoff_time"]:
        errors.append("AVAILABLE_TIME_AFTER_FEATURE_CUTOFF")
    decision_time = times["decision_time"]
    future_fields = [
        field
        for field in ("source_time", "observed_time", "available_time", "feature_cutoff_time")
        if times[field] > decision_time
    ]
    if future_fields:
        errors.append("FUTURE_INFORMATION_TOLERANCE_EXCEEDED")
        errors.extend("FUTURE_%s" % field.upper() for field in future_fields)
    return errors


def _safe_record_sha256(record: Any) -> str:
    try:
        return sha256_json(record)
    except Exception:
        return "UNAVAILABLE"


def _result(
    *,
    status: str,
    lineage_eligible: bool,
    reason_codes: Sequence[str],
    record_sha256: str,
    future_information_count: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "lineage_eligible": lineage_eligible,
        "action": NO_ADVICE,
        "reason_codes": list(reason_codes),
        "future_information_tolerance": FUTURE_INFORMATION_TOLERANCE,
        "future_information_count": future_information_count,
        "record_sha256": record_sha256,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
    }
    payload["output_sha256"] = sha256_json(payload)
    return payload


def evaluate_lineage(policy: PreparedLineagePolicy, record: Any) -> dict[str, Any]:
    """Evaluate one record without allowing any side effect or future tolerance."""

    record_hash = _safe_record_sha256(record)
    try:
        payload, times, _odds = _validate_record(record)
        error_codes = _lineage_error_codes(policy, payload, times)
        future_count = sum(
            1
            for field in ("source_time", "observed_time", "available_time", "feature_cutoff_time")
            if times[field] > times["decision_time"]
        )
        if error_codes:
            return _result(
                status=NO_ADVICE,
                lineage_eligible=False,
                reason_codes=error_codes,
                record_sha256=record_hash,
                future_information_count=future_count,
            )
        return _result(
            status=LINEAGE_APPROVED_NO_ADVICE,
            lineage_eligible=True,
            reason_codes=[],
            record_sha256=record_hash,
            future_information_count=0,
        )
    except LineageValidationError as exc:
        return _result(
            status=NO_ADVICE,
            lineage_eligible=False,
            reason_codes=[exc.code],
            record_sha256=record_hash,
            future_information_count=0,
        )


def deterministic_lineage_hash(policy: PreparedLineagePolicy, record: Any) -> str:
    """Return the stable evidence hash for a record/policy evaluation."""

    return str(evaluate_lineage(policy, record)["output_sha256"])
