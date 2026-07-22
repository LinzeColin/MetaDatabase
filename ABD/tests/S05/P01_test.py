from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.market_ontology import (
    ALL_KINDS,
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXED_CLOCK,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    JUNIT_PATH,
    KNOWN_KINDS,
    ONTOLOGY_PATH,
    PINNED_PHASE_HASHES,
    REQUIREMENT_ID,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    SCHEMA_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    UNKNOWN_REASON_CODES,
    MarketOntologyError,
    _structural_self_hash,
    build_coverage_manifest,
    build_evidence,
    classify_discovery_object,
    evaluate_contract as _evaluate_contract,
    perform_rollback_drill,
    safe_build_coverage_manifest,
    validate_candidate_preflight,
    validate_coverage_manifest,
    validate_ontology,
    validate_signed_receipt_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from abd_acceptance.stage2_delivery import verify_stage2_delivery
from abd_acceptance.stage4_delivery import RECEIPT_PATH as S04_RECEIPT_PATH
from abd_acceptance.stage4_delivery import verify_stage4_delivery


ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = strict_json_load(ROOT / ONTOLOGY_PATH)
SCHEMA = strict_json_load(ROOT / SCHEMA_PATH)
FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)
RAW = FIXTURE["raw_discovery_objects"]


def evaluate_contract(root: Path, require_external_reports: bool = False):
    return _evaluate_contract(
        root,
        require_external_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github")
    return destination


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _assert_failed(result: dict, check_id: str | None = None) -> None:
    assert result["status"] == "FAIL", result
    if check_id is not None:
        assert check_id in result["summary"]["failed_check_ids"], result["summary"]


def test_candidate_preflight_passes() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "S05_P01_CANDIDATE_VALID"
    assert result["next"] == FIXTURE["expected_next"]


def test_contract_passes_without_external_reports() -> None:
    result = evaluate_contract(ROOT)
    assert result["status"] == "PASS", result
    assert result["decision"] == "MARKET_ONTOLOGY_AND_COVERAGE_SCHEMA_FROZEN"
    assert result["phase_status"] == "S05_P01_PASS"
    assert result["summary"]["checks"] >= FIXTURE["expected_oracle_check_minimum"]
    assert result["summary"]["failed"] == 0
    assert result["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert result["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert result["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert result["next"] == "S05/P02_READY_NOT_STARTED"


def test_taskpack_identity_and_scope_are_exact() -> None:
    assert CONTRACT_ID == "AC-S05-P01"
    assert REQUIREMENT_ID == "REQ-S05-P01"
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    row = next(item for item in requirements if item["id"] == REQUIREMENT_ID)
    assert row["scope"] == ["market_ontology.json", "coverage_manifest.schema.json"]
    assert row["target"] == "所有发现对象都有唯一类型或明确未知状态。"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_ontology_is_valid_and_has_no_binary_float() -> None:
    assert validate_ontology(ONTOLOGY) == []
    assert ONTOLOGY["classification_contract"]["drop_unclassified_input_allowed"] is False
    assert ONTOLOGY["classification_contract"]["unknown_advice_eligible"] is False


@pytest.mark.parametrize("index,kind", list(enumerate(KNOWN_KINDS)))
def test_known_kind_order_and_identity_are_exact(index: int, kind: str) -> None:
    row = ONTOLOGY["known_object_kinds"][index]
    assert row["id"] == kind
    assert row["name_zh"]
    assert row["description"]
    assert len(row["allowed_parent_kinds"]) == len(set(row["allowed_parent_kinds"]))


@pytest.mark.parametrize(
    "kind,required",
    [
        ("SPORT", {}),
        ("COMPETITION", {"SPORT": 1}),
        ("EVENT", {"SPORT": 1}),
        ("PERIOD", {"EVENT": 1}),
        ("MARKET", {"EVENT": 1, "PERIOD": 1}),
        ("SELECTION", {"MARKET": 1}),
        ("LINE", {"MARKET": 1}),
        ("SETTLEMENT_RULE", {"MARKET": 1}),
    ],
)
def test_parent_contract_is_explicit(kind: str, required: dict) -> None:
    row = next(item for item in ONTOLOGY["known_object_kinds"] if item["id"] == kind)
    assert row["required_parent_counts"] == required
    assert set(required).issubset(row["allowed_parent_kinds"])


def test_unknown_contract_is_explicit_and_fail_closed() -> None:
    unknown = ONTOLOGY["unknown_contract"]
    assert set(unknown["required_reason_codes"]) == UNKNOWN_REASON_CODES
    assert unknown["routing_action"] == "QUARANTINE_AND_SURFACE_COVERAGE_GAP"
    assert unknown["advice_eligible"] is False


def test_coverage_schema_is_draft_2020_12_meta_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert SCHEMA["additionalProperties"] is False


def test_frozen_manifest_represents_every_input_once() -> None:
    manifest = build_coverage_manifest(RAW, ONTOLOGY)
    assert validate_coverage_manifest(SCHEMA, ONTOLOGY, manifest) == []
    assert manifest["summary"] == FIXTURE["expected_summary"]
    assert manifest["input_set"]["observed_object_count"] == len(RAW) == len(manifest["records"])
    assert len({row["record_id"] for row in manifest["records"]}) == len(RAW)
    assert len({(row["source_id"], row["source_object_ref"]) for row in manifest["records"]}) == len(RAW)


@pytest.mark.parametrize("raw", RAW[:8], ids=lambda row: row["candidate_kinds"][0])
def test_each_declared_known_object_gets_one_unique_kind(raw: dict) -> None:
    record = classify_discovery_object(raw, ONTOLOGY)
    assert record["classification_status"] == "KNOWN"
    assert record["object_kind"] == raw["candidate_kinds"][0]
    assert record["object_id"] == raw["proposed_object_id"]
    assert record["advice_eligible"] is False


def test_unrecognized_object_gets_explicit_unknown() -> None:
    record = classify_discovery_object(RAW[-1], ONTOLOGY)
    assert record["classification_status"] == "UNKNOWN"
    assert record["object_kind"] == "UNKNOWN"
    assert record["unknown_reason_code"] == "UNRECOGNIZED_TYPE"
    assert record["parent_refs"] == []
    assert record["advice_eligible"] is False


@pytest.mark.parametrize(
    "candidate_kinds,expected_reason",
    [
        ([], "UNRECOGNIZED_TYPE"),
        (["SPORT", "EVENT"], "AMBIGUOUS_TYPE"),
        (["SPORT", "SPORT"], "AMBIGUOUS_TYPE"),
        (["SOURCE_PRIVATE_KIND"], "UNRECOGNIZED_TYPE"),
    ],
)
def test_ambiguous_or_unrecognized_type_becomes_unknown(candidate_kinds: list, expected_reason: str) -> None:
    raw = copy.deepcopy(RAW[0])
    raw["candidate_kinds"] = candidate_kinds
    record = classify_discovery_object(raw, ONTOLOGY)
    assert record["object_kind"] == "UNKNOWN"
    assert record["unknown_reason_code"] == expected_reason


@pytest.mark.parametrize("proposed", [None, "EVENT:wrong-prefix", "SPORT:UPPER", "SPORT:"])
def test_malformed_proposed_object_id_becomes_unknown(proposed) -> None:
    raw = copy.deepcopy(RAW[0])
    raw["proposed_object_id"] = proposed
    record = classify_discovery_object(raw, ONTOLOGY)
    assert record["unknown_reason_code"] == "MALFORMED_IDENTIFIER"
    assert record["advice_eligible"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "lowercase"),
        ("source_object_ref", "bad\nref"),
        ("source_payload_sha256", "0" * 63),
        ("observed_at", ""),
        ("raw_type_label", ""),
        ("source_object_ref", ""),
    ],
)
def test_unidentifiable_raw_input_blocks_entire_manifest(field: str, value: str) -> None:
    raw = copy.deepcopy(RAW)
    raw[0][field] = value
    result = safe_build_coverage_manifest(raw, ONTOLOGY)
    assert result["status"] == "BLOCKED_INVALID_INPUT"
    assert result["manifest"] is None


@pytest.mark.parametrize(
    "index,parent_refs,expected_reason",
    [
        (1, [], "MISSING_REQUIRED_RELATION"),
        (2, ["competition/1"], "MISSING_REQUIRED_RELATION"),
        (2, ["sport/1", "period/1"], "INVALID_PARENT_RELATION"),
        (4, ["event/1"], "MISSING_REQUIRED_RELATION"),
        (5, ["event/1"], "INVALID_PARENT_RELATION"),
        (5, ["market/1", "market/1"], "MISSING_REQUIRED_RELATION"),
    ],
)
def test_bad_parent_relation_degrades_to_explicit_unknown(index: int, parent_refs: list, expected_reason: str) -> None:
    raw = copy.deepcopy(RAW)
    raw[index]["parent_source_refs"] = parent_refs
    manifest = build_coverage_manifest(raw, ONTOLOGY)
    record = next(row for row in manifest["records"] if row["source_object_ref"] == raw[index]["source_object_ref"])
    assert record["classification_status"] == "UNKNOWN"
    assert record["unknown_reason_code"] == expected_reason
    assert record["advice_eligible"] is False


def test_invalid_upstream_relation_cascades_without_silent_children() -> None:
    raw = copy.deepcopy(RAW)
    raw[4]["parent_source_refs"] = ["event/1", "period/missing"]
    manifest = build_coverage_manifest(raw, ONTOLOGY)
    by_ref = {row["source_object_ref"]: row for row in manifest["records"]}
    assert by_ref["market/1"]["object_kind"] == "UNKNOWN"
    for source_ref in ["selection/1", "line/1", "settlement/1"]:
        assert by_ref[source_ref]["object_kind"] == "UNKNOWN"
        assert by_ref[source_ref]["unknown_reason_code"] == "MISSING_REQUIRED_RELATION"
    assert manifest["summary"]["total_records"] == len(RAW)


def test_duplicate_source_reference_blocks_manifest() -> None:
    raw = copy.deepcopy(RAW)
    raw.append(copy.deepcopy(raw[0]))
    result = safe_build_coverage_manifest(raw, ONTOLOGY)
    assert result["status"] == "BLOCKED_INVALID_INPUT"
    assert "duplicate source object reference" in result["error"]["message"]


def test_duplicate_known_object_id_blocks_manifest() -> None:
    raw = copy.deepcopy(RAW)
    raw[1]["proposed_object_id"] = "COMPETITION:synthetic-league"
    duplicate = copy.deepcopy(raw[1])
    duplicate["source_object_ref"] = "competition/2"
    duplicate["source_payload_sha256"] = "0" * 64
    raw.append(duplicate)
    result = safe_build_coverage_manifest(raw, ONTOLOGY)
    assert result["status"] == "BLOCKED_INVALID_INPUT"
    assert "duplicate proposed object_id" in result["error"]["message"]


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_object_id",
        "duplicate_record_id",
        "duplicate_source_ref",
        "summary_tamper",
        "input_count_tamper",
        "input_digest_tamper",
        "claim_overreach",
        "status_tamper",
        "unknown_parent",
        "unknown_advice",
        "known_unknown_reason",
        "parent_cycle",
        "selection_removed",
        "settlement_removed",
    ],
)
def test_manifest_mutations_are_rejected(mutation: str) -> None:
    manifest = build_coverage_manifest(RAW, ONTOLOGY)
    candidate = copy.deepcopy(manifest)
    records = candidate["records"]
    if mutation == "duplicate_object_id":
        records[1]["object_id"] = records[0]["object_id"]
    elif mutation == "duplicate_record_id":
        records[1]["record_id"] = records[0]["record_id"]
    elif mutation == "duplicate_source_ref":
        records[1]["source_id"] = records[0]["source_id"]
        records[1]["source_object_ref"] = records[0]["source_object_ref"]
    elif mutation == "summary_tamper":
        candidate["summary"]["known_count"] += 1
    elif mutation == "input_count_tamper":
        candidate["input_set"]["observed_object_count"] += 1
    elif mutation == "input_digest_tamper":
        candidate["input_set"]["source_object_refs_sha256"] = "0" * 64
    elif mutation == "claim_overreach":
        candidate["claim_boundary"]["recommendation_or_order_enabled"] = True
    elif mutation == "status_tamper":
        candidate["manifest_status"] = "BLOCKED_INVALID_INPUT"
    elif mutation == "unknown_parent":
        unknown = next(row for row in records if row["object_kind"] == "UNKNOWN")
        unknown["parent_refs"] = [next(row["object_id"] for row in records if row["object_kind"] == "SPORT")]
    elif mutation == "unknown_advice":
        next(row for row in records if row["object_kind"] == "UNKNOWN")["advice_eligible"] = True
    elif mutation == "known_unknown_reason":
        next(row for row in records if row["object_kind"] == "SPORT")["unknown_reason_code"] = "UNRECOGNIZED_TYPE"
    elif mutation == "parent_cycle":
        sport = next(row for row in records if row["object_kind"] == "SPORT")
        sport["parent_refs"] = [sport["object_id"]]
    elif mutation == "selection_removed":
        candidate["records"] = [row for row in records if row["object_kind"] != "SELECTION"]
    elif mutation == "settlement_removed":
        candidate["records"] = [row for row in records if row["object_kind"] != "SETTLEMENT_RULE"]
    assert validate_coverage_manifest(SCHEMA, ONTOLOGY, candidate), mutation


