from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import shutil

import pytest

from abd_acceptance.target_falsification_gate import (
    TargetFalsificationAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from target_falsification import (
    EMPIRICAL_EVIDENCE_STATUS,
    TargetFalsificationError,
    artifact_sha256,
    build_artifacts,
    classify_falsification,
    classify_verification,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S12_P04.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
CAPACITY = json.loads((ROOT / "capacity_report.json").read_text(encoding="utf-8"))
GRID = json.loads((ROOT / "sensitivity_grid.json").read_text(encoding="utf-8"))
OPPORTUNITY = json.loads((ROOT / "opportunity_cost.json").read_text(encoding="utf-8"))
P01_PATH = ROOT / "machine/evidence/EVD-S12-P01.json"
P02_PATH = ROOT / "machine/evidence/EVD-S12-P02.json"
P03_PATH = ROOT / "machine/evidence/EVD-S12-P03.json"
P01 = json.loads(P01_PATH.read_text(encoding="utf-8"))
P02 = json.loads(P02_PATH.read_text(encoding="utf-8"))
P03 = json.loads(P03_PATH.read_text(encoding="utf-8"))
P01_SHA256 = hashlib.sha256(P01_PATH.read_bytes()).hexdigest()
P02_SHA256 = hashlib.sha256(P02_PATH.read_bytes()).hexdigest()
P03_SHA256 = hashlib.sha256(P03_PATH.read_bytes()).hexdigest()
CAPACITY_SHA256 = hashlib.sha256((ROOT / "capacity_report.json").read_bytes()).hexdigest()
GRID_SHA256 = hashlib.sha256((ROOT / "sensitivity_grid.json").read_bytes()).hexdigest()
OPPORTUNITY_SHA256 = hashlib.sha256((ROOT / "opportunity_cost.json").read_bytes()).hexdigest()


def _artifacts(
    fixture: dict | None = None,
    parameters: dict | None = None,
    capacity: dict | None = None,
    grid: dict | None = None,
    opportunity: dict | None = None,
    p01: dict | None = None,
    p02: dict | None = None,
    p03: dict | None = None,
    *,
    require_expected_hash: bool = True,
) -> tuple[dict, dict]:
    return build_artifacts(
        FIXTURE if fixture is None else fixture,
        PARAMETERS if parameters is None else parameters,
        CAPACITY if capacity is None else capacity,
        GRID if grid is None else grid,
        OPPORTUNITY if opportunity is None else opportunity,
        P01 if p01 is None else p01,
        P02 if p02 is None else p02,
        P03 if p03 is None else p03,
        P01_SHA256,
        P02_SHA256,
        P03_SHA256,
        CAPACITY_SHA256,
        GRID_SHA256,
        OPPORTUNITY_SHA256,
        require_expected_hash=require_expected_hash,
    )


def test_frozen_target_gate_outputs_are_exact_replays() -> None:
    target_acceptance, kill_schema = _artifacts()
    assert target_acceptance["target_acceptance_sha256"] == FIXTURE["expected_target_acceptance_sha256"]
    assert kill_schema["kill_report_schema_sha256"] == FIXTURE["expected_kill_report_schema_sha256"]
    assert json.loads((ROOT / "target_acceptance.json").read_text(encoding="utf-8")) == target_acceptance
    assert json.loads((ROOT / "kill_report.schema.json").read_text(encoding="utf-8")) == kill_schema


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S12-P04"
    assert result["next"] == "S12/STAGE_REVIEW_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 15
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_current_state_does_not_claim_plausibility_falsification_or_verification() -> None:
    target_acceptance, _ = _artifacts()
    assert target_acceptance["plausibility_gate"]["status"] == "NOT_PLAUSIBLE_INSUFFICIENT_90D_OR_1000_SIGNALS"
    assert target_acceptance["plausibility_gate"]["observed_shadow_days"] == 0
    assert target_acceptance["plausibility_gate"]["observed_independent_equivalent_signals"] == 5
    assert target_acceptance["falsification_gate"]["current_empirical_assessment"]["status"] == "NOT_EVALUABLE_NO_EMPIRICAL_6_MONTH_DATA"
    assert target_acceptance["verification_gate"]["current_empirical_assessment"]["status"] == "NOT_VERIFIABLE_NO_ACTUAL_EXECUTION_AND_RECONCILIATION_EVIDENCE"
    assert target_acceptance["financial_target_status"] == "UNVERIFIED_NOT_GUARANTEED"


def test_synthetic_falsification_fixture_is_never_promoted_to_empirical() -> None:
    target_acceptance, _ = _artifacts()
    synthetic = target_acceptance["falsification_gate"]["synthetic_case_assessment"]
    assert synthetic["complete_calendar_months"] == 6
    assert synthetic["independent_equivalent_signals"] == 1000
    assert synthetic["monthly_return_95_upper_bound"] == "0.2999"
    assert synthetic["status"] == "SYNTHETIC_TEST_ONLY_NOT_EMPIRICAL"
    assert target_acceptance["falsification_gate"]["synthetic_case_is_not_empirical"] is True


@pytest.mark.parametrize(
    ("upper_bound", "expected"),
    [("0.2999", "FALSIFIED"), ("0.3000", "NOT_FALSIFIED_CONTINUE_EMPIRICAL_OBSERVATION"), ("0.3001", "NOT_FALSIFIED_CONTINUE_EMPIRICAL_OBSERVATION")],
)
def test_six_month_falsification_boundary_uses_strict_upper_bound(upper_bound: str, expected: str) -> None:
    result = classify_falsification(
        {
            "evidence_status": EMPIRICAL_EVIDENCE_STATUS,
            "complete_calendar_months": 6,
            "independent_equivalent_signals": 1000,
            "monthly_return_95_upper_bound": upper_bound,
        },
        target_monthly_return=Decimal("0.30"),
    )
    assert result["status"] == expected


@pytest.mark.parametrize(
    ("return_rate", "evidence_complete", "differences", "expected"),
    [("0.2999", True, 0, "NOT_VERIFIED_EMPIRICAL_RETURN_BELOW_TARGET"), ("0.3000", True, 0, "VERIFIED_30_PERCENT_TARGET"), ("0.3001", True, 0, "VERIFIED_30_PERCENT_TARGET"), ("0.3000", False, 0, "NOT_VERIFIABLE_INSUFFICIENT_12_MONTHS_OR_EVIDENCE"), ("0.3000", True, 1, "NOT_VERIFIABLE_INSUFFICIENT_12_MONTHS_OR_EVIDENCE")],
)
def test_twelve_month_verification_boundary_keeps_evidence_and_reconciliation_hard(return_rate: str, evidence_complete: bool, differences: int, expected: str) -> None:
    result = classify_verification(
        {
            "evidence_status": EMPIRICAL_EVIDENCE_STATUS,
            "complete_calendar_months": 12,
            "cashflow_adjusted_geometric_monthly_return": return_rate,
            "evidence_complete": evidence_complete,
            "unresolved_reconciliation_differences": differences,
        },
        target_monthly_return=Decimal("0.30"),
    )
    assert result["status"] == expected


def test_one_in_ten_thousand_adverse_threshold_delta_cannot_relax_a_gate() -> None:
    target_acceptance, _ = _artifacts()
    for upper_bound in (Decimal("0.2999"), Decimal("0.3001")):
        result = classify_falsification(
            {
                "evidence_status": EMPIRICAL_EVIDENCE_STATUS,
                "complete_calendar_months": 6,
                "independent_equivalent_signals": 1000,
                "monthly_return_95_upper_bound": format(upper_bound, "f"),
            },
            target_monthly_return=Decimal("0.30"),
        )
        assert result["reason_code"] != "NO_GATE_RELAXATION_FOR_TARGET_SHORTFALL"
    invariant = target_acceptance["hard_gate_invariants"]
    assert invariant["threshold_or_position_or_evidence_may_be_relaxed"] is False
    assert invariant["risk_target_shortfall_may_relax_gate"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture.update({"target_monthly_return": "0.3001"}),
        lambda fixture: fixture.update({"current_shadow_observed_days": 90}),
        lambda fixture: fixture.update({"current_independent_equivalent_signals": 1000}),
        lambda fixture: fixture.update({"p03_evidence_sha256": "f" * 64}),
        lambda fixture: fixture["synthetic_falsification_case"].update({"evidence_status": EMPIRICAL_EVIDENCE_STATUS}),
    ],
)
def test_unsafe_fixture_inputs_fail_closed(mutate) -> None:
    fixture = deepcopy(FIXTURE)
    mutate(fixture)
    with pytest.raises(TargetFalsificationError):
        _artifacts(fixture, require_expected_hash=False)


@pytest.mark.parametrize("target", ["p01", "p02", "p03", "capacity", "grid", "opportunity"])
def test_signed_predecessor_or_derived_artifact_tampering_fails_closed(target: str) -> None:
    if target == "p01":
        p01 = deepcopy(P01)
        p01["decision"] = "TARGET_GUARANTEED"
        with pytest.raises(TargetFalsificationError):
            _artifacts(p01=p01, require_expected_hash=False)
    elif target == "p02":
        p02 = deepcopy(P02)
        p02["next"] = "S12/P04_READY_NOT_STARTED"
        with pytest.raises(TargetFalsificationError):
            _artifacts(p02=p02, require_expected_hash=False)
    elif target == "p03":
        p03 = deepcopy(P03)
        p03["financial_target_status"] = "VERIFIED"
        with pytest.raises(TargetFalsificationError):
            _artifacts(p03=p03, require_expected_hash=False)
    elif target == "capacity":
        capacity = deepcopy(CAPACITY)
        capacity["summary"]["independent_equivalent_signals"] = 1000
        with pytest.raises(TargetFalsificationError):
            _artifacts(capacity=capacity, require_expected_hash=False)
    elif target == "grid":
        grid = deepcopy(GRID)
        grid["summary"]["highest_upper_band_cents"] = 9000
        with pytest.raises(TargetFalsificationError):
            _artifacts(grid=grid, require_expected_hash=False)
    else:
        opportunity = deepcopy(OPPORTUNITY)
        opportunity["return_cost_boundary"]["roi_reported"] = True
        with pytest.raises(TargetFalsificationError):
            _artifacts(opportunity=opportunity, require_expected_hash=False)


def test_core_source_has_no_network_soak_order_or_binary_float_capability() -> None:
    source = (ROOT / "target_falsification.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection({"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"})
    for forbidden in ("sleep(", "submit_order", "retry_order", "gmail", "cloudflare", "ovh", "float("):
        assert forbidden not in source


def test_candidate_fails_closed_when_generated_target_acceptance_is_tampered(tmp_path: Path) -> None:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    artifact_path = clone / "target_acceptance.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["hard_gate_invariants"]["threshold_or_position_or_evidence_may_be_relaxed"] = True
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S12P04-FROZEN-TARGET-GATE-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_rollback_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "target:falsification_and_verification_gate"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_acceptance_cli_is_wired_to_the_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S12-P04": write_target_falsification_phase_evidence' in source
    assert '"AC-S12-P04": verify_target_falsification_phase_evidence' in source
    with pytest.raises((TargetFalsificationAcceptanceError, FileNotFoundError)):
        from abd_acceptance.target_falsification_gate import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")


def test_artifact_hashes_remain_content_addressed_and_replay_is_deterministic() -> None:
    first_target, first_schema = _artifacts()
    for _ in range(4):
        target_acceptance, kill_schema = _artifacts()
        assert target_acceptance == first_target
        assert kill_schema == first_schema
    target_without_hash = deepcopy(first_target)
    schema_without_hash = deepcopy(first_schema)
    assert target_without_hash.pop("target_acceptance_sha256") == artifact_sha256(target_without_hash)
    assert schema_without_hash.pop("kill_report_schema_sha256") == artifact_sha256(schema_without_hash)


def test_kill_schema_covers_all_report_only_and_empirical_gate_reason_codes() -> None:
    _, kill_schema = _artifacts()
    assert [row["code"] for row in kill_schema["reason_codes"]] == [
        "TARGET_SHORTFALL_REPORT_ONLY",
        "PLAUSIBILITY_INSUFFICIENT_90D_OR_1000_SIGNALS",
        "FALSIFICATION_REQUIRES_6_COMPLETE_MONTHS_AND_1000_SIGNALS",
        "VERIFICATION_REQUIRES_12_MONTHS_EXECUTION_EVIDENCE_AND_ZERO_RECONCILIATION_DIFFERENCE",
        "NO_GATE_RELAXATION_FOR_TARGET_SHORTFALL",
    ]
    assert kill_schema["hard_invariants"]["synthetic_fixture_may_be_marked_empirical"] is False
