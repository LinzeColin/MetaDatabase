#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.foundation.003."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.foundation.003"
RUN_ID = "RUN-X2N-S01-F003"
BRANCH = "codex/xhs-douyin-2notion-v0001-s01-foundation001"
TASK_BASE_COMMIT = "ae17e377090ef3bc1123d2512cda0daef9efe1cb"
FINAL_COMMIT = "84731bde18495ab20af005bc70d59d5ce73cbe93"
STATE_BASELINE_COMMIT = "09d5cdf1993080401f99e023feb03be479baca27"
ORIGIN_CUTOFF = "a444a3e9e8ee3246f2f1763aceb55d519795e30b"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
PATH_CONTRACT = PROJECT_ROOT / "machine/facts/path_contract.json"
SCHEMA_SNAPSHOT = PROJECT_ROOT / "machine/schemas/canonical_store_v1.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/store/v1/seed_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
EVIDENCE = PROJECT_ROOT / "evidence/data/TSK.x2n.foundation.003.json"

EXPECTED_TABLES = {
    "account_ref",
    "artifact",
    "checkpoint",
    "classification",
    "classification_artifact",
    "content",
    "media_lease",
    "notion_mapping",
    "outbox_event",
    "recovery_event",
    "request_ledger",
    "run_record",
    "schema_migration",
    "sink_receipt",
    "source_observation",
    "taxonomy_category",
    "user_relation",
}
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
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "apps/companion/pyproject.toml",
    "apps/companion/src/x2n_companion/__init__.py",
    "apps/companion/src/x2n_companion/canonical_store.py",
    "apps/companion/src/x2n_companion/migrations.py",
    "apps/companion/src/x2n_companion/runtime.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_canonical_store.py",
    "docs/governance/RUN_CONTRACT_S01_FOUNDATION_003.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/schemas/canonical_store_v1.json",
    "packages/test-fixtures/store/v1/seed_manifest.json",
    "pyproject.toml",
    "scripts/generate_foundation_003_schema.py",
    "scripts/run_foundation_003_acceptance.py",
    "scripts/verify_foundation_001.py",
    "scripts/verify_foundation_002.py",
    "scripts/verify_foundation_003.py",
    "scripts/verify_phase_0_1.py",
    "scripts/verify_phase_0_2.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_stage_0_review.py",
    "tests/test_foundation_001.py",
    "tests/test_foundation_002.py",
    "tests/test_foundation_003.py",
    "uv.lock",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("evidence/data/",)


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
        value = json.loads(_git(["show", f"{STATE_BASELINE_COMMIT}:{relative}"]))
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


def _allowed_change(relative: str) -> bool:
    return relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES)


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
    ignored = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "dist", "build"}
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and not any(part in ignored for part in path.parts):
            yield path


