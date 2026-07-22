#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.001."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.skeleton.001"
RUN_ID = "RUN-X2N-S02-S001"
PHASE = "PH.X2N.2.1"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton001"
TASK_BASE_COMMIT = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
ORIGIN_CUTOFF = TASK_BASE_COMMIT
FINAL_COMMIT = "894553c6d15c3c73315e54429c8bd26588b6f83a"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
PLATFORM_FACT = PROJECT_ROOT / "machine/facts/platform_scope_registry.json"
PLATFORM_POLICY = PROJECT_ROOT / "machine/policy/platform_policy_registry.json"
PERMISSION_POLICY = PROJECT_ROOT / "machine/policy/extension_permission_policy.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "packages/test-fixtures/extension/v1/xhs_current_page/fixture_manifest.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
MANIFEST = PROJECT_ROOT / "apps/extension/manifest.json"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.001.json"
EXTENSION_ID = "chheapilbdfnpajmlkijppmblnlheeac"
CURRENT_PERMISSIONS = ["activeTab", "nativeMessaging", "scripting", "sidePanel"]

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/extension/manifest.json",
    "apps/extension/package.json",
    "apps/extension/scripts/extension-e2e.mjs",
    "apps/extension/scripts/self-test.mjs",
    "apps/extension/scripts/xhs-fixture-e2e.mjs",
    "apps/extension/sidepanel.html",
    "apps/extension/src/page-support.js",
    "apps/extension/src/service-worker.js",
    "apps/extension/src/sidepanel.js",
    "apps/extension/src/xhs-current-page.js",
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/tests/test_canonical_store.py",
    "docs/governance/PLATFORM_POLICY_REGISTER_S00_P05.md",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_001.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "machine/facts/architecture_decisions.json",
    "machine/facts/platform_scope_registry.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/extension_permission_policy.json",
    "machine/policy/platform_policy_registry.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/verify_foundation_001.py",
    "scripts/verify_foundation_002.py",
    "scripts/verify_foundation_003.py",
    "scripts/verify_foundation_004.py",
    "scripts/verify_foundation_005.py",
    "scripts/verify_phase_0_2.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_skeleton_001.py",
    "scripts/verify_stage_0_review.py",
    "scripts/verify_stage_1_review.py",
    "tests/test_foundation_001.py",
    "tests/test_foundation_002.py",
    "tests/test_foundation_003.py",
    "tests/test_foundation_004.py",
    "tests/test_foundation_005.py",
    "tests/test_phase_0_1.py",
    "tests/test_phase_0_2.py",
    "tests/test_phase_0_5.py",
    "tests/test_skeleton_001.py",
    "tests/test_stage_0_review.py",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = (
    "evidence/adapters/",
    "packages/test-fixtures/extension/v1/xhs_current_page/",
)


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"JSON unavailable: {path.name}") from error
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _read_blob_at(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )
    _require(result.returncode == 0, f"historical blob unavailable: {relative}")
    return result.stdout


def _read_text_at(commit: str, path: Path) -> str:
    try:
        return _read_blob_at(commit, path).decode("utf-8")
    except UnicodeDecodeError as error:
        raise VerificationError(f"historical text is not UTF-8: {path.name}") from error


def _load_json_at(commit: str, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_text_at(commit, path), object_pairs_hook=_pairs)
    except json.JSONDecodeError as error:
        raise VerificationError(f"historical JSON invalid: {path.name}") from error
    _require(isinstance(value, dict), f"historical JSON object required: {path.name}")
    return value


def _git(args: Sequence[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, "Git scope check failed")
    return result.stdout.rstrip()


def _porcelain_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value)
    return paths


def _project_relative(path: str) -> Optional[str]:
    prefix = "xhs-douyin-2notion/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return "" if path == "xhs-douyin-2notion" else None


def _task_block(text: str, task_id: str) -> str:
    match = re.search(
        rf"(?ms)^- id: {re.escape(task_id)}\n(?P<body>.*?)(?=^- id: TSK\.x2n\.|\Z)",
        text,
    )
    _require(match is not None, f"Task block missing: {task_id}")
    return match.group(0)


