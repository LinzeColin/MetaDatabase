from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.metrics_economics import (
    ECONOMICS_PATH,
    EVIDENCE_PATH,
    FIXTURE_PATH,
    KILL_PATH,
    METRICS_PATH,
    P03_COMMIT,
    P03_EVIDENCE_PATH,
    P03_EVIDENCE_SHA256,
    P03_ROLLBACK_PATH,
    P03_ROLLBACK_SHA256,
    build_evidence,
    classify_target_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_incremental_cost_gate,
    resolve_kill_default,
    resolve_roi_default,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    is_real_tree = Path(root).resolve() == ROOT.resolve()
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=is_real_tree,
        _allow_stage_review_candidate=is_real_tree,
    )


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


def _row(rows, item_id: str):
    return next(row for row in rows if row["id"] == item_id)


def test_baseline_metrics_economics_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 110
    assert result["decision"] == "METRICS_ECONOMICS_AND_KILL_CONTRACT_FROZEN"
    assert result["release_status"] == "NOT_READY_STAGE_REVIEW_REQUIRED"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["roi_status"] == "NOT_COMPUTABLE"
    assert result["next"] == "S01/STAGE_REVIEW_READY_NOT_STARTED"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p03_immutable_receipt_and_git_ancestry_are_verified() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["S01P04-P03-IMMUTABLE-RECEIPT"]["passed"] is True
    assert checks["S01P04-P03-SIGNED-ARTIFACTS"]["passed"] is True
    assert checks["S01P04-P03-EVIDENCE-INDEX"]["passed"] is True
    assert checks["S01P04-P03-GIT-ANCESTRY"]["passed"] is True
    assert sha256_file(ROOT / P03_EVIDENCE_PATH) == P03_EVIDENCE_SHA256
    assert sha256_file(ROOT / P03_ROLLBACK_PATH) == P03_ROLLBACK_SHA256
    assert P03_COMMIT == "a4d5e3076f1e327072680207944a2d75514b1f03"


@pytest.mark.parametrize("relative", [METRICS_PATH, ECONOMICS_PATH, KILL_PATH, FIXTURE_PATH])
def test_phase_artifact_hashes_match_frozen_fixture(relative: Path) -> None:
    expected = FIXTURE["expected_artifact_hashes"].get(relative.as_posix())
    if relative == FIXTURE_PATH:
        expected = "7abb7982198c21a41b04f677c64fe8c6b5ad23b5068b0d2171b18569759c3b14"
    assert expected is not None
    assert sha256_file(ROOT / relative) == expected


@pytest.mark.parametrize("case", FIXTURE["target_classification_vectors"], ids=lambda case: case["name"])
def test_target_classification_boundaries_are_falsifiable(case) -> None:
    inputs = {key: value for key, value in case.items() if key not in {"name", "expected"}}
    assert classify_target_evidence(**inputs) == case["expected"]


VALID_TARGET_INPUT = {
    "complete_days": 90,
    "complete_months": 3,
    "signals": 1000,
    "median_monthly_log_growth": "0.26236426446749106",
    "monthly_log_growth_p05": "0.0001",
    "capacity_pass": True,
    "monthly_return_95pct_upper_bound": "0.40",
    "cashflow_adjusted_geometric_monthly_return": None,
    "complete_execution_evidence": False,
    "unresolved_reconciliation_differences": None,
}


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete_days", True),
        ("complete_days", -1),
        ("complete_days", "90"),
        ("complete_months", -1),
        ("signals", 1.0),
        ("capacity_pass", 1),
        ("complete_execution_evidence", None),
        ("unresolved_reconciliation_differences", -1),
        ("unresolved_reconciliation_differences", True),
        ("median_monthly_log_growth", "NaN"),
        ("monthly_log_growth_p05", 0.1),
        ("monthly_return_95pct_upper_bound", " Infinity"),
        ("cashflow_adjusted_geometric_monthly_return", {}),
    ],
)
def test_malformed_target_evidence_fails_closed(field, value) -> None:
    inputs = dict(VALID_TARGET_INPUT)
    inputs[field] = value
    assert classify_target_evidence(**inputs) == "INVALID_TARGET_EVIDENCE"


