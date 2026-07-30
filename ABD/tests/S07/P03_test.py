from __future__ import annotations

import ast
from copy import deepcopy
import json
import os
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.ledger_trace import (
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    LEDGER_PATH,
    ORACLE_PATH,
    P02_EVIDENCE_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    RECONCILIATION_ORACLE_PATH,
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
from abd_acceptance.temporal_lineage import verify_existing_phase_evidence as verify_p02_evidence
from ledger import (
    ACTUAL_FUNDS_LEDGER,
    ADVICE_LEDGER,
    GENESIS,
    LEDGER_VALID_NO_ADVICE,
    NO_ADVICE,
    LedgerValidationError,
    append_event,
    deterministic_ledger_hash,
    evaluate_ledgers,
    make_event,
    prepare_policy,
    strict_json_load as strict_ledger_json_load,
    validate_schema_document,
)
from reconciliation_oracle import deterministic_reconciliation_hash, reconcile_ledgers


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = strict_ledger_json_load(ROOT / SCHEMA_PATH)
FIXTURE = strict_ledger_json_load(ROOT / FIXTURE_PATH)
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


def _rehash(event: dict) -> dict:
    return make_event({key: value for key, value in event.items() if key != "event_sha256"})


def _assert_no_action(result: dict) -> None:
    assert result["status"] == NO_ADVICE
    assert result["actual_funds_changed"] is False
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


def test_taskpack_scope_trace_and_two_ledger_gate_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    requirement = next(item for item in requirements if item["id"] == "REQ-S07-P03")
    contracts = strict_json_load(ROOT / "machine/facts/acceptance_contracts.json")
    contract = next(item for item in contracts if item["id"] == CONTRACT_ID)
    graph = strict_json_load(ROOT / "machine/facts/task_graph.json")["tasks"]
    trace = strict_json_load(ROOT / "machine/facts/traceability_matrix.json")
    trace_row = next(item for item in trace if item["requirement_id"] == "REQ-S07-P03")
    tasks = [item for item in graph if item.get("stage_id") == "S07" and item.get("phase_id") == "P03"]
    assert requirement["scope"] == ["ledger.py", "ledger.schema.json", "reconciliation_oracle.py"]
    assert requirement["target"] == "无成交证据时真实资金账本不变化。"
    assert contract["pass_gate"] == requirement["target"]
    assert [row["id"] for row in contract["tests"]] == ["TEST-S07-P03", "TEST-S07-P03-BOUNDARY", "TEST-S07-P03-REPLAY"]
    assert [item["id"] for item in tasks] == ["T-S07-P03-01", "T-S07-P03-02", "T-S07-P03-03"]
    assert trace_row["artifact_ids"] == ["ART-S07-P03-01", "ART-S07-P03-02", "ART-S07-P03-03"]


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
    assert SCHEMA["x_abd_two_ledgers"] is True
    assert SCHEMA["x_abd_production_equivalent"] is True
    assert POLICY.parameter_version_sha256 == sha256_file(ROOT / "machine/facts/parameters.json")
    assert POLICY.opening_balance_cents == 30000
    assert POLICY.maximum_abs_cash_delta_cents == 30000


@pytest.mark.parametrize("case_id", [case["case_id"] for case in FIXTURE["cases"]])
def test_frozen_positive_boundary_negative_and_fault_cases_are_exact(case_id: str) -> None:
    case = _case(case_id)
    ledger_result = evaluate_ledgers(POLICY, case["advice_events"], case["actual_funds_events"])
    reconciliation = reconcile_ledgers(FIXTURE["policy"], case["advice_events"], case["actual_funds_events"])
    expected = case["expected"]
    assert ledger_result["status"] == expected["ledger_status"]
    assert reconciliation["status"] == expected["reconciliation_status"]
    assert ledger_result["recommendation_generated"] is False
    assert ledger_result["order_submission_enabled"] is False
    assert ledger_result["external_network_used"] is False
    assert ledger_result["real_time_soak_waited"] is False
    assert reconciliation["external_network_used"] is False
    assert reconciliation["real_time_soak_waited"] is False
    if "ledger_reason_code" in expected:
        assert expected["ledger_reason_code"] in ledger_result["reason_codes"]
    if "reconciliation_reason_code" in expected:
        assert expected["reconciliation_reason_code"] in reconciliation["reason_codes"]
    for field in ("actual_funds_balance_cents", "actual_funds_unchanged_without_execution_evidence", "execution_evidence_count"):
        if field in expected:
            assert ledger_result[field] == expected[field]
            assert reconciliation[field] == expected[field]


def test_no_execution_evidence_keeps_actual_funds_at_opening_balance() -> None:
    case = _case("NO_EXECUTION_EVIDENCE")
    ledger_result = evaluate_ledgers(POLICY, case["advice_events"], case["actual_funds_events"])
    reconciliation = reconcile_ledgers(FIXTURE["policy"], case["advice_events"], case["actual_funds_events"])
    assert ledger_result["status"] == LEDGER_VALID_NO_ADVICE
    assert ledger_result["actual_funds_event_count"] == 0
    assert ledger_result["execution_evidence_count"] == 0
    assert ledger_result["actual_funds_cash_delta_cents"] == 0
    assert ledger_result["actual_funds_balance_cents"] == POLICY.opening_balance_cents
    assert ledger_result["actual_funds_unchanged_without_execution_evidence"] is True
    assert reconciliation["actual_funds_unchanged_without_execution_evidence"] is True
    assert reconciliation["reconciliation_difference_cents"] == 0
    assert ledger_result["output_sha256"] == FIXTURE["expected_no_execution_output_sha256"]


def test_verified_frozen_fixture_is_explicitly_synthetic_and_reconciled() -> None:
    case = _case("VERIFIED_FROZEN_EXECUTION_EVIDENCE")
    ledger_result = evaluate_ledgers(POLICY, case["advice_events"], case["actual_funds_events"])
    reconciliation = reconcile_ledgers(FIXTURE["policy"], case["advice_events"], case["actual_funds_events"])
    assert case["actual_funds_events"][0]["payload"]["fixture_only"] is True
    assert case["actual_funds_events"][0]["payload"]["execution_evidence_kind"] == "FROZEN_TEST_FIXTURE"
    assert ledger_result["status"] == LEDGER_VALID_NO_ADVICE
    assert ledger_result["actual_funds_balance_cents"] == 30150
    assert ledger_result["actual_funds_unchanged_without_execution_evidence"] is False
    assert ledger_result["output_sha256"] == FIXTURE["expected_verified_execution_output_sha256"]
    assert reconciliation["status"] == "RECONCILED"
    assert reconciliation["reconciliation_difference_cents"] == 0


def test_append_is_hash_chained_and_idempotent_without_mutating_actual_ledger() -> None:
    advice = deepcopy(_case("NO_EXECUTION_EVIDENCE")["advice_events"][0])
    appended = append_event(POLICY, ADVICE_LEDGER, [], advice)
    assert appended["status"] == "APPENDED"
    assert appended["appended"] is True
    assert appended["ledger"]["chain_head_sha256"] == advice["event_sha256"]
    replay = append_event(POLICY, ADVICE_LEDGER, appended["events"], advice)
    assert replay["status"] == "IDEMPOTENT_REPLAY"
    assert replay["appended"] is False
    conflict = deepcopy(advice)
    conflict["event_id"] = "LED-ADVICE-0002"
    conflict = _rehash(conflict)
    result = append_event(POLICY, ADVICE_LEDGER, appended["events"], conflict)
    assert result["status"] == "IDEMPOTENCY_CONFLICT"
    assert result["appended"] is False
    assert append_event(POLICY, ACTUAL_FUNDS_LEDGER, [], deepcopy(_case("VERIFIED_FROZEN_EXECUTION_EVIDENCE")["actual_funds_events"][0]))["status"] == "APPENDED"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (
            lambda advice, actual: advice[0]["payload"].__setitem__("adverse_probability_delta", "-0.0001"),
            "ADVERSE_PROBABILITY_BOUNDARY_INVALID",
        ),
        (
            lambda advice, actual: advice[0]["payload"].__setitem__("adverse_odds_tick", "0.0002"),
            "ADVERSE_ODDS_BOUNDARY_INVALID",
        ),
        (
            lambda advice, actual: actual[0]["payload"].__setitem__("execution_evidence_verified", False),
            "EXECUTION_EVIDENCE_REQUIRED",
        ),
        (
            lambda advice, actual: actual[0]["payload"].__setitem__("advice_event_sha256", "f" * 64),
            "ACTUAL_EVENT_WITHOUT_ADVICE_PROVENANCE",
        ),
        (
            lambda advice, actual: actual[0].__setitem__("previous_event_sha256", "f" * 64),
            "HASH_CHAIN_BROKEN",
        ),
        (
            lambda advice, actual: advice[0]["payload"].__setitem__("recommended_stake_cents", 1),
            "STAKE_MUST_BE_ZERO",
        ),
    ],
)
def test_semantic_faults_fail_closed_before_any_funds_change(mutation, reason_code: str) -> None:
    positive = _case("VERIFIED_FROZEN_EXECUTION_EVIDENCE")
    advice = deepcopy(positive["advice_events"])
    actual = deepcopy(positive["actual_funds_events"])
    mutation(advice, actual)
    advice[0] = _rehash(advice[0])
    actual[0] = _rehash(actual[0])
    ledger_result = evaluate_ledgers(POLICY, advice, actual)
    _assert_no_action(ledger_result)
    assert reason_code in ledger_result["reason_codes"]
    reconciliation = reconcile_ledgers(FIXTURE["policy"], advice, actual)
    assert reconciliation["status"] == "RECONCILIATION_REJECTED"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (lambda advice, actual: advice[0].__setitem__("unknown", "x"), "UNKNOWN_FIELD"),
        (lambda advice, actual: advice[0]["payload"].__setitem__("recommended_stake_cents", 0.0), "BINARY_FLOAT_NOT_ALLOWED"),
        (lambda advice, actual: advice[0].pop("payload"), "MISSING_FIELD"),
        (lambda advice, actual: advice[0].__setitem__("recorded_at", "2026-07-30T00:00:00"), "TIMEZONE_REQUIRED"),
        (lambda advice, actual: actual[0]["payload"].__setitem__("actual_cash_delta_cents", 30001), "CASH_DELTA_INVALID"),
    ],
)
def test_unknown_float_missing_timezone_and_cash_limit_fail_closed(mutation, reason_code: str) -> None:
    positive = _case("VERIFIED_FROZEN_EXECUTION_EVIDENCE")
    advice = deepcopy(positive["advice_events"])
    actual = deepcopy(positive["actual_funds_events"])
    mutation(advice, actual)
    if "payload" in advice[0] and not isinstance(advice[0]["payload"].get("recommended_stake_cents"), float):
        advice[0] = _rehash(advice[0])
    if not isinstance(actual[0]["payload"].get("actual_cash_delta_cents"), float):
        actual[0] = _rehash(actual[0])
    result = evaluate_ledgers(POLICY, advice, actual)
    _assert_no_action(result)
    assert reason_code in result["reason_codes"]


