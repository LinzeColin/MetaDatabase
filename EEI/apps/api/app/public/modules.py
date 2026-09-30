"""只读查询与响应整形：实体检索、证据、评分解释、各模块概览、变更流。

所有关系读取都经 gate.py（发布门）；整形逻辑与 worker.mjs 同名函数一一对应。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ..domain_repository import SCORING_SERVICE_VERSION, SUPPLY_TYPE_STAGE_MAP, DomainRepository
from ..scoring import CANDIDATE_SOURCE_THRESHOLD_MIN, relationship_score_metrics
from .gate import ENTITY_VISIBLE_SQL, RULES, fetch_one, fetch_published, has_published_edge
from .graph import load_entity
from .stats import LightStats, SurfaceStats, production_context

MAX_SEARCH_TERM = 64


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_entities(conn: psycopg.Connection, query: str, limit: int) -> dict[str, Any]:
    trimmed = query.strip()[:MAX_SEARCH_TERM]
    escaped = escape_like(trimmed)
    # SQL 只做预筛（多取几倍），精确的「是否真有过门的边」逐个走发布门确认。
    candidates = conn.execute(
        f"""
        SELECT e.id, e.canonical_name, e.entity_type::text, e.status
        FROM entities e
        WHERE e.canonical_name ILIKE %(pattern)s AND {ENTITY_VISIBLE_SQL}
        ORDER BY (e.canonical_name ILIKE %(prefix)s) DESC, length(e.canonical_name),
                 e.canonical_name, e.id
        LIMIT %(fetch)s
        """,
        {
            "pattern": f"%{escaped}%",
            "prefix": f"{escaped}%",
            "fetch": limit * 4,
            "rules": RULES,
        },
    ).fetchall()
    entities = []
    for row in candidates:
        if row[3] != "research_target" and not has_published_edge(conn, str(row[0])):
            continue
        entities.append(
            {"id": str(row[0]), "canonical_name": row[1], "entity_type": row[2], "status": row[3]}
        )
        if len(entities) >= limit:
            break
    return {"query": trimmed, "entities": entities}


def _entity_names(conn: psycopg.Connection, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {
        str(r[0]): r[1]
        for r in conn.execute(
            "SELECT id, canonical_name FROM entities WHERE id = ANY(%(ids)s::uuid[])",
            {"ids": sorted(ids)},
        ).fetchall()
    }


def relationship_evidence(conn: psycopg.Connection, relationship_id: UUID) -> dict[str, Any] | None:
    edge = fetch_one(conn, relationship_id)
    if edge is None:
        return None
    return {
        "object_type": "relationship",
        "object_id": edge.id,
        "evidence_tier": edge.relationship["evidence_tier"],
        "evidence": edge.evidence,
        "evidence_count": len(edge.evidence),
    }


def score_explanation(
    conn: psycopg.Connection,
    relationship_id: UUID,
    light: LightStats | None,
    surface: SurfaceStats | None,
) -> dict[str, Any] | None:
    edge = fetch_one(conn, relationship_id)
    if edge is None:
        return None
    row = edge.relationship
    names = _entity_names(conn, {row["subject_entity_id"], row["object_entity_id"]})
    qualifiers = edge.qualifiers
    policy = qualifiers.get("source_threshold_policy") or {}
    try:
        minimum_sources = max(
            int(policy.get("minimum_independent_sources") or CANDIDATE_SOURCE_THRESHOLD_MIN), 1
        )
    except (TypeError, ValueError):
        minimum_sources = CANDIDATE_SOURCE_THRESHOLD_MIN
    distinct_documents = len({e["source_document_id"] for e in edge.evidence})
    try:
        independent = int(policy.get("independent_source_count", distinct_documents))
    except (TypeError, ValueError):
        independent = distinct_documents
    threshold_met = independent >= minimum_sources or bool(policy.get("met_by_review_override"))
    # 发布不变量：能出现在这里的关系都已过发布门；复核状态看是否来自已签名的决定集。
    review_status = "human_verified" if qualifiers.get("decision_set_key") else "unreviewed"
    metrics = relationship_score_metrics(
        confidence=float(row["confidence"]) if row["confidence"] is not None else 0.0,
        independent_source_count=independent,
        source_threshold_met=threshold_met,
        review_status=review_status,
        publication_status="published",
        fact_version_present=True,
        evidence_present=bool(edge.evidence),
        minimum_independent_sources=minimum_sources,
    )
    snapshot = light.snapshot if light else None
    context = light.analysis_context if light else None
    return {
        "object_type": "relationship",
        "object_id": edge.id,
        "relationship_type": row["relationship_type"],
        "relationship_family": row["relationship_family"],
        "record_mode": snapshot["record_mode"] if snapshot else "database",
        "fact_status": row["status"],
        "evidence_tier": row["evidence_tier"],
        "publication_status": "published",
        "relationship_status": row["status"],
        "source_threshold": metrics["source_threshold"],
        "review_status": review_status,
        "parser_version": qualifiers.get("parser_version"),
        "raw_score": metrics["raw_score"],
        "evidence_quality": metrics["evidence_quality"],
        "adjusted_score": metrics["adjusted_score"],
        "coverage": metrics["coverage"],
        "contributions": metrics["contributions"],
        "missing_inputs": metrics["missing_inputs"],
        "model_version": context["model_version"] if context else "selfhost-publication-surface",
        "profile_version": (
            context["profile_version"] if context else "selfhost-publication-surface"
        ),
        "profile_version_id": context["active_scoring_profile_version_id"] if context else None,
        "structured_fact": qualifiers.get("structured_fact") or {},
        "counter_evidence": [],
        "qualifiers": qualifiers,
        "fact_version": {
            "id": None,
            "version_no": None,
            "snapshot_key": snapshot["snapshot_key"] if snapshot else None,
            "snapshot_scope": snapshot["scope"] if snapshot else None,
            "snapshot_status": snapshot["status"] if snapshot else None,
            "record_mode": snapshot["record_mode"] if snapshot else None,
            "parser_version": qualifiers.get("parser_version"),
        },
        "subject": {
            "entity_id": row["subject_entity_id"],
            "canonical_name": names.get(row["subject_entity_id"]),
        },
        "object": {
            "entity_id": row["object_entity_id"],
            "canonical_name": names.get(row["object_entity_id"]),
        },
        "evidence": edge.evidence,
        "review_queue": [],
        "production_context": production_context(light, surface, None),
        "scoring_service_version": SCORING_SERVICE_VERSION,
    }


# -- 模块概览 -----------------------------------------------------------------


def family_relationships(
    conn: psycopg.Connection, families: list[str], *, stage_map: bool = False
) -> list[dict[str, Any]]:
    edges = fetch_published(
        conn,
        where="r.relationship_family = ANY(%(families)s)",
        params={"families": families},
        order_by="r.relationship_type, r.id",
        limit=300,
    )
    names = _entity_names(
        conn,
        {e.relationship["subject_entity_id"] for e in edges}
        | {e.relationship["object_entity_id"] for e in edges},
    )
    out = []
    for edge in edges:
        row = edge.relationship
        item = {
            "id": row["id"],
            "relationship_type": row["relationship_type"],
            "relationship_family": row["relationship_family"],
            "status": row["status"],
            "confidence": row["confidence"],
            "observed_at": row["observed_at"],
            "evidence_tier": row["evidence_tier"],
            # 只有走复核流水线的才算「Owner 签发」；单一官方来源的边用 evidence_tier 说明自己。
            "owner_signed_published": row["evidence_tier"] != "single_official",
            "subject_name": names.get(row["subject_entity_id"]),
            "object_name": names.get(row["object_entity_id"]),
            "fixture_flag": False,
        }
        out.append(item)
    return out


def control_overview(conn: psycopg.Connection) -> dict[str, Any]:
    relationships = family_relationships(conn, ["ownership_control", "corporate_structure"])
    by_type: dict[str, int] = {}
    for r in relationships:
        by_type[r["relationship_type"]] = by_type.get(r["relationship_type"], 0) + 1
    return {
        "relationships": relationships,
        "summary": {
            "published_fact_count": len(relationships),
            "relationship_count": len(relationships),
            "by_type": by_type,
        },
        "abstentions": {
            "semantics": (
                "Control edges are legal/governance assertions and are never merged with"
                " commercial dependency; absence of an edge means no assertion, not independence."
            )
        },
    }


def ma_overview(conn: psycopg.Connection) -> dict[str, Any]:
    relationships = family_relationships(conn, ["mergers_acquisitions"])
    return {
        "relationships": relationships,
        "events": [],
        "summary": {
            "published_fact_count": len(relationships),
            "relationship_count": len(relationships),
            "event_count": 0,
        },
        "abstentions": {
            "coverage": (
                "M&A coverage is what the published graph asserts; deal candidates enter through"
                " the candidate -> dual-source -> owner sign-off chain and stay private until"
                " published."
            )
        },
    }


def signals_overview(conn: psycopg.Connection) -> dict[str, Any]:
    relationships = family_relationships(conn, ["strategic_signal"])
    return {
        "relationships": relationships,
        "signal_models": [],
        "summary": {
            "published_fact_count": len(relationships),
            "relationship_count": len(relationships),
        },
        "abstentions": {
            "research_orientation": (
                "Strategic signals are research prioritization aids derived from disclosed themes;"
                " they are NOT investment advice, price predictions or trading signals."
            ),
            "scoring": (
                "Signal models without a scored run report has_scored_run=false;"
                " no synthetic scores are shown."
            ),
        },
    }


def policy_overview(conn: psycopg.Connection, light: LightStats) -> dict[str, Any]:
    return {
        "schema_version": "cloud-policy-overview-v1",
        "policy_relationships": family_relationships(conn, ["government_policy"]),
        "regulatory_filings": {
            "source": "sec_edgar",
            "by_year": [{"year": y, "filings": n} for y, n in light.filing_year_counts],
            # 单份申报的标题与链接不出库，只给按年聚合（与 Worker 发布面边界一致）。
            "latest": [],
            "scoped_to_entity": False,
        },
        "policy_models": [],
        "abstentions": {
            "coverage": (
                "Policy edges and filings are what the published graph and the SEC EDGAR source"
                " assert; absence of an edge means no assertion, not the absence of policy exposure"
                " in the real world."
            )
        },
    }


def supply_chain_overview(conn: psycopg.Connection, light: LightStats) -> dict[str, Any]:
    relationships = family_relationships(conn, ["supply_chain_operations"])
    for r in relationships:
        r["stage_id"] = SUPPLY_TYPE_STAGE_MAP.get(r["relationship_type"])
        del r["relationship_family"]
    mapped = {r["stage_id"] for r in relationships if r["stage_id"]}
    stages = light.supply_chain_stages
    return {
        "stages": stages,
        "relationships": relationships,
        "summary": {
            "published_fact_count": len(relationships),
            "demo_or_candidate_count": 0,
            "stages_total": len(stages),
            "stages_with_relationships": len(mapped),
        },
        "abstentions": {
            "coverage": (
                "Stages without relationships mean no assertion exists in the published graph for"
                " that stage - not that the stage is empty in the real world."
            ),
            "labeling": (
                "The public surface carries published facts only; demo and candidate rows are"
                " never exposed."
            ),
        },
    }


def list_changes(conn: psycopg.Connection, since: datetime | None) -> list[dict[str, Any]]:
    edges = fetch_published(
        conn,
        where="(%(since)s::timestamptz IS NULL OR r.created_at >= %(since)s::timestamptz)",
        params={"since": since},
        order_by="r.created_at DESC, r.id DESC",
        limit=100,
    )
    names = _entity_names(
        conn,
        {e.relationship["subject_entity_id"] for e in edges}
        | {e.relationship["object_entity_id"] for e in edges},
    )
    return [
        {
            "id": e.id,
            "change_type": "relationship_published",
            "object_type": "relationship",
            "object_id": e.id,
            "old_value": None,
            "new_value": {
                "relationship_type": e.relationship["relationship_type"],
                "relationship_family": e.relationship["relationship_family"],
                "status": e.relationship["status"],
                "subject_name": names.get(e.relationship["subject_entity_id"]),
                "object_name": names.get(e.relationship["object_entity_id"]),
            },
            "review_required": False,
            "created_at": e.relationship["published_at"],
            "trigger_source": None,
        }
        for e in edges
    ]


def entity_empire(
    conn: psycopg.Connection, entity_id: UUID, light: LightStats | None
) -> dict[str, Any] | None:
    focus = load_entity(conn, entity_id)
    if focus is None:
        return None
    snapshot = light.snapshot if light else None
    return {
        "as_of": snapshot["as_of"] if snapshot else None,
        "focus": {
            **focus,
            "primary_identifiers": {},
            "fixture_notice": None,
            "synthetic": False,
        },
        "structure": {},
        "coverage": {
            "published_structure_sections": 0,
            "note": (
                "The public surface carries published relationships, not a full legal-group"
                " hierarchy; structure sections appear here only when group/segment/brand/product/"
                "facility facts are published."
            ),
        },
        "data_mode": "selfhost_publication",
        "fixture_notice": None,
    }


def scoring_profiles(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT spv.id, sp.profile_key, sp.name, spv.version, sm.model_key, sm.formula,
                   spv.weights, spv.thresholds, spv.half_lives, spv.missing_value_policy,
                   spv.reason, spv.active
            FROM scoring_profile_versions spv
            JOIN scoring_profiles sp ON sp.id = spv.profile_id
            JOIN scoring_models sm ON sm.id = spv.model_id
            ORDER BY spv.active DESC, sp.is_system_default DESC, sp.profile_key, spv.version DESC
            """
        ).fetchall()
    return [DomainRepository.scoring_profile_payload(row) for row in rows]


def parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))  # ValueError -> 400 at route
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
