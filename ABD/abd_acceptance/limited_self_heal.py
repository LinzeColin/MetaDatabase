"""Offline, bounded S18/P03 self-heal planning with immutable funds and risk gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


PRODUCT_VERSION = "0.0.0.1"
CONTRACT_ID = "AC-S18-P03"
REQUIREMENT_ID = "REQ-S18-P03"
STAGE_ID = "S18"
PHASE_ID = "P03"
FIXED_CLOCK = "2026-08-10T03:00:00+10:00"
POLICY_ID = "S18-P03-LIMITED-SELF-HEAL-POLICY"
SAFE_ACTION = "NO_RECOMMENDATION_NO_ORDER"
HEALTHY_DECISION = "SELF_HEAL_NO_ACTION_KEEP_GATES"
APPROVED_DECISION = "SELF_HEAL_PLAN_APPROVED_WITH_IMMUTABLE_FUNDS_AND_RISK"
ESCALATION_DECISION = "SELF_HEAL_FAIL_CLOSED_ESCALATION"
FALLBACK_FAULT_ID = "UNSAFE_MUTATION_OR_MALFORMED_INPUT"
EXPECTED_OPERATIONS = (
    ("CANDIDATE_PROCESS_UNHEALTHY", "LOGICAL_RESTART_CANDIDATE_ONLY"),
    ("FROZEN_REPLAY_MISMATCH", "LOGICAL_RETRY_FROZEN_REPLAY_ONLY"),
    ("SILENT_COVERAGE_GAP_DETECTED", "LOGICAL_REPLAY_DERIVED_STATE_ONLY"),
    ("SOURCE_FRESHNESS_FAILED", "LOGICAL_SWITCH_TO_PREVIOUS_SIGNED_SOURCE_SNAPSHOT"),
    ("MODEL_PSI_STOP", "LOGICAL_ROLLBACK_TO_PREVIOUS_SIGNED_MODEL_CANDIDATE"),
    ("EVIDENCE_DERIVED_STATE_CORRUPT", "LOGICAL_REBUILD_DERIVED_STATE_ONLY"),
    (FALLBACK_FAULT_ID, "LOGICAL_ESCALATE_OWNER_OUTBOX_ONLY"),
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
    "ovh_account_or_host_accessed": False,
    "cloudflare_account_dns_or_tunnel_accessed": False,
    "gmail_account_or_api_accessed": False,
    "process_or_service_restarted": False,
    "source_switched": False,
    "model_activated_or_rolled_back": False,
    "actual_fund_facts_read_or_written": False,
    "actual_ledger_read_or_written": False,
    "risk_gate_relaxed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
FALLBACK_OPERATION = {
    "fault_id": FALLBACK_FAULT_ID,
    "operation_id": "LOGICAL_ESCALATE_OWNER_OUTBOX_ONLY",
    "mode": "MANUAL_LOGICAL",
    "allowed_target": "LOCAL_OWNER_OUTBOX_PROJECTION_ONLY",
    "derived_state_only": True,
    "writes_shared_ledger": False,
}


class SelfHealInputError(ValueError):
    """Raised when an S18/P03 action cannot be planned without weakening a gate."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _operation_map(policy: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    operations = policy.get("allowed_operations")
    if not isinstance(operations, list):
        raise SelfHealInputError("allowed operations are unavailable")
    selected: dict[str, Mapping[str, Any]] = {}
    for row in operations:
        if not isinstance(row, Mapping) or set(row) != {"fault_id", "operation_id", "mode", "allowed_target", "derived_state_only", "writes_shared_ledger"}:
            raise SelfHealInputError("operation schema is invalid")
        fault_id = row.get("fault_id")
        if not isinstance(fault_id, str) or fault_id in selected:
            raise SelfHealInputError("operation fault id is invalid")
        if not isinstance(row.get("operation_id"), str) or row.get("mode") not in {"AUTOMATIC_LOGICAL", "MANUAL_LOGICAL"}:
            raise SelfHealInputError("operation mode is invalid")
        if row.get("derived_state_only") is not True or row.get("writes_shared_ledger") is not False:
            raise SelfHealInputError("operation exceeds derived-state boundary")
        selected[fault_id] = row
    expected_fault_ids = tuple(fault_id for fault_id, _ in EXPECTED_OPERATIONS)
    if tuple(selected) != expected_fault_ids or tuple((fault_id, selected[fault_id].get("operation_id")) for fault_id in expected_fault_ids) != EXPECTED_OPERATIONS:
        raise SelfHealInputError("operation mapping is not exact")
    return selected


