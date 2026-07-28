#!/usr/bin/env python3
"""Fail-closed verifier for the independent Stage 5 G5 review."""

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
from typing import Any, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
REVIEW_ID = "STG.X2N.5.REVIEW"
RUN_ID = "RUN-X2N-S05-REVIEW"
REVIEW_BASE_COMMIT = "645ab212eb2e5d7d0e9aeac3c6d2c73804de346c"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
G4_FACT = PROJECT_ROOT / "machine/facts/stage_4_review_state.json"
REVIEW_FACT = PROJECT_ROOT / "machine/facts/stage_5_review_state.json"
REVIEW_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_5_review_state.schema.json"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S05_REVIEW.md"
REPORT = PROJECT_ROOT / "docs/governance/STAGE_5_REVIEW.md"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_stage_5_review_acceptance.py"
HISTORICAL_REPLAY = PROJECT_ROOT / "scripts/replay_uxops_005_historical.py"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_5/review"
GATE_EVIDENCE = EVIDENCE_DIR / "G5.json"
FINDINGS_EVIDENCE = EVIDENCE_DIR / "findings.json"
VERIFICATION_EVIDENCE = EVIDENCE_DIR / "verification.json"
G4_EVIDENCE_COMMIT = "4dc64a0b191fc3c1188df41c2eb22cdd9350415f"
G4_EVIDENCE_PATH = PROJECT_ROOT / "machine/evidence/stage_4/review/G4.json"
G4_EVIDENCE_SHA256 = "e69248102a75e4b3183c77a3cf1fdf62557f74e6019bdfe4c691542ae3fdb5d1"
PLATFORM_CDN_PATTERN = re.compile(
    "|".join(
        re.escape("".join(parts))
        for parts in (
            ("xhs", "cdn"),
            ("douyin", "vod"),
            ("byte", "img"),
            ("pstat", "p"),
            ("bili", "video"),
            ("hd", "slb"),
            ("ks", "cdn"),
            ("yx", "imgs"),
            ("sina", "img"),
            ("tb", "cdn"),
            ("ali", "cdn"),
        )
    ),
    re.I,
)

