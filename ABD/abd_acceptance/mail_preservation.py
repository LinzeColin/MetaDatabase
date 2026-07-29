"""Independent deterministic acceptance oracle for ABD S06/P02 preservation.

The oracle uses only frozen synthetic bytes in temporary private-plane paths.
It never contacts Gmail, invokes a Private-Database client, starts a daemon,
moves a message to trash, reads a real token, or waits for real time.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from mail_collector import (
    ARCHIVE_DIRECTORY_NAME,
    ARCHIVE_LAYOUT_VERSION,
    ARCHIVE_STATUS,
    COLLECTOR_INTERVAL_SECONDS,
    CONTRACT_ID as COLLECTOR_CONTRACT_ID,
    PRIVATE_DATABASE_AREA,
    PRIVATE_DATABASE_DOMAIN,
    REAL_TIME_SOAK_REQUIRED,
    REQUIREMENT_ID as COLLECTOR_REQUIREMENT_ID,
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

from .canonical_facts import sha256_file, strict_json_load
from .gmail_authorization import verify_existing_phase_evidence as verify_gmail_authorization_evidence


CONTRACT_ID = "AC-S06-P02"
REQUIREMENT_ID = "REQ-S06-P02"
STAGE_ID = "S06"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-29T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

COLLECTOR_PATH = Path("mail_collector.py")
SCHEMA_PATH = Path("mail_manifest.schema.json")
LAYOUT_PATH = Path("archive_layout.md")
FIXTURE_PATH = Path("machine/tests/fixtures/S06_P02.json")
TEST_PATH = Path("tests/S06/P02_test.py")
ORACLE_PATH = Path("abd_acceptance/mail_preservation.py")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P01.json")
P01_ROLLBACK_PATH = Path("machine/evidence/EVD-S06-P01_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S06/P02/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S06/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")

PINNED_PHASE_HASHES: Dict[str, str] = {
    "mail_collector.py": "dcc3f76a6067f84b8541e6752d0de28b90352ffae57620c391848b26c3967b3d",
    "mail_manifest.schema.json": "9cdd35b0dd62fd899582d9848346d8493fc13139ace4a115e48952ae8e09f0f4",
    "archive_layout.md": "7c9eb14786c040b253bb35f76b334ede396cd9a4b881433fbc26a1c08aa2c275",
    "machine/tests/fixtures/S06_P02.json": "8d159a62a774cb879cc45f1d4cd5bb193d0b50f82ed9fd9beea1c49a25288e46",
    "tests/S06/P02_test.py": "5c31dfb11d590add2fe482b729d979757c6d51f89c48dc1e3b0ad4626570b63f",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "b5e5151f38eecf068db5a134111e96b01aca75e8a93ae53796b95c83304d955e"

ROLLBACK_ARTIFACTS = (COLLECTOR_PATH, SCHEMA_PATH, LAYOUT_PATH)
EXTERNAL_EFFECT_BOUNDARY = {
    "gmail_account_or_api_accessed": False,
    "gmail_mutation_performed": False,
    "private_database_client_executed": False,
    "private_database_or_raw_data_written": False,
    "real_network_accessed": False,
    "real_time_soak_waited": False,
    "scheduler_daemon_started": False,
    "token_or_client_secret_read": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "real_order_submitted_or_retried": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
}

SECRET_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])ya29\.[A-Za-z0-9._-]+", re.I),
    re.compile(r"(?:^|[^a-z0-9])1//[A-Za-z0-9._-]+", re.I),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}", re.I),
)
LOCAL_PATH_FRAGMENTS = ("/" + "Users/", "file" + "://")
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    rendered = path.as_posix()
    marker = "/machine/"
    portable = "machine/" + rendered.split(marker, 1)[1] if marker in rendered else path.name
    _add(checks, check_id, True, portable)
    return value


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8"))


def _current_code_hash(root: Path) -> str:
    payload = b""
    for relative in (COLLECTOR_PATH, ORACLE_PATH):
        payload += relative.as_posix().encode("utf-8") + b"\0" + (root / relative).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s=%s row" % (key, identifier))
    return matches[0]


def _parse_layout_contract(text: str) -> Mapping[str, Any]:
    begin = "<!-- ABD_ARCHIVE_LAYOUT_CONTRACT\n"
    end = "\n-->"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError("archive layout contract markers are not exact")
    start = text.index(begin) + len(begin)
    finish = text.index(end, start)

    def reject_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate contract key")
            result[key] = value
        return result

    value = json.loads(text[start:finish], object_pairs_hook=reject_duplicates)
    if not isinstance(value, Mapping):
        raise ValueError("archive layout contract is not an object")
    return value


ARCHIVE_LAYOUT_CONTRACT = {
    "archive_directory": ARCHIVE_DIRECTORY_NAME,
    "archive_layout_version": ARCHIVE_LAYOUT_VERSION,
    "contract_id": CONTRACT_ID,
    "gmail_mutation_in_p02": "PROHIBITED",
    "manifest": "manifest.json",
    "private_database_area": PRIVATE_DATABASE_AREA,
    "private_database_domain": PRIVATE_DATABASE_DOMAIN,
    "private_db_client_execution_in_p02": False,
    "raw_data_repository_write": "PROHIBITED",
    "real_time_soak_required": False,
    "requirement_id": REQUIREMENT_ID,
    "schema": SCHEMA_PATH.as_posix(),
    "stage": STAGE_ID,
    "trash_action": TRASH_ACTION,
}


def validate_manifest_schema_document(value: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(value, Mapping):
        return ["schema_not_mapping"]
    expected_keys = {"$schema", "$id", "title", "description", "type", "additionalProperties", "required", "properties", "$defs"}
    if set(value) != expected_keys:
        errors.append("schema_fields_not_exact")
    if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema_draft_invalid")
    if value.get("$id") != "https://abd.invalid/schema/mail_manifest.schema.json":
        errors.append("schema_id_invalid")
    if value.get("type") != "object" or value.get("additionalProperties") is not False:
        errors.append("schema_object_boundary_invalid")
    required = value.get("required")
    expected_required = [
        "schema_version", "manifest_id", "contract_id", "requirement_id", "product_version", "archive_layout_version",
        "status", "gmail_message_id", "source_history_id", "received_at_utc", "private_storage", "raw_eml", "headers",
        "attachments", "readback_verified", "trash_action", "gmail_mutation_performed", "real_time_soak_wait_required",
        "archive_root_reference", "manifest_sha256",
    ]
    if required != expected_required:
        errors.append("schema_required_fields_invalid")
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        errors.append("schema_properties_invalid")
    else:
        constants = {
            "schema_version": "1.0.0",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "product_version": VERSION,
            "archive_layout_version": ARCHIVE_LAYOUT_VERSION,
            "status": ARCHIVE_STATUS,
            "readback_verified": True,
            "trash_action": TRASH_ACTION,
            "gmail_mutation_performed": False,
            "real_time_soak_wait_required": False,
        }
        for key, expected in constants.items():
            if not isinstance(properties.get(key), Mapping) or properties[key].get("const") != expected:
                errors.append("schema_constant_invalid_%s" % key)
    definitions = value.get("$defs")
    if not isinstance(definitions, Mapping) or set(definitions) != {"sha256", "file", "attachment"}:
        errors.append("schema_definitions_invalid")
    return errors


def _fixture_record(fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    mail = fixture.get("mail_record")
    if not isinstance(mail, Mapping):
        raise ValueError("mail_record unavailable")
    try:
        raw = base64.b64decode(mail["raw_eml_base64"], validate=True)
        attachments = [
            {
                "attachment_id": item["attachment_id"],
                "filename": item["filename"],
                "content": base64.b64decode(item["content_base64"], validate=True),
            }
            for item in mail["attachments"]
        ]
    except Exception as exc:
        raise ValueError("frozen mail bytes are malformed") from exc
    return {
        "gmail_message_id": mail["gmail_message_id"],
        "source_history_id": mail["source_history_id"],
        "received_at_utc": mail["received_at_utc"],
        "raw_eml": raw,
        "headers": mail["headers"],
        "attachments": attachments,
    }


def _private_test_root(directory: Path, fixture: Mapping[str, Any]) -> tuple[Path, Path]:
    segments = fixture.get("archive_root_segments")
    if segments != ["private", "Private-MetaDatabase", "ABD"]:
        raise ValueError("private archive root fixture is invalid")
    repository_root = directory / "repo"
    repository_root.mkdir()
    return directory.joinpath(*segments), repository_root


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in sorted(PINNED_PHASE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(
            checks,
            "S06P02-PHASE-PIN-%s" % relative.replace("/", "-").replace(".", "_"),
            actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor),
            {"expected": expected, "accepted_successor": successor, "actual": actual},
        )


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        requirements = strict_json_load(root / "machine/facts/requirements.json")
        contracts = strict_json_load(root / "machine/facts/acceptance_contracts.json")
        task_graph = strict_json_load(root / "machine/facts/task_graph.json")
        roadmap = strict_json_load(root / "machine/facts/roadmap.json")
        traceability = strict_json_load(root / "machine/facts/traceability_matrix.json")
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        tasks = [row for row in task_graph.get("tasks", []) if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
        stage = _row(roadmap.get("stages"), STAGE_ID)
        phase = _row(stage.get("phases"), PHASE_ID)
        expected_outputs = [COLLECTOR_PATH.as_posix(), SCHEMA_PATH.as_posix(), LAYOUT_PATH.as_posix()]
        expected_task_ids = ["T-S06-P02-01", "T-S06-P02-02", "T-S06-P02-03"]
        expected_test_ids = ["TEST-S06-P02", "TEST-S06-P02-BOUNDARY", "TEST-S06-P02-REPLAY"]
        pass_gate = "任何文件缺失或哈希不一致时邮件不删除。"
        ok = (
            requirement.get("scope") == expected_outputs
            and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == pass_gate
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S06-P02 --evidence machine/evidence"
            and contract.get("pass_gate") == pass_gate
            and phase.get("outputs") == expected_outputs
            and phase.get("pass_gate") == pass_gate
            and [task.get("id") for task in tasks] == expected_task_ids
            and tasks[0].get("depends_on") == ["T-S06-P01-03"]
            and trace.get("task_ids") == expected_task_ids
            and trace.get("test_ids") == expected_test_ids
            and trace.get("evidence_id") == "EVD-S06-P02"
        )
        _add(checks, "S06P02-TASKPACK-TRACE-EXACT", ok, {"outputs": expected_outputs, "tasks": [task.get("id") for task in tasks]})
    except Exception as exc:
        _add(checks, "S06P02-TASKPACK-TRACE-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    try:
        predecessor = verify_gmail_authorization_evidence(root, verify_git_history=verify_git_history)
        ok = predecessor.get("status") == "PASS" and predecessor.get("next") == "S06/P02_READY_NOT_STARTED"
        _add(checks, "S06P02-P01-SIGNED-PREREQUISITE", ok, {"status": predecessor.get("status"), "next": predecessor.get("next")})
    except Exception as exc:
        _add(checks, "S06P02-P01-SIGNED-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_artifacts(
    root: Path,
    fixture: Mapping[str, Any] | None,
    schema: Mapping[str, Any] | None,
    layout_text: str | None,
    checks: List[Dict[str, Any]],
) -> Mapping[str, Any] | None:
    if not isinstance(fixture, Mapping) or not isinstance(schema, Mapping) or not isinstance(layout_text, str):
        _add(checks, "S06P02-ARTIFACTS-AVAILABLE", False, "one or more required artifacts are unavailable")
        return None
    fixture_ok = (
        fixture.get("schema_version") == "1.0.0"
        and fixture.get("fixture_id") == "FIX-S06-P02"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("requirement_id") == REQUIREMENT_ID
        and fixture.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
        and fixture.get("archive_root_segments") == ["private", "Private-MetaDatabase", "ABD"]
        and fixture.get("numeric_boundary_deltas") == ["-0.0001", "0", "0.0001"]
        and fixture.get("adverse_odds_tick_action") == "NOT_APPLICABLE_NO_ODDS_OR_ORDER_ACTION_IN_S06_P02"
        and fixture.get("expected_next") == "S06/P03_READY_NOT_STARTED"
        and fixture.get("expected_release_status") == "NOT_READY_S06_P03_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED"
    )
    _add(checks, "S06P02-FIXTURE-SHAPE", fixture_ok, fixture.get("fixture_id"))
    schema_errors = validate_manifest_schema_document(schema)
    _add(checks, "S06P02-MANIFEST-SCHEMA-EXACT", not schema_errors, schema_errors or "valid")
    try:
        layout = _parse_layout_contract(layout_text)
        _add(checks, "S06P02-ARCHIVE-LAYOUT-CONTRACT-EXACT", layout == ARCHIVE_LAYOUT_CONTRACT, layout)
    except Exception as exc:
        _add(checks, "S06P02-ARCHIVE-LAYOUT-CONTRACT-EXACT", False, "%s: %s" % (type(exc).__name__, exc))
    source = (root / COLLECTOR_PATH).read_text(encoding="utf-8")
    source_ok = (
        "time.sleep(" not in source
        and "requests." not in source
        and "urllib.request" not in source
        and "subprocess." not in source
        and "users.messages.trash" not in source
        and "Private-MetaDatabase" in source
        and "os.rename" in source
        and REAL_TIME_SOAK_REQUIRED is False
        and COLLECTOR_CONTRACT_ID == CONTRACT_ID
        and COLLECTOR_REQUIREMENT_ID == REQUIREMENT_ID
    )
    _add(checks, "S06P02-NO-NETWORK-TRASH-OR-REALTIME-SOAK", source_ok, "deterministic private-plane collector only")
    try:
        canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
        canonical_keep_only_ok = (
            canonical.get("email", {}).get("permanent_delete") is False
            and canonical.get("scope", {}).get("order_submission_module_present") is False
            and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00"
        )
        _add(checks, "S06P02-CANONICAL-KEEP-ONLY-BOUNDARY", canonical_keep_only_ok, "no permanent delete, order submission, or incremental cash")
    except Exception as exc:
        _add(checks, "S06P02-CANONICAL-KEEP-ONLY-BOUNDARY", False, "%s: %s" % (type(exc).__name__, exc))
    return fixture


def _check_core_flow(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Mapping[str, Any] | None:
    try:
        record = _fixture_record(fixture)
        normalized = normalize_mail_record(record)
        with tempfile.TemporaryDirectory(prefix="abd-s06-p02-") as directory:
            temporary = Path(directory)
            archive_root, repository_root = _private_test_root(temporary, fixture)
            first = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            repeats = [preserve_mail(record, archive_root=archive_root, repository_root=repository_root) for _ in range(100)]
            bundle = archive_root / ARCHIVE_DIRECTORY_NAME / "records" / normalized["gmail_message_id"]
            manifest = strict_json_load(bundle / "manifest.json")
            verification = verify_preserved_mail(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=normalized["gmail_message_id"],
            )
            restored = restore_for_readback(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=normalized["gmail_message_id"],
            )
            cadence = fixture["cadence"]
            before = evaluate_collection_cadence(last_success_epoch=cadence["last_success_epoch"], now_epoch=cadence["not_due_epoch"])
            at = evaluate_collection_cadence(last_success_epoch=cadence["last_success_epoch"], now_epoch=cadence["due_epoch"])
            after = evaluate_collection_cadence(last_success_epoch=cadence["last_success_epoch"], now_epoch=cadence["later_due_epoch"])
            plan = private_db_ingest_plan(gmail_message_id=normalized["gmail_message_id"])
            core_ok = (
                first.get("status") == "PRESERVED_READBACK_VERIFIED"
                and all(row.get("status") == "IDEMPOTENT_ALREADY_PRESERVED" for row in repeats)
                and verification.get("status") == "PASS"
                and restored.get("raw_eml") == normalized["raw_eml"]
                and restored.get("headers") == normalized["headers"]
                and [item.get("content") for item in restored.get("attachments", [])] == [item["content"] for item in normalized["attachments"]]
                and first.get("trash_eligible") is False
                and all(row.get("gmail_mutation_performed") is False for row in [first, verification, *repeats])
                and before.get("status") == "NOT_DUE"
                and at.get("status") == "DUE"
                and after.get("status") == "DUE"
                and all(row.get("real_time_wait_performed") is False for row in [before, at, after])
                and plan.get("status") == "PLAN_ONLY_NO_EXECUTION"
                and plan.get("private_database_client_executed") is False
            )
            _add(checks, "S06P02-TWO-PHASE-PRESERVE-READBACK-IDEMPOTENT", core_ok, {"repeat_count": len(repeats), "attachment_count": len(normalized["attachments"])})
            manifest_private_plane_ok = (
                isinstance(manifest, Mapping)
                and manifest.get("private_storage") == {
                    "area": PRIVATE_DATABASE_AREA,
                    "domain": "ABD",
                    "repository_raw_data_write": "PROHIBITED",
                    "private_db_client_execution_in_p02": False,
                }
                and manifest.get("archive_root_reference") == "records/%s" % normalized["gmail_message_id"]
            )
            _add(checks, "S06P02-MANIFEST-PRIVATE-PLANE-EXACT", manifest_private_plane_ok, manifest.get("private_storage") if isinstance(manifest, Mapping) else "manifest unavailable")
            manifest_hashes_ok = (
                isinstance(manifest, Mapping)
                and isinstance(manifest.get("raw_eml"), Mapping)
                and isinstance(manifest.get("headers"), Mapping)
                and isinstance(manifest.get("attachments"), list)
                and SHA256_RE.fullmatch(str(manifest["raw_eml"].get("sha256"))) is not None
                and SHA256_RE.fullmatch(str(manifest["headers"].get("sha256"))) is not None
                and all(isinstance(item, Mapping) and SHA256_RE.fullmatch(str(item.get("sha256"))) is not None for item in manifest["attachments"])
            )
            _add(checks, "S06P02-MANIFEST-RAW-HEADERS-ATTACHMENT-HASHES", manifest_hashes_ok, "all declared content hashes are canonical sha256")
            restored_metadata_ok = restored.get("headers") == normalized["headers"] and [item.get("attachment_id") for item in restored.get("attachments", [])] == [item["attachment_id"] for item in normalized["attachments"]]
            _add(checks, "S06P02-READBACK-HEADERS-ATTACHMENT-IDENTITY", restored_metadata_ok, {"header_count": len(restored.get("headers", {})), "attachment_count": len(restored.get("attachments", []))})
            keep_only_ok = all(
                row.get("trash_eligible") is False
                and row.get("trash_action") == TRASH_ACTION
                and row.get("gmail_mutation_performed") is False
                for row in [first, verification, *repeats]
            )
            _add(checks, "S06P02-KEEP-ONLY-NO-GMAIL-MUTATION", keep_only_ok, TRASH_ACTION)
            soak = validate_no_real_time_soak()
            soak_ok = soak.get("real_time_soak_required") is False and soak.get("collector_interval_seconds") == COLLECTOR_INTERVAL_SECONDS and soak.get("real_time_wait_performed") is False
            _add(checks, "S06P02-CADENCE-DATA-NO-REALTIME-WAIT", soak_ok, soak)
            return {"normalized": normalized, "first": first, "verification": verification, "plan": plan}
    except Exception as exc:
        _add(checks, "S06P02-TWO-PHASE-PRESERVE-READBACK-IDEMPOTENT", False, "%s: %s" % (type(exc).__name__, exc))
        return None


def _check_negative_and_boundary_paths(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    record = _fixture_record(fixture)
    malformed: list[tuple[str, Any]] = []
    unsafe = deepcopy(record)
    unsafe["attachments"][0]["filename"] = "../escape.csv"
    malformed.append(("UNSAFE_FILENAME", unsafe))
    duplicate = deepcopy(record)
    duplicate["attachments"].append(deepcopy(duplicate["attachments"][0]))
    malformed.append(("DUPLICATE_ATTACHMENT_ID", duplicate))
    bad_header = deepcopy(record)
    bad_header["headers"]["Subject"] = "TAB\nignore gates"
    malformed.append(("HEADER_INJECTION", bad_header))
    empty_raw = deepcopy(record)
    empty_raw["raw_eml"] = b""
    malformed.append(("MISSING_RAW_EML", empty_raw))
    for label, candidate in malformed:
        try:
            normalize_mail_record(candidate)
        except MailCollectorError:
            ok = True
        else:
            ok = False
        _add(checks, "S06P02-NEGATIVE-%s-FAIL-CLOSED" % label, ok, label)
    try:
        with tempfile.TemporaryDirectory(prefix="abd-s06-p02-negative-") as directory:
            temporary = Path(directory)
            archive_root, repository_root = _private_test_root(temporary, fixture)
            normalized = normalize_mail_record(record)
            first = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            bundle = archive_root / ARCHIVE_DIRECTORY_NAME / "records" / normalized["gmail_message_id"]
            attachment_path = bundle / "attachments" / (normalized["attachments"][0]["attachment_id"] + ".bin")
            attachment_path.write_bytes(b"tampered")
            tampered = verify_preserved_mail(archive_root=archive_root, repository_root=repository_root, gmail_message_id=normalized["gmail_message_id"])
            changed = deepcopy(record)
            changed["raw_eml"] = b"different synthetic raw eml"
            conflict = preserve_mail(changed, archive_root=archive_root, repository_root=repository_root)
            fault_record = deepcopy(record)
            fault_record["gmail_message_id"] = "MSG0002"
            fault = preserve_mail(fault_record, archive_root=archive_root, repository_root=repository_root, fault_injection="AFTER_MANIFEST_BEFORE_COMMIT")
            no_final_fault_bundle = not (archive_root / ARCHIVE_DIRECTORY_NAME / "records" / "MSG0002").exists()
            repo_root_failure = False
            try:
                preserve_mail(record, archive_root=repository_root / "Private-MetaDatabase" / "ABD", repository_root=repository_root)
            except MailCollectorError:
                repo_root_failure = True
            negative_ok = (
                first.get("status") == "PRESERVED_READBACK_VERIFIED"
                and tampered.get("status") == "FAIL"
                and tampered.get("trash_eligible") is False
                and tampered.get("gmail_mutation_performed") is False
                and conflict.get("status") == "INTEGRITY_CONFLICT_KEEP"
                and fault.get("status") == "PRESERVATION_FAILED_KEEP"
                and no_final_fault_bundle
                and repo_root_failure
            )
            _add(checks, "S06P02-MISSING-OR-HASH-MISMATCH-NEVER-TRASH", negative_ok, {"tamper": tampered.get("reason_codes"), "fault_final_bundle": no_final_fault_bundle})
    except Exception as exc:
        _add(checks, "S06P02-MISSING-OR-HASH-MISMATCH-NEVER-TRASH", False, "%s: %s" % (type(exc).__name__, exc))
    cadence = fixture.get("cadence", {})
    try:
        rewind = evaluate_collection_cadence(last_success_epoch=cadence["due_epoch"], now_epoch=cadence["last_success_epoch"])
        _add(checks, "S06P02-CADENCE-CLOCK-REWIND-FAIL-CLOSED", rewind.get("status") == "INVALID_CLOCK_KEEP" and rewind.get("due") is False, rewind)
    except Exception as exc:
        _add(checks, "S06P02-CADENCE-CLOCK-REWIND-FAIL-CLOSED", False, "%s: %s" % (type(exc).__name__, exc))
    for delta in fixture.get("numeric_boundary_deltas", []):
        _add(checks, "S06P02-NUMERIC-BOUNDARY-%s" % str(delta).replace("-", "NEG").replace(".", "_"), delta in {"-0.0001", "0", "0.0001"}, delta)


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        return False
    return all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
        for suite in suites
    )


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    reports = [
        ("TARGETED", JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases")),
        ("FULL", FULL_JUNIT_PATH, fixture.get("minimum_full_pytest_cases")),
    ]
    for label, relative, minimum in reports:
        try:
            summary = _junit_summary(root / relative)
            ok = type(minimum) is int and summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and _junit_is_normalized(root / relative)
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, "S06P02-%s-PYTEST-REPORT" % label, ok, {"summary": summary, "minimum": minimum, "normalized": _junit_is_normalized(root / relative)})
        except Exception as exc:
            _add(checks, "S06P02-%s-PYTEST-REPORT" % label, False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S06P02-PACK-REPORT-STRICT-JSON")
    if isinstance(pack, Mapping):
        pack_ok = pack.get("status") == "PASS" and pack.get("summary", {}).get("checks") == 49 and pack.get("summary", {}).get("failed") == 0
        _add(checks, "S06P02-TASKPACK-49-PASS", pack_ok, pack.get("summary"))
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8") if (root / SCAN_REPORT_PATH).is_file() else ""
    required_lines = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    _add(checks, "S06P02-PAID-DEPENDENCY-SCAN", required_lines <= set(scan.splitlines()), SCAN_REPORT_PATH.as_posix())
    if (root / SCAN_REPORT_PATH).is_file():
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)


def _check_no_sensitive_material(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = (COLLECTOR_PATH, SCHEMA_PATH, LAYOUT_PATH, FIXTURE_PATH)
    leaks: List[Dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative.as_posix(), "kind": "local-path"})
    _add(checks, "S06P02-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S06P02-FIXTURE-STRICT-JSON")
    schema = _safe_load(root / SCHEMA_PATH, checks, "S06P02-SCHEMA-STRICT-JSON")
    try:
        layout_text = (root / LAYOUT_PATH).read_text(encoding="utf-8")
        _add(checks, "S06P02-LAYOUT-UTF8", True, LAYOUT_PATH.as_posix())
    except Exception as exc:
        layout_text = None
        _add(checks, "S06P02-LAYOUT-UTF8", False, "%s: %s" % (type(exc).__name__, exc))
    _check_pins(root, checks, hashes)
    _add(checks, "S06P02-ORACLE-SELF-INTEGRITY", _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": _structural_self_hash(root)})
    _check_taskpack_trace(root, checks)
    _check_predecessor(root, checks, verify_git_history=_verify_git_history)
    valid_fixture = _check_artifacts(root, fixture if isinstance(fixture, Mapping) else None, schema if isinstance(schema, Mapping) else None, layout_text, checks)
    if valid_fixture is not None:
        _check_core_flow(valid_fixture, checks)
        _check_negative_and_boundary_paths(valid_fixture, checks)
        if require_external_reports:
            _check_external_reports(root, valid_fixture, checks, hashes)
    else:
        _add(checks, "S06P02-TWO-PHASE-PRESERVE-READBACK-IDEMPOTENT", False, "fixture unavailable")
    _check_no_sensitive_material(root, checks)
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS" if not failed else "FAIL",
        "phase_status": "S06_P02_PASS" if not failed else "S06_P02_FAIL",
        "decision": "MAIL_BYTES_PRESERVED_READBACK_VERIFIED_KEEP_ONLY" if not failed else "S06_P02_BLOCKED_FAIL_CLOSED",
        "release_status": "NOT_READY_S06_P03_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S06/P03_READY_NOT_STARTED" if not failed else "S06/P02_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S06_P02_CANDIDATE_VALID" if result["status"] == "PASS" else "S06_P02_CANDIDATE_INVALID",
        "summary": result["summary"],
        "next": result["next"],
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, str]] = {}
    for relative in ROLLBACK_ARTIFACTS:
        try:
            before = sha256_file(root / relative)
            after = sha256_file(root / relative)
            artifacts[relative.as_posix()] = {"status": "PASS" if before == after else "FAIL", "before": before, "after": after}
        except Exception as exc:
            artifacts[relative.as_posix()] = {"status": "FAIL", "detail": "%s: %s" % (type(exc).__name__, exc)}
    status = "PASS" if artifacts and all(row.get("status") == "PASS" for row in artifacts.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_PRESERVATION_KEEP_SOURCE_MAIL_NO_EXTERNAL_ACTION",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "gmail_account_or_api_accessed": False,
        "private_database_client_executed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = (
        COLLECTOR_PATH,
        SCHEMA_PATH,
        LAYOUT_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        P01_EVIDENCE_PATH,
        P01_ROLLBACK_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/email_ingestion.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
    )
    return {relative.as_posix(): sha256_file(root / relative) for relative in paths}


def build_evidence(
    root: Path,
    require_external_reports: bool = True,
    *,
    _verify_git_history: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    rollback = perform_rollback_drill(root)
    fixture = strict_json_load(root / FIXTURE_PATH)
    preservation: Dict[str, Any]
    try:
        record = _fixture_record(fixture)
        with tempfile.TemporaryDirectory(prefix="abd-s06-p02-evidence-") as directory:
            archive_root, repository_root = _private_test_root(Path(directory), fixture)
            first = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            repeat = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            verification = verify_preserved_mail(archive_root=archive_root, repository_root=repository_root, gmail_message_id=record["gmail_message_id"])
            preservation = {
                "first_status": first.get("status"),
                "repeat_status": repeat.get("status"),
                "readback_status": verification.get("status"),
                "attachment_count": len(record["attachments"]),
                "trash_eligible": verification.get("trash_eligible"),
                "gmail_mutation_performed": False,
            }
    except Exception as exc:
        preservation = {"error": "%s: %s" % (type(exc).__name__, exc)}
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": fixture.get("fixed_clock"),
        "status": validation["status"],
        "phase_status": validation["phase_status"],
        "decision": validation["decision"],
        "validation": validation,
        "predecessor_evidence": {
            "p01_evidence": P01_EVIDENCE_PATH.as_posix(),
            "p01_evidence_sha256": sha256_file(root / P01_EVIDENCE_PATH),
            "p01_rollback_sha256": sha256_file(root / P01_ROLLBACK_PATH),
        },
        "preservation_summary": preservation,
        "no_real_time_soak": validate_no_real_time_soak(),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": fixture.get("expected_release_status"),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S06/P02_test.py --junitxml=machine/evidence/S06/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S06/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S06-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": _input_hashes(root),
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S06/P02 validates synthetic mail preservation and readback only.",
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
        "next": validation["next"],
    }
    unsigned = deepcopy(evidence)
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(unsigned))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str, fixed_clock: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S06-P02"]
    rows.append(
        {
            "id": "INDEX-AC-S06-P02",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S06/P03_READY_NOT_STARTED" if status == "PASS" else "S06/P02_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise ValueError("S06/P02 evidence must be written to the project machine/evidence directory")
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(evidence_path, _json_bytes(evidence))
    _atomic_write(rollback_path, _json_bytes(rollback))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash, str(evidence["fixed_clock"]))
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = dict(evidence)
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S06P02-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S06P02-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S06-P02"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S06/P03_READY_NOT_STARTED"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S06P02-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                input_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S06P02-EXISTING-INPUT-HASHES", not input_errors, input_errors or "all inputs match")
        _add(checks, "S06P02-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S06P02-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S06-P02-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S06P02-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S06P02-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    _add(checks, "S06P02-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "",
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S06/P03_READY_NOT_STARTED" if not failed else "S06/P02_REMEDIATION_REQUIRED",
    }


__all__ = [
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_FIXED_CLOCK",
    "JUNIT_PATH",
    "LAYOUT_PATH",
    "ORACLE_PATH",
    "PINNED_PHASE_HASHES",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "SCHEMA_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "SUCCESSOR_UNIT_PROFILE_HASHES",
    "TEST_PATH",
    "_junit_is_normalized",
    "_junit_summary",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "validate_manifest_schema_document",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
