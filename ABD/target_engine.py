"""S12/P01 deterministic target curve and cashflow-adjustment replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path
from typing import Any, Mapping, Sequence

from cashflow_adjustment import CashflowInputError, adjust_month


CONTRACT_ID = "AC-S12-P01"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
INITIAL_BANKROLL_CENTS = 30_000
MONTHLY_RETURN = Decimal("0.30")
MONTHLY_LOG_GROWTH = "0.26236426446749106"
DECIMAL_PRECISION = 50
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_RECORD_KEYS = {
    "month_index",
    "month_start",
    "opening_balance_cents",
    "closing_balance_cents",
    "cashflows",
    "expected_target_status",
}
_FIXTURE_KEYS = {
    "schema_version",
    "product_version",
    "contract_id",
    "fixed_clock",
    "input_mode",
    "claim_boundary",
    "initial_bankroll_cents",
    "monthly_records",
    "expected_target_vectors_sha256",
}
_CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_account_balance_read_or_written": False,
    "financial_return_verified_or_guaranteed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class TargetInputError(ValueError):
    """Raised when a target or cashflow vector violates its frozen contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise TargetInputError("%s must be an integer" % label)
    if minimum is not None and value < minimum:
        raise TargetInputError("%s must be >= %d" % (label, minimum))
    return value


