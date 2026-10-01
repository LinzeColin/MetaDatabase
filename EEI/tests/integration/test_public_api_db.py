"""公开数据接口（apps/api/app/public）对真实 Postgres：发布门、契约、只读。

夹具自造：每个测试模块一套带随机后缀的实体/关系/事件，结束时只删自己造的行。
覆盖的是「未过门的东西绝不出现」——explore / evidence / 评分解释 / 变更流 / 模块概览 / 事件 /
实体检索 / 脉搏 —— 以及只读角色、写入路由默认关闭、契约与 worker.mjs 逐路由对得上。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from apps.api.app.public.app import create_public_app
from apps.api.app.public.db import PublicDatabase
from apps.api.app.public.settings import PublicSettings
from scripts.db_tools import connect_database
from scripts.publish_to_cloud_channel import AUTHORITATIVE_RULE, PUBLISHED_RULE

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") and not os.path.exists(".env"),
    reason="DATABASE_URL or .env is required for database integration tests",
)

ROOT = Path(__file__).resolve().parents[2]
READER_PASSWORD = "reader-test-only"  # noqa: S105 - 仅用于本地一次性测试库
OFFICIAL_URL = "https://www.sec.gov/Archives/edgar/data/1/public-api-test.htm"


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@dataclass
class World:
    suffix: str
    focus: str
    e1: str
    e2: str
    e4: str
    e3: str
    e5: str
    e6: str
    e7: str
    e8: str
    lonely: str
    published: dict[str, str]  # 名字 -> 关系 id（应当可见）
    hidden: dict[str, str]  # 名字 -> 关系 id（必须不可见）
    event_published: str
    event_hidden: dict[str, str]
    entity_ids: list[str]
    source_ids: list[str]
    relationship_ids: list[str]
    event_ids: list[str]


def _run_script(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT, text=True)


@pytest.fixture(scope="module", autouse=True)
def provisioned_database() -> Iterator[None]:
    """迁移测试会把库留在「已降级」状态：没表就升级+灌目录，用完还原成原样。"""
    with connect_database() as connection:
        present = connection.execute("SELECT to_regclass('public.sources')").fetchone()[0]
    if present is not None:
        yield
        return
    _run_script("scripts/migrate.py", "upgrade")
    _run_script("scripts/load_seed_catalogs.py")
    try:
        yield
    finally:
        _run_script("scripts/migrate.py", "downgrade", "--all")


def _owner_dsn() -> str:
    with connect_database() as connection:
        return connection.info.dsn


@pytest.fixture(scope="module")
def reader_dsn(provisioned_database: None) -> str:
    """按 readonly_role.sql 建 eei_reader（也就是在测试这份 SQL 本身），再拼出它的连接串。"""
    sql = (ROOT / "apps/api/deploy/readonly_role.sql").read_text(encoding="utf-8")
    with connect_database() as connection:
        connection.execute(sql)
        connection.execute(f"ALTER ROLE eei_reader PASSWORD '{READER_PASSWORD}'")
        connection.commit()
        info = conninfo_to_dict(connection.info.dsn)
        # dsn 里不含密码；从环境里的 DATABASE_URL 取 host/port/dbname
    base = conninfo_to_dict(os.environ.get("DATABASE_URL") or _dotenv_database_url())
    return make_conninfo(
        host=base.get("host") or info.get("host"),
        port=base.get("port") or info.get("port"),
        dbname=base.get("dbname") or info.get("dbname"),
        user="eei_reader",
        password=READER_PASSWORD,
    )


def _dotenv_database_url() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("DATABASE_URL not found")


def _settings(dsn: str, **overrides: Any) -> PublicSettings:
    base: dict[str, Any] = {
        "database_url": dsn,
        "db_pool_size": 2,
        "surface_stats_ttl_seconds": 5,
        "pulse_ttl_seconds": 1,
    }
    base.update(overrides)
    return PublicSettings(**base)


@pytest.fixture()
def client(reader_dsn: str, world: World) -> Iterator[TestClient]:
    app = create_public_app(_settings(reader_dsn), warm_up=False)
    with TestClient(app) as test_client:
        yield test_client
    app.state.public.db.close()


def _entity(c: Any, name: str, *, status: str = "active") -> str:
    entity_id = str(uuid4())
    c.execute(
        "INSERT INTO entities (id, canonical_name, entity_type, status)"
        " VALUES (%s, %s, 'legal_entity', %s)",
        (entity_id, name, status),
    )
    return entity_id


def _source(c: Any, code: str, tier: int, *, active: bool = True) -> str:
    return str(
        c.execute(
            "INSERT INTO sources (code, name, base_url, source_tier, active)"
            " VALUES (%s, %s, 'https://example.test', %s, %s) RETURNING id",
            (code, code, tier, active),
        ).fetchone()[0]
    )


def _document(c: Any, source_id: str, url: str, publisher: str) -> str:
    return str(
        c.execute(
            "INSERT INTO source_documents (source_id, external_id, url, title, publisher,"
            " document_date, observed_at, content_hash)"
            " VALUES (%s, %s, %s, 'doc', %s, now(), now(), %s) RETURNING id",
            (source_id, str(uuid4()), url, publisher, str(uuid4())),
        ).fetchone()[0]
    )


def _type_for(c: Any, family: str | None = None) -> tuple[str, str]:
    row = c.execute(
        "SELECT relationship_type, family_key FROM relationship_type_catalog"
        " WHERE (%s::text IS NULL OR family_key = %s) ORDER BY relationship_type LIMIT 1",
        (family, family),
    ).fetchone()
    if row is None:
        pytest.skip("relationship catalogs are not seeded in this database")
    return row[0], row[1]


def _relationship(
    c: Any,
    subject: str,
    obj: str,
    *,
    rule: str,
    evidence: list[tuple[str, str, str]],
    family: str | None = None,
    status: str = "reported",
    role: str = "supports",
) -> str:
    """evidence: [(source_id, url, publisher)]。"""
    relationship_id = str(uuid4())
    rel_type, rel_family = _type_for(c, family)
    c.execute(
        "INSERT INTO relationships (id, subject_entity_id, object_entity_id, relationship_type,"
        " relationship_family, status, confidence, observed_at, derivation_rule,"
        " derivation_version, qualifiers)"
        " VALUES (%s, %s, %s, %s, %s, %s, 0.9, now(), %s, 'public-api-test',"
        ' \'{"owner_actor": "secret-person@example.test", "parser_version": "p1"}\')',
        (relationship_id, subject, obj, rel_type, rel_family, status, rule),
    )
    for source_id, url, publisher in evidence:
        document_id = _document(c, source_id, url, publisher)
        c.execute(
            "INSERT INTO relationship_evidence (relationship_id, source_document_id, role,"
            " locator, support_excerpt) VALUES (%s, %s, %s, 'p.1', 'excerpt')",
            (relationship_id, document_id, role),
        )
    return relationship_id


@pytest.fixture(scope="module")
def world(provisioned_database: None) -> Iterator[World]:
    suffix = uuid4().hex[:8]
    with connect_database() as c:
        official = _source(c, f"pa_official_{suffix}", 1)
        inactive_official = _source(c, f"pa_inactive_{suffix}", 1, active=False)
        ir = _source(c, f"pa_ir_{suffix}", 2)
        news = _source(c, f"pa_news_{suffix}", 3)
        focus = _entity(c, f"PubApi {suffix} Focus", status="research_target")
        e1, e2, e3, e4, e5, e6, e7, e8, lonely = (
            _entity(c, f"PubApi {suffix} {n}")
            for n in ("One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Lonely")
        )
        published = {
            # 官方一手来源 + 可打开原文：单来源即可上图
            "official_single": _relationship(
                c,
                focus,
                e1,
                rule=AUTHORITATIVE_RULE,
                evidence=[(official, OFFICIAL_URL, "SEC EDGAR")],
            ),
            # 非官方，走复核流水线，两家独立来源
            "reviewed_multi": _relationship(
                c,
                focus,
                e2,
                rule=PUBLISHED_RULE,
                evidence=[
                    (ir, "https://ir.example.test/a", "Acme IR"),
                    (news, "https://news.example.test/a", "Example News"),
                ],
                family="ownership_control",
            ),
            # 第二跳
            "hop2": _relationship(
                c,
                e1,
                e4,
                rule=AUTHORITATIVE_RULE,
                evidence=[(official, OFFICIAL_URL + "?hop2", "SEC EDGAR")],
                family="supply_chain_operations",
            ),
            "policy": _relationship(
                c,
                focus,
                e8,
                rule=AUTHORITATIVE_RULE,
                evidence=[(official, OFFICIAL_URL + "?policy", "SEC EDGAR")],
                family="government_policy",
            ),
        }
        hidden = {
            # 非官方单来源且没走复核：不够
            "non_official_single": _relationship(
                c,
                focus,
                e3,
                rule=AUTHORITATIVE_RULE,
                evidence=[(ir, "https://ir.example.test/b", "Acme IR")],
            ),
            # 官方来源但没有可打开的原文链接
            "official_no_url": _relationship(
                c, focus, e5, rule=AUTHORITATIVE_RULE, evidence=[(official, "", "SEC EDGAR")]
            ),
            # 没有任何证据（草稿）
            "no_evidence": _relationship(c, focus, e6, rule=AUTHORITATIVE_RULE, evidence=[]),
            # 只有 contradicts 证据，没有 supports
            "contradicts_only": _relationship(
                c,
                focus,
                e6,
                rule=AUTHORITATIVE_RULE,
                evidence=[(official, OFFICIAL_URL + "?c", "SEC EDGAR")],
                role="contradicts",
            ),
            # 来源已停用：官方等级不作数，又没走复核
            "inactive_source": _relationship(
                c,
                focus,
                e7,
                rule=AUTHORITATIVE_RULE,
                evidence=[(inactive_official, OFFICIAL_URL + "?i", "SEC EDGAR")],
            ),
            # 夹具/其它派生规则：发布端从不取
            "wrong_rule": _relationship(
                c,
                focus,
                e7,
                rule="synthetic_fixture",
                evidence=[(official, OFFICIAL_URL + "?w", "SEC EDGAR")],
            ),
            # 已被取代
            "superseded": _relationship(
                c,
                focus,
                e7,
                rule=AUTHORITATIVE_RULE,
                status="superseded",
                evidence=[(official, OFFICIAL_URL + "?s", "SEC EDGAR")],
            ),
            # 复核流水线的关系，但只有一家非官方来源
            "reviewed_single": _relationship(
                c,
                focus,
                e7,
                rule=PUBLISHED_RULE,
                evidence=[(ir, "https://ir.example.test/c", "Acme IR")],
            ),
        }

        def event(
            title: str,
            *,
            rule: str,
            amount: float | None,
            with_evidence: bool,
            status: str = "reported",
        ) -> str:
            event_id = str(uuid4())
            c.execute(
                "INSERT INTO events (id, event_type, title, status, observed_at, amount,"
                " currency, amount_kind, derivation_rule, derivation_version, announced_at,"
                " qualifiers) VALUES (%s, 'sec_filing', %s, %s, now(), %s, %s, %s, %s,"
                ' \'public-api-test\', now(), \'{"owner_actor": "x", "parser_version": "p"}\')',
                (
                    event_id,
                    title,
                    status,
                    amount,
                    "USD" if amount else None,
                    "reported_total" if amount else None,
                    rule,
                ),
            )
            c.execute(
                "INSERT INTO event_participants (event_id, entity_id, role, direction)"
                " VALUES (%s, %s, 'filer', 'out')",
                (event_id, focus),
            )
            if with_evidence:
                document_id = _document(c, official, OFFICIAL_URL + f"?e={event_id}", "SEC EDGAR")
                c.execute(
                    "INSERT INTO event_evidence (event_id, source_document_id, role, locator,"
                    " support_excerpt) VALUES (%s, %s, 'supports', 'p.2', 'event excerpt')",
                    (event_id, document_id),
                )
            return event_id

        event_published = event(
            f"PubApi {suffix} filing", rule=AUTHORITATIVE_RULE, amount=1250.0, with_evidence=True
        )
        event_hidden = {
            "no_evidence": event(
                f"PubApi {suffix} draft", rule=AUTHORITATIVE_RULE, amount=1.0, with_evidence=False
            ),
            "wrong_rule": event(
                f"PubApi {suffix} fixture", rule="synthetic_fixture", amount=2.0, with_evidence=True
            ),
            "superseded": event(
                f"PubApi {suffix} old",
                rule=AUTHORITATIVE_RULE,
                amount=3.0,
                with_evidence=True,
                status="superseded",
            ),
        }
        c.commit()
        rel_ids = [*published.values(), *hidden.values()]
        world_data = World(
            suffix=suffix,
            focus=focus,
            e1=e1,
            e2=e2,
            e4=e4,
            e3=e3,
            e5=e5,
            e6=e6,
            e7=e7,
            e8=e8,
            lonely=lonely,
            published=published,
            hidden=hidden,
            event_published=event_published,
            event_hidden=event_hidden,
            entity_ids=[focus, e1, e2, e3, e4, e5, e6, e7, e8, lonely],
            source_ids=[official, inactive_official, ir, news],
            relationship_ids=rel_ids,
            event_ids=[event_published, *event_hidden.values()],
        )
    try:
        yield world_data
    finally:
        with connect_database() as c:
            c.execute(
                "DELETE FROM event_evidence WHERE event_id = ANY(%s::uuid[])",
                (world_data.event_ids,),
            )
            c.execute(
                "DELETE FROM event_participants WHERE event_id = ANY(%s::uuid[])",
                (world_data.event_ids,),
            )
            c.execute("DELETE FROM events WHERE id = ANY(%s::uuid[])", (world_data.event_ids,))
            c.execute(
                "DELETE FROM relationship_evidence WHERE relationship_id = ANY(%s::uuid[])",
                (world_data.relationship_ids,),
            )
            c.execute(
                "DELETE FROM relationships WHERE id = ANY(%s::uuid[])",
                (world_data.relationship_ids,),
            )
            c.execute(
                "DELETE FROM source_documents WHERE source_id = ANY(%s::uuid[])",
                (world_data.source_ids,),
            )
            c.execute("DELETE FROM sources WHERE id = ANY(%s::uuid[])", (world_data.source_ids,))
            c.execute("DELETE FROM entities WHERE id = ANY(%s::uuid[])", (world_data.entity_ids,))
            c.commit()


def _explore(client: TestClient, world: World, **overrides: Any) -> dict[str, Any]:
    body = {
        "focus": {"object_type": "entity", "object_id": world.focus},
        "active_layers": [],
        "direction": "both",
        "hops": 1,
        "filters": {},
        "budget": {"max_nodes": 160, "max_edges": 320, "expand_nodes": 40},
    }
    body.update(overrides)
    response = client.post("/v1/explore", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 发布门：未过门的东西绝不出现
# ---------------------------------------------------------------------------


def test_explore_serves_only_gated_relationships_with_tier(
    client: TestClient, world: World
) -> None:
    payload = _explore(client, world)
    edges = {edge["id"]: edge for edge in payload["edges"]}

    assert set(edges) == {
        world.published["official_single"],
        world.published["reviewed_multi"],
        world.published["policy"],
    }
    assert edges[world.published["official_single"]]["evidence_tier"] == "single_official"
    assert edges[world.published["official_single"]]["source_url"] == OFFICIAL_URL
    assert edges[world.published["official_single"]]["source_publisher"] == "SEC EDGAR"
    assert edges[world.published["reviewed_multi"]]["evidence_tier"] == "multi_source"
    assert edges[world.published["reviewed_multi"]]["evidence_count"] == 2
    # 节点只来自已过门的边：被拒关系的另一端不会被带出来
    node_ids = {node["id"] for node in payload["nodes"]}
    assert node_ids == {world.focus, world.e1, world.e2, world.e8}
    for hidden_entity in (world.e3, world.e5, world.e6, world.e7):
        assert hidden_entity not in node_ids
    assert payload["production_context"]["publication_policy"]["official_single_source_publishable"]


def test_explore_hops_two_reaches_second_ring(client: TestClient, world: World) -> None:
    one = _explore(client, world, hops=1)
    two = _explore(client, world, hops=2)

    assert world.published["hop2"] not in {edge["id"] for edge in one["edges"]}
    assert world.published["hop2"] in {edge["id"] for edge in two["edges"]}
    assert world.e4 in {node["id"] for node in two["nodes"]}
    assert two["query"]["hops"] == 2


def test_explore_budget_truncation_counts_only_published_edges(
    client: TestClient, world: World
) -> None:
    payload = _explore(client, world, budget={"max_nodes": 160, "max_edges": 2, "expand_nodes": 4})

    assert len(payload["edges"]) == 2
    assert payload["truncated"] is True
    assert payload["truncation"]["reasons"] == ["edge_budget"]
    assert payload["continuation"]["expand_endpoint"] == "/v1/explore/expand"


def test_explore_directions_and_expand_reroot(client: TestClient, world: World) -> None:
    downstream = _explore(client, world, direction="downstream")
    assert {edge["subject_id"] for edge in downstream["edges"]} == {world.focus}
    upstream = _explore(client, world, direction="upstream")
    assert upstream["edges"] == []

    expanded = client.post(
        "/v1/explore/expand",
        json={"anchor_entity_id": world.e1, "budget": {"max_nodes": 10, "expand_nodes": 10}},
    )
    assert expanded.status_code == 200
    assert {edge["id"] for edge in expanded.json()["edges"]} == {
        world.published["official_single"],
        world.published["hop2"],
    }
    rerooted = client.post("/v1/explore/reroot", json={"new_focus_entity_id": world.e4})
    assert rerooted.status_code == 200
    assert rerooted.json()["focus"]["id"] == world.e4


def test_explore_focus_that_is_not_published_is_404(client: TestClient, world: World) -> None:
    # e3 只出现在一条被拒的关系里：它在发布面上不存在
    response = client.post(
        "/v1/explore", json={"focus": {"object_type": "entity", "object_id": world.e3}}
    )
    assert response.status_code == 404
    bogus = client.post(
        "/v1/explore", json={"focus": {"object_type": "entity", "object_id": "not-a-uuid"}}
    )
    assert bogus.status_code == 404
    assert client.post("/v1/explore", json={}).status_code == 400
    assert client.post("/v1/explore/expand", json={}).status_code == 400
    assert client.post("/v1/explore/reroot", json={}).status_code == 400


def test_relationship_evidence_and_explanation_hide_unpublished(
    client: TestClient, world: World
) -> None:
    published = world.published["official_single"]
    evidence = client.get(f"/v1/evidence/relationship/{published}").json()
    assert evidence["evidence_tier"] == "single_official"
    assert evidence["evidence_count"] == 1
    assert evidence["evidence"][0]["source_url"] == OFFICIAL_URL
    assert set(evidence["evidence"][0]) == {
        "relationship_id",
        "source_document_id",
        "role",
        "locator",
        "support_excerpt",
        "source_url",
        "source_title",
        "publisher",
        "document_date",
    }
    explanation = client.get(f"/v1/scoring/relationship/{published}/explanation").json()
    assert explanation["evidence_tier"] == "single_official"
    assert explanation["source_threshold"]["met"] is True
    assert explanation["subject"]["entity_id"] == world.focus

    for name, relationship_id in world.hidden.items():
        assert client.get(f"/v1/evidence/relationship/{relationship_id}").status_code == 404, name
        assert (
            client.get(f"/v1/scoring/relationship/{relationship_id}/explanation").status_code == 404
        ), name
    assert client.get("/v1/evidence/relationship/not-a-uuid").status_code == 404


def test_public_qualifiers_never_carry_private_identifiers(
    client: TestClient, world: World
) -> None:
    explanation = client.get(
        f"/v1/scoring/relationship/{world.published['official_single']}/explanation"
    ).json()
    assert "owner_actor" not in explanation["qualifiers"]
    assert (
        "secret-person"
        not in client.get(
            f"/v1/scoring/relationship/{world.published['official_single']}/explanation"
        ).text
    )
    assert (
        explanation["qualifiers"]["source_threshold_policy"]["policy"] == "official_single_source"
    )


def test_changes_feed_lists_published_only(client: TestClient, world: World) -> None:
    changes = client.get("/v1/changes").json()
    ids = {item["id"] for item in changes}
    assert world.published["official_single"] in ids
    assert ids.isdisjoint(world.hidden.values())
    item = next(i for i in changes if i["id"] == world.published["official_single"])
    assert item["change_type"] == "relationship_published"
    assert item["new_value"]["subject_name"] == f"PubApi {world.suffix} Focus"
    assert client.get("/v1/changes", params={"since": "2999-01-01T00:00:00Z"}).json() == []
    assert client.get("/v1/changes", params={"since": "garbage"}).status_code == 400


def test_module_overviews_exclude_unpublished(client: TestClient, world: World) -> None:
    control = client.get("/v1/control/overview").json()
    assert world.published["reviewed_multi"] in {r["id"] for r in control["relationships"]}
    supply = client.get("/v1/supply-chain/overview").json()
    assert world.published["hop2"] in {r["id"] for r in supply["relationships"]}
    policy = client.get("/v1/policy/overview").json()
    assert world.published["policy"] in {r["id"] for r in policy["policy_relationships"]}
    ma = client.get("/v1/ma/overview").json()
    signals = client.get("/v1/signals/overview").json()
    everything = {
        r["id"]
        for rows in (
            control["relationships"],
            supply["relationships"],
            ma["relationships"],
            signals["relationships"],
            policy["policy_relationships"],
        )
        for r in rows
    }
    assert everything.isdisjoint(world.hidden.values())
    multi = next(
        r for r in control["relationships"] if r["id"] == world.published["reviewed_multi"]
    )
    assert multi["owner_signed_published"] is True
    assert multi["evidence_tier"] == "multi_source"


def test_entity_search_only_finds_published_surface(client: TestClient, world: World) -> None:
    found = client.get("/v1/entities", params={"q": f"PubApi {world.suffix}", "limit": 50}).json()
    names = {e["id"] for e in found["entities"]}
    assert world.focus in names and world.e1 in names and world.e2 in names
    # 只在被拒关系里出现、或根本没有关系的实体：搜不到
    for entity_id in (world.e3, world.e5, world.e6, world.e7, world.lonely):
        assert entity_id not in names
    assert found["query"] == f"PubApi {world.suffix}"
    assert client.get("/v1/entities", params={"q": "  "}).status_code == 400
    assert client.get("/v1/entities").status_code == 400
    # LIKE 元字符按字面匹配；超长词不报错
    assert client.get("/v1/entities", params={"q": "%_%"}).json()["entities"] == []
    assert client.get("/v1/entities", params={"q": "x" * 500}).status_code == 200
    limited = client.get("/v1/entities", params={"q": f"PubApi {world.suffix}", "limit": 1}).json()
    assert len(limited["entities"]) == 1
    # 前缀优先：名字以检索词开头的排在前面
    prefix = client.get("/v1/entities", params={"q": "PubApi"}).json()["entities"]
    assert all(e["canonical_name"].lower().startswith("pubapi") for e in prefix[:1])


def test_empire_requires_a_published_entity(client: TestClient, world: World) -> None:
    ok = client.get(f"/v1/entities/{world.focus}/empire")
    assert ok.status_code == 200
    assert ok.json()["focus"]["id"] == world.focus
    assert ok.json()["data_mode"] == "selfhost_publication"
    assert client.get(f"/v1/entities/{world.e3}/empire").status_code == 404


def test_events_serve_published_only_with_participants_and_amounts(
    client: TestClient, world: World
) -> None:
    events = client.get("/v1/events", params={"entity": world.focus, "limit": 50}).json()
    ids = {e["id"] for e in events}
    assert ids == {world.event_published}
    event = events[0]
    assert event["participants"] == [
        {
            "entity_id": world.focus,
            "entity_name": f"PubApi {world.suffix} Focus",
            "role": "filer",
            "direction": "out",
        }
    ]
    assert event["amount"] == 1250.0
    assert event["amount_semantics"]["state"] == "reported"
    assert event["evidence_count"] == 1
    assert "owner_actor" not in event["qualifiers"]

    summary = client.get("/v1/events/amount-summary", params={"entity": world.focus}).json()
    assert summary["event_count"] == 1
    assert summary["comparable_reported_total"] == 1250.0
    assert summary["filters"]["entity"] == world.focus
    assert summary["cross_bucket_summation_performed"] is False

    detail = client.get(f"/v1/evidence/event/{world.event_published}").json()
    assert detail["schema_version"] == "evidence-detail-v1"
    assert detail["evidence_count"] == 1
    assert detail["evidence"][0]["snippet"]["redaction_status"] == "public"
    for event_id in world.event_hidden.values():
        assert client.get(f"/v1/evidence/event/{event_id}").status_code == 404

    assert client.get("/v1/events", params={"entity": "nope"}).status_code == 400
    assert client.get("/v1/events", params={"from": "garbage"}).status_code == 400
    assert client.get("/v1/events", params={"entity": str(uuid4())}).json() == []


def test_pulse_and_meta_endpoints(client: TestClient, world: World) -> None:
    pulse = client.get("/v1/meta/pulse").json()
    assert pulse["schema_version"] == "eei-data-pulse-v1"
    assert set(pulse) >= {
        "generated_at",
        "data_as_of",
        "last_publish_at",
        "totals",
        "added",
        "series",
        "composition",
        "sources",
        "heartbeat",
    }
    assert pulse["totals"]["relationships"] >= 4
    assert pulse["series"][-1]["relationships"] == pulse["totals"]["relationships"]
    assert {b["bucket"] for b in pulse["composition"]["relationship_family"]} >= {
        "ownership_control",
        "supply_chain_operations",
    }
    assert pulse["heartbeat"]["state"] in {"live", "delayed", "stalled", "unknown"}

    meta = client.get("/v1/publication/meta").json()
    assert meta["published_relationship_count"] == pulse["totals"]["relationships"]
    assert meta["publication_meta"]["publisher_version"].startswith("eei-selfhost-api")

    freshness = client.get("/v1/sources/freshness").json()
    assert freshness["schema_version"] == "cloud-sources-freshness-v1"
    assert any(s["code"] == f"pa_official_{world.suffix}" for s in freshness["sources"])

    build = client.get("/v1/meta/build").json()
    assert {"repo", "commit", "built_at", "deploy_id", "publisher_version"} <= set(build)


def test_published_count_matches_publisher_gate(client: TestClient, world: World) -> None:
    """公开面数的「已发布关系数」必须等于发布端同一份判定数出来的。"""
    from scripts import publish_to_cloud_channel as publisher

    with connect_database() as connection:
        publisher_count = sum(
            1
            for _raw, relationship, _evidence, _decision in publisher.iter_gated_relationships(
                connection
            )
            if relationship is not None
        )
    assert (
        client.get("/v1/publication/meta").json()["published_relationship_count"] == publisher_count
    )


def test_scoring_and_catalog_reference_data(client: TestClient) -> None:
    context = client.get("/v1/scoring/active-context")
    assert context.status_code in {200, 404}
    if context.status_code == 200:
        body = context.json()
        assert body["client_state"] == "current"
        stale = client.get("/v1/scoring/active-context", params={"client_refresh_token": "x"})
        assert stale.json()["client_state"] == "stale"
        assert "activated_by" not in body
    profiles = client.get("/v1/scoring/profiles")
    assert profiles.status_code == 200
    assert isinstance(profiles.json(), list)
    catalogs = client.get("/v1/catalogs").json()
    assert catalogs["catalog_count"] > 0
    key = catalogs["catalogs"][0]["catalog_key"]
    assert client.get(f"/v1/catalogs/{key}").status_code == 200
    assert client.get("/v1/catalogs/no-such-catalog").status_code == 404


# ---------------------------------------------------------------------------
# 契约：worker.mjs 的每条路由，在公开面上要么对得上、要么被明确关掉
# ---------------------------------------------------------------------------

SERVED_GET = {
    "/v1/publication/meta",
    "/v1/meta/pulse",
    "/v1/sources/freshness",
    "/v1/policy/overview",
    "/v1/control/overview",
    "/v1/ma/overview",
    "/v1/signals/overview",
    "/v1/entities",
    "/v1/scoring/active-context",
    "/v1/supply-chain/overview",
    "/v1/changes",
    "/v1/events",
    "/v1/events/amount-summary",
    "/v1/meta/build",
}
SERVED_POST = {"/v1/explore", "/v1/explore/reroot", "/v1/explore/expand"}
DENIED = {
    "/v1/saved-views",
    "/v1/watchlists",
    "/v1/exploration-log",
    "/v1/cloud/runs",
    "/v1/cloud/runs/trigger",
    "/v1/internal/publish/exec",
}


def _worker_literal_routes() -> set[tuple[str, str]]:
    source = (ROOT / "apps/cloudflare-public/src/worker.mjs").read_text(encoding="utf-8")
    return {
        (method, path)
        for path, method in re.findall(
            r'pathname === "(/v1/[^"]+)" && request\.method === "(\w+)"', source
        )
    }


def test_every_worker_route_is_served_or_explicitly_closed(client: TestClient) -> None:
    for method, path in sorted(_worker_literal_routes()):
        if method == "GET" and path in SERVED_GET:
            params = {"q": "x"} if path == "/v1/entities" else None
            response = client.get(path, params=params)
            assert response.status_code == 200, (path, response.text[:200])
        elif method == "POST" and path in SERVED_POST:
            response = client.post(path, json={})
            assert response.status_code == 400, (path, response.status_code)  # 缺必填字段，不是 404
        elif path in DENIED:
            response = client.request(method, path)
            assert response.status_code == 403, (method, path, response.status_code)
        else:
            pytest.fail(f"worker route {method} {path} is neither served nor closed here")


def test_worker_regex_routes_are_served(client: TestClient, world: World) -> None:
    source = (ROOT / "apps/cloudflare-public/src/worker.mjs").read_text(encoding="utf-8")
    for needle in ("/empire$", "/explanation$", r"evidence\/relationship", r"evidence\/event"):
        assert needle in source
    rel = world.published["official_single"]
    assert client.get(f"/v1/entities/{world.focus}/empire").status_code == 200
    assert client.get(f"/v1/scoring/relationship/{rel}/explanation").status_code == 200
    assert client.get(f"/v1/evidence/relationship/{rel}").status_code == 200
    assert client.get(f"/v1/evidence/event/{world.event_published}").status_code == 200


def test_explore_response_fields_match_worker_contract(client: TestClient, world: World) -> None:
    payload = _explore(client, world)
    assert set(payload) == {
        "session_id",
        "focus",
        "query",
        "nodes",
        "edges",
        "truncated",
        "truncation",
        "continuation",
        "warnings",
        "coverage",
        "production_context",
    }
    assert set(payload["edges"][0]) == {
        "id",
        "subject_id",
        "object_id",
        "relationship_type",
        "relationship_family",
        "status",
        "confidence",
        "valid_from",
        "valid_to",
        "evidence_count",
        "evidence_tier",
        "source_url",
        "source_publisher",
        "synthetic",
        "fixture_notice",
    }
    assert set(payload["nodes"][0]) == {
        "id",
        "canonical_name",
        "entity_type",
        "fixture_notice",
        "synthetic",
    }
    assert set(payload["query"]) == {
        "focus",
        "direction",
        "hops",
        "as_of",
        "scoring_profile_version_id",
        "active_layers",
        "filters",
        "budget",
        "hard_limits",
    }
    assert set(payload["truncation"]) == {
        "applied",
        "reasons",
        "message",
        "fetched_edge_count",
        "returned_edge_count",
        "returned_node_count",
    }
    assert set(payload["coverage"]) == {
        "visible_nodes",
        "visible_edges",
        "source_count",
        "relationship_family_count",
        "synthetic_fixture_edges",
    }
    assert payload["session_id"]
    assert (
        client.post(
            "/v1/explore",
            json={"focus": {"object_id": world.focus}, "session_id": "keep-me"},
        ).json()["session_id"]
        == "keep-me"
    )


# ---------------------------------------------------------------------------
# 只读
# ---------------------------------------------------------------------------


def test_reader_role_can_only_select_whitelisted_tables(reader_dsn: str, world: World) -> None:
    with psycopg.connect(reader_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM relationships").fetchone()[0] >= 1
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute(
                "INSERT INTO entities (canonical_name, entity_type) VALUES ('x', 'legal_entity')"
            )
        conn.rollback()
        for forbidden in (
            "saved_views",
            "watchlists",
            "relationship_fact_candidates",
            "manual_review_queue",
            "operation_logs",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT 1 FROM {forbidden} LIMIT 1")
            conn.rollback()
    # 即使绕开「默认只读」，没有写权限也写不了
    with psycopg.connect(reader_dsn, options="-c default_transaction_read_only=off") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM relationships")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE eei_reader_should_not_create (id int)")


def test_readonly_role_sql_is_idempotent(reader_dsn: str) -> None:
    sql = (ROOT / "apps/api/deploy/readonly_role.sql").read_text(encoding="utf-8")
    with connect_database() as connection:
        connection.execute(sql)
        connection.execute(sql)
        connection.commit()
    with psycopg.connect(reader_dsn) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_indexes_sql_is_idempotent(provisioned_database: None) -> None:
    sql = (ROOT / "apps/api/deploy/indexes.sql").read_text(encoding="utf-8")
    with connect_database() as connection:
        connection.execute(sql)
        connection.execute(sql)
        connection.commit()
        found = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE indexname = ANY(%s)",
                (
                    [
                        "relationships_created_idx",
                        "relationships_family_type_idx",
                        "events_public_time_idx",
                        "event_participants_entity_idx",
                    ],
                ),
            ).fetchall()
        }
    assert len(found) == 4


def test_pool_connections_are_read_only_even_for_the_owner_role(
    provisioned_database: None,
) -> None:
    owner = PublicDatabase(
        _settings(
            os.environ.get("DATABASE_URL") or _dotenv_database_url(), require_read_only_role=False
        )
    )
    try:
        with owner.connection() as conn:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                conn.execute(
                    "INSERT INTO entities (canonical_name, entity_type)"
                    " VALUES ('x', 'legal_entity')"
                )
    finally:
        owner.close()


def test_refuses_to_serve_with_a_writable_role(provisioned_database: None, world: World) -> None:
    dsn = os.environ.get("DATABASE_URL") or _dotenv_database_url()
    app = create_public_app(_settings(dsn, require_read_only_role=True), warm_up=False)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        health = test_client.get("/health")
        assert health.status_code == 503
        assert health.json()["status"] == "degraded"
        assert "eei_reader" in health.json()["database"]["detail"]
        assert test_client.get("/v1/changes").status_code == 503
    app.state.public.db.close()


def test_health_reports_ok_and_read_only_role(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == {"ok": True, "detail": "postgresql ready", "read_only_role": True}
    assert body["surface"] == "selfhost_publication"
    assert set(body["build"]) == {"repo", "commit", "built_at", "deploy_id"}
