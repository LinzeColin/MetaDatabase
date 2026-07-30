"""Independent pure reconciliation oracle for ABD S07/P03.

This module intentionally rechecks the event shape, canonical hashes, chain
links, idempotency keys, execution evidence, and derived actual balance rather
than trusting the ledger implementation.  It reads only supplied in-memory
fixtures and has no external side-effect capability.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1.0.0"
ADVICE_LEDGER = "ADVICE"
ACTUAL_FUNDS_LEDGER = "ACTUAL_FUNDS"
ADVICE_RECORDED = "ADVICE_RECORDED"
EXECUTION_EVIDENCE_RECONCILED = "EXECUTION_EVIDENCE_RECONCILED"
NO_ADVICE = "NO_ADVICE"
GENESIS = "GENESIS"

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$")
EVENT_ID_RE = re.compile(r"^LED-[A-Z0-9][A-Z0-9_-]{3,63}$")
IDEMPOTENCY_KEY_RE = re.compile(r"^IDEMP-[A-Z0-9][A-Z0-9:_-]{3,95}$")
ADVICE_ID_RE = re.compile(r"^ADV-[A-Z0-9][A-Z0-9_-]{3,63}$")
IDENTITY_KEY_RE = re.compile(r"^IDK-S07P01-[A-Z0-9_-]{8,64}$")
EVIDENCE_ID_RE = re.compile(r"^EXEC-[A-Z0-9][A-Z0-9_-]{3,63}$")

EVENT_FIELDS = frozenset(
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
POLICY_FIELDS = frozenset(
    {
        "schema_content_sha256",
        "parameter_version_sha256",
        "temporal_lineage_evidence_sha256",
        "opening_balance_cents",
        "currency",
        "maximum_abs_cash_delta_cents",
    }
)
ADVICE_FIELDS = frozenset(
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
EXECUTION_FIELDS = frozenset(
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


class ReconciliationValidationError(ValueError):
    """Fail-closed independent reconciliation error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


