"""Versioned JSON Schema and Pandera contract registry."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from importlib.resources import files
from typing import Any

import pandas as pd
import pandera.pandas as pa
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACT_FILES = {
    "message": "message-envelope-v1.schema.json",
    "document": "document-class-v1.schema.json",
    "transaction": "transaction-v1.schema.json",
    "timeline": "timeline-event-v1.schema.json",
    "lineage": "lineage-v1.schema.json",
    "evidence": "public-evidence-v1.schema.json",
}
SCHEMA_BASE = "https://metadatabase.example/schemas/moomooau/"


def _load_schema(filename: str) -> dict[str, Any]:
    resource = files("moomooau_archive").joinpath("contracts", filename)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("schema root must be an object")
    return value


def schema_catalog() -> dict[str, dict[str, Any]]:
    return {name: _load_schema(filename) for name, filename in CONTRACT_FILES.items()}


def validate_json_contract(contract_name: str, instance: object) -> None:
    catalog = schema_catalog()
    try:
        schema = catalog[contract_name]
    except KeyError as exc:
        raise ValueError("unknown contract name") from exc
    registry = Registry()
    for name, filename in CONTRACT_FILES.items():
        candidate = catalog[name]
        uri = str(candidate.get("$id") or (SCHEMA_BASE + filename))
        registry = registry.with_resource(uri, Resource.from_contents(candidate))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )
    validator.validate(instance)


def transaction_frame_schema() -> pa.DataFrameSchema:
    return pa.DataFrameSchema(
        {
            "source_id": pa.Column(str, pa.Check.str_matches(r"^[A-Za-z0-9_-]{16,}$")),
            "transaction_id": pa.Column(str, pa.Check.str_matches(r"^[A-Za-z0-9_-]{8,}$")),
            "transaction_date_utc": pa.Column("datetime64[ns, UTC]", nullable=True, coerce=True),
            "currency": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{3}$")),
            "amount": pa.Column(float, nullable=True, coerce=True),
            "quantity": pa.Column(float, nullable=True, coerce=True),
            "status": pa.Column(
                str,
                pa.Check.isin(["OBSERVED", "PENDING", "UNKNOWN"]),
            ),
        },
        coerce=True,
        strict=True,
        ordered=True,
        unique_column_names=True,
        name="MooMooAU Transaction v1",
    )


def validate_transaction_records(records: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(records)
    validated = transaction_frame_schema().validate(frame, lazy=True)
    if not isinstance(validated, pd.DataFrame):
        raise TypeError("Pandera returned a non-DataFrame object")
    return validated
