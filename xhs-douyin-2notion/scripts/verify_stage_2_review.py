#!/usr/bin/env python3
"""Fail-closed Stage 2 Review and project-native local G2 verifier for x2n."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
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
import run_lane as LANE  # noqa: E402


REVIEW_ID = "STG.X2N.2.REVIEW"
RUN_ID = "RUN-X2N-S02-REVIEW"
REVIEW_BRANCH = "codex/xhs-douyin-2notion-v0001-s02-review"
STAGE_BASE_COMMIT = "6777c8fcce75a36741b70c2858c8bc5fff17d440"
REVIEW_BASE_COMMIT = "c133e1d4c1cbc17a3165e19fa5dbb2368da6b32b"
ORIGIN_CUTOFF = STAGE_BASE_COMMIT

SKELETON_COMMITS = {
    "TSK.x2n.skeleton.001": "894553c6d15c3c73315e54429c8bd26588b6f83a",
    "TSK.x2n.skeleton.002": "2a91efbc899aaaf3f6191ba3fb93ac825e3a9a0d",
    "TSK.x2n.skeleton.006": "a314a1d049998eae6a052ea8900aa5ac448cb2ca",
    "TSK.x2n.skeleton.007": "17f1988b309fe62071c273369f7088b7f6cc6046",
    "TSK.x2n.skeleton.008": "7e8a3dbf3c4c27643330489353ed162130fba506",
    "TSK.x2n.skeleton.009": "0af2d3b269e7d5631257cb49f41f75cc79438f70",
    "TSK.x2n.skeleton.003": "d5f61f30657ac6aa1bc7be3f7942d4b77df5b8ae",
    "TSK.x2n.skeleton.004": "36bd12133f402321b160292ea13ca51272c63e93",
    "TSK.x2n.skeleton.005": REVIEW_BASE_COMMIT,
}
SKELETON_EVIDENCE = {
    "TSK.x2n.skeleton.001": PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.001.json",
    "TSK.x2n.skeleton.002": PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.002.json",
    "TSK.x2n.skeleton.006": PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.006.json",
    "TSK.x2n.skeleton.007": PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.007.json",
    "TSK.x2n.skeleton.008": PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.008.json",
    "TSK.x2n.skeleton.009": PROJECT_ROOT / "evidence/adapters/TSK.x2n.skeleton.009.json",
    "TSK.x2n.skeleton.003": PROJECT_ROOT / "evidence/media/TSK.x2n.skeleton.003.json",
    "TSK.x2n.skeleton.004": PROJECT_ROOT / "evidence/orchestrator/TSK.x2n.skeleton.004.json",
    "TSK.x2n.skeleton.005": PROJECT_ROOT / "evidence/sinks/TSK.x2n.skeleton.005.json",
}
SKELETON_RUNS = {task_id: f"RUN-X2N-S02-S{task_id.rsplit('.', 1)[1]}" for task_id in SKELETON_COMMITS}

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S02_REVIEW.md"
REVIEW_REPORT = PROJECT_ROOT / "docs/governance/STAGE_2_REVIEW.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
CI_POLICY = PROJECT_ROOT / "machine/policy/ci_gate_manifest.json"
G2_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_2_gate_state.schema.json"
G2_FACT = PROJECT_ROOT / "machine/facts/stage_2_gate_state.json"
FINDINGS = PROJECT_ROOT / "machine/evidence/stage_2/review/findings.json"
VERIFICATION_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_2/review/verification.json"
G2_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_2/review/G2.json"
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/x2n-ci.yml"

EXPECTED_G2_CONDITIONS = [
    "all six platforms each complete an independently gated current-page walking path",
    "zero duplicates",
    "zero CDN persistence",
    "successful media cleanup",
    "Notion outage does not block canonical and Markdown",
]
EXPECTED_PASS_CONDITIONS = {
    "six_platform_current_page_paths": "pass",
    "zero_duplicates": "pass",
    "zero_cdn_persistence": "pass",
    "media_cleanup": "pass",
    "notion_outage_canonical_markdown_independent": "pass",
}
EXPECTED_STOP_CONDITIONS = {
    "sensitive_or_cdn_material_presence": "inactive",
    "historical_evidence_rewritten": "inactive",
    "blocking_test_silently_skipped": "inactive",
    "toolchain_policy_mismatch": "inactive",
    "real_external_surface_required": "inactive",
    "stage_3_product_task_entered": "inactive",
}
EXPECTED_FINDINGS = {f"F-X2N-S02-R{index:02d}" for index in range(1, 9)}
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

ALLOWED_REVIEW_EXACT = {
    "xhs-douyin-2notion/CHANGELOG.md",
    "xhs-douyin-2notion/HANDOFF.md",
    "xhs-douyin-2notion/README.md",
    "xhs-douyin-2notion/SKILL.md",
    "xhs-douyin-2notion/docs/governance/RUN_CONTRACT_S02_REVIEW.md",
    "xhs-douyin-2notion/docs/governance/STAGE_2_REVIEW.md",
    "xhs-douyin-2notion/docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "xhs-douyin-2notion/machine/facts/architecture_decisions.json",
    "xhs-douyin-2notion/machine/facts/project.json",
    "xhs-douyin-2notion/machine/facts/stage_2_gate_state.json",
    "xhs-douyin-2notion/machine/facts/task_state.json",
    "xhs-douyin-2notion/machine/policy/artifact_allowlist.json",
    "xhs-douyin-2notion/machine/schemas/stage_2_gate_state.schema.json",
    "xhs-douyin-2notion/scripts/ci/run_lane.py",
    "xhs-douyin-2notion/scripts/verify_foundation_005.py",
    "xhs-douyin-2notion/scripts/verify_skeleton_005.py",
    "xhs-douyin-2notion/scripts/verify_stage_1_review.py",
    "xhs-douyin-2notion/scripts/verify_stage_2_review.py",
    "xhs-douyin-2notion/tests/test_skeleton_005.py",
    "xhs-douyin-2notion/tests/test_stage_1_review.py",
    "xhs-douyin-2notion/tests/test_stage_2_review.py",
    "xhs-douyin-2notion/功能清单.md",
    "xhs-douyin-2notion/开发记录.md",
}
ALLOWED_REVIEW_PREFIXES = ("xhs-douyin-2notion/machine/evidence/stage_2/review/",)


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


def _reject_json_duplicates(path: Path):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            _require(key not in value, f"duplicate JSON key rejected: {path.name}")
            value[key] = item
        return value

    return hook


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_json_duplicates(path))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    value: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        _require(key not in value, "duplicate YAML key rejected")
        value[key] = loader.construct_object(value_node, deep=deep)
    return value


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _load_yaml_text(text: str, name: str) -> dict[str, Any]:
    value = yaml.load(text, Loader=_UniqueKeyLoader)
    _require(isinstance(value, dict), f"YAML object required: {name}")
    return value


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
        [git, *args], cwd=cwd, env=_git_environment(), check=False, capture_output=True, text=not binary
    )
    _require(result.returncode == 0, "local Git verification failed")
    return result.stdout if binary else str(result.stdout).rstrip()


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
    _require(len(candidates) == 1, "PR merge does not identify exactly one Stage 2 Review parent")
    return candidates[0]


def _review_bytes(path: Path) -> bytes:
    review_head = _logical_review_head()
    physical_head = str(_git(["rev-parse", "HEAD"]))
    if review_head == physical_head:
        return path.read_bytes()
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    return bytes(_git(["show", f"{review_head}:{relative}"], binary=True))


def _review_json(path: Path) -> dict[str, Any]:
    value = json.loads(_review_bytes(path).decode("utf-8"), object_pairs_hook=_reject_json_duplicates(path))
    _require(isinstance(value, dict), f"Review JSON object required: {path.name}")
    return value


def _review_yaml(path: Path) -> dict[str, Any]:
    return _load_yaml_text(_review_bytes(path).decode("utf-8"), path.name)


def _yaml_at(commit: str, path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    return _load_yaml_text(str(_git(["show", f"{commit}:{relative}"])), path.name)


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


def _validate_taskpack_review_delta(current: dict[str, Any], baseline: dict[str, Any]) -> None:
    normalized = copy.deepcopy(current)
    normalized["project"]["status"] = baseline["project"]["status"]
    authorization = normalized["authorization"]
    baseline_authorization = baseline["authorization"]
    expected = {"stage_2_review": True, "stage_2_remote_upload": True, "stage_3_task_start": False}
    for field, value in expected.items():
        _require(
            field not in baseline_authorization and authorization.get(field) is value,
            f"invalid Review authorization delta: {field}",
        )
        del authorization[field]
    authorization["instruction"] = baseline_authorization["instruction"]
    current_ids = [row.get("id") for row in normalized["tasks"]]
    baseline_ids = [row.get("id") for row in baseline["tasks"]]
    _require(current_ids == baseline_ids, "Task registry or order changed during Stage 2 Review")
    _require(normalized == baseline, "Task Pack changed outside the exact Stage 2 Review state delta")


def validate_review_documents() -> Check:
    required = (RUN_CONTRACT, REVIEW_REPORT, G2_SCHEMA, G2_FACT, FINDINGS)
    _require(all(path.is_file() for path in required), "Stage 2 Review artifact missing")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REVIEW_REPORT.read_text(encoding="utf-8")
    for token in (
        RUN_ID,
        REVIEW_ID,
        REVIEW_BASE_COMMIT,
        ORIGIN_CUTOFF,
        "不执行新的 DAG Task",
        "pending_post_g2_upload",
    ):
        _require(token in contract, f"Review Run Contract missing: {token}")
    for token in (
        "REVIEW_COMPLETE / G2_PASS",
        "PENDING_POST_G2_UPLOAD",
        "TSK.x2n.adapters.001",
        *sorted(EXPECTED_FINDINGS),
    ):
        _require(token in report, f"Stage 2 Review report missing: {token}")
    json_files = yaml_files = 0
    ignored = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "build", "node_modules", "__pycache__"}
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.suffix == ".json":
            _load_json(path)
            json_files += 1
        elif path.suffix in {".yaml", ".yml"}:
            _load_yaml_text(path.read_text(encoding="utf-8"), path.name)
            yaml_files += 1
    _load_yaml_text(WORKFLOW.read_text(encoding="utf-8"), WORKFLOW.name)
    return Check(
        "review_contract",
        "PASS",
        {"findings_declared": 8, "json_files": json_files, "new_dag_tasks": 0, "yaml_files": yaml_files + 1},
    )


def validate_task_dag_and_state() -> Check:
    taskpack = _review_yaml(TASKPACK)
    baseline = _yaml_at(REVIEW_BASE_COMMIT, TASKPACK)
    _validate_taskpack_review_delta(taskpack, baseline)
    _require(
        taskpack["project"]["status"]
        == "STAGE_2_REVIEW_PASS_G2_PASS_REMOTE_UPLOAD_AUTHORIZED_STAGE_3_PENDING_REMOTE_MERGE",
        "Task Pack status drifted",
    )
    authorization = taskpack["authorization"]
    _require(
        authorization.get("stage_2_review") is True
        and authorization.get("stage_2_remote_upload") is True
        and authorization.get("stage_3_task_start") is False,
        "Stage authorization drifted",
    )
    gate = next(row for row in taskpack["stage_gates"] if row.get("id") == "G2")
    _require(gate.get("requires_tasks") == list(SKELETON_COMMITS), "G2 Task order drifted")
    _require(gate.get("pass_conditions") == EXPECTED_G2_CONDITIONS, "G2 pass conditions drifted")
    tasks = {row.get("id"): row for row in taskpack["tasks"]}
    _require(
        all(tasks[task_id].get("status") == "completed" for task_id in SKELETON_COMMITS), "Skeleton Task incomplete"
    )
    _require(
        tasks["TSK.x2n.adapters.001"]
        == next(row for row in baseline["tasks"] if row.get("id") == "TSK.x2n.adapters.001"),
        "Stage 3 Task was entered",
    )

    state = _review_json(TASK_STATE)
    constants = {
        "schema_version": "1.18",
        "stage": "STG.X2N.2",
        "last_completed_phase": REVIEW_ID,
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "run_kind": "stage_review_no_new_dag_task",
        "state": "stage_2_review_pass_g2_pass_remote_upload_authorized_stage_3_pending_remote_merge",
        "next_phase": "STG.X2N.2.REMOTE_UPLOAD",
        "next_run": "STG.X2N.2.REMOTE_UPLOAD",
        "stage_gate": "pass",
        "remote_upload": "authorized_after_g2_pass",
        "current_stage_gate": "pass",
        "current_stage_remote_upload": "authorized_after_g2_pass",
        "remote_ci_execution": "pending_stage_2_post_g2_upload",
    }
    _require(all(state.get(key) == value for key, value in constants.items()), "Stage 2 task state drifted")
    _require(
        state.get("stage_2_review_complete") is True
        and state.get("stage_2_remote_upload_authorized") is True
        and state.get("stage_3_authorized") is False,
        "Stage 2/3 authorization state drifted",
    )
    _require(
        all(state.get("tasks", {}).get(task_id) == "pass" for task_id in SKELETON_COMMITS), "Skeleton task fact drifted"
    )
    for field in ("real_account_execution", "platform_calls", "model_calls", "media_processing"):
        _require(state.get(field) == "not_run", f"external execution overstated: {field}")
    _require(state.get("notion_calls") == "mock_only_real_api_not_run", "real Notion execution overstated")
    _require(
        _review_json(PROJECT_FACT).get("status")
        == "stage_2_review_pass_g2_pass_remote_upload_authorized_stage_3_pending_remote_merge",
        "project fact drifted",
    )
    architecture = _review_json(ARCHITECTURE_FACT)
    _require(
        architecture.get("phase") == REVIEW_ID and architecture.get("stage_gate") == "g2_pass",
        "architecture G2 fact drifted",
    )
    return Check(
        "task_dag_and_state",
        "PASS",
        {"g2_conditions": 5, "next_action": "STG.X2N.2.REMOTE_UPLOAD", "skeleton_tasks": 9, "stage_3_tasks_run": 0},
    )


def validate_gate_fact() -> Check:
    schema = _load_json(G2_SCHEMA)
    fact = _review_json(G2_FACT)
    _require(
        schema.get("additionalProperties") is False and set(schema.get("required", [])) == set(fact),
        "G2 schema/fact field set drifted",
    )
    constants = {
        "schema_version": "1.0",
        "project": "x2n",
        "stage": "STG.X2N.2",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "stage_base_commit": STAGE_BASE_COMMIT,
        "review_base_commit": REVIEW_BASE_COMMIT,
        "review_sync_target": ORIGIN_CUTOFF,
        "review_status": "complete",
        "automated_reacceptance": "pass",
        "gate_id": "G2",
        "gate_status": "pass",
        "gate_decision": "pass",
        "assurance_scope": "project_native_local_developer_gate",
        "stage_2_remote_upload_authorized": True,
        "stage_3_authorized": False,
        "remote_upload": "authorized_after_g2_pass",
        "remote_ci_execution": "pending_post_g2_upload",
        "next_action": "stage_2_whole_stage_remote_upload",
        "formal_verifier_release_candidate": "blocked_requirement_gap_missing_canonical_manifest",
        "public_release_authorized": False,
        "product_scope": "stage_2_walking_skeleton_ci_synthetic_and_notion_mock_only",
        "real_account_execution": "not_run",
        "platform_calls": "not_run",
        "notion_calls": "mock_only_real_api_not_run",
        "model_calls": "not_run",
        "media_processing": "not_run",
    }
    _require(all(fact.get(key) == value for key, value in constants.items()), "G2 fact value drifted")
    _require(fact.get("pass_conditions") == EXPECTED_PASS_CONDITIONS, "G2 pass-condition evidence drifted")
    _require(
        fact.get("stop_conditions") == EXPECTED_STOP_CONDITIONS and fact.get("blocking_followups") == [],
        "G2 stop condition is active",
    )
    return Check(
        "g2_fact",
        "PASS",
        {"blocking_followups": 0, "pass_conditions": 5, "stage_3_authorized": False, "stop_conditions": 6},
    )


def validate_findings() -> Check:
    payload = _review_json(FINDINGS)
    rows = payload.get("findings", [])
    _require(payload.get("review_id") == REVIEW_ID and payload.get("run_id") == RUN_ID, "finding identity drifted")
    _require({row.get("id") for row in rows} == EXPECTED_FINDINGS, "Review finding set drifted")
    expected_severity = {
        finding: ("MEDIUM" if finding in {"F-X2N-S02-R02", "F-X2N-S02-R03"} else "HIGH")
        for finding in EXPECTED_FINDINGS
    }
    _require(
        {row.get("id"): row.get("severity") for row in rows} == expected_severity, "Review finding severity drifted"
    )
    _require(all(row.get("status") == "RESOLVED" for row in rows), "Review finding unresolved")
    _require(
        payload.get("summary") == {"blocking_open": 0, "resolved": 8, "total": 8}, "Review finding summary drifted"
    )
    return Check("review_findings", "PASS", {"blocking_open": 0, "resolved": 8})


def _import_verifier(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "scripts" / filename)
    _require(spec is not None and spec.loader is not None, f"verifier unavailable: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PLATFORM_VERIFIER = _import_verifier("verify_skeleton_009_for_stage_2_review", "verify_skeleton_009.py")
SINK_VERIFIER = _import_verifier("verify_skeleton_005_for_stage_2_review", "verify_skeleton_005.py")
ORCHESTRATOR_VERIFIER = SINK_VERIFIER.PREVIOUS
MEDIA_VERIFIER = ORCHESTRATOR_VERIFIER.PREVIOUS


def validate_skeleton_evidence() -> Check:
    review_head = _logical_review_head()
    for task_id, commit in SKELETON_COMMITS.items():
        _require(_is_ancestor(commit, review_head), f"Skeleton commit is not an ancestor: {task_id}")
        path = SKELETON_EVIDENCE[task_id]
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        frozen = bytes(_git(["show", f"{commit}:{relative}"], binary=True))
        _require(path.read_bytes() == frozen, f"historical Skeleton evidence was rewritten: {task_id}")
        evidence = _load_json(path)
        _require(
            evidence.get("task_id") == task_id and evidence.get("run_id") == SKELETON_RUNS[task_id],
            "Skeleton evidence identity drifted",
        )
        _require(str(evidence.get("status", "")).startswith("PASS"), f"Skeleton evidence is not pass: {task_id}")
    platform_checks = PLATFORM_VERIFIER.run_checks(
        verify_worktree=False, allow_external_main_dirty=False, run_external=False
    )
    sink_checks = SINK_VERIFIER.run_checks(verify_worktree=False, allow_external_main_dirty=False, run_external=False)
    _require(
        all(row.status == "PASS" for row in platform_checks + sink_checks), "historical Skeleton regression failed"
    )
    return Check(
        "skeleton_evidence",
        "PASS",
        {
            "frozen_receipts": 9,
            "historical_checks": len(platform_checks) + len(sink_checks),
            "rewritten_receipts": 0,
            "skeleton_tasks": 9,
        },
    )


def _expected_blocking_results() -> list[dict[str, Any]]:
    return [
        {"blocking": True, "gate": gate, "label": f"{gate}_r{repetition}", "repetition": repetition, "status": "PASS"}
        for repetition in (1, 2)
        for gate in EXPECTED_GATES
    ]


def validate_lane_report(path: Path) -> Check:
    report = _load_json(path)
    _require(report.get("status") == "PASS" and report.get("lane") == "full", "full lane report missing or failed")
    _require(
        report.get("blocking_commands") == 12
        and report.get("blocking_repetitions") == 2
        and report.get("blocking_executions") == 24,
        "blocking execution count drifted",
    )
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
    _require(
        report.get("explicit_nonblocking_skips") == 6 and report.get("artifact_deterministic") is True,
        "lane quality evidence drifted",
    )
    _require(
        report.get("stage_gate_evaluation") == "NOT_PERFORMED_BY_SOFTWARE_LANE" and "g1" not in report,
        "software lane claimed a dynamic stage gate",
    )
    _require(report.get("remote_github_actions") == "NOT_RUN_LOCAL_BASELINE", "software lane overstated remote CI")
    toolchain = report.get("toolchain", {})
    expected = _load_json(CI_POLICY).get("toolchain", {})
    actual = toolchain.get("actual", {})
    _require(
        toolchain.get("status") == "PASS"
        and toolchain.get("policy_id") == "CI.X2N.001"
        and toolchain.get("policy_sha256") == hashlib.sha256(CI_POLICY.read_bytes()).hexdigest()
        and toolchain.get("expected") == expected,
        "toolchain policy identity drifted",
    )
    try:
        LANE._validate_toolchain_versions(expected, actual)
    except LANE.LaneError as error:
        raise ReviewError("software lane toolchain identity drifted") from error
    _require(
        report.get("coverage", {}).get("status") == "PASS"
        and len(report.get("coverage", {}).get("critical_modules", {})) == 7,
        "coverage evidence incomplete",
    )
    _require(
        report.get("osv", {}).get("status") == "PASS" and report.get("osv", {}).get("vulnerabilities_reported") == 0,
        "OSV evidence failed",
    )
    artifact_report = report.get("artifact_report", {})
    artifact = path.parent / "x2n-source-candidate.zip"
    _require(
        artifact_report.get("member_count") == 65
        and artifact_report.get("runtime_data_files") == 0
        and artifact_report.get("allowlist_findings") == 0,
        "candidate boundary drifted",
    )
    _require(
        artifact.is_file()
        and hashlib.sha256(artifact.read_bytes()).hexdigest() == artifact_report.get("artifact_sha256"),
        "candidate receipt drifted",
    )
    for filename, status in {
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
    }.items():
        _require(_load_json(path.parent / filename).get("status") == status, f"lane subreport failed: {filename}")
    return Check(
        "g2_full_lane",
        "PASS",
        {
            "artifact_members": 65,
            "blocking_executions": 24,
            "blocking_failures": 0,
            "blocking_repetitions": 2,
            "explicit_nonblocking_skips": 6,
            "python": actual["python"],
            "silent_blocking_skips": 0,
        },
    )


def validate_g2_acceptance() -> Check:
    platform = PLATFORM_VERIFIER.validate_execution()
    media = MEDIA_VERIFIER.validate_execution()
    orchestration = ORCHESTRATOR_VERIFIER.validate_execution()
    sinks = SINK_VERIFIER.validate_execution()
    _require(
        all(row.status == "PASS" for row in (platform, media, orchestration, sinks)), "G2 component acceptance failed"
    )
    platform_details = platform.details
    _require(
        platform_details.get("service_worker_restarts_per_platform") == 100
        and platform_details.get("action_before_grant_rejections_per_platform") == 2
        and platform_details.get("platform_calls") == 0
        and platform_details.get("owner_canary") == "NOT_RUN",
        "six-platform walking path gate drifted",
    )
    for name in ("xhs", "douyin", "bilibili", "kuaishou", "weibo", "taobao"):
        for receipt in ("screenshot", "trace"):
            value = platform_details.get(f"{name}_{receipt}", {})
            _require(
                isinstance(value.get("bytes"), int)
                and value["bytes"] > 0
                and re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", ""))) is not None,
                f"{name} {receipt} receipt invalid",
            )
    _require(
        media.details.get("scanner_findings") == 0
        and media.details.get("cleanup_cases") == 8
        and media.details.get("active_lease_misdeletes") == 0,
        "media cleanup/CDN gate drifted",
    )
    _require(
        orchestration.details.get("duplicate_entities") == 0
        and orchestration.details.get("stuck_runs") == 0
        and orchestration.details.get("broken_provenance_traces") == 0,
        "canonical idempotency gate drifted",
    )
    _require(
        sinks.details.get("duplicate_pages") == 0
        and sinks.details.get("partial_files") == 0
        and sinks.details.get("unit_tests", 0) >= 17
        and sinks.details.get("notion_real_api_calls") == 0,
        "sink/outage gate drifted",
    )
    return Check(
        "g2_acceptance",
        "PASS",
        {
            "cdn_persistence_findings": 0,
            "duplicate_entities": 0,
            "duplicate_notion_pages": 0,
            "media_cleanup_cases": 8,
            "notion_outage_canonical_markdown_independent": True,
            "platform_calls": 0,
            "platforms": 6,
            "service_worker_restarts_per_platform": 100,
        },
    )


def _relevant_history_path(path: str) -> bool:
    return path == ".github/workflows/x2n-ci.yml" or path.startswith("xhs-douyin-2notion/")


def validate_history_privacy() -> Check:
    review_head = _logical_review_head()
    commits = str(_git(["rev-list", "--reverse", f"{STAGE_BASE_COMMIT}..{review_head}"])).splitlines()
    expected = list(SKELETON_COMMITS.values())
    _require(commits[:9] == expected and len(commits) in {9, 10}, "Stage 2 commit lineage drifted")
    if len(commits) == 10:
        _require(commits[-1] == review_head, "unexpected commit after Stage 2 Review")
    denied_suffixes = set(
        _load_json(PROJECT_ROOT / "machine/policy/release_artifact_allowlist.json")["denied_suffixes"]
    )
    findings = []
    blob_versions = 0
    for index, commit in enumerate(commits, start=1):
        findings.extend(scan_text(str(_git(["show", "-s", "--format=%B", commit])), f"commit-message/{index}"))
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
            _require(Path(path).suffix.lower() not in denied_suffixes, "denied file type exists in Stage 2 history")
            result = subprocess.run(
                [shutil.which("git") or "git", "show", f"{commit}:{path}"],
                cwd=REPOSITORY_ROOT,
                env=_git_environment(),
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                continue
            _require(len(result.stdout) <= 4 * 1024 * 1024, "oversized file exists in Stage 2 history")
            try:
                text = result.stdout.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ReviewError("binary file exists in Stage 2 history") from error
            findings.extend(scan_text(text, path))
            blob_versions += 1
    current = scan_source()
    _require(
        current.get("status") == "PASS" and current.get("finding_count") == 0, "current source privacy scan failed"
    )
    findings.extend(scan_text(WORKFLOW.read_text(encoding="utf-8"), ".github/workflows/x2n-ci.yml"))
    _require(not findings, "Secret/Private/CDN material exists in Stage 2 history or current tree")
    return Check(
        "stage_2_history_privacy",
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
            _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{REVIEW_BASE_COMMIT}..{review_head}"])
        ).splitlines()
    )
    if review_head == physical_head:
        changed.update(str(_git(["-c", "core.quotePath=false", "diff", "--name-only", review_head])).splitlines())
    changed.update(str(_git(["-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard"])).splitlines())
    return {path for path in changed if path}


def validate_review_scope() -> Check:
    changes = _changed_review_paths()
    _require(changes, "Stage 2 Review has no recorded change")
    for path in changes:
        _require(
            path in ALLOWED_REVIEW_EXACT or any(path.startswith(prefix) for prefix in ALLOWED_REVIEW_PREFIXES),
            f"out-of-scope Stage 2 Review change: {path}",
        )
    product_changes = [
        path for path in changes if path.startswith(("xhs-douyin-2notion/apps/", "xhs-douyin-2notion/packages/"))
    ]
    _require(not product_changes, "Stage 2 Review entered product or Stage 3 implementation")
    return Check(
        "review_scope",
        "PASS",
        {"changed_files": len(changes), "new_dag_tasks": 0, "product_changes": 0, "stage_3_tasks_run": 0},
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    review_head = _logical_review_head()
    _require(Path(str(_git(["rev-parse", "--show-toplevel"]))).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    current_branch = str(_git(["branch", "--show-current"]))
    if review_head == str(_git(["rev-parse", "HEAD"])):
        _require(current_branch == REVIEW_BRANCH, "wrong Stage 2 Review branch")
    else:
        _require(current_branch == "", "PR merge verification must be detached")
    persisted_remote = str(_git(["config", "--local", "--get", "remote.origin.url"]))
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    _require(_is_ancestor(REVIEW_BASE_COMMIT, review_head), "Review no longer descends from Skeleton005")
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
    _require(not overlap, "origin/main and Stage 2 branch overlap")
    return Check(
        "worktree_isolation",
        "PASS",
        {
            "branch": REVIEW_BRANCH,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(str(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"]))),
            "origin_overlap": 0,
            "project_overlap_paths": main_overlap,
        },
    )


def run_checks(
    *, lane_report: Path, verify_worktree: bool, allow_external_main_dirty: bool, run_g2_acceptance: bool
) -> list[Check]:
    checks = [
        validate_review_documents(),
        validate_task_dag_and_state(),
        validate_gate_fact(),
        validate_findings(),
        validate_skeleton_evidence(),
        validate_lane_report(lane_report),
        validate_history_privacy(),
        validate_review_scope(),
    ]
    if run_g2_acceptance:
        checks.append(validate_g2_acceptance())
    if verify_worktree:
        checks.append(validate_worktree(allow_external_main_dirty))
    _require(all(check.status == "PASS" for check in checks), "a Stage 2 Review check failed")
    return checks


def write_evidence(checks: list[Check]) -> None:
    _require(
        any(check.name == "g2_acceptance" for check in checks), "G2 evidence requires live local acceptance replay"
    )
    payload = {
        "assurance_scope": "PROJECT_NATIVE_LOCAL_DEVELOPER_GATE",
        "automated_reacceptance": "PASS",
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "formal_verifier_release_candidate": "BLOCKED_REQUIREMENT_GAP_MISSING_CANONICAL_MANIFEST",
        "g2": "PASS",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model_calls": 0,
        "notion_real_api_calls": 0,
        "platform_calls": 0,
        "private_content_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_ci_execution": "PENDING_POST_G2_UPLOAD",
        "review_base_commit": REVIEW_BASE_COMMIT,
        "review_id": REVIEW_ID,
        "review_sync_target": ORIGIN_CUTOFF,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.2",
        "status": "PASS",
    }
    _safe_payload(payload)
    VERIFICATION_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    VERIFICATION_EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fact = _review_json(G2_FACT)
    _safe_payload(fact)
    G2_EVIDENCE.write_text(json.dumps(fact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    verification = _load_json(VERIFICATION_EVIDENCE)
    gate = _load_json(G2_EVIDENCE)
    fact = _review_json(G2_FACT)
    _safe_payload(verification)
    _safe_payload(gate)
    _require(
        verification.get("review_id") == REVIEW_ID
        and verification.get("run_id") == RUN_ID
        and verification.get("status") == "PASS"
        and verification.get("g2") == "PASS",
        "Review evidence identity/status drifted",
    )
    _require(
        verification.get("remote_ci_execution") == "PENDING_POST_G2_UPLOAD"
        and verification.get("formal_verifier_release_candidate")
        == "BLOCKED_REQUIREMENT_GAP_MISSING_CANONICAL_MANIFEST",
        "Review evidence overstates remote/formal assurance",
    )
    _require(
        all(row.get("status") == "PASS" for row in verification.get("checks", [])),
        "Review evidence contains a failed check",
    )
    _require(gate == fact, "G2 evidence/fact drifted")
    return Check(
        "evidence",
        "PASS",
        {
            "g2_receipt_sha256": hashlib.sha256(G2_EVIDENCE.read_bytes()).hexdigest(),
            "verification_receipt_sha256": hashlib.sha256(VERIFICATION_EVIDENCE.read_bytes()).hexdigest(),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify STG.X2N.2.REVIEW and project-native local G2")
    parser.add_argument("--lane-report", type=Path, required=True)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--run-g2-acceptance", action="store_true")
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
            run_g2_acceptance=args.run_g2_acceptance,
        )
        if args.write_evidence:
            _require(args.run_g2_acceptance, "--write-evidence requires --run-g2-acceptance")
            write_evidence(checks)
        if args.require_evidence:
            checks.append(verify_evidence())
        print(
            json.dumps(
                {
                    "checks": [{"name": check.name, "status": check.status} for check in checks],
                    "formal_verifier_release_candidate": "BLOCKED_REQUIREMENT_GAP",
                    "g2": "PASS",
                    "next_action": "STAGE_2_REMOTE_UPLOAD",
                    "remote_ci_execution": "PENDING_POST_G2_UPLOAD",
                    "status": "PASS",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (LANE.LaneError, OSError, ValueError, ReviewError, yaml.YAMLError) as error:
        print(
            json.dumps({"reason": str(error), "status": "FAIL_CLOSED"}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
