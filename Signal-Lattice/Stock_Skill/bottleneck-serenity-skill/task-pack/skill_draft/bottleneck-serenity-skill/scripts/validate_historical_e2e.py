#!/usr/bin/env python3
"""Fail-closed validation for the immutable Historical E2E case."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"
SKILL_VERSION = "0.0.0.1"
CUTOFF = "2024-12-31"
CASE_ID = "historical-ai-data-center-power-transformers-20241231"
DECISION_LABEL = "BOTTLENECK_NOT_EQUITY"
EXPECTED_FILES = {
    "decision.json",
    "evidence.json",
    "frozen_input.json",
    "memo.md",
    "opportunity.json",
    "portfolio.json",
    "rubric.json",
}
EXPECTED_ROLES = [
    "owner",
    "unlocker",
    "substitute",
    "tollbooth",
    "absorber",
    "public_proxy",
]
EXPECTED_ARTIFACTS = [
    "evidence.json",
    "opportunity.json",
    "portfolio.json",
    "decision.json",
    "memo.md",
    "rubric.json",
]
EXPECTED_CLAIMS = [f"C-{number:03d}" for number in range(1, 15)]
EXPECTED_HEADINGS = [
    "## 1. Decision",
    "## 2. Funded demand",
    "## 3. System map",
    "## 4. Constraint proof",
    "## 5. Security map",
    "## 6. Equity capture",
    "## 7. Three clocks",
    "## 8. Valuation",
    "## 9. Catalysts",
    "## 10. Red team",
    "## 11. Kill switches",
    "## 12. Portfolio fit",
    "## 13. Open questions",
    "## 14. Sources",
]
EXPECTED_RUBRIC_CATEGORIES = [
    "Activation",
    "As-of discipline",
    "Roles before tickers",
    "Evidence",
    "Constraint clocks",
    "Rent capture",
    "Expectations/valuation",
    "Red team",
    "Portfolio fit",
    "Output contract",
    "Efficiency",
    "Safety",
]
EXPECTED_GATES = {
    "constraint_reality": "PASS",
    "scarcity_duration": "PASS_WITH_RANGE",
    "equity_rent_capture": "FAIL",
    "expectation_gap": "UNKNOWN",
}
KNOWN_DECISION_LABELS = {
    "AVOID",
    "BOTTLENECK_NOT_EQUITY",
    "BROKEN",
    "CANDIDATE",
    "RESEARCH_PRIORITY",
    "WATCH_EVIDENCE",
    "WATCH_PRICED",
}
PROHIBITED_OUTCOME_KEYS = {
    "actual_return",
    "evaluated_after_cutoff",
    "observed_outcome",
    "outcome",
    "post_cutoff_return",
    "realized_return",
    "retrieved_at",
}
CLAIM_ID = re.compile(r"^C-[0-9]{3}$")
HTTPS_URL = re.compile(r"^https://[^/\s]+(?:/[^\s]*)?$")


class HistoricalE2EError(RuntimeError):
    """An immutable Historical E2E invariant failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HistoricalE2EError(message)


def _canonical_date(value: Any, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a canonical YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HistoricalE2EError(
            f"{label} must be a canonical YYYY-MM-DD string"
        ) from exc
    _require(parsed.isoformat() == value, f"{label} must be canonical YYYY-MM-DD")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HistoricalE2EError(f"{path.name}: invalid UTF-8 JSON: {exc}") from exc
    _require(isinstance(payload, dict), f"{path.name}: root must be an object")
    return payload


def _load_sibling(skill_root: Path, stem: str) -> ModuleType:
    path = skill_root / "scripts" / f"{stem}.py"
    _require(path.is_file() and not path.is_symlink(), f"missing runtime dependency: {path}")
    spec = importlib.util.spec_from_file_location(f"_bss_historical_{stem}", path)
    _require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_envelope(name: str, payload: Mapping[str, Any]) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "as_of": CUTOFF,
        "source_cutoff": CUTOFF,
        "previous_version": None,
    }
    for field, value in expected.items():
        _require(
            field in payload,
            f"{name}: missing immutable envelope field {field}",
        )
        _require(
            payload[field] == value,
            f"{name}: {field} must equal {value!r}",
        )
    _canonical_date(payload["as_of"], f"{name}.as_of")
    _canonical_date(payload["source_cutoff"], f"{name}.source_cutoff")


