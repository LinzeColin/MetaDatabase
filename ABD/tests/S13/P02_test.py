from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from abd_acceptance.platform_quote_check import (
    FEATURE_FLAG_ID,
    PlatformQuoteCheckAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
    verify_existing_phase_evidence,
    write_phase_evidence,
)
from quote_check import (
    CLAIM_BOUNDARY,
    GREEN_STATUS,
    RED_STATUS,
    QuoteCheckError,
    apply_adverse_perturbation,
    build_copy_instruction,
    evaluate_quote,
    replay_match_fixtures,
    validate_match_fixtures,
    validate_ticket,
)


ROOT = Path(__file__).resolve().parents[2]
MATCH = json.loads((ROOT / "match_fixtures.json").read_text(encoding="utf-8"))
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S13_P02.json").read_text(encoding="utf-8"))


def _clone_project(tmp_path: Path) -> Path:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    return clone


def _case(case_id: str) -> dict[str, object]:
    return next(item for item in MATCH["cases"] if item["case_id"] == case_id)


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S13-P02"
    assert result["next"] == FIXTURE["expected_next"]
    assert result["summary"]["checks"] >= FIXTURE["expected_preflight_minimum"]
    assert result["external_effect_boundary"] == FIXTURE["claim_boundary"]


def test_fixture_is_closed_and_matches_the_frozen_acceptance_contract() -> None:
    normalized = validate_match_fixtures(MATCH)
    assert normalized["fixture_id"] == FIXTURE["expected_match_fixture_id"]
    assert len(normalized["cases"]) == FIXTURE["expected_case_count"]
    assert len(normalized["adverse_scenarios"]) == FIXTURE["expected_adverse_scenario_count"]
    assert normalized["ticket"]["parameters_sha256"] == FIXTURE["expected_parameters_sha256"]
    assert normalized["ticket"]["provider_contracts_sha256"] == FIXTURE["expected_provider_contracts_sha256"]
    assert normalized["claim_boundary"] == CLAIM_BOUNDARY == FIXTURE["claim_boundary"]


def test_replay_has_exact_green_red_partition_and_hash() -> None:
    replay = replay_match_fixtures(MATCH)
    green = [item["case_id"] for item in replay["case_results"] if item["status"] == GREEN_STATUS]
    red = [item["case_id"] for item in replay["case_results"] if item["status"] == RED_STATUS]
    assert green == FIXTURE["expected_green_case_ids"]
    assert red == FIXTURE["expected_red_case_ids"]
    assert replay["replay_sha256"] == FIXTURE["expected_replay_sha256"]


@pytest.mark.parametrize("case_id", [item["case_id"] for item in MATCH["cases"]])
def test_each_frozen_visible_page_case_matches_the_expected_fail_closed_result(case_id: str) -> None:
    case = _case(case_id)
    result = evaluate_quote(MATCH["ticket"], case["snapshot"])
    assert result["status"] == case["expected_status"]
    assert result["action"] == case["expected_action"]
    assert result["failed_gate_ids"] == case["expected_failed_gate_ids"]
    assert result["automatic_platform_open_performed"] is False
    assert result["order_submission_enabled"] is False
    assert result["synthetic_test_only"] is True


@pytest.mark.parametrize("scenario", MATCH["adverse_scenarios"], ids=lambda item: item["scenario_id"])
def test_one_provider_tick_and_two_second_adverse_variants_revoke_immediately(scenario: dict[str, object]) -> None:
    base = _case(str(scenario["base_case_id"]))
    altered = apply_adverse_perturbation(
        base["snapshot"],
        odds_down_ticks=int(scenario["odds_down_ticks"]),
        seconds_later=int(scenario["seconds_later"]),
    )
    result = evaluate_quote(MATCH["ticket"], altered)
    assert result["status"] == scenario["expected_status"] == RED_STATUS
    assert result["failed_gate_ids"] == scenario["expected_failed_gate_ids"]


