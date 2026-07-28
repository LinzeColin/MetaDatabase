#!/usr/bin/env python3
"""Fail-closed verifier for Stage 5 observability and recovery Task004."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.uxops.004"
PHASE = "PH.X2N.5.4"
RUN_ID = "RUN-X2N-S05-U004"
TASK_BASE_COMMIT = "7f78c3074880d887a683fa9cb2ed8b0477dc414c"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S05_UXOPS_004.md"
TASK003_EVIDENCE = PROJECT_ROOT / "evidence/ui/TSK.x2n.uxops.003.json"
EVIDENCE = PROJECT_ROOT / "evidence/operations/TSK.x2n.uxops.004.json"
OPERATIONS_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/operations.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
WEBUI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/webui.py"
OPERATIONS_TEST = PROJECT_ROOT / "apps/companion/tests/test_operations.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_uxops_004_acceptance.py"
HISTORICAL_REPLAY = PROJECT_ROOT / "scripts/replay_uxops_003_historical.py"

SOURCE_RECEIPT_PATHS = (
    OPERATIONS_SOURCE,
    CLI_SOURCE,
    WEBUI_SOURCE,
    OPERATIONS_TEST,
    RUN_CONTRACT,
    TASKPACK,
    ACCEPTANCE_RUNNER,
    HISTORICAL_REPLAY,
    PROJECT_ROOT / "scripts/verify_uxops_004.py",
)
SOURCE_CHANGED_EXACT = frozenset(
    {
        "apps/companion/src/x2n_companion/operations.py",
        "apps/companion/src/x2n_companion/runtime_cli.py",
        "apps/companion/src/x2n_companion/webui.py",
        "apps/companion/tests/test_operations.py",
        "docs/governance/RUN_CONTRACT_S05_UXOPS_004.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "scripts/replay_uxops_003_historical.py",
        "scripts/run_uxops_004_acceptance.py",
        "scripts/verify_uxops_004.py",
    }
)
CURRENT_ALLOWED_EXACT = SOURCE_CHANGED_EXACT | {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    "docs/product_design/v0.0.0.1/01_PRD.md",
    "docs/product_design/v0.0.0.1/02_ROADMAP.md",
    "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    "evidence/operations/TSK.x2n.uxops.004.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "功能清单.md",
    "开发记录.md",
}


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
        raise VerificationError("required historical source blob is missing")
    return result.stdout


def _task_relative(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def _source_receipt(commit: str) -> str:
    digest = hashlib.sha256()
    for path in SOURCE_RECEIPT_PATHS:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(commit, path))
        digest.update(b"\0")
    return digest.hexdigest()


def _task_commit() -> str:
    evidence = _load_json(EVIDENCE)
    commit = evidence.get("task_commit")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task004 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "Task004 audit pin does not descend from Task003 evidence",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task004 audit pin",
    )
    return commit


def _scan_public_boundary(paths: Iterable[Path], *, commit: str) -> None:
    forbidden_literals = ("Agent" + "Database", "OpenAI" + "Database", "github" + "_pat_", "Bear" + "er ")
    private_path = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    cdn = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|(?:img|gw|video|vod|pic|media)\.alicdn)",
        flags=re.IGNORECASE,
    )
    for path in paths:
        text = _blob_at(commit, path).decode("utf-8", errors="replace")
        _require(not any(item in text for item in forbidden_literals), "Task004 public boundary violated")
        _require(private_path.search(text) is None, "Task004 local path entered public source")
        _require(cdn.search(text) is None, "Task004 media CDN URL entered public source")


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(["branch", "--show-current"])
    _require(branch not in {"", "main"}, "Task004 must run in a non-main worktree")
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


def validate_scope_and_boundary() -> Check:
    commit = _task_commit()
    changed = [item for item in _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..{commit}"]).split("\0") if item]
    scoped = [_task_relative(item) for item in changed]
    _require(changed and all(item is not None for item in scoped), "Task004 changed scope escaped x2n")
    relative = sorted(item for item in scoped if item is not None)
    _require(all(path in SOURCE_CHANGED_EXACT for path in relative), "Task004 source changed scope is invalid")
    _scan_public_boundary([PROJECT_ROOT / path for path in relative], commit=commit)
    suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(not any(Path(path).suffix.lower() in suffixes for path in relative), "Task004 runtime artifact entered public source")
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(relative), "platform_cdn_urls": 0, "runtime_media_files": 0},
    )


def validate_current_scope() -> Check:
    changed = [item for item in _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..HEAD"]).split("\0") if item]
    relative = [_task_relative(item) for item in changed]
    _require(changed and all(item is not None for item in relative), "Task004 current scope escaped x2n")
    scoped = sorted(item for item in relative if item is not None)
    _require(all(path in CURRENT_ALLOWED_EXACT for path in scoped), "Task004 current evidence scope is invalid")
    return Check("current_scope", "PASS", {"changed_files": len(scoped)})


def validate_predecessor() -> Check:
    _require(TASK003_EVIDENCE.read_bytes() == _blob_at(TASK_BASE_COMMIT, TASK003_EVIDENCE), "Task003 evidence was rewritten")
    receipt = _load_json(TASK003_EVIDENCE)
    _require(receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task003 receipt is invalid")
    _require(receipt.get("task_id") == "TSK.x2n.uxops.003", "Task003 receipt identity is invalid")
    return Check(
        "immutable_task003_predecessor",
        "PASS",
        {"task003_evidence_unchanged": True, "task003_final_commit": TASK_BASE_COMMIT},
    )


def validate_taskpack_and_state() -> Check:
    try:
        taskpack = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is invalid") from error
    tasks = taskpack.get("tasks") if isinstance(taskpack, dict) else None
    _require(isinstance(tasks, list), "Taskpack task list is invalid")
    task = next((item for item in tasks if isinstance(item, dict) and item.get("id") == TASK_ID), None)
    _require(isinstance(task, dict), "Task004 is absent from Taskpack")
    _require(task.get("phase") == PHASE and task.get("status") == "complete_ci_synth", "Task004 Taskpack state is invalid")
    state = _load_json(TASK_STATE)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    _require(state.get("phase") == PHASE and state.get("next_task") == "TSK.x2n.uxops.005", "Task004 state transition is invalid")
    _require(state.get("stage_5_task004_complete") is True, "Task004 completion fact is missing")
    _require(
        project.get("status") == "stage_5_task004_operations_ci_synth_pass_task005_next_real_runtime_not_run",
        "project fact does not record Task004 boundary",
    )
    _require(architecture.get("phase") == PHASE, "architecture fact does not record Task004")
    return Check(
        "taskpack_and_state_transition",
        "PASS",
        {"next_task": state.get("next_task"), "real_runtime": "NOT_RUN", "release_track": "direct_mvp_no_soak"},
    )


def validate_operations_surface() -> Check:
    source = OPERATIONS_SOURCE.read_text(encoding="utf-8")
    cli = CLI_SOURCE.read_text(encoding="utf-8")
    webui = WEBUI_SOURCE.read_text(encoding="utf-8")
    tests = OPERATIONS_TEST.read_text(encoding="utf-8")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    for token in (
        "DiagnosticJournal",
        "DIAGNOSTIC_COMPONENTS",
        "assert_diagnostic_safe",
        "derived_from_canonical_store_not_persisted",
        "startup_recovery",
        "disabled_not_configured",
        "MarkdownSink",
        "NotionSinkWorker",
    ):
        _require(token in source, "operations implementation surface is incomplete")
    for token in ("operations", "startup-recovery", "RECOVERY_CONFIRMATION"):
        _require(token in cli, "operations CLI confirmation surface is incomplete")
    _require("APPLY_LOCAL_OPERATIONS_RECOVERY" in source, "operations recovery confirmation literal is incomplete")
    _require("OperationsService" in webui and "diagnostic_bundle" in webui, "WebUI diagnostics is not unified")
    for token in (
        "test_redaction_canaries",
        "test_doctor_degraded_cases",
        "test_all_stage_kill",
        "test_startup_recovery",
    ):
        _require(token in tests, "operations test coverage is incomplete")
    _require("Alpha" in contract and "Beta" in contract and "soak" in contract, "direct MVP policy is absent")
    return Check(
        "redaction_metrics_doctor_recovery_and_direct_mvp_surface",
        "PASS",
        {"diagnostic_free_text_fields": 0, "metrics_second_source": False, "notion_default_transport": "NOT_RUN"},
    )


def _isolated_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run_json(command: Sequence[str], *, timeout: int = 360) -> dict[str, Any]:
    result = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=_isolated_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise VerificationError("Task004 synthetic acceptance failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError("Task004 acceptance output is invalid") from error
    if not isinstance(payload, dict):
        raise VerificationError("Task004 acceptance output is invalid")
    return payload


def validate_historical_replay() -> Check:
    payload = _run_json((sys.executable, "-B", "scripts/replay_uxops_003_historical.py"), timeout=360)
    _require(
        payload.get("status") == "PASS"
        and payload.get("historical_commit") == TASK_BASE_COMMIT
        and payload.get("current_task004_tree_evaluated") is False,
        "historical Task003 replay is invalid",
    )
    return Check("pinned_historical_task003_replay", "PASS", payload)


def validate_acceptance() -> Check:
    payload = _run_json((sys.executable, "-B", "scripts/run_uxops_004_acceptance.py"), timeout=420)
    _require(payload.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task004 acceptance state is invalid")
    statuses = payload.get("acceptance_status")
    _require(isinstance(statuses, dict) and set(statuses) == {"ACC.x2n.ops.001", "ACC.x2n.ops.002", "ACC.x2n.ops.004"}, "Task004 acceptance coverage is incomplete")
    execution = payload.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("external_network_calls") == 0
        and execution.get("platform_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN"
        and execution.get("real_notion_calls") == 0,
        "Task004 acceptance crossed the runtime boundary",
    )
    metrics = payload.get("metrics")
    _require(
        isinstance(metrics, dict)
        and metrics.get("all_stage_kill_points") == 10
        and metrics.get("canonical_loss") == 0
        and metrics.get("duplicate_notion_pages") == 0
        and metrics.get("diagnostic_private_content_hits") == 0,
        "Task004 recovery or redaction metric is invalid",
    )
    return Check("operations_chaos_redaction_doctor_rebuild_reconcile_acceptance", "PASS", payload)


def validate_evidence() -> Check:
    commit = _task_commit()
    evidence = _load_json(EVIDENCE)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("phase") == PHASE and evidence.get("run_id") == RUN_ID, "Task004 evidence identity is invalid")
    _require(evidence.get("task_commit") == commit and evidence.get("source_receipt_sha256") == _source_receipt(commit), "Task004 evidence receipt is invalid")
    _require(evidence.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task004 evidence overstates completion")
    execution = evidence.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("external_network_calls") == 0
        and execution.get("platform_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN"
        and execution.get("real_notion_calls") == 0,
        "Task004 evidence crossed the runtime boundary",
    )
    rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered and "Bear" + "er " not in rendered, "Task004 evidence is unsafe")
    _require("https://" not in rendered and "http://" not in rendered, "Task004 evidence contains a URL")
    return Check(
        "immutable_task_evidence",
        "PASS",
        {"source_receipt_sha256": evidence.get("source_receipt_sha256"), "task_commit": commit},
    )


def run_checks(
    *,
    verify_worktree: bool,
    allow_external_main_dirty: bool,
    run_acceptance: bool,
    require_evidence: bool,
) -> list[Check]:
    checks = [
        validate_scope_and_boundary(),
        validate_current_scope(),
        validate_predecessor(),
        validate_taskpack_and_state(),
        validate_operations_surface(),
        validate_historical_replay(),
    ]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_acceptance())
    if require_evidence:
        checks.append(validate_evidence())
    _require(all(item.status == "PASS" for item in checks), "a Task004 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.uxops.004")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_acceptance=args.run_acceptance,
            require_evidence=args.require_evidence,
        )
        print(
            json.dumps(
                {
                    "checks": [{"details": item.details, "name": item.name, "status": item.status} for item in checks],
                    "status": "PASS",
                    "task_id": TASK_ID,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, subprocess.SubprocessError, VerificationError, yaml.YAMLError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
