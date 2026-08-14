from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from abd_acceptance.security_analysis import (
    CONTROL_PLANE_TARGETS,
    CONTRACT_ID,
    EXECUTION_POLICY,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    ORACLE_PATH,
    PIPELINE_PATH,
    PIPELINE_STAGE_IDS,
    SAST_POLICY_PATH,
    SAST_RULE_IDS,
    SECRET_POLICY_PATH,
    SECRET_RULE_IDS,
    SecurityAnalysisError,
    build_evidence,
    evaluate_security_snapshot,
    perform_rollback_drill,
    run_security_analysis,
    scan_secret_text,
    scan_source_text,
    validate_candidate_preflight,
    validate_sast_policy,
    validate_secret_policy,
    validate_security_fixture,
    validate_security_pipeline,
    verify_existing_phase_evidence,
    write_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = json.loads((ROOT / PIPELINE_PATH).read_text(encoding="utf-8"))
SAST_POLICY = json.loads((ROOT / SAST_POLICY_PATH).read_text(encoding="utf-8"))
SECRET_POLICY = json.loads((ROOT / SECRET_POLICY_PATH).read_text(encoding="utf-8"))
FIXTURE = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == CONTRACT_ID
    assert result["decision"] == FIXTURE["expected_decision"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["analysis"]["unresolved_critical_count"] == 0
    assert result["analysis"]["unresolved_high_count"] == 0


def test_frozen_pipeline_and_policies_bind_exact_rule_sets() -> None:
    pipeline = validate_security_pipeline(PIPELINE)
    sast = validate_sast_policy(SAST_POLICY)
    secret = validate_secret_policy(SECRET_POLICY)
    fixture = validate_security_fixture(FIXTURE)
    assert [row["id"] for row in pipeline["stages"]] == list(PIPELINE_STAGE_IDS)
    assert [row["id"] for row in sast["analysis_rules"]] == list(SAST_RULE_IDS)
    assert [row["id"] for row in secret["detection_rules"]] == list(SECRET_RULE_IDS)
    assert fixture["expected_pipeline_stage_ids"] == list(PIPELINE_STAGE_IDS)


@pytest.mark.parametrize("stage_id", PIPELINE_STAGE_IDS)
def test_each_pipeline_stage_is_local_and_fail_closed(stage_id: str) -> None:
    pipeline = validate_security_pipeline(PIPELINE)
    stage = next(row for row in pipeline["stages"] if row["id"] == stage_id)
    assert stage["failure_action"] == "FAIL_CLOSED_NO_RELEASE"
    assert stage["network_accessed"] is False
    assert stage["external_execution"] is False
    assert stage["scope"]


@pytest.mark.parametrize("row", FIXTURE["snapshot_cases"], ids=lambda row: row["case_id"])
def test_frozen_single_pass_security_snapshots_replay_exactly(row: dict[str, object]) -> None:
    result = evaluate_security_snapshot(row["snapshot"])
    assert result["status"] == row["expected"]["status"]
    assert result["reason_codes"] == row["expected"]["reason_codes"]
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False
    assert result["real_time_soak_waited"] is False
    assert result["incremental_cash_spent_aud"] == "0.00"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"coverage_score": 1.0}),
        lambda value: value.update({"unresolved_high_count": True}),
        lambda value: value.update({"unknown": False}),
    ],
)
def test_malformed_security_snapshots_fail_closed(mutate) -> None:
    snapshot = deepcopy(FIXTURE["snapshot_cases"][0]["snapshot"])
    mutate(snapshot)
    with pytest.raises(SecurityAnalysisError):
        evaluate_security_snapshot(snapshot)


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("sample = 'AKIA" + "A" * 16 + "'", "SECRET-AWS-ACCESS-KEY"),
        ("sample = '-----BEGIN PRIVATE KEY-----'", "SECRET-PRIVATE-KEY"),
        ("sample = 'ghp_" + "a" * 36 + "'", "SECRET-GITHUB-PERSONAL-TOKEN"),
        ("api_key = 'abcdefghijklmnop'", "SECRET-GENERIC-INLINE-ASSIGNMENT"),
    ],
)
def test_literal_secret_patterns_become_unresolved_findings(text: str, rule_id: str) -> None:
    findings = scan_secret_text("synthetic.txt", text)
    assert [finding["rule_id"] for finding in findings] == [rule_id]
    assert findings[0]["status"] == "UNRESOLVED"


