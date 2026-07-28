#!/usr/bin/env python3
"""Fail-closed verifier for fusion and injection isolation (TSK.x2n.multimodal.004)."""

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
TASK_ID = "TSK.x2n.multimodal.004"
PHASE = "PH.X2N.4.4"
RUN_ID = "RUN-X2N-S04-M004"
TASK_BASE_COMMIT = "85e26fb3c85f72f848c784cb8ad615f57b79c8fd"
NEXT_TASK = "TSK.x2n.multimodal.005"
TASK005 = NEXT_TASK
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_004.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_multimodal_004_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/models/TSK.x2n.multimodal.004.json"
G4_REVIEW_ID = "STG.X2N.4.REVIEW"

SOURCE_RECEIPT_PATHS = (
    PROJECT_ROOT / "apps/companion/src/x2n_companion/fusion.py",
    PROJECT_ROOT / "apps/companion/tests/test_fusion.py",
    ACCEPTANCE_RUNNER,
    PROJECT_ROOT / "scripts/verify_multimodal_001.py",
    PROJECT_ROOT / "scripts/verify_multimodal_002.py",
    PROJECT_ROOT / "scripts/verify_multimodal_003.py",
    PROJECT_ROOT / "scripts/verify_multimodal_004.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume_recheck.py",
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
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
        "apps/companion/src/x2n_companion/fusion.py",
        "apps/companion/tests/test_fusion.py",
        "docs/governance/RUN_CONTRACT_S04_MULTIMODAL_004.md",
        "docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "docs/product_design/v0.0.0.1/01_PRD.md",
        "docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "evidence/models/TSK.x2n.multimodal.004.json",
        "machine/facts/architecture_decisions.json",
        "machine/facts/project.json",
        "machine/facts/task_state.json",
        "scripts/run_multimodal_004_acceptance.py",
        "scripts/verify_adapters_010.py",
        "scripts/verify_multimodal_001.py",
        "scripts/verify_multimodal_002.py",
        "scripts/verify_multimodal_003.py",
        "scripts/verify_multimodal_004.py",
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
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Task004 audit pin is missing")
    _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, commit],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Task004 audit pin does not descend from Task003 evidence pin",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the Task004 audit pin",
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
        raise VerificationError("Task004 historical source blob is missing")
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
        _require(not any(item in text for item in forbidden_literals), "Task004 public boundary violated")
        _require(private_path.search(text) is None, "Task004 local path entered public source")
        _require(cdn.search(text) is None, "Task004 media CDN URL entered public source")


