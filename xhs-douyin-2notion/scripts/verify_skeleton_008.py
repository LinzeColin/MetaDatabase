#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.008."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
PREVIOUS_SPEC = importlib.util.spec_from_file_location(
    "verify_skeleton_007_for_008",
    PROJECT_ROOT / "scripts/verify_skeleton_007.py",
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
_require_metrics = PREVIOUS._require_metrics
_validate_extension_metrics = PREVIOUS._validate_extension_metrics

TASK_ID = "TSK.x2n.skeleton.008"
RUN_ID = "RUN-X2N-S02-S008"
PHASE = "PH.X2N.2.5"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton008"
TASK_BASE_COMMIT = "17f1988b309fe62071c273369f7088b7f6cc6046"
ORIGIN_CUTOFF = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_SKELETON_008.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
PLATFORM_FACT = PROJECT_ROOT / "machine/facts/platform_scope_registry.json"
PLATFORM_POLICY = PROJECT_ROOT / "machine/policy/platform_policy_registry.json"
WEIBO_POLICY = PROJECT_ROOT / "machine/policy/weibo_current_page_policy.json"
PERMISSION_POLICY = PROJECT_ROOT / "machine/policy/extension_permission_policy.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "packages/test-fixtures/extension/v1/weibo_current_page/fixture_manifest.json"
MANIFEST = PROJECT_ROOT / "apps/extension/manifest.json"
NATIVE_POLICY = PROJECT_ROOT / "apps/companion/native-host/policy.json"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.008.json"
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
FULL_LANE_GATES = PREVIOUS.FULL_LANE_GATES

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/extension/package.json",
    "apps/extension/scripts/extension-e2e.mjs",
    "apps/extension/scripts/self-test.mjs",
    "apps/extension/scripts/weibo-fixture-e2e.mjs",
    "apps/extension/src/page-support.js",
    "apps/extension/src/service-worker.js",
    "apps/extension/src/sidepanel.js",
    "apps/extension/src/weibo-current-page.js",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_008.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.skeleton.008.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/platform_scope_registry.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/platform_policy_registry.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/policy/weibo_current_page_policy.json",
    "scripts/verify_skeleton_007.py",
    "scripts/verify_skeleton_008.py",
    "tests/test_skeleton_007.py",
    "tests/test_skeleton_008.py",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/extension/v1/weibo_current_page/",)


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
        _require(relative is not None, "Skeleton008 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton008 change: {relative}",
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
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Skeleton008 worktree branch")
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
        "Skeleton008 branch no longer descends from its Task base",
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
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton008 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.foundation.004", "TSK.x2n.foundation.005"],
        "Skeleton008 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.capture.005", "ACC.x2n.ext.001"],
        "Skeleton008 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Skeleton008 Task changed beyond status")
    _require("  status: STAGE_2_SKELETON_008_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack status drifted")
    next_task = _task_block(taskpack, "TSK.x2n.skeleton.009")
    _require(next_task == _task_block(base_taskpack, "TSK.x2n.skeleton.009"), "Skeleton009 was entered by this Run")

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.13", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton008 state is not pass")
    _require("TSK.x2n.skeleton.009" not in state.get("tasks", {}), "Skeleton009 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.2.6" and state.get("next_run") == "TSK.x2n.skeleton.009",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.capture.005")
        == "pass_ci_synth_8_dom_plus_12_policy_plus_16_redirect_ssrf_2_blocked_budget_owner_canary_not_run_real_page_disabled",
        "Weibo capture Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.ext.001")
        == "pass_stage_1_scaffold_plus_xhs_douyin_bilibili_kuaishou_weibo_current_page_ci_synth_owner_canary_not_run",
        "Extension Acceptance drifted",
    )
    _require(
        state.get("weibo_current_page_execution")
        == "pass_ci_synth_real_page_blocked_budget_api_transport_dom_fallback_and_arbitrary_url_surface_disabled_16_redirect_ssrf_rejected_action_before_grant_rejected_owner_canary_not_run",
        "Weibo execution boundary drifted",
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
    _require(_load_json(PROJECT_FACT).get("status") == "stage_2_skeleton_008_pass_g2_not_run", "project drifted")
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
            "next_task": "TSK.x2n.skeleton.009",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "real_page_execution": "BLOCKED_BUDGET",
            "single_task": True,
        },
    )


