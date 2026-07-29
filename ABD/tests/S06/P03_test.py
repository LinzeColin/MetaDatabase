from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import pytest

from attachment_sandbox import load_policy, sandbox_plan, scan_attachment, scan_attachments
from abd_acceptance.attachment_security import (
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    ORACLE_PATH,
    PINNED_PHASE_HASHES,
    REGISTRY_PATH,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    RULES_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    _junit_is_normalized,
    _junit_summary,
    _structural_self_hash,
    build_evidence as _build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.mail_preservation import verify_existing_phase_evidence as verify_p02_evidence


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(root, require_external_reports, _verify_git_history=Path(root).resolve() == ROOT.resolve())


def build_evidence(root: Path, require_external_reports: bool = False):
    return _build_evidence(root, require_external_reports, _verify_git_history=Path(root).resolve() == ROOT.resolve())


def verify_existing_phase_evidence(root: Path):
    return _verify_existing_phase_evidence(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"))
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _failed(result: dict, check_id: str | None = None) -> None:
    assert result["status"] == "FAIL", result
    if check_id is not None:
        assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _record(case: dict) -> dict:
    return {
        "attachment_id": case["attachment_id"],
        "filename": case["filename"],
        "content": base64.b64decode(case["content_base64"], validate=True),
    }


def _cases() -> list[dict]:
    return list(FIXTURE["cases"])


def _case(case_id: str) -> dict:
    return next(row for row in _cases() if row["id"] == case_id)


def _scan(case: dict, root: Path = ROOT) -> dict:
    return scan_attachment(_record(case), parser_registry_path=root / REGISTRY_PATH, quarantine_rules_path=root / RULES_PATH)


def test_candidate_preflight_and_contract_pass_without_external_reports() -> None:
    preflight = validate_candidate_preflight(ROOT)
    result = evaluate_contract(ROOT)
    assert preflight["status"] == "PASS", preflight
    assert preflight["next"] == FIXTURE["expected_next"]
    assert result["status"] == "PASS", result
    assert result["decision"] == "ATTACHMENTS_PARSED_OR_QUARANTINED_KEEP_ONLY"
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["external_network_used_by_verifier"] is False


def test_taskpack_identity_scope_gate_and_trace_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    requirement = next(item for item in requirements if item["id"] == "REQ-S06-P03")
    contracts = strict_json_load(ROOT / "machine/facts/acceptance_contracts.json")
    contract = next(item for item in contracts if item["id"] == CONTRACT_ID)
    trace = strict_json_load(ROOT / "machine/facts/traceability_matrix.json")
    trace_row = next(item for item in trace if item["requirement_id"] == "REQ-S06-P03")
    assert requirement["scope"] == ["attachment_sandbox.py", "parser_registry.json", "quarantine_rules.json"]
    assert requirement["target"] == "恶意、宏、脚本、公式注入或未知类型全部隔离。"
    assert contract["pass_gate"] == requirement["target"]
    assert [row["id"] for row in contract["tests"]] == ["TEST-S06-P03", "TEST-S06-P03-BOUNDARY", "TEST-S06-P03-REPLAY"]
    assert trace_row["evidence_id"] == "EVD-S06-P03"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_policy_is_bound_to_machine_facts_and_no_execution_mode() -> None:
    policy = load_policy(parser_registry_path=ROOT / REGISTRY_PATH, quarantine_rules_path=ROOT / RULES_PATH)
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")["email"]
    plan = sandbox_plan(policy=policy)
    assert policy["runtime"]["attachment_max_bytes"] == parameters["max_attachment_bytes"] == 50_000_000
    assert policy["runtime"]["cpu_budget_seconds"] == parameters["parser_sandbox_cpu_seconds"] == 60
    assert policy["runtime"]["memory_budget_mb"] == parameters["parser_sandbox_memory_mb"] == 256
    assert set(policy["profiles_by_extension"]) == {"csv", "pdf", "xlsx", "docx", "pptx"}
    assert policy["rules"]["permanent_delete"] is False
    assert policy["rules"]["mail_content_instruction_trust"] == "NONE"
    assert plan["external_network_accessed"] is False
    assert plan["attachment_execution_performed"] is False
    assert plan["zip_extracted_to_disk"] is False
    assert plan["real_time_soak_waited"] is False
    assert plan["malware_clearance_claimed"] is False


@pytest.mark.parametrize("case", _cases(), ids=lambda row: row["id"])
def test_frozen_case_actions_are_exact_and_fail_closed(case: dict) -> None:
    result = _scan(case)
    assert result["status"] == case["expected_status"]
    if case["expected_reason"] is None:
        assert result["reason_codes"] == []
        assert result["quarantined"] is False
    else:
        assert case["expected_reason"] in result["reason_codes"]
        assert result["quarantined"] is True
    assert result["trash_eligible"] is False
    assert result["gmail_mutation_performed"] is False
    assert result["permanent_delete_performed"] is False
    assert result["sandbox"]["external_network_accessed"] is False
    assert result["sandbox"]["attachment_execution_performed"] is False
    assert result["sandbox"]["real_time_soak_waited"] is False
    assert "content" not in result


@pytest.mark.parametrize(
    "case_id,reason",
    [
        ("MALWARE_MARKER", "MALWARE_MARKER_QUARANTINE"),
        ("MACRO_OFFICE", "MACRO_OR_ACTIVE_OFFICE_ENTRY_QUARANTINE"),
        ("SCRIPT_PDF", "PDF_ACTIVE_CONTENT_QUARANTINE"),
        ("FORMULA_CSV", "FORMULA_INJECTION_QUARANTINE"),
        ("PROMPT_INJECTION", "PROMPT_INJECTION_QUARANTINE"),
        ("UNKNOWN_TYPE", "UNKNOWN_TYPE_QUARANTINE"),
        ("TYPE_MISMATCH", "TYPE_SIGNATURE_MISMATCH_QUARANTINE"),
        ("PATH_TRAVERSAL", "PATH_TRAVERSAL_QUARANTINE"),
        ("DANGEROUS_EXTENSION", "DANGEROUS_EXTENSION_QUARANTINE"),
        ("MALFORMED_OFFICE", "OFFICE_PARSE_FAILURE_QUARANTINE"),
    ],
)
def test_each_required_threat_has_its_required_isolation_reason(case_id: str, reason: str) -> None:
    result = _scan(_case(case_id))
    assert result["status"] == "QUARANTINED_KEEP"
    assert reason in result["reason_codes"]
    assert result["malware_scan_result"] == "NOT_CLEARED_STATIC_INSPECTION_ONLY"


def test_batch_order_and_one_hundred_replay_are_deterministic_without_wait() -> None:
    values = [_record(case) for case in _cases()]
    results = scan_attachments(values, parser_registry_path=ROOT / REGISTRY_PATH, quarantine_rules_path=ROOT / RULES_PATH)
    first = _scan(_case("SAFE_CSV"))
    repeats = [_scan(_case("SAFE_CSV")) for _ in range(FIXTURE["replay_iterations"])]
    assert [result["attachment_id"] for result in results] == [value["attachment_id"] for value in values]
    assert all("content" not in result and result["trash_eligible"] is False for result in results)
    assert len(repeats) == 100
    assert all(result == first and result["sandbox"]["real_time_soak_waited"] is False for result in repeats)


def test_one_in_ten_thousand_adverse_perturbations_stay_quarantined_without_soak() -> None:
    first = _scan(_case("FORMULA_CSV"))
    repeats = [_scan(_case("FORMULA_CSV")) for _ in range(FIXTURE["adverse_perturbation_iterations"])]
    assert len(repeats) == 10_000
    assert all(result == first for result in repeats)
    assert first["status"] == "QUARANTINED_KEEP"
    assert "FORMULA_INJECTION_QUARANTINE" in first["reason_codes"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"attachment_id": "bad id", "filename": "a.csv", "content": b"a,b\n"},
        {"attachment_id": "ATTINVALID", "filename": "../a.csv", "content": b"a,b\n"},
        {"attachment_id": "ATTINVALID", "filename": "a.csv", "content": b""},
        {"attachment_id": "ATTINVALID", "filename": "a.csv", "content": "not bytes"},
    ],
)
def test_malformed_inputs_are_converted_to_keep_quarantine(value) -> None:
    result = scan_attachment(value, parser_registry_path=ROOT / REGISTRY_PATH, quarantine_rules_path=ROOT / RULES_PATH)
    assert result["status"] == "QUARANTINED_KEEP"
    assert result["reason_codes"] == ["INPUT_INVALID_QUARANTINE"]
    assert result["trash_eligible"] is False


