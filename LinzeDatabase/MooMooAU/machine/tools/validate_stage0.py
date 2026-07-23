#!/usr/bin/env python3
"""Fail-closed, read-only Stage 0 verifier for MooMooAU v1.0.1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from validate_evidence import validate_record
from validate_governance import validate as validate_governance
from validate_package import validate as validate_package
from validate_publication import scan_tree


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEVEN_DOCS = [
    "00_我在哪.md",
    "01_产品需求.md",
    "02_系统架构.md",
    "03_口径字典.md",
    "04_操作流程.md",
    "05_执行与验收.md",
    "06_运维手册.md",
]
STAGE_IDS = [f"S{i}" for i in range(8)]
STAGE0_TASKS = [f"T{i:04d}" for i in range(1, 8)]
STAGE0_ACCEPTANCES = [f"S0AC-{i:03d}" for i in range(1, 8)]
AC_FIELDS = {
    "environment",
    "input",
    "oracle",
    "threshold",
    "evidence_required",
    "verification",
    "pass_gate",
    "failure_action",
}
SHARED_GOVERNANCE_TOOL_NAMES = {
    "render_human.py",
    "check_doc_budget.py",
    "check_blocker_stop.py",
    "check_dual_plane_ci.py",
    "install_dual_plane.py",
}
GENERATED_MARKER = "<!-- 本文件由 machine/tools/render_human.py"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(check_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail}


def _validate_public_fixture(path: Path) -> list[str]:
    errors: list[str] = []
    data = _load_json(path)
    required = {
        "schema_version",
        "run_status",
        "freshness_bucket",
        "count_bucket",
        "code_version",
        "parser_versions",
        "opaque_evidence_root",
        "gates",
    }
    allowed = required | {"failure_code"}
    if not required.issubset(data) or set(data) - allowed:
        errors.append("public evidence field contract mismatch")
    if data.get("schema_version") != "1.0.0":
        errors.append("public evidence schema version mismatch")
    if data.get("run_status") not in {"HEALTHY", "DEGRADED", "UNHEALTHY"}:
        errors.append("invalid public run status")
    if data.get("freshness_bucket") not in {"LT_24H", "D1_TO_D7", "GT_7D", "UNKNOWN"}:
        errors.append("invalid public freshness bucket")
    if data.get("count_bucket") not in {"ZERO", "ONE_TO_NINE", "TEN_TO_NINETY_NINE", "HUNDRED_PLUS", "UNKNOWN"}:
        errors.append("invalid public count bucket")
    if not isinstance(data.get("parser_versions"), list):
        errors.append("public parser versions must be an array")
    if re.fullmatch(r"[A-Za-z0-9_-]{16,}", str(data.get("opaque_evidence_root", ""))) is None:
        errors.append("invalid opaque evidence root")
    gates = data.get("gates")
    if not isinstance(gates, dict) or any(
        value not in {"PASS", "FAIL", "DEGRADED", "NOT_RUN"}
        for value in (gates.values() if isinstance(gates, dict) else [])
    ):
        errors.append("invalid public gates")
    return errors


def _acyclic_task_graph(graph: dict[str, Any]) -> tuple[bool, list[str]]:
    task_ids = [task["id"] for task in graph["tasks"]]
    task_set = set(task_ids)
    indegree = {task_id: 0 for task_id in task_ids}
    edges: dict[str, list[str]] = defaultdict(list)
    unknown_dependencies = []
    for task in graph["tasks"]:
        for dependency in task["dependencies"]:
            if dependency not in task_set:
                unknown_dependencies.append(dependency)
                continue
            edges[dependency].append(task["id"])
            indegree[task["id"]] += 1
    queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
    visited = []
    while queue:
        task_id = queue.popleft()
        visited.append(task_id)
        for child in edges[task_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return not unknown_dependencies and len(visited) == len(task_ids), unknown_dependencies


def _current_evidence_paths(root: Path) -> list[Path]:
    return [root / "evidence/tasks" / f"{task_id}.json" for task_id in STAGE0_TASKS] + [
        root / "evidence/stage0/latest.json"
    ]


def evaluate_stage0(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    checks: list[dict[str, str]] = []
    facts = _load_json(root / "machine/facts/canonical_facts.json")
    requirements = _load_json(root / "machine/contracts/requirements.json")["requirements"]
    acceptances = _load_json(root / "machine/contracts/acceptance_contract.json")["acceptance_contracts"]
    stage_acceptances = _load_json(root / "machine/contracts/stage_acceptance_contract.json")["acceptance_contracts"]
    graph = _load_json(root / "machine/contracts/task_graph.json")
    semantic_gate = _load_json(root / "machine/contracts/stage0_semantic_gate.json")
    provenance = _load_json(root / "taskpack/SOURCE_PROVENANCE.json")

    package_result = validate_package(root)
    manifest = _load_json(root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json") if package_result["verified_files"] else {}
    identity_ok = (
        facts["package"]["package_id"]
        == provenance["effective_package"]["package_id"]
        == manifest.get("package_id")
        == "MMAU-ARCHIVE-TP-2026-07-20-V1.0.1"
        and facts["package"]["version"]
        == provenance["effective_package"]["version"]
        == manifest.get("version")
        == "1.0.1"
    )
    checks.append(_check("source.package_identity", identity_ok, "v1.0.1 identity agrees across facts, provenance and manifest"))
    checks.append(
        _check(
            "package.read_only_manifest",
            package_result["status"] == "PASS",
            f"read-only manifest verified {package_result['verified_files']} files with {len(package_result['failures'])} failures",
        )
    )

    retained_failures = []
    for entry in provenance["retained_source_artifacts"]:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"] or _sha256(path) != entry["sha256"]:
            retained_failures.append(entry["path"])
    source_ok = (
        provenance["source_package"]["version"] == "1.0.0"
        and provenance["source_package"]["zip_integrity"] == "PASS"
        and provenance["source_package"]["local_import_commit_publication_allowed"] is False
        and provenance["source_validator_reproduction"]["manifest_preservation"] == "FAIL"
        and not retained_failures
    )
    checks.append(
        _check(
            "source.provenance_integrity",
            source_ok,
            f"verified {len(provenance['retained_source_artifacts'])} retained source artifacts and preserved the source-validator finding",
        )
    )
    symlinks = [path for path in root.rglob("*") if path.is_symlink()]
    checks.append(_check("source.no_symlinks", not symlinks, f"unsafe symlink count {len(symlinks)}"))

    requirement_ids = [item["id"] for item in requirements]
    acceptance_ids = [item["id"] for item in acceptances]
    task_ids = [item["id"] for item in graph["tasks"]]
    stage_ids = [item["id"] for item in graph["stages"]]
    identity_counts_ok = (
        len(requirement_ids) == len(set(requirement_ids)) == 34
        and len(acceptance_ids) == len(set(acceptance_ids)) == 34
        and len(task_ids) == len(set(task_ids)) == 58
        and stage_ids == STAGE_IDS
    )
    checks.append(_check("contracts.identity_and_counts", identity_counts_ok, "34 requirements, 34 final acceptances, 58 tasks and stages S0-S7"))

    acceptance_by_requirement = {item["requirement_id"]: item for item in acceptances}
    final_mapping_ok = (
        len(acceptance_by_requirement) == 34
        and all(
            acceptance_by_requirement.get(item["id"], {}).get("id") == item["acceptance_id"]
            for item in requirements
        )
        and all(
            AC_FIELDS.issubset(item)
            and all(isinstance(item[field], str) and item[field].strip() for field in AC_FIELDS)
            for item in acceptances
        )
    )
    checks.append(_check("contracts.requirement_acceptance_mapping", final_mapping_ok, "one complete final acceptance contract per requirement"))

    stage_acceptance_ids = [item["id"] for item in stage_acceptances]
    stage_task_ids = [item["task_id"] for item in stage_acceptances]
    stage0_tasks = [task for task in graph["tasks"] if task["stage_id"] == "S0"]
    local_mapping_ok = (
        stage_acceptance_ids == STAGE0_ACCEPTANCES
        and stage_task_ids == STAGE0_TASKS
        and [task["id"] for task in stage0_tasks] == STAGE0_TASKS
        and all(task.get("stage_acceptance_ids") == [STAGE0_ACCEPTANCES[index]] for index, task in enumerate(stage0_tasks))
        and all(task.get("acceptance_ids") for task in stage0_tasks)
        and all(set(task["acceptance_ids"]).issubset(set(acceptance_ids)) for task in stage0_tasks)
        and all(task["status"] == "completed" for task in stage0_tasks)
        and all(task["status"] == "planned" for task in graph["tasks"] if task["stage_id"] != "S0")
    )
    checks.append(_check("contracts.stage_local_acceptance", local_mapping_ok, "seven one-to-one S0 gates pass locally while final AC links remain preserved"))

    dag_ok, unknown_dependencies = _acyclic_task_graph(graph)
    child_limits = all(
        len(stage["phases"]) <= 5 and all(len(phase["tasks"]) <= 5 for phase in stage["phases"])
        for stage in graph["stages"]
    )
    checks.append(_check("contracts.task_dag", dag_ok and child_limits, f"acyclic graph; unknown dependencies {len(unknown_dependencies)}; child limits satisfied"))

    with (root / "machine/contracts/traceability_matrix.csv").open(encoding="utf-8", newline="") as stream:
        trace_rows = list(csv.DictReader(stream))
    trace_ok = (
        len(trace_rows) == 34
        and {row["requirement_id"] for row in trace_rows} == set(requirement_ids)
        and {row["acceptance_id"] for row in trace_rows} == set(acceptance_ids)
        and all(row["task_ids"].strip() for row in trace_rows)
    )
    checks.append(_check("contracts.traceability", trace_ok, "all 34 requirement and final acceptance links have task traceability"))

    repositories = facts["repositories"]
    timeline = facts["timeline"]
    invariant_values = [
        repositories["public_project_path"] == "LinzeDatabase/MooMooAU",
        repositories["private_repository_count"] == 1,
        repositories["private_repository_identity"] == "immutable Repository ID from protected configuration",
        repositories["private_repository_name_in_public_tree"] is False,
        facts["schedule"]["cron"] == "30 4 * * *",
        facts["schedule"]["timezone"] == "Australia/Sydney",
        facts["schedule"]["local_time_target"] == "04:30",
        facts["schedule"]["exact_start_guaranteed"] is False,
        facts["gmail"]["allowed_mutation"] == "users.messages.trash only",
        facts["gmail"]["permanent_delete"] is False,
        facts["gmail"]["thread_trash"] is False,
        timeline["count"] == 1,
        timeline["count_semantics"] == "healthy steady state",
        timeline["maximum_asset_count"] == 1,
        timeline["failure_state_asset_count"] == 0,
        timeline["atomic_replace"] is False,
        timeline["history_images"] is False,
        facts["runtime"]["local_runtime"] is False,
        facts["runtime"]["self_hosted_server"] is False,
        facts["runtime"]["plaintext_persistence"] is False,
        facts["runtime"]["actions_cache"] is False,
        facts["keys"]["live_key_in_package"] is False,
        facts["data"]["portal_h2"] is False,
    ]
    checks.append(_check("invariants.frozen_values", all(invariant_values), f"verified {len(invariant_values)} frozen invariant values"))

    timeline_protocol = _load_json(root / "machine/contracts/timeline_publish_protocol.json")
    platform = _load_json(root / "research/platform_capabilities.v1.0.1.json")
    schedule_capability = platform["workflow_schedule"]
    schedule_ok = (
        schedule_capability["timezone_aware_schedule_supported"] is True
        and schedule_capability["iana_timezone"] == "Australia/Sydney"
        and schedule_capability["cron"] == "30 4 * * *"
        and schedule_capability["dst_aware"] is True
        and schedule_capability["delay_possible"] is True
        and schedule_capability["drop_possible"] is True
        and schedule_capability["exact_execution_start_guaranteed"] is False
        and facts["schedule"]["missed_trigger_recovery"]
        == "next invocation idempotent catch-up plus Sunday full reconciliation"
    )
    checks.append(_check("invariants.schedule_platform_semantics", schedule_ok, "timezone-aware 04:30 target and provider delay/drop recovery are explicit without an exact-start claim"))

    age_capability = platform["age_encryption"]
    timeline_ok = (
        timeline_protocol["healthy_asset_count"] == 1
        and timeline_protocol["maximum_asset_count"] == 1
        and timeline_protocol["repair_asset_count"] == 0
        and timeline_protocol["history_asset_count"] == 0
        and timeline_protocol["atomic_replace_required"] is False
        and timeline_protocol["ciphertext_deterministic"] is False
        and timeline_protocol["semantic_idempotency_key"]
        == ["processed_snapshot_root", "timeline_plaintext_sha256"]
        and platform["release_assets"]["same_filename_upload_response"] == 422
        and platform["release_assets"]["delete_success_response"] == 204
        and platform["release_assets"]["atomic_replace_operation"] is False
        and age_capability["file_key_from_csprng"] is True
        and age_capability["payload_nonce_from_csprng"] is True
        and age_capability["x25519_ephemeral_secret_per_file"] is True
        and age_capability["deterministic_ciphertext"] is False
        and timeline_protocol["platform_evidence_ref"] == "research/platform_capabilities.v1.0.1.json"
    )
    checks.append(_check("invariants.timeline_platform_protocol", timeline_ok, "serial maximum-one replacement, plaintext idempotency and zero-asset repair match pinned Release and age evidence"))

    publication_result = scan_tree(root)
    checks.append(
        _check(
            "security.publication_safety",
            publication_result["status"] == "PASS",
            f"scanned {publication_result['files_scanned']} files with {publication_result['total_matches']} forbidden matches",
        )
    )
    fixture_errors = _validate_public_fixture(root / "tests/fixtures/stage0/public_evidence_synthetic.json")
    checks.append(_check("baseline.synthetic_redacted_fixture", not fixture_errors, f"synthetic public fixture errors {len(fixture_errors)}"))

    metrics = _load_json(root / "machine/facts/metrics.json")["metrics"]
    kill_criteria = _load_json(root / "machine/contracts/kill_criteria.json")["kill_criteria"]
    metrics_ok = (
        len(metrics) == 12
        and len({item["id"] for item in metrics}) == 12
        and all(set(item) == {"id", "name", "baseline", "target", "measure", "window"} for item in metrics)
        and all(all(isinstance(value, str) and value.strip() for value in item.values()) for item in metrics)
    )
    kills_ok = (
        len(kill_criteria) == 10
        and len({item["id"] for item in kill_criteria}) == 10
        and all(set(item) == {"id", "condition", "action", "resume_gate"} for item in kill_criteria)
        and all(all(isinstance(value, str) and value.strip() for value in item.values()) for item in kill_criteria)
    )
    checks.append(
        _check(
            "baseline.cost_and_kill",
            metrics_ok and kills_ok and (root / "prd/COST_BENEFIT_AND_KILL.md").is_file(),
            "12 complete metrics, 10 complete kill criteria and cost-benefit baseline",
        )
    )
    setup_text = (root / "implementation/ONE_TIME_SETUP.md").read_text(encoding="utf-8")
    setup_sections = ["Google OAuth", "GitHub App", "age", "Moomoo PDF Password", "仓库设置"]
    checks.append(_check("baseline.one_time_setup", all(section in setup_text for section in setup_sections), "all five protected one-time setup domains are documented only"))

    docs = [root / "文档" / name for name in SEVEN_DOCS]
    copied_tools = [name for name in SHARED_GOVERNANCE_TOOL_NAMES if (root / "machine/tools" / name).exists()]
    checks.append(_check("governance.no_framework_copy", not copied_tools, f"copied shared tool count {len(copied_tools)}"))
    docs_ok = all(path.is_file() and GENERATED_MARKER in path.read_text(encoding="utf-8") for path in docs)
    checks.append(_check("governance.seven_files_generated", docs_ok, f"generated seven-file count {sum(path.is_file() and GENERATED_MARKER in path.read_text(encoding='utf-8') for path in docs)}"))

    if governance_root is None and os.environ.get("MOOMOOAU_GOVERNANCE_ROOT"):
        governance_root = Path(os.environ["MOOMOOAU_GOVERNANCE_ROOT"])
    if governance_root is None:
        governance_result = {"status": "FAIL", "failures": ["external Governance checkout not configured"]}
    else:
        governance_result = validate_governance(root, governance_root, render=False)
    checks.append(
        _check(
            "governance.external_determinism",
            governance_result["status"] == "PASS",
            f"pinned external render and shared gates produced {len(governance_result.get('failures', []))} failures",
        )
    )

    evidence_paths = _current_evidence_paths(root)
    evidence_errors = {
        path.relative_to(root).as_posix(): validate_record(path, root)
        for path in evidence_paths
        if path.is_file()
    }
    missing_evidence = [path for path in evidence_paths if not path.is_file()]
    evidence_ok = not missing_evidence and len(evidence_errors) == 8 and all(not errors for errors in evidence_errors.values())
    checks.append(_check("evidence.current_records", evidence_ok, f"current records valid {sum(not errors for errors in evidence_errors.values())}/8; missing {len(missing_evidence)}"))

    open_issues = [issue["id"] for issue in semantic_gate["blocking_issues"] if issue["status"] != "RESOLVED"]
    semantic_ok = (
        semantic_gate["baseline_version"] == "1.0.1"
        and semantic_gate["current_status"] == "PASS"
        and semantic_gate["baseline_repair_authorized"] is True
        and not open_issues
        and semantic_gate["nonblocking_unknowns"][0]["status"] == "CONTROLLED_UNKNOWN"
    )
    checks.append(_check("semantic.resolutions_and_authority", semantic_ok, f"unresolved semantic issues {len(open_issues)}; controlled unknowns retained"))

    repository_root = root.parents[1]
    workflow_dir = repository_root / ".github/workflows"
    stage_workflows = list(workflow_dir.glob("*moomoo*")) if workflow_dir.is_dir() else []
    runtime_entries = [root / name for name in ("src", "pyproject.toml", "Dockerfile") if (root / name).exists()]
    scope_ok = not stage_workflows and not runtime_entries
    checks.append(_check("scope.no_stage1_or_deployment", scope_ok, f"MooMooAU workflows {len(stage_workflows)}; runtime entries {len(runtime_entries)}"))

    failed_check_ids = [check["id"] for check in checks if check["status"] != "PASS"]
    verifier_status = "PASS" if not failed_check_ids else "FAIL"
    stage_status = "PASS" if verifier_status == "PASS" else "BLOCKED"
    return {
        "schema_version": "moomooau.stage0-verification.v2",
        "package_version": "1.0.1",
        "verifier_status": verifier_status,
        "stage_status": stage_status,
        "checks": checks,
        "signals": {
            "requirements": len(requirement_ids),
            "final_acceptances": len(acceptance_ids),
            "tasks": len(task_ids),
            "stage0_tasks": len(stage0_tasks),
            "stage0_acceptances": len(stage_acceptances),
            "current_evidence_records": len(evidence_errors),
            "publication_matches": publication_result["total_matches"],
            "governance_failures": len(governance_result.get("failures", [])),
            "remote_writes": 0,
            "deployment_actions": 0,
            "gmail_calls": 0,
            "secrets_read": 0,
        },
        "failed_check_ids": failed_check_ids,
        "blocking_issue_ids": open_issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--governance-root",
        type=Path,
        default=Path(os.environ["MOOMOOAU_GOVERNANCE_ROOT"]) if os.environ.get("MOOMOOAU_GOVERNANCE_ROOT") else None,
    )
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    result = evaluate_stage0(args.root, args.governance_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["verifier_status"] != "PASS":
        return 1
    if args.require_pass and result["stage_status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