def validate_extension_surface() -> Check:
    manifest = _load_json(MANIFEST)
    _require(manifest == _load_json_at(TASK_BASE_COMMIT, MANIFEST), "Extension Manifest changed in Skeleton008")
    _require(manifest.get("manifest_version") == 3 and manifest.get("minimum_chrome_version") == "120", "MV3 drifted")
    _require(manifest.get("permissions") == CURRENT_PERMISSIONS, "permission allowlist drifted")
    _require("host_permissions" not in manifest and "content_scripts" not in manifest, "persistent page access entered")
    _require(
        manifest.get("content_security_policy", {}).get("extension_pages") == "script-src 'self'; object-src 'none';",
        "Extension CSP weakened",
    )
    _require(_load_json(PROJECT_ROOT / "package-lock.json") == _load_json_at(TASK_BASE_COMMIT, PROJECT_ROOT / "package-lock.json"), "npm lock changed")
    _require((PROJECT_ROOT / "uv.lock").read_bytes() == _read_blob_at(TASK_BASE_COMMIT, PROJECT_ROOT / "uv.lock"), "uv lock changed")
    permission = _load_json(PERMISSION_POLICY)
    _require([item.get("name") for item in permission.get("permissions", [])] == CURRENT_PERMISSIONS, "permission policy drifted")
    _require(permission.get("host_permissions") == [] and permission.get("content_scripts") == [], "policy widened")
    native = _load_json(NATIVE_POLICY)
    _require(native == _load_json_at(TASK_BASE_COMMIT, NATIVE_POLICY), "Native policy changed in Skeleton008")
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
    weibo = sources["weibo-current-page.js"]
    _require('weibo: "ci_synth_only"' in page_support, "Weibo feature gate drifted")
    _require('startsWith("synthetic-wb-status-")' in page_support, "Weibo synthetic gate missing")
    for value in (
        "weibo_arbitrary_url_control_rejected",
        "weibo_budget_zero_quota_unknown_disabled",
        "weibo_query_fragment_unsupported",
    ):
        _require(value in page_support, f"Weibo policy gate missing: {value}")
    _require("buildWeiboCapturePayload" in worker and "extractWeiboCurrentPage" in worker, "Weibo adapter missing")
    _require('world: "ISOLATED"' in worker and "currentTab.url !== tab.url" in worker, "injection race gate missing")
    _require('weibo: "Weibo"' in panel and "captureInFlight" in panel, "Side Panel gate missing")
    _require("auto_scroll: false" in weibo and "change_account_state: false" in weibo, "capture literals drifted")
    _require("stable_mid" in weibo and "data-mid" in weibo, "Weibo identity cross-check missing")
    _require('.getAttribute("src")' not in weibo and ".src" not in weibo, "media source read entered extractor")
    _require("hydration" not in weibo.lower() and "innerhtml" not in weibo.lower(), "raw page state read entered extractor")
    package = _load_json(PROJECT_ROOT / "apps/extension/package.json")
    scripts = package.get("scripts", {})
    _require(scripts.get("test:weibo-fixtures") == "node scripts/weibo-fixture-e2e.mjs", "fixture script missing")
    _require(scripts.get("test:weibo-extension") == "node scripts/extension-e2e.mjs weibo", "E2E script missing")
    return Check(
        "extension_permission_and_security_surface",
        "PASS",
        {
            "arbitrary_url_preview_proxy": 0,
            "content_scripts": 0,
            "host_permissions": 0,
            "native_actions": len(NATIVE_ACTIONS),
            "permissions": len(CURRENT_PERMISSIONS),
            "production_network_transport": 0,
            "real_page_execution": "BLOCKED_BUDGET",
        },
    )


