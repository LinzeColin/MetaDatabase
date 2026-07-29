"""Fail-closed Gmail-trash gating, audit planning, and restore planning for S06/P04.

This module never opens a network connection, reads credentials, starts a
scheduler, permanently deletes data, or waits for real time. It verifies a
previously preserved private-plane bundle and emits an idempotent Gmail-trash
request only when every supplied gate is true. A separately deployed runtime
adapter may consume that request after its own authorization boundary; tests
use no such adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from abd_acceptance.gmail_oauth_core import validate_gmail_method
from mail_collector import (
    PRIVATE_DATABASE_AREA,
    REAL_TIME_SOAK_REQUIRED as PRESERVATION_REAL_TIME_SOAK_REQUIRED,
    restore_for_readback,
    verify_preserved_mail,
)


VERSION = "0.0.0.1"
CONTRACT_ID = "AC-S06-P04"
REQUIREMENT_ID = "REQ-S06-P04"
SCHEDULED_AUDIT_LOCAL_TIME = "06:00"
TRASH_METHOD = "users.messages.trash"
UNTRASH_METHOD = "users.messages.untrash"
PERMANENT_DELETE_CAPABILITY = False
REAL_TIME_SOAK_REQUIRED = False

_IDENTIFIER_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_LOCAL_TIME_RE = re.compile(r"\A(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")


class MailTrashWorkerError(ValueError):
    """Raised by explicit validators before a candidate becomes trash-eligible."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or isinstance(value, bool) or not _IDENTIFIER_RE.fullmatch(value):
        raise MailTrashWorkerError("%s is malformed" % field)
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise MailTrashWorkerError("%s must be lowercase SHA-256" % field)
    return value


