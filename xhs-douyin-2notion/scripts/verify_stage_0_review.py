#!/usr/bin/env python3
"""Fail-closed verifier for x2n Stage 0 Review and G0 decision.

The review can complete while G0 remains blocked. A pending before-G0 owner
action must never be converted into PASS by this verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ROADMAP = PROJECT_ROOT / "docs/product_design/v0.0.0.1/02_ROADMAP.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S00_REVIEW.md"
RECOVERY_RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S00_REVIEW_RESUME_PREP.md"
REVIEW_REPORT = PROJECT_ROOT / "docs/governance/STAGE_0_REVIEW.md"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
GATE_STATE = PROJECT_ROOT / "machine/facts/stage_gate_state.json"
GATE_SCHEMA = PROJECT_ROOT / "machine/schemas/stage_gate_state.schema.json"
PATH_CONTRACT = PROJECT_ROOT / "machine/facts/path_contract.json"
PLATFORM_SCOPE = PROJECT_ROOT / "machine/facts/platform_scope_registry.json"
COMPETITOR = PROJECT_ROOT / "machine/facts/competitor_registry.json"
UPSTREAM_REGISTRY = PROJECT_ROOT / "machine/facts/upstream_registry.json"
ARCHITECTURE = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
STOP_KILL = PROJECT_ROOT / "machine/policy/stop_kill_registry.json"
FIXTURES = PROJECT_ROOT / "machine/fixtures/stage_0_governance_cases.json"
OWNER_SCHEMA = PROJECT_ROOT / "machine/schemas/owner_input_contract.schema.json"
RECOVERY_SCHEMA = PROJECT_ROOT / "machine/schemas/owner_recovery_attestation.schema.json"
RECOVERY_FIXTURE = PROJECT_ROOT / "machine/fixtures/owner_recovery_attestation.example.json"
EXTERNAL_REVALIDATION = PROJECT_ROOT / "machine/evidence/stage_0/review/external_revalidation.json"
REVIEW_EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_0/review"

REVIEW_BRANCH = "codex/xhs-douyin-2notion-v0001-s00-review"
REVIEW_ID = "STG.X2N.0.REVIEW"
REVIEW_RUN_ID = "RUN-X2N-S00-REVIEW"
REVIEW_FINAL_COMMIT = "623ba01c951aa6d5d11bfecda6b482efac4a4d1f"
STAGE_1_REVIEW_COMMIT = "2a81db2dd36638b00175ec6226462b37905d4705"
RESUME_ID = "STG.X2N.0.REVIEW.RESUME"
RESUME_RUN_ID = "RUN-X2N-S00-REVIEW-RESUME"
INCIDENT_ID = "INC-X2N-S00-P05-001"
EXPECTED_ROADMAP_SHA256 = "66f949b2109ffe2701d7b74099430e862f4027bb4a429c56e84e13716c0bc906"
EXPECTED_TASKPACK_ZIP_SHA256 = "b32993f465888d9352d745b353c3b923c38406c941a8f357ddf1a64e2bba5a58"

STAGE_TASKS = tuple(f"TSK.x2n.discovery.{index:03d}" for index in range(1, 6))
PLATFORMS = ("xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao")
G0_PASS_CONDITIONS = (
    "governance registered",
    "license and upstream registry complete",
    "public/private runtime policy machine-checkable",
    "threat model and ADRs complete",
    "synthetic fixtures permit development without real credentials",
)
G0_TASKPACK_STOP_CONDITIONS = (
    "license conflict",
    "bypass requirement",
    "private data must enter public repo",
)
G0_STATE_PASS_KEYS = (
    "governance_registered",
    "license_and_upstream_registry_complete",
    "public_private_runtime_policy_machine_checkable",
    "threat_model_and_adrs_complete",
    "synthetic_fixtures_support_no_real_credentials",
)
G0_STATE_STOP_KEYS = (
    "license_conflict",
    "bypass_requirement",
    "private_data_must_enter_public_repo",
    "no_reversible_data_design",
)

PHASE_EVIDENCE_FILES = {
    "phase_0_1": {
        "verification.json",
        "TSK.x2n.discovery.001.json",
        "TSK.x2n.discovery.002.json",
        "TSK.x2n.discovery.003.json",
        "ACC.x2n.gov.001.json",
        "ACC.x2n.gov.002.json",
        "ACC.x2n.media.001.json",
        "ACC.x2n.ops.002.json",
    },
    "phase_0_2": {
        "verification.json",
        "TSK.x2n.discovery.004.json",
        "ACC.x2n.gov.003.json",
        "ACC.x2n.dy.003.json",
        "cleanup.json",
    },
    "phase_0_5": {
        "verification.json",
        "TSK.x2n.discovery.005.json",
        "ACC.x2n.gov.003.json",
        "ACC.x2n.media.003.json",
        "ACC.x2n.rel.003.json",
        "cleanup.json",
        "INC-X2N-S00-P05-001.json",
    },
}


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


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    _require(isinstance(value, dict), f"YAML object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, f"git command failed: {' '.join(args)}")
    return result.stdout.rstrip()


def _load_json_at(commit: str, path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    value = json.loads(_git(["show", f"{commit}:{relative}"]))
    _require(isinstance(value, dict), f"historical JSON object required: {path.name}")
    return value


def _text_files() -> Iterable[Path]:
    suffixes = {"", ".md", ".json", ".yaml", ".yml", ".py", ".txt", ".toml"}
    ignored = {
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "build",
        "dist",
        "node_modules",
    }
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.parts):
            continue
        if path.suffix.lower() in suffixes or path.name in {"VERSION", ".gitignore"}:
            yield path


def _load_verifier(module_name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / "scripts" / filename)
    _require(spec is not None and spec.loader is not None, f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def validate_review_documents() -> Check:
    required = (
        RUN_CONTRACT,
        RECOVERY_RUN_CONTRACT,
        REVIEW_REPORT,
        PROJECT_ROOT / "docs/governance/CHANGE_EVENT_S00_REVIEW.md",
        GATE_STATE,
        TASK_STATE,
        GATE_SCHEMA,
        RECOVERY_SCHEMA,
        RECOVERY_FIXTURE,
        PROJECT_ROOT / "scripts/record_owner_recovery.py",
        PROJECT_ROOT / "scripts/verify_owner_recovery_attestation.py",
        EXTERNAL_REVALIDATION,
    )
    missing = [path.name for path in required if not path.is_file()]
    _require(not missing, f"Stage Review artifacts missing: {missing}")
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    report = REVIEW_REPORT.read_text(encoding="utf-8")
    for token in (REVIEW_RUN_ID, REVIEW_ID, "不执行新的 DAG Task", "不 push"):
        _require(token in contract, f"Review Run Contract missing: {token}")
    recovery_contract = RECOVERY_RUN_CONTRACT.read_text(encoding="utf-8")
    for token in (
        "RUN-X2N-S00-REVIEW-RESUME-PREP",
        "不执行新的 DAG Task",
        "STAGE_0_REVIEW_RESUME_ONLY",
        "BLOCKED_OWNER_ACTION",
    ):
        _require(token in recovery_contract, f"Recovery Run Contract missing: {token}")
    for token in (
        "G0_BLOCKED_OWNER_ACTION",
        "STAGE_1_UNAUTHORIZED",
        "REMOTE_UPLOAD_FORBIDDEN",
        INCIDENT_ID,
        "UNKNOWN_DISABLED",
    ):
        _require(token in report, f"Stage Review report missing: {token}")
    change_event = (PROJECT_ROOT / "docs/governance/CHANGE_EVENT_S00_REVIEW.md").read_text(encoding="utf-8")
    for token in ("CE-X2N-20260720-S00-REVIEW", "流程粒度不符合项", "G0_BLOCKED_OWNER_ACTION"):
        _require(token in change_event, f"Review Change Event missing: {token}")
    return Check("review_documents", "PASS", {"required_artifacts": len(required), "missing": 0})


def validate_task_and_gate_contract() -> Check:
    taskpack = _load_yaml(TASKPACK)
    execution = taskpack.get("execution_policy", {})
    _require(execution.get("single_task_focus") is True, "single-task focus missing")
    _require(execution.get("max_tasks_per_run") == 1, "more than one DAG task may run")
    _require(execution.get("single_phase_focus") is True, "single-phase upper bound missing")
    _require(execution.get("max_phases_per_run") == 1, "more than one Phase may run")
    _require(execution.get("intermediate_phase_push") == "forbidden", "intermediate push is not forbidden")

    stage_tasks = [item for item in taskpack.get("tasks", []) if item.get("stage") == "STG.X2N.0"]
    _require(tuple(item.get("id") for item in stage_tasks) == STAGE_TASKS, "Stage 0 task set/order drifted")
    _require(all(item.get("status") == "completed" for item in stage_tasks), "Stage 0 task is not completed")
    _require(
        [item.get("phase") for item in stage_tasks]
        == ["PH.X2N.0.1", "PH.X2N.0.1", "PH.X2N.0.1", "PH.X2N.0.2", "PH.X2N.0.5"],
        "Stage 0 Phase routing drifted",
    )
    for task in stage_tasks:
        _require(task.get("completion_gate") == "all outputs exist; declared tests pass; evidence receipts emitted; no stop condition active", f"completion gate drifted: {task['id']}")
        for relative in task.get("evidence", []):
            _require((PROJECT_ROOT / relative).is_file(), f"task evidence missing: {relative}")

    gates = [item for item in taskpack.get("stage_gates", []) if item.get("id") == "G0"]
    _require(len(gates) == 1, "G0 missing or duplicated")
    gate = gates[0]
    _require(tuple(gate.get("requires_tasks", [])) == STAGE_TASKS, "G0 required task set drifted")
    _require(tuple(gate.get("pass_conditions", [])) == G0_PASS_CONDITIONS, "G0 pass conditions drifted")
    _require(tuple(gate.get("stop_conditions", [])) == G0_TASKPACK_STOP_CONDITIONS, "G0 taskpack stop conditions drifted")
    roadmap = ROADMAP.read_text(encoding="utf-8")
    _require("无可回滚数据设计" in roadmap, "roadmap reversible-data Stop Condition missing")

    feature_flags = taskpack.get("feature_flags", {})
    _require("mediacrawler_adapter" not in feature_flags, "restricted upstream remains a product feature flag")
    return Check(
        "task_and_gate_contract",
        "PASS",
        {"stage_tasks": len(stage_tasks), "g0_pass_conditions": 5, "combined_stop_conditions": 4, "max_tasks_per_run": 1},
    )


def validate_canonical_boundaries() -> Check:
    project = _load_json(PROJECT_FACT)
    _require(project.get("parent_repository") == "LinzeColin/MetaDatabase", "wrong parent repository")
    _require(project.get("name") == "xhs-douyin-2notion" and project.get("project_path") == "xhs-douyin-2notion/", "wrong project identity")
    _require(project.get("run_maximum") == "one_task", "project fact weakened the run limit")
    _require(project.get("stage_review_run_kind") == "no_new_dag_task", "Review exception is not bounded")
    _require(project.get("repository_visibility") == "public", "public-repository boundary drifted")
    _require(project.get("license_policy") == "proprietary_all_rights_reserved", "proprietary license policy drifted")
    _require(tuple(project.get("platform_scope", [])) == PLATFORMS, "six-platform scope drifted")

    path_contract = _load_json(PATH_CONTRACT)
    _require(path_contract.get("root_ref") == "X2N_DATA_ROOT", "wrong private root reference")
    _require(path_contract.get("owner_download_destination_ref") == "X2N_DOWNLOAD_DESTINATION", "download destination reference missing")
    _require(path_contract.get("owner_download_destination_required_basename") == "MediaCrawler", "download destination basename drifted")
    _require(path_contract.get("owner_namespace") == "xhs-douyin-2notion", "private namespace drifted")
    _require(path_contract.get("destination_name_semantics") == "storage_parent_only_no_upstream_authorization", "storage parent authorized an upstream")
    _require(path_contract.get("must_be_outside_git") is True and path_contract.get("runtime_and_downloads_share_root") is True, "runtime/download boundary drifted")
    required_dirs = set(path_contract.get("required_directories", []))
    allowed_private_files = set(path_contract.get("allowed_private_contract_files", []))
    _require(
        "runtime/owner_recovery_attestation.local.json" in allowed_private_files,
        "private recovery attestation path is not registered",
    )
    for platform in PLATFORMS:
        _require(f"downloads/{platform}/runs" in required_dirs, f"download namespace missing: {platform}")

    platforms = _load_json_at(REVIEW_FINAL_COMMIT, PLATFORM_SCOPE)
    rows = platforms.get("platforms", [])
    _require(tuple(item.get("id") for item in rows) == PLATFORMS, "platform registry drifted")
    _require(all(item.get("policy_state") == "unknown_disabled" for item in rows), "a platform was enabled without its Gate")
    _require(platforms.get("implementation_started") is False and platforms.get("real_platform_calls") is False, "platform implementation/execution was overstated")

    competitor = _load_json(COMPETITOR)
    _require(competitor.get("actual_runtime_dependencies") == [] and competitor.get("code_copies") == 0, "competitor entered product source/runtime")
    boundary = competitor.get("restricted_research_boundary", {})
    for key in ("product_adapter_allowed", "installation_allowed", "execution_allowed", "output_ingest_allowed", "runtime_dependency_allowed", "vendoring_allowed"):
        _require(boundary.get(key) is False, f"restricted upstream boundary weakened: {key}")
    upstream = _load_json(UPSTREAM_REGISTRY)
    _require(upstream.get("actual_runtime_dependencies") == [], "Stage 0 has an actual runtime dependency")

    architecture = _load_json_at(REVIEW_FINAL_COMMIT, ARCHITECTURE)
    _require([item.get("id") for item in architecture.get("decisions", [])] == [f"ADR-{index:03d}" for index in range(1, 11)], "ADR set drifted")
    if architecture.get("implementation_started") is False:
        _require(architecture.get("status") == "accepted_design_not_implemented", "historical architecture status drifted")
    else:
        implementation_scopes = {
            "foundation_004_extension_native_skeleton_implemented_g1_not_run": (
                "TSK.x2n.foundation.001-004_scaffold_contracts_store_extension_native_skeleton"
            ),
            "foundation_005_ci_and_model_assurance_baseline_implemented_g1_not_run": (
                "TSK.x2n.foundation.001-005_scaffold_contracts_store_extension_native_and_ci_baseline"
            ),
            "stage_1_review_pass_g1_pass": (
                "TSK.x2n.foundation.001-005_scaffold_contracts_store_extension_native_and_ci_baseline"
            ),
        }
        status = architecture.get("status")
        _require(status in implementation_scopes, "foundation architecture status drifted")
        _require(architecture.get("implementation_scope") == implementation_scopes[status], "foundation implementation scope overstated")
        expected_gate = "g1_pass" if status == "stage_1_review_pass_g1_pass" else "g1_not_run"
        _require(
            architecture.get("real_account_execution") is False
            and architecture.get("stage_gate") == expected_gate,
            "foundation Gate/account status mismatch",
        )
    stop_kill = _load_json(STOP_KILL)
    _require([item.get("id") for item in stop_kill.get("rules", [])] == [f"SK-X2N-{index:03d}" for index in range(1, 21)], "Stop/Kill rule set drifted")
    fixtures = _load_json(FIXTURES)
    _require(len(fixtures.get("cases", [])) == 50 and fixtures.get("synthetic_only") is True and fixtures.get("real_accounts") is False, "synthetic fixture boundary drifted")
    owner_schema = _load_json(OWNER_SCHEMA)
    taxonomy = owner_schema["properties"]["taxonomy"]["properties"]
    media = owner_schema["properties"]["media_retention"]["properties"]
    _require(taxonomy["ai_may_create_top_level"]["const"] is False, "AI may create a top-level category")
    _require(media["persist_platform_cdn_urls"]["const"] is False and media["persist_raw_media"]["const"] is False, "media persistence boundary drifted")
    recovery_schema = _load_json(RECOVERY_SCHEMA)
    _require(recovery_schema.get("additionalProperties") is False, "recovery attestation schema permits extra fields")
    recovery_properties = recovery_schema.get("properties", {})
    _require(set(recovery_schema.get("required", [])) == set(recovery_properties), "recovery attestation schema has optional or undeclared fields")
    _require(recovery_properties.get("g0_pass_granted", {}).get("const") is False, "recovery receipt may grant G0")
    _require(recovery_properties.get("stage_1_authorized", {}).get("const") is False, "recovery receipt may authorize Stage 1")
    _require(recovery_properties.get("remote_upload_authorized", {}).get("const") is False, "recovery receipt may authorize upload")
    recovery_fixture = _load_json(RECOVERY_FIXTURE)
    recovery_verifier = _load_verifier("verify_owner_recovery_attestation_review", "verify_owner_recovery_attestation.py")
    recovery_check = recovery_verifier.validate_receipt_payload(
        recovery_fixture,
        now=datetime(2026, 7, 20, 0, 0, 0, tzinfo=timezone.utc),
        incident_at=datetime(2026, 7, 19, 20, 55, 14, tzinfo=timezone.utc),
    )
    _require(recovery_check.status == "PASS", "synthetic recovery attestation does not pass its verifier")

    current_state = _load_json(TASK_STATE)
    if current_state.get("tasks", {}).get("TSK.x2n.foundation.001") == "pass":
        for relative in ("apps", "packages", "SKILL.md"):
            _require((PROJECT_ROOT / relative).exists(), f"registered foundation scaffold missing: {relative}")
        for relative in ("extension", "companion", "runtime", "downloads"):
            _require(not (PROJECT_ROOT / relative).exists(), f"unexpected top-level product/runtime path: {relative}")
    else:
        for relative in ("apps", "packages", "extension", "companion", "SKILL.md"):
            _require(not (PROJECT_ROOT / relative).exists(), f"product implementation entered Stage 0 Review: {relative}")

    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "Codex" + "Project",
        "LinzeColin/" + "xhs-douyin-2notion",
        "/Users" + "/",
    )
    forbidden_hits: list[str] = []
    stale_upstream_hits: list[str] = []
    credential_hits: list[str] = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(token in text for token in forbidden_tokens):
            forbidden_hits.append(str(path.relative_to(PROJECT_ROOT)))
        stale_scope = path in {
            TASKPACK,
            PROJECT_ROOT / "docs/product_design/v0.0.0.1/01_PRD.md",
            PROJECT_ROOT / "docs/product_design/v0.0.0.1/03_ARCHITECTURE_SECURITY_SYSTEM_CARD.md",
            PROJECT_ROOT / "docs/product_design/v0.0.0.1/06_RELEASE_OPERATIONS.md",
        }
        stale_tokens = ("media" + "crawler_adapter", "MediaCrawler" + "ResearchAdapter", "默认关闭、" + "外部安装")
        if stale_scope and any(token in text for token in stale_tokens):
            stale_upstream_hits.append(str(path.relative_to(PROJECT_ROOT)))
        if re.search(re.escape("github" + "_pat_") + r"[A-Za-z0-9]", text) or re.search(r"https://[^\s/@]+@github\.com/", text):
            credential_hits.append(str(path.relative_to(PROJECT_ROOT)))
    _require(not forbidden_hits, f"forbidden repository/path identity entered x2n: {forbidden_hits}")
    _require(not stale_upstream_hits, f"stale MediaCrawler product semantics remain: {stale_upstream_hits}")
    _require(not credential_hits, f"credential-shaped content entered repository: {credential_hits}")
    return Check(
        "canonical_boundaries",
        "PASS",
        {
            "platforms": 6,
            "platforms_enabled": 0,
            "runtime_dependencies": 0,
            "competitor_code_copies": 0,
            "recovery_attestation_contract": "PASS_SYNTHETIC_ONLY",
            "product_code": (
                "FOUNDATION_IMPLEMENTATION_PRESENT"
                if current_state.get("tasks", {}).get("TSK.x2n.foundation.001") == "pass"
                else "NOT_STARTED"
            ),
        },
    )


def validate_gate_payload(gate: dict[str, Any]) -> None:
    _require(gate.get("schema_version") == "1.0", "gate state schema drifted")
    _require(gate.get("project") == "x2n" and gate.get("stage") == "STG.X2N.0", "gate state identity drifted")
    identity = (gate.get("review_id"), gate.get("run_id"))
    _require(identity in {(REVIEW_ID, REVIEW_RUN_ID), (RESUME_ID, RESUME_RUN_ID)}, "gate Review identity drifted")
    _require(re.fullmatch(r"[0-9a-f]{40}", str(gate.get("review_sync_target", ""))) is not None, "Review sync target is missing or invalid")
    _require(gate.get("review_status") == "complete" and gate.get("automated_reacceptance") == "pass", "Review did not complete local reacceptance")
    _require(gate.get("gate_id") == "G0", "wrong stage gate")
    _require(tuple(gate.get("pass_conditions", {}).keys()) == G0_STATE_PASS_KEYS, "G0 state pass-condition keys drifted")
    _require(all(value == "pass" for value in gate["pass_conditions"].values()), "a local G0 pass condition failed")
    _require(tuple(gate.get("stop_conditions", {}).keys()) == G0_STATE_STOP_KEYS, "G0 state stop-condition keys drifted")
    _require(all(value == "inactive" for value in gate["stop_conditions"].values()), "a G0 Stop Condition is active or unknown")
    if identity == (REVIEW_ID, REVIEW_RUN_ID):
        _require(gate.get("blocking_followups") == [{
            "id": INCIDENT_ID,
            "scope": "before_g0_pass",
            "status": "owner_action_pending",
            "required_resolution": "rotate_or_reauthenticate_or_prove_expiry",
        }], "before-G0 credential follow-up missing or weakened")
        _require(gate.get("gate_status") == "blocked_owner_action", "pending owner action did not block G0")
        _require(gate.get("gate_decision") == "fail_closed", "G0 decision is not fail-closed")
        _require(gate.get("stage_1_authorized") is False, "Stage 1 was authorized while G0 is blocked")
        _require(gate.get("remote_upload") == "forbidden_until_g0_pass", "remote upload was authorized while G0 is blocked")
    else:
        _require(gate.get("blocking_followups") == [{
            "id": INCIDENT_ID,
            "scope": "before_g0_pass",
            "status": "resolved",
            "required_resolution": "owner_directed_external_retention_with_x2n_zero_contact",
        }], "Resume resolution is missing or ambiguous")
        _require(gate.get("gate_status") == "pass" and gate.get("gate_decision") == "pass", "Resume did not produce an exact G0 pass")
        _require(gate.get("stage_1_authorized") is True, "Stage 1 was not authorized after G0 pass")
        _require(gate.get("remote_upload") == "authorized_after_g0_pass", "Stage 0 upload was not authorized after G0 pass")
    _require(gate.get("product_code") == "not_started" and gate.get("real_account_execution") == "not_run" and gate.get("platform_calls") == "not_run", "Stage 0 execution boundary overstated")


def validate_current_state() -> Check:
    gate = _load_json(GATE_STATE)
    schema = _load_json(GATE_SCHEMA)
    required = set(schema.get("required", []))
    allowed = set(schema.get("properties", {}))
    _require(required.issubset(gate), f"gate state missing fields: {sorted(required - set(gate))}")
    _require(set(gate).issubset(allowed), f"gate state has unknown fields: {sorted(set(gate) - allowed)}")
    validate_gate_payload(gate)

    state = _load_json_at(STAGE_1_REVIEW_COMMIT, TASK_STATE)
    _require(tuple(state.get("tasks", {}).keys())[: len(STAGE_TASKS)] == STAGE_TASKS, "Stage 0 task order drifted")
    _require(all(state.get("tasks", {}).get(task) == "pass" for task in STAGE_TASKS), "Stage 0 task state drifted")
    if state.get("schema_version") == "1.8":
        _require(
            state.get("previous_stage_gate")
            == {"gate_id": "G0", "status": gate["gate_status"], "stage": "STG.X2N.0", "remote_upload": "merged"},
            "task state lost the historical G0 result",
        )
    else:
        _require(state.get("stage_gate") == gate["gate_status"], "task/gate state disagree")
        _require(state.get("remote_upload") == gate["remote_upload"], "task/gate upload state disagree")
    project = _load_json_at(STAGE_1_REVIEW_COMMIT, PROJECT_FACT)
    if gate.get("gate_status") == "blocked_owner_action":
        _require(state.get("schema_version") == "1.1", "blocked task state schema drifted")
        _require(state.get("review_id") == REVIEW_ID and state.get("run_id") == REVIEW_RUN_ID, "blocked task state Review identity drifted")
        _require(state.get("run_kind") == "stage_review_no_new_dag_task" and state.get("state") == "review_complete_gate_blocked", "blocked Review state is invalid")
        _require(state.get("stage_1_authorized") is False and state.get("next_phase_authorized") is False, "next Stage/Phase was authorized while blocked")
        _require(state.get("next_phase") is None and state.get("next_run") == RESUME_ID, "blocked next route drifted")
        _require(state.get("blocking_followups", [{}])[0].get("id") == INCIDENT_ID and state["blocking_followups"][0].get("status") == "owner_action_pending", "task state lost the pending follow-up")
        _require(project.get("status") == "stage_0_review_complete_g0_blocked_owner_action", "project fact does not reflect blocked Review verdict")
        details = {"review": "COMPLETE", "g0": "BLOCKED_OWNER_ACTION", "stage_1_authorized": False, "remote_upload": "FORBIDDEN"}
    elif state.get("schema_version") == "1.2":
        _require(state.get("schema_version") == "1.2", "Resume task state schema drifted")
        _require(state.get("review_id") == RESUME_ID and state.get("run_id") == RESUME_RUN_ID, "Resume task state identity drifted")
        _require(state.get("run_kind") == "stage_review_resume_no_new_dag_task" and state.get("state") == "stage_0_g0_pass", "Resume task state is invalid")
        _require(state.get("stage_1_authorized") is True and state.get("next_phase_authorized") is True, "next Stage/Phase was not authorized after G0 pass")
        _require(state.get("next_phase") == "PH.X2N.1.1" and state.get("next_run") == "TSK.x2n.foundation.001", "post-G0 next route drifted")
        _require(state.get("blocking_followups") == [{
            "id": INCIDENT_ID,
            "scope": "before_g0_pass",
            "status": "resolved",
            "action": "owner_directed_external_retention_with_x2n_zero_contact",
        }], "task state Resume resolution is missing or ambiguous")
        _require(project.get("status") == "stage_0_g0_pass_stage_1_authorized", "project fact does not reflect G0 pass")
        details = {"review": "RESUME_COMPLETE", "g0": "PASS", "stage_1_authorized": True, "remote_upload": "AUTHORIZED"}
    else:
        schema_version = state.get("schema_version")
        _require(schema_version in {"1.6", "1.7", "1.8"}, "unsupported current task state")
        expected_current = {
            "1.6": {
                "next_phase": "PH.X2N.1.5",
                "next_run": "TSK.x2n.foundation.005",
                "project_status": "stage_1_foundation_004_complete_g1_not_run",
                "run_id": "RUN-X2N-S01-F004",
                "state": "stage_1_foundation_004_pass_g1_not_run",
            },
            "1.7": {
                "next_phase": "STG.X2N.1.REVIEW",
                "next_run": "STG.X2N.1.REVIEW",
                "project_status": "stage_1_foundation_005_complete_g1_not_run",
                "run_id": "RUN-X2N-S01-F005",
                "state": "stage_1_foundation_005_pass_g1_not_run",
            },
            "1.8": {
                "next_phase": "PH.X2N.2.1",
                "next_run": "TSK.x2n.skeleton.001",
                "project_status": "stage_1_review_pass_g1_pass_stage_2_authorized",
                "run_id": "RUN-X2N-S01-REVIEW",
                "state": "stage_1_review_pass_g1_pass_remote_upload_authorized",
            },
        }[schema_version]
        if schema_version == "1.8":
            _require(state.get("review_id") == "STG.X2N.1.REVIEW", "G1 Review identity mismatch")
            _require(
                state.get("run_id") == expected_current["run_id"]
                and state.get("run_kind") == "stage_review_no_new_dag_task",
                "G1 Review Run identity mismatch",
            )
        else:
            _require(state.get("review_id") == RESUME_ID, "G0 Resume identity was lost")
            _require(
                state.get("run_id") == expected_current["run_id"] and state.get("run_kind") == "single_dag_task",
                "foundation Run identity mismatch",
            )
        _require(state.get("stage") == "STG.X2N.1" and state.get("state") == expected_current["state"], "current Stage state is invalid")
        _require(state.get("stage_1_authorized") is True and state.get("next_phase_authorized") is True, "Stage 1 authorization drifted")
        _require(state.get("tasks", {}).get("TSK.x2n.foundation.002") == "pass", "foundation.002 Task is not pass")
        _require(state.get("tasks", {}).get("TSK.x2n.foundation.003") == "pass", "foundation.003 Task is not pass")
        _require(state.get("tasks", {}).get("TSK.x2n.foundation.004") == "pass", "foundation.004 Task is not pass")
        if schema_version in {"1.7", "1.8"}:
            _require(state.get("tasks", {}).get("TSK.x2n.foundation.005") == "pass", "foundation.005 Task is not pass")
        _require(
            state.get("next_phase") == expected_current["next_phase"]
            and state.get("next_run") == expected_current["next_run"],
            "foundation next route drifted",
        )
        _require(state.get("blocking_followups") == [{
            "id": INCIDENT_ID,
            "scope": "before_g0_pass",
            "status": "resolved",
            "action": "owner_directed_external_retention_with_x2n_zero_contact",
        }], "task state Resume resolution is missing or ambiguous")
        if schema_version == "1.8":
            _require(
                state.get("current_stage_gate") == "pass"
                and state.get("current_stage_remote_upload") == "authorized_after_g1_pass",
                "G1 Review state mismatch",
            )
        else:
            _require(state.get("current_stage_gate") == "not_run" and state.get("current_stage_remote_upload") == "forbidden_until_g1_pass", "G1/upload overstated")
        _require(project.get("status") == expected_current["project_status"], "project fact does not reflect foundation completion")
        details = {
            "review": "RESUME_COMPLETE",
            "g0": "PASS",
            "stage_1_authorized": True,
            "remote_upload": "AUTHORIZED_AFTER_G1_PASS" if schema_version == "1.8" else "STAGE_1_FORBIDDEN_UNTIL_G1",
        }
    return Check("current_stage_state", "PASS", details)


def validate_phase_receipts() -> Check:
    base = PROJECT_ROOT / "machine/evidence/stage_0"
    manifest: dict[str, str] = {}
    for phase, expected in PHASE_EVIDENCE_FILES.items():
        directory = base / phase
        actual = {path.name for path in directory.glob("*.json")}
        _require(actual == expected, f"{phase} evidence set mismatch: {sorted(actual)}")
        for path in sorted(directory.glob("*.json")):
            manifest[str(path.relative_to(PROJECT_ROOT))] = _sha256(path)

    p01 = _load_json(base / "phase_0_1/verification.json")
    _require(p01.get("phase_status") == "PASS" and p01.get("stage_gate") == "NOT_RUN", "Phase 0.1 receipt overstated")
    _require(p01.get("downstream_acceptance") == {
        "ACC.x2n.gov.001": "PASS",
        "ACC.x2n.gov.002": "DOWNSTREAM_NOT_RUN",
        "ACC.x2n.media.001": "DOWNSTREAM_NOT_RUN",
        "ACC.x2n.ops.002": "DOWNSTREAM_NOT_RUN",
    }, "Phase 0.1 downstream status drifted")
    p02 = _load_json(base / "phase_0_2/verification.json")
    _require(p02.get("status") == "PASS" and p02.get("stage_gate") == "NOT_RUN", "Phase 0.2 receipt overstated")
    _require(p02.get("adapter_contract_tests") == "DOWNSTREAM_NOT_RUN", "Phase 0.2 adapter status overstated")
    p05 = _load_json(base / "phase_0_5/verification.json")
    _require(p05.get("status") == "PASS" and p05.get("stage_gate") == "NOT_RUN", "Phase 0.5 receipt overstated")
    _require(p05.get("acceptance_status", {}).get("ACC.x2n.media.003") == "DESIGN_FIXTURE_PASS_DOWNSTREAM_NOT_RUN", "Phase 0.5 media status overstated")
    incident = _load_json(base / f"phase_0_5/{INCIDENT_ID}.json")
    _require(incident.get("status") == "CONTAINED_OWNER_ACTION_PENDING", "credential incident status overstated")
    _require(incident.get("credential_value_in_evidence") is False and incident.get("affected_product_or_runtime_files") == 0, "credential incident evidence is unsafe")
    manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return Check("phase_evidence_receipts", "PASS", {"files": len(manifest), "manifest_sha256": manifest_hash, "downstream_product_oracles": "NOT_RUN"})


def validate_external_revalidation() -> Check:
    evidence = _load_json(EXTERNAL_REVALIDATION)
    _require(evidence.get("review_id") == REVIEW_ID and evidence.get("revalidated_on") == "2026-07-20", "external revalidation identity/date drifted")
    competitor = evidence.get("competitor", {})
    expected_commit = "765207310a90a81c615c0ba2df124543b424af89"
    _require(competitor.get("selected_commit") == expected_commit and competitor.get("current_default_head") == expected_commit, "competitor fixed/current commit mismatch")
    _require(competitor.get("tree") == "3fe084d7e3835669ccdb4193312b065a48eeb5d7" and competitor.get("non_git_files") == 177, "competitor tree metrics drifted")
    _require(competitor.get("source_copy") is False and competitor.get("runtime_dependency") is False and competitor.get("execution") is False and competitor.get("output_ingest") is False, "competitor crossed the research boundary")
    sources = evidence.get("official_policy_sources", {})
    _require(tuple(sources.keys()) == ("chrome", "notion", *PLATFORMS), "official source lanes drifted")
    _require(all(isinstance(urls, list) and urls and all(str(url).startswith("https://") for url in urls) for urls in sources.values()), "official source registry is incomplete")
    conclusions = evidence.get("policy_conclusions", {})
    _require(conclusions.get("legal_or_platform_authorization_granted_by_research") is False, "research was treated as platform authorization")
    _require(conclusions.get("platform_enablement_changed") is False and conclusions.get("all_six_platforms_remain_unknown_disabled") is True, "external recheck enabled a platform")
    return Check("external_revalidation", "PASS", {"competitor_head_unchanged": True, "official_source_lanes": len(sources), "platforms_enabled": 0})


def _porcelain_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value)
    return paths


def _evaluate_main_isolation(changed_paths: list[str], allow_external_main_dirty: bool) -> dict[str, Any]:
    legacy = "xiao" + "hongshu-douyin-2notion"
    overlap = sum(
        path == "xhs-douyin-2notion"
        or path.startswith("xhs-douyin-2notion/")
        or path == legacy
        or path.startswith(f"{legacy}/")
        for path in changed_paths
    )
    _require(overlap == 0, "MetaDatabase main worktree overlaps x2n")
    _require(allow_external_main_dirty or not changed_paths, "MetaDatabase main worktree is dirty")
    return {
        "main_worktree_clean": not changed_paths,
        "isolation_mode": "strict_main_clean" if not changed_paths else "external_main_dirty_zero_project_overlap",
        "external_main_dirty_paths": len(changed_paths),
        "project_overlap_paths": overlap,
    }


def validate_worktree_scope(allow_external_main_dirty: bool = False) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "not in the MetaDatabase Review worktree")
    branch = _git(["branch", "--show-current"])
    _require(branch == REVIEW_BRANCH, "wrong Stage 0 Review branch")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote) is not None, "wrong or unsafe persisted origin")
    live_origin = _git(["rev-parse", "--verify", "origin/main"])
    sync_target = _load_json(GATE_STATE)["review_sync_target"]
    _git(["cat-file", "-e", f"{sync_target}^{{commit}}"])
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", sync_target, "HEAD"], cwd=REPOSITORY_ROOT, check=False)
    _require(ancestor.returncode == 0, "Review branch does not contain its recorded origin/main cutoff")

    origin_drift_commits = 0
    origin_project_overlap = 0
    if live_origin != sync_target:
        linear = subprocess.run(["git", "merge-base", "--is-ancestor", sync_target, live_origin], cwd=REPOSITORY_ROOT, check=False)
        _require(linear.returncode == 0, "origin/main no longer descends from the recorded Review cutoff")
        drift_paths = _git(["diff", "--name-only", f"{sync_target}..{live_origin}"]).splitlines()
        origin_project_overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in drift_paths)
        _require(origin_project_overlap == 0, "origin/main changed x2n after the Review cutoff")
        readme_diff = _git(["diff", "--unified=0", f"{sync_target}..{live_origin}", "--", "README.md"])
        _require(not any(line.startswith(("+", "-")) and "xhs-douyin-2notion" in line for line in readme_diff.splitlines()), "origin/main changed the x2n parent index after the Review cutoff")
        origin_drift_commits = int(_git(["rev-list", "--count", f"{sync_target}..{live_origin}"]))

    status = _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    changed = _porcelain_paths(status)
    _require(all(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in changed), "Review changed scope escaped x2n")
    _require(not any(path.startswith("xhs-douyin-2notion/machine/evidence/stage_0/phase_") for path in changed), "Review rewrote historical Phase evidence")

    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        fields = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in fields if line.startswith("worktree ")), None)
        branch_field = next((line for line in fields if line.startswith("branch ")), None)
        if worktree and branch_field == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None, "MetaDatabase main worktree missing")
    _require(_git(["branch", "--show-current"], main_path) == "main", "MetaDatabase main worktree is not on main")
    main_status = _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], main_path)
    isolation = _evaluate_main_isolation(_porcelain_paths(main_status), allow_external_main_dirty)
    counts = _git(["rev-list", "--left-right", "--count", f"{sync_target}...HEAD"]).split()
    _require(len(counts) == 2 and counts[0] == "0", "Review cutoff contains commits missing from Review")
    return Check(
        "review_worktree_scope",
        "PASS",
        {
            "branch": branch,
            "remote": "LinzeColin/MetaDatabase",
            "review_sync_target_is_ancestor": True,
            "origin_main_matches_cutoff": live_origin == sync_target,
            "origin_drift_commits_after_cutoff": origin_drift_commits,
            "origin_project_overlap_paths_after_cutoff": origin_project_overlap,
            "changed_paths": len(changed),
            "commits_ahead_of_origin": int(counts[1]),
            **isolation,
        },
    )


def validate_original_sources(roadmap: Path, taskpack_zip: Path) -> Check:
    _require(roadmap.is_file() and taskpack_zip.is_file(), "original roadmap or taskpack ZIP missing")
    roadmap_hash = _sha256(roadmap)
    taskpack_hash = _sha256(taskpack_zip)
    _require(roadmap_hash == EXPECTED_ROADMAP_SHA256, "original roadmap hash changed")
    _require(taskpack_hash == EXPECTED_TASKPACK_ZIP_SHA256, "original taskpack ZIP hash changed")
    return Check("original_sources", "PASS", {"roadmap_sha256": roadmap_hash, "taskpack_zip_sha256": taskpack_hash, "absolute_download_path_in_source": "UNSPECIFIED"})


def validate_phase_reacceptance(
    roadmap: Path,
    taskpack_zip: Path,
    local_root: Path,
    allow_external_main_dirty: bool,
) -> Check:
    p01 = _load_verifier("x2n_review_phase_0_1", "verify_phase_0_1.py")
    p02 = _load_verifier("x2n_review_phase_0_2", "verify_phase_0_2.py")
    p05 = _load_verifier("x2n_review_phase_0_5", "verify_phase_0_5.py")
    try:
        p01_checks = p01.run_core_checks()
        p01_checks.extend([
            p01.validate_local_root(local_root),
            p01.validate_worktree_scope(allow_external_main_dirty),
            p01.validate_original_sources(roadmap, taskpack_zip),
        ])
        p02_checks = p02.run_core_checks()
        p02_checks.extend([
            p02.validate_worktree_scope(allow_external_main_dirty),
            p02.validate_temp_cleanup(),
            p02.validate_evidence(),
        ])
        p05_checks = p05.run_core_checks()
        p05_checks.extend([
            p05.validate_owner_input(local_root),
            p05.validate_worktree_scope(allow_external_main_dirty),
            p05.validate_temp_cleanup(),
            p05.validate_evidence(),
        ])
    except Exception as exc:  # Convert verifier-specific fail-closed errors.
        raise VerificationError(f"Phase reacceptance failed: {exc}") from exc
    all_checks = [*p01_checks, *p02_checks, *p05_checks]
    _require(all(getattr(check, "status", None) == "PASS" for check in all_checks), "a Phase reacceptance check did not pass")
    return Check(
        "phase_reacceptance",
        "PASS",
        {"phase_0_1_checks": len(p01_checks), "phase_0_2_checks": len(p02_checks), "phase_0_5_checks": len(p05_checks), "downstream_product_oracles": "NOT_RUN"},
    )


def run_core_checks() -> list[Check]:
    return [
        validate_review_documents(),
        validate_task_and_gate_contract(),
        validate_canonical_boundaries(),
        validate_current_state(),
        validate_phase_receipts(),
        validate_external_revalidation(),
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_evidence(checks: list[Check]) -> None:
    gate = _load_json(GATE_STATE)
    validate_gate_payload(gate)
    _require(gate.get("gate_status") == "blocked_owner_action", "historical Review writer cannot overwrite evidence after Resume")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    common = {
        "schema_version": "1.0",
        "project": "x2n",
        "stage": "STG.X2N.0",
        "review_id": REVIEW_ID,
        "run_id": REVIEW_RUN_ID,
        "generated_at": now,
        "review_base_head": _git(["rev-parse", "HEAD"]),
        "review_sync_target": gate["review_sync_target"],
        "origin_main_observed_at_evidence": _git(["rev-parse", "origin/main"]),
        "product_code": "NOT_STARTED",
        "real_account_execution": "NOT_RUN",
        "platform_calls": "NOT_RUN",
        "notion_calls": "NOT_RUN",
        "model_calls": "NOT_RUN",
        "media_downloads": "NOT_RUN",
        "stage_1_authorized": False,
        "remote_upload": "FORBIDDEN_UNTIL_G0_PASS",
        "redaction": {"private_content_included": False, "secrets_included": False, "cdn_urls_included": False, "external_main_paths_included": False},
    }
    verification = dict(common)
    verification.update({
        "status": "PASS",
        "review_status": "COMPLETE",
        "g0_status": "BLOCKED_OWNER_ACTION",
        "checks": [check.__dict__ for check in checks],
        "findings": {
            "fixed": ["F-X2N-S00-R01", "F-X2N-S00-R02", "F-X2N-S00-R03", "F-X2N-S00-R04"],
            "blocking_owner_action": ["F-X2N-S00-R05"],
        },
        "downstream_product_acceptances": "NOT_RUN",
    })
    _write_json(REVIEW_EVIDENCE_DIR / "verification.json", verification)

    g0 = dict(common)
    g0.update({
        "gate_id": "G0",
        "status": "BLOCKED_OWNER_ACTION",
        "decision": "FAIL_CLOSED",
        "pass_conditions": {key: value.upper() for key, value in gate["pass_conditions"].items()},
        "stop_conditions": {key: value.upper() for key, value in gate["stop_conditions"].items()},
        "blocking_followups": gate["blocking_followups"],
        "required_next_run": "STG.X2N.0.REVIEW.RESUME",
    })
    _write_json(REVIEW_EVIDENCE_DIR / "G0.json", g0)


def validate_review_evidence() -> Check:
    expected = {"external_revalidation.json", "verification.json", "G0.json"}
    actual = {path.name for path in REVIEW_EVIDENCE_DIR.glob("*.json")}
    _require(actual == expected, f"Stage Review evidence set mismatch: {sorted(actual)}")
    verification = _load_json(REVIEW_EVIDENCE_DIR / "verification.json")
    _require(verification.get("status") == "PASS" and verification.get("review_status") == "COMPLETE", "Review verification receipt is not complete/pass")
    _require(verification.get("g0_status") == "BLOCKED_OWNER_ACTION", "Review verification receipt overstated G0")
    _require(verification.get("stage_1_authorized") is False and verification.get("remote_upload") == "FORBIDDEN_UNTIL_G0_PASS", "Review receipt weakened Stage/upload gate")
    _require(verification.get("downstream_product_acceptances") == "NOT_RUN", "Review receipt overstated downstream acceptance")
    redaction = verification.get("redaction", {})
    _require(all(value is False for value in redaction.values()), "Review evidence redaction flags are unsafe")
    worktree_checks = [item for item in verification.get("checks", []) if item.get("name") == "review_worktree_scope"]
    _require(len(worktree_checks) == 1, "Review worktree evidence missing or duplicated")
    details = worktree_checks[0].get("details", {})
    _require(details.get("project_overlap_paths") == 0 and isinstance(details.get("external_main_dirty_paths"), int), "Review worktree isolation evidence invalid")
    _require("external_main_paths" not in details and "external_paths" not in details, "Review evidence leaked external paths")
    g0 = _load_json(REVIEW_EVIDENCE_DIR / "G0.json")
    _require(g0.get("status") == "BLOCKED_OWNER_ACTION" and g0.get("decision") == "FAIL_CLOSED", "G0 receipt is not fail-closed")
    _require(g0.get("blocking_followups", [{}])[0].get("id") == INCIDENT_ID and g0["blocking_followups"][0].get("status") == "owner_action_pending", "G0 receipt lost the Owner action")
    _require(g0.get("stage_1_authorized") is False and g0.get("remote_upload") == "FORBIDDEN_UNTIL_G0_PASS", "G0 receipt authorized Stage/upload")
    return Check("review_evidence_receipts", "PASS", {"files": len(actual), "g0": "BLOCKED_OWNER_ACTION", "stage_1_authorized": False})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--verify-local-root", action="store_true")
    parser.add_argument("--source-roadmap", type=Path)
    parser.add_argument("--source-taskpack", type=Path)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        _require(not args.allow_external_main_dirty or args.verify_worktree, "--allow-external-main-dirty requires --verify-worktree")
        _require(not (args.source_roadmap or args.source_taskpack) or bool(args.source_roadmap and args.source_taskpack), "both original source paths are required")
        if args.write_evidence or args.require_evidence:
            _require(args.verify_worktree and args.verify_local_root, "Review evidence requires worktree and private-root verification")
            _require(bool(args.source_roadmap and args.source_taskpack), "Review evidence requires both original source files")

        checks = run_core_checks()
        local_root: Optional[Path] = None
        if args.verify_local_root:
            root_value = os.environ.get("X2N_DATA_ROOT")
            local_root = Path(root_value) if root_value else Path.home() / "Downloads" / "MediaCrawler" / "xhs-douyin-2notion"
        if args.verify_worktree:
            checks.append(validate_worktree_scope(args.allow_external_main_dirty))
        if args.source_roadmap and args.source_taskpack:
            checks.append(validate_original_sources(args.source_roadmap, args.source_taskpack))
        if local_root is not None and args.source_roadmap and args.source_taskpack:
            checks.append(validate_phase_reacceptance(args.source_roadmap, args.source_taskpack, local_root, args.allow_external_main_dirty))
        if args.write_evidence:
            write_evidence(checks)
            checks.append(validate_review_evidence())
        elif args.require_evidence:
            checks.append(validate_review_evidence())

        gate = _load_json(GATE_STATE)
        g0_pass = gate.get("gate_status") == "pass"
        print(json.dumps({
            "status": "PASS",
            "review_status": "RESUME_COMPLETE" if g0_pass else "COMPLETE",
            "review_id": gate.get("review_id"),
            "checks": [check.__dict__ for check in checks],
            "historical_review_g0_status": "BLOCKED_OWNER_ACTION",
            "g0_status": "PASS" if g0_pass else "BLOCKED_OWNER_ACTION",
            "stage_1_authorized": g0_pass,
            "remote_upload": "AUTHORIZED_AFTER_G0_PASS" if g0_pass else "FORBIDDEN_UNTIL_G0_PASS",
            "product_code": "NOT_STARTED",
            "real_account_execution": "NOT_RUN",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, VerificationError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
