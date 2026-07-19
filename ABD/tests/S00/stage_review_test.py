from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage_review import (
    CONTRACT_PATH,
    FINDINGS_PATH,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
)


ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    """Use full independent gates on the real tree and a fail-marked partial profile on mutation clones."""
    is_real_tree = Path(root).resolve() == ROOT.resolve()
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_history=is_real_tree,
        _verify_phase_oracles=is_real_tree,
    )


def _clone_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    project = repo / "ABD"
    shutil.copytree(
        str(ROOT),
        str(project),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(str(REPO_ROOT / ".github"), str(repo / ".github"))
    return project


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _phase_record(contract, phase_id: str):
    return next(row for row in contract["phase_records"] if row["phase_id"] == phase_id)


def _finding(findings, finding_id: str):
    return next(row for row in findings["findings"] if row["id"] == finding_id)


def _action(authorization, action_id: str):
    return next(row for row in authorization["actions"] if row["id"] == action_id)


def test_baseline_whole_stage_review_passes_without_generated_stage_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 40
    assert result["stage_status"] == "S00_REVIEW_PASS_REMOTE_UPLOAD_PENDING"
    assert result["remote_ci_status"] == "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD"
    assert result["release_status"] == "NOT_READY"
    assert result["next"] == "S00/GITHUB_STAGE_UPLOAD_READY"


@pytest.mark.parametrize(
    ("label", "replacement"),
    [
        ("ABD_Roadmap_Stage_Phase_v0.0.0.1.md", "0" * 64),
        ("ABD_ProductDesign_TaskPack_v0.0.0.1_FINAL.zip", "f" * 64),
    ],
)
def test_supplied_source_receipt_drift_fails_closed(tmp_path: Path, label: str, replacement: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    next(row for row in contract["supplied_source_receipts"] if row["artifact_label"] == label)["sha256"] = replacement
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "REVIEW-SUPPLIED-SOURCE-RECEIPTS")


@pytest.mark.parametrize(
    "mutation",
    ["missing_phase", "duplicate_task", "wrong_version"],
)
def test_review_scope_must_be_exact(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    if mutation == "missing_phase":
        contract["review_scope"]["phase_ids"].pop()
    elif mutation == "duplicate_task":
        contract["review_scope"]["task_ids"][-1] = contract["review_scope"]["task_ids"][0]
    else:
        contract["product_version"] = "0.0.0.2"
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "REVIEW-CONTRACT-SCOPE")


@pytest.mark.parametrize(
    "field",
    [
        "github_upload_performed_by_local_review",
        "remote_ci_result_claimed_by_local_review",
        "production_deployment_claimed",
        "real_order_capability_present",
        "return_guaranteed",
    ],
)
def test_local_review_cannot_claim_external_or_release_effect(tmp_path: Path, field: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    contract["external_effect_boundary"][field] = True
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "REVIEW-EXTERNAL-EFFECT-BOUNDARY")


def test_local_review_cannot_skip_upload_and_start_s01(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    contract["next_on_local_review_pass"] = "S01/P01_READY_NOT_STARTED"
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "REVIEW-EXTERNAL-EFFECT-BOUNDARY")


@pytest.mark.parametrize(
    "relative",
    [
        "machine/facts/canonical_facts.json",
        "machine/facts/parameters.json",
        "machine/facts/release_policy.json",
    ],
)
def test_critical_taskpack_baseline_drift_fails_closed(tmp_path: Path, relative: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / relative
    value = strict_json_load(path)
    value["stage_review_injected_drift"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project, False), "REVIEW-BASELINE-CRITICAL-HASHES")


def test_roadmap_stage_stop_conditions_cannot_change(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/roadmap.json"
    roadmap = strict_json_load(path)
    next(row for row in roadmap["stages"] if row["id"] == "S00")["stop_conditions"].pop()
    _write_json(path, roadmap)
    _failed(evaluate_contract(project, False), "REVIEW-S00-ROADMAP-EXACT")


@pytest.mark.parametrize(
    "surface",
    ["requirement", "acceptance", "traceability"],
)
def test_requirement_acceptance_trace_semantics_cannot_drift(tmp_path: Path, surface: str) -> None:
    project = _clone_repo(tmp_path)
    if surface == "requirement":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "REQ-S00-P04")["target"] = "ALLOW_GMAIL_WITHOUT_CONSENT"
    elif surface == "acceptance":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "AC-S00-P04")["oracle"]["type"] = "SELF_REPORTED"
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        next(row for row in value if row["requirement_id"] == "REQ-S00-P04")["task_ids"].pop()
    _write_json(path, value)
    _failed(evaluate_contract(project, False), "REVIEW-S00-SEMANTIC-TRACE")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("depends_on", []),
        ("owner_input_required", True),
        ("auto_advance_on_pass", False),
    ],
)
def test_stage_task_chain_and_auto_advance_are_exact(tmp_path: Path, field: str, value) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/task_graph.json"
    graph = strict_json_load(path)
    task = next(row for row in graph["tasks"] if row["id"] == "T-S00-P04-03")
    task[field] = value
    _write_json(path, graph)
    _failed(evaluate_contract(project, False), "REVIEW-S00-TASK-CHAIN-EXACT")


