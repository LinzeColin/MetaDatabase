#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.foundation.001."""

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
TASK_ID = "TSK.x2n.foundation.001"
RUN_ID = "RUN-X2N-S01-F001"
BRANCH = "codex/xhs-douyin-2notion-v0001-s01-foundation001"
BASE_COMMIT = "f1e5016a4e1bba10c86d8dd017868d5d64835f42"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE_DOC = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
EVIDENCE = PROJECT_ROOT / "evidence/foundation/TSK.x2n.foundation.001.json"

EXPECTED_OUTPUTS = (
    "SKILL.md",
    "agents/openai.yaml",
    "apps/extension",
    "apps/companion",
    "packages/contracts",
    "tests",
    "THIRD_PARTY_NOTICES.md",
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    ".gitignore",
    "agents/openai.yaml",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "uv.lock",
    "功能清单.md",
    "开发记录.md",
    "模型参数文件.md",
    "docs/governance/RUN_CONTRACT_S01_FOUNDATION_001.md",
    "docs/governance/RUN_CONTRACT_S01_FOUNDATION_002.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/sbom/stage_1_foundation_002.cdx.json",
    "scripts/generate_foundation_002_sbom.py",
    "scripts/verify_foundation_001.py",
    "scripts/verify_foundation_002.py",
    "scripts/verify_phase_0_2.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_stage_0_review.py",
    "scripts/verify_stage_0_review_resume.py",
    "tests/test_foundation_001.py",
    "tests/test_foundation_002.py",
    "tests/test_phase_0_5.py",
}
ALLOWED_CHANGED_PREFIXES = (
    "apps/extension/",
    "apps/companion/",
    "packages/contracts/",
    "packages/test-fixtures/",
    "evidence/foundation/",
    "evidence/contracts/",
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
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _git(args: Sequence[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
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
    if path == "xhs-douyin-2notion":
        return ""
    if path.startswith(prefix):
        return path[len(prefix) :]
    return None


def _allowed_change(relative: str) -> bool:
    return relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES)


def _task_block(taskpack_text: str, task_id: str) -> str:
    match = re.search(
        rf"(?ms)^- id: {re.escape(task_id)}\n(?P<body>.*?)(?=^- id: TSK\.x2n\.|\Z)",
        taskpack_text,
    )
    _require(match is not None, f"Task block missing: {task_id}")
    return match.group(0)


def _field(block: str, name: str) -> str:
    match = re.search(rf"(?m)^  {re.escape(name)}: ([^\n]+)$", block)
    _require(match is not None, f"Task field missing: {name}")
    return match.group(1).strip().strip("'\"")


def _list_field(block: str, name: str) -> list[str]:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<items>(?:  - [^\n]+\n)*)",
        block,
    )
    _require(match is not None, f"Task list field missing: {name}")
    return [line.removeprefix("  - ") for line in match.group("items").splitlines()]