@pytest.mark.parametrize("case", FIXTURE["incremental_cost_vectors"])
def test_incremental_cost_gate_is_exact_and_unknown_blocks(case) -> None:
    assert resolve_incremental_cost_gate(case["value"]) == case["expected"]


@pytest.mark.parametrize("malformed", [0, 0.0, True, {}, [], "", " NaN", "Infinity"])
def test_malformed_incremental_cost_fails_closed(malformed) -> None:
    assert resolve_incremental_cost_gate(malformed) == "FAIL_INVALID_INCREMENTAL_COST"


@pytest.mark.parametrize("case", FIXTURE["roi_vectors"])
def test_roi_never_uses_unknown_or_zero_denominator(case) -> None:
    result = resolve_roi_default(case["verified_benefit_aud"], case["complete_total_economic_cost_aud"])
    assert result == {"status": case["expected_status"], "value": case["expected_value"]}


@pytest.mark.parametrize(
    "benefit,cost",
    [(1, "1"), ("1", 1), (True, "1"), ("1", False), ("NaN", "1"), ("1", "Infinity")],
)
def test_malformed_roi_inputs_never_produce_value(benefit, cost) -> None:
    assert resolve_roi_default(benefit, cost) == {"status": "INVALID_INPUT", "value": None}


@pytest.mark.parametrize("values", list(itertools.product([False, True], repeat=3)))
def test_kill_evaluation_truth_table_fails_closed(values) -> None:
    evidence_complete, threshold_evaluable, triggered = values
    result = resolve_kill_default(
        evidence_complete=evidence_complete,
        threshold_evaluable=threshold_evaluable,
        triggered=triggered,
    )
    if not evidence_complete or not threshold_evaluable:
        assert result == "UNVERIFIED_BLOCK_AFFECTED_DECISION"
    elif triggered:
        assert result == "APPLY_PREREGISTERED_KILL_ACTION"
    else:
        assert result == "CLEARED_FOR_PREREGISTERED_SCOPE_ONLY"


