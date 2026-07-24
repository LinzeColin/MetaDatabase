"""Synthetic-only Stage 4 fixtures built through the verified Stage 3 boundaries."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import openpyxl
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from stage3_support import (
    SyntheticGmailMessage,
    SyntheticGmailTransport,
    make_raw_message,
    metadata_headers,
    synthetic_registry,
)

from moomooau_archive.age_stream import OfficialAgeStream
from moomooau_archive.attachment_inspector import (
    AttachmentInspectionReport,
    AttachmentInspector,
    AttachmentKind,
)
from moomooau_archive.canonical_raw import CanonicalRaw, CanonicalRawFetcher
from moomooau_archive.document_parser import (
    ExtractionBatch,
    ParserProfile,
    ParserProfileRegistry,
    SafeArtifactExtractor,
)
from moomooau_archive.gmail_discovery import GmailReadClient
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.processed_commit import CurrentProcessedPointer
from moomooau_archive.processed_models import (
    ClassificationRegistry,
    DocumentClass,
    DocumentClassification,
    DocumentClassifier,
    DocumentEnvelope,
    DocumentEnvelopeFactory,
)
from moomooau_archive.processed_product import ProcessedBundle
from moomooau_archive.raw_commit import OpaqueIdFactory, RawCommitPlan, RawCommitPlanner
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.secret_values import SecretBytes, SecretText
from moomooau_archive.sender_registry import MessageVerification, SenderVerifier, VerificationPhase


@dataclass(frozen=True, slots=True)
class VerifiedInputs:
    canonical: CanonicalRaw
    verification: MessageVerification
    attachments: AttachmentInspectionReport


@dataclass(frozen=True, slots=True)
class Stage4Context:
    canonical: CanonicalRaw
    verification: MessageVerification
    attachments: AttachmentInspectionReport
    raw_plan: RawCommitPlan
    classification: DocumentClassification
    envelope: DocumentEnvelope
    recipient: str


def csv_statement(
    *,
    total_value: str = "123.45",
    transaction_amount: str = "1.25",
    conflict: bool = False,
) -> bytes:
    rows = [
        "Statement Date,2026-01-02",
        "Currency,AUD",
        f"Total Value,{total_value}",
    ]
    if conflict:
        rows.append("Total Value,999.99")
    rows.extend(
        (
            "Date,Description,Amount",
            f"2026-01-01,Synthetic transaction,{transaction_amount}",
        )
    )
    return ("\n".join(rows) + "\n").encode("utf-8")


def xlsx_statement(*, formula: bool = False) -> bytes:
    workbook = openpyxl.Workbook(write_only=False)
    sheet = workbook.active
    sheet.title = "Synthetic"
    sheet.append(("Statement Date", "2026-06-30"))
    sheet.append(("Currency", "AUD"))
    sheet.append(("Total Value", "456.78"))
    sheet.append(("Date", "Description", "Amount"))
    sheet.append(("2026-06-29", "Synthetic FY transaction", "-2.50"))
    if formula:
        sheet.append(("2026-06-30", "Synthetic formula", "=1+1"))
    sink = io.BytesIO()
    workbook.save(sink)
    workbook.close()
    return sink.getvalue()


def text_pdf(*, password: str | None = None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 72 720 Td (Statement Date: 2026-01-02) Tj "
        b"0 -18 Td (Currency: AUD) Tj 0 -18 Td (Total Value: 123.45) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    if password is not None:
        writer.encrypt(password, algorithm="AES-256")
    sink = io.BytesIO()
    writer.write(sink)
    return sink.getvalue()


def verified_inputs(
    document_class: DocumentClass,
    content: bytes,
    kind: AttachmentKind,
    *,
    message_suffix: str = "1",
) -> VerifiedInputs:
    message_id = (
        f"synthetic-stage4-{document_class.value.casefold().replace('_', '-')}-{message_suffix}"
    )
    subject = f"Synthetic Moomoo AU Daily {document_class.value}"
    filename, maintype, subtype = _attachment_identity(kind)
    raw = make_raw_message(
        message_id=message_id,
        subject=subject,
        attachments=((filename, maintype, subtype, content),),
    )
    message = SyntheticGmailMessage(
        message_id=message_id,
        thread_id="thread-" + message_id,
        labels=("INBOX", "CATEGORY_UPDATES"),
        history_id="400",
        internal_date_ms=1_767_225_600_000,
        headers=metadata_headers(subject=subject),
        raw=raw,
    )
    transport = SyntheticGmailTransport((message,))
    guard = GmailEndpointGuard(transport)
    registry = synthetic_registry()
    verifier = SenderVerifier()
    metadata = GmailReadClient(guard).get_metadata(
        message_id,
        header_names=registry.requested_header_names,
    )
    verification = verifier.verify_message(
        metadata,
        registry,
        phase=VerificationPhase.PRE_RAW,
    )
    if verification.raw_fetch_permit is None:
        raise AssertionError("synthetic verified fixture did not receive a Raw permit")
    canonical = CanonicalRawFetcher(guard, verifier).fetch(
        verification.raw_fetch_permit,
        registry,
    )
    report = AttachmentInspector().inspect(canonical)
    return VerifiedInputs(canonical, verification, report)


def stage4_context(
    document_class: DocumentClass = DocumentClass.DAILY_STATEMENT,
    content: bytes | None = None,
    kind: AttachmentKind = AttachmentKind.CSV,
    *,
    message_suffix: str = "1",
) -> Stage4Context:
    attachment_content = content if content is not None else csv_statement()
    verified = verified_inputs(
        document_class,
        attachment_content,
        kind,
        message_suffix=message_suffix,
    )
    class_registry = classification_registry(document_class, kind)
    classification = DocumentClassifier().classify(
        verified.canonical,
        verified.verification,
        verified.attachments,
        class_registry,
    )
    generated = AgeIdentityGenerator().generate()
    opaque_key = SecretBytes(b"synthetic-stage4-opaque-key-material-0001")
    try:
        raw_plan = RawCommitPlanner(
            OfficialAgeStream(),
            generated.recipient,
            OpaqueIdFactory(opaque_key),
        ).plan(
            verified.canonical,
            verified.attachments,
            key_epoch="synthetic-epoch-1",
        )
        envelope = DocumentEnvelopeFactory().issue(
            verified.canonical,
            verified.verification,
            verified.attachments,
            raw_plan,
            classification,
            imported_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        )
        return Stage4Context(
            verified.canonical,
            verified.verification,
            verified.attachments,
            raw_plan,
            classification,
            envelope,
            generated.recipient,
        )
    finally:
        opaque_key.destroy()
        generated.destroy()


def classification_registry(
    document_class: DocumentClass,
    kind: AttachmentKind,
) -> ClassificationRegistry:
    return ClassificationRegistry.from_json(
        classification_registry_payload(((document_class, kind),))
    )


def classification_registry_payload(
    entries: tuple[tuple[DocumentClass, AttachmentKind], ...],
) -> bytes:
    rules = [
        {
            "rule_id": "SYNTHETIC_" + document_class.value,
            "document_class": document_class.value,
            "subject_phrases_all": [document_class.value],
            "attachment_kinds_any": [kind.value],
            "filename_suffixes_any": [],
            "evidence_digest": hashlib.sha256(
                (document_class.value + ":synthetic-evidence").encode("ascii")
            ).hexdigest(),
        }
        for document_class, kind in sorted(entries, key=lambda item: item[0].value)
    ]
    value = {
        "schema_version": "moomooau.classification-registry.v1",
        "registry_version": "1.0.0",
        "issued_at_utc": "2026-01-01T00:00:00Z",
        "activation_state": "ACTIVE" if rules else "EMPTY_PROTECTED_EVIDENCE_REQUIRED",
        "rules": rules,
    }
    return _canonical_json(value)


def parser_profile(
    document_class: DocumentClass,
    kind: AttachmentKind,
    *,
    parser_version: str = "1.0.0",
    include_table: bool = True,
) -> ParserProfile:
    registry = ParserProfileRegistry.from_json(
        parser_registry_payload(
            document_class,
            kind,
            parser_version=parser_version,
            include_table=include_table,
        )
    )
    profile = registry.current_for(document_class)
    if profile is None:
        raise AssertionError("synthetic parser profile is unavailable")
    return profile


def parser_registry_payload(
    document_class: DocumentClass,
    kind: AttachmentKind,
    *,
    parser_version: str = "1.0.0",
    include_table: bool = True,
) -> bytes:
    table_columns: list[dict[str, object]] = []
    if include_table:
        table_columns = [
            _field("trade_date", ("Date",), "DATE", True, ("%Y-%m-%d",)),
            _field("description", ("Description",), "TEXT", True),
            _field("amount", ("Amount",), "DECIMAL", True),
        ]
    profile = {
        "profile_id": "SYNTHETIC_" + document_class.value,
        "parser_name": "synthetic-statement-parser",
        "parser_version": parser_version,
        "document_class": document_class.value,
        "supported_kinds": [kind.value],
        "fields": [
            _field(
                "statement_label_date",
                ("Statement Date",),
                "DATE",
                True,
                ("%Y-%m-%d",),
            ),
            _field("currency", ("Currency",), "CURRENCY", True),
            _field("total_value", ("Total Value",), "DECIMAL", True),
        ],
        "table_columns": table_columns,
        "evidence_digest": hashlib.sha256(
            (document_class.value + ":" + parser_version).encode("ascii")
        ).hexdigest(),
    }
    return _canonical_json(
        {
            "schema_version": "moomooau.parser-profile-registry.v1",
            "registry_version": "1.0.0",
            "issued_at_utc": "2026-01-01T00:00:00Z",
            "activation_state": "ACTIVE",
            "profiles": [profile],
        }
    )


def extract_context(
    context: Stage4Context,
    *,
    pdf_passwords: dict[int, SecretText] | None = None,
) -> ExtractionBatch:
    passwords = pdf_passwords
    return SafeArtifactExtractor().extract(
        context.attachments,
        pdf_passwords=passwords,
    )


def current_pointer(
    bundle: ProcessedBundle,
    *,
    generation: int = 1,
    key_epoch: str = "synthetic-epoch-1",
) -> CurrentProcessedPointer:
    path = (
        f"MooMooAU/Manifests/processed/{bundle.parser_name}/"
        f"{bundle.parser_version}/{bundle.source_id}.json.age"
    )
    return CurrentProcessedPointer.from_bytes(
        _canonical_json(
            {
                "schema_version": "moomooau.processed-current.v1",
                "source_id": bundle.source_id,
                "parser_name": bundle.parser_name,
                "parser_version": bundle.parser_version,
                "output_schema_version": bundle.schema_version,
                "business_root": bundle.business_root,
                "snapshot_root": bundle.snapshot_root,
                "manifest_path": path,
                "key_epoch": key_epoch,
                "generation": generation,
            }
        )
    )


def signed_approval(
    incumbent: CurrentProcessedPointer,
    candidate: ProcessedBundle,
    key: SecretBytes,
) -> tuple[bytes, str]:
    payload = _canonical_json(
        {
            "schema_version": "moomooau.parser-promotion-approval.v1",
            "decision": "APPROVE",
            "source_id": candidate.source_id,
            "incumbent_snapshot_root": incumbent.snapshot_root,
            "candidate_snapshot_root": candidate.snapshot_root,
            "issued_at_utc": "2026-01-15T00:00:00Z",
        }
    )
    return payload, hmac.digest(key.reveal(), payload, "sha256").hex()


def _attachment_identity(kind: AttachmentKind) -> tuple[str, str, str]:
    if kind is AttachmentKind.CSV:
        return "synthetic.csv", "text", "csv"
    if kind is AttachmentKind.XLSX:
        return (
            "synthetic.xlsx",
            "application",
            "vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if kind is AttachmentKind.PDF:
        return "synthetic.pdf", "application", "pdf"
    raise AssertionError("unsupported synthetic Stage 4 attachment kind")


def _field(
    output_name: str,
    labels: tuple[str, ...],
    value_kind: str,
    required: bool,
    date_formats: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "output_name": output_name,
        "labels": list(labels),
        "value_kind": value_kind,
        "required": required,
        "date_formats": list(date_formats),
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
