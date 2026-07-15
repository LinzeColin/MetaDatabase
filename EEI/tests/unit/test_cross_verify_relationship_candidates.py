from __future__ import annotations

import copy
from typing import Any

import httpx
import pytest

from scripts import cross_verify_relationship_candidates as cross_verify_module
from scripts import fetch_official_source_full_text as official_source
from scripts.cross_verify_relationship_candidates import (
    CONFLICTED,
    CORROBORATED,
    SINGLE_SOURCE,
    UNVERIFIED,
    CrossVerificationError,
    build_contract_artifact,
    build_queue_rows,
    capture_rows_for_candidates,
    cross_verify,
    policy_fingerprint,
)


def sample_candidates_payload() -> dict[str, Any]:
    return {
        "schema_version": "test",
        "record_mode": "curated_official_fixture",
        "source_threshold_min": 2,
        "source_snapshots": [
            {
                "anchor_id": "SNAP-A",
                "source_date": "2026-01-01",
                "official_publisher": "SEC EDGAR / NVIDIA Form 10-K",
                "title": "NVIDIA 10-K",
                "url": "https://www.sec.gov/Archives/test/nvda.htm",
            },
            {
                "anchor_id": "SNAP-B",
                "source_date": "2026-02-01",
                "official_publisher": "TSMC Press Center",
                "title": "TSMC press",
                "url": "https://pr.tsmc.com/english/news/test",
            },
        ],
        "relationship_candidates": [
            {
                "candidate_key": "FACT-1",
                "source_anchor_id": "SNAP-A",
                "supporting_source_anchor_ids": ["SNAP-B"],
                "subject_candidate_name": "TSMC",
                "object_candidate_name": "NVIDIA Corporation",
                "relationship_type": "wafer_foundry_for",
                "counter_evidence": [],
            }
        ],
    }


def healthy_anchor(row_id: str, *, missing: list[str] | None = None) -> dict[str, Any]:
    return {
        "anchor_id": row_id,
        "source_text_sha256": "0" * 64,
        "source_health": {
            "status": "healthy",
            "http_status": 200,
            "text_char_count": 5000,
            "missing_tokens": missing or [],
        },
    }


def capture_payload(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "LIVE_CAPTURE_READY_FOR_OPERATOR_REVIEW", "anchors": anchors}


def test_capture_rows_expected_tokens_and_composite_ids() -> None:
    rows = capture_rows_for_candidates(sample_candidates_payload())
    assert [row["anchor_id"] for row in rows] == ["FACT-1@SNAP-A", "FACT-1@SNAP-B"]
    expected = rows[0]["expected_entities_or_stages"]
    assert "TSMC" in expected
    assert "NVIDIA Corporation" in expected
    assert "foundry" in expected
    assert rows[0]["source_date"] == "2026-01-01"


def test_capture_rows_fail_closed_on_unknown_snapshot_and_relation() -> None:
    payload = sample_candidates_payload()
    payload["relationship_candidates"][0]["supporting_source_anchor_ids"] = ["SNAP-X"]
    with pytest.raises(CrossVerificationError):
        capture_rows_for_candidates(payload)
    payload = sample_candidates_payload()
    payload["relationship_candidates"][0]["relationship_type"] = "unknown_relation"
    with pytest.raises(CrossVerificationError):
        capture_rows_for_candidates(payload)


def test_corroborated_when_two_independent_sources_support() -> None:
    verification = cross_verify(
        sample_candidates_payload(),
        capture_payload(
            [healthy_anchor("FACT-1@SNAP-A"), healthy_anchor("FACT-1@SNAP-B")]
        ),
    )
    result = verification["results"][0]
    assert result["corroboration_status"] == CORROBORATED
    assert result["supporting_source_count"] == 2
    assert result["independent_publisher_count"] == 2
    assert result["queue_required"] is False
    assert build_queue_rows(verification) == []
    assert verification["release_scope"]["relationship_publication_performed"] is False


