from __future__ import annotations

import copy
import re
import unicodedata
from itertools import islice
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Any, Iterable

from .canonical import canonical_decimal, canonical_json_bytes, decimal_from, sha256_hex, strict_json_loads
from .errors import EFSError

STABLE_ID = "equity-foresight-signal"
RUNTIME_VERSION = "0.0.0.1"
REQUEST_SCHEMA = "efs.forecast_request.v3"
BUNDLE_SCHEMA = "efs.forecast_bundle.v3"
RESULT_SCHEMA = "efs.forecast_signal_envelope.v3"
TRUST_SCHEMA = "efs.host_trust_context.v1"
PROMOTION_SCHEMA = "efs.promotion_evidence.v1"
VISUALIZATION_SCHEMA = "efs.visualization_envelope.v3"

GRADE_ORDER = {"RAW": 0, "SOURCE_VERIFIED": 1, "POINT_IN_TIME_VERIFIED": 2}
MATURITY_ORDER = {
    "NOT_AVAILABLE": 0,
    "ENGINEERING_VALIDATED": 1,
    "OOS_VALIDATED": 2,
    "OUTCOME_PROVEN": 3,
    "SUSPENDED": -1,
}
ASSURANCE_ORDER = {
    "NONE": 0,
    "HOST_POLICY_BOUND": 1,
    "CRYPTOGRAPHICALLY_VERIFIED": 2,
}
USAGE_MODES = {"RESEARCH", "SHADOW", "DECISION_SUPPORT"}
RELEASE_AUTHORIZED_MODES = {"RESEARCH", "SHADOW"}
RELEASE_CAPABILITY_CEILING = "SHADOW_ONLY"
TEMPORAL_SEMANTICS = {"OBSERVED_FACT", "SCHEDULED_FUTURE", "REVISED_SERIES", "MARKET_QUOTE"}
FRESHNESS_CLOCKS = {"EFFECTIVE_AT", "PUBLISHED_AT", "AVAILABLE_AT"}
ALLOWED_MODEL_TYPES = {"linear_logit_v1"}
ALLOWED_SCOPE_TYPES = {"single_instrument_v1", "universe_snapshot_v1"}
MACHINE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

DEFAULT_LIMITS = {
    "request_bytes": 256_000,
    "bundle_bytes": 1_000_000,
    "trust_bytes": 64_000,
    "max_features": 128,
    "max_experts": 16,
    "max_buckets": 64,
    "max_batch": 256,
}

REQUEST_KEYS = {
    "schema", "request_id", "instrument_id", "as_of", "horizon", "calendar_id",
    "label_contract_id", "cost_contract_sha256", "usage_mode", "features",
    "universe_snapshot_sha256",
}
FEATURE_KEYS = {
    "name", "value", "effective_at", "published_at", "available_at", "revision_id",
    "source", "source_dataset_id", "source_record_sha256", "license_id", "evidence_grade",
    "temporal_semantics", "unit", "transform_id", "transform_sha256", "conflict",
    "feature_payload_sha256",
}
BUNDLE_KEYS = {
    "schema", "stable_id", "runtime_version", "bundle_id", "created_at", "expires_at",
    "scope", "horizons", "calendar_id", "label_contract", "cost_contract",
    "feature_contracts", "experts", "admissible_expert_sets", "baseline", "calibration",
    "magnitude_head", "timing_head", "economic_edge_head", "reliability_head",
    "usage_policy", "runtime_limits", "model_set_sha256", "promotion_evidence", "payload_sha256",
}

