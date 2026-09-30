#!/usr/bin/env python3
"""explore 压测：建一个一次性的大库，量 POST /v1/explore 的延迟分布。

验收口径（任务书）：hops=2、max_nodes=160 时 p95 < 1.5s。

    # 1) 起一个本地 Postgres（任意 16 版本都行；这里用 docker）
    docker run -d --name eei-bench-pg -e POSTGRES_PASSWORD=bench -p 127.0.0.1:55433:5432 postgres:16
    # 2) 压测（自动建库 eei_bench、迁移、造数据、测量、删库）
    cd EEI && uv run python apps/api/deploy/bench_explore.py \
        --admin-dsn postgresql://postgres:bench@127.0.0.1:55433/postgres \
        --entities 20000 --relationships 150000

默认按「进程内」直接打应用（含连接池、发布门、JSON 序列化，不含网络）；加 ``--http`` 会起一个
真 uvicorn 子进程、用 httpx 走回环 HTTP 测，更接近线上。
数据形状：幂律度分布（少数枢纽实体挂几千条边），约 90% 的关系能过门，5% 非官方单来源、
5% 官方但没有原文链接（这两类会被发布门拒绝，专门用来考「被拒候选要往后翻」的路径）。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))  # 直接 `python apps/api/deploy/bench_explore.py` 也能 import apps.*
DB_NAME = "eei_bench"

GENERATE_SQL = """
CREATE TEMP TABLE ent AS
  SELECT i AS rn, gen_random_uuid() AS id FROM generate_series(1, %(n)s) i;
INSERT INTO entities (id, canonical_name, entity_type, status)
  SELECT id, 'Bench Corp ' || rn, 'legal_entity',
         CASE WHEN rn % 10 = 0 THEN 'research_target' ELSE 'active' END
  FROM ent;
CREATE UNIQUE INDEX ON ent (rn);

INSERT INTO sources (code, name, base_url, source_tier, active) VALUES
  ('bench_official', 'Bench SEC', 'https://www.sec.gov', 1, true),
  ('bench_ir', 'Bench IR', 'https://ir.example.test', 2, true);

CREATE TEMP TABLE pairs AS
  SELECT g, 1 + floor(%(n)s * power(random(), 2.2))::int AS sr,
            1 + floor(%(n)s * random())::int AS orr, random() AS kind
  FROM generate_series(1, %(r)s) g;

CREATE TEMP TABLE rel AS
  SELECT gen_random_uuid() AS id, s.id AS subj, o.id AS obj, p.g, p.kind
  FROM pairs p JOIN ent s ON s.rn = p.sr JOIN ent o ON o.rn = p.orr
  WHERE p.sr <> p.orr;

INSERT INTO relationships (id, subject_entity_id, object_entity_id, relationship_type,
                           relationship_family, status, confidence, observed_at, created_at,
                           derivation_rule, derivation_version)
SELECT r.id, r.subj, r.obj,
       (ARRAY['capacity_commitment','logistics_provider_to','energy_provider_to'])[1 + r.g % 3],
       'supply_chain_operations', 'reported', 0.9,
       now() - (random() * interval '90 days'), now() - (random() * interval '90 days'),
       'authoritative_first_hand_ingestion', 'bench'
FROM rel r;

CREATE TEMP TABLE doc AS
  SELECT gen_random_uuid() AS id, r.id AS rid, r.kind,
         CASE WHEN r.kind < 0.90 OR r.kind >= 0.95 THEN (SELECT id FROM sources WHERE code = 'bench_official')
              ELSE (SELECT id FROM sources WHERE code = 'bench_ir') END AS source_id
  FROM rel r;

INSERT INTO source_documents (id, source_id, external_id, url, title, publisher, document_date,
                              observed_at, content_hash)
SELECT d.id, d.source_id, d.id::text,
       CASE WHEN d.kind >= 0.95 THEN '' ELSE 'https://www.sec.gov/Archives/bench/' || d.id || '.htm' END,
       'doc', CASE WHEN d.kind >= 0.90 AND d.kind < 0.95 THEN 'Bench IR' ELSE 'SEC EDGAR' END,
       now(), now(), d.id::text
FROM doc d;