def test_replay_is_deterministic_and_input_order_independent() -> None:
    first = build_coverage_manifest(RAW, ONTOLOGY)
    second = build_coverage_manifest(copy.deepcopy(RAW), ONTOLOGY)
    reverse = build_coverage_manifest(list(reversed(copy.deepcopy(RAW))), ONTOLOGY)
    assert first == second == reverse


@pytest.mark.parametrize("delta", FIXTURE["allowed_numeric_boundary_deltas"])
def test_numeric_probe_and_adverse_tick_do_not_change_categorical_action(delta: str) -> None:
    baseline = build_coverage_manifest(RAW, ONTOLOGY)
    raw = copy.deepcopy(RAW)
    for row in raw:
        row["numeric_probe"] = delta
        row["adverse_odds_tick"] = True
    replay = build_coverage_manifest(raw, ONTOLOGY)
    assert [row["classification_status"] for row in replay["records"]] == [row["classification_status"] for row in baseline["records"]]
    assert [row["object_kind"] for row in replay["records"]] == [row["object_kind"] for row in baseline["records"]]
    assert FIXTURE["adverse_odds_tick_action"] == "NOT_APPLICABLE_NO_ODDS_OR_ACTION_DECISION_IN_S05_P01"


@pytest.mark.parametrize("field", sorted(EXTERNAL_EFFECT_BOUNDARY))
def test_external_effect_boundary_is_exact_and_non_operational(field: str) -> None:
    if field == "incremental_cash_spent_aud":
        assert EXTERNAL_EFFECT_BOUNDARY[field] == "0.00"
    else:
        assert EXTERNAL_EFFECT_BOUNDARY[field] is False