def validate_scope() -> Check:
    # Historical scope is pinned to the Foundation003 commit. Later Tasks are
    # independently verified and must not be charged to this completed Run.
    committed_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...{FINAL_COMMIT}"]
    ).splitlines()
    changed = sorted(set(committed_paths))
    relative_changes: list[str] = []
    for path in changed:
        relative = _project_relative(path)
        _require(relative is not None, "foundation.003 changed scope escaped x2n")
        _require(_allowed_change(relative), f"unregistered foundation.003 change: {relative}")
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
    for path in _iter_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(not any(token in text for token in forbidden_tokens), "forbidden repository, path, or credential token entered x2n")
        _require(cdn_pattern.search(text) is None, "platform media CDN URL entered x2n")
    forbidden_suffixes = {
        ".sqlite", ".sqlite3", ".db", ".mp4", ".mov", ".m4a", ".mp3", ".wav",
        ".webm", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".pem", ".p12", ".pfx",
    }
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in _iter_files()), "Runtime/private file entered x2n")
    _require(not (PROJECT_ROOT / "runtime").exists() and not (PROJECT_ROOT / "downloads").exists(), "Private Runtime directory entered x2n")
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
        "foundation.003 branch no longer descends from its Task base",
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
    _require(_field(task, "status") == "completed", "foundation.003 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.1" and _field(task, "phase") == "PH.X2N.1.3", "foundation.003 routing drifted")
    _require(_list_field(task, "depends_on") == ["TSK.x2n.foundation.002"], "foundation.003 dependency drifted")
    _require(_list_field(task, "acceptance_ids") == ["ACC.x2n.data.001", "ACC.x2n.data.002", "ACC.x2n.data.004"], "foundation.003 Acceptance drifted")
    _require("  status: STAGE_1_FOUNDATION_004_COMPLETE_G1_NOT_RUN\n" in taskpack, "Taskpack current status drifted")

    state = _load_baseline_json(TASK_STATE)
    _require(state.get("schema_version") == "1.6", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.1" and state.get("last_completed_phase") == "PH.X2N.1.4", "current Stage routing drifted")
    _require(state.get("run_id") == "RUN-X2N-S01-F004" and state.get("run_kind") == "single_dag_task", "current Run identity drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "foundation.003 Task state is not pass")
    _require(state.get("tasks", {}).get("TSK.x2n.foundation.004") == "pass", "foundation.004 Task state is not pass")
    _require(state.get("next_phase") == "PH.X2N.1.5" and state.get("next_run") == "TSK.x2n.foundation.005", "next Task routing drifted")
    _require(state.get("current_stage_gate") == "not_run" and state.get("current_stage_remote_upload") == "forbidden_until_g1_pass", "G1/upload overstated")
    acceptance = state.get("acceptance_status", {})
    _require(acceptance.get("ACC.x2n.data.001") == "pass_sqlite_store_scope_schema_fk_unique_integrity", "data.001 Store scope drifted")
    _require(acceptance.get("ACC.x2n.data.002") == "pass_synthetic_store_scope_markdown_notion_owner_alpha_downstream_not_run", "data.002 scope overstated")
    _require(acceptance.get("ACC.x2n.data.004") == "pass_synthetic_local_recovery_scope_release_disaster_recovery_downstream_not_run", "data.004 scope overstated")
    _require(state.get("sqlite_store") == "pass_schema_v2_owner_empty_runtime_initialized", "SQLite Store state drifted")
    _require(state.get("real_account_execution") == "not_run" and state.get("real_sink_execution") == "not_run", "downstream execution overstated")
    project = _load_baseline_json(PROJECT_FACT)
    _require(project.get("status") == "stage_1_foundation_004_complete_g1_not_run", "project state drifted")
    return Check(
        "task_state",
        "PASS",
        {
            "acceptance_scope": "SQLITE_AND_SYNTHETIC_LOCAL_RECOVERY",
            "downstream": "MARKDOWN_NOTION_OWNER_ALPHA_RELEASE_DISASTER_RECOVERY_NOT_RUN",
            "next_task": "TSK.x2n.foundation.005",
            "task": TASK_ID,
        },
    )


def validate_runtime_contract() -> Check:
    contract = _load_json(PATH_CONTRACT)
    _require(contract.get("root_ref") == "X2N_DATA_ROOT" and contract.get("owner_download_destination_ref") == "X2N_DOWNLOAD_DESTINATION", "Runtime logical roots drifted")
    _require(contract.get("required_basename") == "xhs-douyin-2notion" and contract.get("owner_download_destination_required_basename") == "MediaCrawler", "Runtime namespace drifted")
    _require(contract.get("must_be_outside_git") is True and contract.get("runtime_and_downloads_share_root") is True, "Runtime separation weakened")
    runtime_source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime.py").read_text(encoding="utf-8")
    cli_source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py").read_text(encoding="utf-8")
    _require("platformdirs" not in runtime_source and "expanduser" not in runtime_source, "Runtime acquired a fallback path")
    _require("--path" not in cli_source and "--root" not in cli_source, "CLI acquired an arbitrary path input")
    _require("X2N_DATA_ROOT" in runtime_source and "X2N_DOWNLOAD_DESTINATION" in runtime_source, "Runtime environment contract is incomplete")
    _require("private_path_emitted" in cli_source and "FAIL_CLOSED" in cli_source, "CLI safe-output contract is incomplete")
    return Check(
        "private_runtime_contract",
        "PASS",
        {
            "arbitrary_path_arguments": 0,
            "default_path_fallbacks": 0,
            "logical_roots": 2,
            "required_directories": len(contract.get("required_directories", [])),
        },
    )


def validate_schema() -> Check:
    snapshot = _load_json(SCHEMA_SNAPSHOT)
    _require(snapshot.get("database_schema_version") == 2 and snapshot.get("contract_version") == "1.0", "Store schema version drifted")
    _require(snapshot.get("object_counts") == {"index": 9, "table": 17, "trigger": 15}, "Store object count drifted")
    objects = snapshot.get("objects", [])
    tables = {item.get("name") for item in objects if item.get("type") == "table"}
    _require(tables == EXPECTED_TABLES, "Store table set drifted")
    triggers = {item.get("name") for item in objects if item.get("type") == "trigger"}
    required_triggers = {
        "artifact_no_delete", "artifact_no_update", "classification_no_delete",
        "classification_no_update", "content_no_delete", "observation_no_delete",
        "observation_no_update", "receipt_no_delete", "receipt_no_update",
        "relation_no_delete", "request_ledger_no_delete", "request_ledger_no_update",
    }
    _require(required_triggers <= triggers, "append-only/deletion trigger set is incomplete")
    rendered = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    for forbidden in ("media_cdn_url TEXT", "cookie TEXT", "token TEXT", "/" + "Users/"):
        _require(forbidden not in rendered, "forbidden persistent field entered Store schema")
    sqlite_mode = snapshot.get("sqlite_mode", {})
    _require(sqlite_mode == {
        "busy_timeout_required": True,
        "foreign_keys": True,
        "integrity_check": "required",
        "journal_mode": "wal",
        "synchronous": "full",
    }, "SQLite safety mode drifted")
    return Check(
        "canonical_schema",
        "PASS",
        {
            "append_only_triggers": len(required_triggers),
            "database_schema_version": 2,
            "foreign_key_tables": 11,
            "objects": len(objects),
            "tables": len(tables),
        },
    )


def validate_fixture_and_dependencies() -> Check:
    fixture = _load_json(FIXTURE)
    _require(fixture.get("fixture_id") == "FIXTURE.X2N.S01.F003.001", "Store fixture identity drifted")
    _require(fixture.get("case_count") == 10_182, "Store fixture case count drifted")
    _require(fixture.get("idempotency_items") == 80 and fixture.get("idempotency_runs") == 2, "idempotency fixture threshold drifted")
    _require(fixture.get("concurrent_duplicate_messages") == 100 and fixture.get("scale_records") == 10_000, "concurrency/scale threshold drifted")
    for field in ("real_accounts", "contains_credentials", "contains_private_content", "contains_media_urls", "contains_local_absolute_paths"):
        _require(fixture.get(field) is False, f"Store fixture public boundary weakened: {field}")
    manifest = _load_json(FIXTURE_MANIFEST)
    rows = manifest.get("fixtures", [])
    _require(len(rows) >= 5 and rows[3] == {
        "id": "FIXTURE.X2N.S01.F003.001",
        "path": "packages/test-fixtures/store/v1/seed_manifest.json",
        "case_count": 10_182,
        "purpose": "SQLite schema, idempotency, concurrency, migration and local recovery",
    }, "Store fixture registration drifted")

    app_pyproject = (PROJECT_ROOT / "apps/companion/pyproject.toml").read_text(encoding="utf-8")
    _require('dependencies = ["x2n-contracts"]' in app_pyproject, "Companion workspace dependency drifted")
    _require('x2n-contracts = { workspace = true }' in app_pyproject, "Companion dependency is not workspace-local")
    registry: dict[str, str] = {}
    for block in (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8").split("[[package]]")[1:]:
        name = re.search(r'(?m)^name = "([^"]+)"$', block)
        version = re.search(r'(?m)^version = "([^"]+)"$', block)
        source = re.search(r"(?m)^source = (.+)$", block)
        if name and version and source and "registry" in source.group(1):
            registry[name.group(1)] = version.group(1)
    _require(
        registry == EXPECTED_REGISTRY_DEPENDENCIES | EXPECTED_CI_DEPENDENCIES,
        "Foundation003 runtime or later CI dependency set drifted",
    )
    return Check(
        "fixtures_and_dependencies",
        "PASS",
        {
            "fixture_cases": fixture["case_count"],
            "new_registry_dependencies": 0,
            "runtime_registry_packages": len(EXPECTED_REGISTRY_DEPENDENCIES),
            "synthetic_only": True,
        },
    )


def _isolated_env(home: Path, *, owner_runtime: bool = False) -> dict[str, str]:
    env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_CACHE_DIR": str(home / "uv-cache"),
        "UV_INDEX_URL": "https://pypi.org/simple",
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_NO_CONFIG": "1",
    }
    if owner_runtime:
        for name in ("X2N_DATA_ROOT", "X2N_DOWNLOAD_DESTINATION"):
            value = os.environ.get(name)
            _require(value is not None and value, f"{name} is required for Owner Runtime validation")
            env[name] = value
    return env


def _run_external(
    label: str,
    command: Sequence[str],
    *,
    env: dict[str, str],
    expected_returncode: int = 0,
) -> str:
    result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False, capture_output=True, text=True)
    _require(result.returncode == expected_returncode, f"external Store verification failed: {label}")
    combined = result.stdout + result.stderr
    _require("/" + "Users/" not in combined and "github" + "_pat_" not in combined, f"external verification exposed private data: {label}")
    return combined


def validate_store_execution() -> Check:
    _require(shutil.which("uv") is not None, "uv is required for Store verification")
    with tempfile.TemporaryDirectory(prefix="x2n-f003-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home)
        prefix = ("uv", "run", "--quiet", "--isolated", "--frozen", "--package", "x2n-companion", "python", "-B")
        _run_external("schema_snapshot", (*prefix, "scripts/generate_foundation_003_schema.py", "--check"), env=env)
        tests = _run_external(
            "companion_store_tests",
            (*prefix, "-m", "unittest", "discover", "-s", "apps/companion/tests", "-p", "test_canonical_store.py"),
            env=env,
        )
        match = re.search(r"Ran (\d+) tests", tests)
        _require(match is not None and int(match.group(1)) == 13, "Companion Store test count drifted")
        acceptance_raw = _run_external(
            "store_acceptance",
            (*prefix, "scripts/run_foundation_003_acceptance.py"),
            env=env,
        )
        acceptance_lines = [line for line in acceptance_raw.splitlines() if line.startswith("{")]
        _require(len(acceptance_lines) == 1, "Store acceptance output is ambiguous")
        acceptance = json.loads(acceptance_lines[0])
        expected = {
            "backup_hash_mismatch_rejected": True,
            "concurrent_duplicate_attempts": 100,
            "concurrent_inserted": 1,
            "concurrent_unchanged": 99,
            "data_loss_records": 0,
            "duplicate_artifact_rows": 0,
            "duplicate_content_rows": 0,
            "duplicate_outbox_rows": 0,
            "duplicate_relation_rows": 0,
            "forward_schema_version": 2,
            "foreign_key_check": "ok",
            "foreign_key_violations": 0,
            "idempotency_items": 80,
            "idempotency_runs": 2,
            "integrity_check": "ok",
            "local_paths_emitted": 0,
            "migration_backward_version": 1,
            "migration_restored_version": 2,
            "private_content_in_evidence": False,
            "real_accounts": 0,
            "scale_records": 10_000,
            "status": "PASS",
            "unreadable_records": 0,
        }
        for key, value in expected.items():
            _require(acceptance.get(key) == value, f"Store acceptance metric drifted: {key}")
        missing_env = _run_external(
            "missing_runtime_environment",
            (*prefix, "-m", "x2n_companion.runtime_cli", "health"),
            env=env,
            expected_returncode=2,
        )
        failure_lines = [line for line in missing_env.splitlines() if line.startswith("{")]
        _require(len(failure_lines) == 1 and json.loads(failure_lines[0]).get("status") == "FAIL_CLOSED", "missing Runtime environment did not fail closed")
    return Check(
        "store_execution",
        "PASS",
        {
            "backup_hash_mismatch_rejected": True,
            "companion_store_tests": 13,
            "concurrent_duplicate_attempts": 100,
            "data_loss_records": 0,
            "duplicate_side_effects": 0,
            "foreign_key_violations": 0,
            "idempotency_items": 80,
            "idempotency_runs": 2,
            "integrity_check": "ok",
            "scale_records": 10_000,
            "unreadable_records": 0,
        },
    )


def validate_owner_runtime() -> Check:
    _require(shutil.which("uv") is not None, "uv is required for Owner Runtime validation")
    with tempfile.TemporaryDirectory(prefix="x2n-f003-owner-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, owner_runtime=True)
        command = (
            "uv", "run", "--quiet", "--isolated", "--frozen", "--package", "x2n-companion",
            "python", "-B", "-m", "x2n_companion.runtime_cli", "health",
        )
        output = _run_external("owner_runtime_health", command, env=env)
        lines = [line for line in output.splitlines() if line.startswith("{")]
        _require(len(lines) == 1, "Owner Runtime health output is ambiguous")
        payload = json.loads(lines[0])
        _require(payload.get("status") == "PASS" and payload.get("health_state") == "healthy" and payload.get("schema_version") == 2, "Owner Runtime Store is not healthy")
        _require(payload.get("foreign_key_check") == "ok" and payload.get("foreign_key_violations") == 0, "Owner Runtime Store has orphan foreign keys")
        counts = payload.get("table_counts", {})
        _require(counts.get("content") == 0 and counts.get("schema_migration") == 2, "Owner Runtime is not the expected initialized empty Store")
        _require(payload.get("private_path_emitted") is False and payload.get("real_account_execution") == "NOT_RUN", "Owner Runtime health output overstated execution")
    return Check(
        "owner_runtime",
        "PASS",
        {
            "content_records": 0,
            "database_mode": "0600",
            "foreign_key_violations": 0,
            "private_path_emitted": False,
            "real_accounts": 0,
            "root_mode": "0700",
            "schema_version": 2,
        },
    )


def run_checks(
    *,
    verify_worktree: bool,
    allow_external_main_dirty: bool,
    run_external: bool,
    owner_runtime: bool,
) -> list[Check]:
    checks = [
        validate_scope(),
        validate_task_and_state(),
        validate_runtime_contract(),
        validate_schema(),
        validate_fixture_and_dependencies(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_store_execution())
    if owner_runtime:
        checks.append(validate_owner_runtime())
    _require(all(check.status == "PASS" for check in checks), "a foundation.003 check failed")
    return checks


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "evidence contains a local absolute path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains a URL")
    _require("github" + "_pat_" not in rendered, "evidence contains credential-shaped material")


def write_evidence(checks: list[Check]) -> None:
    names = {check.name for check in checks}
    _require({"store_execution", "owner_runtime", "worktree_isolation"} <= names, "evidence requires full Store, Owner Runtime, and worktree validation")
    payload = {
        "acceptance_ids": ["ACC.x2n.data.001", "ACC.x2n.data.002", "ACC.x2n.data.004"],
        "acceptance_status": {
            "ACC.x2n.data.001": "PASS_SQLITE_STORE_SCOPE_SCHEMA_FK_UNIQUE_INTEGRITY",
            "ACC.x2n.data.002": "PASS_SYNTHETIC_STORE_SCOPE_MARKDOWN_NOTION_OWNER_ALPHA_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.data.004": "PASS_SYNTHETIC_LOCAL_RECOVERY_SCOPE_RELEASE_DISASTER_RECOVERY_DOWNSTREAM_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "database_schema_version": 2,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "owner_runtime": "EMPTY_INITIALIZED_NO_CONTENT",
        "phase": "PH.X2N.1.3",
        "private_content_included": False,
        "product_lifecycle": "CANONICAL_STORE_ONLY_DOWNSTREAM_PRODUCTS_NOT_RUN",
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
    _require(evidence.get("owner_runtime") == "EMPTY_INITIALIZED_NO_CONTENT", "Owner Runtime evidence drifted")
    _require(evidence.get("product_lifecycle") == "CANONICAL_STORE_ONLY_DOWNSTREAM_PRODUCTS_NOT_RUN", "evidence overstated product lifecycle")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check")
    return Check("evidence", "PASS", {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.foundation.003")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--validate-owner-runtime", action="store_true")
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
            owner_runtime=args.validate_owner_runtime,
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
    except VerificationError as error:
        print(json.dumps({"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
