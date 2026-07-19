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

from .canonical_facts import sha256_file, strict_json_load
from .delivery import verify_stage0_delivery
from .model_risk_research import (
    evaluate_contract as evaluate_p02,
    verify_existing_phase_evidence as verify_p02,
)
from .official_platform_research import (
    evaluate_contract as evaluate_p01,
    verify_existing_phase_evidence as verify_p01,
)
from .open_source_reuse import (
    evaluate_contract as evaluate_p03,
    verify_existing_phase_evidence as verify_p03,
)
from .research_gap_audit import (
    evaluate_contract as evaluate_p04,
    verify_existing_phase_evidence as verify_p04,
)
from .stage1_delivery import verify_stage1_delivery


CONTRACT_ID = "STAGE-REVIEW-S02"
REVIEW_ID = "ABD-S02-WHOLE-STAGE-REVIEW"
STAGE_ID = "S02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-20T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

CONTRACT_PATH = Path("machine/facts/stage2_review_contract.json")
FINDINGS_PATH = Path("machine/evidence/S02/STAGE_REVIEW/findings.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S02_STAGE_REVIEW.json")
TEST_PATH = Path("tests/S02/stage_review_test.py")
JUNIT_PATH = Path("machine/evidence/S02/STAGE_REVIEW/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S02/STAGE_REVIEW/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S02-STAGE-REVIEW.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

REVIEW_ARTIFACT_HASHES = {
    CONTRACT_PATH.as_posix(): "06db1c9fbc93257ab232f46988860f191aa8efa4c7623e5243ce2a031a441730",
    FINDINGS_PATH.as_posix(): "67237a340447dcd2f651e0fb8f152389ad48be442439ac082cdeb32fae917840",
    FIXTURE_PATH.as_posix(): "f356340ebc9db6907569b1a6b6cbbb308466f7cabd7b4920b61e1078eabd93fa",
}
WORKFLOW_SHA256 = "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d"
DELIVERED_PHASE_COMMIT = "23289557d12a46e1f64ee584af5afc552a2b6023"
PINNED_DELIVERED_CODE_HASH = "a674b8c50b089f8377893d9d25161c993cfe9ad44c86e5ce13f2406cb97e3346"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/__init__.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/stage2_review.py",
    "tests/S02/stage_review_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES = {
    "README.md": "c50ff3be6da031b828ef322eb52311ffc95933aae7c4e180f9a932df64c7b101",
    "abd_acceptance/__init__.py": "969ef9ecfa9c9a05e36167b68da678913439fd7e73ff28bbf92f7fa91a512234",
    "abd_acceptance/__main__.py": "77ed53daf201c59aedd72c9e5d10207997353a5bbd097fa599fd65f9ebb8806a",
    "tests/S02/stage_review_test.py": "40431438418cb4212c00c3e241b980b4188cd017af2722ffb267670a8aa0f124",
}
SUCCESSOR_UNIT_SELF_NORMALIZED_SHA256 = "53c87cf3e90ae5a24661c06ad190e76f6d2d4fb0143a9c107269db69bdc82d5d"

PHASE_EVALUATORS = {"P01": evaluate_p01, "P02": evaluate_p02, "P03": evaluate_p03, "P04": evaluate_p04}
PHASE_VERIFIERS = {"P01": verify_p01, "P02": verify_p02, "P03": verify_p03, "P04": verify_p04}


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


