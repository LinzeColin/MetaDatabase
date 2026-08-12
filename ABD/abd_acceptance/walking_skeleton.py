"""Offline, fail-closed walking skeleton for ABD S19/P01.

This module deliberately models one *frozen synthetic* market.  It proves the
local lifecycle wiring only; it does not connect to a market, a mailbox, a
wallet, an order endpoint, or infrastructure.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Sequence


FIXED_CLOCK = "2026-08-10T06:00:00+10:00"
FEATURE_FLAG_ID = "walking_skeleton:s19_p01_local_only"
LIFECYCLE_STEPS = (
    "DISCOVER",
    "ADVICE",
    "INVALIDATE",
    "SYNTHETIC_RESULT",
    "REPLAY",
    "LOCAL_MAIL_EVIDENCE",
    "RECOVERY",
)
SAFE_FUND_FACTS = {
    "money_storage": "INTEGER_CENTS",
    "frozen_bankroll_reference_aud": "300.00",
    "actual_fund_fact_mutation_allowed": False,
    "actual_ledger_mutation_allowed": False,
}
SAFE_RISK_GATE = {
    "kelly_fraction_alpha": "0.00",
    "kelly_fraction_beta": "0.20",
    "kelly_fraction_ga": "0.25",
    "total_open_exposure_cap": "0.150",
    "target_shortfall_may_relax_gate": False,
    "unstable_action": "NO_RECOMMENDATION",
}
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "market_or_account_runtime_accessed": False,
    "actual_fund_facts_read_or_written": False,
    "actual_ledger_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "gmail_account_or_api_accessed": False,
    "gmail_message_sent": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
    "incremental_cash_spent_aud": "0.00",
    "owner_final_order_only": True,
}


class WalkingSkeletonInputError(ValueError):
    """Raised for malformed inputs that cannot be safely interpreted."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def artifact_sha256(value: Mapping[str, Any], field: str) -> str:
    unsigned = dict(value)
    unsigned.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WalkingSkeletonInputError("%s must be an object" % name)
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise WalkingSkeletonInputError("%s must be a boolean" % name)
    return value


def _failure_codes(payload: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload["fund_facts_snapshot"] != SAFE_FUND_FACTS:
        failures.append("IMMUTABLE_FUND_FACTS_CHANGED")
    if payload["risk_gate_snapshot"] != SAFE_RISK_GATE:
        failures.append("IMMUTABLE_RISK_GATE_CHANGED_OR_RELAXED")
    requested = {
        "requested_external_execution": "EXTERNAL_RUNTIME_REQUESTED",
        "requested_actual_order": "ACTUAL_ORDER_REQUESTED",
        "requested_real_fund_mutation": "REAL_FUND_MUTATION_REQUESTED",
        "requested_real_mail_send": "REAL_MAIL_SEND_REQUESTED",
        "requested_production_deploy": "PRODUCTION_DEPLOY_REQUESTED",
    }
    for key, code in requested.items():
        if payload[key]:
            failures.append(code)
    return failures


def validate_cycle_input(value: Any) -> Mapping[str, Any]:
    """Validate a production-shaped local fixture without interpreting unsafe data."""

    if not isinstance(value, Mapping) or _contains_float(value):
        raise WalkingSkeletonInputError("cycle input must be a non-float object")
    required = {
        "schema_version",
        "fixed_clock",
        "cycle_id",
        "market",
        "lifecycle_steps",
        "probability_delta",
        "odds_tick_delta",
        "fund_facts_snapshot",
        "risk_gate_snapshot",
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    }
    if set(value) != required:
        raise WalkingSkeletonInputError("cycle input keys do not match the frozen schema")
    if value["schema_version"] != "1.0.0" or value["fixed_clock"] != FIXED_CLOCK:
        raise WalkingSkeletonInputError("schema version or fixed clock changed")
    if not isinstance(value["cycle_id"], str) or not value["cycle_id"].startswith("S19-P01-"):
        raise WalkingSkeletonInputError("cycle id is outside S19/P01")
    market = _require_mapping(value["market"], "market")
    expected_market = {
        "market_id": "SYNTHETIC-MARKET-S19-P01",
        "source_kind": "FROZEN_LOCAL_FIXTURE",
        "evidence_tier": "E0_SYNTHETIC_TEST_ONLY",
        "implied_probability": "0.500000000",
    }
    if dict(market) != expected_market:
        raise WalkingSkeletonInputError("only the frozen local market is admissible")
    if not isinstance(value["lifecycle_steps"], list) or tuple(value["lifecycle_steps"]) != LIFECYCLE_STEPS:
        raise WalkingSkeletonInputError("lifecycle must contain every frozen step exactly once")
    if value["probability_delta"] not in ("0", "-0.0001") or value["odds_tick_delta"] not in (-1, 0):
        raise WalkingSkeletonInputError("numeric perturbation is outside the frozen boundary vectors")
    if dict(_require_mapping(value["fund_facts_snapshot"], "fund_facts_snapshot")) != SAFE_FUND_FACTS and not isinstance(value["fund_facts_snapshot"], Mapping):
        raise WalkingSkeletonInputError("fund facts must be an object")
    _require_mapping(value["risk_gate_snapshot"], "risk_gate_snapshot")
    for key in (
        "requested_external_execution",
        "requested_actual_order",
        "requested_real_fund_mutation",
        "requested_real_mail_send",
        "requested_production_deploy",
    ):
        _require_bool(value[key], key)
    return value


def evaluate_walking_skeleton(value: Any) -> Dict[str, Any]:
    """Return a deterministic no-order lifecycle projection or a fail-closed pause."""

    payload = validate_cycle_input(value)
    failures = _failure_codes(payload)
    passed = not failures
    lifecycle = [
        {"step": "DISCOVER", "status": "LOCAL_SYNTHETIC_DISCOVERY_ONLY"},
        {"step": "ADVICE", "status": "ADVICE_PROJECTION_NO_ORDER"},
        {"step": "INVALIDATE", "status": "INVALIDATED_TO_NO_RECOMMENDATION"},
        {"step": "SYNTHETIC_RESULT", "status": "SYNTHETIC_RESULT_NOT_EMPIRICAL"},
        {"step": "REPLAY", "status": "DETERMINISTIC_REPLAY_READY"},
        {"step": "LOCAL_MAIL_EVIDENCE", "status": "LOCAL_EVIDENCE_PROJECTION_NOT_SENT"},
        {"step": "RECOVERY", "status": "DERIVED_STATE_RECOVERY_READY"},
    ]
    result: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "fixed_clock": FIXED_CLOCK,
        "cycle_id": payload["cycle_id"],
        "market": dict(payload["market"]),
        "lifecycle": lifecycle,
        "probability_delta": payload["probability_delta"],
        "odds_tick_delta": payload["odds_tick_delta"],
        "status": "PASS" if passed else "FAIL_CLOSED",
        "decision": "LOCAL_ALPHA_CLOSED_LOOP_NO_ORDER" if passed else "PAUSE_AND_REJECT_UNSAFE_REQUEST",
        "action": "NO_RECOMMENDATION",
        "failure_codes": failures,
        "fund_facts_before": SAFE_FUND_FACTS,
        "fund_facts_after": SAFE_FUND_FACTS,
        "risk_gate_before": SAFE_RISK_GATE,
        "risk_gate_after": SAFE_RISK_GATE,
        "owner_action": "FINAL_ORDER_ONLY_IF_FUTURE_EXTERNAL_GATES_PASS",
        "feature_flag_id": FEATURE_FLAG_ID,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    result["walking_skeleton_plan_sha256"] = artifact_sha256(result, "walking_skeleton_plan_sha256")
    return result


def build_walking_skeleton_artifact(plan: Mapping[str, Any], *, fixture_sha256: str, predecessor_evidence_sha256: Mapping[str, str]) -> Dict[str, Any]:
    if plan.get("status") != "PASS":
        raise WalkingSkeletonInputError("a failed plan cannot be promoted to a local artifact")
    artifact: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S19-P01-01",
        "contract_id": "AC-S19-P01",
        "requirement_id": "REQ-S19-P01",
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS",
        "scope": "ONE_FROZEN_SYNTHETIC_MARKET_LOCAL_ONLY",
        "market": plan["market"],
        "lifecycle": plan["lifecycle"],
        "decision": plan["decision"],
        "action": plan["action"],
        "replay_plan_sha256": plan["walking_skeleton_plan_sha256"],
        "fixture_sha256": fixture_sha256,
        "predecessor_evidence_sha256": dict(predecessor_evidence_sha256),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    artifact["walking_skeleton_evidence_sha256"] = artifact_sha256(artifact, "walking_skeleton_evidence_sha256")
    return artifact


def build_software_alpha_artifact(walking: Mapping[str, Any]) -> Dict[str, Any]:
    if walking.get("status") != "PASS" or walking.get("action") != "NO_RECOMMENDATION":
        raise WalkingSkeletonInputError("software alpha requires a passed no-order walking skeleton")
    artifact: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S19-P01-02",
        "contract_id": "AC-S19-P01",
        "requirement_id": "REQ-S19-P01",
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS",
        "alpha_status": "SOFTWARE_ALPHA_LOCAL_ONLY_NOT_DEPLOYED",
        "activation_conditions": {
            "single_market_lifecycle_closed": True,
            "real_funds_used": False,
            "actual_order_submission_enabled": False,
            "external_runtime_accessed": False,
            "local_mail_evidence_only": True,
            "recovery_replay_ready": True,
            "risk_or_evidence_gate_relaxed": False,
        },
        "walking_skeleton_evidence_sha256": walking["walking_skeleton_evidence_sha256"],
        "owner_action": "FINAL_ORDER_ONLY_IF_FUTURE_EXTERNAL_GATES_PASS",
        "next_required_gate": "S19/P02_READY_NOT_STARTED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
    }
    artifact["software_alpha_gate_sha256"] = artifact_sha256(artifact, "software_alpha_gate_sha256")
    return artifact


__all__ = [
    "EXTERNAL_EFFECT_BOUNDARY", "FEATURE_FLAG_ID", "FIXED_CLOCK", "LIFECYCLE_STEPS", "SAFE_FUND_FACTS", "SAFE_RISK_GATE",
    "WalkingSkeletonInputError", "artifact_sha256", "build_software_alpha_artifact", "build_walking_skeleton_artifact",
    "canonical_json_bytes", "evaluate_walking_skeleton", "validate_cycle_input",
]