def _reject_binary_float(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise ReconciliationValidationError("BINARY_FLOAT_NOT_ALLOWED", path)
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


def _mapping(value: Any, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReconciliationValidationError(code, "%s must be an object" % label)
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ReconciliationValidationError("UNKNOWN_FIELD", "%s: %s" % (label, ",".join(unknown)))
    if missing:
        raise ReconciliationValidationError("MISSING_FIELD", "%s: %s" % (label, ",".join(missing)))


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ReconciliationValidationError("HASH_INVALID", label)
    return value


def _identifier(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ReconciliationValidationError("IDENTIFIER_INVALID", label)
    return value


def _integer(value: Any, code: str, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReconciliationValidationError(code, label)
    if minimum is not None and value < minimum:
        raise ReconciliationValidationError(code, label)
    return value


def _timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str) or not TIME_RE.fullmatch(value):
        raise ReconciliationValidationError("TIMEZONE_REQUIRED", label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReconciliationValidationError("MALFORMED_TIMESTAMP", label) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReconciliationValidationError("TIMEZONE_REQUIRED", label)


def _event_hash(event: Mapping[str, Any]) -> str:
    body = dict(event)
    body.pop("event_sha256", None)
    return sha256_json(body)


def _policy(value: Any) -> Mapping[str, Any]:
    policy = _mapping(value, "POLICY_INVALID", "policy")
    _reject_binary_float(policy)
    _exact_keys(policy, POLICY_FIELDS, "policy")
    _hash(policy["schema_content_sha256"], "schema_content_sha256")
    _hash(policy["parameter_version_sha256"], "parameter_version_sha256")
    _hash(policy["temporal_lineage_evidence_sha256"], "temporal_lineage_evidence_sha256")
    opening = _integer(policy["opening_balance_cents"], "OPENING_BALANCE_INVALID", "opening_balance_cents", minimum=1)
    maximum = _integer(
        policy["maximum_abs_cash_delta_cents"],
        "MAXIMUM_CASH_DELTA_INVALID",
        "maximum_abs_cash_delta_cents",
        minimum=1,
    )
    if policy["currency"] != "AUD" or maximum > opening:
        raise ReconciliationValidationError("POLICY_INVALID", "currency or maximum")
    return policy


def _advice_payload(policy: Mapping[str, Any], value: Any) -> Mapping[str, Any]:
    payload = _mapping(value, "PAYLOAD_INVALID", "advice payload")
    _reject_binary_float(payload)
    _exact_keys(payload, ADVICE_FIELDS, "advice payload")
    _identifier(payload["advice_id"], ADVICE_ID_RE, "advice_id")
    _identifier(payload["identity_key"], IDENTITY_KEY_RE, "identity_key")
    if payload["temporal_lineage_evidence_sha256"] != policy["temporal_lineage_evidence_sha256"]:
        raise ReconciliationValidationError("TEMPORAL_LINEAGE_EVIDENCE_MISMATCH", "advice")
    if payload["policy_version_sha256"] != policy["parameter_version_sha256"]:
        raise ReconciliationValidationError("PARAMETER_VERSION_MISMATCH", "advice")
    if payload["advice_action"] != NO_ADVICE:
        raise ReconciliationValidationError("ADVICE_ACTION_NOT_ALLOWED", str(payload["advice_action"]))
    if _integer(payload["recommended_stake_cents"], "STAKE_INVALID", "recommended_stake_cents", minimum=0) != 0:
        raise ReconciliationValidationError("STAKE_MUST_BE_ZERO", "P03")
    if payload["adverse_probability_delta"] != "0.0001" or payload["adverse_odds_tick"] != "0.0001":
        raise ReconciliationValidationError("ADVERSE_PERTURBATION_BOUNDARY_INVALID", "0.0001 required")
    return payload


def _execution_payload(policy: Mapping[str, Any], value: Any) -> Mapping[str, Any]:
    payload = _mapping(value, "PAYLOAD_INVALID", "execution payload")
    _reject_binary_float(payload)
    _exact_keys(payload, EXECUTION_FIELDS, "execution payload")
    _identifier(payload["execution_evidence_id"], EVIDENCE_ID_RE, "execution_evidence_id")
    _hash(payload["execution_evidence_sha256"], "execution_evidence_sha256")
    if payload["execution_evidence_verified"] is not True:
        raise ReconciliationValidationError("EXECUTION_EVIDENCE_REQUIRED", "unverified")
    if payload["execution_evidence_kind"] not in {"FROZEN_TEST_FIXTURE", "VERIFIED_EXECUTION_EVIDENCE"}:
        raise ReconciliationValidationError("EXECUTION_EVIDENCE_KIND_INVALID", str(payload["execution_evidence_kind"]))
    if not isinstance(payload["fixture_only"], bool):
        raise ReconciliationValidationError("FIXTURE_MARKER_INVALID", "fixture_only")
    _hash(payload["advice_event_sha256"], "advice_event_sha256")
    delta = _integer(payload["actual_cash_delta_cents"], "CASH_DELTA_INVALID", "actual_cash_delta_cents")
    if delta == 0 or abs(delta) > int(policy["maximum_abs_cash_delta_cents"]):
        raise ReconciliationValidationError("CASH_DELTA_INVALID", str(delta))
    if payload["settlement_status"] != "SETTLED":
        raise ReconciliationValidationError("SETTLEMENT_STATUS_INVALID", str(payload["settlement_status"]))
    return payload


def _walk_chain(policy: Mapping[str, Any], ledger_kind: str, events: Any) -> dict[str, Any]:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise ReconciliationValidationError("LEDGER_INVALID", "events must be a sequence")
    prior_hash = GENESIS
    seen_event_ids: set[str] = set()
    seen_idempotency: set[str] = set()
    normalized: list[Mapping[str, Any]] = []
    cash_delta = 0
    for expected_sequence, raw in enumerate(events, 1):
        event = _mapping(raw, "EVENT_INVALID", "event")
        _reject_binary_float(event)
        _exact_keys(event, EVENT_FIELDS, "event")
        if event["schema_version"] != SCHEMA_VERSION:
            raise ReconciliationValidationError("SCHEMA_VERSION_MISMATCH", str(event["schema_version"]))
        _identifier(event["event_id"], EVENT_ID_RE, "event_id")
        _identifier(event["idempotency_key"], IDEMPOTENCY_KEY_RE, "idempotency_key")
        if event["ledger_kind"] != ledger_kind:
            raise ReconciliationValidationError("LEDGER_KIND_MISMATCH", str(event["ledger_kind"]))
        expected_type = ADVICE_RECORDED if ledger_kind == ADVICE_LEDGER else EXECUTION_EVIDENCE_RECONCILED
        if event["event_type"] != expected_type:
            raise ReconciliationValidationError("EVENT_TYPE_INVALID", str(event["event_type"]))
        if _integer(event["sequence"], "SEQUENCE_INVALID", "sequence", minimum=1) != expected_sequence:
            raise ReconciliationValidationError("SEQUENCE_INVALID", str(event["sequence"]))
        _timestamp(event["recorded_at"], "recorded_at")
        if event["previous_event_sha256"] != prior_hash:
            raise ReconciliationValidationError("HASH_CHAIN_BROKEN", str(event["event_id"]))
        if prior_hash != GENESIS:
            _hash(prior_hash, "previous_event_sha256")
        actual_hash = _hash(event["event_sha256"], "event_sha256")
        if actual_hash != _event_hash(event):
            raise ReconciliationValidationError("EVENT_HASH_MISMATCH", str(event["event_id"]))
        if event["event_id"] in seen_event_ids or event["idempotency_key"] in seen_idempotency:
            raise ReconciliationValidationError("IDEMPOTENCY_OR_EVENT_DUPLICATE", str(event["event_id"]))
        seen_event_ids.add(str(event["event_id"]))
        seen_idempotency.add(str(event["idempotency_key"]))
        if ledger_kind == ADVICE_LEDGER:
            _advice_payload(policy, event["payload"])
        else:
            payload = _execution_payload(policy, event["payload"])
            cash_delta += int(payload["actual_cash_delta_cents"])
        prior_hash = actual_hash
        normalized.append(event)
    return {
        "events": tuple(normalized),
        "event_count": len(normalized),
        "chain_head_sha256": prior_hash,
        "cash_delta_cents": cash_delta,
    }


def reconcile_ledgers(policy: Any, advice_events: Any, actual_funds_events: Any) -> dict[str, Any]:
    """Independently derive the reconciled actual balance or reject closed."""

    try:
        checked_policy = _policy(policy)
        advice = _walk_chain(checked_policy, ADVICE_LEDGER, advice_events)
        actual = _walk_chain(checked_policy, ACTUAL_FUNDS_LEDGER, actual_funds_events)
        advice_hashes = {event["event_sha256"] for event in advice["events"]}
        orphaned = [
            event["event_sha256"]
            for event in actual["events"]
            if event["payload"]["advice_event_sha256"] not in advice_hashes
        ]
        if orphaned:
            raise ReconciliationValidationError("ACTUAL_EVENT_WITHOUT_ADVICE_PROVENANCE", ",".join(orphaned))
        balance = int(checked_policy["opening_balance_cents"]) + actual["cash_delta_cents"]
        if balance < 0:
            raise ReconciliationValidationError("NEGATIVE_BALANCE", str(balance))
        execution_evidence_count = actual["event_count"]
        no_evidence = execution_evidence_count == 0
        unchanged_without_evidence = (
            no_evidence
            and actual["cash_delta_cents"] == 0
            and balance == int(checked_policy["opening_balance_cents"])
        )
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": "RECONCILED",
            "reason_codes": [],
            "advice_event_count": advice["event_count"],
            "advice_chain_head_sha256": advice["chain_head_sha256"],
            "actual_funds_event_count": actual["event_count"],
            "actual_funds_chain_head_sha256": actual["chain_head_sha256"],
            "actual_funds_cash_delta_cents": actual["cash_delta_cents"],
            "actual_funds_balance_cents": balance,
            "execution_evidence_count": execution_evidence_count,
            "actual_funds_unchanged_without_execution_evidence": unchanged_without_evidence,
            "reconciliation_difference_cents": 0,
            "external_network_used": False,
            "real_time_soak_waited": False,
        }
    except ReconciliationValidationError as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "RECONCILIATION_REJECTED",
            "reason_codes": [exc.code],
            "advice_event_count": 0,
            "advice_chain_head_sha256": GENESIS,
            "actual_funds_event_count": 0,
            "actual_funds_chain_head_sha256": GENESIS,
            "actual_funds_cash_delta_cents": 0,
            "actual_funds_balance_cents": None,
            "execution_evidence_count": 0,
            "actual_funds_unchanged_without_execution_evidence": False,
            "reconciliation_difference_cents": None,
            "external_network_used": False,
            "real_time_soak_waited": False,
        }
    result["output_sha256"] = sha256_json(result)
    return result


def deterministic_reconciliation_hash(policy: Any, advice_events: Any, actual_funds_events: Any) -> str:
    """Return the independent canonical reconciliation output hash."""

    return reconcile_ledgers(policy, advice_events, actual_funds_events)["output_sha256"]