MODEL_PAYLOAD_KEYS = (
    "scope",
    "horizons",
    "calendar_id",
    "label_contract",
    "cost_contract",
    "feature_contracts",
    "experts",
    "admissible_expert_sets",
    "baseline",
    "calibration",
    "magnitude_head",
    "timing_head",
    "economic_edge_head",
    "reliability_head",
    "usage_policy",
)
HEAD_STATUS_MAP = {
    "baseline": "baseline",
    "direction": "calibration",
    "magnitude": "magnitude_head",
    "timing": "timing_head",
    "economic_edge": "economic_edge_head",
    "reliability": "reliability_head",
}


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EFSError("CONTRACT_INVALID", f"{field} must be a non-empty RFC3339 UTC string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EFSError("CONTRACT_INVALID", f"{field} is not RFC3339") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise EFSError("CONTRACT_INVALID", f"{field} must be UTC")
    return dt.astimezone(timezone.utc)


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object")
    return value


def _normalize_json_mapping(value: Any, field: str, max_bytes: int) -> dict[str, Any]:
    if isinstance(value, (str, bytes)):
        parsed = strict_json_loads(value, max_bytes=max_bytes)
    elif isinstance(value, dict):
        raw = canonical_json_bytes(value)
        if len(raw) > max_bytes:
            raise EFSError("RESOURCE_LIMIT", f"{field} exceeds byte limit")
        parsed = strict_json_loads(raw, max_bytes=max_bytes)
    else:
        raise EFSError("CONTRACT_INVALID", f"{field} must be an object or JSON payload")
    return _require_mapping(parsed, field)


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an array")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EFSError("CONTRACT_INVALID", f"{field} must be a non-empty string")
    return unicodedata.normalize("NFC", value)


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise EFSError("CONTRACT_INVALID", f"{field} contains unknown keys: {', '.join(unknown)}")


def _validate_method(head: dict[str, Any], field: str, key: str) -> None:
    method = _require_machine_id(head.get(key), f"{field}.{key}")
    status = head.get("status")
    if _status_at_least(status, "OOS_VALIDATED") and method.startswith("engineering_fixture_"):
        raise EFSError("PROMOTION_EVIDENCE_INVALID", f"{field} calibrated status cannot use an engineering fixture method")


def _require_machine_id(value: Any, field: str) -> str:
    identifier = _require_string(value, field)
    if not MACHINE_ID_PATTERN.fullmatch(identifier):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an ASCII machine identifier")
    return identifier


def _require_sha256(value: Any, field: str) -> str:
    digest = _require_string(value, field)
    if not SHA256_PATTERN.fullmatch(digest):
        raise EFSError("CONTRACT_INVALID", f"{field} must be a lowercase SHA-256 hex digest")
    return digest


def _require_int(value: Any, field: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise EFSError("CONTRACT_INVALID", f"{field} must be an integer")
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise EFSError("CONTRACT_INVALID", f"{field} must be an integer")
        number = int(value)
    elif isinstance(value, int):
        number = value
    else:
        raise EFSError("CONTRACT_INVALID", f"{field} must be an integer")
    if number < minimum or (maximum is not None and number > maximum):
        code = "RESOURCE_LIMIT" if maximum is not None and number > maximum else "CONTRACT_INVALID"
        raise EFSError(code, f"{field} outside allowed range")
    return number


def _status_at_least(status: Any, required: str) -> bool:
    if not isinstance(status, str):
        return False
    return MATURITY_ORDER.get(status, -999) >= MATURITY_ORDER[required]


def _assurance_at_least(actual: Any, required: str) -> bool:
    if not isinstance(actual, str):
        return False
    return ASSURANCE_ORDER.get(actual, -999) >= ASSURANCE_ORDER[required]


def _sigmoid(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 42
        if value >= 0:
            z = (-value).exp()
            return Decimal(1) / (Decimal(1) + z)
        z = value.exp()
        return z / (Decimal(1) + z)


def _softmax(values: list[Decimal]) -> list[Decimal]:
    if not values:
        raise EFSError("CONTRACT_INVALID", "softmax requires at least one value")
    with localcontext() as context:
        context.prec = 42
        maximum = max(values)
        exps = [(value - maximum).exp() for value in values]
        denominator = sum(exps, Decimal(0))
        if denominator <= 0:
            raise EFSError("INTERNAL_ERROR", "invalid softmax denominator")
        return [value / denominator for value in exps]


def _weighted_sum(weights: dict[str, Any], values: dict[str, Decimal], intercept: Any, field: str) -> Decimal:
    result = decimal_from(intercept, f"{field}.intercept")
    for name, raw_weight in weights.items():
        if name not in values:
            raise EFSError("CONTRACT_INVALID", f"{field} references unavailable input: {name}")
        result += decimal_from(raw_weight, f"{field}.weights.{name}") * values[name]
    return result


def _validate_embedded_hash(value: dict[str, Any], field: str, hash_key: str = "artifact_sha256") -> str:
    claimed = _require_sha256(value.get(hash_key), f"{field}.{hash_key}")
    payload = copy.deepcopy(value)
    payload.pop(hash_key, None)
    actual = sha256_hex(payload)
    if claimed != actual:
        raise EFSError("BUNDLE_INTEGRITY_FAILED", f"{field} SHA-256 mismatch")
    return actual


def _validate_bundle_hash(bundle: dict[str, Any]) -> str:
    claimed = _require_sha256(bundle.get("payload_sha256"), "bundle.payload_sha256")
    payload = copy.deepcopy(bundle)
    payload.pop("payload_sha256", None)
    actual = sha256_hex(payload)
    if claimed != actual:
        raise EFSError("BUNDLE_INTEGRITY_FAILED", "bundle payload SHA-256 mismatch")
    return actual


def _model_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(bundle[key]) for key in MODEL_PAYLOAD_KEYS}


def _validate_scope(scope: dict[str, Any]) -> None:
    scope_type = _require_machine_id(scope.get("type"), "bundle.scope.type")
    if scope_type not in ALLOWED_SCOPE_TYPES:
        raise EFSError("CONTRACT_INVALID", "unsupported scope type")
    if scope_type == "single_instrument_v1":
        _require_machine_id(scope.get("instrument_id"), "bundle.scope.instrument_id")
        return
    members = _require_list(scope.get("members"), "bundle.scope.members")
    if not members:
        raise EFSError("CONTRACT_INVALID", "universe snapshot must not be empty")
    normalized_members = sorted({_require_machine_id(item, "bundle.scope.members[]") for item in members})
    if len(normalized_members) != len(members):
        raise EFSError("CONTRACT_INVALID", "universe snapshot contains duplicate members")
    if members != normalized_members:
        raise EFSError("CONTRACT_INVALID", "universe snapshot members must be canonically sorted")
    claimed = _require_sha256(scope.get("snapshot_sha256"), "bundle.scope.snapshot_sha256")
    if claimed != sha256_hex(normalized_members):
        raise EFSError("BUNDLE_INTEGRITY_FAILED", "universe snapshot hash mismatch")


def _validate_binding(head: dict[str, Any], field: str, bundle: dict[str, Any]) -> None:
    if head.get("label_contract_id") != bundle["label_contract"]["id"]:
        raise EFSError("CONTRACT_INVALID", f"{field} label contract mismatch")
    if head.get("cost_contract_sha256") != bundle["cost_contract"]["sha256"]:
        raise EFSError("CONTRACT_INVALID", f"{field} cost contract mismatch")
    if head.get("calendar_id") != bundle["calendar_id"]:
        raise EFSError("CONTRACT_INVALID", f"{field} calendar mismatch")
    horizon = _require_int(head.get("horizon"), f"{field}.horizon", minimum=1, maximum=2520)
    if horizon not in [int(item) for item in bundle["horizons"]]:
        raise EFSError("CONTRACT_INVALID", f"{field} horizon mismatch")


def _validate_feature_contracts(bundle: dict[str, Any]) -> None:
    contracts = _require_mapping(bundle.get("feature_contracts"), "bundle.feature_contracts")
    if not contracts:
        raise EFSError("CONTRACT_INVALID", "feature contracts must not be empty")
    limit = _require_int(bundle["runtime_limits"].get("max_features"), "bundle.runtime_limits.max_features", minimum=1, maximum=DEFAULT_LIMITS["max_features"])
    if len(contracts) > limit:
        raise EFSError("RESOURCE_LIMIT", "feature contract count exceeds limit")
    for raw_name, raw_contract in contracts.items():
        name = _require_machine_id(raw_name, "bundle.feature_contracts key")
        contract = _require_mapping(raw_contract, f"bundle.feature_contracts.{name}")
        _require_machine_id(contract.get("unit"), f"feature contract {name}.unit")
        _require_machine_id(contract.get("transform_id"), f"feature contract {name}.transform_id")
        _require_sha256(contract.get("transform_sha256"), f"feature contract {name}.transform_sha256")
        minimum = decimal_from(contract.get("min_value"), f"feature contract {name}.min_value")
        maximum = decimal_from(contract.get("max_value"), f"feature contract {name}.max_value")
        model_minimum = decimal_from(contract.get("model_min_value"), f"feature contract {name}.model_min_value")
        model_maximum = decimal_from(contract.get("model_max_value"), f"feature contract {name}.model_max_value")
        if minimum > maximum or model_minimum > model_maximum:
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} range is inverted")
        if model_minimum < minimum or model_maximum > maximum:
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} model range must be inside its hard range")
        if contract.get("null_policy") != "REJECT":
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} must use fail-closed null policy")
        semantics = [
            _require_machine_id(item, f"feature contract {name}.allowed_temporal_semantics[]")
            for item in _require_list(
                contract.get("allowed_temporal_semantics"),
                f"feature contract {name}.allowed_temporal_semantics",
            )
        ]
        if not semantics or any(item not in TEMPORAL_SEMANTICS for item in semantics):
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} has invalid temporal semantics")
        if len(set(semantics)) != len(semantics):
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} repeats temporal semantics")
        freshness_clock = _require_machine_id(contract.get("freshness_clock"), f"feature contract {name}.freshness_clock")
        if freshness_clock not in FRESHNESS_CLOCKS:
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} has an invalid freshness clock")
        datasets = [_require_machine_id(item, f"feature contract {name}.allowed_source_dataset_ids[]") for item in _require_list(contract.get("allowed_source_dataset_ids"), f"feature contract {name}.allowed_source_dataset_ids")]
        licenses = [_require_machine_id(item, f"feature contract {name}.allowed_license_ids[]") for item in _require_list(contract.get("allowed_license_ids"), f"feature contract {name}.allowed_license_ids")]
        if not datasets or len(set(datasets)) != len(datasets):
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} has an invalid source dataset allowlist")
        if not licenses or len(set(licenses)) != len(licenses):
            raise EFSError("CONTRACT_INVALID", f"feature contract {name} has an invalid license allowlist")
        _require_machine_id(contract.get("source_policy"), f"feature contract {name}.source_policy")
        _validate_embedded_hash(contract, f"feature contract {name}")