def _field(block: str, name: str) -> str:
    match = re.search(rf"(?m)^  {re.escape(name)}: ([^\n]+)$", block)
    _require(match is not None, f"Task field missing: {name}")
    return match.group(1).strip().strip("'\"")


def _list_field(block: str, name: str) -> list[str]:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(?P<items>(?:  - [^\n]+\n)*)", block)
    _require(match is not None, f"Task list missing: {name}")
    return [line.removeprefix("  - ") for line in match.group("items").splitlines()]


def _iter_files() -> Iterable[Path]:
    ignored = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and not any(part in ignored for part in path.parts):
            yield path


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    relative_changes: list[str] = []
    for path in sorted(set(committed)):
        relative = _project_relative(path)
        _require(relative is not None, "Skeleton001 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton001 change: {relative}",
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
    scanned = 0
    files = list(_iter_files())
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(
            not any(token in text for token in forbidden_tokens),
            "forbidden repository, path, or credential token entered x2n",
        )
        _require(cdn_pattern.search(text) is None, "platform media CDN URL entered x2n")
        _require(
            re.search(r"(?i)(?:xsec_token|signature|auth_key)=", text) is None, "signed platform parameter entered x2n"
        )
        scanned += 1
    forbidden_suffixes = {
        ".sqlite",
        ".sqlite3",
        ".db",
        ".mp4",
        ".mov",
        ".m4a",
        ".mp3",
        ".wav",
        ".webm",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".heic",
        ".pem",
        ".p12",
        ".pfx",
    }
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in files), "Runtime/private file entered x2n")
    return Check(
        "scope_and_privacy",
        "PASS",
        {
            "changed_files": len(relative_changes),
            "out_of_scope_writes": 0,
            "private_runtime_files": 0,
            "sensitive_or_media_url_hits": 0,
            "text_files_scanned": scanned,
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    current_branch = _git(["branch", "--show-current"])
    _require(current_branch not in {"", "main"}, "Skeleton001 regression must run in a non-main worktree")
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
        "Skeleton001 final commit no longer descends from its Task base",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current tree no longer descends from the Skeleton001 final commit",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the Run cutoff",
    )
    origin_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{ORIGIN_CUTOFF}..{live_origin}"]
    ).splitlines()
    origin_overlap = sum(
        path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in origin_paths
    )

    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(
        main_path is not None and _git(["branch", "--show-current"], main_path) == "main",
        "MetaDatabase main worktree unavailable or off main",
    )
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


def validate_task_and_state() -> Check:
    taskpack = _read_text_at(FINAL_COMMIT, TASKPACK)
    task = _task_block(taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton001 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Skeleton001 routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.foundation.004", "TSK.x2n.foundation.005"],
        "Skeleton001 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.capture.001", "ACC.x2n.ext.001"],
        "Skeleton001 Acceptance drifted",
    )
    _require("  status: STAGE_2_SKELETON_001_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack current status drifted")

    current_task = _task_block(TASKPACK.read_text(encoding="utf-8"), TASK_ID)
    for name in ("status", "stage", "phase"):
        _require(_field(current_task, name) == _field(task, name), f"Skeleton001 current Task field drifted: {name}")
    for name in ("depends_on", "acceptance_ids"):
        _require(_list_field(current_task, name) == _list_field(task, name), f"Skeleton001 Task list drifted: {name}")

    state = _load_json_at(FINAL_COMMIT, TASK_STATE)
    _require(state.get("schema_version") == "1.9", "task state schema drifted")
    _require(
        state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE,
        "current Stage routing drifted",
    )
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run identity drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton001 state is not pass")
    _require(
        state.get("next_phase") == "PH.X2N.2.2" and state.get("next_run") == "TSK.x2n.skeleton.002",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.capture.001") == "pass_ci_synth_5_of_5_owner_canary_not_run",
        "capture Acceptance scope drifted",
    )
    _require(
        acceptance.get("ACC.x2n.ext.001")
        == "pass_stage_1_scaffold_plus_xhs_current_page_ci_synth_owner_canary_not_run",
        "Extension Acceptance scope drifted",
    )
    _require(
        state.get("xhs_current_page_execution")
        == "pass_ci_synth_real_page_policy_disabled_action_before_grant_rejected_owner_canary_not_run",
        "XHS execution scope drifted",
    )
    for field in (
        "real_account_execution",
        "platform_calls",
        "notion_calls",
        "model_calls",
        "media_processing",
        "real_sink_execution",
    ):
        _require(state.get(field) == "not_run", f"downstream execution overstated: {field}")
    project = _load_json_at(FINAL_COMMIT, PROJECT_FACT)
    _require(project.get("status") == "stage_2_skeleton_001_pass_g2_not_run", "project state drifted")
    architecture = _load_json_at(FINAL_COMMIT, ARCHITECTURE_FACT)
    _require(
        architecture.get("phase") == PHASE and architecture.get("stage_gate") == "g2_not_run",
        "architecture state drifted",
    )
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 2,
            "next_task": "TSK.x2n.skeleton.002",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "real_page_execution": "DISABLED",
            "single_task": True,
        },
    )


