from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from stage3_support import metadata_headers, synthetic_registry
from stage4_support import (
    classification_registry,
    csv_statement,
    parser_profile,
    verified_inputs,
)

from moomooau_archive.age_stream import OfficialAgeStream
from moomooau_archive.attachment_inspector import AttachmentKind
from moomooau_archive.canonical_raw import CanonicalRaw
from moomooau_archive.document_parser import (
    ParsedStatement,
    SafeArtifactExtractor,
    StatementParser,
)
from moomooau_archive.gmail_discovery import HeaderSnapshot, MessageRef, MinimalMessage
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.m3 import M3State
from moomooau_archive.market_calendar import ExpectationPolicy, USMarketCalendar
from moomooau_archive.processed_commit import (
    ParserBlueGreenComparator,
    ProcessedCommitPlan,
    ProcessedCommitPlanner,
)
from moomooau_archive.processed_models import (
    DocumentClass,
    DocumentClassifier,
    DocumentEnvelope,
    DocumentEnvelopeFactory,
)
from moomooau_archive.processed_product import ProcessedBundle, ProcessedProductBuilder
from moomooau_archive.raw_commit import OpaqueIdFactory, RawCommitPlan, RawCommitPlanner
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.remote_recovery_gate import (
    MemoryRemoteCiphertextReader,
    OfficialAgeDecryptor,
)
from moomooau_archive.secret_values import SecretBytes
from moomooau_archive.sender_registry import (
    MessageVerification,
    SenderVerifier,
    VerificationPhase,
)
from moomooau_archive.timeline_event import TimelineEvent, TimelineEventFactory


@dataclass(frozen=True, slots=True)
class Stage5RecoveryContext:
    canonical: CanonicalRaw
    first_verification: MessageVerification
    raw_plan: RawCommitPlan
    processed_bundle: ProcessedBundle
    processed_plan: ProcessedCommitPlan
    envelope: DocumentEnvelope
    statement: ParsedStatement | None
    reader: MemoryRemoteCiphertextReader
    decryptor: OfficialAgeDecryptor


@contextmanager
def recovery_context(*, safe_deferred: bool = False) -> Iterator[Stage5RecoveryContext]:
    verified = verified_inputs(
        DocumentClass.DAILY_STATEMENT,
        csv_statement(),
        AttachmentKind.CSV,
        message_suffix="stage5-recovery-deferred" if safe_deferred else "stage5-recovery-complete",
    )
    class_registry = classification_registry(DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV)
    classification = DocumentClassifier().classify(
        verified.canonical,
        verified.verification,
        verified.attachments,
        class_registry,
    )
    generated = AgeIdentityGenerator().generate()
    opaque_key = SecretBytes(b"synthetic-stage5-opaque-key-material-0001")
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage5-age-")
    identity_path = Path(temporary.name) / "identity.agekey"
    try:
        identity_path.write_bytes(generated.identity.reveal())
        identity_path.chmod(0o600)
        age = OfficialAgeStream()
        raw_plan = RawCommitPlanner(
            age,
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
        extraction = SafeArtifactExtractor().extract(verified.attachments)
        profile = (
            None
            if safe_deferred
            else parser_profile(
                DocumentClass.DAILY_STATEMENT,
                AttachmentKind.CSV,
            )
        )
        outcome = StatementParser().parse(envelope, classification, extraction, profile)
        statement_lineage = outcome.statement.field_lineage if outcome.statement is not None else ()
        final_envelope = envelope.with_processing(
            outcome.state,
            outcome.reason_code,
            parser_name=outcome.parser_name,
            parser_version=outcome.parser_version,
            field_lineage=statement_lineage,
        )
        bundle = ProcessedProductBuilder().build(envelope, outcome)
        decision = ParserBlueGreenComparator().compare(bundle, None, observed_days=0)
        processed_plan = ProcessedCommitPlanner(age, generated.recipient).plan(
            bundle,
            decision,
            None,
            key_epoch="synthetic-epoch-1",
            expected_pointer_revision=None,
        )
        reader = MemoryRemoteCiphertextReader()
        for raw_item in raw_plan.objects:
            reader.put(raw_item.relative_path, raw_item.ciphertext)
        for processed_item in processed_plan.immutable_objects:
            reader.put(processed_item.relative_path, processed_item.ciphertext)
        if processed_plan.current_pointer is not None:
            reader.put(
                processed_plan.current_pointer.relative_path,
                processed_plan.current_pointer.ciphertext,
            )
        decryptor = OfficialAgeDecryptor(
            age,
            identity_path,
            allowed_tmpfs_roots=(Path(temporary.name),),
        )
        yield Stage5RecoveryContext(
            verified.canonical,
            verified.verification,
            raw_plan,
            bundle,
            processed_plan,
            final_envelope,
            outcome.statement,
            reader,
            decryptor,
        )
    finally:
        opaque_key.destroy()
        generated.destroy()
        temporary.cleanup()


def pre_m3_message(
    context: Stage5RecoveryContext,
    *,
    trashed: bool = False,
    subject: str = "Synthetic Moomoo AU Daily DAILY_STATEMENT",
) -> tuple[MinimalMessage, MessageVerification]:
    canonical = context.canonical
    labels = tuple(sorted(("CATEGORY_UPDATES", "TRASH" if trashed else "INBOX")))
    message = MinimalMessage(
        ref=MessageRef(canonical.message_id, canonical.thread_id),
        history_id="501",
        internal_date_ms=canonical.internal_date_ms,
        label_ids=labels,
        headers=HeaderSnapshot(metadata_headers(subject=subject)),
    )
    second = SenderVerifier().verify_message(
        message,
        synthetic_registry(),
        phase=VerificationPhase.PRE_M3,
    )
    return message, second


class SyntheticM3Transport:
    def __init__(
        self, message_id: str, *, trash_status: int = 200, confirm_trash: bool = True
    ) -> None:
        self.message_id = message_id
        self.trash_status = trash_status
        self.confirm_trash = confirm_trash
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        parsed = urlsplit(request.url)
        query = parse_qs(parsed.query)
        trash_path = f"/gmail/v1/users/me/messages/{self.message_id}/trash"
        get_path = f"/gmail/v1/users/me/messages/{self.message_id}"
        if request.method == "POST" and parsed.path == trash_path:
            return HttpResponse(
                self.trash_status,
                json.dumps({"id": self.message_id}, separators=(",", ":")).encode("utf-8"),
            )
        if request.method == "GET" and parsed.path == get_path and query == {"format": ["minimal"]}:
            labels = ["CATEGORY_UPDATES", "TRASH" if self.confirm_trash else "INBOX"]
            return HttpResponse(
                200,
                json.dumps(
                    {"id": self.message_id, "labelIds": labels},
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        return HttpResponse(404, b"{}")


def timeline_event(
    context: Stage5RecoveryContext,
    *,
    statement_date: date | None = date(2025, 12, 31),
    m3_state: M3State = M3State.TRASHED,
) -> TimelineEvent:
    expectation = ExpectationPolicy().assess(
        observed=True,
        independent_activity_evidence=True,
        market_session_expected=True,
        sla_exceeded=False,
        parser_state=context.envelope.processing_state,
    )
    return TimelineEventFactory(USMarketCalendar()).issue(
        context.envelope,
        statement_label_date=statement_date,
        date_header_observed="Thu, 01 Jan 2099 00:00:00 +0000",
        m3_state=m3_state,
        expectation=expectation,
    )