def validate_scope_and_boundary() -> Check:
    commit = _task_commit()
    changed = _changed_paths(commit)
    relative = [_task_relative(path) for path in changed]
    _require(changed and all(path is not None for path in relative), "Task004 change escaped the child project")
    scoped = [path for path in relative if path is not None]
    _require(all(path in ALLOWED_CHANGED_EXACT for path in scoped), "Task004 contains an out-of-scope change")
    files = [PROJECT_ROOT / path for path in scoped if (PROJECT_ROOT / path).is_file()]
    _safety_scan(files, commit=commit)
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".m4a", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".webp"}
    _require(
        not any(Path(path).suffix.lower() in forbidden_suffixes for path in scoped),
        "Task004 Runtime media or database entered public source",
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
    _require(len(matches) == 1, "Task004 is missing or duplicated")
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


def _stage5_task001_completed(state: dict[str, Any]) -> bool:
    return (
        _stage4_review_completed(state)
        and state.get("tasks", {}).get("TSK.x2n.uxops.001") == "pass"
        and state.get("last_completed_phase") == "PH.X2N.5.1"
        and state.get("run_id") == "RUN-X2N-S05-U001"
        and state.get("state") == "stage_5_task001_notion_projection_ci_synth_pass_task002_next_real_notion_not_run"
        and state.get("next_run") == "TSK.x2n.uxops.002"
        and state.get("stage_5_task001_complete") is True
        and state.get("stage_5_remote_upload_authorized") is False
    )


def validate_task_and_transition() -> Check:
    task = _load_task()
    state = _load_json(TASK_STATE)
    _require(
        task.get("status") == "completed"
        and task.get("stage") == "STG.X2N.4"
        and task.get("phase") == PHASE
        and task.get("acceptance_ids") == ["ACC.x2n.ai.004", "ACC.x2n.ai.007"]
        and task.get("depends_on") == ["TSK.x2n.multimodal.002", "TSK.x2n.multimodal.003"],
        "Task004 contract drifted",
    )
    task005_completed = state.get("tasks", {}).get(TASK005) == "pass"
    if task005_completed:
        g4_completed = _stage4_review_completed(state)
        _require(
            g4_completed
            or (
                state.get("stage") == "STG.X2N.4"
                and state.get("last_completed_phase") == "PH.X2N.4.5"
                and state.get("run_id") == "RUN-X2N-S04-M005"
                and state.get("run_kind") == "single_dag_task_ci_synth_owner_taxonomy_classifier_private_gold_pending"
                and all(
                    state.get("tasks", {}).get(task_id) == "pass"
                    for task_id in (
                        "TSK.x2n.multimodal.001",
                        "TSK.x2n.multimodal.002",
                        "TSK.x2n.multimodal.003",
                        TASK_ID,
                        TASK005,
                    )
                )
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
            "Task004 historical boundary was not preserved after Task005 completion",
        )
        next_task = "TSK.x2n.uxops.002" if _stage5_task001_completed(state) else "TSK.x2n.uxops.001" if g4_completed else "G4"
    else:
        _require(
            state.get("stage") == "STG.X2N.4"
            and state.get("last_completed_phase") == PHASE
            and state.get("run_id") == RUN_ID
            and state.get("run_kind") == "single_dag_task_ci_synth_fusion_injection_model_not_run"
            and all(state.get("tasks", {}).get(task_id) == "pass" for task_id in ("TSK.x2n.multimodal.001", "TSK.x2n.multimodal.002", "TSK.x2n.multimodal.003", TASK_ID))
            and state.get("next_phase") == "PH.X2N.4.5"
            and state.get("next_run") == NEXT_TASK
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "not_run"
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("remote_upload") == "not_required_for_local_stage_transition",
            "Task004 state transition is invalid",
        )
        next_task = NEXT_TASK
    statuses = state.get("acceptance_status", {})
    if task005_completed:
        _require(
            statuses.get("ACC.x2n.ai.001") == "pending_private_gold_asr_disabled_ci_synth_contract_pass"
            and statuses.get("ACC.x2n.ai.002") == "pending_private_gold_ocr_disabled_ci_synth_contract_pass"
            and statuses.get("ACC.x2n.ai.003") == "pending_private_gold_vision_disabled_ci_synth_contract_pass"
            and statuses.get("ACC.x2n.ai.004") == "pass_ci_synth_fusion_schema_injection_isolation_model_not_run"
            and statuses.get("ACC.x2n.ai.005") == "pass_ci_synth_owner_taxonomy_registry_revision_review_suggestion_only"
            and statuses.get("ACC.x2n.ai.006") == "pending_private_gold_classification_suggestion_only_ci_contract_pass"
            and statuses.get("ACC.x2n.ai.007") == "pass_ci_synth_task005_provenance_cache_budget_cloud_zero",
            "Task004 historical acceptance boundary was not preserved after Task005 completion",
        )
    else:
        _require(
            statuses.get("ACC.x2n.ai.001") == "pending_private_gold_asr_disabled_ci_synth_contract_pass"
            and statuses.get("ACC.x2n.ai.002") == "pending_private_gold_ocr_disabled_ci_synth_contract_pass"
            and statuses.get("ACC.x2n.ai.003") == "pending_private_gold_vision_disabled_ci_synth_contract_pass"
            and statuses.get("ACC.x2n.ai.004") == "pass_ci_synth_fusion_schema_injection_isolation_model_not_run"
            and statuses.get("ACC.x2n.ai.007") == "pass_ci_synth_task004_provenance_cache_budget_cloud_zero",
            "Task004 acceptance state is invalid",
        )
    return Check(
        "taskpack_and_stage4_transition",
        "PASS",
        {"completed_task": TASK_ID, "next_task": next_task, "model_execution": "NOT_RUN"},
    )


def validate_implementation_shape() -> Check:
    source = (PROJECT_ROOT / "apps/companion/src/x2n_companion/fusion.py").read_text(encoding="utf-8")
    tests = (PROJECT_ROOT / "apps/companion/tests/test_fusion.py").read_text(encoding="utf-8")
    required = (
        "class FusionPolicy",
        "class FusionProcessorDescriptor",
        "class FusionSource",
        "class FusionRequest",
        "class FusionSession",
        "class EphemeralFusionArtifact",
        "def build_isolated_prompt",
        "def parse_untrusted_fusion_response",
        "max_model_calls: int = 0",
        "max_tool_calls: int = 0",
        "__getstate__",
    )
    _require(all(token in source for token in required), "Task004 fail-closed fusion implementation is incomplete")
    _require(
        "requests." not in source
        and "httpx" not in source
        and "sqlite3" not in source
        and "subprocess" not in source
        and "open(" not in source,
        "Task004 fusion implementation crossed its no-side-effect boundary",
    )
    red_team = ("malicious_caption_ocr_and_subtitle", "unicode_bidi_and_long_input", "strict_parser_rejects")
    _require(all(token in tests for token in red_team), "Task004 red-team coverage is incomplete")
    return Check(
        "fusion_schema_isolation_and_injection_shape",
        "PASS",
        {"cloud_upload_authorized": False, "durable_text_writes": 0, "model_calls": 0, "tool_calls": 0},
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
        and evidence.get("status") == "PASS_CI_SYNTH_SCOPED_FUSION_MODEL_NOT_RUN"
        and evidence.get("task_commit") == commit
        and evidence.get("source_receipt_sha256") == _source_receipt(commit),
        "Task004 evidence receipt drifted",
    )
    execution = evidence.get("execution", {})
    _require(
        all(execution.get(field) == 0 for field in ("platform_calls", "model_calls", "tool_calls", "file_reads", "network_calls", "config_writes", "secret_reads", "cloud_uploads"))
        and execution.get("real_account_execution") == "NOT_RUN",
        "Task004 evidence overclaims model or external execution",
    )
    _require(
        project.get("status")
        in {
            "stage_4_task004_fusion_injection_ci_synth_model_not_run",
            "stage_4_task005_taxonomy_classifier_ci_synth_private_gold_pending_g4_review_pending",
            "stage_4_g4_pass_ci_synth_private_gold_disabled_stage_5_task001_next",
            "stage_5_task001_notion_projection_ci_synth_pass_task002_next_real_notion_not_run",
        }
        and project.get("canonical_store") == "active_local_sqlite_logical_truth",
        "project fact drifted",
    )
    decisions = architecture.get("decisions")
    _require(isinstance(decisions, list), "architecture decisions are invalid")
    fusion = next((item for item in decisions if isinstance(item, dict) and item.get("id") == "ADR-015"), None)
    _require(
        isinstance(fusion, dict)
        and fusion.get("state") == "accepted_implementation"
        and fusion.get("implementation_state") == "deterministic_local_extractive_fusion_ephemeral_artifacts_strict_grounded_parser_prompt_isolation_zero_side_effects_ci_synth_model_not_run",
        "Fusion architecture decision drifted",
    )
    return Check(
        "evidence_and_current_facts",
        "PASS",
        {"cloud_uploads": 0, "model_execution": "NOT_RUN", "source_receipt": "verified"},
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
        raise VerificationError("Task004 acceptance runner failed")
    payloads: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    _require(payloads, "Task004 acceptance runner did not emit a receipt")
    return payloads[-1]


def validate_acceptance_execution() -> Check:
    receipt = _run_acceptance()
    execution = receipt.get("execution", {})
    _require(
        receipt.get("task_id") == TASK_ID
        and receipt.get("phase") == PHASE
        and receipt.get("status") == "PASS_CI_SYNTH_SCOPED_FUSION_MODEL_NOT_RUN"
        and receipt.get("metrics", {}).get("synthetic_unit_tests") >= 12
        and receipt.get("metrics", {}).get("same_input_duplicate_model_calls") == 0
        and receipt.get("metrics", {}).get("url_uploads") == 0
        and all(execution.get(field) == 0 for field in ("platform_calls", "model_calls", "tool_calls", "file_reads", "network_calls", "config_writes", "secret_reads", "cloud_uploads")),
        "Task004 acceptance receipt is invalid",
    )
    return Check(
        "fresh_synthetic_acceptance",
        "PASS",
        {"model_calls": 0, "tool_calls": 0, "synthetic_unit_tests": receipt["metrics"]["synthetic_unit_tests"]},
    )


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) not in {"", "main"}, "Task004 must remain in a non-main worktree")
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
