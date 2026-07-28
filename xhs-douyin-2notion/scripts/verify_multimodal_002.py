#!/usr/bin/env python3
"""Fail-closed verifier for local-first ASR (TSK.x2n.multimodal.002)."""

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
TASK_ID = "TSK.x2n.multimodal.002"
PHASE = "PH.X2N.4.2"
RUN_ID = "RUN-X2N-S04-M002"
TASK_BASE_COMMIT = "db902304ef4231fa78f1e84109938511cac9b046"
NEXT_TASK = "TSK.x2n.multimodal.003"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_002.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_multimodal_002_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/models/TSK.x2n.multimodal.002.json"

SOURCE_RECEIPT_PATHS = (
    PROJECT_ROOT / "apps/companion/src/x2n_companion/asr.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py",
    PROJECT_ROOT / "apps/companion/tests/test_asr.py",
    ACCEPTANCE_RUNNER,
    PROJECT_ROOT / "scripts/verify_multimodal_001.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume_recheck.py",
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
    PROJECT_ROOT / "scripts/verify_multimodal_002.py",
    RUN_CONTRACT,
    TASKPACK,
    TASK_STATE,
    PROJECT_FACT,
    ARCHITECTURE,
)

ALLOWED_CHANGED_EXACT = frozenset(
    {
        "CHANGELOG.md",
        "HANDOFF.md",
        "README.md",
        "apps/companion/src/x2n_companion/asr.py",
        "apps/companion/src/x2n_companion/runtime_cli.py",
        "apps/companion/tests/test_asr.py",
        "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_002.md",
        "docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "docs/product_design/v0.0.0.1/01_PRD.md",
        "docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "evidence/models/TSK.x2n.multimodal.002.json",
        "machine/facts/architecture_decisions.json",
        "machine/facts/project.json",
        "machine/facts/task_state.json",
        "scripts/run_multimodal_002_acceptance.py",
        "scripts/verify_adapters_010.py",
        "scripts/verify_multimodal_001.py",
        "scripts/verify_multimodal_002.py",
        "scripts/verify_stage_3_review_resume.py",
        "scripts/verify_stage_3_review_resume_recheck.py",
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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError("required JSON fact is invalid") from error
    if not isinstance(value, dict):
        raise VerificationError("required JSON fact must be an object")
    return value


def _task_commit() -> str:
    evidence = _load_json(EVIDENCE)
    commit = evidence.get("task_commit")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task002 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Task002 audit pin does not descend from Task001 evidence pin",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task002 audit pin",
    )
    return commit


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


def _changed_paths(commit: str) -> list[str]:
    values = _git(["diff", "--name-only", "-z", f"{TASK_BASE_COMMIT}..{commit}"])
    return sorted(path for path in values.split("\0") if path)


def _task_relative(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


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
    changed = _changed_paths(commit)
    relative = [_task_relative(path) for path in changed]
    _require(changed and all(path is not None for path in relative), "Task002 change escaped the child project")
    scoped = [path for path in relative if path is not None]
    _require(all(path in ALLOWED_CHANGED_EXACT for path in scoped), "Task002 contains an out-of-scope change")
    files = [PROJECT_ROOT / path for path in scoped if (PROJECT_ROOT / path).is_file()]
    _safety_scan(files, commit=commit)
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(
        not any(Path(path).suffix.lower() in forbidden_suffixes for path in scoped),
        "Task002 Runtime media or database entered public source",
    )
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {"changed_files": len(scoped), "platform_cdn_urls": 0, "runtime_media_files": 0},
    )


def _load_task() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError("Taskpack is unreadable") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise VerificationError("Taskpack is invalid")
    matches = [item for item in payload["tasks"] if isinstance(item, dict) and item.get("id") == TASK_ID]
    _require(len(matches) == 1, "Task002 is missing or duplicated")
    return matches[0]


def validate_task_and_transition() -> Check:
    task = _load_task()
    state = _load_json(TASK_STATE)
    _require(
        task.get("status") == "completed"
        and task.get("stage") == "STG.X2N.4"
        and task.get("phase") == PHASE
        and task.get("acceptance_ids") == ["ACC.x2n.ai.001", "ACC.x2n.ai.007"]
        and task.get("depends_on") == ["TSK.x2n.multimodal.001"],
        "Task002 contract drifted",
    )
    _require(
        state.get("stage") == "STG.X2N.4"
        and state.get("last_completed_phase") == PHASE
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "single_dag_task_ci_synth_local_first_asr_private_gold_pending"
        and state.get("tasks", {}).get("TSK.x2n.multimodal.001") == "pass"
        and state.get("tasks", {}).get(TASK_ID) == "pass"
        and state.get("next_phase") == "PH.X2N.4.3"
        and state.get("next_run") == NEXT_TASK
        and state.get("next_phase_authorized") is True
        and state.get("stage_gate") == "pass"
        and state.get("current_stage_gate") == "not_run"
        and state.get("stage_3_review_complete") is True
        and state.get("stage_3_remote_upload_authorized") is False
        and state.get("stage_4_authorized") is True
        and state.get("public_release_authorized") is False
        and state.get("remote_upload") == "not_required_for_local_stage_transition",
        "Task002 state transition is invalid",
    )
    statuses = state.get("acceptance_status", {})
    _require(
        statuses.get("ACC.x2n.ai.001") == "pending_private_gold_asr_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.007") == "pass_ci_synth_task002_provenance_cache_budget_cloud_zero",
        "Task002 acceptance state is invalid",
    )
    return Check(
        "taskpack_and_stage4_transition",
        "PASS",
        {"completed_task": TASK_ID, "next_task": NEXT_TASK, "private_gold_evaluation": "NOT_RUN"},
    )


