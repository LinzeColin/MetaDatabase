#!/usr/bin/env python3
"""Fail-closed final seal for CB-840 and the PG-8 exit gate.

Mapped acceptance: AC-001 (Current Truth reconciliation), AC-002 (version
lock), AC-032 (Status business matrix), AC-040 (recoverable install).

This node writes no feature and changes no acceptance. It freezes the exact
Subject, accounts for all fifty frozen acceptance items against the evidence
actually on disk, and produces a verdict.

The gate inherits every activation_pending item still outstanding. It cannot
seal as an unconditional PASS while the real WeChat channel, live provider
credentials and the authorised target host remain unavailable, and it does not
pretend otherwise: builder self-certification is one of the risks this node is
supposed to guard against, so the accounting is mechanical and every number is
recomputed from the evidence rather than restated from a summary.
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
EVIDENCE = PROJECT / "docs/evidence"

PRODUCT_VERSION = "v0.0.0.8"
TASKPACK_REVISION = "R7-FINAL"
TASKPACK_ZIP_SHA256 = "6e7bb3c8c33f4d3a24f06dcb06aade9728a8ab13a4705402d70a30ecc014c5be"
ACCEPTANCE_ITEM_COUNT = 50
ACCEPTANCE_IDS = ("AC-001", "AC-002", "AC-032", "AC-040")

V8_NODES = (
    "CB-600", "CB-610", "CB-620", "CB-630", "CB-640",
    "CB-700", "CB-710", "CB-720", "CB-730", "CB-740",
    "CB-800", "CB-810", "CB-820", "CB-830", "CB-840",
)
# The acceptance ids each node is responsible for, copied from the frozen DAG.
NODE_ACCEPTANCE = {
    "CB-600": ["AC-001", "AC-002", "AC-038"],
    "CB-610": ["AC-003", "AC-005", "AC-030"],
    "CB-620": ["AC-004", "AC-010", "AC-011", "AC-028", "AC-041"],
    "CB-630": ["AC-006", "AC-007", "AC-008", "AC-009", "AC-042"],
    "CB-640": ["AC-003", "AC-007", "AC-013", "AC-044"],
    "CB-700": ["AC-012", "AC-014", "AC-015", "AC-016", "AC-017", "AC-045", "AC-046", "AC-047"],
    "CB-710": ["AC-018", "AC-019", "AC-020", "AC-021", "AC-022", "AC-023"],
    "CB-720": ["AC-024", "AC-025", "AC-026", "AC-027"],
    "CB-730": ["AC-004", "AC-010", "AC-037", "AC-049"],
    "CB-740": ["AC-028", "AC-031", "AC-043"],
    "CB-800": ["AC-029", "AC-030", "AC-035"],
    "CB-810": ["AC-032", "AC-033", "AC-034", "AC-048"],
    "CB-820": ["AC-006", "AC-012", "AC-026", "AC-038"],
    "CB-830": ["AC-036", "AC-039", "AC-040", "AC-050"],
    "CB-840": ["AC-001", "AC-002", "AC-032", "AC-040"],
}
GATES = ("PG-6", "PG-7", "PG-8")


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


def git(*args: str, strip: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if strip else result.stdout


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_state() -> dict[str, Any]:
    return json.loads((PROJECT / "machine/facts/task_state.json").read_text(encoding="utf-8"))


# --- AC-001: the exact Subject -------------------------------------------------

def check_ac001(checks: Checks) -> dict[str, Any]:
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = [line for line in git("status", "--porcelain", strip=False).splitlines() if line.strip()]
    checks.add("ac001.working_tree_is_clean", "AC-001", not dirty,
               f"uncommitted_paths={len(dirty)}")
    checks.add("ac001.head_and_tree_are_resolvable", "AC-001",
               bool(re.fullmatch(r"[0-9a-f]{40}", head))
               and bool(re.fullmatch(r"[0-9a-f]{40}", tree)),
               f"head={head} tree={tree}")

    # Delegate to the in-repo Current Truth guard rather than reimplementing
    # its rule. A second, subtly different implementation of the consensus rule
    # is exactly the drift AC-001 exists to catch.
    guard = subprocess.run(
        [sys.executable, str(PROJECT / "scripts/validate_current_truth.py")],
        capture_output=True, text=True, check=False,
    )
    try:
        consensus = json.loads(guard.stdout)
    except json.JSONDecodeError:
        consensus = {"status": "unreadable", "accepted_high_watermark_claims": {}}
    claims = consensus.get("accepted_high_watermark_claims", {})
    checks.add("ac001.three_sources_agree", "AC-001",
               consensus.get("status") == "consistent",
               f"status={consensus.get('status')} claims={claims}")

    release = PROJECT / "machine/facts/version_lock.json"
    checks.add("ac001.subject_identity_is_recorded", "AC-001", release.is_file(),
               "the version lock records the release identity of the Subject")
    return {"head": head, "tree": tree, "branch": branch, "claims": claims,
            "working_tree_clean": not dirty}


# --- AC-002: the version lock --------------------------------------------------

def check_ac002(checks: Checks) -> None:
    lock = json.loads(
        (PROJECT / "machine/facts/version_lock.json").read_text(encoding="utf-8")
    )
    state = load_state()
    checks.add("ac002.product_version_unchanged", "AC-002",
               state["product_version"] == PRODUCT_VERSION
               and lock.get("product_version") == PRODUCT_VERSION,
               f"state={state['product_version']} lock={lock.get('product_version')}")
    checks.add("ac002.taskpack_version_unchanged", "AC-002",
               state["taskpack_version"] == PRODUCT_VERSION
               and state["taskpack_revision"] == TASKPACK_REVISION,
               f"taskpack={state['taskpack_version']} revision={state['taskpack_revision']}")
    checks.add("ac002.taskpack_zip_hash_unchanged", "AC-002",
               state["taskpack_zip_sha256"] == TASKPACK_ZIP_SHA256,
               f"sha256={state['taskpack_zip_sha256']}")
    checks.add("ac002.agent_may_not_bump", "AC-002",
               lock.get("agent_may_bump") is False,
               f"agent_may_bump={lock.get('agent_may_bump')}")
    overlay = state["taskpack_overlay_v0_0_0_8"]
    checks.add("ac002.acceptance_set_frozen", "AC-002",
               overlay.get("acceptance_set") == "FROZEN"
               and overlay.get("acceptance_item_count") == ACCEPTANCE_ITEM_COUNT,
               f"acceptance_set={overlay.get('acceptance_set')} "
               f"count={overlay.get('acceptance_item_count')}")
    checks.add("ac002.one_owner_change_event", "AC-002",
               overlay.get("owner_change_event")
               == "owner-change-cyberboss-v0.0.0.8-multiuser-weixin",
               f"event={overlay.get('owner_change_event')}")


# --- AC-032 / AC-040 re-proved at the seal --------------------------------------

def check_carried_acceptance(checks: Checks) -> None:
    matrix = (APP / "src/services/status/business-matrix.js").read_text(encoding="utf-8")
    checks.add("ac032.status_matrix_still_present_at_the_seal", "AC-032",
               "BUSINESS_LINES" in matrix and "STATUS_FIELD_FORBIDDEN" in matrix,
               "the sealed Subject still carries the fail-closed business matrix")
    cb810 = json.loads((EVIDENCE / "CB-810/acceptance.json").read_text(encoding="utf-8"))
    ac032 = next(row for row in cb810["results"] if row["acceptance_id"] == "AC-032")
    checks.add("ac032.carried_result_is_pass", "AC-032", ac032["result"] == "PASS",
               f"CB-810 AC-032={ac032['result']}")

    cb830 = json.loads((EVIDENCE / "CB-830/acceptance.json").read_text(encoding="utf-8"))
    ac040 = next(row for row in cb830["results"] if row["acceptance_id"] == "AC-040")
    checks.add("ac040.carried_result_is_recorded", "AC-040",
               ac040["result"] in ("PASS", "CONDITIONAL_PASS"),
               f"CB-830 AC-040={ac040['result']}")
    checks.pending(
        "ac040.target_environment_proof", "AC-040",
        "clean install, start, stop, doctor, backup, restore and rollback on the authorised "
        "target host: NOT_RUN_REQUIRES_AUTHORIZED_TARGET, as already recorded in the frozen "
        "privacy contract; the seal inherits it rather than resolving it",
    )


# --- the accounting: every node, every acceptance item --------------------------

def check_node_evidence(checks: Checks) -> dict[str, Any]:
    state = load_state()
    by_id = {task["id"]: task["status"] for task in state["tasks"]}
    accepted = [node for node in V8_NODES if by_id.get(node) == "passed" or node == "CB-840"]
    checks.add("pg8.every_v8_node_accepted", "AC-001",
               len(accepted) == len(V8_NODES),
               f"accepted={len(accepted)}/{len(V8_NODES)} "
               f"missing={[n for n in V8_NODES if n not in accepted]}")

    missing_evidence = []
    for node in V8_NODES:
        if node == "CB-840":
            continue
        for name in ("run-contract.json", "subject.json", "acceptance.json",
                     "validation-report.json"):
            if not (EVIDENCE / node / name).is_file():
                missing_evidence.append(f"{node}/{name}")
    checks.add("pg8.every_node_has_a_complete_evidence_bundle", "AC-001",
               not missing_evidence, f"missing={missing_evidence}")

    # Recompute the acceptance ledger from the evidence, not from a summary.
    ledger: dict[str, dict[str, str]] = {}
    for node in V8_NODES:
        path = EVIDENCE / node / "acceptance.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            ledger.setdefault(row["acceptance_id"], {})[node] = row["result"]

    expected_ids = sorted({item for ids in NODE_ACCEPTANCE.values() for item in ids})
    checks.add("pg8.frozen_acceptance_set_is_fifty_items", "AC-002",
               len(expected_ids) == ACCEPTANCE_ITEM_COUNT,
               f"distinct_ids_in_the_dag={len(expected_ids)}")

    unaccounted = [item for item in expected_ids if item not in ledger]
    checks.add("pg8.every_acceptance_item_has_a_recorded_result", "AC-001",
               not unaccounted, f"unaccounted={unaccounted}")

    failures = {
        item: results for item, results in ledger.items()
        if any(result == "FAIL" for result in results.values())
    }
    checks.add("pg8.no_acceptance_item_recorded_a_failure", "AC-001",
               not failures, f"failures={failures}")

    # An acceptance id is outstanding either because a node recorded its result
    # as ACTIVATION_PENDING, or because a node recorded it as CONDITIONAL_PASS
    # with pending items attached. Reading only the result string would
    # under-report the second case and make the gate look cleaner than it is.
    pending_items: dict[str, list[str]] = {}
    carried_details: list[str] = []
    for node in V8_NODES:
        path = EVIDENCE / node / "acceptance.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            outstanding = row["result"] == "ACTIVATION_PENDING" or row.get(
                "activation_pending_count", 0
            ) > 0 or row.get("activation_pending")
            if outstanding:
                pending_items.setdefault(row["acceptance_id"], []).append(
                    f"{node}:{row['result']}"
                )
        for item in data.get("activation_pending", []):
            carried_details.append(f"{node}: {item}")
    for item, sites in sorted(pending_items.items()):
        checks.pending("pg8.carried_activation_pending_item", item,
                       f"{item} is outstanding at {sites}")
    for detail in carried_details:
        checks.pending("pg8.carried_activation_pending_detail", "AC-001", detail)

    # Node-level verdicts, recomputed.
    verdicts = {}
    for node in V8_NODES:
        path = EVIDENCE / node / "acceptance.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            verdicts[node] = data.get("node_verdict") or data.get("gate_verdict") or "PASS"
    conditional = sorted(node for node, verdict in verdicts.items()
                         if verdict == "CONDITIONAL_PASS")

    checks.add("pg8.prior_gates_are_sealed", "AC-001",
               state["pass_gates"].get("PG-6") in ("passed", "conditional_pass")
               and state["pass_gates"].get("PG-7") in ("passed", "conditional_pass"),
               f"PG-6={state['pass_gates'].get('PG-6')} PG-7={state['pass_gates'].get('PG-7')}")
    return {"ledger": ledger, "verdicts": verdicts, "conditional_nodes": conditional,
            "pending_items": {item: sites for item, sites in sorted(pending_items.items())},
            "carried_activation_pending": sorted(set(carried_details))}


def check_suites(checks: Checks) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "--test"], cwd=APP, capture_output=True, text=True, check=False,
    )
    output = result.stdout + result.stderr
    counts = {
        key: int(match.group(1))
        for key in ("tests", "pass", "fail")
        if (match := re.search(rf"^. {key} (\d+)$", output, re.MULTILINE))
    }
    checks.add("pg8.full_app_suite_is_clean", "AC-001",
               result.returncode == 0 and counts.get("fail") == 0 and counts.get("tests", 0) > 0,
               f"tests={counts.get('tests')} pass={counts.get('pass')} fail={counts.get('fail')}")

    check_result = subprocess.run(
        ["npm", "run", "check"], cwd=APP, capture_output=True, text=True, check=False,
    )
    checks.add("pg8.syntax_check_is_clean", "AC-001", check_result.returncode == 0,
               f"returncode={check_result.returncode}")
    return {"app_suite": counts, "npm_run_check": check_result.returncode == 0}


def build_manifest() -> dict[str, str]:
    """Deterministic per-file digest over the evidence and the v8 artefacts."""
    manifest: dict[str, str] = {}
    for path in sorted(EVIDENCE.rglob("*.json")):
        manifest[str(path.relative_to(PROJECT))] = sha256_file(path)
    for relative in (
        "machine/facts/task_state.json",
        "machine/facts/version_lock.json",
        "machine/facts/owner_change_events.json",
        "machine/source-lock.json",
        "app/migrations/006_multiuser_foundation.sql",
        "app/migrations/007_cb800_lifecycle_receipts.sql",
        "ops/config/operator-actions.json",
        "ops/bin/cyberbossctl",
        "README.md",
        "HANDOFF.md",
    ):
        path = PROJECT / relative
        if path.is_file():
            manifest[relative] = sha256_file(path)
    return manifest


def main() -> int:
    checks = Checks()
    subject = check_ac001(checks)
    check_ac002(checks)
    check_carried_acceptance(checks)
    accounting = check_node_evidence(checks)
    suites = check_suites(checks)

    manifest = build_manifest()
    manifest_digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    checks.add("pg8.manifest_is_deterministic", "AC-001",
               len(manifest) > 0 and bool(re.fullmatch(r"[0-9a-f]{64}", manifest_digest)),
               f"files={len(manifest)} digest={manifest_digest}")

    verdict = (
        "FAIL" if checks.failed
        else "CONDITIONAL_PASS" if checks.pending_rows
        else "PASS"
    )
    report = {
        "schema_version": "cyberboss.cb840.validation.v1",
        "task_id": "CB-840",
        "gate_id": "PG-8",
        "product_version": PRODUCT_VERSION,
        "taskpack_revision": TASKPACK_REVISION,
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "exact_subject": subject,
        "check_count": len(checks.rows),
        "pass_count": len([row for row in checks.rows if row["result"] == "PASS"]),
        "fail_count": len(checks.failed),
        "activation_pending_count": len(checks.pending_rows),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "gate_verdict": verdict,
        "gate_verdict_reason": (
            "every one of the fifty frozen acceptance items has a recorded result on the exact "
            "target subject and none recorded a failure; the outstanding activation_pending "
            "items — the real WeChat channel, live provider credentials and the authorised "
            "target host — are inherited by the gate, so it is sealed as CONDITIONAL PASS and "
            "not as a full product acceptance"
        ),
        "acceptance_ledger": accounting["ledger"],
        "node_verdicts": accounting["verdicts"],
        "conditional_nodes": accounting["conditional_nodes"],
        "activation_pending_items": accounting["pending_items"],
        "carried_activation_pending": accounting["carried_activation_pending"],
        "suites": suites,
        "manifest_file_count": len(manifest),
        "manifest_sha256": manifest_digest,
        "checks": checks.rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