def _strict_keys(value: Any, expected: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise MailTrashWorkerError("%s fields are not exact" % field)
    return value


def _reason_codes(values: Sequence[str]) -> list[str]:
    return sorted(set(str(value) for value in values))


def _keep_result(
    *,
    gmail_message_id: str,
    reason_codes: Sequence[str],
    gate_report: Mapping[str, Any],
    request_key: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "gmail_message_id": gmail_message_id,
        "status": "KEEP_AND_QUARANTINE",
        "reason_codes": _reason_codes(reason_codes) or ["UNSPECIFIED_KEEP"],
        "trash_eligible": False,
        "trash_request_key": request_key,
        "gmail_method": None,
        "gmail_mutation_performed": False,
        "permanent_delete_capability": PERMANENT_DELETE_CAPABILITY,
        "permanent_delete_performed": False,
        "real_time_soak_waited": False,
        "gate_report": dict(gate_report),
    }


def _validate_sender_gate(sender_state: Any, authentication_state: Any) -> tuple[bool, list[str], dict[str, Any]]:
    allowed_sender_states = {"KNOWN_ALLOWLISTED", "UNKNOWN", "KNOWN_UNVERIFIED"}
    allowed_authentication_states = {"PASS", "FAIL", "UNKNOWN"}
    reasons: list[str] = []
    if sender_state not in allowed_sender_states:
        reasons.append("SENDER_STATE_INVALID_KEEP")
    elif sender_state != "KNOWN_ALLOWLISTED":
        reasons.append("UNKNOWN_OR_UNVERIFIED_SENDER_KEEP")
    if authentication_state not in allowed_authentication_states:
        reasons.append("AUTHENTICATION_STATE_INVALID_KEEP")
    elif authentication_state != "PASS":
        reasons.append("AUTHENTICATION_FAILED_OR_UNKNOWN_KEEP")
    return not reasons, reasons, {
        "known_sender_allowlisted": sender_state == "KNOWN_ALLOWLISTED",
        "authentication_passed": authentication_state == "PASS",
    }


def _normalize_security_results(value: Any, restored_attachments: Sequence[Mapping[str, Any]]) -> tuple[bool, list[str], list[dict[str, str]]]:
    if not isinstance(value, list) or not value:
        return False, ["PARSER_RESULTS_MISSING_KEEP"], []
    restored = {
        _require_identifier(row.get("attachment_id"), "restored attachment_id"): _sha256_bytes(row.get("content", b""))
        for row in restored_attachments
        if isinstance(row, Mapping)
    }
    reasons: list[str] = []
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in value:
        try:
            item = _strict_keys(
                row,
                {
                    "attachment_id",
                    "content_sha256",
                    "status",
                    "quarantined",
                    "parser_result_recorded",
                    "trash_eligible",
                    "gmail_mutation_performed",
                    "permanent_delete_performed",
                },
                "attachment security result",
            )
            attachment_id = _require_identifier(item["attachment_id"], "attachment_id")
            digest = _require_sha256(item["content_sha256"], "content_sha256")
            if attachment_id in seen:
                raise MailTrashWorkerError("attachment security result is duplicated")
            seen.add(attachment_id)
            if (
                item["status"] != "PARSED_SAFE"
                or item["quarantined"] is not False
                or item["parser_result_recorded"] is not True
                or item["trash_eligible"] is not False
                or item["gmail_mutation_performed"] is not False
                or item["permanent_delete_performed"] is not False
            ):
                reasons.append("PARSER_RESULT_NOT_SAFE_KEEP")
            if restored.get(attachment_id) != digest:
                reasons.append("PARSER_RESULT_HASH_MISMATCH_KEEP")
            normalized.append({"attachment_id": attachment_id, "content_sha256": digest})
        except Exception:
            reasons.append("PARSER_RESULT_INVALID_KEEP")
    if set(restored) != seen:
        reasons.append("PARSER_RESULT_COVERAGE_MISMATCH_KEEP")
    return not reasons, _reason_codes(reasons), sorted(normalized, key=lambda row: row["attachment_id"])


def _normalize_malware_attestations(value: Any, expected: Sequence[Mapping[str, str]]) -> tuple[bool, list[str], list[dict[str, str]]]:
    if not isinstance(value, list) or not value:
        return False, ["MALWARE_ATTESTATION_MISSING_KEEP"], []
    expected_by_id = {row["attachment_id"]: row["content_sha256"] for row in expected}
    normalized: list[dict[str, str]] = []
    reasons: list[str] = []
    seen: set[str] = set()
    for row in value:
        try:
            item = _strict_keys(row, {"attachment_id", "content_sha256", "status"}, "malware attestation")
            attachment_id = _require_identifier(item["attachment_id"], "attachment_id")
            digest = _require_sha256(item["content_sha256"], "content_sha256")
            if attachment_id in seen:
                raise MailTrashWorkerError("malware attestation is duplicated")
            seen.add(attachment_id)
            if item["status"] != "PASS":
                reasons.append("MALWARE_SCAN_NOT_PASSED_KEEP")
            if expected_by_id.get(attachment_id) != digest:
                reasons.append("MALWARE_ATTESTATION_HASH_MISMATCH_KEEP")
            normalized.append({"attachment_id": attachment_id, "content_sha256": digest})
        except Exception:
            reasons.append("MALWARE_ATTESTATION_INVALID_KEEP")
    if set(expected_by_id) != seen:
        reasons.append("MALWARE_ATTESTATION_COVERAGE_MISMATCH_KEEP")
    return not reasons, _reason_codes(reasons), sorted(normalized, key=lambda row: row["attachment_id"])


def _request_key(gmail_message_id: str, security: Sequence[Mapping[str, str]], attestations: Sequence[Mapping[str, str]]) -> str:
    return _sha256_bytes(
        _json_bytes(
            {
                "contract_id": CONTRACT_ID,
                "gmail_message_id": gmail_message_id,
                "security": list(security),
                "malware_attestations": list(attestations),
            }
        )
    )


def assess_trash_candidate(
    *,
    archive_root: Path | str,
    repository_root: Path | str,
    gmail_message_id: Any,
    sender_state: Any,
    authentication_state: Any,
    attachment_security_results: Any,
    malware_attestations: Any,
) -> dict[str, Any]:
    """Return a Gmail-trash request only after every non-destructive gate passes."""

    try:
        message_id = _require_identifier(gmail_message_id, "gmail_message_id")
    except Exception:
        return _keep_result(
            gmail_message_id="INVALID_MESSAGE",
            reason_codes=["GMAIL_MESSAGE_ID_INVALID_KEEP"],
            gate_report={"archive_readback_passed": False},
        )
    reasons: list[str] = []
    sender_ok, sender_reasons, sender_report = _validate_sender_gate(sender_state, authentication_state)
    reasons.extend(sender_reasons)
    if not sender_ok:
        return _keep_result(
            gmail_message_id=message_id,
            reason_codes=reasons,
            gate_report={
                "archive_readback_passed": False,
                "known_sender_allowlisted": sender_report["known_sender_allowlisted"],
                "authentication_passed": sender_report["authentication_passed"],
                "all_attachments_saved_and_hashed": False,
                "parser_result_recorded_and_safe": False,
                "malware_scan_passed": False,
                "permanent_delete_capability": PERMANENT_DELETE_CAPABILITY,
                "private_database_area": PRIVATE_DATABASE_AREA,
                "real_time_soak_waited": False,
            },
        )
    try:
        archive_verification = verify_preserved_mail(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=message_id,
        )
        archive_ok = archive_verification.get("status") == "PASS" and archive_verification.get("readback_verified") is True
        if not archive_ok:
            reasons.append("ARCHIVE_OR_READBACK_VERIFICATION_FAILED_KEEP")
            restored: Mapping[str, Any] = {"attachments": []}
        else:
            restored = restore_for_readback(
                archive_root=archive_root,
                repository_root=repository_root,
                gmail_message_id=message_id,
            )
    except Exception:
        archive_ok = False
        restored = {"attachments": []}
        reasons.append("ARCHIVE_OR_READBACK_VERIFICATION_FAILED_KEEP")
    try:
        security_ok, security_reasons, security = _normalize_security_results(
            attachment_security_results,
            restored.get("attachments", []),
        )
    except Exception:
        security_ok, security_reasons, security = False, ["PARSER_RESULT_INVALID_KEEP"], []
    reasons.extend(security_reasons)
    try:
        malware_ok, malware_reasons, attestations = _normalize_malware_attestations(malware_attestations, security)
    except Exception:
        malware_ok, malware_reasons, attestations = False, ["MALWARE_ATTESTATION_INVALID_KEEP"], []
    reasons.extend(malware_reasons)
    request_key = _request_key(message_id, security, attestations) if security and attestations else ""
    gate_report = {
        "archive_readback_passed": archive_ok,
        "known_sender_allowlisted": sender_report["known_sender_allowlisted"],
        "authentication_passed": sender_report["authentication_passed"],
        "all_attachments_saved_and_hashed": archive_ok,
        "parser_result_recorded_and_safe": security_ok,
        "malware_scan_passed": malware_ok,
        "permanent_delete_capability": PERMANENT_DELETE_CAPABILITY,
        "private_database_area": PRIVATE_DATABASE_AREA,
        "real_time_soak_waited": False,
    }
    if reasons or not (archive_ok and sender_ok and security_ok and malware_ok):
        return _keep_result(
            gmail_message_id=message_id,
            reason_codes=reasons,
            gate_report=gate_report,
            request_key=request_key,
        )
    validate_gmail_method(TRASH_METHOD)
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "gmail_message_id": message_id,
        "status": "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER",
        "reason_codes": [],
        "trash_eligible": True,
        "trash_request_key": request_key,
        "gmail_method": TRASH_METHOD,
        "gmail_mutation_performed": False,
        "permanent_delete_capability": PERMANENT_DELETE_CAPABILITY,
        "permanent_delete_performed": False,
        "real_time_soak_waited": False,
        "gate_report": gate_report,
    }


