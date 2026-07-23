"""Bounded, non-executing MIME attachment classification and quarantine."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import time
import unicodedata
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from email import policy
from email.message import Message
from email.parser import BytesParser
from enum import StrEnum
from pathlib import PurePosixPath

import pikepdf

from .canonical_raw import CanonicalRaw

_PDF_ACTIVE_KEYS = frozenset(
    {
        "/aa",
        "/acroform",
        "/embeddedfile",
        "/embeddedfiles",
        "/importdata",
        "/javascript",
        "/js",
        "/launch",
        "/openaction",
        "/richmedia",
        "/submitform",
        "/xfa",
    }
)
_PDF_ACTIVE_NAMES = frozenset(
    {
        "/3d",
        "/embeddedfile",
        "/gotoe",
        "/gotor",
        "/importdata",
        "/javascript",
        "/launch",
        "/movie",
        "/rendition",
        "/richmedia",
        "/screen",
        "/sound",
        "/submitform",
        "/uri",
    }
)
_PDF_MAX_GRAPH_DEPTH = 64
_PDF_MAX_GRAPH_NODES = 100_000


class AttachmentInspectionError(RuntimeError):
    """Attachment inspection failed without exposing input content."""


class AttachmentDecision(StrEnum):
    SAFE = "SAFE"
    QUARANTINED = "QUARANTINED"
    UNSUPPORTED = "UNSUPPORTED"


class AttachmentKind(StrEnum):
    PDF = "PDF"
    XLSX = "XLSX"
    CSV = "CSV"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AttachmentLimits:
    maximum_parts: int = 512
    maximum_depth: int = 12
    maximum_attachments: int = 256
    maximum_attachment_bytes: int = 32 * 1024 * 1024
    maximum_total_decoded_bytes: int = 64 * 1024 * 1024
    maximum_zip_entries: int = 1024
    maximum_zip_uncompressed_bytes: int = 256 * 1024 * 1024
    maximum_zip_ratio: int = 100
    maximum_csv_rows: int = 100_000
    maximum_csv_columns: int = 1_024
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        values = (
            self.maximum_parts,
            self.maximum_depth,
            self.maximum_attachments,
            self.maximum_attachment_bytes,
            self.maximum_total_decoded_bytes,
            self.maximum_zip_entries,
            self.maximum_zip_uncompressed_bytes,
            self.maximum_zip_ratio,
            self.maximum_csv_rows,
            self.maximum_csv_columns,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("attachment limits must be positive integers")
        if (
            self.timeout_seconds <= 0
            or self.maximum_total_decoded_bytes < self.maximum_attachment_bytes
        ):
            raise ValueError("attachment aggregate limits are invalid")


@dataclass(frozen=True, slots=True, repr=False)
class InspectedAttachment:
    ordinal: int
    filename: str
    declared_content_type: str
    decision: AttachmentDecision
    kind: AttachmentKind
    reason_code: str
    byte_count: int | None
    plaintext_sha256: str | None
    content: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        if self.ordinal <= 0 or not self.filename or not self.declared_content_type:
            raise AttachmentInspectionError("attachment identity is invalid")
        if self.content is None:
            if self.byte_count is not None or self.plaintext_sha256 is not None:
                raise AttachmentInspectionError("attachment content metadata is inconsistent")
        elif (
            self.byte_count != len(self.content)
            or self.plaintext_sha256 != hashlib.sha256(self.content).hexdigest()
        ):
            raise AttachmentInspectionError("attachment content digest is invalid")

    def __repr__(self) -> str:
        return (
            f"InspectedAttachment(ordinal={self.ordinal}, filename=<redacted>, "
            f"declared_content_type={self.declared_content_type!r}, "
            f"decision={self.decision.value!r}, kind={self.kind.value!r}, "
            f"reason_code={self.reason_code!r}, byte_count=<redacted>, "
            "plaintext_sha256=<redacted>, content=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class AttachmentInspectionReport:
    canonical_plaintext_sha256: str
    attachments: tuple[InspectedAttachment, ...]
    message_quarantined: bool
    message_reason_code: str | None
    parts_seen: int
    total_decoded_bytes: int

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"[0-9a-f]{64}", self.canonical_plaintext_sha256) is None
            or self.parts_seen < 0
            or self.total_decoded_bytes < 0
            or tuple(item.ordinal for item in self.attachments)
            != tuple(range(1, len(self.attachments) + 1))
        ):
            raise AttachmentInspectionError("attachment report identity is invalid")

    def __repr__(self) -> str:
        return (
            "AttachmentInspectionReport(canonical_plaintext_sha256=<redacted>, "
            f"attachments={len(self.attachments)}, "
            f"message_quarantined={self.message_quarantined}, "
            f"message_reason_code={self.message_reason_code!r}, parts_seen={self.parts_seen}, "
            "total_decoded_bytes=<redacted>)"
        )


@dataclass(slots=True)
class _InspectionState:
    started_at: float
    parts_seen: int = 0
    total_decoded_bytes: int = 0
    attachments: list[InspectedAttachment] = field(default_factory=list)


class AttachmentInspector:
    """Inspect bounded bytes only; never extract paths, run code, or access a network."""

    def __init__(
        self,
        limits: AttachmentLimits | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = limits or AttachmentLimits()
        self._clock = clock

    def inspect(self, canonical: CanonicalRaw) -> AttachmentInspectionReport:
        state = _InspectionState(self._clock())
        try:
            message = BytesParser(policy=policy.default).parsebytes(canonical.data)
            if message.defects:
                raise AttachmentInspectionError("MALFORMED_MIME")
            self._visit(message, 0, state)
        except AttachmentInspectionError as exc:
            code = str(exc) if str(exc).isupper() else "INSPECTION_FAILED"
            return AttachmentInspectionReport(
                canonical.plaintext_sha256,
                tuple(state.attachments),
                True,
                code,
                state.parts_seen,
                state.total_decoded_bytes,
            )
        except Exception:
            return AttachmentInspectionReport(
                canonical.plaintext_sha256,
                tuple(state.attachments),
                True,
                "INSPECTION_FAILED",
                state.parts_seen,
                state.total_decoded_bytes,
            )
        return AttachmentInspectionReport(
            canonical.plaintext_sha256,
            tuple(state.attachments),
            False,
            None,
            state.parts_seen,
            state.total_decoded_bytes,
        )

    def _visit(self, part: Message, depth: int, state: _InspectionState) -> None:
        self._check_limits(depth, state)
        state.parts_seen += 1
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        content_type = part.get_content_type().casefold()
        if content_type == "message/rfc822":
            if len(state.attachments) >= self._limits.maximum_attachments:
                raise AttachmentInspectionError("ATTACHMENT_COUNT_LIMIT")
            ordinal = len(state.attachments) + 1
            safe_filename = filename or f"unnamed-{ordinal}.eml"
            state.attachments.append(
                _attachment_without_content(
                    ordinal,
                    safe_filename,
                    content_type,
                    AttachmentDecision.QUARANTINED,
                    "NESTED_MESSAGE",
                )
            )
            return
        if part.is_multipart():
            payload = part.get_payload()
            if not isinstance(payload, list):
                raise AttachmentInspectionError("MALFORMED_MULTIPART")
            for child in payload:
                if not isinstance(child, Message):
                    raise AttachmentInspectionError("MALFORMED_MULTIPART")
                self._visit(child, depth + 1, state)
            return
        is_attachment = filename is not None or disposition in {"attachment", "inline"}
        if not is_attachment:
            return
        if len(state.attachments) >= self._limits.maximum_attachments:
            raise AttachmentInspectionError("ATTACHMENT_COUNT_LIMIT")
        ordinal = len(state.attachments) + 1
        safe_filename = filename or f"unnamed-{ordinal}"
        if not _safe_filename(safe_filename):
            state.attachments.append(
                _attachment_without_content(
                    ordinal,
                    safe_filename,
                    content_type,
                    AttachmentDecision.QUARANTINED,
                    "UNSAFE_FILENAME",
                )
            )
            return
        raw_payload = part.get_payload()
        encoded_length = (
            len(raw_payload.encode("utf-8", errors="surrogatepass"))
            if isinstance(raw_payload, str)
            else 0
        )
        if encoded_length > self._limits.maximum_attachment_bytes * 2:
            state.attachments.append(
                _attachment_without_content(
                    ordinal,
                    safe_filename,
                    content_type,
                    AttachmentDecision.QUARANTINED,
                    "ENCODED_SIZE_LIMIT",
                )
            )
            return
        try:
            content = part.get_payload(decode=True)
        except Exception:
            content = None
        if not isinstance(content, bytes):
            state.attachments.append(
                _attachment_without_content(
                    ordinal,
                    safe_filename,
                    content_type,
                    AttachmentDecision.QUARANTINED,
                    "DECODE_FAILED",
                )
            )
            return
        if len(content) > self._limits.maximum_attachment_bytes:
            state.attachments.append(
                _attachment_without_content(
                    ordinal,
                    safe_filename,
                    content_type,
                    AttachmentDecision.QUARANTINED,
                    "DECODED_SIZE_LIMIT",
                )
            )
            return
        state.total_decoded_bytes += len(content)
        if state.total_decoded_bytes > self._limits.maximum_total_decoded_bytes:
            raise AttachmentInspectionError("TOTAL_DECODED_SIZE_LIMIT")
        decision, kind, reason = self._classify(safe_filename, content_type, content, state)
        state.attachments.append(
            InspectedAttachment(
                ordinal=ordinal,
                filename=safe_filename,
                declared_content_type=content_type,
                decision=decision,
                kind=kind,
                reason_code=reason,
                byte_count=len(content),
                plaintext_sha256=hashlib.sha256(content).hexdigest(),
                content=content,
            )
        )

    def _classify(
        self,
        filename: str,
        content_type: str,
        content: bytes,
        state: _InspectionState,
    ) -> tuple[AttachmentDecision, AttachmentKind, str]:
        self._check_limits(0, state)
        lowered_name = filename.casefold()
        declared_pdf = content_type == "application/pdf" or lowered_name.endswith(".pdf")
        declared_xlsx = content_type in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel.sheet.macroenabled.12",
        } or lowered_name.endswith((".xlsx", ".xlsm"))
        declared_csv = content_type in {"text/csv", "application/csv"} or lowered_name.endswith(
            ".csv"
        )
        if content.startswith(b"%PDF-"):
            return _classify_pdf(content)
        if declared_pdf:
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "PDF_MAGIC_MISMATCH"
        if content.startswith(b"PK\x03\x04"):
            return self._classify_zip(filename, content, state)
        if declared_xlsx:
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "XLSX_MAGIC_MISMATCH"
        if declared_csv:
            return self._classify_csv(content, state)
        if lowered_name.endswith((".zip", ".tar", ".gz", ".7z", ".rar")):
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "NESTED_ARCHIVE"
        return AttachmentDecision.UNSUPPORTED, AttachmentKind.UNKNOWN, "NO_SAFE_STAGE3_CLASSIFIER"

    def _classify_zip(
        self,
        filename: str,
        content: bytes,
        state: _InspectionState,
    ) -> tuple[AttachmentDecision, AttachmentKind, str]:
        if not filename.casefold().endswith(".xlsx"):
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "NESTED_ARCHIVE"
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                infos = archive.infolist()
        except (OSError, zipfile.BadZipFile, NotImplementedError):
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "MALFORMED_XLSX"
        self._check_limits(0, state)
        if not infos or len(infos) > self._limits.maximum_zip_entries:
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "ZIP_ENTRY_LIMIT"
        names: set[str] = set()
        total_uncompressed = 0
        total_compressed = 0
        required = {"[Content_Types].xml", "xl/workbook.xml"}
        for info in infos:
            name = info.filename
            normalized = PurePosixPath(name.replace("\\", "/"))
            if (
                not name
                or name in names
                or normalized.is_absolute()
                or any(segment in {"", ".", ".."} for segment in normalized.parts)
                or "\\" in name
                or info.flag_bits & 0x1
                or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "UNSAFE_XLSX_ENTRY"
            names.add(name)
            total_uncompressed += info.file_size
            total_compressed += max(info.compress_size, 1)
            if any(
                token in name.casefold()
                for token in ("vbaproject.bin", "macrosheets", "externallinks", "embeddings/")
            ):
                return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "ACTIVE_XLSX_CONTENT"
        if not required.issubset(names):
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "XLSX_STRUCTURE_MISSING"
        if (
            total_uncompressed > self._limits.maximum_zip_uncompressed_bytes
            or total_uncompressed > total_compressed * self._limits.maximum_zip_ratio
        ):
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "ZIP_BOMB_LIMIT"
        return AttachmentDecision.SAFE, AttachmentKind.XLSX, "XLSX_CONTAINER_BOUNDED"

    def _classify_csv(
        self,
        content: bytes,
        state: _InspectionState,
    ) -> tuple[AttachmentDecision, AttachmentKind, str]:
        if b"\x00" in content:
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "CSV_NUL_BYTE"
        try:
            text = content.decode("utf-8-sig", errors="strict")
            rows = csv.reader(io.StringIO(text, newline=""), strict=True)
            for row_number, row in enumerate(rows, start=1):
                self._check_limits(0, state)
                if (
                    row_number > self._limits.maximum_csv_rows
                    or len(row) > self._limits.maximum_csv_columns
                ):
                    return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "CSV_SHAPE_LIMIT"
                for cell in row:
                    if len(cell) > 1_000_000:
                        return (
                            AttachmentDecision.QUARANTINED,
                            AttachmentKind.UNKNOWN,
                            "CSV_CELL_LIMIT",
                        )
                    normalized = unicodedata.normalize("NFKC", cell)
                    if any(
                        unicodedata.category(character).startswith("C") for character in normalized
                    ):
                        return (
                            AttachmentDecision.QUARANTINED,
                            AttachmentKind.UNKNOWN,
                            "CSV_CONTROL_CHARACTER",
                        )
                    stripped = normalized.lstrip()
                    numeric = re.fullmatch(r"[-+]?[0-9]+(?:\.[0-9]+)?", stripped) is not None
                    if stripped.startswith(("=", "@")) or (
                        stripped.startswith(("+", "-")) and not numeric
                    ):
                        return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "CSV_FORMULA"
        except (UnicodeDecodeError, csv.Error):
            return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "MALFORMED_CSV"
        return AttachmentDecision.SAFE, AttachmentKind.CSV, "CSV_BOUNDED_TEXT"

    def _check_limits(self, depth: int, state: _InspectionState) -> None:
        if self._clock() - state.started_at > self._limits.timeout_seconds:
            raise AttachmentInspectionError("INSPECTION_TIMEOUT")
        if depth > self._limits.maximum_depth:
            raise AttachmentInspectionError("MIME_DEPTH_LIMIT")
        if state.parts_seen >= self._limits.maximum_parts:
            raise AttachmentInspectionError("MIME_PART_LIMIT")


def _classify_pdf(
    content: bytes,
) -> tuple[AttachmentDecision, AttachmentKind, str]:
    normalized_names = re.sub(
        rb"#([0-9A-Fa-f]{2})",
        lambda match: bytes((int(match.group(1), 16),)),
        content,
    )
    lowered = normalized_names.lower()
    eof = content.rfind(b"%%EOF")
    if eof < 0 or content[eof + 5 :].strip():
        return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "MALFORMED_PDF"
    if b"PK\x03\x04" in content or any(
        token in lowered
        for token in (
            b"/javascript",
            b"/js",
            b"/launch",
            b"/openaction",
            b"/embeddedfile",
            b"/richmedia",
        )
    ):
        return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "ACTIVE_OR_POLYGLOT_PDF"
    try:
        with pikepdf.Pdf.open(
            io.BytesIO(content),
            password="",
            attempt_recovery=False,
            suppress_warnings=True,
        ) as document:
            if pdf_has_active_objects(document):
                return (
                    AttachmentDecision.QUARANTINED,
                    AttachmentKind.UNKNOWN,
                    "ACTIVE_OR_POLYGLOT_PDF",
                )
    except pikepdf.PasswordError:
        return AttachmentDecision.SAFE, AttachmentKind.PDF, "PDF_ENCRYPTED_DEFERRED"
    except (pikepdf.PdfError, OSError, RuntimeError, TypeError, ValueError):
        return AttachmentDecision.QUARANTINED, AttachmentKind.UNKNOWN, "MALFORMED_PDF"
    return AttachmentDecision.SAFE, AttachmentKind.PDF, "PDF_OBJECT_GRAPH_BOUNDED"


def pdf_has_active_objects(
    document: pikepdf.Pdf,
    *,
    maximum_depth: int = _PDF_MAX_GRAPH_DEPTH,
    maximum_nodes: int = _PDF_MAX_GRAPH_NODES,
) -> bool:
    """Return true for active PDF capabilities or an over-limit object graph.

    Pikepdf resolves indirect and compressed objects before this walk. Stream payloads
    are deliberately not decoded; only their dictionaries are inspected.
    """

    if maximum_depth <= 0 or maximum_nodes <= 0:
        raise ValueError("PDF graph limits must be positive")
    stack: list[tuple[object, int]] = [(document.Root, 0)]
    stack.extend((item, 0) for item in document.objects)
    seen: set[tuple[str, int, int] | tuple[str, int]] = set()
    visited = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        if depth > maximum_depth or visited > maximum_nodes:
            return True
        if isinstance(item, pikepdf.Name):
            if str(item).casefold() in _PDF_ACTIVE_NAMES:
                return True
            continue
        if not isinstance(item, pikepdf.Object):
            continue
        objgen = item.objgen
        identity: tuple[str, int, int] | tuple[str, int]
        if objgen != (0, 0):
            identity = ("indirect", objgen[0], objgen[1])
        else:
            identity = ("direct", id(item))
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(item, (pikepdf.Dictionary, pikepdf.Stream)):
            try:
                entries = tuple(item.items())
            except (pikepdf.PdfError, RuntimeError, TypeError, ValueError):
                return True
            for key, value in entries:
                if str(key).casefold() in _PDF_ACTIVE_KEYS:
                    return True
                stack.append((value, depth + 1))
        elif isinstance(item, pikepdf.Array):
            try:
                stack.extend((value, depth + 1) for value in item)
            except (pikepdf.PdfError, RuntimeError, TypeError, ValueError):
                return True
    return False


def _safe_filename(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value)
    path = PurePosixPath(normalized.replace("\\", "/"))
    return (
        normalized == value
        and 0 < len(value) <= 255
        and not path.is_absolute()
        and path.name == value
        and all(segment not in {"", ".", ".."} for segment in path.parts)
        and not any(unicodedata.category(character).startswith("C") for character in value)
    )


def _attachment_without_content(
    ordinal: int,
    filename: str,
    content_type: str,
    decision: AttachmentDecision,
    reason_code: str,
) -> InspectedAttachment:
    return InspectedAttachment(
        ordinal=ordinal,
        filename=filename,
        declared_content_type=content_type,
        decision=decision,
        kind=AttachmentKind.UNKNOWN,
        reason_code=reason_code,
        byte_count=None,
        plaintext_sha256=None,
        content=None,
    )