def _walk_keys(value: Any, location: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key)
            yield location, name
            yield from _walk_keys(child, f"{location}.{name}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_keys(child, f"{location}[{index}]")


def _claim_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for child in value.values():
            references.update(_claim_references(child))
    elif isinstance(value, list):
        for child in value:
            references.update(_claim_references(child))
    elif isinstance(value, str) and CLAIM_ID.fullmatch(value):
        references.add(value)
    return references


def _validate_input(payload: Mapping[str, Any]) -> None:
    _require(payload.get("case_id") == CASE_ID, "frozen_input.json: wrong case_id")
    _require(payload.get("mode") == "scan", "frozen_input.json: mode must be scan")
    _require(
        payload.get("required_roles") == EXPECTED_ROLES,
        "frozen_input.json: required_roles must contain all six frozen roles in order",
    )
    _require(
        payload.get("required_artifacts") == EXPECTED_ARTIFACTS,
        "frozen_input.json: required_artifacts changed",
    )
    _require(
        payload.get("execution_boundary")
        == ["research only", "no leverage", "no automatic trading"],
        "frozen_input.json: execution boundary changed",
    )
    query = payload.get("query")
    _require(isinstance(query, str) and query.strip(), "frozen_input.json: query is required")
    lowered = query.lower()
    for marker in ("2024-12-31", "ai", "transformer"):
        _require(marker in lowered, f"frozen_input.json: query missing {marker!r}")
    combined = " ".join(
        str(payload.get(field, "")) for field in ("query", "decision_supported")
    )
    leaked = sorted(label for label in KNOWN_DECISION_LABELS if label in combined)
    _require(
        not leaked,
        f"frozen_input.json: expected decision label leaked into frozen input: {leaked}",
    )
    _require(
        payload.get("risk_constraints", {}).get("leverage_allowed") is False,
        "frozen_input.json: leverage must be disabled",
    )
    _require(
        payload.get("risk_constraints", {}).get("derivatives_allowed") is False,
        "frozen_input.json: derivatives must be disabled",
    )
    _require(
        payload.get("risk_constraints", {}).get("automatic_trading_allowed") is False,
        "frozen_input.json: automatic trading must be disabled",
    )


def _validate_evidence(
    payload: Mapping[str, Any],
    evidence_module: ModuleType,
) -> tuple[dict[str, Any], int, str]:
    try:
        result = evidence_module.validate_ledger(payload)
    except ValueError as exc:
        raise HistoricalE2EError(f"evidence.json: validator rejected ledger: {exc}") from exc
    _require(result.get("valid") is True, f"evidence.json: {result.get('errors')}")
    _require(result.get("warnings") == [], f"evidence.json: warnings are fatal: {result.get('warnings')}")

    claims = payload.get("claims")
    _require(isinstance(claims, list), "evidence.json: claims must be an array")
    observed_ids = [claim.get("id") for claim in claims if isinstance(claim, Mapping)]
    _require(observed_ids == EXPECTED_CLAIMS, "evidence.json: frozen claim IDs or order changed")
    known_ids = set(observed_ids)
    index_by_id = {claim_id: index for index, claim_id in enumerate(observed_ids)}
    types = {str(claim.get("claim_type")) for claim in claims}
    _require(
        {"fact", "inference", "assumption", "forecast"} <= types,
        "evidence.json: required claim-type coverage is incomplete",
    )
    _require(
        any(
            claim.get("claim_type") == "inference"
            and claim.get("critical") is True
            and claim.get("status") == "open"
            for claim in claims
        ),
        "evidence.json: unresolved critical inference is required",
    )

    source_count = 0
    latest_source_date = ""
    for claim_index, claim in enumerate(claims):
        _require(isinstance(claim, Mapping), f"evidence.json: claims[{claim_index}] must be an object")
        claim_id = str(claim.get("id"))
        sources = claim.get("sources")
        _require(isinstance(sources, list), f"evidence.json: {claim_id}.sources must be an array")
        if claim.get("claim_type") == "fact":
            _require(sources, f"evidence.json: fact {claim_id} has no source")
        for source_index, source in enumerate(sources):
            _require(
                isinstance(source, Mapping),
                f"evidence.json: {claim_id}.sources[{source_index}] must be an object",
            )
            source_date = _canonical_date(
                source.get("date"),
                f"evidence.json:{claim_id}.sources[{source_index}].date",
            )
            _require(
                source_date <= CUTOFF,
                f"evidence.json: source date {source_date} is later than source_cutoff {CUTOFF}",
            )
            url = source.get("url")
            _require(
                isinstance(url, str)
                and HTTPS_URL.fullmatch(url) is not None,
                f"evidence.json: {claim_id}.sources[{source_index}].url must be a valid HTTPS URL",
            )
            _require(
                isinstance(source.get("publisher"), str)
                and bool(source["publisher"].strip()),
                f"evidence.json: {claim_id}.sources[{source_index}].publisher is required",
            )
            source_count += 1
            latest_source_date = max(latest_source_date, source_date)

        if claim.get("claim_type") == "inference":
            dependencies = claim.get("depends_on")
            _require(
                isinstance(dependencies, list) and dependencies,
                f"evidence.json: inference {claim_id} must declare depends_on",
            )
            _require(
                len(dependencies) == len(set(dependencies)),
                f"evidence.json: inference {claim_id} has duplicate dependencies",
            )
            for dependency in dependencies:
                _require(
                    dependency in known_ids,
                    f"evidence.json: inference {claim_id} has unknown dependency {dependency!r}",
                )
                _require(
                    index_by_id[dependency] < index_by_id[claim_id],
                    f"evidence.json: dependency {dependency} must precede inference {claim_id}",
                )

    _require(source_count == 12, "evidence.json: frozen source count must equal 12")
    _require(
        latest_source_date == "2024-12-20",
        "evidence.json: latest frozen source date changed",
    )
    return result, source_count, latest_source_date


def _validate_opportunity(
    payload: Mapping[str, Any],
    score_module: ModuleType,
) -> dict[str, Any]:
    try:
        result = score_module.score_payload(payload)
    except ValueError as exc:
        raise HistoricalE2EError(f"opportunity.json: scoring failed: {exc}") from exc
    _require(result.get("warnings") == [], f"opportunity.json: scoring warnings are fatal: {result.get('warnings')}")
    _require(
        result.get("candidate", {}).get("ticker") == "GEV",
        "opportunity.json: frozen candidate must be GEV",
    )
    _require(
        result.get("decision", {}).get("label") == DECISION_LABEL,
        "opportunity.json: computed decision label changed",
    )
    _require(
        result.get("decision", {}).get("hard_gates_passed") is False,
        "opportunity.json: hard gates must fail",
    )
    _require(
        result.get("active_hard_flags") == ["no_material_revenue_bridge"],
        "opportunity.json: active hard flags changed",
    )
    equity_bridge = result.get("equity_bridge")
    _require(
        isinstance(equity_bridge, Mapping)
        and equity_bridge.get("complete") is False
        and equity_bridge.get("fully_diluted_shares") == 275.5
        and equity_bridge.get("per_share_fcf") is None
        and len(equity_bridge.get("unverified_critical_multipliers", [])) == 5,
        "opportunity.json: incomplete equity bridge is not fail-closed",
    )
    _require(
        math.isclose(float(result.get("final_score", -1)), 55.215, abs_tol=1e-9),
        "opportunity.json: computed final score must equal 55.215",
    )
    _require(
        result.get("dimension_scores")
        == {
            "constraint": 78.0,
            "capture": 58.0,
            "mispricing": 34.0,
            "evidence": 83.0,
            "investability": 70.0,
        },
        "opportunity.json: frozen dimension scores changed",
    )
    _require(
        result.get("scenario_metrics", {}).get("expected_return_pct") == 4.5,
        "opportunity.json: expected-return sensitivity changed",
    )
    kill_switches = result.get("kill_switches")
    _require(
        isinstance(kill_switches, list) and len(kill_switches) == 3,
        "opportunity.json: exactly three kill switches are required",
    )
    _require(
        all(item.get("triggered") is False for item in kill_switches if isinstance(item, Mapping)),
        "opportunity.json: a historical kill switch cannot be marked triggered",
    )
    return result


def _validate_portfolio(
    payload: Mapping[str, Any],
    portfolio_module: ModuleType,
) -> dict[str, Any]:
    try:
        result = portfolio_module.analyze_portfolio(payload)
    except ValueError as exc:
        raise HistoricalE2EError(f"portfolio.json: analysis failed: {exc}") from exc
    _require(result.get("valid") is True, f"portfolio.json: {result.get('errors')}")
    _require(result.get("errors") == [], f"portfolio.json: {result.get('errors')}")
    _require(result.get("total_weight") == 0.1, "portfolio.json: frozen research weight changed")
    positions = payload.get("positions")
    _require(
        isinstance(positions, list)
        and [item.get("ticker") for item in positions if isinstance(item, Mapping)]
        == ["GEV", "ETN"],
        "portfolio.json: frozen comparison set must be GEV then ETN",
    )
    pairs = result.get("pair_overlaps")
    _require(
        pairs
        == [
            {
                "left": "GEV",
                "right": "ETN",
                "jaccard": 0.857,
                "shared": [
                    "architectures:utility-grid-to-data-center",
                    "constraints:power-transformer-capacity",
                    "constraints:qualified-electrical-equipment",
                    "customers:large-load-developers",
                    "customers:utilities",
                    "drivers:ai-data-center-capex",
                    "drivers:grid-electrification",
                    "regions:global",
                    "regions:north-america",
                    "risk_factors:capital-cycle-response",
                    "risk_factors:project-timing",
                    "risk_factors:theme-valuation",
                ],
            }
        ],
        "portfolio.json: frozen GEV|ETN causal overlap changed",
    )
    _require(
        any(
            alert.get("type") == "near_duplicate_pairs"
            and alert.get("count") == 1
            for alert in result.get("alerts", [])
            if isinstance(alert, Mapping)
        ),
        "portfolio.json: near-duplicate causal-cluster alert is required",
    )
    return result


def _validate_sensitivity(decision: Mapping[str, Any]) -> None:
    rent_capture = decision.get("rent_capture")
    _require(isinstance(rent_capture, Mapping), "decision.json: rent_capture is required")
    _require(
        rent_capture.get("hard_flag") == "no_material_revenue_bridge",
        "decision.json: rent-capture hard flag changed",
    )
    bridge = rent_capture.get("bridge")
    _require(
        isinstance(bridge, list)
        and len(bridge) >= 10
        and bridge[-1] == "fully diluted per-share free cash flow",
        "decision.json: per-share rent bridge is incomplete",
    )
    _require(
        isinstance(rent_capture.get("unverified_multipliers"), list)
        and len(rent_capture["unverified_multipliers"]) >= 5,
        "decision.json: unverified rent multipliers must remain explicit",
    )
    sensitivity = rent_capture.get("sensitivity_only")
    _require(isinstance(sensitivity, Mapping), "decision.json: sensitivity_only is required")
    shares = float(sensitivity.get("diluted_shares_millions_assumption", 0))
    _require(shares > 0, "decision.json: diluted share assumption must be positive")
    for scenario in ("bear", "base", "bull"):
        values = sensitivity.get(scenario)
        _require(isinstance(values, Mapping), f"decision.json: missing {scenario} FCF sensitivity")
        revenue = float(values["incremental_revenue_millions"])
        margin = float(values["gross_margin_pct"]) / 100
        opex = float(values["incremental_opex_millions"])
        tax = float(values["tax_rate_pct"]) / 100
        reinvestment = float(values["capex_and_working_capital_millions"])
        calculated_fcf = round((revenue * margin - opex) * (1 - tax) - reinvestment, 2)
        _require(
            math.isclose(calculated_fcf, float(values["incremental_fcf_millions"]), abs_tol=1e-9),
            f"decision.json: {scenario} incremental FCF arithmetic changed",
        )
        _require(
            math.isclose(
                round(calculated_fcf / shares, 2),
                float(values["incremental_fcf_per_share"]),
                abs_tol=1e-9,
            ),
            f"decision.json: {scenario} per-share FCF arithmetic changed",
        )


def _validate_decision(
    payload: Mapping[str, Any],
    score_result: Mapping[str, Any],
    portfolio_result: Mapping[str, Any],
    claim_ids: set[str],
) -> None:
    _require(payload.get("case_id") == CASE_ID, "decision.json: wrong case_id")
    _require(payload.get("mode") == "scan", "decision.json: mode must be scan")
    computed = payload.get("decision")
    _require(isinstance(computed, Mapping), "decision.json: decision object is required")
    _require(computed.get("label") == DECISION_LABEL, "decision.json: wrong decision label")
    _require(
        computed.get("hard_gates_passed") is False,
        "decision.json: hard_gates_passed must be false",
    )
    _require(
        computed.get("blocking_gate") == "equity_rent_capture",
        "decision.json: blocking gate must remain equity_rent_capture",
    )
    _require(
        math.isclose(
            float(computed.get("final_score", -1)),
            float(score_result["final_score"]),
            abs_tol=1e-9,
        ),
        "decision.json: final score does not match score engine",
    )
    _require(
        payload.get("execution_boundary")
        == ["research only", "no leverage", "no automatic trading"],
        "decision.json: execution boundary changed",
    )

    system_map = payload.get("system_map")
    _require(isinstance(system_map, Mapping), "decision.json: system_map is required")
    _require(
        isinstance(system_map.get("nodes"), list) and len(system_map["nodes"]) == 6,
        "decision.json: system_map must contain six frozen nodes",
    )
    _require(
        isinstance(system_map.get("edges"), list) and len(system_map["edges"]) == 5,
        "decision.json: system_map must contain five frozen edges",
    )
    _require(
        isinstance(system_map.get("category_control"), str)
        and bool(system_map["category_control"].strip()),
        "decision.json: transformer category control is required",
    )

    roles = payload.get("role_screening")
    _require(
        isinstance(roles, list)
        and [item.get("role") for item in roles if isinstance(item, Mapping)]
        == EXPECTED_ROLES,
        "decision.json: six-role screening changed",
    )
    gates = payload.get("non_compensating_gates")
    _require(isinstance(gates, list) and len(gates) == 4, "decision.json: four gates are required")
    observed_gates = {
        item.get("gate"): item.get("verdict")
        for item in gates
        if isinstance(item, Mapping)
    }
    _require(observed_gates == EXPECTED_GATES, "decision.json: non-compensating gate verdicts changed")

    clocks = payload.get("clocks")
    _require(isinstance(clocks, Mapping), "decision.json: clocks are required")
    for field in (
        "scarcity_p10_months",
        "scarcity_p50_months",
        "scarcity_p90_months",
        "monetization_lag_months",
        "market_discovery_months",
        "monetizable_runway_months",
    ):
        _require(
            math.isclose(float(clocks.get(field, -1)), float(score_result["clocks"][field]), abs_tol=1e-9),
            f"decision.json: {field} does not match score engine",
        )

    _validate_sensitivity(payload)
    valuation = payload.get("valuation")
    _require(isinstance(valuation, Mapping), "decision.json: valuation is required")
    _require(
        valuation.get("reference_anchor_type") == "assumption_not_fact",
        "decision.json: reference anchor must remain an explicit assumption",
    )
    _require(
        valuation.get("expected_return_pct")
        == score_result["scenario_metrics"]["expected_return_pct"],
        "decision.json: valuation expected return does not match score engine",
    )
    anchor = float(valuation.get("reference_anchor_usd", 0))
    shares = float(valuation.get("assumed_diluted_shares_millions", 0))
    _require(
        math.isclose(anchor * shares / 1000, float(valuation.get("assumed_equity_value_usd_billions", -1)), abs_tol=1e-9),
        "decision.json: assumed equity value arithmetic changed",
    )
    for scenario in ("bear", "base", "bull"):
        values = valuation.get("scenarios", {}).get(scenario)
        _require(isinstance(values, Mapping), f"decision.json: missing valuation scenario {scenario}")
        expected_endpoint = round(anchor * (1 + float(values["return_pct"]) / 100) / 10) * 10
        _require(
            values.get("endpoint_usd_rounded") == expected_endpoint,
            f"decision.json: {scenario} rounded endpoint arithmetic changed",
        )

    _require(
        isinstance(payload.get("strongest_countercase"), Mapping)
        and bool(str(payload["strongest_countercase"].get("case", "")).strip()),
        "decision.json: strongest countercase is required",
    )
    _require(
        isinstance(payload.get("documented_negative_search"), list)
        and len(payload["documented_negative_search"]) >= 6,
        "decision.json: documented negative search is incomplete",
    )
    kill_switches = payload.get("kill_switches")
    _require(
        isinstance(kill_switches, list) and len(kill_switches) == 3,
        "decision.json: exactly three kill switches are required",
    )
    _require(
        [item.get("review_date") for item in kill_switches if isinstance(item, Mapping)]
        == [
            item.get("review_date")
            for item in score_result["kill_switches"]
            if isinstance(item, Mapping)
        ],
        "decision.json: kill-switch review dates do not match opportunity.json",
    )

    portfolio_fit = payload.get("portfolio_fit")
    _require(isinstance(portfolio_fit, Mapping), "decision.json: portfolio_fit is required")
    _require(
        portfolio_fit.get("comparison_set") == ["GEV", "ETN"],
        "decision.json: portfolio comparison set changed",
    )
    _require(
        portfolio_fit.get("pairwise_overlap") == {"GEV|ETN": 0.857}
        and portfolio_result["pair_overlaps"][0]["jaccard"] == 0.857,
        "decision.json: portfolio overlap does not match analyzer",
    )
    _require(
        payload.get("artifacts")
        == {
            "input_file": "frozen_input.json",
            "evidence_file": "evidence.json",
            "opportunity_file": "opportunity.json",
            "portfolio_file": "portfolio.json",
            "memo_file": "memo.md",
            "rubric_file": "rubric.json",
        },
        "decision.json: artifact links changed",
    )
    _require(
        payload.get("historical_integrity")
        == {
            "fact_source_dates_lte_cutoff": True,
            "post_cutoff_outcomes_used": False,
            "expected_answer_in_frozen_input": False,
            "immutable_first_snapshot": True,
        },
        "decision.json: historical-integrity declaration changed",
    )
    references = _claim_references(payload)
    _require(
        references <= claim_ids,
        f"decision.json: unknown claim references {sorted(references - claim_ids)}",
    )


def _validate_memo(
    text: str,
    source_urls: set[str],
    entity_payloads: Iterable[Any],
    presentation_module: ModuleType,
) -> None:
    headings = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    _require(headings == EXPECTED_HEADINGS, "memo.md: required section headings or order changed")
    _, separator, _ = text.partition("## 5. Security map")
    _require(separator != "", "memo.md: Security map boundary is required")
    violations = presentation_module.find_role_neutral_violations(
        text,
        "## 5. Security map",
        entity_payloads,
    )
    _require(
        not violations,
        "memo.md: issuer/company/ticker appears before Security map: "
        + ", ".join(violations),
    )
    for marker in (
        DECISION_LABEL,
        "2024-12-31",
        "research only",
        "no leverage",
        "no automatic trading",
        "documented negative search",
    ):
        _require(marker.lower() in text.lower(), f"memo.md: missing required marker {marker!r}")
    missing_urls = sorted(url for url in source_urls if url not in text)
    _require(not missing_urls, f"memo.md: source URLs missing from memo: {missing_urls}")
    _require(
        "no post-cutoff outcome" in text.lower(),
        "memo.md: immutable no-post-cutoff-outcome declaration is required",
    )


def _validate_rubric(payload: Mapping[str, Any]) -> None:
    _require(payload.get("case_id") == CASE_ID, "rubric.json: wrong case_id")
    scores = payload.get("scores")
    _require(isinstance(scores, list), "rubric.json: scores must be an array")
    _require(
        [item.get("category") for item in scores if isinstance(item, Mapping)]
        == EXPECTED_RUBRIC_CATEGORIES,
        "rubric.json: categories or order changed",
    )
    total = 0
    for index, item in enumerate(scores):
        _require(isinstance(item, Mapping), f"rubric.json: scores[{index}] must be an object")
        score = item.get("score")
        _require(
            isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 2,
            f"rubric.json: scores[{index}].score must be integer 0..2",
        )
        total += score
        if item.get("must_pass") is True:
            _require(score == 2, f"rubric.json: must-pass category {item.get('category')} is below 2")
    _require(total == payload.get("total_score") == 23, "rubric.json: total_score must recompute to 23")
    _require(
        payload.get("maximum_score") == len(scores) * 2 == 24,
        "rubric.json: maximum_score must equal 24",
    )
    _require(payload.get("must_pass_categories_at_two") is True, "rubric.json: must-pass declaration failed")
    _require(payload.get("safety_failure") is False, "rubric.json: safety failure is fatal")
    _require(
        payload.get("deterministic_scripts_and_schemas_valid") is True,
        "rubric.json: deterministic validation declaration failed",
    )
    _require(payload.get("verdict") == "PASS", "rubric.json: verdict must be PASS")


def validate_case(
    case_dir: Path,
    skill_root: Path | None = None,
) -> dict[str, Any]:
    """Validate one immutable Historical E2E directory and return a summary."""

    root = (skill_root or Path(__file__).resolve().parents[1]).resolve()
    case = case_dir if case_dir.is_absolute() else root / case_dir
    case = case.resolve()
    _require(case.is_dir() and not case.is_symlink(), f"historical case directory is missing: {case}")
    entries = list(case.iterdir())
    observed = {path.name for path in entries}
    _require(
        observed == EXPECTED_FILES,
        f"historical case file set mismatch; missing={sorted(EXPECTED_FILES - observed)}; extra={sorted(observed - EXPECTED_FILES)}",
    )
    for path in entries:
        _require(path.is_file() and not path.is_symlink(), f"historical case entry must be a regular file: {path.name}")

    json_names = sorted(EXPECTED_FILES - {"memo.md"})
    payloads = {name: _load_json(case / name) for name in json_names}
    for name, payload in payloads.items():
        _validate_envelope(name, payload)
        prohibited = sorted(
            f"{location}.{key}"
            for location, key in _walk_keys(payload)
            if key in PROHIBITED_OUTCOME_KEYS
        )
        _require(
            not prohibited,
            f"{name}: prohibited post-cutoff outcome key(s): {prohibited}",
        )

    _validate_input(payloads["frozen_input.json"])
    evidence_module = _load_sibling(root, "validate_evidence")
    score_module = _load_sibling(root, "score_opportunity")
    portfolio_module = _load_sibling(root, "analyze_portfolio_clusters")
    presentation_module = _load_sibling(root, "presentation_contract")
    evidence_result, source_count, latest_source_date = _validate_evidence(
        payloads["evidence.json"], evidence_module
    )
    score_result = _validate_opportunity(payloads["opportunity.json"], score_module)
    portfolio_result = _validate_portfolio(payloads["portfolio.json"], portfolio_module)
    claim_ids = {claim["id"] for claim in payloads["evidence.json"]["claims"]}
    _validate_decision(
        payloads["decision.json"],
        score_result,
        portfolio_result,
        claim_ids,
    )
    memo = (case / "memo.md").read_text(encoding="utf-8")
    source_urls = {
        source["url"]
        for claim in payloads["evidence.json"]["claims"]
        for source in claim.get("sources", [])
    }
    _validate_memo(memo, source_urls, payloads.values(), presentation_module)
    _validate_rubric(payloads["rubric.json"])

    decision = payloads["decision.json"]
    return {
        "case_id": CASE_ID,
        "source_cutoff": CUTOFF,
        "claim_count": evidence_result["claim_count"],
        "fact_count": sum(
            claim.get("claim_type") == "fact"
            for claim in payloads["evidence.json"]["claims"]
        ),
        "source_count": source_count,
        "latest_source_date": latest_source_date,
        "all_source_dates_lte_cutoff": True,
        "decision_label": score_result["decision"]["label"],
        "final_score": score_result["final_score"],
        "role_count": len(decision["role_screening"]),
        "system_node_count": len(decision["system_map"]["nodes"]),
        "kill_switch_count": len(decision["kill_switches"]),
        "portfolio_pair_count": len(portfolio_result["pair_overlaps"]),
        "portfolio_jaccard": portfolio_result["pair_overlaps"][0]["jaccard"],
        "rubric_total": payloads["rubric.json"]["total_score"],
        "rubric_maximum": payloads["rubric.json"]["maximum_score"],
        "rubric_verdict": payloads["rubric.json"]["verdict"],
        "post_cutoff_outcomes_used": False,
        "expected_answer_in_input": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "case_dir",
        nargs="?",
        type=Path,
        default=Path("evals/historical_e2e"),
        help="Historical case directory (default: evals/historical_e2e relative to Skill root)",
    )
    args = parser.parse_args()
    try:
        result = validate_case(args.case_dir)
    except (HistoricalE2EError, OSError, UnicodeError) as exc:
        raise SystemExit(f"Historical E2E validation error: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