def dispatch_trash_request(
    decision: Any,
    *,
    completed_request_keys: Sequence[Any] = (),
    runtime_adapter: Callable[[Mapping[str, str]], Mapping[str, Any]] | None = None,
    allow_external_mutation: bool = False,
) -> dict[str, Any]:
    """Dispatch an authorized request only through an explicit runtime adapter."""

    try:
        item = _strict_keys(
            decision,
            {
                "schema_version",
                "contract_id",
                "requirement_id",
                "gmail_message_id",
                "status",
                "reason_codes",
                "trash_eligible",
                "trash_request_key",
                "gmail_method",
                "gmail_mutation_performed",
                "permanent_delete_capability",
                "permanent_delete_performed",
                "real_time_soak_waited",
                "gate_report",
            },
            "trash decision",
        )
        message_id = _require_identifier(item["gmail_message_id"], "gmail_message_id")
        request_key = _require_sha256(item["trash_request_key"], "trash_request_key")
        valid = (
            item["contract_id"] == CONTRACT_ID
            and item["requirement_id"] == REQUIREMENT_ID
            and item["status"] == "TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER"
            and item["trash_eligible"] is True
            and item["gmail_method"] == TRASH_METHOD
            and item["gmail_mutation_performed"] is False
            and item["permanent_delete_capability"] is False
            and item["permanent_delete_performed"] is False
            and item["real_time_soak_waited"] is False
        )
    except Exception:
        return {
            "status": "KEEP_NOT_DISPATCHED",
            "reason_codes": ["TRASH_DECISION_INVALID_KEEP"],
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
            "real_time_soak_waited": False,
        }
    if not valid:
        return {
            "status": "KEEP_NOT_DISPATCHED",
            "reason_codes": ["TRASH_DECISION_NOT_ELIGIBLE_KEEP"],
            "gmail_message_id": message_id,
            "trash_request_key": request_key,
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
            "real_time_soak_waited": False,
        }
    completed = {key for key in completed_request_keys if isinstance(key, str) and _SHA256_RE.fullmatch(key)}
    if request_key in completed:
        return {
            "status": "IDEMPOTENT_ALREADY_DISPATCHED",
            "reason_codes": [],
            "gmail_message_id": message_id,
            "trash_request_key": request_key,
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
            "real_time_soak_waited": False,
        }
    request = {"gmail_method": TRASH_METHOD, "gmail_message_id": message_id, "trash_request_key": request_key}
    if not allow_external_mutation or runtime_adapter is None:
        return {
            "status": "TRASH_REQUEST_READY_NO_MUTATION",
            "reason_codes": [],
            "request": request,
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
            "real_time_soak_waited": False,
        }
    try:
        receipt = runtime_adapter(request)
        adapter_ok = (
            isinstance(receipt, Mapping)
            and set(receipt) == {"status", "gmail_message_id", "trash_request_key"}
            and receipt.get("status") == "TRASHED"
            and receipt.get("gmail_message_id") == message_id
            and receipt.get("trash_request_key") == request_key
        )
    except Exception:
        adapter_ok = False
    if not adapter_ok:
        return {
            "status": "TRASH_ADAPTER_FAILED_KEEP",
            "reason_codes": ["RUNTIME_ADAPTER_FAILED_KEEP"],
            "request": request,
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
            "real_time_soak_waited": False,
        }
    return {
        "status": "TRASH_ADAPTER_REPORTED_SUCCESS",
        "reason_codes": [],
        "request": request,
        "receipt": {
            "status": "TRASHED",
            "gmail_message_id": message_id,
            "trash_request_key": request_key,
        },
        "gmail_mutation_performed": True,
        "permanent_delete_performed": False,
        "real_time_soak_waited": False,
    }