def test_scaled_attachment_size_boundary_is_exact_and_overflow_is_isolated(tmp_path: Path) -> None:
    registry = strict_json_load(ROOT / REGISTRY_PATH)
    registry["runtime"]["attachment_max_bytes"] = FIXTURE["scaled_attachment_boundary_bytes"]
    registry["runtime"]["max_zip_uncompressed_bytes"] = FIXTURE["scaled_attachment_boundary_bytes"]
    registry_path = tmp_path / "parser_registry.json"
    rules_path = tmp_path / "quarantine_rules.json"
    _write_json(registry_path, registry)
    _write_json(rules_path, strict_json_load(ROOT / RULES_PATH))
    at_limit = scan_attachment(
        {"attachment_id": "ATTLIMIT", "filename": "limit.csv", "content": b"a,b\n"},
        parser_registry_path=registry_path,
        quarantine_rules_path=rules_path,
    )
    over_limit = scan_attachment(
        {"attachment_id": "ATTOVER", "filename": "over.csv", "content": b"a,b\nx"},
        parser_registry_path=registry_path,
        quarantine_rules_path=rules_path,
    )
    assert at_limit["status"] == "PARSED_SAFE"
    assert over_limit["status"] == "QUARANTINED_KEEP"
    assert over_limit["reason_codes"] == ["ATTACHMENT_SIZE_EXCEEDED_QUARANTINE"]


