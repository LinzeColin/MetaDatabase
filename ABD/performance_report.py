"""Fail-closed performance report for the frozen ABD S13/P03 replay.

Advice quality and synthetic closing-line observations are reported separately
from actual funds.  No report emitted here can turn advice, owner indication,
or synthetic settlement into a real financial-return assertion.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, localcontext
from typing import Any, Mapping, Sequence

from post_advice_worker import CLAIM_BOUNDARY, canonical_sha256, validate_advice_record


class PerformanceReportError(ValueError):
    """Raised when report inputs are incomplete, duplicated, or unsafe."""


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001"), rounding=ROUND_DOWN), "f")


def _validate_result(value: Any, advice_records: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    expected = {
        "schema_version",
        "result_id",
        "advice_id",
        "advice_record_sha256",
        "result_status",
        "settlement",
        "synthetic_pnl_cents",
        "actual_return_claimed",
        "actual_return_cents",
        "relative_closing_line_advantage",
        "synthetic_test_only",
        "claim_boundary",
        "result_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PerformanceReportError("result fields are not closed")
    advice_id = value.get("advice_id")
    if advice_id not in advice_records:
        raise PerformanceReportError("result references an unknown advice record")
    if value.get("advice_record_sha256") != advice_records[advice_id].get("record_sha256"):
        raise PerformanceReportError("result does not bind to its advice record")
    if value.get("schema_version") != "1.0.0" or value.get("synthetic_test_only") is not True:
        raise PerformanceReportError("result is not frozen synthetic input")
    if value.get("claim_boundary") != CLAIM_BOUNDARY:
        raise PerformanceReportError("result claim boundary differs")
    if value.get("actual_return_claimed") is not False or value.get("actual_return_cents") is not None:
        raise PerformanceReportError("result must not claim an actual return")
    hash_input = {key: item for key, item in value.items() if key != "result_sha256"}
    if value.get("result_sha256") != canonical_sha256(hash_input):
        raise PerformanceReportError("result hash is not reproducible")
    return value


def build_performance_report(advice_records: Sequence[Any], results: Sequence[Any]) -> dict[str, Any]:
    """Summarize synthetic evidence without making a real-funds assertion."""

    records: dict[str, Mapping[str, Any]] = {}
    for item in advice_records:
        record = validate_advice_record(item)
        advice_id = record["advice"]["advice_id"]
        if advice_id in records:
            raise PerformanceReportError("advice records must be unique")
        records[advice_id] = record
    if not records:
        raise PerformanceReportError("at least one advice record is required")

    normalized_results: list[Mapping[str, Any]] = []
    seen_result_ids: set[str] = set()
    for item in results:
        result = _validate_result(item, records)
        if result["result_id"] in seen_result_ids:
            raise PerformanceReportError("result ids must be unique")
        seen_result_ids.add(result["result_id"])
        normalized_results.append(result)
    if {item["advice_id"] for item in normalized_results} != set(records):
        raise PerformanceReportError("every advice record must have one result state")

    unconfirmed_count = sum(record["confirmation"]["confirmation_state"] == "NOT_CONFIRMED" for record in records.values())
    confirmed_count = len(records) - unconfirmed_count
    settled = [item for item in normalized_results if item["result_status"] == "SYNTHETIC_SETTLED_NOT_ACTUAL_RETURN"]
    synthetic_pnl_cents = sum(int(item["synthetic_pnl_cents"]) for item in settled)
    clv_values = [Decimal(str(item["relative_closing_line_advantage"])) for item in settled]
    with localcontext() as context:
        context.prec = 50
        mean_clv = _decimal_text(sum(clv_values, Decimal("0")) / Decimal(len(clv_values))) if clv_values else None

    if unconfirmed_count:
        actual_return_status = "DO_NOT_CLAIM_ACTUAL_RETURN_UNCONFIRMED_ADVICE"
    elif settled:
        actual_return_status = "SYNTHETIC_ONLY_NOT_REAL_RETURN"
    else:
        actual_return_status = "DO_NOT_CLAIM_ACTUAL_RETURN_NO_SETTLEMENT_EVIDENCE"
    report = {
        "schema_version": "1.0.0",
        "report_id": "S13-P03-FROZEN-PERFORMANCE-REPORT",
        "advice_count": len(records),
        "owner_confirmed_count": confirmed_count,
        "unconfirmed_advice_count": unconfirmed_count,
        "synthetic_settled_count": len(settled),
        "synthetic_pnl_cents": synthetic_pnl_cents,
        "actual_return_status": actual_return_status,
        "actual_return_claimed": False,
        "actual_return_cents": None,
        "relative_closing_line_observation_count": len(clv_values),
        "mean_relative_closing_line_advantage": mean_clv,
        "review_status": "ADVICE_AND_SYNTHETIC_EVIDENCE_ONLY_REAL_FUNDS_REQUIRE_SEPARATE_VERIFIABLE_EVIDENCE",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "synthetic_test_only": True,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    report["report_sha256"] = canonical_sha256(report)
    return report
