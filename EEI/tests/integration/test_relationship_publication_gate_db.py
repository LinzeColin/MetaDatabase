"""Publication gate against a real PostgreSQL: what the publisher actually selects.

The unit tests prove the rule; this proves the SQL that feeds it - registry tier of
each evidence source, the evidence aggregate, the (created_at, id) backlog cursor
and the UTC-day write budget - on the real schema.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from scripts import publish_to_cloud_channel as publisher
from scripts.db_tools import connect_database

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") and not os.path.exists(".env"),
    reason="DATABASE_URL or .env is required for database integration tests",
)

OFFICIAL_URL = "https://www.sec.gov/Archives/edgar/data/1/gate-test.htm"


@dataclass
class Seeded:
    official_single: str
    non_official_single: str
    official_no_url: str
    entity_ids: list[str]
    source_ids: list[str]


def _entity(connection: Any, name: str) -> str:
    entity_id = str(uuid4())
    connection.execute(
        "INSERT INTO entities (id, canonical_name, entity_type, status)"
        " VALUES (%s, %s, 'legal_entity', 'research_target')",
        (entity_id, name),
    )
    return entity_id


def _source(connection: Any, code: str, tier: int) -> str:
    return str(
        connection.execute(
            "INSERT INTO sources (code, name, base_url, source_tier, active)"
            " VALUES (%s, %s, 'https://example.test', %s, true) RETURNING id",
            (code, code, tier),
        ).fetchone()[0]
    )


def _relationship(
    connection: Any, subject: str, obj: str, source_id: str, *, url: str, publisher_name: str
) -> str:
    relationship_id = str(uuid4())
    # Any catalogued (type, family) pair: the FK catalogs come from the seed load.
    catalogued = connection.execute(
        "SELECT relationship_type, family_key FROM relationship_type_catalog"
        " ORDER BY relationship_type LIMIT 1"
    ).fetchone()
    if catalogued is None:
        pytest.skip("relationship catalogs are not seeded in this database")
    connection.execute(
        "INSERT INTO relationships (id, subject_entity_id, object_entity_id,"
        " relationship_type, relationship_family, status, confidence, observed_at,"
        " derivation_rule, derivation_version)"
        " VALUES (%s, %s, %s, %s, %s, 'reported', 0.9, now(), %s, 'gate-test')",
        (relationship_id, subject, obj, catalogued[0], catalogued[1],
         publisher.AUTHORITATIVE_RULE),
    )
    document_id = connection.execute(
        "INSERT INTO source_documents (source_id, external_id, url, title, publisher,"
        " observed_at, content_hash) VALUES (%s, %s, %s, 'doc', %s, now(), %s)"
        " RETURNING id",
        (source_id, str(uuid4()), url, publisher_name, str(uuid4())),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO relationship_evidence (relationship_id, source_document_id, role,"
        " locator, support_excerpt) VALUES (%s, %s, 'supports', 'p.1', 'excerpt')",
        (relationship_id, document_id),
    )
    return relationship_id


@pytest.fixture()
def seeded() -> Iterator[Seeded]:
    suffix = uuid4().hex[:8]
    with connect_database() as connection:
        official = _source(connection, f"gate_test_official_{suffix}", 1)
        company_ir = _source(connection, f"gate_test_ir_{suffix}", 2)
        parent, child_a, child_b, child_c = (
            _entity(connection, f"Gate Test {suffix} {label}")
            for label in ("Parent", "A", "B", "C")
        )
        a = _relationship(
            connection, child_a, parent, official, url=OFFICIAL_URL, publisher_name="GateTest SEC"
        )
        b = _relationship(
            connection, child_b, parent, company_ir,
            url="https://ir.example.test/x", publisher_name="GateTest IR",
        )
        c = _relationship(
            connection, child_c, parent, official, url="", publisher_name="GateTest SEC"
        )
        connection.commit()
    seeded_rows = Seeded(a, b, c, [parent, child_a, child_b, child_c], [official, company_ir])
    try:
        yield seeded_rows
    finally:
        with connect_database() as connection:
            rel_ids = [seeded_rows.official_single, seeded_rows.non_official_single,
                       seeded_rows.official_no_url]
            connection.execute(
                "DELETE FROM relationship_evidence WHERE relationship_id = ANY(%s::uuid[])",
                (rel_ids,),
            )
            connection.execute("DELETE FROM relationships WHERE id = ANY(%s::uuid[])", (rel_ids,))
            connection.execute(
                "DELETE FROM source_documents WHERE source_id = ANY(%s::uuid[])",
                (seeded_rows.source_ids,),
            )
            connection.execute(
                "DELETE FROM sources WHERE id = ANY(%s::uuid[])", (seeded_rows.source_ids,)
            )
            connection.execute(
                "DELETE FROM entities WHERE id = ANY(%s::uuid[])", (seeded_rows.entity_ids,)
            )
            connection.commit()


def test_gate_selects_official_single_source_only(seeded: Seeded) -> None:
    stats: dict[str, int] = {}
    with connect_database() as connection:
        decisions = {
            str(raw[0]): (relationship, decision)
            for raw, relationship, _evidence, decision in publisher.iter_gated_relationships(
                connection, stats=stats
            )
        }
    published, decision = decisions[seeded.official_single]
    assert published is not None
    assert published["evidence_tier"] == "single_official"
    assert decision.reason == "official_single_source"

    rejected, decision = decisions[seeded.non_official_single]
    assert rejected is None
    assert decision.reason == "non_official_needs_human_review"

    rejected, decision = decisions[seeded.official_no_url]
    assert rejected is None
    assert decision.reason == "official_source_missing_url"
    assert stats["official_single_source"] >= 1


class RecordingTransport(publisher.WorkerApiTransport):
    """Stands in for the D1 channel: records SQL, answers the probes."""

    instances: list[RecordingTransport] = []

    def __init__(self, url: str, token: str) -> None:  # noqa: D107
        self.statements: list[str] = []
        self.requests = 0
        self.bytes_sent = 0
        RecordingTransport.instances.append(self)

    def close(self) -> None:  # noqa: D102
        return None

    def ensure_relationship_schema(self) -> str:  # noqa: D102
        return "current"

    def execute(self, statements: list[str]) -> list[dict[str, Any]]:  # noqa: D102
        out: list[dict[str, Any]] = []
        for statement in statements:
            self.requests += 1
            if statement.startswith("SELECT count(*)"):
                out.append({"rows": [{"n": 1, "newest": "2026-09-30T00:00:00+00:00"}]})
            else:
                self.statements.append(statement)
                out.append({})
        return out

    def apply_statements(self, statements: Any) -> None:  # noqa: D102
        self.statements.extend(statements)


def _backlog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    RecordingTransport.instances.clear()
    monkeypatch.setattr(publisher, "WorkerApiTransport", RecordingTransport)
    return publisher.push_relationship_backlog(
        publish_url="https://example.test/exec",
        publish_token="t",
        state_path=tmp_path / "relpub.json",
        **kwargs,
    )


def test_backlog_publishes_only_gated_rows_then_is_idempotent(
    seeded: Seeded, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = _backlog(monkeypatch, tmp_path, max_relationships=100_000)
    sql = "\n".join(RecordingTransport.instances[0].statements)
    assert seeded.official_single in sql
    assert seeded.non_official_single not in sql
    assert seeded.official_no_url not in sql
    assert OFFICIAL_URL in sql, "the evidence row carries the original link"
    assert "'single_official'" in sql
    assert first["published"] >= 1
    assert first["rows_written_today"] >= first["published"]

    # Same state file again: the cursor is at the end, nothing more to push.
    RecordingTransport.instances.clear()
    monkeypatch.setattr(publisher, "WorkerApiTransport", RecordingTransport)
    second = publisher.push_relationship_backlog(
        publish_url="https://example.test/exec", publish_token="t",
        state_path=tmp_path / "relpub.json", max_relationships=100_000,
    )
    assert second["published"] == 0


def test_backlog_respects_the_daily_write_budget(
    seeded: Seeded, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exhausted = _backlog(monkeypatch, tmp_path, daily_write_budget=0, max_relationships=1000)
    assert exhausted["skipped"] == "daily_write_budget_exhausted"
    assert exhausted["published"] == 0
    assert not RecordingTransport.instances, "no D1 request when the budget is spent"

    one = _backlog(
        monkeypatch, tmp_path,
        daily_write_budget=publisher.WRITES_PER_PUBLISHED_RELATIONSHIP,
        max_relationships=1000,
    )
    assert one["published"] == 1