def validate_extension_surface() -> Check:
    manifest = _load_json(MANIFEST)
    _require(
        manifest.get("manifest_version") == 3 and manifest.get("minimum_chrome_version") == "120",
        "MV3 baseline drifted",
    )
    _require(manifest.get("permissions") == CURRENT_PERMISSIONS, "permission allowlist drifted")
    _require(
        "host_permissions" not in manifest and "content_scripts" not in manifest,
        "persistent host/content script surface entered extension",
    )
    _require(
        manifest.get("content_security_policy", {}).get("extension_pages") == "script-src 'self'; object-src 'none';",
        "Extension CSP weakened",
    )
    policy = _load_json_at(FINAL_COMMIT, PERMISSION_POLICY)
    rows = policy.get("permissions", [])
    _require([row.get("name") for row in rows] == CURRENT_PERMISSIONS, "permission policy mapping drifted")
    _require(
        all(row.get("requirements") and row.get("persistent_host_access") is False for row in rows),
        "permission requirement mapping incomplete",
    )
    _require(policy.get("host_permissions") == [] and policy.get("content_scripts") == [], "permission policy widened")
    _require(
        policy.get("feature_flag")
        == {
            "name": "xiaohongshu_current_page",
            "value": "ci_synth_only",
            "real_page_execution": False,
            "owner_canary": "not_run",
        },
        "XHS feature flag scope drifted",
    )

    paths = [
        PROJECT_ROOT / "apps/extension/sidepanel.html",
        PROJECT_ROOT / "apps/extension/src/page-support.js",
        PROJECT_ROOT / "apps/extension/src/service-worker.js",
        PROJECT_ROOT / "apps/extension/src/sidepanel.js",
        PROJECT_ROOT / "apps/extension/src/xhs-current-page.js",
    ]
    sources = {path.name: path.read_text(encoding="utf-8") for path in paths}
    rendered = "\n".join(sources.values())
    for pattern in (
        r"\beval\s*\(",
        r"new Function\s*\(",
        r"chrome\.storage",
        r"document\.cookie",
        r"\bfetch\s*\(",
        r"XMLHttpRequest",
        r"\.scroll(?:By|To)?\s*\(",
        r"\.innerHTML\s*=",
    ):
        _require(
            re.search(pattern, rendered, flags=re.IGNORECASE) is None,
            "remote/dynamic/persistent or state-changing extension surface detected",
        )
    _require('xiaohongshu: "ci_synth_only"' in sources["page-support.js"], "real XHS page gate is not closed")
    _require(
        "chrome.action.onClicked.addListener" in sources["service-worker.js"], "Extension Action user gesture missing"
    )
    _require("chrome.sidePanel.open" in sources["service-worker.js"], "Side Panel action open missing")
    _require("chrome.scripting.executeScript" in sources["service-worker.js"], "isolated page extraction missing")
    _require('world: "ISOLATED"' in sources["service-worker.js"], "page extraction world is not isolated")
    _require(
        'sender.url === chrome.runtime.getURL("sidepanel.html")' in sources["service-worker.js"],
        "Side Panel sender identity weakened",
    )
    _require(
        "auto_scroll: false" in sources["xhs-current-page.js"]
        and "change_account_state: false" in sources["xhs-current-page.js"],
        "capture safety literals drifted",
    )
    _require(
        '.getAttribute("src")' not in sources["xhs-current-page.js"] and ".src" not in sources["xhs-current-page.js"],
        "media source read entered extractor",
    )
    return Check(
        "extension_permission_and_security_surface",
        "PASS",
        {
            "content_scripts": 0,
            "host_permissions": 0,
            "permissions": len(CURRENT_PERMISSIONS),
            "real_page_execution": "DISABLED",
            "remote_code": 0,
            "storage_permissions": 0,
        },
    )