@pytest.mark.parametrize("verifier", [verify_stage2_delivery, verify_stage4_delivery])
def test_stage_prerequisite_delivery_receipts_pass(verifier) -> None:
    result = verifier(ROOT)
    assert result["status"] == "PASS", result


def test_stage4_delivery_receipt_mutation_fails_closed(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    receipt = strict_json_load(root / S04_RECEIPT_PATH)
    receipt["pull_request"]["merge_commit"] = "0" * 40
    _write_json(root / S04_RECEIPT_PATH, receipt)
    _assert_failed(verify_stage4_delivery(root, verify_git_history=False))


def test_evidence_build_is_deterministic_without_external_reports() -> None:
    first, first_rollback = build_evidence(ROOT, require_external_reports=False)
    second, second_rollback = build_evidence(ROOT, require_external_reports=False)
    assert first == second
    assert first_rollback == second_rollback
    assert first["status"] == "PASS", first["validation"]["summary"]
    assert first["frozen_manifest_proof"]["all_observed_inputs_represented"] is True
    assert first["scope_boundary"]["fixture_is_synthetic_and_not_market_evidence"] is True
    assert first["next"] == "S05/P02_READY_NOT_STARTED"


def test_rollback_drill_restores_every_phase_artifact() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["artifacts"]) == len(ROLLBACK_ARTIFACTS)
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["external_state_changed"] is False
    assert result["provider_or_market_accessed"] is False


