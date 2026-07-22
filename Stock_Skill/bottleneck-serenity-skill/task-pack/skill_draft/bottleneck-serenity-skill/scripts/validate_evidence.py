#!/usr/bin/env python3
"""Validate claim-level evidence against bottleneck-serenity-skill rules."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Mapping

VALID_TYPES = {"fact", "inference", "assumption", "forecast"}
VALID_TIERS = {"A", "B", "C", "D", "E"}
VALID_STANCES = {"supports", "contradicts", "mixed"}
ARTIFACT_SCHEMA_VERSION = "1.0"
SKILL_VERSION = "0.0.0.1"


def _canonical_date(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a canonical YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a canonical YYYY-MM-DD string") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be a canonical YYYY-MM-DD string")
    return value


def _artifact_metadata(payload: Mapping[str, Any]) -> Dict[str, Any]:
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {ARTIFACT_SCHEMA_VERSION}")
    if payload.get("skill_version") != SKILL_VERSION:
        raise ValueError(f"skill_version must equal {SKILL_VERSION}")
    as_of = _canonical_date(payload.get("as_of"), "as_of")
    source_cutoff = _canonical_date(payload.get("source_cutoff"), "source_cutoff")
    if source_cutoff > as_of:
        raise ValueError("source_cutoff cannot be later than as_of")
    if "previous_version" not in payload:
        raise ValueError("previous_version is required")
    previous_version = payload.get("previous_version")
    if previous_version is not None and (
        not isinstance(previous_version, str) or not previous_version.strip()
    ):
        raise ValueError("previous_version must be null or a non-empty string")
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "as_of": as_of,
        "source_cutoff": source_cutoff,
        "previous_version": previous_version,
    }


def validate_ledger(payload: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = _artifact_metadata(payload)
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("claims must be an array")

    errors: list[str] = []
    warnings: list[str] = []
    claim_results: list[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, claim in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(claim, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        claim_id = str(claim.get("id", "")).strip()
        text = str(claim.get("claim", "")).strip()
        claim_type = str(claim.get("claim_type", "")).strip()
        critical = bool(claim.get("critical", False))
        sources = claim.get("sources", [])

        local_errors: list[str] = []
        local_warnings: list[str] = []
        if not claim_id:
            local_errors.append("id is required")
        elif claim_id in seen_ids:
            local_errors.append(f"duplicate id {claim_id}")
        else:
            seen_ids.add(claim_id)
        if not text:
            local_errors.append("claim text is required")
        if claim_type not in VALID_TYPES:
            local_errors.append(f"claim_type must be one of {sorted(VALID_TYPES)}")
        if not isinstance(sources, list):
            local_errors.append("sources must be an array")
            sources = []

        independent_support: set[str] = set()
        primary_support = 0
        contradiction_count = 0
        tier_counts = {tier: 0 for tier in VALID_TIERS}

        for source_index, source in enumerate(sources):
            source_prefix = f"{prefix}.sources[{source_index}]"
            if not isinstance(source, Mapping):
                local_errors.append(f"{source_prefix} must be an object")
                continue
            url = str(source.get("url", "")).strip()
            publisher = str(source.get("publisher", "")).strip()
            date = str(source.get("date", "")).strip()
            tier = str(source.get("tier", "")).strip().upper()
            group = str(source.get("independence_group", "")).strip()
            stance = str(source.get("stance", "")).strip()
            if not url:
                local_errors.append(f"{source_prefix}.url is required")
            if not publisher:
                local_errors.append(f"{source_prefix}.publisher is required")
            if not date:
                local_errors.append(f"{source_prefix}.date is required")
            if tier not in VALID_TIERS:
                local_errors.append(f"{source_prefix}.tier must be A-E")
            else:
                tier_counts[tier] += 1
            if not group:
                local_errors.append(f"{source_prefix}.independence_group is required")
            if stance not in VALID_STANCES:
                local_errors.append(f"{source_prefix}.stance must be supports/contradicts/mixed")
            elif stance == "supports":
                if group:
                    independent_support.add(group)
                if tier == "A":
                    primary_support += 1
            elif stance in {"contradicts", "mixed"}:
                contradiction_count += 1

        if claim_type == "fact" and critical:
            if len(independent_support) < 2:
                local_errors.append(
                    "critical fact needs at least two independent supporting source origins"
                )
            if primary_support < 1:
                local_errors.append("critical fact needs at least one Tier A supporting source")
            if not str(claim.get("contradiction_search", "")).strip():
                local_warnings.append("critical fact has no documented contradiction search")
        elif claim_type == "fact" and not sources:
            local_errors.append("fact has no source")
        elif claim_type == "inference":
            depends_on = claim.get("depends_on", [])
            if not isinstance(depends_on, list) or not depends_on:
                local_warnings.append("inference should reference supporting claim IDs in depends_on")
        elif claim_type in {"assumption", "forecast"} and not str(claim.get("notes", "")).strip():
            local_warnings.append(f"{claim_type} should document rationale/range in notes")

        if contradiction_count and str(claim.get("status", "")) == "supported":
            local_warnings.append("claim marked supported despite contradictory/mixed sources")
        if tier_counts["D"] + tier_counts["E"] == len(sources) and sources:
            local_warnings.append("claim relies only on lead-generation or unverified sources")

        errors.extend(f"{prefix}: {item}" for item in local_errors)
        warnings.extend(f"{prefix}: {item}" for item in local_warnings)
        claim_results.append(
            {
                "id": claim_id,
                "critical": critical,
                "claim_type": claim_type,
                "independent_support_groups": len(independent_support),
                "tier_a_support_count": primary_support,
                "contradictory_or_mixed_sources": contradiction_count,
                "valid": not local_errors,
                "errors": local_errors,
                "warnings": local_warnings,
            }
        )

    return {
        **metadata,
        "valid": not errors,
        "claim_count": len(claims),
        "errors": errors,
        "warnings": warnings,
        "claims": claim_results,
    }


def load_json(path: str) -> Dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("Input must be a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Evidence ledger JSON file or '-' for stdin")
    parser.add_argument("--strict-warnings", action="store_true", help="Return non-zero on warnings")
    args = parser.parse_args()
    try:
        result = validate_ledger(load_json(args.input))
    except ValueError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"] or (args.strict_warnings and result["warnings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
