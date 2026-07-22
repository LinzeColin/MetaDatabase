#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.006."""

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
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.skeleton.006"
RUN_ID = "RUN-X2N-S02-S006"
PHASE = "PH.X2N.2.3"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton006"
TASK_BASE_COMMIT = "2a91efbc899aaaf3f6191ba3fb93ac825e3a9a0d"
ORIGIN_CUTOFF = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_SKELETON_006.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
PLATFORM_FACT = PROJECT_ROOT / "machine/facts/platform_scope_registry.json"
PLATFORM_POLICY = PROJECT_ROOT / "machine/policy/platform_policy_registry.json"
BILIBILI_POLICY = PROJECT_ROOT / "machine/policy/bilibili_current_page_policy.json"
PERMISSION_POLICY = PROJECT_ROOT / "machine/policy/extension_permission_policy.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
FIXTURE_MANIFEST = (
    PROJECT_ROOT / "packages/test-fixtures/extension/v1/bilibili_current_page/fixture_manifest.json"
)
MANIFEST = PROJECT_ROOT / "apps/extension/manifest.json"
NATIVE_POLICY = PROJECT_ROOT / "apps/companion/native-host/policy.json"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.006.json"
EXTENSION_ID = "chheapilbdfnpajmlkijppmblnlheeac"
CURRENT_PERMISSIONS = ["activeTab", "nativeMessaging", "scripting", "sidePanel"]
NATIVE_ACTIONS = [
    "capture_current",
    "start_sync",
    "get_job",
    "cancel_job",
    "retry_job",
    "get_capabilities",
    "health",
]
FULL_LANE_GATES = (
    "format",
    "lint",
    "python_compile",
    "typescript_contract",
    "root_unit",
    "companion_unit_integration",
    "contract_unit",
    "contract_acceptance",
    "sbom_drift",
    "scaffold_acceptance",
    "migration_integration",
    "extension_native_e2e",
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/extension/package.json",
    "apps/extension/scripts/bilibili-fixture-e2e.mjs",
    "apps/extension/scripts/extension-e2e.mjs",
    "apps/extension/scripts/self-test.mjs",
    "apps/extension/src/bilibili-current-page.js",
    "apps/extension/src/page-support.js",
    "apps/extension/src/service-worker.js",
    "apps/extension/src/sidepanel.js",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_006.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.skeleton.006.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/platform_scope_registry.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/bilibili_current_page_policy.json",
    "machine/policy/platform_policy_registry.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/verify_skeleton_002.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_skeleton_006.py",
    "tests/test_phase_0_5.py",
    "tests/test_skeleton_002.py",
    "tests/test_skeleton_006.py",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/extension/v1/bilibili_current_page/",)


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


def _load_json_at(commit: str, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_blob_at(commit, path).decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
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
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...HEAD"]
    ).splitlines()
    working = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    relative_changes: list[str] = []
    for path in sorted(set(committed + working)):
        relative = _project_relative(path)
        _require(relative is not None, "Skeleton006 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton006 change: {relative}",
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
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in files), "private runtime artifact entered x2n")
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
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Skeleton006 worktree branch")
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
        "Skeleton006 branch no longer descends from its Task base",
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
            "branch": BRANCH,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": main_overlap,
        },
    )


