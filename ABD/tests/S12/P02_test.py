from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import shutil

import pytest

from abd_acceptance.capacity_correlation import (
    CapacityCorrelationAcceptanceError,
    evaluate_contract,
    perform_rollback_drill,
    validate_candidate_preflight,
)
from capacity_model import CapacityModelError, artifact_sha256, build_capacity_report


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "machine/tests/fixtures/S12_P02.json").read_text(encoding="utf-8"))
PARAMETERS = json.loads((ROOT / "machine/facts/parameters.json").read_text(encoding="utf-8"))
GRAPH = json.loads((ROOT / "correlation_graph.json").read_text(encoding="utf-8"))
P01_EVIDENCE_PATH = ROOT / "machine/evidence/EVD-S12-P01.json"
P01_EVIDENCE = json.loads(P01_EVIDENCE_PATH.read_text(encoding="utf-8"))
P01_SHA256 = hashlib.sha256(P01_EVIDENCE_PATH.read_bytes()).hexdigest()


def _report(fixture: dict | None = None, graph: dict | None = None, evidence: dict | None = None, *, require_expected_hash: bool = True) -> dict:
    return build_capacity_report(
        FIXTURE if fixture is None else fixture,
        PARAMETERS,
        GRAPH if graph is None else graph,
        P01_EVIDENCE if evidence is None else evidence,
        P01_SHA256,
        require_expected_hash=require_expected_hash,
    )


def test_frozen_capacity_report_is_an_exact_replay() -> None:
    report = _report()
    assert report["report_sha256"] == FIXTURE["expected_capacity_report_sha256"]
    assert json.loads((ROOT / "capacity_report.json").read_text(encoding="utf-8")) == report
    assert artifact_sha256(GRAPH) == FIXTURE["correlation_graph_sha256"]


def test_candidate_preflight_passes_without_generated_test_reports() -> None:
    result = validate_candidate_preflight(ROOT)
    assert result["status"] == "PASS", result
    assert result["contract_id"] == "AC-S12-P02"
    assert result["next"] == "S12/P03_READY_NOT_STARTED"
    assert result["summary"]["checks"] >= 21
    assert result["external_effect_boundary"]["real_time_soak_waited"] is False
    assert result["external_effect_boundary"]["incremental_cash_spent_aud"] == "0.00"


def test_highly_correlated_members_are_counted_once_per_declared_cluster() -> None:
    report = _report()
    clusters = {item["cluster_id"]: item for item in report["clusters"]}
    assert clusters["C01-SAME-EVENT-MARKETS"]["naive_member_executable_capacity_cents"] == 2320
    assert clusters["C01-SAME-EVENT-MARKETS"]["correlation_adjusted_capacity_cents"] == 1200
    assert clusters["C01-SAME-EVENT-MARKETS"]["not_counted_as_additional_coverage_ids"] == ["S12-P02-C01-B"]
    assert clusters["C03-LEAGUE-WEATHER-LINEUP"]["naive_member_executable_capacity_cents"] == 2430
    assert clusters["C03-LEAGUE-WEATHER-LINEUP"]["correlation_adjusted_capacity_cents"] == 1350
    assert report["summary"]["duplicate_capacity_not_counted_cents"] == 2200


def test_platform_capacity_is_applied_once_across_independent_clusters() -> None:
    report = _report()
    allocations = {item["opportunity_id"]: item["final_executable_capacity_cents"] for item in report["platform_allocations"]}
    assert allocations == {
        "S12-P02-C01-A": 1200,
        "S12-P02-C02-A": 600,
        "S12-P02-C03-A": 1350,
        "S12-P02-C04-A": 250,
        "S12-P02-C05-A": 0,
        "S12-P02-C06-A": 600,
    }
    assert report["summary"]["final_platform_and_executable_capacity_cents"] == 4000
    assert report["summary"]["platform_remaining_capacity_cents"] == {
        "SYNTHETIC-OTHER-C": 100,
        "SYNTHETIC-SPORTSBET-B": 0,
        "SYNTHETIC-TAB-A": 0,
    }


