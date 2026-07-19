from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .customer_faq import evaluate_contract as evaluate_p02
from .customer_press_release import evaluate_contract as evaluate_p01
from .delivery import verify_stage0_delivery
from .metrics_economics import evaluate_contract as evaluate_p04
from .requirements_scope import evaluate_contract as evaluate_p03


CONTRACT_ID = "STAGE-REVIEW-S01"
REVIEW_ID = "ABD-S01-WHOLE-STAGE-REVIEW"
STAGE_ID = "S01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage1_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S01/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S01_STAGE_REVIEW.json")
JUNIT_PATH = Path("machine/evidence/S01/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S01/STAGE_REVIEW/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S01-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S01-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

PROJECT_PINNED_PATHS = {
    CONTRACT_PATH.as_posix(): "c5a6c977bdec169f780555420d80cf382258a3a7531899f1df986fb1c6d20d56",
    FINDINGS_PATH.as_posix(): "845af70562b7da6885cb2bb93a9799b2c8e958d34d21c2b5b609b044c1e14d2a",
    FIXTURE_PATH.as_posix(): "65a041ed3fba5f0e5f6a2fa00c407c6dbe32f2dfee00b08c800bde0552a30ad6",
}
REPO_PINNED_PATHS = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}
PHASE_EVALUATORS = {
    "P01": evaluate_p01,
    "P02": evaluate_p02,
    "P03": evaluate_p03,
    "P04": evaluate_p04,
}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _repo_path(relative: str) -> str:
    return relative if relative.startswith(".github/") else "ABD/%s" % relative


def _blob_hash_at_commit(repo_root: Path, commit: str, relative: str) -> str:
    result = _git(repo_root, "show", "%s:%s" % (commit, _repo_path(relative)))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return _sha256_bytes(result.stdout)


def _code_hash_at_commit(repo_root: Path, commit: str) -> str:
    listing = _git(repo_root, "ls-tree", "-r", "--name-only", commit, "--", "ABD/abd_acceptance")
    if listing.returncode != 0:
        raise RuntimeError(listing.stderr.decode("utf-8", errors="replace").strip())
    paths = sorted(path for path in listing.stdout.decode("utf-8").splitlines() if path.endswith(".py"))
    if not paths:
        raise RuntimeError("no acceptance code found at commit")
    digest = hashlib.sha256()
    for repo_path in paths:
        payload = _git(repo_root, "show", "%s:%s" % (commit, repo_path))
        if payload.returncode != 0:
            raise RuntimeError(payload.stderr.decode("utf-8", errors="replace").strip())
        project_path = repo_path.removeprefix("ABD/")
        digest.update(project_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("decision_sha256")
    unsigned = deepcopy(dict(evidence))
    unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and _sha256_bytes(_json_bytes(unsigned)) == expected


def _load_evidence_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
        if line
    ]


