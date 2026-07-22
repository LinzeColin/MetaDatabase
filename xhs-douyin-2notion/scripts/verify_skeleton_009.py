#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.skeleton.009."""

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
    "verify_skeleton_008_for_009",
    PROJECT_ROOT / "scripts/verify_skeleton_008.py",
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

TASK_ID = "TSK.x2n.skeleton.009"
RUN_ID = "RUN-X2N-S02-S009"
PHASE = "PH.X2N.2.6"
BRANCH = "codex/xhs-douyin-2notion-v0001-s02-skeleton009"
TASK_BASE_COMMIT = "7e8a3dbf3c4c27643330489353ed162130fba506"
FINAL_COMMIT = "0af2d3b269e7d5631257cb49f41f75cc79438f70"
ORIGIN_CUTOFF = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_SKELETON_009.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
PLATFORM_FACT = PROJECT_ROOT / "machine/facts/platform_scope_registry.json"
PLATFORM_POLICY = PROJECT_ROOT / "machine/policy/platform_policy_registry.json"
TAOBAO_POLICY = PROJECT_ROOT / "machine/policy/taobao_current_page_policy.json"
PERMISSION_POLICY = PROJECT_ROOT / "machine/policy/extension_permission_policy.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "packages/test-fixtures/extension/v1/taobao_current_page/fixture_manifest.json"
MANIFEST = PROJECT_ROOT / "apps/extension/manifest.json"
NATIVE_POLICY = PROJECT_ROOT / "apps/companion/native-host/policy.json"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.009.json"
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
    "apps/extension/scripts/taobao-fixture-e2e.mjs",
    "apps/extension/src/page-support.js",
    "apps/extension/src/service-worker.js",
    "apps/extension/src/sidepanel.js",
    "apps/extension/src/taobao-current-page.js",
    "docs/governance/RUN_CONTRACT_S02_SKELETON_009.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.skeleton.009.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/platform_scope_registry.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/platform_policy_registry.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/policy/taobao_current_page_policy.json",
    "scripts/verify_skeleton_008.py",
    "scripts/verify_skeleton_009.py",
    "tests/test_skeleton_008.py",
    "tests/test_skeleton_009.py",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/extension/v1/taobao_current_page/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    relative_changes: list[str] = []
    for path in sorted(set(committed)):
        relative = _project_relative(path)
        _require(relative is not None, "Skeleton009 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Skeleton009 change: {relative}",
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
    current_branch = _git(["branch", "--show-current"])
    _require(current_branch not in {"", "main"}, "Skeleton009 regression must run in a non-main worktree")
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
        "Skeleton009 final commit no longer descends from its Task base",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current tree no longer descends from the Skeleton009 final commit",
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


def validate_task_and_state() -> Check:
    taskpack = _read_blob_at(FINAL_COMMIT, TASKPACK).decode("utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Skeleton009 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.2" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.foundation.004", "TSK.x2n.foundation.005"],
        "Skeleton009 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.capture.006", "ACC.x2n.ext.001"],
        "Skeleton009 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Skeleton009 Task changed beyond status")
    _require("  status: STAGE_2_SKELETON_009_PASS_G2_NOT_RUN\n" in taskpack, "Task Pack status drifted")
    next_task = _task_block(taskpack, "TSK.x2n.skeleton.003")
    _require(next_task == _task_block(base_taskpack, "TSK.x2n.skeleton.003"), "Skeleton003 was entered by this Run")

    state = _load_json_at(FINAL_COMMIT, TASK_STATE)
    _require(state.get("schema_version") == "1.14", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.2" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Skeleton009 state is not pass")
    _require("TSK.x2n.skeleton.003" not in state.get("tasks", {}), "Skeleton003 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.2.7" and state.get("next_run") == "TSK.x2n.skeleton.003",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g2_pass",
        "G2/upload overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.capture.006")
        == "pass_ci_synth_8_dom_plus_14_policy_plus_16_undocumented_signature_2_scope_retention_unknown_disabled_owner_canary_not_run_real_page_disabled",
        "Taobao capture Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.ext.001")
        == "pass_stage_1_scaffold_plus_six_platform_current_page_ci_synth_owner_canary_not_run",
        "Extension Acceptance drifted",
    )
    _require(
        state.get("taobao_current_page_execution")
        == "pass_ci_synth_real_page_api_and_dom_unknown_disabled_scope_retention_unapproved_cookie_mtop_signature_surface_disabled_16_undocumented_signature_inputs_rejected_action_before_grant_rejected_owner_canary_not_run",
        "Taobao execution boundary drifted",
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
    _require(
        _load_json_at(FINAL_COMMIT, PROJECT_FACT).get("status") == "stage_2_skeleton_009_pass_g2_not_run",
        "project drifted",
    )
    architecture = _load_json_at(FINAL_COMMIT, ARCHITECTURE_FACT)
    _require(architecture.get("phase") == PHASE and architecture.get("stage_gate") == "g2_not_run", "ADR drifted")
    contract = _read_blob_at(FINAL_COMMIT, RUN_CONTRACT).decode("utf-8")
    for value in (TASK_ID, RUN_ID, PHASE, TASK_BASE_COMMIT, BRANCH, "PASS_CI_SYNTH_SCOPED"):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 2,
            "next_task": "TSK.x2n.skeleton.003",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "real_page_execution": "UNKNOWN_DISABLED_SCOPE_RETENTION",
            "single_task": True,
        },
    )


