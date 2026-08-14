"""Synthetic, read-only S19/P02 Shadow Beta control surface for ABD.

The runtime reports the frozen quality-gate projection only.  It never treats
the projection as real-time shadow evidence and never enables Model Beta,
recommendations, orders, funding, market, account, TAB, or mailbox access.
"""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.0.0.1"
SAFE_DECISION = "NO_RECOMMENDATION_NO_ORDER"


class ShadowBetaRuntimeError(ValueError):
    """Raised when the observation boundary is not intact."""


def build_shadow_beta(runtime_state: Mapping[str, Any]) -> dict[str, Any]:
    """Render the fixed S19/P02 gate projection from a safe runtime state."""

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
        raise ShadowBetaRuntimeError("runtime state cannot expose Shadow Beta")
    if runtime_state.get("mode") not in {"OBSERVATION_ONLY", "SHADOW_READ_ONLY"}:
        raise ShadowBetaRuntimeError("runtime mode cannot expose Shadow Beta")

    return {
        "service": "ABD",
        "version": VERSION,
        "surface": "S19_P02_SYNTHETIC_SHADOW_BETA",
        "runtime_surface_status": "ACTIVE_READ_ONLY_OBSERVATION_SURFACE",
        "frozen_acceptance_contract_status": "LOCAL_SHADOW_GATE_CONTROL_ONLY_EMPIRICAL_RUNTIME_REQUIRED",
        "mode": runtime_state["mode"],
        "contract": {
            "id": "AC-S19-P02",
            "scope": "FROZEN_SYNTHETIC_METRIC_GATE_REPLAY_ONLY",
        },
        "quality_gates": [
            {"gate_id": "CALIBRATION", "passed": True, "evidence": "FROZEN_SYNTHETIC_METRIC"},
            {"gate_id": "NET_GROWTH", "passed": True, "evidence": "FROZEN_SYNTHETIC_METRIC"},
            {"gate_id": "FRESHNESS", "passed": True, "evidence": "FROZEN_SYNTHETIC_METRIC"},
            {"gate_id": "CAPACITY", "passed": True, "evidence": "FROZEN_SYNTHETIC_ASSERTION_NOT_REAL_PROVIDER_CAPACITY"},
            {"gate_id": "DRIFT", "passed": True, "evidence": "FROZEN_SYNTHETIC_METRIC"},
        ],
        "adverse_perturbation": {
            "probability_delta": "-0.0001",
            "odds_tick_delta": -1,
            "result": "LOCAL_SYNTHETIC_GATES_PASS",
        },
        "synthetic_window": {
            "logical_shadow_days": 90,
            "logical_qualified_signals": 1000,
            "evidence_status": "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL",
            "counts_may_substitute_for_empirical_evidence": False,
        },
        "empirical_observation": {
            "observed_realtime_shadow_days": 0,
            "observed_realtime_qualified_signals": 0,
            "model_beta_required_days": 60,
            "model_beta_required_qualified_signals": 500,
            "signed_empirical_evidence_required": True,
        },
        "model_boundary": {
            "kelly_fraction": "0.20",
            "residual_weight_cap": "0.35",
            "target_shortfall_may_relax_gate": False,
            "unstable_action": "NO_RECOMMENDATION",
        },
        "model_beta": {
            "status": "BLOCKED_NO_EMPIRICAL_REALTIME_SHADOW_EVIDENCE",
            "eligible": False,
            "activation_allowed": False,
            "recommendation_generation_allowed": False,
            "order_submission_allowed": False,
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
