from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.target_curve import (
    TargetCurveAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from cashflow_adjustment import CashflowInputError, adjust_month
from target_engine import TargetInputError, artifact_sha256, build_artifacts, build_target_vectors, canonical_json_bytes, target_cents_for_month, validate_fixture


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S12_P01.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S12-P01"
    assert result["next"] == "S12/P02_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 14
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_target_vectors_are_exact_frozen_replay() -> None:
    vectors = build_artifacts(FIXTURE, PARAMETERS)
    assert artifact_sha256(vectors) == FIXTURE["expected_target_vectors_sha256"]
    assert json.loads((ROOT / "target_vectors.json").read_text(encoding="utf-8")) == vectors
    assert vectors["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert vectors["summary"]["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"


def test_a300_x_1point3n_target_curve_and_conservative_cent_rounding() -> None:
    assert [target_cents_for_month(index) for index in range(6)] == [30000, 39000, 50700, 65910, 85683, 111388]
    vectors = build_artifacts(FIXTURE, PARAMETERS)
    assert [row["baseline_target_start_cents"] for row in vectors["monthly_rows"]] == [30000, 39000, 50700, 65910]
    assert [row["baseline_target_end_cents"] for row in vectors["monthly_rows"]] == [39000, 50700, 65910, 85683]


def test_month_start_and_month_end_cashflows_are_adjusted_at_their_exact_boundaries() -> None:
    row = build_artifacts(FIXTURE, PARAMETERS)["monthly_rows"][2]
    assert row["month_start_external_cashflow_cents"] == 10000
    assert row["month_end_external_cashflow_cents"] == -5000
    assert row["cashflow_adjusted_opening_cents"] == 60700
    assert row["cashflow_adjusted_closing_before_end_flows_cents"] == 78910
    assert row["cashflow_adjusted_return"] == "0.3"
    assert row["cashflow_adjusted_target_end_cents"] == 73910
    assert row["target_gap_cents"] == 0


def test_shortfall_is_report_only_and_does_not_relax_any_gate() -> None:
    vectors = build_artifacts(FIXTURE, PARAMETERS)
    shortfall = vectors["monthly_rows"][3]
    assert shortfall["target_status"] == "TARGET_SHORTFALL_REPORT_ONLY"
    assert shortfall["target_gap_cents"] == -6083
    assert shortfall["shortfall_action"] == "REPORT_ONLY_NO_GATE_RELAXATION"
    assert vectors["summary"]["target_shortfall_may_relax_gate"] is False
    assert vectors["summary"]["chase_loss_prohibited"] is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture["monthly_records"][2]["cashflows"][0].update({"timing": "MID_MONTH"}),
        lambda fixture: fixture["monthly_records"][2]["cashflows"][0].update({"evidence_status": "UNVERIFIED"}),
        lambda fixture: fixture["monthly_records"][2]["cashflows"][1].update({"flow_id": "S12-P01-FLOW-001"}),
        lambda fixture: fixture["monthly_records"][3].update({"month_start": "2026-06-02T00:00:00+10:00"}),
        lambda fixture: fixture["monthly_records"][1].update({"opening_balance_cents": 39001}),
    ],
)
def test_malformed_or_unauditable_cashflows_fail_closed(mutate) -> None:
    fixture = deepcopy(FIXTURE)
    mutate(fixture)
    with pytest.raises(TargetInputError):
        validate_fixture(fixture, PARAMETERS)


def test_cashflow_adjustment_rejects_nonpositive_adjusted_opening() -> None:
    with pytest.raises(CashflowInputError):
        adjust_month(
            opening_balance_cents=100,
            closing_balance_cents=0,
            cashflows=[
                {
                    "flow_id": "S12-P01-FLOW-NEGATIVE",
                    "direction": "WITHDRAWAL",
                    "amount_cents": 100,
                    "timing": "MONTH_START",
                    "evidence_id": "S12-P01-SYNTHETIC-WITHDRAWAL-NEGATIVE",
                    "evidence_status": "SYNTHETIC_VERIFIED_FOR_TEST_ONLY",
                }
            ],
        )


