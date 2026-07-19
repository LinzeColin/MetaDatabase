#!/usr/bin/env python3
"""Fail-closed verifier for x2n Stage 0 / Phase 0.1.

The verifier deliberately distinguishes a Phase 0.1 policy/baseline pass from
later DB, media, Markdown, Notion, build, release and owner-account acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE_DOC = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
PATH_CONTRACT = PROJECT_ROOT / "machine/facts/path_contract.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
SOURCE_MANIFEST = PROJECT_ROOT / "machine/source/source_manifest.json"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_0/phase_0_1"

PHASE_TASKS = (
    "TSK.x2n.discovery.001",
    "TSK.x2n.discovery.002",
    "TSK.x2n.discovery.003",
)
PHASE_ACCEPTANCES = (
    "ACC.x2n.gov.001",
    "ACC.x2n.gov.002",
    "ACC.x2n.media.001",
    "ACC.x2n.ops.002",
)

EXPECTED_ROADMAP_SHA256 = "66f949b2109ffe2701d7b74099430e862f4027bb4a429c56e84e13716c0bc906"
EXPECTED_TASKPACK_ZIP_SHA256 = "b32993f465888d9352d745b353c3b923c38406c941a8f357ddf1a64e2bba5a58"


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_files() -> Iterable[Path]:
    ignored_parts = {"__pycache__", ".pytest_cache"}
    suffixes = {"", ".md", ".json", ".yaml", ".yml", ".py", ".txt", ".toml"}
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored_parts for part in path.parts):
            continue
        if path.suffix.lower() in suffixes or path.name in {"VERSION", ".gitignore"}:
            yield path


def validate_taskpack() -> Check:
    with TASKPACK.open("r", encoding="utf-8") as handle:
        taskpack = yaml.safe_load(handle)

    project = taskpack.get("project", {})
    _require(project.get("name") == "xiaohongshu-douyin-2notion", "wrong project name")
    _require(project.get("version") == "v0.0.0.1", "wrong product-design version")
    _require(project.get("repository") == "https://github.com/LinzeColin/MetaDatabase", "wrong parent repository")
    _require(project.get("skill_path") == "xiaohongshu-douyin-2notion/", "wrong project path")
    _require(project.get("data_root_ref") == "X2N_DATA_ROOT", "runtime root contract missing")
    _require(project.get("downloads_root_ref") == "X2N_DATA_ROOT", "download root is not unified")

    execution = taskpack.get("execution_policy", {})
    _require(execution.get("single_phase_focus") is True, "single-phase run policy missing")
    _require(execution.get("max_phases_per_run") == 1, "run may exceed one phase")
    _require(execution.get("intermediate_phase_push") == "forbidden", "intermediate push is not forbidden")
    _require(execution.get("default_git_allowed_paths") == ["xiaohongshu-douyin-2notion/**"], "default changed scope is ambiguous")
    _require(execution.get("external_writes_require_explicit_run_contract") is True, "external writes are not gated")
    _require(execution.get("missing_or_ambiguous_scope") == "fail_closed", "ambiguous scope is not fail-closed")
    _require(
        execution.get("stage_0_runnable_phase_sequence")
        == ["PH.X2N.0.1", "PH.X2N.0.2", "PH.X2N.0.5"],
        "Stage 0 runnable phase sequence is ambiguous",
    )
    _require(
        execution.get("stage_0_non_executable_preparation_lanes") == ["PH.X2N.0.3", "PH.X2N.0.4"],
        "Stage 0 preparation lanes are ambiguous",
    )

    stages = taskpack.get("stages", [])
    expected_stages = [f"STG.X2N.{index}" for index in range(7)]
    stage_ids = [stage.get("id") for stage in stages]
    _require(stage_ids == expected_stages, f"expected Stage 0-6, got {stage_ids}")

    tasks = taskpack.get("tasks", [])
    _require(len(tasks) == 35, f"expected 35 tasks, got {len(tasks)}")
    task_ids = [task.get("id") for task in tasks]
    _require(None not in task_ids, "task without id")
    _require(len(task_ids) == len(set(task_ids)), "duplicate task IDs")
    task_id_set = set(task_ids)
    task_positions = {task_id: index for index, task_id in enumerate(task_ids)}

    requirements = taskpack.get("requirements", [])
    requirement_ids = [requirement.get("id") for requirement in requirements]
    expected_requirements = [f"REQ.X2N.{index:03d}" for index in range(1, 29)]
    _require(requirement_ids == expected_requirements, "requirement registry must contain REQ.X2N.001-028 exactly once")

    acceptance_text = ACCEPTANCE_DOC.read_text(encoding="utf-8")
    acceptance_ids = re.findall(r"^## (ACC\.x2n\.[a-z]+\.\d{3})\b", acceptance_text, flags=re.MULTILINE)
    _require(len(acceptance_ids) == 49, f"expected 49 acceptances, got {len(acceptance_ids)}")
    _require(len(acceptance_ids) == len(set(acceptance_ids)), "duplicate acceptance IDs")
    acceptance_id_set = set(acceptance_ids)

    required_task_fields = {
        "id",
        "title",
        "stage",
        "phase",
        "status",
        "owner",
        "authorization",
        "objective",
        "inputs",
        "outputs",
        "depends_on",
        "acceptance_ids",
        "tests",
        "evidence",
        "risks",
        "rollback",
        "stop_conditions",
        "effort_hours",
        "completion_gate",
    }
    stage_task_counts = {stage_id: 0 for stage_id in stage_ids}
    for task in tasks:
        missing_fields = sorted(required_task_fields - set(task))
        _require(not missing_fields, f"{task.get('id')} missing fields: {missing_fields}")
        _require(task.get("stage") in set(stage_ids), f"unknown stage for {task.get('id')}")
        stage_task_counts[task["stage"]] += 1
        stage_number = task["stage"].rsplit(".", 1)[1]
        _require(task.get("phase", "").startswith(f"PH.X2N.{stage_number}."), f"phase/stage mismatch for {task['id']}")
        effort = task.get("effort_hours", {})
        _require(effort.get("low", 0) <= effort.get("likely", 0) <= effort.get("high", 0), f"invalid effort range for {task['id']}")
        for dependency in task.get("depends_on", []):
            _require(dependency in task_id_set, f"missing dependency {dependency}")
            _require(task_positions[dependency] < task_positions[task["id"]], f"dependency listed after task: {dependency}")
        for acceptance_id in task.get("acceptance_ids", []):
            _require(acceptance_id in acceptance_id_set, f"missing acceptance {acceptance_id}")
    _require(set(stage_task_counts.values()) == {5}, f"each stage must contain five tasks: {stage_task_counts}")

    visiting: set[str] = set()
    visited: set[str] = set()
    dependencies = {task["id"]: task.get("depends_on", []) for task in tasks}

    def visit(task_id: str) -> None:
        _require(task_id not in visiting, f"cycle detected at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)

    phase_tasks = tuple(task["id"] for task in tasks if task.get("phase") == "PH.X2N.0.1")
    _require(phase_tasks == PHASE_TASKS, f"unexpected Phase 0.1 task order: {phase_tasks}")
    _require(set(PHASE_ACCEPTANCES).issubset(acceptance_id_set), "Phase 0.1 acceptance registration incomplete")
    stage_0_phase_map = {
        task["id"]: task["phase"] for task in tasks if task.get("stage") == "STG.X2N.0"
    }
    _require(
        stage_0_phase_map
        == {
            "TSK.x2n.discovery.001": "PH.X2N.0.1",
            "TSK.x2n.discovery.002": "PH.X2N.0.1",
            "TSK.x2n.discovery.003": "PH.X2N.0.1",
            "TSK.x2n.discovery.004": "PH.X2N.0.2",
            "TSK.x2n.discovery.005": "PH.X2N.0.5",
        },
        "Stage 0 task-to-phase mapping drifted",
    )
    roadmap_text = (PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md").read_text(encoding="utf-8")
    phase_0_2_text = roadmap_text.split("## Phase 0.2", 1)[1].split("## Phase 0.3", 1)[0]
    phase_0_5_text = roadmap_text.split("## Phase 0.5", 1)[1].split("### Gate G0", 1)[0]
    _require("TSK.x2n.discovery.004" in phase_0_2_text and "TSK.x2n.discovery.005" not in phase_0_2_text, "Roadmap Phase 0.2 task mapping conflicts with DAG")
    _require("TSK.x2n.discovery.005" in phase_0_5_text, "Roadmap Phase 0.5 task missing")
    _require(roadmap_text.count("非独立准备域") == 2, "Roadmap Phase 0.3/0.4 preparation semantics missing")

    effort_policy = taskpack.get("effort_rollup_policy", {})
    stage_low = sum(stage.get("effort_hours", {}).get("low", 0) for stage in stages)
    stage_high = sum(stage.get("effort_hours", {}).get("high", 0) for stage in stages)
    task_low = sum(task.get("effort_hours", {}).get("low", 0) for task in tasks)
    task_likely = sum(task.get("effort_hours", {}).get("likely", 0) for task in tasks)
    task_high = sum(task.get("effort_hours", {}).get("high", 0) for task in tasks)
    _require(effort_policy.get("stage_envelope_total") == {"low": stage_low, "high": stage_high}, "stage effort envelope is ambiguous")
    _require(
        effort_policy.get("task_arithmetic_total")
        == {"low": task_low, "likely": task_likely, "isolated_high": task_high},
        "task effort arithmetic is ambiguous",
    )
    _require(effort_policy.get("acceptance_gate") is False, "effort estimate must not become acceptance")

    return Check(
        "taskpack_structure",
        "PASS",
        {
            "stages": len(stages),
            "tasks": len(tasks),
            "acceptances": len(acceptance_ids),
            "requirements": len(requirement_ids),
            "cycles": 0,
            "stage_effort_envelope": [stage_low, stage_high],
            "task_likely_total": task_likely,
        },
    )


def validate_registration() -> Check:
    required = (
        "AGENTS.md",
        "README.md",
        "VERSION",
        "PURSUING_GOAL.md",
        "HANDOFF.md",
        "功能清单.md",
        "开发记录.md",
        "模型参数文件.md",
        "docs/governance/BASELINE_INVENTORY.md",
        "docs/governance/RUN_CONTRACT_S00_P01.md",
        "docs/governance/ARTIFACT_RUNTIME_POLICY.md",
        "docs/governance/CHANGE_EVENT_S00_P01.md",
        "docs/governance/READINESS_MATRIX.md",
        "machine/facts/project.json",
        "machine/facts/path_contract.json",
        "machine/facts/task_state.json",
        "machine/facts/id_registry.json",
        "machine/policy/artifact_allowlist.json",
        "machine/policy/synthetic_fixture_manifest.json",
        "machine/source/source_manifest.json",
    )
    missing = [relative for relative in required if not (PROJECT_ROOT / relative).is_file()]
    _require(not missing, f"missing registration files: {missing}")

    project = _load_json(PROJECT_FACT)
    _require(project.get("parent_repository") == "LinzeColin/MetaDatabase", "project fact parent mismatch")
    _require(project.get("project_path") == "xiaohongshu-douyin-2notion/", "project fact path mismatch")
    _require(project.get("stage_min") == 0 and project.get("stage_max") == 6, "project stage range mismatch")
    _require(project.get("runtime_root_ref") == project.get("downloads_root_ref") == "X2N_DATA_ROOT", "project roots differ")
    _require(project.get("license_policy") == "proprietary_all_rights_reserved", "proprietary policy missing")

    source = _load_json(SOURCE_MANIFEST)
    _require(source.get("roadmap_sha256") == EXPECTED_ROADMAP_SHA256, "roadmap source hash mismatch")
    _require(source.get("taskpack_zip_sha256") == EXPECTED_TASKPACK_ZIP_SHA256, "taskpack source hash mismatch")
    _require(source.get("zip_member_count") == 7, "source member count mismatch")

    repository_root = PROJECT_ROOT.parent
    root_readme = (repository_root / "README.md").read_text(encoding="utf-8")
    project_index_rows = [line for line in root_readme.splitlines() if line.startswith("| xiaohongshu-douyin-2notion |")]
    _require(len(project_index_rows) == 1, "MetaDatabase README project registration must exist exactly once")

    design_root = PROJECT_ROOT / "docs/product_design/v0.0.0.1"
    imported = source.get("imported_documents", [])
    actual_documents = sorted(path.name for path in design_root.iterdir() if path.is_file())
    _require(sorted(imported) == actual_documents and len(imported) == 7, "product-design document set drifted")
    for filename in imported:
        if filename.endswith(".yaml"):
            continue
        text = (design_root / filename).read_text(encoding="utf-8")
        _require(text.startswith("---\n") and "\n---\n" in text[4:], f"front matter missing: {filename}")
        front_matter_text = text.split("---", 2)[1]
        front_matter = yaml.safe_load(front_matter_text)
        _require(front_matter.get("project") == "xiaohongshu-douyin-2notion", f"project drift in {filename}")
        _require(front_matter.get("version") == "v0.0.0.1", f"version drift in {filename}")
        _require(front_matter.get("owner_change_event") == "CE-X2N-20260719-S00-P01", f"change event missing in {filename}")

    return Check(
        "project_registration",
        "PASS",
        {"required_files": len(required), "missing": 0, "product_design_documents": len(imported), "root_project_index_rows": 1},
    )


def validate_repository_boundary() -> Check:
    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "Codex" + "Project",
        "LinzeColin/" + "xiaohongshu-douyin-2notion",
        "Library/Application " + "Support/xiaohongshu-douyin-2notion",
        "/Users" + "/",
    )
    hits: list[str] = []
    scanned = 0
    for path in _text_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in forbidden_tokens:
            if token in text:
                hits.append(f"{path.relative_to(PROJECT_ROOT)}:{token}")
    _require(not hits, f"forbidden route/path tokens found: {hits}")

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
    private_files = [
        str(path.relative_to(PROJECT_ROOT))
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_suffixes
    ]
    _require(not private_files, f"private/runtime file types in repository: {private_files}")
    _require(not (PROJECT_ROOT / ".x2n-root.json").exists(), "private root marker entered repository")
    _require(not (PROJECT_ROOT / "runtime").exists(), "runtime directory entered repository")
    _require(not (PROJECT_ROOT / "downloads").exists(), "downloads directory entered repository")

    secret_patterns = (
        re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
        re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{16,}|(?:ntn|secret)_[A-Za-z0-9_-]{16,})"),
        re.compile(r"(?:sessionid|cookie)\s*[:=]\s*['\"][^'\"]{12,}['\"]", flags=re.IGNORECASE),
    )
    cdn_pattern = re.compile(
        r"https?://[^\s'\"]*(?:xhs" + r"cdn|douyin" + r"vod|byte" + r"img|pstatp|sns-video)[^\s'\"]*",
        flags=re.IGNORECASE,
    )
    secret_hits: list[str] = []
    cdn_hits: list[str] = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in secret_patterns):
            secret_hits.append(str(path.relative_to(PROJECT_ROOT)))
        if cdn_pattern.search(text):
            cdn_hits.append(str(path.relative_to(PROJECT_ROOT)))
    _require(not secret_hits, f"credential-shaped values found: {secret_hits}")
    _require(not cdn_hits, f"platform CDN URLs found: {cdn_hits}")

    return Check(
        "repository_boundary",
        "PASS",
        {
            "text_files_scanned": scanned,
            "forbidden_token_hits": 0,
            "private_file_hits": 0,
            "credential_pattern_hits": 0,
            "platform_cdn_url_hits": 0,
        },
    )


def validate_path_contract() -> Check:
    contract = _load_json(PATH_CONTRACT)
    _require(contract.get("root_ref") == "X2N_DATA_ROOT", "wrong root reference")
    _require(contract.get("required_basename") == "xiaohongshu-douyin-2notion", "wrong root basename")
    _require(contract.get("owner_resolution_method") == "home_downloads_required_basename", "owner root resolution is ambiguous")
    _require(contract.get("must_be_outside_git") is True, "root may enter Git")
    _require(contract.get("runtime_and_downloads_share_root") is True, "runtime/download roots differ")
    _require(contract.get("root_mode") == "0700", "root mode contract mismatch")
    _require(contract.get("marker_mode") == "0600", "marker mode contract mismatch")
    directories = contract.get("required_directories", [])
    _require(len(directories) == len(set(directories)) and directories, "invalid required directory list")
    for relative in directories:
        candidate = Path(relative)
        _require(not candidate.is_absolute() and ".." not in candidate.parts, f"unsafe relative path {relative}")
    return Check("path_contract", "PASS", {"required_directories": len(directories), "shared_root": True})


def _tmutil_excluded(path: Path) -> bool:
    result = subprocess.run(
        ["tmutil", "isexcluded", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    _require(result.returncode == 0, f"tmutil isexcluded failed for {path.name}")
    return "[Excluded]" in result.stdout


def validate_local_root(root: Path) -> Check:
    root = root.expanduser().resolve()
    _require(root.name == "xiaohongshu-douyin-2notion", "private root basename mismatch")
    expected_owner_root = (Path.home() / "Downloads" / "xiaohongshu-douyin-2notion").resolve()
    _require(root == expected_owner_root, "private root is not the owner-approved Downloads location")
    _require(root.is_dir(), "private root missing")
    _require(not root.is_symlink(), "private root must not be a symlink")
    _require(PROJECT_ROOT.resolve() not in root.parents and root not in PROJECT_ROOT.resolve().parents, "private root overlaps Git")
    _require(stat.S_IMODE(root.stat().st_mode) == 0o700, "private root mode must be 0700")

    contract = _load_json(PATH_CONTRACT)
    marker = root / contract["private_marker"]
    _require(marker.is_file() and not marker.is_symlink(), "private marker missing or symlinked")
    _require(stat.S_IMODE(marker.stat().st_mode) == 0o600, "private marker mode must be 0600")
    marker_data = _load_json(marker)
    _require(marker_data.get("project") == "xiaohongshu-douyin-2notion", "private marker project mismatch")
    _require(marker_data.get("root_ref") == "X2N_DATA_ROOT", "private marker root ref mismatch")
    _require(Path(marker_data.get("resolved_root", "")).resolve() == root, "private marker resolved root mismatch")
    _require(marker_data.get("real_data_state") == "empty_pre_stage_00", "unexpected private data state")
    _require(marker_data.get("legacy_import") is False, "legacy import must be false")

    for relative in contract["required_directories"]:
        directory = root / relative
        _require(directory.is_dir() and not directory.is_symlink(), f"missing or symlinked directory: {relative}")
        _require(stat.S_IMODE(directory.stat().st_mode) == 0o700, f"directory mode must be 0700: {relative}")

    all_directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in all_directories:
        _require(not directory.is_symlink(), f"symlinked directory forbidden: {directory.name}")
        _require(stat.S_IMODE(directory.stat().st_mode) == 0o700, f"all private directories must be 0700: {directory.name}")

    allowed_system_files = set(contract.get("allowed_system_files", []))
    allowed_top_level = {"downloads", "runtime", contract["private_marker"], *allowed_system_files}
    unexpected = sorted(path.name for path in root.iterdir() if path.name not in allowed_top_level)
    _require(not unexpected, f"unexpected private-root entries: {unexpected}")

    allowed_files = {contract["private_marker"], *allowed_system_files}
    unexpected_files = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name not in allowed_files]
    _require(not unexpected_files, f"private root is not empty pre Stage 00: {unexpected_files}")
    system_mode = int(contract.get("system_file_mode", "0600"), 8)
    system_max_bytes = int(contract.get("system_file_max_bytes", 65536))
    present_system_files = []
    for filename in allowed_system_files:
        system_file = root / filename
        if not system_file.exists():
            continue
        _require(system_file.is_file() and not system_file.is_symlink(), f"invalid system file: {filename}")
        _require(stat.S_IMODE(system_file.stat().st_mode) == system_mode, f"system file must be owner-only: {filename}")
        _require(system_file.stat().st_size <= system_max_bytes, f"system file exceeds size cap: {filename}")
        present_system_files.append(filename)

    excluded = contract["time_machine_excluded"]
    for relative in excluded:
        _require(_tmutil_excluded(root / relative), f"Time Machine exclusion missing: {relative}")
    included = contract["time_machine_included"]
    for relative in included:
        _require(not _tmutil_excluded(root / relative), f"recovery data unexpectedly excluded: {relative}")

    _require((root / ".metadata_never_index").is_file(), "Spotlight exclusion marker missing")
    return Check(
        "private_local_root",
        "PASS",
        {
            "root_ref": "X2N_DATA_ROOT",
            "basename": root.name,
            "root_mode": "0700",
            "marker_mode": "0600",
            "required_directories": len(contract["required_directories"]),
            "time_machine_exclusions": len(excluded),
            "directories_checked": len(all_directories),
            "system_metadata_files": len(present_system_files),
            "real_data_files": 0,
        },
    )


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, f"git command failed: {' '.join(args)}")
    return result.stdout.rstrip()


def validate_worktree_scope() -> Check:
    repo_root = Path(_run_git(["rev-parse", "--show-toplevel"], PROJECT_ROOT)).resolve()
    _require(PROJECT_ROOT.parent == repo_root, "project is not a direct MetaDatabase child")
    branch = _run_git(["branch", "--show-current"], repo_root)
    _require(
        re.fullmatch(r"codex/xiaohongshu-douyin-2notion-v0001-s00-p(?:01|02|05)", branch) is not None,
        "wrong Stage 0 worktree branch",
    )
    remote = _run_git(["remote", "get-url", "origin"], repo_root)
    _require("LinzeColin/MetaDatabase" in remote, "wrong Git remote")

    status_lines = _run_git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], repo_root).splitlines()
    changed_paths: list[str] = []
    for line in status_lines:
        if not line:
            continue
        path_value = line[3:]
        if " -> " in path_value:
            path_value = path_value.split(" -> ", 1)[1]
        changed_paths.append(path_value)
    _require(
        all(
            path == "README.md"
            or path == "xiaohongshu-douyin-2notion"
            or path.startswith("xiaohongshu-douyin-2notion/")
            for path in changed_paths
        ),
        f"changed scope escaped project: {changed_paths}",
    )

    blocks = _run_git(["worktree", "list", "--porcelain"], repo_root).split("\n\n")
    main_worktree: Optional[Path] = None
    for block in blocks:
        fields = block.splitlines()
        worktree_line = next((line for line in fields if line.startswith("worktree ")), None)
        branch_line = next((line for line in fields if line.startswith("branch ")), None)
        if worktree_line and branch_line == "branch refs/heads/main":
            main_worktree = Path(worktree_line.removeprefix("worktree "))
            break
    _require(main_worktree is not None, "main worktree not found")
    _require(_run_git(["status", "--porcelain=v1"], main_worktree) == "", "MetaDatabase main worktree is dirty")
    return Check(
        "worktree_scope",
        "PASS",
        {"branch": branch, "changed_paths": len(changed_paths), "main_worktree_clean": True, "remote": "LinzeColin/MetaDatabase"},
    )


def validate_original_sources(roadmap: Path, taskpack_zip: Path) -> Check:
    _require(roadmap.is_file(), "original roadmap missing")
    _require(taskpack_zip.is_file(), "original taskpack ZIP missing")
    roadmap_hash = _sha256(roadmap)
    taskpack_hash = _sha256(taskpack_zip)
    _require(roadmap_hash == EXPECTED_ROADMAP_SHA256, "original roadmap hash changed")
    _require(taskpack_hash == EXPECTED_TASKPACK_ZIP_SHA256, "original taskpack ZIP hash changed")
    return Check("original_sources", "PASS", {"roadmap_sha256": roadmap_hash, "taskpack_zip_sha256": taskpack_hash})


def run_core_checks() -> list[Check]:
    return [
        validate_taskpack(),
        validate_registration(),
        validate_repository_boundary(),
        validate_path_contract(),
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(rendered, encoding="utf-8")


def write_evidence(checks: list[Check]) -> None:
    state = _load_json(TASK_STATE)
    _require(state.get("state") == "phase_pass", "task_state must be finalized before evidence")
    _require(all(value == "pass" for value in state.get("tasks", {}).values()), "all Phase tasks must be pass")
    _require(state.get("stage_gate") == "not_run", "Stage gate must remain not_run")
    _require(state.get("remote_upload") == "forbidden_until_stage_gate", "remote upload gate weakened")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source = _load_json(SOURCE_MANIFEST)
    base = {
        "schema_version": "1.0",
        "project": "x2n",
        "stage": "STG.X2N.0",
        "phase": "PH.X2N.0.1",
        "run_id": "RUN-X2N-S00-P01",
        "generated_at": now,
        "phase_status": "PASS",
        "stage_gate": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_STAGE_GATE",
        "real_account_execution": "NOT_RUN",
        "product_code": "NOT_STARTED",
        "source_hashes": {
            "roadmap": source["roadmap_sha256"],
            "taskpack_zip": source["taskpack_zip_sha256"],
        },
    }
    summary = dict(base)
    summary["checks"] = [check.__dict__ for check in checks]
    summary["downstream_acceptance"] = {
        "ACC.x2n.gov.001": "PASS",
        "ACC.x2n.gov.002": "DOWNSTREAM_NOT_RUN",
        "ACC.x2n.media.001": "DOWNSTREAM_NOT_RUN",
        "ACC.x2n.ops.002": "DOWNSTREAM_NOT_RUN",
    }
    _write_json(EVIDENCE_DIR / "verification.json", summary)

    task_acceptances = {
        PHASE_TASKS[0]: ["ACC.x2n.gov.001", "ACC.x2n.gov.002"],
        PHASE_TASKS[1]: ["ACC.x2n.gov.001"],
        PHASE_TASKS[2]: ["ACC.x2n.gov.002", "ACC.x2n.media.001", "ACC.x2n.ops.002"],
    }
    for task_id, acceptance_ids in task_acceptances.items():
        receipt = dict(base)
        receipt.update(
            {
                "task_id": task_id,
                "task_status": "PASS",
                "acceptance_ids": acceptance_ids,
                "acceptance_scope": "phase_0_1_governance_baseline",
                "downstream_release_scopes": "NOT_RUN",
            }
        )
        _write_json(EVIDENCE_DIR / f"{task_id}.json", receipt)

    acceptance_statuses = {
        "ACC.x2n.gov.001": ("PASS", "phase_0_1_complete"),
        "ACC.x2n.gov.002": ("DOWNSTREAM_NOT_RUN", "repo_and_empty_root_baseline_only"),
        "ACC.x2n.media.001": ("DOWNSTREAM_NOT_RUN", "no_media_pipeline_exists"),
        "ACC.x2n.ops.002": ("DOWNSTREAM_NOT_RUN", "no_product_logs_or_diagnostics_exist"),
    }
    for acceptance_id, (status_value, reason) in acceptance_statuses.items():
        receipt = dict(base)
        receipt.update({"acceptance_id": acceptance_id, "status": status_value, "reason": reason})
        _write_json(EVIDENCE_DIR / f"{acceptance_id}.json", receipt)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-local-root", action="store_true")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--source-roadmap", type=Path)
    parser.add_argument("--source-taskpack", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        checks = run_core_checks()
        if args.verify_local_root:
            root_value = os.environ.get("X2N_DATA_ROOT")
            local_root = Path(root_value) if root_value else Path.home() / "Downloads" / "xiaohongshu-douyin-2notion"
            checks.append(validate_local_root(local_root))
        if args.verify_worktree:
            checks.append(validate_worktree_scope())
        if args.source_roadmap or args.source_taskpack:
            _require(bool(args.source_roadmap and args.source_taskpack), "both source paths are required")
            checks.append(validate_original_sources(args.source_roadmap, args.source_taskpack))
        if args.write_evidence:
            _require(args.verify_local_root, "local root verification is required before evidence")
            _require(args.verify_worktree, "worktree scope verification is required before evidence")
            _require(bool(args.source_roadmap and args.source_taskpack), "source verification is required before evidence")
            write_evidence(checks)
        result = {
            "status": "PASS",
            "phase": "PH.X2N.0.1",
            "checks": [check.__dict__ for check in checks],
            "evidence_written": bool(args.write_evidence),
            "stage_gate": "NOT_RUN",
            "next_phase_authorized": False,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (VerificationError, OSError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
