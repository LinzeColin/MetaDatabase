from __future__ import annotations

import json

from stage4_support import (
    parser_profile,
    parser_registry_payload,
    stage4_context,
    xlsx_statement,
)

from moomooau_archive.attachment_inspector import AttachmentDecision, AttachmentKind
from moomooau_archive.document_parser import (
    ExtractionState,
    ParserProfileRegistry,
    SafeArtifactExtractor,
    StatementParser,
)
from moomooau_archive.processed_models import DocumentClass, ProcessingState


def test_t0404_financial_year_xlsx_and_negative_table_values_parse_in_memory() -> None:
    context = stage4_context(
        DocumentClass.FINANCIAL_YEAR_SUMMARY,
        xlsx_statement(),
        AttachmentKind.XLSX,
        message_suffix="fy-xlsx",
    )
    assert context.attachments.attachments[0].decision is AttachmentDecision.SAFE
    extraction = SafeArtifactExtractor().extract(context.attachments)
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        extraction,
        parser_profile(DocumentClass.FINANCIAL_YEAR_SUMMARY, AttachmentKind.XLSX),
    )
    assert extraction.state is ExtractionState.READY
    assert outcome.state is ProcessingState.COMPLETE
    assert outcome.statement is not None
    assert outcome.statement.statement_label_date is not None
    assert outcome.statement.statement_label_date.isoformat() == "2026-06-30"
    assert dict(outcome.statement.transactions[0])["amount"] == "-2.5"


def test_t0404_generic_table_profile_can_omit_summary_fields_without_portal_access() -> None:
    raw_profile = json.loads(
        parser_registry_payload(
            DocumentClass.FINANCIAL_YEAR_SUMMARY,
            AttachmentKind.XLSX,
        )
    )
    raw_profile["profiles"][0]["fields"] = []
    registry = ParserProfileRegistry.from_json(
        json.dumps(raw_profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    profile = registry.current_for(DocumentClass.FINANCIAL_YEAR_SUMMARY)
    assert profile is not None
    context = stage4_context(
        DocumentClass.FINANCIAL_YEAR_SUMMARY,
        xlsx_statement(),
        AttachmentKind.XLSX,
        message_suffix="generic-table",
    )
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        SafeArtifactExtractor().extract(context.attachments),
        profile,
    )
    assert outcome.state is ProcessingState.COMPLETE
    assert outcome.statement is not None
    assert outcome.statement.statement_label_date is None
    assert outcome.statement.currency is None
    assert len(outcome.statement.transactions) == 1


def test_t0404_xlsx_formula_is_quarantined_before_parser_interpretation() -> None:
    context = stage4_context(
        DocumentClass.FINANCIAL_YEAR_SUMMARY,
        xlsx_statement(formula=True),
        AttachmentKind.XLSX,
        message_suffix="formula",
    )
    extraction = SafeArtifactExtractor().extract(context.attachments)
    assert extraction.state is ExtractionState.QUARANTINED
    assert extraction.artifacts == ()
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        extraction,
        parser_profile(DocumentClass.FINANCIAL_YEAR_SUMMARY, AttachmentKind.XLSX),
    )
    assert outcome.state is ProcessingState.QUARANTINED
    assert outcome.statement is None
