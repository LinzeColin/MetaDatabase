"""资本河事件面：GET /v1/events、/v1/events/amount-summary、/v1/evidence/event/{id}。

事件没有关系那样的发布门（发布端只按 derivation_rule 与状态筛，且要求至少一条证据），这里同口径。
金额语义复用 apps/api/app/amount_semantics.py（与本地 API、Worker 的移植版同一套判定）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from scripts.publish_to_cloud_channel import sanitize_public_qualifiers

from ..amount_semantics import AmountSemanticError, aggregate_event_amounts, event_amount_semantics
from .gate import RULES


class BadFilter(ValueError):
    pass


def plain(value: Any) -> Any:
    """Decimal 一律转成 JSON 数字（Worker 发的是数字，不是字符串）。"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (datetime, date)) else str(value)


def clamp_limit(raw: Any, default: int = 100, ceiling: int = 500) -> int:
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(1, min(ceiling, parsed))


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _uuid(name: str, value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise BadFilter(f"{name} must be a UUID") from exc


def _timestamp(name: str, value: str | None) -> datetime | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadFilter(f"{name} must be an ISO-8601 timestamp") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


EVENT_COLUMNS = """
    ev.id, ev.event_type, ev.title, ev.status::text, ev.announced_at, ev.effective_at,
    ev.period_start, ev.period_end, ev.observed_at, ev.amount, ev.currency, ev.amount_kind,
    ev.description, ev.qualifiers,
    (SELECT count(*) FROM event_evidence ee WHERE ee.event_id = ev.id) AS evidence_count
"""
SUMMARY_COLUMNS = "ev.id, ev.amount, ev.currency, ev.amount_kind, ev.period_start, ev.period_end"


def _event_query(
    params: dict[str, str | None], *, summary: bool, limit: int
) -> tuple[str, dict[str, Any]]:
    clauses = [
        "ev.derivation_rule = ANY(%(rules)s)",
        "ev.status NOT IN ('superseded', 'revoked')",
        "EXISTS (SELECT 1 FROM event_evidence ee WHERE ee.event_id = ev.id)",
    ]
    bound: dict[str, Any] = {"rules": RULES, "_limit": limit}
    entity = _clean(params.get("entity"))
    if entity:
        clauses.append(
            "EXISTS (SELECT 1 FROM event_participants ep"
            " WHERE ep.event_id = ev.id AND ep.entity_id = %(entity)s)"
        )
        bound["entity"] = _uuid("entity", entity)
    theme = _clean(params.get("theme"))
    if theme:
        clauses.append(
            "EXISTS (SELECT 1 FROM event_participants ep WHERE ep.event_id = ev.id"
            " AND ep.entity_id = %(theme)s AND ep.role = 'theme')"
        )
        bound["theme"] = _uuid("theme", theme)
    when = "COALESCE(ev.effective_at, ev.announced_at, ev.observed_at)"
    start = _timestamp("from", params.get("from"))
    if start:
        clauses.append(f"{when} >= %(from)s")
        bound["from"] = start
    end = _timestamp("to", params.get("to"))
    if end:
        clauses.append(f"{when} <= %(to)s")
        bound["to"] = end
    event_type = _clean(params.get("event_type"))
    if event_type:
        clauses.append("ev.event_type = %(event_type)s")
        bound["event_type"] = event_type
    currency = _clean(params.get("currency"))
    if currency:
        clauses.append("upper(ev.currency::text) = upper(%(currency)s)")
        bound["currency"] = currency
    amount_kind = _clean(params.get("amount_kind"))
    if amount_kind:
        clauses.append("ev.amount_kind = %(amount_kind)s")
        bound["amount_kind"] = amount_kind
    sql = (
        f"SELECT {SUMMARY_COLUMNS if summary else EVENT_COLUMNS} FROM events ev WHERE "
        + " AND ".join(clauses)
        + f" ORDER BY {when} DESC, ev.observed_at DESC, ev.id LIMIT %(_limit)s"
    )
    return sql, bound


def _semantics(row: dict[str, Any]) -> dict[str, Any]:
    """读路径永不抛错（与 Worker 一致）：金额语义非法就降级为 reported_unclassified。"""
    try:
        return event_amount_semantics(
            amount=row["amount"],
            currency=row["currency"],
            amount_kind=row["amount_kind"],
            period_start=row["period_start"],
            period_end=row["period_end"],
        )
    except AmountSemanticError:
        return {
            "schema_version": "event-amount-semantics-v1",
            "state": "reported_unclassified",
            "amount": row["amount"],
            "display_amount": row["amount"],
            "currency": row["currency"],
            "amount_kind": row["amount_kind"],
            "period_start": iso(row["period_start"]),
            "period_end": iso(row["period_end"]),
            "visual_weight": None,
            "width_eligible": False,
            "aggregate_eligible": False,
            "aggregation_key": None,
            "non_aggregation_reason": "amount_semantics_unclassified",
        }


def _row(r: tuple, *, summary: bool) -> dict[str, Any]:
    if summary:
        amount = float(r[1]) if r[1] is not None else None
        return {
            "id": str(r[0]),
            "amount": amount,
            "currency": r[2].strip() if r[2] else None,
            "amount_kind": r[3],
            "period_start": r[4],
            "period_end": r[5],
        }
    amount = float(r[9]) if r[9] is not None else None
    return {
        "id": str(r[0]),
        "event_type": r[1],
        "title": r[2],
        "status": r[3],
        "announced_at": iso(r[4]),
        "effective_at": iso(r[5]),
        "period_start": r[6],
        "period_end": r[7],
        "observed_at": iso(r[8]),
        "amount": amount,
        "currency": r[10].strip() if r[10] else None,
        "amount_kind": r[11],
        "description": r[12],
        "qualifiers": sanitize_public_qualifiers(r[13]) or {},
        "evidence_count": int(r[14] or 0),
    }


def list_events(
    conn: psycopg.Connection, params: dict[str, str | None], limit: int
) -> list[dict[str, Any]]:
    sql, bound = _event_query(params, summary=False, limit=limit)
    rows = [_row(r, summary=False) for r in conn.execute(sql, bound).fetchall()]
    if not rows:
        return []
    participants: dict[str, list[dict[str, Any]]] = {}
    for event_id, entity_id, name, role, direction in conn.execute(
        """
        SELECT ep.event_id, ep.entity_id, e.canonical_name, ep.role, ep.direction
        FROM event_participants ep JOIN entities e ON e.id = ep.entity_id
        WHERE ep.event_id = ANY(%(ids)s::uuid[]) ORDER BY ep.role, ep.entity_id
        """,
        {"ids": [r["id"] for r in rows]},
    ).fetchall():
        participants.setdefault(str(event_id), []).append(
            {
                "entity_id": str(entity_id),
                "entity_name": name,
                "role": role,
                "direction": direction,
            }
        )
    out = []
    for row in rows:
        semantics = _semantics(row)
        out.append(
            {
                **row,
                "period_start": iso(row["period_start"]),
                "period_end": iso(row["period_end"]),
                "participants": participants.get(row["id"], []),
                "amount_semantics": plain(semantics),
            }
        )
    return out


def _summary_safe(row: dict[str, Any]) -> dict[str, Any]:
    """读路径永不抛错：金额语义非法的行降级成「已报告但未分类」，不参与汇总。"""
    try:
        event_amount_semantics(
            amount=row["amount"],
            currency=row["currency"],
            amount_kind=row["amount_kind"],
            period_start=row["period_start"],
            period_end=row["period_end"],
        )
        return row
    except AmountSemanticError:
        return {
            **row,
            "currency": "XXX",
            "amount_kind": row["amount_kind"] or "unknown",
            "period_start": None,
            "period_end": None,
        }


def amount_summary(
    conn: psycopg.Connection, params: dict[str, str | None], limit: int
) -> dict[str, Any]:
    sql, bound = _event_query(params, summary=True, limit=limit)
    rows = [_summary_safe(_row(r, summary=True)) for r in conn.execute(sql, bound).fetchall()]
    summary = aggregate_event_amounts(rows)
    summary["filters"] = {k: v for k, v in params.items() if k != "limit" and v is not None}
    return plain(summary)


def event_evidence(conn: psycopg.Connection, event_id: UUID, limit: Any) -> dict[str, Any] | None:
    event = conn.execute(
        """
        SELECT ev.id, ev.event_type, ev.title, ev.status::text, ev.announced_at, ev.effective_at,
               ev.observed_at, ev.amount, ev.currency, ev.amount_kind, ev.description
        FROM events ev
        WHERE ev.id = %(id)s AND ev.derivation_rule = ANY(%(rules)s)
          AND ev.status NOT IN ('superseded', 'revoked')
          AND EXISTS (SELECT 1 FROM event_evidence ee WHERE ee.event_id = ev.id)
        """,
        {"id": event_id, "rules": RULES},
    ).fetchone()
    if event is None:
        return None
    cap = clamp_limit(limit if limit is not None else 20, default=20, ceiling=100)
    rows = conn.execute(
        """
        SELECT ee.source_document_id, ee.role::text, ee.locator, ee.support_excerpt,
               sd.url, sd.title, sd.publisher, sd.document_date
        FROM event_evidence ee JOIN source_documents sd ON sd.id = ee.source_document_id
        WHERE ee.event_id = %(id)s ORDER BY ee.role::text, sd.publisher, sd.url
        """,
        {"id": event_id},
    ).fetchall()
    docs: dict[str, dict[str, Any]] = {}
    for doc_id, _role, _loc, _ex, url, title, publisher, doc_date in rows:
        docs.setdefault(
            str(doc_id),
            {
                "id": str(doc_id),
                "url": url,
                "title": title,
                "publisher": publisher,
                "document_date": iso(doc_date),
            },
        )
    evidence = []
    for doc_id, role, locator, excerpt, url, title, publisher, doc_date in rows[:cap]:
        evidence.append(
            {
                "evidence_id": f"{event_id}:{doc_id}:{role}",
                "source_document_id": str(doc_id),
                "ingestion_evidence_chain_id": None,
                "role": role,
                # 官方一手来源（SEC/GLEIF）均为 tier 1。
                "source_tier": 1,
                "publisher": publisher,
                "title": title,
                "url": url,
                "locator": locator,
                "support_excerpt": excerpt,
                "snippet": {"text": excerpt, "locator": locator, "redaction_status": "public"},
                "structured_fact": {},
                "counter_evidence": [],
                "parser_version": None,
                "confidence": None,
                "review_status": None,
                "source_document": {
                    "id": str(doc_id),
                    "url": url,
                    "title": title,
                    "publisher": publisher,
                    "document_date": iso(doc_date),
                },
            }
        )
    return {
        "schema_version": "evidence-detail-v1",
        "object_type": "event",
        "object_id": str(event_id),
        "object_summary": {
            "event_type": event[1],
            "title": event[2],
            "status": event[3],
            "announced_at": iso(event[4]),
            "effective_at": iso(event[5]),
            "observed_at": iso(event[6]),
            "amount": float(event[7]) if event[7] is not None else None,
            "currency": event[8].strip() if event[8] else None,
            "amount_kind": event[9],
            "description": event[10],
        },
        "evidence_count": len(rows),
        "returned_evidence_count": len(evidence),
        "source_document_count": len(docs),
        "limit": cap,
        "truncated": len(rows) > len(evidence),
        "source_documents": list(docs.values()),
        "evidence": evidence,
        "production_context": {"surface": "selfhost_publication"},
    }
