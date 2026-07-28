#!/usr/bin/env python3
"""Fail-closed verifier for Stage 5 Local WebUI and Owner review Task003."""

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
TASK_ID = "TSK.x2n.uxops.003"
PHASE = "PH.X2N.5.3"
RUN_ID = "RUN-X2N-S05-U003"
TASK_BASE_COMMIT = "ab1839184976cad6a3a128350b8d4c498c452ae7"
LOOPBACK_HOST = "127.0.0.1"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S05_UXOPS_003.md"
TASK002_EVIDENCE = PROJECT_ROOT / "evidence/sinks/TSK.x2n.uxops.002.json"
EVIDENCE = PROJECT_ROOT / "evidence/ui/TSK.x2n.uxops.003.json"
WEBUI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/webui.py"
STORE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
RECONCILIATION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/relation_reconciliation.py"
WEBUI_TEST = PROJECT_ROOT / "apps/companion/tests/test_webui.py"
RECONCILIATION_TEST = PROJECT_ROOT / "apps/companion/tests/test_relation_reconciliation.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_uxops_003_acceptance.py"
HISTORICAL_REPLAY = PROJECT_ROOT / "scripts/replay_adapters_005_historical.py"

SOURCE_RECEIPT_PATHS = (
    STORE_SOURCE,
    RECONCILIATION_SOURCE,
    CLI_SOURCE,
    WEBUI_SOURCE,
    RECONCILIATION_TEST,
    WEBUI_TEST,
    RUN_CONTRACT,
    TASKPACK,
    ACCEPTANCE_RUNNER,
    HISTORICAL_REPLAY,
    PROJECT_ROOT / "scripts/verify_uxops_003.py",
)

SOURCE_CHANGED_EXACT = frozenset(
    {
        "apps/companion/src/x2n_companion/canonical_store.py",
        "apps/companion/src/x2n_companion/relation_reconciliation.py",
        "apps/companion/src/x2n_companion/runtime_cli.py",
        "apps/companion/src/x2n_companion/webui.py",
        "apps/companion/tests/test_relation_reconciliation.py",
        "apps/companion/tests/test_webui.py",
        "docs/governance/RUN_CONTRACT_S05_UXOPS_003.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "scripts/replay_adapters_005_historical.py",
        "scripts/run_uxops_003_acceptance.py",
        "scripts/verify_uxops_003.py",
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
    "evidence/ui/TSK.x2n.uxops.003.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "功能清单.md",
    "开发记录.md",
}

ACTIVE_NOMENCLATURE_PATHS = (
    RECONCILIATION_SOURCE,
    CLI_SOURCE,
    WEBUI_SOURCE,
    RECONCILIATION_TEST,
    WEBUI_TEST,
    EVIDENCE,
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
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task003 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "Task003 audit pin does not descend from Task002 evidence",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task003 audit pin",
    )
    return commit


def _scan_public_boundary(paths: Iterable[Path], *, commit: str) -> None:
    forbidden_literals = ("Agent" + "Database", "OpenAI" + "Database", "github" + "_pat_", "Bearer" + " ")
    private_path = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    cdn = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|(?:img|gw|video|vod|pic|media)\.alicdn)",
        flags=re.IGNORECASE,
    )
    for path in paths:
        text = _blob_at(commit, path).decode("utf-8", errors="replace")
        _require(not any(item in text for item in forbidden_literals), "Task003 public boundary violated")
        _require(private_path.search(text) is None, "Task003 local path entered public source")
        _require(cdn.search(text) is None, "Task003 media CDN URL entered public source")


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(["branch", "--show-current"])
    _require(branch not in {"", "main"}, "Task003 must run in a non-main worktree")
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
    _require(changed and all(item is not None for item in scoped), "Task003 changed scope escaped x2n")
    relative = sorted(item for item in scoped if item is not None)
    _require(all(path in SOURCE_CHANGED_EXACT for path in relative), "Task003 source changed scope is invalid")
    _scan_public_boundary([PROJECT_ROOT / path for path in relative], commit=commit)
    suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(not any(Path(path).suffix.lower() in suffixes for path in relative), "Task003 runtime artifact entered public source")
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(relative), "platform_cdn_urls": 0, "runtime_media_files": 0},
    )


