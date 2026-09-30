"""分支 2：商业机会（stock-commercial-opportunities）。严格按
Stock_Skill/stock-commercial-opportunities-skill/task-pack/skill_draft/stock-commercial-opportunities/references/scoring-and-maturity.md：

- base_score（10 个维度、权重和 100，每个 0–10）、risk_deduction（8 项、最大 40）、evidence_confidence（7 项、权重和 100）、
  evidence_maturity（E0–E5 离散门禁）；
- decision_score = clamp(base_score − risk_deduction − 0.15 × (100 − confidence), 0, 100)，是研究优先级，不是预期收益；
- 状态：REJECT / SCREEN_FLAG / WATCHLIST / DILIGENCE_NEXT / ADVANCE_RESEARCH；硬门：无敞口归因不高于 SCREEN_FLAG，
  无 E4 不得 ADVANCE_RESEARCH，任何状态都不是买卖建议。

取数（拿不到记 NO_EVIDENCE，不填中值也不记 0 分；每条有数的评分都带 SEC 原文链接）：
- 敞口：XBRL 分部（segment 维度）在免费 companyfacts 里拿不到，按 Owner 的口径退到「TTM 营收同比 + RPO（剩余履约义务）」；
- 财务捕获：RPO 同比（订单/积压代理）、营收同比、毛利率变化、经营现金流率；
- 估值：市值/营收、市值/毛利，与自身历史分位和同业（同 SIC 两位码）分位；
- 催化剂：下一份 10-Q/10-K 预计申报日（按过去申报节奏推算，标 ESTIMATED，因此不算「已确认催化剂」，E 级最高到 E3，
  ADVANCE_RESEARCH 不可达）。

与 Skill 参考实现的有意差异（收据里显式标出）：
1. 未观察到的维度不记 0 分：base 只对有证据的维度按权重归一，并报告覆盖率；覆盖率低于下限或缺必备维度，
   该分支不给 DILIGENCE_NEXT 以上（按 Skill「缺口一律取更低」）；
2. 未观察到的风险项扣 0 分，但会拉低 claim_coverage 从而降低置信度（Skill：未知且关键时提高风险或降低 confidence）。
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..evidence.factstore import FactStore
from .param_floors import enforce_not_looser, floors_from_defaults
from .fundamentals import CHINA_HK_CODES, US_STATE_CODES, Fundamentals, MarketInput, PeerContext, compute_fundamentals
from .scoring_support import (NO_EVIDENCE, EvidenceRef, FactorResult, ParamsError, Receipt, _check_weights,
                              check_shape, check_table, check_unit_interval, clamp, dedupe_refs, load_params,
                              no_evidence, table_rating)

SKILL_ID = "stock-commercial-opportunities-skill"
DEFAULT_PARAMS_PATH = (Path(__file__).resolve().parents[3] / "Stock_Skill" / SKILL_ID / "runtime" / "params.json")

BASE_DIMENSIONS = ("commercial_value_pool", "issuer_exposure_attribution", "financial_capture_path",
                   "beneficiary_position", "expectations_variant", "valuation_support", "catalyst_revision_path",
                   "durability_balance_sheet", "liquidity_instrument_fit", "research_edge_speed")
RISK_FACTORS = ("exposure_gap", "expectations_priced_in", "valuation_downside", "earnings_cyclicality",
                "balance_sheet_funding", "regulatory_geopolitical", "liquidity_shortability", "freshness_source_gap")
CONFIDENCE_FACTORS = ("claim_coverage", "primary_source_quality", "exposure_directness", "metric_period_normalization",
                      "source_diversity", "recency", "contradiction_resolution")
MATURITY_LABELS = {"E0": "Theme", "E1": "Desk-screened", "E2": "Exposure-attributed", "E3": "Commercial-capture",
                   "E4": "Equity-setup", "E5": "Thesis-ready"}
MATURITY_RANK = {code: rank for rank, code in enumerate(MATURITY_LABELS)}
STATUS_TO_VERDICT = {"ADVANCE_RESEARCH": "PASS", "DILIGENCE_NEXT": "PASS", "WATCHLIST": "ABSTAIN",
                     "SCREEN_FLAG": "ABSTAIN", "REJECT": "FAILED"}

DEFAULT_PARAMS: Dict[str, Any] = {
    "schema": "signal-lattice-branch-params/1",
    "skill": SKILL_ID,
    "params_version": "3.0.0",
    "source": "Stock_Skill/stock-commercial-opportunities-skill/task-pack/skill_draft/stock-commercial-opportunities/references/scoring-and-maturity.md",
    "base_weights": {"commercial_value_pool": 12, "issuer_exposure_attribution": 16, "financial_capture_path": 12,
                     "beneficiary_position": 10, "expectations_variant": 12, "valuation_support": 10,
                     "catalyst_revision_path": 10, "durability_balance_sheet": 7, "liquidity_instrument_fit": 5,
                     "research_edge_speed": 6},
    "risk_max_deductions": {"exposure_gap": 8, "expectations_priced_in": 7, "valuation_downside": 6,
                            "earnings_cyclicality": 5, "balance_sheet_funding": 4, "regulatory_geopolitical": 4,
                            "liquidity_shortability": 3, "freshness_source_gap": 3},
    "confidence_weights": {"claim_coverage": 20, "primary_source_quality": 20, "exposure_directness": 20,
                           "metric_period_normalization": 15, "source_diversity": 10, "recency": 10,
                           "contradiction_resolution": 5},
    # scoring-and-maturity.md §1、§7 原样
    "decision": {"uncertainty_coefficient": 0.15, "reject_below": 40, "screen_flag_below": 55, "watchlist_below": 65,
                 "diligence_min_confidence": 55, "advance_min_score": 75, "advance_min_confidence": 65},
    "coverage": {"base_min_coverage": 0.60,
                 "required_dimensions": ["issuer_exposure_attribution", "financial_capture_path"]},
    "exposure": {"revenue_only_rating": 4, "revenue_plus_rpo_rating": 5, "rpo_months_bonus_min": 12,
                 "rpo_months_bonus": 1, "max_rating": 6, "gap_reference_rating": 6},
    "catalyst": {"rpo_bonus": 1, "max_rating": 6},
    "research_edge": {"base_rating": 3, "near_report_days": 60, "near_report_bonus": 2, "core_metrics_bonus": 3,
                      "max_rating": 8},
    "durability": {"profitable_rating_if_net_cash_unknown": 5, "debt_assumed_zero_cap_rating": 6},
    "cyclicality": {"min_annual_points": 3, "deep_drawdown": -0.30, "deep_drawdown_bonus": 2},
    "priced_in": {"expensive_percentile": 0.85, "expensive_bonus": 1},
    "valuation_downside": {"loss_op_margin": -0.20, "loss_bonus": 2},
    "funding": {"dilution_threshold": 0.08, "dilution_bonus": 2, "debt_assumed_zero_min_risk": 2},
    "geography": {"us_risk": 1, "foreign_risk": 5, "china_hk_risk": 8},
    "liquidity_risk": {"low_price": 5.0, "low_price_bonus": 1},
    "freshness_risk": {"sina_mismatch_bonus": 2},
    "peers": {"min_group": 8},
    # RPO 要覆盖至少这么多个月的 TTM 营收才算订单/积压证据；基数微小的 RPO 同比是噪声
    "rpo": {"min_months_as_evidence": 1.0},
    "confidence": {
        "primary_source_quality_with_primary": 8, "primary_source_quality_without": 2,
        "exposure_directness_revenue_and_rpo": 6, "exposure_directness_revenue_only": 4,
        "metric_period_normalization_ttm_with_prior": 8, "metric_period_normalization_single": 5,
        "source_families_score_per_family": 2.5, "recency_days": [[120, 9], [180, 7], [270, 5], [400, 3]],
        "recency_floor": 1, "contradiction_clean": 6, "contradiction_tripped": 2,
        "restatement_threshold": 0.05,
    },
    "sensitivity": {"exposure_delta": -2, "priced_in_risk_delta": 2, "confidence_delta": -20},
    "tables": {
        "value_pool_peer_median_yoy": {"direction": "higher", "cuts": [[0.25, 8], [0.15, 7], [0.08, 6], [0.03, 5], [0.0, 4], [-0.05, 3]], "floor": 1},
        "capture_revenue_yoy": {"direction": "higher", "cuts": [[0.40, 9], [0.20, 7], [0.10, 6], [0.0, 4], [-0.10, 2]], "floor": 0},
        "capture_rpo_yoy": {"direction": "higher", "cuts": [[0.6, 9], [0.3, 8], [0.1, 6], [0.0, 4], [-0.1, 2]], "floor": 0},
        "capture_gm_change_bps": {"direction": "higher", "cuts": [[300, 8], [100, 6], [0, 4], [-200, 2]], "floor": 0},
        "capture_ocf_margin": {"direction": "higher", "cuts": [[0.15, 8], [0.05, 6], [0.0, 4], [-0.10, 2]], "floor": 0},
        "position_gm_percentile": {"direction": "higher", "cuts": [[0.8, 8], [0.6, 7], [0.4, 5], [0.2, 3]], "floor": 1},
        "position_relative_growth": {"direction": "higher", "cuts": [[0.20, 8], [0.08, 7], [0.0, 5], [-0.10, 3]], "floor": 1},
        "valuation_support_percentile": {"direction": "lower", "cuts": [[0.2, 9], [0.35, 7], [0.5, 6], [0.65, 4], [0.8, 3]], "floor": 1},
        "catalyst_days_to_report": {"direction": "lower", "cuts": [[45, 5], [90, 4], [135, 2]], "floor": 0},
        "durability_net_cash_to_cap": {"direction": "higher", "cuts": [[0.15, 9], [0.05, 7], [-0.05, 5], [-0.20, 3], [-0.40, 1]], "floor": 0},
        "durability_runway_months": {"direction": "higher", "cuts": [[36, 6], [24, 4], [12, 2]], "floor": 0},
        "liquidity_fit_dollar_volume": {"direction": "higher", "cuts": [[30000000, 9], [15000000, 8], [8000000, 7], [4500000, 5], [3000000, 4]], "floor": 0},
        "risk_priced_in_ret_252d": {"direction": "higher", "cuts": [[1.5, 9], [0.8, 7], [0.4, 5], [0.15, 3]], "floor": 1},
        "risk_valuation_percentile": {"direction": "higher", "cuts": [[0.85, 8], [0.7, 6], [0.5, 4], [0.3, 2]], "floor": 1},
        "risk_cyclicality_growth_std": {"direction": "higher", "cuts": [[0.40, 8], [0.25, 6], [0.15, 4], [0.08, 2]], "floor": 1},
        "risk_funding_runway_months": {"direction": "lower", "cuts": [[6, 9], [12, 7], [24, 4], [36, 2]], "floor": 1},
        "risk_funding_debt_to_ocf": {"direction": "higher", "cuts": [[6, 6], [3, 4]], "floor": 1},
        "risk_liquidity_dollar_volume": {"direction": "lower", "cuts": [[4500000, 6], [8000000, 4], [15000000, 2]], "floor": 1},
        "risk_freshness_age_days": {"direction": "higher", "cuts": [[270, 6], [180, 3]], "floor": 1},
    },
}

FACTOR_SOURCES: Dict[str, str] = {
    "commercial_value_pool": "PROXY：同业（同 SIC 两位码，组太小退全池）TTM 营收同比的中位数，反映利润池是否在扩张，最高 8",
    "issuer_exposure_attribution": "XBRL segment 拿不到 → 退到 TTM 营收 + RPO：有营收 4，营收+RPO 5，RPO 覆盖 ≥12 个月再 +1，最高 6",
    "financial_capture_path": "RPO 同比、营收同比、毛利率同比变化、经营现金流率（≥2 项）取平均",
    "beneficiary_position": "毛利率在同业中的分位与营收增速相对同业中位数的差（份额代理）取平均",
    "expectations_variant": "NO_EVIDENCE：需要一致预期与「已计入什么」的第一手数据",
    "valuation_support": "市值/营收、市值/毛利 的自身历史分位与同业分位的平均（越低越好）",
    "catalyst_revision_path": "ESTIMATED：按过去申报节奏推算下一份 10-Q/10-K 申报日；有 RPO 再 +1，最高 6",
    "durability_balance_sheet": "经营现金流为负：现金跑道；否则净现金/市值",
    "liquidity_instrument_fit": "20 日成交额中位数（美元）",
    "research_edge_speed": "PROXY：核心指标齐全 + 下次申报临近，最高 8",
}


# 远端参数只许收紧：发布/证据门槛不得低于仓库默认（阈值越高越严）。
FLOOR_RULES = {"decision.reject_below": "min", "decision.screen_flag_below": "min", "decision.watchlist_below": "min",
               "decision.diligence_min_confidence": "min", "decision.advance_min_score": "min", "decision.advance_min_confidence": "min",
               "decision.uncertainty_coefficient": "min", "coverage.base_min_coverage": "min"}


def validate_params(params: Any) -> None:
    check_shape(DEFAULT_PARAMS, params, "params")
    _check_weights(params["base_weights"], "base_weights", 100.0, BASE_DIMENSIONS)
    _check_weights(params["risk_max_deductions"], "risk_max_deductions", 40.0, RISK_FACTORS)
    _check_weights(params["confidence_weights"], "confidence_weights", 100.0, CONFIDENCE_FACTORS)
    d = params["decision"]
    if not (0 <= d["reject_below"] <= d["screen_flag_below"] <= d["watchlist_below"] <= d["advance_min_score"] <= 100):
        raise ParamsError("decision 阈值必须 reject<=screen<=watchlist<=advance")
    if not 0 <= d["uncertainty_coefficient"] <= 1:
        raise ParamsError("decision.uncertainty_coefficient 必须在 [0,1]")
    check_unit_interval(params["coverage"]["base_min_coverage"], "coverage.base_min_coverage")
    if set(params["coverage"]["required_dimensions"]) - set(BASE_DIMENSIONS):
        raise ParamsError("coverage.required_dimensions 含未知维度")
    for name, table in params["tables"].items():
        check_table(table, "tables." + name)
    enforce_not_looser(params, floors_from_defaults(DEFAULT_PARAMS, FLOOR_RULES), ParamsError, SKILL_ID)


def load_commercial_params(path: Optional[Path] = DEFAULT_PARAMS_PATH) -> Tuple[dict, List[dict]]:
    return load_params(DEFAULT_PARAMS, validate_params, path)


def write_default_params(path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(DEFAULT_PARAMS, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _fmt(value: Optional[float], pct: bool = False) -> str:
    if value is None:
        return "n/a"
    return ("%.1f%%" % (value * 100.0)) if pct else ("%.2f" % value)


# ---- 维度（0-10）-----------------------------------------------------------------------
def rpo_is_material(f: Fundamentals, p: dict) -> bool:
    return f.rpo.ok and f.rpo_months.ok and f.rpo_months.value >= p["rpo"]["min_months_as_evidence"]


def base_factors(f: Fundamentals, peers: Optional[PeerContext], p: dict) -> Dict[str, FactorResult]:
    T = p["tables"]
    out: Dict[str, FactorResult] = {}
    rpo_ok = rpo_is_material(f, p)

    med, group, n = (None, "n/a", 0)
    if peers is not None:
        med, group, n = peers.median(f, "revenue_yoy")
    if med is not None:
        out["commercial_value_pool"] = FactorResult(
            "commercial_value_pool", table_rating(med, T["value_pool_peer_median_yoy"]),
            "PROXY 同业(%s,n=%d) TTM 营收同比中位数 %s" % (group, n, _fmt(med, True)),
            f.revenue_yoy.refs, "PROXY", med)
    else:
        out["commercial_value_pool"] = no_evidence("commercial_value_pool", "同业样本不足或本公司拿不到营收同比")

    ex = p["exposure"]
    if f.revenue_ttm.ok and f.revenue_ttm.value > 0:
        rating = ex["revenue_plus_rpo_rating"] if rpo_ok else ex["revenue_only_rating"]
        why = "REVENUE_LEVEL_ONLY（segment 拿不到）：TTM 营收 %.0f" % f.revenue_ttm.value + ("，有实质 RPO" if rpo_ok else "")
        if rpo_ok and f.rpo_months.value >= ex["rpo_months_bonus_min"]:
            rating += ex["rpo_months_bonus"]
            why += "，RPO 覆盖 %.1f 个月营收" % f.rpo_months.value
        rating = min(rating, ex["max_rating"])
        out["issuer_exposure_attribution"] = FactorResult("issuer_exposure_attribution", rating, why,
                                                          dedupe_refs(f.revenue_ttm.refs + f.rpo.refs), "OBSERVED",
                                                          f.revenue_ttm.value)
    else:
        out["issuer_exposure_attribution"] = no_evidence("issuer_exposure_attribution", "没有 TTM 营收，无法归因敞口")

    parts: List[Tuple[float, str, Any]] = []
    if f.rpo_yoy.ok and rpo_ok:
        parts.append((table_rating(f.rpo_yoy.value, T["capture_rpo_yoy"]), "RPO 同比 %s" % _fmt(f.rpo_yoy.value, True), f.rpo_yoy))
    if f.revenue_yoy.ok:
        parts.append((table_rating(f.revenue_yoy.value, T["capture_revenue_yoy"]), "营收同比 %s" % _fmt(f.revenue_yoy.value, True), f.revenue_yoy))
    if f.gm_change_bps.ok:
        parts.append((table_rating(f.gm_change_bps.value, T["capture_gm_change_bps"]), "毛利率变化 %+.0fbp" % f.gm_change_bps.value, f.gm_change_bps))
    if f.ocf_margin.ok:
        parts.append((table_rating(f.ocf_margin.value, T["capture_ocf_margin"]), "经营现金流率 %s" % _fmt(f.ocf_margin.value, True), f.ocf_margin))
    if len(parts) >= 2:
        out["financial_capture_path"] = FactorResult(
            "financial_capture_path", sum(x[0] for x in parts) / len(parts), "；".join(x[1] for x in parts) + "（取平均）",
            dedupe_refs(tuple(r for x in parts for r in x[2].refs)), "OBSERVED", None)
    else:
        out["financial_capture_path"] = no_evidence("financial_capture_path", "可用的捕获指标不足 2 项")

    pieces: List[Tuple[float, str, Any]] = []
    if peers is not None:
        pct, grp, n = peers.percentile(f, "gross_margin")
        if pct is not None:
            pieces.append((table_rating(pct, T["position_gm_percentile"]), "毛利率同业(%s,n=%d)分位 %s" % (grp, n, _fmt(pct, True)), f.gross_margin))
        med, grp, n = peers.median(f, "revenue_yoy")
        if med is not None and f.revenue_yoy.ok:
            gap = f.revenue_yoy.value - med
            pieces.append((table_rating(gap, T["position_relative_growth"]), "营收增速较同业中位数 %+.1f 个百分点" % (gap * 100), f.revenue_yoy))
    if pieces:
        out["beneficiary_position"] = FactorResult("beneficiary_position", sum(x[0] for x in pieces) / len(pieces),
                                                   "；".join(x[1] for x in pieces), dedupe_refs(tuple(r for x in pieces for r in x[2].refs)),
                                                   "PROXY", None)
    else:
        out["beneficiary_position"] = no_evidence("beneficiary_position", "同业样本不足或缺毛利率/营收增速")
    out["expectations_variant"] = no_evidence("expectations_variant", FACTOR_SOURCES["expectations_variant"])

    pcts: List[Tuple[float, str, Any]] = []
    for metric, label in ((f.hist_cap_sales_pct, "自身历史 市值/营收 分位"), (f.hist_cap_gp_pct, "自身历史 市值/毛利 分位")):
        if metric.ok:
            pcts.append((metric.value, "%s %s" % (label, _fmt(metric.value, True)), metric))
    if peers is not None:
        for attr, label in (("cap_sales", "市值/营收"), ("cap_gp", "市值/毛利")):
            pct, grp, n = peers.percentile(f, attr)
            if pct is not None:
                pcts.append((pct, "同业(%s,n=%d) %s 分位 %s" % (grp, n, label, _fmt(pct, True)), getattr(f, attr)))
    if pcts:
        avg = sum(x[0] for x in pcts) / len(pcts)
        out["valuation_support"] = FactorResult("valuation_support", table_rating(avg, T["valuation_support_percentile"]),
                                                "；".join(x[1] for x in pcts) + "；平均分位 %s" % _fmt(avg, True),
                                                dedupe_refs(tuple(r for x in pcts for r in x[2].refs)), "OBSERVED", avg)
    else:
        out["valuation_support"] = no_evidence("valuation_support", "缺营收或历史价格，算不出估值分位")

    est = f.next_report
    ct = p["catalyst"]
    if est is not None and est.days_until >= 0:
        rating = table_rating(est.days_until, T["catalyst_days_to_report"]) + (ct["rpo_bonus"] if rpo_ok else 0)
        out["catalyst_revision_path"] = FactorResult(
            "catalyst_revision_path", min(rating, ct["max_rating"]),
            "ESTIMATED 下次财报预计 %s（%d 天后）：%s%s" % (est.est_date, est.days_until, est.basis, "；有实质 RPO 可跟踪积压" if rpo_ok else ""),
            dedupe_refs(est.refs + (f.rpo.refs if rpo_ok else ())), "ESTIMATED", float(est.days_until))
    else:
        out["catalyst_revision_path"] = no_evidence("catalyst_revision_path", "推算不出下次申报日或推算已失效")

    dur = p["durability"]
    if f.ocf_ttm.ok and f.ocf_ttm.value < 0 and f.cash_runway_months.ok:
        out["durability_balance_sheet"] = FactorResult(
            "durability_balance_sheet", table_rating(f.cash_runway_months.value, T["durability_runway_months"]),
            "经营现金流为负，现金覆盖 %.1f 个月" % f.cash_runway_months.value, f.cash_runway_months.refs, "OBSERVED", f.cash_runway_months.value)
    elif f.net_cash_to_cap.ok and f.ocf_ttm.ok and f.ocf_ttm.value >= 0:
        rating = table_rating(f.net_cash_to_cap.value, T["durability_net_cash_to_cap"])
        basis, status = "经营现金流为正，净现金/市值 %s" % _fmt(f.net_cash_to_cap.value, True), "OBSERVED"
        if f.debt_assumed_zero:
            rating = min(rating, dur["debt_assumed_zero_cap_rating"])
            basis += "；申报里没有任何债务标签，按无债务估算，封顶 %s" % dur["debt_assumed_zero_cap_rating"]
            status = "PROXY"
        out["durability_balance_sheet"] = FactorResult("durability_balance_sheet", rating, basis,
                                                       dedupe_refs(f.net_cash_to_cap.refs + f.ocf_ttm.refs), status, f.net_cash_to_cap.value)
    elif f.ocf_ttm.ok and f.ocf_ttm.value >= 0:
        out["durability_balance_sheet"] = FactorResult("durability_balance_sheet", dur["profitable_rating_if_net_cash_unknown"],
                                                       "经营现金流为正，但拿不到债务，净现金未知", f.ocf_ttm.refs, "OBSERVED", None)
    else:
        out["durability_balance_sheet"] = no_evidence("durability_balance_sheet", "拿不到经营现金流或现金")

    m = f.market
    out["liquidity_instrument_fit"] = FactorResult(
        "liquidity_instrument_fit", table_rating(m.median_dollar_volume, T["liquidity_fit_dollar_volume"]),
        "20 日成交额中位数 %.0f 美元（普通股，无 ADR/类别股借券问题未核）" % m.median_dollar_volume,
        (m.market_ref(f.as_of),), "OBSERVED", m.median_dollar_volume)

    re = p["research_edge"]
    core = [f.revenue_ttm.ok, f.gross_profit_ttm.ok, f.ocf_ttm.ok, rpo_ok]
    rating = re["base_rating"]
    why = ["PROXY 基础 %d" % re["base_rating"]]
    if est is not None and 0 <= est.days_until <= re["near_report_days"]:
        rating += re["near_report_bonus"]; why.append("下次申报 ≤%d 天" % re["near_report_days"])
    if all(core):
        rating += re["core_metrics_bonus"]; why.append("营收/毛利/经营现金流/RPO 齐全")
    out["research_edge_speed"] = FactorResult("research_edge_speed", min(rating, re["max_rating"]), "；".join(why),
                                              dedupe_refs(f.revenue_ttm.refs[:1] + f.rpo.refs[:1]), "PROXY", None)
    return out


def risk_factors(f: Fundamentals, exposure_rating: Optional[float], p: dict) -> Dict[str, FactorResult]:
    T = p["tables"]
    out: Dict[str, FactorResult] = {}
    if exposure_rating is not None:
        ref = p["exposure"]["gap_reference_rating"]   # 无 segment 时能达到的最高归因评分；只扣「相对可得最好证据」的缺口，不重复惩罚数据口径
        out["exposure_gap"] = FactorResult("exposure_gap", max(0.0, ref - exposure_rating),
                                           "PROXY 可得最好归因评分 %s − 本公司 %.1f" % (ref, exposure_rating), (), "PROXY", None)
    else:
        out["exposure_gap"] = no_evidence("exposure_gap", "敞口未归因")

    if f.ret_252d is not None:
        rating = table_rating(f.ret_252d, T["risk_priced_in_ret_252d"])
        why = "过去 252 个交易日涨幅 %s" % _fmt(f.ret_252d, True)
        if f.hist_cap_sales_pct.ok and f.hist_cap_sales_pct.value >= p["priced_in"]["expensive_percentile"]:
            rating = min(10, rating + p["priced_in"]["expensive_bonus"]); why += "；市值/营收处自身历史高位"
        out["expectations_priced_in"] = FactorResult("expectations_priced_in", rating, "PROXY " + why, (f.market.market_ref(f.as_of),), "PROXY", f.ret_252d)
    else:
        out["expectations_priced_in"] = no_evidence("expectations_priced_in", "没有一年日线，也没有一致预期")

    pct_metric = f.hist_cap_sales_pct if f.hist_cap_sales_pct.ok else None
    if pct_metric is not None:
        rating = table_rating(pct_metric.value, T["risk_valuation_percentile"])
        why = "市值/营收自身历史分位 %s" % _fmt(pct_metric.value, True)
        if f.op_margin.ok and f.op_margin.value <= p["valuation_downside"]["loss_op_margin"]:
            rating = min(10, rating + p["valuation_downside"]["loss_bonus"]); why += "；营业利润率 %s（亏损）" % _fmt(f.op_margin.value, True)
        out["valuation_downside"] = FactorResult("valuation_downside", rating, why, pct_metric.refs, "OBSERVED", pct_metric.value)
    else:
        out["valuation_downside"] = no_evidence("valuation_downside", "没有自身历史分位")

    cy = p["cyclicality"]
    if len(f.annual_revenue_growth) >= cy["min_annual_points"]:
        sd = statistics.pstdev(f.annual_revenue_growth)
        rating = table_rating(sd, T["risk_cyclicality_growth_std"])
        why = "近 %d 个财年营收增速标准差 %.2f" % (len(f.annual_revenue_growth), sd)
        if min(f.annual_revenue_growth) <= cy["deep_drawdown"]:
            rating = min(10, rating + cy["deep_drawdown_bonus"]); why += "；出现 ≤%.0f%% 的年度营收下滑" % (cy["deep_drawdown"] * 100)
        out["earnings_cyclicality"] = FactorResult("earnings_cyclicality", rating, why, f.annual_revenue_refs, "OBSERVED", sd)
    else:
        out["earnings_cyclicality"] = no_evidence("earnings_cyclicality", "年度营收不足 %d 个增速点" % cy["min_annual_points"])

    fund = p["funding"]
    rating: Optional[float] = None
    why = ""
    refs: Tuple[EvidenceRef, ...] = ()
    if f.ocf_ttm.ok and f.ocf_ttm.value < 0 and f.cash_runway_months.ok:
        rating = table_rating(f.cash_runway_months.value, T["risk_funding_runway_months"])
        why, refs = "经营现金流为负，现金覆盖 %.1f 个月" % f.cash_runway_months.value, f.cash_runway_months.refs
    elif f.ocf_ttm.ok and f.ocf_ttm.value >= 0:
        if f.net_cash.ok and f.net_cash.value >= 0:
            rating, why, refs = 1, "经营现金流为正且净现金为正", dedupe_refs(f.ocf_ttm.refs + f.net_cash.refs)
            if f.debt_assumed_zero:
                rating = max(rating, fund["debt_assumed_zero_min_risk"])
                why += "（申报里没有任何债务标签，按无债务估算，风险不低于 %s）" % fund["debt_assumed_zero_min_risk"]
        elif f.debt.ok and f.ocf_ttm.value > 0:
            ratio = f.debt.value / f.ocf_ttm.value
            rating, why, refs = table_rating(ratio, T["risk_funding_debt_to_ocf"]), "债务/经营现金流 %.1f 年" % ratio, dedupe_refs(f.ocf_ttm.refs + f.debt.refs)
    if rating is not None:
        if f.share_change_yoy.ok and f.share_change_yoy.value >= fund["dilution_threshold"]:
            rating = min(10, rating + fund["dilution_bonus"]); why += "；股数同比 %s（稀释）" % _fmt(f.share_change_yoy.value, True)
        out["balance_sheet_funding"] = FactorResult("balance_sheet_funding", rating, why, refs, "OBSERVED", None)
    else:
        out["balance_sheet_funding"] = no_evidence("balance_sheet_funding", "拿不到现金流/债务")

    geo = p["geography"]
    state = f.market.state_of_business
    if state:
        risk = geo["us_risk"] if state in US_STATE_CODES else geo["china_hk_risk"] if state in CHINA_HK_CODES else geo["foreign_risk"]
        out["regulatory_geopolitical"] = FactorResult("regulatory_geopolitical", risk, "PROXY 登记地 %s" % state, (), "PROXY", None)
    else:
        out["regulatory_geopolitical"] = no_evidence("regulatory_geopolitical", "没有营业地址")

    lr = p["liquidity_risk"]
    risk = table_rating(f.market.median_dollar_volume, T["risk_liquidity_dollar_volume"])
    why = "20 日成交额中位数 %.0f 美元" % f.market.median_dollar_volume
    if f.market.price < lr["low_price"]:
        risk = min(10, risk + lr["low_price_bonus"]); why += "；股价低于 %.0f 美元" % lr["low_price"]
    out["liquidity_shortability"] = FactorResult("liquidity_shortability", risk, why + "（借券/做空未核）", (f.market.market_ref(f.as_of),), "OBSERVED", None)

    if f.latest_period_age_days is not None:
        risk = table_rating(f.latest_period_age_days, T["risk_freshness_age_days"])
        why = "最近报告期距 as_of %d 天" % f.latest_period_age_days
        if "SINA_CAP_MISMATCH" in f.market.flags:
            risk = min(10, risk + p["freshness_risk"]["sina_mismatch_bonus"]); why += "；SEC 与新浪市值不一致"
        out["freshness_source_gap"] = FactorResult("freshness_source_gap", risk, why, (), "OBSERVED", float(f.latest_period_age_days))
    else:
        out["freshness_source_gap"] = no_evidence("freshness_source_gap", "没有 10-K/10-Q 申报清单")
    return out


def capture_signals(f: Fundamentals, p: dict) -> List[str]:
    """E3 的「订单/积压/营收/毛利/现金流」捕获信号：必须是正向且达到量级的观察，而不是「有这个标签」。"""
    signals = []
    if f.rpo_yoy.ok and rpo_is_material(f, p) and f.rpo_yoy.value >= 0.10:
        signals.append("RPO 同比 %s" % _fmt(f.rpo_yoy.value, True))
    if f.revenue_yoy.ok and f.revenue_yoy.value >= 0.10:
        signals.append("营收同比 %s" % _fmt(f.revenue_yoy.value, True))
    if f.gm_change_bps.ok and f.gm_change_bps.value >= 100:
        signals.append("毛利率 %+.0fbp" % f.gm_change_bps.value)
    if f.ocf_margin.ok and f.ocf_margin.value >= 0.05:
        signals.append("经营现金流率 %s" % _fmt(f.ocf_margin.value, True))
    return signals


def evidence_signals(f: Fundamentals, factors: Dict[str, FactorResult], p: dict) -> Dict[str, int]:
    primary_accessions = {ref.accession for fr in factors.values() if fr.observed for ref in fr.refs
                          if ref.is_primary_link and ref.accession}
    exposure_metrics = int(f.revenue_yoy.ok) + int(rpo_is_material(f, p))     # 没有 segment，只算营收同比与有实质的 RPO
    families = 1 + 1 + int(bool(f.market.history))               # SEC、新浪报价、腾讯日线
    return {
        "public_source_families": families,
        "company_filings": len(primary_accessions),
        "quantified_exposure_metrics": exposure_metrics,
        "commercial_capture_signals": len(capture_signals(f, p)),
        "current_valuation_observations": int(f.cap_sales.ok or f.cap_gp.ok),
        "confirmed_catalysts": 0,                                # 推算的申报日不是公司确认的催化剂
        "thesis_falsifiers": 0,
        "liquidity_checks": int(f.market.median_dollar_volume > 0),
    }


def evidence_maturity(signals: Mapping[str, int]) -> str:
    """与 Skill 参考实现同一条件链：缺口一律取更低。"""
    if signals["company_filings"] >= 1 and signals["quantified_exposure_metrics"] >= 1:
        if signals["commercial_capture_signals"] >= 1:
            if signals["current_valuation_observations"] >= 1 and signals["confirmed_catalysts"] >= 1:
                if signals["thesis_falsifiers"] >= 2 and signals["liquidity_checks"] >= 1:
                    return "E5"
                return "E4"
            return "E3"
        return "E2"
    if signals["public_source_families"] >= 3:
        return "E1"
    return "E0"


def next_gate(code: str) -> str:
    return {
        "E0": "open at least 3 independent public source families and resolve identity",
        "E1": "add one company filing and one quantified exposure metric",
        "E2": "add an orders/backlog/revenue/margin/cash-flow capture signal",
        "E3": "add a company-confirmed catalyst date (earnings-date 8-K/press release); estimated dates do not count",
        "E4": "add at least 2 falsifiers plus one liquidity/instrument check",
        "E5": "route to deeper research and maintain freshness; no trade approval",
    }[code]


def decision_status(score: float, confidence: float, maturity: str, hard_stops: Sequence[str], exposure_observed: bool, d: dict) -> str:
    if hard_stops or score < d["reject_below"]:
        return "REJECT"
    if MATURITY_RANK[maturity] <= MATURITY_RANK["E1"] or score < d["screen_flag_below"] or not exposure_observed:
        return "SCREEN_FLAG"
    if score < d["watchlist_below"] or confidence < d["diligence_min_confidence"]:
        return "WATCHLIST"
    if MATURITY_RANK[maturity] >= MATURITY_RANK["E4"] and score >= d["advance_min_score"] and confidence >= d["advance_min_confidence"]:
        return "ADVANCE_RESEARCH"
    return "DILIGENCE_NEXT"


def confidence_factors(f: Fundamentals, base: Dict[str, FactorResult], risks: Dict[str, FactorResult], p: dict) -> Dict[str, float]:
    c = p["confidence"]
    weights = p["base_weights"]
    base_cov = sum(weights[k] for k, fr in base.items() if fr.observed) / sum(weights.values())
    rw = p["risk_max_deductions"]
    risk_cov = sum(rw[k] for k, fr in risks.items() if fr.observed) / sum(rw.values())
    primary_backed = any(fr.observed and any(r.is_primary_link for r in fr.refs)
                         for k, fr in base.items() if k in ("issuer_exposure_attribution", "financial_capture_path"))
    exposure_ok = base["issuer_exposure_attribution"].observed
    tripped = ((f.restatement.ok and f.restatement.value > c["restatement_threshold"]) or "SINA_CAP_MISMATCH" in f.market.flags)
    recency = c["recency_floor"]
    if f.latest_period_age_days is not None:
        for days, rating in sorted(c["recency_days"], key=lambda x: x[0]):
            if f.latest_period_age_days <= days:
                recency = rating
                break
    return {
        "claim_coverage": 10.0 * (base_cov + risk_cov) / 2.0,
        "primary_source_quality": c["primary_source_quality_with_primary"] if primary_backed else c["primary_source_quality_without"],
        "exposure_directness": (0 if not exposure_ok else
                                c["exposure_directness_revenue_and_rpo"] if rpo_is_material(f, p) else c["exposure_directness_revenue_only"]),
        "metric_period_normalization": (c["metric_period_normalization_ttm_with_prior"] if f.revenue_ttm_prior.ok
                                        else c["metric_period_normalization_single"] if f.revenue_ttm.ok else 0),
        "source_diversity": min(10.0, c["source_families_score_per_family"] * (2 + int(bool(f.market.history)))),
        "recency": float(recency),
        "contradiction_resolution": c["contradiction_tripped"] if tripped else c["contradiction_clean"],
    }


def compose(base: Dict[str, FactorResult], risks: Dict[str, FactorResult], conf: Dict[str, float], p: dict,
            maturity: str, confidence_override: Optional[float] = None) -> dict:
    weights = p["base_weights"]
    observed = [k for k in weights if base[k].observed]
    observed_weight = sum(weights[k] for k in observed)
    coverage = observed_weight / sum(weights.values())
    base_score = (sum(base[k].rating / 10.0 * weights[k] for k in observed) / observed_weight * 100.0) if observed_weight else None
    required_missing = [k for k in p["coverage"]["required_dimensions"] if not base[k].observed]
    verifiable = bool(observed) and not required_missing and coverage + 1e-9 >= p["coverage"]["base_min_coverage"]
    risk_deduction = sum(fr.rating / 10.0 * p["risk_max_deductions"][k] for k, fr in risks.items() if fr.observed)
    confidence = confidence_override if confidence_override is not None else sum(
        conf[k] / 10.0 * w for k, w in p["confidence_weights"].items())
    confidence = clamp(confidence, 0.0, 100.0)
    uncertainty = (100.0 - confidence) * p["decision"]["uncertainty_coefficient"]
    score = clamp((base_score or 0.0) - risk_deduction - uncertainty, 0.0, 100.0) if base_score is not None else None
    status = None
    if score is not None:
        status = decision_status(score, confidence, maturity, [], base["issuer_exposure_attribution"].observed, p["decision"])
        if not verifiable and STATUS_TO_VERDICT[status] == "PASS":
            status = "WATCHLIST"   # 覆盖不足：Skill「缺口一律取更低」
    return {"base_score": base_score, "coverage": coverage, "verifiable": verifiable, "required_missing": required_missing,
            "risk_deduction": risk_deduction, "evidence_confidence": confidence, "uncertainty_penalty": uncertainty,
            "decision_score": score, "status": status}


def falsifiers(f: Fundamentals) -> List[str]:
    out = ["下一份 10-Q/10-K 的 TTM 营收同比转负（当前 %s）" % _fmt(f.revenue_yoy.value, True) if f.revenue_yoy.ok
           else "下一份 10-Q/10-K 的 TTM 营收同比转负"]
    if f.rpo.ok:
        out.append("RPO 同比转负（当前 %s）" % _fmt(f.rpo_yoy.value, True) if f.rpo_yoy.ok else "RPO 环比下降")
    out.append("毛利率 TTM 较当前再降 200bp 以上")
    out.append("出现 S-3/424B/ATM 增发使股数同比 ≥8%，或 8-K 4.02（财报不可依赖）")
    return out


def score_commercial(store: FactStore, market: MarketInput, as_of: str, params: Optional[dict] = None,
                     findings: Optional[List[dict]] = None, peers: Optional[PeerContext] = None,
                     fundamentals: Optional[Fundamentals] = None) -> Receipt:
    if params is None:
        params, findings = load_commercial_params()
    if fundamentals is None:
        fundamentals = compute_fundamentals(store, market, as_of)
    elif fundamentals.as_of != as_of:
        raise ValueError("fundamentals.as_of %s != as_of %s" % (fundamentals.as_of, as_of))
    f, p = fundamentals, params

    base = base_factors(f, peers, p)
    exposure_rating = base["issuer_exposure_attribution"].rating
    risks = risk_factors(f, exposure_rating, p)
    conf = confidence_factors(f, base, risks, p)
    signals = evidence_signals(f, {**base, **risks}, p)
    signals["thesis_falsifiers"] = len(falsifiers(f))
    maturity = evidence_maturity(signals)
    result = compose(base, risks, conf, p, maturity)

    verdict = STATUS_TO_VERDICT.get(result["status"], "ABSTAIN") if result["status"] else "ABSTAIN"
    reasons: List[str] = []
    if result["status"] is None:
        reasons.append("NO_BASE_DIMENSION_OBSERVED")
    else:
        reasons.append("STATUS:%s" % result["status"])
    if not result["verifiable"]:
        if result["required_missing"]:
            reasons.append("BASE_REQUIRED_DIMENSION_NO_EVIDENCE:" + ",".join(result["required_missing"]))
        if result["coverage"] + 1e-9 < p["coverage"]["base_min_coverage"]:
            reasons.append("BASE_COVERAGE_BELOW_FLOOR:%.2f<%.2f" % (result["coverage"], p["coverage"]["base_min_coverage"]))
    if result["status"]:
        d = p["decision"]
        if result["decision_score"] < d["reject_below"]:
            reasons.append("DECISION_SCORE_BELOW_REJECT:%.1f<%s" % (result["decision_score"], d["reject_below"]))
        elif result["decision_score"] < d["screen_flag_below"]:
            reasons.append("DECISION_SCORE_BELOW_SCREEN_FLAG:%.1f<%s" % (result["decision_score"], d["screen_flag_below"]))
        elif result["decision_score"] < d["watchlist_below"]:
            reasons.append("DECISION_SCORE_BELOW_DILIGENCE:%.1f<%s" % (result["decision_score"], d["watchlist_below"]))
        if result["evidence_confidence"] < d["diligence_min_confidence"]:
            reasons.append("CONFIDENCE_BELOW_MIN:%.1f<%s" % (result["evidence_confidence"], d["diligence_min_confidence"]))
        if maturity != "E5" and MATURITY_RANK[maturity] < MATURITY_RANK["E4"]:
            reasons.append("MATURITY_%s_BELOW_E4:NO_CONFIRMED_CATALYST(ESTIMATED_ONLY)" % maturity)

    links = _primary_links(base, risks)
    if verdict == "PASS" and not links:
        verdict = "ABSTAIN"
        reasons.insert(0, "PASS_REQUIRES_PRIMARY_SEC_LINK")
    if findings:
        reasons += ["PARAMS_FINDING:" + item["code"] for item in findings]

    sens = None
    if result["status"] is not None and verdict != "FAILED":
        sens = sensitivity(base, risks, conf, p, maturity, result)

    ne = {"base": sum(not fr.observed for fr in base.values()), "base_total": len(base),
          "risk": sum(not fr.observed for fr in risks.values()), "risk_total": len(risks)}
    detail = {
        "market_cap_usd": f.market.market_cap, "price_usd": f.market.price,
        "base_score": None if result["base_score"] is None else round(result["base_score"], 2),
        "base_coverage": round(result["coverage"], 3),
        "risk_deduction": round(result["risk_deduction"], 2),
        "evidence_confidence": round(result["evidence_confidence"], 2),
        "uncertainty_penalty": round(result["uncertainty_penalty"], 2),
        "decision_score": None if result["decision_score"] is None else round(result["decision_score"], 2),
        "maturity_code": maturity, "maturity_label": MATURITY_LABELS[maturity], "next_maturity_gate": next_gate(maturity),
        "status": result["status"],
        "evidence_signals": signals,
        "base_dimensions": {k: fr.to_dict() for k, fr in base.items()},
        "risk_factors": {k: fr.to_dict() for k, fr in risks.items()},
        "confidence_components": {k: round(v, 2) for k, v in conf.items()},
        "hard_stops": [],
        "falsifiers": falsifiers(f),
        "sensitivity": sens,
        "primary_links": links,
        "no_evidence_ratio": ne,
        "rank_key": rank_key(verdict, result["decision_score"]),
        "params_version": p["params_version"], "params_findings": findings or [],
    }
    return Receipt(f.symbol, f.cik, f.name, as_of, verdict, result["status"] or "NO_STATUS", reasons, detail)


def sensitivity(base: Dict[str, FactorResult], risks: Dict[str, FactorResult], conf: Dict[str, float], p: dict,
                maturity: str, baseline: dict) -> dict:
    """Skill §9：敞口 −2、预期已计入风险 +2、置信度 −20，看状态是否翻转。"""
    s = p["sensitivity"]
    out = {"baseline": baseline["status"]}
    exp = base["issuer_exposure_attribution"]
    if exp.observed:
        shifted = dict(base)
        shifted["issuer_exposure_attribution"] = FactorResult(exp.name, max(0.0, exp.rating + s["exposure_delta"]), exp.basis, exp.refs, exp.status)
        r = compose(shifted, risks, conf, p, maturity)
        out["exposure_minus_2"] = {"status": r["status"], "decision_score": None if r["decision_score"] is None else round(r["decision_score"], 1)}
    pi = risks["expectations_priced_in"]
    bumped = dict(risks)
    start = pi.rating if pi.observed else 5.0
    bumped["expectations_priced_in"] = FactorResult(pi.name, min(10.0, start + s["priced_in_risk_delta"]), "sensitivity", (), "PROXY")
    r = compose(base, bumped, conf, p, maturity)
    out["priced_in_risk_plus_2"] = {"status": r["status"], "decision_score": None if r["decision_score"] is None else round(r["decision_score"], 1)}
    r = compose(base, risks, conf, p, maturity, confidence_override=baseline["evidence_confidence"] + s["confidence_delta"])
    out["confidence_minus_20"] = {"status": r["status"], "decision_score": None if r["decision_score"] is None else round(r["decision_score"], 1)}
    out["flips"] = [k for k, v in out.items() if isinstance(v, dict) and v["status"] != baseline["status"]]
    return out


def _primary_links(base: Dict[str, FactorResult], risks: Dict[str, FactorResult], limit: int = 8) -> List[dict]:
    seen: Dict[str, dict] = {}
    priority = ("financial_capture_path", "issuer_exposure_attribution", "valuation_support", "durability_balance_sheet",
                "catalyst_revision_path")
    for name in list(priority) + [k for k in base if k not in priority]:
        fr = base[name]
        for ref in fr.refs:
            if fr.observed and ref.is_primary_link and ref.url not in seen:
                seen[ref.url] = {"url": ref.url, "accession": ref.accession, "form": ref.form, "filed": ref.filed,
                                 "period_end": ref.period_end, "supports": name, "label": ref.label}
    return list(seen.values())[:limit]


def rank_key(verdict: str, score: Optional[float]) -> float:
    tier = {"PASS": 2000.0, "ABSTAIN": 1000.0, "FAILED": 0.0}[verdict]
    return tier + (score or 0.0)
