"""EEI relationship publication gate: the single place that decides "上图 or not".

Owner ruling (2026-09-30, 「官方单来源可上图」):

* A relationship backed by an OFFICIAL first-hand source (SEC EDGAR, GLEIF, ...)
  may be published on ONE source, provided the evidence carries an openable
  original-document URL. It is published with ``evidence_tier = "single_official"``
  so every surface can say "单一官方来源" and let the reader open the original.
* Anything NOT backed by an official source keeps the old rule unchanged:
  ≥ 2 independent sources (distinct publishers) AND human review.

"Official" is not decided here by name. It is the tier the source registry
already carries: ``sources.source_tier == 1`` (first-hand issuer / registry:
sec_edgar, gleif) on an ``active`` source. Fixtures are tier 5, IR pages tier 2,
so neither can ever pass as official.

Every publication path (full republish, backlog push, entity/delta push) MUST go
through :func:`evaluate_relationship_gate`; there is deliberately no second copy of
this logic in SQL.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

# sources.source_tier: 1 = first-hand official issuer/registry. This is the
# classification the registry already stores (specs/domain_schema_v0001.sql).
OFFICIAL_SOURCE_TIER_MAX = 1

# Non-official rule (unchanged from the original publication policy).
NON_OFFICIAL_MIN_INDEPENDENT_SOURCES = 2

TIER_SINGLE_OFFICIAL = "single_official"
TIER_MULTI_SOURCE = "multi_source"

REASON_OFFICIAL_SINGLE = "official_single_source"
REASON_MULTI_SOURCE = "independent_sources_reviewed"
REASON_NO_SUPPORTING_EVIDENCE = "no_supporting_evidence"
REASON_OFFICIAL_MISSING_URL = "official_source_missing_url"
REASON_NON_OFFICIAL_NEEDS_TWO = "non_official_needs_2_independent_sources"
REASON_NON_OFFICIAL_NEEDS_REVIEW = "non_official_needs_human_review"


@dataclass(frozen=True)
class EvidenceFact:
    """One evidence row plus the registry facts about its source."""

    source_id: str
    source_tier: int
    source_active: bool
    role: str
    url: str | None
    publisher: str | None = None
    source_code: str | None = None


@dataclass(frozen=True)
class GateDecision:
    publishable: bool
    evidence_tier: str | None
    reason: str
    supporting_source_count: int
    official_source_count: int

    def as_source_threshold_policy(self) -> dict[str, Any]:
        """Qualifier block the cloud score explanation already understands."""
        if self.evidence_tier == TIER_SINGLE_OFFICIAL:
            return {
                "minimum_independent_sources": 1,
                "independent_source_count": self.supporting_source_count,
                "policy": "official_single_source",
            }
        return {
            "minimum_independent_sources": NON_OFFICIAL_MIN_INDEPENDENT_SOURCES,
            "independent_source_count": self.supporting_source_count,
            "policy": "independent_sources_and_review",
        }


def is_openable_url(url: str | None) -> bool:
    """True when the URL is an absolute http(s) link a reader could open."""
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _independence_key(fact: EvidenceFact) -> str:
    # Independence = distinct publisher (same rule as cross_verify_relationship_
    # candidates); fall back to the registry source when a publisher is unknown.
    publisher = (fact.publisher or "").strip().lower()
    return f"publisher:{publisher}" if publisher else f"source:{fact.source_id}"


def is_official(fact: EvidenceFact) -> bool:
    return bool(fact.source_active) and int(fact.source_tier) <= OFFICIAL_SOURCE_TIER_MAX


def evaluate_relationship_gate(
    evidence: Iterable[EvidenceFact],
    *,
    human_reviewed: bool = False,
    review_override: bool = False,
) -> GateDecision:
    """Decide whether a relationship may go on the public graph, and how to label it.

    ``human_reviewed`` is True only for relationships that came through the signed
    review pipeline (derivation rule ``reviewed_relationship_fact_publication``).
    ``review_override`` mirrors ``source_threshold_policy.met_by_review_override``
    that pipeline may record for a reviewed fact.
    """
    supporting = [fact for fact in evidence if fact.role == "supports"]
    independent = {_independence_key(fact) for fact in supporting if is_openable_url(fact.url)}
    official_openable = [
        fact for fact in supporting if is_official(fact) and is_openable_url(fact.url)
    ]
    official_sources = {fact.source_id for fact in official_openable}

    if not supporting:
        return GateDecision(False, None, REASON_NO_SUPPORTING_EVIDENCE, 0, 0)

    if official_openable:
        tier = TIER_SINGLE_OFFICIAL if len(independent) <= 1 else TIER_MULTI_SOURCE
        reason = REASON_OFFICIAL_SINGLE if tier == TIER_SINGLE_OFFICIAL else REASON_MULTI_SOURCE
        return GateDecision(True, tier, reason, len(independent), len(official_sources))

    if any(is_official(fact) for fact in supporting):
        # Official source, but nothing the reader can open: not publishable.
        return GateDecision(False, None, REASON_OFFICIAL_MISSING_URL, len(independent), 0)

    # Non-official: the original rule, unchanged.
    if not human_reviewed:
        return GateDecision(False, None, REASON_NON_OFFICIAL_NEEDS_REVIEW, len(independent), 0)
    if len(independent) < NON_OFFICIAL_MIN_INDEPENDENT_SOURCES and not review_override:
        return GateDecision(False, None, REASON_NON_OFFICIAL_NEEDS_TWO, len(independent), 0)
    if not independent:
        return GateDecision(False, None, REASON_NO_SUPPORTING_EVIDENCE, 0, 0)
    return GateDecision(True, TIER_MULTI_SOURCE, REASON_MULTI_SOURCE, len(independent), 0)


def evidence_facts_from_rows(rows: Iterable[dict[str, Any]]) -> list[EvidenceFact]:
    """Adapt the JSON evidence aggregate the publisher SQL returns."""
    facts: list[EvidenceFact] = []
    for row in rows:
        facts.append(
            EvidenceFact(
                source_id=str(row["source_id"]),
                source_tier=int(row["source_tier"]),
                source_active=bool(row["source_active"]),
                role=str(row["role"]),
                url=row.get("url"),
                publisher=row.get("publisher"),
                source_code=row.get("source_code"),
            )
        )
    return facts
