#!/usr/bin/env python3
"""CAL-2:季节窗口(万圣节效应)叠加在冻结的冠军参数上,直跑样本外 A/B。

方法声明:参数全部冻结为生产配置(s1_gold_blend.yaml 当选参数),只变
in_market_months 一个轴,同段直跑对比——无重训、无选择自由度,归因最干净。
若某窗口版胜出,晋级前仍须走完整滚动前推重训协议再确认。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    S1Params, load_promo1_gate, metrics, precompute, promo1_verdict, simulate_s1,
)

START_DATA, START_OOS, END = date(2014, 1, 1), date(2016, 1, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
OUT = Path("reports/backtest/research_CAL2_2026-07-17")

CHAMPION = dict(weights=(0.7, 0.2, 0.1), top_n=1, target_vol=999.0,
                rebalance_threshold_pct=5.0, eval_frequency="weekly",
                high_proximity=0.90, defensive_symbol="GLD", defensive_weight=0.20)

WINDOWS = {
    "全年(冠军基线)": None,
    "万圣节(11-4月)": (11, 12, 1, 2, 3, 4),
    "扩展(10-5月)": (10, 11, 12, 1, 2, 3, 4, 5),
}


def main() -> int:
    fee = FeeModel.from_yaml()
    gate = load_promo1_gate()
    cfg = yaml.safe_load(Path("configs/strategies/s1_gold_blend.yaml").read_text())
    universe, cash = list(cfg["universe"]), cfg["cash_proxy"]

    series = {}
    for sym in universe:
        bars, _ev = fetch_verified(sym, START_DATA, END)
        series[sym] = precompute(sym, bars)
    cal = series[universe[0]].days

    results = {}
    for label, months in WINDOWS.items():
        p = S1Params(**CHAMPION, in_market_months=months)
        r = simulate_s1(series, universe, cash, p, start=START_OOS, end=END,
                        sleeve_usd=CAPITAL_USD, fee=fee, calendar=cal)
        m = metrics(r.equity_days, r.equity)
        results[label] = {"in_market_months": months, "oos": m,
                          "orders": r.orders, "fees_usd": round(r.fees_usd, 2),
                          "promo1": promo1_verdict(m, **gate)}
        print(f"{label}: 月均 {m.get('monthly_mean_net_pct')}% 回撤 {m.get('max_drawdown_pct')}% "
              f"订单 {r.orders} 费 {r.fees_usd:.2f}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research_report.json").write_text(json.dumps(
        {"round": "CAL-2 季节窗口×冻结冠军", "gate": gate,
         "period_oos": [START_OOS.isoformat(), END.isoformat()],
         "method": "参数冻结为生产配置,仅变 in_market_months,同段直跑 A/B(无重训)",
         "champion_frozen": {k: (list(v) if isinstance(v, tuple) else v)
                             for k, v in CHAMPION.items()},
         "results": results}, ensure_ascii=False, indent=2, default=str))
    print("\n=== CAL-2 汇总(冻结参数直跑,同段对比) ===")
    for k, v in results.items():
        print(k, json.dumps(v["oos"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
