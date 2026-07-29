"""Fail-closed attachment inspection for ABD S06/P03.

The module deliberately performs only bounded, in-memory byte inspection.  It
never executes an attachment, opens a network connection, extracts a ZIP file
to disk, starts a process, contacts Gmail, or waits for real time.  It is not
a claim that an operating-system malware scanner has run: unrecognised or
uninspectable input is quarantined and a later phase remains responsible for
any Gmail action.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence


VERSION = "0.0.0.1"
CONTRACT_ID = "AC-S06-P03"
REQUIREMENT_ID = "REQ-S06-P03"
SCHEMA_VERSION = "1.0.0"
PARSER_REGISTRY_PATH = Path(__file__).with_name("parser_registry.json")
QUARANTINE_RULES_PATH = Path(__file__).with_name("quarantine_rules.json")

_IDENTIFIER_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SAFE_FILENAME_RE = re.compile(r"\A[^/\\\x00-\x1f\x7f]{1,255}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class AttachmentSandboxError(ValueError):
    """Raised by explicit policy loading when a local policy is unsafe."""


def _json_load(path: Path) -> Mapping[str, Any]:
    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AttachmentSandboxError("duplicate JSON key in policy")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except Exception as exc:
        raise AttachmentSandboxError("policy is not strict UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise AttachmentSandboxError("policy root must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise AttachmentSandboxError("%s fields are not exact" % label)


def _require_string(value: Any, label: str, *, minimum: int = 1, maximum: int = 256) -> str:
    if not isinstance(value, str) or isinstance(value, bool) or not minimum <= len(value) <= maximum:
        raise AttachmentSandboxError("%s is not a bounded string" % label)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AttachmentSandboxError("%s contains a control character" % label)
    return value


def _require_positive_int(value: Any, label: str, *, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise AttachmentSandboxError("%s is not a bounded positive integer" % label)
    return value


def _require_string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise AttachmentSandboxError("%s must be a non-empty list" % label)
    normalized = [_require_string(item, label) for item in value]
    if len(normalized) != len(set(normalized)):
        raise AttachmentSandboxError("%s contains duplicates" % label)
    return normalized


def _validate_registry(value: Mapping[str, Any]) -> dict[str, Any]:
    _require_exact_keys(value, {"schema_version", "contract_id", "requirement_id", "runtime", "parsers"}, "parser registry")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("contract_id") != CONTRACT_ID or value.get("requirement_id") != REQUIREMENT_ID:
        raise AttachmentSandboxError("parser registry identity is invalid")
    runtime = value.get("runtime")
    if not isinstance(runtime, Mapping):
        raise AttachmentSandboxError("runtime is unavailable")
    _require_exact_keys(
        runtime,
        {
            "mode",
            "external_network_access",
            "attachment_max_bytes",
            "cpu_budget_seconds",
            "memory_budget_mb",
            "max_zip_members",
            "max_zip_uncompressed_bytes",
            "max_zip_ratio",
            "max_csv_rows",
            "max_csv_cells",
        },
        "runtime",
    )
    if runtime.get("mode") != "NO_EXECUTION_PURE_BYTES_INSPECTION" or runtime.get("external_network_access") is not False:
        raise AttachmentSandboxError("runtime cannot execute attachments or access a network")
    checked_runtime = {
        "mode": runtime["mode"],
        "external_network_access": False,
        "attachment_max_bytes": _require_positive_int(runtime.get("attachment_max_bytes"), "attachment_max_bytes", maximum=50_000_000),
        "cpu_budget_seconds": _require_positive_int(runtime.get("cpu_budget_seconds"), "cpu_budget_seconds", maximum=60),
        "memory_budget_mb": _require_positive_int(runtime.get("memory_budget_mb"), "memory_budget_mb", maximum=256),
        "max_zip_members": _require_positive_int(runtime.get("max_zip_members"), "max_zip_members", maximum=1_024),
        "max_zip_uncompressed_bytes": _require_positive_int(runtime.get("max_zip_uncompressed_bytes"), "max_zip_uncompressed_bytes", maximum=50_000_000),
        "max_zip_ratio": _require_positive_int(runtime.get("max_zip_ratio"), "max_zip_ratio", maximum=1_000),
        "max_csv_rows": _require_positive_int(runtime.get("max_csv_rows"), "max_csv_rows", maximum=1_000_000),
        "max_csv_cells": _require_positive_int(runtime.get("max_csv_cells"), "max_csv_cells", maximum=10_000_000),
    }
    if checked_runtime["max_zip_uncompressed_bytes"] > checked_runtime["attachment_max_bytes"]:
        raise AttachmentSandboxError("ZIP inspection bound exceeds attachment bound")
    parsers = value.get("parsers")
    if not isinstance(parsers, list) or not parsers:
        raise AttachmentSandboxError("parser registry has no parsers")
    profiles_by_extension: dict[str, dict[str, Any]] = {}
    allowed_types = {"text/csv", "application/pdf", "application/vnd.openxmlformats-officedocument"}
    for item in parsers:
        if not isinstance(item, Mapping):
            raise AttachmentSandboxError("parser item is not an object")
        _require_exact_keys(item, {"id", "media_type", "extensions", "signature", "active_content"}, "parser item")
        parser_id = _require_string(item.get("id"), "parser id")
        media_type = _require_string(item.get("media_type"), "media type")
        if media_type not in allowed_types:
            raise AttachmentSandboxError("parser media type is outside the fail-closed allowlist")
        signature = _require_string(item.get("signature"), "parser signature")
        if signature not in {"UTF8_CSV", "PDF_HEADER_AND_EOF", "OOXML_ZIP"}:
            raise AttachmentSandboxError("parser signature is not allowlisted")
        if item.get("active_content") != "DENY":
            raise AttachmentSandboxError("active content must be denied")
        extensions = _require_string_list(item.get("extensions"), "parser extensions")
        for extension in extensions:
            normalized = extension.lower()
            if normalized != extension or not re.fullmatch(r"[a-z0-9]{1,12}", extension) or extension in profiles_by_extension:
                raise AttachmentSandboxError("parser extension is invalid or duplicated")
            profiles_by_extension[extension] = {
                "id": parser_id,
                "media_type": media_type,
                "signature": signature,
                "active_content": "DENY",
            }
    return {"runtime": checked_runtime, "profiles_by_extension": profiles_by_extension}


def _validate_rules(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "contract_id",
        "requirement_id",
        "quarantine_status",
        "safe_status",
        "permanent_delete",
        "mail_content_instruction_trust",
        "dangerous_extensions",
        "malware_markers",
        "script_markers",
        "prompt_injection_markers",
        "pdf_active_markers",
        "office_deny_name_fragments",
        "office_deny_content_markers",
        "formula_prefixes",
    }
    _require_exact_keys(value, expected, "quarantine rules")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("contract_id") != CONTRACT_ID or value.get("requirement_id") != REQUIREMENT_ID:
        raise AttachmentSandboxError("quarantine rules identity is invalid")
    if value.get("quarantine_status") != "QUARANTINED_KEEP" or value.get("safe_status") != "PARSED_SAFE":
        raise AttachmentSandboxError("quarantine status is invalid")
    if value.get("permanent_delete") is not False or value.get("mail_content_instruction_trust") != "NONE":
        raise AttachmentSandboxError("destructive or content-trust policy is unsafe")
    result: dict[str, Any] = {
        "quarantine_status": "QUARANTINED_KEEP",
        "safe_status": "PARSED_SAFE",
        "permanent_delete": False,
        "mail_content_instruction_trust": "NONE",
    }
    for key in (
        "dangerous_extensions",
        "malware_markers",
        "script_markers",
        "prompt_injection_markers",
        "pdf_active_markers",
        "office_deny_name_fragments",
        "office_deny_content_markers",
        "formula_prefixes",
    ):
        result[key] = _require_string_list(value.get(key), key)
    normalized_extensions = [item.lower() for item in result["dangerous_extensions"]]
    if normalized_extensions != result["dangerous_extensions"] or any(not re.fullmatch(r"[a-z0-9]{1,12}", item) for item in normalized_extensions):
        raise AttachmentSandboxError("dangerous extensions are invalid")
    if set(result["formula_prefixes"]) != {"=", "+", "-", "@"}:
        raise AttachmentSandboxError("formula prefixes are not exact")
    return result


def load_policy(
    *,
    parser_registry_path: Path | str = PARSER_REGISTRY_PATH,
    quarantine_rules_path: Path | str = QUARANTINE_RULES_PATH,
) -> dict[str, Any]:
    """Load only two local JSON policy files and validate them strictly."""

    registry_path = Path(parser_registry_path)
    rules_path = Path(quarantine_rules_path)
    registry = _validate_registry(_json_load(registry_path))
    rules = _validate_rules(_json_load(rules_path))
    return {
        "runtime": registry["runtime"],
        "profiles_by_extension": registry["profiles_by_extension"],
        "rules": rules,
        "policy_sha256": hashlib.sha256(registry_path.read_bytes() + b"\0" + rules_path.read_bytes()).hexdigest(),
    }


def sandbox_plan(*, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the actual no-execution boundary, without starting a sandbox."""

    active_policy = dict(policy) if policy is not None else load_policy()
    runtime = active_policy["runtime"]
    return {
        "mode": runtime["mode"],
        "external_network_accessed": False,
        "attachment_execution_performed": False,
        "zip_extracted_to_disk": False,
        "subprocess_started": False,
        "real_time_soak_waited": False,
        "os_level_sandbox_spawned": False,
        "cpu_budget_seconds": runtime["cpu_budget_seconds"],
        "memory_budget_mb": runtime["memory_budget_mb"],
        "resource_bound_enforced_by_parser": True,
        "malware_clearance_claimed": False,
    }


