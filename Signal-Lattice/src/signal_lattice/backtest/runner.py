# 来源: Alpha/backend/app/backtest/runner.py; 原路径: Alpha/backend/app/backtest/runner.py.
"""Signal-Lattice 的 Stage 4 回测运行器。

本文件保留 Alpha runner 的工作流：训练窗网格搜索、紧随其后的样本外测试、
测试窗拼接和 PROMO-1 判定。数据入口改为本仓已经取得的 marketdata 日线，
不跨目录 import，不读取 Alpha 配置路径，也不发起网络请求。
"""

from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..marketdata.models import Bar, Instrument
from ..serialization import strict_json_dumps
from ..branches.s1_momentum import default_s1_config
from ..branches.s2_meanrev import default_s2_config
from .fees import FeeModel
from .pipeline import (
    S1Params,
    S2Params,
    SleeveResult,
    ledger_metrics,
    load_promo1_gate,
    metrics,
    pick_best,
    precompute,
    promo1_verdict,
    s1_grid,
    s2_grid,
    simulate_s1,
    simulate_s2,
    walk_forward_windows,
)


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

# 来源：Alpha/configs/strategies/s1_momentum.yaml 的 review_grid。
S1_REVIEW_GRID = {
    "lookbacks_allowed": [[63, 126, 252]],
    "weights_allowed": [[0.4, 0.3, 0.3], [0.5, 0.3, 0.2], [0.33, 0.33, 0.34]],
    "top_n_allowed": [2, 3],
    "target_vol_allowed": [10, 12, 15],
    "rebalance_threshold_allowed": [3, 5, 8],
}
# 来源：Alpha/configs/strategies/s2_meanrev.yaml 的 review_grid。
S2_REVIEW_GRID = {
    "rsi_threshold_allowed": [5, 8, 10],
    "ibs_threshold_allowed": [0.15, 0.2, 0.3],
    "stop_loss_allowed": [3.0, 4.0, 5.0],
    "time_stop_allowed": [7, 10, 15],
    "volatility_floor_allowed": [1.0, 1.5, 2.0],
}

# 来源：Alpha/backend/app/backtest/runner.py 的 capital_aud=3000 与
# DEFAULT_AUD_USD=0.66。Stage 4 单分支比较以同一 1,980 USD 起始资金运行。
DEFAULT_CAPITAL_USD = 1_980.0
MIN_COMPLETE_WINDOWS = 2
# 一个严格样本外窗口为 6 个月。PROMO-1 的最短样本外年限为 3 年，
# 因而收益数字的统一发布门也必须是 6 个窗口，避免 S1 用更低标准发布业绩。
MIN_OOS_WINDOWS_FOR_PROFITABILITY = 6
OOS_HISTORY_INSUFFICIENT_MESSAGE = "样本外历史不足，仅供研究参考，不构成收益证据。"


@dataclass(frozen=True)
class ContributionSample:
    """一个分支在一个严格样本外 test 窗口的贡献度观察。

    risk_adjusted_excess = excess_return / active_daily_volatility。若该期
    active return 波动为零，数学上不可定义，字段落为 null 而非伪造数值。
    """

    branch_id: str
    period_start: date
    period_end: date
    symbol: str
    branch_return: float
    benchmark_return: float
    excess_return: float
    risk_adjusted_excess: float | None
    window_label: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["period_start"] = self.period_start.isoformat()
        value["period_end"] = self.period_end.isoformat()
        return value


def _common_days(bars_by_symbol: Mapping[str, Sequence[Bar]], symbols: Sequence[str]) -> list[date]:
    if not symbols or any(not bars_by_symbol.get(symbol) for symbol in symbols):
        return []
    common = set(bar.day for bar in bars_by_symbol[symbols[0]])
    for symbol in symbols[1:]:
        common.intersection_update(bar.day for bar in bars_by_symbol[symbol])
    return sorted(common)