def validate_implementation_shape() -> Check:
    source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/asr.py").read_text(encoding="utf-8")
    cli = (PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py").read_text(encoding="utf-8")
    required = (
        "class AsrPolicy",
        "class WhisperCppLocalProvider",
        "class DisabledCloudAsrProvider",
        "class AsrEvaluator",
        "class AsrSession",
        "def load_private_asr_gold_dataset",
        "def character_error_rate",
        "def word_error_rate",
        "whisper-cli",
        "max_cloud_cost_microunits: int = 0",
        "__getstate__",
    )
    _require(all(token in source for token in required), "Task002 local-first ASR implementation is incomplete")
    _require(
        "raw_url" not in source
        and "requests." not in source
        and "httpx" not in source
        and "sqlite3" not in source,
        "Task002 ASR implementation crossed its no-network/no-persistence boundary",
    )
    _require(
        'if args.action == "eval"' in cli and 'evaluation_actions.add_parser("asr")' in cli,
        "Task002 equivalent x2n eval asr oracle is missing",
    )
    return Check(
        "local_first_asr_provenance_cache_and_private_eval_shape",
        "PASS",
        {"cloud_upload_authorized": False, "durable_transcript_writes": 0, "shell_invocations": 0},
    )


def validate_facts_and_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    commit = _task_commit()
    _require(
        evidence.get("task_id") == TASK_ID
        and evidence.get("phase") == PHASE
        and evidence.get("run_id") == RUN_ID
        and evidence.get("status") == "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING"
        and evidence.get("task_commit") == commit
        and evidence.get("source_receipt_sha256") == _source_receipt(commit),
        "Task002 evidence receipt drifted",
    )
    execution = evidence.get("execution", {})
    _require(
        execution.get("platform_calls") == 0
        and execution.get("model_calls") == 0
        and execution.get("cloud_uploads") == 0
        and execution.get("private_gold_evaluation") == "NOT_RUN"
        and execution.get("real_account_execution") == "NOT_RUN",
        "Task002 evidence overclaims model or external execution",
    )
    _require(
        project.get("status") == "stage_4_task002_local_first_asr_ci_synth_private_gold_pending"
        and project.get("canonical_store") == "active_local_sqlite_logical_truth",
        "project fact drifted",
    )
    decisions = architecture.get("decisions")
    _require(isinstance(decisions, list), "architecture decisions are invalid")
    asr = next((item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-013"), None)
    _require(
        isinstance(asr, dict)
        and asr.get("state") == "accepted_implementation"
        and asr.get("implementation_state")
        == "local_whispercpp_cli_ephemeral_transcript_provenance_cache_budget_disabled_cloud_ci_synth_private_gold_pending",
        "ASR architecture decision drifted",
    )
    return Check(
        "evidence_and_current_facts",
        "PASS",
        {"cloud_uploads": 0, "private_gold": "NOT_RUN", "source_receipt": "verified"},
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
        timeout=240,
    )
    if result.returncode != 0:
        raise VerificationError("Task002 acceptance runner failed")
    payloads: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(payloads, "Task002 acceptance runner did not emit a receipt")
    return payloads[-1]


def validate_acceptance_execution() -> Check:
    receipt = _run_acceptance()
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING"
        and receipt.get("metrics", {}).get("synthetic_unit_tests") >= 9
        and receipt.get("metrics", {}).get("same_input_duplicate_provider_calls") == 0
        and receipt.get("execution", {}).get("platform_calls") == 0
        and receipt.get("execution", {}).get("cloud_uploads") == 0
        and receipt.get("execution", {}).get("private_gold_evaluation") == "NOT_RUN",
        "Task002 acceptance receipt is invalid",
    )
    return Check(
        "fresh_synthetic_acceptance",
        "PASS",
        {"cloud_uploads": 0, "private_gold": "NOT_RUN", "synthetic_unit_tests": receipt["metrics"]["synthetic_unit_tests"]},
    )


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) not in {"", "main"}, "Task002 must remain in a non-main worktree")
    return Check("worktree_isolation", "PASS", {"main_mutated": False, "task_worktree": True})


def run_checks(*, verify_worktree: bool, run_acceptance: bool) -> list[Check]:
    checks = [validate_scope_and_boundary(), validate_task_and_transition(), validate_implementation_shape(), validate_facts_and_evidence()]
    if verify_worktree:
        checks.append(validate_worktree())
    if run_acceptance:
        checks.append(validate_acceptance_execution())
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    arguments = parser.parse_args()
    try:
        checks = run_checks(verify_worktree=arguments.verify_worktree, run_acceptance=arguments.run_acceptance)
    except VerificationError:
        return 1
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


if __name__ == "__main__":
    raise SystemExit(main())
