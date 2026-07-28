#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.010."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.adapters.010"
RUN_ID = "RUN-X2N-S03-A010"
PHASE = "PH.X2N.3.10"
TASK_BASE_COMMIT = "2e7de513f4d5d829c78a4d015aa2297575522434"
TASK010_FINAL_COMMIT = "c528ff14836f116f624fa8b1ea63472a7f4b678f"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
RESUME_FACT = PROJECT_ROOT / "machine/facts/stage_3_review_resume_state.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_010.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_010_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.010.json"

INPUT_RECEIPT_PATHS = (
    TASKPACK,
    TASK_STATE,
    RESUME_FACT,
    RUN_CONTRACT,
    PROJECT_ROOT / "apps/companion/src/x2n_companion/adapter_dispatch.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/douyin_upstream.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/orchestrator.py",
    PROJECT_ROOT / "apps/companion/tests/test_adapter_dispatch.py",
    PROJECT_ROOT / "apps/companion/tests/test_canonical_store.py",
    PROJECT_ROOT / "apps/extension/src/service-worker.js",
    PROJECT_ROOT / "apps/extension/src/sidepanel.js",
    PROJECT_ROOT / "apps/extension/sidepanel.html",
    PROJECT_ROOT / "apps/extension/styles/sidepanel.css",
    PROJECT_ROOT / "apps/extension/scripts/extension-e2e.mjs",
    PROJECT_ROOT / "apps/extension/scripts/self-test.mjs",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/__init__.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/errors.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/generate.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "packages/contracts/registry/error_codes.v1.json",
    PROJECT_ROOT / "packages/contracts/schemas/v1/native_message_request.schema.json",
    PROJECT_ROOT / "packages/contracts/schemas/v1/native_message_response.schema.json",
    PROJECT_ROOT / "packages/contracts/types/contracts.ts",
    PROJECT_ROOT / "packages/contracts/tests/test_adapter_dispatch_contracts.py",
    ACCEPTANCE_RUNNER,
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
    PROJECT_ROOT / "tests/test_adapters_010.py",
)

ALLOWED_CHANGED_EXACT = frozenset(
    {
        "CHANGELOG.md",
        "HANDOFF.md",
        "README.md",
        "功能清单.md",
        "开发记录.md",
        "apps/companion/src/x2n_companion/adapter_dispatch.py",
        "apps/companion/src/x2n_companion/canonical_store.py",
        "apps/companion/src/x2n_companion/douyin_upstream.py",
        "apps/companion/src/x2n_companion/migrations.py",
        "apps/companion/src/x2n_companion/native_host.py",
        "apps/companion/src/x2n_companion/orchestrator.py",
        "apps/companion/tests/test_adapter_dispatch.py",
        "apps/companion/tests/test_canonical_store.py",
        "apps/extension/scripts/extension-e2e.mjs",
        "apps/extension/scripts/self-test.mjs",
        "apps/extension/sidepanel.html",
        "apps/extension/src/service-worker.js",
        "apps/extension/src/sidepanel.js",
        "apps/extension/styles/sidepanel.css",
        "docs/governance/RUN_CONTRACT_S03_ADAPTERS_010.md",
        "docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "docs/product_design/v0.0.0.1/01_PRD.md",
        "docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
        "evidence/adapters/TSK.x2n.adapters.010.json",
        "machine/facts/task_state.json",
        "packages/contracts/registry/error_codes.v1.json",
        "packages/contracts/schemas/v1/error.schema.json",
        "packages/contracts/schemas/v1/health_report.schema.json",
        "packages/contracts/schemas/v1/native_message_request.schema.json",
        "packages/contracts/schemas/v1/native_message_response.schema.json",
        "packages/contracts/schemas/v1/source_observation.schema.json",
        "packages/contracts/src/x2n_contracts/__init__.py",
        "packages/contracts/src/x2n_contracts/errors.py",
        "packages/contracts/src/x2n_contracts/generate.py",
        "packages/contracts/src/x2n_contracts/models.py",
        "packages/contracts/tests/test_adapter_dispatch_contracts.py",
        "packages/contracts/types/contracts.ts",
        "scripts/run_adapters_010_acceptance.py",
        "scripts/verify_adapters_010.py",
        "scripts/verify_stage_3_review_resume.py",
        "tests/test_adapters_010.py",
        "tests/test_stage_3_review_resume.py",
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


def _git(args: Sequence[str], *, cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("required JSON fact is invalid") from error
    if not isinstance(value, dict):
        raise VerificationError("required JSON fact must be an object")
    return value


def _load_task() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is unreadable") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise VerificationError("Taskpack task list is invalid")
    matches = [item for item in payload["tasks"] if isinstance(item, dict) and item.get("id") == TASK_ID]
    if len(matches) != 1:
        raise VerificationError("Task010 is missing or duplicated")
    return matches[0]


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
        raise VerificationError("Task010 historical source blob is missing")
    return result.stdout


def _source_receipt() -> str:
    digest = hashlib.sha256()
    for path in INPUT_RECEIPT_PATHS:
        _require(path.is_file(), "Task010 input receipt file is missing")
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(TASK010_FINAL_COMMIT, path))
        digest.update(b"\0")
    return digest.hexdigest()


def _changed_paths() -> list[str]:
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    candidates: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..{TASK010_FINAL_COMMIT}"),
    ):
        candidates.update(path for path in _git(arguments).split("\0") if path)
    return sorted(candidates)


def _task_relative(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def _safety_scan(paths: Iterable[Path]) -> None:
    forbidden_literals = ("Agent" + "Database", "OpenAI" + "Database", "github" + "_pat_", "Bearer" + " ")
    private_path = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    cdn = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|(?:img|gw|video|vod|pic|media)\.alicdn)",
        flags=re.IGNORECASE,
    )
    for path in paths:
        text = _blob_at(TASK010_FINAL_COMMIT, path).decode("utf-8", errors="replace")
        _require(not any(item in text for item in forbidden_literals), "Task010 public boundary violated")
        _require(private_path.search(text) is None, "Task010 local path entered public source")
        _require(cdn.search(text) is None, "Task010 media CDN URL entered public source")


