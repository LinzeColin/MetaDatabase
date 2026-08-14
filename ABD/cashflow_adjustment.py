"""Deterministic, evidence-bound monthly cashflow adjustment for S12/P01.

The module deliberately supports only month-start and month-end external
cashflows.  A mid-month flow would require an independently evidenced
sub-period valuation, so it is rejected rather than approximated.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any, Mapping, Sequence


DECIMAL_PRECISION = 50
_FLOW_KEYS = {"flow_id", "direction", "amount_cents", "timing", "evidence_id", "evidence_status"}
_DIRECTIONS = {"DEPOSIT", "WITHDRAWAL"}
_TIMINGS = {"MONTH_START", "MONTH_END"}
_SYNTHETIC_EVIDENCE_STATUS = "SYNTHETIC_VERIFIED_FOR_TEST_ONLY"


class CashflowInputError(ValueError):
    """Raised when a cashflow cannot be safely included in a monthly return."""


def _strict_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise CashflowInputError("%s must be an integer" % label)
    if minimum is not None and value < minimum:
        raise CashflowInputError("%s must be >= %d" % (label, minimum))
    return value


def decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def normalize_cashflows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize externally evidenced synthetic cashflows.

    The production ledger is intentionally not read by S12/P01.  These rows
    are frozen synthetic vectors, so accepting any other evidence state would
    create an unsupported actual-return claim.
    """

    if not isinstance(rows, list):
        raise CashflowInputError("cashflows must be a list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != _FLOW_KEYS:
            raise CashflowInputError("cashflow %d has an unexpected schema" % index)
        flow_id = row.get("flow_id")
        direction = row.get("direction")
        amount_cents = _strict_int(row.get("amount_cents"), "cashflow amount_cents", minimum=1)
        timing = row.get("timing")
        evidence_id = row.get("evidence_id")
        evidence_status = row.get("evidence_status")
        if not isinstance(flow_id, str) or not flow_id or flow_id in seen_ids:
            raise CashflowInputError("cashflow ids must be unique non-empty strings")
        if direction not in _DIRECTIONS:
            raise CashflowInputError("cashflow direction is not allowed")
        if timing not in _TIMINGS:
            raise CashflowInputError("cashflow timing is not allowed")
        if not isinstance(evidence_id, str) or not evidence_id.startswith("S12-P01-SYNTHETIC-"):
            raise CashflowInputError("cashflow evidence_id is not a frozen synthetic receipt")
        if evidence_status != _SYNTHETIC_EVIDENCE_STATUS:
            raise CashflowInputError("cashflow evidence status is not frozen synthetic")
        seen_ids.add(flow_id)
        signed_amount = amount_cents if direction == "DEPOSIT" else -amount_cents
        normalized.append(
            {
                "flow_id": flow_id,
                "direction": direction,
                "amount_cents": amount_cents,
                "timing": timing,
                "evidence_id": evidence_id,
                "evidence_status": evidence_status,
                "signed_amount_cents": signed_amount,
            }
        )
    return normalized


def adjust_month(
    *,
    opening_balance_cents: int,
    closing_balance_cents: int,
    cashflows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a cashflow-adjusted monthly performance view in integer cents.

    Start-of-month flows participate in the month and are included in the
    denominator.  End-of-month flows are removed from the ending balance.
    This is exact for the only two timings this phase permits.
    """

    opening = _strict_int(opening_balance_cents, "opening_balance_cents", minimum=0)
    closing = _strict_int(closing_balance_cents, "closing_balance_cents", minimum=0)
    flows = normalize_cashflows(cashflows)
    start_net = sum(row["signed_amount_cents"] for row in flows if row["timing"] == "MONTH_START")
    end_net = sum(row["signed_amount_cents"] for row in flows if row["timing"] == "MONTH_END")
    adjusted_opening = opening + start_net
    adjusted_closing_before_end_flows = closing - end_net
    if adjusted_opening <= 0:
        raise CashflowInputError("cashflow-adjusted opening balance must remain positive")
    if adjusted_closing_before_end_flows < 0:
        raise CashflowInputError("cashflow-adjusted closing balance cannot be negative")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        gross_factor = Decimal(adjusted_closing_before_end_flows) / Decimal(adjusted_opening)
        adjusted_return = gross_factor - Decimal("1")
    return {
        "cashflows": flows,
        "month_start_external_cashflow_cents": start_net,
        "month_end_external_cashflow_cents": end_net,
        "net_external_cashflow_cents": start_net + end_net,
        "cashflow_adjusted_opening_cents": adjusted_opening,
        "cashflow_adjusted_closing_before_end_flows_cents": adjusted_closing_before_end_flows,
        "cashflow_adjusted_strategy_gain_cents": adjusted_closing_before_end_flows - adjusted_opening,
        "cashflow_adjusted_gross_factor": decimal_text(gross_factor),
        "cashflow_adjusted_return": decimal_text(adjusted_return),
    }
