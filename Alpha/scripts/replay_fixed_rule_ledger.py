"""固定规则连续复盘 + 逐笔账本(补策略表『盈亏比/胜率/回撤修复时间』三列的真数字)。

动机:外部量化复核包指出——WFO 报告只有月度聚合,没有连续逐笔账本与回撤 episodes,
所以逐笔盈亏比、逐笔胜率、回撤修复时间在旧表里只能写"未验证"。本脚本对实盘部署的
固定规则做一次跨全样本的连续单次模拟,产出真实的 closed round-trip 账本与回撤修复时间。

对三条固定规则用同一引擎、同一真实资金(3000 AUD × 0.65 = 1950 USD)、同一费用模型跑:
  1) 精调版末窗选参 [0.2,0.4,0.4]/Top-1  —— 实盘现役固定规则
  2) 基础版末窗选参 [0.3,0.3,0.4]/Top-1  —— 外部复核偏好的更简单版
  3) SPY 买入持有                        —— 基准

诚实口径(全部随报告声明):
- 这是"固定规则"的独立连续回测,不是每 6 个月重选参的动态 WFO 流程;两者不可混用,
  也不冒充报告里 1.108%/1.052% 的流程级数字。
- 数据 2014-01-02 → 2026-07-16(本机缓存可得区间),晚于报告声称的 2010 起;如实标注。
- 起点取满 252 交易日指标预热之后,三者同起点公平对比(约 11.5 年)。
- 资金 1950 USD + 整股约束 = 真实账户颗粒度(会有整股拖累,这是实盘真相,不是缺陷)。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    S1Params, drawdown_episodes, ledger_metrics, precompute, simulate_s1,
)

UNIVERSE = ["SPY", "EFA", "QQQ", "GLD", "IEF"]
CASH = "BIL"
CAPITAL_AUD, FX = 3000.0, 0.65
CAPITAL_USD = CAPITAL_AUD * FX
WARMUP = 252  # 满 252 日后 r252/SMA200 才就绪 → 公平起点

RULES = {
    "精调版[0.2,0.4,0.4]·实盘现役": S1Params(weights=(0.2, 0.4, 0.4), top_n=1,
                                          target_vol=999.0, rebalance_threshold_pct=5.0),
    "基础版[0.3,0.3,0.4]·复核偏好": S1Params(weights=(0.3, 0.3, 0.4), top_n=1,
                                          target_vol=999.0, rebalance_threshold_pct=5.0),
}


def spy_buy_hold(series, calendar, start, end, fee) -> dict:
    """SPY 买入持有基准:起点用可用资金买满整股,持有到末,逐日盯市。"""
    ss = series["SPY"]
    i0 = ss.index_by_day[start]
    p0 = ss.closes[i0]
    qty = int((CAPITAL_USD - fee.commission_usd_per_order) // p0)
    buy_fee = fee.order_cost_usd(side="BUY", quantity=qty, price=p0)
    cash = CAPITAL_USD - qty * p0 - buy_fee
    days, equity, fills = [], [], [
        {"day": start, "sym": "SPY", "side": "BUY", "qty": qty, "price": p0, "fee": buy_fee}]
    last_p = p0
    for d in calendar:
        if d < start or d > end:
            continue
        j = ss.index_by_day.get(d)
        if j is not None:
            last_p = ss.closes[j]
        days.append(d)
        equity.append(cash + qty * last_p)
    # 末日平仓一笔,凑成 closed round-trip(供逐笔口径)
    sell_fee = fee.order_cost_usd(side="SELL", quantity=qty, price=last_p)
    fills.append({"day": end, "sym": "SPY", "side": "SELL", "qty": qty,
                  "price": last_p, "fee": sell_fee})
    return {"days": days, "equity": equity, "fills": fills}


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "reports/backtest/replay_fixedrule")
    out_dir.mkdir(parents=True, exist_ok=True)

    series = {}
    for sym in UNIVERSE + [CASH]:
        bars, _ = fetch_verified(sym, "2014-01-01", "2026-07-16", use_cache=True)
        series[sym] = precompute(sym, bars)
    calendar = sorted(series["SPY"].index_by_day)
    start = calendar[WARMUP]
    end = calendar[-1]
    fee = FeeModel.from_yaml("configs/fees.yaml")

    report = {"window": [start.isoformat(), end.isoformat()],
              "capital_usd": round(CAPITAL_USD, 2), "warmup_days": WARMUP,
              "note": "固定规则连续复盘(非动态WFO);数据2014起,晚于报告2010;整股@1950USD真实颗粒度",
              "results": {}}

    for name, params in RULES.items():
        res = simulate_s1(series, UNIVERSE, CASH, params, start=start, end=end,
                          sleeve_usd=CAPITAL_USD, fee=fee, calendar=calendar)
        m = ledger_metrics(res.equity_days, res.equity, res.fills)
        m["orders"] = res.orders
        m["fees_usd"] = round(res.fees_usd, 2)
        m["skipped_infeasible"] = res.skipped_infeasible
        report["results"][name] = m

    bh = spy_buy_hold(series, calendar, start, end, fee)
    report["results"]["SPY买入持有·基准"] = ledger_metrics(bh["days"], bh["equity"], bh["fills"])

    (out_dir / "replay_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str))

    # ---- 控制台对照表 ----
    cols = [("月均净", "monthly_mean_net_pct", "%"), ("CAGR推算", None, ""),
            ("最大回撤", "max_drawdown_pct", "%"), ("修复", "max_dd_recovery_days", "天"),
            ("逐笔盈亏比", "per_trade_pl_ratio", ""), ("逐笔胜率", "per_trade_win_rate_pct", "%"),
            ("往返数", "round_trips", ""), ("月胜率", "monthly_win_rate_pct", "%")]
    print(f"\n{'策略':<26}{'月数':>5}{'总收益%':>9}{'月均%':>7}{'最大回撤%':>9}"
          f"{'修复天':>7}{'逐笔盈亏比':>9}{'逐笔胜率%':>9}{'往返':>6}")
    for name, m in report["results"].items():
        rec = m.get("max_dd_recovery_days")
        rec_s = "OPEN" if rec is None else str(rec)
        plr = m.get("per_trade_pl_ratio")
        plr_s = "∞" if plr == float("inf") else (f"{plr:.2f}" if plr is not None else "-")
        print(f"{name:<26}{m.get('months',0):>5}{m.get('total_return_pct',0):>9.2f}"
              f"{m.get('monthly_mean_net_pct',0):>7.3f}{m.get('max_drawdown_pct',0):>9.2f}"
              f"{rec_s:>7}{plr_s:>9}{m.get('per_trade_win_rate_pct') or 0:>9.1f}"
              f"{m.get('round_trips',0):>6}")
    print(f"\n报告 → {out_dir / 'replay_report.json'}")


if __name__ == "__main__":
    main()
