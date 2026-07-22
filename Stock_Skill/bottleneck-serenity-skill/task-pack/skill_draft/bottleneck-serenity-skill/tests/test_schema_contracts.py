#!/usr/bin/env python3
"""Dependency-free schema and example contract tests for the Skill payload."""

from __future__ import annotations

import copy
import csv
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = SKILL_ROOT / "schemas"
EXAMPLES = SKILL_ROOT / "examples"
ARTIFACT_FIELD_ORDER = (
    "schema_version",
    "skill_version",
    "as_of",
    "source_cutoff",
    "previous_version",
)
ARTIFACT_FIELDS = set(ARTIFACT_FIELD_ORDER)
EXPECTED_JSON = {
    "evals/golden_cases.json",
    "examples/illustrative_portfolio.json",
    "examples/illustrative_portfolio_analysis.json",
    "examples/illustrative_transformer_equipment.json",
    "schemas/evidence.schema.json",
    "schemas/opportunity.schema.json",
    "schemas/portfolio.schema.json",
    "templates/research_config.json",
}
SUPPORTED_KEYWORDS = {
    "$defs",
    "$id",
    "$ref",
    "$schema",
    "additionalProperties",
    "default",
    "description",
    "enum",
    "format",
    "items",
    "maximum",
    "minimum",
    "minLength",
    "properties",
    "required",
    "title",
    "type",
}
JSON_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