def audit_daily_mail_state(
    decisions: Any,
    *,
    scheduled_local_time: Any = SCHEDULED_AUDIT_LOCAL_TIME,
    observed_local_time: Any = SCHEDULED_AUDIT_LOCAL_TIME,
) -> dict[str, Any]:
    """Audit sanitized decision metadata as data; never start or wait for a scheduler."""

    if scheduled_local_time != SCHEDULED_AUDIT_LOCAL_TIME or not isinstance(observed_local_time, str) or not _LOCAL_TIME_RE.fullmatch(observed_local_time):
        return {
            "status": "AUDIT_CONFIGURATION_INVALID",
            "action": "ESCALATE",
            "findings": ["AUDIT_TIME_CONFIGURATION_INVALID"],
            "real_time_waited": False,
            "scheduler_started": False,
        }
    if observed_local_time != SCHEDULED_AUDIT_LOCAL_TIME:
        return {
            "status": "AUDIT_OFF_SCHEDULE",
            "action": "ESCALATE",
            "findings": ["AUDIT_NOT_EVALUATED_AT_0600"],
            "real_time_waited": False,
            "scheduler_started": False,
        }
    if not isinstance(decisions, list):
        return {
            "status": "AUDIT_INPUT_INVALID",
            "action": "ESCALATE",
            "findings": ["DECISIONS_INPUT_INVALID"],
            "real_time_waited": False,
            "scheduler_started": False,
        }
    findings: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for row in decisions:
        if not isinstance(row, Mapping):
            findings.append({"code": "DECISION_RECORD_INVALID", "reference": "UNKNOWN"})
            continue
        message_id = row.get("gmail_message_id")
        request_key = row.get("trash_request_key")
        status = row.get("status")
        if not isinstance(message_id, str) or not _IDENTIFIER_RE.fullmatch(message_id):
            findings.append({"code": "DECISION_MESSAGE_ID_INVALID", "reference": "UNKNOWN"})
            continue
        if isinstance(request_key, str) and _SHA256_RE.fullmatch(request_key):
            if request_key in seen_keys:
                findings.append({"code": "DUPLICATE_TRASH_REQUEST_KEY", "reference": message_id})
            seen_keys.add(request_key)
        if status == "KEEP_AND_QUARANTINE":
            findings.append({"code": "KEEP_REQUIRES_REMEDIATION", "reference": message_id})
        elif status not in {"TRASH_AUTHORIZED_PENDING_RUNTIME_ADAPTER", "TRASH_REQUEST_READY_NO_MUTATION", "IDEMPOTENT_ALREADY_DISPATCHED", "TRASH_ADAPTER_REPORTED_SUCCESS"}:
            findings.append({"code": "DECISION_STATUS_UNRECOGNISED", "reference": message_id})
    findings = sorted(findings, key=lambda row: (row["code"], row["reference"]))
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "scheduled_local_time": SCHEDULED_AUDIT_LOCAL_TIME,
        "observed_local_time": observed_local_time,
        "on_schedule": observed_local_time == SCHEDULED_AUDIT_LOCAL_TIME,
        "status": "AUDIT_PASS" if not findings else "AUDIT_REMEDIATION_REQUIRED",
        "action": "NONE" if not findings else "ESCALATE",
        "findings": findings,
        "real_time_waited": False,
        "scheduler_started": False,
        "gmail_mutation_performed": False,
        "permanent_delete_performed": False,
    }


