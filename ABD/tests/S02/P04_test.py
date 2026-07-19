from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.open_source_reuse import verify_existing_phase_evidence as verify_p03_evidence
from abd_acceptance.research_gap_audit import (
    COUNTEREVIDENCE_PATH,
    EVIDENCE_PATH,
    FIXTURE_PATH,
    GAPS_PATH,
    P03_EVIDENCE_SHA256,
    P03_ROLLBACK_SHA256,
    PINNED_PHASE_HASHES,
    REVIEW_SCHEDULE_PATH,
    ROLLBACK_EVIDENCE_PATH,
    TEST_PATH,
    build_evidence,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    resolve_gap_disposition,
)


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
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _row(rows, item_id: str, key: str = "id"):
    return next(row for row in rows if row[key] == item_id)


def _failed(result, check_id: str) -> None:
    assert result["status"] == "FAIL", result
    assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def _resolve(inputs: dict) -> str:
    return resolve_gap_disposition(**inputs)


def test_baseline_research_gap_contract_passes_without_runtime_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["decision"] == "RESEARCH_GAPS_COUNTEREVIDENCE_AND_REVIEW_ROUTES_FROZEN"
    assert result["gap_status"] == "26_OPEN_EXPLICIT_0_RESOLVED_0_SILENT"
    assert result["exhaustiveness_status"] == "SCOPED_NON_EXHAUSTIVE_NO_INTERNET_EXHAUSTION_CLAIM"
    assert result["production_status"] == "NOT_DEPLOYED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["release_status"] == "NOT_READY_STAGE_REVIEW_REQUIRED"
    assert result["next"] == FIXTURE["expected_next"]
    check_ids = [row["id"] for row in result["checks"]]
    assert len(check_ids) == len(set(check_ids))


def test_p03_signed_receipt_is_exact_prerequisite_without_successor_recursion() -> None:
    result = verify_p03_evidence(
        ROOT,
        verify_git_history=True,
        verify_p02_prerequisite=True,
        verify_successor_state=False,
    )
    assert result["status"] == "PASS", result
    assert result["decision"] == "S02_P03_EVIDENCE_VERIFIED"
    assert result["evidence_sha256"] == P03_EVIDENCE_SHA256
    assert result["rollback_sha256"] == P03_ROLLBACK_SHA256
    assert result["next"] == "S02/P04_READY_NOT_STARTED"


@pytest.mark.parametrize(
    "relative",
    [GAPS_PATH, COUNTEREVIDENCE_PATH, REVIEW_SCHEDULE_PATH, FIXTURE_PATH],
)
def test_frozen_phase_artifact_hashes_match_oracle_pins(relative: Path) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative.as_posix()]


@pytest.mark.parametrize("gap_id", FIXTURE["expected_gap_ids"])
def test_every_registered_gap_is_explicit_open_non_pass_safe_and_reviewable(gap_id: str) -> None:
    artifact = strict_json_load(ROOT / GAPS_PATH)
    gap = _row(artifact["gaps"], gap_id)
    assert gap["gap_state"] == "OPEN_EXPLICIT"
    assert gap["evidence_maturity"]
    assert gap["assessment_confidence"]
    assert gap["source_refs"]
    assert gap["safe_default"]
    assert gap["closure_evidence"]
    assert gap["review_ids"]
    assert gap["blocks"]
    assert type(gap["owner_input_required_for_closure"]) is bool


@pytest.mark.parametrize("counter_id", FIXTURE["expected_counterevidence_ids"])
def test_every_counterevidence_record_has_local_evidence_and_fail_closed_routes(counter_id: str) -> None:
    artifact = strict_json_load(ROOT / COUNTEREVIDENCE_PATH)
    record = _row(artifact["records"], counter_id)
    assert record["proposition"]
    assert record["verdict"]
    assert record["implication"]
    assert record["safe_default"]
    assert record["gap_ids"]
    assert record["review_ids"]
    assert record["evidence_refs"]
    assert all(ref["artifact"] and ref["ids"] for ref in record["evidence_refs"])


@pytest.mark.parametrize("review_id", FIXTURE["expected_review_ids"])
def test_every_review_route_is_registered_but_not_executed(review_id: str) -> None:
    artifact = strict_json_load(ROOT / REVIEW_SCHEDULE_PATH)
    review = _row(artifact["reviews"], review_id)
    assert review["trigger"]
    assert review["required_inputs"]
    assert review["required_outputs"]
    assert review["gap_ids"]
    assert review["overdue_action"]
    assert review["external_access_allowed_in_p04"] is False
    assert review["current_status"] not in {"PASS", "COMPLETE", "EXECUTED", "REVIEWED"}


@pytest.mark.parametrize(
    "route",
    strict_json_load(ROOT / GAPS_PATH)["receipt_unknown_coverage"],
    ids=lambda row: row["unknown_id"],
)
def test_every_signed_receipt_unknown_is_indexed_once_and_routed(route: dict) -> None:
    receipt = strict_json_load(ROOT / f"machine/evidence/{route['evidence_id']}.json")
    assert 0 <= route["index"] < len(receipt["explicit_unknowns"])
    assert route["gap_ids"]
    assert set(route["gap_ids"]).issubset(set(FIXTURE["expected_gap_ids"]))


@pytest.mark.parametrize("fact_id", FIXTURE["expected_provider_unknown_fact_ids"])
def test_every_provider_unknown_fact_has_an_explicit_gap_route(fact_id: str) -> None:
    routes = strict_json_load(ROOT / GAPS_PATH)["provider_unknown_fact_coverage"]
    assert routes[fact_id]


@pytest.mark.parametrize("key", FIXTURE["expected_runtime_prerequisite_keys"])
def test_every_false_runtime_prerequisite_has_an_explicit_gap_route(key: str) -> None:
    routes = strict_json_load(ROOT / GAPS_PATH)["runtime_prerequisite_coverage"]
    assert routes[key]


@pytest.mark.parametrize("claim_id", FIXTURE["expected_model_claim_ids"])
def test_every_model_claim_has_an_explicit_gap_route(claim_id: str) -> None:
    routes = strict_json_load(ROOT / GAPS_PATH)["model_claim_coverage"]
    assert routes[claim_id]


@pytest.mark.parametrize("pointer", FIXTURE["expected_local_threshold_pointers"])
def test_every_local_threshold_has_an_explicit_gap_route(pointer: str) -> None:
    routes = strict_json_load(ROOT / GAPS_PATH)["local_threshold_coverage"]
    assert routes[pointer]


@pytest.mark.parametrize("source_id", sorted(FIXTURE["expected_reuse_unknown_counts"]))
def test_every_reuse_project_preserves_all_unverified_items(source_id: str) -> None:
    routes = strict_json_load(ROOT / GAPS_PATH)["reuse_unknown_coverage"]
    assert routes[source_id]["expected_unknown_count"] == FIXTURE["expected_reuse_unknown_counts"][source_id]
    assert routes[source_id]["gap_ids"]


@pytest.mark.parametrize("rule_id", FIXTURE["expected_regulatory_rule_ids"])
def test_every_regulatory_rule_has_an_explicit_gap_route(rule_id: str) -> None:
    routes = strict_json_load(ROOT / GAPS_PATH)["regulatory_rule_coverage"]
    assert routes[rule_id]


@pytest.mark.parametrize("case", FIXTURE["decision_vectors"], ids=lambda row: row["id"])
def test_frozen_gap_disposition_vectors_are_fail_closed(case: dict) -> None:
    assert _resolve(case["inputs"]) == case["expected"]


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_delta_strings"])
@pytest.mark.parametrize("adverse_odds_tick", [False, True])
def test_plus_minus_point_0001_and_adverse_tick_cannot_relax_an_open_block(delta: str, adverse_odds_tick: bool) -> None:
    result = resolve_gap_disposition(
        gap_state="OPEN_EXPLICIT",
        registered=True,
        has_safe_default=True,
        review_route_count=2,
        closure_evidence_verified=False,
        blocks_capability=True,
        numeric_delta=delta,
        adverse_odds_tick=adverse_odds_tick,
    )
    assert result == "REGISTERED_OPEN_CAPABILITY_BLOCKED"


@pytest.mark.parametrize("registered", [False, True])
@pytest.mark.parametrize("has_safe_default", [False, True])
@pytest.mark.parametrize("review_route_count", [0, 1])
@pytest.mark.parametrize("closure_evidence_verified", [False, True])
@pytest.mark.parametrize("blocks_capability", [False, True])
@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_delta_strings"])
def test_gap_disposition_is_deterministic_and_preserves_fail_closed_precedence(
    registered: bool,
    has_safe_default: bool,
    review_route_count: int,
    closure_evidence_verified: bool,
    blocks_capability: bool,
    delta: str,
) -> None:
    kwargs = {
        "gap_state": "OPEN_EXPLICIT",
        "registered": registered,
        "has_safe_default": has_safe_default,
        "review_route_count": review_route_count,
        "closure_evidence_verified": closure_evidence_verified,
        "blocks_capability": blocks_capability,
        "numeric_delta": delta,
        "adverse_odds_tick": True,
    }
    first = resolve_gap_disposition(**kwargs)
    second = resolve_gap_disposition(**kwargs)
    assert first == second
    if not registered:
        assert first == "BLOCK_SILENT_GAP"
    elif not has_safe_default:
        assert first == "BLOCK_UNSAFE_OPEN_GAP"
    elif review_route_count == 0:
        assert first == "BLOCK_UNSCHEDULED_GAP"
    elif closure_evidence_verified:
        assert first == "BLOCK_CONTRADICTORY_GAP_STATE"
    elif blocks_capability:
        assert first == "REGISTERED_OPEN_CAPABILITY_BLOCKED"
    else:
        assert first == "REGISTERED_OPEN_MONITOR"