def _series_for(
    bars_by_symbol: Mapping[str, Sequence[Bar]], mapping: Mapping[str, str]
) -> tuple[dict[str, Any], list[date], list[str]]:
    missing = [live for live in mapping if not bars_by_symbol.get(live)]
    if missing:
        return {}, [], missing
    common_days = _common_days(bars_by_symbol, list(mapping))
    if not common_days:
        return {}, [], list(mapping)
    allowed = set(common_days)
    series = {
        alpha: precompute(alpha, [bar for bar in bars_by_symbol[live] if bar.day in allowed])
        for live, alpha in mapping.items()
    }
    return series, common_days, []


def _daily_returns(values: Sequence[float]) -> list[float]:
    return [
        values[index] / values[index - 1] - 1.0
        for index in range(1, len(values))
        if values[index - 1] > 0
    ]


def _active_return_volatility(equity: Sequence[float], benchmark: Sequence[float]) -> float | None:
    strategy_returns = _daily_returns(equity)
    benchmark_returns = _daily_returns(benchmark)
    active = [
        strategy - index_return
        for strategy, index_return in zip(strategy_returns, benchmark_returns)
    ]
    if len(active) < 2:
        return None
    value = statistics.stdev(active)
    return value if value > 0 else None


def _information_ratio(equity: Sequence[float], benchmark: Sequence[float]) -> float | None:
    strategy_returns = _daily_returns(equity)
    benchmark_returns = _daily_returns(benchmark)
    active = [
        strategy - index_return
        for strategy, index_return in zip(strategy_returns, benchmark_returns)
    ]
    if len(active) < 2:
        return None
    standard_deviation = statistics.stdev(active)
    if standard_deviation == 0:
        return None
    return statistics.fmean(active) / standard_deviation * math.sqrt(252)


def _turnover_ratio(fills: Sequence[dict[str, Any]], equity: Sequence[float]) -> float | None:
    if not equity:
        return None
    average_equity = statistics.fmean(equity)
    if average_equity <= 0:
        return None
    turnover = sum(float(fill["qty"]) * float(fill["price"]) for fill in fills)
    return turnover / average_equity


def _finite_metrics(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (None if isinstance(value, float) and not math.isfinite(value) else value)
        for key, value in values.items()
    }


def alpha_metrics(
    days: Sequence[date],
    equity: Sequence[float],
    benchmark_prices: Sequence[float],
    fills: Sequence[dict[str, Any]],
    *,
    initial_capital: float | None = None,
) -> dict[str, Any]:
    """计算费后策略相对 Instrument.benchmark 的样本外 Alpha 度量。"""
    if not equity or not benchmark_prices or len(equity) != len(benchmark_prices):
        return {"status": "SAMPLE_INSUFFICIENT"}
    initial_capital = initial_capital if initial_capital is not None else equity[0]
    strategy_return = equity[-1] / initial_capital - 1.0 if initial_capital > 0 else 0.0
    benchmark_return = (
        benchmark_prices[-1] / benchmark_prices[0] - 1.0
        if benchmark_prices[0] > 0
        else 0.0
    )
    performance = _finite_metrics(ledger_metrics(days, equity, fills))
    active_volatility = _active_return_volatility(equity, benchmark_prices)
    excess_return = strategy_return - benchmark_return
    return {
        "status": "OOS_READY",
        "branch_return_pct": round(strategy_return * 100.0, 4),
        "benchmark_return_pct": round(benchmark_return * 100.0, 4),
        "excess_return_pct": round(excess_return * 100.0, 4),
        "information_ratio": (
            round(value, 4)
            if (value := _information_ratio(equity, benchmark_prices)) is not None
            else None
        ),
        "active_daily_volatility": active_volatility,
        "max_drawdown_pct": performance.get("max_drawdown_pct"),
        "win_rate_pct": performance.get("per_trade_win_rate_pct"),
        "turnover_ratio": _turnover_ratio(fills, equity),
        "performance": performance,
    }


