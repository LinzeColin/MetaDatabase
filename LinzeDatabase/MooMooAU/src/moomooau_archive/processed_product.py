"""Deterministic in-memory Canonical JSONL and Parquet products for Stage 4."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum

import pyarrow as pa
import pyarrow.parquet as pq

from .document_parser import ParsedStatement, ParserOutcome
from .processed_models import DocumentEnvelope, ProcessingBoundaryError, ProcessingState

_OPAQUE_ID = re.compile(r"^[0-9a-f]{64}$")
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
_PARSER_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATASET = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_PRODUCT_SENTINEL = object()


class ProcessedFormat(StrEnum):
    JSONL = "JSONL"
    PARQUET = "PARQUET"


class ProcessedRole(StrEnum):
    DOCUMENT_ENVELOPE = "DOCUMENT_ENVELOPE"
    STATEMENT = "STATEMENT"
    ANALYTICS = "ANALYTICS"


@dataclass(frozen=True, slots=True, repr=False)
class ProcessedArtifact:
    dataset_name: str
    role: ProcessedRole
    format: ProcessedFormat
    schema_version: str
    plaintext_sha256: str
    plaintext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            _DATASET.fullmatch(self.dataset_name) is None
            or _SEMVER.fullmatch(self.schema_version) is None
            or _SHA256.fullmatch(self.plaintext_sha256) is None
            or hashlib.sha256(self.plaintext).hexdigest() != self.plaintext_sha256
            or not self.plaintext
            or (self.format is ProcessedFormat.JSONL and not self.plaintext.endswith(b"\n"))
            or (self.format is ProcessedFormat.PARQUET and not self.plaintext.startswith(b"PAR1"))
            or (self.format is ProcessedFormat.PARQUET and not self.plaintext.endswith(b"PAR1"))
        ):
            raise ProcessingBoundaryError("processed artifact is invalid")

    def __repr__(self) -> str:
        return (
            f"ProcessedArtifact(dataset_name={self.dataset_name!r}, role={self.role.value!r}, "
            f"format={self.format.value!r}, schema_version={self.schema_version!r}, "
            "plaintext_sha256=<redacted>, plaintext=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProcessedBundle:
    source_id: str
    parser_name: str
    parser_version: str
    schema_version: str
    processing_state: ProcessingState
    artifacts: tuple[ProcessedArtifact, ...]
    business_root: str
    snapshot_root: str
    _sentinel: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        keys = [(item.dataset_name, item.format.value, item.role.value) for item in self.artifacts]
        if (
            self._sentinel is not _PRODUCT_SENTINEL
            or _OPAQUE_ID.fullmatch(self.source_id) is None
            or _PARSER_NAME.fullmatch(self.parser_name) is None
            or _SEMVER.fullmatch(self.parser_version) is None
            or _SEMVER.fullmatch(self.schema_version) is None
            or not self.artifacts
            or keys != sorted(keys)
            or len(keys) != len(set(keys))
            or _SHA256.fullmatch(self.business_root) is None
            or _SHA256.fullmatch(self.snapshot_root) is None
            or self.snapshot_root
            != _snapshot_root(
                self.source_id,
                self.parser_name,
                self.parser_version,
                self.schema_version,
                self.processing_state,
                self.artifacts,
            )
        ):
            raise ProcessingBoundaryError("processed bundle is invalid")

    def __repr__(self) -> str:
        return (
            "ProcessedBundle(source_id=<redacted>, "
            f"parser_name={self.parser_name!r}, parser_version={self.parser_version!r}, "
            f"schema_version={self.schema_version!r}, "
            f"processing_state={self.processing_state.value!r}, "
            f"artifact_count={len(self.artifacts)}, business_root=<redacted>, "
            "snapshot_root=<redacted>)"
        )


class ProcessedProductBuilder:
    """Build private plaintext only in memory; persistence belongs to the age-only commit layer."""

    schema_version = "1.0.0"

    def build(self, envelope: DocumentEnvelope, outcome: ParserOutcome) -> ProcessedBundle:
        statement = outcome.statement
        if (outcome.state is ProcessingState.COMPLETE) != (statement is not None):
            raise ProcessingBoundaryError("processed outcome is internally inconsistent")
        field_lineage = statement.field_lineage if statement is not None else ()
        final_envelope = envelope.with_processing(
            outcome.state,
            outcome.reason_code,
            parser_name=outcome.parser_name,
            parser_version=outcome.parser_version,
            field_lineage=field_lineage,
        )
        artifacts = [
            _artifact(
                "document_envelopes",
                ProcessedRole.DOCUMENT_ENVELOPE,
                ProcessedFormat.JSONL,
                _canonical_json(final_envelope.to_private_dict()) + b"\n",
            )
        ]
        statement_value: dict[str, object] | None = None
        if statement is not None:
            statement_value = statement.to_private_dict(final_envelope.lineage.to_private_dict())
            artifacts.extend(
                (
                    _artifact(
                        "statements",
                        ProcessedRole.STATEMENT,
                        ProcessedFormat.JSONL,
                        _canonical_json(statement_value) + b"\n",
                    ),
                    _artifact(
                        "analytics",
                        ProcessedRole.ANALYTICS,
                        ProcessedFormat.PARQUET,
                        _statement_parquet(statement),
                    ),
                )
            )
        ordered = tuple(
            sorted(
                artifacts,
                key=lambda item: (item.dataset_name, item.format.value, item.role.value),
            )
        )
        business_value = _business_value(final_envelope, statement_value)
        business_root = hashlib.sha256(_canonical_json(business_value)).hexdigest()
        snapshot_root = _snapshot_root(
            final_envelope.source_id,
            outcome.parser_name,
            outcome.parser_version,
            self.schema_version,
            outcome.state,
            ordered,
        )
        return ProcessedBundle(
            source_id=final_envelope.source_id,
            parser_name=outcome.parser_name,
            parser_version=outcome.parser_version,
            schema_version=self.schema_version,
            processing_state=outcome.state,
            artifacts=ordered,
            business_root=business_root,
            snapshot_root=snapshot_root,
            _sentinel=_PRODUCT_SENTINEL,
        )


def _artifact(
    dataset_name: str,
    role: ProcessedRole,
    artifact_format: ProcessedFormat,
    plaintext: bytes,
) -> ProcessedArtifact:
    return ProcessedArtifact(
        dataset_name=dataset_name,
        role=role,
        format=artifact_format,
        schema_version="1.0.0",
        plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
        plaintext=plaintext,
    )


def _statement_parquet(statement: ParsedStatement) -> bytes:
    records: list[tuple[str, int, str]] = [
        ("SUMMARY", 0, _canonical_json(dict(statement.summary)).decode("utf-8"))
    ]
    records.extend(
        (
            "TRANSACTION",
            index,
            _canonical_json(dict(transaction)).decode("utf-8"),
        )
        for index, transaction in enumerate(statement.transactions, start=1)
    )
    count = len(records)
    schema = pa.schema(
        [
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("document_class", pa.string(), nullable=False),
            pa.field("statement_type", pa.string(), nullable=False),
            pa.field("statement_label_date", pa.date32(), nullable=True),
            pa.field("currency", pa.string(), nullable=True),
            pa.field("record_kind", pa.string(), nullable=False),
            pa.field("record_index", pa.int64(), nullable=False),
            pa.field("record_json", pa.string(), nullable=False),
        ],
        metadata={
            b"moomooau.schema_version": b"1.0.0",
            b"moomooau.dataset": b"analytics",
        },
    )
    table = pa.Table.from_arrays(
        [
            pa.array([statement.source_id] * count, type=pa.string()),
            pa.array([statement.document_class.value] * count, type=pa.string()),
            pa.array([statement.statement_type.value] * count, type=pa.string()),
            pa.array([statement.statement_label_date] * count, type=pa.date32()),
            pa.array([statement.currency] * count, type=pa.string()),
            pa.array([record[0] for record in records], type=pa.string()),
            pa.array([record[1] for record in records], type=pa.int64()),
            pa.array([record[2] for record in records], type=pa.string()),
        ],
        schema=schema,
    )
    sink = io.BytesIO()
    pq.write_table(
        table,
        sink,
        version="2.6",
        compression="zstd",
        compression_level=9,
        use_dictionary=False,
        write_statistics=True,
        row_group_size=65_536,
        data_page_version="2.0",
        use_compliant_nested_type=True,
        store_schema=True,
        write_page_index=False,
    )
    payload = sink.getvalue()
    recovered = pq.read_table(io.BytesIO(payload), schema=schema)
    if not recovered.equals(table, check_metadata=True):
        raise ProcessingBoundaryError("Parquet round-trip changed the canonical table")
    return payload


def _business_value(
    envelope: DocumentEnvelope,
    statement_value: dict[str, object] | None,
) -> dict[str, object]:
    statement_business: dict[str, object] | None = None
    if statement_value is not None:
        statement_business = {
            key: value
            for key, value in statement_value.items()
            if key not in {"lineage", "schema_version"}
        }
    return {
        "source_id": envelope.source_id,
        "document_class": envelope.document_class.value,
        "internal_date_utc": envelope.internal_date_utc.isoformat(),
        "received_at_sydney": envelope.received_at_sydney.isoformat(),
        "label_state": list(envelope.label_state),
        "attachment_object_ids": list(envelope.lineage.attachment_object_ids),
        "processing_state": envelope.processing_state.value,
        "statement": statement_business,
    }


def _snapshot_root(
    source_id: str,
    parser_name: str,
    parser_version: str,
    schema_version: str,
    processing_state: ProcessingState,
    artifacts: tuple[ProcessedArtifact, ...],
) -> str:
    value = {
        "source_id": source_id,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "schema_version": schema_version,
        "processing_state": processing_state.value,
        "artifacts": [
            {
                "dataset_name": item.dataset_name,
                "role": item.role.value,
                "format": item.format.value,
                "schema_version": item.schema_version,
                "plaintext_sha256": item.plaintext_sha256,
            }
            for item in artifacts
        ],
    }
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProcessingBoundaryError("processed value is not canonical JSON") from exc
