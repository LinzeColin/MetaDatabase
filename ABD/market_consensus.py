"""Deterministic source-independence weighted median consensus for ABD S08/P03.

This module consumes frozen synthetic source observations only. It derives a
market-prior consensus from the already fail-closed P02 source clusters; it
does not fetch a market, create a recommendation, access an account, or
submit an order.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from source_independence import SourceIndependenceError, cluster_sources


FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
DECIMAL_PRECISION = 50
INDEPENDENT_IMPLEMENTATION_TOLERANCE = Decimal("0.000000000001")
CONSENSUS_SPACE = "LOGIT"
CONSENSUS_ESTIMATOR = "SOURCE_INDEPENDENCE_WEIGHTED_MEDIAN"
TIE_POLICY = "LOWER_LOGIT_AT_EXACT_HALF_CUMULATIVE_WEIGHT"
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{1,79}")


class MarketConsensusError(ValueError):
    """Raised when no deterministic, independent market consensus is safe."""


def canonical_json_bytes(value: Any) -> bytes:
    """Render canonical JSON for hashes and checked-in frozen artifacts."""

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decimal_text(value: Decimal) -> str:
    """Render a finite Decimal without exponent notation or trailing zeroes."""

    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise MarketConsensusError("%s must be an uppercase stable identifier" % label)
    return value


def _probability(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise MarketConsensusError("%s must be a decimal-string probability" % label)
    try:
        probability = Decimal(value)
    except InvalidOperation as exc:
        raise MarketConsensusError("%s is not decimal" % label) from exc
    if not probability.is_finite() or not _ZERO < probability < _ONE:
        raise MarketConsensusError("%s must be strictly between zero and one" % label)
    return probability


def logit(probability: Decimal) -> Decimal:
    """Return the log-odds of a strictly interior probability."""

    if not probability.is_finite() or not _ZERO < probability < _ONE:
        raise MarketConsensusError("logit requires a finite probability strictly between zero and one")
    return probability.ln() - (_ONE - probability).ln()


def inverse_logit(value: Decimal) -> Decimal:
    """Return the probability corresponding to a finite log-odds value."""

    if not value.is_finite():
        raise MarketConsensusError("logit must be finite")
    return _ONE / (_ONE + (-value).exp())


def weighted_median_logit(contributions: Sequence[Mapping[str, Any]]) -> Decimal:
    """Choose the deterministic lower weighted median in log-odds space."""

    if not contributions:
        raise MarketConsensusError("at least one eligible independent cluster is required")
    ordered: list[tuple[Decimal, Decimal, str]] = []
    total_weight = _ZERO
    for index, contribution in enumerate(contributions):
        if not isinstance(contribution, Mapping):
            raise MarketConsensusError("contributions[%d] must be an object" % index)
        value = contribution.get("logit")
        weight = contribution.get("weight")
        tie_key = contribution.get("tie_key")
        if not isinstance(value, Decimal) or not value.is_finite():
            raise MarketConsensusError("contributions[%d].logit must be a finite Decimal" % index)
        if not isinstance(weight, Decimal) or not weight.is_finite() or weight <= _ZERO:
            raise MarketConsensusError("contributions[%d].weight must be a positive Decimal" % index)
        if not isinstance(tie_key, str):
            raise MarketConsensusError("contributions[%d].tie_key must be text" % index)
        ordered.append((value, weight, tie_key))
        total_weight += weight
    if total_weight <= _ZERO:
        raise MarketConsensusError("effective independent weight must be positive")
    cumulative = _ZERO
    threshold = total_weight / _TWO
    for value, weight, _ in sorted(ordered, key=lambda item: (item[0], item[2])):
        cumulative += weight
        if cumulative >= threshold:
            return value
    raise MarketConsensusError("weighted median could not be resolved")


def _source_probabilities(case: Mapping[str, Any]) -> dict[str, Decimal]:
    raw_sources = case.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise MarketConsensusError("sources must be a non-empty list")
    probabilities: dict[str, Decimal] = {}
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, Mapping):
            raise MarketConsensusError("sources[%d] must be an object" % index)
        source_id = _identifier(raw_source.get("source_id"), label="sources[%d].source_id" % index)
        if source_id in probabilities:
            raise MarketConsensusError("source_id values must be unique")
        probabilities[source_id] = _probability(raw_source.get("probability"), label="sources[%d].probability" % index)
    return probabilities


def calculate_consensus(case: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate one P02-weighted median consensus from frozen observations."""

    if not isinstance(case, Mapping):
        raise MarketConsensusError("consensus case must be an object")
    identifier = _identifier(case.get("id"), label="case.id")
    try:
        source_clusters = cluster_sources(case)
    except SourceIndependenceError as exc:
        raise MarketConsensusError("source independence prerequisite failed: %s" % exc) from exc
    probabilities = _source_probabilities(case)

    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        contributions: list[dict[str, Any]] = []
        for cluster in source_clusters["clusters"]:
            if not isinstance(cluster, Mapping):
                raise MarketConsensusError("source cluster must be an object")
            members = cluster.get("members")
            if not isinstance(members, list):
                raise MarketConsensusError("source cluster members must be a list")
            eligible_members = [member for member in members if isinstance(member, Mapping) and member.get("eligible") is True]
            if not eligible_members:
                continue
            member_probabilities = {
                probabilities.get(member.get("source_id"))
                for member in eligible_members
                if isinstance(member.get("source_id"), str)
            }
            if None in member_probabilities or len(member_probabilities) != 1:
                raise MarketConsensusError("each eligible source cluster must carry one canonical probability")
            probability = next(iter(member_probabilities))
            if not isinstance(probability, Decimal):
                raise MarketConsensusError("cluster probability is unavailable")
            member_weight = sum((Decimal(str(member.get("weight"))) for member in eligible_members), _ZERO)
            cluster_weight = Decimal(str(cluster.get("independent_weight")))
            if member_weight != cluster_weight or cluster_weight <= _ZERO:
                raise MarketConsensusError("source cluster weight cannot be safely reconstructed")
            cluster_id = cluster.get("cluster_id")
            if not isinstance(cluster_id, str):
                raise MarketConsensusError("source cluster id is unavailable")
            contributions.append(
                {
                    "cluster_id": cluster_id,
                    "eligible_member_count": len(eligible_members),
                    "probability": probability,
                    "logit": logit(probability),
                    "weight": cluster_weight,
                    "tie_key": cluster_id,
                }
            )
        if not contributions:
            raise MarketConsensusError("no eligible independent source cluster remains")
        median_logit = weighted_median_logit(contributions)
        selected = [item for item in contributions if item["logit"] == median_logit]
        if not selected:
            raise MarketConsensusError("median logit has no source cluster")
        consensus_probability = selected[0]["probability"]
        restored_probability = inverse_logit(median_logit)
        if abs(restored_probability - consensus_probability) > INDEPENDENT_IMPLEMENTATION_TOLERANCE:
            raise MarketConsensusError("logit round-trip exceeds independent implementation tolerance")
        total_weight = sum((item["weight"] for item in contributions), _ZERO)
        rendered_clusters = [
            {
                "cluster_id": item["cluster_id"],
                "eligible_member_count": item["eligible_member_count"],
                "independent_weight": decimal_text(item["weight"]),
                "probability": decimal_text(item["probability"]),
                "logit": decimal_text(item["logit"]),
            }
            for item in sorted(contributions, key=lambda item: item["cluster_id"])
        ]
        return {
            "id": identifier,
            "consensus_space": CONSENSUS_SPACE,
            "consensus_estimator": CONSENSUS_ESTIMATOR,
            "tie_policy": TIE_POLICY,
            "source_cluster_count": source_clusters["cluster_count"],
            "eligible_independent_cluster_count": len(contributions),
            "effective_independent_weight": decimal_text(total_weight),
            "weighted_median_logit": decimal_text(median_logit),
            "consensus_probability": decimal_text(consensus_probability),
            "consensus_probability_from_logit": decimal_text(restored_probability),
            "clusters": rendered_clusters,
            "decision_boundary": "CONSENSUS_ONLY_NO_ADVICE_OR_ORDER",
        }


