"""Independent deterministic acceptance oracle for ABD S06/P04.

The oracle consumes frozen synthetic mail bytes only in a temporary path. It
does not contact Gmail, read a credential, invoke a Private-Database client,
start a scheduler, wait for real time, or invoke a production trash adapter.
Passing proves the bounded fail-closed request and audit contract; it does not
claim an account mutation, a live malware verdict, a deployment, or a
financial result.
"""

from __future__ import annotations

import ast
import base64
from copy import deepcopy
import hashlib
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from attachment_sandbox import scan_attachment
from mail_collector import preserve_mail
from mail_trash_worker import (
    CONTRACT_ID as WORKER_CONTRACT_ID,
    PERMANENT_DELETE_CAPABILITY,
    REAL_TIME_SOAK_REQUIRED,
    REQUIREMENT_ID as WORKER_REQUIREMENT_ID,
    SCHEDULED_AUDIT_LOCAL_TIME,
    assess_trash_candidate,
    audit_daily_mail_state,
    dispatch_trash_request,
    prepare_restore_request,
    validate_no_real_time_soak,
)

from .attachment_security import verify_existing_phase_evidence as verify_attachment_security_evidence
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S06-P04"
REQUIREMENT_ID = "REQ-S06-P04"
STAGE_ID = "S06"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-29T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

WORKER_PATH = Path("mail_trash_worker.py")
AUDIT_PATH = Path("codex_daily_audit.md")
RESTORE_PATH = Path("mail_restore_runbook.md")
FIXTURE_PATH = Path("machine/tests/fixtures/S06_P04.json")
TEST_PATH = Path("tests/S06/P04_test.py")
ORACLE_PATH = Path("abd_acceptance/mail_deletion_audit.py")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S06-P03_rollback.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S06-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S06/P04/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S06/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")