def validate_governance() -> Check:
    _require((REPOSITORY_ROOT / "AGENTS.md").is_file(), "repository AGENTS missing")
    _require((PROJECT_ROOT / "AGENTS.md").is_file(), "project AGENTS missing")
    for relative in ("功能清单.md", "开发记录.md", "模型参数文件.md", "machine/facts/project.json", "machine/facts/task_state.json"):
        _require((PROJECT_ROOT / relative).is_file(), "governance registration file missing")

    status_paths = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    committed_paths = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{BASE_COMMIT}...HEAD"]).splitlines()
    changed = sorted(set(status_paths + committed_paths))
    relative_changes: list[str] = []
    for path in changed:
        relative = _project_relative(path)
        _require(relative is not None, "changed scope escaped xhs-douyin-2notion")
        _require(_allowed_change(relative), "an unregistered foundation fact writer changed the tree")
        relative_changes.append(relative)

    taskpack_text = TASKPACK.read_text(encoding="utf-8")
    task_ids = re.findall(r"(?m)^- id: (TSK\.x2n\.[a-z]+\.\d{3})$", taskpack_text)
    stage_ids = re.findall(r"(?m)^- id: (STG\.X2N\.\d)$", taskpack_text)
    requirement_ids = re.findall(r"(?m)^- id: (REQ\.X2N\.\d{3})$", taskpack_text)
    acceptance_ids = re.findall(
        r"^## (ACC\.x2n\.[a-z]+\.\d{3})\b",
        ACCEPTANCE_DOC.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    _require(stage_ids == [f"STG.X2N.{index}" for index in range(7)], "Stage registry drifted")
    _require(len(task_ids) == 43, "Task registry count drifted")
    _require(requirement_ids == [f"REQ.X2N.{index:03d}" for index in range(1, 33)], "Requirement registry drifted")
    _require(len(acceptance_ids) == 61, "Acceptance registry count drifted")
    _require(len(task_ids) == len(set(task_ids)), "duplicate Task IDs")
    _require(len(acceptance_ids) == len(set(acceptance_ids)), "duplicate Acceptance IDs")
    _require("  name: xhs-douyin-2notion\n" in taskpack_text, "project identity drifted")

    project = _load_json(PROJECT_FACT)
    _require(project.get("parent_repository") == "LinzeColin/MetaDatabase", "parent repository drifted")
    _require(project.get("project_path") == "xhs-douyin-2notion/", "project path drifted")
    _require(project.get("runtime_root_ref") == project.get("downloads_root_ref") == "X2N_DATA_ROOT", "Runtime/download root drifted")
    root_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    _require(sum(line.startswith("| xhs-douyin-2notion |") for line in root_readme.splitlines()) == 1, "parent project registration drifted")

    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "Codex" + "Project",
        "LinzeColin/" + "xhs-douyin-2notion",
        "/" + "Users/",
    )
    safe_suffixes = {"", ".md", ".json", ".yaml", ".yml", ".py", ".toml", ".mjs", ".ts"}
    scanned = 0
    for path in _iter_files():
        if path.suffix.lower() not in safe_suffixes and path.name not in {"VERSION", ".gitignore"}:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(not any(token in text for token in forbidden_tokens), "forbidden repository or local-path token entered the project")
        _require(re.search(r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp)", text, flags=re.IGNORECASE) is None, "platform media CDN URL entered the project")
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".mov", ".m4a", ".mp3", ".wav", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".pem", ".p12", ".pfx"}
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in _iter_files()), "private/runtime file type entered the project")

    return Check(
        "governance",
        "PASS",
        {
            "acceptance_id_duplicates": 0,
            "changed_files": len(relative_changes),
            "out_of_scope_writes": 0,
            "text_files_scanned": scanned,
            "task_id_duplicates": 0,
            "unregistered_fact_writers": 0,
        },
    )