def _load_index(root: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines()
        if line
    ]


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _delivered_phase_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", DELIVERED_PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(root: Path, relative: str, expected_sha256: str) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if _delivered_phase_is_ancestor(root):
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (DELIVERED_PHASE_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if not (root.parent / ".git").exists():
        if relative == "abd_acceptance/stage2_review.py":
            try:
                text = (root / relative).read_text(encoding="utf-8")
                normalized = re.sub(
                    r'(?m)^(SUCCESSOR_UNIT_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
                    r'\1<NORMALIZED>\2',
                    text,
                    count=1,
                )
                return normalized != text and _sha256_bytes(normalized.encode("utf-8")) == SUCCESSOR_UNIT_SELF_NORMALIZED_SHA256
            except Exception:
                return False
        evolved = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        return evolved is not None and (root / relative).is_file() and sha256_file(root / relative) == evolved
    return False


def _historical_code_hash(root: Path) -> str:
    if not _delivered_phase_is_ancestor(root):
        return "UNVERIFIED_UNIT_TEST_HISTORY" if not (root.parent / ".git").exists() else "INVALID_DELIVERED_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", DELIVERED_PHASE_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_DELIVERED_PHASE_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        line for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (DELIVERED_PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_DELIVERED_PHASE_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _code_hash_at_commit(repo_root: Path, commit: str) -> str:
    listing = _git(repo_root, "ls-tree", "-r", "--name-only", commit, "--", "ABD/abd_acceptance")
    if listing.returncode != 0:
        raise RuntimeError(listing.stderr.decode("utf-8", errors="replace").strip())
    paths = sorted(path for path in listing.stdout.decode("utf-8").splitlines() if path.endswith(".py"))
    if not paths:
        raise RuntimeError("no acceptance code at phase commit")
    digest = hashlib.sha256()
    for repo_path in paths:
        blob = _git(repo_root, "show", "%s:%s" % (commit, repo_path))
        if blob.returncode != 0:
            raise RuntimeError(blob.stderr.decode("utf-8", errors="replace").strip())
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    expected = evidence.get("decision_sha256")
    unsigned = deepcopy(dict(evidence))
    unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and _sha256_bytes(_json_bytes(unsigned)) == expected


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    matches = [row for row in rows if row.get(key) == item_id]
    return matches[0] if len(matches) == 1 else {}


def _check_review_pins(root: Path, checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for relative, expected in REVIEW_ARTIFACT_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(
            checks,
            "S02REVIEW-PIN-%s" % Path(relative).stem.upper(),
            actual == expected,
            {"expected": expected, "actual": actual},
        )
    workflow = root.parent / WORKFLOW_PATH
    actual = sha256_file(workflow) if workflow.is_file() else "MISSING"
    hashes[WORKFLOW_PATH.as_posix()] = actual
    _add(checks, "S02REVIEW-PIN-CI-WORKFLOW", actual == WORKFLOW_SHA256, {"expected": WORKFLOW_SHA256, "actual": actual})


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
    _add(checks, "S02REVIEW-CONTRACT-SCOPE-EXACT", scope_ok, scope)

    receipts = {row.get("artifact_label"): row for row in contract.get("supplied_source_receipts", []) if isinstance(row, dict)}
    source_ok = (
        len(receipts) == 2
        and receipts.get("ABD_Roadmap_Stage_Phase_v0.0.0.1.md", {}).get("sha256")
        == "d861c97541de373e55672e7ce7db86def4c46ef8adc5005366705839291423de"
        and receipts.get("ABD_ProductDesign_TaskPack_v0.0.0.1_FINAL.zip", {}).get("sha256")
        == "fd2b86044accbe08cf30e6834e1ebe4523ba310f59170fe2e4cc302d0634ad7f"
        and receipts.get("ABD_ProductDesign_TaskPack_v0.0.0.1_FINAL.zip", {}).get("original_file_count") == 53
    )
    _add(checks, "S02REVIEW-SUPPLIED-SOURCE-RECEIPTS", source_ok, receipts)

    actions = [row for row in authorization.get("actions", []) if isinstance(row, dict) and row.get("id") == "GITHUB_STAGE_UPLOAD"]
    upload = actions[0] if len(actions) == 1 else {}
    upload_ok = (
        len(actions) == 1
        and upload.get("authorization") == "CONDITIONALLY_PREAUTHORIZED"
        and upload.get("effect") == "WRITE_EXTERNAL_REVERSIBLE"
        and upload.get("cash_cost_aud") == "0.00"
        and upload.get("preconditions") == fixture.get("required_upload_preconditions")
        and contract.get("upload_preconditions") == fixture.get("required_upload_preconditions")
        and upload.get("on_precondition_failure") == "KEEP_COMMITS_LOCAL_CONTINUE_STAGE_REMEDIATION"
    )
    _add(checks, "S02REVIEW-GITHUB-UPLOAD-AUTHORIZATION-ALIGNED", upload_ok, upload)

    boundary = contract.get("external_effect_boundary", {})
    boundary_ok = (
        boundary == fixture.get("expected_external_effect_boundary")
        and contract.get("next_on_local_review_pass") == fixture.get("expected_next")
        and contract.get("next_after_verified_remote_upload") == fixture.get("expected_next_after_verified_upload")
    )
    _add(checks, "S02REVIEW-LOCAL-EXTERNAL-EFFECT-BOUNDARY", boundary_ok, boundary)


def _check_baseline_hashes(root: Path, contract: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    expected = contract.get("baseline_critical_artifacts", {})
    errors: List[Any] = []
    if not isinstance(expected, dict) or len(expected) != 24:
        errors.append("expected exactly 24 critical baseline artifacts")
        expected = expected if isinstance(expected, dict) else {}
    for relative, wanted in expected.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        if actual != wanted:
            errors.append({"path": relative, "expected": wanted, "actual": actual})
    _add(checks, "S02REVIEW-BASELINE-CRITICAL-HASHES", not errors, errors or sorted(expected))


def _check_stage_trace(
    contract: Mapping[str, Any],
    fixture: Mapping[str, Any],
    roadmap: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    acceptance: Sequence[Mapping[str, Any]],
    task_graph: Mapping[str, Any],
    traceability: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    stages = [row for row in roadmap.get("stages", []) if isinstance(row, dict) and row.get("id") == STAGE_ID]
    stage = stages[0] if len(stages) == 1 else {}
    phases = stage.get("phases", []) if isinstance(stage, dict) else []
    stage_ok = (
        len(stages) == 1
        and [row.get("id") for row in phases] == fixture.get("expected_phase_ids")
        and stage.get("depends_on") == ["S00"]
        and stage.get("stop_conditions") == contract.get("stage_stop_conditions")
    )
    _add(checks, "S02REVIEW-ROADMAP-STAGE-EXACT", stage_ok, stage)

    reqs = [row for row in requirements if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    acs = [row for row in acceptance if isinstance(row, dict) and str(row.get("id", "")).startswith("AC-S02-")]
    tasks = [row for row in task_graph.get("tasks", []) if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    traces = [row for row in traceability if isinstance(row, dict) and row.get("stage_id") == STAGE_ID]
    sets_ok = (
        [row.get("id") for row in reqs] == fixture.get("expected_requirement_ids")
        and [row.get("id") for row in acs] == fixture.get("expected_acceptance_contract_ids")
        and [row.get("id") for row in tasks] == fixture.get("expected_task_ids")
        and [row.get("requirement_id") for row in traces] == fixture.get("expected_requirement_ids")
    )
    _add(checks, "S02REVIEW-REQ-AC-TASK-TRACE-SETS-EXACT", sets_ok, {"requirements": len(reqs), "acceptance": len(acs), "tasks": len(tasks), "traces": len(traces)})

    phase_by_id = {row.get("id"): row for row in phases}
    req_by_id = {row.get("id"): row for row in reqs}
    ac_by_id = {row.get("id"): row for row in acs}
    trace_by_req = {row.get("requirement_id"): row for row in traces}
    errors = []
    for record in contract.get("phase_records", []):
        phase = phase_by_id.get(record.get("phase_id"), {})
        req = req_by_id.get(record.get("requirement_id"), {})
        ac = ac_by_id.get(record.get("acceptance_contract_id"), {})
        trace = trace_by_req.get(record.get("requirement_id"), {})
        if req.get("phase_id") != record.get("phase_id") or req.get("target") != phase.get("pass_gate"):
            errors.append({"phase": record.get("phase_id"), "route": "requirement_to_phase"})
        if req.get("primary_acceptance_criteria_id") != record.get("acceptance_contract_id"):
            errors.append({"phase": record.get("phase_id"), "route": "requirement_to_acceptance"})
        if ac.get("requirement_id") != record.get("requirement_id") or ac.get("pass_gate") != phase.get("pass_gate"):
            errors.append({"phase": record.get("phase_id"), "route": "acceptance_semantics"})
        if ac.get("oracle", {}).get("type") != "EXECUTABLE" or ac.get("oracle", {}).get("rule") != phase.get("pass_gate"):
            errors.append({"phase": record.get("phase_id"), "route": "executable_oracle"})
        if trace.get("task_ids") != record.get("task_ids") or trace.get("acceptance_criteria_id") != record.get("acceptance_contract_id"):
            errors.append({"phase": record.get("phase_id"), "route": "traceability"})
    _add(checks, "S02REVIEW-SEMANTIC-TRACE-EXACT", not errors, errors or "all aligned")

    task_by_id = {row.get("id"): row for row in tasks}
    task_errors = []
    expected_ids = fixture.get("expected_task_ids", [])
    for index, task_id in enumerate(expected_ids):
        expected_dep = ["T-S00-P04-03"] if index == 0 else [expected_ids[index - 1]]
        task = task_by_id.get(task_id, {})
        if task.get("depends_on") != expected_dep:
            task_errors.append({"task": task_id, "expected": expected_dep, "actual": task.get("depends_on")})
        if task.get("owner_input_required") is not False or task.get("auto_advance_on_pass") is not True:
            task_errors.append({"task": task_id, "reason": "owner_or_auto_advance"})
    _add(checks, "S02REVIEW-TASK-CHAIN-EXACT", not task_errors, task_errors or {"tasks": len(expected_ids)})


def _verify_phase(
    phase_id: str,
    root: Path,
    verify_history: bool,
) -> Dict[str, Any]:
    verifier = PHASE_VERIFIERS[phase_id]
    if phase_id == "P01":
        return verifier(root, verify_git_history=verify_history, verify_successor_state=False)
    if phase_id == "P02":
        return verifier(root, verify_git_history=verify_history, verify_p01_prerequisite=False, verify_successor_state=False)
    if phase_id == "P03":
        return verifier(root, verify_git_history=verify_history, verify_p02_prerequisite=False, verify_successor_state=False)
    return verifier(root, verify_git_history=verify_history, verify_p03_prerequisite=False, verify_successor_state=False)


def _check_phase_evidence_and_history(
    root: Path,
    contract: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: Dict[str, str],
    *,
    verify_history: bool,
) -> None:
    repo_root = root.parent
    receipt_errors: List[Any] = []
    history_errors: List[Any] = []
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
            receipt_errors.append({"phase": phase_id, "reason": "receipt_hash"})
        try:
            verified = _verify_phase(phase_id, root, verify_history)
        except Exception as exc:
            receipt_errors.append({"phase": phase_id, "reason": "%s: %s" % (type(exc).__name__, exc)})
        else:
            if (
                verified.get("status") != "PASS"
                or verified.get("evidence_sha256") != record.get("evidence_sha256")
                or verified.get("rollback_sha256") != record.get("rollback_sha256")
                or verified.get("next") != record.get("expected_next")
            ):
                receipt_errors.append({"phase": phase_id, "summary": verified.get("summary"), "next": verified.get("next")})
        for relative in record.get("required_outputs", []):
            if not (root / relative).is_file():
                receipt_errors.append({"phase": phase_id, "missing": relative})

        if verify_history:
            commit = str(record.get("implementation_commit", ""))
            commits.append(commit)
            if _git(repo_root, "cat-file", "-e", "%s^{commit}" % commit).returncode != 0 or _git(repo_root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
                history_errors.append({"phase": phase_id, "reason": "commit_missing_or_not_ancestor", "commit": commit})
                continue
            try:
                code_hash = _code_hash_at_commit(repo_root, commit)
            except Exception as exc:
                history_errors.append({"phase": phase_id, "reason": "code_hash_error", "detail": str(exc)})
            else:
                if code_hash != record.get("implementation_code_sha256"):
                    history_errors.append({"phase": phase_id, "reason": "code_hash", "actual": code_hash})
            changed = _git(repo_root, "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", commit)
            paths = [item.decode("utf-8") for item in changed.stdout.split(b"\0") if item] if changed.returncode == 0 else []
            allowed = record.get("allowed_commit_paths", [])
            escaped = [path for path in paths if not any(path == prefix or path.startswith(prefix) for prefix in allowed)]
            if not paths or escaped:
                history_errors.append({"phase": phase_id, "reason": "commit_scope", "escaped": escaped})
    if verify_history:
        for previous, current in zip(commits, commits[1:]):
            if _git(repo_root, "merge-base", "--is-ancestor", previous, current).returncode != 0:
                history_errors.append({"reason": "commit_order", "previous": previous, "current": current})
    _add(checks, "S02REVIEW-PHASE-EVIDENCE-ROLLBACK-INDEX", not receipt_errors, receipt_errors or {"phases": 4})
    _add(checks, "S02REVIEW-HISTORICAL-CODE-AND-COMMIT-SCOPE", not history_errors, history_errors or commits if verify_history else "unit profile")


def _check_phase_oracles(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], verify_history: bool) -> None:
    errors = []
    summaries = {}
    minimums = fixture.get("expected_phase_evaluator_min_checks", {})
    for phase_id in fixture.get("expected_phase_ids", []):
        try:
            result = PHASE_EVALUATORS[phase_id](root, require_external_reports=True, _verify_git_history=verify_history)
        except Exception as exc:
            errors.append({"phase": phase_id, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        summary = result.get("summary", {})
        summaries[phase_id] = {"status": result.get("status"), "checks": summary.get("checks"), "failed": summary.get("failed"), "next": result.get("next")}
        if result.get("status") != "PASS" or summary.get("failed") != 0 or int(summary.get("checks", 0)) < int(minimums.get(phase_id, 0)):
            errors.append({"phase": phase_id, "summary": summaries[phase_id]})
    _add(checks, "S02REVIEW-ALL-PHASE-ORACLES-PASS", not errors, errors or summaries)


def _check_research_graph(
    fixture: Mapping[str, Any],
    sources: Mapping[str, Any],
    provider: Mapping[str, Any],
    regulatory: Mapping[str, Any],
    papers: Mapping[str, Any],
    claims: Mapping[str, Any],
    reuse: Mapping[str, Any],
    licenses: Mapping[str, Any],
    gaps: Mapping[str, Any],
    counter: Mapping[str, Any],
    schedule: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    source_ids = [row.get("id") for row in sources.get("sources", []) if isinstance(row, dict)]
    fact_rows = [fact for row in provider.get("providers", []) if isinstance(row, dict) for fact in row.get("facts", []) if isinstance(fact, dict)]
    fact_ids = [row.get("fact_id") for row in fact_rows]
    rule_rows = [row for row in regulatory.get("rules", []) if isinstance(row, dict)]
    rule_ids = [row.get("rule_id") for row in rule_rows]
    paper_rows = [row for row in papers.get("papers", []) if isinstance(row, dict)]
    paper_ids = [row.get("id") for row in paper_rows]
    claim_rows = [row for row in claims.get("claims", []) if isinstance(row, dict)]
    claim_ids = [row.get("id") for row in claim_rows]
    threshold_pointers = [row.get("parameter_pointer") for row in claims.get("local_threshold_inventory", []) if isinstance(row, dict)]
    reuse_rows = [row for row in reuse.get("projects", []) if isinstance(row, dict)]
    reuse_ids = [row.get("source_id") for row in reuse_rows]
    license_rows = [row for row in licenses.get("entries", []) if isinstance(row, dict)]
    license_ids = [row.get("id") for row in license_rows]
    gap_rows = [row for row in gaps.get("gaps", []) if isinstance(row, dict)]
    gap_ids = [row.get("id") for row in gap_rows]
    counter_rows = [row for row in counter.get("records", []) if isinstance(row, dict)]
    counter_ids = [row.get("id") for row in counter_rows]
    review_rows = [row for row in schedule.get("reviews", []) if isinstance(row, dict)]
    review_ids = [row.get("id") for row in review_rows]

    exact_sets = {
        "sources": (source_ids, fixture.get("expected_source_ids")),
        "provider_facts": (fact_ids, fixture.get("expected_provider_fact_ids")),
        "regulatory_rules": (rule_ids, fixture.get("expected_regulatory_rule_ids")),
        "papers": (paper_ids, fixture.get("expected_paper_ids")),
        "model_claims": (claim_ids, fixture.get("expected_model_claim_ids")),
        "thresholds": (threshold_pointers, fixture.get("expected_threshold_pointers")),
        "reuse": (reuse_ids, fixture.get("expected_reuse_source_ids")),
        "licenses": (license_ids, fixture.get("expected_license_ids")),
        "gaps": (gap_ids, fixture.get("expected_gap_ids")),
        "counterevidence": (counter_ids, fixture.get("expected_counterevidence_ids")),
        "reviews": (review_ids, fixture.get("expected_review_ids")),
    }
    set_errors = {label: {"actual": actual, "expected": expected} for label, (actual, expected) in exact_sets.items() if actual != expected or len(actual) != len(set(actual))}
    _add(checks, "S02REVIEW-RESEARCH-ID-SETS-EXACT", not set_errors, set_errors or {label: len(actual) for label, (actual, _) in exact_sets.items()})

    citation_errors = []
    source_set = set(source_ids)
    for row in [*fact_rows, *rule_rows]:
        citations = row.get("citations", [])
        if not citations or any(citation.get("source_id") not in source_set for citation in citations if isinstance(citation, dict)):
            citation_errors.append(row.get("fact_id") or row.get("rule_id"))
    _add(checks, "S02REVIEW-OFFICIAL-FACT-RULE-SOURCE-CITATIONS", not citation_errors, citation_errors or {"facts": len(fact_rows), "rules": len(rule_rows)})

    paper_by_id = {row.get("id"): row for row in paper_rows}
    claim_by_id = {row.get("id"): row for row in claim_rows}
    paper_claim_errors = []
    for paper in paper_rows:
        if not paper.get("claim_ids") or any(claim_id not in claim_by_id for claim_id in paper.get("claim_ids", [])):
            paper_claim_errors.append({"paper": paper.get("id"), "reason": "claim_route"})
        for claim_id in paper.get("claim_ids", []):
            cited = {citation.get("paper_id") for citation in claim_by_id.get(claim_id, {}).get("citations", []) if isinstance(citation, dict)}
            if paper.get("id") not in cited:
                paper_claim_errors.append({"paper": paper.get("id"), "claim": claim_id, "reason": "not_reciprocal"})
    for claim in claim_rows:
        citations = claim.get("citations", [])
        if not citations or any(citation.get("paper_id") not in paper_by_id for citation in citations if isinstance(citation, dict)):
            paper_claim_errors.append({"claim": claim.get("id"), "reason": "paper_route"})
    _add(checks, "S02REVIEW-PAPER-CLAIM-RECIPROCAL-GRAPH", not paper_claim_errors, paper_claim_errors or {"papers": len(paper_rows), "claims": len(claim_rows)})

    license_by_id = {row.get("id"): row for row in license_rows}
    reuse_errors = []
    for project in reuse_rows:
        license_id = project.get("license_evidence_id")
        license_row = license_by_id.get(license_id, {})
        if license_row.get("source_id") != project.get("source_id") or license_row.get("pinned_commit") != project.get("pinned_commit"):
            reuse_errors.append(project.get("source_id"))
    if {row.get("source_id") for row in license_rows} != set(reuse_ids):
        reuse_errors.append("license_source_set")
    _add(checks, "S02REVIEW-REUSE-LICENSE-BIJECTION", not reuse_errors, reuse_errors or reuse_ids)

    special_refs = {
        "canonical_facts.json#/scope/discovery_scope",
        "conflict_assessment",
        "costs.json#/future_source_admission_policy",
        "license_inventory.json#/policy",
        "parameters.json#/numeric_determinism",
        "parameters.json#/target_30pct",
        "provider_facts_snapshot.json#/fact_semantics",
        "research_evidence_matrix.json#/research_mode",
        "runtime_prerequisite_state",
    }
    valid_refs = set(fact_ids) | set(rule_ids) | set(claim_ids) | set(reuse_ids) | set(license_ids) | special_refs
    all_gap_refs = [ref for gap in gap_rows for ref in gap.get("source_refs", [])]
    gap_ref_errors = [ref for ref in all_gap_refs if ref not in valid_refs]
    expected_ref_count = int(fixture.get("expected_item_counts", {}).get("gap_source_references", 0))
    _add(checks, "S02REVIEW-ALL-GAP-SOURCE-REFS-RESOLVE", not gap_ref_errors and len(all_gap_refs) == expected_ref_count, gap_ref_errors or {"references": len(all_gap_refs), "expected": expected_ref_count})

    gap_set = set(gap_ids)
    review_set = set(review_ids)
    gap_errors = []
    for gap in gap_rows:
        gap_id = gap.get("id")
        direct_counter = [row.get("id") for row in counter_rows if gap_id in row.get("gap_ids", [])]
        routed_reviews = [review_id for review_id in gap.get("review_ids", []) if review_id in review_set]
        schedule_reviews = [row.get("id") for row in review_rows if gap_id in row.get("gap_ids", [])]
        if gap.get("gap_state") != "OPEN_EXPLICIT" or not gap.get("safe_default") or not direct_counter or set(routed_reviews) != set(gap.get("review_ids", [])) or not schedule_reviews:
            gap_errors.append({"gap": gap_id, "counter": direct_counter, "reviews": routed_reviews, "scheduled": schedule_reviews})
    route_errors = []
    for row in counter_rows:
        if not row.get("gap_ids") or not set(row.get("gap_ids", [])).issubset(gap_set) or not row.get("safe_default") or not set(row.get("review_ids", [])).issubset(review_set):
            route_errors.append(row.get("id"))
    for row in review_rows:
        if not row.get("gap_ids") or not set(row.get("gap_ids", [])).issubset(gap_set) or row.get("current_status") in {"PASS", "COMPLETE", "EXECUTED"}:
            route_errors.append(row.get("id"))
    _add(checks, "S02REVIEW-ALL-26-GAPS-SAFE-COUNTER-REVIEW-ROUTED", not gap_errors and not route_errors, {"gap_errors": gap_errors, "route_errors": route_errors} if gap_errors or route_errors else {"gaps": 26, "counterevidence": 22, "reviews": 12})

    summaries_ok = (
        gaps.get("coverage_summary", {}).get("open_gap_count") == 26
        and gaps.get("coverage_summary", {}).get("resolved_gap_count") == 0
        and gaps.get("coverage_summary", {}).get("silent_gap_count") == 0
        and counter.get("summary", {}).get("gap_with_counterevidence_count") == 26
        and counter.get("summary", {}).get("gap_without_counterevidence_count") == 0
        and schedule.get("coverage_summary", {}).get("gap_without_any_review_route_count") == 0
        and schedule.get("coverage_summary", {}).get("current_phase_reviews_executed") == 0
    )
    _add(checks, "S02REVIEW-GAP-COUNTER-REVIEW-SUMMARIES-EXACT", summaries_ok, {"gaps": gaps.get("coverage_summary"), "counter": counter.get("summary"), "review": schedule.get("coverage_summary")})


def _check_safety_and_progression(
    root: Path,
    canonical: Mapping[str, Any],
    parameters: Mapping[str, Any],
    costs: Mapping[str, Any],
    authorization: Mapping[str, Any],
    provider_contracts: Mapping[str, Any],
    stage_artifacts: Sequence[Mapping[str, Any]],
    checks: List[Dict[str, Any]],
) -> None:
    real_order = _row(authorization.get("actions", []), "REAL_ORDER_SUBMISSION")
    baseline_ok = (
        canonical.get("product", {}).get("initial_bankroll_aud") == "300.00"
        and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00"
        and canonical.get("scope", {}).get("product_role") == "ANALYSIS_AND_ADVICE_ONLY"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
        and parameters.get("numeric_determinism", {}).get("boundary_perturbation_absolute_probability") == "0.0001"
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and real_order.get("authorization") == "PROHIBITED"
        and real_order.get("capability_status") == "MODULE_MUST_NOT_EXIST"
    )
    _add(checks, "S02REVIEW-A300-A0-ADVICE-ONLY-NO-ORDER", baseline_ok, {"product": canonical.get("product"), "scope": canonical.get("scope"), "real_order": real_order})

    provider_rows = provider_contracts.get("providers", [])
    capability_rows = provider_contracts.get("capabilities", [])
    authenticated = next((row for row in capability_rows if row.get("mode") == "AUTHENTICATED_OBSERVER"), {})
    provider_ok = (
        len(provider_rows) == 3
        and all(row.get("order_submission") == "NOT_PRESENT" for row in provider_rows)
        and all(row.get("background_public_page_collection") == "SOURCE_CONTRACT_DEPENDENT" for row in provider_rows)
        and authenticated.get("default") == "OFF"
        and "无订单能力" in authenticated.get("requirements", [])
    )
    _add(checks, "S02REVIEW-PROVIDER-CONTRACTS-PRESENT-UNVERIFIED-FAIL-CLOSED", provider_ok, {"providers": len(provider_rows), "authenticated_observer": authenticated})

    boundary_errors = []
    for artifact in stage_artifacts:
        boundary = artifact.get("external_effect_boundary")
        if boundary is None:
            boundary = artifact.get("s02_p01_execution_boundary", {})
        if not isinstance(boundary, dict):
            continue
        for key, value in boundary.items():
            if key == "incremental_cash_spent_aud" and value != "0.00":
                boundary_errors.append({"key": key, "value": value})
            if value is True and any(token in key for token in ("access", "called", "installed", "cloned", "executed", "deployed", "order", "return", "guarantee", "upload", "started")):
                boundary_errors.append({"key": key, "value": value})
    _add(checks, "S02REVIEW-NO-RUNTIME-ACCOUNT-MODEL-DEPLOY-ORDER-RETURN-EFFECT", not boundary_errors, boundary_errors or "all stage boundaries false")

    try:
        stage0 = verify_stage0_delivery(root)
        stage1 = verify_stage1_delivery(root)
        delivery_ok = stage0.get("status") == "PASS" and stage1.get("status") == "PASS"
        delivery_detail: Any = {"S00": stage0.get("status"), "S01": stage1.get("status")}
    except Exception as exc:
        delivery_ok = False
        delivery_detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02REVIEW-PREDECESSOR-STAGE-DELIVERIES-VERIFIED", delivery_ok, delivery_detail)

    try:
        rows = _load_index(root)
        s03 = [row for row in rows if str(row.get("id", "")).startswith("INDEX-AC-S03-")]
        actual_s03 = sorted(path.name for path in (root / "machine/evidence").glob("EVD-S03-*.json"))
        review_rows = [row for row in rows if row.get("id") == "INDEX-S02-STAGE-REVIEW"]
        progression_ok = (
            len(review_rows) == 1
            and review_rows[0].get("status") in {"PLANNED", "PASS"}
            and len(s03) == 4
            and all(row.get("status") == "PLANNED" and "actual_artifact" not in row for row in s03)
            and not actual_s03
        )
        detail = {
            "review_route": "PLANNED_OR_SIGNED_PASS",
            "s03": [row.get("status") for row in s03],
            "actual_s03": actual_s03,
        }
    except Exception as exc:
        progression_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S02REVIEW-S03-NOT-STARTED", progression_ok, detail)


def _check_findings(findings: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    rows = findings.get("findings", [])
    errors = []
    if [row.get("id") for row in rows if isinstance(row, dict)] != fixture.get("expected_review_finding_ids"):
        errors.append("finding id set")
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "RESOLVED_IN_REVIEW_CANDIDATE" or not row.get("evidence") or not row.get("resolution"):
            errors.append(row)
    summary = findings.get("summary", {})
    if summary != {"total": 4, "resolved_in_review_candidate": 4, "open": 0, "remote_ci_pending_is_upload_evidence_not_an_open_code_finding": True}:
        errors.append({"summary": summary})
    boundary = findings.get("scope_boundaries", {})
    if boundary != {
        "s03_started": False,
        "external_account_or_api_accessed": False,
        "secret_provisioned": False,
        "incremental_cash_spent_aud": "0.00",
        "network_research_performed": False,
        "model_or_strategy_executed": False,
        "production_or_return_claimed": False,
        "real_order_submitted": False,
        "github_upload_performed": False,
    }:
        errors.append({"scope_boundaries": boundary})
    _add(checks, "S02REVIEW-FINDINGS-ALL-RESOLVED", not errors, errors or summary)


def _iter_text_files(root: Path) -> Iterable[Path]:
    excluded = {".git", ".venv", ".pytest_cache", "__pycache__"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or excluded.intersection(path.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        yield path


def _check_integration_and_security(root: Path, contract: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        workflow = (root.parent / WORKFLOW_PATH).read_text(encoding="utf-8")
        main_text = (root / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
        init_text = (root / "abd_acceptance/__init__.py").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, "S02REVIEW-INTEGRATION-FILES-AVAILABLE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    _add(checks, "S02REVIEW-INTEGRATION-FILES-AVAILABLE", True, "workflow, CLI, package and README")

    refs = re.findall(r"^\s*-\s+uses:\s+[^@\s]+@([^\s#]+)", workflow, flags=re.MULTILINE)
    expected_refs = set(contract.get("repository_integration", {}).get("pinned_actions", {}).values())
    pins_ok = len(refs) == 3 and set(refs) == expected_refs and all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)
    _add(checks, "S02REVIEW-CI-SUPPLY-CHAIN-PINS", pins_ok, refs)
    missing = [command for command in fixture.get("required_workflow_commands", []) if command not in workflow]
    workflow_ok = (
        not missing
        and "runs-on: ubuntu-latest" in workflow
        and "timeout-minutes: 15" in workflow
        and "permissions:\n  contents: read" in workflow
        and ("$" + "{{ secrets.") not in workflow
    )
    _add(checks, "S02REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED", workflow_ok, missing or "all required commands present")

    historical_readme_route = (
        TEST_PATH.as_posix() in readme
        and "STAGE-REVIEW-S02" in readme
        and "S02/GITHUB_STAGE_UPLOAD_READY" in readme
        and "S03" in readme
        and "尚未上传" in readme
    )
    successor_readme_route = (
        "Stage 2 已通过 GitHub PR #65" in readme
        and "tests/S03/P01_test.py" in readme
        and "AC-S03-P01" in readme
        and "S03/P02_READY_NOT_STARTED" in readme
        and "本 Phase 仅本地开发" in readme
    )
    registration_ok = (
        re.search(r'["\']STAGE-REVIEW-S02["\']\s*:\s*write_stage2_review_evidence', main_text) is not None
        and "stage2_review" in init_text
        and (historical_readme_route or successor_readme_route)
    )
    _add(checks, "S02REVIEW-CLI-TEST-README-REPLAY-ROUTED", registration_ok, {"test": (root / TEST_PATH).is_file(), "cli": "STAGE-REVIEW-S02" in main_text})

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
    _add(checks, "S02REVIEW-SECRET-AND-LOCAL-PATH-SCAN", not matches, matches or "none")


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
            if element.attrib.get("hostname") is not None or element.attrib.get("timestamp") != JUNIT_FIXED_CLOCK or element.attrib.get("time") != "0.000":
                return False
        elif element.tag == "testcase" and element.attrib.get("time") != "0.000":
            return False
    return True


def _check_runtime_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: Dict[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S02REVIEW-TEST-TARGETED-PASS", JUNIT_PATH, int(fixture.get("expected_targeted_test_minimum", 0))),
        ("S02REVIEW-TEST-FULL-REGRESSION-PASS", FULL_JUNIT_PATH, int(fixture.get("expected_full_regression_test_minimum", 0))),
    ]:
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            passed = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and normalized
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, check_id, passed, {**summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))

    report = _safe_load(root / PACK_REPORT_PATH, checks, "S02REVIEW-PACK-REPORT-PARSE")
    report_ok = isinstance(report, dict) and report.get("status") == "PASS" and report.get("summary", {}).get("checks") == 49 and report.get("summary", {}).get("failed") == 0
    _add(checks, "S02REVIEW-TASKPACK-49-GATES-PASS", report_ok, report.get("summary") if isinstance(report, dict) else "unavailable")
    if (root / PACK_REPORT_PATH).is_file():
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        passed = "STATUS: PASS" in scan and "MAX_INCREMENTAL_CASH_AUD: 0.00" in scan and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan and "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false" in scan
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
        _add(checks, "S02REVIEW-PAID-DEPENDENCY-SCAN-PASS", passed, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S02REVIEW-PAID-DEPENDENCY-SCAN-PASS", False, "%s: %s" % (type(exc).__name__, exc))


def _build_result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "S02_WHOLE_STAGE_REVIEW_PASS" if status == "PASS" else "S02_REVIEW_BLOCKED_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": sum(1 for row in checks if row["passed"]), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "stage_status": "S02_REVIEW_PASS_REMOTE_UPLOAD_PENDING" if status == "PASS" else "S02_REVIEW_FAILED",
        "remote_ci_status": "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD",
        "release_status": "NOT_READY",
        "next": "S02/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S02/STAGE_REVIEW_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    contract = _safe_load(root / CONTRACT_PATH, checks, "S02REVIEW-PREFLIGHT-CONTRACT-PARSE")
    findings = _safe_load(root / FINDINGS_PATH, checks, "S02REVIEW-PREFLIGHT-FINDINGS-PARSE")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S02REVIEW-PREFLIGHT-FIXTURE-PARSE")
    _check_review_pins(root, checks, hashes)
    if isinstance(contract, dict) and isinstance(findings, dict) and isinstance(fixture, dict):
        shape_ok = (
            contract.get("review_id") == REVIEW_ID
            and contract.get("stage_id") == STAGE_ID
            and contract.get("fixed_at") == FIXED_CLOCK
            and fixture.get("review_id") == REVIEW_ID
            and findings.get("review_id") == REVIEW_ID
            and findings.get("summary", {}).get("open") == 0
            and contract.get("next_on_local_review_pass") == "S02/GITHUB_STAGE_UPLOAD_READY"
        )
        _add(checks, "S02REVIEW-PREFLIGHT-SHAPE-EXACT", shape_ok, REVIEW_ID)
    else:
        _add(checks, "S02REVIEW-PREFLIGHT-SHAPE-EXACT", False, "required candidate objects unavailable")
    required = [TEST_PATH, Path("abd_acceptance/stage2_review.py")]
    _add(checks, "S02REVIEW-PREFLIGHT-EXECUTABLES-PRESENT", all((root / path).is_file() for path in required), [path.as_posix() for path in required])
    try:
        rows = _load_index(root)
        matching = [row for row in rows if row.get("id") == "INDEX-S02-STAGE-REVIEW"]
        index_ok = len(matching) == 1 and matching[0].get("status") == "PLANNED" and "actual_artifact" not in matching[0] and "artifact_sha256" not in matching[0]
        _add(checks, "S02REVIEW-PREFLIGHT-INDEX-PLANNED", index_ok, matching)
    except Exception as exc:
        _add(checks, "S02REVIEW-PREFLIGHT-INDEX-PLANNED", False, "%s: %s" % (type(exc).__name__, exc))
    signed_absent = not (root / EVIDENCE_PATH).exists() and not (root / ROLLBACK_EVIDENCE_PATH).exists()
    _add(checks, "S02REVIEW-PREFLIGHT-NOT-YET-SIGNED", signed_absent, {"evidence": (root / EVIDENCE_PATH).exists(), "rollback": (root / ROLLBACK_EVIDENCE_PATH).exists()})
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S02_REVIEW_CANDIDATE_PREFLIGHT_PASS" if not failed else "S02_REVIEW_CANDIDATE_INVALID", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "hashes": hashes, "next": "S02/STAGE_REVIEW_CANDIDATE" if not failed else "S02/P04_REMEDIATION_REQUIRED"}


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_history: bool = True,
    _verify_phase_oracles: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    paths = {
        "contract": (CONTRACT_PATH, "S02REVIEW-INPUT-CONTRACT-PARSE"),
        "findings": (FINDINGS_PATH, "S02REVIEW-INPUT-FINDINGS-PARSE"),
        "fixture": (FIXTURE_PATH, "S02REVIEW-INPUT-FIXTURE-PARSE"),
        "roadmap": (Path("machine/facts/roadmap.json"), "S02REVIEW-INPUT-ROADMAP-PARSE"),
        "requirements": (Path("machine/facts/requirements.json"), "S02REVIEW-INPUT-REQUIREMENTS-PARSE"),
        "acceptance": (Path("machine/facts/acceptance_contracts.json"), "S02REVIEW-INPUT-ACCEPTANCE-PARSE"),
        "task_graph": (Path("machine/facts/task_graph.json"), "S02REVIEW-INPUT-TASK-GRAPH-PARSE"),
        "traceability": (Path("machine/facts/traceability_matrix.json"), "S02REVIEW-INPUT-TRACEABILITY-PARSE"),
        "authorization": (Path("machine/facts/authorization_matrix.json"), "S02REVIEW-INPUT-AUTHORIZATION-PARSE"),
        "canonical": (Path("machine/facts/canonical_facts.json"), "S02REVIEW-INPUT-CANONICAL-PARSE"),
        "parameters": (Path("machine/facts/parameters.json"), "S02REVIEW-INPUT-PARAMETERS-PARSE"),
        "costs": (Path("machine/facts/costs.json"), "S02REVIEW-INPUT-COSTS-PARSE"),
        "provider_contracts": (Path("machine/facts/provider_contracts.json"), "S02REVIEW-INPUT-PROVIDER-CONTRACTS-PARSE"),
        "sources": (Path("sources.json"), "S02REVIEW-INPUT-SOURCES-PARSE"),
        "provider": (Path("provider_facts_snapshot.json"), "S02REVIEW-INPUT-PROVIDER-PARSE"),
        "regulatory": (Path("regulatory_matrix.json"), "S02REVIEW-INPUT-REGULATORY-PARSE"),
        "papers": (Path("research_evidence_matrix.json"), "S02REVIEW-INPUT-PAPERS-PARSE"),
        "claims": (Path("model_claims.json"), "S02REVIEW-INPUT-CLAIMS-PARSE"),
        "reuse": (Path("research_reuse_matrix.json"), "S02REVIEW-INPUT-REUSE-PARSE"),
        "licenses": (Path("license_inventory.json"), "S02REVIEW-INPUT-LICENSES-PARSE"),
        "gaps": (Path("research_gaps.json"), "S02REVIEW-INPUT-GAPS-PARSE"),
        "counter": (Path("counterevidence.json"), "S02REVIEW-INPUT-COUNTER-PARSE"),
        "schedule": (Path("review_schedule.json"), "S02REVIEW-INPUT-SCHEDULE-PARSE"),
    }
    values = {name: _safe_load(root / relative, checks, check_id) for name, (relative, check_id) in paths.items()}
    _check_review_pins(root, checks, hashes)
    object_names = set(paths) - {"requirements", "acceptance", "traceability"}
    if not all(isinstance(values[name], dict) for name in object_names) or not all(isinstance(values[name], list) for name in {"requirements", "acceptance", "traceability"}):
        _add(checks, "S02REVIEW-INPUTS-STRUCTURALLY-AVAILABLE", False, "one or more required inputs unavailable")
        return _build_result(checks, hashes)
    _add(checks, "S02REVIEW-INPUTS-STRUCTURALLY-AVAILABLE", True, "all parsed")

    _check_contract_shape(values["contract"], values["fixture"], values["authorization"], checks)
    _check_baseline_hashes(root, values["contract"], checks, hashes)
    _check_stage_trace(values["contract"], values["fixture"], values["roadmap"], values["requirements"], values["acceptance"], values["task_graph"], values["traceability"], checks)
    _check_phase_evidence_and_history(root, values["contract"], checks, hashes, verify_history=_verify_history)
    if _verify_phase_oracles:
        _check_phase_oracles(root, values["fixture"], checks, _verify_history)
    _check_research_graph(values["fixture"], values["sources"], values["provider"], values["regulatory"], values["papers"], values["claims"], values["reuse"], values["licenses"], values["gaps"], values["counter"], values["schedule"], checks)
    _check_safety_and_progression(root, values["canonical"], values["parameters"], values["costs"], values["authorization"], values["provider_contracts"], [values[name] for name in ["sources", "provider", "regulatory", "papers", "claims", "reuse", "licenses", "gaps", "counter", "schedule"]], checks)
    _check_findings(values["findings"], values["fixture"], checks)
    _check_integration_and_security(root, values["contract"], values["fixture"], checks)
    if require_external_reports:
        _check_runtime_reports(root, values["fixture"], checks, hashes)
    result = _build_result(checks, hashes)
    minimum = int(values["fixture"].get("expected_review_oracle_check_minimum", 0))
    if result["summary"]["checks"] < minimum:
        _add(checks, "S02REVIEW-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
        result = _build_result(checks, hashes)
    return result


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    paths = [
        CONTRACT_PATH,
        FINDINGS_PATH,
        FIXTURE_PATH,
        Path("sources.json"),
        Path("provider_facts_snapshot.json"),
        Path("regulatory_matrix.json"),
        Path("research_evidence_matrix.json"),
        Path("model_claims.json"),
        Path("research_reuse_matrix.json"),
        Path("license_inventory.json"),
        Path("research_gaps.json"),
        Path("counterevidence.json"),
        Path("review_schedule.json"),
    ]
    results = {}
    with tempfile.TemporaryDirectory(prefix="abd-s02-stage-review-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(paths):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%d" % index)
            active = temporary / ("active-%d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored = sha256_file(active)
            results[relative.as_posix()] = {"status": "PASS" if corrupted != expected and restored == expected else "FAIL", "signed_sha256": expected, "corrupted_sha256": corrupted, "restored_sha256": restored}
    status = "PASS" if all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {"schema_version": "1.0.0", "evidence_id": "EVD-S02-STAGE-REVIEW-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "mode": "EPHEMERAL_SIGNED_STAGE2_RESEARCH_REVIEW_RESTORE", "status": status, "artifacts": results, "production_state_changed": False, "external_state_changed": False}


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH, TEST_PATH, Path("README.md"),
        Path("sources.json"), Path("provider_facts_snapshot.json"), Path("regulatory_matrix.json"),
        Path("research_evidence_matrix.json"), Path("model_claims.json"), Path("research_reuse_matrix.json"),
        Path("license_inventory.json"), Path("research_gaps.json"), Path("counterevidence.json"), Path("review_schedule.json"),
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/authorization_matrix.json"), Path("machine/facts/provider_contracts.json"),
        Path("machine/facts/roadmap.json"), Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"), Path("machine/facts/traceability_matrix.json"),
        Path("machine/evidence/EVD-S02-P01.json"), Path("machine/evidence/EVD-S02-P01_rollback.json"),
        Path("machine/evidence/EVD-S02-P02.json"), Path("machine/evidence/EVD-S02-P02_rollback.json"),
        Path("machine/evidence/EVD-S02-P03.json"), Path("machine/evidence/EVD-S02-P03_rollback.json"),
        Path("machine/evidence/EVD-S02-P04.json"), Path("machine/evidence/EVD-S02-P04_rollback.json"),
        Path("abd_acceptance/stage2_review.py"), Path("abd_acceptance/__main__.py"), Path("abd_acceptance/__init__.py"),
        Path("machine/tools/normalize_junit.py"), Path("machine/tools/scan_paid_dependencies.py"),
        Path("machine/tools/update_artifact_manifest.py"), Path("machine/tools/validate_pack.py"),
    ]
    result = {path.as_posix(): sha256_file(root / path) for path in paths}
    result[WORKFLOW_PATH.as_posix()] = sha256_file(root.parent / WORKFLOW_PATH)
    return result


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    result = evaluate_contract(root, require_external_reports=require_external_reports)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {"schema_version": "1.0.0", "evidence_id": "EVD-S02-STAGE-REVIEW-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc), "production_state_changed": False, "external_state_changed": False}
    if rollback.get("status") != "PASS":
        result["status"] = "FAIL"
        result["decision"] = "S02_REVIEW_BLOCKED_FAIL_CLOSED"
        result["stage_status"] = "S02_REVIEW_FAILED"
        result["next"] = "S02/STAGE_REVIEW_REMEDIATION_REQUIRED"
    rollback_bytes = _json_bytes(rollback)
    contract = strict_json_load(root / CONTRACT_PATH)
    findings = strict_json_load(root / FINDINGS_PATH)
    input_hashes = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S02-STAGE-REVIEW",
        "contract_id": CONTRACT_ID,
        "review_id": REVIEW_ID,
        "stage_id": STAGE_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": result["status"],
        "decision": result["decision"],
        "stage_goal": "冻结官方平台、监管、模型风险论文、开源复用、研究缺口、反证与复审路线；不把研究写成账户授权、生产能力或收益证明。",
        "phase_completion": {"phase_ids": ["P01", "P02", "P03", "P04"], "phase_evidence_status": "PASS", "phase_count": 4, "task_count": 12, "source_count": 24, "provider_fact_count": 23, "regulatory_rule_count": 9, "paper_count": 8, "model_claim_count": 14, "reuse_project_count": 6, "gap_count": 26, "counterevidence_count": 22, "review_route_count": 12},
        "review_findings": findings.get("summary"),
        "validation": result,
        "source_receipts": contract.get("supplied_source_receipts"),
        "hashes": {"inputs": input_hashes, "parameters": input_hashes.get("machine/facts/parameters.json"), "code": _current_code_hash(root), "model": None, "model_not_applicable_reason": "Stage 2 review validates research contracts and evidence graphs; no prediction model or strategy was executed.", "rollback_evidence": _sha256_bytes(rollback_bytes)},
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S02/stage_review_test.py --junitxml=machine/evidence/S02/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/STAGE_REVIEW/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S02/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S02/STAGE_REVIEW/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "upload_gate": {"local_preconditions_status": "PASS" if result["status"] == "PASS" else "FAIL", "remote_ci_status": "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD", "github_upload_performed_by_review": False, "remote_result_must_be_verified_before_s03": True},
        "external_effect_boundary": contract.get("external_effect_boundary"),
        "explicit_unknowns": [
            "GitHub Actions has not run on this candidate before the authorized Stage 2 upload.",
            "No TAB, Gmail, OVH, Cloudflare, betting-platform or cloud account, credential, quota, billing or production runtime was accessed by this review.",
            "No network research, package installation, repository clone, model execution, backtest, production deployment, live recommendation or real order was performed.",
            "All 26 research gaps remain open and non-pass; registration, counterevidence and review routing do not resolve them.",
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
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-S02-STAGE-REVIEW"]
    if len(matching) != 1:
        raise ValueError("expected exactly one INDEX-S02-STAGE-REVIEW row, found %d" % len(matching))
    row = matching[0]
    row["status"] = status
    row["actual_artifact"] = EVIDENCE_PATH.as_posix()
    row["artifact_sha256"] = evidence_hash
    row["verified_at"] = FIXED_CLOCK
    row["next"] = "S02/GITHUB_STAGE_UPLOAD_READY" if status == "PASS" else "S02/STAGE_REVIEW_REMEDIATION_REQUIRED"
    payload = b"".join((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for item in rows)
    _atomic_write(root / EVIDENCE_INDEX_PATH, payload)


def write_stage2_review_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
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


def verify_existing_stage_review_evidence(root: Path, *, verify_phase_prerequisites: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S02REVIEW-RECEIPT-EVIDENCE-PARSE")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S02REVIEW-RECEIPT-ROLLBACK-PARSE")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, dict):
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S02-STAGE-REVIEW"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("review_id") == REVIEW_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "S02_WHOLE_STAGE_REVIEW_PASS"
            and evidence.get("stage_status") == "S02_REVIEW_PASS_REMOTE_UPLOAD_PENDING"
            and evidence.get("release_status") == "NOT_READY"
            and evidence.get("next") == "S02/GITHUB_STAGE_UPLOAD_READY"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S02REVIEW-RECEIPT-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = validation.get("status") == "PASS" and validation.get("decision") == "S02_WHOLE_STAGE_REVIEW_PASS" and validation.get("summary", {}).get("failed") == 0 and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S02REVIEW-RECEIPT-VALIDATION-ALL-PASS", validation_ok, validation.get("summary"))
        effects = evidence.get("external_effect_boundary", {})
        _add(checks, "S02REVIEW-RECEIPT-NO-EXTERNAL-EFFECT", effects == strict_json_load(root / FIXTURE_PATH).get("expected_external_effect_boundary"), effects)
        input_errors = []
        historical_inputs = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "reason": "unsafe path"})
                continue
            path = root.parent / candidate if relative.startswith(".github/") else root / candidate
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected:
                if _historical_file_matches(root, relative, expected):
                    historical_inputs.append(relative)
                else:
                    input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(
            checks,
            "S02REVIEW-RECEIPT-SIGNED-INPUTS-CURRENT",
            not input_errors,
            input_errors or {
                "current": len(evidence.get("hashes", {}).get("inputs", {})) - len(historical_inputs),
                "historical_delivered_commit": historical_inputs,
            },
        )
        reports = []
        for relative in [JUNIT_PATH, FULL_JUNIT_PATH, PACK_REPORT_PATH, SCAN_REPORT_PATH]:
            expected = validation.get("hashes", {}).get(relative.as_posix())
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if actual != expected:
                reports.append({"path": relative.as_posix(), "expected": expected, "actual": actual})
        _add(checks, "S02REVIEW-RECEIPT-REPORT-HASHES-CURRENT", not reports, reports or "all reports match")
        code_expected = evidence.get("hashes", {}).get("code")
        code_current = _current_code_hash(root)
        code_historical = _historical_code_hash(root) if code_expected != code_current else code_current
        code_ok = code_expected == code_current or (
            code_expected == PINNED_DELIVERED_CODE_HASH
            and code_historical in {PINNED_DELIVERED_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(
            checks,
            "S02REVIEW-RECEIPT-CODE-HASH-CURRENT",
            code_ok,
            {"expected": code_expected, "current": code_current, "historical_delivered_commit": code_historical},
        )
        _add(checks, "S02REVIEW-RECEIPT-ROLLBACK-HASH-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
    else:
        for check_id in ["S02REVIEW-RECEIPT-INTEGRITY", "S02REVIEW-RECEIPT-VALIDATION-ALL-PASS", "S02REVIEW-RECEIPT-NO-EXTERNAL-EFFECT", "S02REVIEW-RECEIPT-SIGNED-INPUTS-CURRENT", "S02REVIEW-RECEIPT-REPORT-HASHES-CURRENT", "S02REVIEW-RECEIPT-CODE-HASH-CURRENT", "S02REVIEW-RECEIPT-ROLLBACK-HASH-BINDING"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, dict) and rollback.get("evidence_id") == "EVD-S02-STAGE-REVIEW-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and len(rollback.get("artifacts", {})) == 13 and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S02REVIEW-RECEIPT-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, dict) else "unavailable")
    try:
        rows = _load_index(root)
        matching = [row for row in rows if row.get("id") == "INDEX-S02-STAGE-REVIEW"]
        index_ok = len(matching) == 1 and matching[0].get("status") == "PASS" and matching[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and matching[0].get("artifact_sha256") == evidence_hash and matching[0].get("next") == "S02/GITHUB_STAGE_UPLOAD_READY"
        _add(checks, "S02REVIEW-RECEIPT-INDEX-BINDING", index_ok, matching)
    except Exception as exc:
        _add(checks, "S02REVIEW-RECEIPT-INDEX-BINDING", False, "%s: %s" % (type(exc).__name__, exc))
    if verify_phase_prerequisites:
        try:
            phases = [_verify_phase(phase_id, root, True) for phase_id in ["P01", "P02", "P03", "P04"]]
            phase_ok = all(row.get("status") == "PASS" for row in phases)
            _add(checks, "S02REVIEW-RECEIPT-PHASE-PREREQUISITES", phase_ok, [row.get("status") for row in phases])
        except Exception as exc:
            _add(checks, "S02REVIEW-RECEIPT-PHASE-PREREQUISITES", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": "STAGE-DELIVERY-S02", "status": "PASS" if not failed else "FAIL", "decision": "S02_STAGE_REVIEW_EVIDENCE_VERIFIED" if not failed else "S02_STAGE_REVIEW_EVIDENCE_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "next": "S02/GITHUB_STAGE_UPLOAD_READY" if not failed else "S02/STAGE_REVIEW_REMEDIATION_REQUIRED"}
