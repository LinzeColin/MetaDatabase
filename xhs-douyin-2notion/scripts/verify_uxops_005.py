#!/usr/bin/env python3
"""Fail-closed verifier for Stage 5 lifecycle and governed deletion Task005."""

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
TASK_ID = "TSK.x2n.uxops.005"
PHASE = "PH.X2N.5.5"
RUN_ID = "RUN-X2N-S05-U005"
TASK_BASE_COMMIT = "798e2693a8255030c19f17572b55392c2d4f5f07"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
WHERE_IS_PROJECT_DATA = REPOSITORY_ROOT / "WHERE_IS_PROJECT_DATA.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S05_UXOPS_005.md"
TASK004_EVIDENCE = PROJECT_ROOT / "evidence/operations/TSK.x2n.uxops.004.json"
EVIDENCE = PROJECT_ROOT / "evidence/lifecycle/TSK.x2n.uxops.005.json"
LIFECYCLE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/lifecycle.py"
CANONICAL_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py"
MIGRATIONS_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py"
RUNTIME_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
WEBUI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/webui.py"
LIFECYCLE_TEST = PROJECT_ROOT / "apps/companion/tests/test_lifecycle.py"
WEBUI_TEST = PROJECT_ROOT / "apps/companion/tests/test_webui.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_uxops_005_acceptance.py"
HISTORICAL_REPLAY = PROJECT_ROOT / "scripts/replay_uxops_004_historical.py"

