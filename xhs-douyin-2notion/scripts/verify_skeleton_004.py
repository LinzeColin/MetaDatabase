#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.004."""

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
    "verify_skeleton_003_for_004",
    PROJECT_ROOT / "scripts/verify_skeleton_003.py",
)
assert PREVIOUS_SPEC and PREVIOUS_SPEC.loader
PREVIOUS = importlib.util.module_from_spec(PREVIOUS_SPEC)
sys.modules[PREVIOUS_SPEC.name] = PREVIOUS
PREVIOUS_SPEC.loader.exec_module(PREVIOUS)

VerificationError = PREVIOUS.VerificationError
Check = PREVIOUS.Check
_require = PREVIOUS._require
_load_json = PREVIOUS._load_json
_load_json_at = PREVIOUS._load_json_at
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

TASK_ID = "TSK.x2n.skeleton.004"
RUN_ID = "RUN-X2N-S02-S004"
PHASE = "PH.X2N.2.8"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton004"
TASK_BASE_COMMIT = "d5f61f30657ac6aa1bc7be3f7942d4b77df5b8ae"
FINAL_COMMIT = "36bd12133f402321b160292ea13ca51272c63e93"
ORIGIN_CUTOFF = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_SKELETON_004.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
ORCHESTRATOR_POLICY = PROJECT_ROOT / "machine/policy/orchestrator_policy.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "packages/test-fixtures/orchestrator/v1/fixture_manifest.json"
STORE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py"
ORCHESTRATOR_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/orchestrator.py"
NATIVE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host.py"
MIGRATION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py"
ORCHESTRATOR_TEST = PROJECT_ROOT / "apps/companion/tests/test_orchestrator.py"
NATIVE_TEST = PROJECT_ROOT / "apps/companion/tests/test_native_host.py"
EXTENSION_E2E = PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs"
SIDEPANEL = PROJECT_ROOT / "apps/extension/src/sidepanel.js"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_skeleton_004_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/orchestrator/TSK.x2n.skeleton.004.json"
FULL_LANE_GATES = PREVIOUS.FULL_LANE_GATES
EXPECTED_ARTIFACT_MEMBERS = 62

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/native_host.py",
    "apps/companion/src/x2n_companion/orchestrator.py",
    "apps/companion/tests/test_native_host.py",
    "apps/companion/tests/test_orchestrator.py",
    "apps/extension/scripts/extension-e2e.mjs",
    "apps/extension/src/sidepanel.js",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_004.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/orchestrator/TSK.x2n.skeleton.004.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/orchestrator_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/run_skeleton_004_acceptance.py",
    "scripts/verify_skeleton_003.py",
    "scripts/verify_skeleton_004.py",
    "tests/test_skeleton_003.py",
    "tests/test_skeleton_004.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/orchestrator/v1/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    changes: list[str] = []
    for path in sorted(set(committed)):
        relative = _project_relative(path)
        _require(relative is not None, "Skeleton004 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton004 change: {relative}",
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
    current_branch = _git(["branch", "--show-current"])
    _require(current_branch not in {"", "main"}, "Skeleton004 regression must run in a non-main worktree")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, FINAL_COMMIT],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Skeleton004 final commit no longer descends from its Task base",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current tree no longer descends from the Skeleton004 final commit",
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
            "current_branch": current_branch,
            "external_main_dirty_paths": len(main_paths),
            "historical_branch": BRANCH,
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": overlap,
        },
    )


def validate_previous_history() -> Check:
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Skeleton003 final commit is not the Skeleton004 base")
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Skeleton003 historical regression failed")
    return Check(
        "skeleton_003_history",
        "PASS",
        {"checks": len(checks), "final_commit": TASK_BASE_COMMIT, "history_rewritten": False},
    )


