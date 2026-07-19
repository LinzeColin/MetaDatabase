from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.model_risk_research import (
    CLAIMS_PATH,
    EVIDENCE_PATH,
    FIXTURE_PATH,
    MATRIX_PATH,
    PINNED_PHASE_HASHES,
    P01_EVIDENCE_PATH,
    P01_EVIDENCE_SHA256,
    P01_ROLLBACK_PATH,
    P01_ROLLBACK_SHA256,
    ROLLBACK_EVIDENCE_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_claim_admission,
    resolve_stability_contract,
)
from abd_acceptance.official_platform_research import verify_existing_phase_evidence as verify_p01_evidence


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
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


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _row(rows, item_id: str, key: str = "id"):
    return next(row for row in rows if row[key] == item_id)


def _paper(value, paper_id: str):
    return _row(value["papers"], paper_id)


def _claim(value, claim_id: str):
    return _row(value["claims"], claim_id)


def test_baseline_model_risk_research_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT, require_external_reports=False)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["decision"] == "MODEL_AND_RISK_RESEARCH_CLAIMS_FROZEN"
    assert result["release_status"] == "NOT_READY_STAGE_REVIEW_REQUIRED"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["model_status"] == "RESEARCH_ONLY_NOT_TRAINED_OR_VALIDATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S02/P03_READY_NOT_STARTED"
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p01_signed_receipt_is_the_exact_prerequisite_without_successor_recursion() -> None:
    result = verify_p01_evidence(ROOT, verify_git_history=True, verify_successor_state=False)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S02_P01_EVIDENCE_VERIFIED"
    assert result["evidence_sha256"] == P01_EVIDENCE_SHA256
    assert result["rollback_sha256"] == P01_ROLLBACK_SHA256
    assert result["next"] == "S02/P02_READY_NOT_STARTED"


@pytest.mark.parametrize("relative", [MATRIX_PATH, CLAIMS_PATH, FIXTURE_PATH])
def test_phase_artifact_hashes_match_oracle_pins(relative: Path) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative.as_posix()]


@pytest.mark.parametrize("paper_id", FIXTURE["expected_paper_ids"])
def test_every_paper_has_exact_primary_identifier_url_date_level_and_limits(paper_id: str) -> None:
    matrix = strict_json_load(ROOT / MATRIX_PATH)
    paper = _paper(matrix, paper_id)
    assert paper["identifiers"] == FIXTURE["expected_identifiers"][paper_id]
    assert paper["primary_url"] == FIXTURE["expected_primary_urls"][paper_id]
    assert paper["retrieved_on"] == FIXTURE["as_of"]
    assert paper["source_level"] == FIXTURE["expected_source_levels"][paper_id]
    assert paper["categories"]
    assert paper["claim_ids"]
    assert len(paper["limitations"]) >= 2
    assert paper["threshold_basis_decision"] == "REJECT_AS_EXACT_ABD_THRESHOLD_BASIS"


@pytest.mark.parametrize("claim_id", FIXTURE["expected_claim_ids"])
def test_every_model_claim_is_explicitly_bounded_and_resolves_to_papers(claim_id: str) -> None:
    matrix = strict_json_load(ROOT / MATRIX_PATH)
    claims = strict_json_load(ROOT / CLAIMS_PATH)
    paper_map = {row["id"]: row for row in matrix["papers"]}
    claim = _claim(claims, claim_id)
    assert claim["evidence_classification"] == FIXTURE["expected_claim_classifications"][claim_id]
    assert claim["direct_finding_or_inference"] == "ABD_DESIGN_INFERENCE"
    assert claim["runtime_status"]
    assert claim["not_proven"]
    assert claim["citations"]
    for citation in claim["citations"]:
        paper = paper_map[citation["paper_id"]]
        assert citation["primary_url"] == paper["primary_url"]
        assert citation["retrieved_on"] == paper["retrieved_on"]
        assert citation["source_level"] == paper["source_level"]
        assert claim_id in paper["claim_ids"]


