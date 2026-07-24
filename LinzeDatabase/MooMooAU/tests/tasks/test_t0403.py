from __future__ import annotations

import io
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from stage4_support import csv_statement, parser_profile, stage4_context

from moomooau_archive.attachment_inspector import AttachmentKind
from moomooau_archive.document_parser import (
    ExtractionState,
    ProcessingDisposition,
    SafeArtifactExtractor,
    StatementParser,
)
from moomooau_archive.processed_models import DocumentClass, ProcessingState
from moomooau_archive.processed_product import (
    ProcessedFormat,
    ProcessedProductBuilder,
    ProcessedRole,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "document_class",
    [
        DocumentClass.DAILY_STATEMENT,
        DocumentClass.MONTHLY_STATEMENT,
        DocumentClass.CONTRACT_NOTE,
    ],
)
def test_t0403_daily_monthly_and_contract_profiles_parse_deterministically(
    document_class: DocumentClass,
) -> None:
    context = stage4_context(document_class, message_suffix=document_class.value.casefold())
    extraction = SafeArtifactExtractor().extract(context.attachments)
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        extraction,
        parser_profile(document_class, AttachmentKind.CSV),
    )

    assert extraction.state is ExtractionState.READY
    assert outcome.state is ProcessingState.COMPLETE
    assert outcome.disposition is ProcessingDisposition.COMPLETE
    assert outcome.statement is not None
    assert outcome.statement.source_id == context.envelope.source_id
    assert outcome.statement.statement_label_date is not None
    assert outcome.statement.statement_label_date.isoformat() == "2026-01-02"
    assert outcome.statement.currency == "AUD"
    assert dict(outcome.statement.summary) == {"total_value": "123.45"}
    assert dict(outcome.statement.transactions[0]) == {
        "amount": "1.25",
        "description": "Synthetic transaction",
        "trade_date": "2026-01-01",
    }
    assert all(
        origin.startswith(("attachment:", "classification:"))
        for _, origin in outcome.statement.field_lineage
    )

    first = ProcessedProductBuilder().build(context.envelope, outcome)
    second = ProcessedProductBuilder().build(context.envelope, outcome)
    assert first.business_root == second.business_root
    assert first.snapshot_root == second.snapshot_root
    assert [item.plaintext for item in first.artifacts] == [
        item.plaintext for item in second.artifacts
    ]
    assert {item.role for item in first.artifacts} == {
        ProcessedRole.DOCUMENT_ENVELOPE,
        ProcessedRole.STATEMENT,
        ProcessedRole.ANALYTICS,
    }
    statement_jsonl = next(
        item
        for item in first.artifacts
        if item.role is ProcessedRole.STATEMENT and item.format is ProcessedFormat.JSONL
    )
    statement_value = json.loads(statement_jsonl.plaintext)
    assert statement_value["source_id"] == context.envelope.source_id
    statement_schema = json.loads(
        (PROJECT_ROOT / "machine/stages/S4/public-schemas/statement-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        list(
            Draft202012Validator(
                statement_schema,
                format_checker=FormatChecker(),
            ).iter_errors(statement_value)
        )
        == []
    )
    parquet = next(item for item in first.artifacts if item.format is ProcessedFormat.PARQUET)
    table = pq.read_table(io.BytesIO(parquet.plaintext))
    assert table.num_rows == 2
    assert table.column("record_kind").to_pylist() == ["SUMMARY", "TRANSACTION"]


def test_t0403_conflicting_protected_fields_are_quarantined_without_guessed_output() -> None:
    context = stage4_context(
        DocumentClass.DAILY_STATEMENT,
        csv_statement(conflict=True),
        message_suffix="conflict",
    )
    extraction = SafeArtifactExtractor().extract(context.attachments)
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        extraction,
        parser_profile(DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV),
    )
    assert outcome.state is ProcessingState.QUARANTINED
    assert outcome.disposition is ProcessingDisposition.BLOCKED
    assert outcome.reason_code == "CONFLICTING_OR_INVALID_PROTECTED_FIELDS"
    assert outcome.statement is None

    product = ProcessedProductBuilder().build(context.envelope, outcome)
    assert len(product.artifacts) == 1
    assert product.artifacts[0].role is ProcessedRole.DOCUMENT_ENVELOPE
    assert b"999.99" not in product.artifacts[0].plaintext
