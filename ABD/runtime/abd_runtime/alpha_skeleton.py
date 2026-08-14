"""Synthetic, read-only S19/P01 software-alpha surface for ABD.

This module is deliberately independent from the frozen acceptance artefacts.
It renders the same constrained lifecycle in the already-safe observation
runtime without opening any market, account, mailbox, TAB, recommendation, or
order capability.
"""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.0.0.1"
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"


class AlphaSkeletonError(ValueError):
    """Raised when the observation boundary is not intact."""


def build_alpha_skeleton(runtime_state: Mapping[str, Any]) -> dict[str, Any]:
    """Render one deterministic synthetic lifecycle from a safe runtime state."""

    required_state = {
        "service": "ABD",
        "version": VERSION,
        "decision": SAFE_DECISION,
        "ready": True,
        "recommendation_enabled": False,
        "order_submission_enabled": False,
        "market_or_account_connected": False,
        "gmail_or_tab_connected": False,
    }
    if {key: runtime_state.get(key) for key in required_state} != required_state:
        raise AlphaSkeletonError("runtime state cannot expose software alpha")
    if runtime_state.get("mode") not in {"OBSERVATION_ONLY", "SHADOW_READ_ONLY"}:
        raise AlphaSkeletonError("runtime mode cannot expose software alpha")

    return {
        "service": "ABD",
        "version": VERSION,
        "surface": "S19_P01_SYNTHETIC_SOFTWARE_ALPHA",
        "runtime_surface_status": "ACTIVE_READ_ONLY_OBSERVATION_SURFACE",
        "frozen_acceptance_contract_status": "LOCAL_ONLY_NOT_DEPLOYED",
        "mode": runtime_state["mode"],
        "contract": {
            "id": "AC-S19-P01",
            "scope": "ONE_FROZEN_SYNTHETIC_MARKET_LOCAL_ONLY",
        },
        "market": {
            "market_id": "SYNTHETIC-MARKET-S19-P01",
            "source_kind": "FROZEN_LOCAL_FIXTURE",
            "evidence_tier": "E0_SYNTHETIC_TEST_ONLY",
        },
        "closed_loop": [
            {"step": "DISCOVER", "status": "LOCAL_SYNTHETIC_DISCOVERY_ONLY"},
            {"step": "ADVICE", "status": "ADVICE_PROJECTION_NO_ORDER"},
            {"step": "INVALIDATE", "status": "INVALIDATED_TO_NO_RECOMMENDATION"},
            {"step": "SYNTHETIC_RESULT", "status": "SYNTHETIC_RESULT_NOT_EMPIRICAL"},
            {"step": "REPLAY", "status": "DETERMINISTIC_REPLAY_READY"},
            {"step": "LOCAL_MAIL_EVIDENCE", "status": "LOCAL_EVIDENCE_PROJECTION_NOT_SENT"},
            {"step": "RECOVERY", "status": "DERIVED_STATE_RECOVERY_READY"},
        ],
        "capability_boundary": {
            "recommendation_enabled": False,
            "order_submission_enabled": False,
            "market_or_account_connected": False,
            "gmail_or_tab_connected": False,
            "actual_funds_used": False,
            "actual_ledger_read_or_written": False,
            "external_runtime_accessed": False,
            "email_sent": False,
        },
        "decision": SAFE_DECISION,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
