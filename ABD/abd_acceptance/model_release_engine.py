"""Deterministic S16/P04 model-system card and independent release gate.

The module generates documentation and a control decision from frozen local
facts.  It is deliberately not a model runner, market client, account client,
or deployment mechanism.  A passing S16/P04 control proves that the software
and model gates are represented independently; it never turns a model gate
into a model pass or enables a production release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .model_eval_engine import canonical_json_bytes, sha256_file, strict_json_load
from .model_redteam_engine import (
    CLAIM_BOUNDARY as P03_CLAIM_BOUNDARY,
    CROSS_MODEL_REVIEW_PATH,
    FIXTURE_PATH as P03_FIXTURE_PATH,
    MODEL_REDTEAM_PATH,
    load_fixture as load_p03_fixture,
    validate_artifacts as validate_p03_artifacts,
)


CONTRACT_ID = "AC-S16-P04"
REQUIREMENT_ID = "REQ-S16-P04"
STAGE_ID = "S16"
PHASE_ID = "P04"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_LOCAL_GATE_CONTROL_NO_NETWORK_NO_ACCOUNT"
FIXTURE_PATH = Path("machine/tests/fixtures/S16_P04.json")
SYSTEM_CARD_PATH = Path("model_system_card.json")
RELEASE_GATE_PATH = Path("model_release_gate.json")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P03.json")
S15_P04_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-P04.json")
S15_STAGE_REVIEW_EVIDENCE_PATH = Path("machine/evidence/EVD-S15-STAGE-REVIEW.json")
CANONICAL_FACTS_PATH = Path("machine/facts/canonical_facts.json")
PARAMETERS_PATH = Path("machine/facts/parameters.json")
RISK_REGISTER_PATH = Path("machine/facts/risk_register.json")
FACT_SYSTEM_CARD_PATH = Path("machine/facts/model_system_card.json")
STRATEGY_SPEC_PATH = Path("machine/facts/strategy_spec.json")
SYSTEM_CARD_ARTIFACT_ID = "ART-S16-P04-01"
RELEASE_GATE_ARTIFACT_ID = "ART-S16-P04-02"
P03_EVIDENCE_SHA256 = "d86c3a811022a14afa76457051dcf575e91c330bd7171c052d7cf1b849b5739d"
S15_P04_EVIDENCE_SHA256 = "3fd288e66d3c473881dc92257992eb41b85422a5c0aaa92f1ff00e202a15feda"
S15_STAGE_REVIEW_EVIDENCE_SHA256 = "1422ca3d52f66d30cb39c7431d928486a0b5d3d0750d45327b7896d03695b9c7"
_SHA256 = re.compile(r"[0-9a-f]{64}")

CLAIM_BOUNDARY = {
    **P03_CLAIM_BOUNDARY,
    "model_system_card_is_not_model_activation": True,
    "software_gate_is_not_model_gate": True,
    "model_gate_is_not_deployment_authorization": True,
    "model_activation_enabled": False,
}


class ModelReleaseInputError(ValueError):
    """Raised when the frozen S16/P04 source surface is incomplete or drifts."""


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ModelReleaseInputError("%s fields are not exact" % label)
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ModelReleaseInputError("%s must be a SHA-256 value" % label)
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelReleaseInputError("%s must be a non-empty string" % label)
    return value


def _exact_receipt(
    root: Path,
    metadata: Any,
    *,
    label: str,
    path: Path,
    sha256: str,
    contract_id: str,
    status: str,
    expected_fields: Mapping[str, Any],
) -> Mapping[str, Any]:
    row = _closed_mapping(metadata, {"evidence_path", "evidence_sha256", "contract_id", "status"}, label)
    if (
        row["evidence_path"] != path.as_posix()
        or row["evidence_sha256"] != sha256
        or row["contract_id"] != contract_id
        or row["status"] != status
        or _sha256(row["evidence_sha256"], "%s SHA" % label) != row["evidence_sha256"]
    ):
        raise ModelReleaseInputError("%s metadata is not frozen" % label)
    actual_path = root / path
    evidence = strict_json_load(actual_path)
    if not isinstance(evidence, Mapping) or sha256_file(actual_path) != sha256:
        raise ModelReleaseInputError("%s signed receipt is not reproducible" % label)
    if any(evidence.get(key) != value for key, value in expected_fields.items()):
        raise ModelReleaseInputError("%s signed receipt fields have drifted" % label)
    return evidence


def _source_surface(root: Path, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    canonical = strict_json_load(root / CANONICAL_FACTS_PATH)
    parameters = strict_json_load(root / PARAMETERS_PATH)
    risk_register = strict_json_load(root / RISK_REGISTER_PATH)
    fact_card = strict_json_load(root / FACT_SYSTEM_CARD_PATH)
    strategy = strict_json_load(root / STRATEGY_SPEC_PATH)
    risks = risk_register.get("risks") if isinstance(risk_register, Mapping) else None
    if not all(isinstance(value, Mapping) for value in (canonical, parameters, fact_card, strategy)) or not isinstance(risks, list):
        raise ModelReleaseInputError("P04 fact surface is unavailable")
    product = canonical.get("product")
    scope = canonical.get("scope")
    runtime = canonical.get("runtime")
    truth = canonical.get("truth_and_evidence")
    market = parameters.get("market_model")
    risk = parameters.get("risk")
    target = parameters.get("target_30pct")
    tiers = parameters.get("evidence_tiers")
    if not all(isinstance(value, Mapping) for value in (product, scope, runtime, truth, market, risk, target, tiers)):
        raise ModelReleaseInputError("P04 canonical controls are unavailable")
    canonical_ok = (
        product.get("id") == "ABD"
        and product.get("version") == PRODUCT_VERSION
        and product.get("initial_bankroll_aud") == "300.00"
        and product.get("incremental_cash_budget_aud") == "0.00"
        and product.get("monthly_target_return") == "0.30"
        and scope.get("product_role") == "ANALYSIS_AND_ADVICE_ONLY"
        and scope.get("order_submission_module_present") is False
        and scope.get("normal_owner_action") == "FINAL_ORDER_ONLY"
        and scope.get("paid_data_api_required") is False
        and runtime.get("single_host_zero_downtime_guaranteed") is False
        and truth.get("actual_return_requires_verified_execution_evidence") is True
        and truth.get("advice_ledger_separate_from_actual_ledger") is True
        and truth.get("no_bet_is_first_class_output") is True
    )
    parameter_ok = (
        market.get("market_prior_weight_min") == "0.50"
        and market.get("residual_weight_alpha_beta_max") == "0.35"
        and market.get("residual_weight_ga_max") == "0.50"
        and market.get("residual_weight_when_no_increment") == "0.00"
        and market.get("conservative_probability_percentile") == 10
        and market.get("edge_haircut_fraction") == "0.25"
        and market.get("remove_top_profit_fraction_for_robustness") == "0.01"
        and market.get("future_leakage_tolerance") == 0
        and risk.get("kelly_fraction_alpha") == "0.00"
        and risk.get("kelly_fraction_beta") == "0.20"
        and risk.get("kelly_fraction_ga") == "0.25"
        and risk.get("single_ticket_cap_beta") == "0.015"
        and risk.get("single_ticket_cap_ga") == "0.020"
        and risk.get("event_cap") == "0.050"
        and risk.get("correlation_cluster_cap") == "0.050"
        and risk.get("total_open_exposure_cap") == "0.150"
        and risk.get("target_shortfall_may_relax_gate") is False
        and risk.get("chase_loss_prohibited") is True
        and target.get("guaranteed") is False
        and target.get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and tiers.get("E3", {}).get("model_stage_min") == "BETA"
        and tiers.get("E4", {}).get("model_stage_min") == "GA"
    )
    if not canonical_ok or not parameter_ok:
        raise ModelReleaseInputError("P04 canonical or parameter controls have drifted")
    selected_risks = {row.get("id"): row for row in risks if isinstance(row, Mapping)}
    required_risks = {
        "R-001": "30%月复利无法由随机市场保证",
        "R-004": "赛事、盘口或结算身份错配",
        "R-005": "未来数据泄漏制造虚假优势",
        "R-006": "离群赔率制造虚假利润",
        "R-007": "万分之一或赔率跳动改变动作",
        "R-008": "邮件误删或附件未保存",
        "R-009": "恶意邮件/网页提示注入控制Agent",
        "R-010": "单VPS故障",
        "R-011": "无付费接口导致时效和覆盖不足",
        "R-012": "建议账本被误当真实资金收益",
    }
    if any(not isinstance(selected_risks.get(key), Mapping) or selected_risks[key].get("risk") != value for key, value in required_risks.items()):
        raise ModelReleaseInputError("P04 risk controls have drifted")
    p03_state = load_p03_fixture(root, P03_FIXTURE_PATH)
    validate_p03_artifacts(root, p03_state["fixture"])
    p03 = _exact_receipt(
        root,
        fixture["p03_evidence"],
        label="P03 predecessor",
        path=P03_EVIDENCE_PATH,
        sha256=P03_EVIDENCE_SHA256,
        contract_id="AC-S16-P03",
        status="PASS",
        expected_fields={
            "decision": "S16_P03_REDTEAM_AND_CROSS_MODEL_REVIEW_PASS_P04_REQUIRED",
            "next": "S16/P04_READY_NOT_STARTED",
            "release_status": "S16_P03_LOCAL_SYNTHETIC_REDTEAM_ONLY_P04_REQUIRED",
        },
    )
    software = _exact_receipt(
        root,
        fixture["software_evidence"],
        label="software gate",
        path=S15_P04_EVIDENCE_PATH,
        sha256=S15_P04_EVIDENCE_SHA256,
        contract_id="AC-S15-P04",
        status="PASS",
        expected_fields={
            "decision": "S15_P04_TRACEABILITY_GATE_PASS_STAGE_REVIEW_REQUIRED",
            "release_status": "S15_PHASES_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED",
        },
    )
    stage15 = _exact_receipt(
        root,
        fixture["software_stage_review"],
        label="S15 stage review",
        path=S15_STAGE_REVIEW_EVIDENCE_PATH,
        sha256=S15_STAGE_REVIEW_EVIDENCE_SHA256,
        contract_id="STAGE-REVIEW-S15",
        status="PASS",
        expected_fields={
            "decision": "S15_WHOLE_STAGE_REVIEW_PASS",
            "release_status": "S15_GITHUB_UPLOAD_REQUIRED_BEFORE_ANY_DEPLOYMENT",
        },
    )
    return {
        "canonical": canonical,
        "parameters": parameters,
        "risks": {key: selected_risks[key] for key in required_risks},
        "fact_card": fact_card,
        "strategy": strategy,
        "p03": p03,
        "software": software,
        "stage15": stage15,
        "hashes": {
            CANONICAL_FACTS_PATH.as_posix(): sha256_file(root / CANONICAL_FACTS_PATH),
            PARAMETERS_PATH.as_posix(): sha256_file(root / PARAMETERS_PATH),
            RISK_REGISTER_PATH.as_posix(): sha256_file(root / RISK_REGISTER_PATH),
            FACT_SYSTEM_CARD_PATH.as_posix(): sha256_file(root / FACT_SYSTEM_CARD_PATH),
            STRATEGY_SPEC_PATH.as_posix(): sha256_file(root / STRATEGY_SPEC_PATH),
            P03_FIXTURE_PATH.as_posix(): sha256_file(root / P03_FIXTURE_PATH),
            MODEL_REDTEAM_PATH.as_posix(): sha256_file(root / MODEL_REDTEAM_PATH),
            CROSS_MODEL_REVIEW_PATH.as_posix(): sha256_file(root / CROSS_MODEL_REVIEW_PATH),
            P03_EVIDENCE_PATH.as_posix(): sha256_file(root / P03_EVIDENCE_PATH),
            S15_P04_EVIDENCE_PATH.as_posix(): sha256_file(root / S15_P04_EVIDENCE_PATH),
            S15_STAGE_REVIEW_EVIDENCE_PATH.as_posix(): sha256_file(root / S15_STAGE_REVIEW_EVIDENCE_PATH),
        },
    }


def _lifecycle_profiles(parameters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    market = parameters["market_model"]
    risk = parameters["risk"]
    return [
        {
            "stage": "ALPHA",
            "configured_kelly_fraction": risk["kelly_fraction_alpha"],
            "configured_single_ticket_cap": "0.00",
            "residual_weight_cap": market["residual_weight_alpha_beta_max"],
            "current_status": "LOCAL_SYNTHETIC_CONTROL_ONLY_NOT_MODEL_ACTIVATION",
            "required_before_any_operational_transition": "independent empirical-model gate and a separately authorized release path",
        },
        {
            "stage": "BETA",
            "configured_kelly_fraction": risk["kelly_fraction_beta"],
            "configured_single_ticket_cap": risk["single_ticket_cap_beta"],
            "residual_weight_cap": market["residual_weight_alpha_beta_max"],
            "current_status": "BLOCKED_PENDING_INDEPENDENT_EMPIRICAL_MODEL_GATE",
            "required_before_any_operational_transition": "E3 evidence tier, independent empirical model increment, and a separately authorized release path",
        },
        {
            "stage": "GA",
            "configured_kelly_fraction": risk["kelly_fraction_ga"],
            "configured_single_ticket_cap": risk["single_ticket_cap_ga"],
            "residual_weight_cap": market["residual_weight_ga_max"],
            "current_status": "BLOCKED_PENDING_INDEPENDENT_EMPIRICAL_MODEL_GATE",
            "required_before_any_operational_transition": "GA-required evidence tiers, independent empirical model increment, and a separately authorized release path",
        },
    ]


def _validate_lifecycle_profiles(value: Any, parameters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    expected = _lifecycle_profiles(parameters)
    if value != expected:
        raise ModelReleaseInputError("lifecycle profiles are not exactly bound to frozen parameters")
    return expected


def _evaluate_control_case(case: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    fields = {
        "case_id",
        "software_gate_passed",
        "model_empirical_increment_verified",
        "stage_review_passed",
        "model_stage",
        "market_prior_weight",
        "residual_weight",
        "adverse_probability_delta",
        "expected_reason",
    }
    row = _closed_mapping(case, fields, "gate case")
    if not isinstance(row["case_id"], str) or not row["case_id"].startswith("S16P04-GATE-"):
        raise ModelReleaseInputError("gate case id is invalid")
    if not all(isinstance(row[key], bool) for key in ("software_gate_passed", "model_empirical_increment_verified", "stage_review_passed")):
        raise ModelReleaseInputError("gate case booleans are invalid")
    if row["model_stage"] not in {"ALPHA", "BETA", "GA"}:
        raise ModelReleaseInputError("gate case model stage is invalid")
    if row["market_prior_weight"] not in {"0.4999", "0.5000"}:
        raise ModelReleaseInputError("gate case market-prior boundary is invalid")
    if row["adverse_probability_delta"] not in {"-0.0001", "0.0000"}:
        raise ModelReleaseInputError("gate case adverse perturbation is invalid")
    cap = parameters["market_model"]["residual_weight_ga_max"] if row["model_stage"] == "GA" else parameters["market_model"]["residual_weight_alpha_beta_max"]
    allowed_weights = {"0.0000", cap, "0.3501"} if cap == "0.35" else {"0.0000", cap}
    if row["residual_weight"] not in allowed_weights:
        raise ModelReleaseInputError("gate case residual boundary is invalid")
    if row["market_prior_weight"] < parameters["market_model"]["market_prior_weight_min"]:
        reason = "MARKET_PRIOR_WEIGHT_BELOW_MIN"
    elif row["residual_weight"] > cap:
        reason = "RESIDUAL_WEIGHT_ABOVE_STAGE_CAP"
    elif not row["software_gate_passed"]:
        reason = "SOFTWARE_GATE_NOT_PASSED"
    elif not row["model_empirical_increment_verified"]:
        reason = "MODEL_GATE_NOT_PASSED"
    elif not row["stage_review_passed"]:
        reason = "STAGE_REVIEW_NOT_PASSED"
    else:
        reason = "P04_PHASE_NOT_A_DEPLOYMENT_AUTHORIZATION"
    if row["expected_reason"] != reason:
        raise ModelReleaseInputError("gate case expected reason is invalid")
    return {
        "case_id": row["case_id"],
        "model_stage": row["model_stage"],
        "software_gate_passed": row["software_gate_passed"],
        "model_empirical_increment_verified": row["model_empirical_increment_verified"],
        "stage_review_passed": row["stage_review_passed"],
        "market_prior_weight": row["market_prior_weight"],
        "residual_weight": row["residual_weight"],
        "adverse_probability_delta": row["adverse_probability_delta"],
        "release_allowed": False,
        "reason_code": reason,
        "classification": "FROZEN_LOGICAL_CONTROL_CASE_NOT_MODEL_OR_RELEASE_EVIDENCE",
    }


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
        "canonical_facts_sha256",
        "parameters_sha256",
        "p03_evidence",
        "software_evidence",
        "software_stage_review",
        "lifecycle_profiles",
        "gate_cases",
        "minimum_targeted_pytest_cases",
        "expected_decision",
        "expected_next",
        "claim_boundary",
    }
    fixture = _closed_mapping(value, fields, "S16/P04 fixture")
    exact = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S16-P04-MODEL-SYSTEM-CARD-DUAL-GATE",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "expected_decision": "S16_P04_DUAL_GATE_CONTROL_PASS_STAGE_REVIEW_REQUIRED_NOT_DEPLOYMENT",
        "expected_next": "S16/STAGE_REVIEW_READY_NOT_STARTED",
    }
    if any(fixture.get(key) != expected for key, expected in exact.items()):
        raise ModelReleaseInputError("fixture identity has drifted")
    if fixture["claim_boundary"] != CLAIM_BOUNDARY:
        raise ModelReleaseInputError("fixture claim boundary has drifted")
    if not isinstance(fixture["minimum_targeted_pytest_cases"], int) or fixture["minimum_targeted_pytest_cases"] < 1:
        raise ModelReleaseInputError("minimum targeted test count is invalid")
    if fixture["canonical_facts_sha256"] != sha256_file(root / CANONICAL_FACTS_PATH) or fixture["parameters_sha256"] != sha256_file(root / PARAMETERS_PATH):
        raise ModelReleaseInputError("fixture source hashes are not bound")
    surface = _source_surface(root, fixture)
    profiles = _validate_lifecycle_profiles(fixture["lifecycle_profiles"], surface["parameters"])
    cases = fixture["gate_cases"]
    if not isinstance(cases, list) or len(cases) != 7:
        raise ModelReleaseInputError("fixture must have the seven frozen independence cases")
    parsed = [_evaluate_control_case(case, surface["parameters"]) for case in cases]
    if [case["case_id"] for case in parsed] != ["S16P04-GATE-%02d" % number for number in range(1, 8)]:
        raise ModelReleaseInputError("gate cases are not in frozen order")
    return {"fixture": fixture, "surface": surface, "lifecycle_profiles": profiles, "gate_cases": parsed}


def load_fixture(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> Mapping[str, Any]:
    root = root.resolve()
    return validate_fixture(root, strict_json_load(root / fixture_path))


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    state = validate_fixture(root, fixture)
    raw = state["fixture"]
    surface = state["surface"]
    parameters = surface["parameters"]
    canonical = surface["canonical"]
    risk = parameters["risk"]
    market = parameters["market_model"]
    fact_card = surface["fact_card"]
    card = {
        "schema_version": "1.0.0",
        "artifact_id": SYSTEM_CARD_ARTIFACT_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "system_name": fact_card["name"],
        "purpose": "在可观察市场上提供受证据、数值、风险、安全和来源合同约束的中文分析与建议；正常路径只由用户完成最终下单。",
        "intended_use": fact_card["intended_use"],
        "prohibited_use": fact_card["prohibited_use"],
        "authority_order": fact_card["authority_order"],
        "known_limitations": [
            *fact_card["known_limitations"],
            "S16/P01-P03均为冻结本地合成控制，未验证独立经验模型增量。",
            "S16/P04的逻辑控制通过不构成模型通过、模型激活、部署或收益验证。",
        ],
        "known_failure_controls": [
            {"risk_id": key, "risk": row["risk"], "control": row["control"], "kill": row["kill"]}
            for key, row in surface["risks"].items()
        ],
        "safety_measures": [
            *fact_card["safety_measures"],
            "市场先验权重至少%s，未证实增量时残差权重为%s。" % (market["market_prior_weight_min"], market["residual_weight_when_no_increment"]),
            "禁止目标落后放宽门或追损；软件证据与模型证据不得互相替代。",
        ],
        "monitoring": fact_card["monitoring"],
        "lifecycle_profiles": state["lifecycle_profiles"],
        "configured_risk_limits": {
            "market_prior_weight_min": market["market_prior_weight_min"],
            "conservative_probability_percentile": market["conservative_probability_percentile"],
            "edge_haircut_fraction": market["edge_haircut_fraction"],
            "remove_top_profit_fraction_for_robustness": market["remove_top_profit_fraction_for_robustness"],
            "future_leakage_tolerance": market["future_leakage_tolerance"],
            "event_cap": risk["event_cap"],
            "correlation_cluster_cap": risk["correlation_cluster_cap"],
            "total_open_exposure_cap": risk["total_open_exposure_cap"],
        },
        "operational_boundary": {
            "product_role": canonical["scope"]["product_role"],
            "order_submission_module_present": canonical["scope"]["order_submission_module_present"],
            "normal_owner_action": canonical["scope"]["normal_owner_action"],
            "paid_data_api_required": canonical["scope"]["paid_data_api_required"],
            "single_host_zero_downtime_guaranteed": canonical["runtime"]["single_host_zero_downtime_guaranteed"],
            "actual_return_requires_verified_execution_evidence": canonical["truth_and_evidence"]["actual_return_requires_verified_execution_evidence"],
        },
        "rollback": {
            "feature_flag_id": "model:s16_system_card_dual_release_gate",
            "action": "关闭对应功能开关，恢复上一已签名制品，保留不可变证据并重放派生状态。",
            "automatic_model_or_order_action": False,
            "external_state_changed": False,
        },
        "source_hashes": surface["hashes"],
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    gate_cases = state["gate_cases"]
    model_gate_conditions = [
        {
            "condition_id": "MODEL-EMPIRICAL-INCREMENT",
            "passed": False,
            "reason_code": "NO_EMPIRICAL_MODEL_INCREMENT_EVIDENCE",
            "evidence_scope": "S16/P01-P03 local synthetic control only",
        },
        {
            "condition_id": "MODEL-P02-SYNTHETIC-EVALUATION",
            "passed": True,
            "reason_code": "SYNTHETIC_EVALUATION_GATES_PASS_NOT_EMPIRICAL",
            "evidence_scope": "frozen synthetic evaluation only",
        },
        {
            "condition_id": "MODEL-P03-REDTEAM",
            "passed": True,
            "reason_code": "FROZEN_REDTEAM_PATHS_BLOCKED_NOT_MODEL_INFERENCE",
            "evidence_scope": "frozen local red-team only",
        },
    ]
    gate = {
        "schema_version": "1.0.0",
        "artifact_id": RELEASE_GATE_ARTIFACT_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "software_gate": {
            "status": "PASS_LOCAL_SOFTWARE_EVIDENCE_ONLY",
            "passed": True,
            "receipt": raw["software_evidence"],
            "stage_review_receipt": raw["software_stage_review"],
            "limitation": "软件控制证据不构成模型经验增量、模型激活或生产部署许可。",
        },
        "model_gate": {
            "status": "BLOCKED_NO_EMPIRICAL_MODEL_INCREMENT",
            "passed": False,
            "conditions": model_gate_conditions,
            "p03_predecessor": raw["p03_evidence"],
            "activation_allowed": False,
        },
        "gate_independence": {
            "software_pass_can_replace_model_pass": False,
            "model_pass_can_replace_software_pass": False,
            "both_gates_required_before_any_future_release_review": True,
            "p04_control_pass_is_not_model_pass": True,
            "p04_control_pass_is_not_deployment_authorization": True,
        },
        "lifecycle_release_status": state["lifecycle_profiles"],
        "frozen_control_cases": gate_cases,
        "summary": {
            "case_count": len(gate_cases),
            "all_cases_release_blocked": all(case["release_allowed"] is False for case in gate_cases),
            "software_gate_passed": True,
            "model_gate_passed": False,
            "model_activation_allowed": False,
            "deployment_allowed": False,
            "stage_review_required": True,
        },
        "decision": raw["expected_decision"],
        "next": raw["expected_next"],
        "rollback": {
            "feature_flag_id": "model:s16_system_card_dual_release_gate",
            "action": "关闭对应功能开关，恢复上一已签名制品，保留不可变证据并重放派生状态。",
            "release_state_after_rollback": "NOT_DEPLOYED_OR_ACTIVATED",
            "model_activation_enabled": False,
            "order_submission_enabled": False,
        },
        "source_hashes": surface["hashes"],
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    return {SYSTEM_CARD_PATH.as_posix(): card, RELEASE_GATE_PATH.as_posix(): gate}


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected = build_artifacts(root, fixture)
    for relative, value in expected.items():
        if strict_json_load(root / relative) != value:
            raise ModelReleaseInputError("artifact differs from frozen local replay: %s" % relative)
    return expected


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_artifacts(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> dict[str, Mapping[str, Any]]:
    root = root.resolve()
    artifacts = build_artifacts(root, strict_json_load(root / fixture_path))
    for relative, value in artifacts.items():
        _atomic_write(root / relative, canonical_json_bytes(value))
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="write deterministic S16/P04 model-system card and release gate")
    parser.add_argument("--root", default=".", help="ABD project root")
    parser.add_argument("--fixture", default=FIXTURE_PATH.as_posix(), help="fixture relative to root")
    args = parser.parse_args()
    artifacts = write_artifacts(Path(args.root), args.fixture)
    print(json.dumps({"status": "PASS", "artifacts": sorted(artifacts)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
