from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.post_advice_settlement import (
    PostAdviceSettlementAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from performance_report import PerformanceReportError, build_performance_report
from post_advice_worker import CLAIM_BOUNDARY, PostAdviceError, canonical_sha256, make_advice_record, validate_advice
from result_settler import ResultSettlementError, settle_advice_record


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S13_P03.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _case(case_id: str) -> dict[str, object]:
    return next(item for item in FIXTURE["cases"] if item["case_id"] == case_id)


def _record_and_result(case_id: str) -> tuple[dict[str, object], dict[str, object]]:
    case = _case(case_id)
    record = make_advice_record(case["advice"], case["confirmation"])
    return record, settle_advice_record(record, case["settlement"])


def test_candidate_preflight_passes_without_generated_p03_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S13-P03"
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= FIXTURE["expected_preflight_minimum"]
    assert result["external_effect_boundary"] == CLAIM_BOUNDARY


@pytest.mark.parametrize("case_id", [item["case_id"] for item in FIXTURE["cases"]])
def test_frozen_cases_preserve_the_exact_expected_advice_and_result_states(case_id: str) -> None:
    case = _case(case_id)
    record, result = _record_and_result(case_id)
    assert record["advice_status"] == case["expected"]["advice_status"]
    assert result["result_status"] == case["expected"]["result_status"]
    assert result["synthetic_pnl_cents"] == case["expected"]["synthetic_pnl_cents"]
    assert result["relative_closing_line_advantage"] == case["expected"]["relative_closing_line_advantage"]
    assert result["actual_return_claimed"] is False
    assert result["actual_return_cents"] is None
    assert result["claim_boundary"] == CLAIM_BOUNDARY


def test_unconfirmed_advice_never_creates_a_settlement_or_actual_return_claim() -> None:
    record, result = _record_and_result("A01-UNCONFIRMED-ADVICE-ONLY")
    assert record["confirmation"]["confirmation_state"] == "NOT_CONFIRMED"
    assert result == settle_advice_record(record, _case("A01-UNCONFIRMED-ADVICE-ONLY")["settlement"])
    assert result["result_status"] == "UNCONFIRMED_DO_NOT_SETTLE_OR_CLAIM_ACTUAL_RETURN"
    assert result["synthetic_pnl_cents"] is None
    assert result["actual_return_claimed"] is False
    assert result["actual_return_cents"] is None


def test_explicit_owner_confirmation_is_not_account_reconciliation_or_real_return() -> None:
    record, result = _record_and_result("A02-CONFIRMED-AWAITING-SETTLEMENT")
    assert record["confirmation"]["confirmation_state"] == "OWNER_CONFIRMED_AWAITING_RECONCILIATION"
    assert record["actual_execution_status"] == "OWNER_CONFIRMED_NOT_ACCOUNT_RECONCILED"
    assert result["result_status"] == "OWNER_CONFIRMED_AWAITING_SETTLEMENT_EVIDENCE"
    assert result["actual_return_claimed"] is False
    assert result["actual_return_cents"] is None


def test_synthetic_settlement_records_result_and_clv_without_becoming_real_funds() -> None:
    record, result = _record_and_result("A03-CONFIRMED-SYNTHETIC-WIN")
    assert record["actual_return_claimed"] is False
    assert result["result_status"] == "SYNTHETIC_SETTLED_NOT_ACTUAL_RETURN"
    assert result["synthetic_pnl_cents"] == 270
    assert result["relative_closing_line_advantage"] == "0.047619047619"
    assert result["actual_return_claimed"] is False
    assert result["actual_return_cents"] is None


def test_point_0001_adverse_closing_variant_is_deterministic_and_non_actual() -> None:
    _, reference = _record_and_result("A03-CONFIRMED-SYNTHETIC-WIN")
    _, adverse = _record_and_result("A04-CONFIRMED-ADVERSE-POINT-0001-LOSS")
    _, favourable = _record_and_result("A05-CONFIRMED-FAVOURABLE-POINT-0001-VOID")
    assert adverse["relative_closing_line_advantage"] == "-0.000045452479"
    assert favourable["relative_closing_line_advantage"] == "0.000045456611"
    assert Decimal(str(reference["relative_closing_line_advantage"])) > Decimal(str(favourable["relative_closing_line_advantage"])) > Decimal("0") > Decimal(str(adverse["relative_closing_line_advantage"]))
    assert all(item["actual_return_claimed"] is False for item in (reference, adverse, favourable))


def test_replay_and_report_are_exactly_deterministic() -> None:
    payloads = []
    for _ in range(3):
        pairs = [_record_and_result(str(case["case_id"])) for case in FIXTURE["cases"]]
        report = build_performance_report([record for record, _ in pairs], [result for _, result in pairs])
        replay = {
            "case_results": [
                {
                    "case_id": case["case_id"],
                    "advice_status": record["advice_status"],
                    "result_status": result["result_status"],
                    "synthetic_pnl_cents": result["synthetic_pnl_cents"],
                    "relative_closing_line_advantage": result["relative_closing_line_advantage"],
                }
                for case, (record, result) in zip(FIXTURE["cases"], pairs)
            ],
            "report": report,
        }
        payloads.append((report, canonical_sha256(replay)))
    assert payloads == [payloads[0]] * 3
    report, replay_hash = payloads[0]
    assert replay_hash == FIXTURE["expected_replay_sha256"]
    assert report["synthetic_pnl_cents"] == FIXTURE["expected_synthetic_pnl_cents"]
    assert report["mean_relative_closing_line_advantage"] == FIXTURE["expected_mean_relative_closing_line_advantage"]
    assert report["actual_return_status"] == "DO_NOT_CLAIM_ACTUAL_RETURN_UNCONFIRMED_ADVICE"
    assert report["actual_return_claimed"] is False
    assert report["actual_return_cents"] is None


def test_binary_float_or_below_minimum_advice_fails_closed() -> None:
    invalid = deepcopy(_case("A01-UNCONFIRMED-ADVICE-ONLY")["advice"])
    invalid["recommended_odds"] = 2.2
    with pytest.raises(PostAdviceError):
        validate_advice(invalid)
    invalid = deepcopy(_case("A01-UNCONFIRMED-ADVICE-ONLY")["advice"])
    invalid["recommended_odds"] = "2.199999"
    with pytest.raises(PostAdviceError):
        make_advice_record(invalid)


def test_mismatched_confirmation_or_settlement_fails_closed() -> None:
    case = _case("A03-CONFIRMED-SYNTHETIC-WIN")
    bad_confirmation = deepcopy(case["confirmation"])
    bad_confirmation["advice_id"] = "S13-P03-ADVICE-0004"
    with pytest.raises(PostAdviceError):
        make_advice_record(case["advice"], bad_confirmation)
    record = make_advice_record(case["advice"], case["confirmation"])
    bad_settlement = deepcopy(case["settlement"])
    bad_settlement["advice_id"] = "S13-P03-ADVICE-0004"
    with pytest.raises(ResultSettlementError):
        settle_advice_record(record, bad_settlement)


def test_report_rejects_duplicate_advice_or_forged_actual_return() -> None:
    record, result = _record_and_result("A03-CONFIRMED-SYNTHETIC-WIN")
    with pytest.raises(PerformanceReportError):
        build_performance_report([record, record], [result])
    forged = deepcopy(result)
    forged["actual_return_claimed"] = True
    forged["actual_return_cents"] = 270
    forged["result_sha256"] = canonical_sha256({key: value for key, value in forged.items() if key != "result_sha256"})
    with pytest.raises(PerformanceReportError):
        build_performance_report([record], [forged])


def test_runtime_modules_have_no_network_soak_or_order_import_capability() -> None:
    prohibited = {"socket", "subprocess", "requests", "urllib", "http", "smtplib", "asyncio", "time", "random", "os"}
    for name in ("post_advice_worker.py", "result_settler.py", "performance_report.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not imports.intersection(prohibited)
        for token in ("sleep(", "submit_order", "retry_order", "http://", "https://", "webhook", "smtplib"):
            assert token not in source


def test_candidate_fails_closed_when_fixture_turns_unconfirmed_advice_into_a_confirmation(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    fixture_path = clone / "machine/tests/fixtures/S13_P03.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["cases"][0]["confirmation"] = deepcopy(fixture["cases"][1]["confirmation"])
    fixture["cases"][0]["confirmation"]["advice_id"] = fixture["cases"][0]["advice"]["advice_id"]
    fixture["cases"][0]["confirmation"]["confirmation_id"] = "S13-P03-CONFIRMATION-0001"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S13P03-FROZEN-CASE-RESULTS-EXACT" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_preserves_non_actual_boundary() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "evidence:post_advice_settlement_fail_closed"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["actual_return_claimed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_signing_replaces_only_the_p03_jsonl_row_and_replays(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    index_path = clone / "machine/evidence/evidence_index.jsonl"
    rows = index_path.read_text(encoding="utf-8").splitlines()
    planned_index = next(index for index, line in enumerate(rows) if json.loads(line).get("id") == "INDEX-AC-S13-P03")
    cases = "".join(
        '<testcase classname="tests.S13.P03_test" name="signer_fixture_%d" time="0.000" />' % index
        for index in range(18)
    )
    report_path = clone / "machine/evidence/S13/P03/pytest.xml"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('<?xml version="1.0" encoding="utf-8"?><testsuite tests="18" failures="0" errors="0" skipped="0">%s</testsuite>' % cases, encoding="utf-8")
    scan_path = clone / "machine/evidence/S13/P03/paid_dependency_scan.txt"
    scan_path.write_text(
        "STATUS: PASS\nMAX_INCREMENTAL_CASH_AUD: 0.00\nPAID_OR_UNKNOWN_DEPENDENCIES: 0\nEXTERNAL_NETWORK_ACCESS_PERFORMED: false\nEXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false\n",
        encoding="utf-8",
    )
    before = index_path.read_text(encoding="utf-8").splitlines()
    result = write_phase_evidence(clone, clone / "machine/evidence")
    after = index_path.read_text(encoding="utf-8").splitlines()
    changed = [index for index, (left, right) in enumerate(zip(before, after)) if left != right]
    assert result["status"] == "PASS"
    assert result["next"] == FIXTURE["expected_next"]
    assert changed == [planned_index]
    assert json.loads(after[planned_index])["kind"] == "PHASE_EVIDENCE"
    assert verify_existing_phase_evidence(clone)["status"] == "PASS"


def test_acceptance_cli_is_wired_to_the_exact_contract_after_integration() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S13-P03": write_post_advice_settlement_phase_evidence' in source
    assert '"AC-S13-P03": verify_post_advice_settlement_phase_evidence' in source
    with pytest.raises((PostAdviceSettlementAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
