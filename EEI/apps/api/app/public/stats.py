"""发布面的统计与脉搏。

两层缓存，各管各的代价：

* ``SurfaceStats``（重）：对全部「已发布规则」关系逐条过发布门（流式游标，内存平），得出
  已发布关系数、按天新增、家族构成、数据截至。和发布端每日做的是同一件事；默认 30 分钟刷一次，
  过期后先回旧值、后台刷新。
* ``LightStats``（轻）：事件日曲线、事件类型、来源新鲜度、最新入库时间、活动快照与分析上下文，
  默认 2 分钟刷一次。

explore 等请求式查询不走这里的数据——它们每次现查现过门；这里只服务「全库规模」类的数字。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg

from scripts.publish_to_cloud_channel import (
    GATED_RELATIONSHIPS_SQL,
    PULSE_DATA_AS_OF_SQL,
    PULSE_ENTITIES_DAILY_SQL,
    PULSE_EVENT_TYPES_SQL,
    PULSE_EVENTS_DAILY_SQL,
    PULSE_SOURCES_SQL,
    active_analysis_context_payload,
    gate_relationship,
)

from ..domain_repository import SCORING_SERVICE_VERSION
from ..scoring import CANDIDATE_SOURCE_THRESHOLD_MIN
from .db import PublicDatabase
from .gate import OPENABLE_SUPPORT_SQL, RULES

log = logging.getLogger("eei.public.stats")

GRAPH_QUERY_VERSION = "pg-gated-graph-v1"
PUBLISHER_VERSION = "eei-selfhost-api-v1"
PULSE_LIVE_SECONDS = 300
PULSE_DELAYED_SECONDS = 3600


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class TtlCache[T]:
    """单飞 + 先回旧值后台刷新的小缓存。"""

    def __init__(self, ttl_seconds: float, loader: Callable[[], T], name: str) -> None:
        self._ttl = ttl_seconds
        self._loader = loader
        self._name = name
        self._value: T | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()
        self._refreshing = False
        self.last_error: str | None = None

    def _load(self) -> T:
        value = self._loader()
        self._value = value
        self._loaded_at = time.monotonic()
        self.last_error = None
        return value

    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def run() -> None:
            try:
                self._load()
            except Exception as exc:  # noqa: BLE001 - 后台刷新失败只记录，继续用旧值
                self.last_error = f"{exc.__class__.__name__}: {exc}"
                log.warning("%s refresh failed: %s", self._name, self.last_error)
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=run, name=f"eei-{self._name}-refresh", daemon=True).start()

    def peek(self) -> T | None:
        return self._value

    def get(self, *, block: bool = True) -> T | None:
        """block=True：没有值就同步加载（失败抛出）；block=False：没有值返回 None 并在后台加载。"""
        if self._value is not None:
            if time.monotonic() - self._loaded_at > self._ttl:
                self._refresh_in_background()
            return self._value
        if not block:
            self._refresh_in_background()
            return None
        with self._lock:
            if self._value is not None:
                return self._value
            return self._load()

    def invalidate(self) -> None:
        self._loaded_at = 0.0


@dataclass(frozen=True)
class SurfaceStats:
    computed_at: str
    published_relationship_count: int
    relationships_as_of: str | None
    by_day: dict[str, int]
    by_family: dict[str, int]
    by_tier: dict[str, int]
    rejected: int


def compute_surface_stats(db: PublicDatabase) -> SurfaceStats:
    by_day: dict[str, int] = {}
    by_family: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    newest = ""
    accepted = rejected = 0
    sql = GATED_RELATIONSHIPS_SQL + f" AND {OPENABLE_SUPPORT_SQL}"
    with db.connection() as conn:
        conn.execute("SET LOCAL statement_timeout = '120s'")
        with conn.cursor(name="eei_surface_scan") as cur:
            cur.itersize = 500
            cur.execute(sql, {"rules": RULES})
            for raw in cur:
                relationship, _evidence, _decision = gate_relationship(raw)
                if relationship is None:
                    rejected += 1
                    continue
                accepted += 1
                day = (relationship["published_at"] or "")[:10]
                if day:
                    by_day[day] = by_day.get(day, 0) + 1
                family = relationship["relationship_family"]
                by_family[family] = by_family.get(family, 0) + 1
                tier = relationship["evidence_tier"] or "unknown"
                by_tier[tier] = by_tier.get(tier, 0) + 1
                observed = relationship["observed_at"] or ""
                if observed > newest:
                    newest = observed
    return SurfaceStats(
        computed_at=utc_now_iso(),
        published_relationship_count=accepted,
        relationships_as_of=newest or None,
        by_day=by_day,
        by_family=by_family,
        by_tier=by_tier,
        rejected=rejected,
    )


@dataclass(frozen=True)
class LightStats:
    generated_at: str
    data_as_of: str | None
    entities_by_day: dict[str, int]
    events_by_day: dict[str, int]
    event_types: list[tuple[str, int]]
    sources: list[dict[str, Any]]
    last_ingest_at: str | None
    filing_year_counts: list[tuple[int, int]]
    snapshot: dict[str, Any] | None
    analysis_context: dict[str, Any] | None
    supply_chain_stages: list[dict[str, Any]] = field(default_factory=list)


def _daily(conn: psycopg.Connection, sql: str, params: tuple) -> dict[str, int]:
    return {row[0]: int(row[1]) for row in conn.execute(sql, params).fetchall() if row[0]}


def compute_light_stats(db: PublicDatabase) -> LightStats:
    rules = list(RULES)
    with db.connection() as conn:
        conn.execute("SET LOCAL statement_timeout = '30s'")
        entities = _daily(conn, PULSE_ENTITIES_DAILY_SQL, (rules, rules))
        events = _daily(conn, PULSE_EVENTS_DAILY_SQL, (rules,))
        event_types = [
            (str(b), int(c))
            for b, c in conn.execute(PULSE_EVENT_TYPES_SQL, (rules,)).fetchall()
            if b
        ]
        sources = [
            {
                "code": str(code),
                "name": name,
                "documents": int(documents),
                "last_seen_at": last_seen,
            }
            for code, name, documents, last_seen in conn.execute(PULSE_SOURCES_SQL).fetchall()
        ]
        as_of_row = conn.execute(PULSE_DATA_AS_OF_SQL).fetchone()
        data_as_of = as_of_row[0] if as_of_row and as_of_row[0] else None
        ingest_row = conn.execute(
            'SELECT to_char(max(retrieved_at), \'YYYY-MM-DD"T"HH24:MI:SS"Z"\')'
            " FROM source_documents"
        ).fetchone()
        filings = [
            (int(y), int(n))
            for y, n in conn.execute(
                """
                SELECT extract(year FROM sd.document_date)::int AS year, count(*)::int
                FROM source_documents sd
                JOIN sources src ON src.id = sd.source_id AND src.code = 'sec_edgar'
                WHERE sd.document_date IS NOT NULL
                GROUP BY 1 ORDER BY 1
                """
            ).fetchall()
        ]
        snap = conn.execute(
            """
            SELECT snapshot_key, scope, record_mode, status
            FROM data_snapshots WHERE status = 'active'
            ORDER BY activated_at DESC NULLS LAST, created_at DESC LIMIT 1
            """
        ).fetchone()
        context = active_analysis_context_payload(conn)
        stages = [
            {
                "stage_id": r[0],
                "stage_order": int(r[1]),
                "slug": r[2],
                "name_zh": r[3],
                "name_en": r[4],
                "default_direction": r[5],
                "examples": r[6],
            }
            for r in conn.execute(
                "SELECT stage_id, stage_order, slug, name_zh, name_en, default_direction, examples"
                " FROM supply_chain_stages ORDER BY stage_order"
            ).fetchall()
        ]
    generated_at = utc_now_iso()
    snapshot = None
    if snap:
        snapshot = {
            "snapshot_key": snap[0],
            "scope": snap[1],
            "record_mode": snap[2],
            "status": snap[3],
            # 与发布端一致：「数据版本」= 库里最新一条事实的时间，不是建表时间。
            "as_of": data_as_of or generated_at,
            "activated_at": generated_at,
        }
    return LightStats(
        generated_at=generated_at,
        data_as_of=data_as_of,
        entities_by_day=entities,
        events_by_day=events,
        event_types=event_types,
        sources=sources,
        last_ingest_at=ingest_row[0] if ingest_row else None,
        filing_year_counts=filings,
        snapshot=snapshot,
        analysis_context=context,
        supply_chain_stages=stages,
    )


class SurfaceStatsService:
    def __init__(self, db: PublicDatabase, *, surface_ttl: float, light_ttl: float) -> None:
        self.surface = TtlCache(surface_ttl, lambda: compute_surface_stats(db), "surface-stats")
        self.light = TtlCache(light_ttl, lambda: compute_light_stats(db), "light-stats")

    def warm_up(self) -> None:
        """启动时后台预热，首个请求不必等全量扫描。"""
        self.light.get(block=False)
        self.surface.get(block=False)


# ---------------------------------------------------------------------------
# 形状：与 worker.mjs 的 dataPulse / productionContext / publicationMeta 一致
# ---------------------------------------------------------------------------


def _delta(series: list[dict[str, Any]], days: int) -> dict[str, int]:
    if not series:
        return {"entities": 0, "relationships": 0, "events": 0}
    last = series[-1]
    idx = len(series) - 1 - days
    base = series[idx] if idx >= 0 else {"entities": 0, "relationships": 0, "events": 0}
    return {k: last[k] - base[k] for k in ("entities", "relationships", "events")}


def build_pulse(light: LightStats, surface: SurfaceStats, *, days: int) -> dict[str, Any]:
    window = min(max(days, 7), 400)
    all_days = sorted(set(light.entities_by_day) | set(surface.by_day) | set(light.events_by_day))
    series: list[dict[str, Any]] = []
    ce = cr = cv = 0
    for day in all_days:
        de = light.entities_by_day.get(day, 0)
        dr = surface.by_day.get(day, 0)
        dv = light.events_by_day.get(day, 0)
        ce, cr, cv = ce + de, cr + dr, cv + dv
        series.append(
            {
                "day": day,
                "entities": ce,
                "relationships": cr,
                "events": cv,
                "entities_added": de,
                "relationships_added": dr,
                "events_added": dv,
            }
        )
    series = series[-window:] if len(series) > window else series
    latest = series[-1] if series else None

    heartbeat = heartbeat_state(light.last_ingest_at)
    today = (
        {
            "entities": latest["entities_added"],
            "relationships": latest["relationships_added"],
            "events": latest["events_added"],
        }
        if latest
        else {"entities": 0, "relationships": 0, "events": 0}
    )
    return {
        "schema_version": "eei-data-pulse-v1",
        "generated_at": utc_now_iso(),
        "data_as_of": light.data_as_of,
        "last_publish_at": surface.computed_at,
        "totals": {
            "entities": latest["entities"] if latest else 0,
            "relationships": surface.published_relationship_count,
            "events": latest["events"] if latest else 0,
        },
        "added": {"today": today, "d7": _delta(series, 7), "d30": _delta(series, 30)},
        "series": series,
        "composition": {
            "event_type": [{"bucket": b, "count": c} for b, c in light.event_types],
            "relationship_family": [
                {"bucket": b, "count": c}
                for b, c in sorted(surface.by_family.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        },
        "sources": light.sources,
        "heartbeat": heartbeat,
    }


def heartbeat_state(last_ingest_at: str | None) -> dict[str, Any]:
    """自托管版没有采集器心跳表；用「最新一份原文入库时间」代替，并在 detail 里说明口径。"""
    lag: int | None = None
    if last_ingest_at:
        seen = datetime.fromisoformat(last_ingest_at.replace("Z", "+00:00"))
        lag = max(0, int((datetime.now(UTC) - seen).total_seconds()))
    if lag is None:
        state = "unknown"
    elif lag <= PULSE_LIVE_SECONDS:
        state = "live"
    elif lag <= PULSE_DELAYED_SECONDS:
        state = "delayed"
    else:
        state = "stalled"
    return {
        "state": state,
        "last_seen_at": last_ingest_at,
        "lag_seconds": lag,
        "collector": "postgres_ingest",
        "detail": {"basis": "newest source_documents.retrieved_at"},
    }


def sources_freshness(light: LightStats) -> dict[str, Any]:
    return {
        "schema_version": "cloud-sources-freshness-v1",
        "generated_at": utc_now_iso(),
        "data_as_of": light.data_as_of,
        "collector": heartbeat_state(light.last_ingest_at),
        "sources": light.sources,
    }


def publication_meta(light: LightStats, surface: SurfaceStats | None) -> dict[str, str]:
    meta = {"publisher_version": PUBLISHER_VERSION}
    if surface is not None:
        meta["published_at"] = surface.computed_at
        meta["published_relationship_count"] = str(surface.published_relationship_count)
        if surface.relationships_as_of:
            meta["relationships_as_of"] = surface.relationships_as_of
    return meta


def production_context(
    light: LightStats | None, surface: SurfaceStats | None, request_as_of: str | None
) -> dict[str, Any]:
    """与 worker.mjs productionContext 同形。统计还没算出来时数字给 None（不是 0）。"""
    context = light.analysis_context if light else None
    snapshot = light.snapshot if light else None
    count = surface.published_relationship_count if surface else None
    return {
        "schema_version": "production-context-v1",
        "request_as_of": request_as_of,
        "graph_query_version": GRAPH_QUERY_VERSION,
        "scoring_service_version": SCORING_SERVICE_VERSION,
        "active_scoring_profile_version_id": (
            context["active_scoring_profile_version_id"] if context else None
        ),
        "active_scoring_profile": (
            {
                "model_version": context["model_version"],
                "profile_version": context["profile_version"],
            }
            if context
            else None
        ),
        "active_analysis_context": {
            "surface": "selfhost_publication",
            "snapshot_key": snapshot["snapshot_key"] if snapshot else None,
            "snapshot_status": snapshot["status"] if snapshot else None,
            "as_of": snapshot["as_of"] if snapshot else None,
            "published_at": surface.computed_at if surface else None,
            # 数据截至：已发布关系里最新一条的观测时间（过发布门后现算，不是建表时间）。
            "relationships_as_of": surface.relationships_as_of if surface else None,
            "publisher_version": PUBLISHER_VERSION,
            "data_snapshot_key": context["active_data_snapshot_key"] if context else None,
            "score_snapshot_id": context["active_scoring_run_id"] if context else None,
            "model_version": context["model_version"] if context else None,
            "profile_version": context["profile_version"] if context else None,
            "refresh_generation": context["refresh_generation"] if context else None,
        },
        "record_modes": {
            "published_relationships": {"database": count, "fixture": 0, "total": count}
        },
        "candidate_fact_summary": {
            "total": count,
            "published": count,
            "unpublished": 0,
            "source_threshold_open": 0,
            "review_open": 0,
            "reason": (
                "public surface serves only relationships that passed the publication gate;"
                " candidates and review queues are never exposed"
            ),
        },
        # 发布门（Owner 2026-09-30 裁定）：官方一手来源 + 可打开原文 → single_official；
        # 其余走原规则：≥2 个独立来源且人工复核。
        "publication_policy": {
            "relationship_fact_candidates_in_graph_edges": False,
            "minimum_independent_sources": CANDIDATE_SOURCE_THRESHOLD_MIN,
            "publish_requires_source_threshold": True,
            "publish_requires_human_review": True,
            "non_official_minimum_independent_sources": CANDIDATE_SOURCE_THRESHOLD_MIN,
            "non_official_requires_human_review": True,
            "official_single_source_publishable": True,
            "official_source_tier_max": 1,
            "official_requires_openable_original": True,
        },
    }