@pytest.mark.parametrize(
    "mutation",
    ["status", "decision_hash", "rollback", "index", "input_hash"],
)
def test_phase_evidence_chain_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    evidence_path = project / "machine/evidence/EVD-S00-P04.json"
    rollback_path = project / "machine/evidence/EVD-S00-P04_rollback.json"
    if mutation == "status":
        evidence = strict_json_load(evidence_path)
        evidence["status"] = "FAIL"
        _write_json(evidence_path, evidence)
    elif mutation == "decision_hash":
        evidence = strict_json_load(evidence_path)
        evidence["decision_sha256"] = "0" * 64
        _write_json(evidence_path, evidence)
    elif mutation == "rollback":
        rollback = strict_json_load(rollback_path)
        rollback["status"] = "FAIL"
        _write_json(rollback_path, rollback)
    elif mutation == "index":
        index_path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-AC-S00-P04")["status"] = "FAIL"
        index_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    else:
        evidence = strict_json_load(evidence_path)
        evidence["hashes"]["inputs"]["machine/facts/canonical_facts.json"] = "f" * 64
        _write_json(evidence_path, evidence)
    _failed(evaluate_contract(project, False), "REVIEW-PHASE-EVIDENCE-INDEX")


def test_malformed_evidence_index_fails_closed_without_crashing(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    (project / "machine/evidence/evidence_index.jsonl").write_text("{\n", encoding="utf-8")
    _failed(evaluate_contract(project, False), "REVIEW-PHASE-EVIDENCE-INDEX")


def test_missing_required_phase_output_fails_closed(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    (project / "machine/facts/canonical_facts.sha256").unlink()
    _failed(evaluate_contract(project, False), "REVIEW-PHASE-REQUIRED-OUTPUTS")


@pytest.mark.parametrize("mutation", ["missing_commit", "wrong_code_hash"])
def test_historical_phase_code_binding_fails_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    record = _phase_record(contract, "P04")
    if mutation == "missing_commit":
        record["implementation_commit"] = "0" * 40
    else:
        record["implementation_code_sha256"] = "f" * 64
    _write_json(path, contract)
    result = _evaluate_contract(
        project,
        False,
        _verify_history=True,
        _verify_phase_oracles=False,
    )
    _failed(result, "REVIEW-PHASE-HISTORICAL-CODE-HASHES")


@pytest.mark.parametrize(
    "mutation",
    ["open_status", "missing_evidence", "open_summary", "s01_started"],
)
def test_review_findings_must_be_resolved_and_bounded(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / FINDINGS_PATH
    findings = strict_json_load(path)
    if mutation == "open_status":
        _finding(findings, "F-S00-R02")["status"] = "OPEN"
    elif mutation == "missing_evidence":
        _finding(findings, "F-S00-R03")["evidence"] = ""
    elif mutation == "open_summary":
        findings["summary"]["open"] = 1
    else:
        findings["scope_boundaries"]["s01_started"] = True
    _write_json(path, findings)
    _failed(evaluate_contract(project, False), "REVIEW-FINDINGS-ALL-RESOLVED")


@pytest.mark.parametrize(
    "mutation",
    ["floating_action", "missing_fetch_depth", "wrong_uv", "missing_command", "secret_reference"],
)
def test_abd_ci_workflow_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project.parent / ".github/workflows/abd-stage0-validation.yml"
    text = path.read_text(encoding="utf-8")
    if mutation == "floating_action":
        text = text.replace("actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", "actions/checkout@v7")
        expected = "REVIEW-CI-SUPPLY-CHAIN-PINS"
    elif mutation == "missing_fetch_depth":
        text = text.replace("fetch-depth: 0", "fetch-depth: 1")
        expected = "REVIEW-CI-SUPPLY-CHAIN-PINS"
    elif mutation == "wrong_uv":
        text = text.replace('version: "0.11.28"', 'version: "latest"')
        expected = "REVIEW-CI-SUPPLY-CHAIN-PINS"
    elif mutation == "missing_command":
        text = text.replace("python machine/tools/validate_pack.py", "python machine/tools/skip_pack.py")
        expected = "REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED"
    else:
        text += "\n# " + "$" + "{{ secrets.GOVERNANCE_READ_TOKEN }}\n"
        expected = "REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED"
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project, False), expected)


@pytest.mark.parametrize("mutation", ["omit_abd", "omit_governance_project"])
def test_repository_ci_classification_cannot_silently_skip_renderer(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project.parent / ".github/workflows/dual-plane.yml"
    text = path.read_text(encoding="utf-8")
    if mutation == "omit_abd":
        text = text.replace('specialized = {"ABD":', 'specialized = {"ABX":')
    else:
        text = text.replace('"QBVS",', '"QBVS-OMITTED",')
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project, False), "REVIEW-CI-PROJECT-CLASSIFICATION")


