"""Bounded attachment extraction and profile-driven statement parsing for Stage 4."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, cast

import openpyxl
import pikepdf
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .attachment_inspector import (
    AttachmentDecision,
    AttachmentInspectionReport,
    AttachmentKind,
    pdf_has_active_objects,
)
from .processed_models import (
    DocumentClass,
    DocumentClassification,
    DocumentEnvelope,
    ProcessingBoundaryError,
    ProcessingState,
)
from .secret_values import SecretText

_PROFILE_SCHEMA = "moomooau.parser-profile-registry.v1"
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_PROFILE_ID = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
_PARSER_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_PARSER_SENTINEL = object()


class ExtractionState(StrEnum):
    READY = "READY"
    WAITING_FOR_PDF_PASSWORD = "WAITING_FOR_PDF_PASSWORD"  # pragma: allowlist secret
    UNSUPPORTED = "UNSUPPORTED"
    QUARANTINED = "QUARANTINED"


class ValueKind(StrEnum):
    TEXT = "TEXT"
    DATE = "DATE"
    DECIMAL = "DECIMAL"
    CURRENCY = "CURRENCY"


class ParserActivation(StrEnum):
    ACTIVE = "ACTIVE"
    EMPTY_PROTECTED_EVIDENCE_REQUIRED = "EMPTY_PROTECTED_EVIDENCE_REQUIRED"


class ProcessingDisposition(StrEnum):
    COMPLETE = "COMPLETE"
    SAFE_DEFERRED = "SAFE_DEFERRED"
    BLOCKED = "BLOCKED"


class StatementType(StrEnum):
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    FINANCIAL_YEAR = "FINANCIAL_YEAR"
    CONTRACT_NOTE = "CONTRACT_NOTE"


@dataclass(frozen=True, slots=True, repr=False)
class ExtractedArtifact:
    ordinal: int
    kind: AttachmentKind
    source_plaintext_sha256: str
    rows: tuple[tuple[str, ...], ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.ordinal <= 0
            or self.kind not in {AttachmentKind.PDF, AttachmentKind.XLSX, AttachmentKind.CSV}
            or _SHA256.fullmatch(self.source_plaintext_sha256) is None
            or not self.rows
            or len(self.rows) > 100_000
            or any(not row or len(row) > 256 for row in self.rows)
            or any(len(cell) > 1_000_000 for row in self.rows for cell in row)
        ):
            raise ProcessingBoundaryError("extracted artifact is invalid")

    def __repr__(self) -> str:
        return (
            f"ExtractedArtifact(ordinal={self.ordinal}, kind={self.kind.value!r}, "
            "source_plaintext_sha256=<redacted>, rows=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ExtractionBatch:
    state: ExtractionState
    reason_code: str
    canonical_plaintext_sha256: str
    artifacts: tuple[ExtractedArtifact, ...]

    def __post_init__(self) -> None:
        if (
            not self.reason_code
            or _SHA256.fullmatch(self.canonical_plaintext_sha256) is None
            or (self.state is ExtractionState.READY) != bool(self.artifacts)
            or tuple(item.ordinal for item in self.artifacts)
            != tuple(sorted(item.ordinal for item in self.artifacts))
            or len({item.ordinal for item in self.artifacts}) != len(self.artifacts)
        ):
            raise ProcessingBoundaryError("extraction batch is invalid")

    def __repr__(self) -> str:
        return (
            f"ExtractionBatch(state={self.state.value!r}, reason_code={self.reason_code!r}, "
            "canonical_plaintext_sha256=<redacted>, "
            f"artifact_count={len(self.artifacts)})"
        )


class SafeArtifactExtractor:
    """Decode bounded in-memory content; never writes files, executes content or uses a network."""

    def __init__(
        self,
        *,
        maximum_pdf_pages: int = 200,
        maximum_pdf_characters: int = 4_000_000,
        maximum_sheets: int = 64,
        maximum_rows: int = 100_000,
        maximum_columns: int = 256,
    ) -> None:
        if (
            min(
                maximum_pdf_pages,
                maximum_pdf_characters,
                maximum_sheets,
                maximum_rows,
                maximum_columns,
            )
            <= 0
        ):
            raise ValueError("artifact extraction limits must be positive")
        self._maximum_pdf_pages = maximum_pdf_pages
        self._maximum_pdf_characters = maximum_pdf_characters
        self._maximum_sheets = maximum_sheets
        self._maximum_rows = maximum_rows
        self._maximum_columns = maximum_columns

    def extract(
        self,
        report: AttachmentInspectionReport,
        *,
        pdf_passwords: dict[int, SecretText] | None = None,
    ) -> ExtractionBatch:
        if report.message_quarantined:
            return self._empty(report, ExtractionState.QUARANTINED, "MESSAGE_QUARANTINED")
        passwords = pdf_passwords or {}
        if any(ordinal <= 0 for ordinal in passwords):
            raise ProcessingBoundaryError("PDF password mapping is invalid")
        artifacts: list[ExtractedArtifact] = []
        for attachment in report.attachments:
            if attachment.decision is AttachmentDecision.QUARANTINED:
                return self._empty(
                    report,
                    ExtractionState.QUARANTINED,
                    "ATTACHMENT_QUARANTINED",
                )
            if attachment.decision is not AttachmentDecision.SAFE:
                continue
            if attachment.content is None or attachment.plaintext_sha256 is None:
                return self._empty(
                    report,
                    ExtractionState.QUARANTINED,
                    "SAFE_ATTACHMENT_CONTENT_MISSING",
                )
            try:
                if attachment.kind is AttachmentKind.CSV:
                    rows = self._extract_csv(attachment.content)
                elif attachment.kind is AttachmentKind.XLSX:
                    rows = self._extract_xlsx(attachment.content)
                elif attachment.kind is AttachmentKind.PDF:
                    pdf_result = self._extract_pdf(
                        attachment.content,
                        passwords.get(attachment.ordinal),
                    )
                    if pdf_result is None:
                        return self._empty(
                            report,
                            ExtractionState.WAITING_FOR_PDF_PASSWORD,
                            "PDF_PASSWORD_REQUIRED_OR_INVALID",
                        )
                    rows = pdf_result
                else:
                    return self._empty(
                        report,
                        ExtractionState.UNSUPPORTED,
                        "SUPPORTED_PARSER_NOT_AVAILABLE",
                    )
            except ProcessingBoundaryError:
                return self._empty(
                    report,
                    ExtractionState.QUARANTINED,
                    "ARTIFACT_EXTRACTION_FAILED",
                )
            artifacts.append(
                ExtractedArtifact(
                    ordinal=attachment.ordinal,
                    kind=attachment.kind,
                    source_plaintext_sha256=attachment.plaintext_sha256,
                    rows=rows,
                )
            )
        if not artifacts:
            return self._empty(
                report,
                ExtractionState.UNSUPPORTED,
                "NO_SUPPORTED_SAFE_ATTACHMENT",
            )
        return ExtractionBatch(
            state=ExtractionState.READY,
            reason_code="BOUNDED_EXTRACTION_COMPLETE",
            canonical_plaintext_sha256=report.canonical_plaintext_sha256,
            artifacts=tuple(sorted(artifacts, key=lambda item: item.ordinal)),
        )

    @staticmethod
    def _empty(
        report: AttachmentInspectionReport,
        state: ExtractionState,
        reason_code: str,
    ) -> ExtractionBatch:
        return ExtractionBatch(
            state=state,
            reason_code=reason_code,
            canonical_plaintext_sha256=report.canonical_plaintext_sha256,
            artifacts=(),
        )

    def _extract_csv(self, content: bytes) -> tuple[tuple[str, ...], ...]:
        try:
            text = content.decode("utf-8-sig", errors="strict")
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            rows = self._normalize_rows(tuple(tuple(row) for row in reader))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ProcessingBoundaryError("CSV extraction failed") from exc
        return rows

    def _extract_xlsx(self, content: bytes) -> tuple[tuple[str, ...], ...]:
        workbook: Any | None = None
        collected: list[tuple[str, ...]] = []
        try:
            workbook = openpyxl.load_workbook(
                io.BytesIO(content),
                read_only=True,
                data_only=False,
                keep_links=False,
                keep_vba=False,
            )
            worksheets = workbook.worksheets
            if len(worksheets) > self._maximum_sheets:
                raise ProcessingBoundaryError("XLSX sheet limit exceeded")
            for sheet in worksheets:
                for row_number, cells in enumerate(sheet.iter_rows(), start=1):
                    if row_number > self._maximum_rows:
                        raise ProcessingBoundaryError("XLSX row limit exceeded")
                    if len(cells) > self._maximum_columns:
                        raise ProcessingBoundaryError("XLSX column limit exceeded")
                    values: list[str] = []
                    for cell in cells:
                        if getattr(cell, "data_type", None) == "f":
                            raise ProcessingBoundaryError("XLSX formula is prohibited")
                        values.append(_cell_text(getattr(cell, "value", None)))
                    trimmed = _trim_row(tuple(values))
                    if trimmed:
                        collected.append(trimmed)
                        if len(collected) > self._maximum_rows:
                            raise ProcessingBoundaryError("XLSX aggregate row limit exceeded")
        except ProcessingBoundaryError:
            raise
        except Exception as exc:
            raise ProcessingBoundaryError("XLSX extraction failed") from exc
        finally:
            if workbook is not None:
                close = getattr(workbook, "close", None)
                if callable(close):
                    close()
        if not collected:
            raise ProcessingBoundaryError("XLSX has no usable rows")
        return tuple(collected)

    def _extract_pdf(
        self,
        content: bytes,
        password_secret: SecretText | None,
    ) -> tuple[tuple[str, ...], ...] | None:
        password = password_secret.reveal() if password_secret is not None else ""
        try:
            with pikepdf.Pdf.open(
                io.BytesIO(content),
                password=password,
                attempt_recovery=False,
                suppress_warnings=True,
            ) as checked:
                if len(checked.pages) <= 0 or len(checked.pages) > self._maximum_pdf_pages:
                    raise ProcessingBoundaryError("PDF page limit is invalid")
                if pdf_has_active_objects(checked):
                    raise ProcessingBoundaryError("active PDF content is prohibited")
            reader = PdfReader(
                io.BytesIO(content),
                strict=True,
                password=password,
                root_object_recovery_limit=0,
            )
            if len(reader.pages) <= 0 or len(reader.pages) > self._maximum_pdf_pages:
                raise ProcessingBoundaryError("PDF reader page limit is invalid")
            rows: list[tuple[str, ...]] = []
            character_count = 0
            for page in reader.pages:
                text = page.extract_text(extraction_mode="plain") or ""
                character_count += len(text)
                if character_count > self._maximum_pdf_characters:
                    raise ProcessingBoundaryError("PDF text limit exceeded")
                for line in text.splitlines():
                    normalized = _safe_text(line, maximum=1_000_000).strip()
                    if normalized:
                        rows.append((normalized,))
                        if len(rows) > self._maximum_rows:
                            raise ProcessingBoundaryError("PDF line limit exceeded")
        except pikepdf.PasswordError:
            return None
        except ProcessingBoundaryError:
            raise
        except (pikepdf.PdfError, PyPdfError, OSError, ValueError, TypeError) as exc:
            raise ProcessingBoundaryError("PDF extraction failed") from exc
        if not rows:
            raise ProcessingBoundaryError("PDF has no extractable text")
        return tuple(rows)

    def _normalize_rows(
        self,
        rows: tuple[tuple[str, ...], ...],
    ) -> tuple[tuple[str, ...], ...]:
        if len(rows) > self._maximum_rows:
            raise ProcessingBoundaryError("table row limit exceeded")
        normalized_rows: list[tuple[str, ...]] = []
        for row in rows:
            if len(row) > self._maximum_columns:
                raise ProcessingBoundaryError("table column limit exceeded")
            normalized = tuple(_safe_cell_text(cell, maximum=1_000_000) for cell in row)
            trimmed = _trim_row(normalized)
            if trimmed:
                normalized_rows.append(trimmed)
        if not normalized_rows:
            raise ProcessingBoundaryError("table has no usable rows")
        return tuple(normalized_rows)


@dataclass(frozen=True, slots=True, repr=False)
class FieldRule:
    output_name: str
    labels: tuple[str, ...]
    value_kind: ValueKind
    required: bool
    date_formats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            _FIELD_NAME.fullmatch(self.output_name) is None
            or not self.labels
            or len(self.labels) > 16
            or len(set(_fold(value) for value in self.labels)) != len(self.labels)
            or any(not _profile_text(value) for value in self.labels)
            or (self.value_kind is ValueKind.DATE) != bool(self.date_formats)
            or len(self.date_formats) > 8
            or any(not value or len(value) > 64 for value in self.date_formats)
        ):
            raise ProcessingBoundaryError("parser field rule is invalid")

    def __repr__(self) -> str:
        return (
            f"FieldRule(output_name={self.output_name!r}, labels=<redacted>, "
            f"value_kind={self.value_kind.value!r}, required={self.required})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TableColumnRule:
    output_name: str
    labels: tuple[str, ...]
    value_kind: ValueKind
    required: bool
    date_formats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        FieldRule(
            self.output_name,
            self.labels,
            self.value_kind,
            self.required,
            self.date_formats,
        )

    def __repr__(self) -> str:
        return (
            f"TableColumnRule(output_name={self.output_name!r}, labels=<redacted>, "
            f"value_kind={self.value_kind.value!r}, required={self.required})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ParserProfile:
    profile_id: str
    parser_name: str
    parser_version: str
    document_class: DocumentClass
    supported_kinds: tuple[AttachmentKind, ...]
    fields: tuple[FieldRule, ...]
    table_columns: tuple[TableColumnRule, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        supported_classes = {
            DocumentClass.DAILY_STATEMENT,
            DocumentClass.MONTHLY_STATEMENT,
            DocumentClass.FINANCIAL_YEAR_SUMMARY,
            DocumentClass.CONTRACT_NOTE,
        }
        names = [rule.output_name for rule in self.fields]
        table_names = [rule.output_name for rule in self.table_columns]
        if (
            _PROFILE_ID.fullmatch(self.profile_id) is None
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _SEMVER.fullmatch(self.parser_version) is None
            or self.document_class not in supported_classes
            or not self.supported_kinds
            or any(
                kind not in {AttachmentKind.PDF, AttachmentKind.XLSX, AttachmentKind.CSV}
                for kind in self.supported_kinds
            )
            or len(set(self.supported_kinds)) != len(self.supported_kinds)
            or not (self.fields or self.table_columns)
            or len(names) != len(set(names))
            or len(table_names) != len(set(table_names))
            or set(names) & set(table_names)
            or _SHA256.fullmatch(self.evidence_digest) is None
        ):
            raise ProcessingBoundaryError("parser profile identity is invalid")

    def __repr__(self) -> str:
        return (
            f"ParserProfile(profile_id=<redacted>, parser_name={self.parser_name!r}, "
            f"parser_version={self.parser_version!r}, "
            f"document_class={self.document_class.value!r}, rules=<redacted>, "
            "evidence_digest=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ParserProfileRegistry:
    registry_version: str
    issued_at_utc: datetime
    activation: ParserActivation
    profiles: tuple[ParserProfile, ...]
    digest: str

    def __post_init__(self) -> None:
        offset = self.issued_at_utc.utcoffset()
        keys = [
            (item.document_class.value, item.parser_version, item.profile_id)
            for item in self.profiles
        ]
        if (
            _SEMVER.fullmatch(self.registry_version) is None
            or self.issued_at_utc.tzinfo is None
            or offset is None
            or offset.total_seconds() != 0
            or _SHA256.fullmatch(self.digest) is None
            or keys != sorted(keys)
            or len(keys) != len(set(keys))
            or (self.activation is ParserActivation.ACTIVE) != bool(self.profiles)
        ):
            raise ProcessingBoundaryError("parser profile registry is invalid")

    def __repr__(self) -> str:
        return (
            f"ParserProfileRegistry(version={self.registry_version!r}, "
            f"activation={self.activation.value!r}, profile_count={len(self.profiles)}, "
            "digest=<redacted>)"
        )

    @classmethod
    def from_json(cls, payload: bytes) -> ParserProfileRegistry:
        if len(payload) > 4 * 1024 * 1024:
            raise ProcessingBoundaryError("parser profile registry exceeds the safe limit")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProcessingBoundaryError("parser profile registry is not valid JSON") from exc
        required = {
            "schema_version",
            "registry_version",
            "issued_at_utc",
            "activation_state",
            "profiles",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ProcessingBoundaryError("parser profile registry schema is invalid")
        profiles = value.get("profiles")
        if value.get("schema_version") != _PROFILE_SCHEMA or not isinstance(profiles, list):
            raise ProcessingBoundaryError("parser profile registry schema is invalid")
        try:
            return cls(
                registry_version=_required_string(value, "registry_version"),
                issued_at_utc=_parse_utc(_required_string(value, "issued_at_utc")),
                activation=ParserActivation(_required_string(value, "activation_state")),
                profiles=tuple(_parse_profile(item) for item in profiles),
                digest=_digest_json(value),
            )
        except ValueError as exc:
            raise ProcessingBoundaryError("parser profile registry enum value is invalid") from exc

    def current_for(self, document_class: DocumentClass) -> ParserProfile | None:
        matches = [item for item in self.profiles if item.document_class is document_class]
        if not matches:
            return None
        versions = {item.parser_version for item in matches}
        if len(versions) != len(matches):
            raise ProcessingBoundaryError("multiple parser profiles share a version")
        return max(matches, key=lambda item: _semver_key(item.parser_version))


@dataclass(frozen=True, slots=True, repr=False)
class ParsedStatement:
    schema_version: str
    source_id: str
    document_class: DocumentClass
    statement_type: StatementType
    statement_label_date: date | None
    currency: str | None
    summary: tuple[tuple[str, str | None], ...] = field(repr=False)
    transactions: tuple[tuple[tuple[str, str | None], ...], ...] = field(repr=False)
    field_lineage: tuple[tuple[str, str], ...] = field(repr=False)
    parser_name: str
    parser_version: str
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        summary_names = [name for name, _ in self.summary]
        if (
            self._sentinel is not _PARSER_SENTINEL
            or self.schema_version != "1.0.0"
            or re.fullmatch(r"^[0-9a-f]{64}$", self.source_id) is None
            or (self.currency is not None and _CURRENCY.fullmatch(self.currency) is None)
            or summary_names != sorted(summary_names)
            or len(summary_names) != len(set(summary_names))
            or any(_FIELD_NAME.fullmatch(name) is None for name in summary_names)
            or any(
                [name for name, _ in row] != sorted(name for name, _ in row)
                or len({name for name, _ in row}) != len(row)
                for row in self.transactions
            )
            or not self.field_lineage
            or [key for key, _ in self.field_lineage]
            != sorted(key for key, _ in self.field_lineage)
            or len({key for key, _ in self.field_lineage}) != len(self.field_lineage)
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _SEMVER.fullmatch(self.parser_version) is None
        ):
            raise ProcessingBoundaryError("parsed statement is invalid")

    def __repr__(self) -> str:
        return (
            f"ParsedStatement(schema_version={self.schema_version!r}, source_id=<redacted>, "
            f"document_class={self.document_class.value!r}, "
            f"statement_type={self.statement_type.value!r}, "
            "statement_label_date=<redacted>, currency=<redacted>, summary=<redacted>, "
            f"transaction_count={len(self.transactions)}, field_lineage=<redacted>, "
            f"parser_name={self.parser_name!r}, parser_version={self.parser_version!r})"
        )

    def to_private_dict(self, lineage: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "document_class": self.document_class.value,
            "statement_type": self.statement_type.value,
            "statement_label_date": (
                self.statement_label_date.isoformat()
                if self.statement_label_date is not None
                else None
            ),
            "currency": self.currency,
            "summary": dict(self.summary),
            "transactions": [dict(row) for row in self.transactions],
            "cash_flows": [],
            "lineage": lineage,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ParserOutcome:
    state: ProcessingState
    disposition: ProcessingDisposition
    reason_code: str
    parser_name: str
    parser_version: str
    statement: ParsedStatement | None

    def __post_init__(self) -> None:
        if (
            not self.reason_code
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _SEMVER.fullmatch(self.parser_version) is None
            or (self.state is ProcessingState.COMPLETE) != (self.statement is not None)
            or (self.state is ProcessingState.COMPLETE)
            != (self.disposition is ProcessingDisposition.COMPLETE)
            or (self.state is ProcessingState.QUARANTINED)
            != (self.disposition is ProcessingDisposition.BLOCKED)
            or (
                self.state
                in {
                    ProcessingState.WAITING_FOR_PDF_PASSWORD,
                    ProcessingState.UNSUPPORTED,
                    ProcessingState.RAW_ONLY,
                }
            )
            != (self.disposition is ProcessingDisposition.SAFE_DEFERRED)
        ):
            raise ProcessingBoundaryError("parser outcome is invalid")

    def __repr__(self) -> str:
        return (
            f"ParserOutcome(state={self.state.value!r}, "
            f"disposition={self.disposition.value!r}, reason_code={self.reason_code!r}, "
            f"parser_name={self.parser_name!r}, parser_version={self.parser_version!r}, "
            f"statement_present={self.statement is not None})"
        )


class StatementParser:
    """Interpret exact protected labels; ambiguous or conflicting values never pass."""

    def parse(
        self,
        envelope: DocumentEnvelope,
        classification: DocumentClassification,
        extraction: ExtractionBatch,
        profile: ParserProfile | None,
    ) -> ParserOutcome:
        if (
            envelope.source_id == ""
            or classification.canonical_plaintext_sha256 != extraction.canonical_plaintext_sha256
            or envelope.document_class is not classification.document_class
        ):
            raise ProcessingBoundaryError("parser inputs are not bound to one source")
        fallback_name = profile.parser_name if profile is not None else "protected-profile-parser"
        fallback_version = profile.parser_version if profile is not None else "1.0.0"
        if extraction.state is ExtractionState.WAITING_FOR_PDF_PASSWORD:
            return ParserOutcome(
                ProcessingState.WAITING_FOR_PDF_PASSWORD,
                ProcessingDisposition.SAFE_DEFERRED,
                extraction.reason_code,
                fallback_name,
                fallback_version,
                None,
            )
        if extraction.state is ExtractionState.QUARANTINED:
            return ParserOutcome(
                ProcessingState.QUARANTINED,
                ProcessingDisposition.BLOCKED,
                extraction.reason_code,
                fallback_name,
                fallback_version,
                None,
            )
        if extraction.state is ExtractionState.UNSUPPORTED or profile is None:
            return ParserOutcome(
                ProcessingState.UNSUPPORTED,
                ProcessingDisposition.SAFE_DEFERRED,
                "PROTECTED_PARSER_PROFILE_NOT_AVAILABLE",
                fallback_name,
                fallback_version,
                None,
            )
        if profile.document_class is not classification.document_class or any(
            artifact.kind not in profile.supported_kinds for artifact in extraction.artifacts
        ):
            return ParserOutcome(
                ProcessingState.QUARANTINED,
                ProcessingDisposition.BLOCKED,
                "PARSER_PROFILE_BINDING_MISMATCH",
                profile.parser_name,
                profile.parser_version,
                None,
            )
        observations = _key_value_observations(extraction.artifacts)
        summary: dict[str, str | None] = {}
        lineage: dict[str, str] = {
            "/statement_type": "classification:document-class",
        }
        statement_date: date | None = None
        currency: str | None = None
        try:
            for rule in profile.fields:
                value, origin = _resolve_field(rule, observations)
                if rule.required and value is None:
                    return ParserOutcome(
                        ProcessingState.UNSUPPORTED,
                        ProcessingDisposition.SAFE_DEFERRED,
                        "REQUIRED_FIELD_NOT_OBSERVED",
                        profile.parser_name,
                        profile.parser_version,
                        None,
                    )
                if rule.output_name == "statement_label_date":
                    statement_date = date.fromisoformat(value) if value is not None else None
                elif rule.output_name == "currency":
                    currency = value
                else:
                    summary[rule.output_name] = value
                if origin is not None:
                    lineage["/" + rule.output_name] = origin
            transactions, transaction_lineage = _parse_tables(
                extraction.artifacts,
                profile.table_columns,
            )
            lineage.update(transaction_lineage)
        except ProcessingBoundaryError:
            return ParserOutcome(
                ProcessingState.QUARANTINED,
                ProcessingDisposition.BLOCKED,
                "CONFLICTING_OR_INVALID_PROTECTED_FIELDS",
                profile.parser_name,
                profile.parser_version,
                None,
            )
        statement = ParsedStatement(
            schema_version="1.0.0",
            source_id=envelope.source_id,
            document_class=classification.document_class,
            statement_type=_statement_type(classification.document_class),
            statement_label_date=statement_date,
            currency=currency,
            summary=tuple(sorted(summary.items())),
            transactions=transactions,
            field_lineage=tuple(sorted(lineage.items())),
            parser_name=profile.parser_name,
            parser_version=profile.parser_version,
            _sentinel=_PARSER_SENTINEL,
        )
        return ParserOutcome(
            ProcessingState.COMPLETE,
            ProcessingDisposition.COMPLETE,
            "PROTECTED_PROFILE_PARSE_COMPLETE",
            profile.parser_name,
            profile.parser_version,
            statement,
        )


def _key_value_observations(
    artifacts: tuple[ExtractedArtifact, ...],
) -> dict[str, list[tuple[str, str]]]:
    observations: dict[str, list[tuple[str, str]]] = {}
    for artifact in artifacts:
        for row_index, row in enumerate(artifact.rows, start=1):
            label: str | None = None
            value: str | None = None
            if len(row) == 1 and ":" in row[0]:
                label, value = row[0].split(":", 1)
            elif len(row) == 2:
                label, value = row
            if label is None or value is None or not label.strip():
                continue
            normalized_value = _safe_text(value.strip(), maximum=1_000_000)
            observations.setdefault(_fold(label), []).append(
                (normalized_value, f"attachment:{artifact.ordinal}:row:{row_index}")
            )
    return observations


def _resolve_field(
    rule: FieldRule,
    observations: dict[str, list[tuple[str, str]]],
) -> tuple[str | None, str | None]:
    candidates: list[tuple[str, str]] = []
    for label in rule.labels:
        candidates.extend(observations.get(_fold(label), []))
    converted = [
        (_convert_value(value, rule.value_kind, rule.date_formats), origin)
        for value, origin in candidates
    ]
    unique_values = {value for value, _ in converted}
    if len(unique_values) > 1:
        raise ProcessingBoundaryError("field observations conflict")
    if not converted:
        return None, None
    return converted[0]


def _parse_tables(
    artifacts: tuple[ExtractedArtifact, ...],
    rules: tuple[TableColumnRule, ...],
) -> tuple[tuple[tuple[tuple[str, str | None], ...], ...], dict[str, str]]:
    if not rules:
        return (), {}
    parsed_rows: list[tuple[tuple[str, str | None], ...]] = []
    lineage: dict[str, str] = {}
    matched_header = False
    for artifact in artifacts:
        for header_index, header in enumerate(artifact.rows):
            mapping = _match_table_header(header, rules)
            if mapping is None:
                continue
            if matched_header:
                raise ProcessingBoundaryError("multiple matching table headers are ambiguous")
            matched_header = True
            for row_number, row in enumerate(
                artifact.rows[header_index + 1 :], start=header_index + 2
            ):
                if not any(cell.strip() for cell in row):
                    continue
                output: dict[str, str | None] = {}
                for rule, column in mapping:
                    raw = row[column].strip() if column < len(row) else ""
                    if not raw:
                        if rule.required:
                            raise ProcessingBoundaryError("required table value is missing")
                        output[rule.output_name] = None
                        continue
                    output[rule.output_name] = _convert_value(
                        raw,
                        rule.value_kind,
                        rule.date_formats,
                    )
                    pointer = f"/transactions/{len(parsed_rows)}/{rule.output_name}"
                    lineage[pointer] = (
                        f"attachment:{artifact.ordinal}:row:{row_number}:column:{column + 1}"
                    )
                parsed_rows.append(tuple(sorted(output.items())))
    if not matched_header and any(rule.required for rule in rules):
        raise ProcessingBoundaryError("required table header is absent")
    return tuple(parsed_rows), lineage


def _match_table_header(
    header: tuple[str, ...],
    rules: tuple[TableColumnRule, ...],
) -> tuple[tuple[TableColumnRule, int], ...] | None:
    folded = [_fold(value) for value in header]
    mapping: list[tuple[TableColumnRule, int]] = []
    used: set[int] = set()
    for rule in rules:
        indexes = [
            index
            for index, value in enumerate(folded)
            if value in {_fold(label) for label in rule.labels}
        ]
        if not indexes:
            if rule.required:
                return None
            continue
        if len(indexes) != 1 or indexes[0] in used:
            raise ProcessingBoundaryError("table header is ambiguous")
        used.add(indexes[0])
        mapping.append((rule, indexes[0]))
    return tuple(mapping) if mapping else None


def _convert_value(value: str, kind: ValueKind, date_formats: tuple[str, ...]) -> str:
    normalized = _safe_text(value.strip(), maximum=1_000_000)
    if kind is ValueKind.TEXT:
        return normalized
    if kind is ValueKind.CURRENCY:
        currency = normalized.upper()
        if _CURRENCY.fullmatch(currency) is None:
            raise ProcessingBoundaryError("currency value is invalid")
        return currency
    if kind is ValueKind.DECIMAL:
        if re.fullmatch(r"[-+]?[0-9]+(?:\.[0-9]+)?", normalized) is None:
            raise ProcessingBoundaryError("decimal value is invalid")
        try:
            parsed = Decimal(normalized)
        except InvalidOperation as exc:
            raise ProcessingBoundaryError("decimal value is invalid") from exc
        if not parsed.is_finite():
            raise ProcessingBoundaryError("decimal value is not finite")
        rendered = format(parsed, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return "0" if rendered in {"-0", "+0", ""} else rendered
    parsed_dates: set[date] = set()
    for date_format in date_formats:
        try:
            parsed_dates.add(datetime.strptime(normalized, date_format).date())
        except ValueError:
            continue
    if len(parsed_dates) != 1:
        raise ProcessingBoundaryError("date value is missing or ambiguous")
    return next(iter(parsed_dates)).isoformat()


def _statement_type(document_class: DocumentClass) -> StatementType:
    mapping = {
        DocumentClass.DAILY_STATEMENT: StatementType.DAILY,
        DocumentClass.MONTHLY_STATEMENT: StatementType.MONTHLY,
        DocumentClass.FINANCIAL_YEAR_SUMMARY: StatementType.FINANCIAL_YEAR,
        DocumentClass.CONTRACT_NOTE: StatementType.CONTRACT_NOTE,
    }
    try:
        return mapping[document_class]
    except KeyError as exc:
        raise ProcessingBoundaryError("document class has no statement parser") from exc


def _parse_profile(value: object) -> ParserProfile:
    if not isinstance(value, dict):
        raise ProcessingBoundaryError("parser profile must be an object")
    required = {
        "profile_id",
        "parser_name",
        "parser_version",
        "document_class",
        "supported_kinds",
        "fields",
        "table_columns",
        "evidence_digest",
    }
    if set(value) != required:
        raise ProcessingBoundaryError("parser profile schema is invalid")
    fields = value.get("fields")
    columns = value.get("table_columns")
    if not isinstance(fields, list) or not isinstance(columns, list):
        raise ProcessingBoundaryError("parser profile rules are invalid")
    return ParserProfile(
        profile_id=_required_string(value, "profile_id"),
        parser_name=_required_string(value, "parser_name"),
        parser_version=_required_string(value, "parser_version"),
        document_class=DocumentClass(_required_string(value, "document_class")),
        supported_kinds=tuple(
            AttachmentKind(item) for item in _string_tuple(value, "supported_kinds")
        ),
        fields=tuple(cast(FieldRule, _parse_field_rule(item, table=False)) for item in fields),
        table_columns=tuple(
            cast(TableColumnRule, _parse_field_rule(item, table=True)) for item in columns
        ),
        evidence_digest=_required_string(value, "evidence_digest"),
    )


def _parse_field_rule(value: object, *, table: bool) -> FieldRule | TableColumnRule:
    if not isinstance(value, dict):
        raise ProcessingBoundaryError("parser field rule must be an object")
    required = {"output_name", "labels", "value_kind", "required", "date_formats"}
    if set(value) != required or type(value.get("required")) is not bool:
        raise ProcessingBoundaryError("parser field rule schema is invalid")
    arguments = (
        _required_string(value, "output_name"),
        _string_tuple(value, "labels"),
        ValueKind(_required_string(value, "value_kind")),
        cast(bool, value["required"]),
        _string_tuple(value, "date_formats"),
    )
    return TableColumnRule(*arguments) if table else FieldRule(*arguments)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _safe_cell_text(value, maximum=1_000_000)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat(timespec="microseconds")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProcessingBoundaryError("XLSX numeric value is not finite")
        return format(Decimal(str(value)), "f")
    raise ProcessingBoundaryError("XLSX cell type is unsupported")


def _trim_row(row: tuple[str, ...]) -> tuple[str, ...]:
    last = len(row)
    while last > 0 and not row[last - 1]:
        last -= 1
    return row[:last]


def _safe_text(value: str, *, maximum: int) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if (
        normalized != value
        or len(value) > maximum
        or any(
            unicodedata.category(character).startswith("C") and character not in {"\t", "\n", "\r"}
            for character in value
        )
    ):
        raise ProcessingBoundaryError("artifact text is not canonical safe text")
    return value


def _safe_cell_text(value: str, *, maximum: int) -> str:
    normalized = _safe_text(value, maximum=maximum)
    stripped = normalized.lstrip()
    numeric = re.fullmatch(r"[-+]?[0-9]+(?:\.[0-9]+)?", stripped) is not None
    if stripped.startswith(("=", "@")) or (stripped.startswith(("+", "-")) and not numeric):
        raise ProcessingBoundaryError("formula-like cell text is prohibited")
    return normalized


def _profile_text(value: str) -> bool:
    try:
        return bool(_safe_text(value, maximum=256).strip())
    except ProcessingBoundaryError:
        return False


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ProcessingBoundaryError(f"parser registry field {key} is invalid")
    return item


def _string_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or not all(isinstance(entry, str) for entry in item):
        raise ProcessingBoundaryError(f"parser registry list {key} is invalid")
    return tuple(cast(list[str], item))


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProcessingBoundaryError("parser registry timestamp is invalid") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ProcessingBoundaryError("parser registry timestamp must be UTC")
    return parsed.astimezone(UTC)


def _semver_key(value: str) -> tuple[int, int, int]:
    return cast(tuple[int, int, int], tuple(int(item) for item in value.split(".")))


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
