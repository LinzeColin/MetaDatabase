"""图谱探索：POST /v1/explore、/v1/explore/expand、/v1/explore/reroot。

算法与 worker.mjs 的 exploreGraph 逐行对应（逐跳取边、边数/节点数预算、截断判定），
区别只有两处：边来自 Postgres 并且每条都现场过发布门；一跳内被拒的候选会被跳过并继续往后取，
预算只数已过门的边。
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import psycopg

from .gate import ENTITY_VISIBLE_SQL, RULES, PublishedEdge, fetch_published, has_published_edge

GRAPH_HARD_LIMITS = {"max_hops": 2, "max_nodes": 500, "max_edges": 2000, "max_path_length": 8}
DEFAULT_GRAPH_BUDGET = {"max_nodes": 42, "max_edges": 64, "expand_nodes": 12}
DIRECTIONS = ("both", "upstream", "downstream", "in", "out")


def _int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value).strip().split(".")[0])
    except (TypeError, ValueError):
        return default
    return parsed or default


def _bounded(raw: dict[str, Any], key: str, ceiling: int) -> int:
    return min(max(_int(raw.get(key), DEFAULT_GRAPH_BUDGET[key]), 1), ceiling)


def normalize_budget(raw: Any) -> dict[str, int]:
    budget = raw if isinstance(raw, dict) else {}
    return {
        "max_nodes": _bounded(budget, "max_nodes", GRAPH_HARD_LIMITS["max_nodes"]),
        "max_edges": _bounded(budget, "max_edges", GRAPH_HARD_LIMITS["max_edges"]),
        "expand_nodes": _bounded(budget, "expand_nodes", GRAPH_HARD_LIMITS["max_nodes"]),
    }


def normalize_direction(raw: Any) -> str:
    return raw if isinstance(raw, str) and raw in DIRECTIONS else "both"


def load_entity(conn: psycopg.Connection, entity_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        f"""
        SELECT e.id, e.canonical_name, e.entity_type::text, e.status
        FROM entities e WHERE e.id = %(id)s AND {ENTITY_VISIBLE_SQL}
        """,
        {"id": entity_id, "rules": RULES},
    ).fetchone()
    if not row:
        return None
    if row[3] != "research_target" and not has_published_edge(conn, str(row[0])):
        return None
    return {"id": str(row[0]), "canonical_name": row[1], "entity_type": row[2], "status": row[3]}


def _touching_where(direction: str) -> str:
    if direction in ("out", "downstream"):
        return "r.subject_entity_id = ANY(%(frontier)s::uuid[])"
    if direction in ("in", "upstream"):
        return "r.object_entity_id = ANY(%(frontier)s::uuid[])"
    return (
        "(r.subject_entity_id = ANY(%(frontier)s::uuid[])"
        " OR r.object_entity_id = ANY(%(frontier)s::uuid[]))"
    )


def published_touching(
    conn: psycopg.Connection, frontier: list[str], direction: str, limit: int
) -> list[PublishedEdge]:
    return fetch_published(
        conn,
        where=_touching_where(direction),
        params={"frontier": frontier},
        order_by="r.id",
        limit=limit,
    )


def explore_graph(
    conn: psycopg.Connection,
    *,
    session_id: str | None,
    focus_entity_id: UUID,
    direction: str,
    hops: Any,
    budget: dict[str, int],
    active_layers: list[Any],
    filters: Any,
    as_of: Any,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    """返回响应体；焦点实体不存在（或不在发布面）返回 None，由路由层翻成 404。"""
    focus = load_entity(conn, focus_entity_id)
    if focus is None:
        return None
    bounded_hops = min(
        max(_int(hops if hops is not None else 1, 1), 1), GRAPH_HARD_LIMITS["max_hops"]
    )
    seen_edges: dict[str, PublishedEdge] = {}
    seen_nodes: set[str] = {focus["id"]}
    frontier = [focus["id"]]
    fetched_edge_count = 0
    edge_budget_hit = False
    node_budget_hit = False
    for _hop in range(bounded_hops):
        if not frontier:
            break
        rows = published_touching(conn, frontier, direction, budget["max_edges"] + 1)
        # 后一跳会重新取到前面已收的边（两端都在更早的前沿里）；
        # 只有没见过的边才占预算、参与截断判定。
        fresh = [row for row in rows if row.id not in seen_edges]
        fetched_edge_count += len(fresh)
        next_frontier: set[str] = set()
        for row in fresh:
            if len(seen_edges) >= budget["max_edges"]:
                edge_budget_hit = True
                break
            seen_edges[row.id] = row
            for endpoint in (
                row.relationship["subject_entity_id"],
                row.relationship["object_entity_id"],
            ):
                if endpoint in seen_nodes:
                    continue
                if len(seen_nodes) >= budget["max_nodes"]:
                    node_budget_hit = True
                    continue
                seen_nodes.add(endpoint)
                next_frontier.add(endpoint)
        frontier = sorted(next_frontier)

    edges = list(seen_edges.values())
    node_ids = sorted(seen_nodes)
    node_rows = conn.execute(
        "SELECT id, canonical_name, entity_type::text, status FROM entities"
        " WHERE id = ANY(%(ids)s::uuid[]) ORDER BY canonical_name, id",
        {"ids": node_ids},
    ).fetchall()
    source_documents = {e["source_document_id"] for edge in edges for e in edge.evidence}
    families = {edge.relationship["relationship_family"] for edge in edges}
    truncated = edge_budget_hit or node_budget_hit
    reasons = []
    if edge_budget_hit:
        reasons.append("edge_budget")
    if node_budget_hit:
        reasons.append("node_budget")
    return {
        "session_id": session_id or str(uuid.uuid4()),
        "focus": {
            "id": focus["id"],
            "canonical_name": focus["canonical_name"],
            "entity_type": focus["entity_type"],
        },
        "query": {
            "focus": {"object_type": "entity", "object_id": focus["id"]},
            "direction": direction,
            "hops": bounded_hops,
            "as_of": as_of,
            "scoring_profile_version_id": None,
            "active_layers": active_layers,
            "filters": filters,
            "budget": budget,
            "hard_limits": GRAPH_HARD_LIMITS,
        },
        "nodes": [
            {
                "id": str(r[0]),
                "canonical_name": r[1],
                "entity_type": r[2],
                "fixture_notice": None,
                "synthetic": False,
            }
            for r in node_rows
        ],
        "edges": [
            {
                "id": edge.id,
                "subject_id": edge.relationship["subject_entity_id"],
                "object_id": edge.relationship["object_entity_id"],
                "relationship_type": edge.relationship["relationship_type"],
                "relationship_family": edge.relationship["relationship_family"],
                "status": edge.relationship["status"],
                "confidence": edge.relationship["confidence"],
                "valid_from": None,
                "valid_to": None,
                "evidence_count": len(edge.evidence),
                # 这条边凭什么上图（single_official | multi_source），以及原文在哪打开。
                "evidence_tier": edge.relationship["evidence_tier"],
                "source_url": edge.source_url(),
                "source_publisher": edge.publisher(),
                "synthetic": False,
                "fixture_notice": None,
            }
            for edge in edges
        ],
        "truncated": truncated,
        "truncation": {
            "applied": truncated,
            "reasons": reasons,
            "message": (
                "graph truncated by budget; raise budget or expand from an anchor"
                if truncated
                else ""
            ),
            "fetched_edge_count": fetched_edge_count,
            "returned_edge_count": len(edges),
            "returned_node_count": len(node_rows),
        },
        "continuation": {
            "available": truncated,
            "expand_endpoint": "/v1/explore/expand" if truncated else None,
            "anchor_entity_id": focus["id"] if truncated else None,
            "direction": direction if truncated else None,
            "expand_nodes": budget["expand_nodes"] if truncated else None,
        },
        "warnings": [],
        "coverage": {
            "visible_nodes": len(node_rows),
            "visible_edges": len(edges),
            "source_count": len(source_documents),
            "relationship_family_count": len(families),
            "synthetic_fixture_edges": 0,
        },
        "production_context": context,
    }
