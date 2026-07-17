#!/usr/bin/env python3
"""第六批:时点正确的道指 30 个股动量(无幸存者偏差)± 黄金叠加。

名单:configs/strategies/research/djia_membership.yaml(每评估日取当期成分)。
口径:双源核验/含费用/3000 澳元整股/训练2年验证6个月滚动/网格内选优/样本外如实。
"""

from __future__ import annotations

import itertools
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from backend.app.backtest.data_sources import DataIntegrityError, fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    S1Params, load_promo1_gate, metrics, pick_best, precompute, promo1_verdict,
    simulate_s1, walk_forward_windows,
)

START, END = date(2014, 1, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
OUT = Path("reports/backtest/research_PIT_2026-07-18")
CAL_REF = ["SPY", "BIL"]  # 日历参照+现金替身(SPY 只作日历,不入候选)


def main() -> int:
    fee = FeeModel.from_yaml()
    gate = load_promo1_gate()
    mem = yaml.safe_load(Path("configs/strategies/research/djia_membership.yaml").read_text())
    snaps = sorted((s["effective_from"], s["tickers"]) for s in mem["snapshots"])

    def members_on(day: date) -> list[str]:
        current = snaps[0][1]
        for eff, tks in snaps:
            if date.fromisoformat(eff) <= day:
                current = tks
            else:
                break
        return current

    all_tickers = sorted({t for _, tks in snaps for t in tks} | {"GLD", "SPY", "BIL"})
    series, failed = {}, []
    for sym in all_tickers:
        try:
            bars, _ev = fetch_verified(sym, START, END)
            series[sym] = precompute(sym, bars)
        except (DataIntegrityError, ConnectionError) as exc:
            failed.append({"symbol": sym, "reason": str(exc)[:160]})
            print(f"⚠️ {sym} 数据不可得: {exc}", flush=True)
    print(f"数据就绪 {len(series)}/{len(all_tickers)};失败 {len(failed)}", flush=True)

    def usable_members(day: date) -> list[str]:
        return [t for t in members_on(day) if t in series]

    cal = series["SPY"].days
    windows = walk_forward_windows(cal)
    print(f"门槛 {gate} 窗口 {len(windows)}", flush=True)

    blocks = {
        "PIT_stock_momentum": {
            "grids": itertools.product(
                [(0.7, 0.2, 0.1), (0.4, 0.3, 0.3)], [1, 2, 3], [15.0, 999.0],
                [None, 0.90], [(None, 0.0)]),
        },
        "PIT_gold_blend": {
            "grids": itertools.product(
                [(0.7, 0.2, 0.1)], [1, 2], [999.0],
                [0.90], [("GLD", 0.2), ("GLD", 0.3)]),
        },
    }
    results = {}
    for name, spec in blocks.items():
        grid = [S1Params(weights=w, top_n=n, target_vol=v, rebalance_threshold_pct=5.0,
                         high_proximity=p, defensive_symbol=ds, defensive_weight=dw)
                for w, n, v, p, (ds, dw) in spec["grids"]]
        oos_d, oos_e, chosen = [], [], []
        carry = CAPITAL_USD
        for t_start, t_end, v_start, v_end in windows:
            train = []
            for prm in grid:
                r = simulate_s1(series, CAL_REF, "BIL", prm, start=t_start, end=t_end,
                                sleeve_usd=CAPITAL_USD, fee=fee, calendar=cal,
                                universe_fn=usable_members)
                train.append((prm, metrics(r.equity_days, r.equity)))
            best_p, _bm, dd_ok = pick_best(train)
            v = simulate_s1(series, CAL_REF, "BIL", best_p, start=v_start, end=v_end,
                            sleeve_usd=carry, fee=fee, calendar=cal,
                            universe_fn=usable_members)
            if v.equity:
                oos_d.extend(v.equity_days); oos_e.extend(v.equity); carry = v.equity[-1]
            chosen.append({"validate": [v_start.isoformat(), v_end.isoformat()],
                           "params": {k: (list(x) if isinstance(x, tuple) else x)
                                      for k, x in vars(best_p).items()},
                           "dd_ok": dd_ok, "val": metrics(v.equity_days, v.equity)})
        m = metrics(oos_d, oos_e)
        results[name] = {"grid_size": len(grid), "oos": m,
                         "promo1": promo1_verdict(m, **gate), "windows": chosen}
        print(f"{name}: 月均 {m.get('monthly_mean_net_pct')}% 回撤 {m.get('max_drawdown_pct')}% "
              f"过保底门 {results[name]['promo1']['passed']}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research_report.json").write_text(json.dumps(
        {"round": "第六批·时点道指(无幸存者偏差)", "gate": gate,
         "period": [START.isoformat(), END.isoformat()],
         "membership_source": mem["source"], "data_failed": failed,
         "results": results}, ensure_ascii=False, indent=2, default=str))
    print("\n=== 第六批汇总(样本外,无偏名单) ===")
    for k, v in results.items():
        print(k, json.dumps(v["oos"], ensure_ascii=False), "过保底门:", v["promo1"]["passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