def validate_scope_and_boundary() -> Check:
    paths = _changed_paths()
    relative = [_task_relative(path) for path in paths]
    _require(all(path is not None for path in relative), "Task010 change escaped the child project")
    relative_paths = [path for path in relative if path is not None]
    _require(relative_paths, "Task010 has no recorded source change")
    _require(all(path in ALLOWED_CHANGED_EXACT for path in relative_paths), "Task010 contains an out-of-scope change")
    files = [PROJECT_ROOT / path for path in relative_paths if (PROJECT_ROOT / path).is_file()]
    _safety_scan(files)
    _require(not any(path.endswith((".sqlite", ".sqlite3", ".db", ".mp4", ".mp3", ".jpg", ".png")) for path in relative_paths), "runtime data entered Task010")
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(relative_paths), "platform_cdn_urls": 0, "runtime_data_files": 0},
    )


def validate_task_state_and_historical_resume() -> Check:
    task = _load_task()
    state = _load_json(TASK_STATE)
    resume = _load_json(RESUME_FACT)
    _require(task.get("phase") == PHASE and task.get("status") == "completed", "Task010 is not completed")
    _require(task.get("acceptance_ids") == ["ACC.x2n.batch.002", "ACC.x2n.ext.003", "ACC.x2n.batch.001"], "Task010 acceptance IDs drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Task010 current state is not pass")
    task001_state = state.get("tasks", {}).get("TSK.x2n.multimodal.001")
    if state.get("stage_gate") == "review_pending":
        _require(
            state.get("last_completed_phase") == PHASE
            and state.get("review_id") == "STG.X2N.3.REVIEW.RESUME.RECHECK_PENDING"
            and state.get("run_id") == RUN_ID
            and state.get("stage_4_authorized") is False,
            "Task010 pending-review state drifted",
        )
        current_stage = "review_pending"
    elif task001_state == "pass":
        _require(
            state.get("last_completed_phase") == "PH.X2N.4.1"
            and state.get("review_id") == "STG.X2N.3.REVIEW.RESUME.RECHECK"
            and state.get("run_id") == "RUN-X2N-S04-M001"
            and state.get("stage") == "STG.X2N.4"
            and state.get("current_stage_gate") == "not_run"
            and state.get("stage_gate") == "pass"
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("next_run") == "TSK.x2n.multimodal.002",
            "Task010 historical boundary was not preserved after Task001 completion",
        )
        current_stage = "stage4_task001_complete"
    else:
        _require(
            state.get("last_completed_phase") == "STG.X2N.3.REVIEW.RESUME.RECHECK"
            and state.get("review_id") == "STG.X2N.3.REVIEW.RESUME.RECHECK"
            and state.get("run_id") == "RUN-X2N-S03-REVIEW-RESUME-RECHECK"
            and state.get("stage_gate") == "pass"
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("next_run") == "TSK.x2n.multimodal.001",
            "Task010 downstream G3 recheck state drifted",
        )
        current_stage = "pass_after_independent_g3_recheck"
    _require(state.get("stage_3_remote_upload_authorized") is False, "Task010 authorized a remote upload")
    historical_task = resume.get("next_task", {})
    _require(
        historical_task.get("id") == TASK_ID
        and historical_task.get("phase") == PHASE
        and historical_task.get("status") == "PLANNED"
        and resume.get("authorization", {}).get("new_dag_task_executed") is False,
        "historical Resume fact was rewritten",
    )
    return Check(
        "task_state_and_historical_resume_boundary",
        "PASS",
        {"current_task": "pass", "historical_resume_task": "PLANNED", "stage_gate": current_stage},
    )