def _window_prices(series: Any, days: Sequence[date]) -> list[float]:
    return [series.closes[series.index_by_day[day]] for day in days]


def _chosen_parameters(chosen: S1Params | S2Params) -> dict[str, Any]:
    """把网格项转为稳定 JSON 结构，避免 tuple 在报告和运行时含义不同。"""
    return (
        {**asdict(chosen), "weights": list(chosen.weights)}
        if isinstance(chosen, S1Params)
        else asdict(chosen)
    )


def _active_s1_config(chosen: S1Params) -> dict[str, Any]:
    """将训练窗选出的 S1 网格项展开成实盘 verdict 直接消费的完整配置。"""
    config = default_s1_config()
    score = dict(config["score"])  # type: ignore[arg-type]
    selection = dict(config["selection"])  # type: ignore[arg-type]
    volatility = dict(config["volatility_targeting"])  # type: ignore[arg-type]
    score["weights"] = list(chosen.weights)
    selection["top_n"] = chosen.top_n
    selection["weight_each"] = 1.0 / chosen.top_n
    volatility["target_annual_vol_pct"] = chosen.target_vol
    config.update({
        "score": score,
        "selection": selection,
        "volatility_targeting": volatility,
        "rebalance_threshold_pct": chosen.rebalance_threshold_pct,
    })
    return config


def _active_s2_config(chosen: S2Params) -> dict[str, Any]:
    """将训练窗选出的 S2 网格项展开成实盘 verdict 直接消费的完整配置。"""
    config = default_s2_config()
    entry = dict(config["entry"])  # type: ignore[arg-type]
    rsi = dict(entry["rsi"])
    ibs = dict(entry["ibs"])
    exit_config = dict(config["exit"])  # type: ignore[arg-type]
    rsi["threshold"] = chosen.rsi_threshold
    ibs["threshold"] = chosen.ibs_threshold
    entry.update({
        "rsi": rsi,
        "ibs": ibs,
        "volatility_floor": "ATR14 / close > %g%%" % chosen.vol_floor_pct,
        "volatility_floor_pct": chosen.vol_floor_pct,
    })
    exit_config.update({
        "stop_loss_pct": chosen.stop_loss_pct,
        "time_stop_trading_days": chosen.time_stop_days,
    })
    config.update({"entry": entry, "exit": exit_config})
    return config


def _active_runtime_config(chosen: S1Params | S2Params) -> dict[str, Any]:
    if isinstance(chosen, S1Params):
        return _active_s1_config(chosen)
    return _active_s2_config(chosen)


def select_active_config(windows: Sequence[Mapping[str, Any]], as_of: date) -> dict[str, Any]:
    """选择 ``train_end <= as_of`` 的最新已评价训练窗配置。

    每个候选的 test 指标只用于样本外评价，选择本身只读取该窗口已经冻结的
    训练期参数。train_end 恰好等于 as_of 时允许使用：当天收盘后训练数据已经
    完整，未读取 as_of 之后的任何 Bar。
    """
    candidates: list[tuple[date, str, Mapping[str, Any]]] = []
    for window in windows:
        if window.get("test_evaluable") is not True:
            continue
        train = window.get("train")
        active_config = window.get("active_config")
        label = window.get("window_label")
        if (
            not isinstance(train, list)
            or len(train) != 2
            or not isinstance(train[1], str)
            or not isinstance(active_config, Mapping)
            or not isinstance(label, str)
        ):
            continue
        try:
            train_end = date.fromisoformat(train[1])
        except ValueError:
            continue
        if train_end <= as_of:
            candidates.append((train_end, label, window))
    if not candidates:
        return {
            "active_config": None,
            "config_as_of": as_of.isoformat(),
            "config_source_window": None,
            "config_status": "NO_EVALUATED_TRAIN_WINDOW_AS_OF",
        }
    _, _, source = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return {
        "active_config": source["active_config"],
        "config_as_of": as_of.isoformat(),
        "config_source_window": {
            "window_label": source["window_label"],
            "train": source["train"],
            "test": source["test"],
        },
        "config_status": "ACTIVE_TRAIN_WINDOW_AS_OF",
    }