def _content_sha256(value: Any) -> str:
    return hashlib.sha256(value).hexdigest() if isinstance(value, bytes) else "UNAVAILABLE"


def _attachment_input(value: Any) -> tuple[str, str, bytes, str]:
    if not isinstance(value, Mapping) or set(value) != {"attachment_id", "filename", "content"}:
        raise AttachmentSandboxError("attachment fields are not exact")
    attachment_id = value.get("attachment_id")
    filename = value.get("filename")
    content = value.get("content")
    if not isinstance(attachment_id, str) or not _IDENTIFIER_RE.fullmatch(attachment_id):
        raise AttachmentSandboxError("attachment_id is malformed")
    if not isinstance(filename, str) or not _SAFE_FILENAME_RE.fullmatch(filename) or filename in {".", ".."}:
        raise AttachmentSandboxError("filename is malformed")
    if not isinstance(content, bytes) or not content:
        raise AttachmentSandboxError("content must be non-empty bytes")
    extension = filename.rsplit(".", 1)[1].lower() if "." in filename and not filename.endswith(".") else ""
    return attachment_id, filename, content, extension


def _quarantined(
    *,
    attachment_id: str,
    filename: str,
    content: Any,
    extension: str,
    reason_codes: Sequence[str],
    policy: Mapping[str, Any] | None,
    parser_id: str | None = None,
    detected_media_type: str = "UNKNOWN",
) -> dict[str, Any]:
    runtime = policy.get("runtime") if isinstance(policy, Mapping) else None
    sandbox = sandbox_plan(policy=policy) if isinstance(runtime, Mapping) else {
        "mode": "POLICY_INVALID_FAIL_CLOSED",
        "external_network_accessed": False,
        "attachment_execution_performed": False,
        "zip_extracted_to_disk": False,
        "subprocess_started": False,
        "real_time_soak_waited": False,
        "os_level_sandbox_spawned": False,
        "cpu_budget_seconds": None,
        "memory_budget_mb": None,
        "resource_bound_enforced_by_parser": False,
        "malware_clearance_claimed": False,
    }
    ordered_reasons = list(dict.fromkeys(str(reason) for reason in reason_codes)) or ["UNSPECIFIED_QUARANTINE"]
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "attachment_id": attachment_id,
        "filename": filename,
        "extension": extension,
        "content_sha256": _content_sha256(content),
        "size_bytes": len(content) if isinstance(content, bytes) else None,
        "detected_media_type": detected_media_type,
        "parser_id": parser_id,
        "status": "QUARANTINED_KEEP",
        "quarantined": True,
        "reason_codes": ordered_reasons,
        "parser_result_recorded": True,
        "malware_scan_result": "NOT_CLEARED_STATIC_INSPECTION_ONLY",
        "trash_eligible": False,
        "gmail_mutation_performed": False,
        "permanent_delete_performed": False,
        "sandbox": sandbox,
    }


