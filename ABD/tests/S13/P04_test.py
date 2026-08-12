from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.journey_paths import (
    CLAIM_BOUNDARY,
    JourneyPathsAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    replay_journeys,
    validate_candidate_preflight,
    validate_journey_catalog,
    validate_recovery_catalog,
    verify_existing_phase_evidence,
    write_phase_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S13_P04.json").read_text(encoding="utf-8"))
JOURNEYS = json.loads((ROOT / "journey_tests.json").read_text(encoding="utf-8"))
RECOVERY = json.loads((ROOT / "recovery_actions.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _journey(journey_id: str) -> dict[str, object]:
    return next(item for item in JOURNEYS["journeys"] if item["journey_id"] == journey_id)


def test_candidate_preflight_passes_without_generated_p04_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S13-P04"
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= FIXTURE["expected_preflight_minimum"]
    assert result["external_effect_boundary"] == CLAIM_BOUNDARY


def test_catalog_has_exactly_the_six_frozen_complete_path_types() -> None:
    catalog = validate_journey_catalog(JOURNEYS)
    recovery = validate_recovery_catalog(RECOVERY, catalog["journeys"])
    assert [item["journey_type"] for item in catalog["journeys"]] == FIXTURE["expected_journey_types"]
    assert [item["action_id"] for item in recovery["actions"]] == FIXTURE["expected_recovery_action_ids"]
    assert catalog["claim_boundary"] == CLAIM_BOUNDARY == recovery["claim_boundary"]


@pytest.mark.parametrize("journey_id", list(FIXTURE["expected_terminal_statuses"]))
def test_each_path_has_input_states_output_evidence_user_action_and_recovery(journey_id: str) -> None:
    catalog = validate_journey_catalog(JOURNEYS)
    journey = next(item for item in catalog["journeys"] if item["journey_id"] == journey_id)
    assert len(journey["state_transitions"]) == FIXTURE["expected_transition_counts"][journey_id]
    assert journey["output"]["terminal_status"] == FIXTURE["expected_terminal_statuses"][journey_id]
    assert {"EVD-S13-P01", "EVD-S13-P02", "EVD-S13-P03"}.issubset(set(journey["evidence_refs"]))
    assert journey["user_action_zh"]
    assert journey["recovery_action_id"] in FIXTURE["expected_recovery_action_ids"]
    assert journey["output"]["automatic_order_submitted"] is False
    assert journey["output"]["actual_return_claimed"] is False
    assert journey["output"]["external_state_changed"] is False


def test_replay_is_exactly_deterministic_and_remains_local_only() -> None:
    replays = [replay_journeys(JOURNEYS, RECOVERY) for _ in range(3)]
    assert replays == [replays[0]] * 3
    replay = replays[0]
    assert replay["replay_sha256"] == FIXTURE["expected_replay_sha256"]
    assert replay["claim_boundary"] == CLAIM_BOUNDARY
    assert all(item["synthetic_test_only"] is True for item in replay["outcomes"])
    assert all(item["automatic_order_submitted"] is False for item in replay["outcomes"])
    assert all(item["actual_return_claimed"] is False for item in replay["outcomes"])
    assert all(item["external_state_changed"] is False for item in replay["outcomes"])


def test_point_0001_adverse_odds_boundary_replays_black_path_and_not_golden_path() -> None:
    black = _journey("S13-P04-BLACK")
    golden = _journey("S13-P04-GOLDEN")
    assert Decimal(str(black["input"]["visible_odds"])) == Decimal(str(black["input"]["minimum_odds"])) - Decimal("0.000100")
    assert Decimal(str(golden["input"]["visible_odds"])) == Decimal(str(golden["input"]["minimum_odds"]))
    replay = replay_journeys(JOURNEYS, RECOVERY)
    outcomes = {item["journey_id"]: item for item in replay["outcomes"]}
    assert outcomes["S13-P04-BLACK"]["terminal_status"] == "RED_REVOKE_DO_NOT_ORDER"
    assert outcomes["S13-P04-GOLDEN"]["terminal_status"] == "SYNTHETIC_SETTLEMENT_RECORDED_NOT_ACTUAL_RETURN"
    assert outcomes["S13-P04-BLACK"]["actual_return_claimed"] is False


def test_float_or_wrong_black_boundary_fails_closed() -> None:
    malformed = deepcopy(JOURNEYS)
    malformed["journeys"][2]["input"]["visible_odds"] = 2.1999
    with pytest.raises(JourneyPathsAcceptanceError):
        validate_journey_catalog(malformed)
    malformed = deepcopy(JOURNEYS)
    malformed["journeys"][2]["input"]["visible_odds"] = "2.199999"
    with pytest.raises(JourneyPathsAcceptanceError):
        validate_journey_catalog(malformed)


def test_noncontiguous_state_transition_fails_closed() -> None:
    malformed = deepcopy(JOURNEYS)
    malformed["journeys"][0]["state_transitions"][1]["from"] = "UNRELATED_STATE"
    with pytest.raises(JourneyPathsAcceptanceError):
        validate_journey_catalog(malformed)


def test_forged_recovery_action_that_claims_actual_return_fails_closed() -> None:
    catalog = validate_journey_catalog(JOURNEYS)
    forged = deepcopy(RECOVERY)
    forged["actions"][1]["actual_return_claimed"] = True
    with pytest.raises(JourneyPathsAcceptanceError):
        validate_recovery_catalog(forged, catalog["journeys"])


def test_candidate_fails_closed_when_path_output_enables_an_actual_return_claim(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    journey_path = clone / "journey_tests.json"
    journeys = json.loads(journey_path.read_text(encoding="utf-8"))
    journeys["journeys"][1]["output"]["actual_return_claimed"] = True
    journey_path.write_text(json.dumps(journeys, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S13P04-SIX-PATH-RUNNER" in result["summary"]["failed_check_ids"]


def test_oracle_and_catalogs_have_no_network_soak_or_order_capability() -> None:
    source = (ROOT / "abd_acceptance/journey_paths.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "smtplib", "asyncio", "time", "random", "os"})
    for text in (source, (ROOT / "journey_tests.json").read_text(encoding="utf-8"), (ROOT / "recovery_actions.json").read_text(encoding="utf-8")):
        for token in ("sleep(", "submit_order", "retry_order", "http://", "https://", "webhook", "smtplib"):
            assert token not in text


def test_rollback_drill_is_local_and_preserves_evidence() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "journey:s13-p04-six-complete-paths"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["actual_return_claimed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_signing_replaces_only_the_p04_jsonl_row_and_replays(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    index_path = clone / "machine/evidence/evidence_index.jsonl"
    rows = index_path.read_text(encoding="utf-8").splitlines()
    planned_index = next(index for index, line in enumerate(rows) if json.loads(line).get("id") == "INDEX-AC-S13-P04")
    cases = "".join(
        '<testcase classname="tests.S13.P04_test" name="signer_fixture_%d" time="0.000" />' % index
        for index in range(17)
    )
    report_path = clone / "machine/evidence/S13/P04/pytest.xml"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('<?xml version="1.0" encoding="utf-8"?><testsuite tests="17" failures="0" errors="0" skipped="0">%s</testsuite>' % cases, encoding="utf-8")
    scan_path = clone / "machine/evidence/S13/P04/paid_dependency_scan.txt"
    scan_path.write_text(
        "STATUS: PASS\nMAX_INCREMENTAL_CASH_AUD: 0.00\nPAID_OR_UNKNOWN_DEPENDENCIES: 0\nEXTERNAL_NETWORK_ACCESS_PERFORMED: false\nEXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false\n",
        encoding="utf-8",
    )
    before = index_path.read_text(encoding="utf-8").splitlines()
    result = write_phase_evidence(clone, clone / "machine/evidence")
    after = index_path.read_text(encoding="utf-8").splitlines()
    changed = [index for index, (left, right) in enumerate(zip(before, after)) if left != right]
    assert result["status"] == "PASS"
    assert result["next"] == FIXTURE["expected_next"]
    assert changed == [planned_index]
    assert json.loads(after[planned_index])["kind"] == "PHASE_EVIDENCE"
    assert verify_existing_phase_evidence(clone)["status"] == "PASS"


def test_acceptance_cli_is_wired_to_the_exact_contract_after_integration() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S13-P04": write_journey_paths_phase_evidence' in source
    assert '"AC-S13-P04": verify_journey_paths_phase_evidence' in source
    with pytest.raises((JourneyPathsAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
