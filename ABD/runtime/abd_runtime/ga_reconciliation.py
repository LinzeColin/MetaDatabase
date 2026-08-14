"""Synthetic, read-only S19/P03 GA reconciliation control surface for ABD.

The endpoint exposes the frozen zero-row local control without presenting it
as an actual ledger, an actual reconciliation, a GA release, or a return.
"""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.0.0.1"
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"


class GAReconciliationRuntimeError(ValueError):
    """Raised when the observation boundary is not intact."""


def build_ga_reconciliation(runtime_state: Mapping[str, Any]) -> dict[str, Any]:
    """Render the fixed S19/P03 reconciliation control from a safe state."""

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
        raise GAReconciliationRuntimeError("runtime state cannot expose GA control")
    if runtime_state.get("mode") not in {"OBSERVATION_ONLY", "SHADOW_READ_ONLY"}:
        raise GAReconciliationRuntimeError("runtime mode cannot expose GA control")

    return {
        "service": "ABD",
        "version": VERSION,
        "surface": "S19_P03_SYNTHETIC_GA_RECONCILIATION",
        "runtime_surface_status": "ACTIVE_READ_ONLY_OBSERVATION_SURFACE",
        "frozen_acceptance_contract_status": "FROZEN_ZERO_ROW_LOCAL_CONTROL_NOT_AN_ACTUAL_GA_RELEASE",
        "mode": runtime_state["mode"],
        "contract": {
            "id": "AC-S19-P03",
            "scope": "FROZEN_ZERO_ROW_LOCAL_CONTROL_NOT_AN_ACTUAL_GA_RELEASE",
        },
        "local_control": {
            "local_ledger_row_count": 0,
            "local_reconciliation_difference_cents": 0,
            "local_evidence_artifact_complete": True,
            "stop_conditions_triggered": False,
            "scope": "FROZEN_ZERO_ROW_SCHEMA_AND_RECONCILIATION_CONTROL_ONLY",
        },
        "adverse_perturbation": {
            "probability_delta": "-0.0001",
            "odds_tick_delta": -1,
            "result": "LOCAL_ZERO_ROW_CONTROL_STABLE",
        },
        "actual_execution_observation": {
            "evidence_status": "NO_EMPIRICAL_EXECUTION_EVIDENCE",
            "actual_execution_evidence_complete": False,
            "actual_record_count": 0,
            "verified_days": 0,
            "actual_reconciliation_difference_cents": None,
            "actual_reconciliation_difference_is_known": False,
            "actual_reconciliation_status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
            "unresolved_reconciliation_differences": 0,
            "zero_difference_requirement_status": "NOT_EVALUABLE_NO_ACTUAL_EXECUTION_EVIDENCE",
            "synthetic_or_local_control_may_substitute_for_actual": False,
        },
        "required_before_actual_ga": {
            "actual_record_count": 200,
            "verified_days": 90,
            "independent_qualified_signals": 1000,
            "signed_execution_evidence_required": True,
            "actual_reconciliation_difference_cents_required": 0,
            "model_gate_must_be_independently_eligible": True,
        },
        "model_boundary": {
            "stage_schema": "GA",
            "kelly_fraction": "0.25",
            "residual_weight_cap": "0.50",
            "target_shortfall_may_relax_gate": False,
            "owner_final_order_only": True,
            "order_submission_module_present": False,
        },
        "model_gate": {
            "model_beta_status": "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE",
            "model_activation_allowed": False,
            "recommendation_generation_allowed": False,
            "order_submission_allowed": False,
            "ga_activation_allowed": False,
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