def validate_policy(value: Any) -> tuple[Mapping[str, Any], Mapping[str, Mapping[str, Any]]]:
    fields = {
        "schema_version", "policy_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "execution_mode", "allowed_operations", "immutable_fund_facts", "immutable_risk_gate",
        "outbox_policy", "external_effect_boundary",
    }
    identity = {
        "schema_version": "1.0.0",
        "policy_id": POLICY_ID,
        "product_version": PRODUCT_VERSION,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "OFFLINE_DETERMINISTIC_CONTRACT_ONLY",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise SelfHealInputError("self-heal policy schema is invalid")
    if {key: value.get(key) for key in identity} != identity:
        raise SelfHealInputError("self-heal policy identity is invalid")
    if value.get("immutable_fund_facts") != SAFE_FUND_FACTS or value.get("immutable_risk_gate") != SAFE_RISK_GATE:
        raise SelfHealInputError("fund facts or risk gate differs from the immutable policy")
    if value.get("outbox_policy") != {
        "delivery_mode": "LOCAL_STRUCTURED_OUTBOX_PROJECTION_ONLY",
        "external_delivery_enabled": False,
        "retry_external_delivery": False,
        "owner_action": "FINAL_ORDER_ONLY",
    }:
        raise SelfHealInputError("outbox policy is unsafe")
    if value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY:
        raise SelfHealInputError("external-effect boundary differs")
    return value, _operation_map(value)


def _validate_watchdog_input(value: Any, policy: Mapping[str, Any], operations: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    fields = {"schema_version", "fixed_clock", "fault_id", "probability_delta", "odds_tick_delta", "fund_facts_snapshot", "risk_gate_snapshot"}
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise SelfHealInputError("watchdog input schema is invalid")
    if value.get("schema_version") != "1.0.0" or value.get("fixed_clock") != policy.get("fixed_clock"):
        raise SelfHealInputError("watchdog input identity is invalid")
    if value.get("fault_id") not in {*operations, "NO_FAULT"}:
        raise SelfHealInputError("watchdog fault id is invalid")
    if value.get("probability_delta") not in {"-0.0001", "0", "0.0001"} or value.get("odds_tick_delta") != -1:
        raise SelfHealInputError("watchdog perturbation vector is invalid")
    if value.get("fund_facts_snapshot") != policy.get("immutable_fund_facts"):
        raise SelfHealInputError("fund fact mutation request is forbidden")
    if value.get("risk_gate_snapshot") != policy.get("immutable_risk_gate"):
        raise SelfHealInputError("risk-gate relaxation request is forbidden")
    return value


def _plan(policy: Mapping[str, Any], operations: Sequence[Mapping[str, Any]], decision: str, *, reason: str | None = None) -> dict[str, Any]:
    operation_plan = [
        {
            "fault_id": operation["fault_id"],
            "operation_id": operation["operation_id"],
            "mode": operation["mode"],
            "allowed_target": operation["allowed_target"],
            "derived_state_only": operation["derived_state_only"],
            "writes_shared_ledger": operation["writes_shared_ledger"],
        }
        for operation in operations
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "watchdog_plan_id": "S18-P03-OFFLINE-LIMITED-SELF-HEAL-PLAN",
        "contract_id": CONTRACT_ID,
        "fixed_clock": policy.get("fixed_clock", FIXED_CLOCK),
        "decision": decision,
        "operation_ids": [item["operation_id"] for item in operation_plan],
        "operation_plan": operation_plan,
        "fund_facts_before": dict(policy.get("immutable_fund_facts", SAFE_FUND_FACTS)),
        "fund_facts_after": dict(policy.get("immutable_fund_facts", SAFE_FUND_FACTS)),
        "risk_gate_before": dict(policy.get("immutable_risk_gate", SAFE_RISK_GATE)),
        "risk_gate_after": dict(policy.get("immutable_risk_gate", SAFE_RISK_GATE)),
        "fund_facts_changed": False,
        "risk_gate_relaxed": False,
        "shared_ledger_written": False,
        "safe_action": SAFE_ACTION,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "external_runtime_accessed": False,
        "production_state_changed": False,
        "real_time_wait_performed": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if reason is not None:
        payload["fail_closed_reason"] = reason
    unsigned = dict(payload)
    payload["watchdog_plan_sha256"] = hashlib.sha256(_json_bytes(unsigned)).hexdigest()
    return payload


def _fallback(policy: Any, reason: str) -> dict[str, Any]:
    selected_policy: Mapping[str, Any] = {
        "fixed_clock": FIXED_CLOCK,
        "immutable_fund_facts": SAFE_FUND_FACTS,
        "immutable_risk_gate": SAFE_RISK_GATE,
    }
    operation = FALLBACK_OPERATION
    try:
        verified_policy, operations = validate_policy(policy)
        selected_policy = verified_policy
        operation = operations[FALLBACK_FAULT_ID]
    except SelfHealInputError:
        pass
    return _plan(selected_policy, [operation], ESCALATION_DECISION, reason=reason)


def evaluate_watchdog_event(value: Any, policy: Any) -> dict[str, Any]:
    """Return an offline action plan without modifying money facts or risk gates."""
    try:
        verified_policy, operations = validate_policy(policy)
        event = _validate_watchdog_input(value, verified_policy, operations)
        if event["fault_id"] == "NO_FAULT":
            return _plan(verified_policy, [], HEALTHY_DECISION)
        return _plan(verified_policy, [operations[event["fault_id"]]], APPROVED_DECISION)
    except SelfHealInputError as exc:
        return _fallback(policy, type(exc).__name__)


def _valid_watchdog_plan(value: Any, policy: Mapping[str, Any], operations: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or _contains_float(value):
        raise SelfHealInputError("watchdog plan is invalid")
    required = {
        "schema_version", "watchdog_plan_id", "contract_id", "fixed_clock", "decision", "operation_ids", "operation_plan",
        "fund_facts_before", "fund_facts_after", "risk_gate_before", "risk_gate_after", "fund_facts_changed", "risk_gate_relaxed",
        "shared_ledger_written", "safe_action", "recommendation_generated_or_enabled", "order_submission_enabled",
        "external_runtime_accessed", "production_state_changed", "real_time_wait_performed", "incremental_cash_spent_aud", "watchdog_plan_sha256",
    }
    if set(value) - {"fail_closed_reason"} != required:
        raise SelfHealInputError("watchdog plan fields differ")
    if value.get("schema_version") != "1.0.0" or value.get("watchdog_plan_id") != "S18-P03-OFFLINE-LIMITED-SELF-HEAL-PLAN" or value.get("contract_id") != CONTRACT_ID or value.get("fixed_clock") != policy.get("fixed_clock"):
        raise SelfHealInputError("watchdog plan identity differs")
    if value.get("fund_facts_before") != policy.get("immutable_fund_facts") or value.get("fund_facts_after") != policy.get("immutable_fund_facts"):
        raise SelfHealInputError("watchdog plan alters fund facts")
    if value.get("risk_gate_before") != policy.get("immutable_risk_gate") or value.get("risk_gate_after") != policy.get("immutable_risk_gate"):
        raise SelfHealInputError("watchdog plan alters risk gates")
    if any(value.get(key) is not False for key in ("fund_facts_changed", "risk_gate_relaxed", "shared_ledger_written", "recommendation_generated_or_enabled", "order_submission_enabled", "external_runtime_accessed", "production_state_changed", "real_time_wait_performed")) or value.get("safe_action") != SAFE_ACTION or value.get("incremental_cash_spent_aud") != "0.00":
        raise SelfHealInputError("watchdog plan crosses a safety boundary")
    operation_ids = value.get("operation_ids")
    if not isinstance(operation_ids, list) or len(operation_ids) != len(set(operation_ids)):
        raise SelfHealInputError("watchdog operations are ambiguous")
    allowed_ids = {row["operation_id"] for row in operations.values()}
    if not set(operation_ids) <= allowed_ids:
        raise SelfHealInputError("watchdog operation is outside the policy")
    operation_plan = value.get("operation_plan")
    expected_by_id = {row["operation_id"]: {
        "fault_id": row["fault_id"],
        "operation_id": row["operation_id"],
        "mode": row["mode"],
        "allowed_target": row["allowed_target"],
        "derived_state_only": row["derived_state_only"],
        "writes_shared_ledger": row["writes_shared_ledger"],
    } for row in operations.values()}
    if not isinstance(operation_plan, list) or operation_plan != [expected_by_id[operation_id] for operation_id in operation_ids]:
        raise SelfHealInputError("watchdog operation plan differs from the immutable policy")
    decision = value.get("decision")
    reason = value.get("fail_closed_reason")
    fallback_id = operations[FALLBACK_FAULT_ID]["operation_id"]
    if (
        (decision == HEALTHY_DECISION and operation_ids == [] and reason is None)
        or (decision == APPROVED_DECISION and len(operation_ids) == 1 and operation_ids[0] != fallback_id and reason is None)
        or (decision == ESCALATION_DECISION and operation_ids == [fallback_id] and isinstance(reason, str) and reason)
    ):
        pass
    else:
        raise SelfHealInputError("watchdog decision does not match its bounded operation")
    unsigned = dict(value)
    observed = unsigned.pop("watchdog_plan_sha256", None)
    if not isinstance(observed, str) or observed != hashlib.sha256(_json_bytes(unsigned)).hexdigest():
        raise SelfHealInputError("watchdog plan hash differs")
    return value


def evaluate_outbox_projection(value: Any, policy: Any) -> dict[str, Any]:
    """Convert a verified watchdog plan into a local-only owner outbox projection."""
    try:
        verified_policy, operations = validate_policy(policy)
        plan = _valid_watchdog_plan(value, verified_policy, operations)
        operation_ids = list(plan["operation_ids"])
        source_hash = plan["watchdog_plan_sha256"]
        decision = "LOCAL_OUTBOX_NOT_SENT"
    except SelfHealInputError as exc:
        fallback = _fallback(policy, type(exc).__name__)
        verified_policy = {"fixed_clock": fallback["fixed_clock"], "outbox_policy": {"owner_action": "FINAL_ORDER_ONLY"}}
        operation_ids = list(fallback["operation_ids"])
        source_hash = fallback["watchdog_plan_sha256"]
        decision = "LOCAL_OUTBOX_FAIL_CLOSED_NOT_SENT"
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "outbox_projection_id": "S18-P03-LOCAL-OUTBOX-PROJECTION",
        "contract_id": CONTRACT_ID,
        "fixed_clock": verified_policy.get("fixed_clock", FIXED_CLOCK),
        "delivery_status": decision,
        "source_watchdog_plan_sha256": source_hash,
        "operation_ids": operation_ids,
        "owner_action": verified_policy.get("outbox_policy", {}).get("owner_action", "FINAL_ORDER_ONLY"),
        "external_delivery_attempted": False,
        "external_delivery_enabled": False,
        "external_network_accessed": False,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "actual_fund_facts_changed": False,
        "risk_gate_relaxed": False,
        "incremental_cash_spent_aud": "0.00",
    }
    unsigned = dict(payload)
    payload["outbox_projection_sha256"] = hashlib.sha256(_json_bytes(unsigned)).hexdigest()
    return payload


def _load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def watchdog_main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an offline ABD S18/P03 watchdog event")
    parser.add_argument("--input", required=True, help="frozen watchdog event JSON")
    parser.add_argument("--policy", default="self_heal_policy.json", help="offline self-heal policy")
    args = parser.parse_args()
    print(json.dumps(evaluate_watchdog_event(_load_json(args.input), _load_json(args.policy)), ensure_ascii=False, sort_keys=True))
    return 0


def outbox_main() -> int:
    parser = argparse.ArgumentParser(description="Project an offline ABD S18/P03 owner outbox entry")
    parser.add_argument("--input", required=True, help="watchdog plan JSON")
    parser.add_argument("--policy", default="self_heal_policy.json", help="offline self-heal policy")
    args = parser.parse_args()
    print(json.dumps(evaluate_outbox_projection(_load_json(args.input), _load_json(args.policy)), ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "APPROVED_DECISION", "CONTRACT_ID", "ESCALATION_DECISION", "EXTERNAL_EFFECT_BOUNDARY", "FALLBACK_FAULT_ID",
    "FIXED_CLOCK", "HEALTHY_DECISION", "POLICY_ID", "SAFE_ACTION", "SAFE_FUND_FACTS", "SAFE_RISK_GATE",
    "SelfHealInputError", "evaluate_outbox_projection", "evaluate_watchdog_event", "outbox_main", "validate_policy", "watchdog_main",
]