def _validate_promotion_evidence(bundle: dict[str, Any]) -> None:
    evidence = _require_mapping(bundle.get("promotion_evidence"), "bundle.promotion_evidence")
    if evidence.get("schema") != PROMOTION_SCHEMA:
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "unsupported promotion evidence schema")
    _require_machine_id(evidence.get("receipt_id"), "bundle.promotion_evidence.receipt_id")
    subject = _require_sha256(evidence.get("subject_model_set_sha256"), "promotion subject_model_set_sha256")
    actual_subject = sha256_hex(_model_payload(bundle))
    if subject != actual_subject:
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "promotion evidence subject mismatch")
    _require_sha256(evidence.get("evidence_set_sha256"), "promotion evidence_set_sha256")
    _require_sha256(evidence.get("trial_ledger_sha256"), "promotion trial_ledger_sha256")
    heads = _require_mapping(evidence.get("heads"), "promotion heads")
    if set(heads) != set(HEAD_STATUS_MAP):
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "promotion evidence head set mismatch")
    for logical_name, bundle_key in HEAD_STATUS_MAP.items():
        head = _require_mapping(heads[logical_name], f"promotion heads.{logical_name}")
        status = _require_machine_id(head.get("status"), f"promotion heads.{logical_name}.status")
        if status != bundle[bundle_key]["status"]:
            raise EFSError("PROMOTION_EVIDENCE_INVALID", f"promotion status mismatch for {logical_name}")
        sample_size = _require_int(head.get("effective_sample_size"), f"promotion heads.{logical_name}.effective_sample_size", minimum=0, maximum=100_000_000)
        if _status_at_least(status, "OOS_VALIDATED"):
            oos_digest = head.get("oos_predictions_sha256")
            if not isinstance(oos_digest, str) or not SHA256_PATTERN.fullmatch(oos_digest):
                raise EFSError("PROMOTION_EVIDENCE_INVALID", f"calibrated head {logical_name} lacks OOS prediction hash")
            if sample_size < 30:
                raise EFSError("PROMOTION_EVIDENCE_INVALID", f"calibrated head {logical_name} lacks sample support")
            _parse_time(head.get("evaluation_start"), f"promotion heads.{logical_name}.evaluation_start")
            _parse_time(head.get("evaluation_end"), f"promotion heads.{logical_name}.evaluation_end")
        if _status_at_least(status, "OUTCOME_PROVEN"):
            holdout_digest = head.get("untouched_holdout_sha256")
            if not isinstance(holdout_digest, str) or not SHA256_PATTERN.fullmatch(holdout_digest):
                raise EFSError("PROMOTION_EVIDENCE_INVALID", f"outcome-proven head {logical_name} lacks untouched holdout hash")
            if head.get("cost_stress_2x_pass") is not True:
                raise EFSError("PROMOTION_EVIDENCE_INVALID", f"outcome-proven head {logical_name} lacks 2x cost pass")
    _validate_embedded_hash(evidence, "promotion evidence", hash_key="receipt_sha256")


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    bundle = _require_mapping(bundle, "bundle")
    _reject_unknown_keys(bundle, BUNDLE_KEYS, "bundle")
    if bundle.get("schema") != BUNDLE_SCHEMA:
        raise EFSError("CONTRACT_INVALID", "unsupported bundle schema")
    if bundle.get("stable_id") != STABLE_ID:
        raise EFSError("CONTRACT_INVALID", "stable_id mismatch")
    if bundle.get("runtime_version") != RUNTIME_VERSION:
        raise EFSError("CONTRACT_INVALID", "runtime version mismatch")
    _require_machine_id(bundle.get("bundle_id"), "bundle.bundle_id")
    created_at = _parse_time(bundle.get("created_at"), "bundle.created_at")
    expires_at = _parse_time(bundle.get("expires_at"), "bundle.expires_at")
    if expires_at <= created_at:
        raise EFSError("CONTRACT_INVALID", "bundle expires_at must be after created_at")
    limits = _require_mapping(bundle.get("runtime_limits"), "bundle.runtime_limits")
    _require_int(limits.get("max_features"), "runtime max_features", minimum=1, maximum=DEFAULT_LIMITS["max_features"])
    _require_int(limits.get("max_experts"), "runtime max_experts", minimum=1, maximum=DEFAULT_LIMITS["max_experts"])
    _require_int(limits.get("max_buckets"), "runtime max_buckets", minimum=1, maximum=DEFAULT_LIMITS["max_buckets"])
    _require_int(limits.get("max_batch"), "runtime max_batch", minimum=1, maximum=DEFAULT_LIMITS["max_batch"])
    _validate_scope(_require_mapping(bundle.get("scope"), "bundle.scope"))
    horizons = _require_list(bundle.get("horizons"), "bundle.horizons")
    if not horizons:
        raise EFSError("CONTRACT_INVALID", "bundle.horizons must not be empty")
    parsed_horizons = [_require_int(item, "bundle.horizons[]", minimum=1, maximum=2520) for item in horizons]
    if len(set(parsed_horizons)) != len(parsed_horizons):
        raise EFSError("CONTRACT_INVALID", "bundle.horizons must be unique")
    if len(parsed_horizons) != 1:
        raise EFSError("CONTRACT_INVALID", "v0 bundles are single-horizon; use one immutable bundle per horizon")
    _require_machine_id(bundle.get("calendar_id"), "bundle.calendar_id")
    label = _require_mapping(bundle.get("label_contract"), "bundle.label_contract")
    _require_machine_id(label.get("id"), "bundle.label_contract.id")
    _require_machine_id(label.get("signal_price"), "bundle.label_contract.signal_price")
    _require_machine_id(label.get("entry_price"), "bundle.label_contract.entry_price")
    _require_machine_id(label.get("exit_price"), "bundle.label_contract.exit_price")
    if label.get("entry_price") == label.get("signal_price"):
        raise EFSError("CONTRACT_INVALID", "same-bar execution is forbidden")
    decimal_from(label.get("hurdle"), "bundle.label_contract.hurdle")
    cost = _require_mapping(bundle.get("cost_contract"), "bundle.cost_contract")
    _require_machine_id(cost.get("id"), "bundle.cost_contract.id")
    _validate_embedded_hash(cost, "cost contract", hash_key="sha256")
    for key in ("commission_bps", "spread_slippage_bps", "borrow_bps", "tax_bps"):
        if decimal_from(cost.get(key), f"bundle.cost_contract.{key}") < 0:
            raise EFSError("CONTRACT_INVALID", "cost components must be non-negative")
    _validate_feature_contracts(bundle)

    experts = _require_mapping(bundle.get("experts"), "bundle.experts")
    max_experts = _require_int(limits.get("max_experts"), "bundle.runtime_limits.max_experts", minimum=1, maximum=DEFAULT_LIMITS["max_experts"])
    if not experts or len(experts) > max_experts:
        raise EFSError("RESOURCE_LIMIT", "invalid bundle expert count")
    for raw_name, raw_expert in experts.items():
        name = _require_machine_id(raw_name, "bundle.experts key")
        expert = _require_mapping(raw_expert, f"bundle.experts.{name}")
        model_type = _require_machine_id(expert.get("model_type"), f"expert {name}.model_type")
        if model_type not in ALLOWED_MODEL_TYPES:
            raise EFSError("CONTRACT_INVALID", "unsupported or unsafe model type")
        required = [_require_machine_id(item, f"expert {name}.required_features[]") for item in _require_list(expert.get("required_features"), f"expert {name}.required_features")]
        if not required or len(set(required)) != len(required):
            raise EFSError("CONTRACT_INVALID", f"expert {name} has invalid required features")
        if any(item not in bundle["feature_contracts"] for item in required):
            raise EFSError("CONTRACT_INVALID", f"expert {name} references undefined feature contract")
        weights = _require_mapping(expert.get("weights"), f"expert {name}.weights")
        if set(required) != set(weights):
            raise EFSError("CONTRACT_INVALID", "expert required_features must equal weight keys")
        _weighted_sum(weights, {item: Decimal(0) for item in required}, expert.get("intercept"), f"expert.{name}")
        grade = _require_machine_id(expert.get("minimum_evidence_grade"), f"expert {name}.minimum_evidence_grade")
        if grade not in GRADE_ORDER:
            raise EFSError("CONTRACT_INVALID", "unknown evidence grade")
        _require_int(expert.get("max_age_seconds"), f"expert {name}.max_age_seconds", minimum=0, maximum=31_536_000)
        expert_status = _require_machine_id(expert.get("status"), f"expert {name}.status")
        if expert_status not in MATURITY_ORDER:
            raise EFSError("CONTRACT_INVALID", "unknown expert status")
        _validate_method(expert, f"expert {name}", "fit_method")
        _validate_embedded_hash(expert, f"expert {name}")

    sets = _require_list(bundle.get("admissible_expert_sets"), "bundle.admissible_expert_sets")
    if not sets:
        raise EFSError("CONTRACT_INVALID", "at least one admissible expert set is required")
    seen_sets: set[tuple[str, ...]] = set()
    seen_set_ids: set[str] = set()
    for item in sets:
        set_map = _require_mapping(item, "bundle.admissible_expert_sets[]")
        set_id = _require_machine_id(set_map.get("set_id"), "expert set set_id")
        if set_id in seen_set_ids:
            raise EFSError("CONTRACT_INVALID", "duplicate expert set id")
        seen_set_ids.add(set_id)
        members = tuple(sorted(_require_machine_id(name, "expert set member") for name in _require_list(set_map.get("experts"), "expert set experts")))
        if not members or any(name not in experts for name in members):
            raise EFSError("CONTRACT_INVALID", "expert set references unknown expert")
        if members in seen_sets:
            raise EFSError("CONTRACT_INVALID", "duplicate admissible expert set")
        seen_sets.add(members)
        aggregator = _require_mapping(set_map.get("aggregator"), "expert set aggregator")
        weights = _require_mapping(aggregator.get("weights"), "expert set aggregator weights")
        if set(weights) != set(members):
            raise EFSError("CONTRACT_INVALID", "aggregator weights must exactly match expert set")
        _weighted_sum(weights, {name: Decimal(0) for name in members}, aggregator.get("intercept"), "aggregator")
        set_status = _require_machine_id(set_map.get("status"), f"expert set {set_id}.status")
        if set_status not in MATURITY_ORDER:
            raise EFSError("CONTRACT_INVALID", "unknown aggregator status")
        _validate_method(set_map, f"expert set {set_map['set_id']}", "fit_method")
        _validate_embedded_hash(set_map, f"expert set {set_map['set_id']}")

    baseline = _require_mapping(bundle.get("baseline"), "bundle.baseline")
    _validate_binding(baseline, "baseline", bundle)
    baseline_prob = decimal_from(baseline.get("prob_up"), "bundle.baseline.prob_up")
    if baseline_prob <= 0 or baseline_prob >= 1:
        raise EFSError("CONTRACT_INVALID", "baseline probability must be between 0 and 1")
    baseline_status = _require_machine_id(baseline.get("status"), "bundle.baseline.status")
    if baseline_status not in MATURITY_ORDER:
        raise EFSError("CONTRACT_INVALID", "unknown baseline status")
    _validate_method(baseline, "baseline", "estimation_method")
    _validate_embedded_hash(baseline, "baseline")

    calibration = _require_mapping(bundle.get("calibration"), "bundle.calibration")
    _validate_binding(calibration, "calibration", bundle)
    if calibration.get("type") != "platt_v1":
        raise EFSError("CONTRACT_INVALID", "unsupported calibration type")
    decimal_from(calibration.get("a"), "bundle.calibration.a")
    decimal_from(calibration.get("b"), "bundle.calibration.b")
    _parse_time(calibration.get("expires_at"), "bundle.calibration.expires_at")
    calibration_status = _require_machine_id(calibration.get("status"), "bundle.calibration.status")
    if calibration_status not in MATURITY_ORDER:
        raise EFSError("CONTRACT_INVALID", "unknown calibration status")
    _validate_method(calibration, "calibration", "fit_method")
    _validate_embedded_hash(calibration, "calibration")

    magnitude = _require_mapping(bundle.get("magnitude_head"), "bundle.magnitude_head")
    _validate_binding(magnitude, "magnitude head", bundle)
    base_quantiles = _require_mapping(magnitude.get("base_quantiles"), "bundle.magnitude_head.base_quantiles")
    q10 = decimal_from(base_quantiles.get("p10"), "magnitude p10")
    q50 = decimal_from(base_quantiles.get("p50"), "magnitude p50")
    q90 = decimal_from(base_quantiles.get("p90"), "magnitude p90")
    if not q10 <= q50 <= q90:
        raise EFSError("CONTRACT_INVALID", "magnitude quantiles cross")
    decimal_from(magnitude.get("aggregate_slope"), "magnitude aggregate_slope")
    magnitude_status = _require_machine_id(magnitude.get("status"), "bundle.magnitude_head.status")
    if magnitude_status not in MATURITY_ORDER:
        raise EFSError("CONTRACT_INVALID", "unknown magnitude status")
    _validate_method(magnitude, "magnitude head", "fit_method")
    _validate_embedded_hash(magnitude, "magnitude head")

    timing = _require_mapping(bundle.get("timing_head"), "bundle.timing_head")
    _validate_binding(timing, "timing head", bundle)
    up_hurdle = decimal_from(timing.get("up_hurdle"), "timing up_hurdle")
    down_hurdle = decimal_from(timing.get("down_hurdle"), "timing down_hurdle")
    if up_hurdle <= 0 or down_hurdle >= 0:
        raise EFSError("CONTRACT_INVALID", "timing barriers must straddle zero")
    buckets = _require_list(timing.get("buckets"), "bundle.timing_head.buckets")
    max_buckets = _require_int(limits.get("max_buckets"), "bundle.runtime_limits.max_buckets", minimum=1, maximum=DEFAULT_LIMITS["max_buckets"])
    if not buckets or len(buckets) > max_buckets:
        raise EFSError("RESOURCE_LIMIT", "invalid timing bucket count")
    previous_end = 0
    for bucket in buckets:
        bucket_map = _require_mapping(bucket, "timing bucket")
        start = _require_int(bucket_map.get("start_day"), "timing start_day", minimum=1)
        end = _require_int(bucket_map.get("end_day"), "timing end_day", minimum=start)
        if start != previous_end + 1:
            raise EFSError("CONTRACT_INVALID", "timing buckets must be contiguous and non-overlapping")
        previous_end = end
        for cause in ("up_logit", "down_logit"):
            decimal_from(bucket_map.get(cause), f"timing bucket {cause}")
        if "timeout_logit" in bucket_map:
            raise EFSError("CONTRACT_INVALID", "timeout is a single horizon-level event, not a per-bucket event")
    if previous_end not in parsed_horizons:
        raise EFSError("CONTRACT_INVALID", "timing buckets must end at a supported horizon")
    decimal_from(timing.get("aggregate_sensitivity"), "timing aggregate_sensitivity")
    decimal_from(timing.get("timeout_logit"), "timing timeout_logit")
    timing_status = _require_machine_id(timing.get("status"), "bundle.timing_head.status")
    if timing_status not in MATURITY_ORDER:
        raise EFSError("CONTRACT_INVALID", "unknown timing status")
    _validate_method(timing, "timing head", "fit_method")
    _validate_embedded_hash(timing, "timing head")

    economic = _require_mapping(bundle.get("economic_edge_head"), "bundle.economic_edge_head")
    _validate_binding(economic, "economic edge head", bundle)
    if economic.get("type") != "linear_expected_net_return_v1":
        raise EFSError("CONTRACT_INVALID", "unsupported economic edge head")
    decimal_from(economic.get("base_mean_net_return"), "economic edge base mean")
    decimal_from(economic.get("aggregate_slope"), "economic edge aggregate slope")
    economic_status = _require_machine_id(economic.get("status"), "bundle.economic_edge_head.status")
    if economic_status not in MATURITY_ORDER:
        raise EFSError("CONTRACT_INVALID", "unknown economic edge status")
    _validate_method(economic, "economic edge head", "fit_method")
    _validate_embedded_hash(economic, "economic edge head")

    reliability = _require_mapping(bundle.get("reliability_head"), "bundle.reliability_head")
    _validate_binding(reliability, "reliability head", bundle)
    if reliability.get("type") != "deterministic_penalty_v1":
        raise EFSError("CONTRACT_INVALID", "unsupported reliability head")
    base = decimal_from(reliability.get("base_score"), "reliability base_score")
    missing_penalty = decimal_from(reliability.get("missing_expert_penalty"), "reliability missing_expert_penalty")
    disagreement_penalty = decimal_from(reliability.get("disagreement_penalty"), "reliability disagreement_penalty")
    if not 0 <= base <= 100 or missing_penalty < 0 or disagreement_penalty < 0:
        raise EFSError("CONTRACT_INVALID", "invalid reliability parameters")
    reliability_status = _require_machine_id(reliability.get("status"), "bundle.reliability_head.status")
    if reliability_status not in MATURITY_ORDER:
        raise EFSError("CONTRACT_INVALID", "unknown reliability status")
    _validate_method(reliability, "reliability head", "fit_method")
    _validate_embedded_hash(reliability, "reliability head")

    usage = _require_mapping(bundle.get("usage_policy"), "bundle.usage_policy")
    if set(usage) != USAGE_MODES:
        raise EFSError("CONTRACT_INVALID", "usage policy modes mismatch")
    for mode, policy in usage.items():
        policy_map = _require_mapping(policy, f"usage policy {mode}")
        status = _require_machine_id(policy_map.get("minimum_head_status"), f"usage policy {mode}.minimum_head_status")
        assurance = _require_machine_id(policy_map.get("minimum_trust_assurance"), f"usage policy {mode}.minimum_trust_assurance")
        if status not in MATURITY_ORDER or assurance not in ASSURANCE_ORDER:
            raise EFSError("CONTRACT_INVALID", "usage policy has invalid threshold")

    model_hash = _require_sha256(bundle.get("model_set_sha256"), "bundle.model_set_sha256")
    if model_hash != sha256_hex(_model_payload(bundle)):
        raise EFSError("BUNDLE_INTEGRITY_FAILED", "model set SHA-256 mismatch")
    _validate_promotion_evidence(bundle)
    bundle_hash = _validate_bundle_hash(bundle)
    return {"valid": True, "bundle_sha256": bundle_hash, "model_set_sha256": model_hash}


