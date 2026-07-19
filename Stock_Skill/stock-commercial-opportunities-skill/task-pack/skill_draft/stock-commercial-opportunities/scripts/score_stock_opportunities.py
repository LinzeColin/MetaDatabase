#!/usr/bin/env python3
"""Deterministically rank listed-equity research candidates.

This standard-library-only utility separates attractiveness, risk, evidence
confidence, and E0-E5 maturity. It prioritizes research; it never predicts
returns or approves a trade.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

DIMENSION_WEIGHTS: Dict[str, float] = {
    "commercial_value_pool": 12.0,
    "issuer_exposure_attribution": 16.0,
    "financial_capture_path": 12.0,
    "beneficiary_position": 10.0,
    "expectations_variant": 12.0,
    "valuation_support": 10.0,
    "catalyst_revision_path": 10.0,
    "durability_balance_sheet": 7.0,
    "liquidity_instrument_fit": 5.0,
    "research_edge_speed": 6.0,
}

RISK_MAX_DEDUCTIONS: Dict[str, float] = {
    "exposure_gap": 8.0,
    "expectations_priced_in": 7.0,
    "valuation_downside": 6.0,
    "earnings_cyclicality": 5.0,
    "balance_sheet_funding": 4.0,
    "regulatory_geopolitical": 4.0,
    "liquidity_shortability": 3.0,
    "freshness_source_gap": 3.0,
}

CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "claim_coverage": 20.0,
    "primary_source_quality": 20.0,
    "exposure_directness": 20.0,
    "metric_period_normalization": 15.0,
    "source_diversity": 10.0,
    "recency": 10.0,
    "contradiction_resolution": 5.0,
}

ROI_FIELDS = ("learning", "thesis", "catalyst", "decision")
EVIDENCE_SIGNAL_FIELDS = (
    "public_source_families",
    "company_filings",
    "quantified_exposure_metrics",
    "commercial_capture_signals",
    "current_valuation_observations",
    "confirmed_catalysts",
    "thesis_falsifiers",
    "liquidity_checks",
)
IDENTITY_FIELDS = (
    "id",
    "title",
    "issuer",
    "ticker",
    "exchange",
    "security_type",
    "currency",
    "as_of",
)
MATURITY_LABELS = {
    "E0": "Theme",
    "E1": "Desk-screened",
    "E2": "Exposure-attributed",
    "E3": "Commercial-capture",
    "E4": "Equity-setup",
    "E5": "Thesis-ready",
}
MATURITY_RANK = {code: rank for rank, code in enumerate(MATURITY_LABELS)}
STATUS_ORDER = {
    "ADVANCE_RESEARCH": 5,
    "DILIGENCE_NEXT": 4,
    "WATCHLIST": 3,
    "SCREEN_FLAG": 2,
    "REJECT": 1,
}


class InputError(ValueError):
    """Raised when scoring input violates the published contract."""


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputError(f"{path} must be an object")
    return value


def _non_empty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{path} must be a non-empty string")
    return value.strip()


def _score(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path} must be a number between 0 and 10")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 10.0:
        raise InputError(f"{path} must be between 0 and 10; got {value!r}")
    return number


def _count(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"{path} must be a non-negative integer")
    return value


def _exact_scores(
    container: Mapping[str, Any], required: Mapping[str, float], path: str
) -> Dict[str, float]:
    missing = sorted(set(required) - set(container))
    unknown = sorted(set(container) - set(required))
    if missing:
        raise InputError(f"{path} missing fields: {', '.join(missing)}")
    if unknown:
        raise InputError(f"{path} has unknown fields: {', '.join(unknown)}")
    return {key: _score(container[key], f"{path}.{key}") for key in required}


def _exact_counts(value: Any, path: str) -> Dict[str, int]:
    signals = _mapping(value, path)
    missing = sorted(set(EVIDENCE_SIGNAL_FIELDS) - set(signals))
    unknown = sorted(set(signals) - set(EVIDENCE_SIGNAL_FIELDS))
    if missing:
        raise InputError(f"{path} missing fields: {', '.join(missing)}")
    if unknown:
        raise InputError(f"{path} has unknown fields: {', '.join(unknown)}")
    return {key: _count(signals[key], f"{path}.{key}") for key in EVIDENCE_SIGNAL_FIELDS}


def validate_payload(payload: Any) -> List[Mapping[str, Any]]:
    root = _mapping(payload, "root")
    unknown_root = sorted(set(root) - {"fixture", "candidates"})
    if unknown_root:
        raise InputError(f"root has unknown fields: {', '.join(unknown_root)}")
    if "fixture" in root and not isinstance(root["fixture"], bool):
        raise InputError("root.fixture must be a boolean")
    candidates = root.get("candidates")
    if not isinstance(candidates, list):
        raise InputError("root.candidates must be an array")

    seen_ids = set()
    validated: List[Mapping[str, Any]] = []
    for index, item in enumerate(candidates):
        path = f"root.candidates[{index}]"
        candidate = _mapping(item, path)
        for field in IDENTITY_FIELDS:
            _non_empty_text(candidate.get(field), f"{path}.{field}")
        candidate_id = str(candidate["id"])
        if candidate_id in seen_ids:
            raise InputError(f"duplicate candidate id: {candidate_id}")
        seen_ids.add(candidate_id)
        try:
            date.fromisoformat(str(candidate["as_of"]))
        except ValueError as exc:
            raise InputError(f"{path}.as_of must use YYYY-MM-DD") from exc
        if "thesis" in candidate:
            _non_empty_text(candidate["thesis"], f"{path}.thesis")
        if "first_rejection" in candidate:
            _non_empty_text(candidate["first_rejection"], f"{path}.first_rejection")

        _exact_scores(
            _mapping(candidate.get("dimensions"), f"{path}.dimensions"),
            DIMENSION_WEIGHTS,
            f"{path}.dimensions",
        )
        _exact_scores(
            _mapping(candidate.get("risks"), f"{path}.risks"),
            RISK_MAX_DEDUCTIONS,
            f"{path}.risks",
        )
        _exact_scores(
            _mapping(candidate.get("confidence"), f"{path}.confidence"),
            CONFIDENCE_WEIGHTS,
            f"{path}.confidence",
        )

        roi = _mapping(candidate.get("roi"), f"{path}.roi")
        missing_roi = sorted(set(ROI_FIELDS) - set(roi))
        unknown_roi = sorted(set(roi) - set(ROI_FIELDS))
        if missing_roi:
            raise InputError(f"{path}.roi missing fields: {', '.join(missing_roi)}")
        if unknown_roi:
            raise InputError(f"{path}.roi has unknown fields: {', '.join(unknown_roi)}")
        for key in ROI_FIELDS:
            _score(roi[key], f"{path}.roi.{key}")

        _exact_counts(candidate.get("evidence_signals"), f"{path}.evidence_signals")
        hard_stops = candidate.get("hard_stops", [])
        if not isinstance(hard_stops, list) or any(
            not isinstance(stop, str) or not stop.strip() for stop in hard_stops
        ):
            raise InputError(f"{path}.hard_stops must be an array of non-empty strings")
        validated.append(candidate)
    return validated


def evidence_maturity(signals: Mapping[str, int]) -> str:
    """Derive the highest conservative evidence gate reached."""
    if (
        signals["company_filings"] >= 1
        and signals["quantified_exposure_metrics"] >= 1
    ):
        if signals["commercial_capture_signals"] >= 1:
            if (
                signals["current_valuation_observations"] >= 1
                and signals["confirmed_catalysts"] >= 1
            ):
                if (
                    signals["thesis_falsifiers"] >= 2
                    and signals["liquidity_checks"] >= 1
                ):
                    return "E5"
                return "E4"
            return "E3"
        return "E2"
    if signals["public_source_families"] >= 3:
        return "E1"
    return "E0"


def next_maturity_gate(code: str) -> str:
    return {
        "E0": "open at least 3 independent public source families and resolve identity",
        "E1": "add one company filing and one quantified exposure metric",
        "E2": "add an orders/backlog/revenue/margin/cash-flow capture signal",
        "E3": "add current valuation context and one confirmed catalyst link",
        "E4": "add at least 2 falsifiers plus one liquidity/instrument check",
        "E5": "route to deeper research and maintain freshness; no trade approval",
    }[code]


def decision_status(
    score: float, confidence: float, maturity: str, hard_stops: Sequence[str]
) -> str:
    if hard_stops or score < 40.0:
        return "REJECT"
    if MATURITY_RANK[maturity] <= MATURITY_RANK["E1"] or score < 55.0:
        return "SCREEN_FLAG"
    if score < 65.0 or confidence < 55.0:
        return "WATCHLIST"
    if (
        MATURITY_RANK[maturity] >= MATURITY_RANK["E4"]
        and score >= 75.0
        and confidence >= 65.0
    ):
        return "ADVANCE_RESEARCH"
    return "DILIGENCE_NEXT"


def score_candidate(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    dimensions = candidate["dimensions"]
    risks = candidate["risks"]
    confidence_parts = candidate["confidence"]
    signals = candidate["evidence_signals"]
    hard_stops = candidate.get("hard_stops", [])

    base_score = sum(
        float(dimensions[key]) / 10.0 * weight
        for key, weight in DIMENSION_WEIGHTS.items()
    )
    risk_deduction = sum(
        float(risks[key]) / 10.0 * maximum
        for key, maximum in RISK_MAX_DEDUCTIONS.items()
    )
    confidence = sum(
        float(confidence_parts[key]) / 10.0 * weight
        for key, weight in CONFIDENCE_WEIGHTS.items()
    )
    uncertainty_penalty = (100.0 - confidence) * 0.15
    decision_score_value = max(
        0.0, min(100.0, base_score - risk_deduction - uncertainty_penalty)
    )
    maturity = evidence_maturity(signals)
    status = decision_status(decision_score_value, confidence, maturity, hard_stops)
    research_roi = sum(float(candidate["roi"][key]) for key in ROI_FIELDS) / len(ROI_FIELDS)

    return {
        "id": candidate["id"],
        "title": candidate["title"],
        "issuer": candidate["issuer"],
        "ticker": candidate["ticker"],
        "exchange": candidate["exchange"],
        "security_type": candidate["security_type"],
        "currency": candidate["currency"],
        "as_of": candidate["as_of"],
        "base_score": round(base_score, 1),
        "risk_deduction": round(risk_deduction, 1),
        "evidence_confidence": round(confidence, 1),
        "uncertainty_penalty": round(uncertainty_penalty, 1),
        "decision_score": round(decision_score_value, 1),
        "research_roi": round(research_roi, 1),
        "maturity_code": maturity,
        "maturity_label": MATURITY_LABELS[maturity],
        "status": status,
        "next_maturity_gate": next_maturity_gate(maturity),
        "first_rejection": candidate.get("first_rejection", "Not provided"),
        "hard_stops": list(hard_stops),
    }


def score_payload(payload: Any) -> List[Dict[str, Any]]:
    rows = [score_candidate(candidate) for candidate in validate_payload(payload)]
    return sorted(
        rows,
        key=lambda row: (
            -STATUS_ORDER[row["status"]],
            -float(row["decision_score"]),
            str(row["id"]),
        ),
    )


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def format_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return (
            "Decision: NO_QUALIFIED_CANDIDATE\n\n"
            "No candidate was supplied or survived the research gate. Do not add filler."
        )
    lines = [
        "| Rank | Issuer / ticker / exchange | Decision score | Risk | Confidence | E-level | Status | Next gate |",
        "|---:|---|---:|---:|---:|---|---|---|",
    ]
    for rank, row in enumerate(rows, start=1):
        security = f"{row['issuer']} / {row['ticker']} / {row['exchange']}"
        lines.append(
            "| {rank} | {security} | {score:.1f} | {risk:.1f} | {confidence:.1f} | "
            "{maturity} | {status} | {gate} |".format(
                rank=rank,
                security=_cell(security),
                score=float(row["decision_score"]),
                risk=float(row["risk_deduction"]),
                confidence=float(row["evidence_confidence"]),
                maturity=_cell(row["maturity_code"]),
                status=_cell(row["status"]),
                gate=_cell(row["next_maturity_gate"]),
            )
        )
    lines.extend(
        [
            "",
            "> Heuristic research priority only. It is not expected return, target price, personal investment advice, or trade approval.",
        ]
    )
    return "\n".join(lines)


def format_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    fields = [
        "id",
        "issuer",
        "ticker",
        "exchange",
        "decision_score",
        "risk_deduction",
        "evidence_confidence",
        "maturity_code",
        "status",
        "research_roi",
        "next_maturity_gate",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON file path, or - for stdin")
    parser.add_argument("--format", choices=("json", "markdown", "csv"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        rows = score_payload(json.loads(raw))
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print(format_markdown(rows))
    elif args.format == "csv":
        print(format_csv(rows), end="")
    else:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
