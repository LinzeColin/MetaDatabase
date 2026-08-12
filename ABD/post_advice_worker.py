"""Deterministic post-advice record boundary for ABD S13/P03.

This module records a frozen recommendation and an optional owner confirmation.
It does not contact a platform, read an account, submit an order, or infer that
an order, return, or settlement is real.  A missing confirmation stays an
advice-only record by construction.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


VERSION = "0.0.0.1"
CLAIM_BOUNDARY = {
    "actual_market_or_odds_observed": False,
    "actual_order_execution_claimed": False,
    "external_network_accessed": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_account_accessed": False,
    "real_time_soak_waited": False,
    "system_order_confirmation_enabled": False,
}
_ADVICE_FIELDS = {
    "schema_version",
    "advice_id",
    "advice_issued_at",
    "ticket_id",
    "provider_id",
    "event_id",
    "market_id",
    "selection_id",
    "recommended_odds",
    "minimum_odds",
    "stake_cents",
    "synthetic_test_only",
}
_CONFIRMATION_FIELDS = {
    "schema_version",
    "confirmation_id",
    "advice_id",
    "confirmed_at",
    "confirmation_mode",
    "synthetic_test_only",
}


class PostAdviceError(ValueError):
    """Raised when a post-advice record is ambiguous or unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _identifier(value: Any, field: str, prefix: str) -> str:
    if not isinstance(value, str) or re.fullmatch(prefix + r"[A-Z0-9-]{3,96}", value) is None:
        raise PostAdviceError("%s is not a closed identifier" % field)
    return value


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PostAdviceError("%s must be an ISO-8601 timestamp" % field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PostAdviceError("%s is invalid" % field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PostAdviceError("%s must include a timezone" % field)
    return value


def _odds(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[1-9]\d*\.\d{6}", value) is None:
        raise PostAdviceError("%s must use six-place decimal text" % field)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PostAdviceError("%s is not decimal" % field) from exc
    if parsed <= Decimal("1.000000"):
        raise PostAdviceError("%s must be greater than one" % field)
    return value


def _stake_cents(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise PostAdviceError("stake_cents must be a positive integer")
    return value


def validate_advice(value: Any) -> dict[str, Any]:
    """Validate a frozen synthetic advice payload without creating side effects."""

    if _contains_float(value):
        raise PostAdviceError("advice must not contain binary floats")
    if not isinstance(value, Mapping) or set(value) != _ADVICE_FIELDS:
        raise PostAdviceError("advice fields are not closed")
    if value.get("schema_version") != "1.0.0" or value.get("synthetic_test_only") is not True:
        raise PostAdviceError("advice must be frozen synthetic input")
    normalized = {
        "schema_version": "1.0.0",
        "advice_id": _identifier(value.get("advice_id"), "advice_id", "S13-P03-ADVICE-"),
        "advice_issued_at": _timestamp(value.get("advice_issued_at"), "advice_issued_at"),
        "ticket_id": _identifier(value.get("ticket_id"), "ticket_id", "S13-P02-TICKET-"),
        "provider_id": _identifier(value.get("provider_id"), "provider_id", "SYNTHETIC_PROVIDER_"),
        "event_id": _identifier(value.get("event_id"), "event_id", "EVENT-SYNTH-"),
        "market_id": _identifier(value.get("market_id"), "market_id", "MARKET-SYNTH-"),
        "selection_id": _identifier(value.get("selection_id"), "selection_id", "SELECTION-SYNTH-"),
        "recommended_odds": _odds(value.get("recommended_odds"), "recommended_odds"),
        "minimum_odds": _odds(value.get("minimum_odds"), "minimum_odds"),
        "stake_cents": _stake_cents(value.get("stake_cents")),
        "synthetic_test_only": True,
    }
    with localcontext() as context:
        context.prec = 50
        if Decimal(normalized["recommended_odds"]) < Decimal(normalized["minimum_odds"]):
            raise PostAdviceError("recommended odds cannot be below the minimum")
    return normalized


def validate_optional_confirmation(value: Any, advice_id: str) -> dict[str, Any]:
    """Normalize explicit owner confirmation without treating it as account proof."""

    if value is None:
        return {
            "confirmation_state": "NOT_CONFIRMED",
            "confirmation_id": None,
            "confirmed_at": None,
            "confirmation_mode": None,
            "synthetic_test_only": True,
        }
    if _contains_float(value):
        raise PostAdviceError("confirmation must not contain binary floats")
    if not isinstance(value, Mapping) or set(value) != _CONFIRMATION_FIELDS:
        raise PostAdviceError("confirmation fields are not closed")
    if value.get("schema_version") != "1.0.0" or value.get("synthetic_test_only") is not True:
        raise PostAdviceError("confirmation must be frozen synthetic input")
    if value.get("advice_id") != advice_id:
        raise PostAdviceError("confirmation must match the advice id")
    if value.get("confirmation_mode") != "OWNER_EXPLICIT_CONFIRMATION":
        raise PostAdviceError("only an explicit owner confirmation is accepted")
    return {
        "confirmation_state": "OWNER_CONFIRMED_AWAITING_RECONCILIATION",
        "confirmation_id": _identifier(value.get("confirmation_id"), "confirmation_id", "S13-P03-CONFIRMATION-"),
        "confirmed_at": _timestamp(value.get("confirmed_at"), "confirmed_at"),
        "confirmation_mode": "OWNER_EXPLICIT_CONFIRMATION",
        "synthetic_test_only": True,
    }


def make_advice_record(advice: Any, confirmation: Any = None) -> dict[str, Any]:
    """Create a deterministic advice-only or owner-confirmed-pending record.

    Even the latter is not an actual-account execution record and carries no
    financial-return amount.  Settlement requires separately recorded evidence.
    """

    normalized_advice = validate_advice(advice)
    normalized_confirmation = validate_optional_confirmation(confirmation, normalized_advice["advice_id"])
    confirmed = normalized_confirmation["confirmation_state"] == "OWNER_CONFIRMED_AWAITING_RECONCILIATION"
    record = {
        "schema_version": "1.0.0",
        "record_id": "S13-P03-RECORD-" + normalized_advice["advice_id"].removeprefix("S13-P03-ADVICE-"),
        "advice": normalized_advice,
        "confirmation": normalized_confirmation,
        "advice_status": "ADVICE_RECORDED_OWNER_CONFIRMATION_PENDING" if not confirmed else "ADVICE_RECORDED_OWNER_CONFIRMED_PENDING_RECONCILIATION",
        "actual_execution_status": "UNCONFIRMED_NO_ACTUAL_EXECUTION_CLAIM" if not confirmed else "OWNER_CONFIRMED_NOT_ACCOUNT_RECONCILED",
        "actual_return_claimed": False,
        "actual_return_cents": None,
        "synthetic_test_only": True,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    record["record_sha256"] = canonical_sha256(record)
    return record


def validate_advice_record(value: Any) -> dict[str, Any]:
    """Verify the record hash and the non-claim boundary before settlement."""

    expected = {
        "schema_version",
        "record_id",
        "advice",
        "confirmation",
        "advice_status",
        "actual_execution_status",
        "actual_return_claimed",
        "actual_return_cents",
        "synthetic_test_only",
        "claim_boundary",
        "record_sha256",
    }
    if _contains_float(value) or not isinstance(value, Mapping) or set(value) != expected:
        raise PostAdviceError("advice record fields are not closed")
    advice = validate_advice(value.get("advice"))
    confirmation_source = value.get("confirmation")
    if not isinstance(confirmation_source, Mapping):
        raise PostAdviceError("advice record confirmation is invalid")
    if confirmation_source.get("confirmation_state") == "NOT_CONFIRMED":
        confirmation: Any = None
    elif confirmation_source.get("confirmation_state") == "OWNER_CONFIRMED_AWAITING_RECONCILIATION":
        confirmation = {
            "schema_version": "1.0.0",
            "confirmation_id": confirmation_source.get("confirmation_id"),
            "advice_id": advice["advice_id"],
            "confirmed_at": confirmation_source.get("confirmed_at"),
            "confirmation_mode": confirmation_source.get("confirmation_mode"),
            "synthetic_test_only": confirmation_source.get("synthetic_test_only"),
        }
    else:
        raise PostAdviceError("advice record confirmation state is invalid")
    expected_record = make_advice_record(advice, confirmation)
    if dict(value) != expected_record:
        raise PostAdviceError("advice record is not reproducible")
    return expected_record