def _validate_trust_context(
    trust_context: dict[str, Any] | str | bytes | None,
    bundle: dict[str, Any],
    mode: str,
    as_of: datetime,
) -> dict[str, Any]:
    required_assurance = bundle["usage_policy"][mode]["minimum_trust_assurance"]
    if required_assurance == "NONE":
        return {
            "assurance_level": "NONE",
            "authority_id": None,
            "policy_id": None,
            "verification_method": None,
            "verification_receipt_sha256": None,
        }

    if trust_context is None:
        raise EFSError("TRUST_CONTEXT_REQUIRED", f"{mode} requires host trust context")

    context = _normalize_json_mapping(trust_context, "trust_context", DEFAULT_LIMITS["trust_bytes"])
    if context.get("schema") != TRUST_SCHEMA:
        raise EFSError("TRUST_CONTEXT_INVALID", "unsupported trust context schema")
    if context.get("source") != "HOST_INJECTED_OUT_OF_BAND":
        raise EFSError("TRUST_CONTEXT_INVALID", "trust context must come from host boundary")
    _require_machine_id(context.get("policy_id"), "trust_context.policy_id")
    _require_machine_id(context.get("authority_id"), "trust_context.authority_id")
    assurance = _require_machine_id(context.get("assurance_level"), "trust_context.assurance_level")
    if assurance not in ASSURANCE_ORDER:
        raise EFSError("TRUST_CONTEXT_INVALID", "unknown trust assurance")
    if assurance == "CRYPTOGRAPHICALLY_VERIFIED":
        raise EFSError("TRUST_CONTEXT_INVALID", "cryptographic assurance must be produced by the Ed25519 verifier adapter")
    if not _assurance_at_least(assurance, required_assurance):
        raise EFSError("TRUST_ASSURANCE_INSUFFICIENT", f"{mode} requires {required_assurance}")
    modes = {_require_machine_id(item, "trust_context.allowed_usage_modes[]") for item in _require_list(context.get("allowed_usage_modes"), "trust_context.allowed_usage_modes")}
    if mode not in modes:
        raise EFSError("TRUST_CONTEXT_INVALID", "usage mode is not approved by host")
    if context.get("approved_bundle_sha256") != bundle["payload_sha256"]:
        raise EFSError("BUNDLE_NOT_APPROVED", "host did not approve this bundle hash")
    if context.get("approved_promotion_receipt_sha256") != bundle["promotion_evidence"]["receipt_sha256"]:
        raise EFSError("BUNDLE_NOT_APPROVED", "host did not approve this promotion receipt")
    valid_from = _parse_time(context.get("valid_from"), "trust_context.valid_from")
    valid_until = _parse_time(context.get("valid_until"), "trust_context.valid_until")
    if not valid_from <= as_of <= valid_until:
        raise EFSError("TRUST_CONTEXT_EXPIRED", "host trust context is not valid at as_of")
    _validate_embedded_hash(context, "trust context", hash_key="policy_sha256")
    return {
        "assurance_level": assurance,
        "authority_id": context["authority_id"],
        "policy_id": context["policy_id"],
        "verification_method": "host_boundary_assertion_v1",
        "verification_receipt_sha256": context["policy_sha256"],
    }