def _safe_result(
    *,
    attachment_id: str,
    filename: str,
    content: bytes,
    extension: str,
    profile: Mapping[str, Any],
    metadata: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "attachment_id": attachment_id,
        "filename": filename,
        "extension": extension,
        "content_sha256": _content_sha256(content),
        "size_bytes": len(content),
        "detected_media_type": profile["media_type"],
        "parser_id": profile["id"],
        "status": "PARSED_SAFE",
        "quarantined": False,
        "reason_codes": [],
        "parser_result_recorded": True,
        "malware_scan_result": "NO_FROZEN_SIGNATURE_MATCH_NOT_A_LIVE_AV_CLEARANCE",
        "trash_eligible": False,
        "gmail_mutation_performed": False,
        "permanent_delete_performed": False,
        "metadata": dict(metadata),
        "sandbox": sandbox_plan(policy=policy),
    }


def _marker_reasons(content: bytes, rules: Mapping[str, Any], *, include_pdf: bool = False, include_office: bool = False) -> list[str]:
    lower = content.lower()
    reasons: list[str] = []
    if any(marker.encode("utf-8").lower() in lower for marker in rules["malware_markers"]):
        reasons.append("MALWARE_MARKER_QUARANTINE")
    if any(marker.encode("utf-8").lower() in lower for marker in rules["script_markers"]):
        reasons.append("SCRIPT_OR_ACTIVE_CONTENT_QUARANTINE")
    if any(marker.encode("utf-8").lower() in lower for marker in rules["prompt_injection_markers"]):
        reasons.append("PROMPT_INJECTION_QUARANTINE")
    if include_pdf and any(marker.encode("utf-8").lower() in lower for marker in rules["pdf_active_markers"]):
        reasons.append("PDF_ACTIVE_CONTENT_QUARANTINE")
    if include_office and any(marker.encode("utf-8").lower() in lower for marker in rules["office_deny_content_markers"]):
        reasons.append("OFFICE_ACTIVE_CONTENT_QUARANTINE")
    return reasons