@pytest.mark.parametrize(
    "values",
    [
        (1, True, False),
        (True, None, False),
        (True, True, 0),
        ("true", True, False),
        (True, [], False),
        (True, True, "false"),
    ],
)
def test_malformed_kill_evaluation_blocks(values) -> None:
    assert (
        resolve_kill_default(
            evidence_complete=values[0],
            threshold_evaluable=values[1],
            triggered=values[2],
        )
        == "BLOCK_MALFORMED_KILL_EVALUATION"
    )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("roadmap", "S01P04-ROADMAP-EXACT"),
        ("requirement", "S01P04-REQUIREMENT-EXACT"),
        ("acceptance", "S01P04-ACCEPTANCE-CONTRACT-EXACT"),
        ("task_dependency", "S01P04-TASK-CHAIN-EXACT"),
        ("task_output", "S01P04-TASK-CHAIN-EXACT"),
        ("task_owner", "S01P04-TASK-CHAIN-EXACT"),
        ("traceability", "S01P04-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_semantics_cannot_drift(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "roadmap":
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = next(row for row in next(row for row in value["stages"] if row["id"] == "S01")["phases"] if row["id"] == "P04")
        phase["objective"] = "drift"
    elif mutation == "requirement":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        _row(value, "REQ-S01-P04")["target"] = "drift"
    elif mutation == "acceptance":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        _row(value, "AC-S01-P04")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = _row(value["tasks"], "T-S01-P04-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"] = ["wrong"]
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        next(row for row in value if row["requirement_id"] == "REQ-S01-P04")["artifact_ids"] = []
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S01P04-METRICS-TOP-LEVEL"),
        ("next", "S01P04-METRICS-TOP-LEVEL"),
        ("duplicate_id", "S01P04-METRIC-IDS-EXACT-UNIQUE"),
        ("duplicate_name", "S01P04-METRIC-NAMES-UNIQUE"),
        ("unknown_requirement", "S01P04-METRIC-REQUIREMENT-ROUTES"),
        ("coverage_gap", "S01P04-ALL-REQUIREMENTS-MEASURED-EXACT"),
        ("baseline_maturity", "S01P04-NULL-BASELINES-NEVER-PASS"),
        ("baseline_fake_pass", "S01P04-NULL-BASELINES-NEVER-PASS"),
        ("measurement", "S01P04-MEASUREMENT-CONTRACTS-COMPLETE"),
        ("empty_source", "S01P04-METRIC-ROWS-COMPLETE"),
        ("semantics", "S01P04-METRIC-SEMANTICS-FAIL-CLOSED"),
        ("summary", "S01P04-METRIC-SUMMARY-EXACT"),
        ("core_threshold", "S01P04-CORE-METRIC-THRESHOLDS-EXACT"),
        ("privacy_threshold", "S01P04-CORE-METRIC-THRESHOLDS-EXACT"),
        ("plausible_threshold", "S01P04-TARGET-CLASSIFICATION-GATES-EXACT"),
        ("verification_threshold", "S01P04-TARGET-CLASSIFICATION-GATES-EXACT"),
        ("boundary", "S01P04-METRICS-NO-RUNTIME-OR-RETURN-CLAIM"),
        ("source_binding", "S01P04-METRICS-SOURCE-BINDINGS"),
        ("source_pointer", "S01P04-METRIC-SOURCE-POINTERS-RESOLVE"),
        ("binary_float", "S01P04-METRICS-NO-BINARY-FLOAT"),
    ],
)
def test_metric_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / METRICS_PATH
    value = strict_json_load(path)
    rows = value["metrics"]
    if mutation == "status":
        value["status"] = "MEASURED"
    elif mutation == "next":
        value["next_on_acceptance_pass"] = "RELEASE"
    elif mutation == "duplicate_id":
        rows[1]["id"] = rows[0]["id"]
    elif mutation == "duplicate_name":
        rows[1]["name"] = rows[0]["name"]
    elif mutation == "unknown_requirement":
        rows[0]["requirement_ids"] = ["ABD-PRD-REQ-999"]
    elif mutation == "coverage_gap":
        _row(rows, "MET-S01-P04-028")["requirement_ids"] = ["ABD-PRD-REQ-001"]
    elif mutation == "baseline_maturity":
        rows[0]["baseline"]["evidence_maturity"] = "VERIFIED_ACTUAL_EXECUTION_AND_RECONCILIATION"
    elif mutation == "baseline_fake_pass":
        rows[0]["baseline"]["status"] = "PASS"
    elif mutation == "measurement":
        rows[0]["measurement"]["minimum_sample"] = 0
    elif mutation == "empty_source":
        rows[0]["source_evidence"] = []
    elif mutation == "semantics":
        value["metric_semantics"]["missing_or_null_baseline"] = "PASS"
    elif mutation == "summary":
        value["traceability_summary"]["metric_count"] = 30
    elif mutation == "core_threshold":
        _row(rows, "MET-S01-P04-006")["target"]["value"] = "0.9949"
    elif mutation == "privacy_threshold":
        _row(rows, "MET-S01-P04-030")["target"]["value"] = 1
    elif mutation == "plausible_threshold":
        _row(rows, "MET-S01-P04-024")["target"]["minimum_days"] = 89
    elif mutation == "verification_threshold":
        _row(rows, "MET-S01-P04-026")["target"]["cashflow_adjusted_geometric_monthly_return_min"] = "0.2999"
    elif mutation == "boundary":
        value["s01_p04_execution_boundary"]["target_plausibility_or_return_verified"] = True
    elif mutation == "source_binding":
        value["source_bindings"]["machine/facts/parameters.json"] = "0" * 64
    elif mutation == "source_pointer":
        rows[0]["source_evidence"][0]["pointers"] = ["/missing"]
    else:
        rows[0]["measurement"]["minimum_sample"] = 1.5
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S01P04-ECONOMICS-TOP-LEVEL"),
        ("source_binding", "S01P04-ECONOMICS-SOURCE-BINDINGS"),
        ("zero_total_cost", "S01P04-ECONOMIC-SEMANTICS-NO-ZERO-COST-OR-GUARANTEE"),
        ("budget", "S01P04-COST-ENVELOPE-EXACT-UNKNOWN-NOT-ZERO"),
        ("phase_spend", "S01P04-COST-ENVELOPE-EXACT-UNKNOWN-NOT-ZERO"),
        ("program_cost", "S01P04-COST-ENVELOPE-EXACT-UNKNOWN-NOT-ZERO"),
        ("existing_cost", "S01P04-COST-ENVELOPE-EXACT-UNKNOWN-NOT-ZERO"),
        ("effort", "S01P04-COST-ENVELOPE-EXACT-UNKNOWN-NOT-ZERO"),
        ("opportunity", "S01P04-OPPORTUNITY-COST-SENSITIVITY-EXACT"),
        ("target_forecast", "S01P04-TARGET-CURVE-NOT-FORECAST-OR-GUARANTEE"),
        ("target_guarantee", "S01P04-TARGET-CURVE-NOT-FORECAST-OR-GUARANTEE"),
        ("benefit", "S01P04-BENEFIT-AND-LOSS-RANGES-UNVERIFIED"),
        ("loss", "S01P04-BENEFIT-AND-LOSS-RANGES-UNVERIFIED"),
        ("noncash_value", "S01P04-NONCASH-BENEFITS-TRACEABLE-NOT-MONETIZED"),
        ("noncash_metric", "S01P04-NONCASH-BENEFITS-TRACEABLE-NOT-MONETIZED"),
        ("noncash_empty", "S01P04-NONCASH-BENEFITS-TRACEABLE-NOT-MONETIZED"),
        ("roi", "S01P04-ROI-NPV-PAYBACK-NOT-FABRICATED"),
        ("feasibility", "S01P04-FEASIBILITY-GATES-EXACT-UNVERIFIED"),
        ("decision", "S01P04-ECONOMIC-DECISIONS-FAIL-CLOSED"),
        ("boundary", "S01P04-ECONOMICS-NO-EXTERNAL-OR-RETURN-EFFECT"),
        ("binary_float", "S01P04-ECONOMICS-NO-BINARY-FLOAT"),
        ("source_pointer", "S01P04-ECONOMICS-SOURCE-POINTERS-RESOLVE"),
    ],
)
def test_economic_mutations_never_fabricate_value(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / ECONOMICS_PATH
    value = strict_json_load(path)
    if mutation == "status":
        value["status"] = "ROI_PASS"
    elif mutation == "source_binding":
        value["source_bindings"]["metrics.json"] = "0" * 64
    elif mutation == "zero_total_cost":
        value["economic_semantics"]["total_system_cost_is_zero"] = True
    elif mutation == "budget":
        value["cost_envelope"]["incremental_cash_budget_aud"]["high"] = "0.0001"
    elif mutation == "phase_spend":
        value["cost_envelope"]["current_phase_incremental_cash_spent_aud"] = "0.0001"
    elif mutation == "program_cost":
        value["cost_envelope"]["program_actual_incremental_cash_cost_aud"]["value"] = "0.00"
    elif mutation == "existing_cost":
        value["cost_envelope"]["existing_recurring_cash_cost_aud"]["likely"] = "0.00"
    elif mutation == "effort":
        value["cost_envelope"]["development_effort_hours"]["likely"] = 319
    elif mutation == "opportunity":
        value["opportunity_cost_sensitivity"]["scenarios"][0]["likely_aud"] = "9599.99"
    elif mutation == "target_forecast":
        value["target_curve_contract"]["is_cash_benefit_forecast"] = True
    elif mutation == "target_guarantee":
        value["target_curve_contract"]["is_guarantee"] = True
    elif mutation == "benefit":
        value["benefit_envelope"]["realized_cash_benefit_aud"]["likely"] = "90.00"
    elif mutation == "loss":
        value["benefit_envelope"]["loss_range_aud"]["low"] = "0.00"
    elif mutation == "noncash_value":
        value["benefit_envelope"]["non_cash_benefits"][0]["monetized_value_aud"] = "1.00"
    elif mutation == "noncash_metric":
        value["benefit_envelope"]["non_cash_benefits"][0]["measurement_metric_ids"] = ["MET-UNKNOWN"]
    elif mutation == "noncash_empty":
        value["benefit_envelope"]["non_cash_benefits"][3]["measurement_metric_ids"] = []
    elif mutation == "roi":
        value["roi_contract"]["roi"] = "0.30"
    elif mutation == "feasibility":
        value["capacity_and_feasibility_contract"]["target_economic_feasibility"] = "PASS"
    elif mutation == "decision":
        value["decision_rules"][0]["action"] = "BUY"
    elif mutation == "boundary":
        value["s01_p04_execution_boundary"]["roi_computed_or_claimed"] = True
    elif mutation == "binary_float":
        value["cost_envelope"]["development_effort_hours"]["low"] = 240.0
    else:
        value["cost_envelope"]["source_evidence"][0]["pointers"] = ["/missing"]
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S01P04-KILL-TOP-LEVEL"),
        ("source_binding", "S01P04-KILL-SOURCE-BINDINGS"),
        ("duplicate_id", "S01P04-KILL-IDS-EXACT-UNIQUE"),
        ("unknown_metric", "S01P04-KILL-METRIC-ROUTES-VALID"),
        ("missing_field", "S01P04-KILL-ROWS-COMPLETE"),
        ("dangerous_action", "S01P04-KILL-ACTIONS-NO-ORDER-OR-SPEND"),
        ("unknown_pass", "S01P04-KILL-SEMANTICS-FAIL-CLOSED"),
        ("contract_kill", "S01P04-KILL-SEMANTICS-FAIL-CLOSED"),
        ("relax_gate", "S01P04-KILL-SEMANTICS-FAIL-CLOSED"),
        ("cost_threshold", "S01P04-KILL-THRESHOLDS-EXACT"),
        ("target_threshold", "S01P04-KILL-THRESHOLDS-EXACT"),
        ("drawdown_threshold", "S01P04-KILL-THRESHOLDS-EXACT"),
        ("drift_threshold", "S01P04-KILL-THRESHOLDS-EXACT"),
        ("performed", "S01P04-NO-FABRICATED-CURRENT-KILL-EVALUATION"),
        ("triggered", "S01P04-NO-FABRICATED-CURRENT-KILL-EVALUATION"),
        ("unknown_list", "S01P04-NO-FABRICATED-CURRENT-KILL-EVALUATION"),
        ("release", "S01P04-NO-FABRICATED-CURRENT-KILL-EVALUATION"),
        ("boundary", "S01P04-KILL-NO-RUNTIME-OR-EXTERNAL-EFFECT"),
        ("source_pointer", "S01P04-KILL-SOURCE-POINTERS-RESOLVE"),
        ("binary_float", "S01P04-KILL-NO-BINARY-FLOAT"),
    ],
)
def test_kill_contract_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / KILL_PATH
    value = strict_json_load(path)
    rows = value["criteria"]
    if mutation == "status":
        value["status"] = "CURRENTLY_KILLED"
    elif mutation == "source_binding":
        value["source_bindings"]["economics.json"] = "0" * 64
    elif mutation == "duplicate_id":
        rows[1]["id"] = rows[0]["id"]
    elif mutation == "unknown_metric":
        rows[0]["metric_ids"] = ["MET-UNKNOWN"]
    elif mutation == "missing_field":
        rows[0]["reentry_gate"] = ""
    elif mutation == "dangerous_action":
        rows[0]["action"] = "SUBMIT_ORDER"
    elif mutation == "unknown_pass":
        value["evaluation_semantics"]["missing_or_incomplete_evidence_is_pass"] = True
    elif mutation == "contract_kill":
        value["evaluation_semantics"]["contract_only_baseline_may_trigger_empirical_kill"] = True
    elif mutation == "relax_gate":
        value["evaluation_semantics"]["target_shortfall_may_relax_any_gate"] = True
    elif mutation == "cost_threshold":
        _row(rows, "KC-S01-P04-001")["condition"]["threshold"] = "0.0001"
    elif mutation == "target_threshold":
        _row(rows, "KC-S01-P04-009")["condition"]["threshold"] = "PLAUSIBLE"
    elif mutation == "drawdown_threshold":
        _row(rows, "KC-S01-P04-010")["condition"]["threshold"] = "0.101"
    elif mutation == "drift_threshold":
        _row(rows, "KC-S01-P04-016")["condition"]["threshold"]["jensen_shannon"] = "0.11"
    elif mutation == "performed":
        value["current_evaluation"]["performed"] = True
    elif mutation == "triggered":
        value["current_evaluation"]["triggered_criterion_ids"] = ["KC-S01-P04-001"]
    elif mutation == "unknown_list":
        value["current_evaluation"]["unknown_criterion_ids"].pop()
    elif mutation == "release":
        value["current_evaluation"]["release_effect"] = "RELEASE"
    elif mutation == "boundary":
        value["s01_p04_execution_boundary"]["kill_criteria_evaluated_against_runtime"] = True
    elif mutation == "source_pointer":
        rows[0]["source_evidence"][0]["pointers"] = ["/missing"]
    else:
        _row(rows, "KC-S01-P04-010")["condition"]["threshold"] = 0.1
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("phase_evidence", "S01P04-P03-IMMUTABLE-RECEIPT"),
        ("rollback", "S01P04-P03-IMMUTABLE-RECEIPT"),
        ("signed_artifact", "S01P04-P03-SIGNED-ARTIFACTS"),
        ("index", "S01P04-P03-EVIDENCE-INDEX"),
    ],
)
def test_p03_prerequisite_mutations_block_p04(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "phase_evidence":
        path = project / P03_EVIDENCE_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "rollback":
        path = project / P03_ROLLBACK_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "signed_artifact":
        path = project / "requirements.json"
        value = strict_json_load(path)
        value["status"] = "drift"
        _write_json(path, value)
    else:
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        _row(rows, "INDEX-AC-S01-P03")["status"] = "FAIL"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize("mutation", ["review_evidence", "review_index", "review_directory"])
def test_stage_review_is_not_started_inside_p04_run(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "review_evidence":
        (project / "machine/evidence/EVD-S01-STAGE-REVIEW.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "review_index":
        path = project / "machine/evidence/evidence_index.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": "INDEX-S01-STAGE-REVIEW", "status": "PLANNED"}) + "\n")
    else:
        (project / "machine/evidence/S01/REVIEW").mkdir(parents=True)
    _failed(evaluate_contract(project), "S01P04-STAGE-REVIEW-NOT-STARTED")