def test_frozen_replay_hash_is_identical_without_waiting() -> None:
    hashes = {hashlib.sha256(canonical_json_bytes(build_target_vectors(FIXTURE, PARAMETERS))).hexdigest() for _ in range(3)}
    assert hashes == {FIXTURE["expected_target_vectors_sha256"]}


def test_core_source_has_no_network_soak_or_order_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    for relative in ("target_engine.py", "cashflow_adjustment.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not imports.intersection(prohibited)
        assert "sleep(" not in source
        assert "submit_order" not in source
        assert "retry_order" not in source
        assert "float(" not in source


def test_candidate_fails_closed_when_target_vectors_are_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "target_vectors.json"
    vectors = json.loads(path.read_text(encoding="utf-8"))
    vectors["monthly_rows"][3]["target_gap_cents"] = 0
    path.write_text(json.dumps(vectors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S12P01-FROZEN-TARGET-VECTOR-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_expected_replay_hash_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/tests/fixtures/S12_P01.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["expected_target_vectors_sha256"] = "f" * 64
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S12P01-TARGET-RUNNER" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_shortfall_policy_is_weakened(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/facts/parameters.json"
    parameters = json.loads(path.read_text(encoding="utf-8"))
    parameters["risk"]["target_shortfall_may_relax_gate"] = True
    path.write_text(json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S12P01-TARGET-RUNNER" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "target:cashflow_adjusted_curve"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_signing_replaces_only_the_p01_jsonl_row_and_replays(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    index_path = clone / "machine/evidence/evidence_index.jsonl"
    planned_row = {
        "acceptance_contract_id": "AC-S12-P01",
        "expected_artifact": "machine/evidence/EVD-S12-P01.json",
        "id": "INDEX-AC-S12-P01",
        "kind": "ACCEPTANCE_EVIDENCE",
        "pass_gate": "固定时钟下目标曲线与高精度参考一致。",
        "requirement_id": "REQ-S12-P01",
        "status": "PLANNED",
    }
    reset_lines = index_path.read_text(encoding="utf-8").splitlines()
    target_index = next(index for index, line in enumerate(reset_lines) if json.loads(line).get("id") == "INDEX-AC-S12-P01")
    reset_lines[target_index] = json.dumps(planned_row, ensure_ascii=False)
    index_path.write_text("\n".join(reset_lines) + "\n", encoding="utf-8")
    # This isolated signer test cannot consume the outer pytest run's still-open report.
    cases = "".join(
        '<testcase classname="tests.S12.P01_test" name="signer_fixture_%d" time="0.000" />' % index
        for index in range(14)
    )
    (clone / "machine/evidence/S12/P01/pytest.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuite tests="14" failures="0" errors="0" skipped="0">%s</testsuite>' % cases,
        encoding="utf-8",
    )
    before_lines = index_path.read_text(encoding="utf-8").splitlines()

    result = write_phase_evidence(clone, clone / "machine/evidence")

    after_lines = index_path.read_text(encoding="utf-8").splitlines()
    changed_rows = [index for index, (before, after) in enumerate(zip(before_lines, after_lines)) if before != after]
    assert result["status"] == "PASS"
    assert len(after_lines) == len(before_lines)
    assert changed_rows == [target_index]
    assert all(isinstance(json.loads(line), dict) for line in after_lines)
    assert json.loads(after_lines[changed_rows[0]])["kind"] == "PHASE_EVIDENCE"
    assert verify_existing_phase_evidence(clone)["status"] == "PASS"


def test_acceptance_cli_is_wired_to_the_exact_contract_after_integration() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S12-P01": write_target_curve_phase_evidence' in source
    assert '"AC-S12-P01": verify_target_curve_phase_evidence' in source
    with pytest.raises((TargetCurveAcceptanceError, FileNotFoundError)):
        from abd_acceptance.target_curve import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