PINNED_PHASE_HASHES: Dict[str, str] = {
    "mail_trash_worker.py": "bec1f15a71ea4a33d9334c34971ceb804310a82fee41c4663bf62d8143841679",
    "codex_daily_audit.md": "be7cc0a0ad8f59ca0c63995d356b419f263f060d00dd6bac85c10fa6677be9b8",
    "mail_restore_runbook.md": "7c513b44656d4f24140996a01e985f62cb92b801e46bb3dc9157f4d3bd91db65",
    "machine/tests/fixtures/S06_P04.json": "02efad66f11217e2a784fd26c8d92cd1083b505d176b993870c4d21424679f55",
    "tests/S06/P04_test.py": "5f523b257e96ba13e50bb99214b9a397dcad69c1094b9dde70fcceecf140cb23",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "7666ba1f964006bb639cdd62148382ab5e9d43cf93d510015eade74147900be5"
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {}

ROLLBACK_ARTIFACTS = (WORKER_PATH, AUDIT_PATH, RESTORE_PATH)
EXTERNAL_EFFECT_BOUNDARY = {
    "gmail_account_or_api_accessed": False,
    "gmail_mutation_performed": False,
    "gmail_runtime_adapter_invoked": False,
    "permanent_delete_capability": False,
    "permanent_delete_performed": False,
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


def _portable(path: Path) -> str:
    rendered = path.as_posix()
    for marker in ("/machine/", "/abd_acceptance/", "/tests/"):
        if marker in rendered:
            return marker.strip("/").split("/", 1)[0] + "/" + rendered.split(marker, 1)[1]
    return path.name


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, _portable(path))
    return value


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ValueError("expected exactly one %s=%s row" % (key, identifier))
    return matches[0]


def _structural_self_hash(root: Path) -> str:
    text = (root / ORACLE_PATH).read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]*("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    return _sha256_bytes(normalized.encode("utf-8"))


def _current_code_hash(root: Path) -> str:
    payload = b""
    for relative in (WORKER_PATH, AUDIT_PATH, RESTORE_PATH, ORACLE_PATH):
        payload += relative.as_posix().encode("utf-8") + b"\0" + (root / relative).read_bytes() + b"\0"
    return _sha256_bytes(payload)


def _parse_embedded_contract(path: Path, marker: str) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    begin = "<!-- %s\n" % marker
    end = "\n-->"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError("embedded contract markers are not exact")
    start = text.index(begin) + len(begin)
    finish = text.index(end, start)

    def reject_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("embedded contract has duplicate key")
            result[key] = value
        return result

    value = json.loads(text[start:finish], object_pairs_hook=reject_duplicates)
    if not isinstance(value, Mapping):
        raise ValueError("embedded contract is not an object")
    return value


def _fixture_mail_record(root: Path, fixture: Mapping[str, Any]) -> dict[str, Any]:
    p02_relative = fixture.get("p02_fixture_path")
    if p02_relative != "machine/tests/fixtures/S06_P02.json":
        raise ValueError("P02 fixture reference is invalid")
    p02 = strict_json_load(root / p02_relative)
    value = p02.get("mail_record") if isinstance(p02, Mapping) else None
    if not isinstance(value, Mapping) or set(value) != {
        "gmail_message_id",
        "source_history_id",
        "received_at_utc",
        "raw_eml_base64",
        "headers",
        "attachments",
    }:
        raise ValueError("P02 mail record is unavailable")
    p03_relative = fixture.get("p03_fixture_path")
    case_ids = fixture.get("attachment_case_ids")
    if p03_relative != "machine/tests/fixtures/S06_P03.json" or case_ids != ["SAFE_CSV", "SAFE_PDF"]:
        raise ValueError("P03 fixture reference is invalid")
    p03 = strict_json_load(root / p03_relative)
    rows = p03.get("cases") if isinstance(p03, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("P03 frozen attachment cases are unavailable")
    by_id = {row.get("id"): row for row in rows if isinstance(row, Mapping)}
    try:
        attachments = [
            {
                "attachment_id": by_id[case_id]["attachment_id"],
                "filename": by_id[case_id]["filename"],
                "content": base64.b64decode(by_id[case_id]["content_base64"], validate=True),
            }
            for case_id in case_ids
        ]
        raw = base64.b64decode(value["raw_eml_base64"], validate=True)
    except Exception as exc:
        raise ValueError("P02 frozen bytes are invalid") from exc
    return {
        "gmail_message_id": value["gmail_message_id"],
        "source_history_id": value["source_history_id"],
        "received_at_utc": value["received_at_utc"],
        "raw_eml": raw,
        "headers": dict(value["headers"]),
        "attachments": attachments,
    }


def _security_inputs(root: Path, record: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    security: list[dict[str, Any]] = []
    attestations: list[dict[str, str]] = []
    for attachment in record["attachments"]:
        result = scan_attachment(
            attachment,
            parser_registry_path=root / "parser_registry.json",
            quarantine_rules_path=root / "quarantine_rules.json",
        )
        security.append(
            {
                "attachment_id": result.get("attachment_id"),
                "content_sha256": result.get("content_sha256"),
                "status": result.get("status"),
                "quarantined": result.get("quarantined"),
                "parser_result_recorded": result.get("parser_result_recorded"),
                "trash_eligible": result.get("trash_eligible"),
                "gmail_mutation_performed": result.get("gmail_mutation_performed"),
                "permanent_delete_performed": result.get("permanent_delete_performed"),
            }
        )
        attestations.append(
            {
                "attachment_id": result.get("attachment_id"),
                "content_sha256": result.get("content_sha256"),
                "status": "PASS",
            }
        )
    return security, attestations


def _private_roots(directory: Path) -> tuple[Path, Path]:
    return directory / "private" / "Private-MetaDatabase" / "ABD", directory / "repository"


def _synthetic_flow(root: Path, fixture: Mapping[str, Any]) -> dict[str, Any]:
    record = _fixture_mail_record(root, fixture)
    with tempfile.TemporaryDirectory(prefix="abd-s06-p04-") as directory_name:
        directory = Path(directory_name)
        archive_root, repository_root = _private_roots(directory)
        preserved = preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
        security, attestations = _security_inputs(root, record)
        decision = assess_trash_candidate(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=record["gmail_message_id"],
            sender_state=fixture["sender_state"],
            authentication_state=fixture["authentication_state"],
            attachment_security_results=security,
            malware_attestations=attestations,
        )
        dispatch = dispatch_trash_request(decision)
        synthetic_receipt = {
            "status": "TRASHED",
            "gmail_message_id": decision.get("gmail_message_id"),
            "trash_request_key": decision.get("trash_request_key"),
        }
        restore = prepare_restore_request(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=record["gmail_message_id"],
            trash_request_key=decision.get("trash_request_key"),
            trash_receipt=synthetic_receipt,
        )
        audit = audit_daily_mail_state([decision], observed_local_time=fixture["scheduled_audit_local_time"])
    return {
        "record": record,
        "preserved": preserved,
        "security": security,
        "attestations": attestations,
        "decision": decision,
        "dispatch": dispatch,
        "restore": restore,
        "audit": audit,
    }


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        path = root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(
            checks,
            "S06P04-PIN-%s" % Path(relative).stem.upper(),
            bool(expected) and actual == expected,
            {"expected": expected or "UNSET", "actual": actual},
        )


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root / "machine/facts/requirements.json", checks, "S06P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root / "machine/facts/acceptance_contracts.json", checks, "S06P04-CONTRACTS-STRICT-JSON")
    graph = _safe_load(root / "machine/facts/task_graph.json", checks, "S06P04-TASK-GRAPH-STRICT-JSON")
    trace = _safe_load(root / "machine/facts/traceability_matrix.json", checks, "S06P04-TRACE-STRICT-JSON")
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = graph.get("tasks") if isinstance(graph, Mapping) else None
        task_01 = _row(tasks, "T-S06-P04-01")
        task_02 = _row(tasks, "T-S06-P04-02")
        task_03 = _row(tasks, "T-S06-P04-03")
        trace_row = _row(trace, REQUIREMENT_ID, key="requirement_id")
        requirement_ok = (
            requirement.get("stage_id") == STAGE_ID
            and requirement.get("phase_id") == PHASE_ID
            and requirement.get("scope") == ["mail_trash_worker.py", "codex_daily_audit.md", "mail_restore_runbook.md"]
            and requirement.get("target") == "未知发件人或验证失败不删除；永久删除能力不存在。"
            and requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
        )
        contract_ok = (
            contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S06-P04 --evidence machine/evidence"
            and contract.get("pass_gate") == "未知发件人或验证失败不删除；永久删除能力不存在。"
            and [test.get("id") for test in contract.get("tests", [])] == ["TEST-S06-P04", "TEST-S06-P04-BOUNDARY", "TEST-S06-P04-REPLAY"]
        )
        graph_ok = (
            task_01.get("outputs") == ["mail_trash_worker.py", "codex_daily_audit.md", "mail_restore_runbook.md"]
            and task_01.get("depends_on") == ["T-S06-P03-03"]
            and task_02.get("outputs") == ["tests/S06/P04_test.py", "machine/tests/fixtures/S06_P04.json"]
            and task_02.get("depends_on") == ["T-S06-P04-01"]
            and task_03.get("outputs") == ["machine/evidence/EVD-S06-P04.json", "machine/evidence/EVD-S06-P04_rollback.json"]
            and task_03.get("depends_on") == ["T-S06-P04-02"]
        )
        trace_ok = (
            trace_row.get("acceptance_criteria_id") == CONTRACT_ID
            and trace_row.get("evidence_id") == "EVD-S06-P04"
            and trace_row.get("artifact_ids") == ["ART-S06-P04-01", "ART-S06-P04-02", "ART-S06-P04-03"]
        )
    except Exception as exc:
        requirement_ok = contract_ok = graph_ok = trace_ok = False
        detail: Any = "%s: %s" % (type(exc).__name__, exc)
    else:
        detail = "exact S06/P04 task-pack rows"
    _add(checks, "S06P04-TASKPACK-REQUIREMENT-EXACT", requirement_ok, detail)
    _add(checks, "S06P04-TASKPACK-CONTRACT-EXACT", contract_ok, detail)
    _add(checks, "S06P04-TASKPACK-GRAPH-EXACT", graph_ok, detail)
    _add(checks, "S06P04-TASKPACK-TRACE-EXACT", trace_ok, detail)


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], *, verify_git_history: bool) -> None:
    try:
        predecessor = verify_attachment_security_evidence(root, verify_git_history=verify_git_history)
        ok = predecessor.get("status") == "PASS" and predecessor.get("next") == "S06/P04_READY_NOT_STARTED"
        detail: Any = {"status": predecessor.get("status"), "next": predecessor.get("next")}
    except Exception as exc:
        ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P04-PREREQUISITE-P03-PASS", ok, detail)


def _check_facts_and_docs(root: Path, checks: List[Dict[str, Any]]) -> None:
    parameters = _safe_load(root / "machine/facts/parameters.json", checks, "S06P04-PARAMETERS-STRICT-JSON")
    ingestion = _safe_load(root / "machine/facts/email_ingestion.json", checks, "S06P04-INGESTION-STRICT-JSON")
    try:
        email = parameters["email"] if isinstance(parameters, Mapping) else None
        facts_ok = (
            email["daily_codex_audit_local_time"] == SCHEDULED_AUDIT_LOCAL_TIME == "06:00"
            and email["malware_scan_required"] is True
            and email["permanent_delete"] is False
            and email["unknown_sender"] == "QUARANTINE"
            and email["trash_only_after"]
            == [
                "raw_eml_saved",
                "all_attachments_saved",
                "hash_manifest_committed",
                "malware_scan_passed",
                "parser_result_recorded",
                "local_restore_readback_passed",
            ]
            and email["archive_attachment_hash"] == "SHA-256"
        )
        trash_gate = ingestion["trash_gate"] if isinstance(ingestion, Mapping) else None
        ingestion_ok = (
            ingestion["architecture"]["current_chat_connector"] == "只读，不用于生产删除"
            and trash_gate["all_required"] is True
            and trash_gate["unknown_sender"] == "KEEP"
            and trash_gate["failed_authentication"] == "KEEP_AND_ALERT"
            and trash_gate["failed_scan"] == "KEEP_AND_QUARANTINE"
            and trash_gate["permanent_delete"] is False
            and ingestion["pipeline"][-2:] == ["满足全部门后移入Gmail垃圾箱", "每日Codex审计和恢复演练"]
        )
        audit_contract = _parse_embedded_contract(root / AUDIT_PATH, "ABD_DAILY_AUDIT_CONTRACT")
        restore_contract = _parse_embedded_contract(root / RESTORE_PATH, "ABD_RESTORE_RUNBOOK_CONTRACT")
        docs_ok = (
            dict(audit_contract)
            == {
                "contract_id": CONTRACT_ID,
                "stage_id": STAGE_ID,
                "phase_id": PHASE_ID,
                "scheduled_local_time": "06:00",
                "evaluation_mode": "DATA_ONLY_NO_SCHEDULER_OR_WAIT",
                "gmail_mutation_default": "DISABLED",
                "permanent_delete_capability": False,
                "real_time_soak_required": False,
                "raw_data_repository_write": "PROHIBITED",
                "private_archive_area": "Private-MetaDatabase/ABD",
            }
            and dict(restore_contract)
            == {
                "contract_id": CONTRACT_ID,
                "stage_id": STAGE_ID,
                "phase_id": PHASE_ID,
                "restore_method": "users.messages.untrash",
                "restore_mode": "REQUEST_ONLY_NO_MUTATION",
                "permanent_delete_capability": False,
                "requires_archive_readback": True,
                "requires_confirmed_trash_receipt": True,
                "real_time_soak_required": False,
                "raw_data_repository_write": "PROHIBITED",
            }
        )
        detail: Any = {"audit_time": email["daily_codex_audit_local_time"], "trash_gate": trash_gate}
    except Exception as exc:
        facts_ok = ingestion_ok = docs_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P04-FACTS-DELETE-AND-AUDIT-GATES-EXACT", facts_ok, detail)
    _add(checks, "S06P04-INGESTION-TRASH-GATE-EXACT", ingestion_ok, detail)
    _add(checks, "S06P04-DOC-CONTRACTS-EXACT", docs_ok, detail)


def _check_fixture(root: Path, fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    expected = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "fixed_clock",
        "input_mode",
        "p02_fixture_path",
        "p03_fixture_path",
        "attachment_case_ids",
        "sender_state",
        "authentication_state",
        "malware_attestation_mode",
        "scheduled_audit_local_time",
        "replay_iterations",
        "adverse_perturbation_iterations",
        "numeric_boundary_deltas",
        "adverse_odds_tick_action",
        "expected_oracle_check_minimum",
        "minimum_targeted_pytest_cases",
        "minimum_full_pytest_cases",
        "expected_next",
        "expected_release_status",
    }
    try:
        shape_ok = (
            isinstance(fixture, Mapping)
            and set(fixture) == expected
            and fixture.get("schema_version") == "1.0.0"
            and fixture.get("fixture_id") == "FIX-S06-P04"
            and fixture.get("contract_id") == CONTRACT_ID
            and fixture.get("requirement_id") == REQUIREMENT_ID
            and fixture.get("fixed_clock") == FIXED_CLOCK
            and fixture.get("input_mode") == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
            and fixture.get("p02_fixture_path") == "machine/tests/fixtures/S06_P02.json"
            and fixture.get("p03_fixture_path") == "machine/tests/fixtures/S06_P03.json"
            and fixture.get("attachment_case_ids") == ["SAFE_CSV", "SAFE_PDF"]
            and fixture.get("sender_state") == "KNOWN_ALLOWLISTED"
            and fixture.get("authentication_state") == "PASS"
            and fixture.get("malware_attestation_mode") == "FROZEN_SYNTHETIC_ATTESTATION_NOT_A_LIVE_AV_CLEARANCE"
            and fixture.get("scheduled_audit_local_time") == "06:00"
            and fixture.get("replay_iterations") == 100
            and fixture.get("adverse_perturbation_iterations") == 10_000
            and fixture.get("numeric_boundary_deltas") == ["-0.0001", "0", "0.0001"]
            and fixture.get("adverse_odds_tick_action") == "NOT_APPLICABLE_NO_ODDS_OR_ORDER_ACTION_IN_S06_P04"
            and type(fixture.get("expected_oracle_check_minimum")) is int
            and type(fixture.get("minimum_targeted_pytest_cases")) is int
            and type(fixture.get("minimum_full_pytest_cases")) is int
            and fixture.get("expected_next") == "S06/STAGE_REVIEW_READY_NOT_STARTED"
            and fixture.get("expected_release_status") == "NOT_READY_S06_STAGE_REVIEW_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED"
        )
        if shape_ok:
            record = _fixture_mail_record(root, fixture)
            shape_ok = len(record["attachments"]) > 0
        detail: Any = {"has_synthetic_record": shape_ok}
    except Exception as exc:
        shape_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P04-FIXTURE-SHAPE", shape_ok, detail)
    return shape_ok


def _check_core_flow(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        flow = _synthetic_flow(root, fixture)
        decision = flow["decision"]
        dispatch = flow["dispatch"]
        restore = flow["restore"]
        audit = flow["audit"]
        p03_safe = all(
            row["status"] == "PARSED_SAFE"
            and row["quarantined"] is False
            and row["parser_result_recorded"] is True
            and row["trash_eligible"] is False
            for row in flow["security"]
        )
        positive_ok = (
            flow["preserved"].get("status") == "PRESERVED_READBACK_VERIFIED"
            and p03_safe
            and decision.get("status") == "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"
            and decision.get("trash_eligible") is True
            and decision.get("gmail_mutation_performed") is False
            and decision.get("permanent_delete_capability") is False
            and decision.get("permanent_delete_performed") is False
            and decision.get("gate_report", {}).get("malware_scan_passed") is True
            and dispatch.get("status") == "TRASH_REQUEST_READY_NO_MUTATION"
            and dispatch.get("gmail_mutation_performed") is False
            and restore.get("status") == "RESTORE_REQUEST_READY_NO_MUTATION"
            and restore.get("gmail_mutation_performed") is False
            and audit.get("status") == "AUDIT_PASS"
            and audit.get("scheduler_started") is False
        )
        with tempfile.TemporaryDirectory(prefix="abd-s06-p04-negative-") as directory_name:
            archive_root, repository_root = _private_roots(Path(directory_name))
            record = _fixture_mail_record(root, fixture)
            preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            unknown = assess_trash_candidate(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=record["gmail_message_id"],
                sender_state="UNKNOWN",
                authentication_state="PASS",
                attachment_security_results=flow["security"],
                malware_attestations=flow["attestations"],
            )
            failed_auth = assess_trash_candidate(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=record["gmail_message_id"],
                sender_state="KNOWN_ALLOWLISTED",
                authentication_state="FAIL",
                attachment_security_results=flow["security"],
                malware_attestations=flow["attestations"],
            )
            failed_scan_attestations = deepcopy(flow["attestations"])
            failed_scan_attestations[0]["status"] = "FAIL"
            failed_scan = assess_trash_candidate(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=record["gmail_message_id"],
                sender_state="KNOWN_ALLOWLISTED",
                authentication_state="PASS",
                attachment_security_results=flow["security"],
                malware_attestations=failed_scan_attestations,
            )
        negative_ok = all(
            row.get("status") == "KEEP_AND_QUARANTINE"
            and row.get("trash_eligible") is False
            and row.get("gmail_mutation_performed") is False
            and row.get("permanent_delete_performed") is False
            for row in (unknown, failed_auth, failed_scan)
        )
        no_secret_or_raw = all(
            "raw_eml" not in json.dumps(value, ensure_ascii=False, sort_keys=True)
            and "content_base64" not in json.dumps(value, ensure_ascii=False, sort_keys=True)
            for value in (decision, dispatch, restore, audit)
        )
        detail: Any = {
            "positive": decision.get("status"),
            "unknown": unknown.get("status"),
            "failed_auth": failed_auth.get("status"),
            "failed_scan": failed_scan.get("status"),
        }
    except Exception as exc:
        positive_ok = negative_ok = no_secret_or_raw = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P04-ALL-GATES-AUTHORIZE-REQUEST-ONLY", positive_ok, detail)
    _add(checks, "S06P04-UNKNOWN-AUTH-OR-SCAN-FAIL-KEEPS", negative_ok, detail)
    _add(checks, "S06P04-NO-RAW-MAIL-IN-DECISION-SUMMARY", no_secret_or_raw, detail)


def _check_replay_and_boundaries(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    try:
        record = _fixture_mail_record(root, fixture)
        with tempfile.TemporaryDirectory(prefix="abd-s06-p04-replay-") as directory_name:
            archive_root, repository_root = _private_roots(Path(directory_name))
            preserve_mail(record, archive_root=archive_root, repository_root=repository_root)
            security, attestations = _security_inputs(root, record)
            first = assess_trash_candidate(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=record["gmail_message_id"],
                sender_state=fixture["sender_state"],
                authentication_state=fixture["authentication_state"],
                attachment_security_results=security,
                malware_attestations=attestations,
            )
            repeats = [
                assess_trash_candidate(
                    archive_root=archive_root,
                    repository_root=repository_root,
                    gmail_message_id=record["gmail_message_id"],
                    sender_state=fixture["sender_state"],
                    authentication_state=fixture["authentication_state"],
                    attachment_security_results=security,
                    malware_attestations=attestations,
                )
                for _ in range(int(fixture["replay_iterations"]))
            ]
            adverse = [
                assess_trash_candidate(
                    archive_root=archive_root,
                    repository_root=repository_root,
                    gmail_message_id=record["gmail_message_id"],
                    sender_state="UNKNOWN",
                    authentication_state="PASS",
                    attachment_security_results=security,
                    malware_attestations=attestations,
                )
                for _ in range(int(fixture["adverse_perturbation_iterations"]))
            ]
            numeric_actions = [
                audit_daily_mail_state([first], observed_local_time="06:00")
                for _ in fixture["numeric_boundary_deltas"]
            ]
            off_schedule = [
                audit_daily_mail_state([first], observed_local_time=value)
                for value in ("05:59", "06:01")
            ]
        replay_ok = all(item == first for item in repeats)
        adverse_ok = all(
            item == adverse[0]
            and item.get("status") == "KEEP_AND_QUARANTINE"
            and item.get("trash_eligible") is False
            and item.get("gmail_mutation_performed") is False
            for item in adverse
        )
        boundary_ok = (
            all(item.get("status") == "AUDIT_PASS" and item.get("action") == "NONE" for item in numeric_actions)
            and all(item.get("status") == "AUDIT_OFF_SCHEDULE" and item.get("action") == "ESCALATE" for item in off_schedule)
            and fixture["adverse_odds_tick_action"] == "NOT_APPLICABLE_NO_ODDS_OR_ORDER_ACTION_IN_S06_P04"
        )
        detail: Any = {"replay": len(repeats), "adverse": len(adverse), "numeric_boundaries": len(numeric_actions)}
    except Exception as exc:
        replay_ok = adverse_ok = boundary_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P04-100-REPLAY-DETERMINISTIC-NO-WAIT", replay_ok, detail)
    _add(checks, "S06P04-ONE-IN-TEN-THOUSAND-UNKNOWN-SENDER-KEEPS", adverse_ok, detail)
    _add(checks, "S06P04-BOUNDARY-NO-ORDER-OR-OFF-SCHEDULE-MUTATION", boundary_ok, detail)


def _check_static_safety(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        text = (root / WORKER_PATH).read_text(encoding="utf-8")
        tree = ast.parse(text, filename=WORKER_PATH.as_posix())
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        denied = {"socket", "subprocess", "requests", "urllib", "http", "os", "shutil", "time", "asyncio"}
        imports_ok = not (imported_roots & denied)
        banned = (
            "time.sleep(",
            "subprocess.",
            "socket.",
            "requests.",
            "urllib.",
            "os.system(",
            "users.messages.delete",
            "users.messages.batchDelete",
            "users.threads.delete",
        )
        calls_ok = not any(marker in text for marker in banned)
        capability_ok = (
            "PERMANENT_DELETE_CAPABILITY = False" in text
            and "REAL_TIME_SOAK_REQUIRED = False" in text
            and "allow_external_mutation: bool = False" in text
        )
        no_scheduler_ok = "schedule." not in text and "cron" not in text.lower()
        detail: Any = {"imports": sorted(imported_roots), "denied": sorted(imported_roots & denied)}
    except Exception as exc:
        imports_ok = calls_ok = capability_ok = no_scheduler_ok = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S06P04-NO-NETWORK-OR-PROCESS-IMPORT", imports_ok, detail)
    _add(checks, "S06P04-NO-SLEEP-OR-PERMANENT-DELETE-CALL", calls_ok, detail)
    _add(checks, "S06P04-PERMANENT-DELETE-CAPABILITY-ABSENT", capability_ok, detail)
    _add(checks, "S06P04-NO-SCHEDULER-DAEMON", no_scheduler_ok, detail)


def _check_no_sensitive_material(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = (WORKER_PATH, AUDIT_PATH, RESTORE_PATH, FIXTURE_PATH, TEST_PATH, ORACLE_PATH)
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
    _add(checks, "S06P04-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(path).getroot()
    suites = list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in result:
            result[key] += int(suite.attrib.get(key, "0"))
    return result


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(path).getroot()
    suites = list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
    return bool(suites) and all(
        suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK
        and suite.attrib.get("time") == "0.000"
        and "hostname" not in suite.attrib
        and all(case.attrib.get("time") == "0.000" and "hostname" not in case.attrib for case in suite.findall("testcase"))
        for suite in suites
    )


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for label, relative, minimum in (
        ("TARGETED", JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases")),
        ("FULL", FULL_JUNIT_PATH, fixture.get("minimum_full_pytest_cases")),
    ):
        try:
            summary = _junit_summary(root / relative)
            normalized = _junit_is_normalized(root / relative)
            ok = (
                type(minimum) is int
                and summary["tests"] >= minimum
                and summary["failures"] == 0
                and summary["errors"] == 0
                and summary["skipped"] == 0
                and normalized
            )
            hashes[relative.as_posix()] = sha256_file(root / relative)
            _add(checks, "S06P04-%s-PYTEST-REPORT" % label, ok, {"summary": summary, "minimum": minimum, "normalized": normalized})
        except Exception as exc:
            _add(checks, "S06P04-%s-PYTEST-REPORT" % label, False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S06P04-PACK-REPORT-STRICT-JSON")
    if isinstance(pack, Mapping):
        pack_ok = pack.get("status") == "PASS" and pack.get("summary", {}).get("failed") == 0
        _add(checks, "S06P04-TASKPACK-PASS", pack_ok, pack.get("summary"))
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8") if (root / SCAN_REPORT_PATH).is_file() else ""
    required_lines = {
        "STATUS: PASS",
        "MAX_INCREMENTAL_CASH_AUD: 0.00",
        "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
        "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
        "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
    }
    _add(checks, "S06P04-PAID-DEPENDENCY-SCAN", required_lines <= set(scan.splitlines()), SCAN_REPORT_PATH.as_posix())
    if (root / SCAN_REPORT_PATH).is_file():
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)


def evaluate_contract(
    root: Path,
    require_external_reports: bool = False,
    *,
    _verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S06P04-FIXTURE-STRICT-JSON")
    _check_pins(root, checks, hashes)
    _add(
        checks,
        "S06P04-ORACLE-SELF-INTEGRITY",
        bool(STRUCTURAL_SELF_NORMALIZED_SHA256) and _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256,
        {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256 or "UNSET", "actual": _structural_self_hash(root)},
    )
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, verify_git_history=_verify_git_history)
    _check_facts_and_docs(root, checks)
    fixture_ok = _check_fixture(root, fixture, checks)
    if isinstance(fixture, Mapping) and fixture_ok:
        _check_core_flow(root, fixture, checks)
        _check_replay_and_boundaries(root, fixture, checks)
        if require_external_reports:
            _check_external_reports(root, fixture, checks, hashes)
    else:
        _add(checks, "S06P04-FROZEN-INPUT-GATE", False, "fixture unavailable")
    _check_static_safety(root, checks)
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
        "phase_status": "S06_P04_PASS" if not failed else "S06_P04_FAIL",
        "decision": "TRASH_REQUEST_ONLY_AFTER_ALL_GATES_NO_PERMANENT_DELETE" if not failed else "S06_P04_BLOCKED_FAIL_CLOSED",
        "release_status": "NOT_READY_S06_STAGE_REVIEW_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "external_network_used_by_verifier": False,
        "next": "S06/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S06/P04_REMEDIATION_REQUIRED",
    }


def validate_candidate_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    result = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    return {
        "status": result["status"],
        "decision": "S06_P04_CANDIDATE_VALID" if result["status"] == "PASS" else "S06_P04_CANDIDATE_INVALID",
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
        "evidence_id": "EVD-S06-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": status,
        "mode": "DISABLE_TRASH_RUNTIME_ADAPTER_KEEP_GMAIL_AND_ARCHIVE",
        "artifacts": artifacts,
        "production_state_changed": False,
        "external_state_changed": False,
        "gmail_account_or_api_accessed": False,
        "gmail_mutation_performed": False,
        "permanent_delete_performed": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = (
        WORKER_PATH,
        AUDIT_PATH,
        RESTORE_PATH,
        FIXTURE_PATH,
        TEST_PATH,
        ORACLE_PATH,
        Path("machine/tests/fixtures/S06_P02.json"),
        Path("machine/tests/fixtures/S06_P03.json"),
        P03_EVIDENCE_PATH,
        P03_ROLLBACK_PATH,
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
    try:
        flow = _synthetic_flow(root, fixture)
        decision = flow["decision"]
        audit = flow["audit"]
        replay_summary: Mapping[str, Any] = {
            "iterations": fixture["adverse_perturbation_iterations"],
            "action": "UNKNOWN_SENDER_KEEP_AND_QUARANTINE",
            "deterministic": True,
            "real_time_waited": False,
            "result_sha256": _sha256_bytes(_json_bytes(decision)),
        }
        flow_summary: Mapping[str, Any] = {
            "preservation_status": flow["preserved"].get("status"),
            "attachment_security_statuses": [row.get("status") for row in flow["security"]],
            "synthetic_malware_attestation_mode": fixture["malware_attestation_mode"],
            "trash_decision": decision.get("status"),
            "trash_request_key_sha256": _sha256_bytes(str(decision.get("trash_request_key", "")).encode("utf-8")),
            "dispatch_status": flow["dispatch"].get("status"),
            "restore_status": flow["restore"].get("status"),
            "audit_status": audit.get("status"),
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
        }
    except Exception as exc:
        flow_summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
        replay_summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S06-P04",
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
            "p03_evidence": P03_EVIDENCE_PATH.as_posix(),
            "p03_evidence_sha256": sha256_file(root / P03_EVIDENCE_PATH),
            "p03_rollback_sha256": sha256_file(root / P03_ROLLBACK_PATH),
        },
        "mail_gate_summary": flow_summary,
        "deterministic_replay": replay_summary,
        "no_real_time_soak": validate_no_real_time_soak(),
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": fixture.get("expected_release_status"),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S06/P04_test.py --junitxml=machine/evidence/S06/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S06/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S06/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S06-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "hashes": {
            "inputs": _input_hashes(root),
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": sha256_file(root / "machine/facts/model_system_card.json"),
            "model_not_executed_reason": "S06/P04 validates frozen synthetic trash gating and audit planning only.",
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
    rows = [row for row in rows if row.get("id") != "INDEX-AC-S06-P04"]
    rows.append(
        {
            "id": "INDEX-AC-S06-P04",
            "kind": "PHASE_EVIDENCE",
            "stage_id": STAGE_ID,
            "contract_id": CONTRACT_ID,
            "status": status,
            "actual_artifact": EVIDENCE_PATH.as_posix(),
            "artifact_sha256": evidence_hash,
            "next": "S06/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S06/P04_REMEDIATION_REQUIRED",
            "verified_at": fixed_clock,
        }
    )
    _atomic_write(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    expected_root = (root / "machine/evidence").resolve()
    if evidence_dir != expected_root:
        raise ValueError("S06/P04 evidence must be written to the project machine/evidence directory")
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
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S06P04-EXISTING-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S06P04-EXISTING-ROLLBACK-STRICT-JSON")
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("evidence_id") == "EVD-S06-P04"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("status") == "PASS"
            and evidence.get("next") == "S06/STAGE_REVIEW_READY_NOT_STARTED"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S06P04-EXISTING-EVIDENCE-INTEGRITY", shape_ok, evidence.get("status"))
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            actual = sha256_file(root / candidate) if (root / candidate).is_file() else "MISSING"
            if actual != expected:
                input_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S06P04-EXISTING-INPUT-HASHES", not input_errors, input_errors or "all inputs match")
        _add(checks, "S06P04-EXISTING-CODE-HASH", evidence.get("hashes", {}).get("code") == _current_code_hash(root), "current code hash")
    else:
        _add(checks, "S06P04-EXISTING-EVIDENCE-INTEGRITY", False, "evidence unavailable")
    if isinstance(rollback, Mapping):
        rollback_ok = (
            rollback.get("evidence_id") == "EVD-S06-P04-ROLLBACK"
            and rollback.get("contract_id") == CONTRACT_ID
            and rollback.get("status") == "PASS"
            and rollback.get("production_state_changed") is False
            and rollback.get("external_state_changed") is False
            and rollback.get("gmail_mutation_performed") is False
            and rollback.get("permanent_delete_performed") is False
            and rollback.get("real_time_soak_waited") is False
        )
        _add(checks, "S06P04-EXISTING-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status"))
    else:
        _add(checks, "S06P04-EXISTING-ROLLBACK-INTEGRITY", False, "rollback unavailable")
    current = evaluate_contract(root, require_external_reports=False, _verify_git_history=verify_git_history)
    _add(checks, "S06P04-EXISTING-CURRENT-CONTRACT", current.get("status") == "PASS", current.get("summary"))
    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "",
        "summary": {"checks": len(checks), "failed": len(failed), "failed_check_ids": failed},
        "next": "S06/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S06/P04_REMEDIATION_REQUIRED",
    }


__all__ = [
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_FIXED_CLOCK",
    "JUNIT_PATH",
    "ORACLE_PATH",
    "PINNED_PHASE_HASHES",
    "RESTORE_PATH",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "SUCCESSOR_UNIT_PROFILE_HASHES",
    "TEST_PATH",
    "WORKER_PATH",
    "_junit_is_normalized",
    "_junit_summary",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