@pytest.mark.parametrize("relative", [METRICS_PATH, ECONOMICS_PATH, KILL_PATH, FIXTURE_PATH])
def test_duplicate_json_keys_fail_strict_parse(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"schema_version":"1.0.0","schema_version":"drift"}\n', encoding="utf-8")
    result = evaluate_contract(project)
    assert result["status"] == "FAIL"
    strict_ids = {
        METRICS_PATH: "S01P04-METRICS-STRICT-JSON",
        ECONOMICS_PATH: "S01P04-ECONOMICS-STRICT-JSON",
        KILL_PATH: "S01P04-KILL-STRICT-JSON",
        FIXTURE_PATH: "S01P04-FIXTURE-STRICT-JSON",
    }
    _failed(result, strict_ids[relative])


def test_rollback_drill_restores_every_signed_input_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 7
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_and_contains_no_absolute_paths() -> None:
    first, first_rollback = build_evidence(
        ROOT,
        require_external_reports=False,
        _allow_stage_review_candidate=True,
    )
    second, second_rollback = build_evidence(
        ROOT,
        require_external_reports=False,
        _allow_stage_review_candidate=True,
    )
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS"
    assert first["next"] == "S01/STAGE_REVIEW_READY_NOT_STARTED"
    assert first["external_effect_boundary"]["stage_review_started"] is False
    assert first["external_effect_boundary"]["real_order_capability_present"] is False
    assert first["external_effect_boundary"]["return_or_guarantee_claimed"] is False
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert str(ROOT) not in rendered
    assert first["decision_sha256"]


def test_artifacts_make_no_runtime_deployment_or_return_claim() -> None:
    metrics = strict_json_load(ROOT / METRICS_PATH)
    economics = strict_json_load(ROOT / ECONOMICS_PATH)
    kill = strict_json_load(ROOT / KILL_PATH)
    assert metrics["s01_p04_execution_boundary"]["metrics_measured_against_runtime"] is False
    assert metrics["s01_p04_execution_boundary"]["target_plausibility_or_return_verified"] is False
    assert economics["roi_contract"]["roi"] is None
    assert economics["roi_contract"]["net_present_value"] is None
    assert economics["roi_contract"]["payback_period"] is None
    assert kill["current_evaluation"]["performed"] is False
    assert kill["current_evaluation"]["triggered_criterion_ids"] is None
    assert all(
        artifact["next_on_acceptance_pass"] == "S01/STAGE_REVIEW_READY_NOT_STARTED"
        for artifact in [metrics, economics, kill]
    )