def test_single_source_when_second_source_misses_entity() -> None:
    verification = cross_verify(
        sample_candidates_payload(),
        capture_payload(
            [
                healthy_anchor("FACT-1@SNAP-A"),
                healthy_anchor("FACT-1@SNAP-B", missing=["nvidia corporation"]),
            ]
        ),
    )
    result = verification["results"][0]
    assert result["corroboration_status"] == SINGLE_SOURCE
    rows = build_queue_rows(verification)
    assert rows[0]["queue_key"] == "second-source:FACT-1"
    assert rows[0]["priority"] == "P1"
    assert rows[0]["object_type"] == "relationship_fact_candidate"


def test_same_publisher_pair_counts_as_single_source() -> None:
    payload = sample_candidates_payload()
    payload["source_snapshots"][1]["official_publisher"] = "SEC EDGAR / NVIDIA Form 10-K"
    verification = cross_verify(
        payload,
        capture_payload(
            [healthy_anchor("FACT-1@SNAP-A"), healthy_anchor("FACT-1@SNAP-B")]
        ),
    )
    result = verification["results"][0]
    assert result["supporting_source_count"] == 2
    assert result["independent_publisher_count"] == 1
    assert result["corroboration_status"] == SINGLE_SOURCE


def test_unverified_when_transport_fails_everywhere() -> None:
    failed = healthy_anchor("FACT-1@SNAP-A")
    failed["source_health"]["http_status"] = 404
    short = healthy_anchor("FACT-1@SNAP-B")
    short["source_health"]["text_char_count"] = 10
    verification = cross_verify(
        sample_candidates_payload(), capture_payload([failed, short])
    )
    result = verification["results"][0]
    assert result["corroboration_status"] == UNVERIFIED
    assert build_queue_rows(verification)[0]["priority"] == "P0"


def test_counter_evidence_forces_conflicted() -> None:
    payload = sample_candidates_payload()
    payload["relationship_candidates"][0]["counter_evidence"] = [
        {"note": "disputed disclosure"}
    ]
    verification = cross_verify(
        payload,
        capture_payload(
            [healthy_anchor("FACT-1@SNAP-A"), healthy_anchor("FACT-1@SNAP-B")]
        ),
    )
    result = verification["results"][0]
    assert result["corroboration_status"] == CONFLICTED
    assert build_queue_rows(verification)[0]["priority"] == "P0"


def test_contract_artifact_is_fail_closed_and_fingerprinted() -> None:
    artifact = build_contract_artifact()
    assert artifact["policy_fingerprint"] == policy_fingerprint()
    assert artifact["release_scope"]["mvp_release_ready"] is False
    assert artifact["release_scope"]["relationship_publication_performed"] is False
    assert artifact["token_alias_policy_version"] == official_source.TOKEN_ALIAS_POLICY_VERSION


def test_end_to_end_through_real_capture_machinery_with_mock_transport() -> None:
    payload = sample_candidates_payload()
    supportive_html = (
        "<html><body>"
        + "NVIDIA Corporation relies on TSMC as a wafer foundry partner. " * 30
        + "</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=supportive_html, headers={"content-type": "text/html"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = capture_rows_for_candidates(payload)
    captured = official_source.capture_live_official_sources(rows=rows, client=client)
    verification = cross_verify(payload, captured)
    result = verification["results"][0]
    assert result["corroboration_status"] == CORROBORATED
    assert all(source["captured"] for source in result["sources"])


def test_cross_verify_ignores_unrelated_anchor_rows() -> None:
    anchors = [
        healthy_anchor("FACT-1@SNAP-A"),
        healthy_anchor("OTHER@SNAP-B"),
    ]
    verification = cross_verify(sample_candidates_payload(), capture_payload(anchors))
    result = verification["results"][0]
    assert result["sources"][1]["captured"] is False
    assert result["corroboration_status"] == SINGLE_SOURCE


def test_policy_fingerprint_stable_under_deepcopy() -> None:
    before = policy_fingerprint()
    _ = copy.deepcopy(cross_verify_module.RELATION_KEYWORDS)
    assert policy_fingerprint() == before
