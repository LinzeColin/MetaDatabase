from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import strict_json_load
from abd_acceptance.stage13_review import (
    BASELINE_HASHES,
    CONTRACT_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FINDINGS_PATH,
    FIXTURE_PATH,
    ORACLE_PATH,
    PHASE_SPECS,
    PHASE_VERIFIERS,
    REQUIRED_GATES,
    ROLLBACK_ARTIFACTS,
    Stage13ReviewError,
    evaluate_stage_snapshot,
    perform_rollback_drill,
    validate_candidate_preflight,
    write_stage_review_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = strict_json_load(ROOT / CONTRACT_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
FINDINGS = strict_json_load(ROOT / FINDINGS_PATH)


@lru_cache
def _preflight() -> dict[str, object]:
    return validate_candidate_preflight(ROOT)


def test_targeted_stage_review_preflight_passes() -> None:
    result = _preflight()
    assert result["status"] == "PASS", result
    assert result["stage_status"] == "S13_WHOLE_STAGE_REVIEW_PASS"
    assert result["next"] == "S13/GITHUB_STAGE_UPLOAD_READY"
    assert result["summary"]["failed"] == 0


@pytest.mark.parametrize("phase", list(PHASE_VERIFIERS))
def test_each_signed_phase_receipt_remains_current(phase: str) -> None:
    spec = PHASE_SPECS[phase]
    checks = {check["id"]: check for check in _preflight()["checks"]}
    assert checks["S13REVIEW-%s-CURRENT-PHASE-ORACLE" % phase]["detail"] == {
        "contract_id": spec["contract_id"],
        "status": "PASS",
        "evidence_path": spec["evidence_path"],
        "evidence_sha256": spec["evidence_sha256"],
        "next": spec["next"],
    }


def test_review_contract_keeps_the_frozen_baseline_and_gates_exact() -> None:
    assert CONTRACT["baseline_hashes"] == BASELINE_HASHES
    assert CONTRACT["review_gates"] == REQUIRED_GATES
    assert CONTRACT["execution_policy"] == {
        "offline_deterministic_only": True,
        "phase_test_rerun_allowed": False,
        "full_regression_or_real_time_soak_allowed": False,
        "single_pass_fixture_cases_only": True,
        "github_upload_performed_by_local_review": False,
        "production_deployed_or_activated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def test_review_has_no_open_or_fabricated_findings() -> None:
    assert FINDINGS["summary"] == FIXTURE["expected_findings_summary"]
    assert FINDINGS["findings"] == []
    assert FINDINGS["explicit_limitations"] == [
        {
            "id": "S13-LOCAL-EVIDENCE-BOUNDARY",
            "status": "UNVERIFIED_OUT_OF_SCOPE",
            "statement": "S13 复审只证明冻结合成制品与本地证据链；不证明真实浏览器、移动设备、市场、账户、TAB/Gmail、OVH、Cloudflare、部署、上线、订单或实际收益。",
        }
    ]


def test_fixture_is_a_small_single_pass_review_set() -> None:
    assert FIXTURE["single_pass_case_count"] == 9
    assert len(FIXTURE["cases"]) == 9
    assert len({case["case_id"] for case in FIXTURE["cases"]}) == 9
    assert "replay_count" not in FIXTURE
    assert "adverse_replay_count" not in FIXTURE


def test_static_taskpack_report_uses_its_actual_summary_schema() -> None:
    report = strict_json_load(ROOT / "machine/evidence/validation_report.json")
    assert report["status"] == "PASS"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["passed"] == report["summary"]["checks"]


def test_rollback_drill_only_preserves_local_evidence() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["recommendation_generated"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert set(rollback["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}


def test_positive_stage_snapshot_is_always_no_action() -> None:
    case = next(case for case in FIXTURE["cases"] if case["case_id"] == "POSITIVE_EXACT_STAGE")
    result = evaluate_stage_snapshot(case["snapshot"])
    assert result["status"] == case["expected"]["status"]
    assert result["reason_codes"] == []
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False
    assert result["real_time_soak_waited"] is False


@pytest.mark.parametrize(
    "case",
    [case for case in FIXTURE["cases"] if case["case_id"] != "POSITIVE_EXACT_STAGE"],
    ids=lambda case: case["case_id"],
)
def test_each_negative_snapshot_fails_closed_without_action(case: dict[str, object]) -> None:
    result = evaluate_stage_snapshot(case["snapshot"])
    assert result["status"] == case["expected"]["status"]
    assert result["reason_codes"] == case["expected"]["reason_codes"]
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False
    assert result["real_time_soak_waited"] is False


@pytest.mark.parametrize("snapshot", [{}, {"findings_open": True}])
def test_malformed_snapshot_is_rejected(snapshot: dict[str, object]) -> None:
    with pytest.raises(Stage13ReviewError):
        evaluate_stage_snapshot(snapshot)


def test_oracle_has_no_network_process_wait_or_order_capability() -> None:
    source = (ROOT / ORACLE_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not imported & {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    call_names = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert not call_names & {"sleep", "Popen", "submit_order"}


def test_local_review_external_boundary_remains_exact() -> None:
    assert EXTERNAL_EFFECT_BOUNDARY == {
        "github_upload_performed_by_local_review": False,
        "remote_ci_result_claimed_by_local_review": False,
        "external_network_accessed_for_product_runtime": False,
        "gmail_account_or_api_accessed": False,
        "ovh_or_cloudflare_runtime_accessed": False,
        "model_or_strategy_executed": False,
        "recommendation_generated_or_enabled": False,
        "order_submitted_confirmed_or_retried": False,
        "production_deployed_or_activated": False,
        "real_account_balance_read_or_written": False,
        "real_time_soak_waited": False,
        "evidence_numeric_risk_safety_or_source_gate_relaxed": False,
        "incremental_cash_spent_aud": "0.00",
        "owner_final_order_only": True,
    }


def test_controls_remain_local_and_unverified() -> None:
    result = _preflight()
    passed = {check["id"] for check in result["checks"] if check["passed"]}
    assert {
        "S13REVIEW-CHINESE-WORKBENCH-AND-LOCAL-PUSH-GATE",
        "S13REVIEW-VISIBLE-QUOTE-REVOKE-AND-OWNER-ONLY-GATE",
        "S13REVIEW-POST-ADVICE-SYNTHETIC-NO-ACTUAL-RETURN-GATE",
        "S13REVIEW-SIX-COMPLETE-PATHS-AND-LOCAL-RECOVERY-GATE",
        "S13REVIEW-NO-NETWORK-ACCOUNT-ORDER-DEPLOY-OR-SOAK-BOUNDARY",
    } <= passed


def test_acceptance_cli_is_wired_to_the_exact_stage_review_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"STAGE-REVIEW-S13": write_stage13_review_evidence' in source
    assert '"STAGE-REVIEW-S13": verify_existing_stage13_review_evidence' in source


def test_writer_refuses_noncanonical_evidence_directory_without_writing() -> None:
    with pytest.raises(Stage13ReviewError, match="canonical machine/evidence"):
        write_stage_review_evidence(ROOT, ROOT / "machine/not-evidence")