def validate_task_and_state() -> Check:
    taskpack = _read_blob_at(FINAL_COMMIT, TASKPACK).decode("utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton004 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on")
        == [
            "TSK.x2n.skeleton.001",
            "TSK.x2n.skeleton.002",
            "TSK.x2n.skeleton.006",
            "TSK.x2n.skeleton.007",
            "TSK.x2n.skeleton.008",
            "TSK.x2n.skeleton.009",
            "TSK.x2n.skeleton.003",
            "TSK.x2n.foundation.003",
        ],
        "Skeleton004 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids")
        == ["ACC.x2n.data.001", "ACC.x2n.data.002", "ACC.x2n.data.003", "ACC.x2n.ops.001"],
        "Skeleton004 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    _require("  status: STAGE_2_SKELETON_004_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack status drifted")
    _require(
        _task_block(taskpack, "TSK.x2n.skeleton.005") == _task_block(base_taskpack, "TSK.x2n.skeleton.005"),
        "Skeleton005 was entered by this Run",
    )

    state = _load_json_at(FINAL_COMMIT, TASK_STATE)
    _require(state.get("schema_version") == "1.16", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton004 state is not pass")
    _require("TSK.x2n.skeleton.005" not in state.get("tasks", {}), "Skeleton005 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.2.9" and state.get("next_run") == "TSK.x2n.skeleton.005",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    expected = {
        "ACC.x2n.data.001": "pass_ci_synth_schema_v2_run_content_relation_observation_checkpoint_artifact_graph_integrity",
        "ACC.x2n.data.002": "pass_ci_synth_80x2_plus_100_concurrent_duplicate_entities_0_markdown_notion_downstream_not_run",
        "ACC.x2n.data.003": "pass_ci_synth_canonical_provenance_broken_traces_0_classification_renderer_sinks_downstream_not_run",
        "ACC.x2n.ops.001": "pass_ci_synth_four_kill_points_non_replayable_states_0_downstream_kill_points_not_run",
    }
    _require(all(acceptance.get(key) == value for key, value in expected.items()), "Acceptance state drifted")
    for field in (
        "real_account_execution",
        "platform_calls",
        "notion_calls",
        "model_calls",
        "media_processing",
        "real_sink_execution",
    ):
        _require(state.get(field) == "not_run", f"downstream execution overstated: {field}")
    _require(
        state.get("canonical_orchestration_execution")
        == "pass_ci_synth_schema_v2_two_transaction_resume_80x2_100_concurrent_four_kill_points_broken_traces_0",
        "orchestration execution state drifted",
    )
    _require(
        _load_json_at(FINAL_COMMIT, PROJECT_FACT).get("status") == "stage_2_skeleton_004_pass_g2_not_run",
        "project drifted",
    )
    architecture = _load_json_at(FINAL_COMMIT, ARCHITECTURE_FACT)
    _require(architecture.get("phase") == PHASE and architecture.get("stage_gate") == "g2_not_run", "ADR drifted")
    adr2 = next((item for item in architecture.get("decisions", []) if item.get("id") == "ADR-002"), {})
    _require("two_transaction_current_page_orchestration" in adr2.get("implementation_state", ""), "ADR-002 drifted")
    contract = _read_blob_at(FINAL_COMMIT, RUN_CONTRACT).decode("utf-8")
    for value in (TASK_ID, RUN_ID, PHASE, TASK_BASE_COMMIT, BRANCH, "PASS_CI_SYNTH_SCOPED"):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 4,
            "downstream": "DOWNSTREAM_NOT_RUN",
            "next_task": "TSK.x2n.skeleton.005",
            "phase": PHASE,
            "single_task": True,
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json_at(FINAL_COMMIT, ORCHESTRATOR_POLICY)
    _require(
        policy.get("policy_id") == "ORCHESTRATOR.X2N.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("phase") == PHASE
        and policy.get("default") == "deny"
        and policy.get("migration") == "not_required_schema_v2_unchanged",
        "orchestrator policy identity drifted",
    )
    _require(policy.get("transaction_count") == 2, "orchestrator transaction boundary drifted")
    _require(policy.get("replay", {}).get("fixture_inputs") == 80, "idempotency fixture count drifted")
    _require(policy.get("replay", {}).get("concurrent_duplicate_requests") == 100, "concurrency count drifted")
    _require(policy.get("replay", {}).get("original_payload_required_for_resume") is False, "resume needs payload")
    _require(set(policy.get("downstream", {}).values()) == {"DOWNSTREAM_NOT_RUN"}, "downstream scope overstated")
    _require(
        policy.get("evidence_receipt", {}).get("redacted_hash_refs_only") is True
        and policy.get("evidence_receipt", {}).get("reproducible_from_sqlite") is True,
        "receipt policy weakened",
    )

    store = _read_blob_at(FINAL_COMMIT, STORE_SOURCE).decode("utf-8")
    orchestrator = _read_blob_at(FINAL_COMMIT, ORCHESTRATOR_SOURCE).decode("utf-8")
    native = _read_blob_at(FINAL_COMMIT, NATIVE_SOURCE).decode("utf-8")
    for marker in (
        "class CurrentPageReceipt",
        "def begin_current_page_capture",
        "def finalize_current_page_capture",
        "def resumable_current_page_jobs",
        "canonical_committed",
        "artifact_placeholder_committed",
    ):
        _require(marker in store, f"Store orchestration primitive missing: {marker}")
    for marker in (
        "class CurrentPageOrchestrator",
        "def execute",
        "def resume",
        "def resume_pending",
        "TRANSITION_BEFORE_CANONICAL",
        "TRANSITION_AFTER_CANONICAL",
        "DOWNSTREAM_NOT_RUN" if "DOWNSTREAM_NOT_RUN" in orchestrator else "Category assignment belongs",
    ):
        _require(marker in orchestrator, f"orchestrator implementation missing: {marker}")
    for forbidden in (
        "import requests",
        "import httpx",
        "import aiohttp",
        "urllib.request",
        "subprocess",
        "os.system",
        "shell=True",
    ):
        _require(forbidden not in orchestrator, "network/shell surface entered canonical orchestration")
    _require("CurrentPageOrchestrator(active_store).execute" in native, "Native capture does not enter orchestrator")
    _require('run_kind="native_sync_skeleton"' in native, "Skeleton005 list/sink path was entered")
    _require(
        "Current page committed to the canonical store" in _read_blob_at(FINAL_COMMIT, SIDEPANEL).decode("utf-8"),
        "UI completion drifted",
    )
    _require(
        'status !== "completed"' in _read_blob_at(FINAL_COMMIT, EXTENSION_E2E).decode("utf-8"),
        "E2E durable status drifted",
    )
    _require(
        _read_blob_at(FINAL_COMMIT, MIGRATION_SOURCE) == _read_blob_at(TASK_BASE_COMMIT, MIGRATION_SOURCE),
        "Skeleton004 unexpectedly changed Schema v2 migrations",
    )
    for lock in (PROJECT_ROOT / "uv.lock", PROJECT_ROOT / "package-lock.json"):
        _require(
            _read_blob_at(FINAL_COMMIT, lock) == _read_blob_at(TASK_BASE_COMMIT, lock),
            f"dependency lock changed: {lock.name}",
        )
    return Check(
        "orchestrator_policy_and_implementation",
        "PASS",
        {
            "migration": "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
            "network_transports": 0,
            "resume_without_payload": True,
            "schema_version": 2,
            "transactions": 2,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json_at(FINAL_COMMIT, FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S004.001"
        and fixture.get("schema_version") == "1.0"
        and fixture.get("case_count") == 80,
        "orchestrator fixture identity drifted",
    )
    for field in (
        "real_accounts",
        "contains_credentials",
        "contains_media_urls",
        "contains_private_content",
        "contains_local_absolute_paths",
    ):
        _require(fixture.get(field) is False, f"orchestrator fixture boundary weakened: {field}")
    _require(
        fixture.get("generation", {}).get("platform_cycle")
        == ["xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"],
        "six-platform fixture cycle drifted",
    )
    _require(
        fixture.get("tests", {}).get("replay_rounds") == 2
        and fixture.get("tests", {}).get("concurrent_duplicate_count") == 100
        and len(fixture.get("tests", {}).get("kill_points", [])) == 4,
        "orchestrator fixture matrix drifted",
    )
    global_manifest = _load_json_at(FINAL_COMMIT, GLOBAL_FIXTURE_MANIFEST)
    _require(
        global_manifest.get("manifest_id") == "FIXTURE.X2N.013" and global_manifest.get("phase") == PHASE,
        "global fixture manifest drifted",
    )
    _require(
        {
            "id": "FIXTURE.X2N.S02.S004.001",
            "path": "packages/test-fixtures/orchestrator/v1/fixture_manifest.json",
            "case_count": 80,
            "purpose": "six-platform current-page canonical orchestration, 80x2 replay, 100 concurrent duplicates, kill-resume and scoped provenance",
        }
        in global_manifest.get("fixtures", []),
        "orchestrator fixture is not globally registered",
    )
    return Check(
        "synthetic_orchestrator_fixtures",
        "PASS",
        {"concurrent_duplicates": 100, "kill_points": 4, "replay_inputs": 80, "replay_rounds": 2},
    )


def validate_execution() -> Check:
    _require(shutil.which("uv") is not None, "required verifier tool unavailable: uv")
    with tempfile.TemporaryDirectory(prefix="x2n-s004-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home)
        acceptance = _json_line(
            _run_external(
                "canonical_orchestration_acceptance",
                (sys.executable, "-B", "scripts/run_skeleton_004_acceptance.py"),
                env=env,
                timeout=300,
            ),
            "canonical_orchestration_acceptance",
        )
        _run_external("uv_lock_check", ("uv", "lock", "--check"), env=env, timeout=120)
    _require(
        acceptance.get("task_id") == TASK_ID
        and acceptance.get("phase") == PHASE
        and acceptance.get("status") == "PASS_CI_SYNTH_SCOPED"
        and acceptance.get("schema_version") == 2
        and acceptance.get("migration") == "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
        "orchestration acceptance identity drifted",
    )
    idempotency = acceptance.get("idempotency", {})
    _require(
        idempotency.get("case_count") == 80
        and idempotency.get("replay_rounds") == 2
        and idempotency.get("new_jobs_round_1") == 80
        and idempotency.get("existing_jobs_round_2") == 80
        and idempotency.get("duplicate_entities") == 0
        and idempotency.get("broken_provenance_traces") == 0
        and idempotency.get("private_placeholder_payloads") == 0
        and idempotency.get("stuck_runs") == 0,
        "80x2 idempotency acceptance drifted",
    )
    _require(set(idempotency.get("entity_counts", {}).values()) == {80}, "canonical entity cardinality drifted")
    concurrency = acceptance.get("concurrency", {})
    _require(
        concurrency.get("requests") == 100
        and concurrency.get("job_count") == 1
        and concurrency.get("new_jobs") == 1
        and concurrency.get("existing_jobs") == 99
        and concurrency.get("duplicate_entities") == 0,
        "100-concurrent duplicate acceptance drifted",
    )
    kill = acceptance.get("kill_points", {})
    _require(kill.get("cases") == 4 and kill.get("non_replayable_states") == 0, "kill-resume acceptance drifted")
    unit = acceptance.get("unit_suite", {})
    _require(
        int(unit.get("tests", 0)) >= 11
        and unit.get("errors") == 0
        and unit.get("failures") == 0
        and unit.get("skips") == 0,
        "orchestrator unit suite drifted",
    )
    _require(set(acceptance.get("downstream", {}).values()) == {"DOWNSTREAM_NOT_RUN"}, "downstream overstated")
    _require(
        acceptance.get("platform_calls") == 0
        and acceptance.get("notion_calls") == 0
        and acceptance.get("real_account_execution") == "NOT_RUN",
        "external execution overstated",
    )
    return Check(
        "canonical_orchestration_acceptance",
        "PASS",
        {
            "broken_provenance_traces": 0,
            "concurrent_requests": 100,
            "duplicate_entities": 0,
            "kill_points": 4,
            "replay_inputs": 80,
            "replay_rounds": 2,
            "stuck_runs": 0,
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
        ORCHESTRATOR_SOURCE,
        NATIVE_SOURCE,
        ORCHESTRATOR_TEST,
        NATIVE_TEST,
        EXTENSION_E2E,
        SIDEPANEL,
        RUN_CONTRACT,
        TASKPACK,
        TASK_STATE,
        PROJECT_FACT,
        ARCHITECTURE_FACT,
        ORCHESTRATOR_POLICY,
        ARTIFACT_POLICY,
        GLOBAL_FIXTURE_MANIFEST,
        FIXTURE_MANIFEST,
        ACCEPTANCE_RUNNER,
        PROJECT_ROOT / "scripts/verify_skeleton_003.py",
        PROJECT_ROOT / "scripts/verify_skeleton_004.py",
        PROJECT_ROOT / "tests/test_skeleton_003.py",
        PROJECT_ROOT / "tests/test_skeleton_004.py",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_read_blob_at(FINAL_COMMIT, path))
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
        {"canonical_orchestration_acceptance", "full_lane_replay", "worktree_isolation"} <= names,
        "evidence requires acceptance, worktree and two-repetition full lane validation",
    )
    acceptance = next(check for check in checks if check.name == "canonical_orchestration_acceptance")
    payload = {
        "acceptance_ids": ["ACC.x2n.data.001", "ACC.x2n.data.002", "ACC.x2n.data.003", "ACC.x2n.ops.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.data.001": "PASS_CI_SYNTH_SCHEMA_V2_CANONICAL_GRAPH_INTEGRITY",
            "ACC.x2n.data.002": "PASS_CI_SYNTH_80X2_100_CONCURRENT_DUPLICATE_ENTITIES_0_SINKS_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.data.003": "PASS_CI_SYNTH_CANONICAL_TRACE_BROKEN_0_CLASSIFICATION_RENDERER_SINKS_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.ops.001": "PASS_CI_SYNTH_4_KILL_POINTS_NON_REPLAYABLE_0_DOWNSTREAM_KILL_POINTS_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "matched_values_included": False,
        "migration": "NOT_REQUIRED_SCHEMA_V2_UNCHANGED",
        "model_calls": 0,
        "notion_calls": 0,
        "owner_canary": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_G2_PASS",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.2",
        "stage_gate": "G2_NOT_RUN",
        "status": "PASS_CI_SYNTH_SCOPED",
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
    _require(EVIDENCE.read_bytes() == _read_blob_at(FINAL_COMMIT, EVIDENCE), "historical evidence was rewritten")
    evidence = _load_json_at(FINAL_COMMIT, EVIDENCE)
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_SCOPED"
        and evidence.get("stage_gate") == "G2_NOT_RUN"
        and evidence.get("remote_upload") == "FORBIDDEN_UNTIL_G2_PASS",
        "evidence overstated",
    )
    _require(
        evidence.get("real_account_execution") == "NOT_RUN"
        and evidence.get("platform_calls") == 0
        and evidence.get("notion_calls") == 0
        and evidence.get("model_calls") == 0,
        "external execution overstated",
    )
    _require(evidence.get("matched_values_included") is False, "evidence includes matched values")
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains failure")
    metrics = evidence.get("task_metrics", {})
    _require(
        metrics.get("replay_inputs") == 80
        and metrics.get("replay_rounds") == 2
        and metrics.get("concurrent_requests") == 100
        and metrics.get("kill_points") == 4
        and metrics.get("duplicate_entities") == 0
        and metrics.get("broken_provenance_traces") == 0
        and metrics.get("stuck_runs") == 0,
        "evidence metrics drifted",
    )
    return Check(
        "evidence",
        "PASS",
        {"receipt_sha256": hashlib.sha256(_read_blob_at(FINAL_COMMIT, EVIDENCE)).hexdigest(), "task": TASK_ID},
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
    _require(all(check.status == "PASS" for check in checks), "a Skeleton004 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.004")
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
