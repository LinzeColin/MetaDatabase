from __future__ import annotations

from copy import deepcopy
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.attachment_security import verify_existing_phase_evidence as verify_p03_evidence
from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.mail_deletion_audit import (
    AUDIT_PATH,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    ORACLE_PATH,
    PINNED_PHASE_HASHES,
    RESTORE_PATH,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    WORKER_PATH,
    _fixture_mail_record,
    _junit_is_normalized,
    _junit_summary,
    _private_roots,
    _security_inputs,
    _structural_self_hash,
    build_evidence as _build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)
from mail_collector import ARCHIVE_DIRECTORY_NAME, preserve_mail
from mail_trash_worker import (
    PERMANENT_DELETE_CAPABILITY,
    REAL_TIME_SOAK_REQUIRED,
    SCHEDULED_AUDIT_LOCAL_TIME,
    assess_trash_candidate,
    audit_daily_mail_state,
    dispatch_trash_request,
    prepare_restore_request,
    validate_no_real_time_soak,
)


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


def _prepared(tmp_path: Path) -> dict:
    record = _fixture_mail_record(ROOT, FIXTURE)
    archive_root, repository_root = _private_roots(tmp_path)
    preserved = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
    assert preserved["status"] == "PRESERVED_READBACK_VERIFIED"
    security, attestations = _security_inputs(ROOT, record)
    decision = assess_trash_candidate(
        archive_root=archive_root,
        repository_root=repository_root,
        gmail_message_id=record["gmail_message_id"],
        sender_state=FIXTURE["sender_state"],
        authentication_state=FIXTURE["authentication_state"],
        attachment_security_results=security,
        malware_attestations=attestations,
    )
    return {
        "record": record,
        "archive_root": archive_root,
        "repository_root": repository_root,
        "preserved": preserved,
        "security": security,
        "attestations": attestations,
        "decision": decision,
    }


def _decision(value: dict, *, sender_state: str = "KNOWN_ALLOWLISTED", authentication_state: str = "PASS", security=None, attestations=None) -> dict:
    return assess_trash_candidate(
        archive_root=value["archive_root"],
        repository_root=value["repository_root"],
        gmail_message_id=value["record"]["gmail_message_id"],
        sender_state=sender_state,
        authentication_state=authentication_state,
        attachment_security_results=value["security"] if security is None else security,
        malware_attestations=value["attestations"] if attestations is None else attestations,
    )


def test_candidate_preflight_and_contract_pass_without_external_reports() -> None:
    preflight = validate_candidate_preflight(ROOT)
    result = evaluate_contract(ROOT)
    assert preflight["status"] == "PASS", preflight
    assert preflight["next"] == FIXTURE["expected_next"]
    assert result["status"] == "PASS", result
    assert result["decision"] == "TRASH_REQUEST_ONLY_AFTER_ALL_GATES_NO_PERMANENT_DELETE"
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["external_network_used_by_verifier"] is False


def test_taskpack_identity_scope_gate_and_trace_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    requirement = next(item for item in requirements if item["id"] == "REQ-S06-P04")
    contracts = strict_json_load(ROOT / "machine/facts/acceptance_contracts.json")
    contract = next(item for item in contracts if item["id"] == CONTRACT_ID)
    trace = strict_json_load(ROOT / "machine/facts/traceability_matrix.json")
    trace_row = next(item for item in trace if item["requirement_id"] == "REQ-S06-P04")
    assert requirement["scope"] == ["mail_trash_worker.py", "codex_daily_audit.md", "mail_restore_runbook.md"]
    assert requirement["target"] == "未知发件人或验证失败不删除；永久删除能力不存在。"
    assert contract["pass_gate"] == requirement["target"]
    assert [row["id"] for row in contract["tests"]] == ["TEST-S06-P04", "TEST-S06-P04-BOUNDARY", "TEST-S06-P04-REPLAY"]
    assert trace_row["evidence_id"] == "EVD-S06-P04"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_machine_facts_and_document_contracts_are_bound_to_the_worker() -> None:
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")["email"]
    ingestion = strict_json_load(ROOT / "machine/facts/email_ingestion.json")
    audit_text = (ROOT / AUDIT_PATH).read_text(encoding="utf-8")
    restore_text = (ROOT / RESTORE_PATH).read_text(encoding="utf-8")
    assert parameters["daily_codex_audit_local_time"] == SCHEDULED_AUDIT_LOCAL_TIME == "06:00"
    assert parameters["malware_scan_required"] is True
    assert parameters["permanent_delete"] is False
    assert parameters["unknown_sender"] == "QUARANTINE"
    assert ingestion["trash_gate"]["permanent_delete"] is False
    assert ingestion["trash_gate"]["unknown_sender"] == "KEEP"
    assert "DATA_ONLY_NO_SCHEDULER_OR_WAIT" in audit_text
    assert "REQUEST_ONLY_NO_MUTATION" in restore_text
    assert PERMANENT_DELETE_CAPABILITY is False