def _match_scope(scope: dict[str, Any], request: dict[str, Any]) -> None:
    instrument = _require_machine_id(request.get("instrument_id"), "request.instrument_id")
    if scope["type"] == "single_instrument_v1":
        if instrument != scope["instrument_id"]:
            raise EFSError("UNIVERSE_MISMATCH", "instrument is outside the model scope")
        return
    if instrument not in scope["members"]:
        raise EFSError("UNIVERSE_MISMATCH", "instrument is not a member of the frozen universe snapshot")
    if request.get("universe_snapshot_sha256") != scope["snapshot_sha256"]:
        raise EFSError("UNIVERSE_MISMATCH", "request universe snapshot hash mismatch")


def _parse_features(request: dict[str, Any], bundle: dict[str, Any], as_of: datetime) -> tuple[dict[str, Decimal], dict[str, dict[str, Any]]]:
    features = _require_list(request.get("features"), "request.features")
    max_features = _require_int(bundle["runtime_limits"].get("max_features"), "bundle.runtime_limits.max_features", minimum=1, maximum=DEFAULT_LIMITS["max_features"])
    if len(features) > max_features:
        raise EFSError("RESOURCE_LIMIT", "feature count exceeds limit")
    values: dict[str, Decimal] = {}
    metadata: dict[str, dict[str, Any]] = {}
    contracts = bundle["feature_contracts"]
    for feature in features:
        feature_map = _require_mapping(feature, "request.features[]")
        _reject_unknown_keys(feature_map, FEATURE_KEYS, "request.features[]")
        name = _require_machine_id(feature_map.get("name"), "feature.name")
        if name in values:
            raise EFSError("CONTRACT_INVALID", f"duplicate feature: {name}")
        if name not in contracts:
            raise EFSError("FEATURE_CONTRACT_MISMATCH", f"feature {name} has no frozen contract")
        contract = contracts[name]
        value = decimal_from(feature_map.get("value"), f"feature.{name}.value")
        minimum = decimal_from(contract["min_value"], f"feature contract {name}.min_value")
        maximum = decimal_from(contract["max_value"], f"feature contract {name}.max_value")
        if not minimum <= value <= maximum:
            raise EFSError("FEATURE_CONTRACT_MISMATCH", f"feature {name} is outside the hard data range")
        model_minimum = decimal_from(contract["model_min_value"], f"feature contract {name}.model_min_value")
        model_maximum = decimal_from(contract["model_max_value"], f"feature contract {name}.model_max_value")
        if not model_minimum <= value <= model_maximum:
            raise EFSError("OUT_OF_DISTRIBUTION", f"feature {name} is outside the frozen model support")
        for field in ("unit", "transform_id", "transform_sha256"):
            if feature_map.get(field) != contract[field]:
                raise EFSError("FEATURE_CONTRACT_MISMATCH", f"feature {name} {field} mismatch")
        effective_at = _parse_time(feature_map.get("effective_at"), f"feature.{name}.effective_at")
        published_at = _parse_time(feature_map.get("published_at"), f"feature.{name}.published_at")
        available_at = _parse_time(feature_map.get("available_at"), f"feature.{name}.available_at")
        if published_at > as_of or available_at > as_of:
            raise EFSError("TEMPORAL_LEAKAGE", f"feature {name} was not available at as_of")
        if available_at < published_at:
            raise EFSError("CONTRACT_INVALID", f"feature {name} available_at precedes published_at")
        temporal = _require_machine_id(feature_map.get("temporal_semantics"), f"feature.{name}.temporal_semantics")
        if temporal not in TEMPORAL_SEMANTICS or temporal not in contract["allowed_temporal_semantics"]:
            raise EFSError("FEATURE_CONTRACT_MISMATCH", f"feature {name} temporal semantics mismatch")
        if temporal in {"OBSERVED_FACT", "REVISED_SERIES", "MARKET_QUOTE"} and effective_at > as_of:
            raise EFSError("TEMPORAL_LEAKAGE", f"feature {name} contains a future observed fact")
        if temporal == "SCHEDULED_FUTURE" and effective_at <= as_of:
            raise EFSError("CONTRACT_INVALID", f"scheduled future feature {name} must have a future effective_at")
        revision_id = _require_machine_id(feature_map.get("revision_id"), f"feature.{name}.revision_id")
        if temporal == "REVISED_SERIES" and not revision_id:
            raise EFSError("CONTRACT_INVALID", f"revised feature {name} requires revision_id")
        grade = _require_machine_id(feature_map.get("evidence_grade"), f"feature.{name}.evidence_grade")
        if grade not in GRADE_ORDER:
            raise EFSError("CONTRACT_INVALID", f"feature {name} has unknown evidence grade")
        source = _require_machine_id(feature_map.get("source"), f"feature.{name}.source")
        source_dataset_id = _require_machine_id(feature_map.get("source_dataset_id"), f"feature.{name}.source_dataset_id")
        license_id = _require_machine_id(feature_map.get("license_id"), f"feature.{name}.license_id")
        if source_dataset_id not in contract["allowed_source_dataset_ids"]:
            raise EFSError("FEATURE_CONTRACT_MISMATCH", f"feature {name} source dataset is not approved")
        if license_id not in contract["allowed_license_ids"]:
            raise EFSError("FEATURE_CONTRACT_MISMATCH", f"feature {name} license is not approved")
        source_record_sha256 = _require_sha256(feature_map.get("source_record_sha256"), f"feature.{name}.source_record_sha256")
        feature_payload_sha256 = _require_sha256(feature_map.get("feature_payload_sha256"), f"feature.{name}.feature_payload_sha256")
        payload = copy.deepcopy(feature_map)
        payload.pop("feature_payload_sha256", None)
        if feature_payload_sha256 != sha256_hex(payload):
            raise EFSError("FEATURE_INTEGRITY_FAILED", f"feature {name} payload SHA-256 mismatch")
        if feature_map.get("conflict") is True:
            raise EFSError("DATA_CONFLICT", f"feature {name} has an unresolved source conflict")
        values[name] = value
        metadata[name] = {
            "effective_at": effective_at,
            "published_at": published_at,
            "available_at": available_at,
            "revision_id": revision_id,
            "source": source,
            "source_dataset_id": source_dataset_id,
            "source_record_sha256": source_record_sha256,
            "license_id": license_id,
            "feature_payload_sha256": feature_payload_sha256,
            "freshness_clock": contract["freshness_clock"],
            "evidence_grade": grade,
            "temporal_semantics": temporal,
        }
    return values, metadata


def _select_experts(bundle: dict[str, Any], values: dict[str, Decimal], metadata: dict[str, dict[str, Any]], as_of: datetime) -> tuple[dict[str, Decimal], list[str], list[str]]:
    expert_scores: dict[str, Decimal] = {}
    suspended: list[str] = []
    unavailable: list[str] = []
    for name, expert in bundle["experts"].items():
        if expert["status"] == "SUSPENDED":
            suspended.append(name)
            continue
        required = expert["required_features"]
        if any(feature not in values for feature in required):
            unavailable.append(name)
            continue
        minimum_grade = expert["minimum_evidence_grade"]
        max_age_seconds = _require_int(expert["max_age_seconds"], f"expert {name} max_age_seconds")
        invalid = False
        for feature in required:
            item = metadata[feature]
            if GRADE_ORDER[item["evidence_grade"]] < GRADE_ORDER[minimum_grade]:
                invalid = True
                break
            clock_field = {
                "EFFECTIVE_AT": "effective_at",
                "PUBLISHED_AT": "published_at",
                "AVAILABLE_AT": "available_at",
            }[item["freshness_clock"]]
            age = (as_of - item[clock_field]).total_seconds()
            if age < 0 or age > max_age_seconds:
                invalid = True
                break
        if invalid:
            unavailable.append(name)
            continue
        expert_scores[name] = _weighted_sum(expert["weights"], values, expert["intercept"], f"expert.{name}")
    return expert_scores, suspended, unavailable


