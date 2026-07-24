#!/usr/bin/env python3
"""Fail-closed verifier for Stage 3 Review and the blocked G3 decision."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
REVIEW_ID = "STG.X2N.3.REVIEW"
RUN_ID = "RUN-X2N-S03-REVIEW"
REVIEW_BRANCH = "codex/xhs-douyin-2notion-v0001-s03-review"
STAGE_BASE_COMMIT = "ee5d251ca30eab226c4df75c53965f312c2d9b05"
REVIEW_BASE_COMMIT = "a67ba091239297b5c9c38a349e0a839680d1c411"
TASK_COMMITS = {
    "TSK.x2n.adapters.001": "ea44053528a6cdec342fff946a35a525e8daf385",
    "TSK.x2n.adapters.002": "050ec0c93ff4b1d6020a5c8e12f79320fc401f53",
    "TSK.x2n.adapters.003": "0939d78303f5e96ddedf9c8ef8a01a8dce03574a",
    "TSK.x2n.adapters.004": "37ec58cb51d5720bdbe16a67a6e4ea82107c3eb0",
    "TSK.x2n.adapters.006": "5b6564d289ab3d188015265faf55cceb13fd577a",
    "TSK.x2n.adapters.007": "a088ea8787acf5b4b2f358317135b089054f1160",
    "TSK.x2n.adapters.008": "a0f4a34675d4b2b8b02c9195976a787d2fbf9c59",
    "TSK.x2n.adapters.009": "8c6442a251f73e645e292a4e77dd03448d153b64",
    "TSK.x2n.adapters.005": REVIEW_BASE_COMMIT,
}
EXPECTED_ACCEPTANCES = {
    "ACC.x2n.gov.002",
    "ACC.x2n.ops.004",
    "ACC.x2n.batch.001",
    "ACC.x2n.xhs.001",
    "ACC.x2n.xhs.002",
    "ACC.x2n.xhs.003",
    "ACC.x2n.dy.001",
    "ACC.x2n.dy.002",
    "ACC.x2n.dy.003",
    "ACC.x2n.bili.001",
    "ACC.x2n.bili.002",
    "ACC.x2n.ks.001",
    "ACC.x2n.ks.002",
    "ACC.x2n.wb.001",
    "ACC.x2n.wb.002",
    "ACC.x2n.tb.001",
    "ACC.x2n.tb.002",
    "ACC.x2n.data.002",
    "ACC.x2n.rel.006",
}
EXPECTED_CANARIES = {
    "xiaohongshu_favorites",
    "xiaohongshu_likes",
    "douyin_favorites",
    "douyin_likes",
    "bilibili_selected_collection",
    "kuaishou_selected_collection",
    "weibo_selected_collection",
    "taobao_selected_collection",
}
EXPECTED_BLOCKERS = {
    "BLK-X2N-S03-NATIVE-DISPATCH",
    "BLK-X2N-S03-EXPLICIT-FALLBACK",
    "BLK-X2N-S03-CANARY-TERMINALS",
    "BLK-X2N-S03-ACCEPTANCE-SCOPE",
    "BLK-X2N-S03-OWNER-CANARIES",
}
EXPECTED_FINDINGS = {f"F-X2N-S03-R{index:02d}" for index in range(1, 12)}

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
ROADMAP = PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_REVIEW.md"
REVIEW_REPORT = PROJECT_ROOT / "docs/governance/STAGE_3_REVIEW.md"
G3_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_3_gate_state.schema.json"
G3_FACT = PROJECT_ROOT / "machine/facts/stage_3_gate_state.json"
FINDINGS = PROJECT_ROOT / "machine/evidence/stage_3/review/findings.json"
VERIFICATION_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_3/review/verification.json"
G3_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_3/review/G3.json"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_stage_3_review_acceptance.py"

EXPECTED_FACT_KEYS = {
    "schema_version",
    "project",
    "stage",
    "review_id",
    "run_id",
    "stage_base_commit",
    "review_base_commit",
    "review_sync_target",
    "review_status",
    "automated_reacceptance",
    "gate_id",
    "gate_status",
    "gate_decision",
    "required_task_receipts",
    "acceptance_union",
    "pass_conditions",
    "canaries",
    "privacy_scans",
    "blockers",
    "upload",
    "next_action",
    "external_execution",
}


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def _reject_json_duplicates(path: Path):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            _require(key not in value, f"duplicate JSON key rejected: {path.name}")
            value[key] = item
        return value

    return hook


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_json_duplicates(path))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _git(args: Sequence[str], *, binary: bool = False) -> str | bytes:
    git = shutil.which("git")
    _require(git is not None, "git unavailable")
    result = subprocess.run(
        [git, *args],
        cwd=REPOSITORY_ROOT,
        env=_git_environment(),
        check=False,
        capture_output=True,
        text=not binary,
    )
    _require(result.returncode == 0, "local Git verification failed")
    return result.stdout if binary else str(result.stdout).rstrip()


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        [shutil.which("git") or "git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPOSITORY_ROOT,
        env=_git_environment(),
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _blob_at(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    return bytes(_git(["show", f"{commit}:{relative}"], binary=True))


def _validate_gate_payload(fact: dict[str, Any]) -> None:
    _require(set(fact) == EXPECTED_FACT_KEYS, "Stage 3 fact fields drifted")
    _require(
        fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.3"
        and fact.get("review_id") == REVIEW_ID
        and fact.get("run_id") == RUN_ID,
        "Stage 3 fact identity drifted",
    )
    _require(
        fact.get("stage_base_commit") == STAGE_BASE_COMMIT
        and fact.get("review_base_commit") == REVIEW_BASE_COMMIT
        and fact.get("review_sync_target") == REVIEW_BASE_COMMIT,
        "Stage 3 fact commit boundary drifted",
    )
    _require(
        fact.get("review_status") == "complete"
        and fact.get("automated_reacceptance") == "pass"
        and fact.get("gate_id") == "G3"
        and fact.get("gate_status") == "blocked_technical_and_owner_clarification"
        and fact.get("gate_decision") == "resume_review",
        "Stage 3 blocked decision drifted",
    )
    upload = fact.get("upload", {})
    _require(
        upload
        == {
            "stage_3_remote_upload_authorized": False,
            "remote_upload": "forbidden_until_g3_pass",
            "stage_4_authorized": False,
            "public_release_authorized": False,
        },
        "blocked G3 authorized upload or Stage 4",
    )
    _require(fact.get("next_action") == "STG.X2N.3.REVIEW.RESUME", "blocked Review routing drifted")
    _require(
        fact.get("pass_conditions")
        == {
            "eight_scoped_relation_list_canaries": "blocked_owner_and_contract_ambiguity",
            "checkpoint_resume": "pass_ci_synth",
            "no_empty_response_deletion": "pass_ci_synth",
            "batch_failure_current_page_fallback": "blocked_technical",
        },
        "G3 condition status drifted",
    )
    _require(all(value == 0 for value in fact.get("privacy_scans", {}).values()), "privacy scan is not zero")
    external = fact.get("external_execution", {})
    _require(
        external
        == {
            "owner_profile_login": "not_run",
            "real_account_execution": "not_run",
            "platform_calls": 0,
            "notion_real_calls": 0,
            "model_calls": 0,
            "media_processing": "not_run",
        },
        "external execution was overstated",
    )

    receipts = fact.get("required_task_receipts", [])
    _require([item.get("task_id") for item in receipts] == list(TASK_COMMITS), "task receipt order or identity drifted")
    for item in receipts:
        task_id = item["task_id"]
        _require(item.get("final_commit") == TASK_COMMITS[task_id], f"{task_id} final commit drifted")
        _require(item.get("status") == "pass_ci_synth_scoped", f"{task_id} status drifted")
        evidence = PROJECT_ROOT / str(item.get("evidence_path", ""))
        _require(evidence.is_file(), f"{task_id} evidence missing")
        _require(_sha256(evidence) == item.get("evidence_sha256"), f"{task_id} evidence digest drifted")
        _require(
            evidence.read_bytes() == _blob_at(TASK_COMMITS[task_id], evidence), f"{task_id} evidence was rewritten"
        )

    acceptances = fact.get("acceptance_union", [])
    _require(len(acceptances) == 19, "Stage 3 acceptance cardinality drifted")
    _require({item.get("id") for item in acceptances} == EXPECTED_ACCEPTANCES, "Stage 3 acceptance union drifted")
    _require(
        next(item for item in acceptances if item["id"] == "ACC.x2n.data.002")["full_contract_status"]
        == "BLOCKED_EVIDENCE",
        "ACC.data.002 full Owner scope was overstated",
    )
    _require(
        next(item for item in acceptances if item["id"] == "ACC.x2n.rel.006")["stage_3_scope_status"]
        == "tooling_ready_owner_execution_not_run",
        "ACC.rel.006 Owner Alpha was overstated",
    )

    canaries = fact.get("canaries", [])
    _require(len(canaries) == 8, "Stage 3 canary cardinality drifted")
    _require({item.get("scope_id") for item in canaries} == EXPECTED_CANARIES, "Stage 3 canary scopes drifted")
    for canary in canaries:
        _require(
            canary.get("max_items") == 20
            and canary.get("feature_enabled") is False
            and canary.get("execution_status") == "NOT_RUN"
            and canary.get("private_manifest_ref_only") is True
            and canary.get("metrics_public") == {"identified_percent": None, "silent_loss": None, "duplicates": None},
            f"{canary.get('scope_id')} real canary status was overstated",
        )
        policy = PROJECT_ROOT / str(canary.get("policy_path", ""))
        _require(policy.is_file() and _sha256(policy) == canary.get("policy_sha256"), "canary policy digest drifted")

    blockers = fact.get("blockers", [])
    _require({item.get("id") for item in blockers} == EXPECTED_BLOCKERS, "G3 blocker inventory drifted")
    _require(
        {item.get("kind") for item in blockers} == {"technical", "owner_action", "contract_ambiguity"},
        "blocker kinds drifted",
    )


def validate_history_and_receipts() -> Check:
    head = str(_git(["rev-parse", "HEAD"]))
    _require(_is_ancestor(REVIEW_BASE_COMMIT, head), "Review HEAD is not based on the final Stage 3 task")
    for task_id, commit in TASK_COMMITS.items():
        _require(_is_ancestor(commit, head), f"{task_id} final commit is outside Review history")
    fact = _load_json(G3_FACT)
    _validate_gate_payload(fact)
    return Check(
        "history_and_receipts",
        "PASS",
        {"review_base": REVIEW_BASE_COMMIT, "task_receipts": len(TASK_COMMITS)},
    )


def validate_taskpack_roadmap_and_acceptance_union() -> Check:
    taskpack = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    _require(isinstance(taskpack, dict), "Taskpack is invalid")
    stage_tasks = [
        item for item in taskpack.get("tasks", []) if isinstance(item, dict) and item.get("stage") == "STG.X2N.3"
    ]
    _require([item.get("id") for item in stage_tasks] == list(TASK_COMMITS), "Stage 3 task order drifted")
    union = {
        acceptance_id
        for task in stage_tasks
        for acceptance_id in task.get("acceptance_ids", [])
        if isinstance(acceptance_id, str)
    }
    _require(union == EXPECTED_ACCEPTANCES, "Taskpack acceptance union drifted")
    gates = [item for item in taskpack.get("stage_gates", []) if item.get("id") == "G3"]
    _require(len(gates) == 1, "G3 definition missing or duplicated")
    _require(
        gates[0].get("pass_conditions")
        == [
            "eight independently scoped relation/list canaries complete",
            "checkpoint/resume pass",
            "no empty-response deletion",
            "batch failure pivots to current-page fallback",
        ],
        "Taskpack G3 conditions drifted",
    )
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for token in (
        "小红书 收藏 20",
        "小红书 点赞 20",
        "抖音 收藏 20",
        "抖音 点赞 20",
        "哔哩哔哩 所选列表 20（仅独立授权后）",
        "快手 所选列表 20（仅独立授权后）",
        "微博 所选列表 20（仅独立授权及预算后）",
        "淘宝 所选列表 20（仅独立授权后）",
        "必填字段完整率 `>=95%`",
        "静默丢失 `0`",
        "新增一条只处理新增/变化",
    ):
        _require(token in roadmap, f"Roadmap G3 oracle missing: {token}")
    acceptance = ACCEPTANCE.read_text(encoding="utf-8")
    for token in (
        "不可获得真实样本时，对应 Acceptance 状态是 `BLOCKED_EVIDENCE`，不能记为 Pass",
        "## ACC.x2n.data.002 — 端到端幂等",
        "## ACC.x2n.rel.006 — 80 条 Owner Alpha",
        "人工 Manifest、Canonical、Artifacts、Markdown、Notion、扫描",
    ):
        _require(token in acceptance, f"Acceptance boundary missing: {token}")
    return Check(
        "taskpack_roadmap_acceptance_union",
        "PASS",
        {"acceptance_count": len(union), "canary_count": 8, "task_count": len(stage_tasks)},
    )


def validate_review_documents_and_findings() -> Check:
    for path in (RUN_CONTRACT, REVIEW_REPORT, G3_SCHEMA, G3_FACT, FINDINGS, G3_EVIDENCE):
        _require(path.is_file(), f"Review artifact missing: {path.name}")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REVIEW_REPORT.read_text(encoding="utf-8")
    for token in (
        REVIEW_ID,
        RUN_ID,
        REVIEW_BASE_COMMIT,
        "BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION",
        "STG.X2N.3.REVIEW.RESUME",
        "Stage 4",
    ):
        _require(token in contract and token in report, f"Review document token missing: {token}")
    findings = _load_json(FINDINGS)
    rows = findings.get("findings", [])
    _require({item.get("id") for item in rows} == EXPECTED_FINDINGS, "Review finding set drifted")
    _require(sum(item.get("status") == "closed" for item in rows) == 6, "closed Review finding count drifted")
    _require(sum(item.get("status") == "open_blocker" for item in rows) == 5, "open Review blocker count drifted")
    g3 = _load_json(G3_EVIDENCE)
    _require(
        g3.get("decision") == "FAIL_CLOSED"
        and g3.get("status") == "BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION"
        and g3.get("required_next_run") == "STG.X2N.3.REVIEW.RESUME"
        and g3.get("stage_3_remote_upload_authorized") is False
        and g3.get("stage_4_authorized") is False,
        "G3 evidence decision drifted",
    )
    return Check(
        "review_documents_and_findings",
        "PASS",
        {"closed_findings": 6, "open_blockers": 5},
    )


def validate_review_fixes_and_known_blockers() -> Check:
    canonical_store = (PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py").read_text(encoding="utf-8")
    reconciliation = (PROJECT_ROOT / "apps/companion/src/x2n_companion/relation_reconciliation.py").read_text(
        encoding="utf-8"
    )
    favorites = (PROJECT_ROOT / "apps/companion/src/x2n_companion/xiaohongshu_favorites.py").read_text(encoding="utf-8")
    likes = (PROJECT_ROOT / "apps/companion/src/x2n_companion/xiaohongshu_likes.py").read_text(encoding="utf-8")
    douyin = (PROJECT_ROOT / "apps/companion/src/x2n_companion/douyin_adapter.py").read_text(encoding="utf-8")
    a005 = (PROJECT_ROOT / "scripts/run_adapters_005_acceptance.py").read_text(encoding="utf-8")
    service_worker = (PROJECT_ROOT / "apps/extension/src/service-worker.js").read_text(encoding="utf-8")
    sidepanel = (PROJECT_ROOT / "apps/extension/sidepanel.html").read_text(encoding="utf-8")
    native_host = (PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host.py").read_text(encoding="utf-8")

    for token in (
        "Removed relation requires Owner confirmation",
        "Stored removed relation lacks Owner confirmation",
        "Generic adapters and reconciliation are not an Owner reactivation",
    ):
        _require(token in canonical_store, f"Owner-removed terminal guard missing: {token}")
    for token in (
        "owner_removed_observed_relation_keys",
        "BatchComparisonReport",
        "compare_batch_snapshots",
        "processing_candidate_count",
    ):
        _require(token in reconciliation or token in favorites or token in likes, f"Review fix missing: {token}")
    _require('RESUME_COMPATIBILITY_VERSION = "xhs-favorites-1.1.0"' in favorites, "favorites resume version drifted")
    _require('RESUME_COMPATIBILITY_VERSION = "xhs-likes-1.1.0"' in likes, "likes resume version drifted")
    _require(
        'self._fault("before_checkpoint")' in douyin and 'self._fault("before_commit")' in douyin,
        "Douyin fault points missing",
    )
    for token in (
        "def _cross_layer_acceptance",
        '"artifact_count": counts["artifact"]',
        '"notion_mock_pages": len(notion_server.pages)',
        '"cdn_or_private_path_findings": scan.total_findings',
    ):
        _require(token in a005, f"cross-layer acceptance missing: {token}")

    _require("X2N_START_SYNC" not in service_worker, "Native dispatch blocker changed without a Resume decision")
    _require("native_sync_skeleton" in native_host, "Native skeleton blocker changed without a Resume decision")
    _require(
        '<button type="button" disabled>Sync unavailable</button>' in sidepanel,
        "disabled Sync UI blocker changed without a Resume decision",
    )
    return Check(
        "review_fixes_and_known_blockers",
        "PASS",
        {"closed_local_findings": 6, "technical_blockers": 2},
    )


def validate_public_source_safety() -> Check:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts/ci"))
    try:
        from ci_baseline import scan_source
    finally:
        sys.path.pop(0)
    report = scan_source(PROJECT_ROOT)
    _require(report.get("finding_count") == 0, "current source privacy scan failed")
    diff = str(_git(["diff", "--no-ext-diff", f"{STAGE_BASE_COMMIT}..HEAD", "--", "xhs-douyin-2notion"]))
    patterns = (
        re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}", re.IGNORECASE),
        re.compile(r"/(?:Users|home)/[^/\s]+/"),
        re.compile(r"https?://[^\s'\"]*(?:xhscdn|byteimg|bilivideo|kscdn|alicdn)", re.IGNORECASE),
    )
    _require(not any(pattern.search(diff) for pattern in patterns), "Stage 3 history diff privacy scan failed")
    return Check(
        "public_source_safety",
        "PASS",
        {
            "current_findings": 0,
            "history_diff_findings": 0,
            "scanned_files": report.get("scanned_files", 0),
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    branch = str(_git(["branch", "--show-current"]))
    _require(branch == REVIEW_BRANCH, "Review worktree branch drifted")
    main_status = str(
        subprocess.run(
            [shutil.which("git") or "git", "status", "--porcelain"],
            cwd=Path.home() / "Documents/Codex/GithubProject/MetaDatabase",
            env=_git_environment(),
            check=False,
            capture_output=True,
            text=True,
        ).stdout
    )
    if main_status and not allow_external_main_dirty:
        raise ReviewError("external main worktree is dirty")
    overlap = [line for line in main_status.splitlines() if "xhs-douyin-2notion" in line]
    _require(not overlap, "external main dirty state overlaps x2n")
    return Check(
        "worktree_isolation",
        "PASS",
        {"branch": branch, "external_main_dirty_allowed": allow_external_main_dirty, "x2n_overlap": 0},
    )


def validate_lane_report(path: Path) -> Check:
    report = _load_json(path)
    _require(
        report.get("status") == "PASS"
        and report.get("lane") == "full"
        and report.get("blocking_commands") == 12
        and report.get("blocking_repetitions") == 2
        and report.get("blocking_executions") == 24
        and report.get("blocking_failures") == 0
        and report.get("flaky_blocking_tests") == 0
        and report.get("silent_blocking_skips") == 0,
        "full lane report failed closed",
    )
    _require(
        report.get("platform_calls") == 0 and report.get("real_accounts") == 0 and report.get("model_calls") == 0,
        "full lane report includes forbidden external execution",
    )
    artifact = report.get("artifact_report", {})
    osv = report.get("osv", {})
    _require(
        report.get("artifact_deterministic") is True
        and artifact.get("status") == "PASS"
        and artifact.get("allowlist_findings") == 0
        and artifact.get("runtime_data_files") == 0
        and osv.get("status") == "PASS"
        and osv.get("critical_high_unresolved") == 0,
        "full lane artifact or dependency gate failed",
    )
    return Check(
        "full_lane",
        "PASS",
        {
            "blocking_executions": 24,
            "coverage_percent": report.get("coverage", {}).get("overall_combined_percent"),
            "dependencies_queried": osv.get("dependencies_queried"),
            "source_candidate_members": artifact.get("member_count"),
        },
    )


def run_external_acceptance() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-s03-review-verifier-") as temporary_directory:
        environment = {
            "HOME": os.environ.get("HOME", ""),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "apps/companion/src:packages/contracts/src",
            "TMPDIR": temporary_directory,
        }
        browser_cache = PROJECT_ROOT / "build/playwright-browsers"
        if browser_cache.is_dir():
            environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
        result = subprocess.run(
            [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    _require(result.returncode == 0, "Stage 3 reacceptance runner failed")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    _require(bool(lines), "Stage 3 reacceptance emitted no report")
    payload = json.loads(lines[-1])
    _require(
        payload.get("status") == "PASS_LOCAL_REACCEPTANCE_G3_BLOCKED"
        and payload.get("g3_eligible") is False
        and payload.get("g3_status") == "BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION"
        and len(payload.get("task_reports", [])) == 9
        and payload.get("verified_cross_layer", {}).get("replay_duplicates") == 0,
        "Stage 3 reacceptance result drifted",
    )
    return Check(
        "stage_3_reacceptance",
        "PASS",
        {
            "g3_eligible": False,
            "task_reports": 9,
            "verified_cross_layer": payload["verified_cross_layer"],
        },
    )


def validate_evidence(lane_report: Path | None) -> Check:
    _require(VERIFICATION_EVIDENCE.is_file(), "Review verification evidence missing")
    evidence = _load_json(VERIFICATION_EVIDENCE)
    _require(
        evidence.get("schema_version") == "1.0"
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("run_id") == RUN_ID
        and evidence.get("status") == "PASS_LOCAL_REACCEPTANCE_G3_BLOCKED"
        and evidence.get("gate_status") == "BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION"
        and evidence.get("stage_3_remote_upload_authorized") is False
        and evidence.get("stage_4_authorized") is False,
        "Review verification evidence drifted",
    )
    _require(evidence.get("task_reacceptance", {}).get("task_count") == 9, "task reacceptance evidence drifted")
    _require(
        evidence.get("cross_layer", {})
        == {
            "artifacts": 80,
            "canonical": 80,
            "cdn_or_private_path_findings": 0,
            "markdown": 80,
            "notion_mock_pages": 80,
            "outbox_receipts": 160,
            "replay_duplicates": 0,
        },
        "cross-layer evidence drifted",
    )
    if lane_report is not None:
        _require(
            evidence.get("full_lane", {}).get("report_sha256") == _sha256(lane_report),
            "full lane evidence digest drifted",
        )
    return Check(
        "review_evidence",
        "PASS",
        {"gate_status": evidence["gate_status"], "stage_3_upload": "FORBIDDEN"},
    )


def run_checks(
    *,
    verify_worktree: bool,
    allow_external_main_dirty: bool,
    run_acceptance: bool,
    lane_report: Path | None,
    require_evidence: bool,
) -> list[Check]:
    checks = [
        validate_history_and_receipts(),
        validate_taskpack_roadmap_and_acceptance_union(),
        validate_review_documents_and_findings(),
        validate_review_fixes_and_known_blockers(),
        validate_public_source_safety(),
    ]
    if verify_worktree:
        checks.append(validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(run_external_acceptance())
    if lane_report is not None:
        checks.append(validate_lane_report(lane_report))
    if require_evidence:
        checks.append(validate_evidence(lane_report))
    return checks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    parser.add_argument("--lane-report", type=Path)
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_acceptance=args.run_acceptance,
            lane_report=args.lane_report,
            require_evidence=args.require_evidence,
        )
    except (OSError, ReviewError, subprocess.TimeoutExpired, yaml.YAMLError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {
                    "reason": str(error),
                    "review_id": REVIEW_ID,
                    "status": "FAIL_CLOSED",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "checks": [
                    {"details": copy.deepcopy(check.details), "name": check.name, "status": check.status}
                    for check in checks
                ],
                "gate_status": "BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION",
                "review_id": REVIEW_ID,
                "run_id": RUN_ID,
                "stage_3_remote_upload_authorized": False,
                "stage_4_authorized": False,
                "status": "PASS_LOCAL_REVIEW_VERIFICATION_G3_BLOCKED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
