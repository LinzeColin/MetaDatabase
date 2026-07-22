#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.003."""

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
    "verify_skeleton_009_for_003",
    PROJECT_ROOT / "scripts/verify_skeleton_009.py",
)
assert PREVIOUS_SPEC and PREVIOUS_SPEC.loader
PREVIOUS = importlib.util.module_from_spec(PREVIOUS_SPEC)
sys.modules[PREVIOUS_SPEC.name] = PREVIOUS
PREVIOUS_SPEC.loader.exec_module(PREVIOUS)

VerificationError = PREVIOUS.VerificationError
Check = PREVIOUS.Check
_require = PREVIOUS._require
_pairs = PREVIOUS._pairs
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

TASK_ID = "TSK.x2n.skeleton.003"
RUN_ID = "RUN-X2N-S02-S003"
PHASE = "PH.X2N.2.7"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton003"
TASK_BASE_COMMIT = "0af2d3b269e7d5631257cb49f41f75cc79438f70"
FINAL_COMMIT = "d5f61f30657ac6aa1bc7be3f7942d4b77df5b8ae"
ORIGIN_CUTOFF = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_SKELETON_003.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
MEDIA_POLICY = PROJECT_ROOT / "machine/policy/media_safety_policy.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "packages/test-fixtures/media/v1/fixture_manifest.json"
MEDIA_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/media_safety.py"
STORE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py"
MIGRATION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py"
RUNTIME_CLI = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
COMPANION_PACKAGE = PROJECT_ROOT / "apps/companion/pyproject.toml"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_skeleton_003_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/media/TSK.x2n.skeleton.003.json"
FULL_LANE_GATES = PREVIOUS.FULL_LANE_GATES

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/pyproject.toml",
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/media_safety.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_media_safety.py",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_003.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/media/TSK.x2n.skeleton.003.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/media_safety_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/run_skeleton_003_acceptance.py",
    "scripts/verify_skeleton_003.py",
    "scripts/verify_skeleton_009.py",
    "tests/test_skeleton_003.py",
    "tests/test_skeleton_009.py",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/media/v1/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    relative_changes: list[str] = []
    for path in sorted(set(committed)):
        relative = _project_relative(path)
        _require(relative is not None, "Skeleton003 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton003 change: {relative}",
        )
        relative_changes.append(relative)

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
        ".db", ".jpeg", ".jpg", ".m4a", ".mov", ".mp3", ".mp4", ".p12", ".pem",
        ".pfx", ".png", ".sqlite", ".sqlite3", ".wav", ".webm", ".webp",
    }
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in files), "private media/runtime artifact entered x2n")
    return Check(
        "scope_and_privacy",
        "PASS",
        {
            "changed_files": len(relative_changes),
            "out_of_scope_writes": 0,
            "private_runtime_files": 0,
            "sensitive_or_media_url_hits": 0,
            "text_files_scanned": len(files),
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    current_branch = _git(["branch", "--show-current"])
    _require(current_branch not in {"", "main"}, "Skeleton003 regression must run in a non-main worktree")
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
        "Skeleton003 final commit no longer descends from its Task base",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current tree no longer descends from the Skeleton003 final commit",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the review cutoff",
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
    main_overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in main_paths)
    _require(main_overlap == 0, "MetaDatabase main dirty state overlaps x2n")
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
            "project_overlap_paths": main_overlap,
        },
    )


def validate_previous_history() -> Check:
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Skeleton009 historical regression failed")
    return Check(
        "skeleton_009_history",
        "PASS",
        {"checks": len(checks), "final_commit": PREVIOUS.FINAL_COMMIT, "history_rewritten": False},
    )


