from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.reason_next_action import verify_existing_phase_evidence as verify_p03_evidence
from abd_acceptance.usability_accessibility import (
    ALLOWED_NUMERIC_BOUNDARY_DELTAS,
    CONTRACT_ID,
    DISPLAY_ORDER,
    FAILURE_GUIDANCE_ORDER,
    EVIDENCE_PATH,
    FIXED_CLOCK,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    PACK_REPORT_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    PLAN_PATH,
    REPORT_PATH,
    ROLLBACK_EVIDENCE_PATH,
    SCAN_REPORT_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    UsabilityAccessibilityError,
    _pack_report_passes,
    _paid_dependency_scan_passes,
    _stage_review_progression,
    _structural_self_hash,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    evaluate_timing_gate,
    perform_rollback_drill,
    verify_existing_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN = strict_json_load(ROOT / PLAN_PATH)
REPORT = strict_json_load(ROOT / REPORT_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
PROFILES = {row["id"]: row for row in PLAN["profiles"]}
CONTRACTS = {row["id"]: row for row in PLAN["accessibility_contracts"]}
SAMPLES = {row["id"]: row for row in PLAN["scenario_budgets"]}
FAILURE_LOGS = {row["id"]: row for row in REPORT["structured_failure_logs"]}


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


def test_baseline_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["failed"] == 0
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["phase_status"] == FIXTURE["expected_phase_status"]
    assert result["release_status"] == FIXTURE["expected_release_status"]
    assert result["human_validation_status"] == "NOT_EXECUTED"
    assert result["production_status"] == "NOT_IMPLEMENTED_NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p03_signed_delivery_is_exact_start_prerequisite() -> None:
    result = verify_p03_evidence(ROOT, verify_git_history=True)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_P03_EVIDENCE_VERIFIED"
    assert result["next"] == "S03/P04_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_measurement_is_explicitly_a_budget_contract_not_human_observation() -> None:
    assert PLAN["measurement_layer"] == "FROZEN_CONSERVATIVE_TASK_BUDGETS_NOT_OBSERVED_HUMAN_TIMES"
    assert PLAN["human_participant_count"] == 0
    assert PLAN["observed_session_count"] == 0
    assert REPORT["timing_assessment"]["human_timing_status"] == "NOT_EXECUTED"
    assert REPORT["timing_assessment"]["human_participant_count"] == 0
    assert REPORT["timing_assessment"]["observed_session_count"] == 0


def test_claim_boundary_is_exact_and_fail_closed() -> None:
    expected = FIXTURE["expected_claim_boundary"]
    assert PLAN["claim_boundary"] == expected
    assert REPORT["claim_boundary"] == expected
    assert all(value is False for key, value in expected.items() if key != "machine_result_scope")
    assert expected["machine_result_scope"] == "确定性任务预算与结构化设计合同"


@pytest.mark.parametrize("task", PLAN["core_tasks"], ids=lambda row: row["id"])
def test_every_core_task_has_chinese_success_criteria_and_known_regions(task: dict) -> None:
    assert any("\u4e00" <= char <= "\u9fff" for char in task["title_zh"])
    assert any("\u4e00" <= char <= "\u9fff" for char in task["success_criteria_zh"])
    assert task["required_regions"]
    assert set(task["required_regions"]).issubset(DISPLAY_ORDER)


def test_core_tasks_cover_the_complete_frozen_display_order() -> None:
    regions = {region for task in PLAN["core_tasks"] for region in task["required_regions"]}
    assert regions == set(DISPLAY_ORDER)
    assert PLAN["timing_contract"]["scenario_scope"] == "ALL_CORE_TASKS_IN_ORDER"


def test_failure_guidance_is_explicitly_bound_to_keyboard_and_reader_order() -> None:
    task = next(row for row in PLAN["core_tasks"] if row["id"] == "CORE-04")
    integration = PLAN["failure_guidance_integration"]
    assessment = REPORT["failure_guidance_assessment"]
    assert task["required_failure_guidance_regions"] == FAILURE_GUIDANCE_ORDER
    assert integration["region_order"] == FAILURE_GUIDANCE_ORDER
    assert integration["keyboard_focus_order"] == FAILURE_GUIDANCE_ORDER
    assert integration["screen_reader_order"] == FAILURE_GUIDANCE_ORDER
    assert integration["declared_reason_count"] == 49
    assert integration["machine_code_visible"] is False
    assert integration["exactly_one_next_action_required"] is True
    assert integration["chinese_ui_gate_required"] is True
    assert integration["runtime_status"] == "NOT_EXECUTED"
    assert assessment["deterministically_replayed_reason_count"] == 49
    assert assessment["unique_next_action_gate_status"] == "PASS"
    assert assessment["chinese_ui_gate_status"] == "PASS"
    assert assessment["runtime_status"] == "NOT_EXECUTED"


@pytest.mark.parametrize("profile_id", FIXTURE["expected_profile_ids"])
def test_every_required_profile_is_structural_only_and_runtime_not_executed(profile_id: str) -> None:
    profile = PROFILES[profile_id]
    assert profile["evidence_layer"] == "STRUCTURAL_DESIGN_CONTRACT_ONLY"
    assert profile["runtime_status"] == "NOT_EXECUTED"
    assert profile["frozen_environment"]


def test_phone_and_desktop_viewports_are_frozen_without_runtime_claim() -> None:
    assert PROFILES["PHONE_BROWSER"]["frozen_environment"] == {
        "viewport_css_px": "360x640",
        "input_mode": "触控与屏幕键盘",
    }
    assert PROFILES["DESKTOP_BROWSER"]["frozen_environment"] == {
        "viewport_css_px": "1440x900",
        "input_mode": "键盘与指针",
    }


def test_low_bandwidth_contract_is_text_first_and_zero_image_dependency() -> None:
    environment = PROFILES["LOW_BANDWIDTH"]["frozen_environment"]
    assert environment["maximum_initial_payload_bytes"] == 32768
    assert environment["image_dependency"] == "NONE"


def test_color_contract_never_uses_color_as_the_only_signal() -> None:
    environment = PROFILES["COLOR_VISION"]["frozen_environment"]
    assert environment["color_only_signal_allowed"] is False
    assert environment["redundant_cues"] == ["中文文字", "状态符号"]


def test_text_scale_contract_requires_200_percent_reflow() -> None:
    assert PROFILES["TEXT_SCALE_200"]["frozen_environment"] == {
        "text_scale_percent": 200,
        "required_reflow": True,
    }


def test_keyboard_focus_and_screen_reader_order_match_display_order() -> None:
    keyboard = PROFILES["KEYBOARD_ONLY"]["frozen_environment"]
    reader = PROFILES["SCREEN_READER_LINEAR"]["frozen_environment"]
    assert keyboard["pointer_required"] is False
    assert keyboard["focus_order"] == DISPLAY_ORDER
    assert reader["reading_order"] == DISPLAY_ORDER
    assert len(reader["dynamic_announcements"]) == 3


@pytest.mark.parametrize("sample_id", sorted(SAMPLES))
def test_each_frozen_budget_is_positive_integer_and_uses_a_required_profile(sample_id: str) -> None:
    sample = SAMPLES[sample_id]
    assert sample["profile_id"] in FIXTURE["expected_profile_ids"]
    assert type(sample["budget_seconds"]) is int
    assert sample["budget_seconds"] > 0
    assert any("\u4e00" <= char <= "\u9fff" for char in sample["variant"])


@pytest.mark.parametrize("profile_id", FIXTURE["expected_profile_ids"])
def test_each_profile_budget_vector_matches_frozen_fixture(profile_id: str) -> None:
    actual = sorted(row["budget_seconds"] for row in PLAN["scenario_budgets"] if row["profile_id"] == profile_id)
    assert actual == FIXTURE["expected_profile_budget_seconds"][profile_id]


def test_frozen_budget_summary_matches_report_and_pass_gate() -> None:
    durations = [row["budget_seconds"] for row in PLAN["scenario_budgets"]]
    result = evaluate_timing_gate(durations)
    expected = FIXTURE["expected_timing_summary"]
    assert result["status"] == expected["status"] == "PASS"
    assert result["sample_count"] == expected["sample_count"] == 21
    assert result["median_seconds"] == expected["median_seconds"] == 540
    assert result["p95_seconds"] == expected["p95_seconds"] == 840
    assert REPORT["timing_assessment"]["median_seconds"] == result["median_seconds"]
    assert REPORT["timing_assessment"]["p95_seconds"] == result["p95_seconds"]


@pytest.mark.parametrize("vector", FIXTURE["boundary_vectors"], ids=lambda row: row["id"])
def test_every_timing_boundary_vector_has_exact_expected_disposition(vector: dict) -> None:
    result = evaluate_timing_gate(vector["durations_seconds"])
    assert result["status"] == vector["expected_status"]


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_boundary_deltas"])
@pytest.mark.parametrize("adverse", [False, True])
def test_numeric_boundary_and_adverse_odds_cannot_change_usability_gate(delta: str, adverse: bool) -> None:
    durations = [row["budget_seconds"] for row in PLAN["scenario_budgets"]]
    baseline = evaluate_timing_gate(durations)
    result = evaluate_timing_gate(durations, numeric_boundary_delta=delta, adverse_odds_tick=adverse)
    assert result["status"] == baseline["status"]
    assert result["median_seconds"] == baseline["median_seconds"]
    assert result["p95_seconds"] == baseline["p95_seconds"]


@pytest.mark.parametrize(
    "samples,kwargs,error",
    [
        ([], {}, "non-empty"),
        ([0], {}, "positive integer"),
        ([-1], {}, "positive integer"),
        ([1.0], {}, "positive integer"),
        ([True], {}, "positive integer"),
        ([600], {"numeric_boundary_delta": "0.001"}, "not frozen"),
        ([600], {"adverse_odds_tick": 1}, "must be boolean"),
        ([600], {"median_max_seconds": 600.0}, "integer seconds"),
    ],
)
def test_malformed_timing_inputs_fail_closed(samples, kwargs, error: str) -> None:
    with pytest.raises(UsabilityAccessibilityError, match=error):
        evaluate_timing_gate(samples, **kwargs)


@pytest.mark.parametrize("contract_id", FIXTURE["expected_accessibility_contract_ids"])
def test_each_accessibility_contract_has_three_chinese_assertions(contract_id: str) -> None:
    row = CONTRACTS[contract_id]
    assert row["profile_id"] in FIXTURE["expected_profile_ids"]
    assert len(row["assertions"]) == 3
    assert all(any("\u4e00" <= char <= "\u9fff" for char in value) for value in row["assertions"])


@pytest.mark.parametrize("fault_id", FIXTURE["expected_failure_ids"])
def test_each_required_failure_has_a_structured_fail_closed_log(fault_id: str) -> None:
    row = FAILURE_LOGS[fault_id]
    assert row["status"] == "FAIL_CLOSED_VERIFIED"
    assert any("\u4e00" <= char <= "\u9fff" for char in row["injected_fault"])
    assert any("\u4e00" <= char <= "\u9fff" for char in row["expected_action"])


def test_structural_report_pass_does_not_upgrade_runtime_status() -> None:
    assessment = REPORT["structural_assessment"]
    assert assessment["machine_gate_status"] == "PASS"
    assert assessment["profile_count"] == 7
    assert assessment["passed_contract_count"] == 7
    assert assessment["failed_contract_count"] == 0
    assert all(row["status"] == "PASS_DESIGN_CONTRACT" for row in assessment["results"])
    assert all(row["runtime_status"] == "NOT_EXECUTED" for row in assessment["results"])


def test_external_effect_boundary_is_all_false_and_zero_cash() -> None:
    boundary = FIXTURE["expected_external_effect_boundary"]
    assert PLAN["safety"] == boundary
    assert REPORT["external_effect_boundary"] == boundary
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert boundary["owner_final_order_only"] is True
    assert all(value is False for key, value in boundary.items() if key not in {"incremental_cash_spent_aud", "owner_final_order_only"})


@pytest.mark.parametrize(
    "target,path,replacement,check_id",
    [
        ("plan", ["scenario_budgets", 0, "budget_seconds"], 601, "S03P04-SAMPLE-PROFILE-BUDGETS"),
        ("plan", ["profiles", 3, "frozen_environment", "color_only_signal_allowed"], True, "S03P04-PROFILE-COLOR_VISION"),
        ("plan", ["profiles", 5, "frozen_environment", "focus_order"], ["action"], "S03P04-PROFILE-KEYBOARD_ONLY"),
        ("plan", ["profiles", 6, "frozen_environment", "reading_order"], list(reversed(DISPLAY_ORDER)), "S03P04-PROFILE-SCREEN_READER_LINEAR"),
        ("plan", ["profiles", 2, "frozen_environment", "maximum_initial_payload_bytes"], 32769, "S03P04-PROFILE-LOW_BANDWIDTH"),
        ("plan", ["profiles", 0, "id"], "UNKNOWN_PROFILE", "S03P04-PROFILE-SET"),
        ("report", ["claim_boundary", "human_timing_observed"], True, "S03P04-REPORT-CLAIM-BOUNDARY"),
        ("report", ["structural_assessment", "results", 0, "runtime_status"], "PASS", "S03P04-REPORT-STRUCTURAL-BINDING"),
        ("report", ["timing_assessment", "median_seconds"], 539, "S03P04-REPORT-TIMING-BINDING"),
        ("report", ["structured_failure_logs", 0, "status"], "PASS", "S03P04-FAILURE-LOG-FAULT-TIMING-MEDIAN"),
    ],
)
def test_semantic_fault_injection_is_rejected_by_oracle_clone(
    tmp_path: Path,
    target: str,
    path: list,
    replacement,
    check_id: str,
) -> None:
    root = _clone_project(tmp_path)
    artifact_path = root / (PLAN_PATH if target == "plan" else REPORT_PATH)
    value = strict_json_load(artifact_path)
    current = value
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement
    _write_json(artifact_path, value)
    _failed(evaluate_contract(root), check_id)


@pytest.mark.parametrize(
    "relative,check_id",
    [
        (PLAN_PATH, "S03P04-PIN-UX_TEST_PLAN-JSON"),
        (REPORT_PATH, "S03P04-PIN-ACCESSIBILITY_REPORT-JSON"),
        (FIXTURE_PATH, "S03P04-PIN-MACHINE-TESTS-FIXTURES-S03_P04-JSON"),
        (P03_EVIDENCE_PATH := Path("machine/evidence/EVD-S03-P03.json"), "S03P04-PIN-MACHINE-EVIDENCE-EVD-S03-P03-JSON"),
        (Path("advice_card_schema.json"), "S03P04-PIN-ADVICE_CARD_SCHEMA-JSON"),
        (Path("reason_codes_zh.json"), "S03P04-PIN-REASON_CODES_ZH-JSON"),
    ],
)
def test_oracle_rejects_tampered_phase_or_prerequisite_artifact(tmp_path: Path, relative: Path, check_id: str) -> None:
    root = _clone_project(tmp_path)
    (root / relative).write_bytes((root / relative).read_bytes() + b"\n")
    _failed(evaluate_contract(root), check_id)


def test_oracle_rejects_its_own_source_tampering(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / "abd_acceptance/usability_accessibility.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
    _failed(evaluate_contract(root), "S03P04-ORACLE-SELF-INTEGRITY")


def test_evidence_build_is_deterministic_without_runtime_reports() -> None:
    first, rollback_first = build_evidence(ROOT, require_external_reports=False)
    second, rollback_second = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert rollback_first == rollback_second
    assert first["measurement_boundary"] == FIXTURE["expected_claim_boundary"]
    assert first["external_effect_boundary"] == FIXTURE["expected_external_effect_boundary"]
    assert first["release_status"] == "NOT_READY_STAGE_3_REVIEW_REQUIRED"
    assert first["next"] == "S03/STAGE_REVIEW_READY_NOT_STARTED"


def test_rollback_restores_every_signed_input_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert len(result["artifacts"]) == 6
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert all(row["signed_sha256"] == row["restored_sha256"] for row in result["artifacts"].values())
    assert all(row["corrupted_sha256"] != row["signed_sha256"] for row in result["artifacts"].values())


def test_existing_evidence_verifier_is_fail_closed_when_absent_or_current() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        assert result["decision"] == "S03_P04_EVIDENCE_VERIFIED"
        assert result["next"] == "S03/STAGE_REVIEW_READY_NOT_STARTED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S03_P04_EVIDENCE_INVALID_FAIL_CLOSED"


def test_signed_receipt_verifies_in_isolated_copy_without_git_history(tmp_path: Path) -> None:
    if not (ROOT / EVIDENCE_PATH).is_file() or not (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        result = verify_existing_phase_evidence(ROOT, verify_git_history=False)
        assert result["status"] == "FAIL"
        assert result["decision"] == "S03_P04_EVIDENCE_INVALID_FAIL_CLOSED"
        return
    root = _clone_project(tmp_path)
    result = verify_existing_phase_evidence(root, verify_git_history=False)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S03_P04_EVIDENCE_VERIFIED"
    assert result["next"] == "S03/STAGE_REVIEW_READY_NOT_STARTED"


def test_stage3_review_progression_is_exact_and_never_starts_s04() -> None:
    progression = _stage_review_progression(ROOT)
    assert progression["status"] in {"READY_NOT_STARTED", "CONTROLLED_CANDIDATE", "SIGNED_REVIEW_PASS"}
    s04_forbidden = [
        Path("machine/evidence/EVD-S04-P01.json"),
        Path("machine/evidence/EVD-S04-P01_rollback.json"),
        Path("tests/S04/P01_test.py"),
        Path("machine/tests/fixtures/S04_P01.json"),
    ]
    assert not [path.as_posix() for path in s04_forbidden if (ROOT / path).exists()]
    assert PLAN["next_on_pass"] == "S03/STAGE_REVIEW_READY_NOT_STARTED"
    assert REPORT["next"] == "S03/STAGE_REVIEW_READY_NOT_STARTED"


def test_current_taskpack_report_matches_exact_external_gate_shape() -> None:
    report = strict_json_load(ROOT / PACK_REPORT_PATH)
    assert _pack_report_passes(report)
    assert report["status"] == "PASS"
    assert {key: report["summary"][key] for key in ["checks", "failed", "passed"]} == {
        "checks": 49,
        "failed": 0,
        "passed": 49,
    }


@pytest.mark.parametrize(
    "path,replacement",
    [
        (["status"], "FAIL"),
        (["summary", "checks"], 48),
        (["summary", "passed"], 48),
        (["summary", "failed"], 1),
    ],
)
def test_taskpack_report_gate_fails_closed_on_mutation(path: list, replacement) -> None:
    report = copy.deepcopy(strict_json_load(ROOT / PACK_REPORT_PATH))
    current = report
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = replacement
    assert not _pack_report_passes(report)


def test_current_paid_dependency_scan_matches_exact_external_gate_shape() -> None:
    text = (ROOT / SCAN_REPORT_PATH).read_text(encoding="utf-8")
    assert _paid_dependency_scan_passes(text)


@pytest.mark.parametrize(
    "required_line",
    [
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    ],
)
def test_paid_dependency_scan_gate_fails_when_required_line_is_missing(required_line: str) -> None:
    lines = (ROOT / SCAN_REPORT_PATH).read_text(encoding="utf-8").splitlines()
    assert required_line in lines
    assert not _paid_dependency_scan_passes("\n".join(line for line in lines if line != required_line))


def test_external_report_mode_fails_closed_if_junit_reports_are_missing(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for path in [JUNIT_PATH, FULL_JUNIT_PATH]:
        if (root / path).exists():
            (root / path).unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S03P04-JUNIT")
    assert "S03P04-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


def test_allowed_numeric_boundary_set_is_exact() -> None:
    assert ALLOWED_NUMERIC_BOUNDARY_DELTAS == {"-0.0001", "0", "0.0001"}
    assert set(FIXTURE["allowed_numeric_boundary_deltas"]) == ALLOWED_NUMERIC_BOUNDARY_DELTAS


def test_release_language_never_claims_returns_or_production_readiness() -> None:
    rendered = json.dumps({"plan": PLAN, "report": REPORT}, ensure_ascii=False, sort_keys=True)
    assert "NOT_READY_STAGE_3_REVIEW_REQUIRED" in rendered
    assert "NOT_EXECUTED" in rendered
    assert "不保证" in rendered
    assert REPORT["release_status"] != "READY"
    assert REPORT["claim_boundary"]["production_ui_deployed"] is False