def validate_contract_and_runtime_shape() -> Check:
    sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
    sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))
    from x2n_contracts import ErrorCode, ERROR_SPECS  # noqa: PLC0415
    from x2n_contracts.models import (  # noqa: PLC0415
        CapabilityFeatureFlag,
        CapabilityReasonCode,
        CapabilityTerminal,
        SyncScopeId,
    )
    from x2n_companion.adapter_dispatch import CapabilityRegistry, SCOPE_BINDINGS  # noqa: PLC0415
    from x2n_companion.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS  # noqa: PLC0415
    from x2n_companion.runtime import X2NRuntimeError  # noqa: PLC0415

    _require(tuple(binding.scope_id for binding in SCOPE_BINDINGS) == tuple(SyncScopeId), "scope registry is not exact")
    _require(LATEST_SCHEMA_VERSION == 3 and len(MIGRATIONS) == 3, "Task010 migration version drifted")
    manifest = CapabilityRegistry().evaluate(evaluated_at="2026-07-28T00:00:00Z")
    _require(len(manifest.outcomes) == 8, "typed capability outcome count drifted")
    _require(
        all(item.terminal is CapabilityTerminal.READY_FOR_MVP_ACTIVATION for item in manifest.outcomes)
        and all(item.reason_code is CapabilityReasonCode.CI_SYNTH_READY for item in manifest.outcomes)
        and all(item.feature_flag is CapabilityFeatureFlag.CI_SYNTHETIC_ONLY for item in manifest.outcomes),
        "CI synthetic capability manifest drifted",
    )
    technical = CapabilityRegistry().with_override(SyncScopeId.XIAOHONGSHU_FAVORITES, technical_blocked=True)
    try:
        technical.evaluate(evaluated_at="2026-07-28T00:00:00Z")
    except X2NRuntimeError as error:
        _require(error.code is ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "technical veto used an unstable code")
    else:
        raise VerificationError("technical veto serialized a terminal outcome")
    spec = ERROR_SPECS[ErrorCode.ADAPTER_FAILED_FALLBACK_AVAILABLE]
    _require(spec.next_action.value == "capture_current" and spec.retryable is False, "fallback error contract drifted")
    return Check(
        "eight_scope_contract_capability_authority_and_migration",
        "PASS",
        {"capability_outcomes": 8, "migration_version": LATEST_SCHEMA_VERSION, "technical_terminal_outcomes": 0},
    )


def validate_generated_artifacts() -> Check:
    sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))
    from x2n_contracts.generate import check_artifacts, generated_artifacts  # noqa: PLC0415

    _require(check_artifacts(generated_artifacts()) == [], "generated public contracts are stale")
    return Check("generated_schema_and_typescript_contracts", "PASS", {"drift_files": 0})


def _playwright_browsers_path() -> str | None:
    """Locate only the local Playwright browser binary cache, never Owner data."""

    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        return configured
    default_cache = Path.home() / "Library/Caches/ms-playwright"
    return str(default_cache) if default_cache.is_dir() else None


def _isolated_env(home: Path) -> dict[str, str]:
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }
    browser_path = _playwright_browsers_path()
    if browser_path:
        environment["PLAYWRIGHT_BROWSERS_PATH"] = browser_path
    return environment


