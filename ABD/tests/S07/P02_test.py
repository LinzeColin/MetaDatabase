from __future__ import annotations

import ast
from copy import deepcopy
import json
import os
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.identity_resolution import verify_existing_phase_evidence as verify_p01_evidence
from abd_acceptance.temporal_lineage import (
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    LEAKAGE_ORACLE_PATH,
    ORACLE_PATH,
    P01_EVIDENCE_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SCHEMA_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    _check_pins,
    _check_reports,
    _junit_is_normalized,
    _junit_summary,
    _structural_self_hash,
    build_evidence as _build_evidence,
    perform_rollback_drill,
    validate_candidate_preflight as _validate_candidate_preflight,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)
from leakage_oracle import (
    FUTURE_INFORMATION_TOLERANCE,
    LINEAGE_APPROVED_NO_ADVICE,
    NO_ADVICE,
    LineageValidationError,
    deterministic_lineage_hash,
    evaluate_lineage,
    prepare_policy,
    strict_json_load as strict_lineage_json_load,
    validate_schema_document,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = strict_lineage_json_load(ROOT / SCHEMA_PATH)
FIXTURE = strict_lineage_json_load(ROOT / FIXTURE_PATH)
POLICY = prepare_policy(SCHEMA, FIXTURE["policy"])


def validate_candidate_preflight(root: Path) -> dict:
    return _validate_candidate_preflight(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def build_evidence(root: Path, require_test_reports: bool = False):
    return _build_evidence(
        root,
        require_test_reports=require_test_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def verify_existing_phase_evidence(root: Path) -> dict:
    return _verify_existing_phase_evidence(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"

    def link_or_copy(source: str, target: str) -> str:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        return target

    shutil.copytree(
        ROOT,
        destination,
        copy_function=link_or_copy,
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github", copy_function=link_or_copy)
    return destination


def _write_json(path: Path, value) -> None:
    path.unlink(missing_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _case(case_id: str) -> dict:
    return next(case for case in FIXTURE["cases"] if case["case_id"] == case_id)


def _assert_no_advice(result: dict) -> None:
    assert result["status"] == NO_ADVICE
    assert result["lineage_eligible"] is False
    assert result["action"] == NO_ADVICE
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False
    assert result["real_time_soak_waited"] is False


def test_candidate_preflight_and_contract_pass_without_generated_reports() -> None:
    preflight = validate_candidate_preflight(ROOT)
    assert preflight["status"] == "PASS", preflight
    assert preflight["next"] == FIXTURE["expected_next"]
    assert preflight["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert preflight["summary"]["failed"] == 0


def test_taskpack_scope_trace_and_zero_tolerance_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    requirement = next(item for item in requirements if item["id"] == "REQ-S07-P02")
    contracts = strict_json_load(ROOT / "machine/facts/acceptance_contracts.json")
    contract = next(item for item in contracts if item["id"] == CONTRACT_ID)
    graph = strict_json_load(ROOT / "machine/facts/task_graph.json")["tasks"]
    trace = strict_json_load(ROOT / "machine/facts/traceability_matrix.json")
    trace_row = next(item for item in trace if item["requirement_id"] == "REQ-S07-P02")
    tasks = [item for item in graph if item.get("stage_id") == "S07" and item.get("phase_id") == "P02"]
    assert requirement["scope"] == ["temporal_lineage.schema.json", "leakage_oracle.py"]
    assert requirement["target"] == "未来信息容忍度=0。"
    assert contract["pass_gate"] == requirement["target"]
    assert [row["id"] for row in contract["tests"]] == ["TEST-S07-P02", "TEST-S07-P02-BOUNDARY", "TEST-S07-P02-REPLAY"]
    assert [item["id"] for item in tasks] == ["T-S07-P02-01", "T-S07-P02-02", "T-S07-P02-03"]
    assert trace_row["artifact_ids"] == ["ART-S07-P02-01", "ART-S07-P02-02"]
    assert FUTURE_INFORMATION_TOLERANCE == 0


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_schema_is_production_equivalent_and_policy_is_frozen() -> None:
    assert validate_schema_document(SCHEMA) == SCHEMA
    assert SCHEMA["x_abd_contract_id"] == CONTRACT_ID
    assert SCHEMA["x_abd_future_information_tolerance"] == 0
    assert SCHEMA["x_abd_production_equivalent"] is True
    assert FIXTURE["policy"]["future_information_tolerance"] == 0
    assert POLICY.future_information_tolerance == 0
    assert POLICY.parameter_version_sha256 == sha256_file(ROOT / "machine/facts/parameters.json")


@pytest.mark.parametrize("case_id", [case["case_id"] for case in FIXTURE["cases"]])
def test_frozen_positive_boundary_negative_and_fault_cases_are_exact(case_id: str) -> None:
    case = _case(case_id)
    result = evaluate_lineage(POLICY, case["record"])
    assert result["status"] == case["expected"]["status"]
    assert result["lineage_eligible"] is case["expected"]["lineage_eligible"]
    assert result["action"] == NO_ADVICE
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    if "reason_codes" in case["expected"]:
        assert result["reason_codes"] == case["expected"]["reason_codes"]
    else:
        assert case["expected"]["reason_code"] in result["reason_codes"]


def test_positive_lineage_is_eligible_but_still_never_a_recommendation_or_order() -> None:
    result = evaluate_lineage(POLICY, _case("POSITIVE_EXACT")["record"])
    assert result["status"] == LINEAGE_APPROVED_NO_ADVICE
    assert result["lineage_eligible"] is True
    assert result["action"] == NO_ADVICE
    assert result["output_sha256"] == FIXTURE["expected_positive_output_sha256"]
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False


def test_exact_time_equality_passes_but_future_cutoff_by_00001_fails_closed() -> None:
    equality = evaluate_lineage(POLICY, _case("BOUNDARY_ALL_TIMES_EQUAL")["record"])
    future = evaluate_lineage(POLICY, _case("NEGATIVE_FEATURE_CUTOFF_PLUS_0001")["record"])
    assert equality["status"] == LINEAGE_APPROVED_NO_ADVICE
    _assert_no_advice(future)
    assert future["future_information_count"] == 1
    assert "FUTURE_INFORMATION_TOLERANCE_EXCEEDED" in future["reason_codes"]


def test_adverse_odds_plus_minus_0001_cannot_enable_an_order_or_change_action() -> None:
    lower = evaluate_lineage(POLICY, _case("BOUNDARY_ODDS_MINUS_0001")["record"])
    upper = evaluate_lineage(POLICY, _case("BOUNDARY_ODDS_PLUS_0001")["record"])
    assert lower["status"] == upper["status"] == LINEAGE_APPROVED_NO_ADVICE
    assert lower["action"] == upper["action"] == NO_ADVICE
    assert lower["order_submission_enabled"] is upper["order_submission_enabled"] is False


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (lambda record: record.__setitem__("source_time", "2026-08-15T18:00:02+10:00"), "SOURCE_TIME_AFTER_OBSERVED"),
        (lambda record: record.__setitem__("observed_time", "2026-08-15T18:00:03+10:00"), "OBSERVED_TIME_AFTER_AVAILABLE"),
        (lambda record: record.__setitem__("available_time", "2026-08-15T18:00:03.0001+10:00"), "AVAILABLE_TIME_AFTER_FEATURE_CUTOFF"),
        (lambda record: record.__setitem__("feature_cutoff_time", "2026-08-15T18:00:04.0001+10:00"), "FUTURE_INFORMATION_TOLERANCE_EXCEEDED"),
        (lambda record: record.__setitem__("source_version_sha256", "f" * 64), "SOURCE_VERSION_MISMATCH"),
        (lambda record: record.__setitem__("model_version_sha256", "f" * 64), "MODEL_VERSION_MISMATCH"),
        (lambda record: record.__setitem__("parameter_version_sha256", "f" * 64), "PARAMETER_VERSION_MISMATCH"),
        (lambda record: record.__setitem__("untrusted_future_field", "x"), "UNKNOWN_FIELD"),
    ],
)
def test_temporal_version_and_unknown_input_fail_closed(mutation, reason_code: str) -> None:
    record = deepcopy(_case("POSITIVE_EXACT")["record"])
    mutation(record)
    result = evaluate_lineage(POLICY, record)
    _assert_no_advice(result)
    assert reason_code in result["reason_codes"]


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (lambda record: record.__setitem__("source_time", "2026-08-15T18:00:00"), "TIMEZONE_REQUIRED"),
        (lambda record: record.__setitem__("reference_odds_decimal", 2.0), "BINARY_FLOAT_NOT_ALLOWED"),
        (lambda record: record.__setitem__("reference_odds_decimal", "1.0000"), "ODDS_INVALID"),
        (lambda record: record.pop("feature_manifest_sha256"), "MISSING_FIELD"),
    ],
)
def test_timezone_binary_float_odds_and_missing_field_fail_closed(mutation, reason_code: str) -> None:
    record = deepcopy(_case("POSITIVE_EXACT")["record"])
    mutation(record)
    result = evaluate_lineage(POLICY, record)
    _assert_no_advice(result)
    assert result["reason_codes"] == [reason_code]


def test_policy_and_schema_mutations_are_rejected_before_any_result() -> None:
    bad_policy = deepcopy(FIXTURE["policy"])
    bad_policy["future_information_tolerance"] = 1
    with pytest.raises(LineageValidationError) as policy_error:
        prepare_policy(SCHEMA, bad_policy)
    assert policy_error.value.code == "FUTURE_INFORMATION_TOLERANCE_INVALID"
    bad_schema = deepcopy(SCHEMA)
    bad_schema["additionalProperties"] = True
    with pytest.raises(LineageValidationError) as schema_error:
        validate_schema_document(bad_schema)
    assert schema_error.value.code == "SCHEMA_INVALID"


def test_strict_loader_rejects_duplicate_keys_and_binary_floats(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(LineageValidationError) as duplicate_error:
        strict_lineage_json_load(duplicate)
    assert duplicate_error.value.code == "DUPLICATE_JSON_KEY"
    binary_float = tmp_path / "float.json"
    binary_float.write_text('{"a":0.1}', encoding="utf-8")
    with pytest.raises(LineageValidationError) as float_error:
        strict_lineage_json_load(binary_float)
    assert float_error.value.code == "BINARY_FLOAT_NOT_ALLOWED"


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    record = _case("POSITIVE_EXACT")["record"]
    expected = deterministic_lineage_hash(POLICY, record)
    hashes = {
        deterministic_lineage_hash(POLICY, {key: record[key] for key in reversed(list(record))})
        for _ in range(FIXTURE["replay_count"])
    }
    assert hashes == {expected} == {FIXTURE["expected_positive_output_sha256"]}


def test_ten_thousand_adverse_perturbations_never_enable_advice_or_orders() -> None:
    base = _case("POSITIVE_EXACT")["record"]
    for index in range(FIXTURE["adverse_replay_count"]):
        record = deepcopy(base)
        mode = index % 5
        if mode == 0:
            record["feature_cutoff_time"] = "2026-08-15T18:00:04.0001+10:00"
        elif mode == 1:
            record["source_version_sha256"] = "f" * 64
        elif mode == 2:
            record["model_version_sha256"] = "f" * 64
        elif mode == 3:
            record["parameter_version_sha256"] = "f" * 64
        else:
            record["untrusted_future_field"] = str(index)
        _assert_no_advice(evaluate_lineage(POLICY, record))


def test_leakage_oracle_has_no_network_process_scheduler_or_sleep_capability() -> None:
    source = (ROOT / LEAKAGE_ORACLE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"}
    assert not any(token in source for token in ("sleep(", "requests.", "urllib.", "socket.", "subprocess.", "http://", "https://"))


def test_rollback_drill_is_hash_only_and_never_changes_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False


def test_candidate_fails_closed_when_phase_artifact_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    payload = strict_lineage_json_load(root / FIXTURE_PATH)
    payload["policy"]["future_information_tolerance"] = 1
    _write_json(root / FIXTURE_PATH, payload)
    checks: list[dict] = []
    _check_pins(root, checks, {})
    assert next(check for check in checks if check["id"] == "S07P02-PIN-S07_P02-JSON")["passed"] is False


def test_candidate_fails_closed_when_p01_predecessor_receipt_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    payload = strict_json_load(root / P01_EVIDENCE_PATH)
    payload["status"] = "FAIL"
    _write_json(root / P01_EVIDENCE_PATH, payload)
    preflight = validate_candidate_preflight(root)
    assert preflight["status"] == "FAIL"
    assert "S07P02-P01-PREDECESSOR-PASS" in preflight["summary"]["failed_check_ids"]


def test_generated_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(root, FIXTURE, checks, require_test_reports=True)
    assert next(check for check in checks if check["id"] == "S07P02-TARGETED-PYTEST-REPORT")["passed"] is False
    assert next(check for check in checks if check["id"] == "S07P02-FULL-PYTEST-REPORT")["passed"] is False


def test_junit_normalization_accepts_only_fixed_metadata(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" timestamp="%s" time="0.000"><testcase name="offline" time="0.000" /></testsuite></testsuites>'
        % JUNIT_FIXED_CLOCK,
        encoding="utf-8",
    )
    assert _junit_is_normalized(report) is True
    assert _junit_summary(report)["tests"] == 1
    report.write_text(report.read_text(encoding="utf-8").replace('time="0.000"', 'time="0.001"', 1), encoding="utf-8")
    assert _junit_is_normalized(report) is False


def test_oracle_cli_is_wired_to_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S07-P02": write_temporal_lineage_phase_evidence' in source
    assert "from .temporal_lineage import write_phase_evidence as write_temporal_lineage_phase_evidence" in source


def test_candidate_evidence_carries_pinned_lineage_and_structured_failure_summary() -> None:
    evidence, rollback = build_evidence(ROOT)
    assert evidence["status"] == "PASS", evidence["validation"]
    assert evidence["lineage_summary"]["future_information_tolerance"] == 0
    assert evidence["lineage_summary"]["positive_action"] == NO_ADVICE
    assert evidence["lineage_summary"]["recommendation_generated"] is False
    assert evidence["lineage_summary"]["order_submission_enabled"] is False
    assert evidence["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert evidence["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert evidence["structured_failure_log"]["case_reason_codes"]["NEGATIVE_FEATURE_CUTOFF_PLUS_0001"]
    assert rollback["status"] == "PASS"


def test_p01_predecessor_receipt_remains_independently_verifiable() -> None:
    result = verify_p01_evidence(ROOT)
    assert result["status"] == "PASS", result


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        result = verify_existing_phase_evidence(ROOT)
        assert result["status"] == "PASS", result
    else:
        assert not (ROOT / EVIDENCE_PATH).is_file()
        assert not (ROOT / ROLLBACK_EVIDENCE_PATH).is_file()
