from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

from abd_acceptance.authorization import (
    AUTHORIZATION_PATH,
    DEFAULTS_PATH,
    PAUSE_SCHEMA_PATH,
    build_evidence,
    evaluate_contract,
    perform_rollback_drill,
)
from abd_acceptance.canonical_facts import strict_json_load


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / "machine/tests/fixtures/S00_P02.json")


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _action(matrix, action_id: str):
    return next(action for action in matrix["actions"] if action["id"] == action_id)


def _default(defaults, condition_code: str):
    return next(row for row in defaults["defaults"] if row["condition_code"] == condition_code)


def test_baseline_authorization_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["next"] == "S00/P03_READY_NOT_STARTED"


def test_real_order_submission_cannot_be_authorized(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    _action(matrix, "REAL_ORDER_SUBMISSION")["authorization"] = "PREAUTHORIZED"
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-PROHIBITIONS" in result["summary"]["failed_check_ids"]


def test_permanent_email_delete_cannot_be_authorized(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    _action(matrix, "PERMANENT_EMAIL_DELETE")["authorization"] = "CONDITIONALLY_PREAUTHORIZED"
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-PROHIBITIONS" in result["summary"]["failed_check_ids"]


def test_external_capability_cannot_be_claimed_verified(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    _action(matrix, "OVH_REVERSIBLE_DEPLOY")["capability_status"] = "VERIFIED_AVAILABLE"
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-ACTIVE-ACTIONS-SAFE" in result["summary"]["failed_check_ids"]


def test_stage_upload_requires_whole_stage_review(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    _action(matrix, "GITHUB_STAGE_UPLOAD")["preconditions"].remove("WHOLE_STAGE_REVIEW_PASS")
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-EXTERNAL-GATES" in result["summary"]["failed_check_ids"]


def test_missing_gmail_consent_must_not_block_core(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    _action(matrix, "GMAIL_OAUTH_CONSENT")["on_precondition_failure"] = "PAUSE_ALL"
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-GMAIL-NONBLOCKING" in result["summary"]["failed_check_ids"]


def test_unknown_authorization_never_executes(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEFAULTS_PATH
    defaults = strict_json_load(path)
    _default(defaults, "AUTHORIZATION_UNKNOWN_OR_MISSING")["decision"] = "EXECUTE"
    _write_json(path, defaults)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "DEFAULTS-UNKNOWN-NEVER-EXECUTES" in result["summary"]["failed_check_ids"]


def test_nonexplicit_reason_cannot_block_task_graph(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / DEFAULTS_PATH
    defaults = strict_json_load(path)
    row = _default(defaults, "SOURCE_UNAVAILABLE_STALE_OR_RATE_LIMITED")
    row["blocks_task_graph"] = True
    row["owner_input_required"] = True
    row["pause_reason_code"] = "SOURCE_FAILED"
    _write_json(path, defaults)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "DEFAULTS-ONLY-EXPLICIT-PAUSE-BLOCKS" in result["summary"]["failed_check_ids"]


def test_unknown_pause_reason_code_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    matrix["global_pause_reasons"][0]["code"] = "UNKNOWN_REASON"
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-PAUSE-REASONS-EXACT" in result["summary"]["failed_check_ids"]


@pytest.mark.parametrize("case", FIXTURE["cash_boundary_cases"], ids=lambda case: case["id"])
def test_cash_boundary_is_exactly_zero(tmp_path: Path, case) -> None:
    project = _clone_project(tmp_path)
    path = project / AUTHORIZATION_PATH
    matrix = strict_json_load(path)
    _action(matrix, "LOCAL_CODE_OR_CONFIG_EDIT")["cash_cost_aud"] = case["value"]
    _write_json(path, matrix)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == case["expected_status"]
    assert "AUTH-ACTIVE-ACTIONS-SAFE" in result["summary"]["failed_check_ids"]


def test_pause_receipt_valid_fixture_passes_schema() -> None:
    schema = strict_json_load(ROOT / PAUSE_SCHEMA_PATH)
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(FIXTURE["valid_pause_receipt"])


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_question",
        "secret_present",
        "unknown_reason",
        "positive_cash",
        "absolute_artifact_path",
    ],
)
def test_invalid_pause_receipts_fail_schema(mutation: str) -> None:
    schema = strict_json_load(ROOT / PAUSE_SCHEMA_PATH)
    receipt = deepcopy(FIXTURE["valid_pause_receipt"])
    if mutation == "missing_question":
        del receipt["minimal_decision_question"]
    elif mutation == "secret_present":
        receipt["secret_material_present"] = True
    elif mutation == "unknown_reason":
        receipt["pause_reason_code"] = "UNKNOWN"
    elif mutation == "positive_cash":
        receipt["incremental_cash_cost_aud"] = "0.01"
    elif mutation == "absolute_artifact_path":
        receipt["evidence"][0]["artifact"] = "/private/secret.txt"
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    assert list(validator.iter_errors(receipt))


def test_p01_prerequisite_must_remain_pass(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/EVD-S00-P01.json"
    evidence = strict_json_load(path)
    evidence["status"] = "FAIL"
    _write_json(path, evidence)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "PREREQ-P01-PASS" in result["summary"]["failed_check_ids"]


def test_malformed_p01_evidence_index_fails_closed_without_crashing(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/evidence/evidence_index.jsonl").write_text("{\n", encoding="utf-8")
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "PREREQ-P01-PASS" in result["summary"]["failed_check_ids"]


def test_canonical_facts_drift_after_p01_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/facts/canonical_facts.json"
    canonical = strict_json_load(path)
    canonical["product"]["initial_bankroll_aud"] = "300.01"
    _write_json(path, canonical)
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "AUTH-AUTHORITY-SOURCE-HASHES" in result["summary"]["failed_check_ids"]


def test_second_authorization_matrix_source_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    shadow = project / "shadow/authorization_matrix.json"
    shadow.parent.mkdir(parents=True)
    shutil.copyfile(str(project / AUTHORIZATION_PATH), str(shadow))
    result = evaluate_contract(project, require_external_reports=False)
    assert result["status"] == "FAIL"
    assert "SOURCE-SINGLE-AUTHORIZATION_MATRIX" in result["summary"]["failed_check_ids"]


def test_evidence_replay_is_deterministic() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback


def test_rollback_drill_restores_all_three_policy_artifacts() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS"
    assert len(result["artifacts"]) == 3
    for artifact in result["artifacts"].values():
        assert artifact["status"] == "PASS"
        assert artifact["signed_sha256"] == artifact["restored_sha256"]
        assert artifact["corrupted_sha256"] != artifact["restored_sha256"]
    assert result["production_state_changed"] is False
