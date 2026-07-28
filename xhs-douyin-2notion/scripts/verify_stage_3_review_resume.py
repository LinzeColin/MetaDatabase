#!/usr/bin/env python3
"""Fail-closed verifier for the frozen x2n Stage 3 Review Resume contract.

The historical Resume contract remains independently verifiable after
TSK.x2n.adapters.010 has executed. This verifier never decides current G3;
when a separate recheck fact exists, it only confirms the fact's bounded local
Stage 4 routing. It never authorizes upload, deployment, or real execution.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
PRFAQ = PROJECT_ROOT / "docs/product_design/v0.0.0.1/00_PRFAQ.md"
PRD = PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md"
ROADMAP = PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md"
RELEASE_OPERATIONS = PROJECT_ROOT / "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_REVIEW_RESUME_MVP.md"
REVIEW_REPORT = PROJECT_ROOT / "docs/governance/STAGE_3_REVIEW_RESUME_MVP.md"
ARTIFACT_RUNTIME_POLICY = PROJECT_ROOT / "docs/governance/ARTIFACT_RUNTIME_POLICY.md"
RESUME_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_3_review_resume_state.schema.json"
RESUME_FACT = PROJECT_ROOT / "machine/facts/stage_3_review_resume_state.json"
HISTORICAL_GATE_FACT = PROJECT_ROOT / "machine/facts/stage_3_gate_state.json"
PATH_CONTRACT = PROJECT_ROOT / "machine/facts/path_contract.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
ID_REGISTRY = PROJECT_ROOT / "machine/facts/id_registry.json"
DECISION_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_3/review_resume_mvp/decision.json"
CLIENT_AUDIT = PROJECT_ROOT / "machine/evidence/stage_3/review_resume_mvp/private_db_client_audit.json"
VERIFICATION_EVIDENCE = PROJECT_ROOT / "machine/evidence/stage_3/review_resume_mvp/verification.json"
DEFAULT_LANE_REPORT = PROJECT_ROOT / "build/s03-review-resume-mvp/software-lane.json"

REVIEW_ID = "STG.X2N.3.REVIEW.RESUME"
RUN_ID = "RUN-X2N-S03-REVIEW-RESUME-MVP"
CHANGE_EVENT = "CE-X2N-20260728-S03-REVIEW-RESUME-MVP"
BASE_COMMIT = "6b3f5464d1ed645d31c3650b9b51998c9e4fe1ab"
TASK010_BASE_COMMIT = "2e7de513f4d5d829c78a4d015aa2297575522434"
HISTORICAL_GATE_SHA256 = "0243a478273de9bda16803e7311ef56c7e461c2bc3b8c871c5d2c1c87cdd6772"
EXPECTED_BRANCH = "codex/xhs-douyin-2notion-v0001-s03-review-resume"
NEXT_TASK = "TSK.x2n.adapters.010"
TASK010_RUN_ID = "RUN-X2N-S03-A010"
TASK010_RECHECK = "STG.X2N.3.REVIEW.RESUME.RECHECK"
G3_RECHECK_RUN_ID = "RUN-X2N-S03-REVIEW-RESUME-RECHECK"
G3_RECHECK_FACT = PROJECT_ROOT / "machine/facts/stage_3_review_resume_recheck_state.json"
STAGE4_NEXT_TASK = "TSK.x2n.multimodal.001"
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
EXPECTED_CAPABILITY_REASON_PRECEDENCE = [
    "BLOCKED_TECHNICAL",
    "UNKNOWN_DISABLED",
    "BLOCKED_POLICY",
    "BLOCKED_AUTH",
    "BLOCKED_BUDGET",
    "BLOCKED_CAPABILITY",
    "CI_SYNTH_READY",
]

EXPECTED_STAGE_COUNTS = {
    "STG.X2N.0": 5,
    "STG.X2N.1": 5,
    "STG.X2N.2": 9,
    "STG.X2N.3": 10,
    "STG.X2N.4": 5,
    "STG.X2N.5": 5,
    "STG.X2N.6": 5,
}
EXPECTED_EFFORTS = {"low": 360, "likely": 692, "high": 1323}
EXPECTED_RELEASE_GATE_ORDER = [
    "G0_TO_G5_PASS",
    "ASSURANCE_001_TO_004_AND_UXOPS_005_COMPLETE",
    "DEPLOYMENT_INDEPENDENT_BLOCKING_ACCEPTANCES_PASS",
    "START_ASSURANCE_005",
    "ASSURANCE_005_BOUNDED_ACTIVATION_OWNER_MVP_SECURITY_PASS_MODEL_PASS_OR_DISABLED_ROLLBACK_SIGNOFF_PASS",
    "ASSURANCE_005_DEPLOY_RUN_ONLINE_SMOKE",
    "G6_PASS",
]
EXPECTED_ASSURANCE_005_START_CONDITIONS = [
    "G0_TO_G5_PASS",
    "ASSURANCE_001_TO_004_AND_UXOPS_005_COMPLETE",
    "ALL_BLOCKING_ACCEPTANCES_OUTSIDE_ASSURANCE_005_OWNED_IN_TASK_SET_PASS",
]
EXPECTED_ASSURANCE_005_IN_TASK_PRE_SWITCH_CHECKS = [
    "EIGHTY_ITEM_XHS_DOUYIN_OWNER_MVP_BASELINE_PASS",
    "EACH_ADDITIONAL_ENABLED_CAPABILITY_INDEPENDENT_MAX_TWENTY_ITEM_ACTIVATION_PASS",
    "SECURITY_ASSURANCE_PASS_MODEL_PASS_OR_EXPLICITLY_DISABLED_OR_SUGGESTION_ONLY",
    "ROLLBACK_REHEARSAL_PASS",
    "OWNER_SIGNOFF",
]
EXPECTED_ASSURANCE_005_OWNED_ACCEPTANCES = [
    "ACC.x2n.capture.001",
    "ACC.x2n.capture.002",
    "ACC.x2n.capture.003",
    "ACC.x2n.capture.004",
    "ACC.x2n.capture.005",
    "ACC.x2n.capture.006",
    "ACC.x2n.xhs.001",
    "ACC.x2n.xhs.002",
    "ACC.x2n.dy.001",
    "ACC.x2n.dy.002",
    "ACC.x2n.bili.001",
    "ACC.x2n.ks.001",
    "ACC.x2n.wb.001",
    "ACC.x2n.tb.001",
    "ACC.x2n.data.002",
    "ACC.x2n.rel.006",
    "ACC.x2n.rel.007",
    "ACC.x2n.rel.008",
]
EXPECTED_G3_CONDITIONS = [
    "eight independently scoped relation/list synthetic requests traverse Extension-to-Native-to-Adapter dispatch",
    "a valid complete snapshot persists exactly eight capability_gate_outcome rows, one per scope, with READY_FOR_MVP_ACTIVATION or DISABLED_EXTERNAL_GATE and deterministic fine-grained reason; any BLOCKED_TECHNICAL reason prevents the complete snapshot and leaves G3 blocked with no legal terminal",
    "checkpoint/resume and worker/companion restart reconciliation pass",
    "no empty-response deletion",
    "adapter failure durably reaches run_record failed plus one sanitized run_failure row and the Side Panel derives FALLBACK_AVAILABLE without a second run state",
    "current-page fallback requires a separate second explicit Owner action and automatic fallback count remains zero",
]
EXPECTED_G6_CONDITIONS = [
    "all blocking acceptances pass",
    "eighty-item XHS/Douyin owner mvp baseline passes",
    "every additional enabled capability passes an independent activation check of no more than twenty items",
    "security assurance passes; model capability passes or is explicitly disabled or degraded to suggestion-only",
    "rollback rehearsal passes",
    "owner signs off",
    "the unique v0.0.0.1 release is deployed, running and online-smoke verified in the same release task",
    "no prerelease phase, fixed observation period or soak gate is inserted",
    "G6 is evaluated only after assurance.005 finishes deployment and online smoke and is never a precondition to assurance.005",
]
EXPECTED_FAST_LANE_GATES = [
    "format",
    "lint",
    "python_compile",
    "typescript_contract",
    "root_unit",
    "companion_unit_integration",
    "contract_unit",
    "contract_acceptance",
    "sbom_drift",
]
ACTIVE_PRODUCT_DOCS = (
    PRFAQ,
    PRD,
    ROADMAP,
    PROJECT_ROOT / "docs/product_design/v0.0.0.1/03_ARCHITECTURE_SECURITY_SYSTEM_CARD.md",
    ACCEPTANCE,
    TASKPACK,
    RELEASE_OPERATIONS,
)
ACTIVE_CONTROL_FILES = (
    *ACTIVE_PRODUCT_DOCS,
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "HANDOFF.md",
    PROJECT_ROOT / "CHANGELOG.md",
    PROJECT_ROOT / "功能清单.md",
    PROJECT_ROOT / "开发记录.md",
    PROJECT_ROOT / "PURSUING_GOAL.md",
    RUN_CONTRACT,
    REVIEW_REPORT,
    ARTIFACT_RUNTIME_POLICY,
    RESUME_SCHEMA,
    RESUME_FACT,
    PATH_CONTRACT,
    PROJECT_FACT,
    TASK_STATE,
    ARCHITECTURE_FACT,
    ID_REGISTRY,
    DECISION_EVIDENCE,
    CLIENT_AUDIT,
    VERIFICATION_EVIDENCE,
)
HISTORICAL_CORE_PATHS = (
    PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_REVIEW.md",
    PROJECT_ROOT / "docs/governance/STAGE_3_REVIEW.md",
    PROJECT_ROOT / "machine/schemas/stage_3_gate_state.schema.json",
    HISTORICAL_GATE_FACT,
    PROJECT_ROOT / "machine/evidence/stage_3/review/G3.json",
    PROJECT_ROOT / "machine/evidence/stage_3/review/findings.json",
    PROJECT_ROOT / "machine/evidence/stage_3/review/verification.json",
)
RESUME_CHANGED_PATH_ALLOWLIST = frozenset(
    {
        "xhs-douyin-2notion/AGENTS.md",
        "xhs-douyin-2notion/CHANGELOG.md",
        "xhs-douyin-2notion/HANDOFF.md",
        "xhs-douyin-2notion/PURSUING_GOAL.md",
        "xhs-douyin-2notion/README.md",
        "xhs-douyin-2notion/docs/governance/ARTIFACT_RUNTIME_POLICY.md",
        "xhs-douyin-2notion/docs/governance/RUN_CONTRACT_S03_REVIEW_RESUME_MVP.md",
        "xhs-douyin-2notion/docs/governance/STAGE_3_REVIEW_RESUME_MVP.md",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/00_PRFAQ.md",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/01_PRD.md",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/02_ROADMAP.md",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/03_ARCHITECTURE_SECURITY_SYSTEM_CARD.md",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
        "xhs-douyin-2notion/docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
        "xhs-douyin-2notion/machine/evidence/stage_3/review_resume_mvp/decision.json",
        "xhs-douyin-2notion/machine/evidence/stage_3/review_resume_mvp/private_db_client_audit.json",
        "xhs-douyin-2notion/machine/evidence/stage_3/review_resume_mvp/verification.json",
        "xhs-douyin-2notion/machine/facts/architecture_decisions.json",
        "xhs-douyin-2notion/machine/facts/id_registry.json",
        "xhs-douyin-2notion/machine/facts/path_contract.json",
        "xhs-douyin-2notion/machine/facts/project.json",
        "xhs-douyin-2notion/machine/facts/stage_3_review_resume_state.json",
        "xhs-douyin-2notion/machine/facts/task_state.json",
        "xhs-douyin-2notion/machine/schemas/stage_3_review_resume_state.schema.json",
        "xhs-douyin-2notion/scripts/verify_foundation_001.py",
        "xhs-douyin-2notion/scripts/verify_phase_0_1.py",
        "xhs-douyin-2notion/scripts/verify_phase_0_5.py",
        "xhs-douyin-2notion/scripts/verify_stage_3_review.py",
        "xhs-douyin-2notion/scripts/verify_stage_3_review_resume.py",
        "xhs-douyin-2notion/tests/test_stage_3_review_resume.py",
        "xhs-douyin-2notion/功能清单.md",
        "xhs-douyin-2notion/开发记录.md",
    }
)
EXPECTED_RECORDED_EVIDENCE_CHECKS = {
    "resume_fact_and_schema",
    "historical_review_integrity",
    "taskpack_and_traceability",
    "release_and_data_contracts",
    "documents_and_source_safety",
    "decision_evidence",
    "private_db_client_read_only_audit",
    "worktree_isolation",
    "bounded_fast_software_lane",
}
EVIDENCE_DIGEST_PATHS = (
    RESUME_SCHEMA,
    RESUME_FACT,
    TASKPACK,
    ACCEPTANCE,
    RUN_CONTRACT,
    REVIEW_REPORT,
    PATH_CONTRACT,
    DECISION_EVIDENCE,
    CLIENT_AUDIT,
)


class ResumeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ResumeError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResumeError(message)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _load_yaml_unique(path: Path) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    _require(isinstance(value, dict), f"YAML object required: {path.name}")
    return value


def _git(args: list[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    _require(result.returncode == 0, f"git command failed: {' '.join(args)}")
    return result.stdout.rstrip()


def _blob_at(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )
    _require(result.returncode == 0, f"historical blob missing: {relative}")
    return result.stdout


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _historical_protected_paths() -> tuple[Path, ...]:
    historical_fact = json.loads(_blob_at(BASE_COMMIT, HISTORICAL_GATE_FACT))
    receipt_paths: list[Path] = []
    for receipt in historical_fact.get("required_task_receipts", []):
        relative = receipt.get("evidence_path")
        _require(isinstance(relative, str) and relative, "historical receipt path missing")
        candidate = (PROJECT_ROOT / relative).resolve()
        _require(candidate.is_relative_to(PROJECT_ROOT), "historical receipt path escaped project")
        receipt_paths.append(candidate)
    protected = tuple(HISTORICAL_CORE_PATHS) + tuple(receipt_paths)
    _require(len(protected) == 16 and len(set(protected)) == 16, "historical protected set must contain 16 unique files")
    return tuple(sorted(protected, key=lambda item: item.relative_to(REPOSITORY_ROOT).as_posix()))


def _historical_manifest(protected: Iterable[Path]) -> tuple[int, str]:
    records: list[bytes] = []
    count = 0
    for path in protected:
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        historical = _blob_at(BASE_COMMIT, path)
        current = path.read_bytes()
        _require(current == historical, f"historical artifact was rewritten: {relative}")
        records.append(f"{relative}\0{_sha256_bytes(current)}\n".encode())
        count += 1
    return count, _sha256_bytes(b"".join(records))


def _lane_input_paths() -> tuple[Path, ...]:
    output_path = VERIFICATION_EVIDENCE.relative_to(REPOSITORY_ROOT).as_posix()
    paths = tuple(
        REPOSITORY_ROOT / relative
        for relative in sorted(RESUME_CHANGED_PATH_ALLOWLIST - {output_path})
    )
    _require(all(path.is_file() for path in paths), "lane input allowlist contains a missing source file")
    return paths


def _source_manifest(paths: Iterable[Path]) -> tuple[int, str]:
    records: list[bytes] = []
    count = 0
    for path in paths:
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        records.append(f"{relative}\0{_sha256(path)}\n".encode())
        count += 1
    return count, _sha256_bytes(b"".join(records))


def _validate_schema_instance(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    """Validate the strict JSON-Schema subset used by the Resume fact.

    Keeping this subset local avoids adding a runtime/CI dependency solely for
    one governance artifact while still checking every required/const/enum
    field and rejecting undeclared properties.
    """

    if "const" in schema:
        _require(value == schema["const"], f"{path} must equal its schema const")
    if "enum" in schema:
        _require(value in schema["enum"], f"{path} is outside its schema enum")

    expected_type = schema.get("type")
    if expected_type == "object":
        _require(isinstance(value, dict), f"{path} must be an object")
        required = schema.get("required", [])
        _require(set(required).issubset(value), f"{path} missing required properties")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            _require(set(value).issubset(properties), f"{path} contains undeclared properties")
        for key, child in properties.items():
            if key in value:
                _validate_schema_instance(child, value[key], f"{path}.{key}")
    elif expected_type == "array":
        _require(isinstance(value, list), f"{path} must be an array")
        _require(len(value) >= schema.get("minItems", 0), f"{path} has too few items")
        if "maxItems" in schema:
            _require(len(value) <= schema["maxItems"], f"{path} has too many items")
        if schema.get("uniqueItems"):
            rendered = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
            _require(len(rendered) == len(set(rendered)), f"{path} items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema_instance(item_schema, item, f"{path}[{index}]")
    elif expected_type == "string":
        _require(isinstance(value, str), f"{path} must be a string")
    elif expected_type == "boolean":
        _require(isinstance(value, bool), f"{path} must be a boolean")
    elif expected_type == "integer":
        _require(isinstance(value, int) and not isinstance(value, bool), f"{path} must be an integer")
    elif expected_type == "number":
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{path} must be a number",
        )


def _validate_resume_fact(fact: dict[str, Any]) -> None:
    schema = _load_json(RESUME_SCHEMA)
    _require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and schema.get("type") == "object"
        and schema.get("additionalProperties") is False,
        "Resume fact schema header is not strict draft 2020-12",
    )
    _validate_schema_instance(schema, fact)
    _require(
        fact["decision"] == {
            "review_status": "contract_versioned",
            "gate_id": "G3",
            "gate_status": "BLOCKED_TECHNICAL",
            "gate_decision": "FAIL_CLOSED",
        },
        "G3 Resume decision was overstated",
    )
    _require(
        fact["authorization"]
        == {
            "contract_only": True,
            "new_dag_task_executed": False,
            "stage_3_upload": False,
            "stage_4": False,
            "deployment": False,
        },
        "Resume authorization escaped contract-only scope",
    )
    capability = fact["capability_terminal_contract"]
    _require(
        capability.get("scope_ids") == EXPECTED_SCOPE_IDS
        and capability.get("durable_table") == "capability_gate_outcome"
        and capability.get("persistence")
        == "AT_MOST_ONE_ROW_PER_SCOPE_EXACTLY_EIGHT_ONLY_FOR_VALID_COMPLETE_EVALUATION"
        and capability.get("required_columns")
        == [
            "scope_id",
            "terminal",
            "reason_code",
            "source_registry_digests",
            "evidence_hash",
            "evaluated_at",
        ]
        and capability.get("reason_precedence") == EXPECTED_CAPABILITY_REASON_PRECEDENCE
        and capability.get("ready_reason") == "CI_SYNTH_READY"
        and capability.get("technical_reason_semantics")
        == "GLOBAL_VETO_BEFORE_EXTERNAL_PRECEDENCE_FAIL_CLOSED_NO_LEGAL_TERMINAL_G3_BLOCKED"
        and capability.get("runtime_authority")
        == "SQLITE_CAPABILITY_GATE_OUTCOME_DERIVED_SNAPSHOT"
        and capability.get("registry_role")
        == "VERSIONED_INPUT_NOT_COMPETING_RUNTIME_STATE",
        "capability terminal persistence, authority, or reason precedence drifted",
    )
    _require(
        fact["external_execution"].get("evidence_class")
        == "PROCESS_ATTESTATION_NOT_INDEPENDENTLY_OBSERVED_BY_OFFLINE_VERIFIER"
        and fact["isolation"].get("local_state_evidence_class") == "OFFLINE_GIT_VERIFIED"
        and fact["isolation"].get("external_state_evidence_class")
        == "PRIOR_READ_ONLY_CHECK_AND_PROCESS_ATTESTATION_NOT_REVERIFIED_OFFLINE",
        "external/process evidence classification drifted",
    )


def validate_resume_fact_and_schema() -> Check:
    _require(RESUME_SCHEMA.is_file() and RESUME_FACT.is_file(), "Resume schema/fact missing")
    fact = _load_json(RESUME_FACT)
    _validate_resume_fact(fact)
    return Check(
        "resume_fact_and_schema",
        "PASS",
        {
            "gate_status": fact["decision"]["gate_status"],
            "resolved_blockers": len(fact["resolved_blockers"]),
            "remaining_blockers": len(fact["remaining_blockers"]),
            "next_task": fact["next_task"]["id"],
        },
    )


def validate_historical_integrity() -> Check:
    protected = _historical_protected_paths()
    count, manifest_sha256 = _historical_manifest(protected)
    _require(_sha256(HISTORICAL_GATE_FACT) == HISTORICAL_GATE_SHA256, "historical gate fact digest drifted")
    return Check(
        "historical_review_integrity",
        "PASS",
        {
            "commit": BASE_COMMIT,
            "protected_files": count,
            "protected_manifest_sha256": manifest_sha256,
            "gate_fact_sha256": HISTORICAL_GATE_SHA256,
        },
    )


def _acceptance_ids() -> list[str]:
    return re.findall(
        r"^## (ACC\.x2n\.[a-z]+\.\d{3})\b",
        ACCEPTANCE.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )


def _validate_dag(tasks: list[dict[str, Any]], order: list[str]) -> None:
    task_ids = [item.get("id") for item in tasks]
    _require(None not in task_ids and len(task_ids) == len(set(task_ids)), "task IDs missing or duplicated")
    by_id = {item["id"]: item for item in tasks}
    _require(len(order) == len(tasks) and len(order) == len(set(order)), "topological order coverage drifted")
    _require(set(order) == set(by_id), "topological order does not cover the DAG")
    positions = {task_id: index for index, task_id in enumerate(order)}
    for task in tasks:
        for dependency in task.get("depends_on", []):
            _require(dependency in by_id, f"unknown dependency: {dependency}")
            _require(
                positions[dependency] < positions[task["id"]],
                f"invalid topological order: {dependency} -> {task['id']}",
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        _require(task_id not in visiting, f"DAG cycle detected at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].get("depends_on", []):
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)


def _validate_taskpack_payload(taskpack: dict[str, Any]) -> None:
    project = taskpack.get("project", {})
    authorization = taskpack.get("authorization", {})
    execution = taskpack.get("execution_policy", {})
    _require(project.get("status") == "STAGE_3_REVIEW_RESUME_CONTRACT_VERSIONED_G3_BLOCKED_TECHNICAL", "Taskpack status drifted")
    _require(project.get("owner_change_event") == CHANGE_EVENT, "Owner Change Event missing")
    _require(authorization.get("stage_3_review_resume") is True, "Resume is not authorized")
    _require(
        authorization.get("stage_3_remote_upload") is False
        and authorization.get("stage_4_task_start") is False
        and authorization.get("public_release") is False,
        "Taskpack prematurely authorized upload, Stage 4, or release",
    )
    _require(
        execution.get("pre_release_phases") == "prohibited"
        and execution.get("fixed_wait_or_soak_gate") == "prohibited"
        and execution.get("post_go_live_monitoring") == "non_blocking",
        "direct MVP release policy drifted",
    )
    _require(
        execution.get("release_gate_order") == EXPECTED_RELEASE_GATE_ORDER,
        "release gate order is circular or drifted",
    )
    _require(
        execution.get("assurance_005_owned_in_task_acceptance_ids")
        == EXPECTED_ASSURANCE_005_OWNED_ACCEPTANCES,
        "assurance.005 in-task Acceptance ownership set drifted",
    )
    _require(
        execution.get("previous_stage_gate_pass_required") is True
        and execution.get("stage_entry_gate_map")
        == {
            "STG.X2N.1": "G0",
            "STG.X2N.2": "G1",
            "STG.X2N.3": "G2",
            "STG.X2N.4": "G3",
            "STG.X2N.5": "G4",
            "STG.X2N.6": "G5",
        },
        "previous-stage Gate start barrier drifted",
    )

    tasks = taskpack.get("tasks", [])
    _require(isinstance(tasks, list) and len(tasks) == 44, "DAG must contain exactly 44 tasks")
    acceptances = _acceptance_ids()
    _require(len(acceptances) == 62 and len(set(acceptances)) == 62, "Acceptance registry must contain 62 unique IDs")
    acceptance_set = set(acceptances)
    for task in tasks:
        _require(
            task.get("acceptance_ids")
            and set(task["acceptance_ids"]).issubset(acceptance_set),
            f"task acceptance trace drifted: {task.get('id')}",
        )

    stage_counts = {stage: 0 for stage in EXPECTED_STAGE_COUNTS}
    for task in tasks:
        _require(task.get("stage") in stage_counts, f"unknown task stage: {task.get('stage')}")
        stage_counts[task["stage"]] += 1
    _require(stage_counts == EXPECTED_STAGE_COUNTS, f"stage task counts drifted: {stage_counts}")

    effort_totals = {
        key: sum(item.get("effort_hours", {}).get(key, 0) for item in tasks)
        for key in ("low", "likely", "high")
    }
    _require(effort_totals == EXPECTED_EFFORTS, f"task effort arithmetic drifted: {effort_totals}")
    rollup = taskpack.get("effort_rollup_policy", {}).get("task_arithmetic_total", {})
    _require(
        rollup
        == {
            "low": EXPECTED_EFFORTS["low"],
            "likely": EXPECTED_EFFORTS["likely"],
            "isolated_high": EXPECTED_EFFORTS["high"],
        },
        "declared effort rollup drifted",
    )

    validation = taskpack.get("validation_contract", {})
    _require(
        validation.get("task_count_expected") == 44
        and validation.get("calculated_task_count") == 44
        and validation.get("calculated_dag_cycles") == 0,
        "declared DAG arithmetic drifted",
    )
    _validate_dag(tasks, validation.get("topological_order", []))

    by_id = {item["id"]: item for item in tasks}
    task010 = by_id.get(NEXT_TASK, {})
    _require(
        task010.get("phase") == "PH.X2N.3.10"
        and task010.get("stage") == "STG.X2N.3"
        and task010.get("status") in {"planned", "completed"},
        "task010 identity/status drifted",
    )
    _require(
        task010.get("depends_on")
        == [
            "TSK.x2n.adapters.005",
            "TSK.x2n.foundation.004",
            "TSK.x2n.skeleton.004",
        ],
        "task010 dependencies drifted",
    )
    _require(
        task010.get("acceptance_ids")
        == ["ACC.x2n.batch.002", "ACC.x2n.ext.003", "ACC.x2n.batch.001"],
        "task010 Acceptance contract drifted",
    )
    rendered010 = json.dumps(task010, ensure_ascii=False, sort_keys=True)
    for token in (
        "strict scope_id enum",
        "bilibili_selected_collection",
        "kuaishou_selected_collection",
        "taobao_selected_collection",
        "Owner-selected manifest, source identity and max_items",
        "versioned discriminated GET_CAPABILITIES result",
        "capability_gate_outcome",
        "BLOCKED_TECHNICAL is a global veto",
        "UNKNOWN_DISABLED > BLOCKED_POLICY > BLOCKED_AUTH > BLOCKED_BUDGET > BLOCKED_CAPABILITY > CI_SYNTH_READY",
        "BLOCKED_TECHNICAL combined with each external reason still yields no terminal",
        "authoritative restart-safe derived runtime snapshot",
        "run_failure",
        "never as a second run_record state",
        "X2N_ADAPTER_FAILED_FALLBACK_AVAILABLE",
        "fallback_from_job_id",
        "generated JSON Schema/TypeScript",
        "migration up/down",
        "automatic fallback and real platform calls remain zero",
        "any fallback runs without a second explicit Owner action",
    ):
        _require(token in rendered010, f"task010 fail-closed oracle missing: {token}")
    _require(
        NEXT_TASK in by_id.get("TSK.x2n.multimodal.001", {}).get("depends_on", []),
        "Stage 4 entry can bypass task010",
    )

    gates = {item.get("id"): item for item in taskpack.get("stage_gates", [])}
    _require(gates.get("G3", {}).get("pass_conditions") == EXPECTED_G3_CONDITIONS, "G3 conditions drifted")
    _require(NEXT_TASK in gates.get("G3", {}).get("requires_tasks", []), "G3 does not require task010")
    _require(gates.get("G6", {}).get("pass_conditions") == EXPECTED_G6_CONDITIONS, "G6 direct go-live conditions drifted")
    _require("optional_future_backlog" not in taskpack, "fixed-delay future backlog key remains active")

    release_task = by_id.get("TSK.x2n.assurance.005", {})
    release_rendered = json.dumps(release_task, ensure_ascii=False, sort_keys=True)
    for token in (
        "signed/tagged v0.0.0.1 release",
        "deployment and runtime receipt",
        "online smoke receipt",
        "deployed runtime and online smoke",
    ):
        _require(token in release_rendered, f"direct MVP release oracle missing: {token}")
    _require(
        release_task.get("task_start_conditions")
        == [
            "G0 through G5 pass",
            "assurance.001 through assurance.004 and uxops.005 are complete",
            "all blocking acceptances outside assurance_005_owned_in_task_acceptance_ids pass",
        ],
        "assurance.005 task-start conditions drifted or include its own outputs",
    )
    _require(
        release_task.get("in_task_pre_switch_checks")
        == [
            "eighty-item XHS/Douyin Owner MVP baseline passes",
            "every additional enabled capability has an independent activation check of no more than twenty items",
            "security assurance passes; model capability passes or is explicitly disabled or degraded to suggestion-only",
            "rollback rehearsal passes",
            "owner signs off",
        ],
        "assurance.005 in-task pre-switch checks drifted",
    )
    _require(
        release_task.get("acceptance_ids") == EXPECTED_ASSURANCE_005_OWNED_ACCEPTANCES,
        "assurance.005 does not own its exact in-task Acceptance set",
    )
    _require(
        release_task.get("post_deployment_conditions")
        == [
            "deployed runtime and online smoke pass",
            "release artifact scan passes with no Runtime Data",
            "unique v0.0.0.1 tag and go-live receipt exist",
        ]
        and release_task.get("gate_order")
        == "assurance.005 performs in-task checks before switching current; G6 is evaluated only after post-deployment conditions and is never a task-start precondition",
        "assurance.005 post-deployment G6 order drifted",
    )
    release_closure: set[str] = set()
    pending = list(release_task.get("depends_on", []))
    while pending:
        dependency = pending.pop()
        if dependency in release_closure:
            continue
        _require(dependency in by_id, f"release dependency is unknown: {dependency}")
        release_closure.add(dependency)
        pending.extend(by_id[dependency].get("depends_on", []))
    _require(
        release_closure == set(by_id) - {"TSK.x2n.assurance.005"},
        "assurance.005 dependency closure does not cover all prior 43 tasks",
    )

    uxops003 = json.dumps(by_id.get("TSK.x2n.uxops.003", {}), ensure_ascii=False, sort_keys=True)
    for token in (
        "owner-mvp-plan",
        "removal of the legacy pre-release-named command",
        "active CLI/help/schema/evidence terminology scan",
        "fixed-commit historical evidence replay",
        "versioned runtime nomenclature v2",
        "current root tests migrated to owner-mvp-plan",
        "historical adapters.005 verifier replay isolated to pinned final commit a67ba091239297b5c9c38a349e0a839680d1c411",
    ):
        _require(token in uxops003, f"runtime terminology migration contract missing: {token}")

    task005 = json.dumps(by_id.get("TSK.x2n.uxops.005", {}), ensure_ascii=False, sort_keys=True)
    for token in (
        "explicit Owner confirmation",
        "tmutil addexclusion",
        "whole X2N_DATA_ROOT",
        "area-global verify output is redacted advisory only",
        "missing other-domain object neither blocks x2n durability nor appears by path/name",
        "monotonic deletion_epoch",
        "UNSUPPORTED_OWNER_PRIVATE_DB_GOVERNANCE_REQUIRED",
        "restore rejects an older deletion_epoch",
    ):
        _require(token in task005, f"Task005 isolation/deletion contract missing: {token}")

    for assurance_id in ("TSK.x2n.assurance.003", "TSK.x2n.assurance.005"):
        rendered = json.dumps(by_id.get(assurance_id, {}), ensure_ascii=False, sort_keys=True)
        _require(
            "owner-mvp-plan" in rendered
            and "legacy pre-release-named command" in rendered,
            f"{assurance_id} does not enforce active runtime terminology",
        )


def validate_taskpack_and_traceability() -> Check:
    taskpack = _load_yaml_unique(TASKPACK)
    _validate_taskpack_payload(taskpack)
    return Check(
        "taskpack_and_traceability",
        "PASS",
        {
            "tasks": 44,
            "acceptances": 62,
            "stage_3_tasks": 10,
            "cycles": 0,
            "effort_hours": EXPECTED_EFFORTS,
        },
    )


def _validate_release_payload(fact: dict[str, Any]) -> None:
    release = fact.get("release_policy", {})
    _require(release.get("target") == "v0.0.0.1", "release target drifted")
    _require(
        release.get("pre_release_phases") == "PROHIBITED"
        and release.get("alpha_beta") == "PROHIBITED"
        and release.get("fixed_health_observation") == "PROHIBITED"
        and release.get("fixed_soak") == "PROHIBITED",
        "a prerelease, fixed observation, or soak gate was reintroduced",
    )
    _require(
        release.get("gate_order") == EXPECTED_RELEASE_GATE_ORDER
        and release.get("assurance_005_start_conditions") == EXPECTED_ASSURANCE_005_START_CONDITIONS
        and release.get("assurance_005_owned_in_task_acceptance_ids")
        == EXPECTED_ASSURANCE_005_OWNED_ACCEPTANCES
        and release.get("assurance_005_in_task_pre_switch_checks")
        == EXPECTED_ASSURANCE_005_IN_TASK_PRE_SWITCH_CHECKS,
        "release gate order is circular or assurance.005 start/in-task boundaries drifted",
    )
    _require(
        release.get("same_task_actions")
        == [
            "bounded_activation_checks",
            "rollback_verification",
            "deploy",
            "run",
            "online_smoke",
        ],
        "same-task MVP actions drifted",
    )
    _require(
        release.get("post_go_live_monitoring") == "NON_BLOCKING_FIX_DEGRADE_OR_ROLLBACK_TRIGGER",
        "post-live monitoring became a blocking wait gate",
    )


def _validate_data_routing_payload(fact: dict[str, Any]) -> None:
    data = fact.get("data_routing", {})
    _require(data.get("local_root_ref") == "X2N_DATA_ROOT", "local data-root reference drifted")
    _require(
        data.get("local_role") == "EPHEMERAL_EXECUTION_DOWNLOAD_AND_ACTIVE_SQLITE_WORKING_COPY",
        "local data root was promoted to durable storage",
    )
    _require(
        data.get("os_backup_policy")
        == "TARGET_ENTIRE_X2N_DATA_ROOT_EXCLUDED_FROM_TIME_MACHINE_IMPLEMENTATION_PLANNED_TASK005",
        "Time Machine target/current implementation boundary drifted",
    )
    _require(
        data.get("durable_repository") == "LinzeColin/Private-Database"
        and data.get("durable_area") == "Private-MetaDatabase"
        and data.get("durable_domain") == "xhs-douyin-2notion",
        "durable Private-MetaDatabase route drifted",
    )
    _require(
        data.get("client") == "KMOS/KMDatabase/machine/tools/private_db_client.py"
        and data.get("operations") == ["ingest", "get", "list", "verify"]
        and data.get("clone") == "FORBIDDEN",
        "Private-Database client/no-clone contract drifted",
    )
    _require(
        data.get("object_model") == "CONTENT_ADDRESSED_OBJECTS_WITH_GLOBAL_MANIFEST_DOMAIN_FIELD"
        and data.get("raw_sqlite_db_upload") == "FORBIDDEN_BY_CLIENT"
        and data.get("archival_chunk_max_bytes") == 94371840
        and data.get("project_verification") == "EXACT_DOMAIN_ROWS_GET_HASH_REASSEMBLE_SQLITE_INTEGRITY",
        "Private-MetaDatabase object, redline, chunk, or project verification contract drifted",
    )
    _require(
        data.get("client_verify_exit_semantics") == "AREA_GLOBAL_VERIFY_REDACTED_ADVISORY_NOT_X2N_GATE"
        and data.get("other_domain_isolation")
        == "OTHER_DOMAIN_MISSING_NON_BLOCKING_ZERO_PATH_DISCLOSURE"
        and data.get("global_manifest_sha_idempotency_mitigation") == "DOMAIN_BOUND_CHUNK_ENVELOPE"
        and data.get("private_db_auth")
        == "OWNER_AUTHORIZED_EXISTING_GH_SESSION_CLIENT_ONLY_NO_TOKEN_VALUE_OR_AUTH_MUTATION"
        and data.get("forbidden_operations") == ["put", "delete"],
        "Private-Database verify, manifest idempotency, auth, or command boundary drifted",
    )
    _require(
        data.get("logical_truth") == "ACTIVE_SQLITE_CANONICAL_STORE"
        and data.get("durability_before_verified_receipt") == "DURABILITY_PENDING",
        "SQLite truth or durable receipt semantics drifted",
    )


def validate_release_and_data_contracts() -> Check:
    fact = _load_json(RESUME_FACT)
    _validate_release_payload(fact)
    _validate_data_routing_payload(fact)

    path = _load_json(PATH_CONTRACT)
    project = _load_json(PROJECT_FACT)
    state = _load_json(TASK_STATE)
    _require(path.get("local_root_role") == "ephemeral_execution_download_and_active_sqlite_working_copy", "path local-role drifted")
    _require(
        path.get("durable_data_repository") == "LinzeColin/Private-Database"
        and path.get("durable_data_area") == "Private-MetaDatabase"
        and path.get("durable_data_domain") == "xhs-douyin-2notion"
        and path.get("private_database_clone") == "forbidden",
        "path durable route drifted",
    )
    _require(
        path.get("raw_sqlite_db_upload") == "forbidden_by_client"
        and path.get("archival_chunk_max_bytes") == 94371840
        and path.get("client_object_hard_limit_bytes") == 99614720
        and path.get("project_verification")
        == "exact_domain_rows_then_get_hash_reassemble_and_sqlite_integrity",
        "path client-limit or restore verification contract drifted",
    )
    _require(
        path.get("client_verify_exit_semantics")
        == "area_global_verify_redacted_advisory_not_x2n_gate"
        and path.get("other_domain_isolation")
        == "other_domain_missing_nonblocking_zero_path_disclosure"
        and path.get("global_manifest_sha_idempotency_mitigation") == "domain_bound_chunk_envelope"
        and path.get("private_db_auth")
        == "owner_authorized_existing_gh_session_client_only_no_token_value_or_auth_mutation"
        and path.get("client_commands_allowed") == ["ingest", "get", "list", "verify"]
        and path.get("client_commands_forbidden") == ["put", "delete"],
        "path verify, domain-idempotency, auth, or command boundary drifted",
    )
    _require(
        path.get("time_machine_excluded") == ["."]
        and path.get("time_machine_included") == []
        and path.get("time_machine_semantics")
        == "entire_x2n_data_root_excluded_only_private_metadatabase_verified_receipt_is_durable"
        and path.get("time_machine_implementation_state")
        == "planned_task_uxops_005_not_claimed_current",
        "whole-root Time Machine target or current implementation state drifted",
    )
    task001_state = state.get("tasks", {}).get(STAGE4_NEXT_TASK)
    _require(task001_state in {None, "pass"}, "Task001 current state is invalid")
    task002_state = state.get("tasks", {}).get("TSK.x2n.multimodal.002")
    _require(task002_state in {None, "pass"}, "Task002 current state is invalid")
    task003_state = state.get("tasks", {}).get("TSK.x2n.multimodal.003")
    _require(task003_state in {None, "pass"}, "Task003 current state is invalid")
    task004_state = state.get("tasks", {}).get("TSK.x2n.multimodal.004")
    _require(task004_state in {None, "pass"}, "Task004 current state is invalid")
    expected_project_status = (
        "stage_4_task004_fusion_injection_ci_synth_model_not_run"
        if task004_state == "pass"
        else "stage_4_task003_local_first_ocr_vision_ci_synth_private_gold_pending"
        if task003_state == "pass"
        else "stage_4_task002_local_first_asr_ci_synth_private_gold_pending"
        if task002_state == "pass"
        else "stage_4_task001_bounded_media_preprocessing_pass_ci_synth"
        if task001_state == "pass"
        else "stage_3_review_resume_contract_versioned_g3_blocked_technical"
    )
    _require(project.get("status") == expected_project_status, "project status drifted")
    _require(project.get("canonical_store") == "active_local_sqlite_logical_truth", "project truth-source drifted")
    _require(
        project.get("private_db_auth")
        == "owner_authorized_existing_gh_session_client_only_no_token_value_or_auth_mutation",
        "project authenticated-session boundary drifted",
    )
    task010_state = state.get("tasks", {}).get(NEXT_TASK)
    if task010_state == "planned":
        _require(
            state.get("review_id") == REVIEW_ID
            and state.get("next_run") == NEXT_TASK
            and state.get("next_phase") == "PH.X2N.3.10"
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "blocked_technical",
            "planned Task010 routing or gate drifted",
        )
        expected_local_ci = (
            "pass_stage_3_review_resume_schema_history_taskpack_release_data_client_audit_isolation_"
            "focused_27_tests_phase0_1_phase0_5_fresh_fast_lane_exact_9_of_9_three_expected_private_"
            "optional_skips_platform_model_real_account_calls_0"
        )
        stage_4_authorized = False
        task_state_mode = "task010_planned"
    elif task010_state == "pass" and state.get("stage_gate") == "review_pending":
        _require(
            state.get("last_completed_phase") == "PH.X2N.3.10"
            and state.get("review_id") == "STG.X2N.3.REVIEW.RESUME.RECHECK_PENDING"
            and state.get("run_id") == TASK010_RUN_ID
            and state.get("next_run") == TASK010_RECHECK
            and state.get("next_phase") == TASK010_RECHECK
            and state.get("next_phase_authorized") is True
            and state.get("stage_gate") == "review_pending",
            "completed Task010 must await an independent G3 recheck",
        )
        expected_local_ci = (
            "pass_task010_eight_scope_extension_native_adapter_ci_synth_typed_capability_snapshot_"
            "failed_run_explicit_fallback_restart_migration_platform_model_real_account_calls_0"
        )
        stage_4_authorized = False
        task_state_mode = "task010_pending_g3_recheck"
    elif task010_state == "pass" and state.get("stage_gate") == "pass":
        recheck = _load_json(G3_RECHECK_FACT)
        _require(
            recheck.get("review_id") == TASK010_RECHECK
            and recheck.get("run_id") == G3_RECHECK_RUN_ID
            and recheck.get("gate", {}).get("id") == "G3"
            and recheck.get("gate", {}).get("status") == "PASS_CI_SYNTH"
            and recheck.get("gate", {}).get("decision") == "PASS"
            and recheck.get("authorization", {}).get("stage_3_remote_upload") is False
            and recheck.get("authorization", {}).get("stage_4_local_task_start") is True
            and recheck.get("next_task", {}).get("id") == STAGE4_NEXT_TASK,
            "G3 recheck fact is not a bounded local Stage 4 authorization",
        )
        if task004_state == "pass":
            _require(
                task002_state == "pass"
                and task003_state == "pass"
                and state.get("last_completed_phase") == "PH.X2N.4.4"
                and state.get("review_id") == TASK010_RECHECK
                and state.get("run_id") == "RUN-X2N-S04-M004"
                and state.get("stage") == "STG.X2N.4"
                and all(
                    state.get("tasks", {}).get(task_id) == "pass"
                    for task_id in (STAGE4_NEXT_TASK, "TSK.x2n.multimodal.002", "TSK.x2n.multimodal.003", "TSK.x2n.multimodal.004")
                )
                and state.get("next_run") == "TSK.x2n.multimodal.005"
                and state.get("next_phase") == "PH.X2N.4.5"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_4_authorized") is True
                and state.get("current_stage_gate") == "not_run"
                and state.get("remote_upload") == "not_required_for_local_stage_transition",
                "completed Task004 did not preserve the bounded Stage 4 routing",
            )
            expected_local_ci = (
                "pass_independent_g3_recheck_task010_eight_scope_extension_native_adapter_typed_capability_snapshot_"
                "technical_veto_failed_run_explicit_fallback_task005_no_empty_response_deletion_extension_100_restart_"
                "reconciliation_task002_local_first_asr_cache_budget_cloud_zero_private_gold_pending_task003_local_first_"
                "ocr_vision_cache_budget_cloud_zero_private_gold_pending_task004_deterministic_fusion_strict_parser_"
                "injection_isolation_platform_model_real_account_calls_0"
            )
            task_state_mode = "stage4_task004_complete"
        elif task003_state == "pass":
            _require(
                task002_state == "pass"
                and state.get("last_completed_phase") == "PH.X2N.4.3"
                and state.get("review_id") == TASK010_RECHECK
                and state.get("run_id") == "RUN-X2N-S04-M003"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get(STAGE4_NEXT_TASK) == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.002") == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.003") == "pass"
                and state.get("next_run") == "TSK.x2n.multimodal.004"
                and state.get("next_phase") == "PH.X2N.4.4"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_4_authorized") is True
                and state.get("current_stage_gate") == "not_run"
                and state.get("remote_upload") == "not_required_for_local_stage_transition",
                "completed Task003 did not preserve the bounded Stage 4 routing",
            )
            expected_local_ci = (
                "pass_independent_g3_recheck_task010_eight_scope_extension_native_adapter_typed_capability_snapshot_"
                "technical_veto_failed_run_explicit_fallback_task005_no_empty_response_deletion_extension_100_restart_"
                "reconciliation_task002_local_first_asr_cache_budget_cloud_zero_private_gold_pending_task003_local_first_"
                "ocr_vision_cache_budget_cloud_zero_private_gold_pending_platform_model_real_account_calls_0"
            )
            task_state_mode = "stage4_task003_complete"
        elif task002_state == "pass":
            _require(
                state.get("last_completed_phase") == "PH.X2N.4.2"
                and state.get("review_id") == TASK010_RECHECK
                and state.get("run_id") == "RUN-X2N-S04-M002"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get(STAGE4_NEXT_TASK) == "pass"
                and state.get("tasks", {}).get("TSK.x2n.multimodal.002") == "pass"
                and state.get("next_run") == "TSK.x2n.multimodal.003"
                and state.get("next_phase") == "PH.X2N.4.3"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_4_authorized") is True
                and state.get("current_stage_gate") == "not_run"
                and state.get("remote_upload") == "not_required_for_local_stage_transition",
                "completed Task002 did not preserve the bounded Stage 4 routing",
            )
            expected_local_ci = (
                "pass_independent_g3_recheck_task010_eight_scope_extension_native_adapter_typed_capability_snapshot_"
                "technical_veto_failed_run_explicit_fallback_task005_no_empty_response_deletion_extension_100_restart_"
                "reconciliation_task002_local_first_asr_cache_budget_cloud_zero_private_gold_pending_platform_model_real_account_calls_0"
            )
            task_state_mode = "stage4_task002_complete"
        elif task001_state == "pass":
            _require(
                state.get("last_completed_phase") == "PH.X2N.4.1"
                and state.get("review_id") == TASK010_RECHECK
                and state.get("run_id") == "RUN-X2N-S04-M001"
                and state.get("stage") == "STG.X2N.4"
                and state.get("tasks", {}).get(STAGE4_NEXT_TASK) == "pass"
                and state.get("next_run") == "TSK.x2n.multimodal.002"
                and state.get("next_phase") == "PH.X2N.4.2"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_4_authorized") is True
                and state.get("current_stage_gate") == "not_run"
                and state.get("remote_upload") == "not_required_for_local_stage_transition",
                "completed Task001 did not preserve the bounded Stage 4 routing",
            )
            expected_local_ci = (
                "pass_independent_g3_recheck_task010_eight_scope_extension_native_adapter_typed_capability_snapshot_"
                "technical_veto_failed_run_explicit_fallback_task005_no_empty_response_deletion_extension_100_restart_"
                "reconciliation_platform_model_real_account_calls_0"
            )
            task_state_mode = "stage4_task001_complete"
        else:
            _require(
                state.get("last_completed_phase") == TASK010_RECHECK
                and state.get("review_id") == TASK010_RECHECK
                and state.get("run_id") == G3_RECHECK_RUN_ID
                and state.get("next_run") == STAGE4_NEXT_TASK
                and state.get("next_phase") == "PH.X2N.4.1"
                and state.get("next_phase_authorized") is True
                and state.get("stage_3_review_complete") is True
                and state.get("stage_4_authorized") is True
                and state.get("remote_upload") == "not_required_for_local_stage_transition",
                "G3 pass did not produce the exact bounded Stage 4 routing",
            )
            expected_local_ci = (
                "pass_independent_g3_recheck_task010_eight_scope_extension_native_adapter_typed_capability_snapshot_"
                "technical_veto_failed_run_explicit_fallback_task005_no_empty_response_deletion_extension_100_restart_"
                "reconciliation_platform_model_real_account_calls_0"
            )
            task_state_mode = "g3_pass_stage4_local_next"
        stage_4_authorized = True
    else:
        raise ResumeError("Task010 current state is neither planned nor pass")
    _require(
        state.get("stage_3_remote_upload_authorized") is False
        and state.get("stage_4_authorized") is stage_4_authorized,
        "Task010 state escaped its permitted stage transition",
    )
    _require(
        state.get("shared_github_auth_boundary")
        == "current_resume_no_session_use_token_value_contact_or_auth_mutation_future_authorized_private_db_client_session_only_no_token_delete_revoke_rotate",
        "task-state shared authentication boundary drifted",
    )
    _require(
        state.get("local_ci_execution") == expected_local_ci
        and state.get("release_policy")
        == "direct_v0_0_0_1_mvp_g0_g5_prior_tasks_and_acceptances_outside_exact_assurance005_owned_set_start_then_in_task_eighty_xhs_douyin_each_additional_enabled_max_twenty_security_must_pass_model_pass_or_disabled_suggestion_only_rollback_signoff_deploy_run_online_then_g6_pass_no_prerelease_no_fixed_wait_no_soak",
        "task-state verification or direct MVP security/model boundary drifted",
    )
    prfaq_text = PRFAQ.read_text(encoding="utf-8")
    prd_text = PRD.read_text(encoding="utf-8")
    if task010_state == "planned":
        _require(
            "status: STAGE_3_REVIEW_RESUME_CONTRACT_VERSIONED_G3_BLOCKED_TECHNICAL" in prfaq_text
            and f"owner_change_event: {CHANGE_EVENT}" in prfaq_text
            and "implementation_authorized: stage_3_task_010_next_single_phase_run" in prfaq_text
            and "status: STAGE_3_REVIEW_RESUME_CONTRACT_VERSIONED_G3_BLOCKED_TECHNICAL" in prd_text
            and f"owner_change_event: {CHANGE_EVENT}" in prd_text
            and "current_run_scope: stage_3_review_resume_contract_only" in prd_text
            and "implementation_authorized: stage_3_task_010_next_single_phase_run" in prd_text,
            "PRFAQ/PRD planned Task010 authorization drifted",
        )
    elif task_state_mode == "task010_pending_g3_recheck":
        _require(
            "status: STAGE_3_TASK010_CI_SYNTH_PASS_G3_REVIEW_PENDING" in prfaq_text
            and "decision: DIRECT_MVP_TASK010_ACCEPTED_G3_RECHECK_NEXT" in prfaq_text
            and "implementation_authorized: stage_3_review_resume_recheck_next_single_phase_run" in prfaq_text
            and "status: STAGE_3_TASK010_CI_SYNTH_PASS_G3_REVIEW_PENDING" in prd_text
            and "current_run_scope: stage_3_task010_ci_synth_accepted_g3_recheck_pending" in prd_text
            and "implementation_authorized: stage_3_review_resume_recheck_next_single_phase_run" in prd_text,
            "PRFAQ/PRD completed Task010 state drifted",
        )
    elif task_state_mode == "stage4_task004_complete":
        _require(
            "status: STAGE_4_TASK004_FUSION_INJECTION_CI_SYNTH_MODEL_NOT_RUN" in prfaq_text
            and "decision: DIRECT_MVP_TASK004_ACCEPTED_TASK005_NEXT" in prfaq_text
            and "implementation_authorized: stage_4_task_005_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK004_FUSION_INJECTION_CI_SYNTH_MODEL_NOT_RUN" in prd_text
            and "current_run_scope: stage_4_task004_complete_task005_next_model_not_run" in prd_text
            and "implementation_authorized: stage_4_task_005_next_single_phase_run" in prd_text,
            "PRFAQ/PRD completed Task004 state drifted",
        )
    elif task_state_mode == "stage4_task003_complete":
        _require(
            "status: STAGE_4_TASK003_LOCAL_FIRST_OCR_VISION_CI_SYNTH_PRIVATE_GOLD_PENDING" in prfaq_text
            and "decision: DIRECT_MVP_TASK003_ACCEPTED_TASK004_NEXT" in prfaq_text
            and "implementation_authorized: stage_4_task_004_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK003_LOCAL_FIRST_OCR_VISION_CI_SYNTH_PRIVATE_GOLD_PENDING" in prd_text
            and "current_run_scope: stage_4_task003_complete_task004_next_private_gold_pending" in prd_text
            and "implementation_authorized: stage_4_task_004_next_single_phase_run" in prd_text,
            "PRFAQ/PRD completed Task003 state drifted",
        )
    elif task_state_mode == "stage4_task002_complete":
        _require(
            "status: STAGE_4_TASK002_LOCAL_FIRST_ASR_CI_SYNTH_PRIVATE_GOLD_PENDING" in prfaq_text
            and "decision: DIRECT_MVP_TASK002_ACCEPTED_TASK003_NEXT" in prfaq_text
            and "implementation_authorized: stage_4_task_003_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK002_LOCAL_FIRST_ASR_CI_SYNTH_PRIVATE_GOLD_PENDING" in prd_text
            and "current_run_scope: stage_4_task002_complete_task003_next_private_gold_pending" in prd_text
            and "implementation_authorized: stage_4_task_003_next_single_phase_run" in prd_text,
            "PRFAQ/PRD completed Task002 state drifted",
        )
    elif task_state_mode == "stage4_task001_complete":
        _require(
            "status: STAGE_4_TASK001_BOUNDED_MEDIA_PREPROCESSING_PASS_CI_SYNTH" in prfaq_text
            and "decision: DIRECT_MVP_TASK001_ACCEPTED_TASK002_NEXT" in prfaq_text
            and "implementation_authorized: stage_4_task_002_next_single_phase_run" in prfaq_text
            and "status: STAGE_4_TASK001_BOUNDED_MEDIA_PREPROCESSING_PASS_CI_SYNTH" in prd_text
            and "current_run_scope: stage_4_task001_complete_task002_next" in prd_text
            and "implementation_authorized: stage_4_task_002_next_single_phase_run" in prd_text,
            "PRFAQ/PRD completed Task001 state drifted",
        )
    else:
        _require(
            "status: STAGE_3_G3_PASS_STAGE_4_LOCAL_NEXT_AUTHORIZED" in prfaq_text
            and "decision: DIRECT_MVP_G3_RECHECK_PASS_STAGE4_LOCAL_NEXT" in prfaq_text
            and "implementation_authorized: stage_4_task_001_next_single_phase_run" in prfaq_text
            and "status: STAGE_3_G3_PASS_STAGE_4_LOCAL_NEXT_AUTHORIZED" in prd_text
            and "current_run_scope: stage_3_g3_recheck_pass_stage_4_task001_next" in prd_text
            and "implementation_authorized: stage_4_task_001_next_single_phase_run" in prd_text,
            "PRFAQ/PRD G3-pass local Stage4 authorization drifted",
        )
    stale_active_status = (
        "stage_0_governance_preparation_only",
        "等待 Owner 启动 Codex Dev",
        "产品代码与 Stage 1 仍未授权",
    )
    active_status_text = "\n".join((prfaq_text, prd_text, TASKPACK.read_text(encoding="utf-8")))
    _require(
        not any(token in active_status_text for token in stale_active_status),
        "stale pre-implementation status remains in active product controls",
    )
    registry = _load_json(ID_REGISTRY)
    _require(
        registry.get("registered_counts", {}).get("tasks") == 44
        and registry.get("registered_counts", {}).get("acceptances") == 62,
        "ID registry counts drifted",
    )
    return Check(
        "release_and_data_contracts",
        "PASS",
        {
            "release": "v0.0.0.1_direct_same_task",
            "fixed_wait_or_soak": 0,
            "local_root_role": "ephemeral",
            "durable_area": "Private-MetaDatabase",
            "durable_domain": "xhs-douyin-2notion",
            "archival_chunk_max_bytes": 94371840,
            "private_database_clone": 0,
            "time_machine_target": "whole_root_planned_task005",
            "area_global_verify_role": "redacted_advisory_only",
        },
    )


def _active_texts() -> Iterable[tuple[Path, str]]:
    for path in ACTIVE_CONTROL_FILES:
        _require(path.is_file(), f"active control artifact missing: {path.name}")
        yield path, path.read_text(encoding="utf-8")


def validate_documents_and_source_safety() -> Check:
    active_text = "\n".join(text for _, text in _active_texts())
    changed_paths = _validate_changed_scope(_resume_contract_changed_paths())
    changed_parts: list[str] = []
    for relative in changed_paths:
        path = REPOSITORY_ROOT / relative
        payload = path.read_bytes()
        _require(len(payload) <= 2 * 1024 * 1024, f"changed text artifact exceeds 2 MiB: {relative}")
        try:
            changed_parts.append(payload.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ResumeError(f"changed artifact is not UTF-8 text: {relative}") from error
    all_text = "\n".join((active_text, *changed_parts))
    product_text = "\n".join(path.read_text(encoding="utf-8") for path in ACTIVE_PRODUCT_DOCS)
    _require(not re.search(r"\b(?:alpha|beta)\b", product_text, flags=re.IGNORECASE), "prerelease phase label remains in active product docs")
    _require(not re.search(r"v0\.0\.0\.1-[a-z0-9]", product_text, flags=re.IGNORECASE), "prerelease version label remains")
    _require("30 stable owner days" not in product_text.lower(), "fixed 30-day entry gate remains")
    _require(("/" + "Users/") not in all_text, "local absolute user path entered an active contract")

    sensitive_patterns = (
        re.compile("github" + r"_pat_[A-Za-z0-9]"),
        re.compile("gh" + r"[pousr]_[A-Za-z0-9]{8,}"),
        re.compile(r"https://[^\s/:@]+(?::[^\s/@]+)?@github\.com/", flags=re.IGNORECASE),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{12,}"),
        re.compile("-----BEGIN " + r"[A-Z ]*" + "PRIVATE KEY-----"),
        re.compile(
            r"https?://[^\s\"']*(?:byteimg|pstatp|douyinpic|douyinstatic|xhscdn|sns-webpic)[^\s\"']*",
            flags=re.IGNORECASE,
        ),
    )
    hits = sum(1 for pattern in sensitive_patterns if pattern.search(all_text))
    _require(hits == 0, "credential, authenticated remote, private key, or platform CDN value entered active controls")

    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REVIEW_REPORT.read_text(encoding="utf-8")
    for token in (
        REVIEW_ID,
        RUN_ID,
        "G3_BLOCKED_TECHNICAL",
        NEXT_TASK,
        "Private-MetaDatabase",
        "domain=xhs-douyin-2notion",
        "不执行新 DAG Task",
    ):
        _require(token in contract, f"Resume Run Contract missing: {token}")
    for token in (
        "CONTRACT_VERSIONED / G3_BLOCKED_TECHNICAL",
        "READY_FOR_MVP_ACTIVATION",
        "DISABLED_EXTERNAL_GATE",
        NEXT_TASK,
        "STAGE_4_UNAUTHORIZED",
    ):
        _require(token in report, f"Resume report missing: {token}")
    return Check(
        "documents_and_source_safety",
        "PASS",
        {
            "active_files": len(ACTIVE_CONTROL_FILES),
            "resume_changed_text_files_scanned": len(changed_paths),
            "prerelease_labels": 0,
            "absolute_user_paths": 0,
            "sensitive_value_hits": 0,
        },
    )


def validate_decision_evidence() -> Check:
    _require(DECISION_EVIDENCE.is_file(), "Resume decision evidence missing")
    evidence = _load_json(DECISION_EVIDENCE)
    _require(
        evidence
        == {
            "schema_version": "1.1",
            "review_id": REVIEW_ID,
            "run_id": RUN_ID,
            "owner_change_event": CHANGE_EVENT,
            "status": "CONTRACT_VERSIONED_G3_BLOCKED_TECHNICAL",
            "stage_3_remote_upload_authorized": False,
            "stage_4_authorized": False,
            "next_task": NEXT_TASK,
            "verification_scope": {
                "repository_contract_state": "MACHINE_VERIFIED_OFFLINE",
                "external_execution": "PROCESS_ATTESTATION_NOT_INDEPENDENTLY_OBSERVED",
                "remote_pull_request_state": "PRIOR_READ_ONLY_CHECK_NOT_REVERIFIED_OFFLINE",
            },
            "process_attestation": {
                "deployment_executed": False,
                "new_dag_task_executed": False,
                "real_platform_calls": 0,
                "shared_github_token_value_contact": "ZERO",
                "shared_github_auth_mutation": "ZERO",
                "authenticated_session_use": "NOT_USED",
            },
        },
        "Resume decision evidence drifted",
    )
    return Check(
        "decision_evidence",
        "PASS",
        {
            "status": evidence["status"],
            "external_execution_evidence_class": evidence["verification_scope"]["external_execution"],
        },
    )


def validate_private_db_client_audit(*, verify_local_source: bool) -> Check:
    _require(CLIENT_AUDIT.is_file(), "Private-Database client read-only audit missing")
    audit = _load_json(CLIENT_AUDIT)
    _require(
        audit.get("schema_version") == "1.1"
        and audit.get("audit_id") == "AUD-X2N-PRIVATE-DB-CLIENT-20260728"
        and audit.get("client_path") == "KMOS/KMDatabase/machine/tools/private_db_client.py"
        and audit.get("client_sha256") == "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa"
        and audit.get("client_size_bytes") == 10818,
        "Private-Database client audit identity drifted",
    )
    _require(
        audit.get("evidence_class")
        == {
            "client_identity": "LOCAL_SOURCE_DIGEST_RECOMPUTABLE",
            "external_actions": "PROCESS_ATTESTATION_NOT_INDEPENDENTLY_OBSERVED_BY_OFFLINE_VERIFIER",
        },
        "Private-Database audit evidence classification drifted",
    )
    _require(
        audit.get("execution") == "READ_SOURCE_AND_HELP_ONLY_NO_GH_API_NO_DATA_WRITE"
        and audit.get("allowed_area") == "Private-MetaDatabase"
        and audit.get("allowed_operations") == ["ingest", "get", "list", "verify"]
        and audit.get("forbidden_operations") == ["put", "delete"],
        "Private-Database audit execution/operation boundary drifted",
    )
    observed = audit.get("observed_contract", {})
    _require(
        observed.get("raw_sqlite_db_rejected") is True
        and observed.get("max_object_bytes") == 99614720
        and observed.get("ingest_object_model") == "objects/{sha_prefix}/{sha256}_{opaque_name}"
        and observed.get("manifest_scope") == "area_global_manifest_jsonl_with_domain_field"
        and observed.get("manifest_idempotency_key") == "sha256_global_not_domain_scoped"
        and observed.get("verify_missing_objects_exit_nonzero") is False
        and observed.get("authentication") == "inherited_gh_api_environment",
        "Private-Database observed client contract drifted",
    )
    mitigations = audit.get("required_x2n_mitigations", [])
    _require(
        mitigations
        == [
            "consistent_sqlite_snapshot_to_non_running_archive",
            "domain_bound_chunk_envelope_with_opaque_name_index_total_and_payload_sha256",
            "chunks_no_larger_than_94371840_bytes",
            "exact_domain_manifest_filter",
            "treat_area_global_verify_as_redacted_advisory_not_x2n_gate",
            "exact_domain_missing_fails_other_domain_missing_nonblocking_zero_path_disclosure",
            "per_object_get_hash_reassembly_and_sqlite_integrity",
            "delete_all_temporary_get_outputs",
            "owner_authorized_existing_gh_session_client_only_no_token_value_or_auth_mutation",
            "revalidate_client_digest_and_contract_before_uxops_005",
        ],
        "Private-Database x2n mitigation set drifted",
    )
    _require(
        audit.get("process_attestation")
        == {
            "external_writes": 0,
            "runtime_data_read": 0,
            "shared_github_token_value_contact": "ZERO",
            "shared_github_auth_mutation": "ZERO",
            "authenticated_session_use": "NOT_USED",
        },
        "Private-Database process attestation drifted",
    )
    digest_observation = "NOT_RECOMPUTED_STATIC_CONTRACT_CHECK"
    if verify_local_source:
        common_dir = Path(
            _git(["rev-parse", "--path-format=absolute", "--git-common-dir"])
        ).resolve()
        _require(common_dir.name == ".git", "unexpected Git common-dir layout")
        github_project_root = common_dir.parent.parent
        actual_client = github_project_root / audit["client_path"]
        _require(actual_client.is_file(), "audited Private-Database client is not locally available")
        _require(
            _sha256(actual_client) == audit["client_sha256"]
            and actual_client.stat().st_size == audit["client_size_bytes"],
            "audited Private-Database client local digest/size drifted",
        )
        digest_observation = "RECOMPUTED_FROM_LOCAL_SOURCE"
    return Check(
        "private_db_client_read_only_audit",
        "PASS",
        {
            "client_sha256": audit["client_sha256"],
            "client_digest_observation": digest_observation,
            "external_action_observation": "NOT_OBSERVED_BY_OFFLINE_VERIFIER",
            "raw_sqlite_db_rejected": True,
            "max_object_bytes": 99614720,
            "mitigations": len(mitigations),
        },
    )


def _validate_lane_report_payload(report: dict[str, Any]) -> None:
    _require(
        report.get("lane") == "fast"
        and report.get("status") == "PASS"
        and report.get("blocking_repetitions") == 1
        and report.get("blocking_commands") == 9
        and report.get("blocking_executions") == 9,
        "bounded fast software lane identity/count drifted",
    )
    _require(
        report.get("blocking_failures") == 0
        and report.get("flaky_blocking_tests") == 0
        and report.get("silent_blocking_skips") == 0
        and report.get("explicit_nonblocking_skips") == 3,
        "software lane failure/flaky/skip boundary drifted",
    )
    blocking_results = report.get("blocking_results")
    _require(
        isinstance(blocking_results, list)
        and len(blocking_results) == len(EXPECTED_FAST_LANE_GATES)
        and [item.get("gate") for item in blocking_results] == EXPECTED_FAST_LANE_GATES
        and [item.get("label") for item in blocking_results]
        == [f"{gate}_r1" for gate in EXPECTED_FAST_LANE_GATES]
        and all(
            item.get("status") == "PASS"
            and item.get("blocking") is True
            and item.get("repetition") == 1
            for item in blocking_results
        ),
        "software lane must contain each expected blocking gate exactly once and PASS",
    )
    _require(
        report.get("platform_calls") == 0
        and report.get("model_calls") == 0
        and report.get("real_accounts") == 0
        and report.get("remote_github_actions") == "NOT_RUN_LOCAL_BASELINE"
        and report.get("stage_gate_evaluation") == "NOT_PERFORMED_BY_SOFTWARE_LANE",
        "software lane overstated external execution or Gate evaluation",
    )
    actual = report.get("toolchain", {}).get("actual", {})
    _require(
        actual
        == {
            "coverage": "7.15.2",
            "node": "24.18.0",
            "npm": "11.16.0",
            "python": "3.12.13",
            "pyyaml": "6.0.3",
            "ruff": "0.15.22",
            "uv": "0.11.28",
        },
        "software lane toolchain drifted",
    )


def validate_lane_report(path: Path) -> Check:
    _require(path.is_file(), f"software lane report missing: {path}")
    lane_inputs = _lane_input_paths()
    newest_input_mtime_ns = max(item.stat().st_mtime_ns for item in lane_inputs)
    _require(
        path.stat().st_mtime_ns >= newest_input_mtime_ns,
        "software lane report predates a Resume source/control input",
    )
    input_count, input_manifest_sha256 = _source_manifest(lane_inputs)
    lane_report_sha256 = _sha256(path)
    report = _load_json(path)
    _validate_lane_report_payload(report)
    return Check(
        "bounded_fast_software_lane",
        "PASS",
        {
            "blocking_executions": 9,
            "blocking_failures": 0,
            "repetitions": 1,
            "explicit_nonblocking_skips": 3,
            "lane_reported_platform_calls": 0,
            "lane_reported_model_calls": 0,
            "lane_reported_real_accounts": 0,
            "remote_github_actions": "NOT_RUN_LOCAL_BASELINE",
            "lane_report_sha256": lane_report_sha256,
            "source_files": input_count,
            "source_manifest_sha256": input_manifest_sha256,
        },
    )


def _resume_contract_changed_paths() -> list[str]:
    """Inspect only the committed Resume contract, not its later DAG continuation."""

    _require(
        _git(["merge-base", "--is-ancestor", BASE_COMMIT, TASK010_BASE_COMMIT]) == "",
        "Task010 base is not descended from the frozen Resume contract",
    )
    paths = _git(
        [
            "-c",
            "core.quotepath=false",
            "diff",
            "--name-only",
            "-z",
            f"{BASE_COMMIT}..{TASK010_BASE_COMMIT}",
            "--",
        ]
    ).split("\0")
    return sorted(path for path in paths if path)


def _validate_changed_scope(changed: Iterable[str]) -> list[str]:
    paths = sorted(set(changed))
    _require(
        all(path.startswith("xhs-douyin-2notion/") for path in paths),
        "worktree changed scope escaped x2n",
    )
    extras = sorted(set(paths) - RESUME_CHANGED_PATH_ALLOWLIST)
    _require(not extras, f"Resume changed scope escaped exact allowlist: {extras}")
    return paths


def validate_worktree() -> Check:
    branch = _git(["branch", "--show-current"])
    _require(branch == EXPECTED_BRANCH, f"wrong Resume branch: {branch or 'DETACHED'}")
    _require(_git(["merge-base", "--is-ancestor", BASE_COMMIT, "HEAD"]) == "", "Resume branch is not based on first Review")

    porcelain = _git(["worktree", "list", "--porcelain"])
    blocks = [block for block in porcelain.split("\n\n") if block.strip()]
    x2n_worktrees = 0
    main_worktree: Path | None = None
    for block in blocks:
        fields = dict(
            line.split(" ", 1)
            for line in block.splitlines()
            if " " in line
        )
        worktree = fields.get("worktree", "")
        worktree_branch = fields.get("branch", "")
        if "xhs-douyin-2notion" in worktree or "xhs-douyin-2notion" in worktree_branch:
            x2n_worktrees += 1
        if worktree_branch == "refs/heads/main":
            main_worktree = Path(worktree)
    _require(x2n_worktrees == 1, f"expected one x2n worktree, got {x2n_worktrees}")

    branches = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads"]).splitlines()
    x2n_branches = [item for item in branches if "xhs-douyin-2notion" in item]
    _require(x2n_branches == [EXPECTED_BRANCH], f"x2n local branch isolation drifted: {len(x2n_branches)}")

    _require(
        _git(["merge-base", "--is-ancestor", TASK010_BASE_COMMIT, "HEAD"]) == "",
        "current worktree predates the Task010 base",
    )
    changed = _validate_changed_scope(_resume_contract_changed_paths())
    _require(main_worktree is not None, "main worktree missing")
    main_status = _git(["status", "--porcelain=v1"], cwd=main_worktree)
    _require(not main_status, "main worktree is not clean")
    return Check(
        "worktree_isolation",
        "PASS",
        {
            "active_x2n_worktrees": 1,
            "active_x2n_local_branches": 1,
            "changed_scope_overlap_other_projects": 0,
            "changed_paths": len(changed),
            "changed_scope_allowlist": "EXACT_SUBSET_PASS",
            "main_worktree_clean": True,
            "open_pull_request_state": "NOT_REVERIFIED_OFFLINE",
        },
    )


def _artifact_digests(*, commit: str | None = None) -> dict[str, str]:
    if commit is None:
        return {
            path.relative_to(PROJECT_ROOT).as_posix(): _sha256(path)
            for path in EVIDENCE_DIGEST_PATHS
        }
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): _sha256_bytes(_blob_at(commit, path))
        for path in EVIDENCE_DIGEST_PATHS
    }


def _verification_payload(checks: list[Check]) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_LOCAL_CONTRACT_VERIFICATION_G3_BLOCKED_TECHNICAL",
        "checks": [
            {"name": item.name, "status": item.status, "details": copy.deepcopy(item.details)}
            for item in checks
        ],
        "gate_status": "BLOCKED_TECHNICAL",
        "stage_3_remote_upload_authorized": False,
        "stage_4_authorized": False,
        "next_task": NEXT_TASK,
        "artifact_digests": _artifact_digests(),
        "external_action_observation": "NOT_OBSERVED_BY_OFFLINE_VERIFIER",
        "remote_pull_request_observation": "NOT_REVERIFIED_OFFLINE",
        "process_attestation": {
            "deployment_executed": False,
            "new_dag_task_executed": False,
            "real_platform_calls": 0,
            "shared_github_token_value_contact": "ZERO",
            "shared_github_auth_mutation": "ZERO",
            "authenticated_session_use": "NOT_USED",
        },
    }


def _write_evidence(checks: list[Check]) -> None:
    _require(
        _load_json(TASK_STATE).get("tasks", {}).get(NEXT_TASK) == "planned",
        "Resume evidence is immutable after Task010 begins",
    )
    VERIFICATION_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    VERIFICATION_EVIDENCE.write_text(
        json.dumps(_verification_payload(checks), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_verification_evidence() -> Check:
    _require(VERIFICATION_EVIDENCE.is_file(), "Resume verification evidence missing")
    evidence = _load_json(VERIFICATION_EVIDENCE)
    _require(
        VERIFICATION_EVIDENCE.read_bytes() == _blob_at(TASK010_BASE_COMMIT, VERIFICATION_EVIDENCE),
        "Resume verification evidence was rewritten",
    )
    _require(
        evidence.get("schema_version") == "1.1"
        and evidence.get("review_id") == REVIEW_ID
        and evidence.get("run_id") == RUN_ID,
        "verification identity/schema drifted",
    )
    _require(
        evidence.get("status") == "PASS_LOCAL_CONTRACT_VERIFICATION_G3_BLOCKED_TECHNICAL"
        and evidence.get("gate_status") == "BLOCKED_TECHNICAL",
        "verification gate status drifted",
    )
    _require(
        evidence.get("stage_3_remote_upload_authorized") is False
        and evidence.get("stage_4_authorized") is False
        and evidence.get("external_action_observation") == "NOT_OBSERVED_BY_OFFLINE_VERIFIER"
        and evidence.get("remote_pull_request_observation") == "NOT_REVERIFIED_OFFLINE"
        and evidence.get("process_attestation")
        == {
            "deployment_executed": False,
            "new_dag_task_executed": False,
            "real_platform_calls": 0,
            "shared_github_token_value_contact": "ZERO",
            "shared_github_auth_mutation": "ZERO",
            "authenticated_session_use": "NOT_USED",
        },
        "verification evidence authorization/evidence class/process attestation drifted",
    )
    generated_at = datetime.fromisoformat(evidence.get("generated_at", ""))
    _require(generated_at.tzinfo is not None, "verification timestamp must be timezone-aware")
    _require(
        evidence.get("artifact_digests") == _artifact_digests(commit=TASK010_BASE_COMMIT),
        "verification source artifact digest set is not pinned to the Resume final commit",
    )
    recorded_checks = evidence.get("checks", [])
    names = [item.get("name") for item in recorded_checks]
    _require(
        len(names) == len(EXPECTED_RECORDED_EVIDENCE_CHECKS)
        and len(names) == len(set(names))
        and set(names) == EXPECTED_RECORDED_EVIDENCE_CHECKS
        and all(item.get("status") == "PASS" for item in recorded_checks),
        "verification evidence contains a failed, duplicate, extra, or missing check",
    )
    lane_details = next(
        item.get("details", {})
        for item in recorded_checks
        if item.get("name") == "bounded_fast_software_lane"
    )
    _require(
        lane_details.get("blocking_executions") == 9
        and lane_details.get("blocking_failures") == 0
        and lane_details.get("remote_github_actions") == "NOT_RUN_LOCAL_BASELINE",
        "pinned Resume software lane receipt drifted",
    )
    return Check(
        "verification_evidence",
        "PASS",
        {
            "recorded_checks": len(recorded_checks),
            "artifact_digests": len(evidence["artifact_digests"]),
            "gate_status": evidence["gate_status"],
            "external_action_observation": evidence["external_action_observation"],
        },
    )


def run_checks(
    *,
    verify_worktree: bool,
    require_evidence: bool,
    lane_report: Path | None = None,
) -> list[Check]:
    checks = [
        validate_resume_fact_and_schema(),
        validate_historical_integrity(),
        validate_taskpack_and_traceability(),
        validate_release_and_data_contracts(),
        validate_documents_and_source_safety(),
        validate_decision_evidence(),
        validate_private_db_client_audit(verify_local_source=verify_worktree),
    ]
    if verify_worktree:
        checks.append(validate_worktree())
    if lane_report is not None:
        checks.append(validate_lane_report(lane_report))
    if require_evidence:
        checks.append(validate_verification_evidence())
    return checks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--lane-report", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            require_evidence=args.require_evidence,
            lane_report=args.lane_report,
        )
        if args.write_evidence:
            _write_evidence(checks)
    except (
        OSError,
        ResumeError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {"reason": str(error), "review_id": REVIEW_ID, "status": "FAIL_CLOSED"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "checks": [item.name for item in checks],
                "review_id": REVIEW_ID,
                "status": "PASS_HISTORICAL_RESUME_CONTRACT",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
