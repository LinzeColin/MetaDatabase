from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.research_gap_audit import evaluate_contract as evaluate_p04
from abd_acceptance.stage2_review import (
    CONTRACT_PATH,
    EVIDENCE_PATH,
    FINDINGS_PATH,
    FIXED_CLOCK,
    FIXTURE_PATH,
    REVIEW_ARTIFACT_HASHES,
    ROLLBACK_EVIDENCE_PATH,
    TEST_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_stage_review_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
SOURCES = strict_json_load(ROOT / "sources.json")
PROVIDER = strict_json_load(ROOT / "provider_facts_snapshot.json")
REGULATORY = strict_json_load(ROOT / "regulatory_matrix.json")
PAPERS = strict_json_load(ROOT / "research_evidence_matrix.json")
CLAIMS = strict_json_load(ROOT / "model_claims.json")
REUSE = strict_json_load(ROOT / "research_reuse_matrix.json")
LICENSES = strict_json_load(ROOT / "license_inventory.json")
GAPS = strict_json_load(ROOT / "research_gaps.json")
COUNTER = strict_json_load(ROOT / "counterevidence.json")
SCHEDULE = strict_json_load(ROOT / "review_schedule.json")
GAP_SOURCE_VECTORS = [
    (gap["id"], index, reference)
    for gap in GAPS["gaps"]
    for index, reference in enumerate(gap["source_refs"])
]


def _evaluate(root: Path, *, phase_oracles: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports=False,
        _verify_history=Path(root).resolve() == ROOT.resolve(),
        _verify_phase_oracles=phase_oracles,
    )


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        str(ROOT),
        str(destination),
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(str(ROOT.parent / ".github"), str(destination.parent / ".github"))
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _row(rows, item_id: str, key: str = "id"):
    return next(row for row in rows if row[key] == item_id)


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_baseline_stage2_whole_stage_review_passes_without_runtime_reports() -> None:
    result = _evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= FIXTURE["expected_review_oracle_check_minimum"]
    assert result["decision"] == "S02_WHOLE_STAGE_REVIEW_PASS"
    assert result["stage_status"] == "S02_REVIEW_PASS_REMOTE_UPLOAD_PENDING"
    assert result["remote_ci_status"] == "NOT_YET_OBSERVED_REQUIRES_STAGE_UPLOAD"
    assert result["release_status"] == "NOT_READY"
    assert result["next"] == "S02/GITHUB_STAGE_UPLOAD_READY"
    ids = [row["id"] for row in result["checks"]]
    assert len(ids) == len(set(ids))


def test_exact_stage2_review_candidate_or_signed_receipt_is_verifiable() -> None:
    if (ROOT / EVIDENCE_PATH).is_file():
        result = verify_existing_stage_review_evidence(ROOT, verify_phase_prerequisites=False)
        assert result["status"] == "PASS", result
        assert result["next"] == "S02/GITHUB_STAGE_UPLOAD_READY"
    else:
        result = validate_candidate_preflight(ROOT)
        assert result["status"] == "PASS", result
        assert result["decision"] == "S02_REVIEW_CANDIDATE_PREFLIGHT_PASS"
        assert result["next"] == "S02/STAGE_REVIEW_CANDIDATE"


def test_p04_oracle_accepts_only_the_exact_review_candidate() -> None:
    result = evaluate_p04(ROOT, require_external_reports=False, _verify_git_history=True)
    assert result["status"] == "PASS", result
    check = next(row for row in result["checks"] if row["id"] == "S02P04-STAGE2-REVIEW-NOT-STARTED")
    assert check["passed"] is True
    assert check["detail"]["state"] in {"STAGE2_REVIEW_CANDIDATE_VALID", "STAGE2_REVIEW_SIGNED_VERIFIED"}


@pytest.mark.parametrize("relative", [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH])
def test_frozen_review_artifact_hashes_match_pins(relative: Path) -> None:
    assert sha256_file(ROOT / relative) == REVIEW_ARTIFACT_HASHES[relative.as_posix()]


@pytest.mark.parametrize("source_id", FIXTURE["expected_source_ids"])
def test_every_official_source_remains_primary_traceable_and_dated(source_id: str) -> None:
    source = _row(SOURCES["sources"], source_id)
    assert source["url"].startswith("https://")
    assert source["retrieved_on"] == "2026-07-20"
    assert source["source_level"].startswith("L1_")
    assert source["claim_ids"]


@pytest.mark.parametrize("fact_id", FIXTURE["expected_provider_fact_ids"])
def test_every_provider_fact_has_official_citation_and_safe_decision(fact_id: str) -> None:
    facts = [fact for provider in PROVIDER["providers"] for fact in provider["facts"]]
    fact = _row(facts, fact_id, "fact_id")
    assert fact["statement"]
    assert fact["operational_decision"]
    assert fact["citations"]
    assert all(citation["source_id"] in FIXTURE["expected_source_ids"] for citation in fact["citations"])


@pytest.mark.parametrize("rule_id", FIXTURE["expected_regulatory_rule_ids"])
def test_every_regulatory_rule_has_control_and_primary_citation(rule_id: str) -> None:
    rule = _row(REGULATORY["rules"], rule_id, "rule_id")
    assert rule["operational_control"]
    assert rule["unknown_or_conflict_action"]
    assert rule["citations"]
    assert all(citation["source_id"] in FIXTURE["expected_source_ids"] for citation in rule["citations"])


@pytest.mark.parametrize("paper_id", FIXTURE["expected_paper_ids"])
def test_every_paper_has_primary_source_limitations_and_claim_routes(paper_id: str) -> None:
    paper = _row(PAPERS["papers"], paper_id)
    assert paper["primary_url"].startswith("https://")
    assert paper["retrieved_on"] == "2026-07-20"
    assert paper["source_level"].startswith("L1_") or paper["source_level"] == "L2_AUTHOR_PREPRINT_PRIMARY"
    assert paper["claim_ids"]
    assert paper["limitations"]


@pytest.mark.parametrize("claim_id", FIXTURE["expected_model_claim_ids"])
def test_every_model_claim_has_reciprocal_paper_route_and_nonproof_boundary(claim_id: str) -> None:
    claim = _row(CLAIMS["claims"], claim_id)
    assert claim["citations"]
    assert claim["not_proven"]
    for citation in claim["citations"]:
        paper = _row(PAPERS["papers"], citation["paper_id"])
        assert claim_id in paper["claim_ids"]


@pytest.mark.parametrize("pointer", FIXTURE["expected_threshold_pointers"])
def test_every_local_threshold_is_explicitly_not_paper_derived(pointer: str) -> None:
    row = _row(CLAIMS["local_threshold_inventory"], pointer, "parameter_pointer")
    assert row["value"] is not None
    assert row["claim_id"] in FIXTURE["expected_model_claim_ids"]
    assert row["status"].endswith("NOT_PAPER_DERIVED")


@pytest.mark.parametrize("source_id", FIXTURE["expected_reuse_source_ids"])
def test_every_reuse_project_has_adopt_adapt_reject_and_license_route(source_id: str) -> None:
    project = _row(REUSE["projects"], source_id, "source_id")
    assert project["pinned_commit"]
    assert project["adopt"]
    assert project["adapt"]
    assert project["reject"]
    assert project["license_evidence_id"] in FIXTURE["expected_license_ids"]
    assert "NO_RUNTIME_DEPENDENCY" in project["adoption_status"] or project["adoption_status"].startswith("CODE_REUSE_REJECTED")


@pytest.mark.parametrize("license_id", FIXTURE["expected_license_ids"])
def test_every_license_entry_is_pinned_and_reciprocal(license_id: str) -> None:
    entry = _row(LICENSES["entries"], license_id)
    project = _row(REUSE["projects"], entry["source_id"], "source_id")
    assert entry["pinned_commit"] == project["pinned_commit"]
    assert project["license_evidence_id"] == license_id
    assert entry["p03_disposition"]
    assert entry["future_reuse"]


@pytest.mark.parametrize("gap_id", FIXTURE["expected_gap_ids"])
def test_every_gap_remains_open_nonpass_safe_and_explicit(gap_id: str) -> None:
    gap = _row(GAPS["gaps"], gap_id)
    assert gap["gap_state"] == "OPEN_EXPLICIT"
    assert gap["safe_default"]
    assert gap["closure_evidence"]
    assert gap["review_ids"]
    assert gap["source_refs"]


@pytest.mark.parametrize("counter_id", FIXTURE["expected_counterevidence_ids"])
def test_every_counterevidence_record_has_gap_review_and_local_evidence_routes(counter_id: str) -> None:
    record = _row(COUNTER["records"], counter_id)
    assert record["verdict"]
    assert record["implication"]
    assert record["safe_default"]
    assert record["gap_ids"]
    assert record["review_ids"]
    assert record["evidence_refs"]


@pytest.mark.parametrize("review_id", FIXTURE["expected_review_ids"])
def test_every_review_route_is_registered_fail_closed_and_not_executed(review_id: str) -> None:
    review = _row(SCHEDULE["reviews"], review_id)
    assert review["trigger"]
    assert review["required_inputs"]
    assert review["required_outputs"]
    assert review["gap_ids"]
    assert review["overdue_action"]
    assert review["external_access_allowed_in_p04"] is False
    assert review["current_status"] not in {"PASS", "COMPLETE", "EXECUTED"}


@pytest.mark.parametrize("gap_id", FIXTURE["expected_gap_ids"])
def test_every_gap_has_direct_counterevidence(gap_id: str) -> None:
    assert any(gap_id in row["gap_ids"] for row in COUNTER["records"])


@pytest.mark.parametrize("gap_id", FIXTURE["expected_gap_ids"])
def test_every_gap_has_reciprocal_review_schedule_route(gap_id: str) -> None:
    gap = _row(GAPS["gaps"], gap_id)
    scheduled = {row["id"] for row in SCHEDULE["reviews"] if gap_id in row["gap_ids"]}
    assert scheduled
    assert set(gap["review_ids"]).issubset(scheduled)


@pytest.mark.parametrize(("gap_id", "index", "reference"), GAP_SOURCE_VECTORS)
def test_every_one_of_71_gap_source_references_resolves(gap_id: str, index: int, reference: str) -> None:
    assert len(GAP_SOURCE_VECTORS) == FIXTURE["expected_item_counts"]["gap_source_references"] == 71
    assert _row(GAPS["gaps"], gap_id)["source_refs"][index] == reference
    valid = (
        set(FIXTURE["expected_provider_fact_ids"])
        | set(FIXTURE["expected_regulatory_rule_ids"])
        | set(FIXTURE["expected_model_claim_ids"])
        | set(FIXTURE["expected_reuse_source_ids"])
        | set(FIXTURE["expected_license_ids"])
        | {
            "canonical_facts.json#/scope/discovery_scope",
            "conflict_assessment",
            "costs.json#/future_source_admission_policy",
            "license_inventory.json#/policy",
            "parameters.json#/numeric_determinism",
            "parameters.json#/target_30pct",
            "provider_facts_snapshot.json#/fact_semantics",
            "research_evidence_matrix.json#/research_mode",
            "runtime_prerequisite_state",
        }
    )
    assert reference in valid


@pytest.mark.parametrize("mutation", ["stage", "phase", "requirement", "acceptance", "task"])
def test_review_scope_drift_fails_closed(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    if mutation == "stage":
        contract["stage_id"] = "S03"
    elif mutation == "phase":
        contract["review_scope"]["phase_ids"].pop()
    elif mutation == "requirement":
        contract["review_scope"]["requirement_ids"].pop()
    elif mutation == "acceptance":
        contract["review_scope"]["acceptance_contract_ids"].pop()
    else:
        contract["review_scope"]["task_ids"][-1] = contract["review_scope"]["task_ids"][0]
    _write_json(path, contract)
    _failed(_evaluate(project), "S02REVIEW-CONTRACT-SCOPE-EXACT")


@pytest.mark.parametrize("field", list(FIXTURE["expected_external_effect_boundary"]))
def test_local_review_cannot_claim_external_effect(tmp_path: Path, field: str) -> None:
    project = _clone_project(tmp_path)
    path = project / CONTRACT_PATH
    contract = strict_json_load(path)
    contract["external_effect_boundary"][field] = True
    _write_json(path, contract)
    _failed(_evaluate(project), "S02REVIEW-LOCAL-EXTERNAL-EFFECT-BOUNDARY")


@pytest.mark.parametrize(
    "relative",
    [
        "sources.json", "provider_facts_snapshot.json", "regulatory_matrix.json", "research_evidence_matrix.json",
        "model_claims.json", "research_reuse_matrix.json", "license_inventory.json", "research_gaps.json",
        "counterevidence.json", "review_schedule.json",
    ],
)
def test_critical_stage2_artifact_drift_fails_closed(tmp_path: Path, relative: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    value = strict_json_load(path)
    value["stage2_review_injected_drift"] = True
    _write_json(path, value)
    _failed(_evaluate(project), "S02REVIEW-BASELINE-CRITICAL-HASHES")


@pytest.mark.parametrize(
    ("mutation", "check_id"),
    [
        ("paper_claim", "S02REVIEW-PAPER-CLAIM-RECIPROCAL-GRAPH"),
        ("claim_paper", "S02REVIEW-PAPER-CLAIM-RECIPROCAL-GRAPH"),
        ("reuse_license", "S02REVIEW-REUSE-LICENSE-BIJECTION"),
        ("license_reuse", "S02REVIEW-REUSE-LICENSE-BIJECTION"),
        ("gap_source", "S02REVIEW-ALL-GAP-SOURCE-REFS-RESOLVE"),
        ("gap_safe", "S02REVIEW-ALL-26-GAPS-SAFE-COUNTER-REVIEW-ROUTED"),
        ("counter_gap", "S02REVIEW-ALL-26-GAPS-SAFE-COUNTER-REVIEW-ROUTED"),
        ("review_gap", "S02REVIEW-ALL-26-GAPS-SAFE-COUNTER-REVIEW-ROUTED"),
    ],
)
def test_cross_artifact_graph_mutations_fail_closed(tmp_path: Path, mutation: str, check_id: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "paper_claim":
        path = project / "research_evidence_matrix.json"
        value = strict_json_load(path)
        value["papers"][0]["claim_ids"] = ["CLM-UNKNOWN"]
    elif mutation == "claim_paper":
        path = project / "model_claims.json"
        value = strict_json_load(path)
        value["claims"][0]["citations"][0]["paper_id"] = "PAPER-UNKNOWN"
    elif mutation == "reuse_license":
        path = project / "research_reuse_matrix.json"
        value = strict_json_load(path)
        value["projects"][0]["license_evidence_id"] = "LIC-UNKNOWN"
    elif mutation == "license_reuse":
        path = project / "license_inventory.json"
        value = strict_json_load(path)
        value["entries"][0]["source_id"] = "SRC-UNKNOWN"
    elif mutation in {"gap_source", "gap_safe"}:
        path = project / "research_gaps.json"
        value = strict_json_load(path)
        if mutation == "gap_source":
            value["gaps"][0]["source_refs"] = ["UNKNOWN"]
        else:
            value["gaps"][0]["safe_default"] = ""
    elif mutation == "counter_gap":
        path = project / "counterevidence.json"
        value = strict_json_load(path)
        for row in value["records"]:
            row["gap_ids"] = [gap_id for gap_id in row["gap_ids"] if gap_id != "GAP-S02-P04-001"]
    else:
        path = project / "review_schedule.json"
        value = strict_json_load(path)
        for row in value["reviews"]:
            row["gap_ids"] = [gap_id for gap_id in row["gap_ids"] if gap_id != "GAP-S02-P04-001"]
    _write_json(path, value)
    _failed(_evaluate(project), check_id)


def test_reopened_finding_fails_closed(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / FINDINGS_PATH
    findings = strict_json_load(path)
    findings["findings"][0]["status"] = "OPEN"
    findings["summary"]["open"] = 1
    _write_json(path, findings)
    _failed(_evaluate(project), "S02REVIEW-FINDINGS-ALL-RESOLVED")


def test_stage3_actual_evidence_fails_progression_gate(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / "machine/evidence/EVD-S03-P01.json").write_text("{}\n", encoding="utf-8")
    _failed(_evaluate(project), "S02REVIEW-S03-NOT-STARTED")


@pytest.mark.parametrize("relative", [CONTRACT_PATH, FINDINGS_PATH, FIXTURE_PATH])
def test_strict_json_duplicate_keys_fail_closed(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    (project / relative).write_text('{"schema_version":"1.0.0","schema_version":"drift"}\n', encoding="utf-8")
    result = _evaluate(project)
    assert result["status"] == "FAIL"
    assert any("PARSE" in check_id for check_id in result["summary"]["failed_check_ids"])


def test_partial_candidate_fails_p04_successor_guard(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    (project / TEST_PATH).unlink()
    result = evaluate_p04(project, require_external_reports=False, _verify_git_history=False)
    _failed(result, "S02P04-STAGE2-REVIEW-NOT-STARTED")


def test_rollback_drill_restores_all_signed_artifacts_without_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"] == 13
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_portable_and_preserves_boundaries() -> None:
    evidence_a, rollback_a = build_evidence(ROOT, require_external_reports=False)
    evidence_b, rollback_b = build_evidence(ROOT, require_external_reports=False)
    assert evidence_a == evidence_b
    assert rollback_a == rollback_b
    assert evidence_a["status"] == "PASS", evidence_a["validation"]["summary"]
    assert evidence_a["decision"] == "S02_WHOLE_STAGE_REVIEW_PASS"
    assert evidence_a["next"] == "S02/GITHUB_STAGE_UPLOAD_READY"
    assert evidence_a["external_effect_boundary"] == FIXTURE["expected_external_effect_boundary"]
    unsigned = dict(evidence_a)
    decision_hash = unsigned.pop("decision_sha256")
    assert decision_hash == hashlib.sha256((json.dumps(unsigned, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    rendered = json.dumps([evidence_a, rollback_a], ensure_ascii=False, sort_keys=True)
    assert str(ROOT) not in rendered
    assert ("/" + "Users/") not in rendered
    assert ("/private/" + "var/") not in rendered
    if (ROOT / EVIDENCE_PATH).is_file():
        delivered = verify_existing_stage_review_evidence(ROOT, verify_phase_prerequisites=False)
        assert delivered["status"] == "PASS", delivered
        assert delivered["evidence_sha256"] == sha256_file(ROOT / EVIDENCE_PATH)


def test_review_receipt_paths_are_reserved_and_atomic_before_or_after_writer() -> None:
    assert TEST_PATH.as_posix() == "tests/S02/stage_review_test.py"
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-STAGE-REVIEW.json"
    assert ROLLBACK_EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json"
    assert (ROOT / EVIDENCE_PATH).exists() is (ROOT / ROLLBACK_EVIDENCE_PATH).exists()
    if (ROOT / EVIDENCE_PATH).exists():
        result = verify_existing_stage_review_evidence(ROOT, verify_phase_prerequisites=False)
        assert result["status"] == "PASS", result
    assert FIXED_CLOCK == "2026-07-20T00:00:00+10:00"
