"""分支 1：瓶颈（bottleneck-serenity）。严格按
Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill/references/scoring_model.md：

- 五个维度（结构性约束 / 股东租金捕获 / 错误定价与时机 / 证据质量 / 可投资性），各因子 0–5，按权重折成 0–100；
- 核心质量 = 五个维度的几何平均；
- 四道不可互补的门：A 约束真实（结构性 ≥60）、B 稀缺持续（可变现跑道）、C 股东捕获（≥55）、D 错误定价（≥45）；
  另有不可互补的阻断项：证据 ≥60、可投资性 ≥50、无一手证据、营收桥缺失、融资缺口；
- 持续期乘数（跑道 = 稀缺期 P50 − 变现滞后）；
- 最终分 = clamp(核心质量 × 持续期乘数 × 情景不对称乘数, 0, 100)，且始终服从门。

因子取数（每个有数的因子都带 SEC 原文链接；拿不到记 NO_EVIDENCE，不填中值也不记 0 分）：
见 FACTOR_SOURCES。原文关键词只作证据标记，不进入「股东租金捕获」「错误定价」两个与收益相关的维度。

与 Skill 参考实现的有意差异（都在收据里显式标出，不悄悄发生）：
1. 未观察到的因子不计 0 分，维度分只对有证据的因子归一，并报告覆盖率；覆盖率低于下限或缺必备因子的维度「不可核实」，对应的门不能算通过；
2. 情景不对称乘数需要人给的 bear/base/bull 情景，运行期零 Agent 拿不到，记 NO_EVIDENCE、乘数取 1.0，
   因此 RESEARCH_PRIORITY（要求正的情景不对称）不可达，最高只到 CANDIDATE；
3. 稀缺期 P50 无法从申报得到：有 RPO（剩余履约义务）时用「积压覆盖月数」作为稀缺期下界，下界只能往上支持
   （乘数取 max(下界档位, 0.85)，门 B 下界达标记 PASS），不能证明稀缺期短；拿不到 RPO 或下界不足时门 B 记 UNVERIFIED，
   乘数取保守的 0.85。所以 Skill 里「跑道 <6 个月且无合同化斜坡」的硬阻断在本数据下不会触发。
4. 申报里从未出现任何债务标签的公司按「无债务」估算净现金，标 PROXY 并封顶（资产负债表 3、存续 3）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..evidence.factstore import FactStore
from .fundamentals import (CHINA_HK_CODES, US_STATE_CODES, Fundamentals, MarketInput, PeerContext,
                           compute_fundamentals)
from .scoring_support import (KIND_MARKET, NO_EVIDENCE, DimensionResult, EvidenceRef, FactorResult, ParamsError,
                              Receipt, aggregate_dimension, check_table, check_unit_interval, dedupe_refs,
                              geometric_mean, load_params, no_evidence, table_rating, clamp, _check_weights)
from .structure_factors import StructureEvidence
from . import structure_factors as SF
from .textmarkers import TextMarkers

SKILL_ID = "bottleneck-serenity-skill"
DEFAULT_PARAMS_PATH = (Path(__file__).resolve().parents[3] / "Stock_Skill" / SKILL_ID / "runtime" / "params.json")

DIMENSIONS = ("constraint", "capture", "mispricing", "evidence", "investability")

DEFAULT_PARAMS: Dict[str, Any] = {
    "schema": "signal-lattice-branch-params/1",
    "skill": SKILL_ID,
    "params_version": "0.0.0.2",
    "source": "Stock_Skill/bottleneck-serenity-skill/task-pack/skill_draft/bottleneck-serenity-skill/references/scoring_model.md",
    "dimension_weights": {
        "constraint": {"funded_demand": 15, "architectural_necessity": 15, "current_tightness": 10,
                       "supplier_concentration": 10, "qualification_barrier": 15, "substitution_difficulty": 15,
                       "expansion_lead_time": 10, "policy_resilience": 10},
        "capture": {"exposure_materiality": 15, "pricing_power": 15, "capacity_to_ship": 15, "unit_economics": 10,
                    "contract_counterparty": 10, "appropriability": 10, "balance_sheet": 10,
                    "dilution_discipline": 10, "capital_allocation": 5},
        "mispricing": {"expectations_gap": 20, "valuation_asymmetry": 20, "coverage_gap": 10, "catalyst_clarity": 15,
                       "estimate_revision_potential": 15, "crowding_headroom": 10, "entry_setup": 10},
        "evidence": {"primary_source_coverage": 25, "independent_corroboration": 20, "numerical_traceability": 15,
                     "freshness": 15, "contradiction_search": 15, "source_independence": 10},
        "investability": {"liquidity": 15, "governance_accounting": 15, "geopolitical_regulatory": 15,
                          "customer_diversification": 10, "technology_resilience": 10, "balance_sheet_survival": 15,
                          "float_gap_risk": 10, "portfolio_fit": 10},
    },
    # scoring_model.md 的默认硬门（原样）
    "gates": {"constraint_min": 60, "capture_min": 55, "evidence_min": 60, "investability_min": 50,
              "mispricing_min": 45, "candidate_min_final": 62, "priority_min_final": 75},
    # 覆盖率下限与必备因子：本仓对「NO_EVIDENCE 怎么处理」的规则（Skill 未规定，此处显式声明）
    "coverage": {
        "min_by_dimension": {"constraint": 0.40, "capture": 0.50, "mispricing": 0.40, "evidence": 0.50,
                             "investability": 0.50},
        "required_factors": {
            "constraint": ["funded_demand", "current_tightness"],
            "capture": ["pricing_power", "unit_economics", "dilution_discipline"],
            "mispricing": ["valuation_asymmetry"],
            "evidence": ["primary_source_coverage"],
            "investability": ["liquidity", "balance_sheet_survival"],
        },
    },
    "geometric_mean_floor": 0.01,
    "duration": {
        # 稀缺期 P50 从申报里拿不到；RPO 覆盖月数只是「已合同化」的下界，下界只能往上支持，不能证明稀缺期很短
        "upper_bounds_months": [0, 6, 12, 24, 48],
        "multipliers": [0.50, 0.70, 0.85, 1.00, 1.07, 1.10],
        "unknown_runway_multiplier": 0.85,
        "monetization_lag_months_when_revenue_flowing": 3,
        "contracted_forward_ramp_min_months": 12,
        "hard_gate_runway_months": 6,
    },
    "asymmetry": {"unavailable_multiplier": 1.0},
    "financing_gap_runway_months": 12,
    # RPO 要覆盖至少这么多个月的 TTM 营收才算需求证据；基数微小的 RPO 同比（如 190 万对 1 亿营收）是噪声
    "rpo": {"min_months_as_demand_evidence": 1.0},
    "text_markers": {"marker_cap_rating": 2, "corroborated_cap_rating": 4, "min_count": 2,
                     "tightness_groups": ["capacity_constrained", "lead_times", "allocation"]},
    "capacity": {"volume_growth_min": 0.10, "capex_intensity_min": 0.03, "ppe_growth_min": 0.10,
                 "with_capex_rating": 3, "with_ppe_bonus": 1, "asset_light_rating": 2, "shrinking_rating": 1,
                 "cap_rating": 4},
    "tightness": {"revenue_yoy_min": 0.0, "shrinking_cap_rating": 1, "corroboration_revenue_yoy_min": 0.10},
    "pricing_power": {"shrinking_cap_rating": 2},
    # 10-K/10-Q 正文抽取（evidence/structure_text.py）如何折成 0-5 分；有数字才能到 3 以上，方向不明不计分
    "structure_text": {
        "owner_sole_source_rating": 3,
        "utilization_min_pct": 90,
        "utilization_text_only_rating": 3,
        "backlog_yoy_cap_rating": 4,
        "upstream_supply_only_rating": 3,
        "upstream_sole_source_rating": 2,
        "upstream_share_mid_pct": 30,
        "upstream_share_mid_rating": 2,
        "upstream_share_high_pct": 50,
        "upstream_share_high_rating": 1,
    },
    "governance": {"start_rating": 4, "nt_penalty": 2, "nonreliance_penalty": 4, "auditor_change_penalty": 1,
                   "restatement_penalty": 1, "restatement_threshold": 0.05, "min_filings_seen": 5},
    "geography": {"us_rating": 4, "foreign_rating": 2, "china_hk_rating": 1},
    "evidence_factors": {"critical_claims": ["funded_demand", "current_tightness", "pricing_power", "unit_economics"],
                         "source_independence_rating": 2, "contradiction_clean_rating": 3,
                         "contradiction_tripped_rating": 1, "restatement_threshold": 0.05,
                         "rpo_up_revenue_down": [0.30, -0.10]},
    "survival": {"profitable_net_cash_rating": 4, "debt_assumed_zero_cap_rating": 3},
    "balance_sheet": {"debt_assumed_zero_cap_rating": 3},
    "entry_setup": {"falling_knife_below_high": -0.5, "falling_knife_cap": 2},
    "tables": {
        "funded_demand_rpo_yoy": {"direction": "higher", "cuts": [[0.6, 5], [0.3, 4], [0.1, 3], [0.0, 2], [-0.1, 1]], "floor": 0},
        "funded_demand_revenue_yoy": {"direction": "higher", "cuts": [[0.25, 3], [0.10, 2], [0.0, 1]], "floor": 0},
        "funded_demand_backlog_months": {"direction": "higher", "cuts": [[6, 3], [3, 2], [1, 1]], "floor": 0},
        "expansion_lead_time_months": {"direction": "higher", "cuts": [[12, 4], [6, 3], [3, 2]], "floor": 1},
        "qualification_months": {"direction": "higher", "cuts": [[24, 4], [12, 3], [6, 2]], "floor": 1},
        "customer_top_share_pct": {"direction": "lower", "cuts": [[9.99, 4], [19.99, 3], [34.99, 2], [49.99, 1]], "floor": 0},
        "tightness_gm_change_bps": {"direction": "higher", "cuts": [[400, 4], [200, 3], [50, 2], [0, 1]], "floor": 0},
        "pricing_power_gm_change_bps": {"direction": "higher", "cuts": [[500, 5], [300, 4], [100, 3], [0, 2], [-100, 1]], "floor": 0},
        "unit_economics_op_margin": {"direction": "higher", "cuts": [[0.20, 5], [0.12, 4], [0.05, 3], [0.0, 2], [-0.15, 1]], "floor": 0},
        "balance_sheet_net_cash_to_cap": {"direction": "higher", "cuts": [[0.15, 5], [0.05, 4], [-0.05, 3], [-0.20, 2], [-0.40, 1]], "floor": 0},
        "dilution_share_change_yoy": {"direction": "lower", "cuts": [[-0.02, 5], [0.01, 4], [0.03, 3], [0.08, 2], [0.20, 1]], "floor": 0},
        "capital_allocation_net_buyback_yield": {"direction": "higher", "cuts": [[0.02, 5], [0.005, 4], [0.0, 3], [-0.02, 2], [-0.06, 1]], "floor": 0},
        "valuation_percentile": {"direction": "lower", "cuts": [[0.15, 5], [0.30, 4], [0.50, 3], [0.70, 2], [0.85, 1]], "floor": 0},
        "coverage_gap_market_cap": {"direction": "lower", "cuts": [[500000000, 4], [1000000000, 3], [2000000000, 2]], "floor": 1},
        "catalyst_days_to_report": {"direction": "lower", "cuts": [[45, 3], [90, 2], [135, 1]], "floor": 0},
        "entry_setup_ret_63d": {"direction": "lower", "cuts": [[0.10, 4], [0.30, 3], [0.60, 2]], "floor": 1},
        "freshness_period_age_days": {"direction": "lower", "cuts": [[120, 5], [180, 4], [240, 3], [330, 2], [460, 1]], "floor": 0},
        "numerical_traceability_fraction": {"direction": "higher", "cuts": [[0.9, 5], [0.75, 4], [0.6, 3], [0.4, 2], [0.2, 1]], "floor": 0},
        "primary_coverage_claims": {"direction": "higher", "cuts": [[4, 5], [3, 4], [2, 3], [1, 1]], "floor": 0},
        "liquidity_dollar_volume": {"direction": "higher", "cuts": [[30000000, 5], [15000000, 4], [8000000, 3], [4500000, 2], [3000000, 1]], "floor": 0},
        "survival_runway_months": {"direction": "higher", "cuts": [[36, 4], [24, 3], [12, 2], [6, 1]], "floor": 0},
        "survival_debt_to_ocf": {"direction": "lower", "cuts": [[3, 3], [6, 2]], "floor": 1},
    },
}

FACTOR_SOURCES: Dict[str, str] = {
    "funded_demand": "XBRL us-gaap:RevenueRemainingPerformanceObligation 同比（最高 5）；无 RPO 时用正文积压订单金额（覆盖月数最高 3，带对比期同比最高 4）；否则 TTM 营收同比（最高 3，间接证据）",
    "architectural_necessity": "NO_EVIDENCE：需要系统架构/客户设计资料，申报 XBRL 没有",
    "current_tightness": "XBRL 毛利率 TTM 同比变化（需营收未下滑）；原文标记（产能受限/交期/配给）只作佐证，单独最高 2",
    "supplier_concentration": "10-K/10-Q 正文抽取：公司自称唯一/少数供应商（OWNER，最高 3）；依赖上游单一来源是风险，进 technology_resilience 不加分；判不出方向=AMBIGUOUS 不计分；没抽到=NO_EVIDENCE",
    "qualification_barrier": "10-K/10-Q 正文抽取：客户换供应商要认证 N 个月（OWNER 且带数字，≥12 个月 3 分、≥24 个月 4 分）；没抽到=NO_EVIDENCE",
    "substitution_difficulty": "NO_EVIDENCE：需要技术替代路线资料",
    "expansion_lead_time": "10-K/10-Q 正文抽取：自家产品交期 N 周/月（OWNER 且带数字，≥6 个月 3 分、≥12 个月 4 分，PROXY）；上游交期进风险；没抽到=NO_EVIDENCE",
    "policy_resilience": "NO_EVIDENCE：需要政策/地理集中度资料",
    "exposure_materiality": "NO_EVIDENCE：companyfacts 无 segment 维度，无法证明约束业务占营收比",
    "pricing_power": "XBRL 毛利率 TTM 同比变化（营收下滑则封顶 2）",
    "capacity_to_ship": "XBRL PaymentsToAcquirePropertyPlantAndEquipment/营收、PP&E 净额同比、营收同比（最高 4）",
    "unit_economics": "XBRL OperatingIncomeLoss / 营收（TTM）",
    "contract_counterparty": "NO_EVIDENCE：需要客户与合同条款",
    "appropriability": "NO_EVIDENCE：需要互补资产与知识产权资料",
    "balance_sheet": "XBRL 现金+短投−债务，占市值比",
    "dilution_discipline": "股数同比变化（dei 封面股数 / 加权稀释股数）",
    "capital_allocation": "XBRL 回购支出−股票发行收入，占市值比；两个标签都没有=NO_EVIDENCE",
    "expectations_gap": "NO_EVIDENCE：需要一致预期，免费一手数据没有",
    "valuation_asymmetry": "市值/营收、市值/毛利 的自身历史分位与同业（同 SIC 两位码）分位的平均；越低越好",
    "coverage_gap": "PROXY：以市值规模代替分析师覆盖（未取覆盖数），最高 4",
    "catalyst_clarity": "ESTIMATED：按过去申报节奏推算下一份 10-Q/10-K 申报日，最高 3（不是公司确认日期）",
    "estimate_revision_potential": "NO_EVIDENCE：需要一致预期修订",
    "crowding_headroom": "NO_EVIDENCE：需要持仓/做空数据",
    "entry_setup": "价格 63 日涨幅（追高扣分）与距 52 周高点（下跌刀封顶），最高 4；无日线=NO_EVIDENCE",
    "primary_source_coverage": "关键论点（融资需求/紧张度/定价权/单位经济）里有 SEC 原文链接支撑的个数",
    "independent_corroboration": "NO_EVIDENCE：本分支只用发行人自己的申报，没有独立第二来源",
    "numerical_traceability": "有数因子中带 accession+期间+数值的占比",
    "freshness": "最近一份 10-K/10-Q 的报告期距 as_of 的天数",
    "contradiction_search": "自动一致性检查：营收重述幅度、SEC/新浪市值差、积压与营收方向背离；没触发=3，触发=1（没有人工反证搜索，不给 4 以上）",
    "source_independence": "固定 2：全部证据都是发行人自述（SEC 申报），无第二独立来源",
    "liquidity": "20 日成交额中位数（美元）",
    "governance_accounting": "起评 4（无审计核验不给 5），扣分项：NT 10-K/10-Q、8-K 4.02 非依赖、8-K 4.01 换所、大幅重述",
    "geopolitical_regulatory": "SEC 登记主要营业地：美国州=4，中国/香港=1，其他境外=2（只是登记地代理）",
    "customer_diversification": "10-K/10-Q 正文抽取：最大单一客户占营收 %（<10% 自述 4 分，10-20% 3 分，20-35% 2 分，35-50% 1 分，≥50% 0 分）；没披露=NO_EVIDENCE",
    "technology_resilience": "PROXY 供应链单点依赖风险：正文披露依赖上游单一来源/单一供应商采购占比时给偏低评分；没披露=NO_EVIDENCE（不给抗风险加分）",
    "balance_sheet_survival": "经营现金流为负：现金/月度消耗；为正：净现金≥0 得 4，否则按 债务/经营现金流 分档，最高 4",
    "float_gap_risk": "NO_EVIDENCE：需要自由流通量与做空数据",
    "portfolio_fit": "NO_EVIDENCE：组合层面因子",
}


def validate_params(params: Any) -> None:
    from .scoring_support import _require_keys, check_shape
    check_shape(DEFAULT_PARAMS, params, "params")
    _require_keys(params["dimension_weights"], DIMENSIONS, "dimension_weights")
    for dim in DIMENSIONS:
        _check_weights(params["dimension_weights"][dim], "dimension_weights." + dim, 100.0,
                       DEFAULT_PARAMS["dimension_weights"][dim].keys())
    gates = params["gates"]
    for key, value in gates.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ParamsError("gates.%s 必须在 0-100" % key)
    if gates["priority_min_final"] < gates["candidate_min_final"]:
        raise ParamsError("priority_min_final 不得低于 candidate_min_final")
    for dim, value in params["coverage"]["min_by_dimension"].items():
        check_unit_interval(value, "coverage.min_by_dimension." + dim)
    for dim, names in params["coverage"]["required_factors"].items():
        unknown = set(names) - set(params["dimension_weights"][dim])
        if unknown:
            raise ParamsError("coverage.required_factors.%s 含未知因子 %s" % (dim, sorted(unknown)))
    duration = params["duration"]
    bounds, mults = duration["upper_bounds_months"], duration["multipliers"]
    if len(mults) != len(bounds) + 1 or sorted(bounds) != bounds or sorted(mults) != mults:
        raise ParamsError("duration 的分段与乘数必须等长+1 且递增")
    for name, table in params["tables"].items():
        check_table(table, "tables." + name)
    claims = params["evidence_factors"]["critical_claims"]
    if set(claims) - set(params["dimension_weights"]["constraint"]) - set(params["dimension_weights"]["capture"]):
        raise ParamsError("evidence_factors.critical_claims 含未知因子")


def load_bottleneck_params(path: Optional[Path] = DEFAULT_PARAMS_PATH) -> Tuple[dict, List[dict]]:
    return load_params(DEFAULT_PARAMS, validate_params, path)


def write_default_params(path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(DEFAULT_PARAMS, ensure_ascii=False, indent=2, sort_keys=False) + "\n", "utf-8")


# ---- 因子 ----------------------------------------------------------------------
class _Metric:
    """funded_demand 的候选证据（数值 + 证据引用），与 fundamentals.M 的 .value/.refs 同形。"""

    def __init__(self, value: float, refs: Tuple[EvidenceRef, ...]) -> None:
        self.value, self.refs = value, refs


def _fmt(value: Optional[float], pct: bool = False, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return ("%.1f%%" % (value * 100.0)) if pct else ("%.*f" % (digits, value))


def constraint_factors(f: Fundamentals, text: Optional[TextMarkers], p: dict,
                       structure: Optional[StructureEvidence] = None) -> Dict[str, FactorResult]:
    T = p["tables"]
    tm = p["text_markers"]
    out: Dict[str, FactorResult] = {}

    # funded_demand
    options: List[Tuple[float, str, Any]] = []
    rpo_min = p["rpo"]["min_months_as_demand_evidence"]
    rpo_material = f.rpo_yoy.ok and f.rpo_months.ok and f.rpo_months.value >= rpo_min
    rpo_note = ""
    if f.rpo_yoy.ok and not rpo_material:
        rpo_note = "（RPO 只覆盖 %s 个月营收，低于 %s 个月，不作需求证据）" % (
            "n/a" if not f.rpo_months.ok else "%.2f" % f.rpo_months.value, rpo_min)
    if rpo_material:
        options.append((table_rating(f.rpo_yoy.value, T["funded_demand_rpo_yoy"]), "RPO 同比 %s（覆盖 %.1f 个月营收）" % (
            _fmt(f.rpo_yoy.value, True), f.rpo_months.value), f.rpo_yoy))
    if f.revenue_yoy.ok:
        options.append((table_rating(f.revenue_yoy.value, T["funded_demand_revenue_yoy"]),
                        "TTM 营收同比 %s（间接证据，最高 3）" % _fmt(f.revenue_yoy.value, True), f.revenue_yoy))
    backlog_option = None
    if structure is not None and not rpo_material:
        backlog_option = SF.backlog_demand(structure, f, p)
    if backlog_option is not None:
        options.append((backlog_option[0], backlog_option[1], _Metric(backlog_option[3], backlog_option[2])))
    if options:
        best = max(options, key=lambda o: o[0])
        out["funded_demand"] = FactorResult("funded_demand", best[0], "；".join(o[1] for o in options) + rpo_note,
                                            dedupe_refs(best[2].refs), "OBSERVED", best[2].value)
    else:
        out["funded_demand"] = no_evidence("funded_demand", "没有 RPO，也拼不出 TTM 营收同比")
    out["architectural_necessity"] = no_evidence("architectural_necessity", FACTOR_SOURCES["architectural_necessity"])

    # current_tightness
    numeric = None
    basis: List[str] = []
    refs: Tuple[EvidenceRef, ...] = ()
    if f.gm_change_bps.ok:
        numeric = table_rating(f.gm_change_bps.value, T["tightness_gm_change_bps"])
        basis.append("毛利率 TTM 同比变化 %+.0f bp" % f.gm_change_bps.value)
        refs = f.gm_change_bps.refs
        if f.revenue_yoy.ok and f.revenue_yoy.value < p["tightness"]["revenue_yoy_min"]:
            numeric = min(numeric, p["tightness"]["shrinking_cap_rating"])
            basis.append("营收同比 %s 为负，毛利率上升不算紧张，封顶 %s" % (
                _fmt(f.revenue_yoy.value, True), p["tightness"]["shrinking_cap_rating"]))
    if structure is not None:
        owner = SF.owner_tightness(structure, p)
        if numeric is None and owner is None:
            out["current_tightness"] = no_evidence("current_tightness", "拿不到毛利率同比；正文没有方向明确的产能受限/满负荷表述" +
                                                   SF._ambiguous_note(structure, "capacity_constraint"))
        else:
            rating = numeric
            if owner is not None:
                basis.append(owner[2])
                refs = refs + owner[3]
                if rating is not None and rating >= 2:
                    rating = min(tm["corroborated_cap_rating"], rating + 1)   # 数字与原文互证
                else:
                    rating = max(rating or 0, owner[1])                        # 只有原文：无数字最高 2，有利用率数字最高 3
            out["current_tightness"] = FactorResult("current_tightness", rating, "；".join(basis), dedupe_refs(refs),
                                                    "OBSERVED", f.gm_change_bps.value if f.gm_change_bps.ok else None)
    else:
        marker_groups = [g for g in tm["tightness_groups"] if text is not None and text.counts.get(g, 0) >= tm["min_count"]]
        if numeric is None and text is None:
            out["current_tightness"] = no_evidence("current_tightness", "拿不到毛利率同比，也未扫描原文")
        else:
            rating = numeric
            if text is not None:
                if marker_groups:
                    basis.append("原文标记：" + ",".join("%s×%d" % (g, text.counts[g]) for g in marker_groups))
                    refs = refs + tuple(text.ref(g) for g in marker_groups)
                    if rating is not None and rating >= 2:
                        rating = min(tm["corroborated_cap_rating"], rating + 1)   # 数字与原文互证
                    else:
                        rating = max(rating or 0, tm["marker_cap_rating"])          # 只有原文：最高 2
                elif rating is None:
                    rating = 0
                    basis.append("已扫描原文，未见产能受限/交期/配给措辞")
            out["current_tightness"] = FactorResult("current_tightness", rating, "；".join(basis), dedupe_refs(refs),
                                                    "OBSERVED", f.gm_change_bps.value if f.gm_change_bps.ok else None)

    # supplier_concentration / expansion_lead_time / qualification_barrier：只来自正文抽取
    if structure is not None:
        out["supplier_concentration"] = SF.supplier_concentration(structure, p)
        out["expansion_lead_time"] = SF.expansion_lead_time(structure, p)
        out["qualification_barrier"] = SF.qualification_barrier(structure, p)
        for name in ("substitution_difficulty", "policy_resilience"):
            out[name] = no_evidence(name, FACTOR_SOURCES[name])
        return out
    for name, group in (("supplier_concentration", "sole_source"), ("expansion_lead_time", "lead_times")):
        if text is None:
            out[name] = no_evidence(name, "未扫描申报原文（不扫描就没有依据）")
            continue
        n = text.counts.get(group, 0)
        if n >= tm["min_count"]:
            out[name] = FactorResult(name, tm["marker_cap_rating"], "原文标记 %s×%d（只是标记，最高 %d；方向需人核对）" % (
                group, n, tm["marker_cap_rating"]), (text.ref(group),), "OBSERVED", float(n))
        else:
            out[name] = FactorResult(name, 1 if n >= 1 else 0, "原文 %s 仅 %d 次（低于 %d 次不算标记）" % (
                group, n, tm["min_count"]), (), "OBSERVED", float(n))
    for name in ("qualification_barrier", "substitution_difficulty", "policy_resilience"):
        out[name] = no_evidence(name, FACTOR_SOURCES[name])
    return out


def capture_factors(f: Fundamentals, p: dict) -> Dict[str, FactorResult]:
    T = p["tables"]
    out: Dict[str, FactorResult] = {}
    out["exposure_materiality"] = no_evidence("exposure_materiality", FACTOR_SOURCES["exposure_materiality"])

    if f.gm_change_bps.ok:
        rating = table_rating(f.gm_change_bps.value, T["pricing_power_gm_change_bps"])
        basis = "毛利率 TTM 同比变化 %+.0f bp" % f.gm_change_bps.value
        if f.revenue_yoy.ok and f.revenue_yoy.value < 0:
            rating = min(rating, p["pricing_power"]["shrinking_cap_rating"])
            basis += "；营收同比 %s 下滑，封顶 %s" % (_fmt(f.revenue_yoy.value, True), p["pricing_power"]["shrinking_cap_rating"])
        out["pricing_power"] = FactorResult("pricing_power", rating, basis, f.gm_change_bps.refs, "OBSERVED", f.gm_change_bps.value)
    else:
        out["pricing_power"] = no_evidence("pricing_power", "拿不到毛利率同比变化")

    cap = p["capacity"]
    if f.revenue_yoy.ok and (f.capex_intensity.ok or f.ppe_yoy.ok):
        growing = f.revenue_yoy.value >= cap["volume_growth_min"]
        invests = f.capex_intensity.ok and f.capex_intensity.value >= cap["capex_intensity_min"]
        ppe_up = f.ppe_yoy.ok and f.ppe_yoy.value >= cap["ppe_growth_min"]
        if not growing and f.revenue_yoy.value < 0:
            rating, why = cap["shrinking_rating"], "营收同比 %s 下滑" % _fmt(f.revenue_yoy.value, True)
        elif growing and invests:
            rating = cap["with_capex_rating"] + (cap["with_ppe_bonus"] if ppe_up else 0)
            why = "营收同比 %s 且资本开支/营收 %s%s" % (_fmt(f.revenue_yoy.value, True), _fmt(f.capex_intensity.value, True),
                                              "，PP&E 同比 %s" % _fmt(f.ppe_yoy.value, True) if ppe_up else "")
        else:
            rating, why = cap["asset_light_rating"], "营收同比 %s，资本开支/营收 %s（未见扩产）" % (
                _fmt(f.revenue_yoy.value, True), _fmt(f.capex_intensity.value, True))
        rating = min(rating, cap["cap_rating"])
        refs = dedupe_refs(f.revenue_yoy.refs + f.capex_intensity.refs + f.ppe_yoy.refs)
        out["capacity_to_ship"] = FactorResult("capacity_to_ship", rating, why + "；最高 %d（名义产能≠合格产出）" % cap["cap_rating"],
                                               refs, "OBSERVED", f.capex_intensity.value)
    else:
        out["capacity_to_ship"] = no_evidence("capacity_to_ship", "拿不到 资本开支/PP&E 与营收同比")

    if f.op_margin.ok:
        out["unit_economics"] = FactorResult("unit_economics", table_rating(f.op_margin.value, T["unit_economics_op_margin"]),
                                             "TTM 营业利润率 %s" % _fmt(f.op_margin.value, True), f.op_margin.refs,
                                             "OBSERVED", f.op_margin.value)
    else:
        out["unit_economics"] = no_evidence("unit_economics", "拿不到 OperatingIncomeLoss TTM")
    out["contract_counterparty"] = no_evidence("contract_counterparty", FACTOR_SOURCES["contract_counterparty"])
    out["appropriability"] = no_evidence("appropriability", FACTOR_SOURCES["appropriability"])

    if f.net_cash_to_cap.ok:
        rating = table_rating(f.net_cash_to_cap.value, T["balance_sheet_net_cash_to_cap"])
        basis = "净现金/市值 %s" % _fmt(f.net_cash_to_cap.value, True)
        status = "OBSERVED"
        if f.debt_assumed_zero:
            rating = min(rating, p["balance_sheet"]["debt_assumed_zero_cap_rating"])
            basis += "；申报里没有任何债务标签，按无债务估算，封顶 %s" % p["balance_sheet"]["debt_assumed_zero_cap_rating"]
            status = "PROXY"
        out["balance_sheet"] = FactorResult("balance_sheet", rating, basis, f.net_cash_to_cap.refs, status, f.net_cash_to_cap.value)
    else:
        out["balance_sheet"] = no_evidence("balance_sheet", "拿不到现金或债务，算不出净现金")

    if f.share_change_yoy.ok:
        out["dilution_discipline"] = FactorResult("dilution_discipline", table_rating(f.share_change_yoy.value, T["dilution_share_change_yoy"]),
                                                  "股数同比 %s（%s）" % (_fmt(f.share_change_yoy.value, True), f.share_change_yoy.note),
                                                  f.share_change_yoy.refs, "OBSERVED", f.share_change_yoy.value)
    else:
        out["dilution_discipline"] = no_evidence("dilution_discipline", "拿不到一年前的股数，算不出稀释")

    if f.net_buyback_yield.ok:
        out["capital_allocation"] = FactorResult("capital_allocation", table_rating(f.net_buyback_yield.value, T["capital_allocation_net_buyback_yield"]),
                                                 "净回购率（回购−发行收入）/市值 %s" % _fmt(f.net_buyback_yield.value, True),
                                                 f.net_buyback_yield.refs, "OBSERVED", f.net_buyback_yield.value)
    else:
        out["capital_allocation"] = no_evidence("capital_allocation", "没有回购与发行收入标签")
    return out


def mispricing_factors(f: Fundamentals, peers: Optional[PeerContext], p: dict) -> Dict[str, FactorResult]:
    T = p["tables"]
    out: Dict[str, FactorResult] = {}
    out["expectations_gap"] = no_evidence("expectations_gap", FACTOR_SOURCES["expectations_gap"])

    pcts: List[Tuple[float, str, Any]] = []
    if f.hist_cap_sales_pct.ok:
        pcts.append((f.hist_cap_sales_pct.value, "自身历史 市值/营收 分位 %s" % _fmt(f.hist_cap_sales_pct.value, True), f.hist_cap_sales_pct))
    if f.hist_cap_gp_pct.ok:
        pcts.append((f.hist_cap_gp_pct.value, "自身历史 市值/毛利 分位 %s" % _fmt(f.hist_cap_gp_pct.value, True), f.hist_cap_gp_pct))
    if peers is not None:
        for attr, label in (("cap_sales", "市值/营收"), ("cap_gp", "市值/毛利")):
            pct, group, n = peers.percentile(f, attr)
            if pct is not None:
                pcts.append((pct, "同业(%s,n=%d) %s 分位 %s" % (group, n, label, _fmt(pct, True)), getattr(f, attr)))
    if pcts:
        avg = sum(x[0] for x in pcts) / len(pcts)
        refs = dedupe_refs(tuple(r for x in pcts for r in x[2].refs))
        out["valuation_asymmetry"] = FactorResult("valuation_asymmetry", table_rating(avg, T["valuation_percentile"]),
                                                  "；".join(x[1] for x in pcts) + "；平均分位 %s（越低越便宜）" % _fmt(avg, True),
                                                  refs, "OBSERVED", avg)
    else:
        out["valuation_asymmetry"] = no_evidence("valuation_asymmetry", "既无自身历史分位也无同业分位（缺营收或缺历史价格）")

    out["coverage_gap"] = FactorResult("coverage_gap", table_rating(f.market.market_cap, T["coverage_gap_market_cap"]),
                                       "PROXY 市值 %.0f 美元（规模代替分析师覆盖）" % f.market.market_cap,
                                       (f.market.market_ref(f.as_of),), "PROXY", f.market.market_cap)

    est = f.next_report
    if est is not None and est.days_until >= 0:
        out["catalyst_clarity"] = FactorResult("catalyst_clarity", table_rating(est.days_until, T["catalyst_days_to_report"]),
                                               "ESTIMATED 下次财报预计 %s（%d 天后）：%s" % (est.est_date, est.days_until, est.basis),
                                               est.refs, "ESTIMATED", float(est.days_until))
    else:
        why = "推算不出下次申报日" if est is None else "推算日 %s 已过而未见新申报（估计失效）" % est.est_date
        out["catalyst_clarity"] = no_evidence("catalyst_clarity", why)
    out["estimate_revision_potential"] = no_evidence("estimate_revision_potential", FACTOR_SOURCES["estimate_revision_potential"])
    out["crowding_headroom"] = no_evidence("crowding_headroom", FACTOR_SOURCES["crowding_headroom"])

    if f.ret_63d is not None:
        rating = table_rating(f.ret_63d, T["entry_setup_ret_63d"])
        basis = "63 日涨幅 %s" % _fmt(f.ret_63d, True)
        es = p["entry_setup"]
        if f.below_52w_high is not None and f.below_52w_high <= es["falling_knife_below_high"]:
            rating = min(rating, es["falling_knife_cap"])
            basis += "；距 52 周高点 %s（下跌刀封顶 %s）" % (_fmt(f.below_52w_high, True), es["falling_knife_cap"])
        out["entry_setup"] = FactorResult("entry_setup", rating, basis, (f.market.market_ref(f.as_of),), "OBSERVED", f.ret_63d)
    else:
        out["entry_setup"] = no_evidence("entry_setup", "没有足够的日线历史")
    return out


def investability_factors(f: Fundamentals, p: dict, structure: Optional[StructureEvidence] = None) -> Dict[str, FactorResult]:
    T = p["tables"]
    out: Dict[str, FactorResult] = {}
    m = f.market
    out["liquidity"] = FactorResult("liquidity", table_rating(m.median_dollar_volume, T["liquidity_dollar_volume"]),
                                    "20 日成交额中位数 %.0f 美元" % m.median_dollar_volume, (m.market_ref(f.as_of),),
                                    "OBSERVED", m.median_dollar_volume)

    g = p["governance"]
    if f.filings_seen >= g["min_filings_seen"]:
        rating = g["start_rating"]
        notes = []
        if f.nt_filings_24m:
            rating -= g["nt_penalty"]; notes.append("NT 迟报×%d" % f.nt_filings_24m)
        if f.nonreliance_8k_24m:
            rating -= g["nonreliance_penalty"]; notes.append("8-K 4.02 非依赖×%d" % f.nonreliance_8k_24m)
        if f.auditor_change_8k_24m:
            rating -= g["auditor_change_penalty"]; notes.append("8-K 4.01 换所×%d" % f.auditor_change_8k_24m)
        if f.restatement.ok and f.restatement.value > g["restatement_threshold"]:
            rating -= g["restatement_penalty"]; notes.append("营收重述幅度 %s" % _fmt(f.restatement.value, True))
        out["governance_accounting"] = FactorResult(
            "governance_accounting", max(0, rating), "近 24 个月红旗：%s（起评 %d，无审计核验不给 5）" % (
                "、".join(notes) if notes else "无", g["start_rating"]),
            f.restatement.refs, "OBSERVED", float(len(notes)))
    else:
        out["governance_accounting"] = no_evidence("governance_accounting", "申报清单太短（%d 份），不足以判断" % f.filings_seen)

    geo = p["geography"]
    state = m.state_of_business
    if state:
        if state in US_STATE_CODES:
            rating, why = geo["us_rating"], "美国州 %s" % state
        elif state in CHINA_HK_CODES:
            rating, why = geo["china_hk_rating"], "登记地 %s（中国大陆/香港）" % state
        else:
            rating, why = geo["foreign_rating"], "境外登记地 %s" % state
        out["geopolitical_regulatory"] = FactorResult("geopolitical_regulatory", rating, "PROXY " + why, (), "PROXY", None)
    else:
        out["geopolitical_regulatory"] = no_evidence("geopolitical_regulatory", "submissions 没有营业地址")
    for name in ("customer_diversification", "technology_resilience", "float_gap_risk", "portfolio_fit"):
        out[name] = no_evidence(name, FACTOR_SOURCES[name])
    if structure is not None:
        out["customer_diversification"] = SF.customer_diversification(structure, p)
        out["technology_resilience"] = SF.upstream_dependency_risk(structure, p)

    sv = p["survival"]
    if f.ocf_ttm.ok and f.ocf_ttm.value < 0 and f.cash_runway_months.ok:
        out["balance_sheet_survival"] = FactorResult(
            "balance_sheet_survival", table_rating(f.cash_runway_months.value, T["survival_runway_months"]),
            "经营现金流为负，现金覆盖 %.1f 个月" % f.cash_runway_months.value, f.cash_runway_months.refs, "OBSERVED",
            f.cash_runway_months.value)
    elif f.ocf_ttm.ok and f.ocf_ttm.value >= 0:
        if f.net_cash.ok and f.net_cash.value >= 0:
            rating = sv["profitable_net_cash_rating"]
            basis, status = "经营现金流为正且净现金为正", "OBSERVED"
            if f.debt_assumed_zero:
                rating = min(rating, sv["debt_assumed_zero_cap_rating"])
                basis += "（申报里没有任何债务标签，按无债务估算，封顶 %d）" % sv["debt_assumed_zero_cap_rating"]
                status = "PROXY"
            out["balance_sheet_survival"] = FactorResult("balance_sheet_survival", rating, basis,
                                                         dedupe_refs(f.ocf_ttm.refs + f.net_cash.refs), status, f.net_cash.value)
        elif f.debt.ok and f.ocf_ttm.value > 0:
            ratio = f.debt.value / f.ocf_ttm.value
            out["balance_sheet_survival"] = FactorResult("balance_sheet_survival", table_rating(ratio, T["survival_debt_to_ocf"]),
                                                         "债务/经营现金流 %.1f 年" % ratio, dedupe_refs(f.ocf_ttm.refs + f.debt.refs),
                                                         "OBSERVED", ratio)
        else:
            out["balance_sheet_survival"] = no_evidence("balance_sheet_survival", "经营现金流为正但拿不到债务，无法判断偿付")
    else:
        out["balance_sheet_survival"] = no_evidence("balance_sheet_survival", "拿不到经营现金流或现金")
    return out


def evidence_factors(f: Fundamentals, others: Dict[str, Dict[str, FactorResult]], p: dict) -> Dict[str, FactorResult]:
    T = p["tables"]
    ef = p["evidence_factors"]
    out: Dict[str, FactorResult] = {}
    flat = {name: fr for dim in others.values() for name, fr in dim.items()}

    def primary(fr: FactorResult) -> bool:
        return fr.observed and any(ref.is_primary_link for ref in fr.refs)

    backed = [name for name in ef["critical_claims"] if primary(flat[name])]
    all_refs = dedupe_refs(tuple(ref for name in backed for ref in flat[name].refs if ref.is_primary_link))
    out["primary_source_coverage"] = FactorResult(
        "primary_source_coverage", table_rating(len(backed), T["primary_coverage_claims"]),
        "关键论点 %d/%d 有 SEC 原文链接：%s" % (len(backed), len(ef["critical_claims"]), ",".join(backed) or "无"),
        all_refs[:6], "OBSERVED", float(len(backed)))
    out["independent_corroboration"] = no_evidence("independent_corroboration", FACTOR_SOURCES["independent_corroboration"])

    observed = [fr for fr in flat.values() if fr.observed and fr.status in ("OBSERVED", "ESTIMATED")]
    traceable = [fr for fr in observed if any(r.accession and r.period_end and r.value is not None for r in fr.refs)]
    if observed:
        frac = len(traceable) / len(observed)
        out["numerical_traceability"] = FactorResult(
            "numerical_traceability", table_rating(frac, T["numerical_traceability_fraction"]),
            "%d/%d 个有数因子带 accession+期间+数值" % (len(traceable), len(observed)), (), "OBSERVED", frac)
    else:
        out["numerical_traceability"] = no_evidence("numerical_traceability", "没有任何有数因子")

    if f.latest_period_age_days is not None and f.latest_periodic is not None:
        row = f.latest_periodic
        ref = EvidenceRef(kind="xbrl", label="latest periodic filing %s period %s" % (row["form"], row["report_date"]),
                          accession=row["accession"], form=row["form"], filed=row["filed"], period_end=row["report_date"],
                          value=float(f.latest_period_age_days),
                          url=(("https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (
                              f.cik, row["accession"].replace("-", ""), row["primary_document"]))
                               if row.get("primary_document") and "/" not in row["primary_document"] else row["source_url"]))
        out["freshness"] = FactorResult("freshness", table_rating(f.latest_period_age_days, T["freshness_period_age_days"]),
                                        "最近一份 %s 报告期 %s，距 as_of %d 天" % (row["form"], row["report_date"], f.latest_period_age_days),
                                        (ref,), "OBSERVED", float(f.latest_period_age_days))
    else:
        out["freshness"] = no_evidence("freshness", "没有 10-K/10-Q 申报清单")

    if f.revenue_ttm.ok:
        tripped: List[str] = []
        if f.restatement.ok and f.restatement.value > ef["restatement_threshold"]:
            tripped.append("营收重述幅度 %s" % _fmt(f.restatement.value, True))
        if "SINA_CAP_MISMATCH" in f.market.flags:
            tripped.append("SEC 与新浪市值相差 >20%")
        rpo_up, rev_down = ef["rpo_up_revenue_down"]
        if f.rpo_yoy.ok and f.revenue_yoy.ok and f.rpo_yoy.value >= rpo_up and f.revenue_yoy.value <= rev_down:
            tripped.append("积压大增但营收下滑")
        rating = ef["contradiction_tripped_rating"] if tripped else ef["contradiction_clean_rating"]
        out["contradiction_search"] = FactorResult(
            "contradiction_search", rating, ("触发：" + "、".join(tripped)) if tripped else "自动一致性检查未触发（无人工反证搜索，最高给 3）",
            f.restatement.refs, "OBSERVED", float(len(tripped)))
    else:
        out["contradiction_search"] = no_evidence("contradiction_search", "没有营收，检查无从做起")
    out["source_independence"] = FactorResult("source_independence", ef["source_independence_rating"],
                                              FACTOR_SOURCES["source_independence"], (), "OBSERVED", None)
    return out


# ---- 持续期、桥、硬标记 ----------------------------------------------------------------
def duration_view(f: Fundamentals, p: dict) -> dict:
    """持续期：稀缺期 P50 无法从申报得到。RPO 覆盖月数只是「已合同化」的下界：
    下界够高时可以支持更高的乘数档位与「合同化斜坡」；下界低只说明合同没写那么长，不能证明稀缺期短，
    所以乘数取 max(下界档位, 未知时的保守值)，门 B 在下界不足时记 UNVERIFIED 而不是 FAIL。"""
    d = p["duration"]
    unknown = d["unknown_runway_multiplier"]
    if f.rpo_months.ok and f.revenue_ttm.ok and f.revenue_ttm.value > 0:
        lower_bound = f.rpo_months.value
        lag = d["monetization_lag_months_when_revenue_flowing"]
        runway_lb = lower_bound - lag
        idx = sum(runway_lb >= b for b in d["upper_bounds_months"])
        band = d["multipliers"][idx]
        ramp = lower_bound >= d["contracted_forward_ramp_min_months"]
        return {"status": "LOWER_BOUND_FROM_BACKLOG", "scarcity_p50_months_lower_bound": round(lower_bound, 2),
                "monetization_lag_months": lag, "monetizable_runway_months_lower_bound": round(runway_lb, 2),
                "contracted_forward_ramp": ramp, "band_multiplier": band,
                "multiplier": max(band, unknown),
                "supports_gate_b": runway_lb >= d["hard_gate_runway_months"] or ramp,
                "refs": [r.to_dict() for r in f.rpo_months.refs]}
    return {"status": NO_EVIDENCE, "scarcity_p50_months_lower_bound": None, "monetization_lag_months": None,
            "monetizable_runway_months_lower_bound": None, "contracted_forward_ramp": False, "band_multiplier": None,
            "multiplier": unknown, "supports_gate_b": False, "refs": []}


def equity_bridge(f: Fundamentals) -> dict:
    """营收桥：营收、自由现金流（经营现金流−资本开支）、每股口径。加权稀释股数缺失时退到 SEC 封面股数（候选池同源）。"""
    shares, shares_source = (f.diluted_shares.value, "diluted_weighted") if f.diluted_shares.ok else (f.market.shares, "sec_cover_shares")
    per_share = None
    if f.fcf_ttm.ok and shares and shares > 0:
        per_share = f.fcf_ttm.value / shares
    missing = [name for name, m in (("revenue", f.revenue_ttm), ("free_cash_flow", f.fcf_ttm)) if not m.ok]
    return {"complete": not missing and f.revenue_ttm.value > 0, "revenue_ttm": f.revenue_ttm.value,
            "free_cash_flow_ttm": f.fcf_ttm.value, "shares": shares, "shares_source": shares_source,
            "per_share_fcf": per_share, "missing": missing,
            "unverified_items": ["convertibles", "warrants", "other_contingent_shares", "working_capital", "interest", "tax"]}


# ---- 决策 ------------------------------------------------------------------------------
def _label_for(dim_results: Dict[str, DimensionResult], flags: Dict[str, Any], gates_cfg: dict, runway: dict,
               final_score: Optional[float], candidate_min: float, p: dict) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    g = gates_cfg

    def unverifiable(dim: str) -> bool:
        return not dim_results[dim].verifiable

    def add_unverifiable(dim: str) -> None:
        reasons.append("DIMENSION_UNVERIFIABLE:%s:%s" % (dim, dim_results[dim].reason))

    if flags["kill_switch_triggered"]:
        return "BROKEN", "FAILED", ["KILL_SWITCH_TRIGGERED"]
    if flags["unfunded_financing_gap"]:
        return "AVOID", "FAILED", ["HARD_FLAG:unfunded_financing_gap"]
    if flags["no_material_revenue_bridge"]:
        if flags["revenue_bridge_cause"] == "NO_REVENUE_OR_NONPOSITIVE":
            return "BOTTLENECK_NOT_EQUITY", "FAILED", ["HARD_FLAG:no_material_revenue_bridge:NO_REVENUE"]
        reasons.append("HARD_FLAG:no_material_revenue_bridge:%s" % flags["revenue_bridge_cause"])
    cap = dim_results["capture"]
    if cap.verifiable and cap.score < g["capture_min"]:
        return "BOTTLENECK_NOT_EQUITY", "FAILED", ["GATE_C_CAPTURE_BELOW_MIN:%.1f<%s" % (cap.score, g["capture_min"])]
    if unverifiable("capture"):
        add_unverifiable("capture")

    if flags.get("no_primary_evidence"):
        reasons.append("HARD_FLAG:no_primary_evidence")
    ev = dim_results["evidence"]
    if ev.verifiable and ev.score < g["evidence_min"]:
        reasons.append("EVIDENCE_BELOW_MIN:%.1f<%s" % (ev.score, g["evidence_min"]))
    if unverifiable("evidence"):
        add_unverifiable("evidence")

    con = dim_results["constraint"]
    if con.verifiable and con.score < g["constraint_min"]:
        reasons.append("GATE_A_CONSTRAINT_BELOW_MIN:%.1f<%s" % (con.score, g["constraint_min"]))
    if unverifiable("constraint"):
        add_unverifiable("constraint")

    inv = dim_results["investability"]
    if inv.verifiable and inv.score < g["investability_min"]:
        return "AVOID", "FAILED", ["INVESTABILITY_BELOW_MIN:%.1f<%s" % (inv.score, g["investability_min"])]
    if unverifiable("investability"):
        add_unverifiable("investability")

    # 门 B（稀缺持续）：Skill 的硬门是「真实可变现跑道 <6 个月且没有合同化斜坡」。跑道只能得到下界，
    # 下界不足不能证明跑道短，所以这里永远不会凭下界阻断；门 B 不能验证时记 UNVERIFIED，由乘数承担保守处理。
    mis = dim_results["mispricing"]
    if mis.verifiable and mis.score < g["mispricing_min"]:
        reasons.append("GATE_D_MISPRICING_BELOW_MIN:%.1f<%s" % (mis.score, g["mispricing_min"]))
    if unverifiable("mispricing"):
        add_unverifiable("mispricing")

    if reasons:
        first = reasons[0]
        label = "WATCH_PRICED" if first.startswith("GATE_D") else "WATCH_EVIDENCE"
        return label, "ABSTAIN", reasons
    if final_score is not None and final_score >= candidate_min:
        return "CANDIDATE", "PASS", ["ALL_GATES_PASSED:final=%.1f>=%s" % (final_score, candidate_min),
                                     "SCENARIO_ASYMMETRY_NO_EVIDENCE:RESEARCH_PRIORITY_UNREACHABLE"]
    return "WATCH_EVIDENCE", "ABSTAIN", ["COMPOSITE_BELOW_CANDIDATE:%s<%s" % (
        "n/a" if final_score is None else "%.1f" % final_score, candidate_min)]


def _gate_summary(dims: Dict[str, DimensionResult], runway: dict, g: dict, p: dict) -> dict:
    def gate(dim: str, threshold: float) -> dict:
        d = dims[dim]
        if not d.verifiable:
            return {"status": "UNVERIFIED", "score": None if d.score is None else round(d.score, 1), "threshold": threshold,
                    "reason": d.reason}
        return {"status": "PASS" if d.score >= threshold else "FAIL", "score": round(d.score, 1), "threshold": threshold}

    if runway["supports_gate_b"]:
        b = {"status": "PASS", "runway_months_lower_bound": runway["monetizable_runway_months_lower_bound"],
             "contracted_forward_ramp": runway["contracted_forward_ramp"]}
    else:
        b = {"status": "UNVERIFIED", "reason": "scarcity duration not observable from filings (RPO horizon is only a lower bound)"}
    return {"A_constraint_reality": gate("constraint", g["constraint_min"]), "B_scarcity_duration": b,
            "C_rent_capture": gate("capture", g["capture_min"]), "D_mispricing": gate("mispricing", g["mispricing_min"]),
            "evidence_min": gate("evidence", g["evidence_min"]), "investability_min": gate("investability", g["investability_min"])}


def score_bottleneck(store: FactStore, market: MarketInput, as_of: str, params: Optional[dict] = None,
                     findings: Optional[List[dict]] = None, peers: Optional[PeerContext] = None,
                     text: Optional[TextMarkers] = None, fundamentals: Optional[Fundamentals] = None,
                     structure: Optional[StructureEvidence] = None) -> Receipt:
    """对一只股票、在 as_of 这一天的可见事实上打分。fundamentals 若传入必须是同一个 as_of 算出来的。"""
    if params is None:
        params, findings = load_bottleneck_params()
    if fundamentals is None:
        fundamentals = compute_fundamentals(store, market, as_of)
    elif fundamentals.as_of != as_of:
        raise ValueError("fundamentals.as_of %s != as_of %s" % (fundamentals.as_of, as_of))
    f = fundamentals
    if text is not None and text.filed > as_of:
        raise ValueError("text markers filed %s are after as_of %s" % (text.filed, as_of))
    if structure is not None and structure.latest_filed is not None and structure.latest_filed > as_of:
        raise ValueError("structure extraction filed %s is after as_of %s" % (structure.latest_filed, as_of))
    p = params

    factors: Dict[str, Dict[str, FactorResult]] = {
        "constraint": constraint_factors(f, text, p, structure),
        "capture": capture_factors(f, p),
        "mispricing": mispricing_factors(f, peers, p),
        "investability": investability_factors(f, p, structure),
    }
    factors["evidence"] = evidence_factors(f, factors, p)

    dims: Dict[str, DimensionResult] = {}
    for dim in DIMENSIONS:
        dims[dim] = aggregate_dimension(dim, factors[dim], p["dimension_weights"][dim], 5.0,
                                        p["coverage"]["min_by_dimension"][dim], p["coverage"]["required_factors"][dim])

    runway = duration_view(f, p)
    bridge = equity_bridge(f)
    flags = hard_flags_v2(f, bridge, factors, p)

    verifiable_scores = [d.score for d in dims.values() if d.verifiable]
    all_ok = len(verifiable_scores) == len(DIMENSIONS)
    floor = p["geometric_mean_floor"]
    core = geometric_mean(verifiable_scores, floor) if all_ok else None
    partial = geometric_mean(verifiable_scores, floor) if verifiable_scores else None
    multiplier = runway["multiplier"] * p["asymmetry"]["unavailable_multiplier"]
    final = clamp(core * multiplier, 0.0, 100.0) if core is not None else None
    indicative = (partial * multiplier * len(verifiable_scores) / len(DIMENSIONS)) if partial is not None else None

    label, verdict, reasons = _label_for(dims, flags, p["gates"], runway, final, p["gates"]["candidate_min_final"], p)

    links = collect_primary_links(factors, text)
    if verdict == "PASS" and not links:
        verdict, label = "ABSTAIN", "WATCH_EVIDENCE"
        reasons = ["PASS_REQUIRES_PRIMARY_SEC_LINK"] + reasons
    if findings:
        reasons = reasons + ["PARAMS_FINDING:" + item["code"] for item in findings]

    detail = {
        "market_cap_usd": f.market.market_cap, "price_usd": f.market.price,
        "dimensions": {dim: dims[dim].to_dict() for dim in DIMENSIONS},
        "factors": {dim: {name: fr.to_dict() for name, fr in factors[dim].items()} for dim in DIMENSIONS},
        "gates": _gate_summary(dims, runway, p["gates"], p),
        "hard_flags": flags,
        "core_quality": None if core is None else round(core, 3),
        "duration": runway,
        "scenario_asymmetry": {"status": NO_EVIDENCE, "multiplier": p["asymmetry"]["unavailable_multiplier"]},
        "final_score": None if final is None else round(final, 3),
        "indicative_score": None if indicative is None else round(indicative, 3),
        "gate_margin": round(gate_margin(dims, p["gates"]), 4),
        "rank_key": rank_key(verdict, final, gate_margin(dims, p["gates"])),
        "equity_bridge": bridge,
        "text_markers": None if text is None else text.to_dict(),
        "structure_text": None if structure is None else SF.summary(structure),
        "primary_links": links,
        "no_evidence_ratio": _ne_ratio(factors),
        "params_version": p["params_version"],
        "params_findings": findings or [],
    }
    return Receipt(f.symbol, f.cik, f.name, as_of, verdict, label, reasons, detail)


def hard_flags_v2(f: Fundamentals, bridge: dict, factors: Dict[str, Dict[str, FactorResult]], p: dict) -> Dict[str, Any]:
    flags: Dict[str, Any] = {
        "kill_switch_triggered": False,
        "wrong_entity_or_ticker": "NOT_EVALUATED",
        "substitution_before_monetization": "NOT_EVALUATED",
        "bull_case_required_to_avoid_loss": "NOT_EVALUATED",
    }
    flags["no_material_revenue_bridge"] = (not bridge["complete"]) or (f.revenue_ttm.ok and f.revenue_ttm.value <= 0)
    if f.revenue_ttm.ok and f.revenue_ttm.value <= 0:
        flags["revenue_bridge_cause"] = "NO_REVENUE_OR_NONPOSITIVE"
    elif bridge["missing"]:
        flags["revenue_bridge_cause"] = "DATA_MISSING:" + ",".join(bridge["missing"])
    else:
        flags["revenue_bridge_cause"] = None
    flags["unfunded_financing_gap"] = bool(f.cash_runway_months.ok and f.cash_runway_months.value < p["financing_gap_runway_months"])
    claims = p["evidence_factors"]["critical_claims"]
    flags["no_primary_evidence"] = not any(
        factors["constraint"].get(c, factors["capture"].get(c)).observed and
        any(ref.is_primary_link for ref in factors["constraint"].get(c, factors["capture"].get(c)).refs)
        for c in claims)
    return flags


def collect_primary_links(factors: Dict[str, Dict[str, FactorResult]], text: Optional[TextMarkers], limit: int = 8) -> List[dict]:
    seen: Dict[str, dict] = {}
    priority = ("funded_demand", "current_tightness", "pricing_power", "unit_economics", "valuation_asymmetry",
                "balance_sheet_survival", "expansion_lead_time", "qualification_barrier", "supplier_concentration",
                "customer_diversification", "technology_resilience", "freshness")
    ordered = [(dim, name) for name in priority for dim in factors if name in factors[dim]]
    ordered += [(dim, name) for dim in factors for name in factors[dim] if name not in priority]
    for dim, name in ordered:
        fr = factors[dim][name]
        for ref in fr.refs:
            if ref.is_primary_link and ref.url not in seen:
                seen[ref.url] = {"url": ref.url, "accession": ref.accession, "form": ref.form, "filed": ref.filed,
                                 "period_end": ref.period_end, "supports": name, "label": ref.label}
    return list(seen.values())[:limit]


def _ne_ratio(factors: Dict[str, Dict[str, FactorResult]]) -> dict:
    per_dim = {}
    for dim, fs in factors.items():
        per_dim[dim] = {"no_evidence": sum(not fr.observed for fr in fs.values()), "total": len(fs)}
    total = sum(v["total"] for v in per_dim.values())
    ne = sum(v["no_evidence"] for v in per_dim.values())
    return {"per_dimension": per_dim, "overall": round(ne / total, 4) if total else None}


def gate_margin(dims: Dict[str, DimensionResult], gates: dict) -> float:
    """非补偿排序用：五个门里「离通过最远」的那个的达标比例（不可核实的门记 0）。越接近 1 越接近同时过所有门。"""
    thresholds = {"constraint": gates["constraint_min"], "capture": gates["capture_min"], "evidence": gates["evidence_min"],
                  "investability": gates["investability_min"], "mispricing": gates["mispricing_min"]}
    return min((dims[d].score / t) if dims[d].verifiable else 0.0 for d, t in thresholds.items())


def rank_key(verdict: str, final: Optional[float], margin: float) -> float:
    """排序用（不是模型分数）：PASS 在前按最终分；其余按「最差的门离通过多远」排，FAILED 垫底。"""
    if verdict == "PASS":
        return 3000.0 + (final or 0.0)
    return (1000.0 if verdict == "ABSTAIN" else 0.0) + 100.0 * margin + (final or 0.0) / 100.0