def test_policy_and_schema_mutations_are_rejected_before_any_result() -> None:
    bad_policy = deepcopy(FIXTURE["policy"])
    bad_policy["opening_balance_cents"] = 0
    with pytest.raises(LedgerValidationError) as policy_error:
        prepare_policy(SCHEMA, bad_policy)
    assert policy_error.value.code == "OPENING_BALANCE_INVALID"
    bad_schema = deepcopy(SCHEMA)
    bad_schema["x_abd_two_ledgers"] = False
    with pytest.raises(LedgerValidationError) as schema_error:
        validate_schema_document(bad_schema)
    assert schema_error.value.code == "SCHEMA_INVALID"


def test_strict_loader_rejects_duplicate_keys_and_binary_floats(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(LedgerValidationError) as duplicate_error:
        strict_ledger_json_load(duplicate)
    assert duplicate_error.value.code == "DUPLICATE_JSON_KEY"
    binary_float = tmp_path / "float.json"
    binary_float.write_text('{"a":0.1}', encoding="utf-8")
    with pytest.raises(LedgerValidationError) as float_error:
        strict_ledger_json_load(binary_float)
    assert float_error.value.code == "BINARY_FLOAT_NOT_ALLOWED"


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    case = _case("NO_EXECUTION_EVIDENCE")
    expected = deterministic_ledger_hash(POLICY, case["advice_events"], case["actual_funds_events"])
    ledger_hashes = {
        deterministic_ledger_hash(
            POLICY,
            [{key: event[key] for key in reversed(list(event))} for event in case["advice_events"]],
            [],
        )
        for _ in range(FIXTURE["replay_count"])
    }
    reconciliation_hashes = {
        deterministic_reconciliation_hash(
            FIXTURE["policy"],
            [{key: event[key] for key in reversed(list(event))} for event in case["advice_events"]],
            [],
        )
        for _ in range(FIXTURE["replay_count"])
    }
    assert ledger_hashes == {expected} == {FIXTURE["expected_no_execution_output_sha256"]}
    assert len(reconciliation_hashes) == 1


def test_ten_thousand_adverse_perturbations_never_change_funds_or_enable_orders() -> None:
    positive = _case("VERIFIED_FROZEN_EXECUTION_EVIDENCE")
    base_advice = positive["advice_events"]
    base_actual = positive["actual_funds_events"]
    for index in range(FIXTURE["adverse_replay_count"]):
        advice = deepcopy(base_advice)
        actual = deepcopy(base_actual)
        mode = index % 5
        if mode == 0:
            advice[0]["payload"]["adverse_probability_delta"] = "-0.0001"
            advice[0] = _rehash(advice[0])
        elif mode == 1:
            advice[0]["payload"]["adverse_odds_tick"] = "0.0002"
            advice[0] = _rehash(advice[0])
        elif mode == 2:
            actual[0]["payload"]["execution_evidence_verified"] = False
            actual[0] = _rehash(actual[0])
        elif mode == 3:
            actual[0]["payload"]["advice_event_sha256"] = "f" * 64
            actual[0] = _rehash(actual[0])
        else:
            actual[0]["previous_event_sha256"] = "f" * 64
            actual[0] = _rehash(actual[0])
        _assert_no_action(evaluate_ledgers(POLICY, advice, actual))
        assert reconcile_ledgers(FIXTURE["policy"], advice, actual)["status"] == "RECONCILIATION_REJECTED"


@pytest.mark.parametrize("relative", [LEDGER_PATH, RECONCILIATION_ORACLE_PATH])
def test_core_sources_have_no_network_process_scheduler_or_sleep_capability(relative: Path) -> None:
    source = (ROOT / relative).read_text(encoding="utf-8")
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
    assert result["real_account_balance_read_or_written"] is False
    assert result["real_time_soak_waited"] is False


def test_candidate_fails_closed_when_phase_artifact_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    payload = strict_ledger_json_load(root / FIXTURE_PATH)
    payload["policy"]["opening_balance_cents"] = 1
    _write_json(root / FIXTURE_PATH, payload)
    checks: list[dict] = []
    _check_pins(root, checks, {})
    assert next(check for check in checks if check["id"] == "S07P03-PIN-S07_P03-JSON")["passed"] is False


def test_candidate_fails_closed_when_p02_predecessor_receipt_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    payload = strict_json_load(root / P02_EVIDENCE_PATH)
    payload["status"] = "FAIL"
    _write_json(root / P02_EVIDENCE_PATH, payload)
    preflight = validate_candidate_preflight(root)
    assert preflight["status"] == "FAIL"
    assert "S07P03-P02-PREDECESSOR-PASS" in preflight["summary"]["failed_check_ids"]


def test_generated_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(root, FIXTURE, checks, require_test_reports=True)
    assert next(check for check in checks if check["id"] == "S07P03-TARGETED-PYTEST-REPORT")["passed"] is False
    assert next(check for check in checks if check["id"] == "S07P03-FULL-PYTEST-REPORT")["passed"] is False


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
    assert '"AC-S07-P03": write_ledger_trace_phase_evidence' in source
    assert "from .ledger_trace import write_phase_evidence as write_ledger_trace_phase_evidence" in source


def test_candidate_evidence_carries_dual_ledger_and_structured_failure_summary() -> None:
    evidence, rollback = build_evidence(ROOT)
    assert evidence["status"] == "PASS", evidence["validation"]
    assert evidence["ledger_summary"]["no_execution_balance_cents"] == 30000
    assert evidence["ledger_summary"]["no_execution_unchanged"] is True
    assert evidence["ledger_summary"]["verified_fixture_only"] is True
    assert evidence["ledger_summary"]["recommendation_generated"] is False
    assert evidence["ledger_summary"]["order_submission_enabled"] is False
    assert evidence["reconciliation_summary"]["no_execution_difference_cents"] == 0
    assert evidence["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert evidence["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert evidence["structured_failure_log"]["case_reason_codes"]["NEGATIVE_EXECUTION_EVIDENCE_UNVERIFIED"]
    assert rollback["status"] == "PASS"


def test_p02_predecessor_receipt_remains_independently_verifiable() -> None:
    result = verify_p02_evidence(ROOT)
    assert result["status"] == "PASS", result


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        result = verify_existing_phase_evidence(ROOT)
        assert result["status"] == "PASS", result
    else:
        assert not (ROOT / EVIDENCE_PATH).is_file()
        assert not (ROOT / ROLLBACK_EVIDENCE_PATH).is_file()
