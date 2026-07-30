from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.source_independence import (
    SourceIndependenceAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
)
from source_independence import (
    SourceIndependenceError,
    build_report,
    canonical_json_bytes,
    cluster_sources,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S08_P02.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _case(identifier: str) -> dict:
    matches = [case for case in FIXTURE["cases"] if case["id"] == identifier]
    assert len(matches) == 1
    return matches[0]


def _weight_total(cluster: dict) -> Decimal:
    return sum((Decimal(member["weight"]) for member in cluster["members"]), Decimal("0"))


def test_candidate_preflight_and_contract_pass_without_generated_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == FIXTURE["contract_id"]
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_clusters_artifact_is_an_exact_deterministic_replay_of_frozen_fixture() -> None:
    actual = json.loads((ROOT / "source_clusters.json").read_text(encoding="utf-8"))
    expected = build_report(FIXTURE)
    assert actual == expected
    assert actual["input_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert actual["external_effect_boundary"]["external_network_accessed"] is False
    assert actual["external_effect_boundary"]["order_submission_enabled"] is False


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_expected_cluster_counts_and_weights_are_exact(case: dict) -> None:
    result = cluster_sources(case)
    expected = case["expected"]
    assert result["cluster_count"] == expected["cluster_count"]
    assert result["eligible_independent_source_count"] == expected["eligible_independent_source_count"]
    assert result["effective_independent_weight"] == expected["effective_independent_weight"]
    assert [cluster["member_count"] for cluster in result["clusters"]] == expected["cluster_member_counts"]
    for cluster in result["clusters"]:
        assert _weight_total(cluster) == Decimal(cluster["independent_weight"])
        assert Decimal(cluster["independent_weight"]) in {Decimal("0"), Decimal("1")}


def test_matching_content_with_distinct_operator_labels_is_still_one_independent_source() -> None:
    result = cluster_sources(_case("MATCHING_CONTENT_UNDECLARED_COPY"))
    assert result["input_source_count"] == 2
    assert result["cluster_count"] == 1
    assert result["eligible_independent_source_count"] == 1
    assert result["clusters"][0]["relation_reasons"] == ["MATCHING_CONTENT_FINGERPRINT"]


def test_stale_or_unverified_sources_contribute_no_independent_weight() -> None:
    result = cluster_sources(_case("STALE_AND_UNVERIFIED_SOURCES"))
    assert result["eligible_independent_source_count"] == 0
    assert result["effective_independent_weight"] == "0"
    assert all(cluster["independent_weight"] == "0" for cluster in result["clusters"])


def test_freshness_boundary_is_inclusive_and_copy_is_not_extra_weight() -> None:
    result = cluster_sources(_case("FRESHNESS_BOUNDARY_COPY"))
    assert result["cluster_count"] == 1
    assert result["eligible_independent_source_count"] == 1
    assert result["clusters"][0]["eligible_member_count"] == 2
    assert _weight_total(result["clusters"][0]) == Decimal("1")


@pytest.mark.parametrize("case", FIXTURE["invalid_cases"], ids=lambda case: case["id"])
def test_invalid_or_ambiguous_provenance_fails_closed(case: dict) -> None:
    with pytest.raises(SourceIndependenceError):
        cluster_sources(case)


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    case = _case("DIRECT_AND_COPIED_SOURCES")
    hashes = {
        hashlib.sha256(canonical_json_bytes(cluster_sources(case))).hexdigest()
        for _ in range(FIXTURE["replay_count"])
    }
    assert len(hashes) == 1


def test_ten_thousand_adverse_copies_never_create_an_extra_independent_source_without_soak() -> None:
    base = _case("DIRECT_AND_COPIED_SOURCES")
    expected_count = base["expected"]["eligible_independent_source_count"]
    for iteration in range(FIXTURE["adverse_replay_count"]):
        candidate = deepcopy(base)
        candidate["sources"].append(
            {
                "source_id": "SRC_ADVERSE_COPY_%05d" % iteration,
                "operator_id": "OPERATOR_A_RELAY",
                "supply_chain_id": "CHAIN_A_RELAY",
                "observed_at": "2026-07-29T23:59:59+10:00",
                "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "source_version_sha256": "%064x" % (iteration + 1),
                "copy_of": "SRC_A_DIRECT",
                "source_contract_status": "VERIFIED",
            }
        )
        result = cluster_sources(candidate)
        assert result["eligible_independent_source_count"] == expected_count
        assert result["effective_independent_weight"] == "3"
        assert result["cluster_count"] == 3


def test_core_source_has_no_network_process_or_sleep_capability() -> None:
    source = (ROOT / "source_independence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"})
    assert "sleep(" not in source
    assert "float(" not in source


def test_rollback_drill_is_hash_only_and_changes_no_external_state() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False
    assert all(item["status"] == "PASS" for item in rollback["artifacts"].values())


def test_candidate_fails_closed_when_cluster_artifact_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "source_clusters.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["summary"]["case_count"] = 999
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S08P02-CLUSTERS-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_signed_predecessor_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    path = clone / "machine/evidence/EVD-S08-P01.json"
    path.write_text("{}\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert any(identifier.startswith("S08P02-PREDECESSOR-HASH") for identifier in result["summary"]["failed_check_ids"])


def test_phase_receipt_is_absent_before_delivery_and_cannot_be_claimed(tmp_path: Path) -> None:
    with pytest.raises((SourceIndependenceAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(tmp_path)


def test_cli_is_wired_to_exact_contract_and_preserves_no_order_boundary() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S08-P02": write_source_independence_phase_evidence' in source
    assert '"AC-S08-P02": verify_source_independence_phase_evidence' in source
    core_source = (ROOT / "source_independence.py").read_text(encoding="utf-8")
    assert '"order_submission_enabled": False' in core_source
    assert "submit_order" not in core_source


def test_fixture_keeps_financial_and_runtime_claims_unverified() -> None:
    boundary = FIXTURE["claim_boundary"]
    assert boundary["network_accessed"] is False
    assert boundary["actual_market_or_odds_observed"] is False
    assert boundary["recommendation_generated"] is False
    assert boundary["order_submission_enabled"] is False
    assert boundary["real_time_soak_required"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
