"""Offline, fail-closed post-release probe evaluator for ABD S18/P01."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


PIPELINE_ID = "S18-P01-SAFE-RELEASE-PIPELINE"
CANARY_POLICY_ID = "S18-P01-CANARY-POLICY"
REQUIRED_PROBE_IDS = (
    "HEALTH_PROBE",
    "NUMERIC_CROSS_IMPLEMENTATION",
    "FROZEN_REPLAY_ACTION_MATCH",
    "SILENT_COVERAGE_GAP_NONINCREASE",
    "MODEL_DRIFT_WITHIN_STOP_LINE",
    "SECURITY_HIGH_CRITICAL_ZERO",
    "LEDGER_AND_EVIDENCE_INTEGRITY",
)
SAFE_ACTION = "NO_RECOMMENDATION_NO_ORDER"
PROMOTE_DECISION = "PROMOTE_CANDIDATE_KEEP_LIVE_ADVICE_DISABLED"
ROLLBACK_DECISION = "AUTO_ROLL_BACK_TO_PREVIOUS_SLOT_KEEP_ADVICE_DISABLED"
UNKNOWN_TRIGGER = "UNKNOWN_OR_MALFORMED_PROBE"
ALLOWED_DELTAS = {"-0.0001", "0", "0.0001"}


class ProbeInputError(ValueError):
    """Raised only while converting a malformed frozen probe bundle."""


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _validate_bundle(value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version", "candidate_slot", "previous_slot", "pipeline_id", "canary_policy_id", "probe_results",
        "probability_delta", "odds_tick_delta", "fixed_clock",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise ProbeInputError("probe bundle must have an exact non-float schema")
    if value["schema_version"] != "1.0.0":
        raise ProbeInputError("unsupported probe bundle schema")
    if value["pipeline_id"] != PIPELINE_ID or value["canary_policy_id"] != CANARY_POLICY_ID:
        raise ProbeInputError("unrecognized release control identifiers")
    if value["candidate_slot"] not in {"blue", "green"} or value["previous_slot"] not in {"blue", "green"}:
        raise ProbeInputError("slots must be blue or green")
    if value["candidate_slot"] == value["previous_slot"]:
        raise ProbeInputError("candidate and previous slots must differ")
    if value["probability_delta"] not in ALLOWED_DELTAS or value["odds_tick_delta"] != -1:
        raise ProbeInputError("adverse numeric boundary vector is not exact")
    if not isinstance(value["fixed_clock"], str) or not value["fixed_clock"].endswith("+10:00"):
        raise ProbeInputError("fixed clock is unavailable")
    probes = value["probe_results"]
    if not isinstance(probes, Mapping) or set(probes) != set(REQUIRED_PROBE_IDS):
        raise ProbeInputError("probe identifiers must be exact")
    if any(status not in {"PASS", "FAIL"} for status in probes.values()):
        raise ProbeInputError("probe statuses must be PASS or FAIL")
    return value


def _fail_closed(previous_slot: str, trigger: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "decision": ROLLBACK_DECISION,
        "logical_active_slot": previous_slot if previous_slot in {"blue", "green"} else "UNKNOWN_PREVIOUS_SLOT",
        "logical_auto_rollback": True,
        "rollback_trigger": trigger,
        "action": SAFE_ACTION,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "production_state_changed": False,
        "external_runtime_accessed": False,
        "real_time_wait_performed": False,
        "incremental_cash_spent_aud": "0.00",
    }


def evaluate_probe_bundle(value: Any) -> dict[str, Any]:
    """Return the only safe logical release outcome for a frozen probe bundle."""
    previous_slot = value.get("previous_slot") if isinstance(value, Mapping) else None
    try:
        bundle = _validate_bundle(value)
    except ProbeInputError:
        return _fail_closed(previous_slot if isinstance(previous_slot, str) else "UNKNOWN_PREVIOUS_SLOT", UNKNOWN_TRIGGER)
    failed = [identifier for identifier in REQUIRED_PROBE_IDS if bundle["probe_results"][identifier] != "PASS"]
    if failed:
        return _fail_closed(str(bundle["previous_slot"]), failed[0])
    return {
        "schema_version": "1.0.0",
        "decision": PROMOTE_DECISION,
        "logical_active_slot": bundle["candidate_slot"],
        "logical_auto_rollback": False,
        "rollback_trigger": None,
        "action": SAFE_ACTION,
        "recommendation_generated_or_enabled": False,
        "order_submission_enabled": False,
        "production_state_changed": False,
        "external_runtime_accessed": False,
        "real_time_wait_performed": False,
        "incremental_cash_spent_aud": "0.00",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an offline ABD S18/P01 probe bundle")
    parser.add_argument("--input", required=True, help="frozen JSON probe bundle")
    args = parser.parse_args()
    try:
        value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception:
        value = {}
    print(json.dumps(evaluate_probe_bundle(value), ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "CANARY_POLICY_ID", "PIPELINE_ID", "PROMOTE_DECISION", "ProbeInputError", "REQUIRED_PROBE_IDS",
    "ROLLBACK_DECISION", "SAFE_ACTION", "UNKNOWN_TRIGGER", "evaluate_probe_bundle", "main",
]