@pytest.mark.parametrize(
    ("text", "rule_id", "severity"),
    [
        ("import socket\n", "SAST-IMPORT-CAPABILITY", "HIGH"),
        ("def action():\n    sleep(1)\n", "SAST-CALL-CAPABILITY", "HIGH"),
        ("def action():\n    submit_order()\n", "SAST-ORDER-CAPABILITY", "CRITICAL"),
        ("value = 0.1\n", "SAST-FLOAT-NUMERIC-SAFETY", "HIGH"),
    ],
)
def test_unsafe_source_patterns_become_unresolved_findings(text: str, rule_id: str, severity: str) -> None:
    findings = scan_source_text("synthetic.py", text)
    assert [finding["rule_id"] for finding in findings] == [rule_id]
    assert findings[0]["severity"] == severity


def test_pipeline_tampering_fails_closed() -> None:
    pipeline = deepcopy(PIPELINE)
    pipeline["findings_gate"]["unresolved_high"] = 1
    with pytest.raises(SecurityAnalysisError):
        validate_security_pipeline(pipeline)


def test_sast_policy_tampering_fails_closed() -> None:
    policy = deepcopy(SAST_POLICY)
    policy["analysis_rules"][0]["severity"] = "LOW"
    with pytest.raises(SecurityAnalysisError):
        validate_sast_policy(policy)


def test_secret_policy_tampering_fails_closed() -> None:
    policy = deepcopy(SECRET_POLICY)
    policy["prohibited_repository_extensions"] = []
    with pytest.raises(SecurityAnalysisError):
        validate_secret_policy(policy)


def test_actual_local_analysis_has_zero_unresolved_critical_or_high_findings() -> None:
    result = run_security_analysis(
        ROOT,
        validate_security_pipeline(PIPELINE),
        validate_sast_policy(SAST_POLICY),
        validate_secret_policy(SECRET_POLICY),
    )
    assert result["status"] == "PASS", result
    assert result["findings"] == []
    assert result["unresolved_critical_count"] == 0
    assert result["unresolved_high_count"] == 0
    assert result["live_vulnerability_database_queried"] is False
    assert result["external_network_used"] is False
    assert result["external_account_or_runtime_used"] is False


def test_receipt_binds_every_control_plane_target_hash() -> None:
    evidence, _ = build_evidence(ROOT, require_test_reports=False)
    hashes = evidence["hashes"]["inputs"]
    assert all(relative in hashes for relative in CONTROL_PLANE_TARGETS)


def test_oracle_has_no_network_process_or_order_capability() -> None:
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "smtplib", "asyncio", "time", "random", "os"})
    assert "sleep(" not in source
    assert "submit_order(" not in source
    assert "retry_order(" not in source
    assert "http://" not in source.replace("http://127.0.0.1:8080", "")
    assert "https://" not in source


def test_execution_boundaries_remain_exactly_local_only() -> None:
    assert PIPELINE["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert EXECUTION_POLICY == {
        "offline_deterministic_only": True,
        "full_regression_or_real_time_soak_allowed": False,
        "external_runtime_access_allowed": False,
        "phase_test_only": True,
        "incremental_cash_spent_aud": "0.00",
    }


def test_rollback_drill_is_local_and_preserves_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["recommendation_generated"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert rollback["incremental_cash_spent_aud"] == "0.00"


def test_writer_rejects_a_noncanonical_evidence_directory_before_mutation() -> None:
    with pytest.raises(SecurityAnalysisError):
        write_phase_evidence(ROOT, ROOT / "machine/not-evidence")


def test_acceptance_cli_is_wired_and_unsigned_evidence_cannot_verify() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S14-P02": write_security_analysis_phase_evidence' in source
    assert '"AC-S14-P02": verify_security_analysis_phase_evidence' in source
    with pytest.raises(SecurityAnalysisError):
        verify_existing_phase_evidence(ROOT / "missing")