@pytest.mark.parametrize("expected", FIXTURE["expected_local_thresholds"])
def test_every_local_threshold_is_exactly_bound_to_parameters_and_not_paper_derived(expected) -> None:
    claims = strict_json_load(ROOT / CLAIMS_PATH)
    parameters = strict_json_load(ROOT / "machine/facts/parameters.json")
    assert expected in claims["local_threshold_inventory"]
    current = parameters
    for part in expected["parameter_pointer"][1:].split("/"):
        current = current[part]
    assert current == expected["value"]
    claim = _claim(claims, expected["claim_id"])
    if expected["status"] == "LOCAL_ENGINEERING_THRESHOLD_NOT_PAPER_DERIVED":
        assert claim["evidence_classification"] == "LOCAL_ENGINEERING_THRESHOLD_NOT_PAPER_DERIVED"
        assert all(
            citation["relation"] == "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE"
            for citation in claim["citations"]
        )
    else:
        assert expected["claim_id"] == "CLM-S02-P02-014"
        assert claim["runtime_status"] == "UNVERIFIED_NOT_GUARANTEED"


@pytest.mark.parametrize("case", FIXTURE["claim_admission_vectors"])
def test_claim_admission_is_fail_closed_for_source_maturity_threshold_and_runtime_proof(case) -> None:
    assert resolve_claim_admission(
        case["evidence_classification"],
        case["citation_relation"],
        case["source_level"],
        case["has_runtime_proof"],
    ) == case["expected"]


