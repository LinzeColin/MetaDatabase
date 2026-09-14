"""Stage 2 分支结论的确定性汇总中枢。

这个模块只消费已经生成的 ``BranchVerdict``，不改变分支实现状态或回测门。
Stage 3 会在这些门之后提供可复算的贡献度权重。
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable, Sequence

if TYPE_CHECKING:
    from .branches.models import BranchVerdict


WEIGHT_MODE = "COLD_START_EQUAL"
WEIGHT_SAMPLE_COUNT = 0
PROFITABILITY_STATUS = "NOT_PRODUCED_STAGE_2_NO_BACKTEST"

# 0.60 表示参与结论平均至少提供六成公式置信度，才把“中性”解读为较强的
# 一致性；低于它时，“观望”明确表示证据不足，而不是隐藏方向。
NEUTRAL_WATCH_CONFIDENCE_THRESHOLD = 0.60

_DIRECTIONS = ("看涨", "中性", "看跌")

# 展示层按这个枚举给结论上色（涨绿、跌红、观望琥珀、无结论琥珀）。方向字段本身
# 是中文文案，改一次文案就会让所有颜色静默失效，所以颜色只绑定这份机器码。
ACTION_CODES: dict[str | None, str] = {
    "看涨": "BULLISH",
    "看跌": "BEARISH",
    "观望": "NEUTRAL_WATCH",
    None: "NONE",
}


def resolve_action_code(action: str | None) -> str:
    """把中文动作文案翻译成展示层使用的稳定机器码。"""
    try:
        return ACTION_CODES[action]
    except KeyError:
        raise ValueError(f"UNKNOWN_DECISION_ACTION:{action}") from None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _weighting_metadata(weighting: dict[str, Any] | None) -> dict[str, Any]:
    """统一取得权重元数据；直接调用聚合函数时保持 Stage 2 冷启动兼容。"""
    if weighting is None:
        return {
            "weight_mode": WEIGHT_MODE,
            "weight_sample_count": WEIGHT_SAMPLE_COUNT,
        }
    return {
        "weight_mode": str(weighting["weight_mode"]),
        "weight_sample_count": int(weighting["weight_sample_count"]),
    }


def _exclusion_reason(verdict: BranchVerdict) -> str:
    """将现有参与状态转为每个标的可审计的排除原因。"""
    labels = {
        "UNIMPLEMENTED": "分支尚未实现",
        "OUT_OF_STRATEGY_UNIVERSE": "该标的不在策略资产池",
        "CONFIGURED_UNIVERSE_INCOMPLETE": "配置资产池不完整",
        "SAMPLE_INSUFFICIENT": "日线样本不足",
        "BACKTEST_CONFIG_UNAVAILABLE": "没有可绑定到当前 as-of 的已评价训练窗参数",
        "EXCLUDED_PENDING_BACKTEST": "尚未通过回测推广门",
    }
    label = labels.get(verdict.participation_status, "当前权重为 0")
    return f"{label}：{verdict.counter_evidence}"


def _dedupe_text(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _resolve_direction(contributors: Sequence[BranchVerdict]) -> tuple[str, dict[str, float], str]:
    """按权重投票并用保守规则处理平票。

    平票时不存在可信的方向优势：只要最高票出现并列，统一裁决为“中性”。
    这同时覆盖“看涨/看跌”互相抵消及“中性”与任一方向并列，且不依赖
    输入顺序或随机数。
    """
    votes = {direction: 0.0 for direction in _DIRECTIONS}
    for verdict in contributors:
        if verdict.direction not in votes:
            raise ValueError(f"UNKNOWN_PARTICIPATING_DIRECTION:{verdict.direction}")
        votes[verdict.direction] += verdict.weight

    highest_weight = max(votes.values())
    winners = [direction for direction in _DIRECTIONS if votes[direction] == highest_weight]
    if len(winners) == 1:
        return winners[0], votes, "UNIQUE_WEIGHTED_WINNER"
    return "中性", votes, "TIED_HIGHEST_WEIGHT_RESOLVED_TO_NEUTRAL"


def aggregate_symbol_verdicts(
    symbol: str,
    verdicts: Sequence[BranchVerdict],
    *,
    weighting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """合成单一标的的所有分支结论。

    置信度公式为 ``sum(confidence_i * weight_i) / sum(weight_i)``；方向投票
    使用同一组原始权重。所有 ``weight == 0`` 的结论保留在排除清单中。
    """
    weight_metadata = _weighting_metadata(weighting)
    symbol_verdicts = [verdict for verdict in verdicts if verdict.symbol == symbol]
    contributors = [verdict for verdict in symbol_verdicts if verdict.weight > 0.0]
    excluded = [verdict for verdict in symbol_verdicts if verdict.weight <= 0.0]
    excluded_details = [
        {
            "branch_id": verdict.branch_id,
            "participation_status": verdict.participation_status,
            "implemented": verdict.implemented,
            "weight": verdict.weight,
            "reason": _exclusion_reason(verdict),
        }
        for verdict in excluded
    ]

    if not contributors:
        return {
            "symbol": symbol,
            "direction": "不适用",
            "confidence": 0.0,
            "conviction": 0.0,
            "direction_vote_share": 0.0,
            "direction_vote_weights": {direction: 0.0 for direction in _DIRECTIONS},
            "tie_breaker": "NO_PARTICIPATING_BRANCH",
            **weight_metadata,
            "participating_branch_count": 0,
            "excluded_branch_count": len(excluded_details),
            "participating_branches": [],
            "excluded_branches": excluded_details,
            "counter_evidence": "没有参与加权的分支，不能形成标的级反证比较。",
            "invalidation": "至少一个分支获得正权重后，按同一汇总公式重新计算。",
            "message": "有数据，但该标的没有可参与加权的分支；不输出方向。",
        }

    total_weight = sum(verdict.weight for verdict in contributors)
    direction, vote_weights, tie_breaker = _resolve_direction(contributors)
    confidence = _clamp(
        sum(verdict.confidence * verdict.weight for verdict in contributors) / total_weight
    )
    winner_weight = (
        vote_weights[direction]
        if tie_breaker == "UNIQUE_WEIGHTED_WINNER"
        else max(vote_weights.values())
    )
    direction_vote_share = winner_weight / total_weight
    conviction = _clamp(confidence * direction_vote_share)
    participating_details = [
        {
            "branch_id": verdict.branch_id,
            "direction": verdict.direction,
            "confidence": verdict.confidence,
            "weight": verdict.weight,
            "normalized_weight": verdict.weight / total_weight,
            "participation_status": verdict.participation_status,
        }
        for verdict in contributors
    ]
    return {
        "symbol": symbol,
        "direction": direction,
        "confidence": confidence,
        "conviction": conviction,
        "direction_vote_share": direction_vote_share,
        "direction_vote_weights": vote_weights,
        "tie_breaker": tie_breaker,
        **weight_metadata,
        "participating_branch_count": len(participating_details),
        "excluded_branch_count": len(excluded_details),
        "participating_branches": participating_details,
        "excluded_branches": excluded_details,
        "counter_evidence": "；".join(_dedupe_text(verdict.counter_evidence for verdict in contributors)),
        "invalidation": "；".join(_dedupe_text(verdict.invalidation for verdict in contributors)),
        "message": "按正权重分支的加权投票与加权平均置信度生成；系统不自动交易。",
    }


def _group_decision_branches(verdicts: Sequence[BranchVerdict], participating: bool) -> list[dict[str, Any]]:
    """将逐标的 verdict 折叠为决策层可读的分支清单，保留符号和原因。"""
    groups: dict[tuple[str, str, str], list[BranchVerdict]] = defaultdict(list)
    for verdict in verdicts:
        if (verdict.weight > 0.0) != participating:
            continue
        reason = "" if participating else _exclusion_reason(verdict)
        groups[(verdict.branch_id, verdict.participation_status, reason)].append(verdict)

    records: list[dict[str, Any]] = []
    for (branch_id, participation_status, reason), items in sorted(groups.items()):
        weights = {item.weight for item in items}
        record: dict[str, Any] = {
            "branch_id": branch_id,
            "participation_status": participation_status,
            "symbols": sorted(item.symbol for item in items),
            "verdict_count": len(items),
        }
        if participating:
            record.update(
                {
                    "weight": items[0].weight if len(weights) == 1 else None,
                    "total_weight": sum(item.weight for item in items),
                }
            )
        else:
            record["reason"] = reason
        records.append(record)
    return records


def _neutral_conviction(contributors: Sequence[BranchVerdict]) -> float:
    total_weight = sum(verdict.weight for verdict in contributors)
    return _clamp(
        sum(verdict.confidence * verdict.weight for verdict in contributors) / total_weight
    )


def _build_decision(
    symbol_aggregates: Sequence[dict[str, Any]],
    verdicts: Sequence[BranchVerdict],
    *,
    weighting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从标的汇总生成组合层唯一建议，保留所有参与和排除事实。"""
    contributors = [verdict for verdict in verdicts if verdict.weight > 0.0]
    participating_branches = _group_decision_branches(verdicts, participating=True)
    excluded_branches = _group_decision_branches(verdicts, participating=False)
    common = {
        "participating_branches": participating_branches,
        "excluded_branches": excluded_branches,
        **_weighting_metadata(weighting),
    }

    if not contributors:
        exclusion_summary = "；".join(
            f"{item['branch_id']}（{item['participation_status']}）：{item['reason']}"
            for item in excluded_branches
        )
        return {
            "state": "NO_ELIGIBLE_BRANCH",
            "action": None,
            "primary_symbol": None,
            "conviction": 0.0,
            "conviction_formula": "无正权重分支，因此 conviction=0。",
            "rationale": f"数据已就绪，但没有可参与加权的分支。{exclusion_summary}",
            "internal_coordination": "未开始方向协调，因为所有分支均被权重门排除。",
            "counter_evidence": "没有参与加权的分支，不能给出方向性建议。",
            "invalidation": "任一分支完成其排除原因对应的前置条件并获得正权重后重新汇总。",
            **common,
        }

    directional = [
        item for item in symbol_aggregates if item["direction"] in {"看涨", "看跌"}
    ]
    if directional:
        # 同一 conviction 下先比较加权平均 confidence，仍相同才按 symbol 升序，
        # 所以多个方向性标的的主标的选择完全可复算。
        primary = sorted(
            directional,
            key=lambda item: (-item["conviction"], -item["confidence"], item["symbol"]),
        )[0]
        opposing = sorted(
            item["symbol"] for item in directional if item["direction"] != primary["direction"]
        )
        coordination = (
            f"主标的 {primary['symbol']} 的标的内加权投票为{primary['direction']}，"
            f"方向票占比 {primary['direction_vote_share']:.1%}，裁决规则为 {primary['tie_breaker']}。"
        )
        if opposing:
            coordination += (
                f"跨标的存在相反方向：{'、'.join(opposing)}；"
                "按 conviction、confidence、symbol 的固定顺序选择主标的。"
            )
        else:
            coordination += "没有与主标的相反的方向性标的。"
        return {
            "state": "DIRECTIONAL_CONCLUSION",
            "action": primary["direction"],
            "primary_symbol": primary["symbol"],
            "conviction": primary["conviction"],
            "conviction_formula": "primary.confidence * primary.direction_vote_share",
            "rationale": (
                f"{primary['symbol']} 的参与分支加权结论为{primary['direction']}，"
                f"加权平均置信度 {primary['confidence']:.1%}，"
                f"方向票占比 {primary['direction_vote_share']:.1%}，因此作为当前关注标的。"
            ),
            "internal_coordination": coordination,
            "counter_evidence": primary["counter_evidence"],
            "invalidation": primary["invalidation"],
            **common,
        }

    conviction = _neutral_conviction(contributors)
    low_confidence = conviction < NEUTRAL_WATCH_CONFIDENCE_THRESHOLD
    state = "NEUTRAL_LOW_CONVICTION" if low_confidence else "NEUTRAL_CONSENSUS"
    threshold_explanation = (
        f"低于 {NEUTRAL_WATCH_CONFIDENCE_THRESHOLD:.0%} 观望阈值，证据不足以支持方向性配置。"
        if low_confidence
        else f"达到 {NEUTRAL_WATCH_CONFIDENCE_THRESHOLD:.0%} 观望阈值，分支一致指向不建立方向性仓位。"
    )
    tie_symbols = [
        item["symbol"]
        for item in symbol_aggregates
        if item["tie_breaker"] == "TIED_HIGHEST_WEIGHT_RESOLVED_TO_NEUTRAL"
    ]
    coordination = "所有可参与标的汇总均为中性。"
    if tie_symbols:
        coordination += f" {'、'.join(sorted(tie_symbols))} 的最高票平票已按保守规则裁决为中性。"
    return {
        "state": state,
        "action": "观望",
        "primary_symbol": None,
        "conviction": conviction,
        "conviction_formula": "sum(confidence_i * weight_i) / sum(weight_i)",
        "rationale": f"可参与分支的组合结论为中性；{threshold_explanation}",
        "internal_coordination": coordination,
        "counter_evidence": "；".join(
            _dedupe_text(item["counter_evidence"] for item in symbol_aggregates if item["participating_branch_count"])
        ),
        "invalidation": "；".join(
            _dedupe_text(item["invalidation"] for item in symbol_aggregates if item["participating_branch_count"])
        ),
        **common,
    }