def _check_pinned_review_artifacts(
    root: Path,
    repo_root: Path,
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    for relative, expected in PROJECT_PINNED_PATHS.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S01REVIEW-PIN-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in REPO_PINNED_PATHS.items():
        path = repo_root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S01REVIEW-PIN-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_contract_shape(
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    authorization: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    scope = contract.get("review_scope", {})
    records = contract.get("phase_records", [])
    scope_ok = (
        contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and contract.get("fixed_at") == FIXED_CLOCK
        and scope.get("phase_ids") == fixture.get("expected_phase_ids")
        and scope.get("requirement_ids") == fixture.get("expected_requirement_ids")
        and scope.get("acceptance_contract_ids") == fixture.get("expected_acceptance_contract_ids")
        and scope.get("task_ids") == fixture.get("expected_task_ids")
        and [row.get("phase_id") for row in records if isinstance(row, dict)] == fixture.get("expected_phase_ids")
    )
    _add(checks, "S01REVIEW-CONTRACT-SCOPE-EXACT", scope_ok, scope)

    receipts = {row.get("artifact_label"): row for row in contract.get("supplied_source_receipts", []) if isinstance(row, dict)}
    roadmap = receipts.get("ABD_Roadmap_Stage_Phase_v0.0.0.1.md", {})
    taskpack = receipts.get("ABD_ProductDesign_TaskPack_v0.0.0.1_FINAL.zip", {})
    receipts_ok = (
        len(receipts) == 2
        and roadmap.get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and roadmap.get("repository_equivalent") == "machine/evidence/roadmap_stage_phase.md"
        and taskpack.get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and taskpack.get("original_file_count") == 53
        and taskpack.get("repository_equivalent") is None
    )
    _add(checks, "S01REVIEW-SUPPLIED-SOURCE-RECEIPTS", receipts_ok, receipts)

    upload_rows = [
        row for row in authorization.get("actions", [])
        if isinstance(row, dict) and row.get("id") == "GITHUB_STAGE_UPLOAD"
    ]
    upload = upload_rows[0] if len(upload_rows) == 1 else {}
    expected_preconditions = fixture.get("required_upload_preconditions")
    upload_ok = (
        len(upload_rows) == 1
        and upload.get("authorization") == "CONDITIONALLY_PREAUTHORIZED"
        and upload.get("effect") == "WRITE_EXTERNAL_REVERSIBLE"
        and upload.get("cash_cost_aud") == "0.00"
        and upload.get("preconditions") == expected_preconditions
        and contract.get("upload_preconditions") == expected_preconditions
        and upload.get("on_precondition_failure") == "KEEP_COMMITS_LOCAL_CONTINUE_STAGE_REMEDIATION"
    )
    _add(checks, "S01REVIEW-GITHUB-UPLOAD-AUTHORIZATION-ALIGNED", upload_ok, upload)

    boundary = contract.get("external_effect_boundary", {})
    boundary_ok = (
        bool(boundary)
        and all(value is False for value in boundary.values())
        and contract.get("next_on_local_review_pass") == "S01/GITHUB_STAGE_UPLOAD_READY"
        and contract.get("next_after_verified_remote_upload") == "S02/P01_READY_NOT_STARTED"
    )
    _add(checks, "S01REVIEW-LOCAL-EXTERNAL-EFFECT-BOUNDARY", boundary_ok, boundary)


def _check_baseline_hashes(
    root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    expected = contract.get("baseline_critical_artifacts", {})
    errors = []
    if not isinstance(expected, dict) or len(expected) != 21:
        errors.append("expected exactly 21 critical S01 artifacts")
        expected = expected if isinstance(expected, dict) else {}
    for relative, wanted in expected.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        if actual != wanted:
            errors.append({"path": relative, "expected": wanted, "actual": actual})
    _add(checks, "S01REVIEW-BASELINE-CRITICAL-HASHES", not errors, errors or sorted(expected))


def _check_stage_trace(
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    roadmap: Mapping[str, Any],
    requirements: Sequence[Any],
    acceptance: Sequence[Any],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Any],
    checks: List[Dict[str, Any]],
) -> None:
    stages = [row for row in roadmap.get("stages", []) if isinstance(row, dict) and row.get("id") == STAGE_ID]
    stage = stages[0] if len(stages) == 1 else {}
    phase_rows = stage.get("phases", []) if isinstance(stage, dict) else []
    stage_ok = (
        len(stages) == 1
        and [row.get("id") for row in phase_rows] == fixture.get("expected_phase_ids")
        and stage.get("depends_on") == ["S00"]
        and stage.get("stop_conditions") == contract.get("stage_stop_conditions")
    )
    _add(checks, "S01REVIEW-ROADMAP-STAGE-EXACT", stage_ok, stage)

    req_rows = [row for row in requirements if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    ac_rows = [row for row in acceptance if isinstance(row, dict) and str(row.get("id", "")).startswith("AC-S01-")]
    tasks = [row for row in task_graph.get("tasks", []) if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    traces = [row for row in traceability if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    sets_ok = (
        [row.get("id") for row in req_rows] == fixture.get("expected_requirement_ids")
        and [row.get("id") for row in ac_rows] == fixture.get("expected_acceptance_contract_ids")
        and [row.get("id") for row in tasks] == fixture.get("expected_task_ids")
        and [row.get("requirement_id") for row in traces] == fixture.get("expected_requirement_ids")
    )
    _add(checks, "S01REVIEW-REQ-AC-TASK-TRACE-SETS-EXACT", sets_ok, {"requirements": len(req_rows), "acceptance": len(ac_rows), "tasks": len(tasks), "traces": len(traces)})

    phase_by_id = {row.get("id"): row for row in phase_rows}
    req_by_id = {row.get("id"): row for row in req_rows}
    ac_by_id = {row.get("id"): row for row in ac_rows}
    trace_by_req = {row.get("requirement_id"): row for row in traces}
    semantic_errors = []
    for record in contract.get("phase_records", []):
        phase = phase_by_id.get(record.get("phase_id"), {})
        requirement = req_by_id.get(record.get("requirement_id"), {})
        ac = ac_by_id.get(record.get("acceptance_contract_id"), {})
        trace = trace_by_req.get(record.get("requirement_id"), {})
        if requirement.get("primary_acceptance_criteria_id") != record.get("acceptance_contract_id"):
            semantic_errors.append({"phase": record.get("phase_id"), "route": "requirement_to_acceptance"})
        if requirement.get("target") != phase.get("pass_gate"):
            semantic_errors.append({"phase": record.get("phase_id"), "route": "requirement_to_phase"})
        if ac.get("requirement_id") != record.get("requirement_id") or ac.get("pass_gate") != phase.get("pass_gate"):
            semantic_errors.append({"phase": record.get("phase_id"), "route": "acceptance_semantics"})
        if ac.get("oracle", {}).get("type") != "EXECUTABLE" or ac.get("oracle", {}).get("rule") != phase.get("pass_gate"):
            semantic_errors.append({"phase": record.get("phase_id"), "route": "executable_oracle"})
        if trace.get("task_ids") != record.get("task_ids") or trace.get("acceptance_criteria_id") != record.get("acceptance_contract_id"):
            semantic_errors.append({"phase": record.get("phase_id"), "route": "traceability"})
    _add(checks, "S01REVIEW-SEMANTIC-TRACE-EXACT", not semantic_errors, semantic_errors or "all aligned")

    task_errors = []
    tasks_by_id = {row.get("id"): row for row in tasks}
    expected_ids = fixture.get("expected_task_ids", [])
    for index, task_id in enumerate(expected_ids):
        expected_dep = ["T-S00-P04-03"] if index == 0 else [expected_ids[index - 1]]
        task = tasks_by_id.get(task_id, {})
        if task.get("depends_on") != expected_dep:
            task_errors.append({"task": task_id, "expected": expected_dep, "actual": task.get("depends_on")})
        if task.get("owner_input_required") is not False or task.get("auto_advance_on_pass") is not True:
            task_errors.append({"task": task_id, "reason": "owner_or_auto_advance"})
    _add(checks, "S01REVIEW-TASK-CHAIN-EXACT", not task_errors, task_errors or {"tasks": len(expected_ids)})


def _safe_phase_boundary(evidence: Mapping[str, Any]) -> bool:
    boundary = evidence.get("external_effect_boundary", {})
    if not isinstance(boundary, dict) or boundary.get("incremental_cash_spent_aud") != "0.00":
        return False
    forbidden_true_tokens = (
        "github_upload", "external_account", "secret_provisioned", "production", "all_market_coverage",
        "gmail_connected", "real_order", "return_or_guarantee", "actual_return", "stage_review_started",
    )
    return not any(value is True and any(token in key for token in forbidden_true_tokens) for key, value in boundary.items())


def _check_phase_evidence_and_history(
    root: Path,
    repo_root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    *,
    verify_history: bool,
) -> None:
    try:
        index_rows = _load_evidence_index(root)
    except Exception as exc:
        index_rows = []
        index_error = "%s: %s" % (type(exc).__name__, exc)
    else:
        index_error = None
    evidence_errors = [index_error] if index_error else []
    history_errors = []
    output_errors = []
    commits = []

    for record in contract.get("phase_records", []):
        phase_id = str(record.get("phase_id"))
        evidence_path = root / str(record.get("evidence_path", ""))
        rollback_path = root / str(record.get("rollback_path", ""))
        evidence_hash = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_hash = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        hashes[str(record.get("evidence_path"))] = evidence_hash
        hashes[str(record.get("rollback_path"))] = rollback_hash
        if evidence_hash != record.get("evidence_sha256") or rollback_hash != record.get("rollback_sha256"):
            evidence_errors.append({"phase": phase_id, "reason": "receipt_hash", "evidence": evidence_hash, "rollback": rollback_hash})
        try:
            evidence = strict_json_load(evidence_path)
            rollback = strict_json_load(rollback_path)
        except Exception as exc:
            evidence_errors.append({"phase": phase_id, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        if not isinstance(evidence, dict) or not isinstance(rollback, dict):
            evidence_errors.append({"phase": phase_id, "reason": "non_object_receipt"})
            continue
        semantic_ok = (
            evidence.get("status") == "PASS"
            and evidence.get("contract_id") == record.get("acceptance_contract_id")
            and evidence.get("requirement_id") == record.get("requirement_id")
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == phase_id
            and evidence.get("next") == record.get("expected_next")
            and evidence.get("release_status") == record.get("expected_release_status")
            and evidence.get("validation", {}).get("status") == "PASS"
            and evidence.get("hashes", {}).get("code") == record.get("implementation_code_sha256")
            and evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash
            and _decision_hash_matches(evidence)
            and _safe_phase_boundary(evidence)
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
        )
        if not semantic_ok:
            evidence_errors.append({"phase": phase_id, "reason": "semantic_receipt_gate"})
        matching = [row for row in index_rows if row.get("id") == "INDEX-AC-S01-%s" % phase_id]
        if len(matching) != 1 or matching[0].get("status") != "PASS" or matching[0].get("artifact_sha256") != evidence_hash:
            evidence_errors.append({"phase": phase_id, "reason": "index_binding"})

        input_hashes = evidence.get("hashes", {}).get("inputs", {})
        for relative in record.get("required_outputs", []):
            path = root / relative
            if not path.is_file():
                output_errors.append({"phase": phase_id, "missing": relative})
            elif relative in input_hashes and sha256_file(path) != input_hashes[relative]:
                output_errors.append({"phase": phase_id, "drift": relative})

        if verify_history:
            commit = str(record.get("implementation_commit", ""))
            commits.append(commit)
            if _git(repo_root, "cat-file", "-e", "%s^{commit}" % commit).returncode != 0 or _git(repo_root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
                history_errors.append({"phase": phase_id, "reason": "commit_missing_or_not_ancestor", "commit": commit})
                continue
            try:
                actual_code_hash = _code_hash_at_commit(repo_root, commit)
            except Exception as exc:
                history_errors.append({"phase": phase_id, "reason": "code_hash_error", "detail": str(exc)})
            else:
                if actual_code_hash != record.get("implementation_code_sha256"):
                    history_errors.append({"phase": phase_id, "reason": "code_hash", "actual": actual_code_hash})
            allowed = record.get("allowed_commit_paths", [])
            changed = _git(repo_root, "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", commit)
            changed_paths = [path.decode("utf-8") for path in changed.stdout.split(b"\0") if path] if changed.returncode == 0 else []
            escaped = [path for path in changed_paths if not any(path == prefix or path.startswith(prefix) for prefix in allowed)]
            if not changed_paths or escaped:
                history_errors.append({"phase": phase_id, "reason": "commit_scope", "escaped": escaped})
            for relative, wanted in input_hashes.items():
                try:
                    actual = _blob_hash_at_commit(repo_root, commit, relative)
                except Exception as exc:
                    history_errors.append({"phase": phase_id, "input": relative, "reason": str(exc)})
                    continue
                if actual != wanted:
                    history_errors.append({"phase": phase_id, "input": relative, "expected": wanted, "actual": actual})

    if verify_history:
        for previous, current in zip(commits, commits[1:]):
            if _git(repo_root, "merge-base", "--is-ancestor", previous, current).returncode != 0:
                history_errors.append({"reason": "commit_order", "previous": previous, "current": current})
    _add(checks, "S01REVIEW-PHASE-EVIDENCE-ROLLBACK-INDEX", not evidence_errors, evidence_errors or {"phases": 4})
    _add(checks, "S01REVIEW-PHASE-REQUIRED-OUTPUTS", not output_errors, output_errors or {"outputs": 10})
    if verify_history:
        _add(checks, "S01REVIEW-HISTORICAL-CODE-AND-INPUT-HASHES", not history_errors, history_errors or commits)


def _check_phase_oracles(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    summaries = {}
    errors = []
    minimums = fixture.get("expected_phase_evaluator_min_checks", {})
    for phase_id in fixture.get("expected_phase_ids", []):
        evaluator = PHASE_EVALUATORS.get(phase_id)
        if evaluator is None:
            errors.append({"phase": phase_id, "reason": "missing_evaluator"})
            continue
        try:
            if phase_id == "P04":
                result = evaluator(root, require_external_reports=True, _allow_stage_review_candidate=True)
            else:
                result = evaluator(root, require_external_reports=True)
        except Exception as exc:
            errors.append({"phase": phase_id, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        summary = result.get("summary", {})
        summaries[phase_id] = {"status": result.get("status"), "checks": summary.get("checks"), "failed": summary.get("failed"), "next": result.get("next")}
        if result.get("status") != "PASS" or summary.get("failed") != 0 or int(summary.get("checks", 0)) < int(minimums.get(phase_id, 0)):
            errors.append({"phase": phase_id, "summary": summaries[phase_id]})
    _add(checks, "S01REVIEW-ALL-PHASE-ORACLES-PASS", not errors, errors or summaries)


def _check_product_metric_economic_trace(
    root: Path,
    fixture: Mapping[str, Any],
    product_requirements: Mapping[str, Any],
    metrics: Mapping[str, Any],
    economics: Mapping[str, Any],
    kills: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    requirement_ids = [row.get("id") for row in product_requirements.get("requirements", []) if isinstance(row, dict)]
    metric_rows = metrics.get("metrics", [])
    metric_ids = [row.get("id") for row in metric_rows if isinstance(row, dict)]
    kill_rows = kills.get("criteria", [])
    kill_ids = [row.get("id") for row in kill_rows if isinstance(row, dict)]
    ids_ok = (
        requirement_ids == fixture.get("expected_product_requirement_ids")
        and metric_ids == fixture.get("expected_metric_ids")
        and kill_ids == fixture.get("expected_kill_criterion_ids")
        and len(set(requirement_ids)) == 21
        and len(set(metric_ids)) == 31
        and len(set(kill_ids)) == 19
    )
    _add(checks, "S01REVIEW-PRODUCT-METRIC-KILL-ID-SETS-EXACT", ids_ok, {"requirements": len(requirement_ids), "metrics": len(metric_ids), "kills": len(kill_ids)})

    required = set(requirement_ids)
    covered = {requirement_id for row in metric_rows if isinstance(row, dict) for requirement_id in row.get("requirement_ids", [])}
    coverage_ok = covered == required and metrics.get("traceability_summary", {}).get("metric_count") == 31
    _add(checks, "S01REVIEW-ALL-21-REQUIREMENTS-MEASURED-EXACT", coverage_ok, {"required": sorted(required), "covered": sorted(covered)})

    metric_set = set(metric_ids)
    benefits = economics.get("benefit_envelope", {}).get("non_cash_benefits", [])
    benefits_ok = (
        len(benefits) == 5
        and all(bool(row.get("measurement_metric_ids")) for row in benefits if isinstance(row, dict))
        and all(set(row.get("measurement_metric_ids", [])).issubset(metric_set) for row in benefits if isinstance(row, dict))
    )
    _add(checks, "S01REVIEW-ALL-NONCASH-BENEFITS-MEASURED", benefits_ok, benefits)

    metric_by_id = {row.get("id"): row for row in metric_rows if isinstance(row, dict)}
    kill_by_id = {row.get("id"): row for row in kill_rows if isinstance(row, dict)}
    new_gate_ok = (
        metric_by_id.get("MET-S01-P04-028", {}).get("requirement_ids") == ["ABD-PRD-REQ-008"]
        and metric_by_id.get("MET-S01-P04-029", {}).get("requirement_ids") == ["ABD-PRD-REQ-009"]
        and metric_by_id.get("MET-S01-P04-030", {}).get("requirement_ids") == ["ABD-PRD-REQ-019"]
        and metric_by_id.get("MET-S01-P04-031", {}).get("requirement_ids") == ["ABD-PRD-REQ-020"]
        and kill_by_id.get("KC-S01-P04-003", {}).get("metric_ids") == ["MET-S01-P04-030"]
        and kill_by_id.get("KC-S01-P04-018", {}).get("metric_ids") == ["MET-S01-P04-028", "MET-S01-P04-029"]
        and kill_by_id.get("KC-S01-P04-019", {}).get("metric_ids") == ["MET-S01-P04-031"]
    )
    _add(checks, "S01REVIEW-GMAIL-PRIVACY-PIPELINE-GATES-EXACT", new_gate_ok, sorted(metric_by_id)[-4:])

    binding_errors = []
    for label, artifact in [("metrics", metrics), ("economics", economics), ("kills", kills)]:
        bindings = artifact.get("source_bindings", {})
        if not isinstance(bindings, dict) or not bindings:
            binding_errors.append({"artifact": label, "reason": "missing_bindings"})
            continue
        for relative, wanted in bindings.items():
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != wanted:
                binding_errors.append({"artifact": label, "path": relative, "expected": wanted, "actual": actual})
    _add(checks, "S01REVIEW-CROSS-ARTIFACT-SOURCE-BINDINGS", not binding_errors, binding_errors or "all source hashes resolve")


def _check_truth_safety_boundaries(
    outcomes: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    scope: Mapping[str, Any],
    metrics: Mapping[str, Any],
    economics: Mapping[str, Any],
    kills: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    experience = outcomes.get("experience_contract", {})
    outcome_claims = outcomes.get("claim_boundaries", {})
    assumptions_by_id = {row.get("id"): row for row in assumptions.get("assumptions", []) if isinstance(row, dict)}
    working_backwards_ok = (
        experience.get("final_order_actor") == "OWNER"
        and experience.get("automatic_order_submission_count") == 0
        and experience.get("missing_or_unstable_evidence_action") == "NO_RECOMMENDATION"
        and outcome_claims.get("gmail_connection_status") == "NOT_CONNECTED"
        and outcome_claims.get("actual_return_verified") is False
        and outcome_claims.get("return_guaranteed") is False
        and outcome_claims.get("release_status") == "NOT_READY"
        and assumptions_by_id.get("ASM-S01-P02-01", {}).get("safe_default") == "REPORT_SHORTFALL_NO_GATE_RELAXATION"
        and assumptions_by_id.get("ASM-S01-P02-03", {}).get("safe_default") == "BLOCK_POSITIVE_OR_UNKNOWN_INCREMENTAL_COST"
        and assumptions_by_id.get("ASM-S01-P02-05", {}).get("safe_default") == "DISABLE_GMAIL_KEEP_OR_QUARANTINE_MESSAGE_CONTINUE_SAFE_CORE"
    )
    _add(checks, "S01REVIEW-WORKING-BACKWARDS-BOUNDARIES-ALIGNED", working_backwards_ok, {"experience": experience, "claims": outcome_claims})

    invariant_ids = [row.get("id") for row in scope.get("hard_invariants", []) if isinstance(row, dict)]
    out_ids = [row.get("id") for row in scope.get("explicit_out_of_scope", []) if isinstance(row, dict)]
    conditional = {row.get("id"): row for row in scope.get("conditional_capabilities", []) if isinstance(row, dict)}
    scope_ok = (
        invariant_ids == ["BOUNDARY-INV-%03d" % index for index in range(1, 11)]
        and out_ids == ["OUT-%03d" % index for index in range(1, 9)]
        and conditional.get("COND-003", {}).get("current_status") == "NOT_CONNECTED_NOT_READY"
        and conditional.get("COND-006", {}).get("current_status") == "UNVERIFIED"
        and scope.get("s01_p03_execution_boundary", {}).get("real_order_capability_present") is False
        and scope.get("s01_p03_execution_boundary", {}).get("incremental_cash_spent_aud") == "0.00"
    )
    _add(checks, "S01REVIEW-SCOPE-HARD-BOUNDARIES-ALIGNED", scope_ok, {"invariants": invariant_ids, "out_of_scope": out_ids})

    metric_semantics = metrics.get("metric_semantics", {})
    target = economics.get("target_curve_contract", {})
    roi = economics.get("roi_contract", {})
    kill_semantics = kills.get("evaluation_semantics", {})
    truth_ok = (
        metric_semantics.get("missing_or_null_baseline") == "UNMEASURED_NOT_PASS"
        and metric_semantics.get("target_shortfall_may_relax_gate") is False
        and metric_semantics.get("return_guaranteed") is False
        and economics.get("economic_semantics", {}).get("total_system_cost_is_zero") is False
        and economics.get("cost_envelope", {}).get("current_phase_incremental_cash_spent_aud") == "0.00"
        and target.get("current_status") == "UNVERIFIED_FALSIFIABLE_TARGET"
        and target.get("is_guarantee") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and roi.get("roi") is None
        and roi.get("unknown_default") == "DO_NOT_REPORT_ROI"
        and kill_semantics.get("current_trigger_evaluation_performed") is False
        and kill_semantics.get("missing_or_incomplete_evidence_is_pass") is False
        and kill_semantics.get("target_shortfall_may_relax_any_gate") is False
        and kills.get("current_evaluation", {}).get("release_effect") == "NO_RELEASE_AUTHORIZATION"
    )
    _add(checks, "S01REVIEW-NO-FABRICATED-COST-ROI-OR-RETURN", truth_ok, {"target": target, "roi": roi, "kill": kills.get("current_evaluation")})

    phase_boundaries = [
        metrics.get("s01_p04_execution_boundary", {}),
        economics.get("s01_p04_execution_boundary", {}),
        kills.get("s01_p04_execution_boundary", {}),
    ]
    boundaries_ok = all(boundary.get("incremental_cash_spent_aud") == "0.00" for boundary in phase_boundaries) and not any(
        value is True for boundary in phase_boundaries for key, value in boundary.items()
        if any(token in key for token in ["evaluated", "verified", "accessed", "deployed", "submitted", "claimed", "started"])
    )
    _add(checks, "S01REVIEW-P04-NO-RUNTIME-EXTERNAL-OR-RETURN-EFFECT", boundaries_ok, phase_boundaries)


def _workflow_action_refs(text: str) -> List[str]:
    return re.findall(r"^\s*-\s+uses:\s+[^@\s]+@([^\s#]+)", text, flags=re.MULTILINE)


def _check_workflow_and_review_replay(
    root: Path,
    repo_root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        text = (repo_root / WORKFLOW_PATH).read_text(encoding="utf-8")
        main_text = (root / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S01REVIEW-CI-WORKFLOW-AVAILABLE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    integration = contract.get("repository_integration", {})
    expected_refs = set(integration.get("pinned_actions", {}).values())
    refs = _workflow_action_refs(text)
    pins_ok = (
        len(refs) == 3
        and set(refs) == expected_refs
        and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)
        and 'version: "0.11.28"' in text
        and 'python-version: "3.12"' in text
        and "fetch-depth: 0" in text
    )
    _add(checks, "S01REVIEW-CI-SUPPLY-CHAIN-PINS", pins_ok, refs)

    missing = [command for command in fixture.get("required_workflow_commands", []) if command not in text]
    workflow_ok = (
        not missing
        and "runs-on: ubuntu-latest" in text
        and "timeout-minutes: 15" in text
        and "permissions:\n  contents: read" in text
        and "pull_request:" in text
        and ("$" + "{{ secrets.") not in text
        and "REMOTE_CI_PASS" not in text
    )
    _add(checks, "S01REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED", workflow_ok, missing or "all required commands present")

    writer_registration_present = bool(
        re.search(
            r'["\']STAGE-REVIEW-S01["\']\s*:\s*write_stage1_review_evidence\s*,?',
            main_text,
        )
    )
    replay_ok = (
        integration.get("stage1_review_replayed_by_full_pytest") is True
        and "python -m pytest -q" in text
        and (root / "tests/S01/stage_review_test.py").is_file()
        and writer_registration_present
    )
    _add(
        checks,
        "S01REVIEW-EXECUTABLE-REPLAY-REGISTERED",
        replay_ok,
        {
            "test": (root / "tests/S01/stage_review_test.py").is_file(),
            "writer_registration": writer_registration_present,
        },
    )


def _iter_text_files(root: Path) -> Iterable[Path]:
    excluded = {".git", ".venv", ".pytest_cache", "__pycache__"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or excluded.intersection(path.parts):
            continue
        if path.name == ".DS_Store" or path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def _check_security_budget_progression_and_readme(
    root: Path,
    canonical: Mapping[str, Any],
    parameters: Mapping[str, Any],
    costs: Mapping[str, Any],
    dependency_lock: Mapping[str, Any],
    authorization: Mapping[str, Any],
    degraded: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    *,
    verify_history: bool,
) -> None:
    actions = authorization.get("actions", [])
    real_order = next((row for row in actions if isinstance(row, dict) and row.get("id") == "REAL_ORDER_SUBMISSION"), {})
    budget_ok = (
        canonical.get("product", {}).get("initial_bankroll_aud") == "300.00"
        and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00"
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and costs.get("incremental_cash_budget", {}).get("high") == "0.00"
        and dependency_lock.get("budget_policy", {}).get("maximum_incremental_cash_cost_aud") == "0.00"
        and dependency_lock.get("budget_policy", {}).get("paid_dependency_allowed") is False
        and real_order.get("authorization") == "PROHIBITED"
        and real_order.get("capability_status") == "MODULE_MUST_NOT_EXIST"
        and degraded.get("current_state") == "CONSENT_NOT_REQUESTED"
        and degraded.get("s00_p04_execution_boundary", {}).get("gmail_api_called") is False
    )
    _add(checks, "S01REVIEW-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT", budget_ok, {"real_order": real_order, "gmail_state": degraded.get("current_state")})

    patterns = {
        "ABSOLUTE_USER_PATH": re.compile(re.escape("/" + "Users/")),
        "PRIVATE_KEY_BLOCK": re.compile("BEGIN (?:RSA |EC |OPENSSH )?" + "PRIVATE KEY"),
        "GITHUB_CLASSIC_TOKEN": re.compile("gh" + r"p_[0-9A-Za-z]{20,}"),
        "GITHUB_FINE_GRAINED_TOKEN": re.compile("github" + r"_pat_[0-9A-Za-z_]{20,}"),
        "GOOGLE_ACCESS_TOKEN": re.compile("ya" + r"29\.[0-9A-Za-z_-]{20,}"),
        "GOOGLE_REFRESH_TOKEN": re.compile("1/" + r"/[0-9A-Za-z_-]{20,}"),
        "GOOGLE_API_KEY": re.compile("AI" + r"za[0-9A-Za-z_-]{20,}"),
    }
    matches = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in patterns.items():
            if pattern.search(text):
                matches.append({"path": path.relative_to(root).as_posix(), "pattern": label})
    _add(checks, "S01REVIEW-SECRET-AND-LOCAL-PATH-SCAN", not matches, matches or "none")

    try:
        index_rows = _load_evidence_index(root)
        s02 = [row for row in index_rows if row.get("id") == "INDEX-AC-S02-P01"]
        s02_p02 = [row for row in index_rows if row.get("id") == "INDEX-AC-S02-P02"]
        s02_evidence = sorted(path.name for path in (root / "machine/evidence").glob("EVD-S02-*.json"))
        delivery = verify_stage0_delivery(root, verify_git_history=verify_history)
        prestart_ok = (
            len(s02) == 1
            and s02[0].get("status") == "PLANNED"
            and not s02_evidence
        )
        successor_status = "NOT_PRESENT"
        successor_ok = False
        successor_mode = "NONE"
        if s02_evidence == ["EVD-S02-P01.json", "EVD-S02-P01_rollback.json"]:
            from .official_platform_research import verify_existing_phase_evidence

            successor = verify_existing_phase_evidence(
                root,
                verify_git_history=verify_history,
            )
            successor_status = successor.get("status", "FAIL")
            successor_ok = (
                len(s02) == 1
                and s02[0].get("status") == "PASS"
                and successor_status == "PASS"
            )
            successor_mode = "VERIFIED_S02_P01_SUCCESSOR"
        elif s02_evidence == [
            "EVD-S02-P01.json",
            "EVD-S02-P01_rollback.json",
            "EVD-S02-P02.json",
            "EVD-S02-P02_rollback.json",
        ]:
            from .model_risk_research import verify_existing_phase_evidence as verify_p02_evidence

            successor = verify_p02_evidence(
                root,
                verify_git_history=verify_history,
            )
            successor_status = successor.get("status", "FAIL")
            successor_ok = (
                len(s02) == 1
                and s02[0].get("status") == "PASS"
                and len(s02_p02) == 1
                and s02_p02[0].get("status") == "PASS"
                and successor_status == "PASS"
                and successor.get("next") == "S02/P03_READY_NOT_STARTED"
            )
            successor_mode = "VERIFIED_S02_P02_SUCCESSOR"
        elif s02_evidence:
            successor_status = "UNRECOGNIZED_S02_SUCCESSOR_SET"
            successor_ok = False
            successor_mode = "INVALID_S02_SUCCESSOR_SET"
        progression_ok = delivery.get("status") == "PASS" and (prestart_ok or successor_ok)
        progression_detail = {
            "mode": "S02_NOT_STARTED" if prestart_ok else successor_mode,
            "s02": s02[0].get("status") if len(s02) == 1 else "INVALID",
            "evidence": s02_evidence,
            "stage0_delivery": delivery.get("status"),
            "successor_verification": successor_status,
        }
    except Exception as exc:
        progression_ok = False
        progression_detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01REVIEW-S02-NOT-STARTED-AND-S00-DELIVERED", progression_ok, progression_detail)

    try:
        readme = (root / "README.md").read_text(encoding="utf-8")
        pre_delivery_readme_ok = (
            "S01/P04" in readme
            and "S01 整体复审" in readme
            and "tests/S01/stage_review_test.py" in readme
            and "STAGE-REVIEW-S01" in readme
            and "远端 CI 尚未验证" in readme
            and "S01/P04 尚未开始" not in readme
        )
        successor_readme_ok = (
            "S01 整体复审" in readme
            and "Stage 1 已通过 GitHub PR #64" in readme
            and "S02/P01" in readme
            and "tests/S02/P01_test.py" in readme
            and "STAGE-REVIEW-S01" in readme
            and "本 Phase 仅本地开发" in readme
            and "远端 CI 尚未验证" not in readme
            and "S01/P04 尚未开始" not in readme
        )
        readme_ok = pre_delivery_readme_ok or successor_readme_ok
    except Exception as exc:
        readme_ok = False
        readme = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S01REVIEW-README-CURRENT-DELIVERY-STATE", readme_ok, "current" if readme_ok else str(readme)[:500])


def _check_findings(findings: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    rows = findings.get("findings", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    errors = []
    if ids != fixture.get("expected_review_finding_ids"):
        errors.append({"expected": fixture.get("expected_review_finding_ids"), "actual": ids})
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "RESOLVED_IN_REVIEW_CANDIDATE" or not row.get("evidence") or not row.get("resolution"):
            errors.append(row)
    summary = findings.get("summary", {})
    boundary = findings.get("scope_boundaries", {})
    if summary != {"total": 4, "resolved_in_review_candidate": 4, "open": 0, "remote_ci_pending_is_upload_evidence_not_an_open_code_finding": True}:
        errors.append({"summary": summary})
    if boundary != {
        "s02_started": False,
        "external_account_or_api_accessed": False,
        "secret_provisioned": False,
        "incremental_cash_spent_aud": "0.00",
        "production_or_return_claimed": False,
        "real_order_submitted": False,
    }:
        errors.append({"scope_boundaries": boundary})
    _add(checks, "S01REVIEW-FINDINGS-ALL-RESOLVED", not errors, errors or summary)


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites: Iterable[ET.Element] = [root] if root.tag == "testsuite" else root.findall("testsuite")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(float(suite.attrib.get(key, "0")))
    return totals


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    for element in root.iter():
        if element.tag == "testsuite":
            if element.attrib.get("hostname") is not None or element.attrib.get("timestamp") != FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S01REVIEW-TEST-TARGETED-PASS", JUNIT_PATH, 45),
        ("S01REVIEW-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, 850),
    ]:
        path = root / relative
        try:
            summary = _junit_summary(path)
            normalized = _junit_is_normalized(path)
            passed = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and normalized
            hashes[relative.as_posix()] = sha256_file(path)
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S01REVIEW-PACK-REPORT-PARSE")
    report_ok = isinstance(report, dict) and report.get("status") == "PASS" and report.get("summary", {}).get("checks") == 49 and report.get("summary", {}).get("failed") == 0
    _add(checks, "S01REVIEW-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = (
            "STATUS: PASS" in scan_text
            and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan_text
            and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
            and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in scan_text
        )
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        _add(checks, "S01REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S01REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "S01_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S01_REVIEW_BLOCKED_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": sum(1 for check in checks if check["passed"]), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "stage_status": "S01_REVIEW_PASS_REMOTE_UPLOAD_PENDING" if status == "PASS" else "S01_REVIEW_FAILED",
        "remote_ci_status": "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD",
        "release_status": "NOT_READY",
        "next": "S01/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S01/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_history: bool = True,
    _verify_phase_oracles: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    repo_root = root.parent
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}

    paths = {
        "contract": (CONTRACT_PATH, "S01REVIEW-INPUT-CONTRACT-PARSE"),
        "findings": (FINDINGS_PATH, "S01REVIEW-INPUT-FINDINGS-PARSE"),
        "fixture": (FIXTURE_PATH, "S01REVIEW-INPUT-FIXTURE-PARSE"),
        "roadmap": (Path("machine/facts/roadmap.json"), "S01REVIEW-INPUT-ROADMAP-PARSE"),
        "requirements": (Path("machine/facts/requirements.json"), "S01REVIEW-INPUT-TASKPACK-REQUIREMENTS-PARSE"),
        "acceptance": (Path("machine/facts/acceptance_contracts.json"), "S01REVIEW-INPUT-ACCEPTANCE-PARSE"),
        "task_graph": (Path("machine/facts/task_graph.json"), "S01REVIEW-INPUT-TASK-GRAPH-PARSE"),
        "traceability": (Path("machine/facts/traceability_matrix.json"), "S01REVIEW-INPUT-TRACEABILITY-PARSE"),
        "authorization": (Path("machine/facts/authorization_matrix.json"), "S01REVIEW-INPUT-AUTHORIZATION-PARSE"),
        "canonical": (Path("machine/facts/canonical_facts.json"), "S01REVIEW-INPUT-CANONICAL-PARSE"),
        "parameters": (Path("machine/facts/parameters.json"), "S01REVIEW-INPUT-PARAMETERS-PARSE"),
        "costs": (Path("machine/facts/costs.json"), "S01REVIEW-INPUT-COSTS-PARSE"),
        "dependency_lock": (Path("machine/facts/dependency_budget.lock"), "S01REVIEW-INPUT-DEPENDENCY-LOCK-PARSE"),
        "degraded": (Path("machine/facts/degraded_mode_contract.json"), "S01REVIEW-INPUT-DEGRADED-PARSE"),
        "outcomes": (Path("customer_outcomes.json"), "S01REVIEW-INPUT-OUTCOMES-PARSE"),
        "assumptions": (Path("assumption_register.json"), "S01REVIEW-INPUT-ASSUMPTIONS-PARSE"),
        "product_requirements": (Path("requirements.json"), "S01REVIEW-INPUT-PRODUCT-REQUIREMENTS-PARSE"),
        "scope": (Path("scope_boundary.json"), "S01REVIEW-INPUT-SCOPE-PARSE"),
        "metrics": (Path("metrics.json"), "S01REVIEW-INPUT-METRICS-PARSE"),
        "economics": (Path("economics.json"), "S01REVIEW-INPUT-ECONOMICS-PARSE"),
        "kills": (Path("kill_criteria.json"), "S01REVIEW-INPUT-KILLS-PARSE"),
    }
    values = {name: _safe_load(root / relative, checks, check_id) for name, (relative, check_id) in paths.items()}
    _check_pinned_review_artifacts(root, repo_root, checks, hashes)
    object_names = {"contract", "findings", "fixture", "roadmap", "task_graph", "authorization", "canonical", "parameters", "costs", "dependency_lock", "degraded", "outcomes", "assumptions", "product_requirements", "scope", "metrics", "economics", "kills"}
    array_names = {"requirements", "acceptance", "traceability"}
    if not all(isinstance(values[name], dict) for name in object_names) or not all(isinstance(values[name], list) for name in array_names):
        _add(checks, "S01REVIEW-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S01REVIEW-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    _check_contract_shape(values["contract"], values["fixture"], values["authorization"], checks)
    _check_baseline_hashes(root, values["contract"], checks, hashes)
    _check_stage_trace(values["contract"], values["fixture"], values["roadmap"], values["requirements"], values["acceptance"], values["task_graph"], values["traceability"], checks)
    _check_phase_evidence_and_history(root, repo_root, values["contract"], checks, hashes, verify_history=_verify_history)
    if _verify_phase_oracles:
        _check_phase_oracles(root, values["fixture"], checks)
    if not _verify_history or not _verify_phase_oracles:
        _add(checks, "S01REVIEW-TEST-ONLY-PARTIAL-PROFILE", False, {"history_verified": _verify_history, "phase_oracles_verified": _verify_phase_oracles})
    _check_product_metric_economic_trace(root, values["fixture"], values["product_requirements"], values["metrics"], values["economics"], values["kills"], checks)
    _check_truth_safety_boundaries(values["outcomes"], values["assumptions"], values["scope"], values["metrics"], values["economics"], values["kills"], checks)
    _check_findings(values["findings"], values["fixture"], checks)
    _check_workflow_and_review_replay(root, repo_root, values["contract"], values["fixture"], checks)
    _check_security_budget_progression_and_readme(root, values["canonical"], values["parameters"], values["costs"], values["dependency_lock"], values["authorization"], values["degraded"], checks, verify_history=_verify_history)
    if require_external_reports:
        _check_runtime_reports(root, checks, hashes)
    return _build_result(checks, hashes)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    repo_root = root.parent
    artifacts = [
        (CONTRACT_PATH.as_posix(), root / CONTRACT_PATH),
        (FINDINGS_PATH.as_posix(), root / FINDINGS_PATH),
        (FIXTURE_PATH.as_posix(), root / FIXTURE_PATH),
        ("metrics.json", root / "metrics.json"),
        ("economics.json", root / "economics.json"),
        ("kill_criteria.json", root / "kill_criteria.json"),
        (WORKFLOW_PATH.as_posix(), repo_root / WORKFLOW_PATH),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s01-stage-review-rollback-") as directory:
        temporary = Path(directory)
        for index, (label, source) in enumerate(artifacts):
            expected = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored = sha256_file(active)
            results[label] = {"status": "PASS" if corrupted != expected and restored == expected else "FAIL", "signed_sha256": expected, "corrupted_sha256": corrupted, "restored_sha256": restored}
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {"schema_version": "1.0.0", "evidence_id": "EVD-S01-STAGE-REVIEW-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "mode": "EPHEMERAL_SIGNED_STAGE1_REVIEW_AND_PRODUCT_CONTRACT_RESTORE", "status": status, "artifacts": results, "production_state_changed": False, "external_state_changed": False}


def _input_hashes(root: Path) -> Dict[str, str]:
    repo_root = root.parent
    paths = [
        CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, Path("README.md"),
        Path("customer_press_release.md"), Path("customer_outcomes.json"), Path("customer_faq.md"), Path("assumption_register.json"),
        Path("requirements.json"), Path("scope_boundary.json"), Path("business_flows.json"),
        Path("metrics.json"), Path("economics.json"), Path("kill_criteria.json"),
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/authorization_matrix.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/dependency_budget.lock"), Path("machine/facts/degraded_mode_contract.json"),
        Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"), Path("machine/facts/roadmap.json"),
        Path("machine/evidence/EVD-S01-P01.json"), Path("machine/evidence/EVD-S01-P02.json"),
        Path("machine/evidence/EVD-S01-P03.json"), Path("machine/evidence/EVD-S01-P04.json"),
        Path("abd_acceptance/stage1_review.py"), Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
        Path("tests/S01/stage_review_test.py"), Path("machine/tools/normalize_junit.py"),
        Path("machine/tools/scan_paid_dependencies.py"), Path("machine/tools/update_artifact_manifest.py"), Path("machine/tools/validate_pack.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[WORKFLOW_PATH.as_posix()] = sha256_file(repo_root / WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {"schema_version": "1.0.0", "evidence_id": "EVD-S01-STAGE-REVIEW-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc), "production_state_changed": False, "external_state_changed": False}
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "S01_REVIEW_BLOCKED_FAIL_CLOSED"
        result["stage_status"] = "S01_REVIEW_FAILED"
        result["next"] = "S01/STAGE_REVIEW_REMEDIATION_REQUIRED"

    rollback_bytes = _json_bytes(rollback)
    contract = strict_json_load(root / CONTRACT_PATH)
    findings = strict_json_load(root / FINDINGS_PATH)
    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S01-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "stage_goal": "从客户结果反推产品，冻结问题、用户、价值、非目标、指标、经济性和证伪合同。",
        "phase_completion": {"phase_ids": ["P01", "P02", "P03", "P04"], "phase_evidence_status": "PASS", "phase_count": 4, "task_count": 12, "product_requirement_count": 21, "metric_count": 31, "kill_criterion_count": 19},
        "review_findings": findings.get("summary"),
        "validation": result,
        "source_receipts": contract.get("supplied_source_receipts"),
        "hashes": {"inputs": input_hashes, "parameters": input_hashes.get("machine/facts/parameters.json"), "code": _current_code_hash(root), "model": None, "model_not_applicable_reason": "Stage 1 freezes product, metric, economic and falsification contracts; no prediction model was executed.", "rollback_evidence": _sha256_bytes(rollback_bytes)},
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S01/stage_review_test.py --junitxml=machine/evidence/S01/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S01/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S01/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "upload_gate": {"local_preconditions_status": "PASS" if result["status"] == "PASS" else "FAIL", "remote_ci_status": "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD", "github_upload_performed_by_review": False, "remote_result_must_be_verified_before_s02": True},
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "explicit_unknowns": [
            "GitHub Actions has not run on this candidate before the authorized Stage 1 upload.",
            "No Gmail, OVH, Cloudflare, betting-platform account, credential, quota, billing or production runtime was accessed by this review.",
            "No production deployment, live recommendation, real order, actual return, ROI, NPV or payback validation is claimed.",
            "A$300*1.3^n remains an unverified falsifiable target, not a random-return guarantee.",
        ],
        "release_status": "NOT_READY",
        "stage_status": result["stage_status"],
        "next": result["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    matching = [row for row in rows if row.get("id") == "INDEX-S01-STAGE-REVIEW"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-S01-STAGE-REVIEW row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S01/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S01/STAGE_REVIEW_REMEDIATION_REQUIRED"
    payload = b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows)
    _atomic_write(path, payload)


def write_stage1_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {"contract_id": CONTRACT_ID, "status": evidence["status"], "evidence_path": evidence_path.relative_to(root).as_posix(), "evidence_sha256": evidence_hash, "next": evidence["next"]}