def _evaluate_main_isolation(changed_paths: list[str], allow_external_main_dirty: bool) -> dict[str, Any]:
    overlap = sum(
        path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/")
        for path in changed_paths
    )
    _require(overlap == 0, "MetaDatabase main worktree overlaps x2n")
    _require(allow_external_main_dirty or not changed_paths, "MetaDatabase main worktree is dirty")
    return {
        "external_main_dirty_paths": len(changed_paths),
        "main_worktree_clean": not changed_paths,
        "project_overlap_paths": overlap,
    }


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong foundation worktree branch")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    _git(["cat-file", "-e", f"{BASE_COMMIT}^{{commit}}"])
    base_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_COMMIT, "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    _require(base_is_ancestor.returncode == 0, "foundation branch no longer descends from its recorded base")
    live_origin = _git(["rev-parse", "origin/main"])
    origin_is_linear = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_COMMIT, live_origin],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    _require(origin_is_linear.returncode == 0, "origin/main no longer descends from the foundation base")
    origin_drift_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{BASE_COMMIT}..{live_origin}"]
    ).splitlines()
    origin_project_overlap = sum(
        path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/")
        for path in origin_drift_paths
    )
    _require(origin_project_overlap == 0, "origin/main changed x2n after the foundation cutoff")
    origin_drift_commits = int(_git(["rev-list", "--count", f"{BASE_COMMIT}..{live_origin}"]))

    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None, "MetaDatabase main worktree missing")
    _require(_git(["branch", "--show-current"], main_path) == "main", "main worktree is not on main")
    main_status = _git(
        ["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        main_path,
    )
    isolation = _evaluate_main_isolation(_porcelain_paths(main_status), allow_external_main_dirty)
    return Check(
        "worktree",
        "PASS",
        {
            "branch": BRANCH,
            "origin_drift_commits": origin_drift_commits,
            "origin_project_overlap": origin_project_overlap,
            **isolation,
        },
    )


def validate_task_and_state() -> Check:
    taskpack_text = TASKPACK.read_text(encoding="utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    _require(_field(task, "status") == "completed", "foundation Task is not completed")
    _require(_field(task, "phase") == "PH.X2N.1.1" and _field(task, "stage") == "STG.X2N.1", "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.discovery.002", "TSK.x2n.discovery.005"],
        "Task dependency drifted",
    )
    _require(_list_field(task, "acceptance_ids") == ["ACC.x2n.gov.001", "ACC.x2n.rel.008"], "Task Acceptance drifted")
    _require("  status: STAGE_1_FOUNDATION_002_COMPLETE_G1_NOT_RUN\n" in taskpack_text, "Taskpack status drifted")

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.4", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.1" and state.get("last_completed_phase") == "PH.X2N.1.2", "current Stage state drifted")
    _require(state.get("run_id") == "RUN-X2N-S01-F002" and state.get("run_kind") == "single_dag_task", "current Run identity drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "foundation Task state is not pass")
    _require(state.get("tasks", {}).get("TSK.x2n.foundation.002") == "pass", "foundation.002 Task state is not pass")
    _require(state.get("next_phase") == "PH.X2N.1.3" and state.get("next_run") == "TSK.x2n.foundation.003", "next Task routing drifted")
    _require(state.get("next_phase_authorized") is True, "next Task authorization missing")
    _require(state.get("current_stage_gate") == "not_run" and state.get("current_stage_remote_upload") == "forbidden_until_g1_pass", "G1/upload overstated")
    acceptances = state.get("acceptance_status", {})
    _require(acceptances.get("ACC.x2n.gov.001") == "pass_current_scaffold_scope", "governance Acceptance missing")
    _require(
        acceptances.get("ACC.x2n.rel.008") == "pass_current_scaffold_scope_product_lifecycle_downstream_not_run",
        "Skill Acceptance overstated or missing",
    )

    project = _load_json(PROJECT_FACT)
    _require(project.get("status") == "stage_1_foundation_002_complete_g1_not_run", "project state drifted")
    return Check(
        "task_state",
        "PASS",
        {
            "acceptance_scope": "CURRENT_SCAFFOLD_ONLY",
            "next_task": "TSK.x2n.foundation.003",
            "product_lifecycle": "DOWNSTREAM_NOT_RUN",
            "task": TASK_ID,
        },
    )


def _iter_files() -> Iterable[Path]:
    ignored = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "dist", "build"}
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        yield path


def validate_scaffold_tree() -> Check:
    missing = [relative for relative in EXPECTED_OUTPUTS if not (PROJECT_ROOT / relative).exists()]
    _require(not missing, "declared scaffold output missing")
    required_files = (
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "uv.lock",
        "apps/extension/package.json",
        "apps/extension/manifest.json",
        "apps/extension/src/scaffold.ts",
        "apps/companion/pyproject.toml",
        "apps/companion/src/x2n_companion/scaffold.py",
        "packages/contracts/package.json",
        "packages/contracts/README.md",
        "packages/test-fixtures/scaffold_case.json",
    )
    _require(all((PROJECT_ROOT / relative).is_file() for relative in required_files), "minimal source tree is incomplete")

    forbidden_names = {"node_modules", "dist", "build", ".venv", "runtime", "downloads"}
    forbidden_directories = [path for path in PROJECT_ROOT.rglob("*") if path.is_dir() and path.name in forbidden_names]
    _require(not forbidden_directories, "build output or Runtime entered the repository")
    _require(not (PROJECT_ROOT / ".x2n-root.json").exists(), "private Runtime marker entered Git")

    manifest = _load_json(PROJECT_ROOT / "apps/extension/manifest.json")
    _require(manifest.get("manifest_version") == 3 and manifest.get("permissions") == [], "extension scaffold is not permission-free")
    _require("host_permissions" not in manifest and "background" not in manifest and "side_panel" not in manifest, "browser behavior entered foundation.001")

    fixture = _load_json(PROJECT_ROOT / "packages/test-fixtures/scaffold_case.json")
    _require(
        fixture.get("synthetic_only") is True
        and fixture.get("real_account") is False
        and fixture.get("contains_credentials") is False
        and fixture.get("contains_media_urls") is False
        and fixture.get("contains_private_content") is False,
        "public fixture boundary failed",
    )
    fixture_manifest = _load_json(FIXTURE_MANIFEST)
    registered = {item.get("path") for item in fixture_manifest.get("fixtures", [])}
    _require("packages/test-fixtures/scaffold_case.json" in registered, "foundation fixture is unregistered")

    skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    for token in ("DOWNSTREAM_NOT_RUN", "--synthetic", "--dry-run", "--retain-data", "Fail Closed"):
        _require(token in skill, "SKILL lifecycle boundary is incomplete")

    return Check(
        "scaffold_tree",
        "PASS",
        {
            "build_output_directories": 0,
            "declared_outputs": len(EXPECTED_OUTPUTS),
            "extension_permissions": 0,
            "private_runtime_entries": 0,
            "synthetic_fixtures": 1,
        },
    )