def validate_task_and_state() -> Check:
    taskpack = TASKPACK.read_text(encoding="utf-8")
    task = _task_block(taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton006 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.foundation.004", "TSK.x2n.foundation.005"],
        "Skeleton006 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.capture.003", "ACC.x2n.ext.001"],
        "Skeleton006 Acceptance drifted",
    )
    _require("  status: STAGE_2_SKELETON_006_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack status drifted")
    next_task = _task_block(taskpack, "TSK.x2n.skeleton.007")
    _require(_field(next_task, "status") == "planned", "Skeleton007 was entered by this Run")

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.11", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton006 state is not pass")
    _require("TSK.x2n.skeleton.007" not in state.get("tasks", {}), "Skeleton007 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.2.4" and state.get("next_run") == "TSK.x2n.skeleton.007",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.capture.003")
        == "pass_ci_synth_10_dom_plus_8_policy_owner_canary_not_run_real_page_disabled",
        "Bilibili capture Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.ext.001")
        == "pass_stage_1_scaffold_plus_xhs_douyin_bilibili_current_page_ci_synth_owner_canary_not_run",
        "Extension Acceptance drifted",
    )
    _require(
        state.get("bilibili_current_page_execution")
        == "pass_ci_synth_real_page_and_api_disabled_semantic_query_rejected_action_before_grant_rejected_owner_canary_not_run",
        "Bilibili execution boundary drifted",
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
    _require(_load_json(PROJECT_FACT).get("status") == "stage_2_skeleton_006_pass_g2_not_run", "project drifted")
    architecture = _load_json(ARCHITECTURE_FACT)
    _require(architecture.get("phase") == PHASE and architecture.get("stage_gate") == "g2_not_run", "ADR drifted")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    for value in (TASK_ID, RUN_ID, PHASE, TASK_BASE_COMMIT, BRANCH, "PASS_CI_SYNTH_SCOPED"):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 2,
            "next_task": "TSK.x2n.skeleton.007",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "real_page_execution": "DISABLED",
            "single_task": True,
        },
    )


def validate_extension_surface() -> Check:
    manifest = _load_json(MANIFEST)
    _require(manifest == _load_json_at(TASK_BASE_COMMIT, MANIFEST), "Extension Manifest changed in Skeleton006")
    _require(manifest.get("manifest_version") == 3 and manifest.get("minimum_chrome_version") == "120", "MV3 drifted")
    _require(manifest.get("permissions") == CURRENT_PERMISSIONS, "permission allowlist drifted")
    _require("host_permissions" not in manifest and "content_scripts" not in manifest, "persistent page access entered")
    _require(
        manifest.get("content_security_policy", {}).get("extension_pages") == "script-src 'self'; object-src 'none';",
        "Extension CSP weakened",
    )
    permission = _load_json(PERMISSION_POLICY)
    _require([item.get("name") for item in permission.get("permissions", [])] == CURRENT_PERMISSIONS, "permission policy drifted")
    _require(permission.get("host_permissions") == [] and permission.get("content_scripts") == [], "policy widened")
    native = _load_json(NATIVE_POLICY)
    _require(native == _load_json_at(TASK_BASE_COMMIT, NATIVE_POLICY), "Native policy changed in Skeleton006")
    _require(native.get("schema_version") == "1.0" and native.get("allowed_actions") == NATIVE_ACTIONS, "Native v1.0 widened")

    source_paths = sorted((PROJECT_ROOT / "apps/extension/src").glob("*.js"))
    sources = {path.name: path.read_text(encoding="utf-8") for path in source_paths}
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
        r"chrome\.tabs\.update",
    ):
        _require(re.search(pattern, rendered, flags=re.IGNORECASE) is None, "unsafe Extension surface detected")
    page_support = sources["page-support.js"]
    worker = sources["service-worker.js"]
    panel = sources["sidepanel.js"]
    bilibili = sources["bilibili-current-page.js"]
    _require('bilibili: "ci_synth_only"' in page_support, "Bilibili feature gate drifted")
    _require('startsWith("synthetic-bili-video-")' in page_support, "Bilibili video synthetic gate missing")
    _require('startsWith("synthetic-bili-article-")' in page_support, "Bilibili article synthetic gate missing")
    _require("bilibili_semantic_query_unsupported" in page_support, "semantic Query policy gate missing")
    _require("buildBilibiliCapturePayload" in worker and "extractBilibiliCurrentPage" in worker, "Bilibili adapter missing")
    _require('world: "ISOLATED"' in worker and "currentTab.url !== tab.url" in worker, "injection race gate missing")
    _require('bilibili: "Bilibili"' in panel and "captureInFlight" in panel, "Side Panel gate missing")
    _require("auto_scroll: false" in bilibili and "change_account_state: false" in bilibili, "capture literals drifted")
    _require("semantic_query_unsupported" in bilibili, "semantic Query extractor gate missing")
    _require('.getAttribute("src")' not in bilibili and ".src" not in bilibili, "media source read entered extractor")
    _require("hydration" not in bilibili.lower() and "innerhtml" not in bilibili.lower(), "raw page state read entered extractor")
    package = _load_json(PROJECT_ROOT / "apps/extension/package.json")
    scripts = package.get("scripts", {})
    _require(scripts.get("test:bilibili-fixtures") == "node scripts/bilibili-fixture-e2e.mjs", "fixture script missing")
    _require(scripts.get("test:bilibili-extension") == "node scripts/extension-e2e.mjs bilibili", "E2E script missing")
    return Check(
        "extension_permission_and_security_surface",
        "PASS",
        {
            "content_scripts": 0,
            "host_permissions": 0,
            "native_actions": len(NATIVE_ACTIONS),
            "permissions": len(CURRENT_PERMISSIONS),
            "production_network_transport": 0,
            "real_page_execution": "DISABLED",
        },
    )


