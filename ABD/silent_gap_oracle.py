from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


ALLOWED_STATUSES = (
    "COVERED",
    "PENDING_PARSE",
    "NON_ADVISABLE",
    "DEGRADED",
    "UNKNOWN",
)
GAP_STATUSES = frozenset(ALLOWED_STATUSES[1:])
STATUS_POLICY = {
    "COVERED": (
        "ALL_SOURCE_RUNTIME_AND_FRESHNESS_GATES_VERIFIED",
        "MONITOR_FRESHNESS_AND_REVALIDATE",
    ),
    "PENDING_PARSE": (
        "SOURCE_PARSER_GATES_PENDING",
        "VERIFY_SOURCE_SCHEMA_AND_PARSER",
    ),
    "NON_ADVISABLE": (
        "SOURCE_MODE_PROHIBITED_OR_BLOCKED",
        "KEEP_MODE_DISABLED_AND_REVIEW_CONTRACT",
    ),
    "DEGRADED": (
        "OPTIONAL_OWNER_VISIBLE_MODE_NOT_READY",
        "OWNER_MAY_CONFIGURE_VISIBLE_OVERLAY",
    ),
    "UNKNOWN": (
        "SOURCE_IDENTITY_OR_PERMISSION_UNKNOWN",
        "BIND_SOURCE_AND_VERIFY_PERMISSION",
    ),
}

