"""Pure append-only dual-ledger core for ABD S07/P03.

The module records immutable advice snapshots separately from actual-funds
events.  An actual-funds event is admissible only with a verified execution
evidence record; an advice event can never mutate actual funds.  This is pure
local deterministic logic: it has no account, order, network, scheduler, or
real-time waiting capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"
ADVICE_LEDGER = "ADVICE"
ACTUAL_FUNDS_LEDGER = "ACTUAL_FUNDS"
ADVICE_RECORDED = "ADVICE_RECORDED"
EXECUTION_EVIDENCE_RECONCILED = "EXECUTION_EVIDENCE_RECONCILED"
NO_ADVICE = "NO_ADVICE"
LEDGER_VALID_NO_ADVICE = "LEDGER_VALID_NO_ADVICE"
GENESIS = "GENESIS"
SCHEMA_DRAFT_URI = "https:" + "//json-schema.org/draft/2020-12/schema"
SCHEMA_ID_URI = "https:" + "//abd.local/schemas/ledger/1.0.0"

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$")
EVENT_ID_RE = re.compile(r"^LED-[A-Z0-9][A-Z0-9_-]{3,63}$")
IDEMPOTENCY_KEY_RE = re.compile(r"^IDEMP-[A-Z0-9][A-Z0-9:_-]{3,95}$")
ADVICE_ID_RE = re.compile(r"^ADV-[A-Z0-9][A-Z0-9_-]{3,63}$")
IDENTITY_KEY_RE = re.compile(r"^IDK-S07P01-[A-Z0-9_-]{8,64}$")
EVIDENCE_ID_RE = re.compile(r"^EXEC-[A-Z0-9][A-Z0-9_-]{3,63}$")

REQUIRED_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "ledger_kind",
        "event_type",
        "idempotency_key",
        "sequence",
        "recorded_at",
        "previous_event_sha256",
        "payload",
        "event_sha256",
    }
)
REQUIRED_POLICY_FIELDS = frozenset(
    {
        "schema_content_sha256",
        "parameter_version_sha256",
        "temporal_lineage_evidence_sha256",
        "opening_balance_cents",
        "currency",
        "maximum_abs_cash_delta_cents",
    }
)
REQUIRED_ADVICE_PAYLOAD_FIELDS = frozenset(
    {
        "advice_id",
        "identity_key",
        "temporal_lineage_evidence_sha256",
        "policy_version_sha256",
        "advice_action",
        "recommended_stake_cents",
        "adverse_probability_delta",
        "adverse_odds_tick",
    }
)
REQUIRED_EXECUTION_PAYLOAD_FIELDS = frozenset(
    {
        "execution_evidence_id",
        "execution_evidence_sha256",
        "execution_evidence_verified",
        "execution_evidence_kind",
        "fixture_only",
        "advice_event_sha256",
        "actual_cash_delta_cents",
        "settlement_status",
    }
)


class LedgerValidationError(ValueError):
    """Fail-closed ledger validation error with a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PreparedLedgerPolicy:
    schema_content_sha256: str
    parameter_version_sha256: str
    temporal_lineage_evidence_sha256: str
    opening_balance_cents: int
    currency: str
    maximum_abs_cash_delta_cents: int


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LedgerValidationError("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def _reject_float(token: str) -> Any:
    raise LedgerValidationError("BINARY_FLOAT_NOT_ALLOWED", token)


def _reject_constant(token: str) -> Any:
    raise LedgerValidationError("NON_FINITE_JSON_NUMBER", token)


def strict_json_load(path: Path) -> Any:
    """Load JSON without duplicate keys, binary floats, or NaN values."""

    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )


def _reject_binary_float(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise LedgerValidationError("BINARY_FLOAT_NOT_ALLOWED", path)
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_binary_float(item, "%s.%s" % (path, key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_binary_float(item, "%s[%d]" % (path, index))


def canonical_json_bytes(value: Any) -> bytes:
    _reject_binary_float(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_mapping(value: Any, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LedgerValidationError(code, "%s must be an object" % label)
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise LedgerValidationError("UNKNOWN_FIELD", "%s: %s" % (label, ",".join(unknown)))
    if missing:
        raise LedgerValidationError("MISSING_FIELD", "%s: %s" % (label, ",".join(missing)))


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise LedgerValidationError("HASH_INVALID", label)
    return value


def _require_identifier(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise LedgerValidationError("IDENTIFIER_INVALID", label)
    return value


def _require_integer(value: Any, code: str, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerValidationError(code, label)
    if minimum is not None and value < minimum:
        raise LedgerValidationError(code, label)
    return value


def _require_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not TIME_RE.fullmatch(value):
        raise LedgerValidationError("TIMEZONE_REQUIRED", label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LedgerValidationError("MALFORMED_TIMESTAMP", label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerValidationError("TIMEZONE_REQUIRED", label)
    return value


def validate_schema_document(schema: Any) -> Mapping[str, Any]:
    """Validate the production-equivalent ledger-event schema."""

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
        "x_abd_production_equivalent",
        "x_abd_two_ledgers",
    }
    if set(payload) != expected_top_level:
        raise LedgerValidationError("SCHEMA_INVALID", "unexpected schema keys")
    if payload.get("$schema") != SCHEMA_DRAFT_URI or payload.get("$id") != SCHEMA_ID_URI:
        raise LedgerValidationError("SCHEMA_INVALID", "schema identifiers")
    if payload.get("type") != "object" or payload.get("additionalProperties") is not False:
        raise LedgerValidationError("SCHEMA_INVALID", "object boundary")
    if payload.get("x_abd_artifact_id") != "ART-S07-P03-01":
        raise LedgerValidationError("SCHEMA_INVALID", "artifact identifier")
    if payload.get("x_abd_contract_id") != "AC-S07-P03":
        raise LedgerValidationError("SCHEMA_INVALID", "contract identifier")
    if payload.get("x_abd_production_equivalent") is not True or payload.get("x_abd_two_ledgers") is not True:
        raise LedgerValidationError("SCHEMA_INVALID", "production boundary")
    required = payload.get("required")
    properties = payload.get("properties")
    if not isinstance(required, list) or frozenset(required) != REQUIRED_EVENT_FIELDS or len(required) != len(REQUIRED_EVENT_FIELDS):
        raise LedgerValidationError("SCHEMA_INVALID", "required fields")
    if not isinstance(properties, Mapping) or frozenset(properties) != REQUIRED_EVENT_FIELDS:
        raise LedgerValidationError("SCHEMA_INVALID", "properties")
    if properties.get("schema_version", {}).get("const") != SCHEMA_VERSION:
        raise LedgerValidationError("SCHEMA_INVALID", "schema version")
    for field in REQUIRED_EVENT_FIELDS - {"schema_version", "sequence", "payload"}:
        definition = properties.get(field)
        if not isinstance(definition, Mapping) or definition.get("type") != "string":
            raise LedgerValidationError("SCHEMA_INVALID", "property %s" % field)
    if properties.get("sequence", {}).get("type") != "integer":
        raise LedgerValidationError("SCHEMA_INVALID", "sequence")
    if properties.get("payload", {}).get("type") != "object":
        raise LedgerValidationError("SCHEMA_INVALID", "payload")
    return payload


def prepare_policy(schema: Any, policy: Any) -> PreparedLedgerPolicy:
    """Pin frozen schema, parameter, temporal lineage, and funds boundaries."""

    validated_schema = validate_schema_document(schema)
    payload = _require_mapping(policy, "POLICY_INVALID", "policy")
    _reject_binary_float(payload)
    _require_exact_keys(payload, REQUIRED_POLICY_FIELDS, "policy")
    schema_hash = _require_sha256(payload["schema_content_sha256"], "schema_content_sha256")
    if schema_hash != sha256_json(validated_schema):
        raise LedgerValidationError("SCHEMA_HASH_MISMATCH", schema_hash)
    parameter_hash = _require_sha256(payload["parameter_version_sha256"], "parameter_version_sha256")
    lineage_hash = _require_sha256(payload["temporal_lineage_evidence_sha256"], "temporal_lineage_evidence_sha256")
    opening = _require_integer(payload["opening_balance_cents"], "OPENING_BALANCE_INVALID", "opening_balance_cents", minimum=1)
    maximum = _require_integer(
        payload["maximum_abs_cash_delta_cents"],
        "MAXIMUM_CASH_DELTA_INVALID",
        "maximum_abs_cash_delta_cents",
        minimum=1,
    )
    if maximum > opening:
        raise LedgerValidationError("MAXIMUM_CASH_DELTA_INVALID", "must not exceed opening balance")
    if payload["currency"] != "AUD":
        raise LedgerValidationError("CURRENCY_INVALID", "AUD required")
    return PreparedLedgerPolicy(
        schema_content_sha256=schema_hash,
        parameter_version_sha256=parameter_hash,
        temporal_lineage_evidence_sha256=lineage_hash,
        opening_balance_cents=opening,
        currency="AUD",
        maximum_abs_cash_delta_cents=maximum,
    )


def event_body_sha256(event: Mapping[str, Any]) -> str:
    """Hash an event body without its self-referential event hash."""

    body = dict(event)
    body.pop("event_sha256", None)
    return sha256_json(body)


def make_event(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return an event with the canonical immutable body hash attached."""

    candidate = dict(body)
    if "event_sha256" in candidate:
        raise LedgerValidationError("EVENT_HASH_ALREADY_PRESENT", "event_sha256")
    candidate["event_sha256"] = event_body_sha256(candidate)
    return candidate


def _validate_advice_payload(policy: PreparedLedgerPolicy, payload: Any) -> Mapping[str, Any]:
    value = _require_mapping(payload, "PAYLOAD_INVALID", "advice payload")
    _reject_binary_float(value)
    _require_exact_keys(value, REQUIRED_ADVICE_PAYLOAD_FIELDS, "advice payload")
    _require_identifier(value["advice_id"], ADVICE_ID_RE, "advice_id")
    _require_identifier(value["identity_key"], IDENTITY_KEY_RE, "identity_key")
    if value["temporal_lineage_evidence_sha256"] != policy.temporal_lineage_evidence_sha256:
        raise LedgerValidationError("TEMPORAL_LINEAGE_EVIDENCE_MISMATCH", "temporal_lineage_evidence_sha256")
    if value["policy_version_sha256"] != policy.parameter_version_sha256:
        raise LedgerValidationError("PARAMETER_VERSION_MISMATCH", "policy_version_sha256")
    if value["advice_action"] != NO_ADVICE:
        raise LedgerValidationError("ADVICE_ACTION_NOT_ALLOWED", str(value["advice_action"]))
    if _require_integer(value["recommended_stake_cents"], "STAKE_INVALID", "recommended_stake_cents", minimum=0) != 0:
        raise LedgerValidationError("STAKE_MUST_BE_ZERO", "P03 records no executable recommendation")
    if value["adverse_probability_delta"] != "0.0001":
        raise LedgerValidationError("ADVERSE_PROBABILITY_BOUNDARY_INVALID", str(value["adverse_probability_delta"]))
    if value["adverse_odds_tick"] != "0.0001":
        raise LedgerValidationError("ADVERSE_ODDS_BOUNDARY_INVALID", str(value["adverse_odds_tick"]))
    return value


def _validate_execution_payload(policy: PreparedLedgerPolicy, payload: Any) -> Mapping[str, Any]:
    value = _require_mapping(payload, "PAYLOAD_INVALID", "execution payload")
    _reject_binary_float(value)
    _require_exact_keys(value, REQUIRED_EXECUTION_PAYLOAD_FIELDS, "execution payload")
    _require_identifier(value["execution_evidence_id"], EVIDENCE_ID_RE, "execution_evidence_id")
    _require_sha256(value["execution_evidence_sha256"], "execution_evidence_sha256")
    if value["execution_evidence_verified"] is not True:
        raise LedgerValidationError("EXECUTION_EVIDENCE_REQUIRED", "execution_evidence_verified")
    if value["execution_evidence_kind"] not in {"FROZEN_TEST_FIXTURE", "VERIFIED_EXECUTION_EVIDENCE"}:
        raise LedgerValidationError("EXECUTION_EVIDENCE_KIND_INVALID", str(value["execution_evidence_kind"]))
    if not isinstance(value["fixture_only"], bool):
        raise LedgerValidationError("FIXTURE_MARKER_INVALID", "fixture_only")
    _require_sha256(value["advice_event_sha256"], "advice_event_sha256")
    delta = _require_integer(value["actual_cash_delta_cents"], "CASH_DELTA_INVALID", "actual_cash_delta_cents")
    if delta == 0 or abs(delta) > policy.maximum_abs_cash_delta_cents:
        raise LedgerValidationError("CASH_DELTA_INVALID", str(delta))
    if value["settlement_status"] != "SETTLED":
        raise LedgerValidationError("SETTLEMENT_STATUS_INVALID", str(value["settlement_status"]))
    return value


def validate_event(policy: PreparedLedgerPolicy, event: Any, *, expected_ledger_kind: str | None = None) -> Mapping[str, Any]:
    """Validate a single fully materialized event, including its self-hash."""

    if not isinstance(policy, PreparedLedgerPolicy):
        raise LedgerValidationError("POLICY_INVALID", "prepared policy required")
    payload = _require_mapping(event, "EVENT_INVALID", "event")
    _reject_binary_float(payload)
    _require_exact_keys(payload, REQUIRED_EVENT_FIELDS, "event")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise LedgerValidationError("SCHEMA_VERSION_MISMATCH", str(payload["schema_version"]))
    _require_identifier(payload["event_id"], EVENT_ID_RE, "event_id")
    kind = payload["ledger_kind"]
    if kind not in {ADVICE_LEDGER, ACTUAL_FUNDS_LEDGER}:
        raise LedgerValidationError("LEDGER_KIND_INVALID", str(kind))
    if expected_ledger_kind is not None and kind != expected_ledger_kind:
        raise LedgerValidationError("LEDGER_KIND_MISMATCH", "%s != %s" % (kind, expected_ledger_kind))
    _require_identifier(payload["idempotency_key"], IDEMPOTENCY_KEY_RE, "idempotency_key")
    _require_integer(payload["sequence"], "SEQUENCE_INVALID", "sequence", minimum=1)
    _require_timestamp(payload["recorded_at"], "recorded_at")
    previous = payload["previous_event_sha256"]
    if previous != GENESIS:
        _require_sha256(previous, "previous_event_sha256")
    expected_type = ADVICE_RECORDED if kind == ADVICE_LEDGER else EXECUTION_EVIDENCE_RECONCILED
    if payload["event_type"] != expected_type:
        raise LedgerValidationError("EVENT_TYPE_INVALID", str(payload["event_type"]))
    if kind == ADVICE_LEDGER:
        _validate_advice_payload(policy, payload["payload"])
    else:
        _validate_execution_payload(policy, payload["payload"])
    actual_hash = _require_sha256(payload["event_sha256"], "event_sha256")
    if actual_hash != event_body_sha256(payload):
        raise LedgerValidationError("EVENT_HASH_MISMATCH", str(payload["event_id"]))
    return payload


def validate_ledger(policy: PreparedLedgerPolicy, ledger_kind: str, events: Any) -> dict[str, Any]:
    """Validate an append-only chain and derive only local deterministic facts."""

    if ledger_kind not in {ADVICE_LEDGER, ACTUAL_FUNDS_LEDGER}:
        raise LedgerValidationError("LEDGER_KIND_INVALID", str(ledger_kind))
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise LedgerValidationError("LEDGER_INVALID", "events must be a sequence")
    previous_hash = GENESIS
    event_ids: set[str] = set()
    idempotency_keys: set[str] = set()
    cash_delta_cents = 0
    execution_evidence_count = 0
    chain: list[Mapping[str, Any]] = []
    for sequence, raw_event in enumerate(events, 1):
        event = validate_event(policy, raw_event, expected_ledger_kind=ledger_kind)
        if event["sequence"] != sequence:
            raise LedgerValidationError("SEQUENCE_INVALID", str(event["sequence"]))
        if event["previous_event_sha256"] != previous_hash:
            raise LedgerValidationError("HASH_CHAIN_BROKEN", str(event["event_id"]))
        if event["event_id"] in event_ids:
            raise LedgerValidationError("DUPLICATE_EVENT_ID", str(event["event_id"]))
        if event["idempotency_key"] in idempotency_keys:
            raise LedgerValidationError("DUPLICATE_IDEMPOTENCY_KEY", str(event["idempotency_key"]))
        event_ids.add(str(event["event_id"]))
        idempotency_keys.add(str(event["idempotency_key"]))
        previous_hash = str(event["event_sha256"])
        if ledger_kind == ACTUAL_FUNDS_LEDGER:
            execution_evidence_count += 1
            cash_delta_cents += int(event["payload"]["actual_cash_delta_cents"])
        chain.append(event)
    balance_cents = policy.opening_balance_cents + cash_delta_cents
    if ledger_kind == ACTUAL_FUNDS_LEDGER and balance_cents < 0:
        raise LedgerValidationError("NEGATIVE_BALANCE", str(balance_cents))
    return {
        "ledger_kind": ledger_kind,
        "event_count": len(chain),
        "chain_head_sha256": previous_hash,
        "cash_delta_cents": cash_delta_cents if ledger_kind == ACTUAL_FUNDS_LEDGER else 0,
        "balance_cents": balance_cents if ledger_kind == ACTUAL_FUNDS_LEDGER else policy.opening_balance_cents,
        "execution_evidence_count": execution_evidence_count if ledger_kind == ACTUAL_FUNDS_LEDGER else 0,
        "events": tuple(chain),
    }


def append_event(
    policy: PreparedLedgerPolicy,
    ledger_kind: str,
    existing_events: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Append once, replay idempotently, and reject conflicting keys."""

    current = validate_ledger(policy, ledger_kind, existing_events)
    event = validate_event(policy, candidate, expected_ledger_kind=ledger_kind)
    for prior in current["events"]:
        if prior["idempotency_key"] == event["idempotency_key"]:
            identical = canonical_json_bytes(prior) == canonical_json_bytes(event)
            return {
                "status": "IDEMPOTENT_REPLAY" if identical else "IDEMPOTENCY_CONFLICT",
                "appended": False,
                "events": current["events"],
                "ledger": current,
            }
    expected_sequence = len(current["events"]) + 1
    if event["sequence"] != expected_sequence or event["previous_event_sha256"] != current["chain_head_sha256"]:
        raise LedgerValidationError("APPEND_POSITION_INVALID", str(event["event_id"]))
    updated = tuple(current["events"]) + (event,)
    return {
        "status": "APPENDED",
        "appended": True,
        "events": updated,
        "ledger": validate_ledger(policy, ledger_kind, updated),
    }


def evaluate_ledgers(
    policy: PreparedLedgerPolicy,
    advice_events: Any,
    actual_funds_events: Any,
) -> dict[str, Any]:
    """Evaluate separation, provenance, and the no-evidence funds invariant."""

    try:
        advice = validate_ledger(policy, ADVICE_LEDGER, advice_events)
        actual = validate_ledger(policy, ACTUAL_FUNDS_LEDGER, actual_funds_events)
        advice_hashes = {event["event_sha256"] for event in advice["events"]}
        orphaned = [
            event["event_sha256"]
            for event in actual["events"]
            if event["payload"]["advice_event_sha256"] not in advice_hashes
        ]
        if orphaned:
            raise LedgerValidationError("ACTUAL_EVENT_WITHOUT_ADVICE_PROVENANCE", ",".join(orphaned))
        no_execution_evidence = actual["execution_evidence_count"] == 0
        unchanged_without_evidence = (
            no_execution_evidence
            and actual["event_count"] == 0
            and actual["cash_delta_cents"] == 0
            and actual["balance_cents"] == policy.opening_balance_cents
        )
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": LEDGER_VALID_NO_ADVICE,
            "reason_codes": [],
            "advice_event_count": advice["event_count"],
            "advice_chain_head_sha256": advice["chain_head_sha256"],
            "actual_funds_event_count": actual["event_count"],
            "actual_funds_chain_head_sha256": actual["chain_head_sha256"],
            "actual_funds_cash_delta_cents": actual["cash_delta_cents"],
            "actual_funds_balance_cents": actual["balance_cents"],
            "execution_evidence_count": actual["execution_evidence_count"],
            "actual_funds_unchanged_without_execution_evidence": unchanged_without_evidence,
            "actual_funds_changed": actual["cash_delta_cents"] != 0,
            "recommendation_generated": False,
            "order_submission_enabled": False,
            "external_network_used": False,
            "real_time_soak_waited": False,
        }
    except LedgerValidationError as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": NO_ADVICE,
            "reason_codes": [exc.code],
            "advice_event_count": 0,
            "advice_chain_head_sha256": GENESIS,
            "actual_funds_event_count": 0,
            "actual_funds_chain_head_sha256": GENESIS,
            "actual_funds_cash_delta_cents": 0,
            "actual_funds_balance_cents": None,
            "execution_evidence_count": 0,
            "actual_funds_unchanged_without_execution_evidence": False,
            "actual_funds_changed": False,
            "recommendation_generated": False,
            "order_submission_enabled": False,
            "external_network_used": False,
            "real_time_soak_waited": False,
        }
    result["output_sha256"] = sha256_json(result)
    return result


def deterministic_ledger_hash(
    policy: PreparedLedgerPolicy,
    advice_events: Any,
    actual_funds_events: Any,
) -> str:
    """Return the canonical output hash for a frozen dual-ledger replay."""

    return evaluate_ledgers(policy, advice_events, actual_funds_events)["output_sha256"]