SOURCE_RECEIPT_PATHS = (
    CANONICAL_SOURCE,
    LIFECYCLE_SOURCE,
    MIGRATIONS_SOURCE,
    RUNTIME_SOURCE,
    CLI_SOURCE,
    WEBUI_SOURCE,
    LIFECYCLE_TEST,
    WEBUI_TEST,
    RUN_CONTRACT,
    TASKPACK,
    ACCEPTANCE_RUNNER,
    HISTORICAL_REPLAY,
    PROJECT_ROOT / "scripts/verify_uxops_005.py",
)
SOURCE_CHANGED_EXACT = frozenset(
    {
        "apps/companion/src/x2n_companion/canonical_store.py",
        "apps/companion/src/x2n_companion/lifecycle.py",
        "apps/companion/src/x2n_companion/migrations.py",
        "apps/companion/src/x2n_companion/runtime.py",
        "apps/companion/src/x2n_companion/runtime_cli.py",
        "apps/companion/src/x2n_companion/webui.py",
        "apps/companion/tests/test_lifecycle.py",
        "apps/companion/tests/test_webui.py",
        "docs/governance/RUN_CONTRACT_S05_UXOPS_005.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "scripts/replay_uxops_004_historical.py",
        "scripts/run_uxops_005_acceptance.py",
        "scripts/verify_uxops_005.py",
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
    "evidence/lifecycle/TSK.x2n.uxops.005.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "功能清单.md",
    "开发记录.md",
    "__repository_root__/WHERE_IS_PROJECT_DATA.md",
}
ACCEPTANCE_STATUS = {
    "ACC.x2n.data.004": "PASS_CI_SYNTH_DOMAIN_BOUND_ARCHIVE_RESTORE_INTEGRITY_DELETION_EPOCH",
    "ACC.x2n.gov.002": "PASS_CI_SYNTH_PRIVATE_CLIENT_ALLOWLIST_DIGEST_PIN_AUTH_ZERO_CONTACT",
    "ACC.x2n.media.002": "PASS_CI_SYNTH_LOCAL_RUNTIME_TEMPORARY_ARCHIVE_CLEANUP",
    "ACC.x2n.ops.003": "PASS_CI_SYNTH_DELETE_PREVIEW_TOMBSTONE_TTL_TMUTIL_CONTRACT",
}
FACT_ACCEPTANCE_STATUS = {
    "ACC.x2n.data.004": "pass_ci_synth_domain_bound_archive_restore_integrity_deletion_epoch",
    "ACC.x2n.gov.002": "pass_ci_synth_private_client_allowlist_digest_pin_auth_zero_contact",
    "ACC.x2n.media.002": "pass_ci_synth_local_runtime_temporary_archive_cleanup",
    "ACC.x2n.ops.003": "pass_ci_synth_delete_preview_tombstone_ttl_tmutil_contract",
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


def _scope_name(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    if path.startswith(prefix):
        return path.removeprefix(prefix)
    if path == "WHERE_IS_PROJECT_DATA.md":
        return "__repository_root__/WHERE_IS_PROJECT_DATA.md"
    return None


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
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task005 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "Task005 audit pin does not descend from Task004 evidence",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task005 audit pin",
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
        _require(not any(item in text for item in forbidden_literals), "Task005 public boundary violated")
        _require(private_path.search(text) is None, "Task005 local path entered public source")
        _require(cdn.search(text) is None, "Task005 media CDN URL entered public source")


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(["branch", "--show-current"])
    _require(branch not in {"", "main"}, "Task005 must run in a non-main worktree")
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
    scoped = [_scope_name(item) for item in changed]
    _require(changed and all(item is not None for item in scoped), "Task005 changed scope escaped x2n")
    relative = sorted(item for item in scoped if item is not None)
    _require(set(relative) == SOURCE_CHANGED_EXACT, "Task005 source changed scope is invalid")
    _scan_public_boundary([PROJECT_ROOT / path for path in relative], commit=commit)
    suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(not any(Path(path).suffix.lower() in suffixes for path in relative), "Task005 runtime artifact entered public source")
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(relative), "platform_cdn_urls": 0, "runtime_media_files": 0},
    )


def validate_current_scope() -> Check:
    changed = [item for item in _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..HEAD"]).split("\0") if item]
    relative = [_scope_name(item) for item in changed]
    _require(changed and all(item is not None for item in relative), "Task005 current scope escaped allowed paths")
    scoped = sorted(item for item in relative if item is not None)
    _require(all(path in CURRENT_ALLOWED_EXACT for path in scoped), "Task005 current evidence scope is invalid")
    return Check("current_scope", "PASS", {"changed_files": len(scoped)})


def validate_predecessor() -> Check:
    _require(TASK004_EVIDENCE.read_bytes() == _blob_at(TASK_BASE_COMMIT, TASK004_EVIDENCE), "Task004 evidence was rewritten")
    receipt = _load_json(TASK004_EVIDENCE)
    _require(receipt.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task004 receipt is invalid")
    _require(receipt.get("task_id") == "TSK.x2n.uxops.004", "Task004 receipt identity is invalid")
    return Check(
        "immutable_task004_predecessor",
        "PASS",
        {"task004_evidence_unchanged": True, "task004_final_commit": TASK_BASE_COMMIT},
    )


def validate_taskpack() -> Check:
    try:
        taskpack = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is invalid") from error
    tasks = taskpack.get("tasks") if isinstance(taskpack, dict) else None
    _require(isinstance(tasks, list), "Taskpack task list is invalid")
    task = next((item for item in tasks if isinstance(item, dict) and item.get("id") == TASK_ID), None)
    _require(isinstance(task, dict), "Task005 is absent from Taskpack")
    _require(task.get("phase") == PHASE and task.get("status") == "complete_ci_synth", "Task005 Taskpack state is invalid")
    acceptance_ids = task.get("acceptance_ids")
    _require(
        isinstance(acceptance_ids, list)
        and len(acceptance_ids) == len(ACCEPTANCE_STATUS)
        and set(acceptance_ids) == set(ACCEPTANCE_STATUS),
        "Task005 acceptance identity changed",
    )
    return Check("taskpack_completion", "PASS", {"task_status": task.get("status"), "phase": PHASE})


def validate_lifecycle_surface() -> Check:
    lifecycle_source = LIFECYCLE_SOURCE.read_text(encoding="utf-8")
    canonical = CANONICAL_SOURCE.read_text(encoding="utf-8")
    migrations = MIGRATIONS_SOURCE.read_text(encoding="utf-8")
    runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
    cli = CLI_SOURCE.read_text(encoding="utf-8")
    webui = WEBUI_SOURCE.read_text(encoding="utf-8")
    tests = LIFECYCLE_TEST.read_text(encoding="utf-8")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    for token in (
        "PRIVATE_AREA = \"Private-MetaDatabase\"",
        "PRIVATE_DOMAIN = \"xhs-douyin-2notion\"",
        "DigestPinnedPrivateDbClient",
        "ARCHIVE_CHUNK_MAX_BYTES = 90 * 1024 * 1024",
        "RESTORE_MANIFEST_FORMAT",
        "LIFECYCLE_DELETE_CONFIRMATION",
        "TIME_MACHINE_CONFIRMATION",
        "_load_private_manifest",
        "_remove_private_tree",
        "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED",
    ):
        _require(token in lifecycle_source, "lifecycle implementation surface is incomplete")
    _require("{\"ingest\", \"get\", \"list\", \"verify\"}" in lifecycle_source, "client allowlist is incomplete")
    _require("Raw SQLite cannot enter Private-MetaDatabase" in lifecycle_source, "raw SQLite rejection is missing")
    for token in ("lifecycle_state", "lifecycle_tombstone", "deletion_epoch"):
        _require(token in canonical and token in migrations, "Canonical lifecycle state is incomplete")
    _require("restore_archival_snapshot" in canonical, "Canonical archive restore guard is incomplete")
    _require('"runtime/lifecycle"' in runtime, "private lifecycle workspace is not registered")
    for token in ("if args.action == \"lifecycle\"", "runtime-wipe-apply", "time-machine-exclusion", "PRIVATE_EXPORT_CONFIRMATION"):
        _require(token in cli, "lifecycle CLI confirmation surface is incomplete")
    _require("/api/v2/lifecycle" in webui and "CLI_TWO_STEP_EXPLICIT_CONFIRMATION_REQUIRED" in webui, "WebUI lifecycle is unsafe")
    for token in (
        "test_domain_bound_export_verifies",
        "test_missing_exact_domain_object_fails_closed",
        "test_preview_cancel_relation_and_content_tombstones",
        "test_restore_cannot_regress_deletion_epoch",
        "test_ttl_client_rejections_tmutil_contract",
    ):
        _require(token in tests, "lifecycle synthetic coverage is incomplete")
    _require("Alpha" in contract and "Beta" in contract and "soak" in contract, "direct MVP policy is absent")
    return Check(
        "lifecycle_archive_delete_restore_tmutil_direct_mvp_surface",
        "PASS",
        {
            "approved_client_commands": 4,
            "durable_hard_erase": "UNSUPPORTED",
            "private_database_clone": False,
            "real_private_transfer": "NOT_RUN",
        },
    )


def _isolated_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }


def _run_json(command: Sequence[str], *, timeout: int = 480) -> dict[str, Any]:
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
        raise VerificationError("Task005 synthetic acceptance failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise VerificationError("Task005 acceptance output is invalid") from error
    if not isinstance(payload, dict):
        raise VerificationError("Task005 acceptance output is invalid")
    return payload


def validate_historical_replay() -> Check:
    payload = _run_json((sys.executable, "-B", "scripts/replay_uxops_004_historical.py"), timeout=480)
    _require(
        payload.get("status") == "PASS"
        and payload.get("historical_commit") == TASK_BASE_COMMIT
        and payload.get("current_task005_tree_evaluated") is False,
        "historical Task004 replay is invalid",
    )
    return Check("pinned_historical_task004_replay", "PASS", payload)


def validate_acceptance() -> Check:
    payload = _run_json((sys.executable, "-B", "scripts/run_uxops_005_acceptance.py"), timeout=540)
    _require(payload.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task005 acceptance state is invalid")
    statuses = payload.get("acceptance_status")
    _require(statuses == ACCEPTANCE_STATUS, "Task005 acceptance coverage is incomplete")
    execution = payload.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("external_network_calls") == 0
        and execution.get("platform_calls") == 0
        and execution.get("private_database_client_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN"
        and execution.get("real_notion_calls") == 0
        and execution.get("tmutil_calls") == 0
        and execution.get("token_value_contact") == 0,
        "Task005 acceptance crossed the runtime boundary",
    )
    metrics = payload.get("metrics")
    _require(
        isinstance(metrics, dict)
        and metrics.get("archive_chunk_max_bytes") == 94371840
        and metrics.get("durable_hard_erase_claims") == 0
        and metrics.get("foreign_domain_leaks") == 0
        and metrics.get("missing_x2n_object_fail_closed") is True
        and metrics.get("temporary_get_outputs_remaining") == 0
        and metrics.get("tombstone_epoch_regressions_accepted") == 0,
        "Task005 archive or deletion metric is invalid",
    )
    return Check("lifecycle_export_restore_delete_ttl_tmutil_acceptance", "PASS", payload)


def validate_task_state_and_docs() -> Check:
    state = _load_json(TASK_STATE)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    _require(
        state.get("phase") == PHASE
        and state.get("last_completed_phase") == PHASE
        and state.get("next_phase") == "G5"
        and state.get("next_run") == "G5"
        and state.get("stage_5_task005_complete") is True,
        "Task005 state transition is invalid",
    )
    tasks = state.get("tasks")
    _require(isinstance(tasks, dict) and tasks.get(TASK_ID) == "pass", "Task005 task fact is missing")
    accepted = state.get("acceptance_status")
    downstream = state.get("downstream_acceptances")
    _require(isinstance(accepted, dict) and isinstance(downstream, dict), "Task005 acceptance facts are invalid")
    for acceptance, value in FACT_ACCEPTANCE_STATUS.items():
        _require(accepted.get(acceptance) == value and downstream.get(acceptance) == value, "Task005 acceptance fact diverged")
    expected_project = "stage_5_task005_lifecycle_ci_synth_pass_g5_review_next_real_runtime_not_run"
    _require(project.get("status") == expected_project, "project fact does not record Task005 boundary")
    _require(project.get("data_lifecycle") == "ci_synth_verified_private_metadatabase_archive_tombstone_ttl_tmutil_contract_real_runtime_not_run", "project lifecycle fact is invalid")
    _require(architecture.get("phase") == PHASE and architecture.get("status") == expected_project, "architecture fact does not record Task005")
    rendered = WHERE_IS_PROJECT_DATA.read_text(encoding="utf-8")
    _require("| xhs-douyin-2notion |" in rendered and "Private-MetaDatabase" in rendered, "WHERE_IS_PROJECT_DATA row is unsynchronized")
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered, "WHERE_IS_PROJECT_DATA row is unsafe")
    return Check(
        "task_state_project_architecture_and_private_data_route",
        "PASS",
        {"next_run": state.get("next_run"), "real_runtime": "NOT_RUN", "release_track": "direct_mvp_no_soak"},
    )


def validate_evidence() -> Check:
    commit = _task_commit()
    evidence = _load_json(EVIDENCE)
    _require(
        evidence.get("task_id") == TASK_ID and evidence.get("phase") == PHASE and evidence.get("run_id") == RUN_ID,
        "Task005 evidence identity is invalid",
    )
    _require(
        evidence.get("task_commit") == commit and evidence.get("source_receipt_sha256") == _source_receipt(commit),
        "Task005 evidence receipt is invalid",
    )
    _require(evidence.get("status") == "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN", "Task005 evidence overstates completion")
    _require(evidence.get("acceptance_status") == ACCEPTANCE_STATUS, "Task005 evidence acceptance set is invalid")
    execution = evidence.get("execution")
    _require(
        isinstance(execution, dict)
        and execution.get("external_network_calls") == 0
        and execution.get("platform_calls") == 0
        and execution.get("private_database_client_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN"
        and execution.get("real_notion_calls") == 0
        and execution.get("tmutil_calls") == 0
        and execution.get("token_value_contact") == 0,
        "Task005 evidence crossed the runtime boundary",
    )
    rendered = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered and "Bear" + "er " not in rendered, "Task005 evidence is unsafe")
    _require("https://" not in rendered and "http://" not in rendered, "Task005 evidence contains a URL")
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
        validate_taskpack(),
        validate_lifecycle_surface(),
        validate_historical_replay(),
    ]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_acceptance())
    if require_evidence:
        checks.extend((validate_task_state_and_docs(), validate_evidence()))
    _require(all(item.status == "PASS" for item in checks), "a Task005 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.uxops.005")
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
