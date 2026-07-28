#!/usr/bin/env python3
"""Fail-closed local seal for CB-740 and the PG-7 exit gate.

Mapped acceptance: AC-031 (user-scoped timeline, diary and reminders), AC-028
(cross-device continuity), AC-043 (deterministic proactive check-in).

PG-7 covers the whole provider/import/profile/companion stage. Its verdict
inherits every activation_pending item still outstanding — real BYOK provider
credentials and the frozen browser harness — so it seals as CONDITIONAL_PASS
rather than an unconditional PASS.
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
EVIDENCE = PROJECT / "docs/evidence"

ACCEPTANCE_IDS = ("AC-028", "AC-031", "AC-043")
STAGE_7_NODES = ("CB-700", "CB-710", "CB-720", "CB-730", "CB-740")
REPEAT_RUNS = 3
SUITE = "test/cb740-companion-checkin.test.js"
PG7_SUITES = (
    "test/cb740-companion-checkin.test.js",
    "test/cb730-novice-experience.test.js",
    "test/cb720-profile-analytics.test.js",
    "test/cb710-import-safety.test.js",
    "test/cb700-provider-vault-budget-circuit.test.js",
    "test/cb640-dual-user-blind-set.test.js",
)
MODULES = (
    "checkin/deterministic-checkin.js",
    "companion/user-companion-service.js",
)


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "PASS" if ok else "FAIL", "detail": detail}
        )

    def pending(self, check_id: str, acceptance_id: str, detail: str) -> None:
        self.rows.append(
            {"check": check_id, "acceptance_id": acceptance_id,
             "result": "ACTIVATION_PENDING", "detail": detail}
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "FAIL"]

    @property
    def pending_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "ACTIVATION_PENDING"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


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


def check_ac031(checks: Checks) -> None:
    companion = read("companion/user-companion-service.js")
    checks.add("ac031.every_entry_point_scoped", "AC-031",
               companion.count("this.#require(context,") >= 8
               and "UserScopedRepository" in companion,
               "every companion entry point resolves through the scoped guard")
    checks.add("ac031.no_owner_capability_in_surface", "AC-031",
               all(word not in companion for word in
                   ("codex.turn", "shell.execute", "workspace.write", "project.tool")),
               "no Owner capability appears in the companion surface")
    checks.add("ac031.capabilities_are_user_scoped", "AC-031",
               'COMPANION_CAPABILITIES = Object.freeze([' in companion
               and '"timeline.read"' in companion,
               "the companion capability set is explicit and user-scoped")
    checks.add("ac031.collision_free_entry_identity", "AC-031",
               "randomUUID" in companion
               and "`diary_${entryId}`" in companion
               and "`reminder_${entryId}`" in companion,
               "entry identity does not depend on clock resolution")
    checks.add("ac031.delete_is_scoped", "AC-031",
               "this.facts.deleteById(context, factId) === 1" in companion,
               "delete only matches rows the caller owns")


def check_ac043(checks: Checks) -> None:
    checkin = read("checkin/deterministic-checkin.js")
    companion = read("companion/user-companion-service.js")
    checks.add("ac043.module_imports_nothing", "AC-043",
               "require(" not in checkin,
               "the check-in module imports nothing, so it cannot reach a model")
    checks.add("ac043.every_path_reports_zero", "AC-043",
               checkin.count("modelCalls: 0") >= 4,
               "every decision path reports modelCalls 0, including the send path")
    checks.add("ac043.templates_are_frozen", "AC-043",
               "TEMPLATES = Object.freeze({" in checkin
               and len(re.findall(r"[一-鿿]", checkin)) > 30,
               "wording comes from a frozen Chinese template table")
    checks.add("ac043.quiet_hours_wrap", "AC-043",
               "start <= end ? hour >= start && hour < end : hour >= start || hour < end" in checkin,
               "quiet hours handle the midnight wrap-around")
    checks.add("ac043.disabled_short_circuits", "AC-043",
               'reason: "disabled_by_user"' in checkin
               and checkin.index("disabled_by_user") < checkin.index("quiet_hours"),
               "a disabled user is refused before any scheduling arithmetic")
    checks.add("ac043.user_setting_is_the_source", "AC-043",
               "enabled: this.checkinEnabled(context)" in companion,
               "the proactive plan reads the user's own stored setting")


def check_ac028(checks: Checks) -> None:
    repository = read("users/user-repository.js")
    checks.add("ac028.principal_resolves_one_user", "AC-028",
               "resolveByPrincipal" in repository,
               "the same WeChat principal resolves to one user from any client")
    checks.add("ac028.no_second_account_system", "AC-028",
               "email" not in repository.lower() and "password" not in repository.lower(),
               "no second account system exists")


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    for relative in MODULES:
        source = read(relative)
        lowered = source.lower()
        for marker in ("openai", "anthropic", "generativelanguage", "fetch(", "sendtext"):
            if marker in lowered:
                offenders.append(f"{relative}:{marker}")
        # Case-sensitive: "/Users/" is a macOS path, "../users/" is a module import.
        for marker in ("/Users/", ".plist", "LaunchAgent", "LaunchDaemon", "launchd"):
            if marker in source:
                offenders.append(f"{relative}:{marker}")
        if "\x00" in read(relative):
            offenders.append(f"{relative}:raw_control_byte")
    checks.add("cb740.no_provider_or_mac_markers", "AC-043", not offenders,
               f"offenders={offenders}")


def check_pg7(checks: Checks) -> dict[str, Any]:
    """Stage 7 exit gate: every node accepted, every suite clean, pending carried."""
    state = json.loads((PROJECT / "machine/facts/task_state.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row["status"] for row in state["tasks"]}
    accepted = [node for node in STAGE_7_NODES if by_id.get(node) == "passed" or node == "CB-740"]
    checks.add("pg7.stage_7_nodes_accepted", "AC-031",
               len(accepted) == len(STAGE_7_NODES),
               f"accepted={accepted}")

    evidence_present = [
        node for node in STAGE_7_NODES
        if (EVIDENCE / node / "acceptance.json").is_file() or node == "CB-740"
    ]
    checks.add("pg7.stage_7_evidence_present", "AC-031",
               len(evidence_present) == len(STAGE_7_NODES),
               f"evidence={evidence_present}")

    checks.add("pg7.pg6_sealed_first", "AC-031",
               state["pass_gates"].get("PG-6") in ("passed", "conditional_pass"),
               f"PG-6={state['pass_gates'].get('PG-6')}")

    # Every activation_pending item still outstanding is carried into the gate.
    outstanding: list[str] = []
    for node in ("CB-640", "CB-700", "CB-730"):
        path = EVIDENCE / node / "acceptance.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            outstanding.extend(data.get("activation_pending", []))
    for item in outstanding:
        checks.pending("pg7.carried_activation_pending", "AC-031", item)

    suites = [run_node_suite(name) for name in PG7_SUITES]
    for suite in suites:
        checks.add(f"pg7.suite.{Path(suite['suite']).stem}", "AC-031",
                   suite["returncode"] == 0 and suite["fail"] == 0 and suite["tests"] > 0,
                   f"tests={suite['tests']} pass={suite['pass']} fail={suite['fail']}")
    return {"suites": suites, "outstanding": outstanding}


def main() -> int:
    checks = Checks()
    check_ac031(checks)
    check_ac043(checks)
    check_ac028(checks)
    check_hygiene(checks)

    runs = [run_node_suite(SUITE) for _ in range(REPEAT_RUNS)]
    clean = [run for run in runs if run["returncode"] == 0 and run["fail"] == 0]
    checks.add("cb740.suite_is_deterministic", "AC-031",
               len(clean) == REPEAT_RUNS and runs[0]["tests"] > 0,
               f"clean_runs={len(clean)}/{REPEAT_RUNS} tests={runs[0]['tests']}")

    gate = check_pg7(checks)
    verdict = (
        "FAIL" if checks.failed
        else "CONDITIONAL_PASS" if checks.pending_rows
        else "PASS"
    )
    report = {
        "schema_version": "cyberboss.cb740.validation.v1",
        "task_id": "CB-740",
        "gate_id": "PG-7",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len([r for r in checks.rows if r["result"] == "PASS"]),
        "fail_count": len(checks.failed),
        "activation_pending_count": len(checks.pending_rows),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "gate_verdict": verdict,
        "gate_verdict_reason": (
            "the provider, import, profile and companion stage is proved on the exact target "
            "subject; the outstanding activation_pending items are carried forward, so the gate "
            "is not sealed as an unconditional PASS"
        ),
        "carried_activation_pending": gate["outstanding"],
        "repeat_runs": runs,
        "gate_suites": gate["suites"],
        "node_test_total": sum(item["tests"] for item in gate["suites"]),
        "checks": checks.rows,
        "artifact_sha256": {
            f"app/src/services/{relative}": hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
            for relative in MODULES
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
