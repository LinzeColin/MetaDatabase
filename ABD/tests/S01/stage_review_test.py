from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.stage1_review import (
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


def evaluate_contract(root: Path, require_external_reports: bool = False):
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
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _phase_record(contract, phase_id: str):
    return next(row for row in contract["phase_records"] if row["phase_id"] == phase_id)


def _finding(findings, finding_id: str):
    return next(row for row in findings["findings"] if row["id"] == finding_id)


def _metric(metrics, metric_id: str):
    return next(row for row in metrics["metrics"] if row["id"] == metric_id)


def _kill(kills, kill_id: str):
    return next(row for row in kills["criteria"] if row["id"] == kill_id)


def test_baseline_s01_whole_stage_review_passes_without_stage_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 45
    assert result["stage_status"] == "S01_REVIEW_PASS_REMOTE_UPLOAD_PENDING"
    assert result["remote_ci_status"] == "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD"
    assert result["release_status"] == "NOT_READY"
    assert result["next"] == "S01/GITHUB_STAGE_UPLOAD_READY"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


@pytest.mark.parametrize(
    ("label", "replacement"),
    [
        ("ABD_Roadmap_Stage_Phase_v0.0.0.1.md", "0" * 64),
        ("ABD_ProductDesign_TaskPack_v0.0.0.1_FINAL.zip", "f" * 64),
    ],
)
def test_source_receipt_drift_fails_closed(tmp_path: Path, label: str, replacement: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    next(row for row in contract["supplied_source_receipts"] if row["artifact_label"] == label)["sha256"] = replacement
    _write_json(path, contract)
    _failed(evaluate_contract(project), "S01REVIEW-SUPPLIED-SOURCE-RECEIPTS")


@pytest.mark.parametrize("mutation", ["stage", "phase", "requirement", "acceptance", "task"])
def test_review_scope_is_exact(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    if mutation == "stage":
        contract["stage_id"] = "S02"
    elif mutation == "phase":
        contract["review_scope"]["phase_ids"].pop()
    elif mutation == "requirement":
        contract["review_scope"]["requirement_ids"].pop()
    elif mutation == "acceptance":
        contract["review_scope"]["acceptance_contract_ids"].pop()
    else:
        contract["review_scope"]["task_ids"][-1] = contract["review_scope"]["task_ids"][0]
    _write_json(path, contract)
    _failed(evaluate_contract(project), "S01REVIEW-CONTRACT-SCOPE-EXACT")


@pytest.mark.parametrize(
    "field",
    [
        "github_upload_performed_by_local_review",
        "remote_ci_result_claimed_by_local_review",
        "gmail_or_provider_account_accessed",
        "production_deployment_claimed",
        "real_order_capability_present",
        "return_or_roi_verified",
        "s02_started",
    ],
)
def test_local_review_cannot_claim_external_effect(tmp_path: Path, field: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    contract["external_effect_boundary"][field] = True
    _write_json(path, contract)
    _failed(evaluate_contract(project), "S01REVIEW-LOCAL-EXTERNAL-EFFECT-BOUNDARY")


def test_local_review_cannot_skip_upload_and_start_s02(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    contract["next_on_local_review_pass"] = "S02/P01_READY_NOT_STARTED"
    _write_json(path, contract)
    _failed(evaluate_contract(project), "S01REVIEW-LOCAL-EXTERNAL-EFFECT-BOUNDARY")


@pytest.mark.parametrize(
    "relative",
    [
        "customer_outcomes.json",
        "assumption_register.json",
        "requirements.json",
        "metrics.json",
        "economics.json",
        "kill_criteria.json",
        "machine/facts/security_assurance.json",
    ],
)
def test_critical_s01_artifact_drift_fails_closed(tmp_path: Path, relative: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / relative
    value = strict_json_load(path)
    value["review_injected_drift"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-BASELINE-CRITICAL-HASHES")


def test_s01_roadmap_dependency_and_stop_conditions_are_exact(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/roadmap.json"
    roadmap = strict_json_load(path)
    stage = next(row for row in roadmap["stages"] if row["id"] == "S01")
    stage["depends_on"] = []
    stage["stop_conditions"].pop()
    _write_json(path, roadmap)
    _failed(evaluate_contract(project), "S01REVIEW-ROADMAP-STAGE-EXACT")


@pytest.mark.parametrize("surface", ["requirement", "acceptance", "traceability"])
def test_requirement_acceptance_trace_semantics_cannot_drift(tmp_path: Path, surface: str) -> None:
    project = _clone_repo(tmp_path)
    if surface == "requirement":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "REQ-S01-P04")["target"] = "GUARANTEE_RETURN"
    elif surface == "acceptance":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "AC-S01-P04")["oracle"]["type"] = "SELF_REPORTED"
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        next(row for row in value if row["requirement_id"] == "REQ-S01-P04")["task_ids"].pop()
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-SEMANTIC-TRACE-EXACT")


@pytest.mark.parametrize(("field", "value"), [("depends_on", []), ("owner_input_required", True), ("auto_advance_on_pass", False)])
def test_stage_task_chain_and_auto_advance_are_exact(tmp_path: Path, field: str, value) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/facts/task_graph.json"
    graph = strict_json_load(path)
    task = next(row for row in graph["tasks"] if row["id"] == "T-S01-P04-03")
    task[field] = value
    _write_json(path, graph)
    _failed(evaluate_contract(project), "S01REVIEW-TASK-CHAIN-EXACT")


@pytest.mark.parametrize("mutation", ["status", "decision", "release", "boundary", "rollback", "index"])
def test_phase_evidence_chain_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    evidence_path = project / "machine/evidence/EVD-S01-P04.json"
    rollback_path = project / "machine/evidence/EVD-S01-P04_rollback.json"
    if mutation == "rollback":
        value = strict_json_load(rollback_path)
        value["status"] = "FAIL"
        _write_json(rollback_path, value)
    elif mutation == "index":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-AC-S01-P04")["status"] = "FAIL"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    else:
        value = strict_json_load(evidence_path)
        if mutation == "status":
            value["status"] = "FAIL"
        elif mutation == "decision":
            value["decision_sha256"] = "0" * 64
        elif mutation == "release":
            value["release_status"] = "READY"
        else:
            value["external_effect_boundary"]["github_upload_performed"] = True
        _write_json(evidence_path, value)
    _failed(evaluate_contract(project), "S01REVIEW-PHASE-EVIDENCE-ROLLBACK-INDEX")


def test_missing_required_output_fails_closed(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    (project / "customer_press_release.md").unlink()
    _failed(evaluate_contract(project), "S01REVIEW-PHASE-REQUIRED-OUTPUTS")


@pytest.mark.parametrize("mutation", ["missing_commit", "wrong_code_hash", "escaped_path"])
def test_historical_phase_binding_fails_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    record = _phase_record(contract, "P04")
    if mutation == "missing_commit":
        record["implementation_commit"] = "0" * 40
    elif mutation == "wrong_code_hash":
        record["implementation_code_sha256"] = "f" * 64
    else:
        record["allowed_commit_paths"] = ["ABD/metrics-only/"]
    _write_json(path, contract)
    result = _evaluate_contract(project, False, _verify_history=True, _verify_phase_oracles=False)
    _failed(result, "S01REVIEW-HISTORICAL-CODE-AND-INPUT-HASHES")


@pytest.mark.parametrize("mutation", ["missing_requirement", "missing_metric", "duplicate_kill"])
def test_product_metric_kill_id_sets_are_exact(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    if mutation == "missing_requirement":
        path = project / "requirements.json"
        value = strict_json_load(path)
        value["requirements"].pop()
    elif mutation == "missing_metric":
        path = project / "metrics.json"
        value = strict_json_load(path)
        value["metrics"].pop()
    else:
        path = project / "kill_criteria.json"
        value = strict_json_load(path)
        value["criteria"][-1]["id"] = value["criteria"][-2]["id"]
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-PRODUCT-METRIC-KILL-ID-SETS-EXACT")


def test_every_product_requirement_must_have_a_metric(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "metrics.json"
    metrics = strict_json_load(path)
    _metric(metrics, "MET-S01-P04-028")["requirement_ids"] = ["ABD-PRD-REQ-001"]
    _write_json(path, metrics)
    _failed(evaluate_contract(project), "S01REVIEW-ALL-21-REQUIREMENTS-MEASURED-EXACT")


def test_every_non_cash_benefit_must_have_valid_metrics(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "economics.json"
    economics = strict_json_load(path)
    economics["benefit_envelope"]["non_cash_benefits"][3]["measurement_metric_ids"] = []
    _write_json(path, economics)
    _failed(evaluate_contract(project), "S01REVIEW-ALL-NONCASH-BENEFITS-MEASURED")


@pytest.mark.parametrize("mutation", ["gmail", "archive", "privacy", "pipeline", "kill"])
def test_new_review_remediation_gates_are_exact(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    if mutation in {"gmail", "archive", "privacy", "pipeline"}:
        path = project / "metrics.json"
        metrics = strict_json_load(path)
        ids = {"gmail": "028", "archive": "029", "privacy": "030", "pipeline": "031"}
        _metric(metrics, "MET-S01-P04-%s" % ids[mutation])["requirement_ids"] = ["ABD-PRD-REQ-001"]
        _write_json(path, metrics)
    else:
        path = project / "kill_criteria.json"
        kills = strict_json_load(path)
        _kill(kills, "KC-S01-P04-018")["metric_ids"] = ["MET-S01-P04-001"]
        _write_json(path, kills)
    _failed(evaluate_contract(project), "S01REVIEW-GMAIL-PRIVACY-PIPELINE-GATES-EXACT")


@pytest.mark.parametrize("artifact", ["metrics.json", "economics.json", "kill_criteria.json"])
def test_cross_artifact_source_binding_drift_fails_closed(tmp_path: Path, artifact: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / artifact
    value = strict_json_load(path)
    first = next(iter(value["source_bindings"]))
    value["source_bindings"][first] = "0" * 64
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-CROSS-ARTIFACT-SOURCE-BINDINGS")


@pytest.mark.parametrize("mutation", ["owner", "auto_order", "return", "zero_budget", "gmail_default"])
def test_working_backwards_truth_boundaries_are_aligned(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    if mutation in {"owner", "auto_order", "return"}:
        path = project / "customer_outcomes.json"
        value = strict_json_load(path)
        if mutation == "owner":
            value["experience_contract"]["final_order_actor"] = "SYSTEM"
        elif mutation == "auto_order":
            value["experience_contract"]["automatic_order_submission_count"] = 1
        else:
            value["claim_boundaries"]["return_guaranteed"] = True
        expected = "S01REVIEW-WORKING-BACKWARDS-BOUNDARIES-ALIGNED"
    else:
        path = project / "assumption_register.json"
        value = strict_json_load(path)
        item_id = "ASM-S01-P02-03" if mutation == "zero_budget" else "ASM-S01-P02-05"
        next(row for row in value["assumptions"] if row["id"] == item_id)["safe_default"] = "ALLOW"
        expected = "S01REVIEW-WORKING-BACKWARDS-BOUNDARIES-ALIGNED"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize("mutation", ["order_scope", "gmail_scope", "return_scope"])
def test_scope_hard_boundaries_cannot_relax(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / "scope_boundary.json"
    value = strict_json_load(path)
    if mutation == "order_scope":
        value["explicit_out_of_scope"].pop(0)
    elif mutation == "gmail_scope":
        value["conditional_capabilities"][2]["current_status"] = "CONNECTED"
    else:
        value["conditional_capabilities"][5]["current_status"] = "VERIFIED"
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-SCOPE-HARD-BOUNDARIES-ALIGNED")


@pytest.mark.parametrize("artifact,field", [("metrics.json", "missing"), ("economics.json", "roi"), ("kill_criteria.json", "release")])
def test_cost_roi_return_or_kill_claims_fail_closed(tmp_path: Path, artifact: str, field: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / artifact
    value = strict_json_load(path)
    if field == "missing":
        value["metric_semantics"]["missing_or_null_baseline"] = "PASS"
    elif field == "roi":
        value["roi_contract"]["roi"] = "0.30"
    else:
        value["current_evaluation"]["release_effect"] = "RELEASE"
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-NO-FABRICATED-COST-ROI-OR-RETURN")


@pytest.mark.parametrize("mutation", ["open", "missing_evidence", "summary", "s02"])
def test_review_findings_must_be_resolved_and_bounded(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / FINDINGS_PATH
    findings = strict_json_load(path)
    if mutation == "open":
        _finding(findings, "F-S01-R02")["status"] = "OPEN"
    elif mutation == "missing_evidence":
        _finding(findings, "F-S01-R03")["evidence"] = ""
    elif mutation == "summary":
        findings["summary"]["open"] = 1
    else:
        findings["scope_boundaries"]["s02_started"] = True
    _write_json(path, findings)
    _failed(evaluate_contract(project), "S01REVIEW-FINDINGS-ALL-RESOLVED")


@pytest.mark.parametrize("mutation", ["floating_action", "missing_fetch_depth", "wrong_uv", "missing_command", "secret_reference"])
def test_abd_ci_workflow_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project.parent / ".github/workflows/abd-stage0-validation.yml"
    text = path.read_text(encoding="utf-8")
    if mutation == "floating_action":
        text = text.replace("actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", "actions/checkout@v7")
        expected = "S01REVIEW-CI-SUPPLY-CHAIN-PINS"
    elif mutation == "missing_fetch_depth":
        text = text.replace("fetch-depth: 0", "fetch-depth: 1")
        expected = "S01REVIEW-CI-SUPPLY-CHAIN-PINS"
    elif mutation == "wrong_uv":
        text = text.replace('version: "0.11.28"', 'version: "latest"')
        expected = "S01REVIEW-CI-SUPPLY-CHAIN-PINS"
    elif mutation == "missing_command":
        text = text.replace("python machine/tools/validate_pack.py", "python machine/tools/skip_pack.py")
        expected = "S01REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED"
    else:
        text += "\n# " + "$" + "{{ secrets.ABD_TOKEN }}\n"
        expected = "S01REVIEW-ABD-UBUNTU-CI-FAIL-CLOSED"
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), expected)


def test_cli_registration_cannot_be_removed(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "abd_acceptance/__main__.py"
    text = path.read_text(encoding="utf-8").replace('"STAGE-REVIEW-S01": write_stage1_review_evidence,', "")
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), "S01REVIEW-EXECUTABLE-REPLAY-REGISTERED")


@pytest.mark.parametrize("mutation", ["positive_cost", "real_order", "gmail_effect"])
def test_budget_order_and_gmail_effects_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    if mutation == "positive_cost":
        path = project / "machine/facts/costs.json"
        value = strict_json_load(path)
        value["incremental_cash_budget"]["high"] = "0.0001"
    elif mutation == "real_order":
        path = project / "machine/facts/authorization_matrix.json"
        value = strict_json_load(path)
        action = next(row for row in value["actions"] if row["id"] == "REAL_ORDER_SUBMISSION")
        action["authorization"] = "PREAUTHORIZED"
    else:
        path = project / "machine/facts/degraded_mode_contract.json"
        value = strict_json_load(path)
        value["s00_p04_execution_boundary"]["gmail_api_called"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01REVIEW-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT")


@pytest.mark.parametrize("mutation", ["secret", "local_path"])
def test_secret_or_local_path_fails_scan(tmp_path: Path, mutation: str) -> None:
    project = _clone_repo(tmp_path)
    path = project / "machine/evidence/injected-review.txt"
    payload = "gh" + "p_" + "A" * 24 if mutation == "secret" else "/" + "Users/example/private.json"
    path.write_text(payload, encoding="utf-8")
    _failed(evaluate_contract(project), "S01REVIEW-SECRET-AND-LOCAL-PATH-SCAN")


def test_s02_cannot_start_before_verified_stage_upload(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    (project / "machine/evidence/EVD-S02-P01.json").write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S01REVIEW-S02-NOT-STARTED-AND-S00-DELIVERED")


def test_readme_cannot_report_stale_p03_state(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / "README.md"
    path.write_text("S01/P04 尚未开始\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S01REVIEW-README-CURRENT-DELIVERY-STATE")


def test_duplicate_contract_key_fails_closed(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    path = project / CONTRACT_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", '{\n  "schema_version": "duplicate",', 1), encoding="utf-8")
    _failed(evaluate_contract(project), "S01REVIEW-INPUT-CONTRACT-PARSE")


def test_malformed_evidence_index_fails_closed_without_crashing(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    (project / "machine/evidence/evidence_index.jsonl").write_text("{\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S01REVIEW-PHASE-EVIDENCE-ROLLBACK-INDEX")


def test_external_reports_are_mandatory_for_formal_review(tmp_path: Path) -> None:
    project = _clone_repo(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (project / relative).unlink(missing_ok=True)
    result = _evaluate_contract(project, True, _verify_history=False, _verify_phase_oracles=False)
    assert "S01REVIEW-TEST-TARGETED-PASS" in result["summary"]["failed_check_ids"]
    assert "S01REVIEW-TEST-FULL-REGRESSION-PASS" in result["summary"]["failed_check_ids"]


def test_stage_review_evidence_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["upload_gate"]["github_upload_performed_by_review"] is False
    assert first["upload_gate"]["remote_result_must_be_verified_before_s02"] is True


def test_stage_review_rollback_restores_all_signed_contracts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 7
    for artifact in result["artifacts"].values():
        assert artifact["status"] == "PASS"
        assert artifact["signed_sha256"] == artifact["restored_sha256"]
        assert artifact["corrupted_sha256"] != artifact["restored_sha256"]


def test_review_evaluation_does_not_mutate_inputs() -> None:
    paths = [ROOT / CONTRACT_PATH, ROOT / FINDINGS_PATH, ROOT / FIXTURE_PATH, ROOT / "metrics.json", ROOT / "economics.json", ROOT / "kill_criteria.json", REPO_ROOT / ".github/workflows/abd-stage0-validation.yml"]
    before = {path.as_posix(): sha256_file(path) for path in paths}
    result = evaluate_contract(ROOT, require_external_reports=False)
    after = {path.as_posix(): sha256_file(path) for path in paths}
    assert result["status"] == "PASS"
    assert before == after
