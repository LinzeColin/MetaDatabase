"""滚动前推回测流水线(ALPHA-LIVE-050)。

口径与近似(全部在报告中如实声明):
- 信号只用 T-1 及更早数据:S1 周二评估用截至周一收盘;S2 收盘判定次日挂单。
- 成交近似:S1 于评估日收盘价成交;S2 入场限价(前收×0.995)当日最低触及才成交、
  成交价=限价;止损按触发日收盘成交;获利/超时按次日收盘成交(保守方向)。
- 整股约束:按 3000 AUD 真实资金逐股取整;买不起一股 = 跳过并计数
  (资金可行性是本回测的一等公民产出,不藏在脚注里)。
- 费用:每单佣金 + CAT 每股费 + 卖出 SEC 费(保守高估占位,报告标注待官方核验)。
- 回测层用浮点(研究口径);实盘资金路径仍全 Decimal。
- 组合 = S1 sleeve + S2 sleeve 各自独立复利,不跨 sleeve 再平衡(月度评审职责,
  本版不模拟),报告声明该近似。
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Sequence

from backend.app.backtest.fees import FeeModel
from backend.app.strategies.bars import Bar
from backend.app.strategies.indicators import (
    atr,
    ibs,
    realized_vol_annual_pct,
    rsi_wilder,
    sma,
    trailing_return,
)

TRADING_DAYS_PER_YEAR = 252


# ---------- 通用指标预计算 ----------

@dataclass
class SymbolSeries:
    symbol: str
    days: list[date]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    sma200: list[Optional[float]] = field(default_factory=list)
    sma5: list[Optional[float]] = field(default_factory=list)
    rsi2: list[Optional[float]] = field(default_factory=list)
    ibs_v: list[Optional[float]] = field(default_factory=list)
    atr14_ratio: list[Optional[float]] = field(default_factory=list)
    r63: list[Optional[float]] = field(default_factory=list)
    r126: list[Optional[float]] = field(default_factory=list)
    r252: list[Optional[float]] = field(default_factory=list)
    vol20: list[Optional[float]] = field(default_factory=list)
    index_by_day: dict[date, int] = field(default_factory=dict)


def precompute(symbol: str, bars: Sequence[Bar]) -> SymbolSeries:
    days = [b.day for b in bars]
    opens = [b.open for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    s = SymbolSeries(symbol, days, opens, highs, lows, closes)
    n = len(bars)
    for i in range(n):
        window = closes[: i + 1]
        s.sma200.append(sma(window, 200))
        s.sma5.append(sma(window, 5))
        s.rsi2.append(rsi_wilder(window[-40:], 2) if i >= 2 else None)
        s.ibs_v.append(ibs(highs[i], lows[i], closes[i]))
        a = atr(highs[: i + 1][-20:], lows[: i + 1][-20:], window[-20:], 14)
        s.atr14_ratio.append((a / closes[i]) if a is not None else None)
        s.r63.append(trailing_return(window, 63))
        s.r126.append(trailing_return(window, 126))
        s.r252.append(trailing_return(window, 252))
        s.vol20.append(realized_vol_annual_pct(window, 20))
        s.index_by_day[days[i]] = i
    return s


# ---------- S1 参数与模拟 ----------

@dataclass(frozen=True)
class S1Params:
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3)
    top_n: int = 2
    target_vol: float = 12.0
    rebalance_threshold_pct: float = 5.0


@dataclass
class SleeveResult:
    equity_days: list[date]
    equity: list[float]
    orders: int = 0
    fees_usd: float = 0.0
    skipped_infeasible: int = 0
    trades: int = 0
    wins: int = 0
    extra: dict = field(default_factory=dict)


def simulate_s1(
    series: dict[str, SymbolSeries],
    universe: list[str],
    cash_proxy: str,
    params: S1Params,
    *,
    start: date,
    end: date,
    sleeve_usd: float,
    fee: FeeModel,
    calendar: list[date],
) -> SleeveResult:
    cash = sleeve_usd
    shares: dict[str, int] = {}
    result = SleeveResult(equity_days=[], equity=[])

    def price(sym: str, idx: int) -> float:
        return series[sym].closes[idx]

    for day in calendar:
        if day < start or day > end:
            continue
        ref = series[universe[0]]
        idx = ref.index_by_day.get(day)
        if idx is None:
            continue
        # 周二评估:用截至前一交易日(idx-1)的数据
        if day.weekday() == 1 and idx >= 1:
            scores: dict[str, float] = {}
            for sym in universe:
                if sym == cash_proxy:
                    continue
                ss = series.get(sym)
                j = ss.index_by_day.get(day) if ss else None
                j_eval = (j - 1) if j is not None and j >= 1 else None
                if j_eval is None:
                    continue
                r1, r2, r3 = ss.r63[j_eval], ss.r126[j_eval], ss.r252[j_eval]
                s200 = ss.sma200[j_eval]
                if None in (r1, r2, r3) or s200 is None:
                    continue
                if ss.closes[j_eval] <= s200:
                    continue
                w1, w2, w3 = params.weights
                scores[sym] = w1 * r1 + w2 * r2 + w3 * r3
            ranked = sorted(scores, key=lambda s_: (-scores[s_], universe.index(s_)))
            selected = ranked[: params.top_n]
            scalar = 1.0
            if selected:
                vols = []
                for sym in selected:
                    ss = series[sym]
                    j = ss.index_by_day.get(day)
                    v = ss.vol20[j - 1] if j is not None and j >= 1 else None
                    if v is not None:
                        vols.append(v)
                if vols:
                    pv = sum(vols) / len(vols)
                    if pv > 0:
                        scalar = min(1.0, params.target_vol / pv)
            equity_now = cash + sum(
                q * price(sym, series[sym].index_by_day[day])
                for sym, q in shares.items() if day in series[sym].index_by_day
            )
            targets: dict[str, int] = {}
            target_syms = selected if selected else [cash_proxy]
            weight_each = (1.0 / params.top_n) * scalar if selected else 1.0
            for sym in target_syms:
                j = series[sym].index_by_day.get(day)
                if j is None:
                    continue
                notional = equity_now * weight_each
                targets[sym] = int(notional // price(sym, j))
            threshold_usd = equity_now * params.rebalance_threshold_pct / 100.0
            for sym in sorted(set(shares) | set(targets)):
                j = series[sym].index_by_day.get(day)
                if j is None:
                    continue
                cur, tgt = shares.get(sym, 0), targets.get(sym, 0)
                delta = tgt - cur
                if delta == 0:
                    continue
                p = price(sym, j)
                if abs(delta) * p < threshold_usd:
                    continue
                if delta > 0:
                    cost = delta * p + fee.order_cost_usd(side="BUY", quantity=delta, price=p)
                    if cost > cash:
                        afford = int((cash - fee.commission_usd_per_order) // p) if cash > fee.commission_usd_per_order else 0
                        if afford <= 0:
                            result.skipped_infeasible += 1
                            continue
                        delta = afford
                        cost = delta * p + fee.order_cost_usd(side="BUY", quantity=delta, price=p)
                    cash -= cost
                    result.fees_usd += fee.order_cost_usd(side="BUY", quantity=delta, price=p)
                    shares[sym] = cur + delta
                    result.orders += 1
                else:
                    sell_q = -delta
                    proceeds = sell_q * p - fee.order_cost_usd(side="SELL", quantity=sell_q, price=p)
                    cash += proceeds
                    result.fees_usd += fee.order_cost_usd(side="SELL", quantity=sell_q, price=p)
                    shares[sym] = cur + delta
                    if shares[sym] == 0:
                        del shares[sym]
                    result.orders += 1

        equity = cash
        for sym, q in shares.items():
            j = series[sym].index_by_day.get(day)
            if j is not None:
                equity += q * series[sym].closes[j]
        result.equity_days.append(day)
        result.equity.append(equity)
    return result


# ---------- S2 参数与模拟 ----------

@dataclass(frozen=True)
class S2Params:
    rsi_threshold: float = 8.0
    ibs_threshold: float = 0.2
    stop_loss_pct: float = 4.0
    time_stop_days: int = 10
    vol_floor_pct: float = 1.5


def simulate_s2(
    series: dict[str, SymbolSeries],
    core_universe: list[str],
    params: S2Params,
    *,
    start: date,
    end: date,
    sleeve_usd: float,
    fee: FeeModel,
    calendar: list[date],
    max_open: int = 2,
) -> SleeveResult:
    cash = sleeve_usd
    open_trades: list[dict] = []
    pending_entries: list[dict] = []
    pending_exits: list[dict] = []
    result = SleeveResult(equity_days=[], equity=[])

    for day in calendar:
        if day < start or day > end:
            continue
        # 1) 处理挂单入场(昨日信号,今日限价)
        for order in list(pending_entries):
            ss = series[order["symbol"]]
            j = ss.index_by_day.get(day)
            if j is None:
                continue
            pending_entries.remove(order)
            limit = order["limit"]
            qty = int((sleeve_usd / max_open) // limit)
            if qty <= 0:
                result.skipped_infeasible += 1   # 3000 AUD 整股买不起:一等公民指标
                continue
            if ss.lows[j] <= limit:
                cost = qty * limit + fee.order_cost_usd(side="BUY", quantity=qty, price=limit)
                if cost > cash:
                    result.skipped_infeasible += 1
                    continue
                cash -= cost
                result.fees_usd += fee.order_cost_usd(side="BUY", quantity=qty, price=limit)
                result.orders += 1
                open_trades.append({"symbol": order["symbol"], "qty": qty, "entry": limit,
                                    "entry_day": day, "held": 0})
        # 2) 处理待执行离场(昨日判定,今日收盘成交)
        for ex in list(pending_exits):
            ss = series[ex["symbol"]]
            j = ss.index_by_day.get(day)
            if j is None:
                continue
            pending_exits.remove(ex)
            p = ss.closes[j]
            proceeds = ex["qty"] * p - fee.order_cost_usd(side="SELL", quantity=ex["qty"], price=p)
            cash += proceeds
            result.fees_usd += fee.order_cost_usd(side="SELL", quantity=ex["qty"], price=p)
            result.orders += 1
            result.trades += 1
            if p > ex["entry"]:
                result.wins += 1
        # 3) 持仓天数与当日离场判定
        for trade in list(open_trades):
            ss = series[trade["symbol"]]
            j = ss.index_by_day.get(day)
            if j is None:
                continue
            trade["held"] += 1
            close = ss.closes[j]
            stop_price = trade["entry"] * (1 - params.stop_loss_pct / 100.0)
            if close <= stop_price:
                # 止损:触发日收盘市价成交
                proceeds = trade["qty"] * close - fee.order_cost_usd(side="SELL", quantity=trade["qty"], price=close)
                cash += proceeds
                result.fees_usd += fee.order_cost_usd(side="SELL", quantity=trade["qty"], price=close)
                result.orders += 1
                result.trades += 1
                open_trades.remove(trade)
                continue
            s5 = ss.sma5[j]
            if trade["held"] >= params.time_stop_days or (s5 is not None and close > s5 and trade["held"] >= 1):
                open_trades.remove(trade)
                pending_exits.append(trade)
        # 4) 收盘信号 -> 次日挂单
        slots = max_open - len(open_trades) - len(pending_entries) - len(pending_exits)
        if slots > 0:
            held_syms = {t["symbol"] for t in open_trades} | {o["symbol"] for o in pending_entries}
            for sym in core_universe:
                if slots <= 0 or sym in held_syms:
                    continue
                ss = series[sym]
                j = ss.index_by_day.get(day)
                if j is None:
                    continue
                s200, r2, i_v, a_r = ss.sma200[j], ss.rsi2[j], ss.ibs_v[j], ss.atr14_ratio[j]
                if None in (s200, r2, i_v, a_r):
                    continue
                if (ss.closes[j] > s200 and r2 < params.rsi_threshold
                        and i_v < params.ibs_threshold and a_r > params.vol_floor_pct / 100.0):
                    pending_entries.append({"symbol": sym, "limit": round(ss.closes[j] * 0.995, 2)})
                    slots -= 1
        # 5) 逐日净值
        equity = cash
        for trade in open_trades + pending_exits:
            ss = series[trade["symbol"]]
            j = ss.index_by_day.get(day)
            if j is not None:
                equity += trade["qty"] * ss.closes[j]
        result.equity_days.append(day)
        result.equity.append(equity)
    return result


# ---------- 指标与判定 ----------

def monthly_returns(days: Sequence[date], equity: Sequence[float]) -> list[tuple[str, float]]:
    if not days:
        return []
    out: list[tuple[str, float]] = []
    month_start_val = equity[0]
    cur_month = (days[0].year, days[0].month)
    last_val = equity[0]
    for d, v in zip(days, equity):
        if (d.year, d.month) != cur_month:
            out.append((f"{cur_month[0]}-{cur_month[1]:02d}", last_val / month_start_val - 1.0))
            cur_month = (d.year, d.month)
            month_start_val = last_val
        last_val = v
    out.append((f"{cur_month[0]}-{cur_month[1]:02d}", last_val / month_start_val - 1.0))
    return out


def max_drawdown(equity: Sequence[float]) -> float:
    peak, mdd = -math.inf, 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, 1.0 - v / peak)
    return mdd


def metrics(days: Sequence[date], equity: Sequence[float]) -> dict:
    mr = monthly_returns(days, equity)
    rets = [r for _, r in mr]
    if not rets or equity[0] <= 0:
        return {"months": 0}
    total_growth = equity[-1] / equity[0]
    geo_monthly = total_growth ** (1.0 / len(rets)) - 1.0
    wins = [r for r in rets if r > 0]
    losses = [abs(r) for r in rets if r < 0]
    return {
        "months": len(rets),
        "years": round(len(rets) / 12.0, 2),
        "total_return_pct": round((total_growth - 1.0) * 100, 2),
        "monthly_mean_net_pct": round(geo_monthly * 100, 3),
        "max_drawdown_pct": round(max_drawdown(equity) * 100, 2),
        "monthly_win_rate_pct": round(100.0 * len(wins) / len(rets), 1),
        "profit_factor": round(sum(wins) / sum(losses), 2) if losses else math.inf,
    }


def promo1_verdict(m: dict, *, gate_monthly_pct: float = 5.0, gate_dd_pct: float = 15.0,
                   min_years: float = 3.0) -> dict:
    ok_years = m.get("years", 0) >= min_years
    ok_ret = m.get("monthly_mean_net_pct", -999) >= gate_monthly_pct
    ok_dd = m.get("max_drawdown_pct", 999) <= gate_dd_pct
    return {
        "years_ok": ok_years, "monthly_return_ok": ok_ret, "drawdown_ok": ok_dd,
        "passed": ok_years and ok_ret and ok_dd,
        "gate": {"monthly_pct": gate_monthly_pct, "dd_pct": gate_dd_pct, "min_years": min_years},
    }


# ---------- 滚动前推 ----------

def walk_forward_windows(calendar: Sequence[date], *, train_months: int = 24,
                         validate_months: int = 6) -> list[tuple[date, date, date, date]]:
    """返回 (train_start, train_end, val_start, val_end) 列表,按 validate 步长滚动。"""
    if not calendar:
        return []
    def add_months(d: date, m: int) -> date:
        y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
        return date(y, mo, 1)
    windows = []
    cursor = date(calendar[0].year, calendar[0].month, 1)
    last = calendar[-1]
    while True:
        t_start = cursor
        t_end = add_months(t_start, train_months)
        v_end = add_months(t_end, validate_months)
        if t_end > last:
            break
        windows.append((t_start, t_end, t_end, min(v_end, last)))
        if v_end > last:
            break
        cursor = add_months(cursor, validate_months)
    return windows


def s1_grid(review_grid: dict) -> list[S1Params]:
    combos = itertools.product(
        [tuple(w) for w in review_grid["weights_allowed"]],
        review_grid["top_n_allowed"],
        review_grid["target_vol_allowed"],
        review_grid["rebalance_threshold_allowed"],
    )
    return [S1Params(weights=w, top_n=n, target_vol=float(v), rebalance_threshold_pct=float(r))
            for w, n, v, r in combos]


def s2_grid(review_grid: dict) -> list[S2Params]:
    combos = itertools.product(
        review_grid["rsi_threshold_allowed"],
        review_grid["ibs_threshold_allowed"],
        review_grid["stop_loss_allowed"],
        review_grid["time_stop_allowed"],
        review_grid["volatility_floor_allowed"],
    )
    return [S2Params(rsi_threshold=float(r), ibs_threshold=float(i), stop_loss_pct=float(s),
                     time_stop_days=int(t), vol_floor_pct=float(v))
            for r, i, s, t, v in combos]


def pick_best(candidates: list[tuple[object, dict]], *, dd_cap: float = 15.0) -> tuple[object, dict, bool]:
    """训练窗选优:回撤达标里挑月均最高;全不达标挑回撤最小并标旗。"""
    within = [(p, m) for p, m in candidates if m.get("max_drawdown_pct", 999) <= dd_cap]
    if within:
        p, m = max(within, key=lambda x: x[1].get("monthly_mean_net_pct", -999))
        return p, m, True
    p, m = min(candidates, key=lambda x: x[1].get("max_drawdown_pct", 999))
    return p, m, False