def _json_line(output: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    if not values:
        raise VerificationError("acceptance output has no JSON receipt")
    return values[-1]


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a010-verify-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir(mode=0o700)
        result = subprocess.run(
            [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
            cwd=PROJECT_ROOT,
            env=_isolated_env(home),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=600,
        )
    _require(result.returncode == 0, "Task010 acceptance runner failed")
    output = _json_line(result.stdout)
    expected = {
        "acceptance_scope": "ADAPTERS_010_NATIVE_DISPATCH_AND_EXPLICIT_FALLBACK_CI_SYNTH",
        "automatic_fallbacks": 0,
        "capability_scope_count": 8,
        "extension_e2e_status": "PASS",
        "model_calls": 0,
        "owner_alpha": "NOT_RUN",
        "owner_beta": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "scope_dispatch_platform_calls": 0,
        "scope_dispatches": 8,
        "stage_3_upload": "NOT_RUN",
        "stage_4": "NOT_RUN",
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "typed_capability_rows": 8,
    }
    for key, expected_value in expected.items():
        _require(output.get(key) == expected_value, "Task010 acceptance metric drifted")
    _require(isinstance(output.get("python_tests"), int) and output["python_tests"] >= 30, "Task010 unit coverage is too small")
    return Check(
        "extension_native_adapter_failure_fallback_and_restart_acceptance",
        "PASS",
        {"platform_calls": 0, "python_tests": output["python_tests"], "scope_dispatches": 8},
    )


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) not in {"", "main"}, "Task010 must run in a non-main worktree")
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK010_FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "Task010 worktree does not descend from its base",
    )
    main_paths: list[str] = []
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_paths = _git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=Path(worktree)).splitlines()
            break
    _require(not any("xhs-douyin-2notion" in item for item in main_paths), "main worktree overlaps Task010")
    return Check("worktree_isolation", "PASS", {"main_x2n_dirty_paths": 0})


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "evidence contains a local user path")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "evidence contains a secret")
    _require("https://" not in rendered and "http://" not in rendered, "evidence contains a URL")


def write_evidence(checks: Sequence[Check]) -> None:
    _require(all(check.status == "PASS" for check in checks), "cannot write failed Task010 evidence")
    _require(
        _load_json(TASK_STATE).get("stage_gate") == "review_pending",
        "Task010 final evidence is immutable after the independent G3 recheck",
    )
    payload = {
        "acceptance_ids": ["ACC.x2n.batch.002", "ACC.x2n.ext.003", "ACC.x2n.batch.001"],
        "acceptance_input_sha256": _source_receipt(),
        "automatic_fallbacks": 0,
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "owner_alpha": "NOT_RUN",
        "owner_beta": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.3",
        "stage_3_upload": "FORBIDDEN_PENDING_INDEPENDENT_G3_REVIEW",
        "stage_4": "UNAUTHORIZED_PENDING_INDEPENDENT_G3_REVIEW",
        "status": "PASS_CI_SYNTH_SCOPED_REVIEW_PENDING",
        "task_id": TASK_ID,
        "task_metrics": {
            "capability_scope_rows": 8,
            "failed_run_state": "verified_by_unit_acceptance",
            "platform_calls": 0,
            "scope_dispatches": 8,
            "synthetic_only": True,
        },
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    _require(EVIDENCE.read_bytes() == _blob_at(TASK010_FINAL_COMMIT, EVIDENCE), "Task010 evidence was rewritten")
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "Task010 evidence identity drifted")
    _require(evidence.get("acceptance_input_sha256") == _source_receipt(), "Task010 evidence receipt is stale")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_SCOPED_REVIEW_PENDING"
        and evidence.get("platform_calls") == 0
        and evidence.get("automatic_fallbacks") == 0
        and evidence.get("stage_3_upload") == "FORBIDDEN_PENDING_INDEPENDENT_G3_REVIEW"
        and evidence.get("stage_4") == "UNAUTHORIZED_PENDING_INDEPENDENT_G3_REVIEW",
        "Task010 evidence overstates authorization",
    )
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "Task010 evidence contains a failed check")
    return Check("evidence_receipt", "PASS", {"input_sha256": evidence["acceptance_input_sha256"], "platform_calls": 0})


def run_checks(*, verify_worktree: bool, run_external: bool, require_evidence: bool) -> list[Check]:
    checks = [
        validate_scope_and_boundary(),
        validate_task_state_and_historical_resume(),
        validate_contract_and_runtime_shape(),
        validate_generated_artifacts(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree())
    if run_external:
        checks.append(validate_execution())
    if require_evidence:
        checks.append(verify_evidence())
    _require(all(check.status == "PASS" for check in checks), "Task010 verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.010")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            run_external=not args.skip_external,
            require_evidence=args.require_evidence and not args.write_evidence,
        )
        if args.write_evidence:
            write_evidence(checks)
            checks.append(verify_evidence())
        print(json.dumps({"checks": [check.name for check in checks], "status": "PASS", "task_id": TASK_ID}, sort_keys=True))
        return 0
    except (OSError, subprocess.TimeoutExpired, VerificationError) as error:
        print(json.dumps({"reason": str(error), "status": "FAIL_CLOSED", "task_id": TASK_ID}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