class SchemaContractError(ValueError):
    """Raised when a schema or instance violates the supported contract."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_local_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaContractError(f"only local JSON Pointer refs are supported: {reference}")
    value: Any = root
    for encoded in reference[2:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            raise SchemaContractError(f"unresolved schema ref: {reference}")
        value = value[token]
    if not isinstance(value, dict):
        raise SchemaContractError(f"schema ref does not resolve to an object: {reference}")
    return value


def check_schema(schema: Any, root: dict[str, Any], location: str = "$") -> None:
    if not isinstance(schema, dict):
        raise SchemaContractError(f"{location}: schema must be an object")
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS)
    if unknown:
        raise SchemaContractError(
            f"{location}: unsupported schema keyword(s): {', '.join(unknown)}"
        )
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str):
            raise SchemaContractError(f"{location}.$ref: expected string")
        resolve_local_ref(root, reference)
    schema_type = schema.get("type")
    allowed_types = {*JSON_TYPES, "number"}
    if isinstance(schema_type, list):
        if (
            not schema_type
            or any(not isinstance(item, str) or item not in allowed_types for item in schema_type)
            or len(schema_type) != len(set(schema_type))
        ):
            raise SchemaContractError(
                f"{location}.type: expected unique supported type names"
            )
    elif schema_type is not None and schema_type not in allowed_types:
        raise SchemaContractError(f"{location}.type: unsupported type {schema_type!r}")
    required = schema.get("required", [])
    if (
        not isinstance(required, list)
        or any(not isinstance(item, str) for item in required)
        or len(required) != len(set(required))
    ):
        raise SchemaContractError(f"{location}.required: expected unique strings")
    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        raise SchemaContractError(f"{location}.enum: expected non-empty array")
    if "format" in schema and schema["format"] != "date":
        raise SchemaContractError(f"{location}.format: unsupported format")
    for keyword in ("minimum", "maximum"):
        if keyword in schema and (
            isinstance(schema[keyword], bool)
            or not isinstance(schema[keyword], (int, float))
        ):
            raise SchemaContractError(f"{location}.{keyword}: expected number")
    if "minLength" in schema and (
        isinstance(schema["minLength"], bool)
        or not isinstance(schema["minLength"], int)
        or schema["minLength"] < 0
    ):
        raise SchemaContractError(f"{location}.minLength: expected non-negative integer")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise SchemaContractError(f"{location}.properties: expected object")
    for name, child in properties.items():
        check_schema(child, root, f"{location}.properties.{name}")
    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, bool):
        check_schema(additional, root, f"{location}.additionalProperties")
    if "items" in schema:
        check_schema(schema["items"], root, f"{location}.items")
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        raise SchemaContractError(f"{location}.$defs: expected object")
    for name, child in definitions.items():
        check_schema(child, root, f"{location}.$defs.{name}")


def validate_instance(
    instance: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    location: str = "$",
) -> None:
    if "$ref" in schema:
        validate_instance(instance, resolve_local_ref(root, schema["$ref"]), root, location)
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaContractError(f"{location}: value is outside enum")
    schema_type = schema.get("type")
    expected_types = schema_type if isinstance(schema_type, list) else [schema_type]

    def matches(type_name: str | None) -> bool:
        if type_name is None:
            return True
        if type_name == "number":
            return not isinstance(instance, bool) and isinstance(instance, (int, float))
        return isinstance(instance, JSON_TYPES[type_name])

    matched_type = next((item for item in expected_types if matches(item)), None)
    if schema_type is not None and matched_type is None:
        raise SchemaContractError(f"{location}: expected {schema_type}")
    if matched_type == "object":
        required = schema.get("required", [])
        missing = [name for name in required if name not in instance]
        if missing:
            raise SchemaContractError(f"{location}: missing required {missing}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for name, value in instance.items():
            if name in properties:
                validate_instance(value, properties[name], root, f"{location}.{name}")
            elif additional is False:
                raise SchemaContractError(f"{location}: unexpected property {name!r}")
            elif isinstance(additional, dict):
                validate_instance(value, additional, root, f"{location}.{name}")
    elif matched_type == "array":
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, value in enumerate(instance):
                validate_instance(value, item_schema, root, f"{location}[{index}]")
    elif matched_type == "string":
        if len(instance) < schema.get("minLength", 0):
            raise SchemaContractError(f"{location}: string is too short")
        if schema.get("format") == "date":
            try:
                parsed = dt.date.fromisoformat(instance)
            except ValueError as exc:
                raise SchemaContractError(f"{location}: invalid ISO date") from exc
            if parsed.isoformat() != instance:
                raise SchemaContractError(f"{location}: date is not canonical")
    elif matched_type == "number":
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaContractError(f"{location}: below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaContractError(f"{location}: above maximum")


def assert_valid(instance: Any, schema: dict[str, Any]) -> None:
    check_schema(schema, schema)
    validate_instance(instance, schema, schema)


class SchemaContractTests(unittest.TestCase):
    def test_all_json_documents_parse_and_schema_vocabulary_is_supported(self) -> None:
        paths = sorted(SKILL_ROOT.rglob("*.json"))
        self.assertEqual(
            {path.relative_to(SKILL_ROOT).as_posix() for path in paths},
            EXPECTED_JSON,
        )
        for path in paths:
            with self.subTest(path=path.relative_to(SKILL_ROOT).as_posix()):
                load_json(path)
        for path in sorted(SCHEMAS.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = load_json(path)
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                check_schema(schema, schema)

    def test_opportunity_and_portfolio_examples_match_schemas(self) -> None:
        pairs = (
            ("illustrative_transformer_equipment.json", "opportunity.schema.json"),
            ("illustrative_portfolio.json", "portfolio.schema.json"),
        )
        for example_name, schema_name in pairs:
            with self.subTest(example=example_name):
                assert_valid(load_json(EXAMPLES / example_name), load_json(SCHEMAS / schema_name))

    def test_runtime_artifact_envelope_is_required_and_frozen(self) -> None:
        for path in sorted(SCHEMAS.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = load_json(path)
                self.assertTrue(ARTIFACT_FIELDS.issubset(schema["required"]))
                self.assertEqual(schema["properties"]["schema_version"]["enum"], ["1.0"])
                self.assertEqual(
                    schema["properties"]["skill_version"]["enum"], ["0.0.0.1"]
                )
                self.assertEqual(
                    schema["properties"]["previous_version"]["type"],
                    ["string", "null"],
                )
                self.assertEqual(
                    schema["properties"]["previous_version"]["minLength"], 1
                )

        config = load_json(SKILL_ROOT / "templates" / "research_config.json")
        self.assertTrue(
            ARTIFACT_FIELDS
            | {"request_id", "query", "upstream_artifacts"}
            <= set(config)
        )
        self.assertNotIn("question", config)
        self.assertEqual(
            config["universe"],
            {
                "markets": ["US", "AU", "HK"],
                "asset_types": ["equity", "ETF"],
                "min_daily_value_traded_usd": 5000000,
            },
        )
        self.assertEqual(config["horizon_months"], 24)
        self.assertEqual(
            config["risk_constraints"],
            {
                "max_position_weight": 0.1,
                "max_root_driver_weight": 0.3,
                "leverage_allowed": False,
                "derivatives_allowed": False,
            },
        )

        for path in sorted((SKILL_ROOT / "templates").glob("*.csv")):
            with self.subTest(csv=path.name):
                with path.open(encoding="utf-8", newline="") as handle:
                    header = next(csv.reader(handle))
                self.assertEqual(header[:5], list(ARTIFACT_FIELD_ORDER))

    def test_evidence_fixture_matches_schema(self) -> None:
        fixture = {
            "schema_version": "1.0",
            "skill_version": "0.0.0.1",
            "as_of": "2026-07-23",
            "source_cutoff": "2026-07-23",
            "previous_version": None,
            "claims": [
                {
                    "id": "CLM-001",
                    "claim": "Synthetic claim used only for schema verification.",
                    "claim_type": "fact",
                    "critical": True,
                    "confidence": "high",
                    "status": "supported",
                    "sources": [
                        {
                            "url": "https://example.invalid/primary",
                            "publisher": "Synthetic primary source",
                            "date": "2026-07-22",
                            "tier": "A",
                            "independence_group": "primary",
                            "stance": "supports",
                        },
                        {
                            "url": "https://example.invalid/corroboration",
                            "publisher": "Synthetic corroborating source",
                            "date": "2026-07-23",
                            "tier": "B",
                            "independence_group": "corroboration",
                            "stance": "supports",
                        },
                    ],
                    "contradiction_search": "Synthetic negative search completed.",
                }
            ],
        }
        assert_valid(fixture, load_json(SCHEMAS / "evidence.schema.json"))

    def test_missing_renamed_or_wrong_artifact_metadata_fails_closed(self) -> None:
        opportunity_schema = load_json(SCHEMAS / "opportunity.schema.json")
        opportunity = load_json(EXAMPLES / "illustrative_transformer_equipment.json")
        for field in sorted(ARTIFACT_FIELDS):
            with self.subTest(field=field, mutation="missing"):
                mutated = copy.deepcopy(opportunity)
                del mutated[field]
                with self.assertRaises(SchemaContractError):
                    assert_valid(mutated, opportunity_schema)
            with self.subTest(field=field, mutation="renamed"):
                mutated = copy.deepcopy(opportunity)
                mutated[f"renamed_{field}"] = mutated.pop(field)
                with self.assertRaises(SchemaContractError):
                    assert_valid(mutated, opportunity_schema)

        for field, value in (
            ("schema_version", "1.1"),
            ("skill_version", "v0.0.0.1"),
            ("previous_version", 1),
            ("previous_version", ""),
        ):
            with self.subTest(field=field, value=value):
                mutated = copy.deepcopy(opportunity)
                mutated[field] = value
                with self.assertRaises(SchemaContractError):
                    assert_valid(mutated, opportunity_schema)

    def test_new_case_scaffold_emits_valid_versioned_artifacts(self) -> None:
        script = SKILL_ROOT / "scripts" / "new_research_case.py"
        with tempfile.TemporaryDirectory(prefix="bss-case-test-") as raw:
            output = Path(raw)
            command = [
                sys.executable,
                "-B",
                str(script),
                "synthetic-case",
                "--output",
                str(output),
                "--as-of",
                "2026-07-23",
                "--source-cutoff",
                "2026-07-22",
                "--request-id",
                "00000000-0000-4000-8000-000000000001",
                "--query",
                "Synthetic research question",
            ]
            created = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            root = output / "synthetic-case-20260723"
            artifacts = {
                name: load_json(root / name)
                for name in ("config.json", "evidence.json", "opportunity.json", "decision.json")
            }
            expected = {
                "schema_version": "1.0",
                "skill_version": "0.0.0.1",
                "as_of": "2026-07-23",
                "source_cutoff": "2026-07-22",
                "previous_version": None,
            }
            for name, artifact in artifacts.items():
                with self.subTest(artifact=name):
                    self.assertEqual({key: artifact[key] for key in expected}, expected)
            template = load_json(SKILL_ROOT / "templates" / "research_config.json")
            for key in (
                "mode",
                "universe",
                "horizon_months",
                "benchmark",
                "risk_constraints",
                "upstream_artifacts",
                "output_language",
            ):
                with self.subTest(config_default=key):
                    self.assertEqual(artifacts["config.json"][key], template[key])
            assert_valid(artifacts["evidence.json"], load_json(SCHEMAS / "evidence.schema.json"))
            assert_valid(
                artifacts["opportunity.json"], load_json(SCHEMAS / "opportunity.schema.json")
            )
            with (root / "monitoring.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual(
                    next(csv.reader(handle))[:5],
                    [
                        "schema_version",
                        "skill_version",
                        "as_of",
                        "source_cutoff",
                        "previous_version",
                    ],
                )
            refused = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("Refusing to overwrite", refused.stderr)

    def test_invalid_examples_fail_closed(self) -> None:
        opportunity_schema = load_json(SCHEMAS / "opportunity.schema.json")
        opportunity = load_json(EXAMPLES / "illustrative_transformer_equipment.json")
        portfolio_schema = load_json(SCHEMAS / "portfolio.schema.json")
        portfolio = load_json(EXAMPLES / "illustrative_portfolio.json")
        evidence_schema = load_json(SCHEMAS / "evidence.schema.json")

        cases: list[tuple[str, Any, dict[str, Any]]] = []
        missing_candidate = copy.deepcopy(opportunity)
        del missing_candidate["candidate"]
        cases.append(("missing-required", missing_candidate, opportunity_schema))
        score_overflow = copy.deepcopy(opportunity)
        score_overflow["scores"]["constraint"]["funded_demand"] = 5.1
        cases.append(("score-maximum", score_overflow, opportunity_schema))
        extra_score_group = copy.deepcopy(opportunity)
        extra_score_group["scores"]["unknown"] = {}
        cases.append(("additional-property", extra_score_group, opportunity_schema))
        invalid_probability = copy.deepcopy(opportunity)
        invalid_probability["scenarios"]["bear"]["probability"] = -0.1
        cases.append(("scenario-minimum", invalid_probability, opportunity_schema))
        invalid_weight = copy.deepcopy(portfolio)
        invalid_weight["positions"][0]["weight"] = 1.1
        cases.append(("portfolio-maximum", invalid_weight, portfolio_schema))
        evidence = {
            "schema_version": "1.0",
            "skill_version": "0.0.0.1",
            "as_of": "2026-07-23",
            "source_cutoff": "2026-07-23",
            "previous_version": None,
            "claims": [
                {
                    "id": "CLM-BASE",
                    "claim": "Synthetic schema fixture.",
                    "claim_type": "fact",
                    "critical": False,
                    "sources": [],
                }
            ],
        }
        invalid_date = copy.deepcopy(evidence)
        invalid_date["as_of"] = "2026-02-30"
        cases.append(("evidence-date-format", invalid_date, evidence_schema))
        invalid_claim_type = copy.deepcopy(evidence)
        invalid_claim_type["claims"][0]["claim_type"] = "opinion"
        cases.append(("evidence-enum", invalid_claim_type, evidence_schema))
        empty_claim = copy.deepcopy(evidence)
        empty_claim["claims"][0]["claim"] = ""
        cases.append(("evidence-min-length", empty_claim, evidence_schema))

        for name, instance, schema in cases:
            with self.subTest(name=name):
                with self.assertRaises(SchemaContractError):
                    assert_valid(instance, schema)


if __name__ == "__main__":
    unittest.main()
