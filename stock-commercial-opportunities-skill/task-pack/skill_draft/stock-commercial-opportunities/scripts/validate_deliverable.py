#!/usr/bin/env python3
"""Validate a stock-commercial-opportunity research deliverable.

The validator is deliberately conservative. It checks structure, evidence
relationships, maturity/status gates, public/private boundaries, and common
financial-safety failures. It cannot verify whether a real-world claim is true.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set

REQUIRED_ROOT = {
    "meta",
    "sources",
    "claims",
    "candidates",
    "assumptions",
    "diligence",
    "decision",
}
SOURCE_TYPES = {
    "regulator_exchange",
    "company_filing",
    "company_ir",
    "primary_dataset",
    "market_data",
    "consensus_estimates",
    "transcript",
    "reputable_media",
    "community_social",
    "user_material",
    "internal_research",
    "synthetic",
}
ORIGINS = {"public", "private", "synthetic"}
ACCESS_LEVELS = {
    "opened_fulltext",
    "opened_partial",
    "snippet_only",
    "user_provided",
    "internal_private",
    "synthetic",
}
EVIDENCE_CLASSES = {
    "identity",
    "commercial_mechanism",
    "issuer_exposure",
    "financial_capture",
    "expectations_valuation",
    "catalyst",
    "risk_falsifier",
}
CLAIM_TYPES = {"Fact", "Inference", "Estimate", "Opinion", "Unverified"}
IMPORTANCE_LEVELS = {"core", "supporting", "context"}
MATURITY_CODES = {"E0", "E1", "E2", "E3", "E4", "E5"}
MATURITY_RANK = {code: rank for rank, code in enumerate(sorted(MATURITY_CODES))}
STATUSES = {
    "REJECT",
    "SCREEN_FLAG",
    "WATCHLIST",
    "DILIGENCE_NEXT",
    "ADVANCE_RESEARCH",
    "NO_QUALIFIED_CANDIDATE",
}
SIGNAL_FIELDS = {
    "public_source_families",
    "company_filings",
    "quantified_exposure_metrics",
    "commercial_capture_signals",
    "current_valuation_observations",
    "confirmed_catalysts",
    "thesis_falsifiers",
    "liquidity_checks",
}
PRIMARY_SOURCE_TYPES = {
    "regulator_exchange",
    "company_filing",
    "company_ir",
    "primary_dataset",
}
WEAK_ACCESS = {"snippet_only", "synthetic"}
WEAK_SOURCE_TYPES = {"community_social", "synthetic"}
SECURITY_TYPES = {
    "ordinary_share",
    "preferred_share",
    "adr",
    "gdr",
    "listed_trust",
    "etf",
    "synthetic_fixture",
}
URL_RE = re.compile(r"https?://[^\s\]\[<>\"']+")
SECRET_PATTERNS = {
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "OPENAI_KEY": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GITHUB_TOKEN": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    "AWS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "LOCAL_USER_PATH": re.compile(r"/(?:Users|home)/[^/\s]+/(?:\.codex|Documents|Downloads)(?:/|\b)"),
}
GUARANTEE_RE = re.compile(
    r"保证收益|稳赚|必涨|确定翻倍|无风险收益|guaranteed?\s+(?:return|profit)|risk[- ]free\s+return",
    re.IGNORECASE,
)
PERSONAL_ACTION_RE = re.compile(
    r"(?:建议你|你应该|立即|马上|强烈)(?:在.{0,8})?(?:买入|卖出|持有|满仓|清仓)|"
    r"(?:buy|sell|hold)\s+(?:it\s+)?(?:now|immediately)|position\s+size\s*[:=]\s*[1-9]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def _add(findings: List[Finding], code: str, path: str, message: str, severity: str = "error") -> None:
    findings.append(Finding(severity, code, path, message))


def _object(value: Any, path: str, findings: List[Finding]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _add(findings, "TYPE_OBJECT", path, "Expected an object")
        return {}
    return value


def _array(value: Any, path: str, findings: List[Finding]) -> List[Any]:
    if not isinstance(value, list):
        _add(findings, "TYPE_ARRAY", path, "Expected an array")
        return []
    return value


def _text(value: Any, path: str, findings: List[Finding]) -> str:
    if not isinstance(value, str) or not value.strip():
        _add(findings, "REQUIRED_TEXT", path, "Expected a non-empty string")
        return ""
    return value.strip()


def _bounded_number(value: Any, path: str, findings: List[Finding], low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _add(findings, "TYPE_NUMBER", path, f"Expected a number from {low} to {high}")
        return low
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        _add(findings, "NUMBER_RANGE", path, f"Expected a finite number from {low} to {high}")
        return low
    return number


def _ids(items: Sequence[Any], path: str, findings: List[Finding]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(items):
        item = _object(raw, f"{path}[{index}]", findings)
        item_id = _text(item.get("id"), f"{path}[{index}].id", findings)
        if not item_id:
            continue
        if item_id in result:
            _add(findings, "DUPLICATE_ID", f"{path}[{index}].id", f"Duplicate id {item_id!r}")
        else:
            result[item_id] = item
    return result


def _ref_list(
    value: Any,
    path: str,
    valid: Set[str],
    findings: List[Finding],
    *,
    allow_empty: bool,
) -> List[str]:
    values = _array(value, path, findings)
    if not values and not allow_empty:
        _add(findings, "EMPTY_REFERENCE_LIST", path, "At least one reference is required")
    result: List[str] = []
    for index, raw in enumerate(values):
        ref = _text(raw, f"{path}[{index}]", findings)
        if ref and ref not in valid:
            _add(findings, "UNKNOWN_REFERENCE", f"{path}[{index}]", f"Unknown reference {ref!r}")
        if ref:
            result.append(ref)
    return result


def evidence_maturity(signals: Mapping[str, int]) -> str:
    if signals["company_filings"] >= 1 and signals["quantified_exposure_metrics"] >= 1:
        if signals["commercial_capture_signals"] >= 1:
            if signals["current_valuation_observations"] >= 1 and signals["confirmed_catalysts"] >= 1:
                if signals["thesis_falsifiers"] >= 2 and signals["liquidity_checks"] >= 1:
                    return "E5"
                return "E4"
            return "E3"
        return "E2"
    if signals["public_source_families"] >= 3:
        return "E1"
    return "E0"


def _validate_signals(value: Any, path: str, findings: List[Finding]) -> Dict[str, int]:
    signals = _object(value, path, findings)
    missing = sorted(SIGNAL_FIELDS - set(signals))
    unknown = sorted(set(signals) - SIGNAL_FIELDS)
    if missing:
        _add(findings, "MISSING_SIGNALS", path, f"Missing signals: {', '.join(missing)}")
    if unknown:
        _add(findings, "UNKNOWN_SIGNALS", path, f"Unknown signals: {', '.join(unknown)}")
    result: Dict[str, int] = {}
    for field in SIGNAL_FIELDS:
        value_for_field = signals.get(field, 0)
        if isinstance(value_for_field, bool) or not isinstance(value_for_field, int) or value_for_field < 0:
            _add(findings, "SIGNAL_COUNT", f"{path}.{field}", "Expected a non-negative integer")
            result[field] = 0
        else:
            result[field] = value_for_field
    return result


def _all_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        output: List[str] = []
        for nested in value.values():
            output.extend(_all_strings(nested))
        return output
    if isinstance(value, list):
        output = []
        for nested in value:
            output.extend(_all_strings(nested))
        return output
    return []


def validate(payload: Any) -> List[Finding]:
    findings: List[Finding] = []
    root = _object(payload, "root", findings)
    missing_root = sorted(REQUIRED_ROOT - set(root))
    if missing_root:
        _add(findings, "MISSING_ROOT", "root", f"Missing fields: {', '.join(missing_root)}")

    meta = _object(root.get("meta"), "meta", findings)
    for field in ("domain", "mandate", "universe", "geography", "horizon", "lane", "as_of", "source_posture", "financial_boundary"):
        _text(meta.get(field), f"meta.{field}", findings)
    if meta.get("high_stakes") is not True:
        _add(findings, "HIGH_STAKES_REQUIRED", "meta.high_stakes", "Listed-equity research must be marked high_stakes=true")
    if meta.get("private_data_used") not in {True, False}:
        _add(findings, "PRIVATE_FLAG", "meta.private_data_used", "Expected a boolean")
    if meta.get("personalized_advice") is not False:
        _add(findings, "PERSONAL_ADVICE_BOUNDARY", "meta.personalized_advice", "Must be false")
    if meta.get("automated_execution") is not False:
        _add(findings, "AUTOMATION_BOUNDARY", "meta.automated_execution", "Must be false")
    visibility = meta.get("output_visibility")
    if visibility not in {"private", "public"}:
        _add(findings, "OUTPUT_VISIBILITY", "meta.output_visibility", "Expected private or public")
    boundary = str(meta.get("financial_boundary", "")).lower()
    if "not investment advice" not in boundary and "非投资建议" not in boundary:
        _add(findings, "FINANCIAL_BOUNDARY", "meta.financial_boundary", "State that the output is not investment advice")
    fixture = meta.get("fixture") is True

    source_items = _array(root.get("sources"), "sources", findings)
    sources = _ids(source_items, "sources", findings)
    registered_urls: Set[str] = set()
    for index, raw in enumerate(source_items):
        source = _object(raw, f"sources[{index}]", findings)
        source_id = str(source.get("id", ""))
        _text(source.get("title"), f"sources[{index}].title", findings)
        url = source.get("url")
        locator = source.get("locator")
        if url is not None:
            if not isinstance(url, str) or not url.startswith("https://"):
                _add(findings, "SOURCE_URL", f"sources[{index}].url", "Public URLs must use https:// or be null")
            else:
                registered_urls.add(url.rstrip(".,);"))
        if url is None and not _text(locator, f"sources[{index}].locator", findings):
            pass
        if source.get("source_type") not in SOURCE_TYPES:
            _add(findings, "SOURCE_TYPE", f"sources[{index}].source_type", "Unsupported source_type")
        if source.get("origin") not in ORIGINS:
            _add(findings, "SOURCE_ORIGIN", f"sources[{index}].origin", "Unsupported origin")
        if source.get("access_level") not in ACCESS_LEVELS:
            _add(findings, "SOURCE_ACCESS", f"sources[{index}].access_level", "Unsupported access_level")
        if source.get("evidence_class") not in EVIDENCE_CLASSES:
            _add(findings, "EVIDENCE_CLASS", f"sources[{index}].evidence_class", "Unsupported evidence_class")
        _text(source.get("retrieved_at"), f"sources[{index}].retrieved_at", findings)
        if source.get("redacted") not in {True, False}:
            _add(findings, "REDACTED_FLAG", f"sources[{index}].redacted", "Expected a boolean")
        if visibility == "public" and source.get("origin") == "private" and source.get("redacted") is not True:
            _add(findings, "PRIVATE_NOT_REDACTED", f"sources[{index}]", f"Private source {source_id!r} must be redacted in public output")

    claim_items = _array(root.get("claims"), "claims", findings)
    claims = _ids(claim_items, "claims", findings)
    for index, raw in enumerate(claim_items):
        claim = _object(raw, f"claims[{index}]", findings)
        _text(claim.get("statement"), f"claims[{index}].statement", findings)
        claim_type = claim.get("type")
        if claim_type not in CLAIM_TYPES:
            _add(findings, "CLAIM_TYPE", f"claims[{index}].type", "Unsupported claim type")
        if claim.get("importance") not in IMPORTANCE_LEVELS:
            _add(findings, "CLAIM_IMPORTANCE", f"claims[{index}].importance", "Unsupported importance")
        _text(claim.get("topic"), f"claims[{index}].topic", findings)
        _text(claim.get("period"), f"claims[{index}].period", findings)
        _text(claim.get("freshness"), f"claims[{index}].freshness", findings)
        _bounded_number(claim.get("confidence"), f"claims[{index}].confidence", findings, 0, 100)
        refs = _ref_list(
            claim.get("source_ids"),
            f"claims[{index}].source_ids",
            set(sources),
            findings,
            allow_empty=claim_type in {"Opinion"},
        )
        if not refs and claim_type not in {"Opinion"}:
            _add(findings, "UNSUPPORTED_CLAIM", f"claims[{index}]", "Non-opinion claim has no registered source")
        if claim.get("importance") == "core" and claim_type in {"Fact", "Estimate"} and refs:
            supporting = [sources[ref] for ref in refs if ref in sources]
            if supporting and all(
                item.get("access_level") in WEAK_ACCESS or item.get("source_type") in WEAK_SOURCE_TYPES
                for item in supporting
            ):
                _add(findings, "CORE_WEAK_ACCESS", f"claims[{index}]", "Core fact/estimate is supported only by snippet, social, or synthetic evidence")

    candidate_items = _array(root.get("candidates"), "candidates", findings)
    candidates = _ids(candidate_items, "candidates", findings)
    candidate_signals: Dict[str, Dict[str, int]] = {}
    for index, raw in enumerate(candidate_items):
        candidate = _object(raw, f"candidates[{index}]", findings)
        candidate_id = str(candidate.get("id", ""))
        for field in ("issuer", "ticker", "exchange", "security_type", "share_class", "currency", "as_of", "beneficiary_path", "exposure_proof", "why_not_stronger", "first_rejection"):
            _text(candidate.get(field), f"candidates[{index}].{field}", findings)
        security_type = candidate.get("security_type")
        if security_type not in SECURITY_TYPES:
            _add(findings, "SECURITY_TYPE", f"candidates[{index}].security_type", "Unsupported security type")
        if security_type == "synthetic_fixture" and not fixture:
            _add(findings, "SYNTHETIC_SECURITY", f"candidates[{index}]", "Synthetic securities require meta.fixture=true")
        score = _bounded_number(candidate.get("decision_score"), f"candidates[{index}].decision_score", findings, 0, 100)
        confidence = _bounded_number(candidate.get("evidence_confidence"), f"candidates[{index}].evidence_confidence", findings, 0, 100)
        maturity = candidate.get("maturity_code")
        if maturity not in MATURITY_CODES:
            _add(findings, "MATURITY_CODE", f"candidates[{index}].maturity_code", "Expected E0-E5")
            maturity = "E0"
        status = candidate.get("status")
        if status not in STATUSES - {"NO_QUALIFIED_CANDIDATE"}:
            _add(findings, "CANDIDATE_STATUS", f"candidates[{index}].status", "Unsupported candidate status")
            status = "REJECT"
        signals = _validate_signals(candidate.get("evidence_signals"), f"candidates[{index}].evidence_signals", findings)
        candidate_signals[candidate_id] = signals
        derived = evidence_maturity(signals)
        if maturity != derived:
            _add(findings, "MATURITY_MISMATCH", f"candidates[{index}].maturity_code", f"Declared {maturity}; conservative signals derive {derived}")
        hard_stops = _array(candidate.get("hard_stops"), f"candidates[{index}].hard_stops", findings)
        for stop_index, stop in enumerate(hard_stops):
            _text(stop, f"candidates[{index}].hard_stops[{stop_index}]", findings)
        if hard_stops and status != "REJECT":
            _add(findings, "HARD_STOP_OVERRIDE", f"candidates[{index}].status", "Hard stops require REJECT")
        if maturity in {"E0", "E1"} and status not in {"REJECT", "SCREEN_FLAG"}:
            _add(findings, "EXPOSURE_GATE", f"candidates[{index}].status", "E0/E1 cannot exceed SCREEN_FLAG")
        if status == "WATCHLIST" and MATURITY_RANK[maturity] < MATURITY_RANK["E2"]:
            _add(findings, "WATCHLIST_GATE", f"candidates[{index}].status", "WATCHLIST requires E2+")
        if status == "DILIGENCE_NEXT" and (
            MATURITY_RANK[maturity] < MATURITY_RANK["E2"] or score < 65 or confidence < 55
        ):
            _add(findings, "DILIGENCE_GATE", f"candidates[{index}].status", "DILIGENCE_NEXT requires E2+, score >=65, confidence >=55")
        if status == "ADVANCE_RESEARCH" and (
            MATURITY_RANK[maturity] < MATURITY_RANK["E4"] or score < 75 or confidence < 65
        ):
            _add(findings, "ADVANCE_GATE", f"candidates[{index}].status", "ADVANCE_RESEARCH requires E4+, score >=75, confidence >=65")
        if security_type == "synthetic_fixture" and status not in {"REJECT", "SCREEN_FLAG"}:
            _add(findings, "FIXTURE_OVERCLAIM", f"candidates[{index}].status", "Synthetic fixtures cannot exceed SCREEN_FLAG")
        _ref_list(candidate.get("claim_ids"), f"candidates[{index}].claim_ids", set(claims), findings, allow_empty=False)
        falsifiers = _array(candidate.get("falsifiers"), f"candidates[{index}].falsifiers", findings)
        if not falsifiers:
            _add(findings, "MISSING_FALSIFIER", f"candidates[{index}].falsifiers", "At least one falsifier is required")
        for falsifier_index, falsifier in enumerate(falsifiers):
            _text(falsifier, f"candidates[{index}].falsifiers[{falsifier_index}]", findings)

    assumption_items = _array(root.get("assumptions"), "assumptions", findings)
    assumptions = _ids(assumption_items, "assumptions", findings)
    for index, raw in enumerate(assumption_items):
        assumption = _object(raw, f"assumptions[{index}]", findings)
        candidate_id = _text(assumption.get("candidate_id"), f"assumptions[{index}].candidate_id", findings)
        if candidate_id and candidate_id not in candidates:
            _add(findings, "UNKNOWN_CANDIDATE", f"assumptions[{index}].candidate_id", "Unknown candidate")
        for field in ("category", "statement", "status"):
            _text(assumption.get(field), f"assumptions[{index}].{field}", findings)
        _bounded_number(assumption.get("impact"), f"assumptions[{index}].impact", findings, 0, 5)
        _bounded_number(assumption.get("uncertainty"), f"assumptions[{index}].uncertainty", findings, 0, 5)
        _ref_list(assumption.get("source_ids"), f"assumptions[{index}].source_ids", set(sources), findings, allow_empty=True)

    for index, raw in enumerate(candidate_items):
        candidate = _object(raw, f"candidates[{index}]", findings)
        _ref_list(candidate.get("assumption_ids"), f"candidates[{index}].assumption_ids", set(assumptions), findings, allow_empty=True)

    diligence_items = _array(root.get("diligence"), "diligence", findings)
    _ids(diligence_items, "diligence", findings)
    for index, raw in enumerate(diligence_items):
        item = _object(raw, f"diligence[{index}]", findings)
        candidate_id = _text(item.get("candidate_id"), f"diligence[{index}].candidate_id", findings)
        assumption_id = _text(item.get("assumption_id"), f"diligence[{index}].assumption_id", findings)
        if candidate_id and candidate_id not in candidates:
            _add(findings, "UNKNOWN_CANDIDATE", f"diligence[{index}].candidate_id", "Unknown candidate")
        if assumption_id and assumption_id not in assumptions:
            _add(findings, "UNKNOWN_ASSUMPTION", f"diligence[{index}].assumption_id", "Unknown assumption")
        for field in (
            "critical_claim",
            "required_source_category",
            "method",
            "metric_period_denominator",
            "pass_threshold",
            "fail_threshold",
            "inconclusive_branch",
            "time_data_cap",
            "mnpi_license_boundary",
            "owner",
            "review_date",
        ):
            _text(item.get(field), f"diligence[{index}].{field}", findings)
        status = item.get("status")
        if status not in {"planned", "running", "passed", "failed", "inconclusive", "stopped"}:
            _add(findings, "DILIGENCE_STATUS", f"diligence[{index}].status", "Unsupported diligence status")
        evidence_refs = _ref_list(item.get("evidence_source_ids"), f"diligence[{index}].evidence_source_ids", set(sources), findings, allow_empty=True)
        if status in {"passed", "failed", "inconclusive"} and not evidence_refs:
            _add(findings, "UNRUN_DILIGENCE", f"diligence[{index}]", "A completed diligence result requires evidence_source_ids")

    decision = _object(root.get("decision"), "decision", findings)
    outcome = decision.get("outcome")
    if outcome not in STATUSES:
        _add(findings, "DECISION_OUTCOME", "decision.outcome", "Unsupported decision outcome")
    for field in (
        "reason",
        "why_not_stronger",
        "first_rejection",
        "next_diligence_workflow",
        "owner",
        "review_date",
    ):
        _text(decision.get(field), f"decision.{field}", findings)
    changes = _array(decision.get("evidence_that_changes_rank"), "decision.evidence_that_changes_rank", findings)
    if not changes:
        _add(findings, "MISSING_RANK_CHANGE", "decision.evidence_that_changes_rank", "At least one rank-changing condition is required")
    selected = decision.get("selected_candidate_id")
    if outcome == "NO_QUALIFIED_CANDIDATE":
        if selected is not None:
            _add(findings, "ZERO_RESULT_SELECTION", "decision.selected_candidate_id", "Must be null for NO_QUALIFIED_CANDIDATE")
        if any(item.get("status") in {"DILIGENCE_NEXT", "ADVANCE_RESEARCH"} for item in candidates.values()):
            _add(findings, "ZERO_RESULT_CONFLICT", "decision.outcome", "Qualified candidates conflict with NO_QUALIFIED_CANDIDATE")
    else:
        if not isinstance(selected, str) or selected not in candidates:
            _add(findings, "DECISION_SELECTION", "decision.selected_candidate_id", "Select a registered candidate")
        else:
            candidate = candidates[selected]
            if candidate.get("status") != outcome:
                _add(findings, "DECISION_STATUS_MISMATCH", "decision.outcome", "Outcome must match selected candidate status")
            if decision.get("evidence_maturity") != candidate.get("maturity_code"):
                _add(findings, "DECISION_MATURITY_MISMATCH", "decision.evidence_maturity", "Decision maturity must match selected candidate")

    if meta.get("high_stakes") is True and not any(
        source.get("source_type") in PRIMARY_SOURCE_TYPES and source.get("access_level") in {"opened_fulltext", "opened_partial"}
        for source in sources.values()
    ):
        _add(findings, "HIGH_STAKES_SOURCE", "sources", "High-stakes research requires at least one opened primary/first-party source")
    if visibility == "public" and meta.get("private_data_used") is True:
        _add(findings, "PUBLIC_PRIVATE_DATA", "meta.private_data_used", "Public output cannot contain raw private data")

    all_text = "\n".join(_all_strings(root))
    for code, pattern in SECRET_PATTERNS.items():
        if pattern.search(all_text):
            _add(findings, code, "root", "Possible secret or private local path detected")
    decision_sensitive_text = "\n".join(
        _all_strings(decision)
        + [
            str(candidate.get(field, ""))
            for candidate in candidates.values()
            for field in ("beneficiary_path", "exposure_proof", "why_not_stronger", "first_rejection")
        ]
    )
    if GUARANTEE_RE.search(decision_sensitive_text):
        _add(findings, "GUARANTEE_LANGUAGE", "decision", "Return-guarantee language is prohibited")
    if PERSONAL_ACTION_RE.search(decision_sensitive_text):
        _add(findings, "PERSONAL_ACTION", "decision", "Personal buy/sell/hold or position instruction is prohibited")

    observed_urls = {url.rstrip(".,);") for url in URL_RE.findall(all_text)}
    for url in sorted(observed_urls - registered_urls):
        _add(findings, "UNREGISTERED_URL", "root", f"URL is not present in sources: {url}")
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Deliverable JSON path")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read JSON: {exc}")
        return 2
    findings = validate(payload)
    for finding in findings:
        print(f"{finding.severity.upper()} {finding.code} {finding.path}: {finding.message}")
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    failed = bool(errors) or (args.strict and bool(warnings))
    print(f"{'FAIL' if failed else 'PASS'}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