def validate_current_scope() -> Check:
    changed = [item for item in _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..HEAD"]).split("\0") if item]
    relative = [_task_relative(item) for item in changed]
    _require(changed and all(item is not None for item in relative), "Task003 current scope escaped x2n")
    scoped = sorted(item for item in relative if item is not None)
    _require(all(path in CURRENT_ALLOWED_EXACT for path in scoped), "Task003 current evidence scope is invalid")
    return Check("current_scope", "PASS", {"changed_files": len(scoped)})


def validate_predecessor() -> Check:
    _require(TASK002_EVIDENCE.read_bytes() == _blob_at(TASK_BASE_COMMIT, TASK002_EVIDENCE), "Task002 evidence was rewritten")
    receipt = _load_json(TASK002_EVIDENCE)
    _require(receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task002 receipt is invalid")
    _require(receipt.get("task_id") == "TSK.x2n.uxops.002", "Task002 receipt identity is invalid")
    return Check(
        "immutable_task002_predecessor",
        "PASS",
        {"renderer_version": "1.1.0", "task002_evidence_unchanged": True},
    )


def validate_taskpack_and_state() -> Check:
    try:
        taskpack = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is invalid") from error
    tasks = taskpack.get("tasks") if isinstance(taskpack, dict) else None
    _require(isinstance(tasks, list), "Taskpack task list is invalid")
    task = next((item for item in tasks if isinstance(item, dict) and item.get("id") == TASK_ID), None)
    _require(isinstance(task, dict), "Task003 is absent from Taskpack")
    _require(task.get("phase") == PHASE and task.get("status") == "complete_ci_synth", "Task003 Taskpack state is invalid")
    state = _load_json(TASK_STATE)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    _require(state.get("phase") == PHASE and state.get("next_task") == "TSK.x2n.uxops.004", "Task003 state transition is invalid")
    _require(state.get("stage_5_task003_complete") is True, "Task003 completion fact is missing")
    _require(state.get("runtime_nomenclature") == "v2_owner_mvp_plan", "Task003 nomenclature fact is invalid")
    _require(
        project.get("status") == "stage_5_task003_local_webui_ci_synth_pass_task004_next_real_runtime_not_run",
        "project fact does not record Task003 boundary",
    )
    _require(architecture.get("phase") == PHASE, "architecture fact does not record Task003")
    return Check(
        "taskpack_and_state_transition",
        "PASS",
        {"next_task": state.get("next_task"), "real_runtime": "NOT_RUN", "runtime_nomenclature": "v2"},
    )


def validate_webui_security_and_review_surface() -> Check:
    text = WEBUI_SOURCE.read_text(encoding="utf-8")
    test_text = WEBUI_TEST.read_text(encoding="utf-8")
    for token in (
        'LOOPBACK_HOST = "127.0.0.1"',
        "CONTENT_SECURITY_POLICY",
        "hmac.compare_digest",
        "X-X2N-CSRF",
        "Origin",
        "html.escape",
        "textContent",
        "create_local_webui_server",
        "LocalReviewItem",
        "DecisionMode.HUMAN",
        "TaxonomyRegistry",
    ):
        _require(token in text, "Local WebUI security or review surface is incomplete")
    _require("Access-Control-Allow-Origin" not in text and "innerHTML" not in text, "Local WebUI exposes unsafe browser surface")
    for token in ("test_csrf_origin", "test_loopback_ui_e2e", "test_owner_taxonomy_create", "owner-mvp-plan"):
        _require(token in test_text, "Local WebUI test coverage is incomplete")
    return Check(
        "loopback_origin_csrf_xss_and_owner_review_contract",
        "PASS",
        {"cors_headers": 0, "loopback_listener": LOOPBACK_HOST, "taxonomy_ai_mutations": 0},
    )


def validate_active_nomenclature() -> Check:
    legacy_alias = "owner-" + "alpha-plan"
    legacy_key = "owner_" + "alpha"
    legacy_constant = "OWNER_" + "ALPHA"
    for path in ACTIVE_NOMENCLATURE_PATHS:
        text = path.read_text(encoding="utf-8")
        _require(legacy_alias not in text and legacy_key not in text and legacy_constant not in text, "retired v1 name remains active")
    cli_text = CLI_SOURCE.read_text(encoding="utf-8")
    reconciliation_text = RECONCILIATION_SOURCE.read_text(encoding="utf-8")
    _require("owner-mvp-plan" in cli_text and "owner_mvp" in reconciliation_text, "v2 nomenclature is incomplete")
    return Check(
        "active_runtime_nomenclature_v2",
        "PASS",
        {"active_legacy_aliases": 0, "historical_v1_artifacts": "fixed_commit_replay_only"},
    )


def _isolated_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run_json(command: Sequence[str], *, timeout: int = 240) -> dict[str, Any]:
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
        raise VerificationError("Task003 synthetic acceptance failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError("Task003 acceptance output is invalid") from error
    if not isinstance(payload, dict):
        raise VerificationError("Task003 acceptance output is invalid")
    return payload


def validate_historical_replay() -> Check:
    payload = _run_json((sys.executable, "-B", "scripts/replay_adapters_005_historical.py"), timeout=180)
    _require(
        payload.get("status") == "PASS"
        and payload.get("historical_commit") == "a67ba091239297b5c9c38a349e0a839680d1c411"
        and payload.get("current_v2_tree_evaluated") is False,
        "historical adapters.005 replay is invalid",
    )
    return Check("pinned_historical_adapters005_replay", "PASS", payload)


def validate_acceptance() -> Check:
    payload = _run_json((sys.executable, "-B", "scripts/run_uxops_003_acceptance.py"), timeout=300)
    _require(payload.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task003 acceptance state is invalid")
    statuses = payload.get("acceptance_status")
    _require(isinstance(statuses, dict) and len(statuses) == 4, "Task003 acceptance coverage is incomplete")
    execution = payload.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("external_network_calls") == 0
        and execution.get("platform_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN",
        "Task003 acceptance crossed the runtime boundary",
    )
    return Check("ui_e2e_csrf_review_accessibility_and_historical_acceptance", "PASS", payload)


def validate_evidence() -> Check:
    commit = _task_commit()
    evidence = _load_json(EVIDENCE)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("phase") == PHASE and evidence.get("run_id") == RUN_ID, "Task003 evidence identity is invalid")
    _require(evidence.get("task_commit") == commit and evidence.get("source_receipt_sha256") == _source_receipt(commit), "Task003 evidence receipt is invalid")
    _require(evidence.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task003 evidence overstates completion")
    execution = evidence.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("external_network_calls") == 0
        and execution.get("platform_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN"
        and execution.get("real_notion_calls") == 0,
        "Task003 evidence crossed the runtime boundary",
    )
    rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "Task003 evidence is unsafe")
    _require("https://" not in rendered and "http://" not in rendered, "Task003 evidence contains a URL")
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
        validate_webui_security_and_review_surface(),
        validate_active_nomenclature(),
        validate_historical_replay(),
    ]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_acceptance())
    if require_evidence:
        checks.append(validate_evidence())
    _require(all(item.status == "PASS" for item in checks), "a Task003 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.uxops.003")
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