def test_all_required_gates_make_only_a_non_mutating_trash_request(tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    decision = values["decision"]
    dispatch = dispatch_trash_request(decision)
    receipt = {
        "status": "TRASHED",
        "gmail_message_id": decision["gmail_message_id"],
        "trash_request_key": decision["trash_request_key"],
    }
    restore = prepare_restore_request(
        archive_root=values["archive_root"],
        repository_root=values["repository_root"],
        gmail_message_id=values["record"]["gmail_message_id"],
        trash_request_key=decision["trash_request_key"],
        trash_receipt=receipt,
    )
    assert decision["status"] == "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"
    assert decision["gate_report"]["archive_readback_passed"] is True
    assert decision["gate_report"]["parser_result_recorded_and_safe"] is True
    assert decision["gate_report"]["malware_scan_passed"] is True
    assert dispatch["status"] == "TRASH_REQUEST_READY_NO_MUTATION"
    assert dispatch["gmail_mutation_performed"] is False
    assert restore["status"] == "RESTORE_REQUEST_READY_NO_MUTATION"
    assert restore["gmail_mutation_performed"] is False
    assert decision["permanent_delete_capability"] is False
    assert decision["permanent_delete_performed"] is False


@pytest.mark.parametrize("sender_state", ["UNKNOWN", "KNOWN_UNVERIFIED", "INVALID"])
def test_unknown_or_unverified_sender_never_becomes_trash_eligible(sender_state: str, tmp_path: Path) -> None:
    result = _decision(_prepared(tmp_path), sender_state=sender_state)
    assert result["status"] == "KEEP_AND_QUARANTINE"
    assert result["trash_eligible"] is False
    assert result["gmail_mutation_performed"] is False
    assert result["permanent_delete_performed"] is False


@pytest.mark.parametrize("authentication_state", ["FAIL", "UNKNOWN", "INVALID"])
def test_failed_or_unknown_authentication_never_becomes_trash_eligible(authentication_state: str, tmp_path: Path) -> None:
    result = _decision(_prepared(tmp_path), authentication_state=authentication_state)
    assert result["status"] == "KEEP_AND_QUARANTINE"
    assert result["trash_eligible"] is False
    assert result["gmail_mutation_performed"] is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.clear(),
        lambda value: value[0].__setitem__("status", "FAIL"),
        lambda value: value[0].__setitem__("content_sha256", "0" * 64),
        lambda value: value.append(deepcopy(value[0])),
        lambda value: value.__setitem__(0, {"attachment_id": "ATTX", "content_sha256": "0" * 64, "status": "PASS", "extra": True}),
    ],
)
def test_missing_failed_or_mismatched_malware_attestation_keeps(mutator, tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    attestations = deepcopy(values["attestations"])
    mutator(attestations)
    result = _decision(values, attestations=attestations)
    assert result["status"] == "KEEP_AND_QUARANTINE"
    assert result["trash_eligible"] is False
    assert result["gate_report"]["malware_scan_passed"] is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value[0].update({"status": "QUARANTINED_KEEP", "quarantined": True}),
        lambda value: value[0].__setitem__("content_sha256", "0" * 64),
        lambda value: value.pop(),
        lambda value: value[0].__setitem__("extra", True),
    ],
)
def test_parser_quarantine_or_incomplete_results_keep(mutator, tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    security = deepcopy(values["security"])
    mutator(security)
    result = _decision(values, security=security)
    assert result["status"] == "KEEP_AND_QUARANTINE"
    assert result["trash_eligible"] is False
    assert result["gate_report"]["parser_result_recorded_and_safe"] is False


@pytest.mark.parametrize("relative", ["raw.eml", "manifest.json", "attachments/ATTCSVSAFE.bin"])
def test_missing_or_tampered_archive_never_becomes_trash_eligible(relative: str, tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    target = values["archive_root"] / ARCHIVE_DIRECTORY_NAME / "records" / values["record"]["gmail_message_id"] / relative
    if relative == "manifest.json":
        target.write_text("{}\n", encoding="utf-8")
    else:
        target.unlink()
    result = _decision(values)
    assert result["status"] == "KEEP_AND_QUARANTINE"
    assert result["trash_eligible"] is False
    assert result["gate_report"]["archive_readback_passed"] is False


def test_dispatch_is_idempotent_and_never_invokes_an_unconfigured_adapter(tmp_path: Path) -> None:
    decision = _prepared(tmp_path)["decision"]
    already = dispatch_trash_request(decision, completed_request_keys=[decision["trash_request_key"]])
    unconfigured = dispatch_trash_request(decision, allow_external_mutation=True, runtime_adapter=None)
    invalid = dispatch_trash_request({"status": "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"})
    assert already["status"] == "IDEMPOTENT_ALREADY_DISPATCHED"
    assert unconfigured["status"] == "TRASH_REQUEST_READY_NO_MUTATION"
    assert invalid["status"] == "KEEP_NOT_DISPATCHED"
    assert all(row["gmail_mutation_performed"] is False for row in (already, unconfigured, invalid))
    assert all(row["permanent_delete_performed"] is False for row in (already, unconfigured, invalid))


@pytest.mark.parametrize(
    "kind",
    ["pass", "keep", "duplicate", "invalid", "off_schedule"],
)
def test_daily_audit_is_data_only_and_escalates_gaps(kind: str, tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    decision = values["decision"]
    if kind == "pass":
        result = audit_daily_mail_state([decision], observed_local_time="06:00")
        expected = ("AUDIT_PASS", "NONE")
    elif kind == "keep":
        result = audit_daily_mail_state([_decision(values, sender_state="UNKNOWN")], observed_local_time="06:00")
        expected = ("AUDIT_REMEDIATION_REQUIRED", "ESCALATE")
    elif kind == "duplicate":
        duplicate = deepcopy(decision)
        duplicate["gmail_message_id"] = "MSG0002"
        result = audit_daily_mail_state([decision, duplicate], observed_local_time="06:00")
        expected = ("AUDIT_REMEDIATION_REQUIRED", "ESCALATE")
    elif kind == "invalid":
        result = audit_daily_mail_state([{}], observed_local_time="06:00")
        expected = ("AUDIT_REMEDIATION_REQUIRED", "ESCALATE")
    else:
        result = audit_daily_mail_state([decision], observed_local_time="05:59")
        expected = ("AUDIT_OFF_SCHEDULE", "ESCALATE")
    assert (result["status"], result["action"]) == expected
    assert result["real_time_waited"] is False
    assert result["scheduler_started"] is False
    assert result.get("gmail_mutation_performed", False) is False


@pytest.mark.parametrize("receipt_kind", ["matching", "missing", "mismatched"])
def test_restore_requires_matching_receipt_and_archive_readback(receipt_kind: str, tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    decision = values["decision"]
    matching = {
        "status": "TRASHED",
        "gmail_message_id": decision["gmail_message_id"],
        "trash_request_key": decision["trash_request_key"],
    }
    if receipt_kind == "matching":
        receipt = matching
        expected = "RESTORE_REQUEST_READY_NO_MUTATION"
    elif receipt_kind == "missing":
        receipt = None
        expected = "RESTORE_BLOCKED_KEEP"
    else:
        receipt = dict(matching, trash_request_key="0" * 64)
        expected = "RESTORE_BLOCKED_KEEP"
    result = prepare_restore_request(
        archive_root=values["archive_root"],
        repository_root=values["repository_root"],
        gmail_message_id=values["record"]["gmail_message_id"],
        trash_request_key=decision["trash_request_key"],
        trash_receipt=receipt,
    )
    assert result["status"] == expected
    assert result["gmail_mutation_performed"] is False
    assert result["permanent_delete_performed"] is False


def test_same_safe_input_one_hundred_times_has_same_request_without_wait(tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    first = values["decision"]
    repeats = [_decision(values) for _ in range(FIXTURE["replay_iterations"])]
    soak = validate_no_real_time_soak()
    assert len(repeats) == 100
    assert all(row == first for row in repeats)
    assert REAL_TIME_SOAK_REQUIRED is False
    assert soak["real_time_soak_required"] is False
    assert soak["real_time_wait_performed"] is False


def test_one_in_ten_thousand_unknown_sender_perturbations_stay_keep_without_soak(tmp_path: Path) -> None:
    values = _prepared(tmp_path)
    first = _decision(values, sender_state="UNKNOWN")
    repeats = [_decision(values, sender_state="UNKNOWN") for _ in range(FIXTURE["adverse_perturbation_iterations"])]
    assert len(repeats) == 10_000
    assert all(row == first and row["status"] == "KEEP_AND_QUARANTINE" for row in repeats)
    assert first["gmail_mutation_performed"] is False
    assert first["real_time_soak_waited"] is False


def test_no_network_scheduler_or_permanent_delete_is_present_in_worker_source() -> None:
    source = (ROOT / WORKER_PATH).read_text(encoding="utf-8")
    for marker in (
        "users.messages.delete",
        "users.messages.batchDelete",
        "users.threads.delete",
        "time.sleep(",
        "subprocess.",
        "requests.",
        "socket.",
    ):
        assert marker not in source
    assert "PERMANENT_DELETE_CAPABILITY = False" in source
    assert "REAL_TIME_SOAK_REQUIRED = False" in source
    assert "allow_external_mutation: bool = False" in source


def test_p03_signed_evidence_is_the_only_phase_prerequisite() -> None:
    result = verify_p03_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["next"] == "S06/P04_READY_NOT_STARTED"


def test_fixture_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    fixture = strict_json_load(root / FIXTURE_PATH)
    fixture["sender_state"] = "UNKNOWN"
    _write_json(root / FIXTURE_PATH, fixture)
    result = evaluate_contract(root)
    _failed(result, "S06P04-FIXTURE-SHAPE")


def test_document_contract_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / AUDIT_PATH
    path.write_text(path.read_text(encoding="utf-8").replace('"gmail_mutation_default":"DISABLED"', '"gmail_mutation_default":"ENABLED"'), encoding="utf-8")
    result = evaluate_contract(root)
    _failed(result, "S06P04-DOC-CONTRACTS-EXACT")


def test_sensitive_or_machine_specific_content_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / RESTORE_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\nfile" + "://local-secret\n", encoding="utf-8")
    result = evaluate_contract(root)
    _failed(result, "S06P04-NO-SECRET-OR-LOCAL-PATH")


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["mail_gate_summary"]["trash_decision"] == "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"
    assert first["mail_gate_summary"]["dispatch_status"] == "TRASH_REQUEST_READY_NO_MUTATION"
    assert first["no_real_time_soak"]["real_time_soak_required"] is False
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
    assert result["gmail_mutation_performed"] is False
    assert result["permanent_delete_performed"] is False
    assert result["real_time_soak_waited"] is False


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S06P04-TARGETED-PYTEST-REPORT")


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
    assert '"AC-S06-P04": write_mail_deletion_audit_phase_evidence' in source
    assert "from .mail_deletion_audit import write_phase_evidence as write_mail_deletion_audit_phase_evidence" in source


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
    else:
        assert result["status"] == "FAIL"


def test_external_effect_boundary_is_exact_and_never_claims_runtime() -> None:
    assert EXTERNAL_EFFECT_BOUNDARY["gmail_account_or_api_accessed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["gmail_mutation_performed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["gmail_runtime_adapter_invoked"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["permanent_delete_capability"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"


def test_canonical_financial_and_order_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert canonical["email"]["permanent_delete"] is False