CAPABILITY_ID_RE = re.compile(r"^CAP-[A-Z0-9][A-Z0-9._-]{2,127}$")
PROVIDER_ID_RE = re.compile(r"^[A-Z][A-Z0-9._-]{2,63}$")
MODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
ACTION_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SilentGapOracleError(ValueError):
    """Raised when a caller requests an unsafe or ambiguous oracle operation."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _strict_strings(value: Any, *, non_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not non_empty)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def evaluate_gap_threshold(value: Any) -> Dict[str, Any]:
    """Evaluate the exact silent-gap hard gate without binary floating point."""

    if not isinstance(value, str):
        return {
            "status": "FAIL",
            "decision": "BLOCK_COVERAGE_AND_ADVICE",
            "reason_code": "GAP_COUNT_MUST_BE_DECIMAL_STRING",
            "silent_gap_count": None,
        }
    try:
        count = Decimal(value)
    except InvalidOperation:
        return {
            "status": "FAIL",
            "decision": "BLOCK_COVERAGE_AND_ADVICE",
            "reason_code": "GAP_COUNT_MALFORMED",
            "silent_gap_count": None,
        }
    if not count.is_finite() or count < 0:
        return {
            "status": "FAIL",
            "decision": "BLOCK_COVERAGE_AND_ADVICE",
            "reason_code": "GAP_COUNT_NEGATIVE_OR_NONFINITE",
            "silent_gap_count": str(count),
        }
    passed = count == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "decision": "NO_SILENT_GAPS" if passed else "BLOCK_COVERAGE_AND_ADVICE",
        "reason_code": "SILENT_GAP_COUNT_ZERO" if passed else "SILENT_GAP_COUNT_NONZERO",
        "silent_gap_count": str(count),
    }


def classify_source_capability(capability: Mapping[str, Any], budget: Mapping[str, Any]) -> Dict[str, str]:
    """Map one versioned provider-mode contract to one explicit coverage state."""

    capability_id = capability.get("capability_id")
    if not isinstance(capability_id, str) or budget.get("capability_id") != capability_id:
        raise SilentGapOracleError("capability and rate-budget identity must match")
    if capability.get("provider_id") != budget.get("provider_id") or capability.get("mode") != budget.get("mode"):
        raise SilentGapOracleError("provider and mode must match their rate budget")

    state = capability.get("state")
    required = capability.get("required_gate_ids")
    passed = capability.get("passed_gate_ids")
    if not isinstance(state, str) or not _strict_strings(required) or not isinstance(passed, list):
        return {
            "coverage_status": "UNKNOWN",
            "reason_code": STATUS_POLICY["UNKNOWN"][0],
            "recovery_action_id": STATUS_POLICY["UNKNOWN"][1],
        }

    required_set = set(required)
    passed_set = {item for item in passed if isinstance(item, str)}
    production_enabled = capability.get("production_collection_enabled") is True
    runtime_verified = capability.get("runtime_verified") is True
    budget_enabled = budget.get("production_collection_enabled") is True
    dispatch_budget = budget.get("max_dispatches_per_window")
    positive_budget = type(dispatch_budget) is int and dispatch_budget > 0

    if production_enabled and runtime_verified and budget_enabled and positive_budget and required_set <= passed_set:
        status = "COVERED"
    elif state.startswith(("PROHIBITED_", "BLOCKED_")):
        status = "NON_ADVISABLE"
    elif state.startswith("CONDITIONAL_") and "PARSER_FIXTURE_PASS" in required_set - passed_set:
        status = "PENDING_PARSE"
    elif state.startswith("CONDITIONAL_"):
        status = "DEGRADED"
    else:
        status = "UNKNOWN"
    reason, action = STATUS_POLICY[status]
    return {"coverage_status": status, "reason_code": reason, "recovery_action_id": action}


def build_coverage_record(
    capability: Mapping[str, Any],
    budget: Mapping[str, Any],
    *,
    observed_at: str,
) -> Dict[str, Any]:
    classification = classify_source_capability(capability, budget)
    status = classification["coverage_status"]
    action_owner = "OWNER" if status == "DEGRADED" else "SOURCE_GOVERNANCE"
    return {
        "coverage_unit_id": capability["capability_id"],
        "provider_id": capability["provider_id"],
        "mode": capability["mode"],
        "coverage_status": status,
        "reason_code": classification["reason_code"],
        "source_state": capability.get("state"),
        "source_reason_codes": list(capability.get("reason_codes", [])),
        "source_failure_action": capability.get("failure_action"),
        "recovery_action_id": classification["recovery_action_id"],
        "action_owner": action_owner,
        "production_collection_enabled": capability.get("production_collection_enabled"),
        "runtime_verified": capability.get("runtime_verified"),
        "rate_budget_enabled": budget.get("production_collection_enabled"),
        "advice_eligible": False,
        "observed_at": observed_at,
    }


def _finding(
    finding_id: str,
    coverage_unit_id: str,
    reason_code: str,
    recovery_action_id: str,
    *,
    silent: bool,
) -> Dict[str, Any]:
    return {
        "finding_id": finding_id,
        "coverage_unit_id": coverage_unit_id,
        "finding_type": "SILENT_GAP" if silent else "EXPLICIT_INVALIDITY",
        "reason_code": reason_code,
        "recovery_action_id": recovery_action_id,
        "advice_allowed": False,
    }


def audit_coverage(
    expected_units: Any,
    records: Any,
    recovery_actions: Any,
    *,
    fixed_clock: Any,
) -> Dict[str, Any]:
    """Audit exact coverage accounting; malformed or unknown input fails closed."""

    findings: List[Dict[str, Any]] = []
    expected_by_id: Dict[str, Mapping[str, Any]] = {}
    record_by_id: Dict[str, Mapping[str, Any]] = {}
    action_by_id: Dict[str, Mapping[str, Any]] = {}

    if not _valid_timestamp(fixed_clock):
        findings.append(_finding("F0001", "__DASHBOARD__", "INVALID_FIXED_CLOCK", "REBUILD_FROM_PINNED_INPUTS", silent=False))

    if not isinstance(expected_units, list) or not expected_units:
        findings.append(_finding("F0002", "__EXPECTED_UNIVERSE__", "EXPECTED_UNIVERSE_MISSING", "REBUILD_FROM_PINNED_INPUTS", silent=True))
        expected_units = []
    for index, unit in enumerate(expected_units):
        if not isinstance(unit, Mapping):
            findings.append(_finding(f"FE{index:04d}", f"__EXPECTED_{index}__", "MALFORMED_EXPECTED_UNIT", "REBUILD_FROM_PINNED_INPUTS", silent=True))
            continue
        unit_id = unit.get("coverage_unit_id")
        provider_id = unit.get("provider_id")
        mode = unit.get("mode")
        valid = (
            isinstance(unit_id, str)
            and CAPABILITY_ID_RE.fullmatch(unit_id) is not None
            and isinstance(provider_id, str)
            and PROVIDER_ID_RE.fullmatch(provider_id) is not None
            and isinstance(mode, str)
            and MODE_RE.fullmatch(mode) is not None
        )
        if not valid:
            findings.append(_finding(f"FE{index:04d}", str(unit_id), "MALFORMED_EXPECTED_UNIT", "REBUILD_FROM_PINNED_INPUTS", silent=True))
            continue
        if unit_id in expected_by_id:
            findings.append(_finding(f"FE{index:04d}", unit_id, "DUPLICATE_EXPECTED_UNIT", "REBUILD_FROM_PINNED_INPUTS", silent=True))
            continue
        expected_by_id[unit_id] = unit

    if not isinstance(recovery_actions, list):
        findings.append(_finding("F0003", "__RECOVERY_CATALOG__", "RECOVERY_CATALOG_MALFORMED", "REBUILD_FROM_PINNED_INPUTS", silent=False))
        recovery_actions = []
    for index, action in enumerate(recovery_actions):
        if not isinstance(action, Mapping):
            findings.append(_finding(f"FA{index:04d}", "__RECOVERY_CATALOG__", "RECOVERY_ACTION_MALFORMED", "REBUILD_FROM_PINNED_INPUTS", silent=False))
            continue
        action_id = action.get("action_id")
        valid = (
            isinstance(action_id, str)
            and ACTION_ID_RE.fullmatch(action_id) is not None
            and isinstance(action.get("owner"), str)
            and bool(action.get("owner"))
            and isinstance(action.get("action_zh"), str)
            and bool(action.get("action_zh"))
            and action.get("changes_external_state") is False
        )
        if not valid or action_id in action_by_id:
            findings.append(_finding(f"FA{index:04d}", str(action_id), "RECOVERY_ACTION_MALFORMED_OR_DUPLICATE", "REBUILD_FROM_PINNED_INPUTS", silent=False))
            continue
        action_by_id[action_id] = action

    if not isinstance(records, list):
        findings.append(_finding("F0004", "__RECORDS__", "COVERAGE_RECORDS_MALFORMED", "REBUILD_FROM_PINNED_INPUTS", silent=True))
        records = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            findings.append(_finding(f"FR{index:04d}", f"__RECORD_{index}__", "MALFORMED_COVERAGE_RECORD", "REBUILD_FROM_PINNED_INPUTS", silent=False))
            continue
        unit_id = record.get("coverage_unit_id")
        if not isinstance(unit_id, str) or CAPABILITY_ID_RE.fullmatch(unit_id) is None:
            findings.append(_finding(f"FR{index:04d}", str(unit_id), "MALFORMED_COVERAGE_UNIT_ID", "REBUILD_FROM_PINNED_INPUTS", silent=False))
            continue
        if unit_id in record_by_id:
            findings.append(_finding(f"FR{index:04d}", unit_id, "DUPLICATE_COVERAGE_RECORD", "REBUILD_FROM_PINNED_INPUTS", silent=False))
            continue
        record_by_id[unit_id] = record

    for unit_id in sorted(expected_by_id):
        if unit_id not in record_by_id:
            findings.append(_finding(f"FM-{unit_id}", unit_id, "EXPECTED_COVERAGE_UNIT_MISSING", "REBUILD_FROM_PINNED_INPUTS", silent=True))

    for unit_id in sorted(record_by_id):
        record = record_by_id[unit_id]
        expected = expected_by_id.get(unit_id)
        if expected is None:
            findings.append(_finding(f"FU-{unit_id}", unit_id, "UNDECLARED_COVERAGE_UNIT_PRESENT", "QUARANTINE_UNDECLARED_UNIT", silent=False))
            continue
        if record.get("provider_id") != expected.get("provider_id") or record.get("mode") != expected.get("mode"):
            findings.append(_finding(f"FI-{unit_id}", unit_id, "COVERAGE_UNIT_IDENTITY_MISMATCH", "REBUILD_FROM_PINNED_INPUTS", silent=False))

        status = record.get("coverage_status")
        if status not in ALLOWED_STATUSES:
            findings.append(_finding(f"FS-{unit_id}", unit_id, "UNKNOWN_COVERAGE_STATUS", "QUARANTINE_UNDECLARED_UNIT", silent=False))
            continue
        expected_reason, expected_action = STATUS_POLICY[status]
        if record.get("reason_code") != expected_reason:
            findings.append(_finding(f"FQ-{unit_id}", unit_id, "MISSING_OR_INVALID_REASON_CODE", expected_action, silent=False))
        action_id = record.get("recovery_action_id")
        if action_id != expected_action or action_id not in action_by_id:
            findings.append(_finding(f"FX-{unit_id}", unit_id, "MISSING_OR_INVALID_RECOVERY_ACTION", expected_action, silent=False))
        if record.get("action_owner") not in {"SOURCE_GOVERNANCE", "OWNER"}:
            findings.append(_finding(f"FO-{unit_id}", unit_id, "MISSING_OR_INVALID_ACTION_OWNER", expected_action, silent=False))
        if not isinstance(record.get("source_state"), str) or not record.get("source_state"):
            findings.append(_finding(f"FT-{unit_id}", unit_id, "SOURCE_STATE_MISSING", expected_action, silent=False))
        if not _strict_strings(record.get("source_reason_codes")):
            findings.append(_finding(f"FC-{unit_id}", unit_id, "SOURCE_REASON_CODES_MISSING", expected_action, silent=False))
        if not isinstance(record.get("source_failure_action"), str) or not record.get("source_failure_action"):
            findings.append(_finding(f"FF-{unit_id}", unit_id, "SOURCE_FAILURE_ACTION_MISSING", expected_action, silent=False))
        if not _valid_timestamp(record.get("observed_at")):
            findings.append(_finding(f"FD-{unit_id}", unit_id, "OBSERVATION_TIMESTAMP_INVALID", expected_action, silent=False))
        if record.get("advice_eligible") is not False:
            findings.append(_finding(f"FV-{unit_id}", unit_id, "ADVICE_ELIGIBILITY_NOT_FAIL_CLOSED", expected_action, silent=False))

        active_flags = (
            record.get("production_collection_enabled") is True,
            record.get("runtime_verified") is True,
            record.get("rate_budget_enabled") is True,
        )
        if status == "COVERED" and not all(active_flags):
            findings.append(_finding(f"FG-{unit_id}", unit_id, "COVERED_WITHOUT_ALL_RUNTIME_GATES", expected_action, silent=False))
        if status in GAP_STATUSES and any(active_flags):
            findings.append(_finding(f"FH-{unit_id}", unit_id, "GAP_RECORD_HAS_ACTIVE_RUNTIME_FLAG", expected_action, silent=False))

    findings.sort(key=lambda row: (row["finding_id"], row["coverage_unit_id"]))
    silent_gap_count = sum(row["finding_type"] == "SILENT_GAP" for row in findings)
    counts = {status: 0 for status in ALLOWED_STATUSES}
    for unit_id, record in record_by_id.items():
        if unit_id in expected_by_id and record.get("coverage_status") in counts:
            counts[record["coverage_status"]] += 1
    explicit_gap_count = sum(counts[status] for status in GAP_STATUSES)
    status = "PASS" if not findings and silent_gap_count == 0 else "FAIL"
    report = {
        "schema_version": "1.0.0",
        "oracle_id": "ABD-S05-P04-SILENT-GAP-ORACLE",
        "fixed_clock": fixed_clock,
        "status": status,
        "decision": "EXPLICIT_GAPS_ONLY_NO_SILENT_GAPS" if status == "PASS" else "BLOCK_COVERAGE_AND_ADVICE",
        "expected_unit_count": len(expected_by_id),
        "represented_unit_count": len(set(expected_by_id) & set(record_by_id)),
        "silent_gap_count": silent_gap_count,
        "explicit_gap_count": explicit_gap_count,
        "covered_count": counts["COVERED"],
        "status_counts": counts,
        "finding_count": len(findings),
        "findings": findings,
        "advice_allowed": False,
        "external_action_performed": False,
        "input_sha256": sha256_json(
            {
                "expected_units": expected_units,
                "records": records,
                "recovery_actions": recovery_actions,
                "fixed_clock": fixed_clock,
            }
        ),
    }
    report["decision_sha256"] = sha256_json(report)
    return report


def _strict_json_load(path: Path) -> Any:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SilentGapOracleError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=reject_duplicates)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit an ABD S05/P04 coverage dashboard offline.")
    parser.add_argument("dashboard", nargs="?", default="coverage_dashboard.json")
    args = parser.parse_args(argv)
    dashboard = _strict_json_load(Path(args.dashboard))
    report = audit_coverage(
        dashboard.get("expected_coverage_units"),
        dashboard.get("coverage_records"),
        dashboard.get("recovery_actions"),
        fixed_clock=dashboard.get("fixed_at"),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