def _choose_aggregator(bundle: dict[str, Any], expert_scores: dict[str, Decimal]) -> tuple[str, Decimal]:
    active = tuple(sorted(expert_scores))
    for item in bundle["admissible_expert_sets"]:
        members = tuple(sorted(item["experts"]))
        if members == active:
            aggregate = _weighted_sum(item["aggregator"]["weights"], expert_scores, item["aggregator"]["intercept"], "aggregator")
            return _require_machine_id(item.get("set_id"), "expert set set_id"), aggregate
    raise EFSError("EXPERT_SET_UNVALIDATED", "active expert combination has no frozen aggregator")


def _magnitude(bundle: dict[str, Any], aggregate: Decimal) -> dict[str, str]:
    head = bundle["magnitude_head"]
    slope = decimal_from(head["aggregate_slope"], "magnitude slope")
    base = head["base_quantiles"]
    q10 = decimal_from(base["p10"], "magnitude p10") + slope * aggregate
    q50 = decimal_from(base["p50"], "magnitude p50") + slope * aggregate
    q90 = decimal_from(base["p90"], "magnitude p90") + slope * aggregate
    if not q10 <= q50 <= q90:
        raise EFSError("CONTRACT_INVALID", "magnitude quantile crossing after inference")
    return {"p10": canonical_decimal(q10), "p50": canonical_decimal(q50), "p90": canonical_decimal(q90)}


def _timing(bundle: dict[str, Any], aggregate: Decimal) -> dict[str, Any]:
    cells: list[tuple[int, int, str, Decimal]] = []
    head = bundle["timing_head"]
    sensitivity = decimal_from(head.get("aggregate_sensitivity", "0"), "timing aggregate_sensitivity")
    for bucket in head["buckets"]:
        start = _require_int(bucket["start_day"], "timing start")
        end = _require_int(bucket["end_day"], "timing end")
        cells.append((start, end, "up", decimal_from(bucket["up_logit"], "up_logit") + sensitivity * aggregate))
        cells.append((start, end, "down", decimal_from(bucket["down_logit"], "down_logit") - sensitivity * aggregate))
    timeout_logit = decimal_from(head["timeout_logit"], "timing timeout_logit")
    all_logits = [item[3] for item in cells] + [timeout_logit]
    probabilities = _softmax(all_logits)
    event_probabilities = probabilities[:-1]
    timeout_probability = probabilities[-1]
    buckets: dict[tuple[int, int], dict[str, Decimal]] = {}
    totals = {"up": Decimal(0), "down": Decimal(0)}
    for (start, end, cause, _), probability in zip(cells, event_probabilities):
        row = buckets.setdefault((start, end), {"up": Decimal(0), "down": Decimal(0)})
        row[cause] = probability
        totals[cause] += probability
    summed = totals["up"] + totals["down"] + timeout_probability
    if abs(summed - Decimal(1)) > Decimal("0.0000000001"):
        raise EFSError("INTERNAL_ERROR", "competing-risk probabilities do not sum to one")
    if event_probabilities and max(event_probabilities) > timeout_probability:
        best_index = max(range(len(cells)), key=lambda index: event_probabilities[index])
        best = cells[best_index]
        most_likely: dict[str, Any] = {"start_day": best[0], "end_day": best[1], "cause": best[2]}
    else:
        most_likely = {"start_day": None, "end_day": None, "cause": "timeout"}
    return {
        "up_hurdle": canonical_decimal(decimal_from(head["up_hurdle"], "timing up_hurdle")),
        "down_hurdle": canonical_decimal(decimal_from(head["down_hurdle"], "timing down_hurdle")),
        "barrier_up": canonical_decimal(totals["up"]),
        "barrier_down": canonical_decimal(totals["down"]),
        "timeout": canonical_decimal(timeout_probability),
        "timeout_semantics": "NO_UP_OR_DOWN_BARRIER_TOUCH_BY_HORIZON",
        "most_likely_window": most_likely,
        "buckets": [
            {
                "start_day": start,
                "end_day": end,
                "up": canonical_decimal(values["up"]),
                "down": canonical_decimal(values["down"]),
                "event_mass": canonical_decimal(values["up"] + values["down"]),
            }
            for (start, end), values in sorted(buckets.items())
        ],
    }


def _economic_edge(bundle: dict[str, Any], aggregate: Decimal) -> Decimal:
    head = bundle["economic_edge_head"]
    return (
        decimal_from(head["base_mean_net_return"], "economic edge base mean")
        + decimal_from(head["aggregate_slope"], "economic edge aggregate slope") * aggregate
    )

def _reliability(bundle: dict[str, Any], expert_scores: dict[str, Decimal]) -> Decimal:
    head = bundle["reliability_head"]
    score = decimal_from(head["base_score"], "reliability base score")
    missing = len(bundle["experts"]) - len(expert_scores)
    score -= decimal_from(head["missing_expert_penalty"], "reliability missing penalty") * Decimal(missing)
    if len(expert_scores) > 1:
        spread = max(expert_scores.values()) - min(expert_scores.values())
        score -= decimal_from(head["disagreement_penalty"], "reliability disagreement penalty") * abs(spread)
    return min(Decimal(100), max(Decimal(0), score))


def _usage_gate(bundle: dict[str, Any], mode: str) -> None:
    if mode not in USAGE_MODES:
        raise EFSError("CONTRACT_INVALID", "unsupported usage mode")
    if mode not in RELEASE_AUTHORIZED_MODES:
        raise EFSError(
            "CAPABILITY_NOT_RELEASED",
            f"{mode} is not authorized in runtime {RUNTIME_VERSION}; release ceiling is {RELEASE_CAPABILITY_CEILING}",
        )
    required = bundle["usage_policy"][mode]["minimum_head_status"]
    for logical_name, bundle_key in HEAD_STATUS_MAP.items():
        status = bundle[bundle_key]["status"]
        if not _status_at_least(status, required):
            code = "OUTCOME_NOT_PROVEN" if required == "OUTCOME_PROVEN" else "OOS_VALIDATION_NOT_PROVEN"
            raise EFSError(code, f"{mode} requires {logical_name} maturity {required}")


def _component_usage_gate(bundle: dict[str, Any], active_experts: Iterable[str], set_id: str, mode: str) -> None:
    required = bundle["usage_policy"][mode]["minimum_head_status"]
    code = "OUTCOME_NOT_PROVEN" if required == "OUTCOME_PROVEN" else "OOS_VALIDATION_NOT_PROVEN"
    for name in active_experts:
        status = bundle["experts"][name]["status"]
        if not _status_at_least(status, required):
            raise EFSError(code, f"{mode} requires active expert {name} maturity {required}")
    selected = next((item for item in bundle["admissible_expert_sets"] if item["set_id"] == set_id), None)
    if selected is None:
        raise EFSError("INTERNAL_ERROR", "selected expert set disappeared")
    if not _status_at_least(selected["status"], required):
        raise EFSError(code, f"{mode} requires aggregator {set_id} maturity {required}")


def _safe_echo(value: Any) -> Any | None:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int) and abs(value) <= 10**18:
        return value
    if isinstance(value, str) and len(value.encode("utf-8")) <= 512:
        return unicodedata.normalize("NFC", value)
    return None


def _empty_envelope(request: dict[str, Any] | None, bundle: dict[str, Any] | None, error: EFSError) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "status": "ABSTAIN",
        "reason_code": error.code,
        "reason_zh": error.message,
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    if isinstance(request, dict):
        for key in ("request_id", "instrument_id", "as_of", "horizon", "usage_mode"):
            if key in request:
                safe = _safe_echo(request[key])
                if safe is not None:
                    result[key] = safe
    if isinstance(bundle, dict):
        bundle_id = _safe_echo(bundle.get("bundle_id"))
        if bundle_id is not None:
            result["bundle_id"] = bundle_id
        digest = bundle.get("payload_sha256")
        if isinstance(digest, str) and SHA256_PATTERN.fullmatch(digest):
            result["bundle_sha256"] = digest
    result["result_sha256"] = sha256_hex(result)
    return result

class PreparedBundle:
    """Opaque validated bundle for repeated deterministic evaluation."""

    __slots__ = ("__bundle", "bundle_id", "bundle_sha256", "model_set_sha256")

    def __init__(self, bundle: dict[str, Any], token: object) -> None:
        if token is not _PREPARED_BUNDLE_TOKEN:
            raise TypeError("PreparedBundle instances must be created by prepare_bundle")
        self.__bundle = bundle
        self.bundle_id = bundle["bundle_id"]
        self.bundle_sha256 = bundle["payload_sha256"]
        self.model_set_sha256 = bundle["model_set_sha256"]

    def _validated_map(self, token: object) -> dict[str, Any]:
        if token is not _PREPARED_BUNDLE_TOKEN:
            raise TypeError("prepared bundle internals are private")
        return self.__bundle


