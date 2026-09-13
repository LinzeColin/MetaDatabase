"""将可计算分支转为审计友好的逐标的 verdict，并做冷启动汇总。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..aggregate import build_aggregate_report
from ..weighting import build_weighting_from_state
from .bars import closes, highs, lows
from .indicators import atr, ibs, rsi_wilder, sma
from .models import BranchVerdict
from .s1_momentum import DEFAULT_S1_CONFIG, default_s1_config, evaluate_s1
from .s2_meanrev import DEFAULT_S2_CONFIG, default_s2_config, evaluate_s2_entries, s2_enabled
from ..marketdata.models import Bar, Instrument


S1_LIVE_TO_ALPHA = {
    "usSPY": "SPY",
    "usQQQ": "QQQ",
    "usIWM": "IWM",
    "usEFA": "EFA",
    "usEEM": "EEM",
    "usGLD": "GLD",
    "usTLT": "TLT",
    "usBIL": "BIL",
}
S2_LIVE_TO_ALPHA = {"usSPY": "SPY", "usQQQ": "QQQ"}

UNIMPLEMENTED_BRANCHES: tuple[dict[str, str], ...] = (
    {
        "branch_id": "stock-commercial-opportunities",
        "reason": "方法要求逐项打开的一手商业、敞口、估值与催化剂证据；实时日线未提供这些已核验输入。",
        "required_input": "已打开的一手商业与估值证据账本",
    },
    {
        "branch_id": "bottleneck-serenity-skill",
        "reason": "架构合同定义任务包和审计结构，没有能由当前 Bar 序列独立执行的量化结论公式。",
        "required_input": "瓶颈、稀缺性与来源可追溯输入集",
    },
    {
        "branch_id": "equity-foresight-signal",
        "reason": "该技能要求冻结的点时数据集、训练配置和宿主信任上下文；当前行情网关只提供日线。",
        "required_input": "合格的点时训练数据集与宿主信任上下文",
    },
    {
        "branch_id": "global-equity-lead-lag-atlas",
        "reason": "该技能要求标准化现金指数、交易会话与收盘时点；当前观察宇宙不具备这些跨市场输入。",
        "required_input": "带会话时间的多市场现金指数数据集",
    },
    {
        "branch_id": "equity-event-atlas",
        "reason": "该技能要求交易所、监管和发行人事件证据及市场能力门；当前行情网关未采集事件证据。",
        "required_input": "已验证的事件证据包与市场能力门结果",
    },
    {
        "branch_id": "serenity-skill",
        "reason": "当前仓库没有该技能的 Stock_Skill 方法契约；运行清单仅指向外部 source-only 路径。",
        "required_input": "本仓可审计的方法契约与确定性输入模式",
    },
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _insufficient_verdict(branch_id: str, symbol: str, used: int, needed: int) -> BranchVerdict:
    coverage = min(used, needed) / needed
    return BranchVerdict(
        branch_id=branch_id,
        symbol=symbol,
        direction="不适用",
        confidence=coverage - coverage,
        evidence={"sample_status": f"样本不足 {used}/{needed}", "bars_available": used, "bars_required": needed},
        counter_evidence="策略最短窗口尚未满足，不能用更短窗口替代。",
        invalidation=f"日线数量达到 {needed} 根并完成同一公式复算。",
        window_used=used,
        implemented=True,
        weight=0.0,
        participation_status="SAMPLE_INSUFFICIENT",
    )


def _not_applicable_verdict(branch_id: str, symbol: str, used: int, reason: str) -> BranchVerdict:
    supported_inputs = len(set() & {symbol})
    required_inputs = 1
    return BranchVerdict(
        branch_id=branch_id,
        symbol=symbol,
        direction="不适用",
        confidence=supported_inputs / required_inputs,
        evidence={"scope_status": "策略资产池不包含该标的", "bars_available": used},
        counter_evidence=reason,
        invalidation="将该标的纳入经版本化审查的策略资产池后重新计算。",
        window_used=used,
        implemented=True,
        weight=0.0,
        participation_status="OUT_OF_STRATEGY_UNIVERSE",
    )


def _universe_incomplete_verdict(
    branch_id: str, symbol: str, used: int, available: int, required: int, missing: Sequence[str]
) -> BranchVerdict:
    coverage = available / required
    return BranchVerdict(
        branch_id=branch_id,
        symbol=symbol,
        direction="不适用",
        confidence=coverage - coverage,
        evidence={
            "coverage_status": f"策略资产池不完整 {available}/{required}",
            "configured_assets_available": available,
            "configured_assets_required": required,
            "missing_configured_assets": list(missing),
        },
        counter_evidence="S1 是全资产池排名策略；缺失配置资产会改变 top_n 排名，不能用部分资产池替代。",
        invalidation=f"补齐并验证缺失的配置资产日线：{', '.join(missing)}。",
        window_used=used,
        implemented=True,
        weight=0.0,
        participation_status="CONFIGURED_UNIVERSE_INCOMPLETE",
    )


def _unimplemented_verdict(branch: Mapping[str, str], symbol: str, used: int) -> BranchVerdict:
    available_input_names: set[str] = set()
    required_input_names = {branch["required_input"]}
    coverage = len(available_input_names & required_input_names) / len(required_input_names)
    return BranchVerdict(
        branch_id=branch["branch_id"],
        symbol=symbol,
        direction="不适用",
        confidence=coverage,
        evidence={
            "implementation_status": "未实现，不参与加权",
            "available_required_input_count": len(available_input_names & required_input_names),
            "required_input_count": len(required_input_names),
            "required_input": branch["required_input"],
        },
        counter_evidence=branch["reason"],
        invalidation=f"接入“{branch['required_input']}”并通过确定性分支单测后才可参与汇总。",
        window_used=used,
        implemented=False,
        weight=0.0,
        participation_status="UNIMPLEMENTED",
    )


def _s1_required_bars() -> int:
    score = DEFAULT_S1_CONFIG["score"]
    return max(max(score["lookbacks_trading_days"]) + 1, DEFAULT_S1_CONFIG["absolute_momentum_filter"]["sma_period"])  # type: ignore[index]


def _s2_required_bars() -> int:
    entry = DEFAULT_S2_CONFIG["entry"]
    return max(200, 14 + 1, entry["rsi"]["period"] + 1)  # type: ignore[index]


def evaluate_s1_verdicts(bars_by_symbol: Mapping[str, Sequence[Bar]]) -> list[BranchVerdict]:
    config = default_s1_config()
    required_bars = _s1_required_bars()
    alpha_bars = {alpha: bars_by_symbol.get(live, ()) for live, alpha in S1_LIVE_TO_ALPHA.items()}
    as_of_candidates = [bars[-1].day for bars in alpha_bars.values() if bars]
    configured_universe = list(config["universe"])  # type: ignore[index]
    unavailable = [symbol for symbol in configured_universe if len(alpha_bars.get(symbol, ())) < required_bars]
    available_count = len(configured_universe) - len(unavailable)
    result = (
        evaluate_s1(alpha_bars, config, min(as_of_candidates))
        if as_of_candidates and not unavailable
        else None
    )
    verdicts: list[BranchVerdict] = []
    for live_symbol, bars in bars_by_symbol.items():
        alpha_symbol = S1_LIVE_TO_ALPHA.get(live_symbol)
        if alpha_symbol is None:
            verdicts.append(_not_applicable_verdict("s1_momentum", live_symbol, len(bars), "S1 Alpha 资产池只包含其配置的全球 ETF。"))
            continue
        if len(bars) < required_bars:
            verdicts.append(_insufficient_verdict("s1_momentum", live_symbol, len(bars), required_bars))
            continue
        if unavailable:
            verdicts.append(
                _universe_incomplete_verdict(
                    "s1_momentum", live_symbol, len(bars), available_count, len(configured_universe), unavailable
                )
            )
            continue
        assert result is not None
        diagnostic = result.diagnostics[alpha_symbol]
        returns = diagnostic["returns"]
        weighted_abs_return = sum(
            abs(returns[f"r{lookback}"]) * weight
            for lookback, weight in zip(config["score"]["lookbacks_trading_days"], config["score"]["weights"])  # type: ignore[index]
        )
        momentum_component = abs(diagnostic["score"]) / weighted_abs_return if weighted_abs_return else 0.0
        trend_component = abs(diagnostic["close"] - diagnostic["sma200"]) / diagnostic["close"]
        confidence = _clamp((momentum_component + trend_component + result.position_scalar) / 3.0)
        selected = alpha_symbol in result.selected
        direction = "看涨" if selected else "中性"
        counter = (
            f"当前没有进入配置 top {config['selection']['top_n']} 的动量排序。"
            if not selected
            else f"收盘跌至或低于 SMA200={diagnostic['sma200']:.4f}，或下次复算退出 top {config['selection']['top_n']}。"
        )
        verdicts.append(
            BranchVerdict(
                branch_id="s1_momentum",
                symbol=live_symbol,
                direction=direction,
                confidence=confidence,
                evidence={
                    "close": diagnostic["close"],
                    "sma200": diagnostic["sma200"],
                    **returns,
                    "momentum_score": diagnostic["score"],
                    "position_scalar": result.position_scalar,
                    "momentum_component": momentum_component,
                    "trend_component": trend_component,
                    "selected": selected,
                    "confidence_formula": "clamp((abs(score)/weighted_abs_return + abs(close-sma200)/close + position_scalar)/3)",
                },
                counter_evidence=counter,
                invalidation=f"收盘不高于 SMA200={diagnostic['sma200']:.4f} 或下一次复算不在 top {config['selection']['top_n']}。",
                window_used=len(bars),
                implemented=True,
                weight=1.0,
                participation_status="COLD_START_ELIGIBLE",
            )
        )
    return verdicts


def evaluate_s2_verdicts(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    promotion: Mapping[str, Any] | None = None,
) -> list[BranchVerdict]:
    config = default_s2_config()
    required_bars = _s2_required_bars()
    alpha_bars = {alpha: bars_by_symbol.get(live, ()) for live, alpha in S2_LIVE_TO_ALPHA.items()}
    as_of_candidates = [bars[-1].day for bars in alpha_bars.values() if bars]
    entries = evaluate_s2_entries(alpha_bars, config, min(as_of_candidates)) if as_of_candidates else []
    entries_by_symbol = {entry.symbol: entry for entry in entries}
    backtest_promotion_passed = (
        bool(promotion.get("passed"))
        if promotion is not None and "passed" in promotion
        else None
    )
    promotion_reason = (
        str(promotion.get("reason"))
        if promotion is not None and promotion.get("reason")
        else "尚未产出自建回测推广门结果。"
    )
    aggregation_enabled = s2_enabled(config, backtest_promotion_passed=backtest_promotion_passed)
    verdicts: list[BranchVerdict] = []
    entry_config = config["entry"]  # type: ignore[index]
    rsi_threshold = float(entry_config["rsi"]["threshold"])  # type: ignore[index]
    ibs_threshold = float(entry_config["ibs"]["threshold"])  # type: ignore[index]
    volatility_floor = 0.015
    for live_symbol, bars in bars_by_symbol.items():
        alpha_symbol = S2_LIVE_TO_ALPHA.get(live_symbol)
        if alpha_symbol is None:
            verdicts.append(_not_applicable_verdict("s2_meanrev", live_symbol, len(bars), "S2 Alpha 核心资产池只包含 SPY 与 QQQ。"))
            continue
        if len(bars) < required_bars:
            verdicts.append(_insufficient_verdict("s2_meanrev", live_symbol, len(bars), required_bars))
            continue
        close_values, high_values, low_values = closes(bars), highs(bars), lows(bars)
        average = sma(close_values, 200)
        rsi = rsi_wilder(close_values, int(entry_config["rsi"]["period"]))  # type: ignore[index]
        close_location = ibs(high_values[-1], low_values[-1], close_values[-1])
        average_range = atr(high_values, low_values, close_values, 14)
        assert average is not None and rsi is not None and close_location is not None and average_range is not None
        atr_ratio = average_range / close_values[-1]
        components = {
            "rsi_component": _clamp((rsi_threshold - rsi) / rsi_threshold),
            "ibs_component": _clamp((ibs_threshold - close_location) / ibs_threshold),
            "trend_component": _clamp((close_values[-1] - average) / close_values[-1]),
            "volatility_component": _clamp((atr_ratio - volatility_floor) / atr_ratio),
        }
        signal_confidence = sum(components.values()) / len(components)
        entry = entries_by_symbol.get(alpha_symbol)
        is_entry = entry is not None
        confidence = signal_confidence if is_entry else 1.0 - signal_confidence
        participation = "COLD_START_ELIGIBLE" if aggregation_enabled else "EXCLUDED_PENDING_BACKTEST"
        signal_counter_evidence = (
            "S2 进场四条件尚未同时满足。"
            if not is_entry
            else "RSI(2)、IBS、趋势或 ATR 比率任一条件在下次收盘复算时失效。"
        )
        verdicts.append(
            BranchVerdict(
                branch_id="s2_meanrev",
                symbol=live_symbol,
                direction="看涨" if is_entry else "中性",
                confidence=_clamp(confidence),
                evidence={
                    "close": close_values[-1],
                    "sma200": average,
                    "rsi2": rsi,
                    "ibs": close_location,
                    "atr_ratio": atr_ratio,
                    **components,
                    "entry_signal": is_entry,
                    "backtest_promotion_passed": backtest_promotion_passed,
                    "aggregation_enabled": aggregation_enabled,
                    "confidence_formula": "mean(rsi_component, ibs_component, trend_component, volatility_component) for entry; 1-mean(...) for neutral",
                },
                counter_evidence=(
                    signal_counter_evidence
                    if aggregation_enabled
                    else f"{signal_counter_evidence} {promotion_reason}"
                ),
                invalidation=(
                    f"收盘不高于 SMA200={average:.4f}、RSI(2)不低于 {rsi_threshold:g}、IBS不低于 {ibs_threshold:g}，或 ATR14/close 不高于 {volatility_floor:.3%}。"
                ),
                window_used=len(bars),
                implemented=True,
                weight=1.0 if aggregation_enabled else 0.0,
                participation_status=participation,
            )
        )
    return verdicts


def build_branch_report(
    instruments: Sequence[Instrument],
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    backtest: Mapping[str, Any] | None = None,
    *,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """计算全部 Stage 2 分支并返回白箱 API 与页面共用的结构。"""
    symbols = [instrument.symbol for instrument in instruments]
    ordered_bars = {symbol: bars_by_symbol.get(symbol, ()) for symbol in symbols}
    s2_backtest = (
        backtest.get("branches", {}).get("s2_meanrev", {})
        if backtest is not None
        else {}
    )
    s2_promotion = s2_backtest.get("promotion") or (
        {
            "passed": False,
            "reason": str(s2_backtest["sample_status"]),
        }
        if s2_backtest.get("status") == "SAMPLE_INSUFFICIENT"
        else None
    )
    verdicts = evaluate_s1_verdicts(ordered_bars) + evaluate_s2_verdicts(ordered_bars, s2_promotion)
    for branch in UNIMPLEMENTED_BRANCHES:
        verdicts.extend(_unimplemented_verdict(branch, symbol, len(ordered_bars[symbol])) for symbol in symbols)
    branch_ids = sorted({verdict.branch_id for verdict in verdicts})
    eligible_branch_ids = sorted({verdict.branch_id for verdict in verdicts if verdict.weight > 0.0})
    branch_participation = {
        branch_id: _branch_participation_status(branch_id, verdicts)
        for branch_id in branch_ids
    }
    weighting = build_weighting_from_state(
        state_dir,
        branch_ids=branch_ids,
        eligible_branch_ids=eligible_branch_ids,
        branch_participation=branch_participation,
    )
    weighted_verdicts = [
        replace(verdict, weight=weighting["weights"].get(verdict.branch_id, 0.0))
        if verdict.weight > 0.0
        else verdict
        for verdict in verdicts
    ]
    return {
        "branches": [verdict.as_dict() for verdict in weighted_verdicts],
        "profitability_status": (
            str(backtest.get("profitability_status"))
            if backtest is not None and backtest.get("profitability_status")
            else "NOT_PRODUCED_STAGE_2_NO_BACKTEST"
        ),
        **build_aggregate_report(symbols, weighted_verdicts, weighting=weighting),
    }


def _branch_participation_status(branch_id: str, verdicts: Sequence[BranchVerdict]) -> str:
    """分支权重先尊重 Stage 2 的逐标的资格门，再读取贡献度样本。"""
    branch_verdicts = [verdict for verdict in verdicts if verdict.branch_id == branch_id]
    if any(verdict.weight > 0.0 for verdict in branch_verdicts):
        return "COLD_START_ELIGIBLE"
    statuses = {verdict.participation_status for verdict in branch_verdicts}
    for status in ("EXCLUDED_PENDING_BACKTEST", "UNIMPLEMENTED", "SAMPLE_INSUFFICIENT"):
        if status in statuses:
            return status
    return sorted(statuses)[0] if statuses else "UNSPECIFIED"
