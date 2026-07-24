from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError
from pandera.errors import SchemaErrors

from moomooau_archive.contracts import (
    schema_catalog,
    validate_json_contract,
    validate_transaction_records,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _lineage() -> dict[str, object]:
    return {
        "source_id": "synthetic-source-000001",
        "parser_name": "synthetic-parser",
        "parser_version": "stage1-v1",
        "schema_version": "1.0.0",
        "imported_at_utc": "2026-01-01T00:00:00Z",
        "key_epoch": "synthetic-epoch",
    }


def test_t0105_six_json_contracts_are_versioned_and_baseline_aligned() -> None:
    catalog = schema_catalog()
    assert set(catalog) == {"message", "document", "transaction", "timeline", "lineage", "evidence"}
    baseline = {
        "message": "message-envelope-v1.schema.json",
        "document": "document-class-v1.schema.json",
        "timeline": "timeline-event-v1.schema.json",
        "lineage": "lineage-v1.schema.json",
        "evidence": "public-evidence-v1.schema.json",
    }
    for name, filename in baseline.items():
        expected = json.loads((PROJECT_ROOT / "schemas" / filename).read_text(encoding="utf-8"))
        assert catalog[name] == expected

    validate_json_contract("document", "DAILY_STATEMENT")
    validate_json_contract("lineage", _lineage())
    validate_json_contract(
        "message",
        {
            "schema_version": "1.0.0",
            "source_id": "synthetic-source-000001",
            "document_class": "DAILY_STATEMENT",
            "verification": {"decision": "VERIFIED", "verifier_version": "stage1-v1"},
            "gmail": {"internal_date_utc": "2026-01-01T00:00:00Z", "label_state": ["SYNTHETIC"]},
            "processing_state": "RAW_ONLY",
            "lineage": _lineage(),
        },
    )
    validate_json_contract(
        "timeline",
        {
            "schema_version": "1.0.0",
            "source_id": "synthetic-source-000001",
            "document_class": "DAILY_STATEMENT",
            "email_internal_date_utc": "2026-01-01T00:00:00Z",
            "email_received_at_sydney": "2026-01-01T11:00:00+11:00",
            "expectation_state": "UNKNOWN",
            "m3_state": "NOT_ELIGIBLE",
        },
    )


def test_t0105_transaction_json_and_pandera_reject_schema_drift() -> None:
    record = {
        "source_id": "synthetic-source-000001",
        "transaction_id": "synthetic-tx-001",
        "transaction_date_utc": "2026-01-01T00:00:00Z",
        "currency": "AUD",
        "amount": 0.0,
        "quantity": None,
        "status": "OBSERVED",
    }
    validate_json_contract("transaction", record)
    frame = validate_transaction_records([record])
    assert list(frame.columns) == list(record)

    invalid = dict(record, currency="INVALID", guessed_value="forbidden")
    with pytest.raises(ValidationError):
        validate_json_contract("transaction", invalid)
    with pytest.raises(SchemaErrors):
        validate_transaction_records([invalid])