def test_review_contract_governance_project_list_is_exact(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    contract["repository_integration"]["governance_registered_projects"].pop()
    _write_json(path, contract)
    _failed(evaluate_contract(project, False), "REVIEW-CI-PROJECT-CLASSIFICATION")


def test_positive_incremental_cash_fails_stage_review(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/costs.json"
    costs = strict_json_load(path)
    costs["incremental_cash_budget"]["high"] = "0.0001"
    _write_json(path, costs)
    _failed(evaluate_contract(project, False), "REVIEW-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT")


def test_real_order_module_cannot_be_authorized(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/authorization_matrix.json"
    authorization = strict_json_load(path)
    action = _action(authorization, "REAL_ORDER_SUBMISSION")
    action["authorization"] = "PREAUTHORIZED"
    action["capability_status"] = "AVAILABLE"
    _write_json(path, authorization)
    _failed(evaluate_contract(project, False), "REVIEW-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT")


def test_gmail_api_effect_cannot_be_claimed(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/degraded_mode_contract.json"
    degraded = strict_json_load(path)
    degraded["s00_p04_execution_boundary"]["gmail_api_called"] = True
    _write_json(path, degraded)
    _failed(evaluate_contract(project, False), "REVIEW-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT")


@pytest.mark.parametrize("mutation", ["secret", "local_path"])
def test_secret_or_local_path_in_stage_artifact_fails_scan(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/evidence/injected-stage-review.txt"
    if mutation == "secret":
        payload = "gh" + "p_" + "A" * 24
    else:
        payload = "/" + "Users/example/private.json"
    path.write_text(payload, encoding="utf-8")
    _failed(evaluate_contract(project, False), "REVIEW-SECRET-AND-LOCAL-PATH-SCAN")


def test_s01_evidence_cannot_exist_before_stage_upload(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    (project / "machine/evidence/EVD-S01-P01.json").write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project, False), "REVIEW-S01-NOT-STARTED")


def test_duplicate_review_contract_key_fails_closed(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", '{\n  "schema_version": "duplicate",', 1), encoding="utf-8")
    _failed(evaluate_contract(project, False), "REVIEW-INPUT-CONTRACT-PARSE")


def test_external_reports_are_mandatory_for_final_stage_review(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (project / relative).unlink(missing_ok=True)
    result = _evaluate_contract(
        project,
        require_external_reports=True,
        _verify_history=False,
        _verify_phase_oracles=False,
    )
    assert result["status"] == "FAIL"
    assert "REVIEW-TEST-TARGETED-PASS" in result["summary"]["failed_check_ids"]
    assert "REVIEW-TEST-FULL-REGRESSION-PASS" in result["summary"]["failed_check_ids"]


def test_stage_review_evidence_is_deterministic_without_runtime_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["upload_gate"]["github_upload_performed_by_review"] is False
    assert first["upload_gate"]["remote_result_must_be_verified_before_s01"] is True


def test_stage_review_rollback_drill_restores_review_and_ci_contracts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 4
    for artifact in result["artifacts"].values():
        assert artifact["status"] == "PASS"
        assert artifact["signed_sha256"] == artifact["restored_sha256"]
        assert artifact["corrupted_sha256"] != artifact["restored_sha256"]


def test_stage_review_evaluation_does_not_mutate_inputs() -> None:
    paths = [
        ROOT / CONTRACT_PATH,
        ROOT / FINDINGS_PATH,
        ROOT / FIXTURE_PATH,
        REPO_ROOT / ".github/workflows/dual-plane.yml",
        REPO_ROOT / ".github/workflows/abd-stage0-validation.yml",
    ]
    before = {path.as_posix(): sha256_file(path) for path in paths}
    result = evaluate_contract(ROOT, require_external_reports=False)
    after = {path.as_posix(): sha256_file(path) for path in paths}
    assert result["status"] == "PASS"
    assert before == after