def _inspect_csv(content: bytes, policy: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    runtime = policy["runtime"]
    rules = policy["rules"]
    if b"\x00" in content:
        return ["CSV_BINARY_OR_NUL_QUARANTINE"], {}
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return ["CSV_NOT_UTF8_QUARANTINE"], {}
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (csv.Error, ValueError):
        return ["CSV_PARSE_FAILURE_QUARANTINE"], {}
    if not rows:
        return ["CSV_EMPTY_QUARANTINE"], {}
    cell_count = sum(len(row) for row in rows)
    if len(rows) > runtime["max_csv_rows"] or cell_count > runtime["max_csv_cells"]:
        return ["CSV_RESOURCE_BOUND_QUARANTINE"], {}
    formula_prefixes = tuple(rules["formula_prefixes"])
    if any(cell.lstrip().startswith(formula_prefixes) for row in rows for cell in row):
        return ["FORMULA_INJECTION_QUARANTINE"], {}
    marker_reasons = _marker_reasons(content, rules)
    if marker_reasons:
        return marker_reasons, {}
    return [], {"rows": len(rows), "cells": cell_count, "content_retained": False}


def _inspect_pdf(content: bytes, policy: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    if not content.startswith(b"%PDF-"):
        return ["TYPE_SIGNATURE_MISMATCH_QUARANTINE"], {}
    if not content.rstrip().endswith(b"%%EOF"):
        return ["PDF_INCOMPLETE_QUARANTINE"], {}
    reasons = _marker_reasons(content, policy["rules"], include_pdf=True)
    if reasons:
        return reasons, {}
    return [], {"pdf_header": True, "pdf_eof": True, "content_retained": False}


def _inspect_ooxml(content: bytes, profile: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    runtime = policy["runtime"]
    rules = policy["rules"]
    if not content.startswith(b"PK\x03\x04"):
        return ["TYPE_SIGNATURE_MISMATCH_QUARANTINE"], {}
    required_entry_by_extension = {
        "xlsx": "xl/workbook.xml",
        "docx": "word/document.xml",
        "pptx": "ppt/presentation.xml",
    }
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > runtime["max_zip_members"]:
                return ["OFFICE_RESOURCE_BOUND_QUARANTINE"], {}
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                return ["OFFICE_DUPLICATE_ENTRY_QUARANTINE"], {}
            if any(name.startswith(("/", "\\")) or "\\" in name or "\x00" in name or any(part in {"", ".", ".."} for part in name.split("/")) for name in names):
                return ["PATH_TRAVERSAL_QUARANTINE"], {}
            if any(info.flag_bits & 0x1 for info in infos):
                return ["OFFICE_ENCRYPTED_UNINSPECTABLE_QUARANTINE"], {}
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > runtime["max_zip_uncompressed_bytes"]:
                return ["OFFICE_RESOURCE_BOUND_QUARANTINE"], {}
            for info in infos:
                compressed = max(info.compress_size, 1)
                if info.file_size / compressed > runtime["max_zip_ratio"]:
                    return ["OFFICE_COMPRESSION_RATIO_QUARANTINE"], {}
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    return ["OFFICE_COMPRESSION_METHOD_QUARANTINE"], {}
            extension = next((item for item, current in policy["profiles_by_extension"].items() if current == profile), "")
            required_entry = required_entry_by_extension.get(extension)
            if "[Content_Types].xml" not in names or required_entry not in names:
                return ["OFFICE_REQUIRED_STRUCTURE_QUARANTINE"], {}
            lower_names = "\n".join(names).lower()
            if any(fragment.lower() in lower_names for fragment in rules["office_deny_name_fragments"]):
                return ["MACRO_OR_ACTIVE_OFFICE_ENTRY_QUARANTINE"], {}
            inspected = b"".join(archive.read(info) for info in infos)
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return ["OFFICE_PARSE_FAILURE_QUARANTINE"], {}
    reasons = _marker_reasons(inspected, rules, include_office=True)
    if reasons:
        return reasons, {}
    return [], {"zip_members": len(names), "zip_uncompressed_bytes": total_uncompressed, "content_retained": False}


def scan_attachment(
    value: Any,
    *,
    parser_registry_path: Path | str = PARSER_REGISTRY_PATH,
    quarantine_rules_path: Path | str = QUARANTINE_RULES_PATH,
) -> dict[str, Any]:
    """Inspect one attachment and return a complete keep-or-quarantine result.

    Inputs are deliberately constrained to ``attachment_id``, ``filename`` and
    raw ``content`` bytes.  The return value never exposes source bytes or
    extracted document text.  Every error is converted to a keep/quarantine
    result so callers cannot accidentally treat an exception as a pass.
    """

    policy: Mapping[str, Any] | None
    try:
        policy = load_policy(parser_registry_path=parser_registry_path, quarantine_rules_path=quarantine_rules_path)
    except AttachmentSandboxError:
        policy = None
    try:
        attachment_id, filename, content, extension = _attachment_input(value)
    except AttachmentSandboxError:
        raw_content = value.get("content") if isinstance(value, Mapping) else None
        return _quarantined(
            attachment_id="INVALID_ATTACHMENT",
            filename="INVALID_FILENAME",
            content=raw_content,
            extension="",
            reason_codes=["INPUT_INVALID_QUARANTINE" if policy is not None else "POLICY_INVALID_QUARANTINE"],
            policy=policy,
        )
    if policy is None:
        return _quarantined(
            attachment_id=attachment_id,
            filename=filename,
            content=content,
            extension=extension,
            reason_codes=["POLICY_INVALID_QUARANTINE"],
            policy=None,
        )
    runtime = policy["runtime"]
    rules = policy["rules"]
    if len(content) > runtime["attachment_max_bytes"]:
        return _quarantined(
            attachment_id=attachment_id,
            filename=filename,
            content=content,
            extension=extension,
            reason_codes=["ATTACHMENT_SIZE_EXCEEDED_QUARANTINE"],
            policy=policy,
        )
    if extension in rules["dangerous_extensions"]:
        return _quarantined(
            attachment_id=attachment_id,
            filename=filename,
            content=content,
            extension=extension,
            reason_codes=["DANGEROUS_EXTENSION_QUARANTINE"],
            policy=policy,
        )
    profile = policy["profiles_by_extension"].get(extension)
    if profile is None:
        return _quarantined(
            attachment_id=attachment_id,
            filename=filename,
            content=content,
            extension=extension,
            reason_codes=["UNKNOWN_TYPE_QUARANTINE"],
            policy=policy,
        )
    if profile["signature"] == "UTF8_CSV":
        reasons, metadata = _inspect_csv(content, policy)
    elif profile["signature"] == "PDF_HEADER_AND_EOF":
        reasons, metadata = _inspect_pdf(content, policy)
    elif profile["signature"] == "OOXML_ZIP":
        reasons, metadata = _inspect_ooxml(content, profile, policy)
    else:
        reasons, metadata = ["PARSER_PROFILE_INVALID_QUARANTINE"], {}
    if reasons:
        return _quarantined(
            attachment_id=attachment_id,
            filename=filename,
            content=content,
            extension=extension,
            reason_codes=reasons,
            policy=policy,
            parser_id=profile["id"],
            detected_media_type=profile["media_type"],
        )
    return _safe_result(
        attachment_id=attachment_id,
        filename=filename,
        content=content,
        extension=extension,
        profile=profile,
        metadata=metadata,
        policy=policy,
    )


def scan_attachments(
    values: Sequence[Any],
    *,
    parser_registry_path: Path | str = PARSER_REGISTRY_PATH,
    quarantine_rules_path: Path | str = QUARANTINE_RULES_PATH,
) -> list[dict[str, Any]]:
    """Scan a finite sequence in input order without making any external call."""

    if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray, str)):
        return [
            _quarantined(
                attachment_id="INVALID_ATTACHMENT",
                filename="INVALID_FILENAME",
                content=None,
                extension="",
                reason_codes=["BATCH_INPUT_INVALID_QUARANTINE"],
                policy=None,
            )
        ]
    return [
        scan_attachment(
            value,
            parser_registry_path=parser_registry_path,
            quarantine_rules_path=quarantine_rules_path,
        )
        for value in values
    ]


__all__ = [
    "AttachmentSandboxError",
    "CONTRACT_ID",
    "PARSER_REGISTRY_PATH",
    "QUARANTINE_RULES_PATH",
    "REQUIREMENT_ID",
    "SCHEMA_VERSION",
    "VERSION",
    "load_policy",
    "sandbox_plan",
    "scan_attachment",
    "scan_attachments",
]
