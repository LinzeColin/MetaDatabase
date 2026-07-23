from __future__ import annotations

from stage4_support import parser_profile, stage4_context, text_pdf

from moomooau_archive.attachment_inspector import AttachmentKind
from moomooau_archive.document_parser import (
    ExtractionState,
    ProcessingDisposition,
    SafeArtifactExtractor,
    StatementParser,
)
from moomooau_archive.processed_models import DocumentClass, ProcessingState
from moomooau_archive.processed_product import ProcessedProductBuilder, ProcessedRole
from moomooau_archive.raw_commit import RawObjectRole
from moomooau_archive.secret_values import SecretText


def test_t0405_missing_and_wrong_pdf_passwords_are_safe_deferred_without_structured_data() -> None:
    context = stage4_context(
        DocumentClass.DAILY_STATEMENT,
        text_pdf(password="synthetic-correct-password"),  # pragma: allowlist secret
        AttachmentKind.PDF,
        message_suffix="encrypted-pdf",
    )
    extractor = SafeArtifactExtractor()
    missing = extractor.extract(context.attachments)
    wrong_secret = SecretText("synthetic-wrong-password")  # pragma: allowlist secret
    try:
        wrong = extractor.extract(context.attachments, pdf_passwords={1: wrong_secret})
    finally:
        wrong_secret.destroy()
    assert missing.state is ExtractionState.WAITING_FOR_PDF_PASSWORD
    assert wrong.state is ExtractionState.WAITING_FOR_PDF_PASSWORD
    assert missing.artifacts == wrong.artifacts == ()
    assert missing.reason_code == wrong.reason_code == "PDF_PASSWORD_REQUIRED_OR_INVALID"

    profile = parser_profile(
        DocumentClass.DAILY_STATEMENT,
        AttachmentKind.PDF,
        include_table=False,
    )
    for extraction in (missing, wrong):
        outcome = StatementParser().parse(
            context.envelope,
            context.classification,
            extraction,
            profile,
        )
        assert outcome.state is ProcessingState.WAITING_FOR_PDF_PASSWORD
        assert outcome.disposition is ProcessingDisposition.SAFE_DEFERRED
        assert outcome.statement is None
        product = ProcessedProductBuilder().build(context.envelope, outcome)
        assert len(product.artifacts) == 1
        assert product.artifacts[0].role is ProcessedRole.DOCUMENT_ENVELOPE
    assert any(item.role is RawObjectRole.MESSAGE for item in context.raw_plan.objects)
    assert context.raw_plan.objects[-1].role is RawObjectRole.MANIFEST


def test_t0405_correct_protected_password_reprocesses_the_same_raw_to_complete() -> None:
    context = stage4_context(
        DocumentClass.DAILY_STATEMENT,
        text_pdf(password="synthetic-correct-password"),  # pragma: allowlist secret
        AttachmentKind.PDF,
        message_suffix="encrypted-pdf-correct",
    )
    secret = SecretText("synthetic-correct-password")  # pragma: allowlist secret
    try:
        extraction = SafeArtifactExtractor().extract(
            context.attachments,
            pdf_passwords={1: secret},
        )
        assert "synthetic-correct-password" not in repr(extraction)
    finally:
        secret.destroy()
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        extraction,
        parser_profile(
            DocumentClass.DAILY_STATEMENT,
            AttachmentKind.PDF,
            include_table=False,
        ),
    )
    assert extraction.state is ExtractionState.READY
    assert outcome.state is ProcessingState.COMPLETE
    assert outcome.statement is not None
    assert dict(outcome.statement.summary)["total_value"] == "123.45"
