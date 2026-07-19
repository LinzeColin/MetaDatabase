from __future__ import annotations

import itertools
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.customer_press_release import (
    CONTINUOUS_WORKFLOW_PATH,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    OUTCOMES_PATH,
    PRESS_RELEASE_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_card_decision,
)
from abd_acceptance.delivery import RECEIPT_PATH, verify_stage0_delivery


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    is_real_tree = Path(root).resolve() == ROOT.resolve()
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=is_real_tree,
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _outcome(value, outcome_id: str):
    return next(row for row in value["observable_outcomes"] if row["id"] == outcome_id)


def _action(value, action_id: str):
    return next(row for row in value["actions"] if row["id"] == action_id)


def test_baseline_customer_press_release_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 55
    assert result["decision"] == "CUSTOMER_OUTCOME_CONTRACT_FROZEN"
    assert result["release_status"] == "NOT_READY"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S01/P02_READY_NOT_STARTED"


def test_stage0_delivery_receipt_is_independently_verified() -> None:
    result = verify_stage0_delivery(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 17
    assert result["decision"] == "S00_DELIVERED_S01_MAY_START"
    assert result["external_network_used_by_verifier"] is False


@pytest.mark.parametrize("case", FIXTURE["decision_scenarios"], ids=lambda case: case["id"])
def test_customer_decision_scenarios_fail_closed(case) -> None:
    actual = resolve_card_decision(
        evidence_complete=case["evidence_complete"],
        fresh=case["fresh"],
        stable_under_adverse_tests=case["stable_under_adverse_tests"],
        risk_gate_passed=case["risk_gate_passed"],
    )
    assert actual == case["expected"]


@pytest.mark.parametrize(
    ("evidence_complete", "fresh", "stable", "risk"),
    list(itertools.product([False, True], repeat=4)),
)
def test_only_all_four_true_gates_can_produce_recommendation(
    evidence_complete: bool,
    fresh: bool,
    stable: bool,
    risk: bool,
) -> None:
    result = resolve_card_decision(
        evidence_complete=evidence_complete,
        fresh=fresh,
        stable_under_adverse_tests=stable,
        risk_gate_passed=risk,
    )
    expected = "RECOMMENDATION" if all((evidence_complete, fresh, stable, risk)) else "NO_RECOMMENDATION"
    assert result == expected


@pytest.mark.parametrize(
    "relative",
    [
        "machine/facts/canonical_facts.json",
        "machine/facts/parameters.json",
        "machine/facts/requirements.json",
        "machine/facts/acceptance_contracts.json",
        "machine/facts/task_graph.json",
        "machine/facts/roadmap.json",
    ],
)
def test_baseline_source_drift_fails_closed(tmp_path: Path, relative: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    value = strict_json_load(path)
    if isinstance(value, dict):
        value["s01_p01_injected_drift"] = True
    else:
        value.append({"id": "S01-P01-INJECTED-DRIFT"})
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01P01-HASH-%s" % path.stem.upper())


@pytest.mark.parametrize(
    "mutation",
    ["roadmap_output", "requirement_scope", "acceptance_oracle", "task_dependency", "trace_artifact"],
)
def test_taskpack_contract_semantics_cannot_drift(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "roadmap_output":
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        stage = next(row for row in value["stages"] if row["id"] == "S01")
        next(row for row in stage["phases"] if row["id"] == "P01")["outputs"].pop()
        expected = "S01P01-ROADMAP-EXACT"
    elif mutation == "requirement_scope":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "REQ-S01-P01")["scope"].append("customer_faq.md")
        expected = "S01P01-REQUIREMENT-EXACT"
    elif mutation == "acceptance_oracle":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "AC-S01-P01")["oracle"]["type"] = "SELF_REPORTED"
        expected = "S01P01-ACCEPTANCE-CONTRACT-EXACT"
    elif mutation == "task_dependency":
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        next(row for row in value["tasks"] if row["id"] == "T-S01-P01-03")["depends_on"] = []
        expected = "S01P01-TASK-CHAIN-EXACT"
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        next(row for row in value if row["requirement_id"] == "REQ-S01-P01")["artifact_ids"].pop()
        expected = "S01P01-TRACEABILITY-EXACT"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation",
    ["jargon", "current_claim", "missing_concept", "missing_section", "duplicate_section", "url", "too_short", "unsafe_order", "second_h1"],
)
def test_press_release_mutations_fail_customer_contract(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project / PRESS_RELEASE_PATH
    text = path.read_text(encoding="utf-8")
    if mutation == "jargon":
        text += "\nAPI 会替用户处理一切。\n"
        expected = "S01P01-PRESS-RELEASE-NO-JARGON"
    elif mutation == "current_claim":
        text += "\n产品已上线并保证收益。\n"
        expected = "S01P01-PRESS-RELEASE-NO-FALSE-CURRENT-CLAIM"
    elif mutation == "missing_concept":
        text = text.replace("证据状态", "资料情况")
        expected = "S01P01-PRESS-RELEASE-OBSERVABLE-CONCEPTS"
    elif mutation == "missing_section":
        text = text.replace("## 重要边界", "### 重要边界")
        expected = "S01P01-PRESS-RELEASE-STRUCTURE"
    elif mutation == "duplicate_section":
        text += "\n## 标题\n\n重复。\n"
        expected = "S01P01-PRESS-RELEASE-STRUCTURE"
    elif mutation == "url":
        text += "\nhttps://example.invalid\n"
        expected = "S01P01-PRESS-RELEASE-STRUCTURE"
    elif mutation == "too_short":
        text = "# ABD 客户新闻稿（目标体验稿）\n\n## 标题\n\n每天一张卡。\n"
        expected = "S01P01-PRESS-RELEASE-CUSTOMER-LANGUAGE"
    elif mutation == "unsafe_order":
        text = text.replace("自动提交次数必须始终为零", "自动提交次数可以为一")
        expected = "S01P01-CROSS-DOCUMENT-CONSISTENCY"
    else:
        text += "\n# 第二份新闻稿\n"
        expected = "S01P01-PRESS-RELEASE-STRUCTURE"
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "source_binding",
        "daily_count",
        "extra_state",
        "automatic_order",
        "unsafe_failure_action",
        "duplicate_outcome",
        "non_object_outcome",
        "fake_implemented",
        "stability",
        "non_goal",
        "production_claim",
        "next_phase",
        "guaranteed_target",
    ],
)
def test_customer_outcome_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project / OUTCOMES_PATH
    value = strict_json_load(path)
    if mutation == "status":
        value["status"] = "PRODUCTION_DEPLOYED"
        expected = "S01P01-OUTCOMES-TOP-LEVEL"
    elif mutation == "source_binding":
        value["source_bindings"]["machine/facts/canonical_facts.json"] = "0" * 64
        expected = "S01P01-OUTCOMES-SOURCE-BINDINGS"
    elif mutation == "daily_count":
        value["experience_contract"]["cards_per_calendar_day"] = 2
        expected = "S01P01-OUTCOMES-EXPERIENCE-EXACT"
    elif mutation == "extra_state":
        value["experience_contract"]["allowed_decision_states"].append("UNKNOWN")
        expected = "S01P01-OUTCOMES-EXPERIENCE-EXACT"
    elif mutation == "automatic_order":
        _outcome(value, "OUT-S01-P01-03")["measurement"]["automatic_order_submission_count"] = 1
        expected = "S01P01-OUTCOME-OWNER-ORDER-MEASURE"
    elif mutation == "unsafe_failure_action":
        _outcome(value, "OUT-S01-P01-04")["measurement"]["critical_gate_failure_action"] = "RECOMMENDATION"
        expected = "S01P01-OUTCOME-FAIL-CLOSED-MEASURE"
    elif mutation == "duplicate_outcome":
        value["observable_outcomes"][-1] = deepcopy(value["observable_outcomes"][0])
        expected = "S01P01-OUTCOMES-OBSERVABLE-ROWS"
    elif mutation == "non_object_outcome":
        value["observable_outcomes"][0] = "malformed"
        expected = "S01P01-OUTCOMES-OBSERVABLE-ROWS"
    elif mutation == "fake_implemented":
        value["observable_outcomes"][0]["current_evidence_status"] = "VERIFIED_IN_PRODUCTION"
        expected = "S01P01-OUTCOMES-OBSERVABLE-ROWS"
    elif mutation == "stability":
        value["adverse_stability_contract"]["friction_perturbation"] = "+0.001"
        expected = "S01P01-OUTCOMES-ADVERSE-STABILITY-BINDING"
    elif mutation == "non_goal":
        value["non_goals"].pop()
        expected = "S01P01-OUTCOMES-NON-GOALS-EXACT"
    elif mutation == "production_claim":
        value["claim_boundaries"]["production_deployment_claimed"] = True
        expected = "S01P01-OUTCOMES-CLAIM-BOUNDARIES"
    elif mutation == "next_phase":
        value["next_on_acceptance_pass"] = "S01/P03_READY_NOT_STARTED"
        expected = "S01P01-OUTCOMES-TOP-LEVEL"
    else:
        _outcome(value, "OUT-S01-P01-05")["measurement"]["return_guaranteed"] = True
        expected = "S01P01-OUTCOME-NO-GUARANTEE-MEASURE"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation",
    ["pr_state", "merge_commit", "ci_failure", "missing_check", "positive_cost", "evidence_hash", "missing_stage_evidence"],
)
def test_stage0_delivery_receipt_mutations_block_s01(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project / RECEIPT_PATH
    value = strict_json_load(path)
    if mutation == "pr_state":
        value["pull_request"]["state"] = "OPEN"
    elif mutation == "merge_commit":
        value["pull_request"]["merge_commit"] = "0" * 40
    elif mutation == "ci_failure":
        value["main_checks"][0]["conclusion"] = "failure"
    elif mutation == "missing_check":
        value["main_checks"].pop()
    elif mutation == "positive_cost":
        value["incremental_cash_spent_aud"] = "0.01"
    elif mutation == "evidence_hash":
        value["stage_review_evidence"]["sha256"] = "f" * 64
    else:
        (project / "machine/evidence/EVD-S00-STAGE-REVIEW.json").unlink()
    if mutation != "missing_stage_evidence":
        _write_json(path, value)
    _failed(evaluate_contract(project), "S01P01-STAGE0-DELIVERY-PREREQUISITE")


@pytest.mark.parametrize("mutation", ["floating_action", "stage0_writer", "missing_regression", "secret_reference"])
def test_continuous_workflow_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project.parent / CONTINUOUS_WORKFLOW_PATH
    text = path.read_text(encoding="utf-8")
    if mutation == "floating_action":
        text = text.replace("actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", "actions/checkout@v7")
        expected = "S01P01-CONTINUOUS-CI-SUPPLY-CHAIN"
    elif mutation == "stage0_writer":
        text = text.replace("--verify-existing STAGE-REVIEW-S00", "--contract STAGE-REVIEW-S00")
        expected = "S01P01-CONTINUOUS-CI-HISTORICAL-REPLAY"
    elif mutation == "missing_regression":
        text = text.replace("python -m pytest -q", "python -m pytest -q tests/S01/P01_test.py")
        expected = "S01P01-CONTINUOUS-CI-HISTORICAL-REPLAY"
    else:
        text += "\n# " + "$" + "{{ secrets.ABD_TOKEN }}\n"
        expected = "S01P01-CONTINUOUS-CI-HISTORICAL-REPLAY"
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize("mutation", ["cost", "real_order", "gmail", "canonical_order"])
def test_budget_order_and_external_effect_boundaries_remain_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "cost":
        path = project / "machine/facts/costs.json"
        value = strict_json_load(path)
        value["incremental_cash_budget"]["high"] = "0.0001"
    elif mutation == "real_order":
        path = project / "machine/facts/authorization_matrix.json"
        value = strict_json_load(path)
        _action(value, "REAL_ORDER_SUBMISSION")["authorization"] = "PREAUTHORIZED"
    elif mutation == "gmail":
        path = project / "machine/facts/degraded_mode_contract.json"
        value = strict_json_load(path)
        value["s00_p04_execution_boundary"]["gmail_api_called"] = True
    else:
        path = project / "machine/facts/canonical_facts.json"
        value = strict_json_load(path)
        value["scope"]["order_submission_module_present"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), "S01P01-ZERO-BUDGET-NO-ORDER-NO-GMAIL-EFFECT")


