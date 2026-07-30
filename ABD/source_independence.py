"""Deterministic, fail-closed source-independence clustering for ABD S08/P02.

This module consumes only frozen synthetic source metadata.  It never fetches
prices or other data, accesses an account, creates advice, or submits orders.
Its sole purpose is to ensure copied or related sources share one independent
evidence weight rather than being counted repeatedly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


FIXED_CLOCK = "2026-07-30T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
_ZERO = Decimal("0")
_ONE = Decimal("1")
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{1,79}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTRACT_STATUSES = {"VERIFIED", "UNVERIFIED", "BLOCKED", "EXPIRED"}


class SourceIndependenceError(ValueError):
    """Raised when source provenance cannot safely prove a cluster boundary."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise SourceIndependenceError("%s must be an uppercase stable identifier" % label)
    return value


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SourceIndependenceError("%s must be a lowercase SHA-256 hex digest" % label)
    return value


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise SourceIndependenceError("%s must be an ISO-8601 timestamp" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SourceIndependenceError("%s is not ISO-8601" % label) from exc
    if parsed.tzinfo is None:
        raise SourceIndependenceError("%s must include an explicit timezone" % label)
    return parsed


def _nonnegative_integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SourceIndependenceError("%s must be a non-negative integer" % label)
    return value


def _source(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise SourceIndependenceError("sources[%d] must be an object" % index)
    copy_of = raw.get("copy_of")
    if copy_of is not None:
        copy_of = _identifier(copy_of, label="sources[%d].copy_of" % index)
    contract_status = raw.get("source_contract_status")
    if contract_status not in _CONTRACT_STATUSES:
        raise SourceIndependenceError("sources[%d].source_contract_status is not recognized" % index)
    return {
        "source_id": _identifier(raw.get("source_id"), label="sources[%d].source_id" % index),
        "operator_id": _identifier(raw.get("operator_id"), label="sources[%d].operator_id" % index),
        "supply_chain_id": _identifier(raw.get("supply_chain_id"), label="sources[%d].supply_chain_id" % index),
        "observed_at": _timestamp(raw.get("observed_at"), label="sources[%d].observed_at" % index),
        "content_sha256": _sha256(raw.get("content_sha256"), label="sources[%d].content_sha256" % index),
        "source_version_sha256": _sha256(raw.get("source_version_sha256"), label="sources[%d].source_version_sha256" % index),
        "copy_of": copy_of,
        "source_contract_status": contract_status,
    }


class _DisjointSet:
    def __init__(self, identifiers: Sequence[str]) -> None:
        self.parent = {identifier: identifier for identifier in identifiers}

    def find(self, identifier: str) -> str:
        root = self.parent[identifier]
        if root != identifier:
            self.parent[identifier] = self.find(root)
        return self.parent[identifier]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _union_by(records: Mapping[str, Mapping[str, Any]], groups: _DisjointSet, field: str) -> None:
    first_by_value: dict[str, str] = {}
    for source_id in sorted(records):
        value = str(records[source_id][field])
        if value in first_by_value:
            groups.union(source_id, first_by_value[value])
        else:
            first_by_value[value] = source_id


def _assert_acyclic_copy_graph(records: Mapping[str, Mapping[str, Any]]) -> None:
    for source_id in sorted(records):
        visited: set[str] = set()
        cursor = source_id
        while records[cursor]["copy_of"] is not None:
            if cursor in visited:
                raise SourceIndependenceError("copy relationship contains a cycle at %s" % cursor)
            visited.add(cursor)
            parent = records[cursor]["copy_of"]
            if parent not in records:
                raise SourceIndependenceError("copy parent %s is not present" % parent)
            cursor = str(parent)


def cluster_sources(case: Mapping[str, Any]) -> dict[str, Any]:
    """Cluster one frozen source set and allocate at most one weight per cluster."""

    if not isinstance(case, Mapping):
        raise SourceIndependenceError("source case must be an object")
    as_of = _timestamp(case.get("as_of"), label="as_of")
    max_age_seconds = _nonnegative_integer(case.get("max_age_seconds"), label="max_age_seconds")
    raw_sources = case.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise SourceIndependenceError("sources must be a non-empty list")
    normalized = [_source(raw, index=index) for index, raw in enumerate(raw_sources)]
    records = {record["source_id"]: record for record in normalized}
    if len(records) != len(normalized):
        raise SourceIndependenceError("source_id values must be unique")
    _assert_acyclic_copy_graph(records)

    groups = _DisjointSet(sorted(records))
    _union_by(records, groups, "operator_id")
    _union_by(records, groups, "supply_chain_id")
    _union_by(records, groups, "content_sha256")
    for source_id, record in records.items():
        parent = record["copy_of"]
        if parent is None:
            continue
        parent_record = records[str(parent)]
        if record["content_sha256"] != parent_record["content_sha256"]:
            raise SourceIndependenceError("copied source %s has a different content hash" % source_id)
        groups.union(source_id, str(parent))

    clusters_by_root: dict[str, list[str]] = {}
    for source_id in sorted(records):
        clusters_by_root.setdefault(groups.find(source_id), []).append(source_id)

    clusters: list[dict[str, Any]] = []
    source_weights: dict[str, dict[str, Any]] = {}
    for position, members in enumerate(sorted(clusters_by_root.values(), key=lambda values: tuple(values)), start=1):
        eligible_members: list[str] = []
        rendered_members: list[dict[str, Any]] = []
        for source_id in members:
            record = records[source_id]
            age_seconds = int((as_of - record["observed_at"]).total_seconds())
            if age_seconds < 0:
                raise SourceIndependenceError("source %s is observed after as_of" % source_id)
            eligible = record["source_contract_status"] == "VERIFIED" and age_seconds <= max_age_seconds
            if eligible:
                eligible_members.append(source_id)
            rendered_members.append(
                {
                    "source_id": source_id,
                    "age_seconds": age_seconds,
                    "source_contract_status": record["source_contract_status"],
                    "eligible": eligible,
                    "source_version_sha256": record["source_version_sha256"],
                }
            )
        cluster_weight = _ONE if eligible_members else _ZERO
        member_weight = cluster_weight / Decimal(len(eligible_members)) if eligible_members else _ZERO
        for member in rendered_members:
            member["weight"] = decimal_text(member_weight if member["eligible"] else _ZERO)
        operators = {str(records[source_id]["operator_id"]) for source_id in members}
        supply_chains = {str(records[source_id]["supply_chain_id"]) for source_id in members}
        content_hashes = {str(records[source_id]["content_sha256"]) for source_id in members}
        reasons = []
        if len(operators) < len(members):
            reasons.append("SHARED_OPERATOR")
        if len(supply_chains) < len(members):
            reasons.append("SHARED_SUPPLY_CHAIN")
        if any(records[source_id]["copy_of"] is not None for source_id in members):
            reasons.append("DECLARED_COPY_RELATION")
        if len(content_hashes) < len(members):
            reasons.append("MATCHING_CONTENT_FINGERPRINT")
        cluster_id = "CLUSTER_%02d" % position
        cluster = {
            "cluster_id": cluster_id,
            "members": rendered_members,
            "member_count": len(members),
            "eligible_member_count": len(eligible_members),
            "independent_weight": decimal_text(cluster_weight),
            "relation_reasons": reasons or ["UNIQUE_OPERATOR_SUPPLY_CHAIN_AND_CONTENT"],
        }
        clusters.append(cluster)
        for member in rendered_members:
            source_weights[member["source_id"]] = {
                "cluster_id": cluster_id,
                "weight": member["weight"],
                "eligible": member["eligible"],
            }

    effective_count = sum(cluster["independent_weight"] == "1" for cluster in clusters)
    return {
        "input_source_count": len(records),
        "cluster_count": len(clusters),
        "eligible_independent_source_count": effective_count,
        "effective_independent_weight": decimal_text(sum((Decimal(cluster["independent_weight"]) for cluster in clusters), _ZERO)),
        "clusters": clusters,
        "source_weights": source_weights,
        "decision_boundary": "CLUSTERING_ONLY_NO_ADVICE_OR_ORDER",
    }


def build_report(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical source-cluster artifact from frozen synthetic cases."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != INPUT_MODE:
        raise SourceIndependenceError("fixture must be frozen synthetic input with no network or account")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SourceIndependenceError("fixture must contain source cases")
    rendered_cases = []
    for raw_case in cases:
        if not isinstance(raw_case, Mapping):
            raise SourceIndependenceError("fixture case must be an object")
        identifier = _identifier(raw_case.get("id"), label="case.id")
        rendered_cases.append({"id": identifier, **cluster_sources(raw_case)})
    rendered_cases.sort(key=lambda case: case["id"])
    independent_counts = [case["eligible_independent_source_count"] for case in rendered_cases]
    return {
        "schema_version": "1.0.0",
        "product_version": "0.0.0.1",
        "contract_id": "AC-S08-P02",
        "stage_id": "S08",
        "phase_id": "P02",
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "fixture_sha256": hashlib.sha256(canonical_json_bytes(dict(fixture))).hexdigest(),
        "cases": rendered_cases,
        "summary": {
            "case_count": len(rendered_cases),
            "minimum_eligible_independent_source_count": min(independent_counts),
            "maximum_eligible_independent_source_count": max(independent_counts),
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
