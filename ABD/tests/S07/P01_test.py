from __future__ import annotations

import ast
from copy import deepcopy
import json
import os
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from abd_acceptance.canonical_facts import sha256_file, strict_json_load
from abd_acceptance.identity_resolution import (
    CONTRACT_ID,
    EVIDENCE_PATH,
    EXTERNAL_EFFECT_BOUNDARY,
    FIXTURE_PATH,
    FULL_JUNIT_PATH,
    IDENTITY_FIXTURES_PATH,
    JUNIT_FIXED_CLOCK,
    JUNIT_PATH,
    ORACLE_PATH,
    PINNED_BASELINE_HASHES,
    PINNED_PHASE_HASHES,
    REGISTRY_PATH,
    RESOLVER_PATH,
    ROLLBACK_ARTIFACTS,
    ROLLBACK_EVIDENCE_PATH,
    STRUCTURAL_SELF_NORMALIZED_SHA256,
    TEST_PATH,
    _check_baseline,
    _check_pins,
    _check_reports,
    _junit_is_normalized,
    _junit_summary,
    _structural_self_hash,
    build_evidence as _build_evidence,
    perform_rollback_drill,
    validate_candidate_preflight as _validate_candidate_preflight,
    verify_existing_phase_evidence as _verify_existing_phase_evidence,
)
from identity_resolver import (
    CONFIDENCE_THRESHOLD,
    IDENTITY_ELIGIBLE,
    NO_ADVICE,
    IdentityResolutionError,
    canonicalize_line,
    canonicalize_start_time,
    confidence_action,
    deterministic_resolution_hash,
    prepare_registry,
    resolve_identity,
    resolve_prepared_identity,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
IDENTITY_FIXTURES = strict_json_load(ROOT / IDENTITY_FIXTURES_PATH)
REGISTRY = strict_json_load(ROOT / REGISTRY_PATH)
MACHINE_FIXTURE = strict_json_load(ROOT / FIXTURE_PATH)


def validate_candidate_preflight(root: Path) -> dict:
    return _validate_candidate_preflight(
        root,
        verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def build_evidence(root: Path, require_test_reports: bool = False):
    return _build_evidence(
        root,
        require_test_reports=require_test_reports,
        _verify_git_history=Path(root).resolve() == ROOT.resolve(),
    )


def verify_existing_phase_evidence(root: Path) -> dict:
    return _verify_existing_phase_evidence(root, verify_git_history=Path(root).resolve() == ROOT.resolve())


def _clone_project(tmp_path: Path) -> Path:
    destination = tmp_path / "ABD"
    def link_or_copy(source: str, target: str) -> str:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        return target

    shutil.copytree(
        ROOT,
        destination,
        copy_function=link_or_copy,
        ignore=shutil.ignore_patterns(".pytest_cache", ".venv", "__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT.parent / ".github", destination.parent / ".github", copy_function=link_or_copy)
    return destination


def _write_json(path: Path, value) -> None:
    path.unlink(missing_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _case(case_id: str) -> dict:
    return next(case for case in IDENTITY_FIXTURES["cases"] if case["case_id"] == case_id)


def _assert_no_advice(result: dict) -> None:
    assert result["status"] == NO_ADVICE
    assert result["identity_eligible"] is False
    assert result["identity_key"] is None
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["external_network_used"] is False


def test_candidate_preflight_and_contract_pass_without_generated_reports() -> None:
    preflight = validate_candidate_preflight(ROOT)
    assert preflight["status"] == "PASS", preflight
    assert preflight["next"] == MACHINE_FIXTURE["expected_next"]
    assert preflight["summary"]["checks"] >= MACHINE_FIXTURE["expected_oracle_check_minimum"]
    assert preflight["summary"]["failed"] == 0


def test_taskpack_identity_scope_and_trace_are_exact() -> None:
    requirements = strict_json_load(ROOT / "machine/facts/requirements.json")
    requirement = next(item for item in requirements if item["id"] == "REQ-S07-P01")
    contracts = strict_json_load(ROOT / "machine/facts/acceptance_contracts.json")
    contract = next(item for item in contracts if item["id"] == CONTRACT_ID)
    graph = strict_json_load(ROOT / "machine/facts/task_graph.json")["tasks"]
    trace = strict_json_load(ROOT / "machine/facts/traceability_matrix.json")
    trace_row = next(item for item in trace if item["requirement_id"] == "REQ-S07-P01")
    tasks = [item for item in graph if item.get("stage_id") == "S07" and item.get("phase_id") == "P01"]
    assert requirement["scope"] == ["identity_resolver.py", "identity_fixtures.json", "identity_registry.json"]
    assert requirement["target"] == "身份置信度<99.5%时不建议。"
    assert contract["pass_gate"] == requirement["target"]
    assert [row["id"] for row in contract["tests"]] == ["TEST-S07-P01", "TEST-S07-P01-BOUNDARY", "TEST-S07-P01-REPLAY"]
    assert [item["id"] for item in tasks] == ["T-S07-P01-01", "T-S07-P01-02", "T-S07-P01-03"]
    assert trace_row["evidence_id"] == "EVD-S07-P01"


@pytest.mark.parametrize("relative", sorted(PINNED_PHASE_HASHES))
def test_phase_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_PHASE_HASHES[relative]


@pytest.mark.parametrize("relative", sorted(PINNED_BASELINE_HASHES))
def test_baseline_artifact_hash_matches_pin(relative: str) -> None:
    assert sha256_file(ROOT / relative) == PINNED_BASELINE_HASHES[relative]


def test_oracle_source_has_normalized_structural_integrity() -> None:
    assert _structural_self_hash(ROOT) == STRUCTURAL_SELF_NORMALIZED_SHA256


def test_registry_is_frozen_synthetic_and_valid() -> None:
    assert validate_registry(REGISTRY) == []
    assert REGISTRY["claim_boundary"]["frozen_synthetic_registry_only"] is True
    assert REGISTRY["claim_boundary"]["network_or_provider_accessed"] is False
    assert all(source["mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT" for source in REGISTRY["sources"])


def test_positive_reference_and_cross_source_boundary_resolutions_are_exact() -> None:
    authoritative = _case("POSITIVE_AUTHORITATIVE_REFERENCE")
    cross_source = _case("POSITIVE_CROSS_SOURCE_MINIMUM_THRESHOLD")
    first = resolve_identity(REGISTRY, authoritative["observation"])
    second = resolve_identity(REGISTRY, cross_source["observation"])
    assert first["status"] == authoritative["expected"]["status"]
    assert first["identity_confidence"] == "1.0000"
    assert first["canonical"]["selection_id"] == "HOME"
    assert first["identity_eligible"] is True
    assert second["status"] == cross_source["expected"]["status"]
    assert second["identity_confidence"] == "0.9950"
    assert second["canonical"]["selection_id"] == "OVER"
    assert second["identity_eligible"] is True
    assert first["identity_key"] != second["identity_key"]
    assert first["recommendation_generated"] is False
    assert second["order_submission_enabled"] is False


@pytest.mark.parametrize(
    ("value", "eligible", "action"),
    [
        (Decimal("0.9949"), False, NO_ADVICE),
        (Decimal("0.9950"), True, IDENTITY_ELIGIBLE),
        (Decimal("0.9951"), True, IDENTITY_ELIGIBLE),
    ],
)
def test_confidence_threshold_boundary_is_exact(value: Decimal, eligible: bool, action: str) -> None:
    result = confidence_action(value)
    assert value in {CONFIDENCE_THRESHOLD - Decimal("0.0001"), CONFIDENCE_THRESHOLD, CONFIDENCE_THRESHOLD + Decimal("0.0001")}
    assert result["identity_eligible"] is eligible
    assert result["identity_action"] == action


@pytest.mark.parametrize("value", [0.995, True, Decimal("0.99495"), Decimal("1.0001")])
def test_confidence_rejects_binary_float_boolean_precision_loss_and_out_of_range(value) -> None:
    with pytest.raises(IdentityResolutionError):
        confidence_action(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"representation": "SCALAR_DECIMAL", "value": "2.500"}, {"representation": "SCALAR_DECIMAL", "value": "2.5"}),
        ({"representation": "RANGE_DECIMAL", "lower": "-1.00", "upper": "0.50"}, {"representation": "RANGE_DECIMAL", "lower": "-1", "upper": "0.5"}),
        ({"representation": "NO_LINE_APPLICABLE"}, {"representation": "NO_LINE_APPLICABLE"}),
        ({"representation": "CATEGORICAL", "value": "DRAW_NO_BET"}, {"representation": "CATEGORICAL", "value": "DRAW_NO_BET"}),
    ],
)
def test_line_canonicalization_is_exact_and_float_free(value: dict, expected: dict) -> None:
    assert canonicalize_line(value) == expected
    with pytest.raises(IdentityResolutionError):
        canonicalize_line({"representation": "SCALAR_DECIMAL", "value": 2.5})


@pytest.mark.parametrize(
    "mutator",
    [
        lambda observation: observation.__setitem__("source_version_sha256", "0" * 64),
        lambda observation: observation.__setitem__("source_event_ref", "UNBOUND-REF"),
        lambda observation: observation.__setitem__("selection_alias", "Unknown selection"),
        lambda observation: observation.__setitem__("odds", "1.01"),
    ],
)
def test_untrusted_or_unsupported_observation_input_is_never_identity_eligible(mutator) -> None:
    observation = deepcopy(_case("POSITIVE_AUTHORITATIVE_REFERENCE")["observation"])
    mutator(observation)
    result = resolve_identity(REGISTRY, observation)
    _assert_no_advice(result)


def test_one_second_drift_and_unknown_alias_fail_closed() -> None:
    drift = resolve_identity(REGISTRY, _case("NEGATIVE_START_TIME_ONE_SECOND_DRIFT")["observation"])
    unknown = resolve_identity(REGISTRY, _case("NEGATIVE_UNKNOWN_ALIAS")["observation"])
    _assert_no_advice(drift)
    _assert_no_advice(unknown)
    assert drift["identity_confidence"] == "0.9949"
    assert "IDENTITY_CONFIDENCE_BELOW_THRESHOLD" in drift["reason_codes"]
    assert "EVENT_NOT_UNIQUELY_IDENTIFIED" in unknown["reason_codes"]


def test_timezone_offset_conflict_and_registry_ambiguity_fail_closed() -> None:
    with pytest.raises(IdentityResolutionError):
        canonicalize_start_time("2026-08-15T19:30:00+00:00", "Australia/Sydney")
    ambiguous = deepcopy(REGISTRY)
    ambiguous["events"].append(deepcopy(ambiguous["events"][0]))
    assert validate_registry(ambiguous)
    result = resolve_identity(ambiguous, _case("POSITIVE_AUTHORITATIVE_REFERENCE")["observation"])
    _assert_no_advice(result)
    assert result["reason_codes"] == ["REGISTRY_INVALID"]


def test_one_hundred_replays_are_hash_identical_without_waiting() -> None:
    observation = _case("POSITIVE_AUTHORITATIVE_REFERENCE")["observation"]
    expected = deterministic_resolution_hash(REGISTRY, observation)
    results = {
        deterministic_resolution_hash(REGISTRY, {key: observation[key] for key in reversed(list(observation))})
        for _ in range(MACHINE_FIXTURE["replay_count"])
    }
    assert results == {expected}


def test_ten_thousand_adverse_perturbations_never_enable_advice_or_orders() -> None:
    base = _case("NEGATIVE_UNKNOWN_ALIAS")["observation"]
    prepared = prepare_registry(REGISTRY)
    for index in range(MACHINE_FIXTURE["adverse_replay_count"]):
        observation = deepcopy(base)
        mode = index % 5
        if mode == 0:
            observation["home_alias"] = "Unknown-%d" % index
        elif mode == 1:
            observation["source_version_sha256"] = "f" * 64
        elif mode == 2:
            observation["selection_alias"] = "Impossible"
        elif mode == 3:
            observation["line"] = {"representation": "SCALAR_DECIMAL", "value": "1.5"}
        else:
            observation["start_time"] = "2026-08-15T19:32:00+10:00"
        _assert_no_advice(resolve_prepared_identity(prepared, observation))


def test_resolver_has_no_network_process_scheduler_or_sleep_capability() -> None:
    source = (ROOT / RESOLVER_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports & {"requests", "urllib", "http", "socket", "subprocess", "asyncio", "time"}
    assert not any(token in source for token in ("sleep(", "requests.", "urllib.", "socket.", "subprocess.", "http://", "https://"))


def test_rollback_drill_is_hash_only_and_never_changes_external_state() -> None:
    result = perform_rollback_drill(ROOT)
    assert result["status"] == "PASS", result
    assert set(result["artifacts"]) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
    assert all(row["status"] == "PASS" for row in result["artifacts"].values())
    assert result["production_state_changed"] is False
    assert result["external_state_changed"] is False
    assert result["recommendation_generated"] is False
    assert result["order_submission_enabled"] is False
    assert result["real_time_soak_waited"] is False


def test_candidate_fails_closed_when_phase_artifact_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    payload = strict_json_load(root / IDENTITY_FIXTURES_PATH)
    payload["cases"][0]["expected"]["identity_confidence"] = "0.9950"
    _write_json(root / IDENTITY_FIXTURES_PATH, payload)
    checks: list[dict] = []
    _check_pins(root, checks, {})
    assert next(check for check in checks if check["id"] == "S07P01-PIN-IDENTITY_FIXTURES-JSON")["passed"] is False


def test_candidate_fails_closed_when_baseline_is_tampered(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    payload = strict_json_load(root / "machine/facts/parameters.json")
    payload["coverage_and_freshness"]["identity_confidence_min"] = "0.994"
    _write_json(root / "machine/facts/parameters.json", payload)
    checks: list[dict] = []
    _check_baseline(root, checks, {})
    assert next(check for check in checks if check["id"] == "S07P01-BASELINE-PARAMETERS-JSON")["passed"] is False


def test_generated_report_mode_fails_closed_when_reports_are_absent(tmp_path: Path) -> None:
    root = _clone_project(tmp_path)
    for relative in (JUNIT_PATH, FULL_JUNIT_PATH):
        (root / relative).unlink(missing_ok=True)
    checks: list[dict] = []
    _check_reports(root, checks, require_test_reports=True)
    assert next(check for check in checks if check["id"] == "S07P01-TARGETED-PYTEST-REPORT")["passed"] is False


def test_junit_normalization_accepts_only_fixed_metadata(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" timestamp="%s" time="0.000"><testcase name="offline" time="0.000" /></testsuite></testsuites>'
        % JUNIT_FIXED_CLOCK,
        encoding="utf-8",
    )
    assert _junit_is_normalized(report) is True
    assert _junit_summary(report)["tests"] == 1
    report.write_text(report.read_text(encoding="utf-8").replace('time="0.000"', 'time="0.001"', 1), encoding="utf-8")
    assert _junit_is_normalized(report) is False


def test_oracle_cli_is_wired_to_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S07-P01": write_identity_resolution_phase_evidence' in source
    assert "from .identity_resolution import write_phase_evidence as write_identity_resolution_phase_evidence" in source


def test_candidate_evidence_carries_only_frozen_synthetic_identity_summary() -> None:
    evidence, rollback = build_evidence(ROOT)
    assert evidence["status"] == "PASS", evidence["validation"]
    assert evidence["identity_summary"]["fixture_mode"] == "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
    assert evidence["identity_summary"]["recommendation_generated"] is False
    assert evidence["identity_summary"]["order_submission_enabled"] is False
    assert evidence["external_effect_boundary"] == EXTERNAL_EFFECT_BOUNDARY
    assert evidence["production_status"] == "NOT_DEPLOYED_OR_ACTIVATED"
    assert evidence["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"
    assert rollback["status"] == "PASS"


def test_existing_receipt_is_fail_closed_when_absent_or_verifiable() -> None:
    if (ROOT / EVIDENCE_PATH).is_file() and (ROOT / ROLLBACK_EVIDENCE_PATH).is_file():
        result = verify_existing_phase_evidence(ROOT)
        assert result["status"] == "PASS", result
    else:
        assert not (ROOT / EVIDENCE_PATH).is_file()
        assert not (ROOT / ROLLBACK_EVIDENCE_PATH).is_file()


def test_canonical_financial_and_order_boundaries_remain_unchanged() -> None:
    canonical = strict_json_load(ROOT / "machine/facts/canonical_facts.json")
    assert canonical["product"]["initial_bankroll_aud"] == "300.00"
    assert canonical["product"]["incremental_cash_budget_aud"] == "0.00"
    assert canonical["scope"]["order_submission_module_present"] is False
    assert EXTERNAL_EFFECT_BOUNDARY["incremental_cash_spent_aud"] == "0.00"
    assert EXTERNAL_EFFECT_BOUNDARY["real_time_soak_waited"] is False