def validate_extension_surface() -> Check:
    manifest = _load_json_at(FINAL_COMMIT, MANIFEST)
    _require(manifest == _load_json_at(TASK_BASE_COMMIT, MANIFEST), "Extension Manifest changed in Skeleton009")
    _require(manifest.get("manifest_version") == 3 and manifest.get("minimum_chrome_version") == "120", "MV3 drifted")
    _require(manifest.get("permissions") == CURRENT_PERMISSIONS, "permission allowlist drifted")
    _require("host_permissions" not in manifest and "content_scripts" not in manifest, "persistent page access entered")
    _require(
        manifest.get("content_security_policy", {}).get("extension_pages") == "script-src 'self'; object-src 'none';",
        "Extension CSP weakened",
    )
    _require(
        _load_json_at(FINAL_COMMIT, PROJECT_ROOT / "package-lock.json")
        == _load_json_at(TASK_BASE_COMMIT, PROJECT_ROOT / "package-lock.json"),
        "npm lock changed",
    )
    _require(
        _read_blob_at(FINAL_COMMIT, PROJECT_ROOT / "uv.lock")
        == _read_blob_at(TASK_BASE_COMMIT, PROJECT_ROOT / "uv.lock"),
        "uv lock changed",
    )
    permission = _load_json_at(FINAL_COMMIT, PERMISSION_POLICY)
    _require([item.get("name") for item in permission.get("permissions", [])] == CURRENT_PERMISSIONS, "permission policy drifted")
    _require(permission.get("host_permissions") == [] and permission.get("content_scripts") == [], "policy widened")
    native = _load_json_at(FINAL_COMMIT, NATIVE_POLICY)
    _require(native == _load_json_at(TASK_BASE_COMMIT, NATIVE_POLICY), "Native policy changed in Skeleton009")
    _require(native.get("schema_version") == "1.0" and native.get("allowed_actions") == NATIVE_ACTIONS, "Native v1.0 widened")

    source_paths = sorted((PROJECT_ROOT / "apps/extension/src").glob("*.js"))
    sources = {path.name: _read_blob_at(FINAL_COMMIT, path).decode("utf-8") for path in source_paths}
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
    taobao = sources["taobao-current-page.js"]
    _require('taobao: "ci_synth_only"' in page_support, "Taobao feature gate drifted")
    _require("isSyntheticTaobaoItem" in page_support and "9900000000000" in page_support, "Taobao synthetic gate missing")
    for value in (
        "taobao_undocumented_signature_input_rejected",
        "taobao_scope_retention_unknown_disabled",
        "taobao_nonsemantic_query_fragment_unsupported",
    ):
        _require(value in page_support, f"Taobao policy gate missing: {value}")
    _require("buildTaobaoCapturePayload" in worker and "extractTaobaoCurrentPage" in worker, "Taobao adapter missing")
    _require('world: "ISOLATED"' in worker and "currentTab.url !== tab.url" in worker, "injection race gate missing")
    _require('taobao: "Taobao"' in panel and "captureInFlight" in panel, "Side Panel gate missing")
    _require("auto_scroll: false" in taobao and "change_account_state: false" in taobao, "capture literals drifted")
    _require(
        "stable_num_iid_and_official_item_route" in taobao and "data-num-iid" in taobao,
        "Taobao identity cross-check missing",
    )
    _require(
        'hostname.toLowerCase() !== "item.taobao.com"' in taobao
        and '["https:", "", "item.taobao.com", "item.htm"]' in taobao,
        "Taobao exact-host/query-free canonical gate missing",
    )
    _require('.getAttribute("src")' not in taobao and ".src" not in taobao, "media source read entered extractor")
    _require("hydration" not in taobao.lower() and "innerhtml" not in taobao.lower(), "raw page state read entered extractor")
    _require("document.cookie" not in taobao and "fetch(" not in taobao, "Cookie or network surface entered extractor")
    package = _load_json_at(FINAL_COMMIT, PROJECT_ROOT / "apps/extension/package.json")
    scripts = package.get("scripts", {})
    _require(scripts.get("test:taobao-fixtures") == "node scripts/taobao-fixture-e2e.mjs", "fixture script missing")
    _require(scripts.get("test:taobao-extension") == "node scripts/extension-e2e.mjs taobao", "E2E script missing")
    return Check(
        "extension_permission_and_security_surface",
        "PASS",
        {
            "content_scripts": 0,
            "host_permissions": 0,
            "native_actions": len(NATIVE_ACTIONS),
            "permissions": len(CURRENT_PERMISSIONS),
            "production_network_transport": 0,
            "real_page_execution": "UNKNOWN_DISABLED_SCOPE_RETENTION",
            "signature_input_surface": 0,
        },
    )