_PREPARED_BUNDLE_TOKEN = object()


def prepare_bundle(bundle: dict[str, Any] | str | bytes) -> PreparedBundle:
    normalized = _normalize_json_mapping(bundle, "bundle", DEFAULT_LIMITS["bundle_bytes"])
    validate_bundle(normalized)
    return PreparedBundle(normalized, _PREPARED_BUNDLE_TOKEN)


def _evaluate_validated_maps(
    request_map: dict[str, Any],
    bundle_map: dict[str, Any],
    trust_context: dict[str, Any] | str | bytes | None,
) -> dict[str, Any]:
    try:
        _reject_unknown_keys(request_map, REQUEST_KEYS, "request")
        if request_map.get("schema") != REQUEST_SCHEMA:
            raise EFSError("CONTRACT_INVALID", "unsupported request schema")
        _require_machine_id(request_map.get("request_id"), "request.request_id")
        as_of = _parse_time(request_map.get("as_of"), "request.as_of")
        mode = _require_machine_id(request_map.get("usage_mode"), "request.usage_mode")
        _usage_gate(bundle_map, mode)
        trust_state = _validate_trust_context(trust_context, bundle_map, mode, as_of)
        _match_scope(bundle_map["scope"], request_map)
        horizon = _require_int(request_map.get("horizon"), "request.horizon", minimum=1, maximum=2520)
        if horizon not in [int(item) for item in bundle_map["horizons"]]:
            raise EFSError("HORIZON_UNSUPPORTED", "requested horizon is not supported")
        if request_map.get("calendar_id") != bundle_map["calendar_id"]:
            raise EFSError("CONTRACT_INVALID", "calendar mismatch")
        if request_map.get("label_contract_id") != bundle_map["label_contract"]["id"]:
            raise EFSError("CONTRACT_INVALID", "label contract mismatch")
        if request_map.get("cost_contract_sha256") != bundle_map["cost_contract"]["sha256"]:
            raise EFSError("CONTRACT_INVALID", "cost contract mismatch")
        if as_of < _parse_time(bundle_map["created_at"], "bundle.created_at") or as_of > _parse_time(bundle_map["expires_at"], "bundle.expires_at"):
            raise EFSError("BUNDLE_EXPIRED", "bundle is not valid at request as_of")
        if as_of > _parse_time(bundle_map["calibration"]["expires_at"], "calibration.expires_at"):
            raise EFSError("CALIBRATION_EXPIRED", "calibration is not valid at request as_of")

        values, metadata = _parse_features(request_map, bundle_map, as_of)
        expert_scores, suspended, unavailable = _select_experts(bundle_map, values, metadata, as_of)
        set_id, aggregate = _choose_aggregator(bundle_map, expert_scores)
        _component_usage_gate(bundle_map, expert_scores, set_id, mode)
        raw_candidate = _sigmoid(aggregate)
        calibration = bundle_map["calibration"]
        calibrated_candidate_raw = _sigmoid(decimal_from(calibration["a"], "calibration a") * aggregate + decimal_from(calibration["b"], "calibration b"))
        candidate_prob = Decimal(canonical_decimal(calibrated_candidate_raw))
        candidate_baseline = Decimal(canonical_decimal(decimal_from(bundle_map["baseline"]["prob_up"], "baseline probability")))
        candidate_lift = candidate_prob - candidate_baseline
        candidate_efs = candidate_prob * Decimal(100)
        candidate_lift_pp = candidate_lift * Decimal(100)
        candidate_magnitude = _magnitude(bundle_map, aggregate)
        candidate_timing = _timing(bundle_map, aggregate)
        candidate_economic_edge = _economic_edge(bundle_map, aggregate)
        candidate_reliability = _reliability(bundle_map, expert_scores)

        direction_validated = _status_at_least(calibration["status"], "OOS_VALIDATED")
        baseline_validated = _status_at_least(bundle_map["baseline"]["status"], "OOS_VALIDATED")
        efs_validated = direction_validated
        lift_validated = direction_validated and baseline_validated
        magnitude_validated = _status_at_least(bundle_map["magnitude_head"]["status"], "OOS_VALIDATED")
        timing_validated = _status_at_least(bundle_map["timing_head"]["status"], "OOS_VALIDATED")
        economic_edge_validated = _status_at_least(bundle_map["economic_edge_head"]["status"], "OOS_VALIDATED")
        reliability_validated = _status_at_least(bundle_map["reliability_head"]["status"], "OOS_VALIDATED")

        if candidate_efs > Decimal(50):
            candidate_direction = "BULLISH_PROBABILITY"
        elif candidate_efs < Decimal(50):
            candidate_direction = "BEARISH_PROBABILITY"
        else:
            candidate_direction = "NEUTRAL_PROBABILITY"

        if candidate_lift > 0:
            candidate_edge = "POSITIVE_LIFT"
        elif candidate_lift < 0:
            candidate_edge = "NEGATIVE_LIFT"
        else:
            candidate_edge = "NO_LIFT"

        result: dict[str, Any] = {
            "schema": RESULT_SCHEMA,
            "stable_id": STABLE_ID,
            "runtime_version": RUNTIME_VERSION,
            "status": "FORECAST",
            "request_id": request_map["request_id"],
            "instrument_id": request_map["instrument_id"],
            "as_of": request_map["as_of"],
            "horizon": horizon,
            "usage_mode": mode,
            "bundle_id": bundle_map["bundle_id"],
            "bundle_sha256": bundle_map["payload_sha256"],
            "model_set_sha256": bundle_map["model_set_sha256"],
            "promotion_receipt_sha256": bundle_map["promotion_evidence"]["receipt_sha256"],
            "trust": trust_state,
            "active_expert_set": set_id,
            "active_experts": sorted(expert_scores),
            "suspended_experts": sorted(suspended),
            "unavailable_experts": sorted(unavailable),
            "raw_candidate_score": canonical_decimal(raw_candidate),
            "candidate_prob_up": canonical_decimal(candidate_prob),
            "prob_up": canonical_decimal(candidate_prob) if direction_validated else None,
            "probability_semantics": "OOS_CALIBRATED_PROBABILITY" if direction_validated else "CANDIDATE_SCORE_NOT_A_VALIDATED_PROBABILITY",
            "candidate_base_prob": canonical_decimal(candidate_baseline),
            "base_prob": canonical_decimal(candidate_baseline) if baseline_validated else None,
            "candidate_probability_lift": canonical_decimal(candidate_lift),
            "probability_lift": canonical_decimal(candidate_lift) if lift_validated else None,
            "candidate_probability_lift_pp": canonical_decimal(candidate_lift_pp),
            "probability_lift_pp": canonical_decimal(candidate_lift_pp) if lift_validated else None,
            "candidate_efs": canonical_decimal(candidate_efs),
            "efs": canonical_decimal(candidate_efs) if efs_validated else None,
            "efs_semantics": "UP_PROBABILITY_PERCENT_0_TO_100",
            "candidate_direction_code": candidate_direction,
            "direction_code": candidate_direction if efs_validated else None,
            "candidate_edge_code": candidate_edge,
            "edge_code": candidate_edge if lift_validated else None,
            "candidate_expected_move": candidate_magnitude,
            "expected_move": candidate_magnitude if magnitude_validated else None,
            "magnitude_semantics": "VALIDATED_NET_RETURN_QUANTILES" if magnitude_validated else "ENGINEERING_CANDIDATE_NOT_A_VALIDATED_INTERVAL",
            "candidate_timing": candidate_timing,
            "timing": candidate_timing if timing_validated else None,
            "timing_semantics": "VALIDATED_COMPETING_RISK_DISTRIBUTION" if timing_validated else "ENGINEERING_CANDIDATE_NOT_A_VALIDATED_TIMING_DISTRIBUTION",
            "candidate_expected_net_return": canonical_decimal(candidate_economic_edge),
            "expected_net_return": canonical_decimal(candidate_economic_edge) if economic_edge_validated else None,
            "candidate_positive_economic_edge": candidate_economic_edge > 0,
            "positive_economic_edge": (candidate_economic_edge > 0) if economic_edge_validated else None,
            "economic_edge_semantics": "VALIDATED_FULL_COST_EXPECTED_NET_RETURN" if economic_edge_validated else "ENGINEERING_CANDIDATE_NOT_A_VALIDATED_ECONOMIC_EDGE",
            "candidate_reliability": canonical_decimal(candidate_reliability),
            "reliability": canonical_decimal(candidate_reliability) if reliability_validated else None,
            "reliability_semantics": "VALIDATED_RELIABILITY_SCORE" if reliability_validated else "ENGINEERING_CANDIDATE_NOT_A_VALIDATED_RELIABILITY_SCORE",
            "data_quality": {
                "state": "POINT_IN_TIME_CONTRACT_VALIDATED",
                "feature_count": len(values),
                "minimum_evidence_grade": min((metadata[name]["evidence_grade"] for name in metadata), key=lambda item: GRADE_ORDER[item]) if metadata else None,
                "source_record_hashes_bound": True,
                "feature_payload_hashes_verified": True,
                "source_dataset_allowlists_enforced": True,
                "license_allowlists_enforced": True,
                "freshness_clocks_enforced": True,
            },
            "head_maturity": {logical: bundle_map[key]["status"] for logical, key in HEAD_STATUS_MAP.items()},
            "sample_support": {
                logical: {
                    "status": bundle_map["promotion_evidence"]["heads"][logical]["status"],
                    "effective_sample_size": bundle_map["promotion_evidence"]["heads"][logical]["effective_sample_size"],
                    "evaluation_start": bundle_map["promotion_evidence"]["heads"][logical]["evaluation_start"],
                    "evaluation_end": bundle_map["promotion_evidence"]["heads"][logical]["evaluation_end"],
                }
                for logical in HEAD_STATUS_MAP
            },
            "visualization": {
                "schema": VISUALIZATION_SCHEMA,
                "remote_resources": [],
                "candidate_layers": {
                    "direction": {"candidate_prob_up": canonical_decimal(candidate_prob), "candidate_base_prob": canonical_decimal(candidate_baseline), "candidate_probability_lift_pp": canonical_decimal(candidate_lift_pp), "candidate_efs": canonical_decimal(candidate_efs), "candidate_direction_code": candidate_direction, "candidate_edge_code": candidate_edge},
                    "fan": candidate_magnitude,
                    "competing_risks": candidate_timing,
                    "economic_edge": {"candidate_expected_net_return": canonical_decimal(candidate_economic_edge), "candidate_positive_economic_edge": candidate_economic_edge > 0},
                    "candidate_reliability": canonical_decimal(candidate_reliability),
                },
                "validated_layers": {
                    "direction": None,
                    "fan": candidate_magnitude if magnitude_validated else None,
                    "competing_risks": candidate_timing if timing_validated else None,
                    "economic_edge": ({"expected_net_return": canonical_decimal(candidate_economic_edge), "positive_economic_edge": candidate_economic_edge > 0} if economic_edge_validated else None),
                    "reliability": canonical_decimal(candidate_reliability) if reliability_validated else None,
                },
                "warnings": [] if all((direction_validated, baseline_validated, magnitude_validated, timing_validated, economic_edge_validated, reliability_validated)) else ["包含未完成样本外验证的候选层，不得解释为已验证预测。"],
            },
            "agent_invocations_total": 0,
            "llm_requests_total": 0,
            "llm_input_tokens_total": 0,
            "llm_output_tokens_total": 0,
            "network_requests_total": 0,
        }
        # Assignment-expression helpers above cannot reference base/efs before binding in all branches.
        result["visualization"]["validated_layers"]["direction"] = (
            {
                "prob_up": result["prob_up"],
                "base_prob": result["base_prob"],
                "efs": result["efs"],
                "probability_lift_pp": result["probability_lift_pp"],
                "direction_code": result["direction_code"],
                "edge_code": result["edge_code"],
            }
            if direction_validated and baseline_validated
            else None
        )
        result["result_sha256"] = sha256_hex(result)
        return result
    except EFSError as error:
        return _empty_envelope(request_map, bundle_map, error)
    except Exception:
        return _empty_envelope(request_map, bundle_map, EFSError("INTERNAL_ERROR", "deterministic evaluation failed"))