def _packages_from_uv_lock(text: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line == "[[package]]":
            if current:
                packages.append(current)
            current = {}
        elif line.startswith("name = "):
            current["name"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("source = "):
            current["source"] = line.split("=", 1)[1].strip()
    if current:
        packages.append(current)
    return packages


def validate_locks() -> Check:
    package = _load_json(PROJECT_ROOT / "package.json")
    lock = _load_json(PROJECT_ROOT / "package-lock.json")
    _require(lock.get("lockfileVersion") == 3 and lock.get("requires") is True, "npm lock format drifted")
    _require(lock.get("name") == package.get("name") and lock.get("version") == package.get("version"), "npm lock root drifted")
    locked_packages = lock.get("packages", {})
    expected_workspace_paths = {"", "apps/extension", "packages/contracts", "packages/test-fixtures"}
    _require(expected_workspace_paths.issubset(locked_packages), "npm workspace lock is incomplete")
    registry_packages = [
        key
        for key, metadata in locked_packages.items()
        if key.startswith("node_modules/") and metadata.get("link") is not True
    ]
    workspace_links = [
        key
        for key, metadata in locked_packages.items()
        if key.startswith("node_modules/") and metadata.get("link") is True
    ]
    registry_names = {path.removeprefix("node_modules/") for path in registry_packages}
    _require(len(registry_names) == 21 and "typescript" in registry_names, "registered npm dependency set drifted")
    _require(all(name == "typescript" or name.startswith("@typescript/typescript-") for name in registry_names), "unexpected npm third-party package entered foundation")
    _require(len(workspace_links) == 3, "npm workspace links are incomplete")
    for path, metadata in locked_packages.items():
        _require("hasInstallScript" not in metadata, f"install script entered npm lock: {path}")

    uv_text = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")
    uv_packages = _packages_from_uv_lock(uv_text)
    names = {item.get("name") for item in uv_packages}
    _require(names == {"annotated-types", "pydantic", "pydantic-core", "typing-extensions", "typing-inspection", "x2n-companion", "x2n-contracts", "x2n-workspace"}, "uv lock contains unexpected packages")
    _require(all("virtual" in item.get("source", "") or "editable" in item.get("source", "") or "registry" in item.get("source", "") for item in uv_packages), "uv lock source is unsupported")
    return Check(
        "package_locks",
        "PASS",
        {
            "install_scripts": 0,
            "npm_lock_version": 3,
            "npm_workspace_links": len(workspace_links),
            "third_party_packages": 26,
            "uv_packages": len(uv_packages),
        },
    )


def _isolated_env(home: Path) -> dict[str, str]:
    path = os.environ.get("PATH", "")
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": path,
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_CACHE_DIR": str(home / "uv-cache"),
    }


def _run_fresh(label: str, command: Sequence[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, f"fresh scaffold step failed: {label}")
    rendered = result.stdout.strip()
    _require("/" + "Users/" not in rendered, f"fresh scaffold step exposed a local path: {label}")
    _require(re.search(r"https?://", rendered) is None, f"fresh scaffold step emitted a URL: {label}")
    return rendered


def validate_fresh_scaffold() -> Check:
    python_312 = sys.executable if sys.version_info >= (3, 12) else shutil.which("python3.12")
    _require(bool(python_312), "Python 3.12 is required for the fresh scaffold test")
    _require(shutil.which("npm") is not None and shutil.which("uv") is not None, "npm and uv are required")

    transcript: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="x2n-foundation-") as temporary:
        temporary_root = Path(temporary)
        fresh = temporary_root / "project"
        shutil.copytree(
            PROJECT_ROOT,
            fresh,
            ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".venv", "dist", "build"),
        )
        home = temporary_root / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home)

        steps: list[tuple[str, Sequence[str]]] = [
            ("npm_frozen_install", ("npm", "ci", "--omit=dev", "--ignore-scripts", "--audit=false", "--fund=false", "--offline")),
            ("uv_lock_check", ("uv", "lock", "--check", "--offline")),
            ("extension_self_test", ("npm", "run", "test:scaffold")),
        ]
        for label, command in steps:
            _run_fresh(label, command, fresh, env)
            transcript.append({"action": label, "status": "PASS"})

        lifecycle = (
            ("install", ("install",)),
            ("self_test", ("self-test",)),
            ("synthetic_canary", ("canary", "--synthetic")),
            ("upgrade_rehearsal", ("upgrade", "--dry-run")),
            ("rollback_rehearsal", ("rollback", "--dry-run")),
            ("diagnose", ("diagnose",)),
            ("uninstall_rehearsal", ("uninstall", "--dry-run", "--retain-data")),
        )
        lifecycle_env = dict(env)
        lifecycle_env["PYTHONPATH"] = "apps/companion/src"
        for label, arguments in lifecycle:
            output = _run_fresh(
                label,
                (str(python_312), "-B", "-m", "x2n_companion.scaffold", *arguments),
                fresh,
                lifecycle_env,
            )
            payload = json.loads(output)
            _require(payload.get("status") == "PASS", f"lifecycle step is not PASS: {label}")
            _require(payload.get("product_lifecycle") == "DOWNSTREAM_NOT_RUN", f"lifecycle was overstated: {label}")
            transcript.append({"action": label, "status": "PASS"})

        failure = subprocess.run(
            (str(python_312), "-B", "-m", "x2n_companion.scaffold", "canary"),
            cwd=fresh,
            env=lifecycle_env,
            check=False,
            capture_output=True,
            text=True,
        )
        _require(failure.returncode == 2, "unauthorized real Canary did not fail closed")
        failure_payload = json.loads(failure.stderr.strip())
        _require(failure_payload.get("status") == "FAIL_CLOSED", "negative lifecycle status drifted")
        _require(bool(failure_payload.get("minimum_decision_question")), "minimum decision question missing")
        transcript.append({"action": "unauthorized_canary_negative", "status": "PASS"})

    return Check(
        "fresh_scaffold",
        "PASS",
        {
            "fresh_environment": True,
            "network_required": False,
            "private_runtime_writes": 0,
            "product_lifecycle": "DOWNSTREAM_NOT_RUN",
            "transcript": transcript,
        },
    )


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "evidence contains a local absolute path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains a URL")
    _require("X2N_DATA_ROOT=" not in rendered, "evidence contains a resolved Runtime assignment")


