"""发布门的读端入口：公开数据面只经过这里读关系。

判定本身不在这里——和 Worker 的发布端共用同一份：
``scripts/relationship_publication_gate.py``（evaluate_relationship_gate）经
``scripts/publish_to_cloud_channel.py`` 的 ``GATED_RELATIONSHIPS_SQL`` + ``gate_relationship``。
这里只做三件事：

1. 取候选行（沿用发布端的 SQL：只取 derivation_rule 属于已发布规则、状态未被取代/撤销的关系，
   连同每条关系的全部证据与其来源登记等级）；
2. 在 SQL 里加一个「必要条件」预筛（至少一条可打开原文的 supports 证据）——它只会挡掉发布门
   一定会拒绝的行，不会多放一行；通不通过始终由 Python 那一份判定说了算；
3. 把通过的行整理成公开形状。未过门的关系、草稿、复核中的数据从不离开这个模块。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg

from scripts.publish_to_cloud_channel import (
    GATED_RELATIONSHIPS_SQL,
    PUBLISHED_RULES,
    gate_relationship,
)

RULES = list(PUBLISHED_RULES)

# 发布门的必要条件：至少一条 supports 证据带 http(s) 链接（宽于 is_openable_url，只挡必拒行）。
OPENABLE_SUPPORT_SQL = """EXISTS (
    SELECT 1 FROM relationship_evidence pre_re
    JOIN source_documents pre_sd ON pre_sd.id = pre_re.source_document_id
    WHERE pre_re.relationship_id = r.id
      AND pre_re.role = 'supports'
      AND pre_sd.url ~* '^\\s*https?:'
)"""

# 实体可见的 SQL 预筛：研究目标，或是至少一条「可能过门」关系的端点（必要条件，只挡必拒的）。
# 精确判定在 Python：研究目标 或 has_published_edge()——比 D1 发布面（任何已发布规则关系的端点）更窄。
ENTITY_VISIBLE_SQL = """(
    e.status = 'research_target'
    OR EXISTS (
        SELECT 1 FROM relationships r
        WHERE r.subject_entity_id = e.id
          AND r.derivation_rule = ANY(%(rules)s)
          AND r.status NOT IN ('superseded', 'revoked')
          AND {openable}
    )
    OR EXISTS (
        SELECT 1 FROM relationships r
        WHERE r.object_entity_id = e.id
          AND r.derivation_rule = ANY(%(rules)s)
          AND r.status NOT IN ('superseded', 'revoked')
          AND {openable}
    )
)""".replace("{openable}", OPENABLE_SUPPORT_SQL)


@dataclass(frozen=True)
class PublishedEdge:
    """一条已过发布门的关系：D1 发布面同形的行 + 证据行。"""

    relationship: dict[str, Any]
    evidence: list[dict[str, Any]]

    @property
    def id(self) -> str:
        return self.relationship["id"]

    @property
    def qualifiers(self) -> dict[str, Any]:
        text = self.relationship.get("qualifiers_json")
        if not text:
            return {}
        try:
            value = json.loads(text)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    def source_url(self) -> str | None:
        urls = [
            str(e["source_url"])
            for e in self.evidence
            if e["role"] == "supports" and str(e.get("source_url") or "").startswith("http")
        ]
        return min(urls) if urls else None

    def publisher(self) -> str | None:
        names = [
            str(e["publisher"])
            for e in self.evidence
            if e["role"] == "supports"
            and str(e.get("source_url") or "").startswith("http")
            and e.get("publisher") is not None
        ]
        return min(names) if names else None


def parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def fetch_page(
    conn: psycopg.Connection,
    *,
    where: str,
    params: dict[str, Any],
    order_by: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[PublishedEdge], int]:
    """取一页候选并过门。返回 (通过的关系, 本页扫描的候选行数)。"""
    sql = (
        GATED_RELATIONSHIPS_SQL
        + f" AND {OPENABLE_SUPPORT_SQL} AND ({where})"
        + f" ORDER BY {order_by} LIMIT %(_limit)s OFFSET %(_offset)s"
    )
    bound = {"rules": RULES, **params, "_limit": limit, "_offset": offset}
    raw_rows = conn.execute(sql, bound).fetchall()
    edges: list[PublishedEdge] = []
    for raw in raw_rows:
        relationship, evidence, _decision = gate_relationship(raw)
        if relationship is not None:
            edges.append(PublishedEdge(relationship, evidence))
    return edges, len(raw_rows)


def fetch_published(
    conn: psycopg.Connection,
    *,
    where: str,
    params: dict[str, Any],
    order_by: str,
    limit: int,
    scan_cap: int = 20_000,
) -> list[PublishedEdge]:
    """按顺序取前 ``limit`` 条已过门的关系；被拒的候选跳过并继续往后翻（最多扫 scan_cap 行）。"""
    out: list[PublishedEdge] = []
    offset = 0
    page = max(limit, 50)
    while len(out) < limit and offset < scan_cap:
        edges, scanned = fetch_page(
            conn, where=where, params=params, order_by=order_by, limit=page, offset=offset
        )
        out.extend(edges)
        offset += scanned
        if scanned < page:
            break
    return out[:limit]


def has_published_edge(conn: psycopg.Connection, entity_id: str) -> bool:
    """实体至少挂着一条真正过门的关系（精确判定，逐条走发布门）。"""
    edges = fetch_published(
        conn,
        where="r.subject_entity_id = %(eid)s OR r.object_entity_id = %(eid)s",
        params={"eid": entity_id},
        order_by="r.id",
        limit=1,
    )
    return bool(edges)


def fetch_one(conn: psycopg.Connection, relationship_id: UUID) -> PublishedEdge | None:
    edges, _ = fetch_page(
        conn,
        where="r.id = %(rid)s",
        params={"rid": relationship_id},
        order_by="r.id",
        limit=1,
    )
    return edges[0] if edges else None
