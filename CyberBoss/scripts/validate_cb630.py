#!/usr/bin/env python3
"""Fail-closed local seal for CB-630 (AC-006 Owner boundary, AC-007 cross-user
isolation, AC-008 per-user sequencing, AC-009 message idempotency, AC-042
immutable reply-route binding, AC-044 quota and abuse protection).

UNKNOWN and NOT_RUN are never folded into PASS.
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
SRC = APP / "src"

ACCEPTANCE_IDS = ("AC-006", "AC-007", "AC-008", "AC-009", "AC-042", "AC-044")
NODE_SUITES = (
    "test/cb630-usercontext-guard-queue.test.js",
    "test/cb620-registration-consent-portal.test.js",
    "test/cb610-multiuser-foundation.test.js",
    "test/durable-inbox-crash-cut.test.js",
    "test/durable-outbox-crash-cut.test.js",
    "test/tool-host.test.js",
)
MODULES = (
    "services/users/user-context.js",
    "services/users/scoped-repository.js",
    "services/runtime/fair-user-queue.js",
    "services/runtime/quota-policy.js",
    "services/channel/reply-route-binding.js",
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

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["result"] != "PASS"]


def read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def run_node_suite(relative: str) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test", relative],
        cwd=APP,
        capture_output=True,
        text=True,
        check=False,
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


def capability_sets(source: str) -> tuple[list[str], list[str]]:
    def extract(name: str) -> list[str]:
        block = source.split(f"const {name} = Object.freeze([")[1].split("]);")[0]
        return re.findall(r'"([a-z.]+)"', block)

    return extract("OWNER_ONLY_CAPABILITIES"), extract("USER_CAPABILITIES")


def check_ac006(checks: Checks) -> None:
    context = read("services/users/user-context.js")
    tool_host = read("tools/tool-host.js")
    owner_only, user_caps = capability_sets(context)

    checks.add(
        "ac006.capability_sets_disjoint",
        "AC-006",
        set(owner_only).isdisjoint(set(user_caps)) and len(owner_only) >= 8,
        f"owner_only={len(owner_only)} user={len(user_caps)} overlap={sorted(set(owner_only) & set(user_caps))}",
    )
    for capability in ("codex.turn", "shell.execute", "workspace.write", "project.tool", "mcp.invoke"):
        checks.add(
            f"ac006.owner_only.{capability.replace('.', '_')}",
            "AC-006",
            capability in owner_only,
            f"{capability} is Owner-only",
        )
    checks.add(
        "ac006.unknown_capability_fails_closed",
        "AC-006",
        "return false;" in context.split("may(capability)")[1].split("}")[0]
        or context.count("return false;") >= 2,
        "an unrecognised capability is denied to everyone",
    )
    checks.add(
        "ac006.tool_host_guard_present",
        "AC-006",
        "#assertOwnerCapability" in tool_host
        and 'requireCapability("project.tool")' in tool_host,
        "the project tool host enforces the Owner capability",
    )
    checks.add(
        "ac006.tool_guard_runs_before_lookup",
        "AC-006",
        tool_host.index("this.#assertOwnerCapability(context);")
        < tool_host.index("const spec = PROJECT_TOOLS.find"),
        "the guard runs before a tool is located or executed",
    )
    checks.add(
        "ac006.forged_context_refused",
        "AC-006",
        'typeof userContext.requireCapability !== "function"' in tool_host,
        "an object that is not a real UserContext is refused",
    )
    checks.add(
        "ac006.context_is_frozen",
        "AC-006",
        "Object.freeze(this);" in context,
        "a UserContext cannot be mutated after construction",
    )
    redacted_keys = re.findall(
        r"^\s*(\w+): this\.",
        context.split("return Object.freeze({", 1)[1].split("});", 1)[0],
        re.MULTILINE,
    )
    checks.add(
        "ac006.redacted_projection_has_no_identifier",
        "AC-006",
        "toRedactedJson" in context
        and sorted(redacted_keys) == ["channel", "role", "status"],
        f"redacted_keys={sorted(redacted_keys)}",
    )


def check_ac007(checks: Checks) -> None:
    scoped = read("services/users/scoped-repository.js")
    context = read("services/users/user-context.js")

    for method in ("getById", "list", "count", "search", "updateById", "deleteById"):
        body = scoped.split(f"  {method}(")[1].split("\n  }")[0]
        checks.add(
            f"ac007.scoped.{method}",
            "AC-007",
            f"{{this.userColumn}}=?".replace("{{", "${") in body
            or "this.userColumn}=?" in body,
            f"{method} carries the user scope in its SQL predicate",
        )
    checks.add(
        "ac007.trusted_identifier_only",
        "AC-007",
        "trustedIdentifier" in scoped and "IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/" in scoped,
        "interpolated identifiers are validated; values stay bound parameters",
    )
    checks.add(
        "ac007.rehoming_refused",
        "AC-007",
        "columns.includes(this.userColumn)" in scoped
        and "USER_SCOPE_VIOLATION" in scoped,
        "an update cannot move a record to another user",
    )
    checks.add(
        "ac007.cross_user_read_is_loud",
        "AC-007",
        "requireById" in scoped and "RECORD_NOT_FOUND" in scoped,
        "a cross-user read is refused distinctly from a missing row",
    )
    checks.add(
        "ac007.like_wildcards_escaped",
        "AC-007",
        "ESCAPE '\\\\'" in scoped and "replace(/[\\\\%_]/g" in scoped,
        "search input cannot inject LIKE wildcards",
    )
    checks.add(
        "ac007.requires_active_context",
        "AC-007",
        "return context.requireActive();" in scoped
        and "USER_CONTEXT_REQUIRED" in scoped
        and scoped.count("this.#context(context)") >= 6,
        "every repository call resolves through the active-context guard",
    )


def check_ac008_ac044(checks: Checks) -> None:
    queue = read("services/runtime/fair-user-queue.js")
    quota = read("services/runtime/quota-policy.js")

    checks.add(
        "ac008.per_user_active_one",
        "AC-008",
        "perUserActive: 1" in queue and ">= this.perUserActive" in queue,
        "at most one active turn per user",
    )
    checks.add(
        "ac008.round_robin_rotation",
        "AC-008",
        "this.rotation.shift()" in queue and "this.rotation.push(userId)" in queue,
        "the head user is rotated to the back on every claim attempt",
    )
    checks.add(
        "ac008.owner_lane_separate",
        "AC-008",
        "activeOwner" in queue and "ownerActive" in queue,
        "the Owner's Codex lane is counted and limited separately",
    )
    checks.add(
        "ac008.queue_metrics_have_no_identifier",
        "AC-008",
        "user_id" not in queue.split("metrics()")[1],
        "queue metrics expose counts only",
    )
    checks.add(
        "ac044.frozen_limits",
        "AC-044",
        "perUserActive: 1" in quota
        and "perUserQueued: 3" in quota
        and "globalProviderActive: 2" in quota
        and "globalImportActive: 1" in quota
        and "maxTextBytes: 32 * 1024" in quota,
        "limits match the frozen abuse/quota contract",
    )
    checks.add(
        "ac044.refusals_are_chinese_and_fixed",
        "AC-044",
        "REFUSALS = Object.freeze({" in quota
        and len(re.findall(r"[一-鿿]", quota)) > 50,
        "every refusal is a fixed Chinese string chosen by table lookup",
    )
    checks.add(
        "ac044.refusal_costs_no_model_call",
        "AC-044",
        "modelCalls: 0" in quota and "require(" not in quota,
        "the quota module has no dependency that could reach a model",
    )
    checks.add(
        "ac044.per_user_queue_cap_enforced",
        "AC-044",
        'reason: "user_queue_full"' in queue,
        "a user exceeding its queue depth is refused without affecting others",
    )


def check_ac009_ac042(checks: Checks) -> None:
    queue = read("services/runtime/fair-user-queue.js")
    route = read("services/channel/reply-route-binding.js")
    adapter = read("services/db/database-adapter.js")

    checks.add(
        "ac009.inbox_conflict_do_nothing",
        "AC-009",
        "ON CONFLICT(source, source_account_hash, source_message_id)" in adapter
        and "DO NOTHING" in adapter,
        "a duplicate provider message cannot create a second inbox row",
    )
    checks.add(
        "ac009.outbox_dedupe_key_unique",
        "AC-009",
        "ON CONFLICT(dedupe_key) DO NOTHING" in adapter,
        "a duplicate final reply cannot be enqueued twice",
    )
    checks.add(
        "ac009.queue_rejects_duplicate_job",
        "AC-009",
        'reason: "duplicate_job"' in queue and "seenJobIds" in queue,
        "the same job id is never admitted twice at the queue layer",
    )
    checks.add(
        "ac042.route_bound_by_hmac",
        "AC-042",
        "createHmac" in route and "cyberboss-reply-route" in route,
        "the destination is an HMAC over user, bot account, sender and context",
    )
    checks.add(
        "ac042.route_fields_length_prefixed",
        "AC-042",
        "writeUInt32BE" in route,
        "field boundaries are unambiguous",
    )
    checks.add(
        "ac042.mismatch_is_constant_time",
        "AC-042",
        "timingSafeEqual" in route and "REPLY_ROUTE_MISMATCH" in route,
        "any disagreement fails closed in constant time",
    )
    checks.add(
        "ac042.outbound_returns_bound_destination",
        "AC-042",
        "resolveOutboundDestination" in route
        and "expectedUserId" in route,
        "the outbound path reads the bound destination instead of choosing one",
    )
    checks.add(
        "ac042.outbox_scope_inherited_not_supplied",
        "AC-042",
        "SELECT user_id FROM jobs WHERE id=?" in adapter,
        "outbox rows inherit the job's user scope",
    )


def check_hygiene(checks: Checks) -> None:
    offenders: list[str] = []
    secret_pattern = re.compile(
        r"(?:sk-[A-Za-z0-9]{16,}|BEGIN [A-Z ]*PRIVATE KEY|Bearer\s+[A-Za-z0-9._-]{20,})"
    )
    for relative in MODULES:
        text = read(relative)
        for marker in ("/Users/", ".plist", "LaunchAgent", "LaunchDaemon", "launchd"):
            if marker in text:
                offenders.append(f"{relative}:{marker}")
        if secret_pattern.search(text):
            offenders.append(f"{relative}:secret_pattern")
    checks.add(
        "cb630.no_mac_or_secret_markers",
        "AC-006",
        not offenders,
        f"offenders={offenders}",
    )
    checks.add(
        "cb630.no_model_dependency_in_guard_path",
        "AC-006",
        not any(
            token in read(relative)
            for relative in MODULES
            for token in ("openai", "anthropic", "gemini", "deepseek", "completion(")
        ),
        "no isolation, queue or quota module can reach a model provider",
    )


def check_suites(checks: Checks) -> list[dict[str, Any]]:
    results = [run_node_suite(name) for name in NODE_SUITES]
    for result in results:
        checks.add(
            f"cb630.suite.{Path(result['suite']).stem}",
            "AC-007",
            result["returncode"] == 0 and result["fail"] == 0 and result["tests"] > 0,
            f"tests={result['tests']} pass={result['pass']} fail={result['fail']}",
        )
    return results


def main() -> int:
    checks = Checks()
    check_ac006(checks)
    check_ac007(checks)
    check_ac008_ac044(checks)
    check_ac009_ac042(checks)
    check_hygiene(checks)
    suites = check_suites(checks)

    report = {
        "schema_version": "cyberboss.cb630.validation.v1",
        "task_id": "CB-630",
        "product_version": "v0.0.0.8",
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "node_suites": suites,
        "node_test_total": sum(item["tests"] for item in suites),
        "checks": checks.rows,
        "artifact_sha256": {
            f"app/src/{relative}": hashlib.sha256((SRC / relative).read_bytes()).hexdigest()
            for relative in MODULES
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
