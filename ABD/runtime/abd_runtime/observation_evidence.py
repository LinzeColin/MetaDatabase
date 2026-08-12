"""Static, non-promotional evidence payload for the ABD observation runtime."""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.0.0.1"
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"
STATIC_CALIBRATION_EVIDENCE_STATUS = "STATIC_SINGLE_SEASON_DESCRIPTION_NOT_ELIGIBLE_FOR_MODEL_UPDATE"


class ObservationEvidenceError(ValueError):
    """Raised when a runtime state would weaken the evidence surface boundary."""


def build_observation_evidence(runtime_state: Mapping[str, Any]) -> dict[str, Any]:
    """Render only fixed aggregate evidence from an already-safe runtime state."""

    if runtime_state.get("service") != "ABD" or runtime_state.get("version") != VERSION:
        raise ObservationEvidenceError("runtime state identity is not accepted")
    mode = runtime_state.get("mode")
    if mode not in {"OBSERVATION_ONLY", "SHADOW_READ_ONLY"}:
        raise ObservationEvidenceError("runtime mode is not observation-only")
    expected_boundary = {
        "decision": SAFE_DECISION,
        "ready": True,
        "recommendation_enabled": False,
        "order_submission_enabled": False,
        "market_or_account_connected": False,
        "gmail_or_tab_connected": False,
    }
    if {key: runtime_state.get(key) for key in expected_boundary} != expected_boundary:
        raise ObservationEvidenceError("runtime state safety boundary is not accepted")
    return {
        "service": "ABD",
        "version": VERSION,
        "mode": mode,
        "surface": "STATIC_OBSERVATION_EVIDENCE_ONLY",
        "static_calibration": {
            "scope": "E0_2025_26_HISTORICAL_SINGLE_SEASON",
            "fixture_count": 380,
            "outcome_rows": 1140,
            "evidence_status": STATIC_CALIBRATION_EVIDENCE_STATUS,
            "model_update_eligible": False,
        },
        "capability_boundary": {
            "market_or_account_connected": False,
            "gmail_or_tab_connected": False,
            "recommendation_enabled": False,
            "order_submission_enabled": False,
            "public_business_inbound_enabled": False,
        },
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