INSERT INTO relationship_evidence (relationship_id, source_document_id, role, locator, support_excerpt)
SELECT d.rid, d.id, 'supports', 'p.1', 'bench excerpt ' || repeat('x', 200) FROM doc d;
"""


def run(*args: str, env: dict[str, str]) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT, env={**os.environ, **env})


def with_db(dsn: str, name: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(path=f"/{name}"))


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--admin-dsn", required=True, help="能 CREATE DATABASE 的连接串")
    parser.add_argument("--entities", type=int, default=20_000)
    parser.add_argument("--relationships", type=int, default=150_000)
    parser.add_argument("--requests", type=int, default=300, help="每个类别的请求数")
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=160)
    parser.add_argument("--max-edges", type=int, default=320)
    parser.add_argument("--http", action="store_true", help="起真 uvicorn，用回环 HTTP 测")
    parser.add_argument("--keep", action="store_true", help="测完不删库")
    args = parser.parse_args()

    bench_dsn = with_db(args.admin_dsn, DB_NAME)
    with psycopg.connect(args.admin_dsn, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
        admin.execute(f"CREATE DATABASE {DB_NAME}")
    try:
        env = {"DATABASE_URL": bench_dsn}
        run("scripts/migrate.py", "upgrade", env=env)
        run("scripts/load_seed_catalogs.py", env=env)
        t0 = time.monotonic()
        with psycopg.connect(bench_dsn) as conn:
            # 无参数执行 = 简单协议，可以一次跑多条语句；n、r 是整数，直接拼进去。
            conn.execute(
                GENERATE_SQL.replace("%(n)s", str(int(args.entities))).replace(
                    "%(r)s", str(int(args.relationships))
                )
            )
            conn.commit()
        print(f"seeded in {time.monotonic() - t0:.1f}s", file=sys.stderr)
        with psycopg.connect(bench_dsn) as conn:
            conn.execute((ROOT / "apps/api/deploy/indexes.sql").read_text(encoding="utf-8"))
            conn.commit()
            conn.execute("ANALYZE")
            conn.commit()
            reader_sql = (ROOT / "apps/api/deploy/readonly_role.sql").read_text(encoding="utf-8")
            conn.execute(reader_sql)
            conn.execute("ALTER ROLE eei_reader PASSWORD 'bench'")
            conn.commit()
            totals = conn.execute(
                "SELECT (SELECT count(*) FROM entities), (SELECT count(*) FROM relationships),"
                " (SELECT count(*) FROM relationship_evidence)"
            ).fetchone()
            # 枢纽：度最大的 5 个；中位：度排在中间；随机：研究目标里随机取
            hubs = [r[0] for r in conn.execute(
                "SELECT e.id::text FROM entities e JOIN (SELECT subject_entity_id AS id, count(*) c"
                " FROM relationships GROUP BY 1 ORDER BY 2 DESC LIMIT 5) d ON d.id = e.id"
                " ORDER BY d.c DESC"
            ).fetchall()]
            degrees = [r[1] for r in conn.execute(
                "SELECT e.id::text, count(*) FROM entities e JOIN relationships r"
                " ON r.subject_entity_id = e.id OR r.object_entity_id = e.id"
                " WHERE e.status = 'research_target' GROUP BY 1 ORDER BY 2 DESC"
            ).fetchall()]
            median = [r[0] for r in conn.execute(
                "SELECT e.id::text FROM entities e WHERE e.status = 'research_target'"
                " ORDER BY random() LIMIT %s", (args.requests,)
            ).fetchall()]
            max_degree = conn.execute(
                "SELECT max(c) FROM (SELECT count(*) c FROM relationships GROUP BY subject_entity_id) x"
            ).fetchone()[0]
        reader_dsn = psycopg.conninfo.make_conninfo(
            bench_dsn, user="eei_reader", password="bench"
        )
        categories = {"hub": (hubs * args.requests)[: args.requests], "random_research_target": median}
        results: dict[str, dict[str, float]] = {}
        body_for = lambda entity: {  # noqa: E731
            "focus": {"object_type": "entity", "object_id": entity},
            "active_layers": [], "direction": "both", "hops": args.hops, "filters": {},
            "budget": {"max_nodes": args.max_nodes, "max_edges": args.max_edges, "expand_nodes": 40},
        }
        server = None
        if args.http:
            port = 18765
            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "apps.api.app.public_main:app",
                 "--port", str(port), "--log-level", "warning"],
                cwd=ROOT,
                env={**os.environ, "DATABASE_URL": reader_dsn, "EEI_DB_POOL_SIZE": "4"},
            )
            import httpx

            client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
            for _ in range(60):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.5)
            post = lambda entity: client.post("/v1/explore", json=body_for(entity))  # noqa: E731
        else:
            from fastapi.testclient import TestClient

            from apps.api.app.public.app import create_public_app
            from apps.api.app.public.settings import PublicSettings

            app = create_public_app(PublicSettings(database_url=reader_dsn, db_pool_size=4),
                                    warm_up=False)
            client = TestClient(app)
            post = lambda entity: client.post("/v1/explore", json=body_for(entity))  # noqa: E731
        try:
            for entity in hubs[:1]:  # 预热（连接、计划缓存）
                post(entity)
            sizes: list[int] = []
            for label, entities in categories.items():
                latencies: list[float] = []
                for entity in entities:
                    start = time.perf_counter()
                    response = post(entity)
                    latencies.append((time.perf_counter() - start) * 1000)
                    assert response.status_code == 200, response.text[:300]
                    sizes.append(len(response.json()["edges"]))
                results[label] = {
                    "n": len(latencies),
                    "p50_ms": round(percentile(latencies, 0.50), 1),
                    "p95_ms": round(percentile(latencies, 0.95), 1),
                    "p99_ms": round(percentile(latencies, 0.99), 1),
                    "max_ms": round(max(latencies), 1),
                    "mean_ms": round(statistics.fmean(latencies), 1),
                }
        finally:
            if server:
                server.terminate()
        summary = {
            "mode": "http(uvicorn, loopback)" if args.http else "in-process",
            "dataset": {"entities": totals[0], "relationships": totals[1],
                        "evidence_rows": totals[2], "max_subject_degree": max_degree,
                        "top_hubs_benchmarked": len(hubs)},
            "request": {"hops": args.hops, "max_nodes": args.max_nodes, "max_edges": args.max_edges},
            "edges_returned": {"mean": round(statistics.fmean(sizes), 1), "max": max(sizes)},
            "results": results,
            "p95_target_ms": 1500,
            "p95_within_target": all(v["p95_ms"] < 1500 for v in results.values()),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["p95_within_target"] else 1
    finally:
        if not args.keep:
            with psycopg.connect(args.admin_dsn, autocommit=True) as admin:
                admin.execute(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")


if __name__ == "__main__":
    raise SystemExit(main())
