#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.foundation.004."""

from __future__ import annotations

import argparse
import base64
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
TASK_ID = "TSK.x2n.foundation.004"
RUN_ID = "RUN-X2N-S01-F004"
BRANCH = "codex/xhs-douyin-2notion-v0001-s01-foundation001"
TASK_BASE_COMMIT = "84731bde18495ab20af005bc70d59d5ce73cbe93"
ORIGIN_CUTOFF = "baac314b7d97369496212ae89057ec107d187f23"
FINAL_COMMIT = "09d5cdf1993080401f99e023feb03be479baca27"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/extension/v1/page_cases.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
MANIFEST = PROJECT_ROOT / "apps/extension/manifest.json"
HOST_TEMPLATE = PROJECT_ROOT / "apps/companion/native-host/com.linzecolin.x2n.json.template"
HOST_POLICY = PROJECT_ROOT / "apps/companion/native-host/policy.json"
SBOM = PROJECT_ROOT / "machine/sbom/stage_1_foundation_004.cdx.json"
EVIDENCE = PROJECT_ROOT / "evidence/extension/TSK.x2n.foundation.004.json"
EXTENSION_ID = "chheapilbdfnpajmlkijppmblnlheeac"
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
HISTORICAL_PERMISSIONS = ["activeTab", "nativeMessaging", "sidePanel"]
CURRENT_PERMISSIONS = ["activeTab", "nativeMessaging", "scripting", "sidePanel"]
EXPECTED_ACTIONS = [
    "capture_current",
    "start_sync",
    "get_job",
    "cancel_job",
    "retry_job",
    "get_capabilities",
    "health",
]
EXPECTED_REGISTRY_DEPENDENCIES = {
    "annotated-types": "0.7.0",
    "pydantic": "2.13.4",
    "pydantic-core": "2.46.4",
    "typing-extensions": "4.16.0",
    "typing-inspection": "0.4.2",
}
EXPECTED_CI_DEPENDENCIES = {
    "coverage": "7.15.2",
    "pyyaml": "6.0.3",
    "ruff": "0.15.22",
}
ALLOWED_CHANGED_EXACT = {
    ".npmrc",
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "apps/companion/pyproject.toml",
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/native_host.py",
    "apps/companion/src/x2n_companion/native_host_installer.py",
    "apps/companion/tests/test_native_host.py",
    "apps/extension/manifest.json",
    "apps/extension/package.json",
    "apps/extension/scripts/extension-e2e.mjs",
    "apps/extension/scripts/self-test.mjs",
    "apps/extension/sidepanel.html",
    "apps/extension/src/page-support.js",
    "apps/extension/src/scaffold.ts",
    "apps/extension/src/service-worker.js",
    "apps/extension/src/sidepanel.js",
    "docs/governance/RUN_CONTRACT_S01_FOUNDATION_004.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/sbom/stage_1_foundation_004.cdx.json",
    "package-lock.json",
    "package.json",
    "scripts/generate_foundation_002_sbom.py",
    "scripts/generate_foundation_004_sbom.py",
    "scripts/verify_foundation_001.py",
    "scripts/verify_foundation_002.py",
    "scripts/verify_foundation_003.py",
    "scripts/verify_foundation_004.py",
    "scripts/verify_phase_0_1.py",
    "scripts/verify_phase_0_2.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_stage_0_review.py",
    "tests/test_foundation_001.py",
    "tests/test_foundation_002.py",
    "tests/test_foundation_003.py",
    "tests/test_foundation_004.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = (
    "apps/companion/native-host/",
    "apps/extension/styles/",
    "evidence/extension/",
    "packages/test-fixtures/extension/",
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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"JSON unavailable: {path.name}") from error
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _git(args: Sequence[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, "Git scope check failed")
    return result.stdout.rstrip()


def _load_baseline_json(path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    try:
        value = json.loads(_git(["show", f"{FINAL_COMMIT}:{relative}"]))
    except json.JSONDecodeError as error:
        raise VerificationError(f"baseline JSON unavailable: {path.name}") from error
    _require(isinstance(value, dict), f"baseline JSON object required: {path.name}")
    return value


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
    committed_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...{FINAL_COMMIT}"]
    ).splitlines()
    changed = sorted(set(committed_paths))
    relative_changes: list[str] = []
    for path in changed:
        relative = _project_relative(path)
        _require(relative is not None, "Foundation004 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Foundation004 change: {relative}",
        )
        relative_changes.append(relative)

    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "/" + "Users/",
        "github" + "_pat_",
        "Bearer" + " ",
    )
    cdn_pattern = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|(?:img|gw|video|vod|pic|media)\.alicdn)",
        flags=re.IGNORECASE,
    )
    scanned = 0
    files = list(_iter_files())
    for path in files:
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(not any(token in text for token in forbidden_tokens), "forbidden repository, path, or credential token entered x2n")
        _require(cdn_pattern.search(text) is None, "platform media CDN URL entered x2n")
    forbidden_suffixes = {
        ".sqlite", ".sqlite3", ".db", ".mp4", ".mov", ".m4a", ".mp3", ".wav",
        ".webm", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".pem", ".p12", ".pfx",
    }
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in files), "Runtime/private file entered x2n")
    for name in ("runtime", "downloads", "browser_profiles", "BrowserProfile"):
        _require(not (PROJECT_ROOT / name).exists(), "Private Runtime or browser profile entered x2n")
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
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Stage 1 worktree branch")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote) is not None,
        "wrong or authenticated persisted origin",
    )
    for commit in (TASK_BASE_COMMIT, ORIGIN_CUTOFF):
        _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"], cwd=REPOSITORY_ROOT, check=False).returncode == 0,
        "Foundation004 branch no longer descends from its Task base",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin], cwd=REPOSITORY_ROOT, check=False).returncode == 0,
        "origin/main no longer descends from the Run cutoff",
    )
    origin_paths = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{ORIGIN_CUTOFF}..{live_origin}"]).splitlines()
    origin_overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in origin_paths)
    _require(origin_overlap == 0, "origin/main changed x2n after the Run cutoff")

    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(["branch", "--show-current"], main_path) == "main", "MetaDatabase main worktree is unavailable or off main")
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
    historical_taskpack = _git(["show", f"{FINAL_COMMIT}:{TASKPACK.relative_to(REPOSITORY_ROOT).as_posix()}"])
    _require(task == _task_block(historical_taskpack, TASK_ID), "Foundation004 Task block history was rewritten")
    _require(_field(task, "status") == "completed", "Foundation004 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.1" and _field(task, "phase") == "PH.X2N.1.4", "Foundation004 routing drifted")
    _require(_list_field(task, "depends_on") == ["TSK.x2n.foundation.002", "TSK.x2n.foundation.003"], "Foundation004 dependency drifted")
    _require(_list_field(task, "acceptance_ids") == ["ACC.x2n.ext.001", "ACC.x2n.ext.002", "ACC.x2n.ext.003", "ACC.x2n.ext.004"], "Foundation004 Acceptance drifted")
    state = _load_baseline_json(TASK_STATE)
    _require(state.get("schema_version") == "1.6", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.1" and state.get("last_completed_phase") == "PH.X2N.1.4", "current Stage routing drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Foundation004 Run identity drifted")
    for task_id in ("TSK.x2n.foundation.001", "TSK.x2n.foundation.002", "TSK.x2n.foundation.003", TASK_ID):
        _require(state.get("tasks", {}).get(task_id) == "pass", f"Task is not pass: {task_id}")
    _require(state.get("next_phase") == "PH.X2N.1.5" and state.get("next_run") == "TSK.x2n.foundation.005", "next Task routing drifted")
    _require(state.get("current_stage_gate") == "not_run" and state.get("current_stage_remote_upload") == "forbidden_until_g1_pass", "G1/upload overstated")
    acceptance = state.get("acceptance_status", {})
    expected_acceptance = {
        "ACC.x2n.ext.001": "pass_ci_synth_20_of_20_owner_canary_not_run",
        "ACC.x2n.ext.002": "pass_isolated_chaos_100_restarts_sqlite_reconciled",
        "ACC.x2n.ext.003": "pass_temp_native_host_contract_idempotency_injection",
        "ACC.x2n.ext.004": "pass_permission_allowlist_3_no_host_permissions",
    }
    _require(all(acceptance.get(key) == value for key, value in expected_acceptance.items()), "Extension Acceptance scope drifted")
    _require(state.get("native_host_execution") == "pass_isolated_synthetic_owner_install_not_run", "Native Host execution overstated")
    for field in ("real_account_execution", "platform_calls", "notion_calls", "model_calls", "media_processing", "real_sink_execution"):
        _require(state.get(field) == "not_run", f"downstream execution overstated: {field}")
    project = _load_baseline_json(PROJECT_FACT)
    _require(project.get("status") == "stage_1_foundation_004_complete_g1_not_run", "project state drifted")
    architecture = _load_baseline_json(ARCHITECTURE_FACT)
    _require(architecture.get("phase") == "PH.X2N.1.4" and architecture.get("status") == "foundation_004_extension_native_skeleton_implemented_g1_not_run", "architecture state drifted")
    return Check(
        "task_state",
        "PASS",
        {
            "acceptance_scope": "ISOLATED_SYNTHETIC_EXTENSION_NATIVE_SKELETON",
            "next_task": "TSK.x2n.foundation.005",
            "owner_canary": "NOT_RUN",
            "task": TASK_ID,
        },
    )


def validate_extension() -> Check:
    manifest = _load_json(MANIFEST)
    historical_manifest = _load_baseline_json(MANIFEST)
    _require(
        historical_manifest.get("permissions") == HISTORICAL_PERMISSIONS
        and "host_permissions" not in historical_manifest
        and "content_scripts" not in historical_manifest,
        "Foundation004 historical permission receipt drifted",
    )
    _require(manifest.get("manifest_version") == 3 and manifest.get("minimum_chrome_version") == "120", "MV3 baseline drifted")
    _require(manifest.get("permissions") == CURRENT_PERMISSIONS, "current extension permission allowlist drifted")
    _require("host_permissions" not in manifest and "content_scripts" not in manifest, "broad host/content-script surface entered extension")
    _require(manifest.get("background") == {"service_worker": "src/service-worker.js", "type": "module"}, "service worker declaration drifted")
    _require(manifest.get("side_panel") == {"default_path": "sidepanel.html"}, "Side Panel declaration drifted")
    _require(manifest.get("content_security_policy", {}).get("extension_pages") == "script-src 'self'; object-src 'none';", "extension CSP weakened")
    try:
        key = base64.b64decode(manifest.get("key", ""), validate=True)
    except (ValueError, TypeError) as error:
        raise VerificationError("extension public key is invalid") from error
    digest = hashlib.sha256(key).digest()[:16].hex()
    derived_id = "".join(chr(ord("a") + int(nibble, 16)) for nibble in digest)
    _require(derived_id == EXTENSION_ID, "development Extension ID mismatch")

    production_files = [
        PROJECT_ROOT / "apps/extension/sidepanel.html",
        PROJECT_ROOT / "apps/extension/src/page-support.js",
        PROJECT_ROOT / "apps/extension/src/service-worker.js",
        PROJECT_ROOT / "apps/extension/src/sidepanel.js",
        PROJECT_ROOT / "apps/extension/src/xhs-current-page.js",
        PROJECT_ROOT / "apps/extension/styles/sidepanel.css",
    ]
    _require(all(path.is_file() for path in production_files), "Extension source surface is incomplete")
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in production_files)
    for pattern in (r"https?://", r"\beval\s*\(", r"new Function\s*\(", r"chrome\.storage", r"\bfetch\s*\("):
        _require(re.search(pattern, rendered, flags=re.IGNORECASE) is None, "remote/dynamic/persistent extension surface detected")
    _require("connectNative" not in rendered and "sendNativeMessage" in rendered, "Native messaging lifecycle is not short-lived")
    _require('sender.url === chrome.runtime.getURL("sidepanel.html")' in rendered, "Side Panel sender identity is not exact")
    _require("__X2N_LIFECYCLE_PROBE" in rendered and "SQLite" in rendered, "restart/reconciliation boundary is undocumented")
    html = production_files[0].read_text(encoding="utf-8")
    for name in ("save", "sync", "review", "status", "settings"):
        _require(f'id="tab-{name}"' in html and f'id="panel-{name}"' in html, f"Side Panel navigation missing: {name}")
    _require(html.count(" disabled") >= 2 and "Save unavailable" in html and "Sync unavailable" in html, "unsupported actions became executable")
    _require(re.search(r"<script(?![^>]+src=)", html, flags=re.IGNORECASE) is None, "inline Extension script detected")
    e2e_source = (PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs").read_text(encoding="utf-8")
    _require("...process.env" not in e2e_source, "Extension E2E inherits the caller environment")
    _require('PATH: process.env.PATH ?? ""' in e2e_source, "Extension E2E minimal PATH allowlist is missing")
    return Check(
        "extension_surface",
        "PASS",
        {
            "extension_id": EXTENSION_ID,
            "host_permissions": 0,
            "historical_permissions": len(HISTORICAL_PERMISSIONS),
            "navigation_tabs": 5,
            "permissions": len(CURRENT_PERMISSIONS),
            "remote_scripts": 0,
        },
    )


def validate_native_host() -> Check:
    template = _load_json(HOST_TEMPLATE)
    _require(template == {
        "allowed_origins": [EXTENSION_ORIGIN],
        "description": "x2n local companion development host",
        "name": "com.linzecolin.x2n",
        "path": "__X2N_NATIVE_HOST_LAUNCHER_ABSOLUTE_PATH__",
        "type": "stdio",
    }, "Native Host manifest template drifted")
    policy = _load_json(HOST_POLICY)
    _require(policy.get("allowed_origins") == [EXTENSION_ORIGIN] and "*" not in json.dumps(policy), "Native Host origin allowlist weakened")
    _require(policy.get("allowed_actions") == EXPECTED_ACTIONS, "Native Host action allowlist drifted")
    _require(policy.get("max_message_bytes") == 1_048_576, "Native Host message limit drifted")
    for field in ("arbitrary_local_path", "arbitrary_shell", "arbitrary_url", "unknown_fields", "unknown_versions"):
        _require(policy.get(field) == "reject", f"Native Host reject policy weakened: {field}")
    _require(policy.get("duplicate_policy") == "return_existing_job_only", "duplicate policy weakened")

    host_source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host.py").read_text(encoding="utf-8")
    installer_source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host_installer.py").read_text(encoding="utf-8")
    store_source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py").read_text(encoding="utf-8")
    for forbidden in ("shell=True", "os.system", "eval(", "exec("):
        _require(forbidden not in host_source + installer_source, "arbitrary execution surface entered Native Host")
    parser_arguments = set(re.findall(r'parser\.add_argument\("([^"]+)"', installer_source))
    _require(parser_arguments == {"action", "--browser", "--confirm"}, "installer acquired an arbitrary input surface")
    for token in (
        "INSTALL_X2N_NATIVE_HOST",
        "UNINSTALL_X2N_NATIVE_HOST",
        "user_level_only",
        ".x2n-native-host-owned.json",
        "launcher_sha256",
        "manifest_sha256",
        "x2n-staging",
        "x2n-backup",
        "os.replace",
        "UV_KEYRING_PROVIDER",
        "UV_NO_CONFIG",
        "exec /usr/bin/env -i",
        "PYTHONNOUSERSITE=1",
        "--frozen",
        "--require-hashes",
    ):
        _require(token in installer_source, f"installer safety control missing: {token}")
    _require("payload, page URL, account data, media reference, or credential" in store_source, "payload-free Store boundary is undocumented")
    _require("submit_skeleton_job" in store_source and "get_skeleton_job" in store_source, "durable skeleton Job API missing")
    _require("one process, one request, one response" in host_source, "Native Host short process boundary missing")
    return Check(
        "native_host_contract",
        "PASS",
        {
            "allowed_actions": len(EXPECTED_ACTIONS),
            "allowed_origins": 1,
            "arbitrary_input_surfaces": 0,
            "max_message_bytes": 1_048_576,
            "owner_install": "NOT_RUN",
        },
    )


def _uv_registry_versions(text: str) -> dict[str, str]:
    packages: dict[str, str] = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'(?m)^name = "([^"]+)"$', block)
        version = re.search(r'(?m)^version = "([^"]+)"$', block)
        source = re.search(r"(?m)^source = (.+)$", block)
        if name and version and source and "registry" in source.group(1):
            packages[name.group(1)] = version.group(1)
    return packages


