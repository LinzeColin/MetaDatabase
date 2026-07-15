from __future__ import annotations

from scripts.backfill_sec_history import (
    BACKFILL_FORMS,
    build_primary_document_url,
    entry_content_hash,
    filter_filing_entries,
    recent_block_entries,
)


def sample_recent_block() -> dict[str, list]:
    return {
        "accessionNumber": ["0001045810-26-000021", "0001045810-15-000100", "0001045810-24-000050"],
        "filingDate": ["2026-02-01", "2015-12-01", "2024-05-01"],
        "form": ["10-K", "10-K", "S-8"],
        "primaryDocument": ["nvda-20260125.htm", "old.htm", "s8.htm"],
        "primaryDocDescription": ["10-K", "10-K", "S-8"],
        "act": ["34", "34", "33"],
        "size": [100, 90, 10],
        "isXBRL": [1, 1, 0],
    }


def test_recent_block_entries_zip_columnar_arrays() -> None:
    entries = recent_block_entries(sample_recent_block())
    assert len(entries) == 3
    assert entries[0]["accessionNumber"] == "0001045810-26-000021"
    assert entries[1]["filingDate"] == "2015-12-01"


def test_filter_keeps_backfill_forms_after_cutoff_only() -> None:
    entries = recent_block_entries(sample_recent_block())
    kept = filter_filing_entries(entries, since="2016-01-01")
    assert [e["accessionNumber"] for e in kept] == ["0001045810-26-000021"]


def test_filter_includes_foreign_issuer_forms() -> None:
    entries = [
        {"accessionNumber": "a1", "filingDate": "2019-04-01", "form": "20-F"},
        {"accessionNumber": "a2", "filingDate": "2019-05-01", "form": "6-K"},
        {"accessionNumber": "a3", "filingDate": "2019-06-01", "form": "S-1"},
    ]
    kept = filter_filing_entries(entries, since="2016-01-01")
    assert [e["accessionNumber"] for e in kept] == ["a1", "a2"]
    assert {"20-F", "6-K", "10-K/A"} <= BACKFILL_FORMS


def test_primary_document_url_shapes() -> None:
    url = build_primary_document_url(1045810, "0001045810-26-000021", "nvda-20260125.htm")
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/"
        "000104581026000021/nvda-20260125.htm"
    )
    fallback = build_primary_document_url(1045810, "0001045810-26-000021", None)
    assert fallback.endswith("/0001045810-26-000021-index.htm")


def test_entry_content_hash_is_stable_and_cik_scoped() -> None:
    entry = {"accessionNumber": "a", "filingDate": "2020-01-01", "form": "8-K"}
    assert entry_content_hash(1, entry) == entry_content_hash(1, dict(entry))
    assert entry_content_hash(1, entry) != entry_content_hash(2, entry)