def build_report(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical P03 consensus artifact from a frozen fixture."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != INPUT_MODE:
        raise MarketConsensusError("fixture must be frozen synthetic input with no network or account")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise MarketConsensusError("fixture must contain consensus cases")
    rendered_cases = [calculate_consensus(case) for case in cases]
    rendered_cases.sort(key=lambda case: case["id"])
    probabilities = [Decimal(case["consensus_probability"]) for case in rendered_cases]
    return {
        "schema_version": "1.0.0",
        "product_version": "0.0.0.1",
        "contract_id": "AC-S08-P03",
        "stage_id": "S08",
        "phase_id": "P03",
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "fixture_sha256": hashlib.sha256(canonical_json_bytes(dict(fixture))).hexdigest(),
        "source_independence_contract_id": "AC-S08-P02",
        "cases": rendered_cases,
        "summary": {
            "case_count": len(rendered_cases),
            "minimum_consensus_probability": decimal_text(min(probabilities)),
            "maximum_consensus_probability": decimal_text(max(probabilities)),
            "consensus_space": CONSENSUS_SPACE,
            "consensus_estimator": CONSENSUS_ESTIMATOR,
        },
        "external_effect_boundary": {
            "external_network_accessed": False,
            "real_market_or_odds_observed": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        },
    }
