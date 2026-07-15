from __future__ import annotations

from app.domain import (
    EXPORT_FILING_COLUMNS,
    EXPORT_RELATIONSHIP_COLUMNS,
    rows_to_csv,
)


def test_rows_to_csv_quotes_and_orders_columns() -> None:
    rows = [
        {
            "accession": "0001045810-26-000021",
            "title": 'NVIDIA "10-K" 2026',
            "document_date": "2026-02-01",
            "url": "https://www.sec.gov/x",
            "publisher": "SEC, EDGAR",
        }
    ]
    csv_text = rows_to_csv(rows, EXPORT_FILING_COLUMNS)
    lines = csv_text.strip().split("\r\n")
    assert lines[0] == '"accession","title","document_date","url","publisher"'
    assert '""10-K""' in lines[1]
    assert '"SEC, EDGAR"' in lines[1]


def test_rows_to_csv_renders_missing_values_as_empty() -> None:
    rows = [{"accession": "a", "title": None}]
    csv_text = rows_to_csv(rows, EXPORT_FILING_COLUMNS)
    assert csv_text.strip().split("\r\n")[1] == '"a","","","",""'


def test_export_column_contracts_are_stable() -> None:
    assert EXPORT_RELATIONSHIP_COLUMNS[:4] == [
        "relationship_id",
        "subject_name",
        "relationship_type",
        "object_name",
    ]
    assert "support_excerpt" in EXPORT_RELATIONSHIP_COLUMNS
    assert "source_url" in EXPORT_RELATIONSHIP_COLUMNS
    assert EXPORT_FILING_COLUMNS == ["accession", "title", "document_date", "url", "publisher"]