def test_capacity_never_becomes_a_30_percent_return_or_order_claim() -> None:
    report = _report()
    assert report["target_plausibility"] == {
        "independent_equivalent_signals_required": 1000,
        "independent_equivalent_signals_observed": 5,
        "status": "INSUFFICIENT_INDEPENDENT_EQUIVALENT_SIGNALS_TARGET_UNVERIFIED",
        "capacity_is_not_return_or_30_PERCENT_COVERAGE": True,
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
    }
    assert report["external_effect_boundary"]["order_submission_enabled"] is False
    assert report["external_effect_boundary"]["financial_return_verified_or_guaranteed"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fixture: fixture["opportunities"][1].update({"opportunity_id": "S12-P02-C01-A"}),
        lambda fixture: fixture["opportunities"][0].update({"correlation_cluster_id": "UNKNOWN-CLUSTER"}),
        lambda fixture: fixture["opportunities"][0].update({"platform_id": "UNKNOWN-PLATFORM"}),
        lambda fixture: fixture["opportunities"][0].update({"candidate_status": "REAL_ORDER_READY"}),
        lambda fixture: fixture["cluster_exposures"][0].update({"evidence_status": "UNVERIFIED"}),
    ],
)
def test_malformed_or_unauditable_inputs_fail_closed(mutate) -> None:
    fixture = deepcopy(FIXTURE)
    mutate(fixture)
    with pytest.raises(CapacityModelError):
        _report(fixture, require_expected_hash=False)


def test_graph_or_p01_receipt_tampering_fails_closed() -> None:
    graph = deepcopy(GRAPH)
    graph["clusters"].pop()
    with pytest.raises(CapacityModelError):
        _report(graph=graph, require_expected_hash=False)
    evidence = deepcopy(P01_EVIDENCE)
    evidence["decision"] = "TARGET_GUARANTEED"
    with pytest.raises(CapacityModelError):
        _report(evidence=evidence, require_expected_hash=False)


@pytest.mark.parametrize("delta", [Decimal("-0.0001"), Decimal("0.0001")])
def test_one_in_ten_thousand_executable_fraction_perturbation_preserves_correction(delta: Decimal) -> None:
    fixture = deepcopy(FIXTURE)
    for row in fixture["opportunities"]:
        row["executable_fraction"] = format(Decimal(row["executable_fraction"]) + delta, "f")
    baseline = _report()
    perturbed = _report(fixture, require_expected_hash=False)
    assert perturbed["summary"]["correlation_adjusted_capacity_cents"] <= perturbed["summary"]["raw_naive_executable_capacity_cents"]
    assert perturbed["summary"]["final_platform_and_executable_capacity_cents"] <= perturbed["summary"]["correlation_adjusted_capacity_cents"]
    assert perturbed["summary"]["independent_equivalent_signals"] <= perturbed["summary"]["distinct_correlation_cluster_count"]
    assert perturbed["target_plausibility"]["capacity_is_not_return_or_30_PERCENT_COVERAGE"] is True
    if delta < 0:
        assert perturbed["summary"]["final_platform_and_executable_capacity_cents"] <= baseline["summary"]["final_platform_and_executable_capacity_cents"]


def test_core_sources_have_no_network_soak_or_order_capability() -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os", "random"}
    for relative in ("capacity_model.py", "equivalent_signal.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert not imports.intersection(prohibited_imports)
        assert "sleep(" not in source
        assert "submit_order" not in source
        assert "retry_order" not in source
        assert "float(" not in source


def test_candidate_fails_closed_when_capacity_report_is_tampered(tmp_path: Path) -> None:
    clone = tmp_path / "ABD"
    shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", ".venv"))
    report_path = clone / "capacity_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["summary"]["correlation_adjusted_capacity_cents"] = 7290
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = evaluate_contract(clone)
    assert result["status"] == "FAIL"
    assert "S12P02-FROZEN-CAPACITY-REPLAY-EXACT" in result["summary"]["failed_check_ids"]


def test_rollback_is_local_and_has_no_external_side_effect() -> None:
    rollback = perform_rollback_drill(ROOT)
    assert rollback["status"] == "PASS"
    assert rollback["feature_flag_id"] == "capacity:correlation_adjustment"
    assert rollback["external_state_changed"] is False
    assert rollback["production_state_changed"] is False
    assert rollback["real_time_soak_waited"] is False


def test_acceptance_cli_is_wired_to_the_exact_contract() -> None:
    source = (ROOT / "abd_acceptance/__main__.py").read_text(encoding="utf-8")
    assert '"AC-S12-P02": write_capacity_correlation_phase_evidence' in source
    assert '"AC-S12-P02": verify_capacity_correlation_phase_evidence' in source
    with pytest.raises((CapacityCorrelationAcceptanceError, FileNotFoundError)):
        from abd_acceptance.capacity_correlation import verify_existing_phase_evidence

        verify_existing_phase_evidence(ROOT / "missing")
