"""日历效应回测(研究线):月初月末窗口(TOM)持有,其余时间现金。

口径(与主流水线同费用模型、整股、T-1 资格判定):
- 入场:当月倒数第 entry_days_before 个交易日收盘价成交。交易日历是公开先验
  (交易所假日表提前数年公布),不构成前视;临时休市会使窗口移位一日,属报告
  注明的近似。
- 离场:次月第 exit_days_after 个交易日收盘价成交;回测段末日强制平仓——
  跨窗口的月初尾巴被截断,方向保守(宁可少算收益)。
- 趋势过滤(可选):入场日前一交易日收盘 > 当日 SMA200 才入场(资格用 T-1)。
- 买不起 1 股 = 跳过该月并计数(资金可行性一等公民)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import SleeveResult, SymbolSeries


@dataclass(frozen=True)
class TomParams:
    entry_days_before: int = 4     # 当月倒数第 N 个交易日收盘入场
    exit_days_after: int = 3       # 次月第 M 个交易日收盘离场
    use_trend_filter: bool = False # True:T-1 收盘须在 SMA200 上方


def simulate_tom(
    ss: SymbolSeries,
    params: TomParams,
    *,
    start: date,
    end: date,
    sleeve_usd: float,
    fee: FeeModel,
) -> SleeveResult:
    days = [d for d in ss.days if start <= d <= end]
    result = SleeveResult(equity_days=[], equity=[])
    if not days:
        return result

    by_month: dict[tuple[int, int], list[date]] = {}
    for d in days:
        by_month.setdefault((d.year, d.month), []).append(d)
    entry_days: set[date] = set()
    exit_days: set[date] = set()
    for mdays in by_month.values():
        if len(mdays) >= params.entry_days_before:
            entry_days.add(mdays[-params.entry_days_before])
        if len(mdays) >= params.exit_days_after:
            exit_days.add(mdays[params.exit_days_after - 1])

    cash = sleeve_usd
    qty = 0
    entry_price = 0.0
    last_day = days[-1]

    for d in days:
        j = ss.index_by_day[d]
        p = ss.closes[j]
        if qty > 0 and (d in exit_days or d == last_day):
            proceeds = qty * p - fee.order_cost_usd(side="SELL", quantity=qty, price=p)
            cash += proceeds
            result.fees_usd += fee.order_cost_usd(side="SELL", quantity=qty, price=p)
            result.orders += 1
            result.trades += 1
            if p > entry_price:
                result.wins += 1
            qty = 0
        if qty == 0 and d in entry_days and d != last_day:
            eligible = True
            if params.use_trend_filter:
                s200 = ss.sma200[j - 1] if j >= 1 else None
                eligible = s200 is not None and ss.closes[j - 1] > s200
            if eligible:
                q = (int((cash - fee.commission_usd_per_order) // p)
                     if cash > fee.commission_usd_per_order else 0)
                if q <= 0:
                    result.skipped_infeasible += 1
                else:
                    cost = q * p + fee.order_cost_usd(side="BUY", quantity=q, price=p)
                    if cost > cash:
                        q -= 1
                        cost = q * p + fee.order_cost_usd(side="BUY", quantity=q, price=p)
                    if q > 0 and cost <= cash:
                        cash -= cost
                        result.fees_usd += fee.order_cost_usd(side="BUY", quantity=q, price=p)
                        result.orders += 1
                        qty = q
                        entry_price = p
        result.equity_days.append(d)
        result.equity.append(cash + qty * p)
    return result