def build_aggregate_report(
    symbols: Sequence[str],
    verdicts: Sequence[BranchVerdict],
    *,
    weighting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 DATA_READY 时页面和 API 共用的完整汇总结果。"""
    weight_metadata = _weighting_metadata(weighting)
    aggregates = [aggregate_symbol_verdicts(symbol, verdicts, weighting=weighting) for symbol in symbols]
    excluded_count = sum(item["excluded_branch_count"] for item in aggregates)
    return {
        "aggregate": aggregates,
        "decision": build_decision(aggregates, verdicts, weighting=weighting),
        **weight_metadata,
        "contribution_weights": weighting or {
            "weight_mode": WEIGHT_MODE,
            "weight_sample_count": WEIGHT_SAMPLE_COUNT,
            "branches": [],
        },
        "coordination": {
            "rule": "仅 weight>0 的分支进入加权投票；置信度按 sum(confidence_i * weight_i) / sum(weight_i) 计算。",
            "tie_break_rule": "最高方向票并列时统一裁决为中性，避免在没有方向优势时输出方向。",
            "neutral_watch_confidence_threshold": NEUTRAL_WATCH_CONFIDENCE_THRESHOLD,
            "excluded_branch_count": excluded_count,
            "dynamic_contribution_weighting": weight_metadata["weight_mode"],
        },
    }


def _blocked_decision() -> dict[str, Any]:
    """数据新鲜度门阻断时的唯一决策表达。"""
    return {
        "state": "SYSTEM_BLOCKED",
        "action": None,
        "primary_symbol": None,
        "conviction": 0.0,
        "conviction_formula": "数据链路不完整时不计算 conviction。",
        "rationale": "数据链路不完整，不出结论。",
        "internal_coordination": "数据新鲜度门已阻断，未执行分支计算或方向协调。",
        "counter_evidence": "缺少通过新鲜度门的数据，任何方向性结论都不成立。",
        "invalidation": "全部报价与日线重新通过数据新鲜度门后，才执行分支与汇总计算。",
        "participating_branches": [],
        "excluded_branches": [],
        "weight_mode": WEIGHT_MODE,
        "weight_sample_count": WEIGHT_SAMPLE_COUNT,
    }


def blocked_aggregate_report() -> dict[str, Any]:
    """阻断态不创建分支结论，但保持 API 的汇总字段完整。"""
    return {
        "aggregate": [],
        "decision": blocked_decision(),
        "weight_mode": WEIGHT_MODE,
        "weight_sample_count": WEIGHT_SAMPLE_COUNT,
        "coordination": {
            "rule": "数据链路不完整，不执行任何分支计算。",
            "tie_break_rule": "未执行",
            "neutral_watch_confidence_threshold": NEUTRAL_WATCH_CONFIDENCE_THRESHOLD,
            "excluded_branch_count": 0,
            "dynamic_contribution_weighting": "SYSTEM_BLOCKED",
        },
        "contribution_weights": {
            "weight_mode": WEIGHT_MODE,
            "weight_sample_count": WEIGHT_SAMPLE_COUNT,
            "branches": [],
        },
    }


def build_decision(
    symbol_aggregates: Sequence[dict[str, Any]],
    verdicts: Sequence[BranchVerdict],
    *,
    weighting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成唯一建议，并附带展示层上色所需的稳定机器码。"""
    payload = _build_decision(symbol_aggregates, verdicts, weighting=weighting)
    payload["action_code"] = resolve_action_code(payload["action"])
    return payload


def blocked_decision() -> dict[str, Any]:
    """阻断态的唯一决策表达，同样带稳定机器码。"""
    payload = _blocked_decision()
    payload["action_code"] = resolve_action_code(payload["action"])
    return payload
