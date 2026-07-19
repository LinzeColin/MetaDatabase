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
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from .authorization import evaluate_contract as evaluate_p02
from .budget import evaluate_contract as evaluate_p03
from .canonical_facts import DuplicateKeyError, sha256_file, strict_json_load
from .canonical_facts import evaluate_contract as evaluate_p01
from .external_consent import evaluate_contract as evaluate_p04
from .delivery import verify_stage0_delivery


CONTRACT_ID = "STAGE-REVIEW-S00"
REVIEW_ID = "ABD-S00-WHOLE-STAGE-REVIEW"
STAGE_ID = "S00"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage0_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S00/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S00_STAGE_REVIEW.json")
JUNIT_PATH = Path("machine/evidence/S00/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S00/STAGE_REVIEW/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S00-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S00-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")

REPO_WORKFLOW_PATHS = {
    ".github/workflows/dual-plane.yml": "56024e39ff14ef6dfc895ebcb384b67ca1d4d5118289588761858b5273397ab9",
    ".github/workflows/abd-stage0-validation.yml": "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}
PROJECT_PINNED_PATHS = {
    CONTRACT_PATH.as_posix(): "b8690e7639dfa50760f372a584e3af324d43b415fc911e084a31de10e97ced30",
    FINDINGS_PATH.as_posix(): "1e04047b92976cc746c9912806358880a17f7740fa1678e5122b9db28e8c7284",
    FIXTURE_PATH.as_posix(): "5ca9ffcb600b7b95d1dac392f0999dd12d62d6c0921e686beb02d8ab77d2d55e",
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


def _load_evidence_index(root: Path) -> List[Dict[str, Any]]:
    rows = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("decision_sha256")
    unsigned = deepcopy(dict(evidence))
    unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and _sha256_bytes(_json_bytes(unsigned)) == expected


def _code_hash_at_commit(repo_root: Path, commit: str) -> str:
    listing = _git(repo_root, "ls-tree", "-r", "--name-only", commit, "--", "ABD/abd_acceptance")
    if listing.returncode != 0:
        raise RuntimeError(listing.stderr.decode("utf-8", errors="replace").strip())
    paths = sorted(
        line for line in listing.stdout.decode("utf-8").splitlines()
        if line.endswith(".py")
    )
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


def _check_pinned_review_artifacts(
    root: Path,
    repo_root: Path,
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    for relative, expected in PROJECT_PINNED_PATHS.items():
        path = root / relative
        try:
            actual = sha256_file(path)
        except Exception as exc:
            _add(checks, "REVIEW-PIN-%s" % Path(relative).stem.upper(), False, str(exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "REVIEW-PIN-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )
    for relative, expected in REPO_WORKFLOW_PATHS.items():
        path = repo_root / relative
        try:
            actual = sha256_file(path)
        except Exception as exc:
            _add(checks, "REVIEW-PIN-%s" % Path(relative).stem.upper(), False, str(exc))
            continue
        hashes[relative] = actual
        _add(
            checks,
            "REVIEW-PIN-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )


def _check_contract_shape(
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    authorization: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    scope = contract.get("review_scope", {})
    expected_phases = fixture.get("expected_phase_ids", [])
    phase_ok = (
        contract.get("schema_version") == "1.0.0"
        and contract.get("product_version") == VERSION
        and contract.get("stage_id") == STAGE_ID
        and contract.get("review_id") == REVIEW_ID
        and scope.get("phase_ids") == expected_phases
        and len(scope.get("requirement_ids", [])) == 4
        and len(scope.get("acceptance_contract_ids", [])) == 4
        and len(scope.get("task_ids", [])) == 12
        and len(set(scope.get("task_ids", []))) == 12
    )
    _add(checks, "REVIEW-CONTRACT-SCOPE", phase_ok, scope)

    receipts = contract.get("supplied_source_receipts", [])
    receipts_by_label = {
        row.get("artifact_label"): row for row in receipts if isinstance(row, dict)
    }
    roadmap = receipts_by_label.get("ABD_Roadmap_Stage_Phase_v0.0.0.1.md", {})
    taskpack = receipts_by_label.get("ABD_ProductDesign_TaskPack_v0.0.0.1_FINAL.zip", {})
    receipts_ok = (
        len(receipts) == 2
        and roadmap.get("sha256") == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and roadmap.get("repository_equivalent") == "machine/evidence/roadmap_stage_phase.md"
        and taskpack.get("sha256") == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and taskpack.get("original_file_count") == 53
        and taskpack.get("repository_equivalent") is None
        and "CI verifies pinned critical files" in str(taskpack.get("verification_boundary", ""))
    )
    _add(checks, "REVIEW-SUPPLIED-SOURCE-RECEIPTS", receipts_ok, receipts)

    actions = authorization.get("actions", [])
    github_rows = [
        row for row in actions
        if isinstance(row, dict) and row.get("id") == "GITHUB_STAGE_UPLOAD"
    ]
    github = github_rows[0] if len(github_rows) == 1 else {}
    expected_preconditions = fixture.get("required_upload_preconditions", [])
    upload_ok = (
        len(github_rows) == 1
        and github.get("authorization") == "CONDITIONALLY_PREAUTHORIZED"
        and github.get("effect") == "WRITE_EXTERNAL_REVERSIBLE"
        and github.get("cash_cost_aud") == "0.00"
        and github.get("preconditions") == expected_preconditions
        and contract.get("upload_preconditions") == expected_preconditions
        and github.get("on_precondition_failure") == "KEEP_COMMITS_LOCAL_CONTINUE_STAGE_REMEDIATION"
    )
    _add(checks, "REVIEW-GITHUB-UPLOAD-AUTHORIZATION-ALIGNMENT", upload_ok, github)

    boundary = contract.get("external_effect_boundary", {})
    boundary_ok = (
        boundary
        and all(value is False for value in boundary.values())
        and contract.get("next_on_local_review_pass") == "S00/GITHUB_STAGE_UPLOAD_READY"
        and contract.get("next_after_verified_remote_upload") == "S01/P01_READY_NOT_STARTED"
    )
    _add(checks, "REVIEW-EXTERNAL-EFFECT-BOUNDARY", boundary_ok, boundary)


def _check_baseline_hashes(
    root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
) -> None:
    expected = contract.get("baseline_critical_artifacts", {})
    errors = []
    if not isinstance(expected, dict) or len(expected) != 13:
        errors.append("expected exactly 13 critical baseline artifacts")
        expected = expected if isinstance(expected, dict) else {}
    for relative, wanted in expected.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        if actual != wanted:
            errors.append({"path": relative, "expected": wanted, "actual": actual})
    _add(checks, "REVIEW-BASELINE-CRITICAL-HASHES", not errors, errors or sorted(expected))


def _check_s00_trace(
    contract: Mapping[str, Any],
    roadmap: Mapping[str, Any],
    requirements: Sequence[Any],
    acceptance: Sequence[Any],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Any],
    checks: List[Dict[str, Any]],
) -> None:
    scope = contract.get("review_scope", {})
    stages = [row for row in roadmap.get("stages", []) if isinstance(row, dict) and row.get("id") == STAGE_ID]
    stage = stages[0] if len(stages) == 1 else {}
    phase_rows = stage.get("phases", []) if isinstance(stage, dict) else []
    phase_ids = [row.get("id") for row in phase_rows if isinstance(row, dict)]
    stage_ok = (
        len(stages) == 1
        and phase_ids == scope.get("phase_ids")
        and stage.get("depends_on") == []
        and len(stage.get("stop_conditions", [])) == 5
        and stage.get("stop_conditions") == contract.get("stage_stop_conditions")
    )
    _add(checks, "REVIEW-S00-ROADMAP-EXACT", stage_ok, stage)

    req_rows = [row for row in requirements if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    ac_rows = [row for row in acceptance if isinstance(row, dict) and str(row.get("id", "")).startswith("AC-S00-")]
    tasks = [row for row in task_graph.get("tasks", []) if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    traces = [row for row in traceability if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    ids_ok = (
        [row.get("id") for row in req_rows] == scope.get("requirement_ids")
        and [row.get("id") for row in ac_rows] == scope.get("acceptance_contract_ids")
        and [row.get("id") for row in tasks] == scope.get("task_ids")
        and [row.get("requirement_id") for row in traces] == scope.get("requirement_ids")
    )
    _add(
        checks,
        "REVIEW-S00-REQ-AC-TASK-TRACE-SETS",
        ids_ok,
        {"requirements": len(req_rows), "acceptance": len(ac_rows), "tasks": len(tasks), "trace": len(traces)},
    )

    phase_by_id = {row.get("id"): row for row in phase_rows if isinstance(row, dict)}
    req_by_id = {row.get("id"): row for row in req_rows}
    ac_by_id = {row.get("id"): row for row in ac_rows}
    trace_by_req = {row.get("requirement_id"): row for row in traces}
    semantic_errors = []
    for record in contract.get("phase_records", []):
        if not isinstance(record, dict):
            semantic_errors.append("non-object phase record")
            continue
        phase = phase_by_id.get(record.get("phase_id"), {})
        requirement = req_by_id.get(record.get("requirement_id"), {})
        ac = ac_by_id.get(record.get("acceptance_contract_id"), {})
        trace = trace_by_req.get(record.get("requirement_id"), {})
        if requirement.get("primary_acceptance_criteria_id") != record.get("acceptance_contract_id"):
            semantic_errors.append("%s requirement->AC" % record.get("phase_id"))
        if requirement.get("target") != phase.get("pass_gate"):
            semantic_errors.append("%s requirement target" % record.get("phase_id"))
        if ac.get("requirement_id") != record.get("requirement_id") or ac.get("pass_gate") != phase.get("pass_gate"):
            semantic_errors.append("%s AC semantics" % record.get("phase_id"))
        oracle = ac.get("oracle", {})
        if oracle.get("type") != "EXECUTABLE" or oracle.get("rule") != phase.get("pass_gate"):
            semantic_errors.append("%s executable oracle" % record.get("phase_id"))
        if trace.get("task_ids") != record.get("task_ids") or trace.get("acceptance_criteria_id") != record.get("acceptance_contract_id"):
            semantic_errors.append("%s trace" % record.get("phase_id"))
    _add(checks, "REVIEW-S00-SEMANTIC-TRACE", not semantic_errors, semantic_errors or "all aligned")

    chain_errors = []
    expected_task_ids = scope.get("task_ids", [])
    tasks_by_id = {row.get("id"): row for row in tasks}
    for index, task_id in enumerate(expected_task_ids):
        expected_deps = [] if index == 0 else [expected_task_ids[index - 1]]
        task = tasks_by_id.get(task_id, {})
        if task.get("depends_on") != expected_deps:
            chain_errors.append({"task": task_id, "expected": expected_deps, "actual": task.get("depends_on")})
        if task.get("owner_input_required") is not False or task.get("auto_advance_on_pass") is not True:
            chain_errors.append({"task": task_id, "reason": "owner/auto-advance"})
    _add(checks, "REVIEW-S00-TASK-CHAIN-EXACT", not chain_errors, chain_errors or {"tasks": len(expected_task_ids)})


def _check_phase_evidence_and_history(
    root: Path,
    repo_root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    verify_history: bool = True,
) -> None:
    try:
        index_rows = _load_evidence_index(root)
    except Exception as exc:
        _add(checks, "REVIEW-PHASE-EVIDENCE-INDEX", False, "%s: %s" % (type(exc).__name__, exc))
        index_rows = []

    evidence_errors = []
    history_errors = []
    output_errors = []
    commits = []
    for record in contract.get("phase_records", []):
        if not isinstance(record, dict):
            evidence_errors.append("non-object phase record")
            continue
        phase_id = record.get("phase_id")
        evidence_path = root / str(record.get("evidence_path", ""))
        rollback_path = root / str(record.get("rollback_path", ""))
        evidence_hash = sha256_file(evidence_path) if evidence_path.is_file() else "MISSING"
        rollback_hash = sha256_file(rollback_path) if rollback_path.is_file() else "MISSING"
        hashes[str(record.get("evidence_path"))] = evidence_hash
        hashes[str(record.get("rollback_path"))] = rollback_hash
        if evidence_hash != record.get("evidence_sha256"):
            evidence_errors.append({"phase": phase_id, "evidence_hash": evidence_hash})
        if rollback_hash != record.get("rollback_sha256"):
            evidence_errors.append({"phase": phase_id, "rollback_hash": rollback_hash})
        try:
            evidence = strict_json_load(evidence_path)
            rollback = strict_json_load(rollback_path)
        except Exception as exc:
            evidence_errors.append({"phase": phase_id, "parse": "%s: %s" % (type(exc).__name__, exc)})
            continue
        if not isinstance(evidence, dict) or not isinstance(rollback, dict):
            evidence_errors.append({"phase": phase_id, "reason": "evidence or rollback not object"})
            continue
        if (
            evidence.get("status") != "PASS"
            or evidence.get("contract_id") != record.get("acceptance_contract_id")
            or evidence.get("requirement_id") != record.get("requirement_id")
            or evidence.get("task_ids") != record.get("task_ids")
            or evidence.get("next") != record.get("expected_next")
            or evidence.get("validation", {}).get("status") != "PASS"
            or evidence.get("release_status") != "NOT_READY"
            or evidence.get("hashes", {}).get("code") != record.get("implementation_code_sha256")
            or not _decision_hash_matches(evidence)
            or rollback.get("status") != "PASS"
            or rollback.get("production_state_changed") is not False
        ):
            evidence_errors.append({"phase": phase_id, "reason": "semantic evidence gate"})
        for relative, wanted in evidence.get("hashes", {}).get("inputs", {}).items():
            path = root / relative
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != wanted:
                evidence_errors.append({"phase": phase_id, "input": relative, "actual": actual})
        if evidence.get("hashes", {}).get("rollback_evidence") != rollback_hash:
            evidence_errors.append({"phase": phase_id, "reason": "rollback binding"})
        matching = [row for row in index_rows if row.get("id") == "INDEX-AC-S00-%s" % phase_id]
        if (
            len(matching) != 1
            or matching[0].get("status") != "PASS"
            or matching[0].get("artifact_sha256") != evidence_hash
        ):
            evidence_errors.append({"phase": phase_id, "reason": "index binding"})
        for relative in record.get("required_outputs", []):
            if not (root / relative).is_file():
                output_errors.append({"phase": phase_id, "missing": relative})

        if verify_history:
            commit = str(record.get("implementation_commit", ""))
            commits.append(commit)
            exists = _git(repo_root, "cat-file", "-e", "%s^{commit}" % commit)
            ancestor = _git(repo_root, "merge-base", "--is-ancestor", commit, "HEAD")
            if exists.returncode != 0 or ancestor.returncode != 0:
                history_errors.append({"phase": phase_id, "reason": "commit missing or not ancestor", "commit": commit})
                continue
            try:
                actual_code_hash = _code_hash_at_commit(repo_root, commit)
            except Exception as exc:
                history_errors.append({"phase": phase_id, "reason": str(exc)})
                continue
            if actual_code_hash != record.get("implementation_code_sha256"):
                history_errors.append({"phase": phase_id, "code_hash": actual_code_hash})
            changed = _git(repo_root, "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", commit)
            changed_paths = [
                path.decode("utf-8") for path in changed.stdout.split(b"\0") if path
            ] if changed.returncode == 0 else []
            if not changed_paths or any(not path.startswith("ABD/") for path in changed_paths):
                history_errors.append({"phase": phase_id, "reason": "commit escaped ABD", "paths": changed_paths})

    if verify_history:
        for previous, current in zip(commits, commits[1:]):
            if _git(repo_root, "merge-base", "--is-ancestor", previous, current).returncode != 0:
                history_errors.append({"reason": "phase commit order", "previous": previous, "current": current})

    _add(checks, "REVIEW-PHASE-EVIDENCE-INDEX", not evidence_errors, evidence_errors or {"phases": 4})
    if verify_history:
        _add(checks, "REVIEW-PHASE-HISTORICAL-CODE-HASHES", not history_errors, history_errors or commits)
    _add(checks, "REVIEW-PHASE-REQUIRED-OUTPUTS", not output_errors, output_errors or {"outputs": 12})


def _check_phase_oracles(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    summaries = {}
    errors = []
    minimums = fixture.get("expected_phase_evaluator_min_checks", {})
    for phase_id in fixture.get("expected_phase_ids", []):
        evaluator = PHASE_EVALUATORS.get(phase_id)
        if evaluator is None:
            errors.append({"phase": phase_id, "reason": "missing evaluator"})
            continue
        try:
            result = evaluator(root, require_external_reports=True)
        except Exception as exc:
            errors.append({"phase": phase_id, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        summary = result.get("summary", {})
        summaries[phase_id] = {
            "status": result.get("status"),
            "checks": summary.get("checks"),
            "failed": summary.get("failed"),
            "next": result.get("next"),
        }
        if (
            result.get("status") != "PASS"
            or summary.get("failed") != 0
            or int(summary.get("checks", 0)) < int(minimums.get(phase_id, 0))
        ):
            errors.append({"phase": phase_id, "summary": summaries[phase_id]})
    _add(checks, "REVIEW-ALL-PHASE-ORACLES-PASS", not errors, errors or summaries)


def _check_findings(findings: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    rows = findings.get("findings", [])
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    errors = []
    if ids != fixture.get("expected_review_finding_ids"):
        errors.append({"expected": fixture.get("expected_review_finding_ids"), "actual": ids})
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "RESOLVED_IN_REVIEW_CANDIDATE":
            errors.append(row)
        elif not row.get("evidence") or not row.get("resolution"):
            errors.append({"id": row.get("id"), "reason": "missing evidence/resolution"})
    summary = findings.get("summary", {})
    boundary = findings.get("scope_boundaries", {})
    if (
        summary.get("total") != 4
        or summary.get("resolved_in_review_candidate") != 4
        or summary.get("open") != 0
        or summary.get("remote_ci_pending_is_upload_evidence_not_an_open_code_finding") is not True
    ):
        errors.append({"summary": summary})
    if (
        boundary.get("s01_started") is not False
        or boundary.get("external_account_or_api_accessed") is not False
        or boundary.get("secret_provisioned") is not False
        or boundary.get("incremental_cash_spent_aud") != "0.00"
        or boundary.get("production_or_return_claimed") is not False
    ):
        errors.append({"scope_boundaries": boundary})
    _add(checks, "REVIEW-FINDINGS-ALL-RESOLVED", not errors, errors or summary)


def _workflow_action_refs(text: str) -> List[str]:
    return re.findall(r"^\s*-\s+uses:\s+[^@\s]+@([^\s#]+)", text, flags=re.MULTILINE)


def _check_workflows(
    repo_root: Path,
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    try:
        dual_text = (repo_root / ".github/workflows/dual-plane.yml").read_text(encoding="utf-8")
        abd_text = (repo_root / ".github/workflows/abd-stage0-validation.yml").read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "REVIEW-REPOSITORY-CI-WORKFLOWS", False, "%s: %s" % (type(exc).__name__, exc))
        return

    integration = contract.get("repository_integration", {})
    governance_projects = integration.get("governance_registered_projects", [])
    specialized = integration.get("specialized_taskpack_projects", [])
    registered_block = re.search(r"registered = \{(.*?)\n\s*\}", dual_text, flags=re.DOTALL)
    workflow_registered = sorted(re.findall(r'"([A-Za-z0-9-]+)"', registered_block.group(1))) if registered_block else []
    specialized_block = re.search(r'specialized = \{"([^"]+)":\s*"([^"]+)"\}', dual_text)
    workflow_specialized = (
        {specialized_block.group(1): specialized_block.group(2)}
        if specialized_block else {}
    )
    classification_ok = (
        governance_projects == fixture.get("expected_governance_projects")
        and specialized == fixture.get("expected_specialized_projects")
        and workflow_registered == sorted(governance_projects)
        and workflow_specialized == {"ABD": ".github/workflows/abd-stage0-validation.yml"}
        and integration.get("classification_rule") == "NO_RENDERER_PROJECT_MAY_BE_SILENTLY_SKIPPED"
        and "expected = registered | set(specialized)" in dual_text
        and "if discovered != expected" in dual_text
        and "Alpha EEI FIFA LinzeDatabase PFI QBVS Serenity-Alipay" in dual_text
        and ".github/workflows/abd-stage0-validation.yml" in dual_text
    )
    _add(
        checks,
        "REVIEW-CI-PROJECT-CLASSIFICATION",
        classification_ok,
        {"governance": governance_projects, "specialized": specialized},
    )

    pins = integration.get("pinned_actions", {})
    all_refs = _workflow_action_refs(dual_text) + _workflow_action_refs(abd_text)
    expected_refs = set(pins.values())
    pins_ok = (
        len(all_refs) == 5
        and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in all_refs)
        and set(all_refs) == expected_refs
        and "pyyaml==6.0.3" in dual_text
        and 'version: "0.11.28"' in abd_text
        and 'python-version: "3.12"' in abd_text
        and "fetch-depth: 0" in abd_text
    )
    _add(checks, "REVIEW-CI-SUPPLY-CHAIN-PINS", pins_ok, {"refs": all_refs, "pins": pins})

    missing_commands = [
        command for command in fixture.get("required_workflow_commands", [])
        if command not in abd_text
    ]
    workflow_ok = (
        not missing_commands
        and "runs-on: ubuntu-latest" in abd_text
        and "timeout-minutes: 15" in abd_text
        and "permissions:\n  contents: read" in abd_text
        and "pull_request:" in abd_text
        and "REMOTE_CI_PASS" not in abd_text
        and ("$" + "{{ secrets.") not in abd_text
    )
    _add(checks, "REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED", workflow_ok, missing_commands or "all required commands present")


def _iter_text_files(root: Path) -> Iterable[Path]:
    excluded = {".git", ".venv", ".pytest_cache", "__pycache__"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or excluded.intersection(path.parts):
            continue
        if path.name == ".DS_Store" or path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def _check_security_budget_and_progression(
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
    _add(checks, "REVIEW-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT", budget_ok, {"real_order": real_order, "gmail_state": degraded.get("current_state")})

    sensitive_patterns = {
        "absolute_user_path": re.compile(re.escape("/" + "Users/")),
        "private_key": re.compile("BEGIN (?:RSA |EC |OPENSSH )?" + "PRIVATE KEY"),
        "github_classic": re.compile("gh" + r"p_[0-9A-Za-z]{20,}"),
        "github_fine_grained": re.compile("github" + r"_pat_[0-9A-Za-z_]{20,}"),
        "github_oauth": re.compile("gh" + r"o_[0-9A-Za-z]{20,}"),
        "google_access": re.compile("ya" + r"29\.[0-9A-Za-z_-]{20,}"),
        "google_refresh": re.compile("1/" + r"/[0-9A-Za-z_-]{20,}"),
        "google_api_key": re.compile("AI" + r"za[0-9A-Za-z_-]{20,}"),
    }
    matches = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in sensitive_patterns.items():
            if pattern.search(text):
                matches.append({"path": path.relative_to(root).as_posix(), "pattern": name})
    _add(checks, "REVIEW-SECRET-AND-LOCAL-PATH-SCAN", not matches, matches or "none")

    try:
        index_rows = _load_evidence_index(root)
        s01 = [row for row in index_rows if row.get("id") == "INDEX-AC-S01-P01"]
        s01_evidence = sorted((root / "machine/evidence").glob("EVD-S01-*.json"))
        delivery = verify_stage0_delivery(root, verify_git_history=verify_history)
        status = s01[0].get("status") if len(s01) == 1 else "INVALID"
        names = [path.name for path in s01_evidence]
        not_started = status == "PLANNED" and not s01_evidence
        p01_started_after_delivery = (
            status == "PASS"
            and "EVD-S01-P01.json" in names
            and "EVD-S01-P01_rollback.json" in names
        )
        progression_ok = (
            len(s01) == 1
            and delivery.get("status") == "PASS"
            and (not_started or p01_started_after_delivery)
        )
        detail = {
            "s01_status": status,
            "s01_evidence": names,
            "stage0_delivery": delivery.get("summary"),
        }
    except Exception as exc:
        progression_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "REVIEW-S01-DELIVERY-GATED-PROGRESSION", progression_ok, detail)


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
            if element.attrib.get("hostname") is not None:
                return False
            if element.attrib.get("timestamp") != FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for check_id, relative, minimum in [
        ("REVIEW-TEST-TARGETED-PASS", JUNIT_PATH, 40),
        ("REVIEW-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, 190),
    ]:
        path = root / relative
        try:
            summary = _junit_summary(path)
            normalized = _junit_is_normalized(path)
            passed = (
                summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and normalized
            )
            hashes[relative.as_posix()] = sha256_file(path)
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    report = _safe_load(root / PACK_REPORT_PATH, checks, "REVIEW-PACK-REPORT-PARSE")
    report_ok = (
        isinstance(report, dict)
        and report.get("status") == "PASS"
        and report.get("summary", {}).get("checks") == 49
        and report.get("summary", {}).get("failed") == 0
    )
    _add(checks, "REVIEW-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
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
        _add(checks, "REVIEW-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


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
        "decision": "S00_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S00_REVIEW_BLOCKED_FAIL_CLOSED",
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
        "hashes": dict(hashes),
        "stage_status": "S00_REVIEW_PASS_REMOTE_UPLOAD_PENDING" if status == "PASS" else "S00_REVIEW_FAILED",
        "remote_ci_status": "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD",
        "release_status": "NOT_READY",
        "next": "S00/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S00/STAGE_REVIEW_REMEDIATION_REQUIRED",
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

    contract = _safe_load(root / CONTRACT_PATH, checks, "REVIEW-INPUT-CONTRACT-PARSE")
    findings = _safe_load(root / FINDINGS_PATH, checks, "REVIEW-INPUT-FINDINGS-PARSE")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "REVIEW-INPUT-FIXTURE-PARSE")
    canonical = _safe_load(root / "machine/facts/canonical_facts.json", checks, "REVIEW-INPUT-CANONICAL-PARSE")
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "REVIEW-INPUT-PARAMETERS-PARSE")
    costs = _safe_load(root / "machine/facts/costs.json", checks, "REVIEW-INPUT-COSTS-PARSE")
    dependency_lock = _safe_load(root / "machine/facts/dependency_budget.lock", checks, "REVIEW-INPUT-DEPENDENCY-LOCK-PARSE")
    authorization = _safe_load(root / "machine/facts/authorization_matrix.json", checks, "REVIEW-INPUT-AUTHORIZATION-PARSE")
    degraded = _safe_load(root / "machine/facts/degraded_mode_contract.json", checks, "REVIEW-INPUT-DEGRADED-PARSE")
    roadmap = _safe_load(root / "machine/facts/roadmap.json", checks, "REVIEW-INPUT-ROADMAP-PARSE")
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "REVIEW-INPUT-REQUIREMENTS-PARSE")
    acceptance = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "REVIEW-INPUT-ACCEPTANCE-PARSE")
    task_graph = _safe_load(root / "machine/facts/task_graph.json", checks, "REVIEW-INPUT-TASK-GRAPH-PARSE")
    traceability = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "REVIEW-INPUT-TRACEABILITY-PARSE")

    _check_pinned_review_artifacts(root, repo_root, checks, hashes)
    objects = (contract, findings, fixture, canonical, parameters, costs, dependency_lock, authorization, degraded, roadmap, task_graph)
    arrays = (requirements, acceptance, traceability)
    if not all(isinstance(value, dict) for value in objects) or not all(isinstance(value, list) for value in arrays):
        _add(checks, "REVIEW-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "REVIEW-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    _check_contract_shape(contract, fixture, authorization, checks)
    _check_baseline_hashes(root, contract, checks, hashes)
    _check_s00_trace(contract, roadmap, requirements, acceptance, task_graph, traceability, checks)
    _check_phase_evidence_and_history(
        root,
        repo_root,
        contract,
        checks,
        hashes,
        verify_history=_verify_history,
    )
    if _verify_phase_oracles:
        _check_phase_oracles(root, fixture, checks)
    if not _verify_history or not _verify_phase_oracles:
        _add(
            checks,
            "REVIEW-TEST-ONLY-PARTIAL-PROFILE",
            False,
            {
                "history_verified": _verify_history,
                "phase_oracles_verified": _verify_phase_oracles,
                "reason": "Mutation tests may skip expensive independent gates; evidence generation never does.",
            },
        )
    _check_findings(findings, fixture, checks)
    _check_workflows(repo_root, contract, fixture, checks)
    _check_security_budget_and_progression(
        root,
        canonical,
        parameters,
        costs,
        dependency_lock,
        authorization,
        degraded,
        checks,
        verify_history=_verify_history,
    )
    if require_external_reports:
        _check_runtime_reports(root, checks, hashes)
    return _build_result(checks, hashes)


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    repo_root = root.parent
    artifacts = [
        (CONTRACT_PATH.as_posix(), root / CONTRACT_PATH),
        (FINDINGS_PATH.as_posix(), root / FINDINGS_PATH),
        (".github/workflows/dual-plane.yml", repo_root / ".github/workflows/dual-plane.yml"),
        (".github/workflows/abd-stage0-validation.yml", repo_root / ".github/workflows/abd-stage0-validation.yml"),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s00-stage-review-rollback-") as directory:
        temporary = Path(directory)
        for index, (label, source) in enumerate(artifacts):
            expected_hash = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted_hash = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored_hash = sha256_file(active)
            results[label] = {
                "status": "PASS" if corrupted_hash != expected_hash and restored_hash == expected_hash else "FAIL",
                "signed_sha256": expected_hash,
                "corrupted_sha256": corrupted_hash,
                "restored_sha256": restored_hash,
            }
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-STAGE-REVIEW-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_STAGE_REVIEW_CONTRACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    repo_root = root.parent
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/authorization_matrix.json"),
        Path("machine/facts/default_decisions.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/dependency_budget.lock"),
        Path("machine/facts/degraded_mode_contract.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("machine/facts/roadmap.json"),
        Path("machine/evidence/EVD-S00-P01.json"),
        Path("machine/evidence/EVD-S00-P02.json"),
        Path("machine/evidence/EVD-S00-P03.json"),
        Path("machine/evidence/EVD-S00-P04.json"),
        Path("machine/tools/normalize_junit.py"),
        Path("machine/tools/scan_paid_dependencies.py"),
        Path("machine/tools/update_artifact_manifest.py"),
        Path("machine/tools/validate_pack.py"),
        Path("tests/S00/stage_review_test.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    for relative in REPO_WORKFLOW_PATHS:
        result[relative] = sha256_file(repo_root / relative)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S00-STAGE-REVIEW-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
            "external_state_changed": False,
        }
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "S00_REVIEW_BLOCKED_FAIL_CLOSED"
        result["stage_status"] = "S00_REVIEW_FAILED"
        result["next"] = "S00/STAGE_REVIEW_REMEDIATION_REQUIRED"

    rollback_bytes = _json_bytes(rollback)
    contract = strict_json_load(root / CONTRACT_PATH)
    findings = strict_json_load(root / FINDINGS_PATH)
    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S00-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "stage_goal": "冻结版本、范围、默认决策、零新增预算和所有开发前置，使后续任务自动推进。",
        "phase_completion": {
            "phase_ids": ["P01", "P02", "P03", "P04"],
            "phase_evidence_status": "PASS",
            "phase_count": 4,
            "task_count": 12,
        },
        "review_findings": findings.get("summary"),
        "validation": result,
        "source_receipts": contract.get("supplied_source_receipts"),
        "hashes": {
            "inputs": input_hashes,
            "parameters": input_hashes.get("machine/facts/parameters.json"),
            "code": _current_code_hash(root),
            "model": None,
            "model_not_applicable_reason": "Stage 0 freezes facts, authority, budget and optional consent; no model artifact exists yet.",
            "rollback_evidence": _sha256_bytes(rollback_bytes),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S00/stage_review_test.py --junitxml=machine/evidence/S00/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S00/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S00/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S00 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {
            "artifact": ROLLBACK_EVIDENCE_PATH.as_posix(),
            "status": rollback.get("status"),
        },
        "upload_gate": {
            "local_preconditions_status": "PASS" if result["status"] == "PASS" else "FAIL",
            "remote_ci_status": "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD",
            "github_upload_performed_by_review": False,
            "remote_result_must_be_verified_before_s01": True,
        },
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "explicit_unknowns": [
            "GitHub Actions has not run on this candidate before the authorized Stage upload.",
            "No Gmail, OVH, Cloudflare, betting-platform account, credential, quota or production runtime was accessed by Stage 0 review.",
            "No production deployment, live recommendation, real order or actual-return validation is claimed.",
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
    matching = [row for row in rows if row.get("id") == "INDEX-S00-STAGE-REVIEW"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-S00-STAGE-REVIEW row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S00/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S00/STAGE_REVIEW_REMEDIATION_REQUIRED"
    data = b"".join(
        (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for item in rows
    )
    _atomic_write(path, data)


def write_stage_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
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
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.relative_to(root).as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }
