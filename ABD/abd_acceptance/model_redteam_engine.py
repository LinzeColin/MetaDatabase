"""Deterministic S16/P03 red-team and cross-model review artifacts.

This module evaluates only pre-registered synthetic adversarial inputs.  It
does not query a market, account, mailbox, or runtime provider; it neither
activates a model nor creates a recommendation or an order.  A P03 pass proves
that the six frozen adversarial paths fail closed in this local contract only.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .model_eval_engine import (
    CLAIM_BOUNDARY as P02_CLAIM_BOUNDARY,
    EVAL_CATALOG_PATH,
    EVAL_REPORT_PATH,
    FIXTURE_PATH as P02_FIXTURE_PATH,
    MODEL_REGISTRY_PATH,
    canonical_json_bytes,
    load_fixture as load_p02_fixture,
    sha256_file,
    strict_json_load,
    validate_artifacts as validate_p02_artifacts,
)


CONTRACT_ID = "AC-S16-P03"
REQUIREMENT_ID = "REQ-S16-P03"
STAGE_ID = "S16"
PHASE_ID = "P03"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_REDTEAM_NO_NETWORK_NO_ACCOUNT"
FIXTURE_PATH = Path("machine/tests/fixtures/S16_P03.json")
MODEL_REDTEAM_PATH = Path("model_redteam.json")
CROSS_MODEL_REVIEW_PATH = Path("cross_model_review.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P02.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
RISK_REGISTER_PATH = Path("machine/facts/risk_register.json")
STRATEGY_SPEC_PATH = Path("machine/facts/strategy_spec.json")
REDTEAM_ARTIFACT_ID = "ART-S16-P03-01"
REVIEW_ARTIFACT_ID = "ART-S16-P03-02"
_ID = re.compile(r"[A-Z][A-Z0-9_:-]{2,79}")
_SHA256 = re.compile(r"[0-9a-f]{64}")

ATTACK_CATEGORIES = (
    "FUTURE_LEAKAGE",
    "OUTLIER_PRICE",
    "IDENTITY_MISMATCH",
    "DATA_POISONING",
    "CORRELATION_EXPOSURE",
    "TARGET_CHASING",
)
ATTACK_REASONS = {
    "FUTURE_LEAKAGE": "FUTURE_LEAKAGE_TOLERANCE_ZERO",
    "OUTLIER_PRICE": "OUTLIER_MAD_GATE_BLOCKED",
    "IDENTITY_MISMATCH": "IDENTITY_GATE_BLOCKED",
    "DATA_POISONING": "SOURCE_HASH_INTEGRITY_BLOCKED",
    "CORRELATION_EXPOSURE": "CORRELATION_CLUSTER_CAP_BLOCKED",
    "TARGET_CHASING": "TARGET_SHORTFALL_CANNOT_RELAX_GATE",
}
CLAIM_BOUNDARY = {
    **P02_CLAIM_BOUNDARY,
    "synthetic_redteam_only": True,
    "cross_model_review_is_not_model_inference": True,
    "model_weight_changed": False,
    "model_promotion_allowed": False,
}


class ModelRedteamInputError(ValueError):
    """Raised when the frozen P03 red-team surface is malformed or drifts."""


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ModelRedteamInputError("%s fields are not exact" % label)
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ModelRedteamInputError("%s must be a stable uppercase identifier" % label)
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ModelRedteamInputError("%s must be a SHA-256 value" % label)
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ModelRedteamInputError("%s must be a decimal string" % label)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ModelRedteamInputError("%s is not a decimal" % label) from exc
    if not result.is_finite():
        raise ModelRedteamInputError("%s must be finite" % label)
    return result


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ModelRedteamInputError("%s must be an ISO timestamp" % label)
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ModelRedteamInputError("%s is not an ISO timestamp" % label) from exc
    if result.tzinfo is None:
        raise ModelRedteamInputError("%s must include a timezone" % label)
    return result


def _parameters(root: Path) -> Mapping[str, Any]:
    value = strict_json_load(root / PARAMETERS_PATH)
    if not isinstance(value, Mapping):
        raise ModelRedteamInputError("parameters must be an object")
    coverage = value.get("coverage_and_freshness")
    market = value.get("market_model")
    risk = value.get("risk")
    target = value.get("target_30pct")
    if not all(isinstance(item, Mapping) for item in (coverage, market, risk, target)):
        raise ModelRedteamInputError("P03 parameter controls are unavailable")
    expected = (
        coverage.get("identity_confidence_min") == "0.995"
        and coverage.get("outlier_mad_multiplier") == "3.5"
        and market.get("future_leakage_tolerance") == 0
        and risk.get("correlation_cluster_cap") == "0.050"
        and risk.get("target_shortfall_may_relax_gate") is False
        and risk.get("chase_loss_prohibited") is True
        and target.get("monthly_return") == "0.30"
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
    )
    if not expected:
        raise ModelRedteamInputError("frozen P03 parameter controls have drifted")
    return value


def _risk_register(root: Path) -> Mapping[str, Mapping[str, Any]]:
    value = strict_json_load(root / RISK_REGISTER_PATH)
    rows = value.get("risks") if isinstance(value, Mapping) else None
    if not isinstance(rows, list):
        raise ModelRedteamInputError("risk register is unavailable")
    selected = {row.get("id"): row for row in rows if isinstance(row, Mapping)}
    expected = {
        "R-001": "30%月复利无法由随机市场保证",
        "R-004": "赛事、盘口或结算身份错配",
        "R-005": "未来数据泄漏制造虚假优势",
        "R-006": "离群赔率制造虚假利润",
        "R-007": "万分之一或赔率跳动改变动作",
    }
    if any(not isinstance(selected.get(key), Mapping) or selected[key].get("risk") != text for key, text in expected.items()):
        raise ModelRedteamInputError("P03 risk-register controls have drifted")
    return {key: selected[key] for key in expected}


def _validate_p02_surface(root: Path, metadata: Any) -> Mapping[str, Any]:
    row = _closed_mapping(metadata, {"evidence_path", "evidence_sha256", "status", "next"}, "p02_evidence")
    if (
        row["evidence_path"] != P02_EVIDENCE_PATH.as_posix()
        or _sha256(row["evidence_sha256"], "p02 evidence SHA") != row["evidence_sha256"]
        or row["status"] != "PASS"
        or row["next"] != "S16/P03_READY_NOT_STARTED"
    ):
        raise ModelRedteamInputError("P02 prerequisite metadata is invalid")
    evidence = strict_json_load(root / P02_EVIDENCE_PATH)
    actual_evidence_hash = sha256_file(root / P02_EVIDENCE_PATH)
    if (
        not isinstance(evidence, Mapping)
        or actual_evidence_hash != row["evidence_sha256"]
        or evidence.get("contract_id") != "AC-S16-P02"
        or evidence.get("status") != "PASS"
        or evidence.get("next") != "S16/P03_READY_NOT_STARTED"
    ):
        raise ModelRedteamInputError("P02 signed receipt is not reproducible")
    p02_fixture = load_p02_fixture(root, P02_FIXTURE_PATH)
    validate_p02_artifacts(root, p02_fixture)
    registry = strict_json_load(root / MODEL_REGISTRY_PATH)
    catalog = strict_json_load(root / EVAL_CATALOG_PATH)
    report = strict_json_load(root / EVAL_REPORT_PATH)
    if not all(isinstance(item, Mapping) for item in (registry, catalog, report)):
        raise ModelRedteamInputError("P01/P02 model artifacts must be objects")
    champion = registry.get("champion")
    challengers = registry.get("challengers")
    promotion = report.get("model_promotion")
    gates = report.get("gate_summary")
    if (
        not isinstance(champion, Mapping)
        or champion.get("model_id") != "MARKET_CONSENSUS_CHAMPION"
        or champion.get("active_weight") != "1.00"
        or not isinstance(challengers, list)
        or len(challengers) != 6
        or any(not isinstance(item, Mapping) or item.get("active_weight") != "0.00" for item in challengers)
        or catalog.get("evaluation_candidate", {}).get("model_id") != "GENERIC_RESIDUAL_CHALLENGER"
        or not isinstance(promotion, Mapping)
        or promotion.get("weight_before") != "0.00"
        or promotion.get("weight_after") != "0.00"
        or promotion.get("weight_change_allowed") is not False
        or promotion.get("activation_status") != "NOT_ACTIVATED_PENDING_S16_P03_AND_S16_P04"
        or gates != {
            "all_95pct_lower_bound_gates_pass": True,
            "all_calibration_gates_pass": True,
            "all_s16_p02_gates_pass": True,
            "scope": "FROZEN_SYNTHETIC_EVALUATION_ONLY_NOT_EMPIRICAL_OR_FINANCIAL_RETURN",
        }
        or catalog.get("claim_boundary") != P02_CLAIM_BOUNDARY
        or report.get("claim_boundary") != P02_CLAIM_BOUNDARY
    ):
        raise ModelRedteamInputError("P02 promotion boundary has drifted")
    return {
        "registry": registry,
        "catalog": catalog,
        "report": report,
        "hashes": {
            P02_EVIDENCE_PATH.as_posix(): actual_evidence_hash,
            P02_FIXTURE_PATH.as_posix(): sha256_file(root / P02_FIXTURE_PATH),
            MODEL_REGISTRY_PATH.as_posix(): sha256_file(root / MODEL_REGISTRY_PATH),
            EVAL_CATALOG_PATH.as_posix(): sha256_file(root / EVAL_CATALOG_PATH),
            EVAL_REPORT_PATH.as_posix(): sha256_file(root / EVAL_REPORT_PATH),
        },
    }


def _validate_attack_input(category: str, value: Any, p02: Mapping[str, Any]) -> Mapping[str, Any]:
    if category == "FUTURE_LEAKAGE":
        row = _closed_mapping(value, {"feature_available_at", "decision_at"}, category)
        _timestamp(row["feature_available_at"], "feature_available_at")
        _timestamp(row["decision_at"], "decision_at")
        return row
    if category == "OUTLIER_PRICE":
        row = _closed_mapping(value, {"observed_odds", "median_odds", "mad"}, category)
        if _decimal(row["observed_odds"], "observed_odds") <= 0 or _decimal(row["median_odds"], "median_odds") <= 0 or _decimal(row["mad"], "mad") <= 0:
            raise ModelRedteamInputError("outlier values must be positive")
        return row
    if category == "IDENTITY_MISMATCH":
        row = _closed_mapping(value, {"expected_identity", "observed_identity", "identity_confidence"}, category)
        if not all(isinstance(row[key], str) and row[key] for key in ("expected_identity", "observed_identity")):
            raise ModelRedteamInputError("identity labels must be non-empty")
        confidence = _decimal(row["identity_confidence"], "identity_confidence")
        if confidence < 0 or confidence > 1:
            raise ModelRedteamInputError("identity confidence must be within zero and one")
        return row
    if category == "DATA_POISONING":
        row = _closed_mapping(value, {"expected_source_sha256", "observed_source_sha256"}, category)
        _sha256(row["expected_source_sha256"], "expected source SHA")
        _sha256(row["observed_source_sha256"], "observed source SHA")
        if row["expected_source_sha256"] != p02["hashes"][EVAL_REPORT_PATH.as_posix()]:
            raise ModelRedteamInputError("data-poisoning control must bind the signed P02 report")
        return row
    if category == "CORRELATION_EXPOSURE":
        row = _closed_mapping(value, {"proposed_cluster_exposure"}, category)
        if _decimal(row["proposed_cluster_exposure"], "proposed_cluster_exposure") < 0:
            raise ModelRedteamInputError("cluster exposure cannot be negative")
        return row
    if category == "TARGET_CHASING":
        row = _closed_mapping(value, {"claimed_monthly_return", "requested_gate_relaxation"}, category)
        _decimal(row["claimed_monthly_return"], "claimed_monthly_return")
        if not isinstance(row["requested_gate_relaxation"], bool):
            raise ModelRedteamInputError("requested_gate_relaxation must be boolean")
        return row
    raise ModelRedteamInputError("unsupported attack category: %s" % category)


def validate_fixture(root: Path, value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "parameters_sha256",
        "p02_evidence",
        "attack_cases",
        "review_protocol",
        "minimum_targeted_pytest_cases",
        "expected_decision",
        "expected_next",
        "claim_boundary",
    }
    fixture = _closed_mapping(value, fields, "S16/P03 fixture")
    expected = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S16-P03-REDTEAM-CROSS-MODEL",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "expected_decision": "S16_P03_REDTEAM_AND_CROSS_MODEL_REVIEW_PASS_P04_REQUIRED",
        "expected_next": "S16/P04_READY_NOT_STARTED",
    }
    if any(fixture.get(key) != expected_value for key, expected_value in expected.items()):
        raise ModelRedteamInputError("fixture identity has drifted")
    if fixture["parameters_sha256"] != sha256_file(root / PARAMETERS_PATH):
        raise ModelRedteamInputError("fixture parameters hash is not bound")
    if fixture["claim_boundary"] != CLAIM_BOUNDARY:
        raise ModelRedteamInputError("fixture claim boundary has drifted")
    if not isinstance(fixture["minimum_targeted_pytest_cases"], int) or fixture["minimum_targeted_pytest_cases"] < 1:
        raise ModelRedteamInputError("minimum targeted test count must be positive")
    parameters = _parameters(root)
    risks = _risk_register(root)
    p02 = _validate_p02_surface(root, fixture["p02_evidence"])
    cases = fixture["attack_cases"]
    if not isinstance(cases, list) or len(cases) != len(ATTACK_CATEGORIES):
        raise ModelRedteamInputError("fixture must contain each frozen attack category exactly once")
    parsed_cases = []
    for number, (category, raw) in enumerate(zip(ATTACK_CATEGORIES, cases), start=1):
        row = _closed_mapping(raw, {"attack_id", "category", "attack_input", "expected_outcome", "expected_reason"}, "attack case")
        if (
            _identifier(row["attack_id"], "attack_id") != "S16P03-ATTACK-%02d" % number
            or row["category"] != category
            or row["expected_outcome"] != "BLOCKED"
            or row["expected_reason"] != ATTACK_REASONS[category]
        ):
            raise ModelRedteamInputError("attack catalog is not the frozen P03 coverage set")
        parsed_cases.append({**row, "attack_input": _validate_attack_input(category, row["attack_input"], p02)})
    protocol = _closed_mapping(
        fixture["review_protocol"],
        {"model_ids", "review_dimensions", "unanimous_block_required"},
        "review protocol",
    )
    if (
        protocol["model_ids"] != ["MARKET_CONSENSUS_CHAMPION", "GENERIC_RESIDUAL_CHALLENGER"]
        or protocol["review_dimensions"] != ["ATTACK_BLOCKING", "PROMOTION_BOUNDARY", "CLAIM_BOUNDARY"]
        or protocol["unanimous_block_required"] is not True
    ):
        raise ModelRedteamInputError("cross-model review protocol has drifted")
    return {"fixture": fixture, "parameters": parameters, "risks": risks, "p02": p02, "cases": parsed_cases}


def load_fixture(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> Mapping[str, Any]:
    root = root.resolve()
    return validate_fixture(root, strict_json_load(root / fixture_path))


def _attack_result(case: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    category = case["category"]
    payload = case["attack_input"]
    if category == "FUTURE_LEAKAGE":
        detected = _timestamp(payload["feature_available_at"], "feature_available_at") > _timestamp(payload["decision_at"], "decision_at")
        detail: Mapping[str, Any] = {"future_rows": 1 if detected else 0, "tolerance": parameters["market_model"]["future_leakage_tolerance"]}
    elif category == "OUTLIER_PRICE":
        score = abs(_decimal(payload["observed_odds"], "observed_odds") - _decimal(payload["median_odds"], "median_odds")) / _decimal(payload["mad"], "mad")
        limit = _decimal(parameters["coverage_and_freshness"]["outlier_mad_multiplier"], "outlier_mad_multiplier")
        detected = score > limit
        detail = {"mad_score": format(score, "f"), "mad_multiplier_limit": format(limit, "f")}
    elif category == "IDENTITY_MISMATCH":
        confidence = _decimal(payload["identity_confidence"], "identity_confidence")
        minimum = _decimal(parameters["coverage_and_freshness"]["identity_confidence_min"], "identity_confidence_min")
        detected = payload["expected_identity"] != payload["observed_identity"] or confidence < minimum
        detail = {"identity_equal": payload["expected_identity"] == payload["observed_identity"], "confidence": format(confidence, "f"), "minimum": format(minimum, "f")}
    elif category == "DATA_POISONING":
        detected = payload["expected_source_sha256"] != payload["observed_source_sha256"]
        detail = {"source_hash_matches": not detected}
    elif category == "CORRELATION_EXPOSURE":
        exposure = _decimal(payload["proposed_cluster_exposure"], "proposed_cluster_exposure")
        cap = _decimal(parameters["risk"]["correlation_cluster_cap"], "correlation_cluster_cap")
        detected = exposure > cap
        detail = {"proposed_cluster_exposure": format(exposure, "f"), "cluster_cap": format(cap, "f")}
    elif category == "TARGET_CHASING":
        claimed = _decimal(payload["claimed_monthly_return"], "claimed_monthly_return")
        target = _decimal(parameters["target_30pct"]["monthly_return"], "monthly_return")
        detected = payload["requested_gate_relaxation"] is True and parameters["risk"]["target_shortfall_may_relax_gate"] is False and claimed == target
        detail = {"requested_gate_relaxation": payload["requested_gate_relaxation"], "target_shortfall_may_relax_gate": parameters["risk"]["target_shortfall_may_relax_gate"], "monthly_return": format(claimed, "f")}
    else:
        raise ModelRedteamInputError("unknown attack category")
    outcome = "BLOCKED" if detected else "BYPASSED"
    return {
        "attack_id": case["attack_id"],
        "category": category,
        "expected_outcome": case["expected_outcome"],
        "observed_outcome": outcome,
        "attack_blocked": detected,
        "reason_code": ATTACK_REASONS[category] if detected else "ATTACK_BYPASSED_BLOCKING_DEFECT",
        "safe_action": "NO_RECOMMENDATION_NO_ORDER",
        "detail": detail,
    }


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    state = validate_fixture(root, fixture)
    raw = state["fixture"]
    parameters = state["parameters"]
    p02 = state["p02"]
    results = [_attack_result(case, parameters) for case in state["cases"]]
    all_blocked = all(result["attack_blocked"] is True and result["observed_outcome"] == "BLOCKED" for result in results)
    redteam = {
        "schema_version": "1.0.0",
        "artifact_id": REDTEAM_ARTIFACT_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "attack_scope": "FROZEN_SYNTHETIC_ADVERSARIAL_INPUTS_NOT_EMPIRICAL_OR_LIVE",
        "required_attack_categories": list(ATTACK_CATEGORIES),
        "attack_results": results,
        "summary": {
            "attack_count": len(results),
            "blocked_count": sum(result["attack_blocked"] is True for result in results),
            "bypass_count": sum(result["attack_blocked"] is not True for result in results),
            "all_attack_paths_blocked": all_blocked,
            "any_bypass_is_blocking_defect": True,
        },
        "p02_predecessor": raw["p02_evidence"],
        "source_hashes": {
            **p02["hashes"],
            PARAMETERS_PATH.as_posix(): sha256_file(root / PARAMETERS_PATH),
            RISK_REGISTER_PATH.as_posix(): sha256_file(root / RISK_REGISTER_PATH),
            STRATEGY_SPEC_PATH.as_posix(): sha256_file(root / STRATEGY_SPEC_PATH),
        },
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    registry = p02["registry"]
    champion = registry["champion"]
    candidate = next(item for item in registry["challengers"] if item["model_id"] == "GENERIC_RESIDUAL_CHALLENGER")
    reviewed_models = [
        {
            "model_id": champion["model_id"],
            "role": champion["role"],
            "p01_active_weight": champion["active_weight"],
            "p02_evaluation_candidate": False,
            "review_verdict": "BLOCK_PROMOTION_PENDING_S16_P04",
        },
        {
            "model_id": candidate["model_id"],
            "role": candidate["role"],
            "p01_active_weight": candidate["active_weight"],
            "p02_evaluation_candidate": True,
            "review_verdict": "BLOCK_PROMOTION_PENDING_S16_P04",
        },
    ]
    agreement = all(row["review_verdict"] == "BLOCK_PROMOTION_PENDING_S16_P04" for row in reviewed_models)
    review = {
        "schema_version": "1.0.0",
        "artifact_id": REVIEW_ARTIFACT_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "review_scope": "FROZEN_CONTROL_REVIEW_NOT_MODEL_INFERENCE_OR_MARKET_EVALUATION",
        "review_protocol": raw["review_protocol"],
        "reviewed_models": reviewed_models,
        "redteam_artifact_sha256": hashlib.sha256(canonical_json_bytes(redteam)).hexdigest(),
        "review_consensus": {
            "all_required_attacks_blocked": all_blocked,
            "all_model_views_agree": agreement,
            "model_promotion_allowed": False,
            "activation_status": "NOT_ACTIVATED_PENDING_S16_P04",
            "next_required_gate": "AC-S16-P04",
            "decision": raw["expected_decision"] if all_blocked and agreement else "S16_P03_BLOCKING_DEFECT_DETECTED",
        },
        "p02_promotion_before_review": p02["report"]["model_promotion"],
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    return {MODEL_REDTEAM_PATH.as_posix(): redteam, CROSS_MODEL_REVIEW_PATH.as_posix(): review}


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected = build_artifacts(root, fixture)
    for relative, value in expected.items():
        if strict_json_load(root / relative) != value:
            raise ModelRedteamInputError("artifact differs from frozen local replay: %s" % relative)
    return expected


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_artifacts(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> dict[str, Mapping[str, Any]]:
    root = root.resolve()
    fixture = strict_json_load(root / fixture_path)
    artifacts = build_artifacts(root, fixture)
    for relative, value in artifacts.items():
        _atomic_write(root / relative, canonical_json_bytes(value))
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="write deterministic S16/P03 local red-team artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    parser.add_argument("--fixture", default=FIXTURE_PATH.as_posix(), help="fixture relative to root")
    args = parser.parse_args()
    artifacts = write_artifacts(Path(args.root), args.fixture)
    print(json.dumps({"status": "PASS", "artifacts": sorted(artifacts)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
