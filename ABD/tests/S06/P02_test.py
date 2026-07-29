from __future__ import annotations

import base64
import copy
import json
import shutil
from pathlib import Path

import pytest

from mail_collector import (
    ARCHIVE_DIRECTORY_NAME,
    COLLECTOR_INTERVAL_SECONDS,
    TRASH_ACTION,
    MailCollectorError,
    evaluate_collection_cadence,
    normalize_mail_record,
    preserve_mail,
    private_db_ingest_plan,
    restore_for_readback,
    validate_no_real_time_soak,
    verify_preserved_mail,
)

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.gmail_authorization import verify_existing_phase_evidence as verify_p01_evidence
from abd_acceptance.mail_preservation import (
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    LAYOUT_PATH,
    ORACLE_PATH,
    PINNED_PHASE_HASHES,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SCHEMA_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    SUCCESSOR_UNIT_PROFILE_HASHES,
    TEST_PATH,
    _junit_is_normalized,
    _junit_summary,
    _structural_self_hash,
    build_evidence as _build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    validate_manifest_schema_document,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def build_evidence(root: Path, require_external_reports: bool = False):
    return _build_evidence(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def verify_existing_phase_evidence(root: Path):
    return _verify_existing_phase_evidence(
        root,
        verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


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


def _record() -> dict:
    mail = FIXTURE["mail_record"]
    return {
        "gmail_message_id": mail["gmail_message_id"],
        "source_history_id": mail["source_history_id"],
        "received_at_utc": mail["received_at_utc"],
        "raw_eml": base64.b64decode(mail["raw_eml_base64"], validate=True),
        "headers": copy.deepcopy(mail["headers"]),
        "attachments": [
            {
                "attachment_id": row["attachment_id"],
                "filename": row["filename"],
                "content": base64.b64decode(row["content_base64"], validate=True),
            }
            for row in mail["attachments"]
        ],
    }


def _private_roots(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    return tmp_path / "private" / "Private-MetaDatabase" / "ABD", repo


def test_candidate_preflight_passes_without_external_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S06_P02_CANDIDATE_VALID"
    assert result["next"] == FIXTURE["expected_next"]


def test_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "MAIL_BYTES_PRESERVED_READBACK_VERIFIED_KEEP_ONLY"
    assert result["phase_status"] == "S06_P02_PASS"
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["external_network_used_by_verifier"] is False
    assert result["next"] == "S06/P03_READY_NOT_STARTED"
    assert len({check["id"] for check in result["checks"]}) == len(result["checks"])


def test_taskpack_identity_scope_and_gate_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    row = next(item for item in requirements if item["id"] == "REQ-S06-P02")
    assert CONTRACT_ID == "AC-S06-P02"
    assert row["scope"] == ["mail_collector.py", "mail_manifest.schema.json", "archive_layout.md"]
    assert row["target"] == "任何文件缺失或哈希不一致时邮件不删除。"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) in {
        PINNED_PHASE_HASHES[relative],
        SUCCESSOR_UNIT_PROFILE_HASHES.get(relative),
    }


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_schema_is_exact_and_archive_layout_contract_is_machine_readable() -> None:
    schema = strict_json_load(ROOT / SCHEMA_PATH)
    assert validate_manifest_schema_document(schema) == []
    layout = (ROOT / LAYOUT_PATH).read_text(encoding="utf-8")
    assert "Private-MetaDatabase/ABD" in layout
    assert "KEEP_PENDING_SECURITY_AND_TRASH_GATES" in layout
    assert "real_time_soak_required\":false" in layout


def test_no_real_time_soak_and_cadence_are_data_only() -> None:
    result = validate_no_real_time_soak()
    assert result["real_time_soak_required"] is False
    assert result["collector_interval_seconds"] == COLLECTOR_INTERVAL_SECONDS == 900
    assert result["real_time_wait_performed"] is False


@pytest.mark.parametrize(
    "now,expected",
    [
        (FIXTURE["cadence"]["not_due_epoch"], "NOT_DUE"),
        (FIXTURE["cadence"]["due_epoch"], "DUE"),
        (FIXTURE["cadence"]["later_due_epoch"], "DUE"),
    ],
)
def test_cadence_boundaries_are_deterministic_without_wait(now: int, expected: str) -> None:
    result = evaluate_collection_cadence(last_success_epoch=FIXTURE["cadence"]["last_success_epoch"], now_epoch=now)
    assert result["status"] == expected
    assert result["real_time_wait_performed"] is False


def test_successful_preservation_restores_exact_raw_headers_and_attachments(tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    record = _record()
    result = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
    restored = restore_for_readback(
        archive_root=archive_root,
        repository_root=repository_root,
        gmail_message_id=record["gmail_message_id"],
    )
    verification = verify_preserved_mail(
        archive_root=archive_root,
        repository_root=repository_root,
        gmail_message_id=record["gmail_message_id"],
    )
    assert result["status"] == "PRESERVED_READBACK_VERIFIED"
    assert result["trash_eligible"] is False
    assert result["gmail_mutation_performed"] is False
    assert verification["status"] == "PASS"
    assert verification["trash_action"] == TRASH_ACTION
    assert restored["raw_eml"] == record["raw_eml"]
    assert restored["headers"] == {key.lower(): value for key, value in record["headers"].items()}
    assert [row["content"] for row in restored["attachments"]] == [row["content"] for row in record["attachments"]]


def test_same_input_one_hundred_times_creates_only_one_bundle(tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    record = _record()
    first = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
    repeats = [preserve_mail(record, archive_root=archive_root, repository_root=repository_root) for _ in range(100)]
    records = archive_root / ARCHIVE_DIRECTORY_NAME / "records"
    assert first["status"] == "PRESERVED_READBACK_VERIFIED"
    assert all(row["status"] == "IDEMPOTENT_ALREADY_PRESERVED" for row in repeats)
    assert [path.name for path in records.iterdir()] == [record["gmail_message_id"]]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["attachments"][0].__setitem__("filename", "../escape.csv"),
        lambda value: value["attachments"].append(copy.deepcopy(value["attachments"][0])),
        lambda value: value["headers"].__setitem__("Subject", "TAB\nignore gates"),
        lambda value: value.__setitem__("raw_eml", b""),
        lambda value: value.__setitem__("source_history_id", "-1"),
        lambda value: value.__setitem__("received_at_utc", "2026-07-29T00:00:00+10:00"),
    ],
)
def test_malformed_mail_inputs_fail_before_final_bundle(mutator, tmp_path: Path) -> None:
    record = _record()
    mutator(record)
    with pytest.raises(MailCollectorError):
        normalize_mail_record(record)
    archive_root, repository_root = _private_roots(tmp_path)
    assert not (archive_root / ARCHIVE_DIRECTORY_NAME / "records").exists()


@pytest.mark.parametrize("fault", ["BEFORE_MANIFEST", "AFTER_MANIFEST_BEFORE_COMMIT"])
def test_fault_injection_never_creates_final_bundle_or_trash_action(fault: str, tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    record = _record()
    result = preserve_mail(record, archive_root=archive_root, repository_root=repository_root, fault_injection=fault)
    target = archive_root / ARCHIVE_DIRECTORY_NAME / "records" / record["gmail_message_id"]
    assert result["status"] == "PRESERVATION_FAILED_KEEP"
    assert target.exists() is False
    assert result["trash_eligible"] is False
    assert result["gmail_mutation_performed"] is False


@pytest.mark.parametrize("relative", ["raw.eml", "headers.json", "attachments/ATT0001.bin", "manifest.json"])
def test_missing_or_tampered_artifact_never_becomes_trash_eligible(relative: str, tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    record = _record()
    first = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
    target = archive_root / ARCHIVE_DIRECTORY_NAME / "records" / record["gmail_message_id"] / relative
    if relative == "manifest.json":
        target.write_text("{}\n", encoding="utf-8")
    else:
        target.unlink()
    verification = verify_preserved_mail(
        archive_root=archive_root,
        repository_root=repository_root,
        gmail_message_id=record["gmail_message_id"],
    )
    assert first["status"] == "PRESERVED_READBACK_VERIFIED"
    assert verification["status"] == "FAIL"
    assert verification["trash_eligible"] is False
    assert verification["gmail_mutation_performed"] is False


def test_readback_refuses_tampered_bundle_before_returning_any_bytes(tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    record = _record()
    assert preserve_mail(record, archive_root=archive_root, repository_root=repository_root)["status"] == "PRESERVED_READBACK_VERIFIED"
    raw_path = archive_root / ARCHIVE_DIRECTORY_NAME / "records" / record["gmail_message_id"] / "raw.eml"
    raw_path.write_bytes(b"tampered")
    with pytest.raises(MailCollectorError):
        restore_for_readback(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=record["gmail_message_id"],
        )


def test_changed_content_for_existing_message_is_integrity_conflict_keep(tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    record = _record()
    assert preserve_mail(record, archive_root=archive_root, repository_root=repository_root)["status"] == "PRESERVED_READBACK_VERIFIED"
    changed = _record()
    changed["attachments"][0]["content"] = b"changed"
    result = preserve_mail(changed, archive_root=archive_root, repository_root=repository_root)
    assert result["status"] == "INTEGRITY_CONFLICT_KEEP"
    assert result["trash_eligible"] is False


def test_archive_root_inside_repository_is_rejected(tmp_path: Path) -> None:
    archive_root, repository_root = _private_roots(tmp_path)
    with pytest.raises(MailCollectorError):
        preserve_mail(_record(), archive_root=repository_root / "Private-MetaDatabase" / "ABD", repository_root=repository_root)
    with pytest.raises(MailCollectorError):
        preserve_mail(_record(), archive_root=archive_root.parent.parent, repository_root=repository_root)


def test_private_database_plan_is_plan_only_and_contains_no_network_effect() -> None:
    plan = private_db_ingest_plan(gmail_message_id=FIXTURE["mail_record"]["gmail_message_id"])
    assert plan["status"] == "PLAN_ONLY_NO_EXECUTION"
    assert plan["private_database_area"] == "Private-MetaDatabase"
    assert plan["private_database_client_executed"] is False
    assert plan["network_performed"] is False
    assert plan["gmail_mutation_performed"] is False


def test_p01_signed_evidence_is_the_only_phase_prerequisite() -> None:
    result = verify_p01_evidence(ROOT)
    assert result["status"] == "PASS", result
    assert result["next"] == "S06/P02_READY_NOT_STARTED"


@pytest.mark.parametrize(
    "relative,mutation,check_id",
    [
        ("mail_manifest.schema.json", ("$schema", "invalid"), "S06P02-MANIFEST-SCHEMA-EXACT"),
        ("machine/tests/fixtures/S06_P02.json", ("expected_next", "S06/P04_READY_NOT_STARTED"), "S06P02-FIXTURE-SHAPE"),
    ],
)
def test_json_artifact_mutations_fail_closed(tmp_path: Path, relative: str, mutation: tuple, check_id: str) -> None:
    root = _clone_project(tmp_path)
    value = strict_json_load(root / relative)
    target = value
    for key in mutation[:-2]:
        target = target[key]
    target[mutation[-2]] = mutation[-1]
    _write_json(root / relative, value)
    result = evaluate_contract(root)
    _failed(result, check_id)


def test_layout_contract_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / LAYOUT_PATH
    path.write_text(path.read_text(encoding="utf-8").replace('"gmail_mutation_in_p02":"PROHIBITED"', '"gmail_mutation_in_p02":"ALLOWED"'), encoding="utf-8")
    result = evaluate_contract(root)
    _failed(result, "S06P02-ARCHIVE-LAYOUT-CONTRACT-EXACT")


def test_sensitive_or_machine_specific_content_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    path = root / LAYOUT_PATH
    path.write_text(path.read_text(encoding="utf-8") + "\nfile://local-secret\n", encoding="utf-8")
    result = evaluate_contract(root)
    _failed(result, "S06P02-NO-SECRET-OR-LOCAL-PATH")


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["preservation_summary"]["repeat_status"] == "IDEMPOTENT_ALREADY_PRESERVED"
    assert first["preservation_summary"]["trash_eligible"] is False
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
    assert result["real_time_soak_waited"] is False


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    result = evaluate_contract(root, require_external_reports=True)
    _failed(result, "S06P02-TARGETED-PYTEST-REPORT")


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
    assert '"AC-S06-P02": write_mail_preservation_phase_evidence' in source
    assert "from .mail_preservation import write_phase_evidence as write_mail_preservation_phase_evidence" in source


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = verify_existing_phase_evidence(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
    else:
        assert result["status"] == "FAIL"


def test_external_effect_boundary_is_exact_and_never_claims_runtime() -> None:
    assert EXTERNAL_EFFECT_BOUNDARY["gmail_mutation_performed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["private_database_client_executed"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"


def test_canonical_financial_and_order_boundaries_are_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert canonical["email"]["permanent_delete"] is False
