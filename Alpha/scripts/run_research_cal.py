#!/usr/bin/env python3
"""CAL 轮:月初月末(TOM)日历效应,滚动前推样本外,如实汇报(门槛从配置读取)。"""

from __future__ import annotations

import itertools
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from backend.app.backtest.calendar_effects import TomParams, simulate_tom
from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    load_promo1_gate, metrics, pick_best, precompute, promo1_verdict,
    walk_forward_windows,
)

START, END = date(2014, 1, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
FLOOR = {"name": "S1_GOLD_BLEND(生产保底线)", "monthly_pct": 0.662, "dd_pct": 13.07}
OUT = Path("reports/backtest/research_CAL_2026-07-17")


def build_grid(g: dict) -> list[TomParams]:
    combos = itertools.product(
        g["entry_days_before_allowed"], g["exit_days_after_allowed"], g["trend_filter_allowed"])
    return [TomParams(entry_days_before=int(e), exit_days_after=int(x), use_trend_filter=bool(t))
            for e, x, t in combos]


def main() -> int:
    fee = FeeModel.from_yaml()
    gate = load_promo1_gate()
    cfg = yaml.safe_load(Path("configs/strategies/research/calendar_tom.yaml").read_text())

    results = {}
    for name, block in cfg["candidates"].items():
        sym = block["symbol"]
        bars, _ev = fetch_verified(sym, START, END)
        ss = precompute(sym, bars)
        windows = walk_forward_windows(ss.days)
        grid = build_grid(block["grid"])
        print(f"{name}: 门槛 {gate} 窗口 {len(windows)} 网格 {len(grid)}", flush=True)

        oos_d, oos_e, chosen = [], [], []
        carry = CAPITAL_USD
        skipped_total = 0
        for t_start, t_end, v_start, v_end in windows:
            train = []
            for p in grid:
                r = simulate_tom(ss, p, start=t_start, end=t_end,
                                 sleeve_usd=CAPITAL_USD, fee=fee)
                train.append((p, metrics(r.equity_days, r.equity)))
            best_p, _bm, dd_ok = pick_best(train)
            v = simulate_tom(ss, best_p, start=v_start, end=v_end,
                             sleeve_usd=carry, fee=fee)
            if v.equity:
                oos_d.extend(v.equity_days); oos_e.extend(v.equity); carry = v.equity[-1]
            skipped_total += v.skipped_infeasible
            chosen.append({"validate": [v_start.isoformat(), v_end.isoformat()],
                           "params": vars(best_p), "dd_ok": dd_ok,
                           "val": metrics(v.equity_days, v.equity)})
        m = metrics(oos_d, oos_e)
        results[name] = {"grid_size": len(grid), "oos": m,
                         "skipped_infeasible": skipped_total,
                         "promo1": promo1_verdict(m, **gate), "windows": chosen}
        print(f"{name}: 月均 {m.get('monthly_mean_net_pct')}% 回撤 {m.get('max_drawdown_pct')}% "
              f"过门 {results[name]['promo1']['passed']}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research_report.json").write_text(json.dumps(
        {"round": "CAL 日历效应(TOM)", "gate": gate,
         "period": [START.isoformat(), END.isoformat()],
         "fee_arithmetic": "每月1来回≈0.106%/月拖累(预筛通过;隔夜效应≈2.2%/月,算术淘汰)",
         "floor_reference": FLOOR,
         "caveats": ["窗口边界强制平仓,跨窗口月初尾巴被截断(保守方向)",
                     "临时休市会使日历窗口移位一日(近似)",
                     "SEC/CAT 费为保守高估占位"],
         "results": results}, ensure_ascii=False, indent=2, default=str))
    print("\n=== CAL 汇总(样本外) ===")
    for k, v in results.items():
        beats = (v["oos"].get("monthly_mean_net_pct", -999) > FLOOR["monthly_pct"]
                 and v["oos"].get("max_drawdown_pct", 999) <= 15.0)
        print(k, json.dumps(v["oos"], ensure_ascii=False),
              "过门:", v["promo1"]["passed"], "| 超保底线:", beats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