EXPECTED_CONDITIONS = {
    "notion_eventually_consistent_or_disabled": "PASS_CI_SYNTH_MOCK_RECONCILE_REAL_NOTION_NOT_RUN",
    "markdown_full_rebuild_deterministic": "PASS_CI_SYNTH_TEN_THOUSAND_REBUILD_SECOND_WRITE_ZERO",
    "review_and_diagnostics_usable": "PASS_CI_SYNTH_LOOPBACK_REVIEW_REDACTED_DOCTOR_RECOVERY",
    "export_delete_backup_behavior_verified": "PASS_CI_SYNTH_DOMAIN_ARCHIVE_RESTORE_TOMBSTONE_TTL",
}
EXPECTED_TASKS = {
    "TSK.x2n.uxops.001": {
        "phase": "PH.X2N.5.1",
        "task_commit": "5eaf99396f8cbbb06dce4a1620a64c8ab2eb957a",
        "evidence_commit": "7a75a2f91b8faf12f0181bc8cdcb2dc4ae901c96",
        "evidence_path": "evidence/sinks/TSK.x2n.uxops.001.json",
        "evidence_sha256": "202715ca1a5d223cff099566470fadc76cf9c6d20120e240537fc28e7cdcd7ee",
        "status": "PASS_CI_SYNTH_MOCK_SCOPED_REAL_NOTION_NOT_RUN",
        "taskpack_status": "completed",
        "acceptance_ids": (
            "ACC.x2n.notion.001",
            "ACC.x2n.notion.002",
            "ACC.x2n.notion.003",
            "ACC.x2n.notion.004",
        ),
    },
    "TSK.x2n.uxops.002": {
        "phase": "PH.X2N.5.2",
        "task_commit": "756faf0aec1f69a5a70af37719a4fda85f1eba77",
        "evidence_commit": "ab1839184976cad6a3a128350b8d4c498c452ae7",
        "evidence_path": "evidence/sinks/TSK.x2n.uxops.002.json",
        "evidence_sha256": "7bc0375af69394e9abd0a8c442662d97752244c00fed494c351a1fbf7763fea7",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "taskpack_status": "completed",
        "acceptance_ids": ("ACC.x2n.md.001", "ACC.x2n.md.002"),
    },
    "TSK.x2n.uxops.003": {
        "phase": "PH.X2N.5.3",
        "task_commit": "dc5aae0bba9ef0e93a7a024766e3285b31e89995",
        "evidence_commit": "7f78c3074880d887a683fa9cb2ed8b0477dc414c",
        "evidence_path": "evidence/ui/TSK.x2n.uxops.003.json",
        "evidence_sha256": "d75187cee428850736e9cb1fb3ad26a6370180e016b5c04d181fe1e256898edb",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "taskpack_status": "complete_ci_synth",
        "acceptance_ids": ("ACC.x2n.ext.001", "ACC.x2n.ai.005", "ACC.x2n.ai.006", "ACC.x2n.ops.004"),
    },
    "TSK.x2n.uxops.004": {
        "phase": "PH.X2N.5.4",
        "task_commit": "0ad6a63741015df2a3d4397e2adb64f2565fcc87",
        "evidence_commit": "798e2693a8255030c19f17572b55392c2d4f5f07",
        "evidence_path": "evidence/operations/TSK.x2n.uxops.004.json",
        "evidence_sha256": "c9a80ec800f6aa867ec9c50825bfe493158dda9fd3c4a98eea9c67ea26a21c8e",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "taskpack_status": "complete_ci_synth",
        "acceptance_ids": ("ACC.x2n.ops.001", "ACC.x2n.ops.002", "ACC.x2n.ops.004"),
    },
    "TSK.x2n.uxops.005": {
        "phase": "PH.X2N.5.5",
        "task_commit": "83bd9b3cfd3a01747e2bd077823beeb4afdc7f48",
        "evidence_commit": REVIEW_BASE_COMMIT,
        "evidence_path": "evidence/lifecycle/TSK.x2n.uxops.005.json",
        "evidence_sha256": "674ecac11e4947c66b795cba1a75325ba42f8cddc41bfd3862eded1d0ae34894",
        "status": "PASS_CI_SYNTH_SCOPED_REAL_RUNTIME_NOT_RUN",
        "taskpack_status": "complete_ci_synth",
        "acceptance_ids": ("ACC.x2n.gov.002", "ACC.x2n.media.002", "ACC.x2n.ops.003", "ACC.x2n.data.004"),
    },
}
REVIEW_SOURCE_PATHS = (
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "HANDOFF.md",
    PROJECT_ROOT / "README.md",
    RUN_CONTRACT,
    REPORT,
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/00_PRFAQ.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md",
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
    ARCHITECTURE,
    PROJECT_FACT,
    REVIEW_FACT,
    TASK_STATE,
    REVIEW_SCHEMA,
    ACCEPTANCE_RUNNER,
    HISTORICAL_REPLAY,
    PROJECT_ROOT / "scripts/verify_stage_5_review.py",
    PROJECT_ROOT / "功能清单.md",
    PROJECT_ROOT / "开发记录.md",
)
SOURCE_CHANGED_EXACT = frozenset(path.relative_to(PROJECT_ROOT).as_posix() for path in REVIEW_SOURCE_PATHS)
CURRENT_ALLOWED_EXACT = SOURCE_CHANGED_EXACT | {
    "machine/evidence/stage_5/review/G5.json",
    "machine/evidence/stage_5/review/findings.json",
    "machine/evidence/stage_5/review/verification.json",
}


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
        raise ReviewError("local Git verification failed")
    return result.stdout.strip()


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
    if result.returncode != 0:
        raise ReviewError("historical review source blob is missing")
    return result.stdout


def _sha256(value: bytes) -> str:
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
    _require("/" + "Users/" not in rendered and "/" + "home/" not in rendered, "local path entered public review artifact")
    _require("github" + "_pat_" not in rendered and "Bearer" + " " not in rendered, "credential entered public review artifact")
    _require(PLATFORM_CDN_PATTERN.search(rendered) is None, "platform media CDN value entered public review artifact")


def _scope_name(path: str) -> str | None:
    prefix = "xhs-douyin-2notion/"
    return path.removeprefix(prefix) if path.startswith(prefix) else None


