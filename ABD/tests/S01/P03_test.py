from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.requirements_scope import (
    CONTINUOUS_WORKFLOW_PATH,
    FIXTURE_PATH,
    FLOWS_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    P02_EVIDENCE_PATH,
    P02_EVIDENCE_SHA256,
    P02_ROLLBACK_PATH,
    REQUIREMENTS_PATH,
    SCOPE_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_stability_default,
    resolve_trace_default,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    is_real_tree = Path(root).resolve() == ROOT.resolve()
    return _evaluate_contract(root, require_external_reports, _verify_git_history=is_real_tree)


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(str(ROOT.parent / ".github"), str(destination.parent / ".github"))
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _row(value, item_id: str):
    return next(row for row in value if row["id"] == item_id)


def test_baseline_requirements_scope_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 100
    assert result["decision"] == "REQUIREMENTS_SCOPE_AND_FLOWS_FROZEN"
    assert result["release_status"] == "NOT_READY"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S01/P04_READY_NOT_STARTED"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p02_immutable_receipt_and_git_ancestry_are_verified() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["S01P03-P02-IMMUTABLE-RECEIPT"]["passed"] is True
    assert checks["S01P03-P02-SIGNED-ARTIFACTS"]["passed"] is True
    assert checks["S01P03-P02-EVIDENCE-INDEX"]["passed"] is True
    assert checks["S01P03-P02-GIT-ANCESTRY"]["passed"] is True
    assert sha256_file(ROOT / P02_EVIDENCE_PATH) == P02_EVIDENCE_SHA256


@pytest.mark.parametrize("route", FIXTURE["expected_requirement_routes"], ids=lambda row: row[0])
def test_each_requirement_has_exact_unique_route(route) -> None:
    requirements = strict_json_load(ROOT / REQUIREMENTS_PATH)["requirements"]
    scope = strict_json_load(ROOT / SCOPE_PATH)
    flows = strict_json_load(ROOT / FLOWS_PATH)["flows"]
    requirement_id, business_line_id, module_id, acceptance_id = route
    row = _row(requirements, requirement_id)
    modules = [module for module in scope["functional_modules"] if requirement_id in module["requirement_ids"]]
    flow_steps = [step for flow in flows for step in flow["steps"] if requirement_id in step["requirement_ids"]]
    assert [row["business_line_id"], row["module_id"], row["primary_acceptance_contract_id"]] == [
        business_line_id,
        module_id,
        acceptance_id,
    ]
    assert len(modules) == 1
    assert [modules[0]["business_line_id"], modules[0]["id"]] == [business_line_id, module_id]
    assert flow_steps


TRACE_GATES = tuple(FIXTURE["trace_gate_order"])


@pytest.mark.parametrize("values", list(itertools.product([False, True], repeat=len(TRACE_GATES))))
def test_trace_gate_truth_table_fails_closed(values) -> None:
    decision = resolve_trace_default(**dict(zip(TRACE_GATES, values)))
    assert decision == ("TRACEABLE" if all(values) else "BLOCK_UNTRACEABLE_REQUIREMENT")


@pytest.mark.parametrize(
    "gates",
    [
        {},
        {"unique_id": True},
        {**{name: True for name in TRACE_GATES}, "unexpected": True},
        {**{name: True for name in TRACE_GATES}, "unique_id": 1},
        {**{name: True for name in TRACE_GATES}, "source_pointers_resolve": None},
    ],
)
def test_malformed_trace_gate_sets_block(gates) -> None:
    assert resolve_trace_default(**gates) == "BLOCK_MALFORMED_TRACE_GATE_SET"


@pytest.mark.parametrize("case", FIXTURE["stability_vectors"], ids=lambda case: case["expected"])
def test_stability_vectors_fail_closed(case) -> None:
    assert resolve_stability_default(case["actions"]) == case["expected"]


@pytest.mark.parametrize("malformed", ["RECOMMENDATION", b"NO_RECOMMENDATION", [], ["RECOMMENDATION"] * 5])
def test_malformed_stability_sequence_fails_closed(malformed) -> None:
    assert resolve_stability_default(malformed) == "NO_RECOMMENDATION_MALFORMED_STABILITY_VECTOR"


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("roadmap", "S01P03-ROADMAP-EXACT"),
        ("requirement", "S01P03-REQUIREMENT-EXACT"),
        ("acceptance", "S01P03-ACCEPTANCE-CONTRACT-EXACT"),
        ("task_dependency", "S01P03-TASK-CHAIN-EXACT"),
        ("task_output", "S01P03-TASK-CHAIN-EXACT"),
        ("task_owner", "S01P03-TASK-CHAIN-EXACT"),
        ("traceability", "S01P03-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_semantics_cannot_drift(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "roadmap":
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = next(row for row in next(row for row in value["stages"] if row["id"] == "S01")["phases"] if row["id"] == "P03")
        phase["objective"] = "drift"
    elif mutation == "requirement":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        _row(value, "REQ-S01-P03")["target"] = "drift"
    elif mutation == "acceptance":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        _row(value, "AC-S01-P03")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = _row(value["tasks"], "T-S01-P03-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"] = ["wrong"]
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        next(row for row in value if row["requirement_id"] == "REQ-S01-P03")["evidence_id"] = "wrong"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("duplicate_id", "S01P03-REQUIREMENT-IDS-UNIQUE-EXACT"),
        ("route", "S01P03-REQUIREMENT-ROUTES-UNIQUE-EXACT"),
        ("duplicate_primary", "S01P03-REQUIREMENT-ROUTES-UNIQUE-EXACT"),
        ("missing_title", "S01P03-REQUIREMENT-ROWS-COMPLETE"),
        ("unknown_acceptance", "S01P03-ACCEPTANCE-ROUTES-VALID-UNIQUE"),
        ("bogus_pointer", "S01P03-SOURCE-POINTERS-RESOLVE"),
        ("unknown_source", "S01P03-SOURCE-POINTERS-RESOLVE"),
        ("non_goals", "S01P03-REQUIREMENTS-TOP-LEVEL"),
        ("claim", "S01P03-REQUIREMENTS-NO-FALSE-CURRENT-CLAIMS"),
        ("semantic", "S01P03-REQUIRED-SEMANTICS-PRESENT"),
        ("source_binding", "S01P03-REQUIREMENTS-SOURCE-BINDINGS"),
        ("status", "S01P03-REQUIREMENTS-TOP-LEVEL"),
    ],
)
def test_requirement_mutations_fail_traceability_oracle(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / REQUIREMENTS_PATH
    value = strict_json_load(path)
    rows = value["requirements"]
    if mutation == "duplicate_id":
        rows[1]["id"] = rows[0]["id"]
    elif mutation == "route":
        rows[0]["module_id"] = "MOD-OWNER-EXECUTION"
    elif mutation == "duplicate_primary":
        rows[1]["primary_acceptance_contract_id"] = rows[0]["primary_acceptance_contract_id"]
    elif mutation == "missing_title":
        rows[0]["title"] = ""
    elif mutation == "unknown_acceptance":
        rows[0]["supporting_acceptance_contract_ids"][0] = "AC-UNKNOWN"
    elif mutation == "bogus_pointer":
        rows[0]["source_evidence"][0]["pointers"] = ["/missing"]
    elif mutation == "unknown_source":
        rows[0]["source_evidence"][0]["path"] = "unknown.json"
    elif mutation == "non_goals":
        value["non_goals"].pop()
    elif mutation == "claim":
        value["claim_boundaries"]["production_deployment_claimed"] = True
    elif mutation == "semantic":
        rows[2]["statement"] = "系统做任何事。"
    elif mutation == "source_binding":
        value["source_bindings"]["machine/facts/canonical_facts.json"] = "0" * 64
    else:
        value["status"] = "PRODUCTION_READY"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("duplicate_line", "S01P03-BUSINESS-LINES-MODULES-EXACT"),
        ("missing_module", "S01P03-BUSINESS-LINES-MODULES-EXACT"),
        ("duplicate_assignment", "S01P03-EACH-REQUIREMENT-EXACTLY-ONE-MODULE"),
        ("module_line", "S01P03-BUSINESS-LINE-MODULE-HIERARCHY"),
        ("invariant_ref", "S01P03-INVARIANTS-OUTSCOPE-CONDITIONAL-EXACT"),
        ("out_count", "S01P03-INVARIANTS-OUTSCOPE-CONDITIONAL-EXACT"),
        ("prohibited", "S01P03-EXPLICIT-NON-GOALS-FAIL-CLOSED"),
        ("conditional_count", "S01P03-INVARIANTS-OUTSCOPE-CONDITIONAL-EXACT"),
        ("external", "S01P03-SCOPE-NO-EXTERNAL-EFFECTS"),
        ("p04", "S01P03-SCOPE-NO-EXTERNAL-EFFECTS"),
    ],
)
def test_scope_boundary_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / SCOPE_PATH
    value = strict_json_load(path)
    if mutation == "duplicate_line":
        value["business_lines"][1]["id"] = value["business_lines"][0]["id"]
    elif mutation == "missing_module":
        value["functional_modules"].pop()
    elif mutation == "duplicate_assignment":
        value["functional_modules"][1]["requirement_ids"].append("ABD-PRD-REQ-001")
    elif mutation == "module_line":
        value["functional_modules"][0]["business_line_id"] = "BL-INFRA-COST"
    elif mutation == "invariant_ref":
        value["hard_invariants"][0]["requirement_ids"] = ["ABD-PRD-REQ-999"]
    elif mutation == "out_count":
        value["explicit_out_of_scope"].pop()
    elif mutation == "prohibited":
        value["explicit_out_of_scope"][0]["capability"] = "普通能力"
    elif mutation == "conditional_count":
        value["conditional_capabilities"].pop()
    elif mutation == "external":
        value["s01_p03_execution_boundary"]["external_account_or_api_accessed"] = True
    else:
        value["s01_p03_execution_boundary"]["p04_artifacts_created"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("duplicate_flow", "S01P03-FLOW-ERROR-IDS-UNIQUE-EXACT"),
        ("duplicate_step", "S01P03-FLOW-STEPS-TRACE-ALL-REQUIREMENTS"),
        ("unknown_requirement", "S01P03-FLOW-STEPS-TRACE-ALL-REQUIREMENTS"),
        ("orphan_requirement", "S01P03-FLOW-STEPS-TRACE-ALL-REQUIREMENTS"),
        ("terminal", "S01P03-FLOW-STEPS-TRACE-ALL-REQUIREMENTS"),
        ("external", "S01P03-FLOW-STEPS-TRACE-ALL-REQUIREMENTS"),
        ("missing_error", "S01P03-FLOW-ERROR-IDS-UNIQUE-EXACT"),
        ("unknown_flow", "S01P03-EVERY-FLOW-HAS-SAFE-ERROR-PATH"),
        ("unsafe_equals_forbidden", "S01P03-EVERY-FLOW-HAS-SAFE-ERROR-PATH"),
        ("summary", "S01P03-FLOW-TRACEABILITY-SUMMARY-EXACT"),
        ("boundary", "S01P03-FLOWS-NO-RUNTIME-OR-EXTERNAL-EFFECT"),
        ("status", "S01P03-FLOWS-TOP-LEVEL"),
    ],
)
def test_business_flow_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / FLOWS_PATH
    value = strict_json_load(path)
    if mutation == "duplicate_flow":
        value["flows"][1]["id"] = value["flows"][0]["id"]
    elif mutation == "duplicate_step":
        value["flows"][1]["steps"][0]["id"] = value["flows"][0]["steps"][0]["id"]
    elif mutation == "unknown_requirement":
        value["flows"][0]["steps"][0]["requirement_ids"] = ["ABD-PRD-REQ-999"]
    elif mutation == "orphan_requirement":
        for flow in value["flows"]:
            for step in flow["steps"]:
                step["requirement_ids"] = [item for item in step["requirement_ids"] if item != "ABD-PRD-REQ-001"]
    elif mutation == "terminal":
        value["flows"][0]["success_terminal"] = "UNKNOWN"
    elif mutation == "external":
        value["flows"][0]["external_effect_in_s01_p03"] = True
    elif mutation == "missing_error":
        value["error_paths"].pop(0)
    elif mutation == "unknown_flow":
        value["error_paths"][0]["affected_flow_ids"] = ["FLOW-999"]
    elif mutation == "unsafe_equals_forbidden":
        value["error_paths"][0]["forbidden_action"] = value["error_paths"][0]["safe_action"]
    elif mutation == "summary":
        value["traceability_summary"]["error_path_count"] = 12
    elif mutation == "boundary":
        value["s01_p03_execution_boundary"]["runtime_flow_executed"] = True
    else:
        value["status"] = "RUNTIME_PROVEN"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("evidence_status", "S01P03-P02-IMMUTABLE-RECEIPT"),
        ("decision_hash", "S01P03-P02-IMMUTABLE-RECEIPT"),
        ("external_effect", "S01P03-P02-IMMUTABLE-RECEIPT"),
        ("rollback_status", "S01P03-P02-IMMUTABLE-RECEIPT"),
        ("p02_artifact", "S01P03-P02-SIGNED-ARTIFACTS"),
        ("index_status", "S01P03-P02-EVIDENCE-INDEX"),
        ("stage0_receipt", "S01P03-STAGE0-DELIVERY-CHAIN"),
    ],
)
def test_p02_prerequisite_mutations_block_p03(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation in {"evidence_status", "decision_hash", "external_effect"}:
        path = project / P02_EVIDENCE_PATH
        value = strict_json_load(path)
        if mutation == "evidence_status":
            value["status"] = "FAIL"
        elif mutation == "decision_hash":
            value["decision_sha256"] = "0" * 64
        else:
            value["external_effect_boundary"]["github_upload_performed"] = True
        _write_json(path, value)
    elif mutation == "rollback_status":
        path = project / P02_ROLLBACK_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "p02_artifact":
        (project / "customer_faq.md").write_text("drift\n", encoding="utf-8")
    elif mutation == "index_status":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-AC-S01-P02")["status"] = "PLANNED"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    else:
        path = project / "machine/evidence/S00/STAGE_REVIEW/github_delivery_receipt.json"
        value = strict_json_load(path)
        value["pull_request"]["state"] = "OPEN"
        _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize("mutation", ["evidence_hash_drift", "partial_outputs", "index_hash_drift"])
def test_p04_progression_requires_complete_outputs_and_signed_p03_receipt(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "evidence_hash_drift":
        (project / "machine/evidence/EVD-S01-P04.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "partial_outputs":
        (project / "kill_criteria.json").unlink()
    else:
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-AC-S01-P04")["artifact_sha256"] = "0" * 64
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    _failed(evaluate_contract(project), "S01P03-SUCCESSOR-PROGRESSION-GATED")


@pytest.mark.parametrize("mutation", ["floating_action", "missing_regression", "secret_reference"])
def test_continuous_workflow_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project.parent / CONTINUOUS_WORKFLOW_PATH
    text = path.read_text(encoding="utf-8")
    if mutation == "floating_action":
        text = text.replace("actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", "actions/checkout@v7")
    elif mutation == "missing_regression":
        text = text.replace("python -m pytest -q", "python -m pytest -q tests/S01/P03_test.py")
    else:
        text += "\n# " + "$" + "{{ secrets.ABD_TOKEN }}\n"
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), "S01P03-CONTINUOUS-CI")


@pytest.mark.parametrize(
    "target,expected",
    [
        ("requirements", "S01P03-PRODUCT-REQUIREMENTS-STRICT-JSON"),
        ("scope", "S01P03-SCOPE-STRICT-JSON"),
        ("flows", "S01P03-FLOWS-STRICT-JSON"),
        ("fixture", "S01P03-FIXTURE-STRICT-JSON"),
        ("p02_evidence", "S01P03-SOURCE-EVD-S01-P02-STRICT-JSON"),
    ],
)
def test_duplicate_json_keys_fail_closed(tmp_path: Path, target: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    paths = {
        "requirements": REQUIREMENTS_PATH,
        "scope": SCOPE_PATH,
        "flows": FLOWS_PATH,
        "fixture": FIXTURE_PATH,
        "p02_evidence": P02_EVIDENCE_PATH,
    }
    path = project / paths[target]
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", '{\n  "schema_version": "duplicate",', 1), encoding="utf-8")
    _failed(evaluate_contract(project), expected)


def test_evidence_is_deterministic_without_runtime_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["external_effect_boundary"]["github_upload_performed"] is False
    assert first["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"
    assert first["external_effect_boundary"]["return_or_guarantee_claimed"] is False
    assert first["external_effect_boundary"]["p04_artifacts_created"] is False
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert "/" + "Users/" not in rendered
    assert "/" + "home/" not in rendered


def test_rollback_drill_restores_all_signed_phase_inputs() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 7
    assert all(row["signed_sha256"] == row["restored_sha256"] for row in result["artifacts"].values())


def test_evaluation_does_not_mutate_inputs() -> None:
    paths = [
        ROOT / REQUIREMENTS_PATH,
        ROOT / SCOPE_PATH,
        ROOT / FLOWS_PATH,
        ROOT / FIXTURE_PATH,
        ROOT / P02_EVIDENCE_PATH,
        ROOT / P02_ROLLBACK_PATH,
        ROOT.parent / CONTINUOUS_WORKFLOW_PATH,
    ]
    before = {path.as_posix(): sha256_file(path) for path in paths}
    result = evaluate_contract(ROOT, require_external_reports=False)
    after = {path.as_posix(): sha256_file(path) for path in paths}
    assert result["status"] == "PASS"
    assert before == after


def test_external_reports_are_required_for_final_phase_evidence(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (project / relative).unlink(missing_ok=True)
    result = evaluate_contract(project, require_external_reports=True)
    assert result["status"] == "FAIL"
    assert "S01P03-TEST-TARGETED-PASS" in result["summary"]["failed_check_ids"]
    assert "S01P03-TEST-FULL-REGRESSION-PASS" in result["summary"]["failed_check_ids"]