def _choose_and_simulate(
    *,
    calendar: Sequence[date],
    windows: Sequence[tuple[date, date, date, date]],
    parameter_grid: Sequence[S1Params] | Sequence[S2Params],
    simulate: Callable[[Any, date, date, float], SleeveResult],
    benchmark_series: Any,
    branch_id: str,
    symbol: str,
    capital_usd: float,
) -> tuple[list[dict[str, Any]], list[date], list[float], list[float], list[dict[str, Any]], list[ContributionSample], int]:
    reports: list[dict[str, Any]] = []
    stitched_days: list[date] = []
    stitched_equity: list[float] = []
    stitched_benchmark: list[float] = []
    stitched_fills: list[dict[str, Any]] = []
    contributions: list[ContributionSample] = []
    compounded_capital = capital_usd
    compounded_benchmark = capital_usd
    evaluable_windows = 0

    for index, (train_start, train_end, test_start, test_end) in enumerate(windows, start=1):
        train_candidates = [
            (params, metrics((result := simulate(params, train_start, train_end, capital_usd)).equity_days, result.equity))
            for params in parameter_grid
        ]
        chosen, train_metrics, train_dd_ok = pick_best(train_candidates)
        chosen_parameters = _chosen_parameters(chosen)
        active_config = _active_runtime_config(chosen)
        test = simulate(chosen, test_start, test_end, capital_usd)
        label = f"WF-{index:02d}"
        if not test.equity_days:
            # 该 test 窗口没有任何可评价交易日（标的在窗口内无可用日线，或策略全程无法建仓）。
            # 这不是一个有效样本：既不能生成贡献度，也不得按零收益并入拼接曲线——后者会把
            # "没有数据"粉饰成"这段时间收益为零"，系统性压低波动并抬高信息比率。剔除并记账。
            reports.append({
                "window_label": label,
                "train": [train_start.isoformat(), train_end.isoformat()],
                "test": [test_start.isoformat(), test_end.isoformat()],
                "test_evaluable": False,
                "excluded_reason": "该测试窗口无可评价交易日，已作为无效样本剔除",
                "chosen_parameters": chosen_parameters,
                "active_config": active_config,
                "train_metrics": train_metrics,
                "train_drawdown_constraint_met": train_dd_ok,
            })
            continue
        evaluable_windows += 1
        benchmark_prices = _window_prices(benchmark_series, test.equity_days)
        window_metrics = alpha_metrics(
            test.equity_days, test.equity, benchmark_prices, test.fills,
            initial_capital=capital_usd,
        )
        branch_return = float(window_metrics.get("branch_return_pct", 0.0)) / 100.0
        benchmark_return = float(window_metrics.get("benchmark_return_pct", 0.0)) / 100.0
        active_volatility = window_metrics.get("active_daily_volatility")
        risk_adjusted_excess = (
            branch_return - benchmark_return
        ) / active_volatility if active_volatility else None
        sample = ContributionSample(
            branch_id=branch_id,
            period_start=test.equity_days[0],
            period_end=test.equity_days[-1],
            symbol=symbol,
            branch_return=branch_return,
            benchmark_return=benchmark_return,
            excess_return=branch_return - benchmark_return,
            risk_adjusted_excess=risk_adjusted_excess,
            window_label=label,
        )
        contributions.append(sample)
        reports.append(
            {
                "window_label": label,
                "test_evaluable": True,
                "train": [train_start.isoformat(), train_end.isoformat()],
                "test": [test_start.isoformat(), test_end.isoformat()],
                "chosen_parameters": chosen_parameters,
                "active_config": active_config,
                "train_metrics": train_metrics,
                "train_drawdown_constraint_met": train_dd_ok,
                "test_metrics": window_metrics,
                "test_orders": test.orders,
                "test_fees_usd": round(test.fees_usd, 4),
                "test_skipped_infeasible": test.skipped_infeasible,
                "contribution": sample.as_dict(),
            }
        )
        if test.equity and benchmark_prices and benchmark_prices[0] > 0:
            # 策略净值与基准必须用同一套串接规则：各自在 test 窗口起点归一到当前
            # 已复利的水平，窗口之间的空档两边都不计入。
            #
            # 原实现只对净值做了归一，基准直接拼原始价格，于是基准白拿了窗口之间
            # 策略根本没参与的那些时段（S2 实测：策略在场 10×6 个月，基准却按
            # 2003→2026 全程 648% 计），并在每个接缝制造一个虚假跳空日收益，
            # 同时虚增波动、污染信息比率。
            base = compounded_capital / capital_usd
            bench_base = compounded_benchmark / benchmark_prices[0]
            stitched_days.extend(test.equity_days)
            stitched_equity.extend(value * base for value in test.equity)
            stitched_benchmark.extend(price * bench_base for price in benchmark_prices)
            stitched_fills.extend(test.fills)
            compounded_capital = stitched_equity[-1]
            compounded_benchmark = stitched_benchmark[-1]
    return reports, stitched_days, stitched_equity, stitched_benchmark, stitched_fills, contributions, evaluable_windows