def validate_fixtures_and_policy() -> Check:
    fixture = _load_json(FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S006.001" and fixture.get("synthetic") is True,
        "fixture drifted",
    )
    cases = fixture.get("cases", [])
    policy_cases = fixture.get("policy_cases", [])
    _require(isinstance(cases, list) and len(cases) == 10, "Bilibili DOM fixture count drifted")
    _require(isinstance(policy_cases, list) and len(policy_cases) == 8, "Bilibili policy fixture count drifted")
    _require(len({item.get("id") for item in cases}) == 10, "DOM fixture IDs are not unique")
    _require(len({item.get("id") for item in policy_cases}) == 8, "policy fixture IDs are not unique")
    _require(sum(item.get("expected", {}).get("status") == "ready" for item in cases) == 5, "ready threshold drifted")
    _require(
        sum(item.get("expected", {}).get("status") == "platform_changed" for item in cases) == 5,
        "platform-changed threshold drifted",
    )
    _require(
        fixture.get("route_assumptions", {}).get("article_read_cv_route")
        == "unverified_real_route_not_enabled",
        "article route assumption was overstated",
    )
    for field in (
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_real_accounts",
        "real_accounts",
    ):
        _require(fixture.get(field) is False, f"fixture public boundary weakened: {field}")
    fixture_root = FIXTURE_MANIFEST.parent
    html_bytes = 0
    for item in cases:
        name = item.get("file")
        _require(isinstance(name, str) and re.fullmatch(r"[a-z_]+\.html", name) is not None, "unsafe fixture filename")
        path = fixture_root / name
        _require(path.is_file() and path.resolve().is_relative_to(fixture_root.resolve()), "HTML fixture missing")
        html = path.read_text(encoding="utf-8")
        _require(
            re.search(r"<(?:form|iframe|script)\b|\b(?:poster|src|srcset)\s*=|url\s*\(", html, flags=re.IGNORECASE)
            is None,
            "unsafe fixture surface",
        )
        html_bytes += len(html.encode("utf-8"))
    for item in policy_cases:
        parsed = urlsplit(str(item.get("url", "")))
        _require(parsed.scheme == "https" and not parsed.username and not parsed.password, "unsafe policy fixture URL")

    global_rows = _load_json(GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S02.S006.001",
            "path": "packages/test-fixtures/extension/v1/bilibili_current_page/fixture_manifest.json",
            "case_count": 18,
            "purpose": "Bilibili current-page video/article identity, sanitized facts, semantic-query rejection, schema drift and real-page policy-disabled behavior",
        }
        in global_rows,
        "Bilibili fixture is not globally registered",
    )
    policy = _load_json(BILIBILI_POLICY)
    _require(policy.get("phase") == PHASE and policy.get("default") == "deny", "Bilibili policy identity drifted")
    _require(policy.get("production_network_transport") is False, "production network transport was enabled")
    _require(
        policy.get("feature_flag")
        == {
            "name": "bilibili_current_page",
            "value": "ci_synth_only",
            "real_page_execution": False,
            "owner_canary": "not_run",
        },
        "Bilibili feature flag drifted",
    )
    _require(
        policy.get("route_evidence", {}).get("article_read_route")
        == "unverified_route_assumption_ci_fixture_only",
        "article route was overstated",
    )
    platform = _load_json(PLATFORM_FACT)
    bilibili_fact = next((item for item in platform.get("platforms", []) if item.get("id") == "bilibili"), {})
    _require(bilibili_fact.get("policy_state") == "unknown_disabled", "real Bilibili policy was enabled")
    _require(
        bilibili_fact.get("current_page_implementation_state")
        == "ci_synth_pass_real_page_and_api_disabled_article_route_unverified_owner_canary_not_run",
        "Bilibili platform fact drifted",
    )
    registry = _load_json(PLATFORM_POLICY)
    _require(registry.get("phase") == PHASE and registry.get("research_cutoff") == "2026-07-22", "policy recheck drifted")
    official_sources = registry.get("official_sources", {}).get("bilibili", [])
    _require(isinstance(official_sources, list) and len(official_sources) >= 10, "official Bilibili evidence incomplete")
    _require(
        all(urlsplit(value).hostname in {"openhome.bilibili.com", "www.bilibili.com"} for value in official_sources),
        "non-first-party Bilibili evidence entered registry",
    )
    _require(
        registry.get("capability_states", {}).get("bilibili_current_page")
        == "ci_synth_only_policy_unknown_real_page_and_api_disabled_article_route_unverified_owner_canary_not_run",
        "real Bilibili policy gate widened",
    )
    return Check(
        "fixtures_and_platform_policy",
        "PASS",
        {
            "dom_fixture_cases": 10,
            "fixture_html_bytes": html_bytes,
            "platform_changed_cases": 5,
            "policy_cases": 8,
            "policy_state": "UNKNOWN_DISABLED_REAL",
            "ready_cases": 5,
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
    _require(result.returncode == 0, f"external Skeleton006 verification failed: {label}")
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
        raise VerificationError(f"external JSON invalid: {label}") from error
    _require(isinstance(value, dict), f"external JSON is not an object: {label}")
    return value


def _require_metrics(value: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    for key, expected_value in expected.items():
        _require(value.get(key) == expected_value, f"{label} metric drifted: {key}")


def _validate_extension_metrics(value: dict[str, Any], prefix: str) -> dict[str, dict[str, Any]]:
    expected = {
        "blocked_platform_network_requests": 0,
        "console_uncaught_errors": 0,
        "duplicate_jobs": 0,
        "extension_id_match": True,
        "fixture_cases": 20,
        "fixture_documents_fulfilled": 1,
        "fixture_recognition_passed": 20,
        "lost_jobs": 0,
        "owner_canary": "NOT_RUN",
        "platform_calls": 0,
        "platform_requests_observed": 1,
        "real_accounts": 0,
        "request_ledger_rows": 1,
        "service_worker_restarts": 100,
        "status": "PASS",
        "wrong_statuses": 0,
        f"{prefix}_action_before_grant_rejections": 2,
        f"{prefix}_action_trigger": "PASS_CDP_DEFAULT_ACTION",
        f"{prefix}_current_page_capture": "PASS_CI_SYNTH",
        f"{prefix}_owner_canary": "NOT_RUN",
        f"{prefix}_query_fragment_persisted": 0,
    }
    _require_metrics(value, expected, f"Extension E2E {prefix}")
    receipts: dict[str, dict[str, Any]] = {}
    for name in ("screenshot", "trace"):
        receipt = value.get(name, {})
        _require(isinstance(receipt.get("bytes"), int) and receipt["bytes"] > 0, f"{prefix} {name} empty")
        _require(re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256", ""))) is not None, f"{prefix} {name} invalid")
        receipts[name] = receipt
    return receipts


def validate_execution() -> Check:
    for command in ("node", "npm", "uv"):
        _require(shutil.which(command) is not None, f"required verifier tool unavailable: {command}")
    with tempfile.TemporaryDirectory(prefix="x2n-s006-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, require_browser=True)
        commands = {
            "self_test": ("npm", "run", "self-test", "--workspace", "@x2n/extension"),
            "xhs_fixture": ("npm", "run", "test:xhs-fixtures", "--workspace", "@x2n/extension"),
            "douyin_fixture": ("npm", "run", "test:douyin-fixtures", "--workspace", "@x2n/extension"),
            "bilibili_fixture": ("npm", "run", "test:bilibili-fixtures", "--workspace", "@x2n/extension"),
            "xhs_extension": ("npm", "run", "test:e2e", "--workspace", "@x2n/extension"),
            "douyin_extension": ("npm", "run", "test:douyin-extension", "--workspace", "@x2n/extension"),
            "bilibili_extension": ("npm", "run", "test:bilibili-extension", "--workspace", "@x2n/extension"),
        }
        outputs = {
            label: _json_line(
                _run_external(label, command, env=env, timeout=1_200 if "extension" in label else 240),
                label,
            )
            for label, command in commands.items()
        }

    _require_metrics(
        outputs["self_test"],
        {
            "action": "extension_self_test",
            "bilibili_fixture_cases": 10,
            "bilibili_policy_cases": 8,
            "douyin_fixture_cases": 8,
            "douyin_shortlink_cases": 16,
            "extension_id": EXTENSION_ID,
            "fixture_cases": 20,
            "fixture_recognition_passed": 20,
            "host_permissions": 0,
            "permissions": 4,
            "platform_execution": "NOT_RUN",
            "status": "PASS",
            "xhs_fixture_cases": 5,
        },
        "Extension self-test",
    )
    _require_metrics(
        outputs["xhs_fixture"],
        {
            "console_uncaught_errors": 0,
            "fixture_cases": 5,
            "observation_diff_mismatches": 0,
            "owner_canary": "NOT_RUN",
            "platform_changed_verified": 2,
            "platform_calls": 0,
            "query_fragment_persisted": 0,
            "stable_ids_verified": 3,
            "status": "PASS",
        },
        "XHS fixture regression",
    )
    _require_metrics(
        outputs["douyin_fixture"],
        {
            "blocked_platform_network_requests": 0,
            "console_uncaught_errors": 0,
            "fixture_cases": 8,
            "fixture_documents_fulfilled": 8,
            "observation_diff_mismatches": 0,
            "owner_canary": "NOT_RUN",
            "platform_changed_verified": 4,
            "platform_calls": 0,
            "query_fragment_persisted": 0,
            "redirect_security_cases": 16,
            "resolved_short_links": 3,
            "short_links_persisted": 0,
            "stable_ids_verified": 4,
            "status": "PASS",
            "synthetic_redirect_requests": 17,
        },
        "Douyin fixture regression",
    )
    _require_metrics(
        outputs["bilibili_fixture"],
        {
            "blocked_platform_network_requests": 0,
            "console_uncaught_errors": 0,
            "fixture_cases": 10,
            "fixture_documents_fulfilled": 10,
            "observation_diff_mismatches": 0,
            "owner_canary": "NOT_RUN",
            "platform_changed_verified": 5,
            "platform_calls": 0,
            "platform_requests_observed": 10,
            "policy_cases_verified": 8,
            "query_fragment_persisted": 0,
            "schema_drift_rejections": 5,
            "stable_ids_verified": 5,
            "status": "PASS",
        },
        "Bilibili fixture E2E",
    )
    receipts = {
        "xhs": _validate_extension_metrics(outputs["xhs_extension"], "xhs"),
        "douyin": _validate_extension_metrics(outputs["douyin_extension"], "douyin"),
        "bilibili": _validate_extension_metrics(outputs["bilibili_extension"], "bilibili"),
    }
    return Check(
        "isolated_current_page_e2e",
        "PASS",
        {
            "action_before_grant_rejections_per_platform": 2,
            "bilibili_dom_fixture_cases": 10,
            "bilibili_policy_cases": 8,
            "blocked_platform_network_requests": 0,
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "service_worker_restarts_per_platform": 100,
            "bilibili_screenshot": receipts["bilibili"]["screenshot"],
            "bilibili_trace": receipts["bilibili"]["trace"],
            "douyin_screenshot": receipts["douyin"]["screenshot"],
            "douyin_trace": receipts["douyin"]["trace"],
            "xhs_screenshot": receipts["xhs"]["screenshot"],
            "xhs_trace": receipts["xhs"]["trace"],
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
    results = report.get("blocking_results", [])
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
    _require(results == expected_results, "full lane execution identity or result drifted")
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
        and artifact.get("member_count") == 57
        and artifact.get("runtime_data_files") == 0
        and artifact.get("allowlist_findings") == 0,
        "full lane artifact gate failed",
    )
    return Check(
        "full_lane_replay",
        "PASS",
        {
            "artifact_members": 57,
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
    fixture = _load_json(FIXTURE_MANIFEST)
    paths = [
        MANIFEST,
        NATIVE_POLICY,
        PERMISSION_POLICY,
        BILIBILI_POLICY,
        PLATFORM_FACT,
        PLATFORM_POLICY,
        TASK_STATE,
        TASKPACK,
        RUN_CONTRACT,
        FIXTURE_MANIFEST,
        *[FIXTURE_MANIFEST.parent / item["file"] for item in fixture["cases"]],
        PROJECT_ROOT / "apps/extension/src/bilibili-current-page.js",
        PROJECT_ROOT / "apps/extension/src/page-support.js",
        PROJECT_ROOT / "apps/extension/src/service-worker.js",
        PROJECT_ROOT / "apps/extension/src/sidepanel.js",
        PROJECT_ROOT / "apps/extension/scripts/bilibili-fixture-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/self-test.mjs",
        PROJECT_ROOT / "scripts/verify_skeleton_002.py",
        PROJECT_ROOT / "scripts/verify_phase_0_5.py",
        PROJECT_ROOT / "scripts/verify_skeleton_006.py",
        PROJECT_ROOT / "tests/test_phase_0_5.py",
        PROJECT_ROOT / "tests/test_skeleton_002.py",
        PROJECT_ROOT / "tests/test_skeleton_006.py",
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


def write_evidence(checks: list[Check]) -> None:
    names = {check.name for check in checks}
    _require(
        {"full_lane_replay", "isolated_current_page_e2e", "worktree_isolation"} <= names,
        "evidence requires Task E2E, worktree and two-repetition full lane validation",
    )
    payload = {
        "acceptance_ids": ["ACC.x2n.capture.003", "ACC.x2n.ext.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.capture.003": "PASS_CI_SYNTH_10_DOM_8_POLICY_OWNER_CANARY_NOT_RUN_REAL_PAGE_DISABLED",
            "ACC.x2n.ext.001": "PASS_BILIBILI_CURRENT_PAGE_CI_SYNTH_ACTION_GATED_OWNER_CANARY_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "feature_flag": "CI_SYNTH_ONLY_REAL_PAGE_AND_API_DISABLED_ARTICLE_ROUTE_UNVERIFIED",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "owner_canary": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "private_content_included": False,
        "production_network_transport": "DISABLED",
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
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_SCOPED" and evidence.get("stage_gate") == "G2_NOT_RUN",
        "evidence overstated",
    )
    _require(
        evidence.get("feature_flag") == "CI_SYNTH_ONLY_REAL_PAGE_AND_API_DISABLED_ARTICLE_ROUTE_UNVERIFIED",
        "evidence real-page/API gate drifted",
    )
    _require(
        evidence.get("owner_canary") == "NOT_RUN" and evidence.get("real_account_execution") == "NOT_RUN",
        "Owner execution overstated",
    )
    _require(
        evidence.get("platform_calls") == 0 and evidence.get("production_network_transport") == "DISABLED",
        "platform execution overstated",
    )
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check")
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
    checks = [validate_scope(), validate_task_and_state(), validate_extension_surface(), validate_fixtures_and_policy()]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_execution())
    if lane_report is not None:
        checks.append(validate_full_lane_report(lane_report))
    _require(all(check.status == "PASS" for check in checks), "a Skeleton006 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.006")
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
            file=os.sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
