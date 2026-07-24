#!/usr/bin/env python3
"""Flag causal-driver concentration and near-duplicate positions."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

DEFAULT_LIMITS = {
    "max_single_position": 0.15,
    "max_root_driver": 0.35,
    "max_constraint": 0.25,
    "max_customer_ecosystem": 0.30,
    "max_binary_risk": 0.10,
    "max_illiquid_total": 0.15,
}

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


def _tokens(position: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for field in ("drivers", "constraints", "architectures", "customers", "regions", "risk_factors"):
        raw = position.get(field, [])
        if isinstance(raw, list):
            values.update(f"{field}:{str(item).strip().lower()}" for item in raw if str(item).strip())
    return values


def _aggregate(positions: Iterable[Mapping[str, Any]], field: str) -> Dict[str, float]:
    totals: Dict[str, float] = defaultdict(float)
    for position in positions:
        weight = float(position.get("weight", 0))
        values = position.get(field, [])
        if isinstance(values, list):
            for value in set(str(v).strip() for v in values if str(v).strip()):
                totals[value] += weight
    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))


def analyze_portfolio(payload: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = _artifact_metadata(payload)
    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise ValueError("positions must be an array")
    normalized: list[Dict[str, Any]] = []
    errors: list[str] = []
    for idx, item in enumerate(positions):
        if not isinstance(item, Mapping):
            errors.append(f"positions[{idx}] must be an object")
            continue
        ticker = str(item.get("ticker", "")).strip()
        try:
            weight = float(item.get("weight", 0))
        except (TypeError, ValueError):
            errors.append(f"positions[{idx}].weight must be numeric")
            continue
        if not ticker:
            errors.append(f"positions[{idx}].ticker is required")
        if not 0 <= weight <= 1:
            errors.append(f"positions[{idx}].weight must be between 0 and 1")
        normalized.append({**dict(item), "ticker": ticker, "weight": weight})
    if errors:
        return {**metadata, "valid": False, "errors": errors, "alerts": []}

    limits = dict(DEFAULT_LIMITS)
    custom = payload.get("limits", {})
    if isinstance(custom, Mapping):
        for key in limits:
            if key in custom:
                value = float(custom[key])
                if not 0 <= value <= 1:
                    raise ValueError(f"limits.{key} must be between 0 and 1")
                limits[key] = value

    total_weight = sum(p["weight"] for p in normalized)
    alerts: list[Dict[str, Any]] = []
    if total_weight > 1.000001:
        alerts.append({"severity": "error", "type": "weight_sum", "value": total_weight})
    elif total_weight < 0.95:
        alerts.append({"severity": "info", "type": "unallocated_weight", "value": 1 - total_weight})

    for position in normalized:
        if position["weight"] > limits["max_single_position"]:
            alerts.append(
                {
                    "severity": "high",
                    "type": "single_position",
                    "ticker": position["ticker"],
                    "weight": position["weight"],
                    "limit": limits["max_single_position"],
                }
            )

    aggregates = {
        "drivers": _aggregate(normalized, "drivers"),
        "constraints": _aggregate(normalized, "constraints"),
        "customers": _aggregate(normalized, "customers"),
        "regions": _aggregate(normalized, "regions"),
        "risk_factors": _aggregate(normalized, "risk_factors"),
    }
    for value, weight in aggregates["drivers"].items():
        if weight > limits["max_root_driver"]:
            alerts.append({"severity": "high", "type": "root_driver", "value": value, "weight": weight, "limit": limits["max_root_driver"]})
    for value, weight in aggregates["constraints"].items():
        if weight > limits["max_constraint"]:
            alerts.append({"severity": "high", "type": "constraint", "value": value, "weight": weight, "limit": limits["max_constraint"]})
    for value, weight in aggregates["customers"].items():
        if weight > limits["max_customer_ecosystem"]:
            alerts.append({"severity": "medium", "type": "customer_ecosystem", "value": value, "weight": weight, "limit": limits["max_customer_ecosystem"]})

    binary_weight = sum(p["weight"] for p in normalized if bool(p.get("binary_risk", False)))
    illiquid_weight = sum(p["weight"] for p in normalized if bool(p.get("illiquid", False)))
    if binary_weight > limits["max_binary_risk"]:
        alerts.append({"severity": "high", "type": "binary_risk_total", "weight": binary_weight, "limit": limits["max_binary_risk"]})
    if illiquid_weight > limits["max_illiquid_total"]:
        alerts.append({"severity": "high", "type": "illiquid_total", "weight": illiquid_weight, "limit": limits["max_illiquid_total"]})

    pair_overlaps: list[Dict[str, Any]] = []
    for i, left in enumerate(normalized):
        left_tokens = _tokens(left)
        for right in normalized[i + 1 :]:
            right_tokens = _tokens(right)
            union = left_tokens | right_tokens
            score = len(left_tokens & right_tokens) / len(union) if union else 0.0
            if score >= 0.40:
                pair_overlaps.append(
                    {
                        "left": left["ticker"],
                        "right": right["ticker"],
                        "jaccard": round(score, 3),
                        "shared": sorted(left_tokens & right_tokens),
                    }
                )
    pair_overlaps.sort(key=lambda item: -item["jaccard"])
    if pair_overlaps:
        alerts.append({"severity": "medium", "type": "near_duplicate_pairs", "count": len(pair_overlaps)})

    return {
        **metadata,
        "valid": not any(a.get("severity") == "error" for a in alerts),
        "total_weight": round(total_weight, 6),
        "limits": limits,
        "aggregates": aggregates,
        "binary_risk_weight": round(binary_weight, 6),
        "illiquid_weight": round(illiquid_weight, 6),
        "pair_overlaps": pair_overlaps,
        "alerts": alerts,
        "errors": errors,
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
    parser.add_argument("input", help="Portfolio JSON file or '-' for stdin")
    args = parser.parse_args()
    try:
        result = analyze_portfolio(load_json(args.input))
    except ValueError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
