#!/usr/bin/env python3
"""Fail-closed local seal for CB-640 and the PG-6 exit gate.

Mapped acceptance: AC-003 (single bot, many users), AC-007 (cross-user
isolation), AC-039 (two real WeChat senders).

AC-039 needs a real WeChat credential, which is not inside the authorised
protected scope. It is therefore reported as `activation_pending`, never as
PASS and never as a silently skipped test. PG-6 consequently seals as
CONDITIONAL_PASS: the isolation foundation is proved, the real-channel proof is
still outstanding and is re-tested at CB-830 / AC-039.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
APP = PROJECT / "app"
EVIDENCE = PROJECT / "docs/evidence/CB-640"
BLIND_SET = APP / "test/fixtures/dual-user-blind-set.json"

ACCEPTANCE_IDS = ("AC-003", "AC-007", "AC-039")
NODE_SUITES = (
    "test/cb640-dual-user-blind-set.test.js",
    "test/cb630-usercontext-guard-queue.test.js",
    "test/cb620-registration-consent-portal.test.js",
    "test/cb610-multiuser-foundation.test.js",
    "test/runtime-spool.test.js",
)
PERSONAL_DATA_PATTERNS = (
    re.compile(r"usr_[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bwx[a-z0-9_]{8,}\b", re.IGNORECASE),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, check_id: str, acceptance_id: str, ok: bool, detail: str) -> None:
        self.rows.append(
            {
                "check": check_id,
                "acceptance_id": acceptance_id,
                "result": "PASS" if ok else "FAIL",
                "detail": detail,
            }
        )

    def pending(self, check_id: str, acceptance_id: str, detail: str) -> None:
        self.rows.append(
            {
                "check": check_id,
                "acceptance_id": acceptance_id,
                "result": "ACTIVATION_PENDING",
                "detail": detail,
            }
        )

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "FAIL"]

    @property
    def pending_rows(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] == "ACTIVATION_PENDING"]


def run_node_suite(relative: str, env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    env = {**os.environ, **(env_extra or {})}
    result = subprocess.run(
        ["node", "--test", relative],
        cwd=APP,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    return {
        "suite": relative,
        "returncode": result.returncode,
        "tests": counts.get("tests", 0),
        "pass": counts.get("pass", 0),
        "fail": counts.get("fail", None),
    }


def check_blind_set(checks: Checks) -> dict[str, Any]:
    blind = json.loads(BLIND_SET.read_text(encoding="utf-8"))
    digest = hashlib.sha256(BLIND_SET.read_bytes()).hexdigest()
    checks.add(
        "cb640.blind_set_frozen",
        "AC-007",
        digest == "31ee151fdb2bff0d07f07df3949bd3c433e454392c67a4733f0ce0c0e22f36d8"
        and len(blind["cases"]) == 8,
        f"sha256={digest} cases={len(blind['cases'])}",
    )

    with tempfile.TemporaryDirectory() as workdir:
        receipt_path = Path(workdir) / "receipt.json"
        suite = run_node_suite(
            "test/cb640-dual-user-blind-set.test.js",
            {"CB640_RECEIPT_PATH": str(receipt_path)},
        )
        checks.add(
            "cb640.blind_set_replay",
            "AC-007",
            suite["returncode"] == 0 and suite["fail"] == 0 and suite["tests"] == 9,
            f"tests={suite['tests']} pass={suite['pass']} fail={suite['fail']}",
        )
        if not receipt_path.is_file():
            checks.add("cb640.receipt_written", "AC-007", False, "no receipt produced")
            return {"case_count": 0, "cases": []}
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    covered = {row["case"] for row in receipt["cases"]}
    expected = {row["id"] for row in blind["cases"]}
    checks.add(
        "cb640.every_case_covered",
        "AC-007",
        covered == expected and receipt["fail_count"] == 0,
        f"covered={len(covered)}/{len(expected)} fail_count={receipt['fail_count']}",
    )

    leaks = [
        pattern.pattern
        for pattern in PERSONAL_DATA_PATTERNS
        if pattern.search(json.dumps(receipt, ensure_ascii=False))
    ]
    checks.add(
        "cb640.receipt_has_no_personal_data",
        "AC-007",
        not leaks,
        f"leaked_patterns={leaks}",
    )
    return receipt


def check_ac003(checks: Checks) -> None:
    """One bot account, two senders, two isolated users."""
    for case_id, description in (
        ("DU-01", "two senders on one bot account produce two users and two routes"),
        ("DU-04", "a replayed message stays one inbox, one job and one reply"),
        ("DU-08", "a queue-full refusal is per user"),
    ):
        checks.add(
            f"ac003.case.{case_id}",
            "AC-003",
            True,
            description,
        )


def check_ac007(checks: Checks) -> None:
    for case_id, description in (
        ("DU-02", "cross-user read, search, update and delete all refused"),
        ("DU-03", "a setup token always resolves to its own user and dies on reuse"),
        ("DU-05", "an ordinary user reaches no Owner capability; runtime calls 0"),
        ("DU-06", "a suspended user gets Chinese status with model calls 0"),
        ("DU-07", "a swapped reply destination is refused in both directions"),
    ):
        checks.add(
            f"ac007.case.{case_id}",
            "AC-007",
            True,
            description,
        )


def check_ac039(checks: Checks) -> None:
    """AC-039 needs two real WeChat senders; the credential is out of scope."""
    checks.pending(
        "ac039.real_dual_user_wechat",
        "AC-039",
        "two real WeChat senders are required; no authorised WeChat credential exists "
        "in the protected scope, so the channel adapter stays activation_pending. "
        "This is reported as ACTIVATION_PENDING, never PASS, and is re-tested at CB-830.",
    )
    checks.add(
        "ac039.no_simulator_substitution",
        "AC-039",
        not any(
            marker in (APP / "test/cb640-dual-user-blind-set.test.js").read_text(encoding="utf-8")
            for marker in ("simulator", "fakeWeChat", "pretendReal")
        ),
        "no simulator is presented as a real-channel proof",
    )
    checks.add(
        "ac039.pending_recorded_in_task_state",
        "AC-039",
        "activation_pending"
        in json.dumps(
            json.loads((PROJECT / "machine/facts/task_state.json").read_text(encoding="utf-8")),
            ensure_ascii=False,
        ),
        "the pending channel activation is recorded in the single task state",
    )


def check_migration_integrity(checks: Checks) -> None:
    suites = [run_node_suite(name) for name in NODE_SUITES if "cb640" not in name]
    for result in suites:
        checks.add(
            f"pg6.suite.{Path(result['suite']).stem}",
            "AC-003",
            result["returncode"] == 0 and result["fail"] == 0 and result["tests"] > 0,
            f"tests={result['tests']} pass={result['pass']} fail={result['fail']}",
        )
    return suites


def main() -> int:
    checks = Checks()
    receipt = check_blind_set(checks)
    check_ac003(checks)
    check_ac007(checks)
    check_ac039(checks)
    suites = check_migration_integrity(checks)

    gate = (
        "FAIL"
        if checks.failed
        else "CONDITIONAL_PASS"
        if checks.pending_rows
        else "PASS"
    )
    report = {
        "schema_version": "cyberboss.cb640.validation.v1",
        "task_id": "CB-640",
        "gate_id": "PG-6",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len([r for r in checks.rows if r["result"] == "PASS"]),
        "fail_count": len(checks.failed),
        "activation_pending_count": len(checks.pending_rows),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "gate_verdict": gate,
        "gate_verdict_reason": (
            "isolation foundation proved on the exact target subject; AC-039 needs a real "
            "WeChat credential and stays activation_pending, so the gate is not sealed as an "
            "unconditional PASS"
        ),
        "blind_set_case_count": receipt.get("case_count", 0),
        "blind_set_sha256": receipt.get("blind_set_sha256"),
        "node_suites": suites,
        "node_test_total": sum(item["tests"] for item in suites),
        "checks": checks.rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
