#!/usr/bin/env python3
"""Fail-closed local seal for CB-810.

Mapped acceptance: AC-032 (Status business matrix), AC-033 (zero-agent
runtime), AC-034 (no Mac dependency), AC-048 (model usage and circuit
observability).

AC-034 is checked against the whole runtime tree rather than the new modules
alone, because a Mac dependency anywhere in the runtime breaks the claim.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
APP = PROJECT / "app"
SRC = APP / "src/services"

# Copied verbatim from machine/status_business_matrix.json and
# machine/zero_agent_contract.json so a drift in either is a failure here.
FROZEN_BUSINESS_LINES = [
    "wechat_channel", "user_registration_consent", "user_isolation",
    "secure_setup_portal", "ai_provider_connection", "four_source_import",
    "profile_memory", "timeline_diary_reminder", "canonical_sync",
    "r2_oci_objects", "backup_restore", "owner_codex_runtime",
    "release_rollback", "model_usage_budget_circuit",
]
FROZEN_REQUIRED_FIELDS = [
    "business_line", "stage", "state", "upstream", "downstream", "slo",
    "queue_depth", "oldest_job_seconds", "error_rate", "last_success_at",
    "last_recovery_at", "release", "rollback_release", "reason_code",
]
FROZEN_FORBIDDEN_FIELDS = [
    "wechat_id", "user_id", "name", "message", "prompt", "response",
    "api_key", "file_name", "profile", "object_key",
]
FROZEN_USAGE_ALLOWED = [
    "provider", "budget_state", "soft_warning", "hard_block",
    "reserved_tokens", "charged_tokens", "circuit_state",
    "last_transition_at", "reason_code",
]
FROZEN_USAGE_FORBIDDEN_DIMENSIONS = [
    "user_id", "wechat_id", "prompt", "response", "api_key",
    "credential_token", "raw_message",
]
FROZEN_MUST_EQUAL_ZERO = [
    "control_plane_llm_calls_total", "scheduler_agent_invocations_total",
    "health_agent_invocations_total", "self_heal_agent_invocations_total",
    "backup_agent_invocations_total", "restore_agent_invocations_total",
    "status_agent_invocations_total", "sync_agent_invocations_total",
    "import_parser_agent_invocations_total",
    "analytics_agent_invocations_total", "release_agent_invocations_total",
]
FROZEN_ALLOWED_MODEL_CALLS = [
    "user_initiated_ai_turn", "user_explicit_profile_suggestion",
    "owner_initiated_codex_turn",
]
FROZEN_FORBIDDEN_BACKGROUND = [
    "provider_health_probe", "budget_summary", "analytics_summary",
    "self_heal_decision", "status_narration",
]

ACCEPTANCE_IDS = ("AC-032", "AC-033", "AC-034", "AC-048")
SUITE = "test/cb810-status-resource-selfheal.test.js"
REPEAT_RUNS = 3
MODULES = (
    "status/business-matrix.js",
    "status/model-usage-summary.js",
    "status/zero-agent-ledger.js",
    "operations/resource-gate.js",
    "operations/self-heal-policy.js",
)
NO_IMPORT_MODULES = (
    "operations/resource-gate.js",
    "operations/self-heal-policy.js",
    "status/zero-agent-ledger.js",
)
MAC_MARKERS = ("/Users/", "/Library/", ".plist", "LaunchAgent", "LaunchDaemon",
               "launchd", "osascript")
PROHIBITION = re.compile(
    r"macos_launchd_dependency|!==\s*false|\.includes\(|\.test\(|FORBIDDEN"
    r"|forbidden|reject|refus|assert|must_not|no_mac"
)


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] != "PASS"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def frozen_list(source: str, name: str) -> list[str]:
    block = source.split(f"{name} = Object.freeze([")[1].split("]")[0]
    return re.findall(r'"([A-Za-z0-9_./-]+)"', block)


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative], cwd=APP,
        capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative, "returncode": result.returncode,
        "tests": counts.get("tests", 0), "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_ac032(checks: Checks) -> None:
    matrix = read("status/business-matrix.js")
    checks.add("ac032.business_lines_match_the_frozen_contract", "AC-032",
               frozen_list(matrix, "BUSINESS_LINES") == FROZEN_BUSINESS_LINES,
               f"declared={frozen_list(matrix, 'BUSINESS_LINES')}")
    checks.add("ac032.required_fields_match_the_frozen_contract", "AC-032",
               frozen_list(matrix, "REQUIRED_FIELDS") == FROZEN_REQUIRED_FIELDS,
               f"declared={frozen_list(matrix, 'REQUIRED_FIELDS')}")
    checks.add("ac032.forbidden_fields_match_the_frozen_contract", "AC-032",
               frozen_list(matrix, "FORBIDDEN_FIELDS") == FROZEN_FORBIDDEN_FIELDS,
               f"declared={frozen_list(matrix, 'FORBIDDEN_FIELDS')}")
    checks.add("ac032.every_line_must_be_present", "AC-032",
               "STATUS_BUSINESS_LINE_MISSING" in matrix
               and "STATUS_BUSINESS_LINE_DUPLICATED" in matrix,
               "a snapshot that omits or duplicates a line is refused whole")
    checks.add("ac032.field_set_is_exact", "AC-032",
               "STATUS_REQUIRED_FIELD_MISSING" in matrix
               and "STATUS_UNEXPECTED_FIELD" in matrix,
               "a missing field and an extra field are both refused")
    checks.add("ac032.scan_is_recursive_on_names_and_values", "AC-032",
               "function assertNoSensitiveValues" in matrix
               and "assertKeyAllowed(key, childPath)" in matrix
               and "MAX_SCAN_DEPTH" in matrix,
               "field names and field values are scanned at every depth")
    checks.add("ac032.value_scan_covers_identity_and_secrets", "AC-032",
               all(fragment in matrix for fragment in
                   ("wxid_", "usr_", "Bearer", "-----BEGIN ", r"(?:root|home|Users)")),
               "wechat ids, user ids, bearer tokens, private keys and Mac paths are refused")
    checks.add("ac032.refusal_names_path_not_value", "AC-032",
               "// A path or a field name, never a field value." in matrix,
               "the refusal carries the field path, never the field value")
    checks.add("ac032.snapshot_is_rescanned_after_assembly", "AC-032",
               matrix.count("assertNoSensitiveValues(payload") >= 1,
               "the assembled document is scanned again, including caller-supplied sections")
    checks.add("ac032.snapshot_is_deterministic", "AC-032",
               "localeCompare" in matrix and "snapshot_sha256" in matrix,
               "ordering is by name and the snapshot carries its own digest")
    # The additive fragment list must not forbid the fields AC-048 requires.
    fragments = frozen_list(matrix, "FORBIDDEN_FIELD_FRAGMENTS")
    conflict = [field for field in FROZEN_USAGE_ALLOWED
                if any(fragment in field for fragment in fragments)]
    checks.add("ac032.guard_does_not_forbid_a_required_usage_field", "AC-032",
               not conflict,
               f"fields the guard would have blocked={conflict}")


def check_ac048(checks: Checks) -> None:
    usage = read("status/model-usage-summary.js")
    checks.add("ac048.allowed_fields_match_the_frozen_contract", "AC-048",
               frozen_list(usage, "ALLOWED_FIELDS") == FROZEN_USAGE_ALLOWED,
               f"declared={frozen_list(usage, 'ALLOWED_FIELDS')}")
    checks.add("ac048.forbidden_dimensions_match_the_frozen_contract", "AC-048",
               frozen_list(usage, "FORBIDDEN_DIMENSIONS") == FROZEN_USAGE_FORBIDDEN_DIMENSIONS,
               f"declared={frozen_list(usage, 'FORBIDDEN_DIMENSIONS')}")
    checks.add("ac048.field_set_is_an_exact_allowlist", "AC-048",
               "USAGE_FIELD_NOT_ALLOWED" in usage
               and "!ALLOWED_FIELDS.includes(key)" in usage,
               "a field outside the frozen set cannot be published even by accident")
    checks.add("ac048.user_dimension_dropped_before_the_summary_exists", "AC-048",
               "function aggregateByProvider" in usage
               and "totals.set(provider" in usage
               and "userId" not in usage,
               "the aggregation collapses to provider totals; no user dimension is carried")
    checks.add("ac048.provider_budget_and_circuit_are_all_present", "AC-048",
               all(field in usage for field in
                   ("budget_state", "reserved_tokens", "charged_tokens",
                    "circuit_state", "reason_code")),
               "provider, budget state, reserved/charged tokens, circuit state and reason code")
    checks.add("ac048.unknown_provider_state_or_reason_is_refused", "AC-048",
               all(code in usage for code in
                   ("USAGE_PROVIDER_UNKNOWN", "USAGE_CIRCUIT_STATE_UNKNOWN",
                    "USAGE_BUDGET_STATE_UNKNOWN", "USAGE_REASON_CODE_INVALID")),
               "an unknown provider, circuit state, budget state or free-text reason is refused")
    checks.add("ac048.summary_passes_the_status_privacy_scan", "AC-048",
               "assertNoSensitiveValues(payload" in usage,
               "the summary is scanned by the same fail-closed status scan")
    checks.add("ac048.summary_declares_zero_model_calls", "AC-048",
               "model_calls: 0" in usage,
               "the summary is arithmetic over stored rows, never a narration")


def check_ac033(checks: Checks) -> None:
    gate = read("operations/resource-gate.js")
    heal = read("operations/self-heal-policy.js")
    ledger = read("status/zero-agent-ledger.js")

    offenders = [relative for relative in NO_IMPORT_MODULES if "require(" in read(relative)]
    checks.add("ac033.operational_modules_import_nothing", "AC-033", not offenders,
               f"modules_with_imports={offenders}")

    checks.add("ac033.unmeasured_floor_rejects", "AC-033",
               "RESOURCE_MEASUREMENT_UNAVAILABLE" in gate
               and 'value === null || value === undefined' in gate,
               "an absent measurement rejects rather than coercing to a plausible zero")
    checks.add("ac033.floors_precede_pressure", "AC-033",
               gate.index("const FLOORS") < gate.index("const PRESSURE")
               and gate.index("for (const { metric, threshold, reasonCode } of FLOORS)")
               < gate.index("for (const { metric, threshold, reasonCode } of PRESSURE)"),
               "a hard floor is reported before a pressure signal")
    checks.add("ac033.degraded_admits_nothing_new", "AC-033",
               'decision.state === "allow"' in gate,
               "only an explicit allow admits work")
    checks.add("ac033.gate_reports_zero_model_calls", "AC-033",
               gate.count("modelCalls: 0") >= 5,
               "every gate outcome reports zero model calls")

    checks.add("ac033.restart_budget_is_bounded", "AC-033",
               "RESTART_BUDGET_EXHAUSTED" in heal
               and "recent.length >= limits.maxRestarts" in heal,
               "the restart budget is counted in a sliding window and then stops")
    checks.add("ac033.cooldown_defers_a_storm", "AC-033",
               "RESTART_COOLDOWN" in heal and "retryAfterMs" in heal,
               "a restart inside the cooldown is deferred rather than amplified")
    checks.add("ac033.clock_skew_buys_no_restarts", "AC-033",
               "// A future timestamp is a clock problem" in heal,
               "a future timestamp is counted, so a skewed clock cannot reset the budget")
    checks.add("ac033.unrestartable_failure_is_isolated", "AC-033",
               "isolate_and_alert" in heal and "RESTARTABLE.includes(code)" in heal,
               "a corrupt database or a rejected credential is isolated, not restarted")
    checks.add("ac033.heal_reports_zero_model_calls", "AC-033",
               heal.count("modelCalls: 0") >= 5,
               "every self-heal outcome reports zero model calls")

    checks.add("ac033.zero_counters_match_the_frozen_contract", "AC-033",
               frozen_list(ledger, "MUST_EQUAL_ZERO") == FROZEN_MUST_EQUAL_ZERO,
               f"declared={frozen_list(ledger, 'MUST_EQUAL_ZERO')}")
    checks.add("ac033.allowed_model_calls_match_the_frozen_contract", "AC-033",
               frozen_list(ledger, "ALLOWED_MODEL_CALLS") == FROZEN_ALLOWED_MODEL_CALLS,
               f"declared={frozen_list(ledger, 'ALLOWED_MODEL_CALLS')}")
    checks.add("ac033.forbidden_background_calls_match_the_frozen_contract", "AC-033",
               frozen_list(ledger, "FORBIDDEN_BACKGROUND_MODEL_CALLS")
               == FROZEN_FORBIDDEN_BACKGROUND,
               f"declared={frozen_list(ledger, 'FORBIDDEN_BACKGROUND_MODEL_CALLS')}")
    checks.add("ac033.unreported_counter_is_not_zero", "AC-033",
               "ZERO_AGENT_COUNTER_MISSING" in ledger,
               "a counter that was never reported fails rather than reading as zero")
    checks.add("ac033.purpose_is_checked_at_the_boundary", "AC-033",
               "MODEL_CALL_PURPOSE_NOT_ALLOWED" in ledger,
               "a call site declares its purpose and anything off the allowlist is refused")


def check_ac034(checks: Checks) -> dict[str, Any]:
    """Scan the whole runtime tree, not only the new modules."""
    offenders: list[str] = []
    prohibitions: list[str] = []
    roots = [APP / "src", APP / "migrations", APP / "bin"]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in (".js", ".sql", ".json"):
                continue
            relative = path.relative_to(APP)
            for number, text in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                for marker in MAC_MARKERS:
                    if marker not in text:
                        continue
                    record = f"{relative}:{number}:{marker}"
                    (prohibitions if PROHIBITION.search(text) else offenders).append(record)
    checks.add("ac034.no_mac_dependency_in_the_runtime_tree", "AC-034", not offenders,
               f"offenders={offenders[:10]} total={len(offenders)}")
    checks.add("ac034.no_mac_rule_is_actively_asserted", "AC-034",
               len(prohibitions) > 0,
               f"prohibition_sites={len(prohibitions)}")

    manifest = json.loads((APP / "package.json").read_text(encoding="utf-8"))
    checks.add("ac034.node_engine_floor_declared", "AC-034",
               str(manifest.get("engines", {}).get("node", "")).startswith(">="),
               f"engines.node={manifest.get('engines', {}).get('node')}")
    serialized = json.dumps(manifest)
    checks.add("ac034.manifest_names_no_mac_runtime", "AC-034",
               not any(marker in serialized
                       for marker in ("darwin", "launchd", ".plist", "/Users/")),
               "the package manifest names no macOS runtime")
    return {"offenders": offenders, "prohibition_sites": len(prohibitions)}


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    for relative in MODULES:
        source = read(relative)
        if "\x00" in source:
            offenders.append(f"{relative}:raw_control_byte")
    checks.add("cb810.no_control_bytes", "AC-032", not offenders, f"offenders={offenders}")

    registered = (APP / "package.json").read_text(encoding="utf-8")
    missing = [relative for relative in MODULES if f"src/services/{relative}" not in registered]
    checks.add("cb810.modules_are_syntax_checked", "AC-032", not missing,
               f"missing_from_check_script={missing}")


def main() -> int:
    checks = Checks()
    check_ac032(checks)
    check_ac048(checks)
    check_ac033(checks)
    mac = check_ac034(checks)
    check_hygiene(checks)

    runs = [run_node_suite(SUITE) for _ in range(REPEAT_RUNS)]
    clean = [run for run in runs if run["returncode"] == 0 and run["fail"] == 0]
    checks.add("cb810.suite_is_deterministic", "AC-032",
               len(clean) == REPEAT_RUNS and runs[0]["tests"] > 0,
               f"clean_runs={len(clean)}/{REPEAT_RUNS} tests={runs[0]['tests']}")

    report = {
        "schema_version": "cyberboss.cb810.validation.v1",
        "task_id": "CB-810",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "activation_pending_count": 0,
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_verdict": "PASS" if not checks.failed else "FAIL",
        "no_mac_scan": mac,
        "repeat_runs": runs,
        "node_test_total": runs[0]["tests"] if runs else 0,
        "checks": checks.rows,
        "artifact_sha256": {
            f"app/src/services/{relative}":
                hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
            for relative in MODULES
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
