#!/usr/bin/env python3
"""Fail-closed verifier for the independent G3 Resume recheck.

This verifier evaluates the current G3 CI-synth contribution only.  It keeps
the first Stage 3 review, the Resume contract, and Task010's final evidence as
separate historical receipts; none of them are rewritten into this decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
REVIEW_ID = "STG.X2N.3.REVIEW.RESUME.RECHECK"
RUN_ID = "RUN-X2N-S03-REVIEW-RESUME-RECHECK"
TASK010_FINAL_COMMIT = "c528ff14836f116f624fa8b1ea63472a7f4b678f"
FIRST_REVIEW_FACT = PROJECT_ROOT / "machine/facts/stage_3_gate_state.json"
RESUME_FACT = PROJECT_ROOT / "machine/facts/stage_3_review_resume_state.json"
RECHECK_FACT = PROJECT_ROOT / "machine/facts/stage_3_review_resume_recheck_state.json"
RECHECK_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_3_review_resume_recheck_state.schema.json"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
PRFAQ = PROJECT_ROOT / "docs/product_design/v0.0.0.1/00_PRFAQ.md"
PRD = PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md"
ROADMAP = PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md"
RELEASE_OPERATIONS = PROJECT_ROOT / "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_REVIEW_RESUME_RECHECK.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_3_REVIEW_RESUME_RECHECK.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_stage_3_review_resume_recheck_acceptance.py"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_3/review_resume_recheck"
GATE_EVIDENCE = EVIDENCE_DIR / "G3.json"
FINDINGS_EVIDENCE = EVIDENCE_DIR / "findings.json"
VERIFICATION_EVIDENCE = EVIDENCE_DIR / "verification.json"
TASK010_EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.010.json"

FIRST_REVIEW_SHA256 = "0243a478273de9bda16803e7311ef56c7e461c2bc3b8c871c5d2c1c87cdd6772"
RESUME_FACT_SHA256 = "d9ba689978bb03525676484252e8453f75a589f7f3e97a0e6a18232de4d1d8f1"
TASK010_EVIDENCE_SHA256 = "285095437aad1a6e0c8589a2e3f65da1d611733d2010abd62f3a2693a6a5cee3"
EXPECTED_SCOPE_IDS = [
    "xiaohongshu_favorites",
    "xiaohongshu_likes",
    "douyin_favorites",
    "douyin_likes",
    "bilibili_selected_collection",
    "kuaishou_selected_collection",
    "weibo_selected_collection",
    "taobao_selected_collection",
]
EXPECTED_G3_CONDITIONS = [
    "eight independently scoped relation/list synthetic requests traverse Extension-to-Native-to-Adapter dispatch",
    "a valid complete snapshot persists exactly eight capability_gate_outcome rows, one per scope, with READY_FOR_MVP_ACTIVATION or DISABLED_EXTERNAL_GATE and deterministic fine-grained reason; any BLOCKED_TECHNICAL reason prevents the complete snapshot and leaves G3 blocked with no legal terminal",
    "checkpoint/resume and worker/companion restart reconciliation pass",
    "no empty-response deletion",
    "adapter failure durably reaches run_record failed plus one sanitized run_failure row and the Side Panel derives FALLBACK_AVAILABLE without a second run state",
    "current-page fallback requires a separate second explicit Owner action and automatic fallback count remains zero",
]
EXPECTED_FACT_CONDITIONS = {
    "eight_scope_extension_native_adapter_dispatch": "PASS_CI_SYNTH_EIGHT_SCOPES_PLATFORM_CALLS_0",
    "complete_capability_snapshot_and_technical_veto": "PASS_CI_SYNTH_EIGHT_ROWS_TECHNICAL_VETO_NO_LEGAL_TERMINAL",
    "checkpoint_resume_and_restart_reconciliation": "PASS_CI_SYNTH_COMPANION_AND_EXTENSION_RECONCILED",
    "no_empty_response_deletion": "PASS_CI_SYNTH_EMPTY_NONAUTHORITATIVE_CONTENT_AUTO_DELETE_0",
    "failed_run_and_single_explicit_fallback": "PASS_CI_SYNTH_FAILED_RUN_SANITIZED_FAILURE_SECOND_OWNER_ACTION",
    "zero_automatic_fallbacks": "PASS_CI_SYNTH_AUTOMATIC_FALLBACKS_0",
}
SAFETY_PATHS = (
    RECHECK_SCHEMA,
    RECHECK_FACT,
    TASK_STATE,
    PRFAQ,
    PRD,
    ROADMAP,
    RELEASE_OPERATIONS,
    RUN_CONTRACT,
    REPORT,
    ACCEPTANCE_RUNNER,
)


class RecheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecheckError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecheckError(f"invalid JSON: {path.name}") from error
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


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
    _require(result.returncode == 0, "local Git verification failed")
    return result.stdout.rstrip()


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
    _require(result.returncode == 0, "historical receipt blob is missing")
    return result.stdout


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_line(output: str) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            receipts.append(value)
    _require(receipts, "recheck acceptance output has no JSON receipt")
    return receipts[-1]


def _safe_payload(payload: Any, *, forbid_all_urls: bool = True) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "local user path entered recheck artifact")
    _require("github" + "_pat_" not in rendered, "credential entered recheck artifact")
    _require("Bearer" + " " not in rendered, "credential entered recheck artifact")
    if forbid_all_urls:
        _require("http://" not in rendered and "https://" not in rendered, "URL entered recheck artifact")
    cdn = re.compile(
        r"(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|alicdn)",
        flags=re.IGNORECASE,
    )
    _require(cdn.search(rendered) is None, "media CDN value entered recheck artifact")


def validate_fact_and_historical_receipts() -> Check:
    schema = _load_json(RECHECK_SCHEMA)
    fact = _load_json(RECHECK_FACT)
    _require(schema.get("$id") == "urn:x2n:stage-3-review-resume-recheck-state:1.0", "recheck schema identity drifted")
    _require(
        fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.3"
        and fact.get("review_id") == REVIEW_ID
        and fact.get("run_id") == RUN_ID
        and fact.get("recheck_base_commit") == TASK010_FINAL_COMMIT,
        "recheck fact identity drifted",
    )
    gate = fact.get("gate", {})
    _require(
        gate.get("id") == "G3"
        and gate.get("status") == "PASS_CI_SYNTH"
        and gate.get("decision") == "PASS"
        and gate.get("pass_conditions") == EXPECTED_FACT_CONDITIONS,
        "G3 pass decision or its six conditions drifted",
    )
    historical = fact.get("historical_contracts", {})
    _require(
        historical.get("first_stage_3_review")
        == {"path": "machine/facts/stage_3_gate_state.json", "sha256": FIRST_REVIEW_SHA256, "immutable": True}
        and historical.get("resume_contract")
        == {"path": "machine/facts/stage_3_review_resume_state.json", "sha256": RESUME_FACT_SHA256, "immutable": True},
        "historical receipt identity drifted",
    )
    _require(_sha256(FIRST_REVIEW_FACT) == FIRST_REVIEW_SHA256, "first G3 review was rewritten")
    _require(_sha256(RESUME_FACT) == RESUME_FACT_SHA256, "Resume contract was rewritten")
    task010 = fact.get("task_receipts", {}).get("task010", {})
    _require(
        task010 == {
            "task_id": "TSK.x2n.adapters.010",
            "final_commit": TASK010_FINAL_COMMIT,
            "evidence_path": "evidence/adapters/TSK.x2n.adapters.010.json",
            "evidence_sha256": TASK010_EVIDENCE_SHA256,
            "status": "PASS_CI_SYNTH_SCOPED_REVIEW_PENDING",
        },
        "Task010 historical receipt drifted",
    )
    _require(
        _sha256_bytes(_blob_at(TASK010_FINAL_COMMIT, TASK010_EVIDENCE)) == TASK010_EVIDENCE_SHA256,
        "Task010 final evidence blob drifted",
    )
    _require(
        fact.get("task_receipts", {}).get("task005")
        == {
            "task_id": "TSK.x2n.adapters.005",
            "acceptance_scope": "ADAPTERS_005_RELATION_RECONCILIATION_CI_SYNTH",
            "status": "PASS_CI_SYNTH_SCOPED",
        },
        "Task005 receipt attribution drifted",
    )
    _safe_payload(fact)
    return Check(
        "recheck_fact_and_historical_receipts",
        "PASS",
        {"gate": "G3", "historical_receipts": 3, "decision": "PASS_CI_SYNTH"},
    )


def validate_taskpack_and_current_transition() -> Check:
    try:
        taskpack = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RecheckError("Taskpack is unreadable") from error
    _require(isinstance(taskpack, dict) and isinstance(taskpack.get("tasks"), list), "Taskpack tasks are invalid")
    by_id = {item.get("id"): item for item in taskpack["tasks"] if isinstance(item, dict)}
    task010 = by_id.get("TSK.x2n.adapters.010", {})
    next_task = by_id.get("TSK.x2n.multimodal.001", {})
    following_task = by_id.get("TSK.x2n.multimodal.002", {})
    task003 = by_id.get("TSK.x2n.multimodal.003", {})
    task004 = by_id.get("TSK.x2n.multimodal.004", {})
    task005 = by_id.get("TSK.x2n.multimodal.005", {})
    gates = {item.get("id"): item for item in taskpack.get("stage_gates", []) if isinstance(item, dict)}
    _require(
        task010.get("status") == "completed"
        and task010.get("phase") == "PH.X2N.3.10"
        and task010.get("acceptance_ids") == ["ACC.x2n.batch.002", "ACC.x2n.ext.003", "ACC.x2n.batch.001"],
        "Task010 completion receipt no longer matches Taskpack",
    )
    _require(
        next_task.get("status") in {"planned", "completed"}
        and next_task.get("phase") == "PH.X2N.4.1"
        and "TSK.x2n.adapters.010" in next_task.get("depends_on", []),
        "Stage 4 Task001 bypasses G3 predecessor",
    )
    _require(gates.get("G3", {}).get("pass_conditions") == EXPECTED_G3_CONDITIONS, "G3 taskpack conditions drifted")
    state = _load_json(TASK_STATE)
    if next_task.get("status") == "planned":
        _require(
            state.get("last_completed_phase") == REVIEW_ID
            and state.get("review_id") == REVIEW_ID
            and state.get("run_id") == RUN_ID
            and state.get("stage") == "STG.X2N.3"
            and state.get("tasks", {}).get("TSK.x2n.adapters.010") == "pass"
            and state.get("next_phase") == "PH.X2N.4.1"
            and state.get("next_run") == "TSK.x2n.multimodal.001"
            and state.get("next_phase_authorized") is True
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "pass",
            "current task-state transition is not a bounded G3 pass",
        )
        completed_task = "TSK.x2n.adapters.010"
        next_task_id = "TSK.x2n.multimodal.001"
    elif following_task.get("status") == "planned":
        _require(
            following_task.get("status") == "planned"
            and following_task.get("phase") == "PH.X2N.4.2"
            and "TSK.x2n.multimodal.001" in following_task.get("depends_on", []),
            "Stage 4 Task002 bypasses the completed media-preprocessing Task001",
        )
        _require(
            state.get("last_completed_phase") == "PH.X2N.4.1"
            and state.get("review_id") == REVIEW_ID
            and state.get("run_id") == "RUN-X2N-S04-M001"
            and state.get("stage") == "STG.X2N.4"
            and state.get("tasks", {}).get("TSK.x2n.adapters.010") == "pass"
            and state.get("tasks", {}).get("TSK.x2n.multimodal.001") == "pass"
            and state.get("next_phase") == "PH.X2N.4.2"
            and state.get("next_run") == "TSK.x2n.multimodal.002"
            and state.get("next_phase_authorized") is True
            and state.get("stage_3_review_complete") is True
            and state.get("stage_3_remote_upload_authorized") is False
            and state.get("stage_4_authorized") is True
            and state.get("public_release_authorized") is False
            and state.get("stage_gate") == "pass"
            and state.get("current_stage_gate") == "not_run",
            "completed Task001 does not preserve the bounded G3 and Stage4 state transition",
        )
        completed_task = "TSK.x2n.multimodal.001"
        next_task_id = "TSK.x2n.multimodal.002"
    else:
        if task005.get("status") == "completed":
            _require(
                following_task.get("status") == "completed"
                and following_task.get("phase") == "PH.X2N.4.2"
                and task003.get("status") == "completed"
                and task003.get("phase") == "PH.X2N.4.3"
                and task004.get("status") == "completed"
                and task004.get("phase") == "PH.X2N.4.4"
                and task005.get("phase") == "PH.X2N.4.5"
                and task005.get("depends_on") == ["TSK.x2n.multimodal.004", "TSK.x2n.foundation.002"],
                "Stage 4 Task005 completion contract drifted",
            )
            _require(
                state.get("last_completed_phase") == "PH.X2N.4.5"
                and state.get("review_id") == REVIEW_ID
                and state.get("run_id") == "RUN-X2N-S04-M005"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get("TSK.x2n.adapters.010") == "pass"
                and all(
                    state.get("tasks", {}).get(task_id) == "pass"
                    for task_id in (
                        "TSK.x2n.multimodal.001",
                        "TSK.x2n.multimodal.002",
                        "TSK.x2n.multimodal.003",
                        "TSK.x2n.multimodal.004",
                        "TSK.x2n.multimodal.005",
                    )
                )
                and state.get("next_phase") == "G4"
                and state.get("next_run") == "G4"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_3_remote_upload_authorized") is False
                and state.get("stage_4_authorized") is True
                and state.get("public_release_authorized") is False
                and state.get("stage_gate") == "review_pending"
                and state.get("current_stage_gate") == "review_pending",
                "completed Task005 does not preserve the independent G4 review transition",
            )
            completed_task = "TSK.x2n.multimodal.005"
            next_task_id = "G4"
        elif task004.get("status") == "completed":
            _require(
                following_task.get("status") == "completed"
                and following_task.get("phase") == "PH.X2N.4.2"
                and task003.get("status") == "completed"
                and task003.get("phase") == "PH.X2N.4.3"
                and task004.get("phase") == "PH.X2N.4.4"
                and task004.get("depends_on") == ["TSK.x2n.multimodal.002", "TSK.x2n.multimodal.003"]
                and task005.get("status") == "planned"
                and task005.get("phase") == "PH.X2N.4.5"
                and "TSK.x2n.multimodal.004" in task005.get("depends_on", []),
                "Stage 4 Task005 contract drifted after completed fusion Task004",
            )
            _require(
                state.get("last_completed_phase") == "PH.X2N.4.4"
                and state.get("review_id") == REVIEW_ID
                and state.get("run_id") == "RUN-X2N-S04-M004"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get("TSK.x2n.adapters.010") == "pass"
                and all(
                    state.get("tasks", {}).get(task_id) == "pass"
                    for task_id in ("TSK.x2n.multimodal.001", "TSK.x2n.multimodal.002", "TSK.x2n.multimodal.003", "TSK.x2n.multimodal.004")
                )
                and state.get("next_phase") == "PH.X2N.4.5"
                and state.get("next_run") == "TSK.x2n.multimodal.005"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_3_remote_upload_authorized") is False
                and state.get("stage_4_authorized") is True
                and state.get("public_release_authorized") is False
                and state.get("stage_gate") == "pass"
                and state.get("current_stage_gate") == "not_run",
                "completed Task004 does not preserve the bounded G3 and Stage4 state transition",
            )
            completed_task = "TSK.x2n.multimodal.004"
            next_task_id = "TSK.x2n.multimodal.005"
        elif task003.get("status") == "completed":
            _require(
                following_task.get("status") == "completed"
                and following_task.get("phase") == "PH.X2N.4.2"
                and "TSK.x2n.multimodal.001" in following_task.get("depends_on", [])
                and task003.get("phase") == "PH.X2N.4.3"
                and "TSK.x2n.multimodal.001" in task003.get("depends_on", [])
                and task004.get("status") == "planned"
                and task004.get("phase") == "PH.X2N.4.4"
                and task004.get("depends_on") == ["TSK.x2n.multimodal.002", "TSK.x2n.multimodal.003"],
                "Stage 4 Task004 contract drifted after completed local-first OCR/Vision Task003",
            )
            _require(
                state.get("last_completed_phase") == "PH.X2N.4.3"
                and state.get("review_id") == REVIEW_ID
                and state.get("run_id") == "RUN-X2N-S04-M003"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get("TSK.x2n.adapters.010") == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.001") == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.002") == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.003") == "pass"
                and state.get("next_phase") == "PH.X2N.4.4"
                and state.get("next_run") == "TSK.x2n.multimodal.004"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_3_remote_upload_authorized") is False
                and state.get("stage_4_authorized") is True
                and state.get("public_release_authorized") is False
                and state.get("stage_gate") == "pass"
                and state.get("current_stage_gate") == "not_run",
                "completed Task003 does not preserve the bounded G3 and Stage4 state transition",
            )
            completed_task = "TSK.x2n.multimodal.003"
            next_task_id = "TSK.x2n.multimodal.004"
        else:
            _require(
                following_task.get("status") == "completed"
                and following_task.get("phase") == "PH.X2N.4.2"
                and "TSK.x2n.multimodal.001" in following_task.get("depends_on", [])
                and task003.get("status") == "planned"
                and task003.get("phase") == "PH.X2N.4.3"
                and "TSK.x2n.multimodal.001" in task003.get("depends_on", []),
                "Stage 4 Task003 contract drifted after completed local-first ASR Task002",
            )
            _require(
                state.get("last_completed_phase") == "PH.X2N.4.2"
                and state.get("review_id") == REVIEW_ID
                and state.get("run_id") == "RUN-X2N-S04-M002"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get("TSK.x2n.adapters.010") == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.001") == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.002") == "pass"
                and state.get("next_phase") == "PH.X2N.4.3"
                and state.get("next_run") == "TSK.x2n.multimodal.003"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_3_remote_upload_authorized") is False
                and state.get("stage_4_authorized") is True
                and state.get("public_release_authorized") is False
                and state.get("stage_gate") == "pass"
                and state.get("current_stage_gate") == "not_run",
                "completed Task002 does not preserve the bounded G3 and Stage4 state transition",
            )
            completed_task = "TSK.x2n.multimodal.002"
            next_task_id = "TSK.x2n.multimodal.003"
    _require(
        state.get("remote_upload") == "not_required_for_local_stage_transition"
        and state.get("current_stage_remote_upload") == "not_required_for_local_stage_transition",
        "G3 recheck authorized a remote upload",
    )
    return Check(
        "taskpack_and_current_stage_transition",
        "PASS",
        {"completed_task": completed_task, "next_task": next_task_id, "remote_upload": 0},
    )


def validate_runtime_shape() -> Check:
    sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
    sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))
    from x2n_contracts import ErrorCode  # noqa: PLC0415
    from x2n_contracts.models import CapabilityTerminal, SyncScopeId  # noqa: PLC0415
    from x2n_companion.adapter_dispatch import CapabilityRegistry, SCOPE_BINDINGS  # noqa: PLC0415
    from x2n_companion.runtime import X2NRuntimeError  # noqa: PLC0415

    _require(tuple(binding.scope_id for binding in SCOPE_BINDINGS) == tuple(SyncScopeId), "scope binding matrix drifted")
    manifest = CapabilityRegistry().evaluate(evaluated_at="2026-07-28T00:00:00Z")
    _require(
        [item.scope_id.value for item in manifest.outcomes] == EXPECTED_SCOPE_IDS
        and len(manifest.outcomes) == 8
        and all(item.terminal is CapabilityTerminal.READY_FOR_MVP_ACTIVATION for item in manifest.outcomes),
        "complete capability snapshot drifted",
    )
    technical = CapabilityRegistry().with_override(SyncScopeId.XIAOHONGSHU_FAVORITES, technical_blocked=True)
    try:
        technical.evaluate(evaluated_at="2026-07-28T00:00:00Z")
    except X2NRuntimeError as error:
        _require(error.code is ErrorCode.CAPABILITY_TECHNICAL_BLOCKED, "technical veto error drifted")
    else:
        raise RecheckError("technical veto produced a legal terminal")
    return Check(
        "eight_scope_capability_snapshot_and_technical_veto",
        "PASS",
        {"capability_rows": 8, "technical_veto_terminal_rows": 0},
    )


def validate_docs_and_public_boundary() -> Check:
    texts: list[str] = []
    for path in SAFETY_PATHS:
        _require(path.is_file(), f"required recheck control artifact missing: {path.name}")
        text = path.read_text(encoding="utf-8")
        _require(len(text.encode("utf-8")) <= 2 * 1024 * 1024, "recheck control artifact exceeds size budget")
        texts.append(text)
    combined = "\n".join(texts)
    _safe_payload({"controls": combined}, forbid_all_urls=False)
    prfaq_text = PRFAQ.read_text(encoding="utf-8")
    prd_text = PRD.read_text(encoding="utf-8")
    current_tasks = _load_json(TASK_STATE).get("tasks", {})
    task001_completed = current_tasks.get("TSK.x2n.multimodal.001") == "pass"
    task002_completed = current_tasks.get("TSK.x2n.multimodal.002") == "pass"
    task003_completed = current_tasks.get("TSK.x2n.multimodal.003") == "pass"
    task004_completed = current_tasks.get("TSK.x2n.multimodal.004") == "pass"
    task005_completed = current_tasks.get("TSK.x2n.multimodal.005") == "pass"
    if task005_completed:
        _require(
            task004_completed
            and "status: STAGE_4_TASK005_TAXONOMY_CLASSIFIER_CI_SYNTH_PRIVATE_GOLD_PENDING_G4_REVIEW_PENDING" in prfaq_text
            and "implementation_authorized: stage_4_g4_review_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK005_TAXONOMY_CLASSIFIER_CI_SYNTH_PRIVATE_GOLD_PENDING_G4_REVIEW_PENDING" in prd_text
            and "current_run_scope: stage_4_task005_complete_g4_review_next_private_gold_pending" in prd_text
            and "implementation_authorized: stage_4_g4_review_next_single_phase_run" in prd_text,
            "PRFAQ/PRD do not describe the completed taxonomy Task005 and independent G4 review",
        )
    elif task004_completed:
        _require(
            task003_completed
            and "status: STAGE_4_TASK004_FUSION_INJECTION_CI_SYNTH_MODEL_NOT_RUN" in prfaq_text
            and "implementation_authorized: stage_4_task_005_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK004_FUSION_INJECTION_CI_SYNTH_MODEL_NOT_RUN" in prd_text
            and "current_run_scope: stage_4_task004_complete_task005_next_model_not_run" in prd_text
            and "implementation_authorized: stage_4_task_005_next_single_phase_run" in prd_text,
            "PRFAQ/PRD do not describe the completed fusion Task004",
        )
    elif task003_completed:
        _require(
            "status: STAGE_4_TASK003_LOCAL_FIRST_OCR_VISION_CI_SYNTH_PRIVATE_GOLD_PENDING" in prfaq_text
            and "implementation_authorized: stage_4_task_004_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK003_LOCAL_FIRST_OCR_VISION_CI_SYNTH_PRIVATE_GOLD_PENDING" in prd_text
            and "current_run_scope: stage_4_task003_complete_task004_next_private_gold_pending" in prd_text
            and "implementation_authorized: stage_4_task_004_next_single_phase_run" in prd_text,
            "PRFAQ/PRD do not describe the completed local-first OCR/Vision Task003",
        )
    elif task002_completed:
        _require(
            "status: STAGE_4_TASK002_LOCAL_FIRST_ASR_CI_SYNTH_PRIVATE_GOLD_PENDING" in prfaq_text
            and "implementation_authorized: stage_4_task_003_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK002_LOCAL_FIRST_ASR_CI_SYNTH_PRIVATE_GOLD_PENDING" in prd_text
            and "current_run_scope: stage_4_task002_complete_task003_next_private_gold_pending" in prd_text
            and "implementation_authorized: stage_4_task_003_next_single_phase_run" in prd_text,
            "PRFAQ/PRD do not describe the completed local-first ASR Task002",
        )
    elif task001_completed:
        _require(
            "status: STAGE_4_TASK001_BOUNDED_MEDIA_PREPROCESSING_PASS_CI_SYNTH" in prfaq_text
            and "implementation_authorized: stage_4_task_002_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK001_BOUNDED_MEDIA_PREPROCESSING_PASS_CI_SYNTH" in prd_text
            and "current_run_scope: stage_4_task001_complete_task002_next" in prd_text
            and "implementation_authorized: stage_4_task_002_next_single_phase_run" in prd_text,
            "PRFAQ/PRD do not describe the completed bounded Task001",
        )
    else:
        _require(
            "status: STAGE_3_G3_PASS_STAGE_4_LOCAL_NEXT_AUTHORIZED" in prfaq_text
            and "implementation_authorized: stage_4_task_001_next_single_phase_run" in prfaq_text
            and "status: STAGE_3_G3_PASS_STAGE_4_LOCAL_NEXT_AUTHORIZED" in prd_text
            and "current_run_scope: stage_3_g3_recheck_pass_stage_4_task001_next" in prd_text
            and "implementation_authorized: stage_4_task_001_next_single_phase_run" in prd_text,
            "PRFAQ/PRD do not describe the bounded G3 pass",
        )
    for token in (
        REVIEW_ID,
        RUN_ID,
        "TSK.x2n.multimodal.001",
        "PH.X2N.4.1",
        "不上传 Stage 3",
        "不部署、不发布",
        "固定",
    ):
        _require(token in RUN_CONTRACT.read_text(encoding="utf-8"), "recheck Run Contract is incomplete")
    _require("30 日观察" in RUN_CONTRACT.read_text(encoding="utf-8"), "direct MVP no-soak boundary missing")
    return Check(
        "documents_and_public_private_boundary",
        "PASS",
        {"controls_scanned": len(SAFETY_PATHS), "sensitive_value_hits": 0, "absolute_user_paths": 0},
    )


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) != "main", "recheck must not run in main")
    _require(_git(["merge-base", "--is-ancestor", TASK010_FINAL_COMMIT, "HEAD"]) == "", "recheck does not descend from Task010 final")
    main_worktree: Path | None = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        if fields.get("branch") == "refs/heads/main":
            main_worktree = Path(fields["worktree"])
            break
    _require(main_worktree is not None, "main worktree is missing")
    _require(not _git(["status", "--porcelain=v1"], cwd=main_worktree), "main worktree is not clean")
    return Check("worktree_isolation", "PASS", {"main_worktree_clean": True, "remote_upload": 0})


def _acceptance_check() -> Check:
    result = subprocess.run(
        [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=1800,
    )
    _require(result.returncode == 0, "fresh G3 recheck acceptance failed")
    receipt = _json_line(result.stdout)
    _require(
        receipt
        == {
            "automatic_fallbacks": 0,
            "capability_gate_outcome_rows": 8,
            "checkpoint_resume_restart_reconciliation": "PASS",
            "extension_service_worker_restarts": 100,
            "failed_run_explicit_fallback": "PASS_BY_TASK010_SCOPED_ACCEPTANCE",
            "no_empty_response_deletion": "PASS",
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "review_id": REVIEW_ID,
            "run_id": RUN_ID,
            "scope_dispatches": 8,
            "stage_3_remote_upload": "NOT_RUN",
            "status": "PASS_CI_SYNTH_G3_RECHECK",
        },
        "fresh G3 recheck metrics drifted",
    )
    return Check(
        "fresh_ci_synth_g3_acceptance",
        "PASS",
        {"scope_dispatches": 8, "capability_rows": 8, "restarts": 100, "platform_calls": 0},
    )


def _evidence_payload(checks: Iterable[Check]) -> dict[str, Any]:
    check_rows = [{"name": check.name, "status": check.status, "details": check.details} for check in checks]
    return {
        "schema_version": "1.0",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "PASS_CI_SYNTH_G3_RECHECK",
        "checks": check_rows,
        "execution": {
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "stage_3_remote_upload": "NOT_RUN",
            "stage_4_executed": False,
        },
    }


def write_evidence(checks: Sequence[Check]) -> None:
    _require(all(check.status == "PASS" for check in checks), "cannot write failed G3 evidence")
    verification = _evidence_payload(checks)
    gate = {
        "schema_version": "1.0",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "gate_id": "G3",
        "status": "PASS_CI_SYNTH",
        "decision": "PASS",
        "stage_3_remote_upload_authorized": False,
        "stage_4_local_task_start_authorized": True,
        "next_task": "TSK.x2n.multimodal.001",
    }
    findings = {
        "schema_version": "1.0",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "status": "NO_OPEN_G3_BLOCKERS",
        "remaining_g3_blockers": [],
        "out_of_scope": {
            "stage_3_remote_upload": "NOT_RUN",
            "stage_4_execution": "NOT_RUN",
            "deployment": "NOT_RUN",
            "real_platform_calls": 0,
        },
    }
    for payload in (verification, gate, findings):
        _safe_payload(payload)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_EVIDENCE.write_text(json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    GATE_EVIDENCE.write_text(json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    FINDINGS_EVIDENCE.write_text(json.dumps(findings, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_evidence() -> Check:
    verification = _load_json(VERIFICATION_EVIDENCE)
    gate = _load_json(GATE_EVIDENCE)
    findings = _load_json(FINDINGS_EVIDENCE)
    for payload in (verification, gate, findings):
        _safe_payload(payload)
    _require(
        verification.get("schema_version") == "1.0"
        and verification.get("review_id") == REVIEW_ID
        and verification.get("run_id") == RUN_ID
        and verification.get("status") == "PASS_CI_SYNTH_G3_RECHECK"
        and verification.get("execution")
        == {"platform_calls": 0, "real_account_execution": "NOT_RUN", "stage_3_remote_upload": "NOT_RUN", "stage_4_executed": False}
        and all(item.get("status") == "PASS" for item in verification.get("checks", [])),
        "verification evidence drifted",
    )
    _require(
        gate
        == {
            "schema_version": "1.0",
            "review_id": REVIEW_ID,
            "run_id": RUN_ID,
            "gate_id": "G3",
            "status": "PASS_CI_SYNTH",
            "decision": "PASS",
            "stage_3_remote_upload_authorized": False,
            "stage_4_local_task_start_authorized": True,
            "next_task": "TSK.x2n.multimodal.001",
        },
        "G3 evidence drifted",
    )
    _require(
        findings.get("status") == "NO_OPEN_G3_BLOCKERS"
        and findings.get("remaining_g3_blockers") == []
        and findings.get("out_of_scope", {}).get("real_platform_calls") == 0
        and findings.get("out_of_scope", {}).get("stage_4_execution") == "NOT_RUN",
        "G3 findings evidence drifted",
    )
    return Check("g3_evidence_receipts", "PASS", {"evidence_files": 3, "platform_calls": 0})


def run_checks(*, verify_worktree: bool, run_acceptance: bool, require_evidence: bool) -> list[Check]:
    checks = [
        validate_fact_and_historical_receipts(),
        validate_taskpack_and_current_transition(),
        validate_runtime_shape(),
        validate_docs_and_public_boundary(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree())
    if run_acceptance:
        checks.append(_acceptance_check())
    if require_evidence:
        checks.append(validate_evidence())
    _require(all(check.status == "PASS" for check in checks), "G3 recheck verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the x2n independent G3 Resume recheck")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--skip-acceptance", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            run_acceptance=not args.skip_acceptance,
            require_evidence=args.require_evidence and not args.write_evidence,
        )
        if args.write_evidence:
            _require(not args.skip_acceptance, "evidence requires a fresh acceptance replay")
            write_evidence(checks)
            checks.append(validate_evidence())
        print(json.dumps({"checks": [item.name for item in checks], "review_id": REVIEW_ID, "status": "PASS"}, sort_keys=True))
        return 0
    except (OSError, RecheckError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"reason": str(error), "review_id": REVIEW_ID, "status": "FAIL_CLOSED"}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
