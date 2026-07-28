#!/usr/bin/env python3
"""Fail-closed verifier for the Stage 5 Markdown library hardening Task."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.uxops.002"
PHASE = "PH.X2N.5.2"
RUN_ID = "RUN-X2N-S05-U002"
TASK_BASE_COMMIT = "7a75a2f91b8faf12f0181bc8cdcb2dc4ae901c96"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S05_UXOPS_002.md"
MARKDOWN_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/markdown_sink.py"
STORE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py"
SINK_TEST = PROJECT_ROOT / "apps/companion/tests/test_sinks.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_uxops_002_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/sinks/TSK.x2n.uxops.002.json"
PREDECESSOR = PROJECT_ROOT / "scripts/verify_uxops_001.py"

SOURCE_RECEIPT_PATHS = (
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "HANDOFF.md",
    PROJECT_ROOT / "README.md",
    STORE_SOURCE,
    MARKDOWN_SOURCE,
    SINK_TEST,
    RUN_CONTRACT,
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    TASKPACK,
    ARCHITECTURE,
    PROJECT_FACT,
    TASK_STATE,
    ACCEPTANCE_RUNNER,
    PROJECT_ROOT / "scripts/verify_stage_4_review.py",
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
    PROJECT_ROOT / "scripts/verify_multimodal_001.py",
    PROJECT_ROOT / "scripts/verify_multimodal_002.py",
    PROJECT_ROOT / "scripts/verify_multimodal_003.py",
    PROJECT_ROOT / "scripts/verify_multimodal_004.py",
    PROJECT_ROOT / "scripts/verify_multimodal_005.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume_recheck.py",
    PROJECT_ROOT / "scripts/verify_uxops_001.py",
    PROJECT_ROOT / "scripts/verify_uxops_002.py",
    PROJECT_ROOT / "功能清单.md",
    PROJECT_ROOT / "开发记录.md",
)

ALLOWED_CHANGED_EXACT = frozenset(
    {
        "CHANGELOG.md",
        "HANDOFF.md",
        "README.md",
        "apps/companion/src/x2n_companion/canonical_store.py",
        "apps/companion/src/x2n_companion/markdown_sink.py",
        "apps/companion/tests/test_sinks.py",
        "docs/governance/RUN_CONTRACT_S05_UXOPS_002.md",
        "docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "docs/product_design/v0.0.0.1/01_PRD.md",
        "docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
        "evidence/sinks/TSK.x2n.uxops.002.json",
        "machine/facts/architecture_decisions.json",
        "machine/facts/project.json",
        "machine/facts/task_state.json",
        "scripts/run_uxops_002_acceptance.py",
        "scripts/verify_stage_4_review.py",
        "scripts/verify_adapters_010.py",
        "scripts/verify_multimodal_001.py",
        "scripts/verify_multimodal_002.py",
        "scripts/verify_multimodal_003.py",
        "scripts/verify_multimodal_004.py",
        "scripts/verify_multimodal_005.py",
        "scripts/verify_stage_3_review_resume.py",
        "scripts/verify_stage_3_review_resume_recheck.py",
        "scripts/verify_uxops_001.py",
        "scripts/verify_uxops_002.py",
        "功能清单.md",
        "开发记录.md",
    }
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


def _git(arguments: Sequence[str], *, cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError("local Git verification failed")
    return result.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("required JSON fact is invalid") from error
    if not isinstance(payload, dict):
        raise VerificationError("required JSON fact must be an object")
    return payload


def _blob_at(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError("Task002 historical source blob is missing")
    return result.stdout


def _source_receipt(commit: str) -> str:
    digest = hashlib.sha256()
    for path in SOURCE_RECEIPT_PATHS:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(commit, path))
        digest.update(b"\0")
    return digest.hexdigest()


def _task_relative(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def _task_commit() -> str:
    evidence = _load_json(EVIDENCE)
    commit = evidence.get("task_commit")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task002 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "Task002 audit pin does not descend from Task001 evidence",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task002 audit pin",
    )
    return commit


def _safety_scan(paths: Iterable[Path], *, commit: str) -> None:
    forbidden_literals = ("Agent" + "Database", "OpenAI" + "Database", "github" + "_pat_", "Bearer" + " ")
    private_path = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    cdn = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|(?:img|gw|video|vod|pic|media)\.alicdn)",
        flags=re.IGNORECASE,
    )
    for path in paths:
        text = _blob_at(commit, path).decode("utf-8", errors="replace")
        _require(not any(item in text for item in forbidden_literals), "Task002 public boundary violated")
        _require(private_path.search(text) is None, "Task002 local path entered public source")
        _require(cdn.search(text) is None, "Task002 media CDN URL entered public source")


def validate_scope_and_boundary() -> Check:
    commit = _task_commit()
    changed = [item for item in _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..{commit}"]).split("\0") if item]
    relative = [_task_relative(item) for item in changed]
    _require(changed and all(item is not None for item in relative), "Task002 changed scope escaped x2n")
    scoped = sorted(item for item in relative if item is not None)
    _require(all(path in ALLOWED_CHANGED_EXACT for path in scoped), "Task002 changed scope is invalid")
    _safety_scan([PROJECT_ROOT / path for path in scoped if (PROJECT_ROOT / path).is_file()], commit=commit)
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(not any(Path(path).suffix.lower() in forbidden_suffixes for path in scoped), "Task002 runtime artifact entered public source")
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(scoped), "platform_cdn_urls": 0, "runtime_media_files": 0},
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(["branch", "--show-current"])
    _require(branch not in {"", "main"}, "Task002 must run in a non-main worktree")
    remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", remote) is not None,
        "wrong or authenticated persisted origin",
    )
    main_path: Path | None = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((item.removeprefix("worktree ") for item in lines if item.startswith("worktree ")), None)
        if worktree and "branch refs/heads/main" in lines:
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(["branch", "--show-current"], cwd=main_path) == "main", "main unavailable")
    main_paths = _git(
        ["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], cwd=main_path
    ).splitlines()
    project_overlap = sum("xhs-douyin-2notion" in item for item in main_paths)
    _require(project_overlap == 0, "main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "MetaDatabase main worktree is dirty")
    return Check(
        "worktree_isolation",
        "PASS",
        {"branch": branch, "external_main_dirty_paths": len(main_paths), "project_overlap_paths": project_overlap},
    )


def _load_task() -> dict[str, Any]:
    try:
        taskpack = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is unreadable") from error
    tasks = taskpack.get("tasks") if isinstance(taskpack, dict) else None
    matches = [item for item in tasks or [] if isinstance(item, dict) and item.get("id") == TASK_ID]
    _require(len(matches) == 1, "Task002 is missing or duplicated")
    return matches[0]


def validate_task_and_state() -> Check:
    task = _load_task()
    state = _load_json(TASK_STATE)
    _require(
        task.get("status") == "completed"
        and task.get("stage") == "STG.X2N.5"
        and task.get("phase") == PHASE
        and task.get("depends_on") == ["TSK.x2n.skeleton.005", "TSK.x2n.multimodal.005"]
        and task.get("acceptance_ids") == ["ACC.x2n.md.001", "ACC.x2n.md.002"],
        "Task002 contract drifted",
    )
    _require(
        state.get("schema_version") == "1.38"
        and state.get("stage") == "STG.X2N.5"
        and state.get("last_completed_phase") == PHASE
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "single_dag_task_ci_synth_markdown_library_hardening"
        and state.get("tasks", {}).get("TSK.x2n.uxops.001") == "pass"
        and state.get("tasks", {}).get(TASK_ID) == "pass"
        and state.get("next_phase") == "PH.X2N.5.3"
        and state.get("next_run") == "TSK.x2n.uxops.003"
        and state.get("next_phase_authorized") is True
        and state.get("stage_4_review_complete") is True
        and state.get("stage_5_task001_complete") is True
        and state.get("stage_5_task002_complete") is True
        and state.get("stage_5_remote_upload_authorized") is False
        and state.get("public_release_authorized") is False,
        "Task002 state transition is invalid",
    )
    expected = {
        "ACC.x2n.md.001": "pass_ci_synth_six_platform_fixed_path_valid_frontmatter_cdn_zero_atomic_provenance",
        "ACC.x2n.md.002": "pass_ci_synth_ten_thousand_sqlite_rebuild_manifest_match_category_index_links_zero_duplicate_copies",
    }
    _require(all(state.get("acceptance_status", {}).get(key) == value for key, value in expected.items()), "Task002 acceptance state drifted")
    return Check(
        "taskpack_and_state_transition",
        "PASS",
        {"next_task": state["next_run"], "real_runtime": "NOT_RUN", "renderer_version": "1.1.0"},
    )


def validate_code_contract() -> Check:
    markdown = MARKDOWN_SOURCE.read_text(encoding="utf-8")
    store = STORE_SOURCE.read_text(encoding="utf-8")
    tests = SINK_TEST.read_text(encoding="utf-8")
    runner = ACCEPTANCE_RUNNER.read_text(encoding="utf-8")
    required_markdown = (
        'MARKDOWN_SINK_SCHEMA_VERSION = "1.1.0"',
        'MARKDOWN_RENDERER_VERSION = "1.1.0"',
        "class MarkdownLibraryManifest",
        "class MarkdownRebuild",
        "def validate_category_links(self)",
        "def rebuild(",
        "def rebuild_from_canonical(",
        "Markdown rebuild received competing Canonical projections",
    )
    required_store = ("def projection_snapshots(self)", "one SQLite read transaction")
    required_tests = (
        "test_rebuild_is_atomic_per_file_and_repairs_category_index_after_kill",
        "test_ten_thousand_canonical_rebuild_is_deterministic_and_category_only_reclassifies",
        "seed_rebuild_canonical",
    )
    _require(all(token in markdown for token in required_markdown), "Task002 Markdown hardening contract is incomplete")
    _require(all(token in store for token in required_store), "Task002 SQLite snapshot contract is incomplete")
    _require(all(token in tests for token in required_tests), "Task002 Markdown hardening tests are incomplete")
    _require("ACC.x2n.md.002" in runner and "10_000" in runner, "Task002 acceptance runner is incomplete")
    return Check(
        "deterministic_rebuild_link_checker_renderer_contract",
        "PASS",
        {"canonical_copy_paths": 0, "renderer_version": "1.1.0", "snapshot_reads": 1},
    )


def _run_acceptance() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        raise VerificationError("Task002 acceptance runner failed")
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise VerificationError("Task002 acceptance output is invalid") from error
    if not isinstance(payload, dict):
        raise VerificationError("Task002 acceptance output is invalid")
    return payload


def validate_fresh_acceptance() -> Check:
    payload = _run_acceptance()
    statuses = payload.get("acceptance_status", {})
    _require(
        payload.get("task_id") == TASK_ID
        and payload.get("phase") == PHASE
        and payload.get("run_id") == RUN_ID
        and payload.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and payload.get("execution")
        == {
            "network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_markdown_library": "NOT_RUN",
            "runtime_data_writes": 0,
        }
        and payload.get("metrics", {}).get("canonical_content_files") == 10_000
        and payload.get("metrics", {}).get("category_index_links") == 10_000
        and payload.get("metrics", {}).get("duplicate_content_copies") == 0
        and payload.get("metrics", {}).get("renderer_version") == "1.1.0"
        and payload.get("metrics", {}).get("second_rebuild_writes") == 0
        and payload.get("metrics", {}).get("synthetic_unit_tests", 0) >= 7
        and payload.get("policy")
        == {
            "canonical_path": "platform_content_id_only",
            "category_indexes": "GENERATED_LINKS_NOT_SECOND_SOURCE",
            "projection_source": "SINGLE_SQLITE_READ_TRANSACTION",
            "rebuild": "DERIVED_ONLY_NO_CANONICAL_OR_OUTBOX_MUTATION",
        }
        and set(statuses) == {"ACC.x2n.md.001", "ACC.x2n.md.002"}
        and all(isinstance(value, str) and value.startswith("PASS_CI_SYNTH_") for value in statuses.values()),
        "Task002 fresh acceptance drifted",
    )
    return Check(
        "fresh_ci_synth_markdown_acceptance",
        "PASS",
        {"canonical_content_files": 10_000, "synthetic_unit_tests": payload["metrics"]["synthetic_unit_tests"]},
    )


def validate_predecessor(allow_external_main_dirty: bool) -> Check:
    _ = allow_external_main_dirty
    result = subprocess.run(
        [sys.executable, "-B", str(PREDECESSOR), "--verify-worktree", "--require-evidence"],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=480,
    )
    _require(result.returncode == 0 and '"status": "PASS"' in result.stdout, "Task001 predecessor verification failed")
    return Check("task001_predecessor", "PASS", {"notion_real_calls": 0, "task001": "PASS_CI_SYNTH"})


def validate_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    commit = _task_commit()
    _require(
        evidence.get("task_id") == TASK_ID
        and evidence.get("phase") == PHASE
        and evidence.get("run_id") == RUN_ID
        and evidence.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN"
        and evidence.get("task_source_receipt_sha256") == _source_receipt(commit)
        and evidence.get("execution")
        == {
            "network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "real_markdown_library": "NOT_RUN",
            "runtime_data_writes": 0,
        }
        and evidence.get("metrics", {}).get("canonical_content_files") == 10_000
        and evidence.get("metrics", {}).get("category_index_links") == 10_000
        and evidence.get("metrics", {}).get("duplicate_content_copies") == 0
        and evidence.get("metrics", {}).get("second_rebuild_writes") == 0,
        "Task002 evidence receipt drifted",
    )
    return Check("immutable_task_evidence", "PASS", {"task_commit": commit, "canonical_content_files": 10_000})


def run_checks(
    *,
    verify_worktree: bool,
    allow_external_main_dirty: bool,
    run_acceptance: bool,
    require_evidence: bool,
) -> list[Check]:
    checks = [validate_task_and_state(), validate_code_contract()]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.extend((validate_scope_and_boundary(), validate_predecessor(allow_external_main_dirty), validate_evidence()))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--print-source-receipt", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.print_source_receipt:
            commit = _git(["rev-parse", "HEAD"])
            print(
                json.dumps(
                    {"task_commit": commit, "task_source_receipt_sha256": _source_receipt(commit)},
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
            return 0
        checks = run_checks(
            verify_worktree=arguments.verify_worktree,
            allow_external_main_dirty=arguments.allow_external_main_dirty,
            run_acceptance=arguments.run_acceptance,
            require_evidence=arguments.require_evidence,
        )
    except (OSError, RuntimeError, VerificationError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(error), "task_id": TASK_ID}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {"checks": [item.__dict__ for item in checks], "status": "PASS", "task_id": TASK_ID},
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