def validate_fixtures_and_policy() -> Check:
    fixture = _load_json_at(FINAL_COMMIT, FIXTURE_MANIFEST)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S02.S009.001" and fixture.get("synthetic") is True,
        "fixture drifted",
    )
    cases = fixture.get("cases", [])
    policy_cases = fixture.get("policy_cases", [])
    signature_cases = fixture.get("undocumented_signature_cases", [])
    _require(isinstance(cases, list) and len(cases) == 8, "Taobao DOM fixture count drifted")
    _require(isinstance(policy_cases, list) and len(policy_cases) == 14, "Taobao policy fixture count drifted")
    _require(isinstance(signature_cases, list) and len(signature_cases) == 16, "signature fixture count drifted")
    _require(len({item.get("id") for item in cases}) == 8, "DOM fixture IDs are not unique")
    _require(len({item.get("id") for item in policy_cases}) == 14, "policy fixture IDs are not unique")
    _require(len({item.get("id") for item in signature_cases}) == 16, "signature fixture IDs are not unique")
    _require(sum(item.get("expected", {}).get("status") == "ready" for item in cases) == 4, "ready threshold drifted")
    _require(
        sum(item.get("expected", {}).get("status") == "platform_changed" for item in cases) == 4,
        "platform-changed threshold drifted",
    )
    _require(
        sum(item.get("expected", {}).get("reason") == "taobao_scope_retention_unknown_disabled" for item in policy_cases)
        == 2,
        "scope/retention-disabled threshold drifted",
    )
    scope = fixture.get("scope_retention_contract", {})
    _require(
        scope.get("application_approved") is False
        and scope.get("oauth_configured") is False
        and scope.get("item_api_permission_approved") is False
        and scope.get("paid_api_plan_approved") is False
        and scope.get("field_scope_approved") is False
        and scope.get("retention_and_deletion_receipt") is False
        and scope.get("real_page_state") == "UNKNOWN_DISABLED"
        and scope.get("production_top_api_transport") is False
        and scope.get("dom_fallback") is False,
        "fixture scope/retention contract drifted",
    )
    signature = fixture.get("signature_contract", {})
    _require(
        signature.get("official_top_protocol_documented") is True
        and signature.get("official_top_protocol_implemented") is False
        and signature.get("browser_mtop_cookie_signature_route") is False
        and signature.get("signature_material_input") is False
        and signature.get("rejection_case_count") == 16
        and signature.get("rejection_rate_percent") == 100,
        "fixture signature contract drifted",
    )
    for field in (
        "contains_cookies",
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_real_accounts",
        "contains_signature_material",
        "real_accounts",
    ):
        _require(fixture.get(field) is False, f"fixture public boundary weakened: {field}")
    fixture_root = FIXTURE_MANIFEST.parent
    html_bytes = 0
    for item in cases:
        name = item.get("file")
        _require(isinstance(name, str) and re.fullmatch(r"[a-z_]+\.html", name) is not None, "unsafe fixture filename")
        path = fixture_root / name
        _require(path.resolve().is_relative_to(fixture_root.resolve()), "HTML fixture escaped its root")
        html = _read_blob_at(FINAL_COMMIT, path).decode("utf-8")
        _require(
            re.search(r"<(?:form|iframe|script)\b|\b(?:poster|src|srcset)\s*=|url\s*\(", html, flags=re.IGNORECASE)
            is None,
            "unsafe fixture surface",
        )
        html_bytes += len(html.encode("utf-8"))
    allowed_policy_hosts = {"detail.tmall.com", "item.taobao.com", "item.taobao.com.example"}
    for item in policy_cases:
        parsed = urlsplit(str(item.get("url", "")))
        _require(
            parsed.scheme in {"http", "https"}
            and parsed.hostname in allowed_policy_hosts
            and parsed.password is None
            and parsed.username in {None, "synthetic"},
            "unsafe policy fixture URL",
        )
    signature_keys = {
        "_m_h5_tk",
        "_m_h5_tk_enc",
        "anti_flood",
        "api",
        "data",
        "ecode",
        "h5st",
        "jsv",
        "sign",
        "sign_method",
        "t",
        "x-bx-version",
        "x-mini-wua",
        "x-sgext",
        "x-sign",
        "x-umt",
    }
    observed_signature_keys: set[str] = set()
    for item in signature_cases:
        parsed = urlsplit(str(item.get("url", "")))
        query = parse_qs(parsed.query, keep_blank_values=True)
        matched = set(query) & signature_keys
        _require(
            parsed.scheme == "https"
            and parsed.hostname == "item.taobao.com"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and parsed.path == "/item.htm"
            and parsed.fragment == ""
            and len(matched) == 1
            and set(query) == {"id", "x2n_fixture", *matched}
            and query.get("x2n_fixture") == ["1"]
            and re.fullmatch(r"9900000000000[0-9]{6}", query.get("id", [""])[0]) is not None,
            "undocumented signature fixture escaped the synthetic current page",
        )
        observed_signature_keys.update(matched)
    _require(observed_signature_keys == signature_keys, "signature-input rejection matrix drifted")

    global_rows = _load_json_at(FINAL_COMMIT, GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S02.S009.001",
            "path": "packages/test-fixtures/extension/v1/taobao_current_page/fixture_manifest.json",
            "case_count": 38,
            "purpose": "Taobao current-page num_iid, sanitized query-free facts, scope/retention disabled behavior, undocumented Cookie/MTop signature-input rejection and schema drift",
        }
        in global_rows,
        "Taobao fixture is not globally registered",
    )
    policy = _load_json_at(FINAL_COMMIT, TAOBAO_POLICY)
    _require(policy.get("phase") == PHASE and policy.get("default") == "deny", "Taobao policy identity drifted")
    _require(policy.get("production_top_api_transport") is False, "production TOP transport was enabled")
    _require(
        policy.get("feature_flag")
        == {
            "name": "taobao_current_page",
            "value": "ci_synth_only",
            "real_page_execution": False,
            "owner_canary": "not_run",
        },
        "Taobao feature flag drifted",
    )
    _require(
        policy.get("platform_policy_state")
        == "unknown_disabled_application_scope_retention_and_dom_fallback",
        "Taobao policy state drifted",
    )
    application = policy.get("application_gate", {})
    _require(
        application.get("application_registered") is False
        and application.get("application_approved") is False
        and application.get("item_api_permission_approved") is False
        and application.get("oauth_configured") is False
        and application.get("paid_api_plan_approved") is False
        and application.get("approved_budget_units") == 0
        and application.get("field_scope_approved") is False,
        "application gate drifted",
    )
    retention = policy.get("retention_gate", {})
    _require(
        retention.get("purpose_and_scope_disclosure_required") is True
        and retention.get("withdrawal_and_service_end_deletion_required") is True
        and retention.get("retention_expiry_deletion_required") is True
        and retention.get("user_delete_and_revoke_flow_implemented") is False
        and retention.get("retention_period_approved") is False
        and retention.get("deletion_receipt_implemented") is False
        and retention.get("unknown_scope_or_retention_state") == "UNKNOWN_DISABLED",
        "retention gate drifted",
    )
    signature_surface = policy.get("undocumented_signature_surface", {})
    _require(
        signature_surface.get("browser_mtop_cookie_signing") is False
        and signature_surface.get("cookie_derived_token_input") is False
        and signature_surface.get("signature_material_input") is False
        and signature_surface.get("undocumented_endpoint_transport") is False
        and signature_surface.get("official_top_sdk_or_protocol_transport") is False
        and signature_surface.get("rejection_case_count") == 16
        and signature_surface.get("rejection_rate_percent") == 100,
        "undocumented signature surface drifted",
    )
    canonical = policy.get("canonical_query_contract", {})
    _require(
        canonical.get("allowed_persisted_query_keys") == []
        and canonical.get("semantic_id_observed_but_stored_as_content_id") is True
        and canonical.get("any_query_persisted") is False
        and canonical.get("fragment_persisted") is False,
        "query-free canonical contract drifted",
    )
    platform = _load_json_at(FINAL_COMMIT, PLATFORM_FACT)
    taobao_fact = next((item for item in platform.get("platforms", []) if item.get("id") == "taobao"), {})
    _require(taobao_fact.get("policy_state") == "unknown_disabled", "real Taobao policy was enabled")
    _require(
        taobao_fact.get("current_page_implementation_state")
        == "ci_synth_pass_real_page_api_and_dom_unknown_disabled_scope_retention_unapproved_cookie_mtop_signature_surface_absent_owner_canary_not_run",
        "Taobao platform fact drifted",
    )
    registry = _load_json_at(FINAL_COMMIT, PLATFORM_POLICY)
    _require(registry.get("phase") == PHASE and registry.get("research_cutoff") == "2026-07-22", "policy recheck drifted")
    official_sources = registry.get("official_sources", {}).get("taobao", [])
    _require(isinstance(official_sources, list) and len(official_sources) >= 8, "official Taobao evidence incomplete")
    _require(
        all(urlsplit(value).hostname == "developer.alibaba.com" for value in official_sources),
        "non-first-party Taobao evidence entered registry",
    )
    recheck = registry.get("policy_recheck", {}).get("taobao", {})
    _require(
        recheck.get("official_item_api") == "taobao_item_get"
        and recheck.get("official_item_api_class") == "authorized_value_added_api"
        and recheck.get("official_item_identity") == "num_iid"
        and recheck.get("official_top_signing_protocol") == "documented_not_implemented"
        and recheck.get("application_and_item_api_permission") == "not_configured_not_approved"
        and recheck.get("paid_plan_and_budget") == "not_approved_budget_zero"
        and recheck.get("field_scope") == "not_approved"
        and recheck.get("retention_and_deletion_flow") == "required_not_implemented_or_approved"
        and recheck.get("platform_crawling") == "prohibited"
        and recheck.get("browser_mtop_cookie_signature_route") == "permanently_forbidden_and_not_implemented"
        and recheck.get("current_state") == "unknown_disabled"
        and recheck.get("decision") == "retain_unknown_disabled_for_real_pages_top_api_and_dom_fallback",
        "Taobao policy recheck drifted",
    )
    return Check(
        "fixtures_and_platform_policy",
        "PASS",
        {
            "dom_fixture_cases": 8,
            "fixture_html_bytes": html_bytes,
            "platform_changed_cases": 4,
            "policy_cases": 14,
            "policy_state": "UNKNOWN_DISABLED_SCOPE_RETENTION_API_DOM",
            "query_fragment_persisted": 0,
            "ready_cases": 4,
            "schema_drift_rejections": 7,
            "scope_retention_disabled_cases": 2,
            "signature_input_rejections": 16,
            "signature_input_rejection_percent": 100,
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    previous = PREVIOUS.validate_execution()
    for command in ("node", "npm", "uv"):
        _require(shutil.which(command) is not None, f"required verifier tool unavailable: {command}")
    with tempfile.TemporaryDirectory(prefix="x2n-s009-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, require_browser=True)
        commands = {
            "self_test": ("npm", "run", "self-test", "--workspace", "@x2n/extension"),
            "taobao_fixture": ("npm", "run", "test:taobao-fixtures", "--workspace", "@x2n/extension"),
            "taobao_extension": ("npm", "run", "test:taobao-extension", "--workspace", "@x2n/extension"),
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
            "taobao_fixture_cases": 8,
            "taobao_policy_cases": 14,
            "taobao_signature_rejection_cases": 16,
        },
        "Extension self-test",
    )
    _require_metrics(
        outputs["taobao_fixture"],
        {
            "blocked_platform_network_requests": 0,
            "console_uncaught_errors": 0,
            "fixture_cases": 8,
            "fixture_documents_fulfilled": 8,
            "observation_diff_mismatches": 0,
            "owner_canary": "NOT_RUN",
            "platform_changed_verified": 4,
            "platform_calls": 0,
            "platform_requests_observed": 8,
            "policy_cases_verified": 14,
            "query_fragment_persisted": 0,
            "schema_drift_rejections": 7,
            "scope_retention_disabled_cases_verified": 2,
            "stable_ids_verified": 4,
            "status": "PASS",
            "undocumented_signature_rejections": 16,
        },
        "Taobao fixture E2E",
    )
    receipts = _validate_extension_metrics(outputs["taobao_extension"], "taobao")
    details = dict(previous.details)
    details.update(
        {
            "platform_calls": 0,
            "service_worker_restarts_per_platform": 100,
            "scope_retention_disabled_cases": 2,
            "taobao_dom_fixture_cases": 8,
            "taobao_policy_cases": 14,
            "taobao_screenshot": receipts["screenshot"],
            "taobao_signature_input_rejections": 16,
            "taobao_trace": receipts["trace"],
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
        and artifact.get("member_count") == 60
        and artifact.get("runtime_data_files") == 0
        and artifact.get("allowlist_findings") == 0,
        "full lane artifact gate failed",
    )
    return Check(
        "full_lane_replay",
        "PASS",
        {
            "artifact_members": 60,
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
    fixture = _load_json_at(FINAL_COMMIT, FIXTURE_MANIFEST)
    paths = [
        MANIFEST,
        NATIVE_POLICY,
        PERMISSION_POLICY,
        TAOBAO_POLICY,
        PLATFORM_FACT,
        PLATFORM_POLICY,
        TASK_STATE,
        TASKPACK,
        RUN_CONTRACT,
        FIXTURE_MANIFEST,
        *[FIXTURE_MANIFEST.parent / item["file"] for item in fixture["cases"]],
        PROJECT_ROOT / "apps/extension/src/taobao-current-page.js",
        PROJECT_ROOT / "apps/extension/src/page-support.js",
        PROJECT_ROOT / "apps/extension/src/service-worker.js",
        PROJECT_ROOT / "apps/extension/src/sidepanel.js",
        PROJECT_ROOT / "apps/extension/scripts/taobao-fixture-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs",
        PROJECT_ROOT / "apps/extension/scripts/self-test.mjs",
        PROJECT_ROOT / "scripts/verify_skeleton_008.py",
        PROJECT_ROOT / "scripts/verify_skeleton_009.py",
        PROJECT_ROOT / "tests/test_skeleton_008.py",
        PROJECT_ROOT / "tests/test_skeleton_009.py",
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
    _require(_git(["rev-parse", "HEAD"]) == FINAL_COMMIT, "historical Skeleton009 evidence is immutable")
    names = {check.name for check in checks}
    _require(
        {"full_lane_replay", "isolated_current_page_e2e", "worktree_isolation"} <= names,
        "evidence requires Task E2E, worktree and two-repetition full lane validation",
    )
    payload = {
        "acceptance_ids": ["ACC.x2n.capture.006", "ACC.x2n.ext.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.capture.006": "PASS_CI_SYNTH_8_DOM_14_POLICY_16_UNDOCUMENTED_SIGNATURE_2_SCOPE_RETENTION_UNKNOWN_DISABLED_OWNER_CANARY_NOT_RUN_REAL_PAGE_DISABLED",
            "ACC.x2n.ext.001": "PASS_TAOBAO_CURRENT_PAGE_CI_SYNTH_ACTION_GATED_OWNER_CANARY_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "feature_flag": "CI_SYNTH_ONLY_REAL_PAGE_TOP_API_DOM_SCOPE_RETENTION_UNKNOWN_DISABLED_COOKIE_MTOP_SIGNATURE_SURFACE_DISABLED_ROUTE_UNVERIFIED",
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
    _require(EVIDENCE.read_bytes() == _read_blob_at(FINAL_COMMIT, EVIDENCE), "historical evidence was rewritten")
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_SCOPED" and evidence.get("stage_gate") == "G2_NOT_RUN",
        "evidence overstated",
    )
    _require(
        evidence.get("feature_flag")
        == "CI_SYNTH_ONLY_REAL_PAGE_TOP_API_DOM_SCOPE_RETENTION_UNKNOWN_DISABLED_COOKIE_MTOP_SIGNATURE_SURFACE_DISABLED_ROUTE_UNVERIFIED",
        "evidence real-page/TOP/DOM/scope/retention/Cookie/MTop/signature gate drifted",
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
    _require(all(check.status == "PASS" for check in checks), "a Skeleton009 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.skeleton.009")
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
