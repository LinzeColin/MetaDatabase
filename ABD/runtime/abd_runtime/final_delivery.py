"""Read-only S19/P04 final-delivery status surface for ABD.

It separates the frozen local final-delivery contract from the active
observation runtime.  The surface never turns a deployed status page into a
claim of final acceptance, production trading, realised returns, or GA.
"""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.0.0.1"
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"


class FinalDeliveryRuntimeError(ValueError):
    """Raised when the observation boundary is not intact."""


def build_final_delivery(runtime_state: Mapping[str, Any]) -> dict[str, Any]:
    """Render the frozen P04 final-delivery status from a safe runtime state."""

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
        raise FinalDeliveryRuntimeError("runtime state cannot expose final delivery")
    if runtime_state.get("mode") not in {"OBSERVATION_ONLY", "SHADOW_READ_ONLY"}:
        raise FinalDeliveryRuntimeError("runtime mode cannot expose final delivery")

    return {
        "service": "ABD",
        "version": VERSION,
        "surface": "S19_P04_FINAL_DELIVERY_STATUS",
        "runtime_surface_status": "ACTIVE_READ_ONLY_OBSERVATION_SURFACE",
        "frozen_acceptance_contract_status": "LOCAL_FINAL_DELIVERY_COMPLETE_STAGE_REVIEW_REQUIRED",
        "mode": runtime_state["mode"],
        "contract": {
            "id": "AC-S19-P04",
            "scope": "FROZEN_OFFLINE_FINAL_DELIVERY_CONTRACT_ONLY",
        },
        "local_final_delivery": {
            "status": "PASS_LOCAL_FINAL_ACCEPTANCE_STAGE_REVIEW_REQUIRED",
            "version_and_contract_status": "UNAMBIGUOUS_FROZEN_LOCAL_CONTRACT",
            "non_secret_handoff_bundle_defined": True,
            "stage_review_required": True,
            "stage_review_completed": False,
            "github_stage_upload_status": "PENDING_STAGE_REVIEW",
        },
        "financial_boundary": {
            "initial_bankroll_reference_aud": "300.00",
            "incremental_cash_budget_aud": "0.00",
            "monthly_target": "30%",
            "target_formula": "B_n=300*1.3^n",
            "target_status": "UNVERIFIED_NOT_GUARANTEED",
        },
        "runtime_and_return_boundary": {
            "actual_execution_evidence_status": "NO_EMPIRICAL_EXECUTION_EVIDENCE",
            "actual_record_count": 0,
            "verified_days": 0,
            "actual_ga_status": "BLOCKED_NO_EMPIRICAL_EXECUTION_OR_MODEL_EVIDENCE",
            "actual_reconciliation_status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
            "return_or_roi_verified": False,
            "synthetic_or_local_control_promoted_to_empirical": False,
        },
        "adverse_perturbation": {
            "probability_delta": "-0.0001",
            "odds_tick_delta": -1,
            "result": "LOCAL_FINAL_DELIVERY_GATE_STABLE",
        },
        "release_boundary": {
            "recommendation_generation_allowed": False,
            "order_submission_allowed": False,
            "production_trading_allowed": False,
            "owner_final_order_only": True,
            "target_shortfall_may_relax_gate": False,
        },
        "capability_boundary": {
            "actual_funds_used": False,
            "actual_ledger_read_or_written": False,
            "market_or_account_connected": False,
            "gmail_or_tab_connected": False,
            "external_runtime_accessed": False,
            "recommendation_enabled": False,
            "order_submission_enabled": False,
            "email_sent": False,
        },
        "decision": SAFE_DECISION,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
