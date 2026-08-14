"""Offline, fail-closed S18/P02 diagnostic-bundle evaluator."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


PRODUCT_VERSION = "0.0.0.1"
CONTRACT_ID = "AC-S18-P02"
REQUIREMENT_ID = "REQ-S18-P02"
STAGE_ID = "S18"
PHASE_ID = "P02"
FIXED_CLOCK = "2026-08-10T02:00:00+10:00"
DASHBOARD_SET_ID = "S18-P02-OFFLINE-OBSERVABILITY-DASHBOARDS"
ALERT_POLICY_ID = "S18-P02-OBSERVABILITY-ALERT-POLICY"
SAFE_ACTION = "NO_RECOMMENDATION_NO_ORDER"
HEALTHY_DECISION = "NO_HIGH_PRIORITY_ALERTS_KEEP_ADVICE_DISABLED"
ALERT_DECISION = "HIGH_PRIORITY_ALERTS_FAIL_CLOSED_ACTIONS_REQUIRED"
MALFORMED_ALERT_ID = "HP-MALFORMED-DIAGNOSTIC-INPUT"
EXPECTED_ALERT_IDS = (
    "HP-LIVE-ADVICE-FRESHNESS",
    "HP-SILENT-COVERAGE-GAP",
    "HP-MODEL-PSI-STOP",
    "HP-RESOURCE-ENVELOPE",
    "HP-EMAIL-VERIFICATION",
    "HP-EVIDENCE-INTEGRITY",
    MALFORMED_ALERT_ID,
)
EXPECTED_SIGNAL_FIELDS = (
    "live_advice_age_seconds",
    "silent_coverage_gap_count",
    "population_stability_index",
    "resource_envelope_status",
    "email_verification_status",
    "evidence_integrity_status",
)
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "ovh_account_or_host_accessed": False,
    "cloudflare_account_dns_or_tunnel_accessed": False,
    "gmail_account_or_api_accessed": False,
    "real_market_data_collected": False,
    "shared_production_ledger_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}
FALLBACK_ACTION = {
    "action_id": "LOGICAL_QUARANTINE_DIAGNOSTIC_INPUT_AND_REQUEST_REPLAY",
    "mode": "MANUAL_LOGICAL",
    "logical_effect": SAFE_ACTION,
    "owner_review_required": True,
}


class DiagnosticInputError(ValueError):
    """Raised when a diagnostic bundle cannot be evaluated deterministically."""


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


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise DiagnosticInputError("authoritative decimal values must be strings")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise DiagnosticInputError("authoritative decimal is invalid") from exc
    if not decimal.is_finite():
        raise DiagnosticInputError("authoritative decimal must be finite")
    return decimal


def _policy_alerts(policy: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    alerts = policy.get("high_priority_alerts")
    if not isinstance(alerts, list):
        raise DiagnosticInputError("high-priority alerts are unavailable")
    selected: dict[str, Mapping[str, Any]] = {}
    action_ids: list[str] = []
    for alert in alerts:
        if not isinstance(alert, Mapping) or set(alert) != {"id", "domain", "signal", "operator", "threshold_ref", "source_path", "action"}:
            raise DiagnosticInputError("high-priority alert schema is invalid")
        identifier = alert.get("id")
        action = alert.get("action")
        if not isinstance(identifier, str) or not isinstance(action, Mapping) or set(action) != {"action_id", "mode", "logical_effect", "owner_review_required"}:
            raise DiagnosticInputError("high-priority alert identity is invalid")
        if action.get("mode") not in {"AUTOMATIC_LOGICAL", "MANUAL_LOGICAL"} or action.get("logical_effect") != SAFE_ACTION or not isinstance(action.get("owner_review_required"), bool):
            raise DiagnosticInputError("high-priority alert action is unsafe")
        if identifier in selected or not isinstance(action.get("action_id"), str):
            raise DiagnosticInputError("high-priority alert action is ambiguous")
        selected[identifier] = alert
        action_ids.append(action["action_id"])
    if tuple(selected) != EXPECTED_ALERT_IDS or len(set(action_ids)) != len(action_ids):
        raise DiagnosticInputError("high-priority alert mapping is not exact and unique")
    return selected


def validate_documents(dashboards: Any, policy: Any) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Mapping[str, Any]]]:
    dashboard_fields = {
        "schema_version", "dashboard_set_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "execution_mode", "dashboards", "external_effect_boundary",
    }
    policy_fields = {
        "schema_version", "alert_policy_id", "product_version", "contract_id", "requirement_id", "stage_id", "phase_id",
        "fixed_clock", "execution_mode", "thresholds", "high_priority_alerts", "safe_action", "external_effect_boundary",
    }
    identity = {
        "schema_version": "1.0.0",
        "product_version": PRODUCT_VERSION,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "fixed_clock": FIXED_CLOCK,
        "execution_mode": "OFFLINE_DETERMINISTIC_CONTRACT_ONLY",
    }
    if not isinstance(dashboards, Mapping) or set(dashboards) != dashboard_fields or _contains_float(dashboards):
        raise DiagnosticInputError("dashboard document schema is invalid")
    if not isinstance(policy, Mapping) or set(policy) != policy_fields or _contains_float(policy):
        raise DiagnosticInputError("alert policy schema is invalid")
    if {key: dashboards.get(key) for key in identity} != identity or dashboards.get("dashboard_set_id") != DASHBOARD_SET_ID:
        raise DiagnosticInputError("dashboard document identity is invalid")
    if {key: policy.get(key) for key in identity} != identity or policy.get("alert_policy_id") != ALERT_POLICY_ID:
        raise DiagnosticInputError("alert policy identity is invalid")
    if dashboards.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY or policy.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY:
        raise DiagnosticInputError("external-effect boundary differs")
    if policy.get("safe_action") != SAFE_ACTION:
        raise DiagnosticInputError("safe action differs")
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, Mapping) or thresholds != {
        "live_advice_usable_seconds": 8,
        "silent_coverage_gap_max": 0,
        "population_stability_index_stop": "0.20",
    }:
        raise DiagnosticInputError("alert thresholds are invalid")
    alert_by_id = _policy_alerts(policy)
    dashboard_rows = dashboards.get("dashboards")
    if not isinstance(dashboard_rows, list) or len(dashboard_rows) != 4:
        raise DiagnosticInputError("dashboard rows are invalid")
    dashboard_alert_ids: list[str] = []
    for row in dashboard_rows:
        if not isinstance(row, Mapping) or set(row) != {"id", "domain", "metric_fields", "alert_ids", "runtime_mode"}:
            raise DiagnosticInputError("dashboard row schema is invalid")
        if row.get("runtime_mode") != "FROZEN_STRUCTURED_INPUT_REPLAY_ONLY" or not isinstance(row.get("alert_ids"), list):
            raise DiagnosticInputError("dashboard row runtime mode is invalid")
        dashboard_alert_ids.extend(row["alert_ids"])
    if tuple(dashboard_alert_ids) != EXPECTED_ALERT_IDS or set(dashboard_alert_ids) != set(alert_by_id):
        raise DiagnosticInputError("dashboard coverage of high-priority alerts is invalid")
    return dashboards, policy, alert_by_id


def _validate_input(value: Any, policy: Mapping[str, Any]) -> Mapping[str, Any]:
    fields = {"schema_version", "fixed_clock", "probability_delta", "odds_tick_delta", "signal_snapshot"}
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise DiagnosticInputError("diagnostic input schema is invalid")
    if value.get("schema_version") != "1.0.0" or value.get("fixed_clock") != policy.get("fixed_clock"):
        raise DiagnosticInputError("diagnostic input identity is invalid")
    if value.get("probability_delta") not in {"-0.0001", "0", "0.0001"} or value.get("odds_tick_delta") != -1:
        raise DiagnosticInputError("diagnostic perturbation vector is invalid")
    snapshot = value.get("signal_snapshot")
    if not isinstance(snapshot, Mapping) or tuple(snapshot) != EXPECTED_SIGNAL_FIELDS:
        raise DiagnosticInputError("diagnostic signal fields are invalid")
    if not _plain_int(snapshot.get("live_advice_age_seconds")) or snapshot["live_advice_age_seconds"] < 0:
        raise DiagnosticInputError("live-advice age is invalid")
    if not _plain_int(snapshot.get("silent_coverage_gap_count")) or snapshot["silent_coverage_gap_count"] < 0:
        raise DiagnosticInputError("silent coverage count is invalid")
    if _decimal(snapshot.get("population_stability_index")) < 0:
        raise DiagnosticInputError("population-stability index is invalid")
    if snapshot.get("resource_envelope_status") not in {"ENVELOPE_PASS", "ENVELOPE_FAIL"}:
        raise DiagnosticInputError("resource envelope status is invalid")
    if snapshot.get("email_verification_status") not in {"VERIFIED", "FAILED"}:
        raise DiagnosticInputError("email verification status is invalid")
    if snapshot.get("evidence_integrity_status") not in {"PASS", "FAIL"}:
        raise DiagnosticInputError("evidence integrity status is invalid")
    return value


def _triggered(alert: Mapping[str, Any], snapshot: Mapping[str, Any], thresholds: Mapping[str, Any]) -> bool:
    operator = alert["operator"]
    signal = alert["signal"]
    reference = alert["threshold_ref"]
    if operator == "GREATER_THAN":
        return snapshot[signal] > thresholds[reference]
    if operator == "GREATER_THAN_OR_EQUAL":
        return _decimal(snapshot[signal]) >= _decimal(thresholds[reference])
    if operator == "NOT_EQUAL":
        return snapshot[signal] != reference
    raise DiagnosticInputError("unrecognized high-priority alert operator")


def _result(policy: Mapping[str, Any], triggered: Sequence[Mapping[str, Any]], *, reason: str | None = None) -> dict[str, Any]:
    action_plan = [
        {
            "alert_id": alert["id"],
            "domain": alert["domain"],
            "action_id": alert["action"]["action_id"],
            "action_mode": alert["action"]["mode"],
            "logical_effect": alert["action"]["logical_effect"],
            "owner_review_required": alert["action"]["owner_review_required"],
        }
        for alert in triggered
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "diagnostic_bundle_id": "S18-P02-OFFLINE-DIAGNOSTIC-BUNDLE",
        "contract_id": CONTRACT_ID,
        "fixed_clock": policy.get("fixed_clock", FIXED_CLOCK),
        "decision": ALERT_DECISION if action_plan else HEALTHY_DECISION,
        "triggered_alert_ids": [item["alert_id"] for item in action_plan],
        "action_ids": [item["action_id"] for item in action_plan],
        "action_plan": action_plan,
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
    payload["diagnostic_bundle_sha256"] = hashlib.sha256(_json_bytes(unsigned)).hexdigest()
    return payload


def _fallback(policy: Any, reason: str) -> dict[str, Any]:
    action = FALLBACK_ACTION
    fixed_clock = FIXED_CLOCK
    if isinstance(policy, Mapping):
        fixed_clock = policy.get("fixed_clock", fixed_clock) if isinstance(policy.get("fixed_clock", fixed_clock), str) else fixed_clock
        try:
            alert = _policy_alerts(policy).get(MALFORMED_ALERT_ID)
        except DiagnosticInputError:
            alert = None
        if isinstance(alert, Mapping):
            action = alert["action"]
    alert = {
        "id": MALFORMED_ALERT_ID,
        "domain": "DIAGNOSTIC_CONTRACT",
        "action": action,
    }
    return _result({"fixed_clock": fixed_clock}, [alert], reason=reason)


def evaluate_diagnostic_input(value: Any, dashboards: Any, policy: Any) -> dict[str, Any]:
    """Evaluate a frozen diagnostic input with no external side effects."""
    try:
        _, verified_policy, alert_by_id = validate_documents(dashboards, policy)
        bundle = _validate_input(value, verified_policy)
        snapshot = bundle["signal_snapshot"]
        triggered = [
            alert
            for identifier, alert in alert_by_id.items()
            if identifier != MALFORMED_ALERT_ID and _triggered(alert, snapshot, verified_policy["thresholds"])
        ]
        if len({alert["action"]["action_id"] for alert in triggered}) != len(triggered):
            raise DiagnosticInputError("triggered high-priority actions are not unique")
        return _result(verified_policy, triggered)
    except DiagnosticInputError as exc:
        return _fallback(policy, type(exc).__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an offline ABD S18/P02 diagnostic bundle")
    parser.add_argument("--input", required=True, help="frozen JSON diagnostic input")
    parser.add_argument("--dashboards", default="dashboards.json", help="offline dashboard configuration")
    parser.add_argument("--alerts", default="alerts.json", help="offline high-priority alert policy")
    args = parser.parse_args()
    try:
        value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception:
        value = {}
    try:
        dashboards = json.loads(Path(args.dashboards).read_text(encoding="utf-8"))
    except Exception:
        dashboards = {}
    try:
        policy = json.loads(Path(args.alerts).read_text(encoding="utf-8"))
    except Exception:
        policy = {}
    print(json.dumps(evaluate_diagnostic_input(value, dashboards, policy), ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "ALERT_DECISION", "ALERT_POLICY_ID", "CONTRACT_ID", "DASHBOARD_SET_ID", "DiagnosticInputError",
    "EXTERNAL_EFFECT_BOUNDARY", "FIXED_CLOCK", "HEALTHY_DECISION", "MALFORMED_ALERT_ID", "SAFE_ACTION",
    "evaluate_diagnostic_input", "main", "validate_documents",
]