def _sample_insufficient(
    branch_id: str,
    available_windows: int,
    missing_symbols: Sequence[str] = (),
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    detail = (
        f"；缺少日线：{'、'.join(missing_symbols)}"
        if missing_symbols
        else ""
    )
    return {
        "branch_id": branch_id,
        "status": "SAMPLE_INSUFFICIENT",
        "sample_status": f"样本不足 {available_windows}/{MIN_COMPLETE_WINDOWS}{detail}",
        "available_complete_windows": available_windows,
        "required_complete_windows": MIN_COMPLETE_WINDOWS,
        "windows": [],
        "contributions": [],
        "active_config": None,
        "config_as_of": as_of.isoformat() if as_of is not None else None,
        "config_source_window": None,
        "config_status": "NO_EVALUATED_TRAIN_WINDOW_AS_OF",
    }


def _s1_backtest(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    instruments: Mapping[str, Instrument],
    fee: FeeModel,
    capital_usd: float,
    train_months: int,
    test_months: int,
) -> dict[str, Any]:
    if "usSPY" not in instruments:
        return _sample_insufficient("s1_momentum", 0, ["usSPY benchmark instrument"])
    series, calendar, missing = _series_for(bars_by_symbol, S1_LIVE_TO_ALPHA)
    windows = walk_forward_windows(calendar, train_months=train_months, validate_months=test_months)
    if missing or len(windows) < MIN_COMPLETE_WINDOWS:
        return _sample_insufficient("s1_momentum", len(windows), missing, as_of=calendar[-1] if calendar else None)
    benchmark_symbol = instruments["usSPY"].benchmark
    if not benchmark_symbol or benchmark_symbol not in bars_by_symbol:
        return _sample_insufficient("s1_momentum", len(windows), [str(benchmark_symbol)], as_of=calendar[-1] if calendar else None)
    benchmark = precompute(benchmark_symbol, bars_by_symbol[benchmark_symbol])
    universe = list(S1_LIVE_TO_ALPHA.values())

    def simulate(params: S1Params, start: date, end: date, sleeve: float) -> SleeveResult:
        return simulate_s1(
            series, universe, "BIL", params, start=start, end=end, sleeve_usd=sleeve,
            fee=fee, calendar=calendar,
        )

    reports, days, equity, benchmark_prices, fills, contributions, evaluable_windows = _choose_and_simulate(
        calendar=calendar, windows=windows, parameter_grid=s1_grid(S1_REVIEW_GRID),
        simulate=simulate, benchmark_series=benchmark, branch_id="s1_momentum",
        symbol="usSPY", capital_usd=capital_usd,
    )
    if evaluable_windows < MIN_COMPLETE_WINDOWS:
        # 窗口切得出来，但真正能评价的不足 —— 按样本不足如实输出，不得用无效窗口凑数。
        return _sample_insufficient("s1_momentum", evaluable_windows, as_of=calendar[-1] if calendar else None)
    config_selection = select_active_config(reports, calendar[-1])
    return {
        "branch_id": "s1_momentum",
        "status": "OOS_READY",
        "symbol": "usSPY",
        "benchmark_symbol": benchmark_symbol,
        "walk_forward": {"train_months": train_months, "test_months": test_months, "windows": len(windows)},
        "windows": reports,
        "stitched": alpha_metrics(
            days, equity, benchmark_prices, fills, initial_capital=capital_usd,
        ),
        "contributions": [sample.as_dict() for sample in contributions],
        **config_selection,
    }


def _s2_backtest(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    instruments: Mapping[str, Instrument],
    fee: FeeModel,
    capital_usd: float,
    train_months: int,
    test_months: int,
) -> dict[str, Any]:
    if "usSPY" not in instruments:
        return _sample_insufficient("s2_meanrev", 0, ["usSPY benchmark instrument"])
    series, calendar, missing = _series_for(bars_by_symbol, S2_LIVE_TO_ALPHA)
    windows = walk_forward_windows(calendar, train_months=train_months, validate_months=test_months)
    if missing or len(windows) < MIN_COMPLETE_WINDOWS:
        return _sample_insufficient("s2_meanrev", len(windows), missing, as_of=calendar[-1] if calendar else None)
    benchmark_symbol = instruments["usSPY"].benchmark
    if not benchmark_symbol or benchmark_symbol not in bars_by_symbol:
        return _sample_insufficient("s2_meanrev", len(windows), [str(benchmark_symbol)], as_of=calendar[-1] if calendar else None)
    benchmark = precompute(benchmark_symbol, bars_by_symbol[benchmark_symbol])
    universe = list(S2_LIVE_TO_ALPHA.values())

    def simulate(params: S2Params, start: date, end: date, sleeve: float) -> SleeveResult:
        return simulate_s2(
            series, universe, params, start=start, end=end, sleeve_usd=sleeve,
            fee=fee, calendar=calendar, max_open=2,
        )

    reports, days, equity, benchmark_prices, fills, contributions, evaluable_windows = _choose_and_simulate(
        calendar=calendar, windows=windows, parameter_grid=s2_grid(S2_REVIEW_GRID),
        simulate=simulate, benchmark_series=benchmark, branch_id="s2_meanrev",
        symbol="usSPY", capital_usd=capital_usd,
    )
    stitched = alpha_metrics(
        days, equity, benchmark_prices, fills, initial_capital=capital_usd,
    )
    promotion = promo1_verdict(stitched.get("performance", {}), **load_promo1_gate())
    promotion["reason"] = promotion_reason(stitched.get("performance", {}), promotion)
    if evaluable_windows < MIN_COMPLETE_WINDOWS:
        # 窗口切得出来，但真正能评价的不足 —— 按样本不足如实输出，不得用无效窗口凑数。
        return _sample_insufficient("s2_meanrev", evaluable_windows, as_of=calendar[-1] if calendar else None)
    config_selection = select_active_config(reports, calendar[-1])
    return {
        "branch_id": "s2_meanrev",
        "status": "OOS_READY",
        "symbol": "usSPY",
        "benchmark_symbol": benchmark_symbol,
        "walk_forward": {"train_months": train_months, "test_months": test_months, "windows": len(windows)},
        "windows": reports,
        "stitched": stitched,
        "promotion": promotion,
        "contributions": [sample.as_dict() for sample in contributions],
        **config_selection,
    }


def promotion_reason(performance: Mapping[str, Any], verdict: Mapping[str, Any]) -> str:
    """生成 S2 推广门的可审计判定，不调整任何 Alpha 配置门槛。"""
    gate = verdict["gate"]
    deficits: list[str] = []
    years = float(performance.get("years", 0.0))
    monthly = float(performance.get("monthly_mean_net_pct", 0.0))
    drawdown = float(performance.get("max_drawdown_pct", 0.0))
    if not verdict["years_ok"]:
        deficits.append(f"样本外年限 {years:.2f} 年，距 {gate['min_years']:.2f} 年差 {gate['min_years'] - years:.2f} 年")
    if not verdict["monthly_return_ok"]:
        deficits.append(f"月均净收益 {monthly:.3f}%，距 {gate['monthly_pct']:.3f}% 差 {gate['monthly_pct'] - monthly:.3f} 个百分点")
    if not verdict["drawdown_ok"]:
        deficits.append(f"最大回撤 {drawdown:.2f}%，超过 {gate['dd_pct']:.2f}% {drawdown - gate['dd_pct']:.2f} 个百分点")
    return "PROMO-1 通过" if verdict["passed"] else "PROMO-1 未通过：" + "；".join(deficits)


def branch_sample_sufficiency(branch: Mapping[str, Any]) -> str:
    observed = len(branch.get("contributions", []))
    if observed < MIN_OOS_WINDOWS_FOR_PROFITABILITY:
        return f"OOS_HISTORY_INSUFFICIENT: {observed}/{MIN_OOS_WINDOWS_FOR_PROFITABILITY}"
    return f"OOS_HISTORY_SUFFICIENT: {observed}/{MIN_OOS_WINDOWS_FOR_PROFITABILITY}"


def sample_sufficiency(branches: Mapping[str, Mapping[str, Any]]) -> str:
    statuses = [branch_sample_sufficiency(branch) for branch in branches.values()]
    insufficient = [
        status for status in statuses
        if status.startswith("OOS_HISTORY_INSUFFICIENT:")
    ]
    if insufficient:
        # 一个严格门约束全部收益发布；取最少窗口数，使顶层状态始终是可直接行动的 N/M。
        counts = [int(status.split(": ", 1)[1].split("/", 1)[0]) for status in insufficient]
        return f"OOS_HISTORY_INSUFFICIENT: {min(counts)}/{MIN_OOS_WINDOWS_FOR_PROFITABILITY}"
    return f"OOS_HISTORY_SUFFICIENT: {MIN_OOS_WINDOWS_FOR_PROFITABILITY}/{MIN_OOS_WINDOWS_FOR_PROFITABILITY}"


def profitability_status(branches: Mapping[str, Mapping[str, Any]]) -> str:
    sufficiency = sample_sufficiency(branches)
    if sufficiency.startswith("OOS_HISTORY_INSUFFICIENT:"):
        return sufficiency
    ready = [
        branch for branch in branches.values()
        if branch.get("status") == "OOS_READY"
    ]
    insufficient = [
        str(branch.get("sample_status"))
        for branch in branches.values()
        if branch.get("status") == "SAMPLE_INSUFFICIENT"
    ]
    if not ready:
        return insufficient[0] if insufficient else f"样本不足 0/{MIN_COMPLETE_WINDOWS}"
    numbers = []
    for branch in ready:
        stitched = branch["stitched"]
        numbers.append(
            f"{branch['branch_id']} 样本外超额收益 {stitched['excess_return_pct']:.4f}%"
        )
    return "；".join(numbers + insufficient)


def run_backtest(
    instruments: Sequence[Instrument],
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    state_dir: Path | None = None,
    fee: FeeModel | None = None,
    capital_usd: float = DEFAULT_CAPITAL_USD,
    train_months: int = 24,
    test_months: int = 6,
) -> dict[str, Any]:
    """运行 S1/S2 的真实日线样本外回测，并可把运行期结果写到 state_dir。"""
    instrument_map = {instrument.symbol: instrument for instrument in instruments}
    fee = fee or FeeModel.default()
    branches = {
        "s1_momentum": _s1_backtest(
            bars_by_symbol, instrument_map, fee, capital_usd, train_months, test_months
        ),
        "s2_meanrev": _s2_backtest(
            bars_by_symbol, instrument_map, fee, capital_usd, train_months, test_months
        ),
    }
    # 每个分支条目自带样本外充足性与收益证据判定。
    # 只改顶层 profitability_status 不够：机器消费方读到分支上的 status="OOS_READY"
    # 会当成"收益结论可用"，而那正是本项目一路在消灭的误读面。
    # 但也不能重载 status —— "OOS_READY" 说的是滚动前推结构跑通了，
    # 与"收益证据是否充分"是两件事，混在一个字段里会级联污染顶层状态判定。
    # 因此用独立字段表达，语义不重叠。
    for branch in branches.values():
        sufficiency = branch_sample_sufficiency(branch)
        branch["sample_sufficiency"] = sufficiency
        insufficient = sufficiency.startswith("OOS_HISTORY_INSUFFICIENT:")
        branch["profitability_evidence"] = (
            "INSUFFICIENT" if insufficient else "SUFFICIENT"
        )
        if insufficient:
            branch["profitability_evidence_note"] = (
                "样本外历史不足，仅供研究参考，不构成收益证据"
            )
    for branch in branches.values():
        branch["sample_sufficiency"] = branch_sample_sufficiency(branch)
        branch["sample_sufficiency_message"] = (
            OOS_HISTORY_INSUFFICIENT_MESSAGE
            if branch["sample_sufficiency"].startswith("OOS_HISTORY_INSUFFICIENT:")
            else "样本外历史达到收益证据门。"
        )
    contributions = [
        sample
        for branch in branches.values()
        for sample in branch.get("contributions", [])
    ]
    result = {
        "status": "OOS_READY" if any(branch["status"] == "OOS_READY" for branch in branches.values()) else "SAMPLE_INSUFFICIENT",
        "method": {
            "out_of_sample_only": True,
            "train_months": train_months,
            "test_months": test_months,
            "minimum_complete_windows": MIN_COMPLETE_WINDOWS,
            "minimum_oos_windows_for_profitability": MIN_OOS_WINDOWS_FOR_PROFITABILITY,
            "profitability_gate": "收益数字与 PROMO-1 的 3 年样本外年限对齐；样本不足时只保留方向性研究结论。",
            "parameter_selection": "仅训练窗口网格搜索；实盘使用 train_end <= config_as_of 的最新已评价训练窗参数；test 窗口从不参与选参。",
            "risk_adjusted_excess_formula": "excess_return / active_daily_volatility；零波动时为 null。",
            "dynamic_contribution_weighting": "CONSUMED_BY_STAGE_3_AGGREGATE",
        },
        "fees": {
            "commission_usd_per_order": fee.commission_usd_per_order,
            "sec_fee_rate_on_sell": fee.sec_fee_rate_on_sell,
            "cat_fee_per_share": fee.cat_fee_per_share,
            "estimates_pending_official": fee.estimates_pending_official,
        },
        "branches": branches,
        "contribution_summary": {
            "sample_count": len(contributions),
            "samples": contributions,
            "storage": "state_dir/backtest/contribution_samples.json",
        },
        "sample_sufficiency": sample_sufficiency(branches),
        "sample_sufficiency_message": (
            OOS_HISTORY_INSUFFICIENT_MESSAGE
            if sample_sufficiency(branches).startswith("OOS_HISTORY_INSUFFICIENT:")
            else "样本外历史达到收益证据门。"
        ),
        "profitability_status": profitability_status(branches),
    }
    if state_dir is not None:
        persist_backtest_result(state_dir, result)
    return result


def persist_backtest_result(state_dir: Path, result: Mapping[str, Any]) -> None:
    """运行期落盘；state_dir 由部署配置提供，不进入 Git。"""
    root = state_dir / "backtest"
    root.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("latest.json", result),
        ("contribution_samples.json", result["contribution_summary"]),
    ):
        temporary = root / f".{name}.tmp"
        temporary.write_text(strict_json_dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, root / name)
