from __future__ import annotations

import itertools
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.customer_faq import (
    CONTINUOUS_WORKFLOW_PATH,
    FAQ_PATH,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    P01_EVIDENCE_PATH,
    P01_EVIDENCE_SHA256,
    P01_ROLLBACK_PATH,
    REGISTER_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_mail_default,
    resolve_recommendation_default,
    resolve_zero_budget_default,
)


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


def _assumption(value, topic: str):
    return next(row for row in value["assumptions"] if row["topic"] == topic)


def _action(value, action_id: str):
    return next(row for row in value["actions"] if row["id"] == action_id)


def test_baseline_customer_faq_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= 85
    assert result["decision"] == "FAQ_AND_ASSUMPTIONS_FROZEN"
    assert result["release_status"] == "NOT_READY"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S01/P03_READY_NOT_STARTED"


def test_p01_immutable_receipt_and_git_ancestry_are_verified() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["S01P02-P01-IMMUTABLE-RECEIPT"]["passed"] is True
    assert checks["S01P02-P01-SIGNED-ARTIFACTS"]["passed"] is True
    assert checks["S01P02-P01-EVIDENCE-INDEX"]["passed"] is True
    assert checks["S01P02-P01-GIT-ANCESTRY"]["passed"] is True
    assert sha256_file(ROOT / P01_EVIDENCE_PATH) == P01_EVIDENCE_SHA256


@pytest.mark.parametrize("case", FIXTURE["zero_budget_vectors"], ids=lambda case: str(case["value"]))
def test_zero_budget_default_vectors(case) -> None:
    assert resolve_zero_budget_default(case["value"]) == case["expected"]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", "CONTINUE_ZERO_INCREMENTAL_CASH_PATH"),
        ("0.000000", "CONTINUE_ZERO_INCREMENTAL_CASH_PATH"),
        ("0.00009999", "BLOCK_INCREMENTAL_CASH_BUDGET_EXCEEDED"),
        ("0.00010000", "BLOCK_INCREMENTAL_CASH_BUDGET_EXCEEDED"),
        ("1", "BLOCK_INCREMENTAL_CASH_BUDGET_EXCEEDED"),
        ("Infinity", "FAIL_INVALID_COST_DATA"),
        ("not-a-number", "FAIL_INVALID_COST_DATA"),
    ],
)
def test_zero_budget_decimal_boundaries(value: str, expected: str) -> None:
    assert resolve_zero_budget_default(value) == expected


MAIL_GATES = tuple(FIXTURE["mail_gate_order"])


@pytest.mark.parametrize("values", list(itertools.product([False, True], repeat=len(MAIL_GATES))))
def test_mail_archive_truth_table_fails_closed(values) -> None:
    gates = dict(zip(MAIL_GATES, values))
    result = resolve_mail_default(**gates)
    if all(values):
        assert result == "TRASH_AFTER_VERIFIED_ARCHIVE"
    elif not gates["consent_active"]:
        assert result == "DISABLE_GMAIL_KEEP_MESSAGE"
    else:
        assert result == "KEEP_OR_QUARANTINE_DO_NOT_TRASH"


@pytest.mark.parametrize(
    "gates",
    [
        {},
        {"consent_active": True},
        {**{name: True for name in MAIL_GATES}, "unexpected": True},
        {**{name: True for name in MAIL_GATES}, "raw_eml_saved": 1},
        {**{name: True for name in MAIL_GATES}, "malware_scan_passed": None},
    ],
)
def test_mail_archive_malformed_gate_sets_disable_gmail(gates) -> None:
    assert resolve_mail_default(**gates) == "DISABLE_GMAIL_KEEP_MESSAGE"


