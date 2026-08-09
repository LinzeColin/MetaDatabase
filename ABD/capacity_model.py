"""Frozen capacity and correlation correction replay for ABD S12/P02."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from equivalent_signal import (
    EquivalentSignalError,
    decimal_text,
    floor_cents,
    require_decimal,
    require_int,
    require_text,
    select_cluster_representatives,
    allocate_platform_capacity,
)
from risk_engine import build_correlation_graph


VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT"
SYNTHETIC_EVIDENCE_STATUS = "SYNTHETIC_VERIFIED_FOR_TEST_ONLY"
P01_CONTRACT_ID = "AC-S12-P01"
P01_DECISION = "TARGET_CURVE_READY_DOWNSTREAM_CAPACITY_ECONOMICS_AND_FALSIFICATION_GATES_REQUIRED"

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_provider_capacity_observed": False,
    "real_account_balance_read_or_written": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class CapacityModelError(ValueError):
    """Raised when a capacity replay could duplicate or overstate coverage."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _no_binary_number(value: Any) -> bool:
    if type(value) is float:
        return False
    if isinstance(value, Mapping):
        return all(_no_binary_number(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(_no_binary_number(item) for item in value)
    return True


def _strict_object(value: Any, required: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not required.issubset(value) or not _no_binary_number(value):
        raise CapacityModelError("%s is malformed" % label)
    return value


def _validate_p01_evidence(value: Any, expected_sha256: str, actual_sha256: str) -> Mapping[str, Any]:
    evidence = _strict_object(value, {"contract_id", "status", "decision", "next", "financial_target_status", "external_effect_boundary"}, label="p01_evidence")
    if (
        evidence.get("contract_id") != P01_CONTRACT_ID
        or evidence.get("status") != "PASS"
        or evidence.get("decision") != P01_DECISION
        or evidence.get("next") != "S12/P02_READY_NOT_STARTED"
        or evidence.get("financial_target_status") != "UNVERIFIED_NOT_GUARANTEED"
        or evidence.get("external_effect_boundary", {}).get("order_submission_enabled") is not False
        or expected_sha256 != actual_sha256
    ):
        raise CapacityModelError("P01 evidence is not the exact signed prerequisite")
    return evidence


def _validate_platforms(value: Any) -> Dict[str, int]:
    if not isinstance(value, list) or not value:
        raise CapacityModelError("platform_limits must be a non-empty list")
    result: Dict[str, int] = {}
    for row in value:
        item = _strict_object(row, {"platform_id", "remaining_capacity_cents", "evidence_status"}, label="platform_limit")
        platform_id = require_text(item["platform_id"], label="platform_id")
        if platform_id in result or item["evidence_status"] != SYNTHETIC_EVIDENCE_STATUS:
            raise CapacityModelError("platform limits are not unique frozen synthetic evidence")
        result[platform_id] = require_int(item["remaining_capacity_cents"], label="remaining_capacity_cents")
    return result


def _validate_cluster_exposures(value: Any, cluster_ids: set[str]) -> Dict[str, int]:
    if not isinstance(value, list) or len(value) != len(cluster_ids):
        raise CapacityModelError("cluster_exposures must cover every declared correlation cluster")
    result: Dict[str, int] = {}
    for row in value:
        item = _strict_object(row, {"cluster_id", "existing_exposure_cents", "evidence_status"}, label="cluster_exposure")
        cluster_id = require_text(item["cluster_id"], label="cluster_id")
        if cluster_id not in cluster_ids or cluster_id in result or item["evidence_status"] != SYNTHETIC_EVIDENCE_STATUS:
            raise CapacityModelError("cluster exposure is unknown, duplicate, or unauditable")
        result[cluster_id] = require_int(item["existing_exposure_cents"], label="existing_exposure_cents")
    return result


def _validate_opportunities(value: Any, cluster_ids: set[str], platform_ids: set[str]) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CapacityModelError("opportunities must be a non-empty list")
    rows: list[Dict[str, Any]] = []
    identifiers: set[str] = set()
    for raw in value:
        row = _strict_object(
            raw,
            {"opportunity_id", "correlation_cluster_id", "platform_id", "requested_capacity_cents", "executable_fraction", "candidate_status", "evidence_status"},
            label="opportunity",
        )
        opportunity_id = require_text(row["opportunity_id"], label="opportunity_id")
        cluster_id = require_text(row["correlation_cluster_id"], label="correlation_cluster_id")
        platform_id = require_text(row["platform_id"], label="platform_id")
        if opportunity_id in identifiers or cluster_id not in cluster_ids or platform_id not in platform_ids:
            raise CapacityModelError("opportunity identity or declared capacity reference is invalid")
        if row["candidate_status"] != "SYNTHETIC_ELIGIBLE_CAPACITY_ONLY" or row["evidence_status"] != SYNTHETIC_EVIDENCE_STATUS:
            raise CapacityModelError("only synthetic capacity-only opportunities are accepted")
        identifiers.add(opportunity_id)
        rows.append(
            {
                "opportunity_id": opportunity_id,
                "correlation_cluster_id": cluster_id,
                "platform_id": platform_id,
                "requested_capacity_cents": require_int(row["requested_capacity_cents"], label="requested_capacity_cents", minimum=1),
                "executable_fraction": require_decimal(row["executable_fraction"], label="executable_fraction"),
            }
        )
    if {row["correlation_cluster_id"] for row in rows} != cluster_ids:
        raise CapacityModelError("frozen opportunities must expose every declared correlation cluster")
    return rows


def _validate_fixture(
    fixture: Any,
    parameters: Any,
    correlation_graph: Any,
    p01_evidence: Any,
    p01_sha256: str,
    *,
    require_expected_hash: bool,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Dict[str, int], Dict[str, int], list[Dict[str, Any]]]:
    row = _strict_object(
        fixture,
        {
            "schema_version",
            "fixture_id",
            "contract_id",
            "requirement_id",
            "stage_id",
            "phase_id",
            "product_version",
            "fixed_clock",
            "input_mode",
            "p01_evidence_sha256",
            "correlation_graph_sha256",
            "bankroll_cents",
            "platform_limits",
            "cluster_exposures",
            "opportunities",
        },
        label="fixture",
    )
    expected_identity = {
        "schema_version": "1.0.0",
        "fixture_id": "S12-P02-CAPACITY-CORRELATION-FROZEN",
        "contract_id": "AC-S12-P02",
        "requirement_id": "REQ-S12-P02",
        "stage_id": "S12",
        "phase_id": "P02",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
    }
    if any(row.get(key) != value for key, value in expected_identity.items()):
        raise CapacityModelError("fixture identity differs from the frozen P02 contract")
    if require_expected_hash and (not isinstance(row.get("expected_capacity_report_sha256"), str) or len(row["expected_capacity_report_sha256"]) != 64):
        raise CapacityModelError("fixture must pin expected_capacity_report_sha256")
    if not isinstance(parameters, Mapping) or parameters.get("numeric_determinism", {}).get("authoritative_decimal_precision_digits") != 50:
        raise CapacityModelError("canonical decimal determinism is unavailable")
    expected_graph = build_correlation_graph(parameters)
    if correlation_graph != expected_graph or artifact_sha256(correlation_graph) != row["correlation_graph_sha256"]:
        raise CapacityModelError("correlation graph differs from the signed S11 policy")
    _validate_p01_evidence(p01_evidence, row["p01_evidence_sha256"], p01_sha256)
    bankroll = require_int(row["bankroll_cents"], label="bankroll_cents", minimum=1)
    if bankroll != 30000:
        raise CapacityModelError("P02 frozen fixture must preserve the A$300 bankroll")
    clusters = expected_graph.get("clusters", [])
    cluster_ids = {item.get("cluster_id") for item in clusters if isinstance(item, Mapping)}
    if len(cluster_ids) != 6 or not all(isinstance(value, str) and value for value in cluster_ids):
        raise CapacityModelError("correlation graph clusters are not complete")
    platform_limits = _validate_platforms(row["platform_limits"])
    cluster_exposures = _validate_cluster_exposures(row["cluster_exposures"], set(cluster_ids))
    opportunities = _validate_opportunities(row["opportunities"], set(cluster_ids), set(platform_limits))
    return row, parameters, expected_graph, p01_evidence, platform_limits, cluster_exposures, opportunities


def build_capacity_report(
    fixture: Any,
    parameters: Any,
    correlation_graph: Any,
    p01_evidence: Any,
    p01_sha256: str,
    *,
    require_expected_hash: bool = True,
) -> Dict[str, Any]:
    """Build a capacity-only report without treating capacity as investment return."""

    row, params, graph, _, platform_limits, cluster_exposures, opportunities = _validate_fixture(
        fixture,
        parameters,
        correlation_graph,
        p01_evidence,
        p01_sha256,
        require_expected_hash=require_expected_hash,
    )
    cluster_caps: Dict[str, int] = {}
    for cluster in graph["clusters"]:
        cluster_id = cluster["cluster_id"]
        cap_fraction = require_decimal(cluster["cap_fraction"], label="cluster_cap_fraction")
        cap_cents = floor_cents(Decimal(row["bankroll_cents"]) * cap_fraction, label="cluster_cap_cents")
        cluster_caps[cluster_id] = max(0, cap_cents - cluster_exposures[cluster_id])

    prepared: list[Dict[str, Any]] = []
    for opportunity in opportunities:
        risk_limited = min(opportunity["requested_capacity_cents"], cluster_caps[opportunity["correlation_cluster_id"]])
        executable = floor_cents(Decimal(risk_limited) * opportunity["executable_fraction"], label="pre_platform_executable_capacity_cents")
        prepared.append(
            {
                **opportunity,
                "risk_limited_capacity_cents": risk_limited,
                "pre_platform_executable_capacity_cents": executable,
                "executable_fraction": decimal_text(opportunity["executable_fraction"]),
            }
        )
    clusters, representatives = select_cluster_representatives(prepared, cluster_caps)
    allocations, platform_remaining = allocate_platform_capacity(representatives, platform_limits)
    allocation_by_id = {item["opportunity_id"]: item for item in allocations}
    correlation_adjusted = sum(item["correlation_adjusted_capacity_cents"] for item in clusters)
    final_executable = sum(item["final_executable_capacity_cents"] for item in allocations)
    raw_naive = sum(item["pre_platform_executable_capacity_cents"] for item in prepared)
    positive_clusters = [item for item in allocations if item["final_executable_capacity_cents"] > 0]
    required_signals = require_int(params["target_30pct"]["shadow_min_independent_equivalent_signals"], label="shadow_min_independent_equivalent_signals", minimum=1)
    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_id": "ART-S12-P02-03",
        "contract_id": "AC-S12-P02",
        "requirement_id": "REQ-S12-P02",
        "stage_id": "S12",
        "phase_id": "P02",
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "p01_evidence_sha256": p01_sha256,
        "correlation_graph_sha256": artifact_sha256(graph),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "policy": {
            "correlation_rule": "ONE_REPRESENTATIVE_PER_PREDECLARED_HIGH_CORRELATION_CLUSTER",
            "platform_rule": "DETERMINISTIC_DECLARED_REMAINING_CAPACITY_NO_OVERALLOCATION",
            "executable_fraction_rule": "FLOOR_RISK_LIMITED_CAPACITY_TIMES_DECLARED_EXECUTABLE_FRACTION",
            "target_shortfall_may_relax_gate": False,
            "chase_loss_prohibited": True,
        },
        "prepared_opportunities": prepared,
        "clusters": clusters,
        "platform_allocations": [
            {**item, "representative_selected": True, "correlation_adjusted_capacity_cents": allocation_by_id[item["opportunity_id"]]["capacity_before_platform_limit_cents"]}
            for item in allocations
        ],
        "summary": {
            "raw_candidate_count": len(prepared),
            "distinct_correlation_cluster_count": len(clusters),
            "remaining_opportunity_count": len(positive_clusters),
            "independent_equivalent_signals": len(positive_clusters),
            "raw_naive_executable_capacity_cents": raw_naive,
            "correlation_adjusted_capacity_cents": correlation_adjusted,
            "final_platform_and_executable_capacity_cents": final_executable,
            "platform_remaining_capacity_cents": dict(sorted(platform_remaining.items())),
            "duplicate_capacity_not_counted_cents": raw_naive - correlation_adjusted,
            "platform_limited_capacity_not_counted_cents": correlation_adjusted - final_executable,
        },
        "target_plausibility": {
            "independent_equivalent_signals_required": required_signals,
            "independent_equivalent_signals_observed": len(positive_clusters),
            "status": "INSUFFICIENT_INDEPENDENT_EQUIVALENT_SIGNALS_TARGET_UNVERIFIED" if len(positive_clusters) < required_signals else "COUNT_GATE_REACHED_TARGET_STILL_UNVERIFIED",
            "capacity_is_not_return_or_30_PERCENT_COVERAGE": True,
            "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        },
        "decision": "CAPACITY_CORRECTED_SYNTHETIC_ONLY_NOT_TARGET_COVERAGE",
        "next": "S12/P03_READY_NOT_STARTED",
    }
    report["report_sha256"] = artifact_sha256(report)
    if require_expected_hash and report["report_sha256"] != row["expected_capacity_report_sha256"]:
        raise CapacityModelError("frozen capacity report replay hash differs")
    return report


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD S12/P02 frozen capacity correlation replay")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--correlation-graph", type=Path, required=True)
    parser.add_argument("--p01-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence_bytes = args.p01_evidence.read_bytes()
    report = build_capacity_report(
        _load_json(args.fixture),
        _load_json(args.parameters),
        _load_json(args.correlation_graph),
        _load_json(args.p01_evidence),
        hashlib.sha256(evidence_bytes).hexdigest(),
    )
    args.output.write_bytes(canonical_json_bytes(report))
    print(json.dumps({"status": "PASS", "capacity_report_sha256": report["report_sha256"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