def validate_fixtures_and_policy() -> Check:
    fixture = _load_json(FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S001.001" and fixture.get("synthetic") is True,
        "XHS fixture identity drifted",
    )
    cases = fixture.get("cases", [])
    _require(isinstance(cases, list) and len(cases) == 5, "XHS fixture count drifted")
    _require(len({item.get("id") for item in cases}) == 5, "XHS fixture IDs are not unique")
    _require(
        sum(item.get("expected", {}).get("status") == "ready" for item in cases) == 3, "ready fixture threshold drifted"
    )
    _require(
        sum(item.get("expected", {}).get("status") == "platform_changed" for item in cases) == 2,
        "platform-changed fixture threshold drifted",
    )
    for field in (
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_real_accounts",
        "real_accounts",
    ):
        _require(fixture.get(field) is False, f"XHS fixture public boundary weakened: {field}")
    fixture_root = FIXTURE_MANIFEST.parent
    html_bytes = 0
    for item in cases:
        name = item.get("file")
        _require(isinstance(name, str) and re.fullmatch(r"[a-z_]+\.html", name) is not None, "unsafe fixture filename")
        path = fixture_root / name
        _require(path.is_file() and path.resolve().is_relative_to(fixture_root.resolve()), "XHS HTML fixture missing")
        html = path.read_text(encoding="utf-8")
        _require(
            re.search(r"<script|\bsrc\s*=|<form", html, flags=re.IGNORECASE) is None,
            "executable, media-source, or form surface entered fixture",
        )
        html_bytes += len(html.encode("utf-8"))
    global_rows = _load_json(GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    expected_row = {
        "id": "FIXTURE.X2N.S02.S001.001",
        "path": "packages/test-fixtures/extension/v1/xhs_current_page/fixture_manifest.json",
        "case_count": 5,
        "purpose": "Xiaohongshu current-page stable ID, sanitized facts, missing fields, platform change and feed-card rejection",
    }
    _require(expected_row in global_rows, "XHS fixture is not globally registered")
    platform = _load_json_at(FINAL_COMMIT, PLATFORM_FACT)
    xhs = next((item for item in platform.get("platforms", []) if item.get("id") == "xiaohongshu"), {})
    _require(xhs.get("policy_state") == "unknown_disabled", "real XHS policy state was enabled")
    _require(
        xhs.get("current_page_implementation_state") == "ci_synth_pass_real_page_disabled_owner_canary_not_run",
        "XHS implementation scope drifted",
    )
    policy = _load_json_at(FINAL_COMMIT, PLATFORM_POLICY)
    _require(policy.get("research_cutoff") == "2026-07-22", "platform policy recheck date drifted")
    _require(
        policy.get("capability_states", {}).get("xiaohongshu_current_page")
        == "ci_synth_only_policy_unknown_real_page_disabled_owner_canary_not_run",
        "real XHS policy gate was widened",
    )
    return Check(
        "fixtures_and_platform_policy",
        "PASS",
        {
            "fixture_cases": 5,
            "fixture_html_bytes": html_bytes,
            "platform_changed_cases": 2,
            "policy_state": "UNKNOWN_DISABLED_REAL",
            "ready_cases": 3,
            "synthetic_only": True,
        },
    )


def _isolated_env(home: Path, *, require_browser: bool = False) -> dict[str, str]:
    env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
        "UV_CACHE_DIR": str(home / "uv-cache"),
        "UV_INDEX_URL": "https://pypi.org/simple",
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_NO_CONFIG": "1",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
        "npm_config_update_notifier": "false",
    }
    configured_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    browser_cache = Path(configured_cache) if configured_cache else Path.home() / "Library/Caches/ms-playwright"
    if browser_cache.is_dir():
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    elif require_browser:
        raise VerificationError("Playwright Chromium cache is unavailable")
    return env