@pytest.mark.parametrize("values", list(itertools.product([False, True], repeat=4)))
def test_recommendation_default_truth_table(values) -> None:
    result = resolve_recommendation_default(
        evidence_complete=values[0],
        fresh=values[1],
        stable=values[2],
        risk_passed=values[3],
    )
    assert result == ("RECOMMENDATION" if all(values) else "NO_RECOMMENDATION")


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("roadmap", "S01P02-ROADMAP-EXACT"),
        ("requirement", "S01P02-REQUIREMENT-EXACT"),
        ("acceptance", "S01P02-ACCEPTANCE-CONTRACT-EXACT"),
        ("task_dependency", "S01P02-TASK-CHAIN-EXACT"),
        ("task_output", "S01P02-TASK-CHAIN-EXACT"),
        ("task_owner", "S01P02-TASK-CHAIN-EXACT"),
        ("traceability", "S01P02-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_semantics_cannot_drift(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "roadmap":
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = next(row for row in next(row for row in value["stages"] if row["id"] == "S01")["phases"] if row["id"] == "P02")
        phase["objective"] = "drift"
    elif mutation == "requirement":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "REQ-S01-P02")["target"] = "drift"
    elif mutation == "acceptance":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        next(row for row in value if row["id"] == "AC-S01-P02")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = next(row for row in value["tasks"] if row["id"] == "T-S01-P02-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"] = ["wrong"]
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        next(row for row in value if row["requirement_id"] == "REQ-S01-P02")["evidence_id"] = "wrong"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("second_h1", "S01P02-FAQ-STRUCTURE"),
        ("missing_question", "S01P02-FAQ-STRUCTURE"),
        ("duplicate_question", "S01P02-FAQ-STRUCTURE"),
        ("missing_answer", "S01P02-FAQ-STRUCTURE"),
        ("duplicate_default", "S01P02-FAQ-STRUCTURE"),
        ("missing_preamble", "S01P02-FAQ-STRUCTURE"),
        ("code_fence", "S01P02-FAQ-STRUCTURE"),
        ("url", "S01P02-FAQ-STRUCTURE"),
        ("too_short", "S01P02-FAQ-CUSTOMER-LANGUAGE"),
        ("false_deployment", "S01P02-FAQ-NO-FALSE-CURRENT-CLAIMS"),
        ("false_return", "S01P02-FAQ-NO-FALSE-CURRENT-CLAIMS"),
        ("missing_concept", "S01P02-FAQ-REQUIRED-CONCEPTS"),
        ("missing_evidence_path", "S01P02-FAQ-DEFAULT-AND-EVIDENCE-PER-QUESTION"),
        ("missing_boundary", "S01P02-FAQ-STRUCTURE"),
    ],
)
def test_faq_mutations_fail_customer_contract(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / FAQ_PATH
    text = path.read_text(encoding="utf-8")
    if mutation == "second_h1":
        text += "\n# 第二份FAQ\n"
    elif mutation == "missing_question":
        start = text.index("## FAQ-S01-P02-04")
        end = text.index("## FAQ-S01-P02-05")
        text = text[:start] + text[end:]
    elif mutation == "duplicate_question":
        text = text.replace("FAQ-S01-P02-07｜", "FAQ-S01-P02-01｜")
    elif mutation == "missing_answer":
        text = text.replace("**答案：**", "", 1)
    elif mutation == "duplicate_default":
        text = text.replace("**默认：**", "**默认：**\n\n**默认：**", 1)
    elif mutation == "missing_preamble":
        text = text.replace(FIXTURE["required_faq_preamble"], "普通说明")
    elif mutation == "code_fence":
        text += "\n```text\nunsafe\n```\n"
    elif mutation == "url":
        text += "\nhttps://example.invalid\n"
    elif mutation == "too_short":
        text = "# ABD 客户常见问题（目标合同稿）\n"
    elif mutation == "false_deployment":
        text = text.replace("本 phase 没有真实订单", "系统已经部署；本 phase 没有真实订单", 1)
    elif mutation == "false_return":
        text = text.replace("当前证据状态：** 未验证", "当前证据状态：** 已实现30%收益；未验证", 1)
    elif mutation == "missing_concept":
        text = text.replace("Gmail尚未连接", "邮件状态未知")
    elif mutation == "missing_evidence_path":
        text = text.replace("`machine/facts/email_ingestion.json#/trash_gate`", "`missing.json`", 1)
    else:
        text = text[: text.index("## 当前交付边界")]
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("status", "S01P02-REGISTER-TOP-LEVEL"),
        ("next", "S01P02-REGISTER-TOP-LEVEL"),
        ("source_binding", "S01P02-REGISTER-SOURCE-BINDINGS"),
        ("required_questions", "S01P02-REGISTER-REQUIRED-QUESTIONS"),
        ("duplicate_id", "S01P02-REGISTER-ONE-ROW-PER-QUESTION"),
        ("question_order", "S01P02-REGISTER-ONE-ROW-PER-QUESTION"),
        ("topic", "S01P02-REGISTER-ONE-ROW-PER-QUESTION"),
        ("safe_default", "S01P02-REGISTER-ONE-ROW-PER-QUESTION"),
        ("external_observed", "S01P02-REGISTER-ONE-ROW-PER-QUESTION"),
        ("empty_proof", "S01P02-REGISTER-ONE-ROW-PER-QUESTION"),
        ("missing_evidence", "S01P02-REGISTER-EVIDENCE-POINTERS-RESOLVE"),
        ("bogus_pointer", "S01P02-REGISTER-EVIDENCE-POINTERS-RESOLVE"),
        ("missing_support", "S01P02-REGISTER-EVIDENCE-POINTERS-RESOLVE"),
        ("target_status", "S01P02-REGISTER-TARGET-DEFAULT"),
        ("target_falsification", "S01P02-REGISTER-TARGET-DEFAULT"),
        ("guarantee", "S01P02-REGISTER-NO-GUARANTEE-DEFAULT"),
        ("budget", "S01P02-REGISTER-ZERO-BUDGET-DEFAULT"),
        ("coverage", "S01P02-REGISTER-COVERAGE-DEFAULT"),
        ("mail", "S01P02-REGISTER-MAIL-DEFAULT"),
        ("failure", "S01P02-REGISTER-FAILURE-DEFAULT"),
        ("privacy", "S01P02-REGISTER-PRIVACY-DEFAULT"),
        ("claim_boundary", "S01P02-REGISTER-CLAIM-BOUNDARIES"),
    ],
)
def test_assumption_register_mutations_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    path = project / REGISTER_PATH
    value = strict_json_load(path)
    if mutation == "status":
        value["status"] = "PRODUCTION_PROVEN"
    elif mutation == "next":
        value["next_on_acceptance_pass"] = "S01/P04_READY_NOT_STARTED"
    elif mutation == "source_binding":
        value["source_bindings"]["machine/facts/costs.json"] = "0" * 64
    elif mutation == "required_questions":
        value["required_question_ids"].pop()
    elif mutation == "duplicate_id":
        value["assumptions"][-1]["id"] = value["assumptions"][0]["id"]
    elif mutation == "question_order":
        value["assumptions"][0]["question_id"], value["assumptions"][1]["question_id"] = (
            value["assumptions"][1]["question_id"],
            value["assumptions"][0]["question_id"],
        )
    elif mutation == "topic":
        value["assumptions"][0]["topic"] = "UNKNOWN"
    elif mutation == "safe_default":
        value["assumptions"][0]["safe_default"] = "RELAX_GATES"
    elif mutation == "external_observed":
        value["assumptions"][0]["external_state_observed_in_phase"] = True
    elif mutation == "empty_proof":
        value["assumptions"][0]["proof_required"] = ""
    elif mutation == "missing_evidence":
        value["assumptions"][0]["evidence"].pop()
    elif mutation == "bogus_pointer":
        value["assumptions"][0]["evidence"][0]["json_pointers"] = ["/missing"]
    elif mutation == "missing_support":
        value["assumptions"][0]["evidence"][0]["supports"] = ""
    elif mutation == "target_status":
        _assumption(value, "MONTHLY_TARGET")["current_status"] = "VERIFIED"
    elif mutation == "target_falsification":
        _assumption(value, "MONTHLY_TARGET")["disconfirming_evidence"] = "none"
    elif mutation == "guarantee":
        _assumption(value, "NO_RETURN_GUARANTEE")["safe_default"] = "CLAIM_RETURN"
    elif mutation == "budget":
        _assumption(value, "ZERO_INCREMENTAL_CASH")["safe_default"] = "AUTO_PURCHASE"
    elif mutation == "coverage":
        _assumption(value, "ALL_OBSERVABLE_MARKETS")["current_status"] = "ALL_COVERED"
    elif mutation == "mail":
        _assumption(value, "MAIL_ARCHIVE")["current_status"] = "GMAIL_ACTIVE"
    elif mutation == "failure":
        _assumption(value, "FAILURE_AND_DEGRADED_OPERATION")["safe_default"] = "KEEP_RECOMMENDING"
    elif mutation == "privacy":
        _assumption(value, "PRIVACY_AND_SECRETS")["current_status"] = "TOKENS_STORED"
    else:
        value["claim_boundaries"]["production_deployment_claimed"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("target_guaranteed", "S01P02-FACT-TARGET-NO-GUARANTEE"),
        ("shortfall_relax", "S01P02-FACT-TARGET-NO-GUARANTEE"),
        ("cost_max", "S01P02-FACT-ZERO-BUDGET-SEMANTICS"),
        ("auto_purchase", "S01P02-FACT-ZERO-BUDGET-SEMANTICS"),
        ("silent_gap", "S01P02-FACT-COVERAGE-AND-SAFE-DEFAULT"),
        ("unstable_recommend", "S01P02-FACT-COVERAGE-AND-SAFE-DEFAULT"),
        ("gmail_active", "S01P02-FACT-GMAIL-NOT-CONNECTED-SAFE-ARCHIVE"),
        ("permanent_delete", "S01P02-FACT-GMAIL-NOT-CONNECTED-SAFE-ARCHIVE"),
        ("rollback_removed", "S01P02-FACT-FAILURE-ROLLBACK"),
        ("privacy_field_removed", "S01P02-FACT-PRIVACY-AND-SECRETS"),
        ("order_authorized", "S01P02-NO-EXTERNAL-EFFECTS-OR-ORDER"),
        ("gmail_called", "S01P02-NO-EXTERNAL-EFFECTS-OR-ORDER"),
    ],
)
def test_frozen_fact_mutations_fail_semantic_oracle(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation in {"target_guaranteed", "shortfall_relax", "unstable_recommend"}:
        path = project / "machine/facts/parameters.json"
        value = strict_json_load(path)
        if mutation == "target_guaranteed":
            value["target_30pct"]["guaranteed"] = True
        elif mutation == "shortfall_relax":
            value["risk"]["target_shortfall_may_relax_gate"] = True
        else:
            value["numeric_determinism"]["unstable_action"] = "RECOMMENDATION"
    elif mutation in {"cost_max", "auto_purchase", "silent_gap"}:
        path = project / "machine/facts/costs.json"
        value = strict_json_load(path)
        if mutation == "cost_max":
            value["incremental_cash_gate"]["maximum_aud"] = "0.0001"
        elif mutation == "auto_purchase":
            value["incremental_cash_gate"]["automatic_purchase_allowed"] = True
        else:
            value["future_source_admission_policy"]["coverage_gap_behavior"] = "DROP_SILENTLY"
    elif mutation == "gmail_active":
        path = project / "machine/facts/decision_prerequisites.json"
        value = strict_json_load(path)
        value["current_phase_observation"]["gmail_module_enabled"] = True
    elif mutation == "permanent_delete":
        path = project / "machine/facts/email_ingestion.json"
        value = strict_json_load(path)
        value["trash_gate"]["permanent_delete"] = True
    elif mutation == "rollback_removed":
        path = project / "machine/facts/release_policy.json"
        value = strict_json_load(path)
        value["auto_rollback_on"].pop()
    elif mutation == "privacy_field_removed":
        path = project / "machine/facts/degraded_mode_contract.json"
        value = strict_json_load(path)
        value["consent_receipt_contract"]["forbidden_fields"].pop()
    elif mutation == "order_authorized":
        path = project / "machine/facts/authorization_matrix.json"
        value = strict_json_load(path)
        _action(value, "REAL_ORDER_SUBMISSION")["authorization"] = "PREAUTHORIZED"
    else:
        path = project / "machine/facts/degraded_mode_contract.json"
        value = strict_json_load(path)
        value["s00_p04_execution_boundary"]["gmail_api_called"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("evidence_status", "S01P02-P01-IMMUTABLE-RECEIPT"),
        ("decision_hash", "S01P02-P01-IMMUTABLE-RECEIPT"),
        ("external_effect", "S01P02-P01-IMMUTABLE-RECEIPT"),
        ("rollback_status", "S01P02-P01-IMMUTABLE-RECEIPT"),
        ("p01_artifact", "S01P02-P01-SIGNED-ARTIFACTS"),
        ("index_status", "S01P02-P01-EVIDENCE-INDEX"),
        ("stage0_receipt", "S01P02-STAGE0-DELIVERY-CHAIN"),
    ],
)
def test_p01_prerequisite_mutations_block_p02(tmp_path: Path, mutation: str, expected: str) -> None:
    project = _clone_project(tmp_path)
    if mutation in {"evidence_status", "decision_hash", "external_effect"}:
        path = project / P01_EVIDENCE_PATH
        value = strict_json_load(path)
        if mutation == "evidence_status":
            value["status"] = "FAIL"
        elif mutation == "decision_hash":
            value["decision_sha256"] = "0" * 64
        else:
            value["external_effect_boundary"]["github_upload_performed"] = True
        _write_json(path, value)
    elif mutation == "rollback_status":
        path = project / P01_ROLLBACK_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "p01_artifact":
        (project / "customer_press_release.md").write_text("drift\n", encoding="utf-8")
    elif mutation == "index_status":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-AC-S01-P01")["status"] = "PLANNED"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    else:
        path = project / "machine/evidence/S00/STAGE_REVIEW/github_delivery_receipt.json"
        value = strict_json_load(path)
        value["pull_request"]["state"] = "OPEN"
        _write_json(path, value)
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize("mutation", ["p03_evidence", "p03_output", "p04_output", "invalid_successor_status"])
def test_successor_requires_immutable_p02_pass_receipt(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "invalid_successor_status":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        next(row for row in rows if row["id"] == "INDEX-AC-S01-P03")["status"] = "SKIPPED"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    else:
        (project / "machine/evidence/EVD-S01-P02.json").unlink()
    if mutation == "p03_evidence":
        (project / "machine/evidence/EVD-S01-P03.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "p03_output":
        (project / "requirements.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "p04_output":
        (project / "metrics.json").write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S01P02-SUCCESSOR-PROGRESSION-GATED")


@pytest.mark.parametrize("mutation", ["floating_action", "missing_regression", "secret_reference"])
def test_continuous_workflow_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project.parent / CONTINUOUS_WORKFLOW_PATH
    text = path.read_text(encoding="utf-8")
    if mutation == "floating_action":
        text = text.replace("actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", "actions/checkout@v7")
    elif mutation == "missing_regression":
        text = text.replace("python -m pytest -q", "python -m pytest -q tests/S01/P02_test.py")
    else:
        text += "\n# " + "$" + "{{ secrets.ABD_TOKEN }}\n"
    path.write_text(text, encoding="utf-8")
    _failed(evaluate_contract(project), "S01P02-CONTINUOUS-CI")


@pytest.mark.parametrize("target", ["register", "fixture", "p01_evidence"])
def test_duplicate_json_keys_fail_closed(tmp_path: Path, target: str) -> None:
    project = _clone_project(tmp_path)
    if target == "register":
        path = project / REGISTER_PATH
        expected = "S01P02-REGISTER-STRICT-JSON"
    elif target == "fixture":
        path = project / FIXTURE_PATH
        expected = "S01P02-FIXTURE-STRICT-JSON"
    else:
        path = project / P01_EVIDENCE_PATH
        expected = "S01P02-P01-EVIDENCE-STRICT-JSON"
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


def test_rollback_drill_restores_all_signed_phase_inputs() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == 6
    assert all(row["signed_sha256"] == row["restored_sha256"] for row in result["artifacts"].values())


def test_evaluation_does_not_mutate_inputs() -> None:
    paths = [
        ROOT / FAQ_PATH,
        ROOT / REGISTER_PATH,
        ROOT / FIXTURE_PATH,
        ROOT / P01_EVIDENCE_PATH,
        ROOT / P01_ROLLBACK_PATH,
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
    assert "S01P02-TEST-TARGETED-PASS" in result["summary"]["failed_check_ids"]
    assert "S01P02-TEST-FULL-REGRESSION-PASS" in result["summary"]["failed_check_ids"]