@pytest.mark.parametrize(
    "relative,mutate",
    [
        ("parser_registry.json", lambda value: value["runtime"].__setitem__("external_network_access", True)),
        ("parser_registry.json", lambda value: value["runtime"].__setitem__("attachment_max_bytes", 49_999_999)),
        ("quarantine_rules.json", lambda value: value.__setitem__("permanent_delete", True)),
        ("quarantine_rules.json", lambda value: value.__setitem__("mail_content_instruction_trust", "ANY")),
        ("machine/tests/fixtures/S06_P03.json", lambda value: value.__setitem__("expected_next", "S06/P05_READY_NOT_STARTED")),
    ],
)
def test_policy_and_fixture_mutations_fail_closed(tmp_path: Path, relative: str, mutate) -> None:
    root = _clone_project(tmp_path)
    path = root / relative
    value = strict_json_load(path)
    mutate(value)
    _write_json(path, value)
    _failed(evaluate_contract(root))


def test_missing_policy_is_quarantined_not_treated_as_a_pass(tmp_path: Path) -> None:
    result = scan_attachment(
        _record(_case("SAFE_CSV")),
        parser_registry_path=tmp_path / "missing.json",
        quarantine_rules_path=ROOT / RULES_PATH,
    )
    assert result["status"] == "QUARANTINED_KEEP"
    assert result["reason_codes"] == ["POLICY_INVALID_QUARANTINE"]
    assert result["sandbox"]["external_network_accessed"] is False


def test_p02_signed_evidence_is_the_only_phase_prerequisite() -> None:
    result = verify_p02_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["next"] == "S06/P03_READY_NOT_STARTED"


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["deterministic_replay"]["iterations"] == 10_000
    assert first["deterministic_replay"]["all_equal"] is True
    assert first["no_real_time_soak"]["real_time_soak_waited"] is False
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered


def test_rollback_drill_preserves_phase_artifacts_without_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["real_time_soak_waited"] is False


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    _failed(evaluate_contract(root, require_external_reports=True), "S06P03-TARGETED-PYTEST-REPORT")


def test_junit_normalization_accepts_only_fixed_metadata(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" timestamp="%s" time="0.000"><testcase name="offline" time="0.000" /></testsuite></testsuites>' % JUNIT_FIXED_CLOCK,
        encoding="utf-8",
    )
    assert _junit_is_normalized(report) is True
    assert _junit_summary(report)["tests"] == 1
    report.write_text(report.read_text(encoding="utf-8").replace('time="0.000"', 'time="0.001"', 1), encoding="utf-8")
    assert _junit_is_normalized(report) is False


def test_oracle_cli_is_wired_to_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S06-P03": write_attachment_security_phase_evidence' in source
    assert "from .attachment_security import write_phase_evidence as write_attachment_security_phase_evidence" in source


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
    else:
        assert result["status"] == "FAIL"


def test_external_effect_and_canonical_financial_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    assert EXTERNAL_EFFECT_BOUNDARY["gmail_mutation_performed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["attachment_executed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["os_sandbox_process_started"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert canonical["email"]["permanent_delete"] is False