def test_copy_instruction_never_creates_a_deep_link_or_an_automatic_open() -> None:
    instruction = build_copy_instruction(MATCH["ticket"])
    assert instruction["deep_link_status"] == "UNAVAILABLE_WITHOUT_VERIFIED_PROVIDER_CONTRACT"
    assert instruction["automatic_platform_open_performed"] is False
    assert instruction["external_network_accessed"] is False
    assert instruction["order_submission_enabled"] is False
    assert instruction["synthetic_test_only"] is True


def test_malformed_float_or_unsafe_ticket_fails_closed() -> None:
    ticket = deepcopy(MATCH["ticket"])
    ticket["minimum_odds"] = 2.2
    with pytest.raises(QuoteCheckError):
        validate_ticket(ticket)
    result = evaluate_quote(ticket, _case("M01-GREEN-EXACT-MINIMUM")["snapshot"])
    assert result["status"] == RED_STATUS
    assert result["action"] == "DO_NOT_ORDER"
    assert result["failed_gate_ids"] == ["MALFORMED_OR_UNTRUSTED_VISIBLE_INPUT"]


def test_browser_component_is_minimum_permission_and_has_no_network_or_click_capability() -> None:
    manifest = json.loads((ROOT / "browser_companion/manifest.json").read_text(encoding="utf-8"))
    background = (ROOT / "browser_companion/background.js").read_text(encoding="utf-8")
    content = (ROOT / "browser_companion/content.js").read_text(encoding="utf-8")
    assert manifest["permissions"] == ["activeTab", "scripting"]
    assert "host_permissions" not in manifest
    assert "externally_connectable" not in manifest
    for token in ("fetch(", "XMLHttpRequest", "WebSocket", "window.open", ".submit(", ".click(", "localStorage", "indexedDB", "document.cookie", "new Date"):
        assert token not in background
        assert token not in content
    assert "data-abd-visible-field" in content
    assert "OWNER_FINAL_ORDER_MANUAL_ONLY" in background
    assert "RED_REVOKE_DO_NOT_ORDER" in background


def test_quote_checker_has_no_network_soak_or_order_import_capability() -> None:
    source = (ROOT / "quote_check.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "smtplib", "asyncio", "time", "random", "os"})
    for token in ("sleep(", "submit_order", "retry_order", "http://", "https://", "webhook", "smtplib"):
        assert token not in source


def test_candidate_fails_closed_when_browser_manifest_requests_a_host_permission(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    manifest_path = clone / "browser_companion/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["host_permissions"] = ["<all_urls>"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S13P02-BROWSER-COMPANION-LEAST-PRIVILEGE" in result["summary"]["failed_check_ids"]


def test_candidate_fails_closed_when_minimum_odds_fixture_is_tampered(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    fixture_path = clone / "match_fixtures.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["ticket"]["minimum_odds"] = "2.199999"
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S13P02-FROZEN-VISIBLE-QUOTE-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_rollback_drill_is_local_and_preserves_no_external_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == FEATURE_FLAG_ID == FIXTURE["expected_feature_flag_id"]
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["order_submission_enabled"] is False
    assert rollback["real_time_soak_waited"] is False


def test_signing_replaces_only_the_p02_jsonl_row_and_replays(tmp_path: Path) -> None:
    clone = _clone_project(tmp_path)
    index_path = clone / "machine/evidence/evidence_index.jsonl"
    rows = index_path.read_text(encoding="utf-8").splitlines()
    planned_index = next(index for index, line in enumerate(rows) if json.loads(line).get("id") == "INDEX-AC-S13-P02")
    cases = "".join(
        '<testcase classname="tests.S13.P02_test" name="signer_fixture_%d" time="0.000" />' % index
        for index in range(16)
    )
    report_path = clone / "machine/evidence/S13/P02/pytest.xml"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('<?xml version="1.0" encoding="utf-8"?><testsuite tests="16" failures="0" errors="0" skipped="0">%s</testsuite>' % cases, encoding="utf-8")
    scan_path = clone / "machine/evidence/S13/P02/paid_dependency_scan.txt"
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
    assert '"AC-S13-P02": write_platform_quote_check_phase_evidence' in source
    assert '"AC-S13-P02": verify_platform_quote_check_phase_evidence' in source
    with pytest.raises((PlatformQuoteCheckAcceptanceError, FileNotFoundError)):
        verify_existing_phase_evidence(ROOT / "missing")
