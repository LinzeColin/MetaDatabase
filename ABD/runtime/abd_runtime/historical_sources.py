"""Public-safe summary of reverified, private historical source receipts."""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.0.0.1"
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"
ARCHIVE_OBSERVED_ON = "2026-08-10"


class HistoricalSourceSummaryError(ValueError):
    """Raised when a source summary would weaken the observation boundary."""


def build_historical_source_summary(runtime_state: Mapping[str, Any]) -> dict[str, Any]:
    """Render aggregate receipt facts only; it never reads raw source data at runtime."""

    if runtime_state.get("service") != "ABD" or runtime_state.get("version") != VERSION:
        raise HistoricalSourceSummaryError("runtime state identity is not accepted")
    mode = runtime_state.get("mode")
    if mode not in {"OBSERVATION_ONLY", "SHADOW_READ_ONLY"}:
        raise HistoricalSourceSummaryError("runtime mode is not observation-only")
    expected_boundary = {
        "decision": SAFE_DECISION,
        "ready": True,
        "recommendation_enabled": False,
        "order_submission_enabled": False,
        "market_or_account_connected": False,
        "gmail_or_tab_connected": False,
    }
    if {key: runtime_state.get(key) for key in expected_boundary} != expected_boundary:
        raise HistoricalSourceSummaryError("runtime state safety boundary is not accepted")
    return {
        "service": "ABD",
        "version": VERSION,
        "mode": mode,
        "surface": "PRIVATE_ARCHIVE_HISTORICAL_SOURCE_SUMMARY_ONLY",
        "archive_evidence": {
            "receipt_observed_on": ARCHIVE_OBSERVED_ON,
            "source_count": 2,
            "crosscheck_status": "PASS_STATIC_HISTORICAL_RESULT_CROSSCHECK_READY_FOR_PRIVATE_ARCHIVE",
            "calibration_status": "PASS_STATIC_DESCRIPTIVE_CALIBRATION_RESIDUAL_READY_FOR_PRIVATE_ARCHIVE",
            "matched_fixture_count": 380,
            "outcome_rows": 1140,
            "model_update_eligible": False,
        },
        "sources": [
            {
                "source_id": "FOOTBALL_DATA_E0_2025_26",
                "scope": "HISTORICAL_ODDS_AND_RESULTS_REFERENCE_ONLY",
                "real_time": False,
                "recommendation_eligible": False,
            },
            {
                "source_id": "OPENFOOTBALL_ENGLAND_PREMIER_LEAGUE_2025_26_RESULTS",
                "scope": "HISTORICAL_RESULT_CROSSCHECK_ONLY",
                "real_time": False,
                "recommendation_eligible": False,
            },
        ],
        "capability_boundary": {
            "private_raw_data_read_at_runtime": False,
            "market_or_account_connected": False,
            "gmail_or_tab_connected": False,
            "recommendation_enabled": False,
            "order_submission_enabled": False,
        },
    }
