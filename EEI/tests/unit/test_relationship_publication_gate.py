"""Publication gate: 官方单来源可上图 (Owner ruling 2026-09-30).

Three rules, one place (scripts/relationship_publication_gate.py):
  * official first-hand source + openable original  -> publish, tier single_official
  * non-official single source                       -> do NOT publish
  * official source WITHOUT an openable original     -> do NOT publish
and the original non-official rule (>= 2 independent sources + human review) is
unchanged.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from scripts import publish_to_cloud_channel as publisher
from scripts.relationship_publication_gate import (
    NON_OFFICIAL_MIN_INDEPENDENT_SOURCES,
    REASON_NO_SUPPORTING_EVIDENCE,
    REASON_NON_OFFICIAL_NEEDS_REVIEW,
    REASON_NON_OFFICIAL_NEEDS_TWO,
    REASON_OFFICIAL_MISSING_URL,
    TIER_MULTI_SOURCE,
    TIER_SINGLE_OFFICIAL,
    EvidenceFact,
    evaluate_relationship_gate,
    evidence_facts_from_rows,
    is_openable_url,
)

SEC_URL = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/0001.htm"
GLEIF_URL = "https://api.gleif.org/api/v1/lei-records/549300EXAMPLE"


def fact(
    *,
    tier: int = 1,
    active: bool = True,
    role: str = "supports",
    url: str | None = SEC_URL,
    publisher: str | None = "SEC EDGAR",
    source_id: str | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        source_id=source_id or f"src-{publisher}",
        source_tier=tier,
        source_active=active,
        role=role,
        url=url,
        publisher=publisher,
    )


# --- the three rules the Owner asked to be tested ---------------------------------


def test_official_single_source_is_published_as_single_official() -> None:
    decision = evaluate_relationship_gate([fact()])
    assert decision.publishable is True
    assert decision.evidence_tier == TIER_SINGLE_OFFICIAL
    assert decision.official_source_count == 1
    assert decision.supporting_source_count == 1
    # The cloud score explanation reads this block: one source is enough here.
    policy = decision.as_source_threshold_policy()
    assert policy["minimum_independent_sources"] == 1
    assert policy["policy"] == "official_single_source"


@pytest.mark.parametrize("tier", [2, 3, 4, 5])
def test_non_official_single_source_is_not_published(tier: int) -> None:
    decision = evaluate_relationship_gate(
        [fact(tier=tier, publisher="Company IR")], human_reviewed=False
    )
    assert decision.publishable is False
    assert decision.evidence_tier is None
    assert decision.reason == REASON_NON_OFFICIAL_NEEDS_REVIEW


def test_non_official_single_source_stays_blocked_even_when_reviewed() -> None:
    decision = evaluate_relationship_gate(
        [fact(tier=2, publisher="Company IR")], human_reviewed=True
    )
    assert decision.publishable is False
    assert decision.reason == REASON_NON_OFFICIAL_NEEDS_TWO


@pytest.mark.parametrize(
    "url", [None, "", "   ", "sec.gov/no-scheme", "javascript:alert(1)", "ftp://x/y", "https://"]
)
def test_official_source_without_openable_original_is_not_published(url: str | None) -> None:
    decision = evaluate_relationship_gate([fact(url=url)])
    assert decision.publishable is False
    assert decision.reason == REASON_OFFICIAL_MISSING_URL
    assert decision.evidence_tier is None


# --- boundaries around the rules ---------------------------------------------------


def test_official_is_decided_by_registry_tier_not_by_name() -> None:
    # A source *named* like SEC but registered as a fixture (tier 5) is not official.
    fixture = fact(tier=5, publisher="SEC EDGAR (synthetic)")
    assert evaluate_relationship_gate([fixture]).publishable is False
    # An inactive official source is not official either.
    assert evaluate_relationship_gate([fact(active=False)]).publishable is False


def test_gleif_and_sec_both_qualify() -> None:
    gleif = fact(publisher="Global LEI Foundation", url=GLEIF_URL)
    assert evaluate_relationship_gate([gleif]).evidence_tier == TIER_SINGLE_OFFICIAL


def test_two_independent_sources_label_multi_source_not_single() -> None:
    decision = evaluate_relationship_gate(
        [fact(), fact(publisher="Global LEI Foundation", url=GLEIF_URL)]
    )
    assert decision.publishable is True
    assert decision.evidence_tier == TIER_MULTI_SOURCE
    assert decision.supporting_source_count == 2


def test_two_documents_from_one_official_publisher_are_still_single_source() -> None:
    decision = evaluate_relationship_gate([fact(), fact(url=SEC_URL + "?p=2")])
    assert decision.evidence_tier == TIER_SINGLE_OFFICIAL


def test_only_supporting_evidence_counts() -> None:
    contradicting = fact(role="contradicts")
    decision = evaluate_relationship_gate([contradicting])
    assert decision.publishable is False
    assert decision.reason == REASON_NO_SUPPORTING_EVIDENCE
    assert evaluate_relationship_gate([]).reason == REASON_NO_SUPPORTING_EVIDENCE


def test_original_non_official_rule_is_unchanged() -> None:
    assert NON_OFFICIAL_MIN_INDEPENDENT_SOURCES == 2
    ir = fact(tier=2, publisher="NVIDIA IR", url="https://investor.nvidia.com/x")
    press = fact(tier=3, publisher="TSMC Newsroom", url="https://pr.tsmc.com/y")
    # >= 2 independent publishers AND human review -> published
    assert evaluate_relationship_gate([ir, press], human_reviewed=True).publishable is True
    # two documents, one publisher -> one independent source -> blocked
    same = fact(tier=2, publisher="NVIDIA IR", url="https://investor.nvidia.com/z")
    assert evaluate_relationship_gate([ir, same], human_reviewed=True).publishable is False
    # 2 sources but nobody reviewed -> blocked
    assert evaluate_relationship_gate([ir, press], human_reviewed=False).publishable is False
    # an explicit review override (recorded by the signed pipeline) still counts
    assert (
        evaluate_relationship_gate([ir], human_reviewed=True, review_override=True).publishable
        is True
    )


def test_is_openable_url() -> None:
    assert is_openable_url(SEC_URL)
    assert is_openable_url("http://example.com/a")
    assert not is_openable_url(None)
    assert not is_openable_url("https:///nohost")


def test_evidence_facts_from_rows_adapts_the_sql_aggregate() -> None:
    facts = evidence_facts_from_rows(
        [
            {
                "source_id": "s1",
                "source_tier": 1,
                "source_active": True,
                "role": "supports",
                "url": SEC_URL,
                "publisher": "SEC EDGAR",
                "source_code": "sec_edgar",
            }
        ]
    )
    assert evaluate_relationship_gate(facts).evidence_tier == TIER_SINGLE_OFFICIAL


# --- the publisher applies the gate to real rows -----------------------------------


def raw_row(evidence: list[dict[str, Any]], *, rule: str, qualifiers: dict | None = None) -> tuple:
    return (
        "10000000-0000-4000-8000-000000000001",  # id
        "20000000-0000-4000-8000-000000000001",  # subject
        "20000000-0000-4000-8000-000000000002",  # object
        "subsidiary_of",
        "corporate_structure",
        "reported",
        0.9,
        None,
        None,
        qualifiers or {},
        rule,
        evidence,
    )


def evidence_json(
    *, tier: int = 1, url: str | None = SEC_URL, publisher: str = "SEC EDGAR"
) -> dict:
    return {
        "source_id": f"src-{publisher}",
        "source_code": "x",
        "source_tier": tier,
        "source_active": True,
        "source_document_id": f"doc-{publisher}",
        "role": "supports",
        "locator": "Exhibit 21",
        "support_excerpt": "Subsidiaries of the registrant",
        "url": url,
        "title": "10-K",
        "publisher": publisher,
        "document_date": "2026-02-01T00:00:00+00:00",
    }


def test_publisher_stamps_tier_and_carries_the_original_link() -> None:
    relationship, evidence_rows, decision = publisher.gate_relationship(
        raw_row([evidence_json()], rule=publisher.AUTHORITATIVE_RULE)
    )
    assert decision.publishable
    assert relationship is not None
    assert relationship["evidence_tier"] == TIER_SINGLE_OFFICIAL
    assert [row["source_url"] for row in evidence_rows] == [SEC_URL]
    assert evidence_rows[0]["relationship_id"] == relationship["id"]
    # the qualifier the cloud worker's score explanation reads survives the allowlist
    assert '"minimum_independent_sources": 1' in relationship["qualifiers_json"]


def test_publisher_drops_rejected_relationships_and_their_evidence() -> None:
    relationship, evidence_rows, decision = publisher.gate_relationship(
        raw_row([evidence_json(tier=2, publisher="Some Blog")], rule=publisher.AUTHORITATIVE_RULE)
    )
    assert relationship is None
    assert evidence_rows == []
    assert not decision.publishable
    relationship, evidence_rows, _ = publisher.gate_relationship(
        raw_row([evidence_json(url=None)], rule=publisher.AUTHORITATIVE_RULE)
    )
    assert relationship is None
    assert evidence_rows == []


def test_reviewed_rule_rows_keep_the_two_source_review_rule() -> None:
    two = [
        evidence_json(tier=2, publisher="NVIDIA IR", url="https://investor.nvidia.com/x"),
        evidence_json(tier=3, publisher="TSMC Newsroom", url="https://pr.tsmc.com/y"),
    ]
    relationship, _, _ = publisher.gate_relationship(raw_row(two, rule=publisher.PUBLISHED_RULE))
    assert relationship is not None
    assert relationship["evidence_tier"] == TIER_MULTI_SOURCE
    # the same two sources without the signed-review rule are not enough
    relationship, _, _ = publisher.gate_relationship(
        raw_row(two, rule=publisher.AUTHORITATIVE_RULE)
    )
    assert relationship is None


# --- D1 schema: the column the gate writes must exist -------------------------------


def _relationships_ddl() -> str:
    for statement in publisher.schema_statements():
        if statement.startswith("CREATE TABLE IF NOT EXISTS relationships "):
            return statement
    raise AssertionError("relationships DDL not found")


def test_d1_schema_has_every_published_relationship_column() -> None:
    ddl = _relationships_ddl()
    columns = set(re.findall(r"^\s+(\w+) [A-Z]+", ddl, flags=re.MULTILINE))
    assert set(publisher.RELATIONSHIP_COLUMNS) <= columns
    assert "evidence_tier" in columns
    assert "WITHOUT ROWID" in ddl


class FakeChannel(publisher.WorkerApiTransport):
    """Answers the schema probes from a canned D1 state; records every write."""

    def __init__(self, *, table_sql: str | None, row_count: int = 0) -> None:  # noqa: D107
        self.table_sql = table_sql
        self.row_count = row_count
        self.applied: list[str] = []

    def execute(self, statements: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for statement in statements:
            if "FROM sqlite_master" in statement:
                out.append({"rows": [{"sql": self.table_sql}] if self.table_sql else []})
            elif "count(*)" in statement:
                out.append({"rows": [{"n": self.row_count}]})
            else:
                self.applied.append(statement)
                out.append({})
        return out


def test_schema_upgrade_is_a_noop_when_already_current() -> None:
    channel = FakeChannel(table_sql=_relationships_ddl())
    assert channel.ensure_relationship_schema() == "current"
    assert channel.applied == []


def test_schema_upgrade_rebuilds_an_empty_old_table() -> None:
    old = "CREATE TABLE relationships (id TEXT PRIMARY KEY, qualifiers_json TEXT)"
    channel = FakeChannel(table_sql=old, row_count=0)
    assert channel.ensure_relationship_schema() == "rebuilt_empty"
    joined = "\n".join(channel.applied)
    assert "DROP TABLE IF EXISTS relationship_evidence" in joined
    assert "DROP TABLE IF EXISTS relationships" in joined
    assert "evidence_tier" in joined


def test_schema_upgrade_never_drops_a_populated_table() -> None:
    old = "CREATE TABLE relationships (id TEXT PRIMARY KEY, qualifiers_json TEXT)"
    channel = FakeChannel(table_sql=old, row_count=123)
    assert channel.ensure_relationship_schema() == "column_added"
    assert channel.applied == ["ALTER TABLE relationships ADD COLUMN evidence_tier TEXT;"]


# --- D1 limits: one statement <= 100 kB, evidence never ahead of its relationship ------


def _wide_relationship(index: int) -> dict[str, Any]:
    return {
        "id": f"rel-{index:05d}",
        "subject_entity_id": "s" * 36,
        "object_entity_id": "o" * 36,
        "relationship_type": "subsidiary_of",
        "relationship_family": "corporate_structure",
        "status": "reported",
        "confidence": 0.9,
        "observed_at": "2026-09-30T00:00:00+00:00",
        "published_at": "2026-09-30T00:00:00+00:00",
        "qualifiers_json": '{"k": "' + "q" * 900 + '"}',
        "evidence_tier": TIER_SINGLE_OFFICIAL,
    }


def test_insert_statements_stay_under_the_d1_statement_limit() -> None:
    rows = [_wide_relationship(i) for i in range(500)]
    statements = publisher.sized_insert_statements(
        "relationships", publisher.RELATIONSHIP_COLUMNS, rows, verb="INSERT OR REPLACE"
    )
    assert all(len(statement.encode("utf-8")) < 100_000 for statement in statements)
    assert sum(statement.count("rel-") for statement in statements) == 500


def test_upsert_orders_each_evidence_chunk_after_its_relationships() -> None:
    relationships = [_wide_relationship(i) for i in range(250)]
    evidence = [
        {
            "relationship_id": r["id"],
            "source_document_id": f"doc-{r['id']}",
            "role": "supports",
            "locator": "p.1",
            "support_excerpt": "x",
            "source_url": SEC_URL,
            "source_title": "t",
            "publisher": "SEC EDGAR",
            "document_date": None,
        }
        for r in relationships
    ]
    statements = publisher.upsert_statements([], [], [], [], relationships, evidence)
    seen_relationships: set[str] = set()
    for statement in statements:
        if statement.startswith("INSERT OR REPLACE INTO relationships("):
            seen_relationships.update(re.findall(r"'(rel-\d+)'", statement))
        elif statement.startswith("INSERT OR REPLACE INTO relationship_evidence("):
            referenced = set(re.findall(r"\('(rel-\d+)'", statement))
            assert referenced <= seen_relationships, "evidence written before its relationship"
    assert len(seen_relationships) == 250