def evaluate_prepared(
    request: dict[str, Any] | str | bytes,
    prepared: PreparedBundle,
    trust_context: dict[str, Any] | str | bytes | None = None,
) -> dict[str, Any]:
    if not isinstance(prepared, PreparedBundle):
        return _empty_envelope(None, None, EFSError("CONTRACT_INVALID", "prepared bundle is required"))
    bundle_map = prepared._validated_map(_PREPARED_BUNDLE_TOKEN)
    request_map: dict[str, Any] | None = None
    try:
        request_map = _normalize_json_mapping(request, "request", DEFAULT_LIMITS["request_bytes"])
    except EFSError as error:
        return _empty_envelope(request_map, bundle_map, error)
    except Exception:
        return _empty_envelope(request_map, bundle_map, EFSError("INTERNAL_ERROR", "deterministic request normalization failed"))
    return _evaluate_validated_maps(request_map, bundle_map, trust_context)


def evaluate(
    request: dict[str, Any] | str | bytes,
    bundle: dict[str, Any] | str | bytes,
    trust_context: dict[str, Any] | str | bytes | None = None,
) -> dict[str, Any]:
    request_map: dict[str, Any] | None = None
    bundle_map: dict[str, Any] | None = None
    try:
        request_map = _normalize_json_mapping(request, "request", DEFAULT_LIMITS["request_bytes"])
        bundle_map = _normalize_json_mapping(bundle, "bundle", DEFAULT_LIMITS["bundle_bytes"])
        validate_bundle(bundle_map)
    except EFSError as error:
        return _empty_envelope(request_map, bundle_map, error)
    except Exception:
        return _empty_envelope(request_map, bundle_map, EFSError("INTERNAL_ERROR", "deterministic input normalization failed"))
    return _evaluate_validated_maps(request_map, bundle_map, trust_context)


def batch_evaluate_prepared(
    requests: Iterable[dict[str, Any] | str | bytes],
    prepared: PreparedBundle,
    trust_context: dict[str, Any] | str | bytes | None = None,
    *,
    max_batch: int | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(prepared, PreparedBundle):
        raise EFSError("CONTRACT_INVALID", "prepared bundle is required")
    bundle_map = prepared._validated_map(_PREPARED_BUNDLE_TOKEN)
    configured = bundle_map.get("runtime_limits", {}).get("max_batch", DEFAULT_LIMITS["max_batch"])
    raw_limit = configured if max_batch is None else max_batch
    limit = _require_int(raw_limit, "batch limit", minimum=1, maximum=DEFAULT_LIMITS["max_batch"])
    iterator = iter(requests)
    items = list(islice(iterator, limit + 1))
    if len(items) > limit:
        raise EFSError("RESOURCE_LIMIT", "batch size exceeds limit")
    return [evaluate_prepared(item, prepared, trust_context) for item in items]

def batch_evaluate(
    requests: Iterable[dict[str, Any]],
    bundle: dict[str, Any],
    trust_context: dict[str, Any] | None = None,
    *,
    max_batch: int | None = None,
) -> list[dict[str, Any]]:
    configured = bundle.get("runtime_limits", {}).get("max_batch", DEFAULT_LIMITS["max_batch"])
    raw_limit = configured if max_batch is None else max_batch
    limit = _require_int(raw_limit, "batch limit", minimum=1, maximum=DEFAULT_LIMITS["max_batch"])
    iterator = iter(requests)
    items = list(islice(iterator, limit + 1))
    if len(items) > limit:
        raise EFSError("RESOURCE_LIMIT", "batch size exceeds limit")
    return [evaluate(item, bundle, trust_context) for item in items]

def self_check() -> dict[str, Any]:
    return {
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "runtime_profile": {
            "agent_dependency": 0,
            "llm_dependency": 0,
            "llm_tokens_per_evaluation": 0,
            "network_dependency": 0,
            "secret_dependency_for_research": 0,
            "daemon_dependency": 0,
            "database_dependency": 0,
            "resident_background_processes_after_invocation": 0,
            "persistent_local_state_bytes_after_invocation": 0,
            "macos_launchd_units": 0,
        },
        "deployment_profile": "REMOTE_HOST_EMBEDDED_ONLY",
        "macos_runtime_install_permitted": False,
        "macos_launchd_permitted": False,
        "local_footprint_policy": {
            "persistent_files_after_invocation": 0,
            "persistent_bytes_after_invocation": 0,
            "resident_processes_after_invocation": 0,
            "transient_cpu_ram_during_explicit_invocation": "UNAVOIDABLE_NOT_CLAIMED_ZERO",
        },
        "supported_model_types": sorted(ALLOWED_MODEL_TYPES),
        "request_schema_recognized_usage_modes": sorted(USAGE_MODES),
        "release_authorized_usage_modes": sorted(RELEASE_AUTHORIZED_MODES),
        "release_blocked_usage_modes": sorted(USAGE_MODES - RELEASE_AUTHORIZED_MODES),
        "release_capability_ceiling": RELEASE_CAPABILITY_CEILING,
        "dependency_profile": {
            "core_runtime_third_party_dependencies": 0,
            "release_authorized_path_third_party_dependencies": 0,
        },
        "trust_note": "HOST_POLICY_BOUND is sufficient only for SHADOW. DECISION_SUPPORT and its cryptographic approval adapter are not included in v0.0.0.1.",
        "status": "FORMAL_CANDIDATE_SHADOW_ONLY",
    }
