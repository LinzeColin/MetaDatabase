"""频率轴穷尽复盘(owner 2026-07-24 把频率上限从「每周一次」放宽到「最多 12 小时一次」)。

诚实前提:本机回测数据是**日线**,测不了日内;12 小时约束下能验证的极限粒度=**日频**。

两条线一起测,同引擎 / 同真实资金(3000 AUD × 0.65 = 1950 USD)/ 同费用 / 同窗口
(2015-2026,满 252 日预热)/ 同逐笔账本:

线一 · 现役规则换频率(只动节拍,其余参数不动 → 干净的频率实验,无选参偏差):
  五腿双动量精调 [0.2,0.4,0.4] Top-1,分别 daily / 2day / 3day / weekly(现役)

线二 · 日频均值回归(真正的新 alpha 家族;用 configs 预登记参数,不做网格挑选):
  S2 超卖反弹 RSI2<8 + IBS<0.2 + ATR14/close>1.5% + close>SMA200,4% 止损 / 10 日时间止损
  三个事前声明的变体:预登记(SPY/QQQ,双仓) / 单仓(小资金少整股浪费) / 五腿池单仓

费用是本实验的主角:每单 0.99 美元,1950 美元本金下一次往返≈0.10% —— 频率越高,
这条税就越重。让数据说话,不靠先验。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    S1Params, S2Params, ledger_metrics, precompute, simulate_s1, simulate_s2,
)

UNIVERSE = ["SPY", "EFA", "QQQ", "GLD", "IEF"]
CASH = "BIL"
CAPITAL_USD = 3000.0 * 0.65
WARMUP = 252

# S2 预登记参数(configs/strategies/s2_meanrev.yaml,未做任何网格挑选)
S2_PRE = S2Params(rsi_threshold=8.0, ibs_threshold=0.2, stop_loss_pct=4.0,
                  time_stop_days=10, vol_floor_pct=1.5)


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "reports/backtest/replay_frequency")
    out_dir.mkdir(parents=True, exist_ok=True)

    series = {}
    for sym in UNIVERSE + [CASH]:
        bars, _ = fetch_verified(sym, "2014-01-01", "2026-07-16", use_cache=True)
        series[sym] = precompute(sym, bars)
    calendar = sorted(series["SPY"].index_by_day)
    start, end = calendar[WARMUP], calendar[-1]
    fee = FeeModel.from_yaml("configs/fees.yaml")

    runs = {}

    # ---- 线一:现役规则,只换节拍 ----
    for freq, label in [("daily", "日频"), ("2day", "两日频"), ("3day", "三日频"),
                        ("weekly", "周频·现役")]:
        p = S1Params(weights=(0.2, 0.4, 0.4), top_n=1, target_vol=999.0,
                     rebalance_threshold_pct=5.0, eval_frequency=freq)
        runs[f"动量·{label}"] = simulate_s1(
            series, UNIVERSE, CASH, p, start=start, end=end,
            sleeve_usd=CAPITAL_USD, fee=fee, calendar=calendar)

    # ---- 线二:日频均值回归(事前声明的三变体) ----
    for label, core, max_open in [
        ("均值回归·预登记(SPY/QQQ双仓)", ["SPY", "QQQ"], 2),
        ("均值回归·单仓(SPY/QQQ)", ["SPY", "QQQ"], 1),
        ("均值回归·五腿池单仓", UNIVERSE, 1),
    ]:
        runs[label] = simulate_s2(
            series, core, S2_PRE, start=start, end=end, sleeve_usd=CAPITAL_USD,
            fee=fee, calendar=calendar, max_open=max_open)

    report = {"window": [start.isoformat(), end.isoformat()],
              "capital_usd": round(CAPITAL_USD, 2),
              "note": "频率轴:日线数据下极限=日频;线一只换节拍无选参偏差;线二用预登记参数",
              "results": {}}
    for name, res in runs.items():
        m = ledger_metrics(res.equity_days, res.equity, res.fills)
        m["orders"] = res.orders
        m["fees_usd"] = round(res.fees_usd, 2)
        m["fees_pct_of_capital"] = round(100.0 * res.fees_usd / CAPITAL_USD, 1)
        m["skipped_infeasible"] = res.skipped_infeasible
        report["results"][name] = m
    (out_dir / "replay_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str))

    print(f"\n{'策略':<26}{'月均%':>7}{'最大回撤%':>9}{'修复天':>7}{'盈亏比':>7}"
          f"{'胜率%':>7}{'往返':>6}{'下单':>6}{'总费用$':>9}{'费/本金%':>9}{'买不起':>7}")
    for name, m in report["results"].items():
        rec = m.get("max_dd_recovery_days")
        rec_s = "OPEN" if rec is None else str(rec)
        plr = m.get("per_trade_pl_ratio")
        plr_s = "∞" if plr == float("inf") else (f"{plr:.2f}" if plr is not None else "-")
        print(f"{name:<26}{m.get('monthly_mean_net_pct',0):>7.3f}"
              f"{m.get('max_drawdown_pct',0):>9.2f}{rec_s:>7}{plr_s:>7}"
              f"{m.get('per_trade_win_rate_pct') or 0:>7.1f}{m.get('round_trips',0):>6}"
              f"{m.get('orders',0):>6}{m.get('fees_usd',0):>9.2f}"
              f"{m.get('fees_pct_of_capital',0):>9.1f}{m.get('skipped_infeasible',0):>7}")
    print(f"\n报告 → {out_dir / 'replay_report.json'}")


if __name__ == "__main__":
    main()