def _taskpack() -> dict[str, Any]:
    try:
        payload = yaml.safe_load(TASKPACK.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ReviewError("Taskpack is unreadable") from error
    _require(isinstance(payload, dict), "Taskpack must be an object")
    return payload


def _g5_state_expected(state: dict[str, Any]) -> bool:
    return (
        state.get("schema_version") == "1.41"
        and state.get("stage") == "STG.X2N.6"
        and state.get("phase") == "G5"
        and state.get("last_completed_phase") == "G5"
        and state.get("review_id") == REVIEW_ID
        and state.get("run_id") == RUN_ID
        and state.get("run_kind") == "stage_gate_review_ci_synth_operability_lifecycle"
        and state.get("state") == "stage_5_g5_pass_ci_synth_stage_6_assurance001_next_real_runtime_not_run"
        and state.get("next_phase") == "PH.X2N.6.1"
        and state.get("next_run") == "TSK.x2n.assurance.001"
        and state.get("next_task") == "TSK.x2n.assurance.001"
        and state.get("next_phase_authorized") is True
        and state.get("stage_gate") == "pass"
        and state.get("current_stage_gate") == "not_run"
        and state.get("stage_5_review_complete") is True
        and state.get("stage_5_gate_status") == "pass_ci_synth"
        and state.get("stage_5_remote_upload_authorized") is False
        and state.get("stage_6_authorized") is True
        and state.get("stage_6_remote_upload_authorized") is False
        and state.get("public_release_authorized") is False
    )


def validate_review_fact_and_task_receipts() -> Check:
    schema = _load_json(REVIEW_SCHEMA)
    fact = _load_json(REVIEW_FACT)
    _require(schema.get("$id") == "urn:x2n:stage-5-review-state:1.0", "G5 review schema identity drifted")
    _require(
        fact.get("schema_version") == "1.0"
        and fact.get("project") == "x2n"
        and fact.get("stage") == "STG.X2N.5"
        and fact.get("review_id") == REVIEW_ID
        and fact.get("run_id") == RUN_ID
        and fact.get("review_base_commit") == REVIEW_BASE_COMMIT,
        "G5 review fact identity drifted",
    )
    gate = fact.get("gate")
    _require(
        isinstance(gate, dict)
        and gate.get("id") == "G5"
        and gate.get("status") == "PASS_CI_SYNTH"
        and gate.get("decision") == "PASS"
        and gate.get("pass_conditions") == EXPECTED_CONDITIONS,
        "G5 decision or conditions drifted",
    )
    expected_receipts = {
        task_id: {key: value for key, value in expected.items() if key not in {"taskpack_status", "acceptance_ids"}}
        for task_id, expected in EXPECTED_TASKS.items()
    }
    _require(fact.get("task_receipts") == expected_receipts, "Stage 5 fixed task receipts drifted")
    for task_id, expected in EXPECTED_TASKS.items():
        evidence_path = PROJECT_ROOT / expected["evidence_path"]
        evidence_blob = _blob_at(expected["evidence_commit"], evidence_path)
        _require(_sha256(evidence_blob) == expected["evidence_sha256"], f"{task_id} evidence blob changed")
        evidence = json.loads(evidence_blob.decode("utf-8"))
        _require(
            evidence.get("task_id") == task_id
            and evidence.get("phase") == expected["phase"]
            and evidence.get("task_commit") == expected["task_commit"]
            and evidence.get("status") == expected["status"],
            f"{task_id} immutable receipt is invalid",
        )
        _git(("cat-file", "-e", f"{expected['task_commit']}^{{commit}}"))
    _require(
        fact.get("execution")
        == {
            "evidence_class": "INDEPENDENT_LOCAL_CI_SYNTH_REVIEW",
            "external_network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "notion_real_calls": 0,
            "private_database_client_calls": 0,
            "tmutil_calls": 0,
            "physical_delete_execution": "NOT_RUN",
            "stage_5_remote_upload": "NOT_RUN",
            "deployment": "NOT_RUN",
        },
        "G5 execution boundary drifted",
    )
    _require(
        fact.get("authorization")
        == {
            "new_dag_task_executed": False,
            "stage_5_remote_upload": False,
            "stage_6_assurance001_start": True,
            "public_release": False,
            "deployment": False,
        },
        "G5 authorization drifted",
    )
    _safe_payload(fact)
    return Check("review_fact_and_immutable_task_receipts", "PASS", {"gate": "G5", "task_receipts": len(EXPECTED_TASKS)})


def validate_taskpack_and_state_transition() -> Check:
    taskpack = _taskpack()
    tasks = {item.get("id"): item for item in taskpack.get("tasks", []) if isinstance(item, dict)}
    gates = {item.get("id"): item for item in taskpack.get("stage_gates", []) if isinstance(item, dict)}
    for task_id, expected in EXPECTED_TASKS.items():
        task = tasks.get(task_id)
        _require(
            isinstance(task, dict)
            and task.get("phase") == expected["phase"]
            and task.get("status") == expected["taskpack_status"]
            and tuple(task.get("acceptance_ids", [])) == expected["acceptance_ids"],
            "Stage 5 Taskpack contract drifted",
        )
    _require(
        gates.get("G5")
        == {
            "id": "G5",
            "after_stage": "STG.X2N.5",
            "requires_tasks": list(EXPECTED_TASKS),
            "pass_conditions": [
                "Notion is eventually consistent or disabled",
                "Markdown full rebuild deterministic",
                "review and diagnostics usable",
                "export/delete/backup behavior verified",
            ],
        },
        "G5 Taskpack contract drifted",
    )
    assurance = tasks.get("TSK.x2n.assurance.001")
    _require(
        isinstance(assurance, dict)
        and assurance.get("phase") == "PH.X2N.6.1"
        and assurance.get("status") == "planned"
        and "TSK.x2n.uxops.005" in assurance.get("depends_on", []),
        "Stage 6 entry task drifted",
    )
    state = _load_json(TASK_STATE)
    _require(
        _g5_state_expected(state)
        and all(state.get("tasks", {}).get(task_id) == "pass" for task_id in EXPECTED_TASKS)
        and state.get("completed_stage_gate")
        == {"gate_id": "G4", "remote_upload": "not_uploaded", "stage": "STG.X2N.4", "status": "pass"},
        "G5 state transition is invalid",
    )
    return Check("taskpack_and_g5_transition", "PASS", {"next_task": "TSK.x2n.assurance.001", "stage_6_authorized": True})


def validate_g4_preservation() -> Check:
    fact = _load_json(G4_FACT)
    gate = fact.get("gate")
    _require(
        isinstance(gate, dict)
        and gate.get("id") == "G4"
        and gate.get("status") == "PASS_CI_SYNTH"
        and gate.get("decision") == "PASS",
        "G4 fact was not preserved",
    )
    evidence_blob = _blob_at(G4_EVIDENCE_COMMIT, G4_EVIDENCE_PATH)
    _require(_sha256(evidence_blob) == G4_EVIDENCE_SHA256, "G4 evidence receipt changed")
    evidence = json.loads(evidence_blob.decode("utf-8"))
    _require(
        evidence.get("gate_id") == "G4"
        and evidence.get("status") == "PASS_CI_SYNTH"
        and evidence.get("review_commit") == "ec76e812ca47e1c943fb6193c197bb16d4eead6e",
        "G4 evidence identity drifted",
    )
    return Check("immutable_g4_predecessor", "PASS", {"g4_evidence_commit": G4_EVIDENCE_COMMIT, "g4_status": "PASS_CI_SYNTH"})


def validate_public_private_boundary() -> Check:
    controls = (*REVIEW_SOURCE_PATHS, GATE_EVIDENCE, FINDINGS_EVIDENCE, VERIFICATION_EVIDENCE)
    for path in controls:
        _require(path.is_file(), f"review control artifact missing: {path.name}")
        _require(path.stat().st_size <= 2 * 1024 * 1024, "review control artifact exceeds size budget")
        _safe_payload({"control": path.read_text(encoding="utf-8")})
    project = _load_json(PROJECT_FACT)
    architecture = _load_json(ARCHITECTURE)
    expected_status = "stage_5_g5_pass_ci_synth_stage_6_assurance001_next_real_runtime_not_run"
    _require(
        project.get("schema_version") == "1.5"
        and project.get("status") == expected_status
        and project.get("stage_5_current_task") == "g5_pass_ci_synth_stage_6_assurance001_next"
        and project.get("stage_6_current_task") == "assurance001_planned_real_runtime_not_run",
        "project fact overclaims G5 capability",
    )
    _require(
        architecture.get("schema_version") == "1.5"
        and architecture.get("phase") == "G5"
        and architecture.get("status") == expected_status
        and architecture.get("stage_gate") == "g5_pass_ci_synth_stage6_assurance001_authorized_private_gold_disabled",
        "architecture fact overclaims G5 capability",
    )
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REPORT.read_text(encoding="utf-8")
    for token in (REVIEW_ID, RUN_ID, "不执行新的 DAG Task", "不上传、不部署、不发布", "Alpha、Beta、固定健康观察或 soak"):
        _require(token in contract or token in report, "G5 public run boundary is incomplete")
    return Check("documents_and_public_private_boundary", "PASS", {"controls_scanned": len(controls), "sensitive_value_hits": 0})


def _json_line(output: str) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            values.append(payload)
    _require(values, "G5 acceptance emitted no JSON receipt")
    return values[-1]


def validate_fresh_acceptance() -> Check:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
    }
    result = subprocess.run(
        [sys.executable, "-B", str(ACCEPTANCE_RUNNER)],
        cwd=PROJECT_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=5400,
    )
    _require(result.returncode == 0, "fresh G5 acceptance failed")
    receipt = _json_line(result.stdout)
    _require(
        receipt.get("schema_version") == "1.0"
        and receipt.get("review_id") == REVIEW_ID
        and receipt.get("run_id") == RUN_ID
        and receipt.get("status") == "PASS_CI_SYNTH_G5_REVIEW"
        and receipt.get("gate_conditions") == EXPECTED_CONDITIONS
        and set(receipt.get("task_receipts", {})) == set(EXPECTED_TASKS)
        and receipt.get("metrics", {}).get("task_reports") == 5
        and int(receipt.get("metrics", {}).get("stage_5_synthetic_unit_tests", 0)) >= 157
        and int(receipt.get("metrics", {}).get("g4_synthetic_unit_tests", 0)) >= 84,
        "fresh G5 acceptance receipt drifted",
    )
    _require(
        receipt.get("execution")
        == {
            "external_network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "notion_real_calls": 0,
            "private_database_client_calls": 0,
            "tmutil_calls": 0,
            "physical_delete_execution": "NOT_RUN",
            "stage_5_remote_upload": "NOT_RUN",
            "stage_6_executed": False,
        },
        "fresh G5 acceptance crossed runtime boundary",
    )
    historical = receipt.get("historical_replay")
    _require(
        isinstance(historical, dict)
        and historical.get("status") == "PASS"
        and historical.get("historical_task") == "TSK.x2n.uxops.005"
        and historical.get("current_g5_tree_evaluated") is False,
        "fresh G5 historical Task005 replay drifted",
    )
    return Check(
        "fresh_ci_synth_g5_acceptance",
        "PASS",
        {"g4_synthetic_unit_tests": receipt["metrics"]["g4_synthetic_unit_tests"], "stage_5_synthetic_unit_tests": receipt["metrics"]["stage_5_synthetic_unit_tests"]},
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(("rev-parse", "--show-toplevel"))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    branch = _git(("branch", "--show-current"))
    _require(branch not in {"", "main"}, "G5 review must run in a non-main worktree")
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", _git(("config", "--local", "--get", "remote.origin.url")))
        is not None,
        "wrong or authenticated persisted origin",
    )
    main_path: Path | None = None
    for block in _git(("worktree", "list", "--porcelain")).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        if worktree and "branch refs/heads/main" in lines:
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(("branch", "--show-current"), cwd=main_path) == "main", "main unavailable")
    main_paths = _git(("-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"), cwd=main_path).splitlines()
    _require(sum("xhs-douyin-2notion" in item for item in main_paths) == 0, "main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "MetaDatabase main worktree is dirty")
    _require(
        subprocess.run(("git", "merge-base", "--is-ancestor", REVIEW_BASE_COMMIT, "HEAD"), cwd=REPOSITORY_ROOT, stdin=subprocess.DEVNULL, check=False).returncode == 0,
        "G5 review does not descend from Task005 evidence receipt",
    )
    return Check("worktree_isolation", "PASS", {"branch": branch, "external_main_dirty_paths": len(main_paths), "main_mutated": False})


def _review_commit_from_evidence() -> str:
    gate = _load_json(GATE_EVIDENCE)
    commit = gate.get("review_commit")
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "G5 review commit is invalid")
    _git(("cat-file", "-e", f"{commit}^{{commit}}"))
    return commit


