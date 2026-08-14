from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .clock import sydney_date
from .config import Settings
from .metrics import relative_path
from .models import Candidate, Metrics, SkillResult

BROAD_BUCKETS = {"us_broad", "developed_ex_us", "emerging_markets", "global_broad"}
NON_PRICE_FAMILIES = {"商业捕获", "瓶颈与稀缺", "离散事件", "综合基本面"}


@dataclass
class DecisionOutcome:
    public: dict[str, Any]
    updated_state: dict[str, Any]
    internal: dict[str, Any]


def _last_price(candidate: Candidate | None, state: dict[str, Any]) -> float:
    if candidate and candidate.price and candidate.price > 0:
        return float(candidate.price)
    if candidate and candidate.bars:
        try:
            value = float(candidate.bars[-1].get("close", 0.0))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return float(state.get("last_price") or state.get("reference_price") or 0.0)


def _direction(candidate: Candidate) -> str:
    if candidate.inverse:
        return "看跌"
    if candidate.bucket_id in {"cash_alternative", "rates_credit"}:
        return "防御"
    return "看涨"


def _path(candidate: Candidate) -> str:
    if candidate.bucket_id == "cash_alternative":
        return "cash"
    if candidate.inverse or candidate.bucket_id == "rates_credit":
        return "defensive"
    return "bullish"


def _candidate_support(candidate: Candidate, skills: list[SkillResult]) -> tuple[set[str], set[str]]:
    supporting: set[str] = set()
    opposing: set[str] = set()
    for row in skills:
        finding = row.candidate_conclusions.get(candidate.provider_code)
        if finding == "支持":
            supporting.add(row.family)
        elif finding == "反对":
            opposing.add(row.family)
    return supporting, opposing