def prepare_restore_request(
    *,
    archive_root: Path | str,
    repository_root: Path | str,
    gmail_message_id: Any,
    trash_request_key: Any,
    trash_receipt: Any,
) -> dict[str, Any]:
    """Produce a non-mutating untrash request after an archive readback check."""

    try:
        message_id = _require_identifier(gmail_message_id, "gmail_message_id")
        request_key = _require_sha256(trash_request_key, "trash_request_key")
        archive = verify_preserved_mail(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=message_id,
        )
        archive_ok = archive.get("status") == "PASS" and archive.get("readback_verified") is True
    except Exception:
        message_id = "INVALID_MESSAGE"
        request_key = ""
        archive_ok = False
    receipt_ok = (
        isinstance(trash_receipt, Mapping)
        and set(trash_receipt) == {"status", "gmail_message_id", "trash_request_key"}
        and trash_receipt.get("status") == "TRASHED"
        and trash_receipt.get("gmail_message_id") == message_id
        and trash_receipt.get("trash_request_key") == request_key
    )
    if not receipt_ok or not archive_ok:
        return {
            "status": "RESTORE_BLOCKED_KEEP",
            "reason_codes": ["RESTORE_REQUIRES_TRASH_RECEIPT_AND_ARCHIVE_READBACK"],
            "gmail_mutation_performed": False,
            "permanent_delete_performed": False,
            "real_time_soak_waited": False,
        }
    validate_gmail_method(UNTRASH_METHOD)
    return {
        "status": "RESTORE_REQUEST_READY_NO_MUTATION",
        "gmail_message_id": message_id,
        "trash_request_key": request_key,
        "gmail_method": UNTRASH_METHOD,
        "gmail_mutation_performed": False,
        "permanent_delete_performed": False,
        "real_time_soak_waited": False,
    }


def validate_no_real_time_soak() -> dict[str, Any]:
    return {
        "real_time_soak_required": REAL_TIME_SOAK_REQUIRED,
        "p02_real_time_soak_required": PRESERVATION_REAL_TIME_SOAK_REQUIRED,
        "scheduled_audit_local_time": SCHEDULED_AUDIT_LOCAL_TIME,
        "audit_evaluated_as_data": True,
        "real_time_wait_performed": False,
        "scheduler_started": False,
    }


__all__ = [
    "CONTRACT_ID",
    "MailTrashWorkerError",
    "PERMANENT_DELETE_CAPABILITY",
    "REAL_TIME_SOAK_REQUIRED",
    "REQUIREMENT_ID",
    "SCHEDULED_AUDIT_LOCAL_TIME",
    "TRASH_METHOD",
    "UNTRASH_METHOD",
    "assess_trash_candidate",
    "audit_daily_mail_state",
    "dispatch_trash_request",
    "prepare_restore_request",
    "validate_no_real_time_soak",
]