def validate_evidence_and_scope() -> Check:
    gate = _load_json(GATE_EVIDENCE)
    findings = _load_json(FINDINGS_EVIDENCE)
    verification = _load_json(VERIFICATION_EVIDENCE)
    for payload in (gate, findings, verification):
        _safe_payload(payload)
    review_commit = _review_commit_from_evidence()
    _require(
        subprocess.run(("git", "merge-base", "--is-ancestor", REVIEW_BASE_COMMIT, review_commit), cwd=REPOSITORY_ROOT, stdin=subprocess.DEVNULL, check=False).returncode == 0
        and subprocess.run(("git", "merge-base", "--is-ancestor", review_commit, "HEAD"), cwd=REPOSITORY_ROOT, stdin=subprocess.DEVNULL, check=False).returncode == 0,
        "G5 review commit ancestry is invalid",
    )
    changed = [item for item in _git(("diff", "--name-only", "-z", f"{REVIEW_BASE_COMMIT}..{review_commit}")).split("\0") if item]
    relative = [_scope_name(item) for item in changed]
    _require(changed and all(item is not None for item in relative) and set(relative) == SOURCE_CHANGED_EXACT, "G5 source scope drifted")
    current = [item for item in _git(("diff", "--name-only", "-z", f"{REVIEW_BASE_COMMIT}..HEAD")).split("\0") if item]
    current_relative = [_scope_name(item) for item in current]
    _require(current and all(item is not None for item in current_relative) and set(current_relative) <= CURRENT_ALLOWED_EXACT, "G5 current scope escaped allowed paths")
    _require(
        gate
        == {
            "schema_version": "1.0",
            "review_id": REVIEW_ID,
            "run_id": RUN_ID,
            "gate_id": "G5",
            "status": "PASS_CI_SYNTH",
            "decision": "PASS",
            "review_base_commit": REVIEW_BASE_COMMIT,
            "review_commit": review_commit,
            "review_source_receipt_sha256": _source_receipt(review_commit),
            "stage_5_review_state_sha256": _sha256(_blob_at(review_commit, REVIEW_FACT)),
            "stage_5_remote_upload_authorized": False,
            "stage_6_assurance001_start_authorized": True,
            "next_task": "TSK.x2n.assurance.001",
        },
        "G5 evidence receipt drifted",
    )
    _require(
        findings.get("status") == "NO_OPEN_G5_STAGE_TRANSITION_BLOCKERS"
        and findings.get("remaining_non_blocking_disabled_capabilities")
        == ["real_notion", "real_private_database_transfer", "real_platform_calls", "real_model_quality", "deployment"]
        and findings.get("out_of_scope")
        == {
            "stage_5_remote_upload": "NOT_RUN",
            "stage_6_execution": "NOT_RUN",
            "real_platform_calls": 0,
            "tmutil_calls": 0,
            "physical_delete_execution": "NOT_RUN",
        },
        "G5 findings evidence drifted",
    )
    _require(
        verification.get("schema_version") == "1.0"
        and verification.get("review_id") == REVIEW_ID
        and verification.get("run_id") == RUN_ID
        and verification.get("status") == "PASS_CI_SYNTH_G5_REVIEW"
        and verification.get("execution")
        == {
            "external_network_calls": 0,
            "platform_calls": 0,
            "real_account_execution": "NOT_RUN",
            "notion_real_calls": 0,
            "private_database_client_calls": 0,
            "tmutil_calls": 0,
            "physical_delete_execution": "NOT_RUN",
            "stage_5_remote_upload": "NOT_RUN",
            "stage_6_executed": False,
        }
        and all(item.get("status") == "PASS" for item in verification.get("checks", [])),
        "G5 verification evidence drifted",
    )
    return Check("g5_evidence_and_scope", "PASS", {"evidence_files": 3, "review_source": "verified", "current_paths": len(current_relative)})


def run_checks(*, verify_worktree: bool, allow_external_main_dirty: bool, run_acceptance: bool, require_evidence: bool) -> list[Check]:
    checks = [validate_review_fact_and_task_receipts(), validate_taskpack_and_state_transition(), validate_g4_preservation()]
    if verify_worktree:
        checks.insert(0, validate_worktree(allow_external_main_dirty))
    if run_acceptance:
        checks.append(validate_fresh_acceptance())
    if require_evidence:
        checks.extend((validate_public_private_boundary(), validate_evidence_and_scope()))
    _require(all(check.status == "PASS" for check in checks), "G5 review verification did not pass")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the x2n independent Stage 5 G5 review")
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
                    "review_id": REVIEW_ID,
                    "status": "PASS",
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ReviewError, subprocess.SubprocessError, yaml.YAMLError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
