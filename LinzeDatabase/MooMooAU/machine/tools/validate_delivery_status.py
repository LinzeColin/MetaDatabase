#!/usr/bin/env python3
"""Fail-closed validator for the sole current MooMooAU delivery status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from build_delivery_status import PROJECT_ROOT, STATUS_PATH, build_status
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from validate_assurance_reviews import evaluate_assurance_reviews
from validate_evidence import validate_stage6_candidate_bundle

sys.dont_write_bytecode = True

SCHEMA_PATH = Path("schemas/delivery-status-v1.schema.json")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_value(value: object, root: Path = PROJECT_ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    try:
        schema = _load(root / SCHEMA_PATH)
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError):
        return ["delivery status schema is missing or invalid"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"schema violation at {location}: {error.validator}")
    try:
        expected = build_status(root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        errors.append("deterministic status rebuild failed")
    else:
        if value != expected:
            errors.append("status differs from deterministic source evidence")
    if isinstance(value, dict) and value.get("package_version") == "1.0.5":
        if validate_stage6_candidate_bundle(root, root.parents[1]):
            errors.append("closed RMD-05 status lacks candidate-bound Stage 6 v2 evidence")
        try:
            assurance = evaluate_assurance_reviews(root, root.parents[1], verify_git=True)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            errors.append("closed RMD-05 assurance provenance evaluation failed")
        else:
            if assurance.get("status") != "PASS":
                errors.append("closed RMD-05 status lacks clean Git-bound assurance provenance")
    return errors


def validate(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = root.resolve()
    path = root / STATUS_PATH
    try:
        value = _load(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "errors": [f"invalid status evidence: {type(exc).__name__}"]}
    errors = validate_value(value, root)
    production_readiness = None
    if isinstance(value, dict):
        dimensions = value.get("dimensions")
        if isinstance(dimensions, dict):
            production = dimensions.get("production_readiness")
            if isinstance(production, dict):
                production_readiness = production.get("status")
    return {
        "status": "PASS" if not errors else "FAIL",
        "authority": STATUS_PATH.as_posix(),
        "overall_status": value.get("overall_status") if isinstance(value, dict) else None,
        "production_readiness": production_readiness,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = validate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