def validate_fixtures_and_dependencies() -> Check:
    fixture = _load_json(FIXTURE)
    cases = fixture.get("cases", [])
    _require(fixture.get("fixture_id") == "FIXTURE.X2N.S01.F004.001" and len(cases) == 20, "Extension fixture count/identity drifted")
    _require(len({item.get("id") for item in cases}) == 20, "Extension fixture IDs are not unique")
    _require({item.get("platform") for item in cases if item.get("supported")} == {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"}, "six-platform recognition coverage drifted")
    for field in ("real_accounts", "contains_credentials", "contains_private_content", "contains_media_urls", "contains_local_absolute_paths"):
        _require(fixture.get(field) is False, f"Extension fixture public boundary weakened: {field}")
    rows = _load_json(FIXTURE_MANIFEST).get("fixtures", [])
    _require(len(rows) >= 5 and rows[4] == {
        "id": "FIXTURE.X2N.S01.F004.001",
        "path": "packages/test-fixtures/extension/v1/page_cases.json",
        "case_count": 20,
        "purpose": "MV3 Side Panel six-platform page recognition and unsupported-page fail-closed behavior",
    }, "Extension fixture registration drifted")

    package = _load_json(PROJECT_ROOT / "package.json")
    _require(package.get("devDependencies") == {"@playwright/test": "1.61.1"}, "Playwright direct dependency drifted")
    lock = _load_json(PROJECT_ROOT / "package-lock.json")
    npm = {
        path.removeprefix("node_modules/"): metadata
        for path, metadata in lock.get("packages", {}).items()
        if path.startswith("node_modules/") and metadata.get("link") is not True
    }
    typescript_names = {name for name in npm if name == "typescript" or name.startswith("@typescript/typescript-")}
    _require(len(typescript_names) == 21 and set(npm) == typescript_names | {"@playwright/test", "playwright", "playwright-core", "fsevents"}, "npm dependency set drifted")
    _require({name for name, item in npm.items() if item.get("hasInstallScript") is True} == {"fsevents"}, "install-script set drifted")
    _require("ignore-scripts=true" in (PROJECT_ROOT / ".npmrc").read_text(encoding="utf-8").splitlines(), "npm scripts are not disabled")
    _require(
        _uv_registry_versions((PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8"))
        == EXPECTED_REGISTRY_DEPENDENCIES | EXPECTED_CI_DEPENDENCIES,
        "Python runtime or later CI dependency set drifted",
    )
    sbom = _load_json(SBOM)
    _require(len(sbom.get("components", [])) == 30, "Foundation004 SBOM component count drifted")
    component_refs = {item.get("bom-ref") for item in sbom.get("components", [])}
    _require(len(component_refs) == 30 and None not in component_refs, "Foundation004 SBOM component identity drifted")
    dependency_rows = sbom.get("dependencies", [])
    dependency_refs = {item.get("ref") for item in dependency_rows}
    _require(component_refs <= dependency_refs, "Foundation004 SBOM dependency rows are incomplete")
    _require(
        all(set(item.get("dependsOn", [])) <= component_refs for item in dependency_rows),
        "Foundation004 SBOM contains an unresolved dependency edge",
    )
    properties = {item.get("name"): item.get("value") for item in sbom.get("metadata", {}).get("properties", [])}
    _require(properties.get("x2n:install-script-packages") == "fsevents" and properties.get("x2n:install-scripts-executed") == "0", "SBOM install-script control drifted")
    return Check(
        "fixtures_and_dependencies",
        "PASS",
        {
            "fixture_cases": 20,
            "install_scripts_executed": 0,
            "registry_components": 30,
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
        "npm_config_ignore_scripts": "true",
    }
    configured_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    browser_cache = Path(configured_cache) if configured_cache else Path.home() / "Library/Caches/ms-playwright"
    if browser_cache.is_dir():
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    elif require_browser:
        raise VerificationError("Playwright Chromium cache is unavailable")
    return env


def _run_external(label: str, command: Sequence[str], *, env: dict[str, str], timeout: int = 240) -> str:
    result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False, capture_output=True, text=True, timeout=timeout)
    _require(result.returncode == 0, f"external Foundation004 verification failed: {label}")
    combined = result.stdout + result.stderr
    _require("/" + "Users/" not in combined and "github" + "_pat_" not in combined, f"external verification exposed private data: {label}")
    return combined


def _json_line(output: str, label: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.startswith("{")]
    _require(len(lines) == 1, f"external JSON output is ambiguous: {label}")
    try:
        value = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise VerificationError(f"external JSON output is invalid: {label}") from error
    _require(isinstance(value, dict), f"external JSON output is not an object: {label}")
    return value


def validate_execution() -> Check:
    for command in ("node", "npm", "uv"):
        _require(shutil.which(command) is not None, f"required verifier tool is unavailable: {command}")
    with tempfile.TemporaryDirectory(prefix="x2n-f004-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, require_browser=True)
        sbom = _json_line(
            _run_external("sbom", (os.sys.executable, "-B", "scripts/generate_foundation_004_sbom.py", "--check"), env=env),
            "sbom",
        )
        _require(sbom == {"components": 30, "install_scripts_executed": 0, "status": "PASS"}, "SBOM verification metrics drifted")
        self_test = _json_line(
            _run_external("extension_self_test", ("npm", "run", "self-test", "--workspace", "@x2n/extension"), env=env),
            "extension_self_test",
        )
        _require(self_test.get("status") == "PASS" and self_test.get("extension_id") == EXTENSION_ID, "Extension self-test failed")
        _require(self_test.get("fixture_recognition_passed") == self_test.get("fixture_cases") == 20, "Extension fixture recognition threshold failed")
        prefix = ("uv", "run", "--quiet", "--isolated", "--frozen", "--package", "x2n-companion", "python", "-B")
        native_tests = _run_external(
            "companion_tests",
            (*prefix, "-m", "unittest", "discover", "-s", "apps/companion/tests", "-p", "test_*.py"),
            env=env,
        )
        test_count = re.search(r"Ran (\d+) tests", native_tests)
        historical_test_paths = [
            path
            for path in _git(["ls-tree", "-r", "--name-only", FINAL_COMMIT, "xhs-douyin-2notion/apps/companion/tests"]).splitlines()
            if Path(path).name.startswith("test_") and path.endswith(".py")
        ]
        historical_count = sum(len(re.findall(r"(?m)^    def test_", _git(["show", f"{FINAL_COMMIT}:{path}"]))) for path in historical_test_paths)
        current_count = sum(len(re.findall(r"(?m)^    def test_", path.read_text(encoding="utf-8"))) for path in sorted((PROJECT_ROOT / "apps/companion/tests").glob("test_*.py")))
        _require(historical_count == 24, "historical Companion test count drifted")
        _require(test_count is not None and int(test_count.group(1)) == current_count and current_count >= historical_count, "current Companion tests were skipped or removed")
        e2e = _json_line(
            _run_external("extension_e2e", ("npm", "run", "test:e2e", "--workspace", "@x2n/extension"), env=env),
            "extension_e2e",
        )
        xhs_fixtures = _json_line(
            _run_external("xhs_fixture_e2e", ("npm", "run", "test:xhs-fixtures", "--workspace", "@x2n/extension"), env=env),
            "xhs_fixture_e2e",
        )
    expected = {
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
    for key, expected_value in expected.items():
        _require(e2e.get(key) == expected_value, f"Extension E2E metric drifted: {key}")
    for name in ("screenshot", "trace"):
        receipt = e2e.get(name, {})
        _require(isinstance(receipt.get("bytes"), int) and receipt["bytes"] > 0, f"E2E {name} is empty")
        _require(re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256", ""))) is not None, f"E2E {name} receipt is invalid")
    _require(xhs_fixtures == {
        "console_uncaught_errors": 0,
        "fixture_cases": 5,
        "observation_diff_mismatches": 0,
        "owner_canary": "NOT_RUN",
        "platform_changed_verified": 2,
        "platform_calls": 0,
        "query_fragment_persisted": 0,
        "stable_ids_verified": 3,
        "status": "PASS",
    }, "XHS fixture E2E metrics drifted")
    return Check(
        "isolated_extension_e2e",
        "PASS",
        {
            "companion_tests": current_count,
            "console_uncaught_errors": 0,
            "duplicate_jobs": 0,
            "fixture_recognition": "20/20",
            "lost_jobs": 0,
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "screenshot": e2e["screenshot"],
            "service_worker_restarts": 100,
            "trace": e2e["trace"],
            "wrong_statuses": 0,
            "xhs_fixture_cases": 5,
            "xhs_platform_changed_verified": 2,
        },
    )


def run_checks(*, verify_worktree: bool, allow_external_main_dirty: bool, run_external: bool) -> list[Check]:
    checks = [
        validate_scope(),
        validate_task_and_state(),
        validate_extension(),
        validate_native_host(),
        validate_fixtures_and_dependencies(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_execution())
    _require(all(check.status == "PASS" for check in checks), "a Foundation004 check failed")
    return checks


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "evidence contains a local absolute path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains a URL")
    _require("github" + "_pat_" not in rendered, "evidence contains credential-shaped material")


def write_evidence(checks: list[Check]) -> None:
    names = {check.name for check in checks}
    _require({"isolated_extension_e2e", "worktree_isolation"} <= names, "evidence requires full E2E and worktree validation")
    payload = {
        "acceptance_ids": ["ACC.x2n.ext.001", "ACC.x2n.ext.002", "ACC.x2n.ext.003", "ACC.x2n.ext.004"],
        "acceptance_status": {
            "ACC.x2n.ext.001": "PASS_CI_SYNTH_20_OF_20_OWNER_CANARY_NOT_RUN",
            "ACC.x2n.ext.002": "PASS_ISOLATED_CHAOS_100_RESTARTS_SQLITE_RECONCILED",
            "ACC.x2n.ext.003": "PASS_TEMP_NATIVE_HOST_CONTRACT_IDEMPOTENCY_INJECTION",
            "ACC.x2n.ext.004": "PASS_PERMISSION_ALLOWLIST_3_NO_HOST_PERMISSIONS",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "native_host_registration": "TEMP_ISOLATED_ONLY_OWNER_INSTALL_NOT_RUN",
        "phase": "PH.X2N.1.4",
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_G1_PASS",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.1",
        "stage_gate": "G1_NOT_RUN",
        "status": "PASS",
        "task_id": TASK_ID,
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(evidence.get("status") == "PASS" and evidence.get("stage_gate") == "G1_NOT_RUN", "evidence status overstated")
    _require(evidence.get("native_host_registration") == "TEMP_ISOLATED_ONLY_OWNER_INSTALL_NOT_RUN", "Native Host registration evidence drifted")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check")
    return Check("evidence", "PASS", {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.foundation.004")
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
                {"checks": [{"name": item.name, "status": item.status} for item in checks], "status": "PASS", "task": TASK_ID},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, subprocess.TimeoutExpired, VerificationError) as error:
        print(json.dumps({"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID}, ensure_ascii=False, sort_keys=True), file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