def validate_task_and_state() -> Check:
    taskpack = _read_blob_at(FINAL_COMMIT, TASKPACK).decode("utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton003 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.foundation.003", "TSK.x2n.foundation.005"],
        "Skeleton003 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids")
        == ["ACC.x2n.media.001", "ACC.x2n.media.002", "ACC.x2n.media.003", "ACC.x2n.media.004"],
        "Skeleton003 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Skeleton003 Task changed beyond status")
    _require("  status: STAGE_2_SKELETON_003_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack status drifted")
    _require(
        _task_block(taskpack, "TSK.x2n.skeleton.004") == _task_block(base_taskpack, "TSK.x2n.skeleton.004"),
        "Skeleton004 was entered by this Run",
    )

    state = _load_json_at(FINAL_COMMIT, TASK_STATE)
    _require(state.get("schema_version") == "1.15", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton003 state is not pass")
    _require("TSK.x2n.skeleton.004" not in state.get("tasks", {}), "Skeleton004 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.2.8" and state.get("next_run") == "TSK.x2n.skeleton.004",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    expected_acceptance = {
        "ACC.x2n.media.001": "pass_ci_synth_5_fixed_scopes_zero_findings_owner_alpha_real_sinks_not_run",
        "ACC.x2n.media.002": "pass_ci_synth_success_residual_0_expired_residual_0_active_misdelete_0_delete_error_receipt_100_percent",
        "ACC.x2n.media.003": "pass_ci_synth_512_url_fuzz_32_ssrf_forbidden_success_0_local_file_reads_0",
        "ACC.x2n.media.004": "pass_ci_synth_8_acquisition_resource_blocks_companion_crash_0_processor_ffmpeg_image_decode_keyframe_downstream_not_run",
    }
    _require(all(acceptance.get(key) == value for key, value in expected_acceptance.items()), "media Acceptance state drifted")
    for field in (
        "real_account_execution", "platform_calls", "notion_calls", "model_calls", "media_processing", "real_sink_execution",
    ):
        _require(state.get(field) == "not_run", f"downstream execution overstated: {field}")
    _require(
        state.get("media_safety_execution")
        == "pass_ci_synth_url_fuzz_ssrf_bounded_download_temporary_lease_cleanup_and_fixed_scope_scanner_real_network_and_processors_not_run",
        "media safety execution scope drifted",
    )
    _require(
        _load_json_at(FINAL_COMMIT, PROJECT_FACT).get("status") == "stage_2_skeleton_003_pass_g2_not_run",
        "project drifted",
    )
    architecture = _load_json_at(FINAL_COMMIT, ARCHITECTURE_FACT)
    _require(architecture.get("phase") == PHASE and architecture.get("stage_gate") == "g2_not_run", "ADR drifted")
    adr8 = next((item for item in architecture.get("decisions", []) if item.get("id") == "ADR-008"), {})
    _require("url_firewall_ip_pinned_transport_contract" in adr8.get("implementation_state", ""), "ADR-008 not implemented")
    contract = _read_blob_at(FINAL_COMMIT, RUN_CONTRACT).decode("utf-8")
    for value in (TASK_ID, RUN_ID, PHASE, TASK_BASE_COMMIT, BRANCH, "PASS_CI_SYNTH_SCOPED"):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 4,
            "media_processors": "DOWNSTREAM_NOT_RUN",
            "next_task": "TSK.x2n.skeleton.004",
            "phase": PHASE,
            "real_media_network": "NOT_RUN",
            "single_task": True,
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json_at(FINAL_COMMIT, MEDIA_POLICY)
    _require(
        policy.get("policy_id") == "MEDIA.X2N.SAFETY.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("phase") == PHASE
        and policy.get("default") == "deny"
        and policy.get("pattern_set_version") == "x2n-media-zero-v1",
        "media policy identity drifted",
    )
    suffixes = policy.get("platform_cdn_suffixes", {})
    _require(set(suffixes) == {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"}, "six-platform CDN policy drifted")
    firewall = policy.get("url_firewall", {})
    _require(
        firewall.get("schemes") == ["https"]
        and firewall.get("ports") == [443]
        and firewall.get("maximum_redirects") == 3
        and firewall.get("validate_every_redirect") is True
        and firewall.get("validate_all_dns_answers") is True
        and firewall.get("required_ip_class") == "global"
        and firewall.get("transport_must_connect_to_validated_ip") is True
        and firewall.get("production_transport_implemented") is False
        and firewall.get("real_media_network_execution") == "NOT_RUN",
        "URL firewall policy weakened",
    )
    limits = policy.get("download_limits", {})
    _require(
        limits.get("maximum_bytes") == 64 * 1024 * 1024
        and limits.get("maximum_duration_seconds") == 7_200
        and limits.get("deadline_seconds") == 60
        and limits.get("remote_filename_used") is False
        and limits.get("required_isolated_inspector") is True,
        "download limits drifted",
    )
    lifecycle = policy.get("lease_lifecycle", {})
    _require(
        lifecycle.get("sqlite_url_column_present") is False
        and lifecycle.get("success_cleanup") == "immediate"
        and lifecycle.get("crash_orphan_maximum_seconds") == 86_400
        and lifecycle.get("unexpired_active_delete_allowed") is False
        and lifecycle.get("delete_failure_receipt_required") is True,
        "media lease lifecycle drifted",
    )
    scanner = policy.get("scanner", {})
    _require(
        scanner.get("arbitrary_path_input_allowed") is False
        and scanner.get("logical_scopes") == ["db", "markdown", "logs", "notion-export", "artifacts"]
        and scanner.get("matched_values_emitted") is False
        and scanner.get("symbolic_links_allowed") is False,
        "persistence scanner policy drifted",
    )

    source = _read_blob_at(FINAL_COMMIT, MEDIA_SOURCE).decode("utf-8")
    for marker in (
        "class EphemeralMediaSource",
        "class ValidatedMediaTarget",
        "def canonicalize_persistable_page_url",
        "def validate_media_target",
        "def download_media",
        "class MediaLeaseManager",
        "class MediaLeaseCleaner",
        "def scan_persisted_scopes",
        "fcntl.LOCK_SH",
        "fcntl.LOCK_EX",
        "os.link(",
        "address.is_global",
    ):
        _require(marker in source, f"media safety implementation missing: {marker}")
    for forbidden in ("import requests", "import httpx", "import aiohttp", "urllib.request", "socket.create_connection"):
        _require(forbidden not in source, "production network implementation entered Skeleton003")
    _require("__getstate__" in source and source.count("cannot be serialized") >= 4, "ephemeral objects are serializable")

    migrations = _read_blob_at(FINAL_COMMIT, MIGRATION_SOURCE).decode("utf-8")
    media_schema = migrations.split("CREATE TABLE media_lease", 1)[1].split(") STRICT", 1)[0]
    _require("url" not in media_schema.lower(), "media lease schema acquired a URL column")
    store = _read_blob_at(FINAL_COMMIT, STORE_SOURCE).decode("utf-8")
    for marker in (
        "class MediaLeaseRecord",
        "def media_cleanup_candidates",
        "def record_media_cleanup",
        "def content_platform",
        "lease_id: str | None = None",
    ):
        _require(marker in store, f"Store lease primitive missing: {marker}")
    cli = _read_blob_at(FINAL_COMMIT, RUNTIME_CLI).decode("utf-8")
    _require("cdn-zero" in cli and "scan_persisted_scopes" in cli and 'MEDIA_TASK_ID = "TSK.x2n.skeleton.003"' in cli, "CDN-zero CLI missing")
    _require("--path" not in cli and "--root" not in cli, "media CLI acquired an arbitrary path input")
    package = _read_blob_at(FINAL_COMMIT, COMPANION_PACKAGE).decode("utf-8")
    _require('x2n = "x2n_companion.runtime_cli:main"' in package, "x2n CLI entry point missing")
    _require(
        _read_blob_at(FINAL_COMMIT, PROJECT_ROOT / "uv.lock")
        == _read_blob_at(TASK_BASE_COMMIT, PROJECT_ROOT / "uv.lock"),
        "Python dependency lock changed in Skeleton003",
    )
    _require(
        _read_blob_at(FINAL_COMMIT, PROJECT_ROOT / "package-lock.json")
        == _read_blob_at(TASK_BASE_COMMIT, PROJECT_ROOT / "package-lock.json"),
        "npm dependency lock changed in Skeleton003",
    )
    return Check(
        "media_policy_and_implementation",
        "PASS",
        {
            "cdn_suffixes": sum(len(value) for value in suffixes.values()),
            "fixed_scanner_scopes": 5,
            "production_transports": 0,
            "raw_url_database_columns": 0,
            "retention_max_seconds": 86_400,
            "six_platforms": 6,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json_at(FINAL_COMMIT, FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S003.001"
        and fixture.get("task_id") == TASK_ID
        and fixture.get("phase") == PHASE
        and fixture.get("data_class") == "public_safe_synthetic",
        "media fixture identity drifted",
    )
    _require(
        fixture.get("raw_url_literals_present") is False
        and fixture.get("real_account_data_present") is False
        and fixture.get("real_media_present") is False
        and fixture.get("platform_network_execution") is False,
        "media fixture public boundary weakened",
    )
    _require(fixture.get("url_fuzz", {}).get("cases") == 512, "URL fuzz fixture count drifted")
    _require(fixture.get("ssrf", {}).get("cases") == 32, "SSRF fixture count drifted")
    _require(fixture.get("cleanup_chaos", {}).get("cases") == 8, "cleanup fixture count drifted")
    _require(fixture.get("resource_limits", {}).get("cases") == 8, "resource fixture count drifted")
    _require(
        fixture.get("scanner", {}).get("scopes") == ["db", "markdown", "logs", "notion-export", "artifacts"],
        "scanner fixture scope drifted",
    )
    rendered = _read_blob_at(FINAL_COMMIT, FIXTURE_MANIFEST).decode("utf-8")
    _require(re.search(r"https?://", rendered) is None, "media fixture contains a URL literal")
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered, "media fixture contains private data")
    global_manifest = _load_json_at(FINAL_COMMIT, GLOBAL_FIXTURE_MANIFEST)
    _require(global_manifest.get("manifest_id") == "FIXTURE.X2N.012" and global_manifest.get("phase") == PHASE, "global fixture manifest drifted")
    _require(
        {
            "id": "FIXTURE.X2N.S02.S003.001",
            "path": "packages/test-fixtures/media/v1/fixture_manifest.json",
            "case_count": 560,
            "purpose": "URL fuzz, SSRF, temporary media cleanup chaos, bounded acquisition and fixed logical persistence-scope scanning",
        }
        in global_manifest.get("fixtures", []),
        "media fixture is not globally registered",
    )
    return Check(
        "synthetic_media_fixtures",
        "PASS",
        {
            "cleanup_cases": 8,
            "resource_cases": 8,
            "ssrf_cases": 32,
            "total_matrix_cases": 560,
            "url_fuzz_cases": 512,
        },
    )


def validate_execution() -> Check:
    _require(shutil.which("uv") is not None, "required verifier tool unavailable: uv")
    with tempfile.TemporaryDirectory(prefix="x2n-s003-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home)
        acceptance = _json_line(
            _run_external(
                "media_security_acceptance",
                (sys.executable, "-B", "scripts/run_skeleton_003_acceptance.py"),
                env=env,
                timeout=240,
            ),
            "media_security_acceptance",
        )
        _run_external(
            "uv_lock_check",
            ("uv", "lock", "--check"),
            env=env,
            timeout=120,
        )
    _require(
        acceptance.get("task_id") == TASK_ID
        and acceptance.get("phase") == PHASE
        and acceptance.get("status") == "PASS_CI_SYNTH_SCOPED"
        and acceptance.get("real_account_execution") == "NOT_RUN"
        and acceptance.get("real_media_network_execution") == "NOT_RUN",
        "media acceptance identity or execution boundary drifted",
    )
    url_fuzz = acceptance.get("url_fuzz", {})
    _require(
        url_fuzz.get("cases") == 512
        and url_fuzz.get("accepted_allowlisted") == 64
        and url_fuzz.get("rejected_forbidden") == 448
        and url_fuzz.get("oracle_mismatches") == 0,
        "URL fuzz acceptance drifted",
    )
    ssrf = acceptance.get("ssrf", {})
    _require(
        ssrf.get("cases") == 32
        and ssrf.get("forbidden_target_successes") == 0
        and ssrf.get("local_file_reads") == 0,
        "SSRF acceptance drifted",
    )
    cleanup = acceptance.get("cleanup", {})
    _require(
        cleanup.get("cases") == 8
        and cleanup.get("success_residual_files") == 0
        and cleanup.get("expired_residual_files") == 0
        and cleanup.get("active_lease_misdeletes") == 0
        and cleanup.get("delete_failures_with_high_priority_error_percent") == 100,
        "cleanup acceptance drifted",
    )
    persistence = acceptance.get("media_persistence", {})
    _require(
        persistence.get("scanner_scopes") == 5
        and persistence.get("platform_cdn_url_findings") == 0
        and persistence.get("sensitive_query_findings") == 0
        and persistence.get("canonical_query_or_fragment_findings") == 0
        and persistence.get("matched_values_emitted") is False,
        "zero-persistence acceptance drifted",
    )
    resources = acceptance.get("resource_limits", {})
    _require(
        resources.get("acquisition_cases") == 8
        and resources.get("structured_blocks") == 8
        and resources.get("companion_crashes") == 0,
        "acquisition resource acceptance drifted",
    )
    _require(
        acceptance.get("processor_acceptance", {}).get("status") == "DOWNSTREAM_NOT_RUN",
        "downstream processor scope was overstated",
    )
    unit = acceptance.get("unit_suite", {})
    _require(
        int(unit.get("tests", 0)) >= 23
        and unit.get("errors") == 0
        and unit.get("failures") == 0
        and unit.get("skips") == 0,
        "media unit suite drifted",
    )
    return Check(
        "media_security_acceptance",
        "PASS",
        {
            "active_lease_misdeletes": 0,
            "cleanup_cases": 8,
            "forbidden_target_successes": 0,
            "local_file_reads": 0,
            "resource_blocks": 8,
            "scanner_findings": 0,
            "ssrf_cases": 32,
            "unit_tests": unit["tests"],
            "url_fuzz_cases": 512,
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
    _require(report.get("blocking_results") == expected_results, "full lane execution identity or result drifted")
    _require(
        report.get("platform_calls") == 0
        and report.get("model_calls") == 0
        and report.get("real_accounts") == 0,
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
        and artifact.get("member_count") == 61
        and artifact.get("runtime_data_files") == 0
        and artifact.get("allowlist_findings") == 0,
        "full lane artifact gate failed",
    )
    return Check(
        "full_lane_replay",
        "PASS",
        {
            "artifact_members": 61,
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
        COMPANION_PACKAGE,
        MEDIA_SOURCE,
        STORE_SOURCE,
        MIGRATION_SOURCE,
        RUNTIME_CLI,
        PROJECT_ROOT / "apps/companion/tests/test_media_safety.py",
        RUN_CONTRACT,
        TASKPACK,
        TASK_STATE,
        PROJECT_FACT,
        ARCHITECTURE_FACT,
        MEDIA_POLICY,
        ARTIFACT_POLICY,
        GLOBAL_FIXTURE_MANIFEST,
        FIXTURE_MANIFEST,
        ACCEPTANCE_RUNNER,
        PROJECT_ROOT / "scripts/verify_skeleton_009.py",
        PROJECT_ROOT / "scripts/verify_skeleton_003.py",
        PROJECT_ROOT / "tests/test_skeleton_009.py",
        PROJECT_ROOT / "tests/test_skeleton_003.py",
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


def write_evidence(checks: list[Check]) -> None:
    names = {check.name for check in checks}
    _require(
        {"full_lane_replay", "media_security_acceptance", "worktree_isolation"} <= names,
        "evidence requires media acceptance, worktree and two-repetition full lane validation",
    )
    acceptance = next(check for check in checks if check.name == "media_security_acceptance")
    payload = {
        "acceptance_ids": [
            "ACC.x2n.media.001",
            "ACC.x2n.media.002",
            "ACC.x2n.media.003",
            "ACC.x2n.media.004",
        ],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.media.001": "PASS_CI_SYNTH_5_FIXED_SCOPES_ZERO_FINDINGS_OWNER_ALPHA_REAL_SINKS_NOT_RUN",
            "ACC.x2n.media.002": "PASS_CI_SYNTH_SUCCESS_AND_EXPIRED_RESIDUAL_0_ACTIVE_MISDELETE_0_DELETE_ERROR_RECEIPT_100_PERCENT",
            "ACC.x2n.media.003": "PASS_CI_SYNTH_512_URL_FUZZ_32_SSRF_FORBIDDEN_SUCCESS_0_LOCAL_FILE_READS_0",
            "ACC.x2n.media.004": "PASS_CI_SYNTH_ACQUISITION_LIMITS_PROCESSOR_FFMPEG_DECODE_KEYFRAME_DOWNSTREAM_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "matched_values_included": False,
        "media_processing": "NOT_RUN",
        "owner_canary": "NOT_RUN",
        "pattern_set_version": "x2n-media-zero-v1",
        "phase": PHASE,
        "platform_calls": 0,
        "private_content_included": False,
        "production_media_transport": "DISABLED",
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
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    _require(EVIDENCE.read_bytes() == _read_blob_at(FINAL_COMMIT, EVIDENCE), "historical evidence was rewritten")
    evidence = _load_json(EVIDENCE)
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
        and evidence.get("production_media_transport") == "DISABLED"
        and evidence.get("media_processing") == "NOT_RUN"
        and evidence.get("platform_calls") == 0,
        "real media/account execution overstated",
    )
    _require(evidence.get("matched_values_included") is False, "evidence includes scanner matches")
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check")
    metrics = evidence.get("task_metrics", {})
    _require(
        metrics.get("url_fuzz_cases") == 512
        and metrics.get("ssrf_cases") == 32
        and metrics.get("forbidden_target_successes") == 0
        and metrics.get("active_lease_misdeletes") == 0
        and metrics.get("scanner_findings") == 0,
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
    _require(all(check.status == "PASS" for check in checks), "a Skeleton003 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.003")
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
                {"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
