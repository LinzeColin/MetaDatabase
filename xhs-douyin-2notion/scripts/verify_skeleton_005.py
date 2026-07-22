#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.005."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
PREVIOUS_SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_004_for_005",
    PROJECT_ROOT / "scripts/verify_skeleton_004.py",
)
assert PREVIOUS_SPEC and PREVIOUS_SPEC.loader
PREVIOUS = importlib.util.module_from_spec(PREVIOUS_SPEC)
sys.modules[PREVIOUS_SPEC.name] = PREVIOUS
PREVIOUS_SPEC.loader.exec_module(PREVIOUS)

VerificationError = PREVIOUS.VerificationError
Check = PREVIOUS.Check
_require = PREVIOUS._require
_load_json = PREVIOUS._load_json
_read_blob_at = PREVIOUS._read_blob_at
_git = PREVIOUS._git
_porcelain_paths = PREVIOUS._porcelain_paths
_project_relative = PREVIOUS._project_relative
_task_block = PREVIOUS._task_block
_field = PREVIOUS._field
_list_field = PREVIOUS._list_field
_iter_files = PREVIOUS._iter_files
_isolated_env = PREVIOUS._isolated_env
_run_external = PREVIOUS._run_external
_json_line = PREVIOUS._json_line

TASK_ID = "TSK.x2n.skeleton.005"
RUN_ID = "RUN-X2N-S02-S005"
PHASE = "PH.X2N.2.9"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton005"
TASK_BASE_COMMIT = "36bd12133f402321b160292ea13ca51272c63e93"
ORIGIN_CUTOFF = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_SKELETON_005.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
SINK_POLICY = PROJECT_ROOT / "machine/policy/sink_projection_policy.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "packages/test-fixtures/sinks/v1/fixture_manifest.json"
STORE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py"
PROJECTION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/sink_projection.py"
MARKDOWN_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/markdown_sink.py"
NOTION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/notion_sink.py"
MIGRATION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py"
SINK_TEST = PROJECT_ROOT / "apps/companion/tests/test_sinks.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_skeleton_005_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/sinks/TSK.x2n.skeleton.005.json"
FULL_LANE_GATES = PREVIOUS.FULL_LANE_GATES
EXPECTED_ARTIFACT_MEMBERS = 65

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/markdown_sink.py",
    "apps/companion/src/x2n_companion/notion_sink.py",
    "apps/companion/src/x2n_companion/sink_projection.py",
    "apps/companion/tests/test_sinks.py",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_005.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/sinks/TSK.x2n.skeleton.005.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/sink_projection_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/run_skeleton_005_acceptance.py",
    "scripts/verify_skeleton_004.py",
    "scripts/verify_skeleton_005.py",
    "tests/test_skeleton_004.py",
    "tests/test_skeleton_005.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/sinks/v1/",)