def _best_reference(
    candidates: list[Candidate], metrics: dict[str, Metrics], bucket_ids: set[str], exclude_code: str
) -> Candidate | None:
    ranked: list[tuple[float, Candidate]] = []
    for candidate in candidates:
        if candidate.provider_code == exclude_code or candidate.bucket_id not in bucket_ids:
            continue
        metric = metrics.get(candidate.provider_code)
        value = metric.returns_pct.get("60") if metric else None
        if value is not None:
            ranked.append((float(value), candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _qualifies(
    candidate: Candidate,
    metric: Metrics,
    settings: Settings,
    skills: list[SkillResult],
    candidates: list[Candidate],
    metrics: dict[str, Metrics],
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    lower60 = metric.relative_stress_lower_pct.get("60")
    lower20 = metric.relative_stress_lower_pct.get("20")
    effective_tier = 3 if candidate.inverse or candidate.leveraged else candidate.risk_tier

    if not candidate.platform_verified:
        reasons.append("平台产品证据不足")
    if candidate.liquidity_score <= 0.05:
        reasons.append("流动性资格不足")
    if lower60 is None:
        reasons.append("缺少60日相对价格链")
    elif float(lower60) <= settings.switch_gate_pct:
        reasons.append("60日保守下界未越切换门")
    if lower20 is None or float(lower20) < settings.tactical_floor_pct:
        reasons.append("20日战术约束未通过")

    supporting, opposing = _candidate_support(candidate, skills)
    evidence["supporting_families"] = sorted(supporting)
    evidence["opposing_families"] = sorted(opposing)
    evidence["effective_risk_tier"] = effective_tier

    if effective_tier >= 2:
        if len(supporting) < 2:
            reasons.append("独立方法家族不足")
        if not supporting.intersection(NON_PRICE_FAMILIES):
            reasons.append("缺少候选级非价格方法支持")
        absolute60 = metric.returns_pct.get("60")
        if absolute60 is None or float(absolute60) <= 0:
            reasons.append("风险候选60日收益未通过")

        broad = _best_reference(candidates, metrics, BROAD_BUCKETS, candidate.provider_code)
        cash = _best_reference(candidates, metrics, {"cash_alternative", "rates_credit"}, candidate.provider_code)
        if broad is not None:
            broad_rel, broad_lower = relative_path(candidate, broad, 60)
            evidence["relative_to_best_broad_pct"] = broad_rel
            evidence["stress_lower_to_best_broad_pct"] = broad_lower
            if broad_lower is None or float(broad_lower) <= settings.switch_gate_pct:
                reasons.append("未以保守下界净胜普通宽基")
        else:
            reasons.append("缺少可比普通宽基")
        if cash is not None:
            cash_rel, cash_lower = relative_path(candidate, cash, 60)
            evidence["relative_to_cash_pct"] = cash_rel
            evidence["stress_lower_to_cash_pct"] = cash_lower
            if cash_lower is None or float(cash_lower) <= settings.switch_gate_pct:
                reasons.append("未以保守下界净胜现金或低风险")
        else:
            reasons.append("缺少现金或低风险比较路径")

    if effective_tier >= 3:
        if not (candidate.leveraged or candidate.inverse):
            reasons.append("第三层路径属性不完整")
        if not candidate.path_dependency_verified:
            reasons.append("日重置与路径损耗证据不足")
        if metric.max_drawdown_pct.get("60") is None:
            reasons.append("第三层压力输入不足")

    return not reasons, reasons, evidence


def _path_frontiers(
    candidates: list[Candidate], metrics: dict[str, Metrics], incumbent_code: str
) -> dict[str, dict[str, Any] | None]:
    frontiers: dict[str, dict[str, Any] | None] = {"bullish": None, "defensive": None, "cash": None}
    for candidate in candidates:
        if candidate.provider_code == incumbent_code:
            continue
        metric = metrics.get(candidate.provider_code)
        lower = metric.relative_stress_lower_pct.get("60") if metric else None
        if lower is None:
            continue
        path = _path(candidate)
        current = frontiers[path]
        if current is None or float(lower) > float(current["lower60"]):
            frontiers[path] = {
                "candidate": candidate,
                "metric": metric,
                "lower60": float(lower),
            }
    return frontiers



def _one_decimal(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

def _fmt(value: float | None) -> str:
    return "缺失" if value is None else f"{value:+.2f}%"


def decide(
    settings: Settings,
    now: datetime,
    candidates: list[Candidate],
    metrics: dict[str, Metrics],
    current_state: dict[str, Any],
    skills: list[SkillResult],
    market_context: dict[str, Any],
) -> DecisionOutcome:
    by_code = {candidate.provider_code: candidate for candidate in candidates}
    incumbent_code = str(current_state["provider_code"])
    incumbent = by_code.get(incumbent_code)
    price = _last_price(incumbent, current_state)
    previous_high = float(current_state.get("high_water") or current_state.get("reference_price") or price)
    high_water = max(previous_high, price) if price > 0 else previous_high
    observable_drawdown = (
        max(0.0, (high_water - price) / high_water * 100.0)
        if high_water > 0 and price > 0
        else float(current_state.get("observable_drawdown_pct", 0.0))
    )
    risk_adjusted = min(100.0, observable_drawdown + settings.reserve_pct)
    remaining_budget = max(0.0, settings.hard_failure_drawdown_pct - risk_adjusted)

    path_frontiers = _path_frontiers(candidates, metrics, incumbent_code)
    qualification: dict[str, dict[str, Any]] = {}
    eligible: list[tuple[float, Candidate, Metrics]] = []
    for path_name, frontier in path_frontiers.items():
        if not frontier:
            continue
        candidate = frontier["candidate"]
        metric = frontier["metric"]
        passed, reasons, evidence = _qualifies(candidate, metric, settings, skills, candidates, metrics)
        qualification[path_name] = {
            "provider_code": candidate.provider_code,
            "passed": passed,
            "reasons": reasons,
            "evidence": evidence,
            "lower60": frontier["lower60"],
        }
        if passed:
            eligible.append((float(frontier["lower60"]), candidate, metric))

    eligible.sort(key=lambda item: item[0], reverse=True)
    best_tuple = eligible[0] if eligible else None
    best = best_tuple[1] if best_tuple else None
    best_metric = best_tuple[2] if best_tuple else None

    operation = "持有"
    winner = incumbent
    direction = str(current_state.get("direction", "看涨"))
    run_state = "正常"
    continuity = "完整状态"
    live_decision_inputs = market_context.get("provider_state") == "live"
    if not live_decision_inputs:
        run_state = "降级持有"
    if market_context.get("state_conflict"):
        continuity = "冲突状态"
        run_state = "基线重试"
    if not market_context.get("state_loaded", True):
        continuity = "首次建基线"

    if risk_adjusted >= settings.hard_failure_drawdown_pct:
        operation = "退出"
        winner = None
        direction = "退出"
        run_state = "策略失效"
    elif live_decision_inputs and best is not None:
        operation = "切换至"
        winner = best
        direction = _direction(best)

    updated = dict(current_state)
    if winner is None:
        updated.update({
            "platform": "无",
            "name": "无",
            "code": "无",
            "provider_code": "NONE",
            "direction": "退出",
            "allocation_pct": 0.0,
            "observable_drawdown_pct": round(observable_drawdown, 4),
            "risk_adjusted_drawdown_pct": round(risk_adjusted, 4),
            "high_water": high_water,
            "last_price": price,
            "last_updated": now.isoformat(),
        })
    elif operation == "切换至":
        new_price = _last_price(winner, current_state)
        updated = {
            "schema_version": "1.0.0",
            "prompt_version": settings.prompt_version,
            "platform": "MooMooAU",
            "name": winner.name,
            "code": winner.public_code,
            "provider_code": winner.provider_code,
            "direction": direction,
            "allocation_pct": 100.0,
            "channel": "ASX" if winner.market == "AU" else winner.market,
            "currency": winner.currency,
            "reference_price": new_price,
            "high_water": new_price,
            "observable_drawdown_pct": 0.0,
            "risk_adjusted_drawdown_pct": settings.reserve_pct,
            "established_at": now.isoformat(),
            "main_window_trading_days": 60,
            "tactical_window_trading_days": 20,
            "shadow_only": True,
            "last_price": new_price,
            "last_updated": now.isoformat(),
        }
        observable_drawdown = 0.0
        risk_adjusted = settings.reserve_pct
        remaining_budget = settings.hard_failure_drawdown_pct - risk_adjusted
    else:
        updated.update({
            "high_water": high_water,
            "observable_drawdown_pct": round(observable_drawdown, 4),
            "risk_adjusted_drawdown_pct": round(risk_adjusted, 4),
            "last_price": price,
            "last_updated": now.isoformat(),
        })

    if winner is None:
        final_name, final_code, final_platform = "无", "无", "无"
    elif operation == "持有":
        final_name = str(current_state.get("name", winner.name))
        final_code = str(current_state.get("code", winner.public_code))
        final_platform = str(current_state.get("platform", "MooMooAU"))
    else:
        final_name, final_code, final_platform = winner.name, winner.public_code, "MooMooAU"
    incumbent_metric = metrics.get(incumbent_code)
    incumbent_r20 = incumbent_metric.returns_pct.get("20") if incumbent_metric else None
    incumbent_r60 = incumbent_metric.returns_pct.get("60") if incumbent_metric else None
    incumbent_r120 = incumbent_metric.returns_pct.get("120") if incumbent_metric else None

    strongest_frontier = max(
        (frontier for frontier in path_frontiers.values() if frontier),
        key=lambda row: float(row["lower60"]),
        default=None,
    )
    strongest_metric = strongest_frontier["metric"] if strongest_frontier else None
    strongest_lower = strongest_metric.relative_stress_lower_pct.get("60") if strongest_metric else None
    strongest_rel60 = strongest_metric.relative_returns_pct.get("60") if strongest_metric else None

    if operation == "切换至" and best_metric is not None:
        lower = best_metric.relative_stress_lower_pct.get("60")
        lower20 = best_metric.relative_stress_lower_pct.get("20")
        basis = (
            f"截至{sydney_date(now)}，挑战路径20/60日非概率压力下界{_fmt(lower20)}/{_fmt(lower)}，"
            f"60日已越过{settings.switch_gate_pct:.2f}%完整切换门，扣除摩擦后成为唯一稳健赢家"
            "【只读行情】【六技能方法契约】【V19状态账本】。"
        )
        now_action = "仅在影子账本原子替换为本轮唯一100.0%赢家，不产生任何真实交易副作用。"
    elif operation == "退出":
        basis = (
            f"截至{sydney_date(now)}，风险调整回撤达到{risk_adjusted:.1f}%硬失效阈值，"
            "当前策略失效并仅在影子账本退出【只读行情】【V19风险门】。"
        )
        now_action = "仅在影子账本记录退出为0.0%，不产生任何真实交易副作用。"
    else:
        anchors = [
            f"20日{incumbent_r20:+.2f}%" if incumbent_r20 is not None else "20日缺失",
            f"60日{incumbent_r60:+.2f}%" if incumbent_r60 is not None else "60日缺失",
            f"挑战60日压力下界{strongest_lower:+.2f}%" if strongest_lower is not None else "挑战60日压力下界缺失",
        ]
        strongest_path_name = _path(strongest_frontier["candidate"]) if strongest_frontier else None
        strongest_check = qualification.get(strongest_path_name, {}) if strongest_path_name else {}
        strongest_reasons = [str(value) for value in strongest_check.get("reasons", [])]
        if strongest_lower is not None and strongest_lower > settings.switch_gate_pct and strongest_reasons:
            gate_explanation = "价格压力下界已越数值门，但未同时通过" + "、".join(strongest_reasons[:2])
        else:
            gate_explanation = f"挑战压力下界仍未越过{settings.switch_gate_pct:.2f}%完整切换门"
        basis = (
            f"截至{sydney_date(now)}，{'、'.join(anchors)}；{gate_explanation}，"
            "现金/低风险机会成本未净胜，因此宽基继续胜出"
            "【只读行情】【六技能方法契约】【V19状态账本】。"
        )
        now_action = "仅在影子账本维持当前100.0%配置，不产生任何真实交易副作用。"

    if strongest_rel60 is not None and strongest_lower is not None:
        strongest_path_name = _path(strongest_frontier["candidate"]) if strongest_frontier else None
        strongest_reasons = [
            str(value) for value in qualification.get(strongest_path_name, {}).get("reasons", [])
        ] if strongest_path_name else []
        remaining_gate = "并补齐其余风险与非价格硬门" if strongest_reasons else "并持续越过完整切换门"
        counter = (
            f"最强挑战仍有{strongest_rel60:+.2f}%的60日历史相对收益且压力后下界为{strongest_lower:+.2f}%；"
            f"若连续PIT证据{remaining_gate}，现行赢家应被推翻。"
        )
    else:
        counter = "市场、事件或非价格证据若出现方向性恶化，当前保守净增长优势可能消失。"

    event_cutoff = str(market_context.get("event_cutoff", "截至本轮已公开事件"))
    data_cutoff = (
        f"美国证券={market_context.get('us_cutoff', '最近有效常规收盘')}；"
        f"中国基金={market_context.get('china_cutoff', '最近可定位净值')}；"
        f"汇率={market_context.get('fx_cutoff', '最近正式值')}；事件={event_cutoff}"
    )
    coverage = str(market_context.get("coverage", "最低可行"))
    method_complete = len(skills) == 6 and all(
        row.applicable and row.run_mode in {"方法契约", "原生运行"} for row in skills
    )
    if coverage == "阻断":
        adjudication = "阻断"
    elif not live_decision_inputs:
        adjudication = "降级裁决"
    else:
        adjudication = "方法完整" if method_complete else "最低可行"
    applicable = sum(1 for row in skills if row.applicable)
    participated = sum(1 for row in skills if row.applicable and row.run_mode in {"方法契约", "原生运行"})
    native = sum(1 for row in skills if row.run_mode == "原生运行")
    coverage_pct = participated / applicable * 100.0 if applicable else 0.0

    central_quant = (
        "已运行；"
        f"现行20/60/120日收益={_fmt(incumbent_r20)}/{_fmt(incumbent_r60)}/{_fmt(incumbent_r120)}，"
        f"最强挑战60日历史相对收益={_fmt(strongest_rel60)}，"
        f"压力后下界={_fmt(strongest_lower)}，完整切换门={settings.switch_gate_pct:.2f}%，"
        f"可观察/风险调整回撤={observable_drawdown:.2f}%/{risk_adjusted:.2f}%。"
    )

    displayed_observable = _one_decimal(observable_drawdown)
    displayed_risk = _one_decimal(risk_adjusted)
    displayed_remaining = max(0.0, _one_decimal(settings.hard_failure_drawdown_pct - displayed_risk))

    public = {
        "运行时间": "",
        "提示词版本": settings.prompt_version,
        "运行状态": run_state,
        "市场覆盖": coverage,
        "数据截止": data_cutoff,
        "状态连续性": continuity,
        "裁决完整性": adjudication,
        "技能适用覆盖率": f"{coverage_pct:.1f}%",
        "第一板块": {
            "唯一操作": operation,
            "唯一平台": final_platform,
            "唯一标的": final_name,
            "代码": final_code,
            "唯一方向": direction,
            "可观察回撤": f"{displayed_observable:.1f}%",
            "风险调整回撤": f"{displayed_risk:.1f}%",
            "剩余回撤预算": f"{displayed_remaining:.1f}%",
            "预期研究窗口": "60交易日主窗；20交易日战术复核",
            "相对宽基": "宽基为赢家" if winner and winner.bucket_id == "us_broad" else "稳健占优" if winner else "未通过",
            "相对现金": "现金为赢家" if winner and winner.bucket_id == "cash_alternative" else "稳健占优" if winner else "未通过",
            "现在怎么做": now_action,
            "核心依据": basis,
            "最大反证": counter,
            "失效条件": "风险调整回撤达到20.0%即硬失效。",
            "下一正式复核": "",
        },
        "第二板块": {
            "矩阵": [row.to_public_row() for row in skills],
            "适用技能": f"{applicable}/6",
            "实际参与": f"{participated}/{applicable}",
            "适用覆盖率": f"{coverage_pct:.1f}%",
            "原生参与": f"{native}/{applicable}",
            "原生覆盖率": f"{(native / applicable * 100.0) if applicable else 0.0:.1f}%",
            "中央定量审查": central_quant,
            "权重说明": "总体权重合计100.0%仅表示实际参与方法内部权重，不代表六技能覆盖率、共识率或收益概率。",
        },
    }
    return DecisionOutcome(
        public=public,
        updated_state=updated,
        internal={
            "path_frontiers": {
                path: ({
                    "provider_code": row["candidate"].provider_code,
                    "lower60": row["lower60"],
                } if row else None)
                for path, row in path_frontiers.items()
            },
            "qualification": qualification,
            "selected_challenger_code": best.provider_code if best else None,
            "switch_gate_pct": settings.switch_gate_pct,
            "skills": [row.to_dict() for row in skills],
            "metrics": {code: value.to_dict() for code, value in metrics.items()},
            "market_context": market_context,
        },
    )
