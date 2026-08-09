"""Deterministic synthetic settlement boundary for ABD S13/P03.

The settlement path is deliberately unable to state a real financial return.
It can replay a frozen synthetic result only after an explicit owner
confirmation record, making missing confirmation a fail-closed no-claim state.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, localcontext
from typing import Any, Mapping

from post_advice_worker import CLAIM_BOUNDARY, PostAdviceError, canonical_sha256, validate_advice_record


_SETTLEMENT_FIELDS = {
    "schema_version",
    "settlement_id",
    "advice_id",
    "settled_at",
    "outcome",
    "settled_odds",
    "closing_odds",
    "synthetic_test_only",
}


class ResultSettlementError(ValueError):
    """Raised when settlement input is ambiguous, mismatched, or unsafe."""


def _identifier(value: Any, field: str, prefix: str) -> str:
    from post_advice_worker import _identifier as checked_identifier

    return checked_identifier(value, field, prefix)


def _timestamp(value: Any, field: str) -> str:
    from post_advice_worker import _timestamp as checked_timestamp

    return checked_timestamp(value, field)


def _odds(value: Any, field: str) -> str:
    from post_advice_worker import _odds as checked_odds

    return checked_odds(value, field)


def validate_synthetic_settlement(value: Any, advice_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SETTLEMENT_FIELDS:
        raise ResultSettlementError("settlement fields are not closed")
    if value.get("schema_version") != "1.0.0" or value.get("synthetic_test_only") is not True:
        raise ResultSettlementError("settlement must be frozen synthetic input")
    if value.get("advice_id") != advice_id:
        raise ResultSettlementError("settlement must match the advice id")
    outcome = value.get("outcome")
    if outcome not in {"WON", "LOST", "VOID"}:
        raise ResultSettlementError("settlement outcome is not closed")
    try:
        normalized = {
            "schema_version": "1.0.0",
            "settlement_id": _identifier(value.get("settlement_id"), "settlement_id", "S13-P03-SETTLEMENT-"),
            "advice_id": advice_id,
            "settled_at": _timestamp(value.get("settled_at"), "settled_at"),
            "outcome": outcome,
            "settled_odds": _odds(value.get("settled_odds"), "settled_odds"),
            "closing_odds": _odds(value.get("closing_odds"), "closing_odds"),
            "synthetic_test_only": True,
        }
    except PostAdviceError as exc:
        raise ResultSettlementError(str(exc)) from exc
    return normalized


def _integer_cents(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001"), rounding=ROUND_DOWN), "f")


def settle_advice_record(advice_record: Any, settlement: Any = None) -> dict[str, Any]:
    """Settle only an explicitly confirmed synthetic record, never a real return."""

    record = validate_advice_record(advice_record)
    advice = record["advice"]
    confirmation = record["confirmation"]
    if confirmation["confirmation_state"] != "OWNER_CONFIRMED_AWAITING_RECONCILIATION":
        result = {
            "schema_version": "1.0.0",
            "result_id": "S13-P03-RESULT-" + advice["advice_id"].removeprefix("S13-P03-ADVICE-"),
            "advice_id": advice["advice_id"],
            "advice_record_sha256": record["record_sha256"],
            "result_status": "UNCONFIRMED_DO_NOT_SETTLE_OR_CLAIM_ACTUAL_RETURN",
            "settlement": None,
            "synthetic_pnl_cents": None,
            "actual_return_claimed": False,
            "actual_return_cents": None,
            "relative_closing_line_advantage": None,
            "synthetic_test_only": True,
            "claim_boundary": dict(CLAIM_BOUNDARY),
        }
        result["result_sha256"] = canonical_sha256(result)
        return result
    if settlement is None:
        result = {
            "schema_version": "1.0.0",
            "result_id": "S13-P03-RESULT-" + advice["advice_id"].removeprefix("S13-P03-ADVICE-"),
            "advice_id": advice["advice_id"],
            "advice_record_sha256": record["record_sha256"],
            "result_status": "OWNER_CONFIRMED_AWAITING_SETTLEMENT_EVIDENCE",
            "settlement": None,
            "synthetic_pnl_cents": None,
            "actual_return_claimed": False,
            "actual_return_cents": None,
            "relative_closing_line_advantage": None,
            "synthetic_test_only": True,
            "claim_boundary": dict(CLAIM_BOUNDARY),
        }
        result["result_sha256"] = canonical_sha256(result)
        return result
    normalized = validate_synthetic_settlement(settlement, advice["advice_id"])
    with localcontext() as context:
        context.prec = 50
        stake = Decimal(advice["stake_cents"])
        settled_odds = Decimal(normalized["settled_odds"])
        closing_odds = Decimal(normalized["closing_odds"])
        if normalized["outcome"] == "WON":
            synthetic_pnl_cents = _integer_cents(stake * (settled_odds - Decimal("1")))
        elif normalized["outcome"] == "LOST":
            synthetic_pnl_cents = -int(stake)
        else:
            synthetic_pnl_cents = 0
        closing_advantage = _decimal_text(Decimal(advice["recommended_odds"]) / closing_odds - Decimal("1"))
    result = {
        "schema_version": "1.0.0",
        "result_id": "S13-P03-RESULT-" + advice["advice_id"].removeprefix("S13-P03-ADVICE-"),
        "advice_id": advice["advice_id"],
        "advice_record_sha256": record["record_sha256"],
        "result_status": "SYNTHETIC_SETTLED_NOT_ACTUAL_RETURN",
        "settlement": normalized,
        "synthetic_pnl_cents": synthetic_pnl_cents,
        "actual_return_claimed": False,
        "actual_return_cents": None,
        "relative_closing_line_advantage": closing_advantage,
        "synthetic_test_only": True,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    result["result_sha256"] = canonical_sha256(result)
    return result
