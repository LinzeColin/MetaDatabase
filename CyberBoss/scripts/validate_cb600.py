#!/usr/bin/env python3
"""Fail-closed local seal for CB-600 (AC-001 current truth, AC-002 version lock, AC-038 AGPL/provenance).

Every check is mechanical and bound to the exact target worktree. UNKNOWN and
NOT_RUN are never folded into PASS.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
EVIDENCE = PROJECT / "docs/evidence/CB-600"
FACTS = PROJECT / "machine/facts"

PRODUCT_VERSION = "v0.0.0.8"
TASKPACK_VERSION = "v0.0.0.8"
TASKPACK_REVISION = "R7-FINAL"
TASKPACK_ZIP_SHA256 = "6e7bb3c8c33f4d3a24f06dcb06aade9728a8ab13a4705402d70a30ecc014c5be"
BASE_HEAD = "bb716bd9cf2760aa9639ef85c626f0fd19c6ec94"
BASE_TREE = "a6426566cdba7dce4d1990eb888d308838b26ef1"
CB540_CLOSURE = "70086d4686975dd4dea39ef30ccefa1562f7302d"
PG5_CLOSURE = "3ad274c82b41e93bf76dcebea68a6b68379657b1"
ACCEPTANCE_IDS = ("AC-001", "AC-002", "AC-038")
REQUIRED_DOMAINS = 18
FORBIDDEN_MAC_MARKERS = ("/Users/", ".plist", "LaunchAgent", "LaunchDaemon")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str, strip: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return ""
    # porcelain status lines are "XY<space>PATH"; stripping would eat the X column
    return result.stdout.strip() if strip else result.stdout


def changed_paths() -> list[str]:
    raw = git("status", "--porcelain=v1", "--untracked-files=all", strip=False)
    return [line[3:] for line in raw.splitlines() if line.strip()]


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


def check_ac001(checks: Checks) -> None:
    """Current Truth is bound read-only to one exact Subject before any state write."""
    probe = load(EVIDENCE / "current-truth-probe.json")
    subject = load(EVIDENCE / "subject.json")

    checks.add(
        "ac001.probe_read_only",
        "AC-001",
        probe.get("probe_kind") == "read_only_current_truth",
        f"probe_kind={probe.get('probe_kind')}",
    )
    checks.add(
        "ac001.consensus_consistent",
        "AC-001",
        probe["consensus"]["status"] == "consistent",
        f"consensus={probe['consensus']['status']} reason={probe['consensus']['reason']}",
    )
    checks.add(
        "ac001.mutation_allowed",
        "AC-001",
        probe["consensus"]["mutation_policy"] == "allow_normal_execution",
        f"mutation_policy={probe['consensus']['mutation_policy']}",
    )

    claims = probe["consensus"]["accepted_high_watermark_claims"]
    sources = ("machine_task_state", "readme", "handoff")
    checks.add(
        "ac001.four_source_reconciliation",
        "AC-001",
        all(claims.get(name) for name in sources) and len(set(claims.values())) == 1,
        f"claims={claims}",
    )

    # Recomputing the probe digest proves the receipt was not hand-edited.
    replay = dict(probe)
    stored_digest = replay.pop("probe_digest", None)
    recomputed = hashlib.sha256(
        json.dumps(replay, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    checks.add(
        "ac001.probe_digest_reproducible",
        "AC-001",
        stored_digest == recomputed,
        f"stored={stored_digest} recomputed={recomputed}",
    )

    checks.add(
        "ac001.subject_head_bound",
        "AC-001",
        probe["subject"]["head"] == BASE_HEAD
        and probe["subject"]["tree"] == BASE_TREE
        and subject["exact_subject"]["head"] == BASE_HEAD
        and subject["exact_subject"]["tree"] == BASE_TREE,
        f"head={probe['subject']['head']} tree={probe['subject']['tree']}",
    )
    checks.add(
        "ac001.clean_base_worktree",
        "AC-001",
        probe["subject"]["dirty"] is False,
        f"dirty_paths={len(probe['subject']['dirty_paths'])}",
    )

    # The publicly observed PG-5 closure commits must exist on the exact target.
    for node, sha in (("CB-540", CB540_CLOSURE), ("PG-5", PG5_CLOSURE)):
        checks.add(
            f"ac001.closure_present.{node}",
            "AC-001",
            git("cat-file", "-t", sha) == "commit",
            f"{node}={sha}",
        )

    # Stage 0-5 evidence must be preserved, never replayed or deleted.
    evidence_root = PROJECT / "docs/evidence"
    preserved = sorted(p.name for p in evidence_root.iterdir() if p.is_dir() and p.name.startswith("CB-"))
    checks.add(
        "ac001.prior_evidence_preserved",
        "AC-001",
        len([n for n in preserved if n <= "CB-540"]) == 30,
        f"stage0_5_evidence_dirs={len([n for n in preserved if n <= 'CB-540'])}",
    )
    checks.add(
        "ac001.single_user_pass_not_inherited",
        "AC-001",
        subject["preserved_foundation"]["single_user_pass_inherited_as_multi_user_pass"] is False
        and subject["preserved_foundation"]["stage_0_to_5_replayed"] is False,
        "stage 0-5 neither replayed nor inherited as multi-user PASS",
    )

    events = load(FACTS / "owner_change_events.json")["events"]
    v8 = [e for e in events if e["product_version"] == PRODUCT_VERSION]
    checks.add(
        "ac001.single_owner_change_event",
        "AC-001",
        len(v8) == 1 and v8[0]["exact_subject"]["head"] == BASE_HEAD,
        f"v0.0.0.8_events={len(v8)}",
    )
    checks.add(
        "ac001.owner_change_preserves_prior_identity",
        "AC-001",
        any("511072bd975abb27cbdf5a726139ddabdab49db42f46c5601728315a46a85417" in item for item in v8[0]["preserves"])
        and any("fd3cd1e19d70caa148c3785288aaabfb909fed85" in item for item in v8[0]["preserves"]),
        "prior task_state hash and release identity retained in the event",
    )


def check_ac002(checks: Checks) -> None:
    """Version lock: v0.0.0.8 everywhere, agent holds no version authority."""
    lock = load(FACTS / "version_lock.json")
    state = load(FACTS / "task_state.json")
    subject = load(EVIDENCE / "subject.json")

    checks.add(
        "ac002.product_version",
        "AC-002",
        lock["product_version"] == PRODUCT_VERSION and lock["taskpack_version"] == TASKPACK_VERSION,
        f"product={lock['product_version']} taskpack={lock['taskpack_version']}",
    )
    checks.add(
        "ac002.revision_and_zip_bound",
        "AC-002",
        lock["taskpack_revision"] == TASKPACK_REVISION and lock["taskpack_zip_sha256"] == TASKPACK_ZIP_SHA256,
        f"revision={lock['taskpack_revision']}",
    )
    checks.add(
        "ac002.agent_has_no_version_authority",
        "AC-002",
        lock["agent_may_bump"] is False
        and lock["agent_may_create_prerelease"] is False
        and lock["agent_may_change_acceptance"] is False,
        "agent_may_bump/prerelease/change_acceptance all false",
    )
    checks.add(
        "ac002.acceptance_set_frozen_50",
        "AC-002",
        lock["acceptance_set"] == "FROZEN" and lock["acceptance_item_count"] == 50,
        f"acceptance={lock['acceptance_set']} count={lock['acceptance_item_count']}",
    )
    checks.add(
        "ac002.task_state_version_aligned",
        "AC-002",
        state["taskpack_version"] == TASKPACK_VERSION and state.get("product_version") == PRODUCT_VERSION,
        f"task_state taskpack={state['taskpack_version']} product={state.get('product_version')}",
    )
    checks.add(
        "ac002.subject_version_aligned",
        "AC-002",
        subject["product_version"] == PRODUCT_VERSION
        and subject["constraints"]["product_version_changed_by_agent"] is False
        and subject["constraints"]["acceptance_set_changed_by_agent"] is False,
        "subject records no agent-side version or acceptance mutation",
    )


def check_ac038(checks: Checks) -> None:
    """AGPL, fixed provenance and corresponding-source entry, no runtime upstream fetch."""
    source_lock = load(PROJECT / "machine/source-lock.json")
    decisions = load(FACTS / "owner_decisions.json")

    declared = {s["id"]: s["license_declared"] for s in source_lock["sources"]}
    checks.add(
        "ac038.subtree_license",
        "AC-038",
        decisions["license"]["subtree_license"] == "AGPL-3.0-only"
        and decisions["license"]["root_license_overrides_subtree"] is False
        and set(declared.values()) == {"AGPL-3.0-only"},
        f"subtree=AGPL-3.0-only root_override=False declared={declared}",
    )
    checks.add(
        "ac038.license_file_present",
        "AC-038",
        (PROJECT / "LICENSE").is_file() and (PROJECT / "app/LICENSE").is_file(),
        "CyberBoss/LICENSE and CyberBoss/app/LICENSE present",
    )
    checks.add(
        "ac038.corresponding_source_entry",
        "AC-038",
        (PROJECT / "docs/evidence/CB-000/LICENSE_COMPLIANCE.md").is_file()
        and (PROJECT / "UPSTREAM_PROVENANCE.md").is_file()
        and (PROJECT / "THIRD_PARTY_NOTICES.md").is_file(),
        "LICENSE_COMPLIANCE.md, UPSTREAM_PROVENANCE.md and THIRD_PARTY_NOTICES.md present",
    )
    checks.add(
        "ac038.no_runtime_fetch",
        "AC-038",
        source_lock["upstream_relationship"]["runtime_source_fetch_allowed"] is False
        and source_lock["upstream_relationship"]["automatic_sync_allowed"] is False
        and source_lock["upstream_relationship"]["periodic_rebase_allowed"] is False,
        "runtime fetch, automatic sync and periodic rebase all forbidden",
    )
    checks.add(
        "ac038.no_upstream_remote_or_submodule",
        "AC-038",
        source_lock["upstream_relationship"]["remote_allowed"] is False
        and source_lock["upstream_relationship"]["submodule_allowed"] is False
        and source_lock["upstream_relationship"]["git_url_dependency_allowed"] is False
        and not (REPO / ".gitmodules").exists()
        and all(s["temporary_fetch_repository_remote_count"] == 0 for s in source_lock["sources"]),
        "no upstream remote, no submodule, no Git-URL dependency, no .gitmodules",
    )
    checks.add(
        "ac038.locked_source_shas_unchanged",
        "AC-038",
        {s["id"]: s["commit"] for s in source_lock["sources"]}
        == {
            "cyberboss": "373ab17d283f1e3b304a6a36e17e9e8d44f1acfc",
            "timeline-for-agent": "62e1fa8db26f7a9147ad96579fc4077a39b94c8b",
            "whereabouts-mcp": "e36cb307f082f747327fd3a5d406fd9718a1428d",
        },
        "three locked upstream SHAs unchanged by CB-600",
    )
    checks.add(
        "ac038.license_conflict_record_honest",
        "AC-038",
        source_lock["whereabouts_license_conflict"]["upstream_clarification_received"] is False
        and source_lock["whereabouts_license_conflict"]["must_not_claim_upstream_clarification"] is True
        and source_lock["whereabouts_license_conflict"]["compliance_expression"]
        == "GPL-3.0-only AND AGPL-3.0-only",
        "whereabouts-mcp dual obligation preserved without claiming clarification",
    )


def check_scope(checks: Checks) -> None:
    """CB-600 mutates only CyberBoss/**, adds no parallel plane, and leaks no Mac markers."""
    changed = changed_paths()
    outside = [p for p in changed if not p.startswith("CyberBoss/")]
    checks.add(
        "scope.writes_inside_cyberboss_only",
        "AC-002",
        not outside,
        f"changed={len(changed)} outside_scope={outside}",
    )

    plan = load(EVIDENCE / "target-adaptation-plan.json")
    checks.add(
        "scope.no_parallel_plane",
        "AC-002",
        plan["parallel_runtime_created"] is False
        and plan["parallel_database_created"] is False
        and plan["parallel_task_state_created"] is False,
        "no parallel runtime, database or task state",
    )
    checks.add(
        "scope.all_required_domains_mapped",
        "AC-002",
        len(plan["domains"]) == REQUIRED_DOMAINS and not plan["unresolved_ambiguities"],
        f"domains={len(plan['domains'])} unresolved={plan['unresolved_ambiguities']}",
    )
    ambiguous = [d["domain"] for d in plan["domains"] if d["probe_status"].startswith("AMBIGUOUS")]
    resolved = [r["domain"] for r in plan["ambiguity_resolution"]]
    checks.add(
        "scope.every_ambiguity_resolved",
        "AC-002",
        sorted(ambiguous) == sorted(resolved),
        f"ambiguous={ambiguous} resolved={resolved}",
    )
    checks.add(
        "scope.migration_prefix_dynamic",
        "AC-002",
        plan["migration_numbering"]["selected_numeric_prefix"] == 6
        and plan["migration_numbering"]["fixed_prefix_008_used"] is False,
        f"selected_prefix={plan['migration_numbering']['selected_numeric_prefix']}",
    )

    leaks: list[str] = []
    for path in sorted(EVIDENCE.rglob("*")) + [FACTS / "version_lock.json", FACTS / "owner_change_events.json"]:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_MAC_MARKERS:
            if marker in text:
                leaks.append(f"{path.relative_to(PROJECT)}:{marker}")
    checks.add(
        "scope.no_mac_markers_in_evidence",
        "AC-038",
        not leaks,
        f"leaks={leaks}",
    )


def main() -> int:
    checks = Checks()
    check_ac001(checks)
    check_ac002(checks)
    check_ac038(checks)
    check_scope(checks)

    report = {
        "schema_version": "cyberboss.cb600.validation.v1",
        "task_id": "CB-600",
        "product_version": PRODUCT_VERSION,
        "acceptance_ids": list(ACCEPTANCE_IDS),
        "check_count": len(checks.rows),
        "pass_count": len(checks.rows) - len(checks.failed),
        "fail_count": len(checks.failed),
        "unknown_count": 0,
        "not_run_count": 0,
        "status": "PASS" if not checks.failed else "FAIL",
        "checks": checks.rows,
        "evidence_sha256": {
            path.name: sha256(path)
            for path in sorted(EVIDENCE.glob("*.json"))
            if path.name != "acceptance.json"
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