@pytest.mark.parametrize("mutation", ["p02_evidence", "p02_output"])
def test_p02_requires_immutable_p01_pass_receipt(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/evidence/EVD-S01-P01.json").unlink()
    if mutation == "p02_evidence":
        (project / "machine/evidence/EVD-S01-P02.json").write_text("{}\n", encoding="utf-8")
    else:
        (project / "customer_faq.md").write_text("premature\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S01P01-SUCCESSOR-PROGRESSION-GATED")


@pytest.mark.parametrize("target", ["outcomes", "receipt"])
def test_duplicate_json_keys_fail_closed(tmp_path: Path, target: str) -> None:
    project = _clone_project(tmp_path)
    path = project / (OUTCOMES_PATH if target == "outcomes" else RECEIPT_PATH)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("{", '{\n  "schema_version": "duplicate",', 1), encoding="utf-8")
    expected = "S01P01-OUTCOMES-STRICT-JSON" if target == "outcomes" else "S01P01-STAGE0-DELIVERY-PREREQUISITE"
    _failed(evaluate_contract(project), expected)


def test_evidence_is_deterministic_without_runtime_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["external_effect_boundary"]["github_upload_performed"] is False
    assert first["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_rollback_drill_restores_all_signed_phase_inputs() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 5
    assert all(row["signed_sha256"] == row["restored_sha256"] for row in result["artifacts"].values())


def test_evaluation_does_not_mutate_inputs() -> None:
    paths = [
        ROOT / PRESS_RELEASE_PATH,
        ROOT / OUTCOMES_PATH,
        ROOT / FIXTURE_PATH,
        ROOT / RECEIPT_PATH,
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
    result = _evaluate_contract(
        project,
        require_external_reports=True,
        _verify_git_history=False,
    )
    assert result["status"] == "FAIL"
    assert "S01P01-TEST-TARGETED-PASS" in result["summary"]["failed_check_ids"]
    assert "S01P01-TEST-FULL-REGRESSION-PASS" in result["summary"]["failed_check_ids"]