@pytest.mark.parametrize("case", FIXTURE["stability_boundary_vectors"])
def test_stability_contract_covers_exact_and_plus_minus_point_0001_boundaries(case) -> None:
    assert resolve_stability_contract(
        case["probability_perturbation"],
        case["threshold_perturbation"],
        case["friction_perturbation"],
        case["odds_perturbation"],
        case["action_if_flip"],
    ) == case["expected"]


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("NaN", "0.0001", "0.0001", "ONE_PROVIDER_TICK_ADVERSE", "NO_RECOMMENDATION"), "REJECT_INVALID_STABILITY_INPUT"),
        (("Infinity", "0.0001", "0.0001", "ONE_PROVIDER_TICK_ADVERSE", "NO_RECOMMENDATION"), "REJECT_INVALID_STABILITY_INPUT"),
        (("-0.0001", "0.0001", "0.0001", "ONE_PROVIDER_TICK_ADVERSE", "NO_RECOMMENDATION"), "REJECT_INVALID_STABILITY_INPUT"),
        ((0.0001, "0.0001", "0.0001", "ONE_PROVIDER_TICK_ADVERSE", "NO_RECOMMENDATION"), "REJECT_INVALID_STABILITY_INPUT"),
        ((" 0.0001", "0.0001", "0.0001", "ONE_PROVIDER_TICK_ADVERSE", "NO_RECOMMENDATION"), "REJECT_INVALID_STABILITY_INPUT"),
        (("invalid", "0.0001", "0.0001", "ONE_PROVIDER_TICK_ADVERSE", "NO_RECOMMENDATION"), "REJECT_INVALID_STABILITY_INPUT"),
    ],
)
def test_stability_contract_rejects_malformed_numeric_inputs(values, expected: str) -> None:
    assert resolve_stability_contract(*values) == expected


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("roadmap_title", "S02P02-ROADMAP-EXACT"),
        ("roadmap_output", "S02P02-ROADMAP-EXACT"),
        ("requirement_target", "S02P02-REQUIREMENT-EXACT"),
        ("acceptance_command", "S02P02-ACCEPTANCE-CONTRACT-EXACT"),
        ("task_dependency", "S02P02-TASK-CHAIN-EXACT"),
        ("task_output", "S02P02-TASK-CHAIN-EXACT"),
        ("task_owner", "S02P02-TASK-CHAIN-EXACT"),
        ("trace_evidence", "S02P02-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_drift_fails_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    project = _clone_project(tmp_path)
    if mutation.startswith("roadmap"):
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = next(row for row in next(row for row in value["stages"] if row["id"] == "S02")["phases"] if row["id"] == "P02")
        if mutation == "roadmap_title":
            phase["title"] = "drift"
        else:
            phase["outputs"][0] = "drift.json"
    elif mutation == "requirement_target":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P02")["target"] = "drift"
    elif mutation == "acceptance_command":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        _row(value, "AC-S02-P02")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = _row(value["tasks"], "T-S02-P02-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"][0] = "wrong"
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P02", "requirement_id")["evidence_id"] = "wrong"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("status", "S02P02-MATRIX-TOP-LEVEL"),
        ("paper_id", "S02P02-PAPER-IDS-EXACT-UNIQUE"),
        ("title", "S02P02-PAPER-METADATA-COMPLETE"),
        ("authors", "S02P02-PAPER-METADATA-COMPLETE"),
        ("year", "S02P02-PAPER-METADATA-COMPLETE"),
        ("publication_status", "S02P02-PAPER-URL-DATE-LEVEL-EXACT"),
        ("doi", "S02P02-PAPER-IDENTIFIERS-EXACT"),
        ("arxiv", "S02P02-PAPER-IDENTIFIERS-EXACT"),
        ("url", "S02P02-PAPER-URL-DATE-LEVEL-EXACT"),
        ("source_level", "S02P02-PAPER-URL-DATE-LEVEL-EXACT"),
        ("retrieved_on", "S02P02-PAPER-URL-DATE-LEVEL-EXACT"),
        ("category", "S02P02-PAPER-CATEGORY-CLAIM-BINDINGS"),
        ("claim_binding", "S02P02-PAPER-CATEGORY-CLAIM-BINDINGS"),
        ("finding", "S02P02-PAPER-FINDING-INFERENCE-LIMITATIONS"),
        ("inference", "S02P02-PAPER-FINDING-INFERENCE-LIMITATIONS"),
        ("limitations", "S02P02-PAPER-FINDING-INFERENCE-LIMITATIONS"),
        ("use_decision", "S02P02-PAPER-FINDING-INFERENCE-LIMITATIONS"),
        ("threshold_basis", "S02P02-PAPER-FINDING-INFERENCE-LIMITATIONS"),
        ("coverage", "S02P02-CATEGORY-COVERAGE-CLOSED"),
        ("boundary", "S02P02-GLOBAL-CLAIM-BOUNDARIES"),
        ("legacy", "S02P02-LEGACY-BASELINE-RECONCILED-NONMUTATING"),
        ("research_login", "S02P02-READ-ONLY-RESEARCH-BOUNDARY"),
    ],
)
def test_matrix_metadata_source_and_boundary_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    expected_check: str,
) -> None:
    project = _clone_project(tmp_path)
    path = project / MATRIX_PATH
    value = strict_json_load(path)
    paper = _paper(value, "PAPER-S02-P02-003")
    if mutation == "status":
        value["status"] = "PASS"
    elif mutation == "paper_id":
        paper["id"] = "PAPER-S02-P02-001"
    elif mutation == "title":
        paper["title"] = ""
    elif mutation == "authors":
        paper["authors"] = []
    elif mutation == "year":
        paper["published_year"] = 2027
    elif mutation == "publication_status":
        paper["publication_status"] = "PEER_REVIEWED_JOURNAL"
    elif mutation == "doi":
        paper["identifiers"]["doi"] = "10.invalid"
    elif mutation == "arxiv":
        paper["identifiers"]["arxiv"] = "2303"
    elif mutation == "url":
        paper["primary_url"] = "http://arxiv.org/abs/2303.06021"
    elif mutation == "source_level":
        paper["source_level"] = "L1_PEER_REVIEWED_PRIMARY_PUBLISHER"
    elif mutation == "retrieved_on":
        paper["retrieved_on"] = "2026-07-19"
    elif mutation == "category":
        paper["categories"] = ["UNKNOWN"]
    elif mutation == "claim_binding":
        paper["claim_ids"].append("CLM-UNKNOWN")
    elif mutation == "finding":
        paper["paper_finding"] = "short"
    elif mutation == "inference":
        paper["abd_inference"] = "short"
    elif mutation == "limitations":
        paper["limitations"] = []
    elif mutation == "use_decision":
        paper["use_decision"] = "ADOPT_RUNTIME_PROOF"
    elif mutation == "threshold_basis":
        paper["threshold_basis_decision"] = "PAPER_DERIVED"
    elif mutation == "coverage":
        value["category_coverage"]["CALIBRATION_PROPER_SCORING"] = []
    elif mutation == "boundary":
        value["global_claim_boundaries"].pop()
    elif mutation == "legacy":
        value["legacy_baseline_reconciliation"][2]["historical_baseline_mutated"] = True
    else:
        value["research_mode"]["account_login_performed"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("status", "S02P02-CLAIMS-TOP-LEVEL"),
        ("next", "S02P02-CLAIMS-TOP-LEVEL"),
        ("duplicate_id", "S02P02-CLAIM-IDS-EXACT-UNIQUE"),
        ("category", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("short_claim", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("classification", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("direct_field", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("runtime", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("not_proven", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("no_citations", "S02P02-CLAIM-FIELDS-AND-CLASSIFICATION"),
        ("unknown_paper", "S02P02-CITATIONS-RESOLVE-EXACTLY"),
        ("citation_relation", "S02P02-CITATIONS-RESOLVE-EXACTLY"),
        ("citation_url", "S02P02-CITATIONS-RESOLVE-EXACTLY"),
        ("citation_date", "S02P02-CITATIONS-RESOLVE-EXACTLY"),
        ("citation_level", "S02P02-CITATIONS-RESOLVE-EXACTLY"),
        ("local_overclaim", "S02P02-LOCAL-THRESHOLDS-NOT-PAPER-OVERCLAIMED"),
        ("nonlocal_context_only", "S02P02-LOCAL-THRESHOLDS-NOT-PAPER-OVERCLAIMED"),
        ("inventory_value", "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT"),
        ("inventory_pointer", "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT"),
        ("inventory_duplicate", "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT"),
        ("inventory_claim", "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT"),
        ("inventory_status", "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT"),
        ("target_status", "S02P02-TARGET-IS-UNVERIFIED-NON-GUARANTEE"),
        ("external_effect", "S02P02-CLAIMS-NO-EXTERNAL-EFFECT"),
    ],
)
def test_claim_citation_threshold_and_external_effect_mutations_fail_closed(
    tmp_path: Path,
    mutation: str,
    expected_check: str,
) -> None:
    project = _clone_project(tmp_path)
    path = project / CLAIMS_PATH
    value = strict_json_load(path)
    claim = _claim(value, "CLM-S02-P02-001")
    if mutation == "status":
        value["status"] = "PASS"
    elif mutation == "next":
        value["next_on_acceptance_pass"] = "S02/P04_READY_NOT_STARTED"
    elif mutation == "duplicate_id":
        value["claims"][1]["id"] = claim["id"]
    elif mutation == "category":
        claim["category"] = "UNKNOWN"
    elif mutation == "short_claim":
        claim["claim"] = "short"
    elif mutation == "classification":
        claim["evidence_classification"] = "PAPER_PROVES_RUNTIME"
    elif mutation == "direct_field":
        claim["direct_finding_or_inference"] = "DIRECT_PAPER_FINDING"
    elif mutation == "runtime":
        claim["runtime_status"] = ""
    elif mutation == "not_proven":
        claim["not_proven"] = "short"
    elif mutation == "no_citations":
        claim["citations"] = []
    elif mutation == "unknown_paper":
        claim["citations"][0]["paper_id"] = "PAPER-UNKNOWN"
    elif mutation == "citation_relation":
        claim["citations"][0]["relation"] = "PROVES_THRESHOLD"
    elif mutation == "citation_url":
        claim["citations"][0]["primary_url"] = "https://example.com"
    elif mutation == "citation_date":
        claim["citations"][0]["retrieved_on"] = "2026-07-19"
    elif mutation == "citation_level":
        claim["citations"][0]["source_level"] = "L0"
    elif mutation == "local_overclaim":
        _claim(value, "CLM-S02-P02-002")["citations"][0]["relation"] = "DIRECT_PAPER_FINDING"
    elif mutation == "nonlocal_context_only":
        claim["citations"][0]["relation"] = "CONTEXT_ONLY_NOT_THRESHOLD_EVIDENCE"
    elif mutation == "inventory_value":
        value["local_threshold_inventory"][0]["value"] = "0.51"
    elif mutation == "inventory_pointer":
        value["local_threshold_inventory"][0]["parameter_pointer"] = "/market_model/missing"
    elif mutation == "inventory_duplicate":
        value["local_threshold_inventory"][1]["parameter_pointer"] = value["local_threshold_inventory"][0]["parameter_pointer"]
    elif mutation == "inventory_claim":
        value["local_threshold_inventory"][0]["claim_id"] = "CLM-S02-P02-001"
    elif mutation == "inventory_status":
        value["local_threshold_inventory"][0]["status"] = "PAPER_DERIVED"
    elif mutation == "target_status":
        _claim(value, "CLM-S02-P02-014")["runtime_status"] = "GUARANTEED"
    else:
        value["external_effect_boundary"]["provider_api_called"] = True
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize("threshold_index", range(len(FIXTURE["expected_local_thresholds"])))
def test_each_local_threshold_value_drift_fails_closed(tmp_path: Path, threshold_index: int) -> None:
    project = _clone_project(tmp_path)
    path = project / CLAIMS_PATH
    value = strict_json_load(path)
    current = value["local_threshold_inventory"][threshold_index]["value"]
    value["local_threshold_inventory"][threshold_index]["value"] = current + 1 if isinstance(current, int) else current + "1"
    _write_json(path, value)
    _failed(evaluate_contract(project), "S02P02-LOCAL-THRESHOLD-INVENTORY-EXACT")


@pytest.mark.parametrize(
    "mutation",
    ["evidence_status", "evidence_missing", "rollback_status", "rollback_missing", "index", "signed_parameter"],
)
def test_p01_prerequisite_tampering_blocks_p02(tmp_path: Path, mutation: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "evidence_missing":
        (project / P01_EVIDENCE_PATH).unlink()
    elif mutation == "rollback_missing":
        (project / P01_ROLLBACK_PATH).unlink()
    elif mutation == "rollback_status":
        path = project / P01_ROLLBACK_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    elif mutation == "index":
        path = project / "machine/evidence/evidence_index.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
        _row(rows, "INDEX-AC-S02-P01")["artifact_sha256"] = "0" * 64
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    elif mutation == "signed_parameter":
        path = project / P01_EVIDENCE_PATH
        value = strict_json_load(path)
        value["hashes"]["inputs"]["machine/facts/parameters.json"] = "0" * 64
        _write_json(path, value)
    else:
        path = project / P01_EVIDENCE_PATH
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    _failed(evaluate_contract(project), "S02P02-P01-IMMUTABLE-PREREQUISITE")


@pytest.mark.parametrize(
    "relative",
    [
        "research_reuse_matrix.json",
        "license_inventory.json",
        "tests/S02/P03_test.py",
        "machine/tests/fixtures/S02_P03.json",
        "machine/evidence/EVD-S02-P03.json",
        "machine/evidence/EVD-S02-P03_rollback.json",
    ],
)
def test_s02_p03_cannot_start_inside_p02_run(tmp_path: Path, relative: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S02P02-P03-NOT-STARTED")


def test_s02_p03_index_cannot_advance_inside_p02_run(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/evidence_index.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    _row(rows, "INDEX-AC-S02-P03")["status"] = "READY"
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    _failed(evaluate_contract(project), "S02P02-P03-NOT-STARTED")


@pytest.mark.parametrize("relative", [MATRIX_PATH, CLAIMS_PATH, FIXTURE_PATH])
def test_duplicate_json_keys_fail_strict_parse(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"schema_version":"1.0.0","schema_version":"drift"}\n', encoding="utf-8")
    expected = {
        MATRIX_PATH: "S02P02-MATRIX-STRICT-JSON",
        CLAIMS_PATH: "S02P02-CLAIMS-STRICT-JSON",
        FIXTURE_PATH: "S02P02-FIXTURE-STRICT-JSON",
    }[relative]
    _failed(evaluate_contract(project), expected)


@pytest.mark.parametrize("relative", [MATRIX_PATH, CLAIMS_PATH, FIXTURE_PATH])
def test_binary_float_in_authoritative_artifact_fails_closed(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    value = strict_json_load(path)
    value["unauthorized_binary_float"] = 0.1
    _write_json(path, value)
    _failed(evaluate_contract(project), "S02P02-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS")


def test_rollback_drill_restores_all_signed_inputs_without_external_effect() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == FIXTURE["rollback_artifact_count"]
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())


def test_evidence_build_is_deterministic_portable_and_research_only() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first
    assert first["next"] == "S02/P03_READY_NOT_STARTED"
    assert first["hashes"]["model_not_executed_reason"]
    assert first["external_effect_boundary"]["github_upload_performed"] is False
    assert first["external_effect_boundary"]["model_or_strategy_executed"] is False
    assert first["external_effect_boundary"]["real_order_capability_present"] is False
    assert first["external_effect_boundary"]["return_or_guarantee_claimed"] is False
    assert first["external_effect_boundary"]["s02_p03_started"] is False
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert str(ROOT) not in rendered
    assert ("/" + "Users/") not in rendered
    assert first["decision_sha256"]


def test_paper_claim_graph_is_closed_without_orphans() -> None:
    matrix = strict_json_load(ROOT / MATRIX_PATH)
    claims = strict_json_load(ROOT / CLAIMS_PATH)
    paper_edges = {
        (paper["id"], claim_id)
        for paper in matrix["papers"]
        for claim_id in paper["claim_ids"]
    }
    citation_edges = {
        (citation["paper_id"], claim["id"])
        for claim in claims["claims"]
        for citation in claim["citations"]
    }
    assert citation_edges == paper_edges
    assert {paper_id for paper_id, _ in citation_edges} == set(FIXTURE["expected_paper_ids"])
    assert {claim_id for _, claim_id in citation_edges} == set(FIXTURE["expected_claim_ids"])


def test_legacy_source_overclaims_are_corrected_without_mutating_historical_baseline() -> None:
    matrix = strict_json_load(ROOT / MATRIX_PATH)
    legacy = strict_json_load(ROOT / "machine/facts/sources.json")
    legacy_map = {row["id"]: row for row in legacy}
    assert legacy_map["SRC-020"]["title"] == "Knowing when to bet"
    assert "删除最高盈利1%复测" in legacy_map["SRC-022"]["used_for"]
    reconciliation = {row["baseline_source_id"]: row for row in matrix["legacy_baseline_reconciliation"]}
    assert "A statistical theory of optimal decision-making in sports betting" in reconciliation["SRC-020"]["p02_resolution"]
    assert "L2_AUTHOR_PREPRINT_PRIMARY" in reconciliation["SRC-021"]["p02_resolution"]
    assert "本地工程阈值" in reconciliation["SRC-022"]["p02_resolution"]
    assert all(row["historical_baseline_mutated"] is False for row in reconciliation.values())


def test_artifacts_make_no_training_backtest_account_deployment_order_or_return_claim() -> None:
    matrix = strict_json_load(ROOT / MATRIX_PATH)
    claims = strict_json_load(ROOT / CLAIMS_PATH)
    mode = matrix["research_mode"]
    boundary = claims["external_effect_boundary"]
    assert mode["prediction_model_executed"] is False
    assert mode["training_or_backtest_performed"] is False
    assert mode["account_login_performed"] is False
    assert mode["paid_source_or_api_used"] is False
    assert mode["production_deployment_performed"] is False
    assert boundary["incremental_cash_spent_aud"] == "0.00"
    assert boundary["provider_api_called"] is False
    assert boundary["real_order_capability_present"] is False
    assert boundary["return_or_roi_verified"] is False
    assert boundary["return_or_guarantee_claimed"] is False
    assert boundary["all_market_coverage_claimed"] is False


def test_evidence_paths_are_reserved_for_p02_while_p04_progresses_separately() -> None:
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P02.json"
    assert ROLLBACK_EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P02_rollback.json"
    assert (ROOT / "research_reuse_matrix.json").exists()
    assert (ROOT / "license_inventory.json").exists()
    assert (ROOT / "research_gaps.json").exists()
    assert (ROOT / "counterevidence.json").exists()
    assert (ROOT / "review_schedule.json").exists()
    assert not (ROOT / "machine/facts/stage2_review_contract.json").exists()