@pytest.mark.parametrize(
    "override",
    [
        {"gap_state": "UNKNOWN"},
        {"gap_state": ""},
        {"registered": 1},
        {"registered": "true"},
        {"has_safe_default": 0},
        {"review_route_count": -1},
        {"review_route_count": True},
        {"review_route_count": "1"},
        {"closure_evidence_verified": None},
        {"blocks_capability": "false"},
        {"numeric_delta": 0},
        {"numeric_delta": 0.0001},
        {"numeric_delta": " 0"},
        {"numeric_delta": "0.0000"},
        {"numeric_delta": "0.0002"},
        {"numeric_delta": "-0.0002"},
        {"numeric_delta": "NaN"},
        {"numeric_delta": "Infinity"},
        {"numeric_delta": "-Infinity"},
        {"adverse_odds_tick": 1},
    ],
)
def test_gap_disposition_rejects_unknown_enums_types_and_unfrozen_numeric_inputs(override: dict) -> None:
    kwargs = {
        "gap_state": "OPEN_EXPLICIT",
        "registered": True,
        "has_safe_default": True,
        "review_route_count": 1,
        "closure_evidence_verified": False,
        "blocks_capability": True,
        "numeric_delta": "0",
        "adverse_odds_tick": False,
    }
    kwargs.update(override)
    with pytest.raises((TypeError, ValueError)):
        resolve_gap_disposition(**kwargs)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("MISSING_GAP", "S02P04-GAPS-IDS-EXACT"),
        ("DUPLICATE_GAP_ID", "S02P04-GAPS-IDS-EXACT"),
        ("GAP_MARKED_RESOLVED_WITHOUT_EVIDENCE", "S02P04-GAPS-ROWS-COMPLETE-OPEN"),
        ("MISSING_SAFE_DEFAULT", "S02P04-GAPS-ROWS-COMPLETE-OPEN"),
        ("MISSING_REVIEW_ROUTE", "S02P04-GAPS-ROWS-COMPLETE-OPEN"),
        ("UNROUTED_RECEIPT_UNKNOWN", "S02P04-COVERAGE-ALL-RECEIPT-UNKNOWNS-ROUTED"),
        ("UNROUTED_PROVIDER_UNKNOWN", "S02P04-COVERAGE-ALL-PROVIDER-UNKNOWNS-ROUTED"),
        ("UNROUTED_RUNTIME_PREREQUISITE", "S02P04-COVERAGE-ALL-RUNTIME-PREREQUISITES-ROUTED"),
        ("UNROUTED_MODEL_CLAIM", "S02P04-COVERAGE-ALL-MODEL-CLAIMS-ROUTED"),
        ("UNROUTED_LOCAL_THRESHOLD", "S02P04-COVERAGE-ALL-LOCAL-THRESHOLDS-ROUTED"),
        ("REUSE_UNKNOWN_COUNT_DRIFT", "S02P04-COVERAGE-ALL-REUSE-UNKNOWNS-ROUTED"),
        ("UNROUTED_REGULATORY_RULE", "S02P04-COVERAGE-ALL-REGULATORY-RULES-ROUTED"),
        ("COUNTEREVIDENCE_WITHOUT_LOCAL_REF", "S02P04-COUNTER-ROWS-COMPLETE-LOCAL-REFS"),
        ("COUNTEREVIDENCE_UNKNOWN_GAP", "S02P04-COUNTER-ROWS-COMPLETE-LOCAL-REFS"),
        ("REVIEW_UNKNOWN_GAP", "S02P04-REVIEW-ROWS-COMPLETE-NOT-EXECUTED"),
        ("REVIEW_MARKED_EXECUTED", "S02P04-REVIEW-ROWS-COMPLETE-NOT-EXECUTED"),
        ("ABSOLUTE_DATE_NOT_SOURCE_BOUND", "S02P04-REVIEW-ABSOLUTE-DATE-SOURCE-BOUND"),
        ("EXHAUSTIVE_RESEARCH_CLAIMED", "S02P04-GAPS-SEMANTICS-FAIL-CLOSED"),
        ("SILENT_GAP_NONZERO", "S02P04-COVERAGE-SUMMARY-EXACT"),
        ("P03_RECEIPT_TAMPERED", "S02P04-P03-IMMUTABLE-PREREQUISITE"),
        ("STAGE2_REVIEW_ARTIFACT_PRESENT", "S02P04-STAGE2-REVIEW-NOT-STARTED"),
        ("INCREMENTAL_CASH_NONZERO", "S02P04-NO-EXTERNAL-EFFECT-ALL-ARTIFACTS"),
        ("PRODUCTION_OR_RETURN_CLAIM", "S02P04-NO-EXTERNAL-EFFECT-ALL-ARTIFACTS"),
        ("ABSOLUTE_LOCAL_PATH_PRESENT", "S02P04-NO-ABSOLUTE-LOCAL-PATH"),
        ("BINARY_FLOAT_PRESENT", "S02P04-NO-BINARY-FLOAT-IN-AUTHORITATIVE-ARTIFACTS"),
    ],
)
def test_all_25_frozen_fault_mutations_fail_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    assert mutation in FIXTURE["fault_mutations"]
    project = _clone_project(tmp_path)
    gaps_path = project / GAPS_PATH
    counter_path = project / COUNTEREVIDENCE_PATH
    review_path = project / REVIEW_SCHEDULE_PATH

    if mutation in {
        "MISSING_GAP", "DUPLICATE_GAP_ID", "GAP_MARKED_RESOLVED_WITHOUT_EVIDENCE",
        "MISSING_SAFE_DEFAULT", "MISSING_REVIEW_ROUTE", "UNROUTED_RECEIPT_UNKNOWN",
        "UNROUTED_PROVIDER_UNKNOWN", "UNROUTED_RUNTIME_PREREQUISITE", "UNROUTED_MODEL_CLAIM",
        "UNROUTED_LOCAL_THRESHOLD", "REUSE_UNKNOWN_COUNT_DRIFT", "UNROUTED_REGULATORY_RULE",
        "EXHAUSTIVE_RESEARCH_CLAIMED", "SILENT_GAP_NONZERO", "INCREMENTAL_CASH_NONZERO",
        "ABSOLUTE_LOCAL_PATH_PRESENT", "BINARY_FLOAT_PRESENT",
    }:
        value = strict_json_load(gaps_path)
        first = value["gaps"][0]
        if mutation == "MISSING_GAP":
            value["gaps"].pop()
        elif mutation == "DUPLICATE_GAP_ID":
            value["gaps"][1]["id"] = first["id"]
        elif mutation == "GAP_MARKED_RESOLVED_WITHOUT_EVIDENCE":
            first["gap_state"] = "RESOLVED_VERIFIED"
        elif mutation == "MISSING_SAFE_DEFAULT":
            first["safe_default"] = ""
        elif mutation == "MISSING_REVIEW_ROUTE":
            first["review_ids"] = []
        elif mutation == "UNROUTED_RECEIPT_UNKNOWN":
            value["receipt_unknown_coverage"].pop()
        elif mutation == "UNROUTED_PROVIDER_UNKNOWN":
            value["provider_unknown_fact_coverage"].pop(next(iter(value["provider_unknown_fact_coverage"])))
        elif mutation == "UNROUTED_RUNTIME_PREREQUISITE":
            value["runtime_prerequisite_coverage"].pop(next(iter(value["runtime_prerequisite_coverage"])))
        elif mutation == "UNROUTED_MODEL_CLAIM":
            value["model_claim_coverage"].pop(next(iter(value["model_claim_coverage"])))
        elif mutation == "UNROUTED_LOCAL_THRESHOLD":
            value["local_threshold_coverage"].pop(next(iter(value["local_threshold_coverage"])))
        elif mutation == "REUSE_UNKNOWN_COUNT_DRIFT":
            value["reuse_unknown_coverage"]["SRC-013"]["expected_unknown_count"] = 2
        elif mutation == "UNROUTED_REGULATORY_RULE":
            value["regulatory_rule_coverage"].pop(next(iter(value["regulatory_rule_coverage"])))
        elif mutation == "EXHAUSTIVE_RESEARCH_CLAIMED":
            value["gap_semantics"]["internet_or_literature_exhaustive_claimed"] = True
        elif mutation == "SILENT_GAP_NONZERO":
            value["coverage_summary"]["silent_gap_count"] = 1
        elif mutation == "INCREMENTAL_CASH_NONZERO":
            value["external_effect_boundary"]["incremental_cash_spent_aud"] = "0.01"
        elif mutation == "ABSOLUTE_LOCAL_PATH_PRESENT":
            first["safe_default"] = "/" + "Users/example/private"
        else:
            value["coverage_summary"]["silent_gap_count"] = 0.0
        _write_json(gaps_path, value)
    elif mutation in {"COUNTEREVIDENCE_WITHOUT_LOCAL_REF", "COUNTEREVIDENCE_UNKNOWN_GAP", "PRODUCTION_OR_RETURN_CLAIM"}:
        value = strict_json_load(counter_path)
        if mutation == "COUNTEREVIDENCE_WITHOUT_LOCAL_REF":
            value["records"][0]["evidence_refs"] = []
        elif mutation == "COUNTEREVIDENCE_UNKNOWN_GAP":
            value["records"][0]["gap_ids"] = ["GAP-NOT-REGISTERED"]
        else:
            value["external_effect_boundary"]["return_or_guarantee_claimed"] = True
        _write_json(counter_path, value)
    elif mutation in {"REVIEW_UNKNOWN_GAP", "REVIEW_MARKED_EXECUTED", "ABSOLUTE_DATE_NOT_SOURCE_BOUND"}:
        value = strict_json_load(review_path)
        if mutation == "REVIEW_UNKNOWN_GAP":
            value["reviews"][0]["gap_ids"] = ["GAP-NOT-REGISTERED"]
        elif mutation == "REVIEW_MARKED_EXECUTED":
            value["reviews"][0]["current_status"] = "PASS_EXECUTED"
        else:
            _row(value["reviews"], "REV-S02-P04-002")["date_basis"] = "INVENTED_DATE"
        _write_json(review_path, value)
    elif mutation == "P03_RECEIPT_TAMPERED":
        path = project / "machine/evidence/EVD-S02-P03.json"
        value = strict_json_load(path)
        value["status"] = "FAIL"
        _write_json(path, value)
    else:
        path = project / "machine/facts/stage2_review_contract.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("roadmap_title", "S02P04-TASKPACK-ROADMAP-EXACT"),
        ("requirement_target", "S02P04-TASKPACK-REQUIREMENT-EXACT"),
        ("acceptance_command", "S02P04-TASKPACK-ACCEPTANCE-EXACT"),
        ("task_dependency", "S02P04-TASKPACK-TASK-DAG-EXACT"),
        ("task_output", "S02P04-TASKPACK-TASK-OUTPUTS-EXACT"),
        ("task_owner", "S02P04-TASKPACK-TASK-GATES-EXACT"),
        ("trace_evidence", "S02P04-TASKPACK-TRACEABILITY-EXACT"),
    ],
)
def test_taskpack_contract_drift_fails_closed(tmp_path: Path, mutation: str, expected_check: str) -> None:
    project = _clone_project(tmp_path)
    if mutation == "roadmap_title":
        path = project / "machine/facts/roadmap.json"
        value = strict_json_load(path)
        phase = _row(_row(value["stages"], "S02")["phases"], "P04")
        phase["title"] = "drift"
    elif mutation == "requirement_target":
        path = project / "machine/facts/requirements.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P04")["target"] = "drift"
    elif mutation == "acceptance_command":
        path = project / "machine/facts/acceptance_contracts.json"
        value = strict_json_load(path)
        _row(value, "AC-S02-P04")["oracle"]["command"] = "true"
    elif mutation.startswith("task"):
        path = project / "machine/facts/task_graph.json"
        value = strict_json_load(path)
        task = _row(value["tasks"], "T-S02-P04-02")
        if mutation == "task_dependency":
            task["depends_on"] = []
        elif mutation == "task_output":
            task["outputs"][0] = "wrong"
        else:
            task["owner_input_required"] = True
    else:
        path = project / "machine/facts/traceability_matrix.json"
        value = strict_json_load(path)
        _row(value, "REQ-S02-P04", "requirement_id")["evidence_id"] = "wrong"
    _write_json(path, value)
    _failed(evaluate_contract(project), expected_check)