def validate_fixtures_and_policy() -> Check:
    fixture = _load_json(FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S008.001" and fixture.get("synthetic") is True,
        "fixture drifted",
    )
    cases = fixture.get("cases", [])
    policy_cases = fixture.get("policy_cases", [])
    redirect_cases = fixture.get("redirect_ssrf_cases", [])
    _require(isinstance(cases, list) and len(cases) == 8, "Weibo DOM fixture count drifted")
    _require(isinstance(policy_cases, list) and len(policy_cases) == 12, "Weibo policy fixture count drifted")
    _require(isinstance(redirect_cases, list) and len(redirect_cases) == 16, "Redirect-SSRF fixture count drifted")
    _require(len({item.get("id") for item in cases}) == 8, "DOM fixture IDs are not unique")
    _require(len({item.get("id") for item in policy_cases}) == 12, "policy fixture IDs are not unique")
    _require(len({item.get("id") for item in redirect_cases}) == 16, "Redirect-SSRF IDs are not unique")
    _require(sum(item.get("expected", {}).get("status") == "ready" for item in cases) == 4, "ready threshold drifted")
    _require(
        sum(item.get("expected", {}).get("status") == "platform_changed" for item in cases) == 4,
        "platform-changed threshold drifted",
    )
    _require(
        sum(item.get("expected", {}).get("reason") == "weibo_budget_zero_quota_unknown_disabled" for item in policy_cases)
        == 2,
        "budget-blocked threshold drifted",
    )
    budget = fixture.get("budget_contract", {})
    _require(
        budget.get("default_budget_units") == 0
        and budget.get("approved_paid_tier") is False
        and budget.get("application_quota_state") == "unknown"
        and budget.get("arbitrary_url_preview_proxy") is False
        and budget.get("production_api_transport") is False,
        "fixture budget contract drifted",
    )
    for field in (
        "contains_cookies",
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
        _require(
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and "weibo.com" in parsed.hostname
            and parsed.password is None
            and parsed.username in {None, "synthetic"},
            "unsafe policy fixture URL",
        )
    forbidden_keys = {
        "callback",
        "continue",
        "dest",
        "destination",
        "next",
        "proxy",
        "redirect",
        "redirect_url",
        "return_url",
        "target",
        "uri",
        "url",
    }
    for item in redirect_cases:
        parsed = urlsplit(str(item.get("url", "")))
        _require(
            parsed.scheme == "https"
            and parsed.hostname == "www.weibo.com"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and parsed.path.startswith("/detail/synthetic-wb-status-ssrf-"),
            "Redirect-SSRF outer URL escaped the synthetic current page",
        )
        _require(len(set(parse_qs(parsed.query, keep_blank_values=True)) & forbidden_keys) == 1, "URL control key drifted")

    global_rows = _load_json(GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S02.S008.001",
            "path": "packages/test-fixtures/extension/v1/weibo_current_page/fixture_manifest.json",
            "case_count": 36,
            "purpose": "Weibo current-page mid, sanitized facts, budget-zero real-page rejection, arbitrary-URL and Redirect-SSRF rejection, schema drift and real-route-disabled behavior",
        }
        in global_rows,
        "Weibo fixture is not globally registered",
    )
    policy = _load_json(WEIBO_POLICY)
    _require(policy.get("phase") == PHASE and policy.get("default") == "deny", "Weibo policy identity drifted")
    _require(policy.get("production_api_transport") is False, "production API transport was enabled")
    _require(
        policy.get("feature_flag")
        == {
            "name": "weibo_current_page",
            "value": "ci_synth_only",
            "real_page_execution": False,
            "owner_canary": "not_run",
        },
        "Weibo feature flag drifted",
    )
    _require(
        policy.get("platform_policy_state")
        == "blocked_budget_real_page_unknown_disabled_api_and_dom_fallback",
        "Weibo policy state drifted",
    )
    budget_gate = policy.get("budget_gate", {})
    _require(
        budget_gate.get("default_budget_units") == 0
        and budget_gate.get("approved_paid_tier") is False
        and budget_gate.get("application_quota_state") == "unknown"
        and budget_gate.get("unknown_quota_or_positive_cost_state") == "BLOCKED_BUDGET",
        "budget gate drifted",
    )
    arbitrary = policy.get("arbitrary_url_surface", {})
    _require(
        arbitrary.get("preview_handler") is False
        and arbitrary.get("proxy_handler") is False
        and arbitrary.get("redirect_follower") is False
        and arbitrary.get("network_fetcher") is False
        and arbitrary.get("redirect_ssrf_case_count") == 16
        and arbitrary.get("redirect_ssrf_rejection_rate_percent") == 100,
        "arbitrary URL or Redirect-SSRF gate drifted",
    )
    platform = _load_json(PLATFORM_FACT)
    weibo_fact = next((item for item in platform.get("platforms", []) if item.get("id") == "weibo"), {})
    _require(weibo_fact.get("policy_state") == "unknown_disabled", "real Weibo policy was enabled")
    _require(
        weibo_fact.get("current_page_implementation_state")
        == "ci_synth_pass_real_page_blocked_budget_api_and_dom_fallback_disabled_arbitrary_url_surface_absent_route_unverified_owner_canary_not_run",
        "Weibo platform fact drifted",
    )
    registry = _load_json(PLATFORM_POLICY)
    _require(registry.get("phase") == PHASE and registry.get("research_cutoff") == "2026-07-22", "policy recheck drifted")
    official_sources = registry.get("official_sources", {}).get("weibo", [])
    _require(isinstance(official_sources, list) and len(official_sources) >= 8, "official Weibo evidence incomplete")
    _require(
        all(urlsplit(value).hostname in {"open.weibo.com", "weibo.com"} for value in official_sources),
        "non-first-party Weibo evidence entered registry",
    )
    recheck = registry.get("policy_recheck", {}).get("weibo", {})
    _require(recheck.get("official_status_show") == "authorized_users_own_status_only", "official status scope drifted")
    _require(recheck.get("application_budget") == "zero", "application budget drifted")
    _require(recheck.get("application_price_scope_and_quota") == "unknown_not_approved", "quota gate drifted")
    _require(
        recheck.get("arbitrary_url_preview_proxy") == "permanently_forbidden_and_not_implemented",
        "arbitrary URL policy drifted",
    )
    return Check(
        "fixtures_and_platform_policy",
        "PASS",
        {
            "blocked_budget_cases": 2,
            "dom_fixture_cases": 8,
            "fixture_html_bytes": html_bytes,
            "platform_changed_cases": 4,
            "policy_cases": 12,
            "policy_state": "BLOCKED_BUDGET_REAL_UNKNOWN_DISABLED_API_DOM",
            "ready_cases": 4,
            "redirect_ssrf_cases": 16,
            "redirect_ssrf_rejection_percent": 100,
            "schema_drift_rejections": 7,
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    previous = PREVIOUS.validate_execution()
    for command in ("node", "npm", "uv"):
        _require(shutil.which(command) is not None, f"required verifier tool unavailable: {command}")
    with tempfile.TemporaryDirectory(prefix="x2n-s008-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, require_browser=True)
        commands = {
            "self_test": ("npm", "run", "self-test", "--workspace", "@x2n/extension"),
            "weibo_fixture": ("npm", "run", "test:weibo-fixtures", "--workspace", "@x2n/extension"),
            "weibo_extension": ("npm", "run", "test:weibo-extension", "--workspace", "@x2n/extension"),
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
            "extension_id": EXTENSION_ID,
            "fixture_cases": 20,
            "fixture_recognition_passed": 20,
            "host_permissions": 0,
            "permissions": 4,
            "platform_execution": "NOT_RUN",
            "status": "PASS",
            "weibo_fixture_cases": 8,
            "weibo_policy_cases": 12,
            "weibo_redirect_ssrf_cases": 16,
        },
        "Extension self-test",
    )
    _require_metrics(
        outputs["weibo_fixture"],
        {
            "blocked_budget_cases_verified": 2,
            "blocked_platform_network_requests": 0,
            "console_uncaught_errors": 0,
            "fixture_cases": 8,
            "fixture_documents_fulfilled": 8,
            "observation_diff_mismatches": 0,
            "owner_canary": "NOT_RUN",
            "platform_changed_verified": 4,
            "platform_calls": 0,
            "platform_requests_observed": 8,
            "policy_cases_verified": 12,
            "query_fragment_persisted": 0,
            "redirect_ssrf_rejections": 16,
            "schema_drift_rejections": 7,
            "stable_ids_verified": 4,
            "status": "PASS",
        },
        "Weibo fixture E2E",
    )
    receipts = _validate_extension_metrics(outputs["weibo_extension"], "weibo")
    details = dict(previous.details)
    details.update(
        {
            "blocked_budget_cases": 2,
            "platform_calls": 0,
            "redirect_ssrf_rejections": 16,
            "service_worker_restarts_per_platform": 100,
            "weibo_dom_fixture_cases": 8,
            "weibo_policy_cases": 12,
            "weibo_screenshot": receipts["screenshot"],
            "weibo_trace": receipts["trace"],
        }
    )
    return Check("isolated_current_page_e2e", "PASS", details)


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
        and artifact.get("member_count") == 59
        and artifact.get("runtime_data_files") == 0
        and artifact.get("allowlist_findings") == 0,
        "full lane artifact gate failed",
    )
    return Check(
        "full_lane_replay",
        "PASS",
        {
            "artifact_members": 59,
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
        WEIBO_POLICY,
        PLATFORM_FACT,
        PLATFORM_POLICY,
        TASK_STATE,
        TASKPACK,
        RUN_CONTRACT,
        FIXTURE_MANIFEST,
        *[FIXTURE_MANIFEST.parent / item["file"] for item in fixture["cases"]],
        PROJECT_ROOT / "apps/extension/src/weibo-current-page.js",
        PROJECT_ROOT / "apps/extension/src/page-support.js",
        PROJECT_ROOT / "apps/extension/src/service-worker.js",
        PROJECT_ROOT / "apps/extension/src/sidepanel.js",
        PROJECT_ROOT / "apps/extension/scripts/weibo-fixture-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/self-test.mjs",
        PROJECT_ROOT / "scripts/verify_skeleton_007.py",
        PROJECT_ROOT / "scripts/verify_skeleton_008.py",
        PROJECT_ROOT / "tests/test_skeleton_007.py",
        PROJECT_ROOT / "tests/test_skeleton_008.py",
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
        "acceptance_ids": ["ACC.x2n.capture.005", "ACC.x2n.ext.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.capture.005": "PASS_CI_SYNTH_8_DOM_12_POLICY_16_REDIRECT_SSRF_2_BLOCKED_BUDGET_OWNER_CANARY_NOT_RUN_REAL_PAGE_DISABLED",
            "ACC.x2n.ext.001": "PASS_WEIBO_CURRENT_PAGE_CI_SYNTH_ACTION_GATED_OWNER_CANARY_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "feature_flag": "CI_SYNTH_ONLY_REAL_PAGE_BLOCKED_BUDGET_API_CLI_DOM_AND_ARBITRARY_URL_SURFACES_DISABLED_ROUTE_UNVERIFIED",
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
        evidence.get("feature_flag")
        == "CI_SYNTH_ONLY_REAL_PAGE_BLOCKED_BUDGET_API_CLI_DOM_AND_ARBITRARY_URL_SURFACES_DISABLED_ROUTE_UNVERIFIED",
        "evidence real-page/budget/API/CLI/DOM/arbitrary-URL gate drifted",
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
    _require(all(check.status == "PASS" for check in checks), "a Skeleton008 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.008")
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