def test_external_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in [JUNIT_PATH, FULL_JUNIT_PATH]:
        path = root / relative
        if path.exists():
            path.unlink()
    result = evaluate_contract(root, require_external_reports=True)
    _assert_failed(result)
    assert "S05P01-TARGETED-PYTEST" in result["summary"]["failed_check_ids"]
    assert "S05P01-FULL-REGRESSION" in result["summary"]["failed_check_ids"]


def test_write_evidence_rejects_path_outside_project(tmp_path: Path) -> None:
    with pytest.raises(MarketOntologyError, match="inside the ABD project root"):
        write_phase_evidence(ROOT, tmp_path)


def test_oracle_cli_is_wired_to_exact_contract(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    result = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-m", "abd_acceptance", "--contract", CONTRACT_ID, "--evidence", "machine/evidence"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert "contract is not implemented" not in result.stderr


def test_stage4_delivery_cli_is_wired() -> None:
    main = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"STAGE-REVIEW-S04": cli_verify_stage4_delivery' in main
    assert '"AC-S05-P01": write_market_ontology_phase_evidence' in main


def test_p02_remains_planned_and_unstarted() -> None:
    result = evaluate_contract(ROOT)
    check = next(row for row in result["checks"] if row["id"] == "S05P01-P02-NOT-STARTED")
    assert check["passed"] is True, check
    assert not check["detail"]["present"]
    assert check["detail"]["index"][0]["status"] == "PLANNED"


def test_p01_artifacts_contain_no_secret_or_machine_specific_path() -> None:
    paths = [ONTOLOGY_PATH, SCHEMA_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/market_ontology.py"), Path("abd_acceptance/stage4_delivery.py"), S04_RECEIPT_PATH]
    rendered = "\n".join((ROOT / path).read_text(encoding="utf-8", errors="replace") for path in paths)
    assert ("/" + "Users/") not in rendered
    assert ("file" + "://") not in rendered
    assert ("-----BEGIN " + "PRIVATE KEY-----") not in rendered
    assert ("ghp" + "_") not in rendered


def test_signed_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    result = validate_signed_receipt_preflight(ROOT)
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        assert result["status"] == "PASS", result
        verified = verify_existing_phase_evidence(ROOT)
        assert verified["status"] == "PASS", verified
        assert verified["decision"] == "S05_P01_EVIDENCE_VERIFIED"
    else:
        assert result["status"] == "FAIL"
        assert result["decision"] == "S05_P01_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED"


def test_p01_claim_boundary_does_not_overstate_observation_or_runtime() -> None:
    assert set(ONTOLOGY["claim_boundary"].values()) == {False}
    manifest = build_coverage_manifest(RAW, ONTOLOGY)
    assert manifest["declared_discovery_scope"] == "ALL_OBSERVABLE_MARKETS"
    assert manifest["claim_boundary"]["all_observable_markets_verified"] is False
    assert manifest["claim_boundary"]["cross_source_identity_resolved"] is False
    assert manifest["claim_boundary"]["source_capabilities_verified"] is False
    assert manifest["claim_boundary"]["market_data_freshness_verified"] is False
    assert manifest["claim_boundary"]["recommendation_or_order_enabled"] is False


@pytest.mark.parametrize("invalid", [[], "not-a-sequence", [None], [True]])
def test_invalid_manifest_input_shape_blocks(invalid) -> None:
    result = safe_build_coverage_manifest(invalid, ONTOLOGY)
    assert result["status"] == "BLOCKED_INVALID_INPUT"
    assert result["manifest"] is None


@pytest.mark.parametrize("reason", sorted(UNKNOWN_REASON_CODES))
def test_schema_admits_every_declared_unknown_reason(reason: str) -> None:
    raw = copy.deepcopy(RAW[-1])
    record = classify_discovery_object(raw, ONTOLOGY)
    record["unknown_reason_code"] = reason
    manifest = build_coverage_manifest(RAW, ONTOLOGY)
    index = next(i for i, row in enumerate(manifest["records"]) if row["object_kind"] == "UNKNOWN")
    manifest["records"][index] = record
    assert validate_coverage_manifest(SCHEMA, ONTOLOGY, manifest) == []


def test_all_kinds_include_exactly_one_unknown_terminal() -> None:
    assert ALL_KINDS == (*KNOWN_KINDS, "UNKNOWN")
    assert len(ALL_KINDS) == 9
