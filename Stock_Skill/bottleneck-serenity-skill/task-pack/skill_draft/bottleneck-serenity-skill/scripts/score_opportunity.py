#!/usr/bin/env python3
"""Score a bottleneck-serenity-skill opportunity.

The score is a research-priority aid, not a return forecast. Hard flags and
minimum gates override the numerical result.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

DIMENSION_WEIGHTS: Dict[str, Dict[str, float]] = {
    "constraint": {
        "funded_demand": 15,
        "architectural_necessity": 15,
        "current_tightness": 10,
        "supplier_concentration": 10,
        "qualification_barrier": 15,
        "substitution_difficulty": 15,
        "expansion_lead_time": 10,
        "policy_resilience": 10,
    },
    "capture": {
        "exposure_materiality": 15,
        "pricing_power": 15,
        "capacity_to_ship": 15,
        "unit_economics": 10,
        "contract_counterparty": 10,
        "appropriability": 10,
        "balance_sheet": 10,
        "dilution_discipline": 10,
        "capital_allocation": 5,
    },
    "mispricing": {
        "expectations_gap": 20,
        "valuation_asymmetry": 20,
        "coverage_gap": 10,
        "catalyst_clarity": 15,
        "estimate_revision_potential": 15,
        "crowding_headroom": 10,
        "entry_setup": 10,
    },
    "evidence": {
        "primary_source_coverage": 25,
        "independent_corroboration": 20,
        "numerical_traceability": 15,
        "freshness": 15,
        "contradiction_search": 15,
        "source_independence": 10,
    },
    "investability": {
        "liquidity": 15,
        "governance_accounting": 15,
        "geopolitical_regulatory": 15,
        "customer_diversification": 10,
        "technology_resilience": 10,
        "balance_sheet_survival": 15,
        "float_gap_risk": 10,
        "portfolio_fit": 10,
    },
}

HARD_FLAG_MESSAGES = {
    "no_primary_evidence": "Critical constraint claim lacks primary evidence.",
    "wrong_entity_or_ticker": "The listed entity or ticker does not own the relevant exposure.",
    "no_material_revenue_bridge": "No material bridge from the constraint to company revenue/per-share value.",
    "substitution_before_monetization": "A substitute or supply response is likely before monetization.",
    "unfunded_financing_gap": "Expansion or survival requires materially unfunded financing.",
    "kill_switch_triggered": "A pre-declared thesis kill switch has triggered.",
    "bull_case_required_to_avoid_loss": "The current price requires the bull case merely to avoid loss.",
}

ARTIFACT_SCHEMA_VERSION = "1.0"
SKILL_VERSION = "0.0.0.1"
BRIDGE_CASH_CHECKS = ("capex", "working_capital", "interest", "tax")
BRIDGE_DILUTION_CHECKS = (
    "stock_based_compensation",
    "convertibles",
    "warrants",
    "other_contingent_shares",
)

TEMPLATE: Dict[str, Any] = {
    "schema_version": ARTIFACT_SCHEMA_VERSION,
    "skill_version": SKILL_VERSION,
    "as_of": "YYYY-MM-DD",
    "source_cutoff": "YYYY-MM-DD",
    "previous_version": None,
    "thesis_id": "theme-company-YYYYMMDD",
    "candidate": {
        "ticker": "EXMPL",
        "company": "Illustrative Company",
        "market": "US",
        "currency": "USD",
        "role": "owner|unlocker|substitute|tollbooth|absorber|public_proxy",
        "lifecycle_stage": "QUALIFICATION",
    },
    "scores": {
        dimension: {factor: 0 for factor in weights}
        for dimension, weights in DIMENSION_WEIGHTS.items()
    },
    "clocks": {
        "scarcity_p10_months": 12,
        "scarcity_p50_months": 30,
        "scarcity_p90_months": 60,
        "monetization_lag_months": 9,
        "market_discovery_months": 6,
        "contracted_forward_ramp": False,
    },
    "scenarios": {
        "bear": {"probability": 0.25, "return_pct": -40, "summary": ""},
        "base": {"probability": 0.50, "return_pct": 30, "summary": ""},
        "bull": {"probability": 0.25, "return_pct": 100, "summary": ""},
    },
    "equity_bridge": {
        "complete": False,
        "revenue": None,
        "free_cash_flow": None,
        "fully_diluted_shares": None,
        "per_share_fcf": None,
        "cash_conversion_checks": {key: False for key in BRIDGE_CASH_CHECKS},
        "dilution_checks": {key: False for key in BRIDGE_DILUTION_CHECKS},
        "unverified_critical_multipliers": [
            "Replace with every unresolved revenue-to-per-share multiplier."
        ],
    },
    "hard_flags": {key: False for key in HARD_FLAG_MESSAGES},
    "kill_switches": [],
    "notes": [],
}


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


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _rating(value: Any, label: str) -> float:
    number = _number(value, label)
    if not 0 <= number <= 5:
        raise ValueError(f"{label} must be between 0 and 5; got {number}")
    return number


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _weighted_dimension(
    ratings: Mapping[str, Any], weights: Mapping[str, float], label: str
) -> Tuple[float, Dict[str, Dict[str, float]], list[str]]:
    details: Dict[str, Dict[str, float]] = {}
    warnings: list[str] = []
    total = 0.0
    for factor, weight in weights.items():
        if factor not in ratings:
            warnings.append(f"Missing {label}.{factor}; scored as 0.")
        rating = _rating(ratings.get(factor, 0), f"scores.{label}.{factor}")
        points = rating / 5.0 * weight
        total += points
        details[factor] = {
            "rating": round(rating, 3),
            "weight": round(weight, 3),
            "points": round(points, 3),
        }
    unknown = sorted(set(ratings) - set(weights))
    if unknown:
        warnings.append(f"Unknown {label} factors ignored: {', '.join(unknown)}")
    return round(total, 3), details, warnings


def _geometric_mean(values: Iterable[float]) -> float:
    vals = [max(float(v), 0.01) for v in values]
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _duration_multiplier(runway: float) -> float:
    if runway < 0:
        return 0.50
    if runway < 6:
        return 0.70
    if runway < 12:
        return 0.85
    if runway < 24:
        return 1.00
    if runway < 48:
        return 1.07
    return 1.10


def _scenario_metrics(scenarios: Mapping[str, Any]) -> Dict[str, float]:
    required = ("bear", "base", "bull")
    parsed: Dict[str, Dict[str, float]] = {}
    for name in required:
        if name not in scenarios or not isinstance(scenarios[name], Mapping):
            raise ValueError(f"scenarios.{name} is required")
        probability = _number(scenarios[name].get("probability"), f"scenarios.{name}.probability")
        return_pct = _number(scenarios[name].get("return_pct"), f"scenarios.{name}.return_pct")
        if not 0 <= probability <= 1:
            raise ValueError(f"scenarios.{name}.probability must be between 0 and 1")
        parsed[name] = {"probability": probability, "return_pct": return_pct}

    probability_sum = sum(v["probability"] for v in parsed.values())
    if abs(probability_sum - 1.0) > 1e-6:
        raise ValueError(f"scenario probabilities must sum to 1.0; got {probability_sum:.6f}")

    expected = sum(v["probability"] * v["return_pct"] for v in parsed.values())
    bear_return = parsed["bear"]["return_pct"]
    downside = max(abs(min(bear_return, 0.0)), 10.0)
    ratio = expected / downside
    if expected < 0:
        multiplier = 0.75
    else:
        multiplier = _clamp(0.85 + 0.35 * ratio, 0.75, 1.20)
    return {
        "expected_return_pct": round(expected, 3),
        "bear_downside_reference_pct": round(downside, 3),
        "asymmetry_ratio": round(ratio, 4),
        "asymmetry_multiplier": round(multiplier, 4),
    }


def _equity_bridge(payload: Mapping[str, Any]) -> Dict[str, Any]:
    bridge = payload.get("equity_bridge")
    if not isinstance(bridge, Mapping):
        raise ValueError("equity_bridge is required")
    required = {
        "complete",
        "revenue",
        "free_cash_flow",
        "fully_diluted_shares",
        "per_share_fcf",
        "cash_conversion_checks",
        "dilution_checks",
        "unverified_critical_multipliers",
    }
    if set(bridge) != required:
        missing = sorted(required - set(bridge))
        extra = sorted(set(bridge) - required)
        raise ValueError(
            f"equity_bridge keys mismatch: missing={missing}, extra={extra}"
        )
    complete = bridge["complete"]
    if not isinstance(complete, bool):
        raise ValueError("equity_bridge.complete must be boolean")

    def checks(name: str, expected: tuple[str, ...]) -> Dict[str, bool]:
        raw = bridge[name]
        if not isinstance(raw, Mapping) or set(raw) != set(expected):
            raise ValueError(f"equity_bridge.{name} must contain exactly {list(expected)}")
        if any(not isinstance(raw[key], bool) for key in expected):
            raise ValueError(f"equity_bridge.{name} values must be boolean")
        return {key: raw[key] for key in expected}

    cash_checks = checks("cash_conversion_checks", BRIDGE_CASH_CHECKS)
    dilution_checks = checks("dilution_checks", BRIDGE_DILUTION_CHECKS)
    unresolved = bridge["unverified_critical_multipliers"]
    if (
        not isinstance(unresolved, list)
        or any(not isinstance(item, str) or not item.strip() for item in unresolved)
        or len(unresolved) != len(set(unresolved))
    ):
        raise ValueError(
            "equity_bridge.unverified_critical_multipliers must be unique strings"
        )

    numeric: Dict[str, float | None] = {}
    for field in (
        "revenue",
        "free_cash_flow",
        "fully_diluted_shares",
        "per_share_fcf",
    ):
        raw = bridge[field]
        numeric[field] = None if raw is None else _number(raw, f"equity_bridge.{field}")
    if numeric["revenue"] is not None and numeric["revenue"] < 0:
        raise ValueError("equity_bridge.revenue cannot be negative")
    if (
        numeric["fully_diluted_shares"] is not None
        and numeric["fully_diluted_shares"] <= 0
    ):
        raise ValueError("equity_bridge.fully_diluted_shares must be positive")

    if complete:
        if any(value is None for value in numeric.values()):
            raise ValueError("complete equity_bridge requires all four numeric values")
        if not all(cash_checks.values()) or not all(dilution_checks.values()):
            raise ValueError("complete equity_bridge requires every cash/dilution check")
        if unresolved:
            raise ValueError(
                "complete equity_bridge cannot retain unverified critical multipliers"
            )
        calculated = numeric["free_cash_flow"] / numeric["fully_diluted_shares"]
        tolerance = max(1e-6, abs(calculated) * 1e-6)
        if abs(numeric["per_share_fcf"] - calculated) > tolerance:
            raise ValueError(
                "equity_bridge.per_share_fcf must equal free_cash_flow / "
                "fully_diluted_shares"
            )
    elif not unresolved:
        raise ValueError(
            "incomplete equity_bridge must list unverified critical multipliers"
        )

    return {
        "complete": complete,
        **numeric,
        "cash_conversion_checks": cash_checks,
        "dilution_checks": dilution_checks,
        "unverified_critical_multipliers": list(unresolved),
    }


def _decision_label(
    dimensions: Mapping[str, float],
    final_score: float,
    expected_return: float,
    active_flags: list[str],
    runway: float,
    contracted_forward_ramp: bool,
) -> Tuple[str, list[str], bool]:
    reasons: list[str] = []
    hard_gates_passed = True

    if "kill_switch_triggered" in active_flags:
        return "BROKEN", [HARD_FLAG_MESSAGES["kill_switch_triggered"]], False

    fatal_flags = {
        "wrong_entity_or_ticker",
        "substitution_before_monetization",
        "unfunded_financing_gap",
        "bull_case_required_to_avoid_loss",
    }
    fatal_active = [flag for flag in active_flags if flag in fatal_flags]
    if fatal_active:
        reasons.extend(HARD_FLAG_MESSAGES[flag] for flag in fatal_active)
        return "AVOID", reasons, False

    if "no_material_revenue_bridge" in active_flags or dimensions["capture"] < 55:
        if "no_material_revenue_bridge" in active_flags:
            reasons.append(HARD_FLAG_MESSAGES["no_material_revenue_bridge"])
        if dimensions["capture"] < 55:
            reasons.append(f"Rent-capture score {dimensions['capture']:.1f} is below 55.")
        return "BOTTLENECK_NOT_EQUITY", reasons, False

    if "no_primary_evidence" in active_flags or dimensions["evidence"] < 60:
        if "no_primary_evidence" in active_flags:
            reasons.append(HARD_FLAG_MESSAGES["no_primary_evidence"])
        if dimensions["evidence"] < 60:
            reasons.append(f"Evidence score {dimensions['evidence']:.1f} is below 60.")
        return "WATCH_EVIDENCE", reasons, False

    if dimensions["constraint"] < 60:
        reasons.append(f"Structural-constraint score {dimensions['constraint']:.1f} is below 60.")
        return "WATCH_EVIDENCE", reasons, False

    if dimensions["investability"] < 50:
        reasons.append(f"Investability score {dimensions['investability']:.1f} is below 50.")
        return "AVOID", reasons, False

    if runway < 6 and not contracted_forward_ramp:
        reasons.append(
            f"Monetizable runway {runway:.1f} months is below six months without a contracted ramp."
        )
        hard_gates_passed = False
        return "WATCH_EVIDENCE", reasons, hard_gates_passed

    if dimensions["mispricing"] < 45:
        reasons.append(f"Mispricing/timing score {dimensions['mispricing']:.1f} is below 45.")
        return "WATCH_PRICED", reasons, True

    if final_score >= 75 and expected_return > 15:
        reasons.append("All gates pass with high composite quality and positive scenario asymmetry.")
        return "RESEARCH_PRIORITY", reasons, True

    if final_score >= 62 and expected_return > 0:
        reasons.append("All hard gates pass, but uncertainty or asymmetry limits priority.")
        return "CANDIDATE", reasons, True

    if expected_return <= 0:
        reasons.append("Scenario-weighted expected return is non-positive.")
        return "WATCH_PRICED", reasons, True

    reasons.append("Composite score is below the candidate threshold.")
    return "WATCH_EVIDENCE", reasons, True


def score_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = _artifact_metadata(payload)
    scores = payload.get("scores")
    if not isinstance(scores, Mapping):
        raise ValueError("scores must be an object")

    dimension_scores: Dict[str, float] = {}
    dimension_details: Dict[str, Any] = {}
    warnings: list[str] = []
    for dimension, weights in DIMENSION_WEIGHTS.items():
        ratings = scores.get(dimension, {})
        if not isinstance(ratings, Mapping):
            raise ValueError(f"scores.{dimension} must be an object")
        value, details, dim_warnings = _weighted_dimension(ratings, weights, dimension)
        dimension_scores[dimension] = value
        dimension_details[dimension] = details
        warnings.extend(dim_warnings)

    clocks = payload.get("clocks")
    if not isinstance(clocks, Mapping):
        raise ValueError("clocks must be an object")
    p10 = _number(clocks.get("scarcity_p10_months"), "clocks.scarcity_p10_months")
    p50 = _number(clocks.get("scarcity_p50_months"), "clocks.scarcity_p50_months")
    p90 = _number(clocks.get("scarcity_p90_months"), "clocks.scarcity_p90_months")
    monetization = _number(clocks.get("monetization_lag_months"), "clocks.monetization_lag_months")
    discovery = _number(clocks.get("market_discovery_months"), "clocks.market_discovery_months")
    if min(p10, p50, p90, monetization, discovery) < 0:
        raise ValueError("clock values cannot be negative")
    if not p10 <= p50 <= p90:
        raise ValueError("scarcity clocks must satisfy P10 <= P50 <= P90")
    runway = p50 - monetization
    duration_mult = _duration_multiplier(runway)
    contracted_forward_ramp = bool(clocks.get("contracted_forward_ramp", False))

    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, Mapping):
        raise ValueError("scenarios must be an object")
    scenario_metrics = _scenario_metrics(scenarios)
    equity_bridge = _equity_bridge(payload)

    core = _geometric_mean(dimension_scores.values())
    final_score = _clamp(
        core * duration_mult * scenario_metrics["asymmetry_multiplier"], 0.0, 100.0
    )

    hard_flags = payload.get("hard_flags", {})
    if hard_flags is None:
        hard_flags = {}
    if not isinstance(hard_flags, Mapping):
        raise ValueError("hard_flags must be an object")
    if (
        not equity_bridge["complete"]
        and not bool(hard_flags.get("no_material_revenue_bridge"))
    ):
        raise ValueError(
            "incomplete equity_bridge requires hard_flags.no_material_revenue_bridge=true"
        )
    active_flags = sorted(str(key) for key, value in hard_flags.items() if bool(value))
    for flag in active_flags:
        if flag not in HARD_FLAG_MESSAGES:
            warnings.append(f"Unknown active hard flag retained: {flag}")

    label, reasons, hard_gates_passed = _decision_label(
        dimension_scores,
        final_score,
        scenario_metrics["expected_return_pct"],
        active_flags,
        runway,
        contracted_forward_ramp,
    )

    candidate = payload.get("candidate", {})
    if not isinstance(candidate, Mapping):
        raise ValueError("candidate must be an object")

    result: Dict[str, Any] = {
        **metadata,
        "thesis_id": payload.get("thesis_id", ""),
        "candidate": dict(candidate),
        "decision": {
            "label": label,
            "hard_gates_passed": hard_gates_passed,
            "reasons": reasons,
        },
        "dimension_scores": {key: round(value, 3) for key, value in dimension_scores.items()},
        "dimension_details": dimension_details,
        "clocks": {
            "scarcity_p10_months": p10,
            "scarcity_p50_months": p50,
            "scarcity_p90_months": p90,
            "monetization_lag_months": monetization,
            "market_discovery_months": discovery,
            "monetizable_runway_months": round(runway, 3),
            "duration_multiplier": duration_mult,
            "contracted_forward_ramp": contracted_forward_ramp,
        },
        "scenario_metrics": scenario_metrics,
        "equity_bridge": equity_bridge,
        "core_geometric_score": round(core, 3),
        "final_score": round(final_score, 3),
        "active_hard_flags": active_flags,
        "hard_flag_messages": [
            HARD_FLAG_MESSAGES.get(flag, f"Unknown hard flag: {flag}") for flag in active_flags
        ],
        "kill_switches": payload.get("kill_switches", []),
        "warnings": warnings,
        "notes": payload.get("notes", []),
    }
    return result


def to_markdown(result: Mapping[str, Any]) -> str:
    candidate = result.get("candidate", {})
    ticker = candidate.get("ticker", "Unknown") if isinstance(candidate, Mapping) else "Unknown"
    company = candidate.get("company", "") if isinstance(candidate, Mapping) else ""
    title = f"{ticker} — {company}" if company else str(ticker)
    decision = result["decision"]
    clocks = result["clocks"]
    scenario = result["scenario_metrics"]
    bridge = result["equity_bridge"]

    lines = [
        f"# bottleneck-serenity-skill score — {title}",
        "",
        f"- As of: `{result.get('as_of', '')}`",
        f"- Source cutoff: `{result.get('source_cutoff', '')}`",
        f"- Skill version: `{result.get('skill_version', '')}`",
        f"- Decision: **{decision['label']}**",
        f"- Final score: **{result['final_score']:.1f} / 100**",
        f"- Core geometric score: {result['core_geometric_score']:.1f}",
        f"- Hard gates passed: `{str(decision['hard_gates_passed']).lower()}`",
        f"- Equity bridge complete: `{str(bridge['complete']).lower()}`",
        f"- Per-share FCF: `{bridge['per_share_fcf']}`",
        "",
        "## Decision reasons",
    ]
    for reason in decision.get("reasons", []):
        lines.append(f"- {reason}")

    lines.extend([
        "",
        "## Dimension scores",
        "",
        "| Dimension | Score |",
        "|---|---:|",
    ])
    for dimension, score in result["dimension_scores"].items():
        lines.append(f"| {dimension} | {score:.1f} |")

    lines.extend([
        "",
        "## Three clocks",
        "",
        "| Metric | Months |",
        "|---|---:|",
        f"| Scarcity P10 | {clocks['scarcity_p10_months']:.1f} |",
        f"| Scarcity P50 | {clocks['scarcity_p50_months']:.1f} |",
        f"| Scarcity P90 | {clocks['scarcity_p90_months']:.1f} |",
        f"| Monetization lag | {clocks['monetization_lag_months']:.1f} |",
        f"| Market discovery | {clocks['market_discovery_months']:.1f} |",
        f"| Monetizable runway | **{clocks['monetizable_runway_months']:.1f}** |",
        "",
        "## Scenario asymmetry",
        "",
        f"- Expected return: {scenario['expected_return_pct']:.1f}%",
        f"- Bear downside reference: {scenario['bear_downside_reference_pct']:.1f}%",
        f"- Expected-return/downside ratio: {scenario['asymmetry_ratio']:.2f}",
    ])

    if result.get("active_hard_flags"):
        lines.extend(["", "## Active hard flags"])
        for message in result.get("hard_flag_messages", []):
            lines.append(f"- {message}")

    if result.get("warnings"):
        lines.extend(["", "## Validation warnings"])
        for warning in result["warnings"]:
            lines.append(f"- {warning}")

    lines.append("")
    return "\n".join(lines)


def load_json(path: str) -> Dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Input must be a JSON object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Opportunity JSON file or '-' for stdin")
    parser.add_argument("--template", action="store_true", help="Print an input template")
    parser.add_argument("--format", choices=("json", "md", "both"), default="json")
    args = parser.parse_args()

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return
    if not args.input:
        parser.error("input is required unless --template is used")

    try:
        result = score_payload(load_json(args.input))
    except ValueError as exc:
        raise SystemExit(f"Validation error: {exc}") from exc

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.format == "md":
        print(to_markdown(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("\n---\n")
        print(to_markdown(result))


if __name__ == "__main__":
    main()