def _month_ordinal(value: str) -> int:
    if not isinstance(value, str):
        raise TargetInputError("month_start must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TargetInputError("month_start is not ISO-8601") from exc
    if parsed.tzinfo is None or (parsed.day, parsed.hour, parsed.minute, parsed.second, parsed.microsecond) != (1, 0, 0, 0, 0):
        raise TargetInputError("month_start must be the first second of a calendar month with an offset")
    return parsed.year * 12 + parsed.month


def _ceil_cents(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def target_cents_for_month(month_index: int, *, initial_bankroll_cents: int = INITIAL_BANKROLL_CENTS) -> int:
    """Return B_n in cents, rounding up to prevent an optimistic target."""

    month = _strict_int(month_index, "month_index", minimum=0)
    initial = _strict_int(initial_bankroll_cents, "initial_bankroll_cents", minimum=1)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return _ceil_cents(Decimal(initial) * (Decimal("1") + MONTHLY_RETURN) ** month)


def _check_parameters(parameters: Mapping[str, Any]) -> None:
    if not isinstance(parameters, Mapping):
        raise TargetInputError("parameters must be an object")
    target = parameters.get("target_30pct")
    risk = parameters.get("risk")
    if not isinstance(target, Mapping) or not isinstance(risk, Mapping):
        raise TargetInputError("target and risk parameters are required")
    exact = (
        target.get("monthly_return") == "0.30"
        and target.get("monthly_log_growth") == MONTHLY_LOG_GROWTH
        and target.get("formula") == "B_n = 300 * 1.3^n"
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and risk.get("chase_loss_prohibited") is True
        and risk.get("target_shortfall_may_relax_gate") is False
    )
    if not exact:
        raise TargetInputError("frozen target or no-chase-loss parameters do not match")


def validate_fixture(fixture: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
    if not isinstance(fixture, Mapping) or set(fixture) != _FIXTURE_KEYS:
        raise TargetInputError("fixture has an unexpected schema")
    _check_parameters(parameters)
    if (
        fixture.get("schema_version") != "1.0.0"
        or fixture.get("product_version") != PRODUCT_VERSION
        or fixture.get("contract_id") != CONTRACT_ID
        or fixture.get("fixed_clock") != FIXED_CLOCK
        or fixture.get("input_mode") != INPUT_MODE
        or fixture.get("claim_boundary") != _CLAIM_BOUNDARY
        or fixture.get("initial_bankroll_cents") != INITIAL_BANKROLL_CENTS
    ):
        raise TargetInputError("fixture is not bound to the S12/P01 frozen boundary")
    expected_hash = fixture.get("expected_target_vectors_sha256")
    if not isinstance(expected_hash, str) or not _HASH_RE.fullmatch(expected_hash):
        raise TargetInputError("fixture target vector hash is invalid")
    records = fixture.get("monthly_records")
    if not isinstance(records, list) or len(records) < 4:
        raise TargetInputError("fixture must contain at least four monthly records")
    previous_ordinal: int | None = None
    previous_closing: int | None = None
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or set(record) != _RECORD_KEYS:
            raise TargetInputError("monthly record %d has an unexpected schema" % index)
        if record.get("month_index") != index:
            raise TargetInputError("monthly records must start at index zero and be contiguous")
        ordinal = _month_ordinal(record.get("month_start"))
        if previous_ordinal is not None and ordinal != previous_ordinal + 1:
            raise TargetInputError("monthly records must be consecutive calendar months")
        opening = _strict_int(record.get("opening_balance_cents"), "opening_balance_cents", minimum=0)
        _strict_int(record.get("closing_balance_cents"), "closing_balance_cents", minimum=0)
        if index == 0 and opening != INITIAL_BANKROLL_CENTS:
            raise TargetInputError("first monthly opening must equal the frozen A$300 bankroll")
        if previous_closing is not None and opening != previous_closing:
            raise TargetInputError("monthly actual balances must be continuous")
        if record.get("expected_target_status") not in {"TARGET_ON_TRACK", "TARGET_SHORTFALL_REPORT_ONLY"}:
            raise TargetInputError("monthly target status is invalid")
        try:
            adjust_month(
                opening_balance_cents=opening,
                closing_balance_cents=record["closing_balance_cents"],
                cashflows=record["cashflows"],
            )
        except (CashflowInputError, KeyError, TypeError) as exc:
            raise TargetInputError("monthly cashflows are invalid") from exc
        previous_ordinal = ordinal
        previous_closing = record["closing_balance_cents"]


def build_target_vectors(fixture: Mapping[str, Any], parameters: Mapping[str, Any]) -> dict[str, Any]:
    validate_fixture(fixture, parameters)
    rows: list[dict[str, Any]] = []
    adjusted_target_start = INITIAL_BANKROLL_CENTS
    for record in fixture["monthly_records"]:
        month_index = record["month_index"]
        adjustment = adjust_month(
            opening_balance_cents=record["opening_balance_cents"],
            closing_balance_cents=record["closing_balance_cents"],
            cashflows=record["cashflows"],
        )
        target_after_start_cashflow = adjusted_target_start + adjustment["month_start_external_cashflow_cents"]
        if target_after_start_cashflow <= 0:
            raise TargetInputError("cashflow-adjusted target start must remain positive")
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            target_before_end_cashflow = _ceil_cents(Decimal(target_after_start_cashflow) * (Decimal("1") + MONTHLY_RETURN))
        adjusted_target_end = target_before_end_cashflow + adjustment["month_end_external_cashflow_cents"]
        if adjusted_target_end <= 0:
            raise TargetInputError("cashflow-adjusted target end must remain positive")
        target_gap = record["closing_balance_cents"] - adjusted_target_end
        target_status = "TARGET_ON_TRACK" if target_gap >= 0 else "TARGET_SHORTFALL_REPORT_ONLY"
        if target_status != record["expected_target_status"]:
            raise TargetInputError("frozen target status disagrees with the deterministic target gap")
        rows.append(
            {
                "month_index": month_index,
                "month_start": record["month_start"],
                "baseline_target_start_cents": target_cents_for_month(month_index),
                "baseline_target_end_cents": target_cents_for_month(month_index + 1),
                "cashflow_adjusted_target_start_cents": adjusted_target_start,
                "cashflow_adjusted_target_after_month_start_cashflow_cents": target_after_start_cashflow,
                "cashflow_adjusted_target_before_month_end_cashflow_cents": target_before_end_cashflow,
                "cashflow_adjusted_target_end_cents": adjusted_target_end,
                "actual_opening_balance_cents": record["opening_balance_cents"],
                "actual_closing_balance_cents": record["closing_balance_cents"],
                **adjustment,
                "target_gap_cents": target_gap,
                "target_status": target_status,
                "shortfall_action": "REPORT_ONLY_NO_GATE_RELAXATION",
            }
        )
        adjusted_target_start = adjusted_target_end
    shortfall_count = sum(row["target_status"] == "TARGET_SHORTFALL_REPORT_ONLY" for row in rows)
    return {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S12-P01-03",
        "contract_id": CONTRACT_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "claim_boundary": fixture["claim_boundary"],
        "target_curve": {
            "initial_bankroll_cents": INITIAL_BANKROLL_CENTS,
            "monthly_return": "0.30",
            "monthly_log_growth": MONTHLY_LOG_GROWTH,
            "formula": "B_n = 300 * 1.3^n",
            "target_rounding": "UP_TO_INTEGER_CENT_FOR_CONSERVATIVE_TARGET",
        },
        "monthly_rows": rows,
        "summary": {
            "months": len(rows),
            "target_on_track_count": len(rows) - shortfall_count,
            "target_shortfall_count": shortfall_count,
            "target_shortfall_may_relax_gate": False,
            "chase_loss_prohibited": True,
            "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
            "actual_execution_or_account_evidence_claimed": False,
        },
        "decision": "TARGET_CURVE_REPLAY_READY_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED",
        "next": "S12/P02_READY_NOT_STARTED",
    }


def build_artifacts(fixture: Mapping[str, Any], parameters: Mapping[str, Any]) -> dict[str, Any]:
    vectors = build_target_vectors(fixture, parameters)
    actual_hash = artifact_sha256(vectors)
    if actual_hash != fixture["expected_target_vectors_sha256"]:
        raise TargetInputError("target vector replay hash does not match the frozen fixture")
    return vectors


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABD S12/P01 target curve replay")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    parameters = json.loads(Path(args.parameters).read_text(encoding="utf-8"))
    vectors = build_artifacts(fixture, parameters)
    _atomic_write(Path(args.output), canonical_json_bytes(vectors))
    print(json.dumps({"status": "PASS", "target_vectors_sha256": artifact_sha256(vectors)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