def validate_scope() -> Check:
    committed = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...HEAD"]).splitlines()
    working = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    changes: list[str] = []
    for path in sorted(set(committed + working)):
        relative = _project_relative(path)
        _require(relative is not None, "Skeleton005 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton005 change: {relative}",
        )
        changes.append(relative)

    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "/" + "Users/",
        "github" + "_pat_",
        "Bearer" + " ",
    )
    cdn_names = "|".join(
        (
            "xhs" + "cdn",
            "douyin" + "vod",
            "byte" + "img",
            "pstatp",
            "bili" + "video",
            "hdslb",
            "ks" + "cdn",
            "yx" + "imgs",
            "sina" + "img",
            "tb" + "cdn",
            r"(?:img|gw|video|vod|pic|media)\.ali" + "cdn",
        )
    )
    cdn_pattern = re.compile(rf"https?://[^\s'\"]*(?:{cdn_names})", flags=re.IGNORECASE)
    files = list(_iter_files())
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(not any(token in text for token in forbidden_tokens), "private or credential token entered x2n")
        _require(cdn_pattern.search(text) is None, "platform media CDN URL entered x2n")
        _require(
            re.search(r"(?i)(?:xsec_token|signature|auth_key)=", text) is None,
            "signed platform parameter entered x2n",
        )
    forbidden_suffixes = {
        ".db",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mov",
        ".mp3",
        ".mp4",
        ".p12",
        ".pem",
        ".pfx",
        ".png",
        ".sqlite",
        ".sqlite3",
        ".wav",
        ".webm",
        ".webp",
    }
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in files), "runtime/media artifact entered x2n")
    return Check(
        "scope_and_privacy",
        "PASS",
        {
            "changed_files": len(changes),
            "out_of_scope_writes": 0,
            "private_runtime_files": 0,
            "sensitive_or_media_url_hits": 0,
            "text_files_scanned": len(files),
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Skeleton005 worktree branch")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Skeleton005 branch no longer descends from its Task base",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the Stage 2 cutoff",
    )
    origin_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{ORIGIN_CUTOFF}..{live_origin}"]
    ).splitlines()
    origin_overlap = sum(
        path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in origin_paths
    )
    _require(origin_overlap == 0, "origin/main changed x2n before the Stage 2 review/upload gate")

    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(["branch", "--show-current"], main_path) == "main", "main unavailable")
    main_paths = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], main_path)
    )
    overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in main_paths)
    _require(overlap == 0, "MetaDatabase main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "MetaDatabase main worktree is dirty")
    return Check(
        "worktree_isolation",
        "PASS",
        {
            "branch": BRANCH,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": overlap,
        },
    )


def validate_previous_history() -> Check:
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Skeleton004 final commit is not the Skeleton005 base")
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    checks.append(PREVIOUS.verify_evidence())
    _require(all(item.status == "PASS" for item in checks), "Skeleton004 historical regression failed")
    return Check(
        "skeleton_004_history",
        "PASS",
        {"checks": len(checks), "final_commit": TASK_BASE_COMMIT, "history_rewritten": False},
    )


def validate_task_and_state() -> Check:
    taskpack = TASKPACK.read_text(encoding="utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton005 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(_list_field(task, "depends_on") == ["TSK.x2n.skeleton.004"], "Skeleton005 dependency drifted")
    _require(
        _list_field(task, "acceptance_ids")
        == ["ACC.x2n.md.001", "ACC.x2n.notion.001", "ACC.x2n.notion.002", "ACC.x2n.notion.003"],
        "Skeleton005 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    _require("  status: STAGE_2_SKELETON_005_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack status drifted")
    _require(
        _task_block(taskpack, "TSK.x2n.adapters.001") == _task_block(base_taskpack, "TSK.x2n.adapters.001"),
        "Stage 3 adapter Task was entered by this Run",
    )

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.17", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton005 state is not pass")
    _require(
        state.get("next_phase") == "STG.X2N.2.REVIEW" and state.get("next_run") == "STG.X2N.2.REVIEW",
        "Stage 2 review routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    expected = {
        "ACC.x2n.md.001": "pass_ci_synth_80_six_platform_valid_frontmatter_atomic_path_stable_cdn_0_owner_alpha_not_run",
        "ACC.x2n.notion.001": "pass_ci_synth_mock_80_unique_pages_relation_contract_user_fields_preserved_hash_noop_real_notion_not_run",
        "ACC.x2n.notion.002": "pass_ci_synth_mock_429_529_retry_after_2rps_max_attempts_4_retry_storm_0",
        "ACC.x2n.notion.003": "pass_ci_synth_mock_outage_kill_reconcile_receipt_or_dead_letter_100_duplicate_pages_0_real_notion_not_run",
    }
    _require(all(acceptance.get(key) == value for key, value in expected.items()), "sink Acceptance state drifted")
    for field in ("real_account_execution", "platform_calls", "model_calls", "media_processing"):
        _require(state.get(field) == "not_run", f"external execution overstated: {field}")
    _require(state.get("notion_calls") == "mock_only_real_api_not_run", "real Notion execution overstated")
    _require(
        state.get("real_sink_execution") == "pass_ci_synth_markdown_and_notion_mock_real_notion_not_run",
        "sink execution state drifted",
    )
    _require(
        state.get("markdown_sink_execution") == "pass_ci_synth_80x2_atomic_fixed_path_frontmatter_index_links_cdn_0",
        "Markdown execution state drifted",
    )
    _require(
        state.get("notion_sink_execution")
        == "pass_ci_synth_in_process_mock_80x2_upsert_outbox_retry_dead_letter_reconcile_real_api_not_run",
        "Notion execution state drifted",
    )
    _require(_load_json(PROJECT_FACT).get("status") == "stage_2_skeleton_005_pass_g2_not_run", "project drifted")
    architecture = _load_json(ARCHITECTURE_FACT)
    _require(architecture.get("phase") == PHASE and architecture.get("stage_gate") == "g2_not_run", "ADR drifted")
    adr2 = next((item for item in architecture.get("decisions", []) if item.get("id") == "ADR-002"), {})
    adr9 = next((item for item in architecture.get("decisions", []) if item.get("id") == "ADR-009"), {})
    _require("rebuildable_markdown_notion_mock_sinks" in adr2.get("implementation_state", ""), "ADR-002 drifted")
    _require("unclassified_projection_seed" in adr9.get("implementation_state", ""), "ADR-009 drifted")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    for value in (TASK_ID, RUN_ID, PHASE, TASK_BASE_COMMIT, BRANCH, "PASS_CI_SYNTH_MOCK_SCOPED"):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 4,
            "next_run": "STG.X2N.2.REVIEW",
            "notion_real_api": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json(SINK_POLICY)
    _require(
        policy.get("policy_id") == "SINK_PROJECTION.X2N.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("phase") == PHASE
        and policy.get("default") == "deny"
        and policy.get("migration") == "not_required_schema_v2_unchanged",
        "sink policy identity drifted",
    )
    markdown_policy = policy.get("markdown", {})
    _require(
        markdown_policy.get("canonical_path_template") == "runtime/library/content/<platform>/<content_id>.md"
        and markdown_policy.get("atomic_replace") is True
        and markdown_policy.get("file_mode") == "0600"
        and markdown_policy.get("path_uses_title") is False
        and markdown_policy.get("path_uses_category") is False,
        "Markdown policy weakened",
    )
    fallback = policy.get("category_fallback", {})
    _require(
        fallback.get("slug") == "unclassified" and fallback.get("creates_taxonomy_row") is False,
        "category ownership boundary weakened",
    )
    notion_policy = policy.get("notion", {})
    _require(
        notion_policy.get("api_version") == "2026-03-11"
        and notion_policy.get("default_requests_per_second") == 2
        and notion_policy.get("schema_changes") == "additive_only"
        and notion_policy.get("user_fields") == "preserve"
        and notion_policy.get("mock_transport") == "in_process_deterministic"
        and notion_policy.get("real_api_calls") == 0
        and notion_policy.get("credential_access") == "NOT_RUN"
        and notion_policy.get("external_file_or_media_blocks") is False,
        "Notion policy weakened",
    )
    outbox = policy.get("outbox", {})
    _require(
        outbox.get("max_attempts") == 4
        and outbox.get("retry_after_statuses") == [429, 529]
        and outbox.get("dead_letter_bounded") is True
        and outbox.get("success_before_receipt_reconcile") is True,
        "Outbox policy weakened",
    )

    store = STORE_SOURCE.read_text(encoding="utf-8")
    projection = PROJECTION_SOURCE.read_text(encoding="utf-8")
    markdown = MARKDOWN_SOURCE.read_text(encoding="utf-8")
    notion = NOTION_SOURCE.read_text(encoding="utf-8")
    for marker in (
        "class OutboxState",
        "class CanonicalProjection",
        "def projection_snapshot",
        "def retry_outbox",
        "def dead_letter_outbox",
        "def notion_mapping",
        "def record_notion_mapping",
    ):
        _require(marker in store, f"Store sink primitive missing: {marker}")
    for marker in (
        "class SinkProjection",
        "class ProjectionText",
        "def build_sink_projection",
        "UNCLASSIFIED_SLUG",
    ):
        _require(marker in projection, f"projection primitive missing: {marker}")
    for marker in (
        "class MarkdownSink",
        "def render_markdown",
        "def parse_frontmatter",
        "def _atomic_write",
        "os.replace(",
        "os.fsync(",
        "def seed_unclassified_index",
        "def validate_unclassified_links",
    ):
        _require(marker in markdown, f"Markdown implementation missing: {marker}")
    for marker in (
        'NOTION_API_VERSION = "2026-03-11"',
        "class RequestRateGate",
        "class RateLimitedNotionClient",
        "class NotionMockServer",
        "class NotionSinkWorker",
        "def plan_additive_schema",
        "def build_notion_projection",
        "def reconcile",
        "category_page_refs",
        "TRANSITION_AFTER_NOTION_SUCCESS",
    ):
        _require(marker in notion, f"Notion implementation missing: {marker}")
    for source in (projection, markdown, notion):
        for forbidden in (
            "import requests",
            "import httpx",
            "import aiohttp",
            "urllib.request",
            "import socket",
            "subprocess",
        ):
            _require(forbidden not in source, "production network/shell surface entered Skeleton005")
    _require("external" not in notion or '"external"' not in notion, "external media block entered Notion projection")
    _require(
        MIGRATION_SOURCE.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, MIGRATION_SOURCE),
        "Skeleton005 unexpectedly changed Schema v2 migrations",
    )
    for lock in (PROJECT_ROOT / "uv.lock", PROJECT_ROOT / "package-lock.json"):
        _require(lock.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, lock), f"dependency lock changed: {lock.name}")
    return Check(
        "sink_policy_and_implementation",
        "PASS",
        {
            "category_rows_created_by_fallback": 0,
            "markdown_atomic": True,
            "migration": "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
            "notion_api_version": "2026-03-11",
            "notion_real_api_calls": 0,
            "production_transports": 0,
            "requests_per_second": 2,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json(FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S005.001"
        and fixture.get("task_id") == TASK_ID
        and fixture.get("schema_version") == "1.0"
        and fixture.get("case_count") == 80,
        "sink fixture identity drifted",
    )
    for field in (
        "contains_credentials",
        "contains_media_urls",
        "contains_private_owner_content",
        "contains_local_absolute_paths",
    ):
        _require(fixture.get(field) is False, f"sink fixture boundary weakened: {field}")
    _require(
        fixture.get("generation", {}).get("platform_cycle")
        == ["xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"],
        "six-platform fixture cycle drifted",
    )
    notion = fixture.get("notion_mock", {})
    _require(
        fixture.get("replay_rounds") == 2
        and notion.get("api_version") == "2026-03-11"
        and notion.get("real_api_calls") == 0
        and len(notion.get("faults", [])) == 7
        and "Owner Notes" in notion.get("initial_user_fields", []),
        "sink fixture matrix drifted",
    )
    global_manifest = _load_json(GLOBAL_FIXTURE_MANIFEST)
    _require(
        global_manifest.get("manifest_id") == "FIXTURE.X2N.014" and global_manifest.get("phase") == PHASE,
        "global fixture manifest drifted",
    )
    _require(
        {
            "id": "FIXTURE.X2N.S02.S005.001",
            "path": "packages/test-fixtures/sinks/v1/fixture_manifest.json",
            "case_count": 80,
            "purpose": "six-platform canonical Markdown and in-process Notion mock projection, 80x2 replay, retry, dead-letter and kill-reconcile",
        }
        in global_manifest.get("fixtures", []),
        "sink fixture is not globally registered",
    )
    return Check(
        "synthetic_sink_fixtures",
        "PASS",
        {"fault_cases": 7, "replay_inputs": 80, "replay_rounds": 2, "six_platforms": 6},
    )


def validate_execution() -> Check:
    _require(shutil.which("uv") is not None, "required verifier tool unavailable: uv")
    with tempfile.TemporaryDirectory(prefix="x2n-s005-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home)
        acceptance = _json_line(
            _run_external(
                "sink_projection_acceptance",
                (sys.executable, "-B", "scripts/run_skeleton_005_acceptance.py"),
                env=env,
                timeout=300,
            ),
            "sink_projection_acceptance",
        )
        _run_external("uv_lock_check", ("uv", "lock", "--check"), env=env, timeout=120)
    _require(
        acceptance.get("task_id") == TASK_ID
        and acceptance.get("phase") == PHASE
        and acceptance.get("status") == "PASS_CI_SYNTH_MOCK_SCOPED"
        and acceptance.get("schema_version") == 2
        and acceptance.get("migration") == "NOT_REQUIRED_SCHEMA_V2_UNCHANGED"
        and acceptance.get("notion_api_version") == "2026-03-11",
        "sink acceptance identity drifted",
    )
    end_to_end = acceptance.get("end_to_end", {})
    _require(
        acceptance.get("case_count") == 80
        and end_to_end.get("replay_rounds") == 2
        and end_to_end.get("markdown_files") == 80
        and end_to_end.get("markdown_frontmatter_invalid") == 0
        and end_to_end.get("markdown_partial_files") == 0
        and end_to_end.get("markdown_cdn_findings") == 0
        and end_to_end.get("index_entries") == 80
        and end_to_end.get("index_dead_links") == 0,
        "Markdown acceptance drifted",
    )
    _require(
        end_to_end.get("notion_mock_pages") == 80
        and end_to_end.get("notion_duplicate_pages") == 0
        and end_to_end.get("notion_projection_hash_replay_requests") == 0
        and end_to_end.get("notion_schema_user_fields_preserved") is True
        and end_to_end.get("rate_maximum_average_requests_per_second") <= 2.0
        and end_to_end.get("outbox_states") == {"delivered": 160}
        and set(end_to_end.get("durable_counts", {}).values()) == {80, 160},
        "Notion mock acceptance drifted",
    )
    fault = acceptance.get("fault_matrix", {})
    _require(
        fault.get("cases") == 7
        and fault.get("max_attempts") == 4
        and fault.get("retry_after_statuses") == [429, 529]
        and fault.get("status") == "PASS_CI_SYNTH_MOCK_SCOPED",
        "Notion fault matrix drifted",
    )
    unit = acceptance.get("unit_suite", {})
    _require(
        int(unit.get("tests", 0)) >= 16
        and unit.get("errors") == 0
        and unit.get("failures") == 0
        and unit.get("skips") == 0,
        "sink unit suite drifted",
    )
    _require(
        acceptance.get("notion_real_api_calls") == 0
        and acceptance.get("owner_notion_canary") == "NOT_RUN"
        and acceptance.get("platform_calls") == 0
        and acceptance.get("real_account_execution") == "NOT_RUN",
        "external execution overstated",
    )
    return Check(
        "sink_projection_acceptance",
        "PASS",
        {
            "dead_links": 0,
            "duplicate_pages": 0,
            "fault_cases": 7,
            "frontmatter_invalid": 0,
            "markdown_files": 80,
            "notion_mock_pages": 80,
            "notion_real_api_calls": 0,
            "partial_files": 0,
            "replay_inputs": 80,
            "replay_rounds": 2,
            "unit_tests": unit["tests"],
        },
    )


def validate_full_lane_report(path: Path) -> Check:
    _require(path.is_file(), "full lane report is unavailable")
    report = _load_json(path)
    _require(report.get("status") == "PASS" and report.get("lane") == "full", "full lane did not pass")
    _require(
        report.get("blocking_commands") == 12
        and report.get("blocking_repetitions") == 2
        and report.get("blocking_executions") == 24,
        "full lane execution cardinality drifted",
    )
    _require(
        report.get("blocking_failures") == 0
        and report.get("flaky_blocking_tests") == 0
        and report.get("silent_blocking_skips") == 0,
        "full lane blocking quality gate failed",
    )
    _require(report.get("explicit_nonblocking_skips") == 6, "full lane optional skip allowlist drifted")
    expected_results = [
        {
            "blocking": True,
            "gate": gate,
            "label": f"{gate}_r{repetition}",
            "repetition": repetition,
            "status": "PASS",
        }
        for repetition in (1, 2)
        for gate in FULL_LANE_GATES
    ]
    _require(report.get("blocking_results") == expected_results, "full lane execution identity drifted")
    _require(
        report.get("platform_calls") == 0 and report.get("model_calls") == 0 and report.get("real_accounts") == 0,
        "full lane executed a forbidden external surface",
    )
    coverage = report.get("coverage", {})
    _require(
        coverage.get("status") == "PASS"
        and coverage.get("branch_mode") is True
        and float(coverage.get("overall_combined_percent", 0)) >= 70.0,
        "full lane coverage gate failed",
    )
    osv = report.get("osv", {})
    _require(
        osv.get("status") == "PASS"
        and osv.get("dependencies_queried") == 33
        and osv.get("vulnerabilities_reported") == 0
        and osv.get("critical_high_unresolved") == 0,
        "full lane OSV gate failed",
    )
    artifact = report.get("artifact_report", {})
    _require(
        report.get("artifact_deterministic") is True
        and artifact.get("status") == "PASS"
        and artifact.get("member_count") == EXPECTED_ARTIFACT_MEMBERS
        and artifact.get("runtime_data_files") == 0
        and artifact.get("allowlist_findings") == 0,
        "full lane artifact gate failed",
    )
    return Check(
        "full_lane_replay",
        "PASS",
        {
            "artifact_members": EXPECTED_ARTIFACT_MEMBERS,
            "blocking_executions": 24,
            "blocking_failures": 0,
            "coverage_percent": coverage["overall_combined_percent"],
            "dependencies_queried": 33,
            "explicit_nonblocking_skips": 6,
            "flaky_blocking_tests": 0,
            "runtime_data_files": 0,
            "silent_blocking_skips": 0,
            "vulnerabilities_reported": 0,
        },
    )


def _acceptance_input_receipt() -> str:
    paths = [
        PROJECT_ROOT / "CHANGELOG.md",
        PROJECT_ROOT / "HANDOFF.md",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "SKILL.md",
        PROJECT_ROOT / "功能清单.md",
        PROJECT_ROOT / "开发记录.md",
        STORE_SOURCE,
        PROJECTION_SOURCE,
        MARKDOWN_SOURCE,
        NOTION_SOURCE,
        SINK_TEST,
        RUN_CONTRACT,
        TASKPACK,
        TASK_STATE,
        PROJECT_FACT,
        ARCHITECTURE_FACT,
        SINK_POLICY,
        ARTIFACT_POLICY,
        GLOBAL_FIXTURE_MANIFEST,
        FIXTURE_MANIFEST,
        ACCEPTANCE_RUNNER,
        PROJECT_ROOT / "scripts/verify_skeleton_004.py",
        PROJECT_ROOT / "scripts/verify_skeleton_005.py",
        PROJECT_ROOT / "tests/test_skeleton_004.py",
        PROJECT_ROOT / "tests/test_skeleton_005.py",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "evidence contains a local absolute path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains a URL")
    _require("github" + "_pat_" not in rendered, "evidence contains credential-shaped material")


def build_evidence(checks: list[Check]) -> dict[str, Any]:
    names = {check.name for check in checks}
    _require(
        {"sink_projection_acceptance", "full_lane_replay", "worktree_isolation"} <= names,
        "evidence requires sink acceptance, worktree and two-repetition full lane validation",
    )
    acceptance = next(check for check in checks if check.name == "sink_projection_acceptance")
    payload = {
        "acceptance_ids": [
            "ACC.x2n.md.001",
            "ACC.x2n.notion.001",
            "ACC.x2n.notion.002",
            "ACC.x2n.notion.003",
        ],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.md.001": "PASS_CI_SYNTH_80_SIX_PLATFORM_ATOMIC_FIXED_PATH_FRONTMATTER_CDN_0_OWNER_ALPHA_NOT_RUN",
            "ACC.x2n.notion.001": "PASS_CI_SYNTH_MOCK_80_UNIQUE_PAGES_RELATION_CONTRACT_USER_FIELDS_PRESERVED_REAL_NOTION_NOT_RUN",
            "ACC.x2n.notion.002": "PASS_CI_SYNTH_MOCK_RETRY_AFTER_2RPS_MAX_ATTEMPTS_4_RETRY_STORM_0",
            "ACC.x2n.notion.003": "PASS_CI_SYNTH_MOCK_OUTAGE_KILL_RECONCILE_DUPLICATE_PAGES_0_REAL_NOTION_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "matched_values_included": False,
        "migration": "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
        "model_calls": 0,
        "notion_api_version": "2026-03-11",
        "notion_real_api_calls": 0,
        "owner_notion_canary": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_G2_PASS",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.2",
        "stage_gate": "G2_NOT_RUN",
        "status": "PASS_CI_SYNTH_MOCK_SCOPED",
        "task_id": TASK_ID,
        "task_metrics": acceptance.details,
    }
    _safe_evidence(payload)
    return payload


def write_evidence(checks: list[Check]) -> None:
    payload = build_evidence(checks)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_MOCK_SCOPED"
        and evidence.get("stage_gate") == "G2_NOT_RUN"
        and evidence.get("remote_upload") == "FORBIDDEN_UNTIL_G2_PASS",
        "evidence overstated",
    )
    _require(
        evidence.get("real_account_execution") == "NOT_RUN"
        and evidence.get("platform_calls") == 0
        and evidence.get("notion_real_api_calls") == 0
        and evidence.get("model_calls") == 0,
        "external execution overstated",
    )
    _require(evidence.get("owner_notion_canary") == "NOT_RUN", "Owner Notion Canary overstated")
    _require(evidence.get("matched_values_included") is False, "evidence includes matched values")
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains failure")
    metrics = evidence.get("task_metrics", {})
    _require(
        metrics.get("replay_inputs") == 80
        and metrics.get("replay_rounds") == 2
        and metrics.get("markdown_files") == 80
        and metrics.get("notion_mock_pages") == 80
        and metrics.get("duplicate_pages") == 0
        and metrics.get("frontmatter_invalid") == 0
        and metrics.get("partial_files") == 0
        and metrics.get("dead_links") == 0,
        "evidence metrics drifted",
    )
    return Check(
        "evidence",
        "PASS",
        {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID},
    )


def run_checks(
    *,
    verify_worktree: bool,
    allow_external_main_dirty: bool,
    run_external: bool,
    lane_report: Optional[Path] = None,
) -> list[Check]:
    checks = [
        validate_scope(),
        validate_previous_history(),
        validate_task_and_state(),
        validate_policy_and_implementation(),
        validate_fixtures(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_execution())
    if lane_report is not None:
        checks.append(validate_full_lane_report(lane_report))
    _require(all(check.status == "PASS" for check in checks), "a Skeleton005 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.005")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--lane-report", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_external=not args.skip_external,
            lane_report=args.lane_report,
        )
        if args.write_evidence:
            write_evidence(checks)
        if args.require_evidence:
            checks.append(verify_evidence())
        print(
            json.dumps(
                {
                    "checks": [{"name": item.name, "status": item.status} for item in checks],
                    "status": "PASS",
                    "task": TASK_ID,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, subprocess.TimeoutExpired, VerificationError) as error:
        print(
            json.dumps(
                {"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID}, ensure_ascii=False, sort_keys=True
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
