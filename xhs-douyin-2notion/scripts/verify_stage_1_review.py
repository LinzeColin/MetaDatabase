#!/usr/bin/env python3
"""Fail-closed Stage 1 Review and G1 verifier for x2n."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
CI_SCRIPT_DIRECTORY = PROJECT_ROOT / "scripts/ci"
if str(CI_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(CI_SCRIPT_DIRECTORY))

from ci_baseline import scan_source, scan_text  # noqa: E402


REVIEW_ID = "STG.X2N.1.REVIEW"
RUN_ID = "RUN-X2N-S01-REVIEW"
REVIEW_BRANCH = "codex/xhs-douyin-2notion-v0001-s01-review"
STAGE_BASE_COMMIT = "f1e5016a4e1bba10c86d8dd017868d5d64835f42"
REVIEW_BASE_COMMIT = "5f770b6daf63d57ec4698dc7fbc95a9dfeab2669"
ORIGIN_CUTOFF = "3e7094774158ead8751a7189041d8d1eeff2b50c"

FOUNDATION_COMMITS = {
    "TSK.x2n.foundation.001": "69130c1db9946850b23e1c78f771129eb094eea2",
    "TSK.x2n.foundation.002": "ae17e377090ef3bc1123d2512cda0daef9efe1cb",
    "TSK.x2n.foundation.003": "84731bde18495ab20af005bc70d59d5ce73cbe93",
    "TSK.x2n.foundation.004": "09d5cdf1993080401f99e023feb03be479baca27",
    "TSK.x2n.foundation.005": REVIEW_BASE_COMMIT,
}
FOUNDATION_EVIDENCE = {
    "TSK.x2n.foundation.001": PROJECT_ROOT / "evidence/foundation/TSK.x2n.foundation.001.json",
    "TSK.x2n.foundation.002": PROJECT_ROOT / "evidence/contracts/TSK.x2n.foundation.002.json",
    "TSK.x2n.foundation.003": PROJECT_ROOT / "evidence/data/TSK.x2n.foundation.003.json",
    "TSK.x2n.foundation.004": PROJECT_ROOT / "evidence/extension/TSK.x2n.foundation.004.json",
    "TSK.x2n.foundation.005": PROJECT_ROOT / "evidence/ci/TSK.x2n.foundation.005.json",
}
FOUNDATION_RUNS = {task_id: f"RUN-X2N-S01-F{index:03d}" for index, task_id in enumerate(FOUNDATION_COMMITS, start=1)}

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ROADMAP = PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S01_REVIEW.md"
REVIEW_REPORT = PROJECT_ROOT / "docs/governance/STAGE_1_REVIEW.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
CI_POLICY = PROJECT_ROOT / "machine/policy/ci_gate_manifest.json"
G1_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_1_gate_state.schema.json"
G1_FACT = PROJECT_ROOT / "machine/facts/stage_1_gate_state.json"
FINDINGS = PROJECT_ROOT / "machine/evidence/stage_1/review/findings.json"
VERIFICATION_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_1/review/verification.json"
G1_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_1/review/G1.json"
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/x2n-ci.yml"

EXPECTED_G1_TASKS = tuple(FOUNDATION_COMMITS)
EXPECTED_G1_CONDITIONS = (
    "contracts round-trip",
    "DB migrations and rollback pass",
    "extension/native host restart-safe",
    "synthetic CI and scans pass",
)
EXPECTED_GATES = (
    "format",
    "lint",
    "python_compile",
    "typescript_contract",
    "root_unit",
    "companion_unit_integration",
    "contract_unit",
    "contract_acceptance",
    "sbom_drift",
    "scaffold_acceptance",
    "migration_integration",
    "extension_native_e2e",
)
EXPECTED_PASS_CONDITIONS = {
    "contracts_round_trip": "pass",
    "db_migrations_and_rollback": "pass",
    "extension_native_host_restart_safe": "pass",
    "synthetic_ci_and_scans": "pass",
}
EXPECTED_STOP_CONDITIONS = {
    "sensitive_or_cdn_material_presence": "inactive",
    "real_credentials_or_accounts_required": "inactive",
    "blocking_test_silently_skipped": "inactive",
    "wildcard_origin_or_arbitrary_command": "inactive",
    "migration_without_verified_rollback": "inactive",
    "runtime_root_inside_repository": "inactive",
}
EXPECTED_FINDINGS = {
    "F-X2N-S01-R01",
    "F-X2N-S01-R02",
    "F-X2N-S01-R03",
    "F-X2N-S01-R04",
    "F-X2N-S01-R05",
    "F-X2N-S01-R06",
    "F-X2N-S01-R07",
    "F-X2N-S01-R08",
}

ALLOWED_REVIEW_EXACT = {
    "xhs-douyin-2notion/apps/companion/src/x2n_companion/runtime_cli.py",
    "xhs-douyin-2notion/CHANGELOG.md",
    "xhs-douyin-2notion/HANDOFF.md",
    "xhs-douyin-2notion/README.md",
    "xhs-douyin-2notion/docs/governance/RUN_CONTRACT_S01_REVIEW.md",
    "xhs-douyin-2notion/docs/governance/STAGE_1_REVIEW.md",
    "xhs-douyin-2notion/docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "xhs-douyin-2notion/machine/facts/architecture_decisions.json",
    "xhs-douyin-2notion/machine/facts/project.json",
    "xhs-douyin-2notion/machine/facts/stage_1_gate_state.json",
    "xhs-douyin-2notion/machine/facts/task_state.json",
    "xhs-douyin-2notion/machine/policy/ci_gate_manifest.json",
    "xhs-douyin-2notion/machine/schemas/stage_1_gate_state.schema.json",
    "xhs-douyin-2notion/scripts/ci/run_lane.py",
    "xhs-douyin-2notion/scripts/verify_foundation_001.py",
    "xhs-douyin-2notion/scripts/verify_foundation_002.py",
    "xhs-douyin-2notion/scripts/verify_foundation_003.py",
    "xhs-douyin-2notion/scripts/verify_foundation_004.py",
    "xhs-douyin-2notion/scripts/verify_foundation_005.py",
    "xhs-douyin-2notion/scripts/verify_phase_0_1.py",
    "xhs-douyin-2notion/scripts/verify_phase_0_2.py",
    "xhs-douyin-2notion/scripts/verify_phase_0_5.py",
    "xhs-douyin-2notion/scripts/verify_stage_0_review.py",
    "xhs-douyin-2notion/scripts/verify_stage_0_review_resume.py",
    "xhs-douyin-2notion/scripts/verify_stage_1_review.py",
    "xhs-douyin-2notion/tests/test_foundation_001.py",
    "xhs-douyin-2notion/tests/test_foundation_002.py",
    "xhs-douyin-2notion/tests/test_foundation_003.py",
    "xhs-douyin-2notion/tests/test_foundation_004.py",
    "xhs-douyin-2notion/tests/test_foundation_005.py",
    "xhs-douyin-2notion/tests/test_phase_0_1.py",
    "xhs-douyin-2notion/tests/test_phase_0_2.py",
    "xhs-douyin-2notion/tests/test_phase_0_5.py",
    "xhs-douyin-2notion/tests/test_stage_1_review.py",
    "xhs-douyin-2notion/tests/test_stage_0_review_resume.py",
    "xhs-douyin-2notion/功能清单.md",
    "xhs-douyin-2notion/开发记录.md",
    "xhs-douyin-2notion/模型参数文件.md",
}
ALLOWED_REVIEW_PREFIXES = ("xhs-douyin-2notion/machine/evidence/stage_1/review/",)


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


def _load_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            _require(key not in value, f"duplicate JSON key rejected: {path.name}")
            value[key] = item
        return value

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"YAML object required: {path.name}")
    return value


def _load_yaml_at(commit: str, path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    value = yaml.safe_load(str(_git(["show", f"{commit}:{relative}"])))
    _require(isinstance(value, dict), f"historical YAML object required: {path.name}")
    return value


def _validate_taskpack_review_delta(current: dict[str, Any], baseline: dict[str, Any]) -> None:
    normalized = copy.deepcopy(current)
    normalized["project"]["status"] = baseline["project"]["status"]

    authorization = normalized["authorization"]
    baseline_authorization = baseline["authorization"]
    for field in ("stage_1_review", "stage_1_remote_upload", "stage_2_task_start"):
        _require(
            field not in baseline_authorization and authorization.get(field) is True,
            f"invalid Review authorization delta: {field}",
        )
        del authorization[field]
    authorization["instruction"] = baseline_authorization["instruction"]

    normalized_tasks = {row.get("id"): row for row in normalized["tasks"]}
    baseline_tasks = {row.get("id"): row for row in baseline["tasks"]}
    _require(set(normalized_tasks) == set(baseline_tasks), "Task registry changed during Stage 1 Review")
    normalized_tasks["TSK.x2n.foundation.005"]["status"] = baseline_tasks["TSK.x2n.foundation.005"]["status"]
    _require(normalized == baseline, "Task Pack changed outside the exact Stage 1 Review state delta")


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def _git(args: Sequence[str], cwd: Path = REPOSITORY_ROOT, *, binary: bool = False) -> str | bytes:
    git = shutil.which("git")
    _require(git is not None, "git unavailable")
    result = subprocess.run(
        [git, *args],
        cwd=cwd,
        env=_git_environment(),
        check=False,
        capture_output=True,
        text=not binary,
    )
    _require(result.returncode == 0, "local Git verification failed")
    if binary:
        return result.stdout
    return str(result.stdout).rstrip()


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        [shutil.which("git") or "git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPOSITORY_ROOT,
        env=_git_environment(),
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _logical_review_head() -> str:
    row = str(_git(["rev-list", "--parents", "-n", "1", "HEAD"])).split()
    _require(len(row) in {2, 3}, "unexpected Review HEAD parent shape")
    head, *parents = row
    if len(parents) == 1:
        return head
    candidates = [parent for parent in parents if _is_ancestor(REVIEW_BASE_COMMIT, parent)]
    _require(len(candidates) == 1, "PR merge does not identify exactly one Stage 1 Review parent")
    return candidates[0]


def _porcelain_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.strip('"'))
    return paths


def _safe_payload(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "/home/" not in rendered, "evidence contains local path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains URL")
    _require("github" + "_pat_" not in rendered and "ghp" + "_" not in rendered, "evidence contains token shape")
    _require(
        re.search(r"(?i)(?:xhs.?cdn|douyin.?vod|byteimg|pstatp|bilivideo|kscdn|alicdn)", rendered) is None,
        "evidence contains CDN material",
    )


def _expected_blocking_results() -> list[dict[str, Any]]:
    return [
        {
            "blocking": True,
            "gate": gate,
            "label": f"{gate}_r{repetition}",
            "repetition": repetition,
            "status": "PASS",
        }
        for repetition in (1, 2)
        for gate in EXPECTED_GATES
    ]


def validate_review_documents() -> Check:
    required = (RUN_CONTRACT, REVIEW_REPORT, G1_SCHEMA, G1_FACT, FINDINGS)
    missing = [path.name for path in required if not path.is_file()]
    _require(not missing, f"Stage 1 Review artifact missing: {missing}")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REVIEW_REPORT.read_text(encoding="utf-8")
    for token in (
        RUN_ID,
        REVIEW_ID,
        REVIEW_BASE_COMMIT,
        ORIGIN_CUTOFF,
        "不执行新的 DAG Task",
        "pending_post_g1_upload",
    ):
        _require(token in contract, f"Review Run Contract missing: {token}")
    for token in (
        "REVIEW_COMPLETE / G1_PASS",
        "PENDING_POST_G1_UPLOAD",
        "F-X2N-S01-R01",
        "F-X2N-S01-R02",
        "F-X2N-S01-R03",
        "F-X2N-S01-R04",
        "F-X2N-S01-R05",
        "F-X2N-S01-R06",
        "F-X2N-S01-R07",
        "F-X2N-S01-R08",
        "TSK.x2n.skeleton.001",
    ):
        _require(token in report, f"Stage 1 Review report missing: {token}")
    return Check("review_contract", "PASS", {"findings_declared": 8, "new_dag_tasks": 0})


def validate_task_dag_and_state() -> Check:
    taskpack = _load_yaml(TASKPACK)
    _validate_taskpack_review_delta(taskpack, _load_yaml_at(REVIEW_BASE_COMMIT, TASKPACK))
    project = taskpack.get("project", {})
    authorization = taskpack.get("authorization", {})
    _require(project.get("status") == "STAGE_1_REVIEW_PASS_G1_PASS_STAGE_2_AUTHORIZED", "Task DAG status drifted")
    for field in ("stage_1_review", "stage_1_remote_upload", "stage_2_task_start"):
        _require(authorization.get(field) is True, f"Task DAG authorization missing: {field}")
    tasks = {row.get("id"): row for row in taskpack.get("tasks", [])}
    _require(
        tuple(task_id for task_id in tasks if task_id in FOUNDATION_COMMITS) == EXPECTED_G1_TASKS,
        "Foundation Task order drifted",
    )
    for task_id in EXPECTED_G1_TASKS:
        _require(tasks[task_id].get("status") == "completed", f"Foundation Task is not completed: {task_id}")
    for task_id, task in tasks.items():
        if task.get("stage") not in {"STG.X2N.0", "STG.X2N.1"}:
            _require(task.get("status") == "planned", f"downstream Task executed during G1 Review: {task_id}")
    gates = {row.get("id"): row for row in taskpack.get("stage_gates", [])}
    g1 = gates.get("G1", {})
    _require(tuple(g1.get("requires_tasks", [])) == EXPECTED_G1_TASKS, "G1 Task set drifted")
    _require(tuple(g1.get("pass_conditions", [])) == EXPECTED_G1_CONDITIONS, "G1 conditions drifted")

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.8", "task state schema drifted")
    _require(state.get("review_id") == REVIEW_ID and state.get("run_id") == RUN_ID, "Review state identity drifted")
    _require(state.get("run_kind") == "stage_review_no_new_dag_task", "Review run kind drifted")
    _require(state.get("current_stage_gate") == "pass", "G1 is not pass in task state")
    _require(state.get("current_stage_remote_upload") == "authorized_after_g1_pass", "Stage 1 upload not gated by G1")
    _require(
        state.get("next_phase") == "PH.X2N.2.1" and state.get("next_run") == "TSK.x2n.skeleton.001",
        "next Task routing drifted",
    )
    _require(state.get("stage_2_authorized") is True, "Stage 2 authorization missing")
    _require(
        all(state.get("tasks", {}).get(task_id) == "pass" for task_id in EXPECTED_G1_TASKS),
        "Foundation Task state missing",
    )
    for field in (
        "real_account_execution",
        "platform_calls",
        "notion_calls",
        "model_calls",
        "media_processing",
        "real_sink_execution",
    ):
        _require(state.get(field) == "not_run", f"downstream execution overstated: {field}")

    project_fact = _load_json(PROJECT_FACT)
    _require(project_fact.get("status") == "stage_1_review_pass_g1_pass_stage_2_authorized", "project fact drifted")
    architecture = _load_json(ARCHITECTURE_FACT)
    _require(
        architecture.get("stage_gate") == "g1_pass" and architecture.get("review_id") == REVIEW_ID,
        "architecture G1 fact drifted",
    )
    return Check(
        "task_dag_and_state",
        "PASS",
        {"foundation_tasks": 5, "g1_conditions": 4, "next_task": "TSK.x2n.skeleton.001", "stage_2_tasks_run": 0},
    )


def validate_gate_fact() -> Check:
    schema = _load_json(G1_SCHEMA)
    fact = _load_json(G1_FACT)
    _require(schema.get("additionalProperties") is False, "G1 schema permits unknown fields")
    _require(set(schema.get("required", [])) == set(fact), "G1 schema/fact field set drifted")
    constants = {
        "schema_version": "1.0",
        "project": "x2n",
        "stage": "STG.X2N.1",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "review_base_commit": REVIEW_BASE_COMMIT,
        "review_sync_target": ORIGIN_CUTOFF,
        "review_status": "complete",
        "automated_reacceptance": "pass",
        "gate_id": "G1",
        "gate_status": "pass",
        "gate_decision": "pass",
        "stage_2_authorized": True,
        "remote_upload": "authorized_after_g1_pass",
        "remote_ci_execution": "pending_post_g1_upload",
        "next_task": "TSK.x2n.skeleton.001",
        "product_scope": "stage_1_foundation_only",
        "real_account_execution": "not_run",
        "platform_calls": "not_run",
        "notion_calls": "not_run",
        "model_calls": "not_run",
        "media_processing": "not_run",
    }
    _require(all(fact.get(key) == value for key, value in constants.items()), "G1 fact value drifted")
    _require(fact.get("pass_conditions") == EXPECTED_PASS_CONDITIONS, "G1 pass-condition evidence drifted")
    _require(fact.get("stop_conditions") == EXPECTED_STOP_CONDITIONS, "G1 stop-condition evidence drifted")
    _require(fact.get("blocking_followups") == [], "G1 has an open blocking follow-up")
    return Check("g1_fact", "PASS", {"blocking_followups": 0, "pass_conditions": 4, "stop_conditions": 6})


def validate_findings() -> Check:
    payload = _load_json(FINDINGS)
    rows = payload.get("findings", [])
    _require(payload.get("review_id") == REVIEW_ID and payload.get("run_id") == RUN_ID, "finding identity drifted")
    _require({row.get("id") for row in rows} == EXPECTED_FINDINGS, "Review finding set drifted")
    severities = {row.get("id"): row.get("severity") for row in rows}
    _require(
        severities
        == {
            "F-X2N-S01-R01": "HIGH",
            "F-X2N-S01-R02": "HIGH",
            "F-X2N-S01-R03": "HIGH",
            "F-X2N-S01-R04": "HIGH",
            "F-X2N-S01-R05": "MEDIUM",
            "F-X2N-S01-R06": "HIGH",
            "F-X2N-S01-R07": "HIGH",
            "F-X2N-S01-R08": "HIGH",
        },
        "Review finding severity drifted",
    )
    _require(all(row.get("status") == "RESOLVED" for row in rows), "Review finding unresolved")
    _require(
        payload.get("summary") == {"blocking_open": 0, "resolved": 8, "total": 8}, "Review finding summary drifted"
    )
    return Check("review_findings", "PASS", {"blocking_open": 0, "resolved": 8})


def validate_foundation_evidence() -> Check:
    review_head = _logical_review_head()
    for task_id, commit in FOUNDATION_COMMITS.items():
        _require(_is_ancestor(commit, review_head), f"Foundation commit is not an ancestor: {task_id}")
        path = FOUNDATION_EVIDENCE[task_id]
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        frozen = _git(["show", f"{REVIEW_BASE_COMMIT}:{relative}"], binary=True)
        _require(path.read_bytes() == frozen, f"historical Foundation evidence was rewritten: {task_id}")
        evidence = _load_json(path)
        _require(
            evidence.get("task_id") == task_id and evidence.get("run_id") == FOUNDATION_RUNS[task_id],
            "Foundation evidence identity drifted",
        )
        _require(evidence.get("status") == "PASS", f"Foundation evidence is not pass: {task_id}")
    _require(
        _load_json(FOUNDATION_EVIDENCE["TSK.x2n.foundation.005"]).get("g1") == "NOT_RUN",
        "Foundation005 historical G1 fact was rewritten",
    )
    return Check(
        "foundation_evidence", "PASS", {"frozen_receipts": 5, "foundation_commits": 5, "rewritten_receipts": 0}
    )


def validate_lane_report(path: Path) -> Check:
    report = _load_json(path)
    _require(report.get("status") == "PASS" and report.get("lane") == "full", "full lane report missing or failed")
    _require(
        report.get("blocking_commands") == 12 and report.get("blocking_executions") == 24,
        "blocking execution count drifted",
    )
    _require(report.get("blocking_repetitions") == 2, "full lane repetition count drifted")
    _require(report.get("blocking_results") == _expected_blocking_results(), "blocking execution identity drifted")
    for field in (
        "blocking_failures",
        "flaky_blocking_tests",
        "silent_blocking_skips",
        "model_calls",
        "platform_calls",
        "real_accounts",
    ):
        _require(report.get(field) == 0, f"lane blocker or prohibited execution: {field}")
    _require(report.get("explicit_nonblocking_skips") == 6, "optional skip count drifted")
    _require(report.get("artifact_deterministic") is True, "artifact determinism missing")
    _require(report.get("coverage", {}).get("status") == "PASS", "coverage report failed")
    _require(len(report.get("coverage", {}).get("critical_modules", {})) == 7, "critical coverage evidence incomplete")
    _require(report.get("osv", {}).get("status") == "PASS", "OSV report failed")
    _require(
        report.get("g1") == "NOT_RUN" and report.get("remote_github_actions") == "NOT_RUN_LOCAL_BASELINE",
        "local lane overstated G1 or remote CI",
    )

    report_statuses = {
        "artifact.json": "PASS",
        "ci-self-test.json": "PASS",
        "coverage-summary.json": "PASS",
        "csp.json": "PASS",
        "fixture-leak.json": "PASS",
        "license.json": "PASS",
        "model-eval.json": "PASS_BASELINE_SKELETON",
        "osv.json": "PASS",
        "public-report-scan.json": "PASS",
        "sast.json": "PASS",
        "source-privacy.json": "PASS",
    }
    for filename, status in report_statuses.items():
        _require(_load_json(path.parent / filename).get("status") == status, f"lane subreport failed: {filename}")
    artifact = path.parent / "x2n-source-candidate.zip"
    _require(artifact.is_file(), "release candidate missing")
    _require(
        hashlib.sha256(artifact.read_bytes()).hexdigest() == report["artifact_report"]["artifact_sha256"],
        "release candidate hash drifted",
    )
    return Check(
        "g1_full_lane",
        "PASS",
        {
            "blocking_executions": 24,
            "blocking_failures": 0,
            "blocking_repetitions": 2,
            "explicit_nonblocking_skips": 6,
            "flaky_blocking_tests": 0,
            "silent_blocking_skips": 0,
        },
    )


def _relevant_history_path(path: str) -> bool:
    return path == ".github/workflows/x2n-ci.yml" or path.startswith("xhs-douyin-2notion/")


def _blob_at(commit: str, path: str) -> bytes | None:
    result = subprocess.run(
        [shutil.which("git") or "git", "show", f"{commit}:{path}"],
        cwd=REPOSITORY_ROOT,
        env=_git_environment(),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def validate_history_privacy() -> Check:
    review_head = _logical_review_head()
    commits = str(_git(["rev-list", "--reverse", f"{STAGE_BASE_COMMIT}..{review_head}"])).splitlines()
    expected = list(FOUNDATION_COMMITS.values())
    _require(commits[:5] == expected, "Foundation commit lineage drifted")
    _require(len(commits) in {5, 6}, "Stage 1 Review must remain one review commit")
    if len(commits) == 6:
        _require(commits[-1] == review_head, "unexpected commit after Review")

    findings = []
    blob_versions = 0
    denied_suffixes = set(
        _load_json(PROJECT_ROOT / "machine/policy/release_artifact_allowlist.json")["denied_suffixes"]
    )
    for index, commit in enumerate(commits, start=1):
        message = str(_git(["show", "-s", "--format=%B", commit]))
        findings.extend(scan_text(message, f"commit-message/{index}"))
        paths = str(
            _git(
                [
                    "-c",
                    "core.quotePath=false",
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "--diff-filter=ACMRT",
                    "-r",
                    commit,
                ]
            )
        ).splitlines()
        for path in paths:
            if not _relevant_history_path(path):
                continue
            _require(Path(path).suffix.lower() not in denied_suffixes, "denied file type exists in Stage 1 history")
            blob = _blob_at(commit, path)
            if blob is None:
                continue
            _require(len(blob) <= 4 * 1024 * 1024, "oversized file exists in Stage 1 history")
            try:
                text = blob.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ReviewError("binary file exists in Stage 1 history") from error
            findings.extend(scan_text(text, path))
            blob_versions += 1

    current = scan_source()
    _require(
        current.get("status") == "PASS" and current.get("finding_count") == 0, "current source privacy scan failed"
    )
    findings.extend(scan_text(WORKFLOW.read_text(encoding="utf-8"), ".github/workflows/x2n-ci.yml"))
    _require(not findings, "Secret/Private/CDN material exists in Stage 1 history or current tree")
    return Check(
        "stage_1_history_privacy",
        "PASS",
        {
            "blob_versions_scanned": blob_versions,
            "commit_messages_scanned": len(commits),
            "commits_scanned": len(commits),
            "current_source_files_scanned": current["scanned_files"],
            "findings": 0,
        },
    )


def _changed_review_paths() -> set[str]:
    review_head = _logical_review_head()
    physical_head = str(_git(["rev-parse", "HEAD"]))
    changed = set(
        str(
            _git(
                [
                    "-c",
                    "core.quotePath=false",
                    "diff",
                    "--name-only",
                    f"{REVIEW_BASE_COMMIT}..{review_head}",
                ]
            )
        ).splitlines()
    )
    if review_head == physical_head:
        changed.update(
            str(
                _git(
                    [
                        "-c",
                        "core.quotePath=false",
                        "diff",
                        "--name-only",
                        review_head,
                    ]
                )
            ).splitlines()
        )
    untracked = str(_git(["-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard"])).splitlines()
    return {path for path in changed | set(untracked) if path}


def validate_review_scope() -> Check:
    changes = _changed_review_paths()
    _require(changes, "Stage 1 Review has no recorded change")
    for path in changes:
        allowed = path in ALLOWED_REVIEW_EXACT or any(path.startswith(prefix) for prefix in ALLOWED_REVIEW_PREFIXES)
        _require(allowed, f"out-of-scope Stage 1 Review change: {path}")
    stage_2_product_code = [
        path
        for path in changes
        if path.startswith(("xhs-douyin-2notion/apps/", "xhs-douyin-2notion/packages/contracts/"))
        and path != "xhs-douyin-2notion/apps/companion/src/x2n_companion/runtime_cli.py"
    ]
    _require(not stage_2_product_code, "Stage 1 Review entered Stage 2 product implementation")
    return Check(
        "review_scope",
        "PASS",
        {
            "changed_files": len(changes),
            "new_dag_tasks": 0,
            "stage_1_state_surface_fixes": 1,
            "stage_2_product_changes": 0,
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    review_head = _logical_review_head()
    _require(Path(str(_git(["rev-parse", "--show-toplevel"]))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    current_branch = str(_git(["branch", "--show-current"]))
    if review_head == str(_git(["rev-parse", "HEAD"])):
        _require(current_branch == REVIEW_BRANCH, "wrong Stage 1 Review branch")
    else:
        _require(current_branch == "", "PR merge verification must be detached")
    for commit in (STAGE_BASE_COMMIT, REVIEW_BASE_COMMIT, ORIGIN_CUTOFF):
        _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(_is_ancestor(REVIEW_BASE_COMMIT, review_head), "Review branch no longer descends from Foundation005")
    live_origin = str(_git(["rev-parse", "origin/main"]))
    _require(_is_ancestor(ORIGIN_CUTOFF, live_origin), "origin/main no longer descends from Review cutoff")

    main_path: Path | None = None
    for block in str(_git(["worktree", "list", "--porcelain"])).split("\n\n"):
        rows = block.splitlines()
        worktree = next((row.removeprefix("worktree ") for row in rows if row.startswith("worktree ")), None)
        branch = next((row for row in rows if row.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(
        main_path is not None and str(_git(["branch", "--show-current"], main_path)) == "main",
        "main worktree unavailable or off main",
    )
    main_paths = _porcelain_paths(
        str(_git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], main_path))
    )
    main_overlap = sum(_relevant_history_path(path) for path in main_paths)
    _require(main_overlap == 0, "main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "main worktree is dirty")

    branch_paths = set(
        str(
            _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{STAGE_BASE_COMMIT}..{review_head}"])
        ).splitlines()
    )
    origin_paths = set(
        str(
            _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{STAGE_BASE_COMMIT}..{live_origin}"])
        ).splitlines()
    )
    overlap = branch_paths & origin_paths
    _require(not overlap, "origin/main and Stage 1 branch overlap")
    return Check(
        "worktree_isolation",
        "PASS",
        {
            "branch": REVIEW_BRANCH,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(str(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"]))),
            "origin_overlap": len(overlap),
            "project_overlap_paths": main_overlap,
        },
    )


def run_checks(*, lane_report: Path, verify_worktree: bool, allow_external_main_dirty: bool) -> list[Check]:
    checks = [
        validate_review_documents(),
        validate_task_dag_and_state(),
        validate_gate_fact(),
        validate_findings(),
        validate_foundation_evidence(),
        validate_lane_report(lane_report),
        validate_history_privacy(),
        validate_review_scope(),
    ]
    if verify_worktree:
        checks.append(validate_worktree(allow_external_main_dirty))
    return checks


def write_evidence(checks: list[Check]) -> None:
    payload = {
        "automated_reacceptance": "PASS",
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "foundation_task_count": 5,
        "g1": "PASS",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model_calls": 0,
        "notion_calls": 0,
        "platform_calls": 0,
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_ci_execution": "PENDING_POST_G1_UPLOAD",
        "review_base_commit": REVIEW_BASE_COMMIT,
        "review_id": REVIEW_ID,
        "review_sync_target": ORIGIN_CUTOFF,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.1",
        "status": "PASS",
    }
    _safe_payload(payload)
    VERIFICATION_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    VERIFICATION_EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fact = _load_json(G1_FACT)
    _safe_payload(fact)
    G1_EVIDENCE.write_text(json.dumps(fact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    verification = _load_json(VERIFICATION_EVIDENCE)
    gate = _load_json(G1_EVIDENCE)
    fact = _load_json(G1_FACT)
    _safe_payload(verification)
    _safe_payload(gate)
    _require(
        verification.get("review_id") == REVIEW_ID and verification.get("run_id") == RUN_ID,
        "Review evidence identity drifted",
    )
    _require(
        verification.get("status") == "PASS" and verification.get("g1") == "PASS", "Review evidence is not G1 PASS"
    )
    _require(
        verification.get("remote_ci_execution") == "PENDING_POST_G1_UPLOAD", "Review evidence overstates remote CI"
    )
    _require(
        all(row.get("status") == "PASS" for row in verification.get("checks", [])),
        "Review evidence contains a failed check",
    )
    _require(gate == fact, "G1 evidence/fact drifted")
    return Check(
        "evidence",
        "PASS",
        {
            "g1_receipt_sha256": hashlib.sha256(G1_EVIDENCE.read_bytes()).hexdigest(),
            "verification_receipt_sha256": hashlib.sha256(VERIFICATION_EVIDENCE.read_bytes()).hexdigest(),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify STG.X2N.1.REVIEW and G1")
    parser.add_argument("--lane-report", type=Path, required=True)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            lane_report=args.lane_report,
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
        )
        if args.write_evidence:
            write_evidence(checks)
        if args.require_evidence:
            checks.append(verify_evidence())
        print(
            json.dumps(
                {
                    "checks": [{"name": check.name, "status": check.status} for check in checks],
                    "g1": "PASS",
                    "next_task": "TSK.x2n.skeleton.001",
                    "remote_ci_execution": "PENDING_POST_G1_UPLOAD",
                    "status": "PASS",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, ReviewError, yaml.YAMLError) as error:
        print(
            json.dumps({"reason": str(error), "status": "FAIL_CLOSED"}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
