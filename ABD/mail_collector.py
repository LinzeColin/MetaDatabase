"""Fail-closed, private-plane mail preservation primitives for ABD S06/P02.

This module accepts already-fetched synthetic or runtime-supplied mail bytes.
It deliberately does not authenticate to Gmail, open a network connection,
start a scheduler, move a message to Gmail trash, or wait in real time.  It
only creates an immutable local bundle in a caller-provided Private-Database
staging root, verifies it by reading it back, and returns a ``KEEP`` decision
for every outcome.  S06/P03 and S06/P04 own security parsing and Gmail trash
mutation respectively.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from abd_acceptance.canonical_facts import strict_json_load
from abd_acceptance.gmail_oauth_core import archive_idempotency_key, normalize_attachment_record


VERSION = "0.0.0.1"
CONTRACT_ID = "AC-S06-P02"
REQUIREMENT_ID = "REQ-S06-P02"
MANIFEST_SCHEMA_VERSION = "1.0.0"
ARCHIVE_LAYOUT_VERSION = "1.0.0"
COLLECTOR_INTERVAL_SECONDS = 900
REAL_TIME_SOAK_REQUIRED = False
PRIVATE_DATABASE_AREA = "Private-MetaDatabase"
PRIVATE_DATABASE_DOMAIN = "ABD-mail-archive"
ARCHIVE_DIRECTORY_NAME = "mail-archive-v0.0.0.1"
ARCHIVE_STATUS = "PRESERVED_PENDING_S06_P03_AND_P04"
TRASH_ACTION = "KEEP_PENDING_SECURITY_AND_TRASH_GATES"

_IDENTIFIER_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_HISTORY_ID_RE = re.compile(r"\A(?:0|[1-9][0-9]{0,38})\Z")
_UTC_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_HEADER_NAME_RE = re.compile(r"\A[A-Za-z0-9-]{1,78}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class MailCollectorError(ValueError):
    """Raised for malformed preservation inputs before a final bundle exists."""


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or isinstance(value, bool) or not _IDENTIFIER_RE.fullmatch(value):
        raise MailCollectorError("%s is malformed" % field)
    return value


def _require_bytes(value: Any, field: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise MailCollectorError("%s must be non-empty bytes" % field)
    return value


def _require_utc(value: Any) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        raise MailCollectorError("received_at_utc must be one UTC second timestamp")
    return value


def _safe_filename(value: Any) -> str:
    if not isinstance(value, str) or isinstance(value, bool) or not 1 <= len(value) <= 255:
        raise MailCollectorError("attachment filename is malformed")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise MailCollectorError("attachment filename is unsafe")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise MailCollectorError("attachment filename contains a control character")
    return value


def _normalize_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise MailCollectorError("headers must be a non-empty mapping")
    normalized: dict[str, str] = {}
    for name, header_value in value.items():
        if not isinstance(name, str) or not _HEADER_NAME_RE.fullmatch(name):
            raise MailCollectorError("header name is malformed")
        key = name.lower()
        if key in normalized:
            raise MailCollectorError("headers contain a case-insensitive duplicate")
        if not isinstance(header_value, str) or isinstance(header_value, bool) or not header_value:
            raise MailCollectorError("header value is malformed")
        if "\r" in header_value or "\n" in header_value or any(ord(character) < 32 or ord(character) == 127 for character in header_value):
            raise MailCollectorError("header value contains a control character")
        normalized[key] = header_value
    return {key: normalized[key] for key in sorted(normalized)}


def _normalize_attachment(message_id: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"attachment_id", "filename", "content"}:
        raise MailCollectorError("attachment fields are not exact")
    attachment_id = _require_identifier(value["attachment_id"], "attachment_id")
    content = _require_bytes(value["content"], "attachment content")
    digest = _sha256_bytes(content)
    identity = normalize_attachment_record(
        {
            "gmail_message_id": message_id,
            "attachment_id": attachment_id,
            "content_sha256": digest,
        }
    )
    return {
        "attachment_id": identity["attachment_id"],
        "filename": _safe_filename(value["filename"]),
        "content": content,
        "sha256": digest,
        "archive_key": archive_idempotency_key(identity),
    }


def normalize_mail_record(value: Any) -> dict[str, Any]:
    """Validate a fully materialised mail record before writing any bytes."""

    expected = {
        "gmail_message_id",
        "source_history_id",
        "received_at_utc",
        "raw_eml",
        "headers",
        "attachments",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise MailCollectorError("mail record fields are not exact")
    message_id = _require_identifier(value["gmail_message_id"], "gmail_message_id")
    history_id = value["source_history_id"]
    if not isinstance(history_id, str) or not _HISTORY_ID_RE.fullmatch(history_id):
        raise MailCollectorError("source_history_id is malformed")
    attachments_value = value["attachments"]
    if not isinstance(attachments_value, Sequence) or isinstance(attachments_value, (bytes, bytearray, str)) or not attachments_value:
        raise MailCollectorError("attachments must be a non-empty sequence")
    attachments = [_normalize_attachment(message_id, item) for item in attachments_value]
    attachment_ids = [item["attachment_id"] for item in attachments]
    if len(attachment_ids) != len(set(attachment_ids)):
        raise MailCollectorError("attachments contain duplicate attachment_id values")
    attachments.sort(key=lambda item: item["attachment_id"])
    return {
        "gmail_message_id": message_id,
        "source_history_id": history_id,
        "received_at_utc": _require_utc(value["received_at_utc"]),
        "raw_eml": _require_bytes(value["raw_eml"], "raw_eml"),
        "headers": _normalize_headers(value["headers"]),
        "attachments": attachments,
    }


def _private_archive_root(archive_root: Path | str, repository_root: Path | str) -> Path:
    root = Path(archive_root).resolve()
    repository = Path(repository_root).resolve()
    if root == repository or repository in root.parents:
        raise MailCollectorError("archive root must be outside the repository")
    try:
        private_index = root.parts.index(PRIVATE_DATABASE_AREA)
    except ValueError as exc:
        raise MailCollectorError("archive root must be routed through Private-MetaDatabase") from exc
    if len(root.parts) <= private_index + 1 or root.parts[private_index + 1] != "ABD":
        raise MailCollectorError("archive root must use the Private-MetaDatabase/ABD domain")
    return root / ARCHIVE_DIRECTORY_NAME


def _relative_path(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise MailCollectorError("archive path escaped its private root") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise MailCollectorError("archive path is unsafe")
    return relative.as_posix()


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(".%s.tmp" % path.name)
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _manifest_unsigned(record: Mapping[str, Any], *, archive_root: Path) -> dict[str, Any]:
    headers_payload = _json_bytes(record["headers"])
    attachments: list[dict[str, Any]] = []
    for attachment in record["attachments"]:
        relative = "attachments/%s.bin" % attachment["attachment_id"]
        attachments.append(
            {
                "attachment_id": attachment["attachment_id"],
                "archive_key": attachment["archive_key"],
                "filename": attachment["filename"],
                "path": relative,
                "sha256": attachment["sha256"],
                "size_bytes": len(attachment["content"]),
            }
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": "MAN-S06-P02-%s" % record["gmail_message_id"],
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "product_version": VERSION,
        "archive_layout_version": ARCHIVE_LAYOUT_VERSION,
        "status": ARCHIVE_STATUS,
        "gmail_message_id": record["gmail_message_id"],
        "source_history_id": record["source_history_id"],
        "received_at_utc": record["received_at_utc"],
        "private_storage": {
            "area": PRIVATE_DATABASE_AREA,
            "domain": "ABD",
            "repository_raw_data_write": "PROHIBITED",
            "private_db_client_execution_in_p02": False,
        },
        "raw_eml": {
            "path": "raw.eml",
            "sha256": _sha256_bytes(record["raw_eml"]),
            "size_bytes": len(record["raw_eml"]),
        },
        "headers": {
            "path": "headers.json",
            "sha256": _sha256_bytes(headers_payload),
            "count": len(record["headers"]),
        },
        "attachments": attachments,
        "readback_verified": True,
        "trash_action": TRASH_ACTION,
        "gmail_mutation_performed": False,
        "real_time_soak_wait_required": False,
        "archive_root_reference": _relative_path(archive_root / "records" / record["gmail_message_id"], archive_root),
    }


def _build_manifest(record: Mapping[str, Any], *, archive_root: Path) -> dict[str, Any]:
    manifest = _manifest_unsigned(record, archive_root=archive_root)
    manifest["manifest_sha256"] = _sha256_bytes(_json_bytes(manifest))
    return manifest


def _manifest_matches_record(manifest: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    try:
        expected = _build_manifest(record, archive_root=Path("/private/%s/ABD" % PRIVATE_DATABASE_AREA))
    except Exception:
        return False
    fields = (
        "gmail_message_id",
        "source_history_id",
        "received_at_utc",
        "raw_eml",
        "headers",
        "attachments",
    )
    for field in fields:
        if manifest.get(field) != expected.get(field):
            return False
    return True


def _expected_manifest_keys() -> set[str]:
    return {
        "schema_version",
        "manifest_id",
        "contract_id",
        "requirement_id",
        "product_version",
        "archive_layout_version",
        "status",
        "gmail_message_id",
        "source_history_id",
        "received_at_utc",
        "private_storage",
        "raw_eml",
        "headers",
        "attachments",
        "readback_verified",
        "trash_action",
        "gmail_mutation_performed",
        "real_time_soak_wait_required",
        "archive_root_reference",
        "manifest_sha256",
    }


def _safe_manifest_relative(value: Any) -> str:
    if not isinstance(value, str) or value.startswith("/") or "\\" in value:
        raise MailCollectorError("manifest path is unsafe")
    candidate = Path(value)
    if not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise MailCollectorError("manifest path is unsafe")
    return candidate.as_posix()


def _load_manifest(path: Path) -> Mapping[str, Any]:
    manifest = strict_json_load(path)
    if not isinstance(manifest, Mapping) or set(manifest) != _expected_manifest_keys():
        raise MailCollectorError("manifest fields are not exact")
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise MailCollectorError("manifest hash is malformed")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    if _sha256_bytes(_json_bytes(unsigned)) != digest:
        raise MailCollectorError("manifest hash does not match")
    return manifest


def verify_preserved_mail(
    *,
    archive_root: Path | str,
    repository_root: Path | str,
    gmail_message_id: Any,
) -> dict[str, Any]:
    """Read every declared preserved byte and return a fail-closed trash decision."""

    message_id = _require_identifier(gmail_message_id, "gmail_message_id")
    root = _private_archive_root(archive_root, repository_root)
    bundle = root / "records" / message_id
    errors: list[str] = []
    manifest: Mapping[str, Any] | None = None
    try:
        manifest = _load_manifest(bundle / "manifest.json")
    except Exception:
        errors.append("MANIFEST_MISSING_OR_INVALID")
    if manifest is not None:
        expected_identity = (
            manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
            and manifest.get("contract_id") == CONTRACT_ID
            and manifest.get("requirement_id") == REQUIREMENT_ID
            and manifest.get("product_version") == VERSION
            and manifest.get("status") == ARCHIVE_STATUS
            and manifest.get("gmail_message_id") == message_id
            and manifest.get("trash_action") == TRASH_ACTION
            and manifest.get("gmail_mutation_performed") is False
            and manifest.get("real_time_soak_wait_required") is False
            and manifest.get("readback_verified") is True
        )
        if not expected_identity:
            errors.append("MANIFEST_CONTRACT_MISMATCH")
        try:
            raw = manifest["raw_eml"]
            headers = manifest["headers"]
            attachments = manifest["attachments"]
            if not isinstance(raw, Mapping) or not isinstance(headers, Mapping) or not isinstance(attachments, list) or not attachments:
                raise MailCollectorError("manifest payload shape is invalid")
            raw_path = bundle / _safe_manifest_relative(raw.get("path"))
            headers_path = bundle / _safe_manifest_relative(headers.get("path"))
            if not raw_path.is_file() or _sha256_bytes(raw_path.read_bytes()) != raw.get("sha256"):
                errors.append("RAW_EML_MISSING_OR_HASH_MISMATCH")
            if not headers_path.is_file() or _sha256_bytes(headers_path.read_bytes()) != headers.get("sha256"):
                errors.append("HEADERS_MISSING_OR_HASH_MISMATCH")
            attachment_ids: set[str] = set()
            for attachment in attachments:
                if not isinstance(attachment, Mapping):
                    errors.append("ATTACHMENT_MANIFEST_INVALID")
                    continue
                attachment_id = _require_identifier(attachment.get("attachment_id"), "attachment_id")
                if attachment_id in attachment_ids:
                    errors.append("ATTACHMENT_MANIFEST_DUPLICATE")
                    continue
                attachment_ids.add(attachment_id)
                attachment_path = bundle / _safe_manifest_relative(attachment.get("path"))
                if not attachment_path.is_file() or _sha256_bytes(attachment_path.read_bytes()) != attachment.get("sha256"):
                    errors.append("ATTACHMENT_MISSING_OR_HASH_MISMATCH")
        except Exception:
            errors.append("MANIFEST_PATH_OR_ATTACHMENT_INVALID")
    unique_errors = sorted(set(errors))
    return {
        "status": "PASS" if not unique_errors else "FAIL",
        "gmail_message_id": message_id,
        "reason_codes": unique_errors,
        "readback_verified": not unique_errors,
        "trash_eligible": False,
        "trash_action": TRASH_ACTION,
        "gmail_mutation_performed": False,
        "real_time_soak_wait_required": False,
    }


def restore_for_readback(
    *,
    archive_root: Path | str,
    repository_root: Path | str,
    gmail_message_id: Any,
) -> dict[str, Any]:
    """Return preserved bytes only after an integrity check; never serialise these into evidence."""

    verification = verify_preserved_mail(
        archive_root=archive_root,
        repository_root=repository_root,
        gmail_message_id=gmail_message_id,
    )
    if verification["status"] != "PASS":
        raise MailCollectorError("preserved mail cannot be restored because integrity verification failed")
    root = _private_archive_root(archive_root, repository_root)
    bundle = root / "records" / verification["gmail_message_id"]
    manifest = _load_manifest(bundle / "manifest.json")
    attachments: list[dict[str, Any]] = []
    for attachment in manifest["attachments"]:
        attachments.append(
            {
                "attachment_id": attachment["attachment_id"],
                "filename": attachment["filename"],
                "content": (bundle / attachment["path"]).read_bytes(),
            }
        )
    return {
        "gmail_message_id": verification["gmail_message_id"],
        "raw_eml": (bundle / manifest["raw_eml"]["path"]).read_bytes(),
        "headers": strict_json_load(bundle / manifest["headers"]["path"]),
        "attachments": attachments,
        "readback_verified": True,
        "gmail_mutation_performed": False,
    }


def preserve_mail(
    value: Any,
    *,
    archive_root: Path | str,
    repository_root: Path | str,
    fault_injection: str | None = None,
) -> dict[str, Any]:
    """Atomically preserve one mail bundle, or return a non-destructive ``KEEP`` result."""

    if fault_injection not in {None, "BEFORE_MANIFEST", "AFTER_MANIFEST_BEFORE_COMMIT"}:
        raise MailCollectorError("fault_injection is not recognised")
    record = normalize_mail_record(value)
    root = _private_archive_root(archive_root, repository_root)
    records_root = root / "records"
    target = records_root / record["gmail_message_id"]
    if target.exists():
        verification = verify_preserved_mail(
            archive_root=archive_root,
            repository_root=repository_root,
            gmail_message_id=record["gmail_message_id"],
        )
        if verification["status"] == "PASS":
            try:
                existing = _load_manifest(target / "manifest.json")
            except Exception:
                existing = None
            if isinstance(existing, Mapping) and _manifest_matches_record(existing, record):
                return {
                    "status": "IDEMPOTENT_ALREADY_PRESERVED",
                    "gmail_message_id": record["gmail_message_id"],
                    "new_archive_created": False,
                    "readback_verified": True,
                    "trash_eligible": False,
                    "trash_action": TRASH_ACTION,
                    "gmail_mutation_performed": False,
                    "real_time_soak_wait_required": False,
                }
        return {
            "status": "INTEGRITY_CONFLICT_KEEP",
            "gmail_message_id": record["gmail_message_id"],
            "new_archive_created": False,
            "readback_verified": False,
            "trash_eligible": False,
            "trash_action": TRASH_ACTION,
            "gmail_mutation_performed": False,
            "real_time_soak_wait_required": False,
        }

    staging_root = root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    records_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="mail-", dir=staging_root))
    try:
        attachments_root = staging / "attachments"
        attachments_root.mkdir()
        _atomic_write(staging / "raw.eml", record["raw_eml"])
        _atomic_write(staging / "headers.json", _json_bytes(record["headers"]))
        for attachment in record["attachments"]:
            _atomic_write(attachments_root / (attachment["attachment_id"] + ".bin"), attachment["content"])
        if fault_injection == "BEFORE_MANIFEST":
            raise OSError("fault before manifest")
        manifest = _build_manifest(record, archive_root=root)
        _atomic_write(staging / "manifest.json", _json_bytes(manifest))
        if fault_injection == "AFTER_MANIFEST_BEFORE_COMMIT":
            raise OSError("fault after manifest")
        os.rename(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "status": "PRESERVATION_FAILED_KEEP",
            "gmail_message_id": record["gmail_message_id"],
            "new_archive_created": False,
            "readback_verified": False,
            "trash_eligible": False,
            "trash_action": TRASH_ACTION,
            "gmail_mutation_performed": False,
            "real_time_soak_wait_required": False,
        }
    verification = verify_preserved_mail(
        archive_root=archive_root,
        repository_root=repository_root,
        gmail_message_id=record["gmail_message_id"],
    )
    return {
        "status": "PRESERVED_READBACK_VERIFIED" if verification["status"] == "PASS" else "PRESERVATION_INTEGRITY_FAILED_KEEP",
        "gmail_message_id": record["gmail_message_id"],
        "new_archive_created": True,
        "readback_verified": verification["status"] == "PASS",
        "trash_eligible": False,
        "trash_action": TRASH_ACTION,
        "gmail_mutation_performed": False,
        "real_time_soak_wait_required": False,
    }


def evaluate_collection_cadence(*, last_success_epoch: Any, now_epoch: Any) -> dict[str, Any]:
    """Evaluate a 15-minute cadence as data; this function never sleeps or schedules work."""

    if type(last_success_epoch) is not int or type(now_epoch) is not int or last_success_epoch < 0 or now_epoch < 0:
        raise MailCollectorError("cadence epochs must be non-negative integers")
    if now_epoch < last_success_epoch:
        return {
            "status": "INVALID_CLOCK_KEEP",
            "due": False,
            "next_eligible_epoch": last_success_epoch + COLLECTOR_INTERVAL_SECONDS,
            "real_time_wait_performed": False,
        }
    next_eligible = last_success_epoch + COLLECTOR_INTERVAL_SECONDS
    return {
        "status": "DUE" if now_epoch >= next_eligible else "NOT_DUE",
        "due": now_epoch >= next_eligible,
        "next_eligible_epoch": next_eligible,
        "real_time_wait_performed": False,
    }


def private_db_ingest_plan(*, gmail_message_id: Any) -> dict[str, Any]:
    """Describe the future private-store hand-off without invoking a client or network."""

    message_id = _require_identifier(gmail_message_id, "gmail_message_id")
    return {
        "status": "PLAN_ONLY_NO_EXECUTION",
        "private_database_area": PRIVATE_DATABASE_AREA,
        "domain": PRIVATE_DATABASE_DOMAIN,
        "client_path": "KMOS/KMDatabase/machine/tools/private_db_client.py",
        "archive_reference": "records/%s" % message_id,
        "network_performed": False,
        "private_database_client_executed": False,
        "gmail_mutation_performed": False,
    }


def validate_no_real_time_soak() -> dict[str, Any]:
    return {
        "real_time_soak_required": REAL_TIME_SOAK_REQUIRED,
        "collector_interval_seconds": COLLECTOR_INTERVAL_SECONDS,
        "cadence_evaluated_as_data": True,
        "core_deployment_behavior": "CONTINUE_WITH_MAIL_ARCHIVE_MODULE_DISABLED_OR_DEGRADED",
        "real_time_wait_performed": False,
    }


__all__ = [
    "ARCHIVE_DIRECTORY_NAME",
    "ARCHIVE_LAYOUT_VERSION",
    "ARCHIVE_STATUS",
    "COLLECTOR_INTERVAL_SECONDS",
    "CONTRACT_ID",
    "MailCollectorError",
    "MANIFEST_SCHEMA_VERSION",
    "PRIVATE_DATABASE_AREA",
    "PRIVATE_DATABASE_DOMAIN",
    "REAL_TIME_SOAK_REQUIRED",
    "REQUIREMENT_ID",
    "TRASH_ACTION",
    "VERSION",
    "evaluate_collection_cadence",
    "normalize_mail_record",
    "preserve_mail",
    "private_db_ingest_plan",
    "restore_for_readback",
    "validate_no_real_time_soak",
    "verify_preserved_mail",
]
