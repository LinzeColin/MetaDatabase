from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.advice_card import (
    DISPLAY_ORDER,
    build_advice_card,
    extract_primary_answers,
    render_visible_text,
    validate_card,
)
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.reason_next_action import (
    render_failure_guidance,
    resolve_failure_states,
    validate_resolution,
)
from abd_acceptance.stage3_review import (
    CONTRACT_ID,
    CONTRACT_PATH,
    EVIDENCE_PATH,
    FINDINGS_PATH,
    FIXED_CLOCK,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PINNED_REVIEW_ARTIFACT_HASHES,
    ROLLBACK_EVIDENCE_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    WORKFLOW_PATH,
    WORKFLOW_SHA256,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_stage_review_evidence,
)
from abd_acceptance.terminology_governance import scan_ui_text
from abd_acceptance.usability_accessibility import FAILURE_GUIDANCE_ORDER, evaluate_timing_gate


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = strict_json_load(ROOT / CONTRACT_PATH)
FINDINGS = strict_json_load(ROOT / FINDINGS_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
GLOSSARY = strict_json_load(ROOT / "glossary_zh.json")
POLICY = strict_json_load(ROOT / "forbidden_ui_terms.json")
SCHEMA = strict_json_load(ROOT / "advice_card_schema.json")
CARD_FIXTURES = strict_json_load(ROOT / "advice_card_fixtures.json")
REASONS = strict_json_load(ROOT / "reason_codes_zh.json")
MATRIX = strict_json_load(ROOT / "next_action_matrix.json")
PLAN = strict_json_load(ROOT / "ux_test_plan.json")
REPORT = strict_json_load(ROOT / "accessibility_report.json")


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
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


def _build_card(vector_name: str):
    return build_advice_card(
        CARD_FIXTURES[vector_name],
        schema=SCHEMA,
        glossary=GLOSSARY,
        policy=POLICY,
        parameters_sha256=sha256_file(ROOT / "machine/facts/parameters.json"),
        model_sha256=sha256_file(ROOT / "machine/facts/model_system_card.json"),
    )


def test_whole_stage_review_candidate_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_WHOLE_STAGE_REVIEW_PASS"
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["human_validation_status"] == "NOT_EXECUTED"
    assert result["production_status"] == "NOT_IMPLEMENTED_NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_candidate_preflight_is_fail_closed_and_upload_ready_only_on_pass() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_REVIEW_CANDIDATE_PREFLIGHT_PASS"
    assert result["next"] == "S03/STAGE_REVIEW_CANDIDATE"


@pytest.mark.parametrize("relative", sorted(PINNED_REVIEW_ARTIFACT_HASHES))
def test_review_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_REVIEW_ARTIFACT_HASHES[relative]


def test_review_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_workflow_is_exactly_pinned() -> None:
    assert sha256_file(ROOT.parent / WORKFLOW_PATH) == WORKFLOW_SHA256


@pytest.mark.parametrize("record", CONTRACT["phase_records"], ids=lambda row: row["phase_id"])
def test_each_phase_record_binds_requirement_acceptance_tasks_and_receipts(record: dict) -> None:
    phase = record["phase_id"]
    assert record["requirement_id"] == f"REQ-S03-{phase}"
    assert record["acceptance_contract_id"] == f"AC-S03-{phase}"
    assert record["task_ids"] == [f"T-S03-{phase}-01", f"T-S03-{phase}-02", f"T-S03-{phase}-03"]
    assert record["evidence_sha256"] == FIXTURE["expected_phase_evidence_sha256"][phase]
    assert record["rollback_sha256"] == FIXTURE["expected_phase_rollback_sha256"][phase]
    assert sha256_file(ROOT / record["evidence_path"]) == record["evidence_sha256"]
    assert sha256_file(ROOT / record["rollback_path"]) == record["rollback_sha256"]
    assert len(record["implementation_commit"]) == 40
    assert len(record["implementation_code_sha256"]) == 64


@pytest.mark.parametrize("entry", GLOSSARY["entries"], ids=lambda row: row["term_id"])
def test_every_glossary_entry_has_chinese_name_definition_and_machine_mapping(entry: dict) -> None:
    assert entry["term_id"].startswith("TERM-")
    assert entry["machine_token"]
    assert any("\u4e00" <= char <= "\u9fff" for char in entry["zh_name"])
    assert any("\u4e00" <= char <= "\u9fff" for char in entry["definition_zh"])
    assert any("\u4e00" <= char <= "\u9fff" for char in entry["preferred_ui_label"])
    assert entry["machine_mappings"]


@pytest.mark.parametrize("vector_name", ["base_recommendation_input", "base_no_recommendation_input"])
def test_advice_and_no_advice_cards_are_deterministic_chinese_and_valid(vector_name: str) -> None:
    first = _build_card(vector_name)
    second = _build_card(vector_name)
    assert first == second
    assert first["display_order"] == DISPLAY_ORDER
    assert not validate_card(first, schema=SCHEMA, glossary=GLOSSARY, policy=POLICY)
    assert not scan_ui_text(render_visible_text(first, SCHEMA), "ADVICE_CARD", GLOSSARY, POLICY)
    answers = extract_primary_answers(first)
    assert list(answers) == ["what_zh", "where_zh", "amount_zh", "minimum_odds_zh"]
    assert all(any("\u4e00" <= char <= "\u9fff" or char.isdigit() for char in value) for value in answers.values())


@pytest.mark.parametrize("reason", REASONS["reason_codes"], ids=lambda row: row["code"])
def test_every_declared_failure_renders_one_deterministic_chinese_next_action(reason: dict) -> None:
    first = resolve_failure_states([reason["code"]], reason_catalog=REASONS, next_action_matrix=MATRIX)
    second = resolve_failure_states([reason["code"]], reason_catalog=REASONS, next_action_matrix=MATRIX)
    assert first == second
    assert first["selected_reason"]["code"] == reason["code"]
    assert first["considered_count"] == 1
    assert isinstance(first["next_action"], dict)
    assert not validate_resolution(first, reason_catalog=REASONS, next_action_matrix=MATRIX, glossary=GLOSSARY, policy=POLICY)
    visible = render_failure_guidance(first)
    assert not scan_ui_text(visible, "USER_ERROR_NEXT_ACTION", GLOSSARY, POLICY)
    assert first["safety"]["external_effect_performed"] is False
    assert first["safety"]["order_submitted"] is False
    assert first["safety"]["order_retried"] is False
    assert first["safety"]["incremental_cash_spent_aud"] == "0.00"


@pytest.mark.parametrize("action", MATRIX["actions"], ids=lambda row: row["action_id"])
def test_every_next_action_is_local_reversible_zero_cash_and_never_an_order(action: dict) -> None:
    assert any("\u4e00" <= char <= "\u9fff" for char in action["title_zh"])
    assert any("\u4e00" <= char <= "\u9fff" for char in action["system_behavior_zh"])
    assert action["external_effect_performed"] is False
    assert action["may_submit_order"] is False
    assert action["may_retry_order"] is False
    assert action["may_spend_cash"] is False
    assert action["may_relax_evidence_numeric_risk_or_safety_gate"] is False
    assert action["irreversible"] is False
    assert action["incremental_cash_cost_aud"] == "0.00"


@pytest.mark.parametrize("profile", PLAN["profiles"], ids=lambda row: row["id"])
def test_every_accessibility_profile_remains_structural_and_not_executed(profile: dict) -> None:
    assert profile["evidence_layer"] == "STRUCTURAL_DESIGN_CONTRACT_ONLY"
    assert profile["runtime_status"] == "NOT_EXECUTED"
    assert profile["frozen_environment"]


@pytest.mark.parametrize("budget", PLAN["scenario_budgets"], ids=lambda row: row["id"])
def test_every_timing_value_is_a_positive_integer_budget_not_observation(budget: dict) -> None:
    assert type(budget["budget_seconds"]) is int
    assert budget["budget_seconds"] > 0
    assert PLAN["human_participant_count"] == 0
    assert PLAN["observed_session_count"] == 0
    assert PLAN["measurement_layer"] == "FROZEN_CONSERVATIVE_TASK_BUDGETS_NOT_OBSERVED_HUMAN_TIMES"


def test_failure_guidance_has_explicit_keyboard_and_screen_reader_order() -> None:
    integration = PLAN["failure_guidance_integration"]
    assessment = REPORT["failure_guidance_assessment"]
    task = next(row for row in PLAN["core_tasks"] if row["id"] == "CORE-04")
    assert FAILURE_GUIDANCE_ORDER == FIXTURE["expected_failure_guidance_order"]
    assert task["required_failure_guidance_regions"] == FAILURE_GUIDANCE_ORDER
    assert integration["region_order"] == FAILURE_GUIDANCE_ORDER
    assert integration["keyboard_focus_order"] == FAILURE_GUIDANCE_ORDER
    assert integration["screen_reader_order"] == FAILURE_GUIDANCE_ORDER
    assert integration["declared_reason_count"] == 49
    assert assessment["deterministically_replayed_reason_count"] == 49
    assert assessment["unique_next_action_gate_status"] == "PASS"
    assert assessment["chinese_ui_gate_status"] == "PASS"
    assert assessment["runtime_status"] == "NOT_EXECUTED"


def test_ten_second_gate_is_not_upgraded_to_human_timing_or_wcag_claim() -> None:
    ten_second = SCHEMA["x-abd-contract"]["ten_second_information_gate"]
    claim = CONTRACT["claim_boundary"]
    assert ten_second["human_timing_validation"] == "DEFERRED_TO_S03_P04"
    assert claim == FIXTURE["expected_claim_boundary"]
    assert claim["ten_second_information_gate_kind"] == "STRUCTURAL_INFORMATION_PLACEMENT_ONLY"
    assert all(value is False for key, value in claim.items() if key != "ten_second_information_gate_kind")
    assert REPORT["timing_assessment"]["human_timing_status"] == "NOT_EXECUTED"
    assert REPORT["claim_boundary"]["formal_wcag_conformance_claimed"] is False


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_boundary_deltas"])
@pytest.mark.parametrize("adverse", [False, True])
def test_numeric_perturbation_and_adverse_odds_cannot_change_usability_budget_gate(delta: str, adverse: bool) -> None:
    durations = [row["budget_seconds"] for row in PLAN["scenario_budgets"]]
    result = evaluate_timing_gate(durations, numeric_boundary_delta=delta, adverse_odds_tick=adverse)
    assert result["status"] == "PASS"
    assert result["median_seconds"] == 540
    assert result["p95_seconds"] == 840


@pytest.mark.parametrize("finding", FINDINGS["findings"], ids=lambda row: row["id"])
def test_each_review_finding_is_resolved_by_an_executable_gate(finding: dict) -> None:
    assert finding["status"] == "RESOLVED_IN_REVIEW_CANDIDATE"
    assert finding["severity"] in {"HIGH", "MEDIUM"}
    assert finding["observation"]
    assert finding["risk"]
    assert finding["remediation"]
    assert finding["verification_gate"].startswith("S03REVIEW-")


def test_review_finding_summary_has_zero_open_items() -> None:
    assert FINDINGS["summary"] == {
        "total": 5,
        "resolved_in_review_candidate": 5,
        "open": 0,
        "remote_ci_pending_is_upload_evidence_not_an_open_code_finding": True,
    }


def test_a300_a0_and_no_return_guarantee_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")["product"]
    costs = strict_json_load(ROOT / "machine/facts/costs.json")
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    assert canonical["initial_bankroll_aud"] == "300.00"
    assert canonical["incremental_cash_budget_aud"] == "0.00"
    assert canonical["monthly_target_return"] == "0.30"
    assert parameters["target_30pct"]["guaranteed"] is False
    assert parameters["target_30pct"]["shortfall_behavior"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert set(costs["incremental_cash_budget"].values()) == {"0.00"}


def test_s04_is_planned_and_not_started() -> None:
    assert not (ROOT / "tests/S04/P01_test.py").exists()
    assert not (ROOT / "machine/tests/fixtures/S04_P01.json").exists()
    assert not (ROOT / "machine/evidence/EVD-S04-P01.json").exists()
    rows = [json.loads(line) for line in (ROOT / "machine/evidence/evidence_index.jsonl").read_text(encoding="utf-8-sig").splitlines() if line]
    s04 = [row for row in rows if row["id"] == "INDEX-AC-S04-P01"]
    assert len(s04) == 1
    assert s04[0]["status"] == "PLANNED"
    assert "actual_artifact" not in s04[0]


def test_rollback_restores_all_twelve_signed_review_inputs_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"] == 12
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert all(row["signed_sha256"] == row["restored_sha256"] for row in result["artifacts"].values())
    assert all(row["corrupted_sha256"] != row["signed_sha256"] for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, rollback_first = build_evidence(ROOT, require_external_reports=False)
    second, rollback_second = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert rollback_first == rollback_second
    assert first["status"] == "PASS"
    assert first["claim_boundary"] == FIXTURE["expected_claim_boundary"]
    assert first["release_status"] == FIXTURE["expected_release_status"]
    assert first["next"] == FIXTURE["expected_next"]


def test_existing_review_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_stage_review_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S03_STAGE_REVIEW_EVIDENCE_VERIFIED"
        assert result["next"] == "S03/GITHUB_STAGE_UPLOAD_READY"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S03_STAGE_REVIEW_EVIDENCE_INVALID_FAIL_CLOSED"


@pytest.mark.parametrize(
    "target,path,replacement,check_id",
    [
        (CONTRACT_PATH, ["claim_boundary", "human_timing_observed"], True, "S03REVIEW-HUMAN-TIMING-CLAIM-BOUNDARY"),
        (CONTRACT_PATH, ["external_effect_boundary", "order_submitted_or_retried"], True, "S03REVIEW-EXTERNAL-EFFECT-BOUNDARY"),
        (FINDINGS_PATH, ["summary", "open"], 1, "S03REVIEW-FINDINGS-SUMMARY"),
        (Path("ux_test_plan.json"), ["failure_guidance_integration", "screen_reader_order"], ["safety"], "S03REVIEW-BASELINE-UX_TEST_PLAN-JSON"),
        (Path("accessibility_report.json"), ["claim_boundary", "formal_wcag_conformance_claimed"], True, "S03REVIEW-BASELINE-ACCESSIBILITY_REPORT-JSON"),
    ],
)
def test_semantic_mutations_fail_closed(
    tmp_path: Path,
    target: Path,
    path: list,
    replacement,
    check_id: str,
) -> None:
    root = _clone_project(tmp_path)
    value = strict_json_load(root / target)
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement
    _write_json(root / target, value)
    _failed(evaluate_contract(root), check_id)


def test_oracle_rejects_its_own_source_tampering(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / "abd_acceptance/stage3_review.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S03REVIEW-ORACLE-SELF-INTEGRITY")


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH]:
        if (root / relative).exists():
            (root / relative).unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S03REVIEW-TARGETED-PYTEST")
    assert "S03REVIEW-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


def test_review_language_never_claims_production_human_wcag_or_return_readiness() -> None:
    rendered = json.dumps({"contract": CONTRACT, "findings": FINDINGS, "plan": PLAN, "report": REPORT}, ensure_ascii=False, sort_keys=True)
    assert "NOT_EXECUTED" in rendered
    assert "NOT_READY_STAGE_4_TO_19_AND_PRODUCTION_VALIDATION_REQUIRED" in rendered
    assert "不保证" in rendered
    assert CONTRACT["claim_boundary"]["production_ui_deployed"] is False
    assert CONTRACT["claim_boundary"]["financial_target_verified_or_guaranteed"] is False