def _run_external(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int) -> str:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    _require(result.returncode == 0, f"external Skeleton001 verification failed: {label}")
    combined = result.stdout + result.stderr
    _require(
        "/" + "Users/" not in combined and "github" + "_pat_" not in combined,
        f"external verification exposed private data: {label}",
    )
    return combined


def _json_line(output: str, label: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.startswith("{")]
    _require(len(lines) == 1, f"external JSON output is ambiguous: {label}")
    try:
        value = json.loads(lines[0], object_pairs_hook=_pairs)
    except json.JSONDecodeError as error:
        raise VerificationError(f"external JSON output is invalid: {label}") from error
    _require(isinstance(value, dict), f"external JSON output is not an object: {label}")
    return value


def validate_execution() -> Check:
    for command in ("node", "npm", "uv"):
        _require(shutil.which(command) is not None, f"required verifier tool unavailable: {command}")
    with tempfile.TemporaryDirectory(prefix="x2n-s001-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, require_browser=True)
        self_test = _json_line(
            _run_external(
                "extension_self_test",
                ("npm", "run", "self-test", "--workspace", "@x2n/extension"),
                env=env,
                timeout=120,
            ),
            "extension_self_test",
        )
        fixture_e2e = _json_line(
            _run_external(
                "xhs_fixture_e2e",
                ("npm", "run", "test:xhs-fixtures", "--workspace", "@x2n/extension"),
                env=env,
                timeout=240,
            ),
            "xhs_fixture_e2e",
        )
        extension_e2e = _json_line(
            _run_external(
                "extension_e2e",
                ("npm", "run", "test:e2e", "--workspace", "@x2n/extension"),
                env=env,
                timeout=1_200,
            ),
            "extension_e2e",
        )
    _require(
        self_test.get("status") == "PASS"
        and self_test.get("extension_id") == EXTENSION_ID
        and self_test.get("fixture_recognition_passed") == self_test.get("fixture_cases") == 20
        and self_test.get("xhs_fixture_cases") == 5
        and self_test.get("permissions") == 4,
        "Extension self-test metrics drifted",
    )
    expected_fixture = {
        "console_uncaught_errors": 0,
        "fixture_cases": 5,
        "observation_diff_mismatches": 0,
        "owner_canary": "NOT_RUN",
        "platform_changed_verified": 2,
        "platform_calls": 0,
        "query_fragment_persisted": 0,
        "stable_ids_verified": 3,
        "status": "PASS",
    }
    _require(fixture_e2e == expected_fixture, "XHS fixture E2E metrics drifted")
    expected_extension = {
        "console_uncaught_errors": 0,
        "duplicate_jobs": 0,
        "extension_id_match": True,
        "fixture_cases": 20,
        "fixture_recognition_passed": 20,
        "lost_jobs": 0,
        "owner_canary": "NOT_RUN",
        "platform_calls": 0,
        "real_accounts": 0,
        "request_ledger_rows": 1,
        "service_worker_restarts": 100,
        "status": "PASS",
        "wrong_statuses": 0,
        "xhs_action_before_grant_rejections": 2,
        "xhs_action_trigger": "PASS_CDP_DEFAULT_ACTION",
        "xhs_current_page_capture": "PASS_CI_SYNTH",
        "xhs_owner_canary": "NOT_RUN",
        "xhs_query_fragment_persisted": 0,
    }
    for key, expected in expected_extension.items():
        _require(extension_e2e.get(key) == expected, f"Extension E2E metric drifted: {key}")
    receipts: dict[str, dict[str, Any]] = {}
    for name in ("screenshot", "trace"):
        receipt = extension_e2e.get(name, {})
        _require(isinstance(receipt.get("bytes"), int) and receipt["bytes"] > 0, f"E2E {name} is empty")
        _require(
            re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256", ""))) is not None, f"E2E {name} receipt invalid"
        )
        receipts[name] = receipt
    return Check(
        "isolated_current_page_e2e",
        "PASS",
        {
            "action_before_grant_rejections": 2,
            "fixture_cases": 5,
            "observation_diff_mismatches": 0,
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "query_fragment_persisted": 0,
            "screenshot": receipts["screenshot"],
            "service_worker_restarts": 100,
            "stable_ids_verified": 3,
            "trace": receipts["trace"],
        },
    )


def _acceptance_input_receipt() -> str:
    historical_fixture = _load_json_at(FINAL_COMMIT, FIXTURE_MANIFEST)
    paths = [
        MANIFEST,
        PERMISSION_POLICY,
        PLATFORM_FACT,
        PLATFORM_POLICY,
        TASK_STATE,
        TASKPACK,
        FIXTURE_MANIFEST,
        *[FIXTURE_MANIFEST.parent / item["file"] for item in historical_fixture["cases"]],
        PROJECT_ROOT / "apps/extension/sidepanel.html",
        PROJECT_ROOT / "apps/extension/src/page-support.js",
        PROJECT_ROOT / "apps/extension/src/service-worker.js",
        PROJECT_ROOT / "apps/extension/src/sidepanel.js",
        PROJECT_ROOT / "apps/extension/src/xhs-current-page.js",
        PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/xhs-fixture-e2e.mjs",
        PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
        PROJECT_ROOT / "apps/companion/tests/test_canonical_store.py",
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
    _require(_git(["rev-parse", "HEAD"]) == FINAL_COMMIT, "historical Skeleton001 evidence is immutable")
    names = {check.name for check in checks}
    _require(
        {"isolated_current_page_e2e", "worktree_isolation"} <= names,
        "evidence requires full E2E and worktree validation",
    )
    payload = {
        "acceptance_ids": ["ACC.x2n.capture.001", "ACC.x2n.ext.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.capture.001": "PASS_CI_SYNTH_5_OF_5_OWNER_CANARY_NOT_RUN_REAL_PAGE_DISABLED",
            "ACC.x2n.ext.001": "PASS_XHS_CURRENT_PAGE_CI_SYNTH_ACTION_GATED_OWNER_CANARY_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "feature_flag": "CI_SYNTH_ONLY_REAL_PAGE_DISABLED",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
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
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _require(EVIDENCE.read_bytes() == _read_blob_at(FINAL_COMMIT, EVIDENCE), "historical evidence was rewritten")
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_SCOPED" and evidence.get("stage_gate") == "G2_NOT_RUN",
        "evidence status overstated",
    )
    _require(evidence.get("feature_flag") == "CI_SYNTH_ONLY_REAL_PAGE_DISABLED", "evidence real-page gate drifted")
    _require(
        evidence.get("owner_canary") == "NOT_RUN" and evidence.get("real_account_execution") == "NOT_RUN",
        "Owner execution overstated",
    )
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(
        all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check"
    )
    return Check(
        "evidence",
        "PASS",
        {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID},
    )


def run_checks(*, verify_worktree: bool, allow_external_main_dirty: bool, run_external: bool) -> list[Check]:
    checks = [
        validate_scope(),
        validate_task_and_state(),
        validate_extension_surface(),
        validate_fixtures_and_policy(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_execution())
    _require(all(check.status == "PASS" for check in checks), "a Skeleton001 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.001")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_external=not args.skip_external,
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
            file=os.sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
