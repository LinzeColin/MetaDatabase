#!/usr/bin/env python3
"""Fail-closed verifier for bounded media preprocessing (TSK.x2n.multimodal.001)."""

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
TASK_ID = "TSK.x2n.multimodal.001"
PHASE = "PH.X2N.4.1"
RUN_ID = "RUN-X2N-S04-M001"
TASK_BASE_COMMIT = "f0018ec5"
NEXT_TASK = "TSK.x2n.multimodal.002"
TASK005 = "TSK.x2n.multimodal.005"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_001.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_multimodal_001_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/multimodal/TSK.x2n.multimodal.001.json"
G4_REVIEW_ID = "STG.X2N.4.REVIEW"

SOURCE_RECEIPT_PATHS = (
    PROJECT_ROOT / "apps/companion/src/x2n_companion/media_preprocessing.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/media_safety.py",
    PROJECT_ROOT / "apps/companion/tests/test_media_preprocessing.py",
    ACCEPTANCE_RUNNER,
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
        "PURSUING_GOAL.md",
        "README.md",
        "apps/companion/src/x2n_companion/media_preprocessing.py",
        "apps/companion/src/x2n_companion/media_safety.py",
        "apps/companion/tests/test_media_preprocessing.py",
        "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_001.md",
        "docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "docs/product_design/v0.0.0.1/01_PRD.md",
        "docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "evidence/multimodal/TSK.x2n.multimodal.001.json",
        "machine/facts/architecture_decisions.json",
        "machine/facts/project.json",
        "machine/facts/task_state.json",
        "scripts/run_multimodal_001_acceptance.py",
        "scripts/verify_adapters_010.py",
        "scripts/verify_multimodal_001.py",
        "scripts/verify_stage_3_review_resume.py",
        "scripts/verify_stage_3_review_resume_recheck.py",
        "tests/test_stage_3_review_resume.py",
        "tests/test_stage_3_review_resume_recheck.py",
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
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task001 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Task001 audit pin does not descend from the G3 recheck",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task001 audit pin",
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
        raise VerificationError("Task001 historical source blob is missing")
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
        _require(not any(item in text for item in forbidden_literals), "Task001 public boundary violated")
        _require(private_path.search(text) is None, "Task001 local path entered public source")
        _require(cdn.search(text) is None, "Task001 media CDN URL entered public source")


def validate_scope_and_boundary() -> Check:
    commit = _task_commit()
    changed = _changed_paths(commit)
    relative = [_task_relative(path) for path in changed]
    _require(changed and all(path is not None for path in relative), "Task001 change escaped the child project")
    scoped = [path for path in relative if path is not None]
    _require(all(path in ALLOWED_CHANGED_EXACT for path in scoped), "Task001 contains an out-of-scope change")
    files = [PROJECT_ROOT / path for path in scoped if (PROJECT_ROOT / path).is_file()]
    _safety_scan(files, commit=commit)
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".jpg", ".jpeg", ".png", ".webp"}
    _require(
        not any(Path(path).suffix.lower() in forbidden_suffixes for path in scoped),
        "Task001 Runtime media or database entered public source",
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
    _require(len(matches) == 1, "Task001 is missing or duplicated")
    return matches[0]


def _stage4_review_completed(state: dict[str, Any]) -> bool:
    return (
        state.get("stage_4_review_complete") is True
        and state.get("stage_4_review_id") == G4_REVIEW_ID
        and state.get("stage_4_gate_status") == "pass_ci_synth"
        and state.get("stage_4_remote_upload_authorized") is False
        and state.get("stage_5_authorized") is True
        and state.get("public_release_authorized") is False
    )


def validate_task_and_transition() -> Check:
    task = _load_task()
    state = _load_json(TASK_STATE)
    _require(
        task.get("status") == "completed"
        and task.get("stage") == "STG.X2N.4"
        and task.get("phase") == PHASE
        and task.get("acceptance_ids") == ["ACC.x2n.media.002", "ACC.x2n.media.004", "ACC.x2n.rel.004"]
        and task.get("depends_on") == [
            "TSK.x2n.skeleton.003",
            "TSK.x2n.skeleton.004",
            "TSK.x2n.adapters.010",
        ],
        "Task001 contract drifted",
    )
    task002_completed = state.get("tasks", {}).get(NEXT_TASK) == "pass"
    task003_completed = state.get("tasks", {}).get("TSK.x2n.multimodal.003") == "pass"
    task004_completed = state.get("tasks", {}).get("TSK.x2n.multimodal.004") == "pass"
    task005_completed = state.get("tasks", {}).get(TASK005) == "pass"
    if task005_completed:
        g4_completed = _stage4_review_completed(state)
        _require(
            g4_completed
            or (
                task002_completed
                and task003_completed
                and task004_completed
                and state.get("stage") == "STG.X2N.4"
                and state.get("last_completed_phase") == "PH.X2N.4.5"
                and state.get("run_id") == "RUN-X2N-S04-M005"
                and state.get("run_kind") == "single_dag_task_ci_synth_owner_taxonomy_classifier_private_gold_pending"
                and state.get("tasks", {}).get(TASK_ID) == "pass"
                and state.get("next_phase") == "G4"
                and state.get("next_run") == "G4"
                and state.get("next_phase_authorized") is True
                and state.get("stage_gate") == "review_pending"
                and state.get("current_stage_gate") == "review_pending"
                and state.get("stage_3_review_complete") is True
                and state.get("stage_3_remote_upload_authorized") is False
                and state.get("stage_4_authorized") is True
                and state.get("public_release_authorized") is False
                and state.get("remote_upload") == "not_required_for_local_stage_transition"
            ),
            "Task001 historical boundary was not preserved after Task005 completion",
        )
        next_task = "TSK.x2n.uxops.001" if g4_completed else "G4"
    elif task004_completed:
        _require(
            task002_completed
            and task003_completed
            and state.get("stage") == "STG.X2N.4"
            and state.get("last_completed_phase") == "PH.X2N.4.4"
            and state.get("run_id") == "RUN-X2N-S04-M004"
            and state.get("run_kind") == "single_dag_task_ci_synth_fusion_injection_model_not_run"
            and state.get("tasks", {}).get(TASK_ID) == "pass"
            and state.get("next_phase") == "PH.X2N.4.5"
            and state.get("next_run") == "TSK.x2n.multimodal.005"
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "not_run"
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("remote_upload") == "not_required_for_local_stage_transition",
            "Task001 historical boundary was not preserved after Task004 completion",
        )
        next_task = "TSK.x2n.multimodal.005"
    elif task003_completed:
        _require(
            task002_completed
            and state.get("stage") == "STG.X2N.4"
            and state.get("last_completed_phase") == "PH.X2N.4.3"
            and state.get("run_id") == "RUN-X2N-S04-M003"
            and state.get("run_kind") == "single_dag_task_ci_synth_local_first_ocr_vision_private_gold_pending"
            and state.get("tasks", {}).get(TASK_ID) == "pass"
            and state.get("next_phase") == "PH.X2N.4.4"
            and state.get("next_run") == "TSK.x2n.multimodal.004"
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "not_run"
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("remote_upload") == "not_required_for_local_stage_transition",
            "Task001 historical boundary was not preserved after Task003 completion",
        )
        next_task = "TSK.x2n.multimodal.004"
    elif task002_completed:
        _require(
            state.get("stage") == "STG.X2N.4"
            and state.get("last_completed_phase") == "PH.X2N.4.2"
            and state.get("run_id") == "RUN-X2N-S04-M002"
            and state.get("run_kind") == "single_dag_task_ci_synth_local_first_asr_private_gold_pending"
            and state.get("tasks", {}).get(TASK_ID) == "pass"
            and state.get("next_phase") == "PH.X2N.4.3"
            and state.get("next_run") == "TSK.x2n.multimodal.003"
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "not_run"
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("remote_upload") == "not_required_for_local_stage_transition",
            "Task001 historical boundary was not preserved after Task002 completion",
        )
        next_task = "TSK.x2n.multimodal.003"
    else:
        _require(
            state.get("stage") == "STG.X2N.4"
            and state.get("last_completed_phase") == PHASE
            and state.get("run_id") == RUN_ID
            and state.get("run_kind") == "single_dag_task_ci_synth_bounded_media_preprocessing"
            and state.get("tasks", {}).get(TASK_ID) == "pass"
            and state.get("next_phase") == "PH.X2N.4.2"
            and state.get("next_run") == NEXT_TASK
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "not_run"
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("remote_upload") == "not_required_for_local_stage_transition",
            "Task001 state transition is invalid",
        )
        next_task = NEXT_TASK
    statuses = state.get("acceptance_status", {})
    _require(
        statuses.get("ACC.x2n.media.002") == "pass_ci_synth_task001_lease_and_derivative_cleanup"
        and statuses.get("ACC.x2n.media.004") == "pass_ci_synth_task001_bounded_ffmpeg_ffprobe"
        and statuses.get("ACC.x2n.rel.004") == "pass_ci_synth_task001_media_capacity_contribution",
        "Task001 acceptance state is invalid",
    )
    return Check(
        "taskpack_and_stage4_transition",
        "PASS",
        {"completed_task": TASK_ID, "next_task": next_task, "stage_3_remote_upload": 0},
    )


def validate_implementation_shape() -> Check:
    source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/media_preprocessing.py").read_text(encoding="utf-8")
    lease_source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/media_safety.py").read_text(encoding="utf-8")
    required = (
        "class MediaProcessingPolicy",
        "class SandboxedCommandRunner",
        "class MediaToolchain",
        "class MediaPreprocessor",
        "def select_representative_timestamps",
        "def deduplicate_frame_candidates",
        "-max_alloc",
        "start_new_session=True",
        "subprocess.Popen",
    )
    _require(all(token in source for token in required), "Task001 bounded preprocessing implementation is incomplete")
    _require("derived_media_workspace" in source and "_lease_derived_path" in lease_source, "Task001 cleanup integration is incomplete")
    _require(
        "raw_url" not in source
        and "reserve_media_lease" not in source
        and "finalize_media_lease" not in source
        and "record_media_cleanup" not in source,
        "Task001 persistence boundary drifted",
    )
    return Check(
        "bounded_media_implementation",
        "PASS",
        {
            "max_duration_seconds": 7200,
            "max_keyframes": 50,
            "processor_persistence": 0,
            "shell_invocations": 0,
        },
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
        and evidence.get("status") == "PASS_CI_SYNTH_SCOPED"
        and evidence.get("task_commit") == commit
        and evidence.get("source_receipt_sha256") == _source_receipt(commit),
        "Task001 evidence receipt drifted",
    )
    execution = evidence.get("execution", {})
    _require(
        execution.get("platform_calls") == 0
        and execution.get("model_calls") == 0
        and execution.get("notion_calls") == 0
        and execution.get("real_account_execution") == "NOT_RUN",
        "Task001 evidence overclaims external execution",
    )
    _require(
        project.get("status")
        in {
            "stage_4_task001_bounded_media_preprocessing_pass_ci_synth",
            "stage_4_task002_local_first_asr_ci_synth_private_gold_pending",
            "stage_4_task003_local_first_ocr_vision_ci_synth_private_gold_pending",
            "stage_4_task004_fusion_injection_ci_synth_model_not_run",
            "stage_4_task005_taxonomy_classifier_ci_synth_private_gold_pending_g4_review_pending",
            "stage_4_g4_pass_ci_synth_private_gold_disabled_stage_5_task001_next",
        }
        and project.get("canonical_store") == "active_local_sqlite_logical_truth",
        "project fact drifted",
    )
    decisions = architecture.get("decisions")
    _require(isinstance(decisions, list), "architecture decisions are invalid")
    media = next((item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-008"), None)
    _require(
        isinstance(media, dict)
        and media.get("state") == "accepted_implementation"
        and media.get("implementation_state") == "lease_scoped_bounded_ffmpeg_ffprobe_audio_keyframe_dedup_and_derivative_cleanup_ci_synth_pass",
        "media architecture decision drifted",
    )
    return Check(
        "evidence_and_current_facts",
        "PASS",
        {"platform_calls": 0, "source_receipt": "verified", "synthetic_unit_tests": 32},
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
        raise VerificationError("Task001 acceptance runner failed")
    payloads: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(payloads, "Task001 acceptance runner did not emit a receipt")
    return payloads[-1]


def validate_acceptance_execution() -> Check:
    receipt = _run_acceptance()
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED"
        and receipt.get("metrics", {}).get("synthetic_unit_tests") >= 32
        and receipt.get("metrics", {}).get("max_keyframes") == 50
        and receipt.get("metrics", {}).get("max_media_duration_seconds") == 7200
        and receipt.get("execution", {}).get("platform_calls") == 0,
        "Task001 acceptance receipt is invalid",
    )
    return Check("fresh_synthetic_acceptance", "PASS", {"platform_calls": 0, "synthetic_unit_tests": 32})


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) not in {"", "main"}, "Task001 must remain in a non-main worktree")
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
