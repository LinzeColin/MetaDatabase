"""Offline, fail-closed S18/P04 operations-maintenance control projection."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .limited_self_heal import SAFE_ACTION, SAFE_FUND_FACTS, SAFE_RISK_GATE


PRODUCT_VERSION = "0.0.0.1"
CONTRACT_ID = "AC-S18-P04"
REQUIREMENT_ID = "REQ-S18-P04"
STAGE_ID = "S18"
PHASE_ID = "P04"
FIXED_CLOCK = "2026-08-10T04:00:00+10:00"
SCHEDULE_ID = "S18-P04-OFFLINE-OPERATIONS-SCHEDULE"
CALENDAR_ID = "S18-P04-OFFLINE-MAINTENANCE-CALENDAR"
NORMAL_DECISION = "CONTINUE_AUTONOMOUS_OFFLINE_CONTROL_PLANE"
NORMAL_ACTION = "NO_OWNER_MAINTENANCE_REQUIRED"
PAUSE_DECISION = "PAUSE_CONTRACT_AND_ESCALATE_OWNER_OUTBOX_ONLY"
PAUSE_ACTION = "PAUSE_CONTRACT_AND_ESCALATE_OWNER_OUTBOX_ONLY"
MALFORMED_REASON = "UNSAFE_OR_MALFORMED_OPERATIONS_INPUT"
EXPECTED_PREDECESSOR = {
    "contract_id": "AC-S18-P03",
    "evidence_sha256": "99ade2e845cd72af99713e4c0d5d07e2aea3a1e49e6895f5b9bcdeca2a9afe1f",
}
JOB_SPECS = (
    ("DAILY_SIGNED_CONTROL_REPLAY", "DAILY", "REPLAY_SIGNED_CONTROL_EVIDENCE_ONLY", ("AC-S18-P01", "AC-S18-P02", "AC-S18-P03")),
    ("DAILY_MAIL_EVIDENCE_CONTINUITY_AUDIT", "DAILY", "AUDIT_LOCAL_MAIL_EVIDENCE_PROJECTION_ONLY", ("AC-S18-P02",)),
    ("WEEKLY_PATCH_READINESS_GATE", "WEEKLY", "REVIEW_PATCH_READINESS_PROJECTION_ONLY", ("AC-S18-P01",)),
    ("WEEKLY_BACKUP_DERIVED_STATE_INTEGRITY_REPLAY", "WEEKLY", "REPLAY_DERIVED_BACKUP_INTEGRITY_ONLY", ("AC-S18-P03",)),
    ("MONTHLY_DISASTER_RECOVERY_PROJECTION", "MONTHLY", "REPLAY_LOCAL_DISASTER_RECOVERY_PROJECTION_ONLY", ("AC-S18-P01", "AC-S18-P03")),
    ("MONTHLY_RETENTION_AND_EVIDENCE_REVIEW", "MONTHLY", "REVIEW_LOCAL_EVIDENCE_RETENTION_PROJECTION_ONLY", ("AC-S18-P02", "AC-S18-P03")),
)
EXPECTED_JOB_IDS = tuple(spec[0] for spec in JOB_SPECS)
CALENDAR_SPECS = (
    ("CAL-DAILY-SIGNED-CONTROL", "DAILY", "DAILY_SIGNED_CONTROL_REPLAY"),
    ("CAL-DAILY-MAIL-EVIDENCE", "DAILY", "DAILY_MAIL_EVIDENCE_CONTINUITY_AUDIT"),
    ("CAL-WEEKLY-PATCH", "WEEKLY", "WEEKLY_PATCH_READINESS_GATE"),
    ("CAL-WEEKLY-BACKUP", "WEEKLY", "WEEKLY_BACKUP_DERIVED_STATE_INTEGRITY_REPLAY"),
    ("CAL-MONTHLY-DR", "MONTHLY", "MONTHLY_DISASTER_RECOVERY_PROJECTION"),
    ("CAL-MONTHLY-RETENTION", "MONTHLY", "MONTHLY_RETENTION_AND_EVIDENCE_REVIEW"),
)
EXPECTED_WINDOW_IDS = tuple(spec[0] for spec in CALENDAR_SPECS)
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "cloudflare_account_dns_or_tunnel_accessed": False,
    "gmail_account_or_api_accessed": False,
    "actual_scheduler_or_cron_installed": False,
    "actual_process_or_service_restarted": False,
    "actual_patch_or_backup_performed": False,
    "actual_disaster_recovery_executed": False,
    "actual_fund_facts_read_or_written": False,
    "actual_ledger_read_or_written": False,
    "risk_gate_relaxed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class OperationsInputError(ValueError):
    """Raised when an operations cycle cannot stay inside the P04 pause contract."""


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


def validate_runbook(text: Any) -> str:
    if not isinstance(text, str):
        raise OperationsInputError("runbook is unavailable")
    markers = (
        "# ABD v0.0.0.1 S18/P04 运行手册与值守自动化",
        "AC-S18-P04",
        "OFFLINE_DETERMINISTIC_CONTRACT_ONLY",
        "正常运行无需用户维护；异常仅按暂停合同升级。",
        NORMAL_DECISION,
        NORMAL_ACTION,
        PAUSE_DECISION,
        "LOCAL_STRUCTURED_OUTBOX_PROJECTION_ONLY",
        SAFE_ACTION,
        "FINAL_ORDER_ONLY",
    )
    if any(marker not in text for marker in markers) or any(job_id not in text for job_id in EXPECTED_JOB_IDS):
        raise OperationsInputError("runbook does not state the immutable P04 boundary")
    return text


def validate_scheduled_jobs(value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "schedule_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "execution_mode", "normal_operation", "exception_policy", "predecessor", "immutable_fund_facts",
        "immutable_risk_gate", "jobs", "external_effect_boundary",
    }
    identity = {
        "schema_version": "1.0.0",
        "schedule_id": SCHEDULE_ID,
        "product_version": PRODUCT_VERSION,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "OFFLINE_DETERMINISTIC_CONTRACT_ONLY",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise OperationsInputError("scheduled-jobs schema is invalid")
    if {key: value.get(key) for key in identity} != identity:
        raise OperationsInputError("scheduled-jobs identity differs")
    if value.get("normal_operation") != {
        "owner_maintenance_required": False,
        "decision": NORMAL_DECISION,
        "action": NORMAL_ACTION,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
    }:
        raise OperationsInputError("normal operations policy differs")
    if value.get("exception_policy") != {
        "decision": PAUSE_DECISION,
        "action": PAUSE_ACTION,
        "pause_contract": True,
        "outbox_delivery_mode": "LOCAL_STRUCTURED_OUTBOX_PROJECTION_ONLY",
        "external_delivery_enabled": False,
        "automatic_real_runtime_recovery_enabled": False,
    }:
        raise OperationsInputError("exception policy differs")
    if value.get("predecessor") != EXPECTED_PREDECESSOR:
        raise OperationsInputError("P03 predecessor differs")
    if value.get("immutable_fund_facts") != SAFE_FUND_FACTS or value.get("immutable_risk_gate") != SAFE_RISK_GATE:
        raise OperationsInputError("immutable fund facts or risk gate differs")
    if value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY:
        raise OperationsInputError("external-effect boundary differs")
    jobs = value.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != len(JOB_SPECS):
        raise OperationsInputError("scheduled jobs are unavailable")
    expected_fields = {
        "job_id", "cadence", "logical_mode", "required_contract_ids", "normal_status", "failure_action",
        "derived_state_only", "external_effects_permitted",
    }
    for item, expected in zip(jobs, JOB_SPECS):
        job_id, cadence, logical_mode, required_contract_ids = expected
        if not isinstance(item, Mapping) or set(item) != expected_fields:
            raise OperationsInputError("scheduled-job schema differs")
        if item != {
            "job_id": job_id,
            "cadence": cadence,
            "logical_mode": logical_mode,
            "required_contract_ids": list(required_contract_ids),
            "normal_status": "PASS",
            "failure_action": PAUSE_ACTION,
            "derived_state_only": True,
            "external_effects_permitted": False,
        }:
            raise OperationsInputError("scheduled job differs from the pause contract")
    return value


def validate_maintenance_calendar(value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "calendar_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "execution_mode", "normal_owner_maintenance_required", "maintenance_windows", "exception_escalation",
        "external_effect_boundary",
    }
    identity = {
        "schema_version": "1.0.0",
        "calendar_id": CALENDAR_ID,
        "product_version": PRODUCT_VERSION,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "OFFLINE_DETERMINISTIC_CONTRACT_ONLY",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise OperationsInputError("maintenance-calendar schema is invalid")
    if {key: value.get(key) for key in identity} != identity or value.get("normal_owner_maintenance_required") is not False:
        raise OperationsInputError("maintenance-calendar identity differs")
    if value.get("exception_escalation") != {
        "pause_contract": True,
        "escalation_destination": "LOCAL_OWNER_OUTBOX_PROJECTION_ONLY",
        "external_delivery_enabled": False,
        "automatic_real_runtime_recovery_enabled": False,
        "owner_order_action": "FINAL_ORDER_ONLY",
    }:
        raise OperationsInputError("maintenance escalation differs")
    if value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY:
        raise OperationsInputError("calendar external-effect boundary differs")
    windows = value.get("maintenance_windows")
    if not isinstance(windows, list) or len(windows) != len(CALENDAR_SPECS):
        raise OperationsInputError("maintenance windows are unavailable")
    expected_fields = {"window_id", "cadence", "job_id", "maintenance_mode", "requires_owner_maintenance_normal"}
    for item, expected in zip(windows, CALENDAR_SPECS):
        window_id, cadence, job_id = expected
        if not isinstance(item, Mapping) or set(item) != expected_fields:
            raise OperationsInputError("maintenance-window schema differs")
        if item != {
            "window_id": window_id,
            "cadence": cadence,
            "job_id": job_id,
            "maintenance_mode": "LOGICAL_CONTROL_WINDOW_ONLY",
            "requires_owner_maintenance_normal": False,
        }:
            raise OperationsInputError("maintenance window differs")
    return value


def _validate_cycle(value: Any, scheduled_jobs: Mapping[str, Any], calendar: Mapping[str, Any]) -> Mapping[str, Any]:
    fields = {
        "schema_version", "fixed_clock", "cycle_id", "job_results", "probability_delta", "odds_tick_delta",
        "fund_facts_snapshot", "risk_gate_snapshot", "requested_external_execution", "requested_actual_maintenance",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise OperationsInputError("operations-cycle schema is invalid")
    if value.get("schema_version") != "1.0.0" or value.get("fixed_clock") != scheduled_jobs.get("fixed_clock") != calendar.get("fixed_clock"):
        raise OperationsInputError("operations-cycle identity differs")
    if not isinstance(value.get("cycle_id"), str) or not value["cycle_id"].startswith("S18-P04-"):
        raise OperationsInputError("operations-cycle id is invalid")
    if value.get("probability_delta") not in {"-0.0001", "0", "0.0001"} or value.get("odds_tick_delta") != -1:
        raise OperationsInputError("operations-cycle perturbation differs")
    if value.get("fund_facts_snapshot") != SAFE_FUND_FACTS or value.get("risk_gate_snapshot") != SAFE_RISK_GATE:
        raise OperationsInputError("operations-cycle attempts to change immutable gates")
    if value.get("requested_external_execution") is not False or value.get("requested_actual_maintenance") is not False:
        raise OperationsInputError("operations-cycle requests real execution")
    results = value.get("job_results")
    if not isinstance(results, list) or len(results) != len(EXPECTED_JOB_IDS):
        raise OperationsInputError("operations-cycle job results are unavailable")
    observed_ids = []
    for item in results:
        if not isinstance(item, Mapping) or set(item) != {"job_id", "status"}:
            raise OperationsInputError("operations-cycle job-result schema differs")
        if item.get("status") not in {"PASS", "FAIL"}:
            raise OperationsInputError("operations-cycle job-result status differs")
        observed_ids.append(item.get("job_id"))
    if tuple(observed_ids) != EXPECTED_JOB_IDS:
        raise OperationsInputError("operations-cycle job-result order differs")
    return value


def _build_plan(
    *,
    cycle_id: str,
    clock: str,
    job_outcomes: Sequence[Mapping[str, Any]],
    decision: str,
    action: str,
    failed_job_ids: Sequence[str],
    reason: str | None = None,
) -> dict[str, Any]:
    paused = decision == PAUSE_DECISION
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "operations_plan_id": "S18-P04-OFFLINE-OPERATIONS-PLAN",
        "contract_id": CONTRACT_ID,
        "fixed_clock": clock,
        "cycle_id": cycle_id,
        "decision": decision,
        "action": action,
        "pause_contract": paused,
        "owner_maintenance_required": paused,
        "failed_job_ids": list(failed_job_ids),
        "job_outcomes": [dict(item) for item in job_outcomes],
        "owner_outbox_projection": {
            "status": "LOCAL_OWNER_ESCALATION_NOT_SENT" if paused else "NOT_REQUIRED_LOCAL_OUTBOX_NOT_SENT",
            "delivery_mode": "LOCAL_STRUCTURED_OUTBOX_PROJECTION_ONLY",
            "external_delivery_attempted": False,
            "external_delivery_enabled": False,
            "external_network_accessed": False,
        },
        "fund_facts_before": dict(SAFE_FUND_FACTS),
        "fund_facts_after": dict(SAFE_FUND_FACTS),
        "risk_gate_before": dict(SAFE_RISK_GATE),
        "risk_gate_after": dict(SAFE_RISK_GATE),
        "fund_facts_changed": False,
        "risk_gate_relaxed": False,
        "actual_scheduler_or_cron_installed": False,
        "actual_process_or_service_restarted": False,
        "actual_patch_or_backup_performed": False,
        "actual_disaster_recovery_executed": False,
        "safe_action": SAFE_ACTION,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "external_runtime_accessed": False,
        "production_state_changed": False,
        "real_time_wait_performed": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if reason is not None:
        payload["pause_reason"] = reason
    unsigned = dict(payload)
    payload["operations_plan_sha256"] = hashlib.sha256(_json_bytes(unsigned)).hexdigest()
    return payload


def _fallback(reason: str) -> dict[str, Any]:
    return _build_plan(
        cycle_id="S18-P04-MALFORMED-OPERATIONS-CYCLE",
        clock=FIXED_CLOCK,
        job_outcomes=[{"job_id": job_id, "status": "NOT_EVALUATED"} for job_id in EXPECTED_JOB_IDS],
        decision=PAUSE_DECISION,
        action=PAUSE_ACTION,
        failed_job_ids=list(EXPECTED_JOB_IDS),
        reason=reason,
    )


def evaluate_operations_cycle(value: Any, scheduled_jobs: Any, calendar: Any) -> dict[str, Any]:
    """Project one deterministic P04 operations cycle without performing it."""
    try:
        schedule = validate_scheduled_jobs(scheduled_jobs)
        validated_calendar = validate_maintenance_calendar(calendar)
        cycle = _validate_cycle(value, schedule, validated_calendar)
        failures = [item["job_id"] for item in cycle["job_results"] if item["status"] == "FAIL"]
        if failures:
            return _build_plan(
                cycle_id=cycle["cycle_id"],
                clock=cycle["fixed_clock"],
                job_outcomes=cycle["job_results"],
                decision=PAUSE_DECISION,
                action=PAUSE_ACTION,
                failed_job_ids=failures,
                reason="SCHEDULED_JOB_FAIL",
            )
        return _build_plan(
            cycle_id=cycle["cycle_id"],
            clock=cycle["fixed_clock"],
            job_outcomes=cycle["job_results"],
            decision=NORMAL_DECISION,
            action=NORMAL_ACTION,
            failed_job_ids=[],
        )
    except OperationsInputError as exc:
        return _fallback(type(exc).__name__)


__all__ = [
    "CALENDAR_ID", "CONTRACT_ID", "EXPECTED_JOB_IDS", "EXPECTED_WINDOW_IDS", "EXTERNAL_EFFECT_BOUNDARY",
    "FIXED_CLOCK", "MALFORMED_REASON", "NORMAL_ACTION", "NORMAL_DECISION", "OperationsInputError", "PAUSE_ACTION",
    "PAUSE_DECISION", "SCHEDULE_ID", "evaluate_operations_cycle", "validate_maintenance_calendar", "validate_runbook",
    "validate_scheduled_jobs",
]
