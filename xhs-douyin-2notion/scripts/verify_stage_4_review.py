#!/usr/bin/env python3
"""Fail-closed verifier for the independent Stage 4 G4 review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
REVIEW_ID = "STG.X2N.4.REVIEW"
RUN_ID = "RUN-X2N-S04-REVIEW"
REVIEW_BASE_COMMIT = "81a8bb7804b968f0cfa4a972c8ed5cfbfce540ae"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
REVIEW_FACT = PROJECT_ROOT / "machine/facts/stage_4_review_state.json"
REVIEW_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_4_review_state.schema.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_REVIEW.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_4_REVIEW.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_stage_4_review_acceptance.py"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_4/review"
GATE_EVIDENCE = EVIDENCE_DIR / "G4.json"
FINDINGS_EVIDENCE = EVIDENCE_DIR / "findings.json"
VERIFICATION_EVIDENCE = EVIDENCE_DIR / "verification.json"

EXPECTED_GATE_CONDITIONS = {
    "asr_ocr_vision_fusion_reports_exist": "PASS_CI_SYNTH_TASK002_TASK003_TASK004_RECEIPTS",
    "prompt_injection_suite_passes": "PASS_CI_SYNTH_TASK004",
    "ai_cannot_mutate_taxonomy": "PASS_CI_SYNTH_TASK005_OWNER_ONLY_REGISTRY",
    "automatic_classification_remains_off_unless_precision_gate_passes": "PASS_DISABLED_PENDING_PRIVATE_GOLD",
}
EXPECTED_TASKS = {
    "TSK.x2n.multimodal.001": {
        "phase": "PH.X2N.4.1",
        "task_commit": "e8e026833a6ed052d5366794f123c2f7916c5369",
        "evidence_commit": "db902304ef4231fa78f1e84109938511cac9b046",
        "evidence_path": "evidence/multimodal/TSK.x2n.multimodal.001.json",
        "evidence_sha256": "86043312c69b37077c5fe8f15d1aaa454797c30f0fd3b94a43d5fba6e4942dc2",
        "source_receipt_sha256": "6f65cb4b61e42cc1f278e20816772237f1faf5b80af4f0242e73f32d71982297",
        "status": "PASS_CI_SYNTH_SCOPED",
    },
    "TSK.x2n.multimodal.002": {
        "phase": "PH.X2N.4.2",
        "task_commit": "e16c5e3c0b145c9ff75a87b1ed3cf1c7bfa67c63",
        "evidence_commit": "60f03caa39cc2accc6e1304c743f041c84122b8c",
        "evidence_path": "evidence/models/TSK.x2n.multimodal.002.json",
        "evidence_sha256": "039150bbcd4a466ecd4a084e03811dacaa5afac09ece3eb0e0caab4018a44fa7",
        "source_receipt_sha256": "30080951c307326433620fb6526f2885f39aceffafe7584fc63200a5028ec0f3",
        "status": "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
    },
    "TSK.x2n.multimodal.003": {
        "phase": "PH.X2N.4.3",
        "task_commit": "1886bb525cfb7228b335f59f9e8ba772dc547d9a",
        "evidence_commit": "85e26fb3c85f72f848c784cb8ad615f57b79c8fd",
        "evidence_path": "evidence/models/TSK.x2n.multimodal.003.json",
        "evidence_sha256": "254631d4e72c29a4e356dc301804b33c61ed1e11d8451c2c65934a4b4a8fac78",
        "source_receipt_sha256": "9d50895a8a5d18f2517ccefc138abc3d31d0c91bafceb8b91b31ae5350be6713",
        "status": "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
    },
    "TSK.x2n.multimodal.004": {
        "phase": "PH.X2N.4.4",
        "task_commit": "439dbb587972690a4a2fce79515ff4396dd3e970",
        "evidence_commit": "0c2eb423c3dffea8a5305d3ce0640c7abb7935b4",
        "evidence_path": "evidence/models/TSK.x2n.multimodal.004.json",
        "evidence_sha256": "e104f2c58a34afac50e3e7e8266e4a0105f6f8ef75053f5ffc9df6e8bf2912c8",
        "source_receipt_sha256": "de39d9e51f340e313d03e4fce2650a7db3767c35dbfd8debb1eb29da899c707e",
        "status": "PASS_CI_SYNTH_SCOPED_FUSION_MODEL_NOT_RUN",
    },
    "TSK.x2n.multimodal.005": {
        "phase": "PH.X2N.4.5",
        "task_commit": "55474c16ba333c9cd1ab63dc505906ef93382ed6",
        "evidence_commit": REVIEW_BASE_COMMIT,
        "evidence_path": "evidence/models/TSK.x2n.multimodal.005.json",
        "evidence_sha256": "7448f37bb2b9146b095c1bd1cd820c97a8447c066c8370aa1d8a58c642c856b7",
        "source_receipt_sha256": "a7858b2c70e61d37483fc39d4c51e0f333c88f8eb47874466ea9659c65d6cfe9",
        "status": "PASS_CI_SYNTH_SCOPED_PRIVATE_GOLD_PENDING",
    },
}
REVIEW_SOURCE_PATHS = (
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "HANDOFF.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S04_REVIEW.md",
    PROJECT_ROOT / "docs/governance/STAGE_4_REVIEW.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    PROJECT_ROOT / "machine/facts/architecture_decisions.json",
    PROJECT_ROOT / "machine/facts/project.json",
    PROJECT_ROOT / "machine/facts/stage_4_review_state.json",
    PROJECT_ROOT / "machine/facts/task_state.json",
    PROJECT_ROOT / "machine/schemas/stage_4_review_state.schema.json",
    PROJECT_ROOT / "scripts/run_stage_4_review_acceptance.py",
    PROJECT_ROOT / "scripts/verify_adapters_010.py",
    PROJECT_ROOT / "scripts/verify_multimodal_001.py",
    PROJECT_ROOT / "scripts/verify_multimodal_002.py",
    PROJECT_ROOT / "scripts/verify_multimodal_003.py",
    PROJECT_ROOT / "scripts/verify_multimodal_004.py",
    PROJECT_ROOT / "scripts/verify_multimodal_005.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume.py",
    PROJECT_ROOT / "scripts/verify_stage_3_review_resume_recheck.py",
    PROJECT_ROOT / "scripts/verify_stage_4_review.py",
    PROJECT_ROOT / "功能清单.md",
    PROJECT_ROOT / "开发记录.md",
)
ALLOWED_REVIEW_SOURCE_PATHS = frozenset(path.relative_to(PROJECT_ROOT).as_posix() for path in REVIEW_SOURCE_PATHS)
SAFETY_PATHS = (
    REVIEW_FACT,
    REVIEW_SCHEMA,
    RUN_CONTRACT,
    REPORT,
    ACCEPTANCE_RUNNER,
    PROJECT_FACT,
    ARCHITECTURE,
    TASK_STATE,
)


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"invalid JSON: {path.name}") from error
    _require(isinstance(payload, dict), f"JSON object required: {path.name}")
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
    _require(result.returncode == 0, "historical review source blob is missing")
    return result.stdout


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source_receipt(commit: str) -> str:
    digest = hashlib.sha256()
    for path in REVIEW_SOURCE_PATHS:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_blob_at(commit, path))
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_payload(payload: Any) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "local user path entered public review artifact")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential entered public review artifact")
    _require(
        re.search(r"(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|tbcdn|alicdn)", rendered, re.I)
        is None,
        "platform media CDN value entered public review artifact",
    )


def _taskpack() -> dict[str, Any]:
    try:
        value = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ReviewError("Taskpack is unreadable") from error
    _require(isinstance(value, dict), "Taskpack must be an object")
    return value


def _stage4_review_transition(state: dict[str, Any]) -> bool:
    return (
        state.get("stage") == "STG.X2N.5"
        and state.get("last_completed_phase") == REVIEW_ID
        and state.get("review_id") == REVIEW_ID
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "stage_gate_review_ci_synth_multimodal_taxonomy"
        and state.get("state") == "stage_4_g4_pass_ci_synth_stage_5_task001_next_private_gold_disabled"
        and state.get("next_phase") == "PH.X2N.5.1"
        and state.get("next_run") == "TSK.x2n.uxops.001"
        and state.get("next_phase_authorized") is True
        and state.get("stage_gate") == "pass"
        and state.get("current_stage_gate") == "not_run"
        and state.get("stage_4_review_complete") is True
        and state.get("stage_4_gate_status") == "pass_ci_synth"
        and state.get("stage_4_remote_upload_authorized") is False
        and state.get("stage_5_authorized") is True
        and state.get("remote_upload") == "not_required_for_local_stage_transition"
        and state.get("current_stage_remote_upload") == "not_required_for_local_stage_transition"
        and state.get("public_release_authorized") is False
    )


def validate_review_fact_and_task_receipts() -> Check:
    schema = _load_json(REVIEW_SCHEMA)
    fact = _load_json(REVIEW_FACT)
    _require(schema.get("$id") == "urn:x2n:stage-4-review-state:1.0", "G4 review schema identity drifted")
    _require(
        fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.4"
        and fact.get("review_id") == REVIEW_ID
        and fact.get("run_id") == RUN_ID
        and fact.get("review_base_commit") == REVIEW_BASE_COMMIT,
        "G4 review fact identity drifted",
    )
    gate = fact.get("gate", {})
    _require(
        gate.get("id") == "G4"
        and gate.get("status") == "PASS_CI_SYNTH"
        and gate.get("decision") == "PASS"
        and gate.get("pass_conditions") == EXPECTED_GATE_CONDITIONS,
        "G4 decision or conditions drifted",
    )
    receipts = fact.get("task_receipts")
    _require(receipts == EXPECTED_TASKS, "Stage 4 fixed task receipts drifted")
    for task_id, expected in EXPECTED_TASKS.items():
        evidence_path = PROJECT_ROOT / expected["evidence_path"]
        evidence_blob = _blob_at(expected["evidence_commit"], evidence_path)
        _require(
            _sha256_bytes(evidence_blob) == expected["evidence_sha256"],
            f"{task_id} evidence blob changed",
        )
        evidence = json.loads(evidence_blob.decode("utf-8"))
        _require(
            evidence.get("task_id") == task_id
            and evidence.get("phase") == expected["phase"]
            and evidence.get("task_commit") == expected["task_commit"]
            and evidence.get("source_receipt_sha256") == expected["source_receipt_sha256"]
            and evidence.get("status") == expected["status"],
            f"{task_id} immutable receipt is invalid",
        )
        _git(["cat-file", "-e", f"{expected['task_commit']}^{{commit}}"])
    execution = fact.get("execution", {})
    _require(
        execution
        == {
            "evidence_class": "INDEPENDENT_LOCAL_CI_SYNTH_REVIEW",
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "owner_profile_login": "NOT_RUN",
            "notion_real_calls": 0,
            "model_calls": 0,
            "private_gold_evaluation": "NOT_RUN",
            "automatic_classification_writes": 0,
            "stage_4_remote_upload": "NOT_RUN",
            "deployment": "NOT_RUN",
        },
        "G4 execution boundary drifted",
    )
    _require(
        fact.get("authorization")
        == {
            "new_dag_task_executed": False,
            "stage_4_remote_upload": False,
            "stage_5_local_task_start": True,
            "public_release": False,
            "deployment": False,
        },
        "G4 authorization drifted",
    )
    _safe_payload(fact)
    return Check(
        "review_fact_and_immutable_task_receipts",
        "PASS",
        {"gate": "G4", "task_receipts": len(EXPECTED_TASKS), "private_gold": "NOT_RUN"},
    )


def validate_taskpack_and_current_transition() -> Check:
    taskpack = _taskpack()
    tasks = {item.get("id"): item for item in taskpack.get("tasks", []) if isinstance(item, dict)}
    gates = {item.get("id"): item for item in taskpack.get("stage_gates", []) if isinstance(item, dict)}
    _require(
        all(
            tasks.get(task_id, {}).get("status") == "completed"
            and tasks[task_id].get("phase") == expected["phase"]
            for task_id, expected in EXPECTED_TASKS.items()
        ),
        "Stage 4 task completion contract drifted",
    )
    _require(
        gates.get("G4", {}).get("requires_tasks") == list(EXPECTED_TASKS)
        and gates.get("G4", {}).get("pass_conditions")
        == [
            "ASR/OCR/Vision/Fusion reports exist",
            "prompt-injection suite passes",
            "AI cannot mutate taxonomy",
            "automatic classification remains off unless precision gate passes",
        ],
        "G4 Taskpack contract drifted",
    )
    next_task = tasks.get("TSK.x2n.uxops.001", {})
    _require(
        next_task.get("status") == "planned"
        and next_task.get("phase") == "PH.X2N.5.1"
        and "TSK.x2n.multimodal.005" in next_task.get("depends_on", []),
        "Stage 5 next task bypasses G4 taxonomy predecessor",
    )
    state = _load_json(TASK_STATE)
    _require(
        _stage4_review_transition(state)
        and all(state.get("tasks", {}).get(task_id) == "pass" for task_id in EXPECTED_TASKS)
        and state.get("previous_stage_gate")
        == {"gate_id": "G3", "remote_upload": "not_uploaded", "stage": "STG.X2N.3", "status": "pass"}
        and state.get("completed_stage_gate")
        == {"gate_id": "G4", "remote_upload": "not_uploaded", "stage": "STG.X2N.4", "status": "pass"},
        "current state is not the bounded G4-to-Stage5 transition",
    )
    statuses = state.get("acceptance_status", {})
    _require(
        statuses.get("ACC.x2n.ai.001") == "pending_private_gold_asr_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.002") == "pending_private_gold_ocr_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.003") == "pending_private_gold_vision_disabled_ci_synth_contract_pass"
        and statuses.get("ACC.x2n.ai.004") == "pass_ci_synth_fusion_schema_injection_isolation_model_not_run"
        and statuses.get("ACC.x2n.ai.005") == "pass_ci_synth_owner_taxonomy_registry_revision_review_suggestion_only"
        and statuses.get("ACC.x2n.ai.006") == "pending_private_gold_classification_suggestion_only_ci_contract_pass"
        and statuses.get("ACC.x2n.ai.007") == "pass_ci_synth_task005_provenance_cache_budget_cloud_zero",
        "G4 changed a Stage 4 Acceptance boundary",
    )
    return Check(
        "taskpack_and_stage4_transition",
        "PASS",
        {"next_task": "TSK.x2n.uxops.001", "stage_4_remote_upload": 0, "stage_5_authorized": True},
    )


def validate_public_private_boundary() -> Check:
    texts: list[str] = []
    for path in SAFETY_PATHS:
        _require(path.is_file(), f"review control artifact missing: {path.name}")
        payload = path.read_text(encoding="utf-8")
        _require(len(payload.encode("utf-8")) <= 2 * 1024 * 1024, "review control artifact exceeds size budget")
        texts.append(payload)
    _safe_payload({"controls": "\n".join(texts)})
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    _require(
        project.get("status") == "stage_4_g4_pass_ci_synth_private_gold_disabled_stage_5_task001_next"
        and project.get("stage_4_current_task")
        == "G4_pass_ci_synth_private_gold_disabled_stage_5_task001_next"
        and project.get("canonical_store") == "active_local_sqlite_logical_truth"
        and project.get("taxonomy_classification")
        == "owner_registry_append_only_revisions_constrained_deterministic_local_suggestion_only_review_private_gold_oracle_auto_classify_disabled_pending_private_gold",
        "project fact overclaims G4 capability",
    )
    _require(
        architecture.get("phase") == REVIEW_ID
        and architecture.get("status") == "stage_4_g4_pass_ci_synth_private_gold_disabled_stage_5_task001_next"
        and architecture.get("review_id") == REVIEW_ID
        and architecture.get("stage_gate") == "g4_pass_ci_synth_stage5_authorized_private_gold_disabled",
        "architecture fact overclaims G4 capability",
    )
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REPORT.read_text(encoding="utf-8")
    for token in (
        REVIEW_ID,
        RUN_ID,
        "DISABLED_PENDING_PRIVATE_GOLD",
        "不上传 Stage 4",
        "不部署、不发布",
        "Alpha、Beta、固定健康观察或 soak",
    ):
        _require(token in contract or token in report, "G4 public run boundary is incomplete")
    return Check(
        "documents_and_public_private_boundary",
        "PASS",
        {"controls_scanned": len(SAFETY_PATHS), "absolute_user_paths": 0, "sensitive_value_hits": 0},
    )


def validate_historical_task_and_g3_compatibility() -> Check:
    commands = (
        ("scripts/verify_multimodal_001.py", "--verify-worktree"),
        ("scripts/verify_multimodal_002.py", "--verify-worktree"),
        ("scripts/verify_multimodal_003.py", "--verify-worktree"),
        ("scripts/verify_multimodal_004.py", "--verify-worktree"),
        ("scripts/verify_multimodal_005.py", "--verify-worktree"),
        ("scripts/verify_adapters_010.py", "--verify-worktree", "--require-evidence"),
        ("scripts/verify_stage_3_review_resume_recheck.py", "--verify-worktree", "--skip-acceptance", "--require-evidence"),
        ("scripts/verify_stage_3_review_resume.py", "--require-evidence"),
    )
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-B", *command],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=360,
        )
        _require(result.returncode == 0, "a fixed Stage 4 or G3 verifier failed")
    return Check(
        "historical_task_and_g3_compatibility",
        "PASS",
        {"historical_verifiers": len(commands), "stage_3_remote_upload": 0, "platform_calls": 0},
    )


def _json_line(output: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    _require(values, "G4 acceptance emitted no JSON receipt")
    return values[-1]


def validate_fresh_acceptance() -> Check:
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
    _require(result.returncode == 0, "fresh G4 acceptance failed")
    receipt = _json_line(result.stdout)
    execution = receipt.get("execution", {})
    _require(
        receipt.get("schema_version") == "1.0"
        and receipt.get("review_id") == REVIEW_ID
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == "PASS_CI_SYNTH_G4_REVIEW"
        and set(receipt.get("task_receipts", {})) == set(EXPECTED_TASKS)
        and receipt.get("metrics", {}).get("task_reports") == 5
        and receipt.get("metrics", {}).get("stage_4_synthetic_unit_tests", 0) >= 84
        and receipt.get("metrics", {}).get("prompt_injection_synthetic_tests", 0) >= 12
        and receipt.get("gate_conditions")
        == {
            "ai_taxonomy_mutations": 0,
            "asr_ocr_vision_fusion_reports": "PASS_CI_SYNTH_FOUR_REPORTS",
            "automatic_classification": "DISABLED_PENDING_PRIVATE_GOLD",
            "prompt_injection_suite": "PASS_CI_SYNTH_TASK004",
        }
        and execution
        == {
            "automatic_classification_writes": 0,
            "model_calls": 0,
            "notion_calls": 0,
            "platform_calls": 0,
            "private_gold_evaluation": "NOT_RUN",
            "real_account_execution": "NOT_RUN",
            "stage_4_remote_upload": "NOT_RUN",
        },
        "fresh G4 acceptance receipt drifted",
    )
    return Check(
        "fresh_ci_synth_g4_acceptance",
        "PASS",
        {
            "prompt_injection_tests": receipt["metrics"]["prompt_injection_synthetic_tests"],
            "synthetic_unit_tests": receipt["metrics"]["stage_4_synthetic_unit_tests"],
            "platform_calls": 0,
        },
    )


def validate_worktree() -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) not in {"", "main"}, "G4 review must run in a non-main worktree")
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", REVIEW_BASE_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "G4 review does not descend from the Task005 evidence receipt",
    )
    return Check("worktree_isolation", "PASS", {"main_mutated": False, "task_worktree": True})


def validate_evidence() -> Check:
    gate = _load_json(GATE_EVIDENCE)
    findings = _load_json(FINDINGS_EVIDENCE)
    verification = _load_json(VERIFICATION_EVIDENCE)
    for payload in (gate, findings, verification):
        _safe_payload(payload)
    review_commit = gate.get("review_commit")
    _require(isinstance(review_commit, str) and re.fullmatch(r"[0-9a-f]{40}", review_commit) is not None, "G4 review commit is invalid")
    _git(["cat-file", "-e", f"{review_commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", REVIEW_BASE_COMMIT, review_commit],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "G4 review commit does not descend from its fixed base",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", review_commit, "HEAD"],
            cwd=REPOSITORY_ROOT,
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer contains the G4 review commit",
    )
    changed = [path for path in _git(["diff", "--name-only", "-z", f"{REVIEW_BASE_COMMIT}..{review_commit}"]).split("\0") if path]
    relative: list[str] = []
    for path in changed:
        prefix = "xhs-douyin-2notion/"
        _require(path.startswith(prefix), "G4 review source escaped the child project")
        relative.append(path.removeprefix(prefix))
    _require(changed and set(relative) == ALLOWED_REVIEW_SOURCE_PATHS, "G4 review source scope drifted")
    _require(
        gate
        == {
            "schema_version": "1.0",
            "review_id": REVIEW_ID,
            "run_id": RUN_ID,
            "gate_id": "G4",
            "status": "PASS_CI_SYNTH",
            "decision": "PASS",
            "review_base_commit": REVIEW_BASE_COMMIT,
            "review_commit": review_commit,
            "review_source_receipt_sha256": _source_receipt(review_commit),
            "stage_4_review_state_sha256": _sha256_bytes(_blob_at(review_commit, REVIEW_FACT)),
            "stage_4_remote_upload_authorized": False,
            "stage_5_local_task_start_authorized": True,
            "next_task": "TSK.x2n.uxops.001",
        },
        "G4 evidence receipt drifted",
    )
    _require(
        verification.get("schema_version") == "1.0"
        and verification.get("review_id") == REVIEW_ID
        and verification.get("run_id") == RUN_ID
        and verification.get("status") == "PASS_CI_SYNTH_G4_REVIEW"
        and verification.get("execution")
        == {
            "automatic_classification_writes": 0,
            "model_calls": 0,
            "platform_calls": 0,
            "private_gold_evaluation": "NOT_RUN",
            "real_account_execution": "NOT_RUN",
            "stage_4_remote_upload": "NOT_RUN",
            "stage_5_executed": False,
        }
        and all(item.get("status") == "PASS" for item in verification.get("checks", [])),
        "G4 verification evidence drifted",
    )
    _require(
        findings.get("status") == "NO_OPEN_G4_STAGE_TRANSITION_BLOCKERS"
        and findings.get("remaining_non_blocking_disabled_capabilities")
        == ["asr_private_gold", "ocr_private_gold", "vision_private_gold", "classification_private_gold"]
        and findings.get("out_of_scope", {}).get("stage_4_remote_upload") == "NOT_RUN"
        and findings.get("out_of_scope", {}).get("stage_5_execution") == "NOT_RUN"
        and findings.get("out_of_scope", {}).get("real_platform_calls") == 0,
        "G4 findings evidence drifted",
    )
    return Check("g4_evidence_receipts", "PASS", {"evidence_files": 3, "review_source": "verified"})


def run_checks(*, verify_worktree: bool, run_acceptance: bool, require_evidence: bool) -> list[Check]:
    checks = [
        validate_review_fact_and_task_receipts(),
        validate_taskpack_and_current_transition(),
        validate_public_private_boundary(),
        validate_historical_task_and_g3_compatibility(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree())
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.append(validate_evidence())
    _require(all(check.status == "PASS" for check in checks), "G4 review verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the x2n independent Stage 4 G4 review")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--run-acceptance", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--print-source-receipt", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.print_source_receipt:
            commit = _git(["rev-parse", "HEAD"])
            print(
                json.dumps(
                    {
                        "review_commit": commit,
                        "review_source_receipt_sha256": _source_receipt(commit),
                        "stage_4_review_state_sha256": _sha256_bytes(_blob_at(commit, REVIEW_FACT)),
                    },
                    sort_keys=True,
                )
            )
            return 0
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            run_acceptance=args.run_acceptance,
            require_evidence=args.require_evidence,
        )
        print(
            json.dumps(
                {
                    "checks": [{"details": item.details, "name": item.name, "status": item.status} for item in checks],
                    "review_id": REVIEW_ID,
                    "status": "PASS",
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ReviewError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"reason": str(error), "review_id": REVIEW_ID, "status": "FAIL_CLOSED"}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