@pytest.mark.parametrize("relative", [GAPS_PATH, COUNTEREVIDENCE_PATH, REVIEW_SCHEDULE_PATH, FIXTURE_PATH])
def test_strict_json_duplicate_keys_fail_closed(tmp_path: Path, relative: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"schema_version":"1.0.0","schema_version":"drift"}\n', encoding="utf-8")
    result = evaluate_contract(project)
    assert result["status"] == "FAIL"
    assert any("STRICT-JSON" in item for item in result["summary"]["failed_check_ids"])


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("relative", [GAPS_PATH, COUNTEREVIDENCE_PATH, REVIEW_SCHEDULE_PATH])
def test_nonfinite_json_numbers_fail_closed(tmp_path: Path, relative: Path, token: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.write_text('{"value":%s}\n' % token, encoding="utf-8")
    assert evaluate_contract(project)["status"] == "FAIL"


def test_p03_rollback_tamper_breaks_immutable_prerequisite(tmp_path: Path) -> None:
    project = _clone_project(tmp_path)
    path = project / "machine/evidence/EVD-S02-P03_rollback.json"
    value = strict_json_load(path)
    value["status"] = "FAIL"
    _write_json(path, value)
    _failed(evaluate_contract(project), "S02P04-P03-IMMUTABLE-PREREQUISITE")


@pytest.mark.parametrize(
    "relative",
    [
        "machine/facts/stage2_review_contract.json",
        "machine/tests/fixtures/S02_STAGE_REVIEW.json",
        "tests/S02/stage_review_test.py",
        "abd_acceptance/stage2_review.py",
        "machine/evidence/EVD-S02-STAGE-REVIEW.json",
        "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json",
    ],
)
def test_any_stage2_review_artifact_fails_current_phase_guard(tmp_path: Path, relative: str) -> None:
    project = _clone_project(tmp_path)
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    _failed(evaluate_contract(project), "S02P04-STAGE2-REVIEW-NOT-STARTED")


def test_rollback_drill_restores_all_ten_signed_artifacts_without_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert len(result["artifacts"]) == FIXTURE["expected_rollback_artifact_count"] == 10
    for artifact in result["artifacts"].values():
        assert artifact["status"] == "PASS"
        assert artifact["corrupted_sha256"] != artifact["signed_sha256"]
        assert artifact["restored_sha256"] == artifact["signed_sha256"]


@pytest.mark.parametrize(
    "artifact",
    [
        GAPS_PATH.as_posix(),
        COUNTEREVIDENCE_PATH.as_posix(),
        REVIEW_SCHEDULE_PATH.as_posix(),
        FIXTURE_PATH.as_posix(),
        "machine/evidence/EVD-S02-P03.json",
        "machine/evidence/EVD-S02-P03_rollback.json",
        "provider_facts_snapshot.json",
        "model_claims.json",
        "research_reuse_matrix.json",
        "license_inventory.json",
    ],
)
def test_rollback_drill_covers_each_required_artifact(artifact: str) -> None:
    result = perform_rollback_drill(ROOT)
    assert result["artifacts"][artifact]["status"] == "PASS"


def test_evidence_build_is_deterministic_and_preserves_stage_review_boundary() -> None:
    evidence_a, rollback_a = build_evidence(ROOT, require_external_reports=False)
    evidence_b, rollback_b = build_evidence(ROOT, require_external_reports=False)
    assert evidence_a == evidence_b
    assert rollback_a == rollback_b
    assert evidence_a["status"] == "PASS", evidence_a["validation"]["summary"]
    assert evidence_a["next"] == FIXTURE["expected_next"]
    assert evidence_a["artifacts"] == {
        "ART-S02-P04-01": GAPS_PATH.as_posix(),
        "ART-S02-P04-02": COUNTEREVIDENCE_PATH.as_posix(),
        "ART-S02-P04-03": REVIEW_SCHEDULE_PATH.as_posix(),
    }
    unsigned = dict(evidence_a)
    decision_hash = unsigned.pop("decision_sha256")
    rendered = (json.dumps(unsigned, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert decision_hash == hashlib.sha256(rendered).hexdigest()


def test_evidence_build_records_no_network_account_install_model_deployment_order_cash_or_return_effect() -> None:
    evidence, _ = build_evidence(ROOT, require_external_reports=False)
    effects = evidence["external_effect_boundary"]
    assert effects == FIXTURE["expected_external_effect_boundary"]
    assert all(
        effects[key] is False
        for key in [
            "network_research_performed_in_p04",
            "provider_or_cloud_account_accessed",
            "provider_api_called",
            "repository_cloned",
            "package_installed",
            "model_or_strategy_executed",
            "production_deployed",
            "real_order_capability_present",
            "return_or_guarantee_claimed",
            "stage2_review_started",
            "github_upload_performed",
        ]
    )
    assert effects["incremental_cash_spent_aud"] == "0.00"


def test_artifacts_and_evidence_contain_no_absolute_local_paths() -> None:
    evidence, rollback = build_evidence(ROOT, require_external_reports=False)
    rendered = json.dumps(
        [
            evidence,
            rollback,
            strict_json_load(ROOT / GAPS_PATH),
            strict_json_load(ROOT / COUNTEREVIDENCE_PATH),
            strict_json_load(ROOT / REVIEW_SCHEDULE_PATH),
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    assert str(ROOT) not in rendered
    assert ("/" + "Users/") not in rendered
    assert ("/private/" + "var/") not in rendered


def test_registration_review_routes_and_stage_readiness_do_not_resolve_any_gap() -> None:
    gaps = strict_json_load(ROOT / GAPS_PATH)
    schedule = strict_json_load(ROOT / REVIEW_SCHEDULE_PATH)
    counter = strict_json_load(ROOT / COUNTEREVIDENCE_PATH)
    assert gaps["gap_semantics"]["registered_gap_is_resolved"] is False
    assert gaps["coverage_summary"]["open_gap_count"] == 26
    assert gaps["coverage_summary"]["resolved_gap_count"] == 0
    assert schedule["schedule_semantics"]["scheduled_is_executed"] is False
    assert schedule["schedule_semantics"]["review_route_closes_gap"] is False
    assert schedule["coverage_summary"]["current_phase_reviews_executed"] == 0
    assert counter["summary"]["thirty_percent_target_verified_or_guaranteed"] is False


def test_p04_receipt_paths_are_reserved_and_stage2_review_is_absent() -> None:
    assert TEST_PATH.as_posix() == "tests/S02/P04_test.py"
    assert EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P04.json"
    assert ROLLBACK_EVIDENCE_PATH.as_posix() == "machine/evidence/EVD-S02-P04_rollback.json"
    assert not (ROOT / "machine/facts/stage2_review_contract.json").exists()
    assert not (ROOT / "abd_acceptance/stage2_review.py").exists()
    assert not (ROOT / "tests/S02/stage_review_test.py").exists()
