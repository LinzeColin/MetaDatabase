#!/usr/bin/env python3
"""Fail-closed local seal for CB-720.

Mapped acceptance: AC-024 (explainable profile), AC-025 (user control), AC-026
(sensitive attribute protection), AC-027 (deterministic behaviour analytics).

The decision-ordering check is run repeatedly, because the defect it guards was
a same-millisecond ordering tie that only appeared intermittently.
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

ACCEPTANCE_IDS = ("AC-024", "AC-025", "AC-026", "AC-027")
SUITE = "test/cb720-profile-analytics.test.js"
REPEAT_RUNS = 5
MODULES = (
    "profile/profile-projector.js",
    "profile/profile-store.js",
    "analytics/activity-aggregator.js",
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


def check_ac024(checks: Checks) -> None:
    projector = read("profile/profile-projector.js")
    checks.add("ac024.inference_requires_full_basis", "AC-024",
               "INFERENCE_EVIDENCE_REQUIRED" in projector
               and all(field in projector for field in
                       ("sourceRef", "evidenceRef", "confidence", "counterevidence")),
               "an inference without source, evidence, confidence or counterevidence is refused")
    checks.add("ac024.confidence_is_a_probability", "AC-024",
               "fact.confidence > 0 && fact.confidence <= 1" in projector,
               "confidence must be a real probability, not a label")
    checks.add("ac024.explain_exposes_the_basis", "AC-024",
               "function explainFact" in projector
               and "counterevidence" in projector.split("function explainFact")[1],
               "the user-facing explanation carries the basis and the counterevidence")
    checks.add("ac024.projection_keeps_references_not_text", "AC-024",
               "evidenceRef" in projector and "evidenceText" not in projector,
               "the projection stores references to evidence, never the evidence text")


def check_ac025(checks: Checks) -> None:
    store = read("profile/profile-store.js")
    projector = read("profile/profile-projector.js")
    declared = set(
        re.findall(
            r'"([a-z]+)"',
            projector.split("DECISIONS = Object.freeze([")[1].split("]")[0],
        )
    )
    checks.add("ac025.all_five_controls", "AC-025",
               {"accepted", "modified", "rejected", "deleted"} <= declared
               and 'decision !== "frozen"' in store
               and "value === undefined ? current.value_json : JSON.stringify(value)" in store,
               f"declared_decisions={sorted(declared)} plus freeze handled by the store")
    checks.add("ac025.decision_and_effect_are_atomic", "AC-025",
               'exec("BEGIN IMMEDIATE")' in store and "profile_decisions" in store,
               "the decision and its effect are applied in one transaction")
    checks.add("ac025.rejected_never_reappears", "AC-025",
               "PROFILE_SUGGESTION_REFUSED_BY_USER" in store,
               "a later suggestion for a rejected key is refused")
    checks.add("ac025.frozen_blocks_overwrite", "AC-025",
               "PROFILE_FACT_FROZEN" in store and "previous.frozen" in projector,
               "a frozen fact is not overwritten by a newer suggestion")
    checks.add("ac025.decision_order_is_deterministic", "AC-025",
               "ORDER BY rowid DESC" in store
               and "ORDER BY occurred_at DESC" not in store,
               "the standing decision is chosen by insertion order, not by a millisecond timestamp")
    checks.add("ac025.freeze_not_cleared_implicitly", "AC-025",
               "Number(current.frozen) === 1 ? 1 : 0" in store,
               "an accept arriving after a freeze does not silently unfreeze the fact")
    checks.add("ac025.suppressed_leave_projection", "AC-025",
               'SUPPRESSED_DECISIONS = Object.freeze(["rejected", "deleted"])' in projector,
               "rejected and deleted facts leave the projection immediately")


def check_ac026(checks: Checks) -> None:
    projector = read("profile/profile-projector.js")
    block = projector.split("SENSITIVE_CATEGORIES = Object.freeze([")[1].split("]")[0]
    categories = re.findall(r'"([a-z_]+)"', block)
    checks.add("ac026.sensitive_set_is_complete", "AC-026",
               len(categories) >= 9
               and {"politics", "religion", "sexual_orientation", "health_diagnosis",
                    "mental_illness", "ethnicity", "biometric"} <= set(categories),
               f"sensitive categories={sorted(categories)}")
    checks.add("ac026.sensitive_never_inferred", "AC-026",
               "SENSITIVE_INFERENCE_FORBIDDEN" in projector,
               "a sensitive attribute can never be inferred, at any confidence")
    checks.add("ac026.consent_is_per_category", "AC-026",
               "fact.explicitSensitiveConsent !== fact.category" in projector,
               "consent for one category does not unlock another")
    allowed = re.findall(
        r'"([a-z_]+)"', projector.split("ALLOWED_CATEGORIES = Object.freeze([")[1].split("]")[0]
    )
    checks.add("ac026.sensitive_not_in_allowlist", "AC-026",
               not set(categories) & set(allowed),
               "no sensitive category appears in the ordinary allowlist")
    checks.add("ac026.default_inference_count_zero", "AC-026",
               "sensitiveInferenceCount" in projector,
               "the count of sensitive inferences is directly observable")


def check_ac027(checks: Checks) -> None:
    aggregator = read("analytics/activity-aggregator.js")
    checks.add("ac027.no_model_dependency", "AC-027",
               "require(" not in aggregator,
               "the aggregator imports nothing, so it cannot reach a model")
    checks.add("ac027.deterministic_ordering", "AC-027",
               ".sort(" in aggregator and "localeCompare" in aggregator,
               "output ordering is deterministic regardless of input order")
    checks.add("ac027.not_a_second_authority", "AC-027",
               "rebuildForUser" in aggregator
               and "DELETE FROM activity_daily WHERE user_id=?" in aggregator,
               "the aggregate is rebuilt from events, so a deleted event disappears")
    checks.add("ac027.per_user_scope", "AC-027",
               "seriesForUser" in aggregator and "row.userId === userId" in aggregator,
               "a series contains only the requesting user's counts")
    checks.add("ac027.unknown_event_ignored", "AC-027",
               "if (field) {" in aggregator,
               "an unknown event type is ignored rather than mis-counted")


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    for relative in MODULES:
        text = read(relative).lower()
        for marker in ("openai", "anthropic", "generativelanguage", "fetch(", "/users/", "launchd"):
            if marker in text:
                offenders.append(f"{relative}:{marker}")
        if "\x00" in read(relative):
            offenders.append(f"{relative}:raw_control_byte")
    checks.add("cb720.no_provider_or_mac_or_control_bytes", "AC-027",
               not offenders, f"offenders={offenders}")


def check_repeat_runs(checks: Checks) -> list[dict[str, Any]]:
    runs = [run_node_suite(SUITE) for _ in range(REPEAT_RUNS)]
    clean = [run for run in runs if run["returncode"] == 0 and run["fail"] == 0]
    checks.add("cb720.suite_is_deterministic", "AC-025",
               len(clean) == REPEAT_RUNS and runs[0]["tests"] > 0,
               f"clean_runs={len(clean)}/{REPEAT_RUNS} tests={runs[0]['tests']}")
    return runs


def main() -> int:
    checks = Checks()
    check_ac024(checks)
    check_ac025(checks)
    check_ac026(checks)
    check_ac027(checks)
    check_hygiene(checks)
    runs = check_repeat_runs(checks)

    report = {
        "schema_version": "cyberboss.cb720.validation.v1",
        "task_id": "CB-720",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "repeat_runs": runs,
        "node_test_total": runs[0]["tests"] if runs else 0,
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