def run_checks(*, verify_worktree: bool, allow_external_main_dirty: bool) -> list[Check]:
    checks = [
        validate_governance(),
        validate_task_and_state(),
        validate_scaffold_tree(),
        validate_locks(),
        validate_fresh_scaffold(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    _require(all(check.status == "PASS" for check in checks), "a foundation check failed")
    return checks


def write_evidence(checks: list[Check]) -> None:
    payload = {
        "acceptance_ids": ["ACC.x2n.gov.001", "ACC.x2n.rel.008"],
        "acceptance_status": {
            "ACC.x2n.gov.001": "PASS_CURRENT_SCAFFOLD_SCOPE",
            "ACC.x2n.rel.008": "PASS_CURRENT_SCAFFOLD_SCOPE_PRODUCT_LIFECYCLE_DOWNSTREAM_NOT_RUN",
        },
        "checks": [
            {"details": check.details, "name": check.name, "status": check.status}
            for check in checks
        ],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "phase": "PH.X2N.1.1",
        "private_content_included": False,
        "product_lifecycle": "DOWNSTREAM_NOT_RUN",
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
    _require(evidence.get("product_lifecycle") == "DOWNSTREAM_NOT_RUN", "evidence overstated product lifecycle")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check")
    digest = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
    return Check("evidence", "PASS", {"receipt_sha256": digest, "task": TASK_ID})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.foundation.001")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
        )
        if args.write_evidence:
            write_evidence(checks)
        if args.require_evidence:
            checks.append(verify_evidence())
    except (OSError, ValueError, VerificationError) as exc:
        print(json.dumps({"code": "X2N_FOUNDATION_001_FAILED", "status": "FAIL_CLOSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "checks": [{"name": check.name, "status": check.status} for check in checks],
                "product_lifecycle": "DOWNSTREAM_NOT_RUN",
                "stage_gate": "G1_NOT_RUN",
                "status": "PASS",
                "task_id": TASK_ID,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
