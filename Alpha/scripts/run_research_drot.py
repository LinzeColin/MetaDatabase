#!/usr/bin/env python3
"""DROT 轮:动态防御轮动(GLD/TLT/IEF 择强)× 冠军动量,晋级口径滚动前推,如实汇报。"""

from __future__ import annotations

import itertools
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
    S1Params, load_promo1_gate, metrics, pick_best, precompute, promo1_verdict,
    simulate_s1, walk_forward_windows,
)

START, END = date(2014, 1, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
FLOOR = {"name": "S1_GOLD_BLEND(生产保底线,静态GLD)", "monthly_pct": 0.662, "dd_pct": 13.07}
OUT = Path("reports/backtest/research_DROT_2026-07-19")


def build_grid(block: dict, basket: list) -> list[S1Params]:
    g = block["grid"]
    combos = itertools.product(
        [tuple(w) for w in g["weights_allowed"]],
        g["top_n_allowed"], g["target_vol_allowed"], g["rebalance_threshold_allowed"],
        g.get("high_proximity_allowed", [None]), g["defensive_weight_allowed"],
    )
    return [S1Params(weights=w, top_n=n, target_vol=float(v),
                     rebalance_threshold_pct=float(r),
                     eval_frequency=block["eval_frequency"],
                     high_proximity=(float(p) if p else None),
                     defensive_basket=tuple(basket), defensive_weight=float(dw))
            for w, n, v, r, p, dw in combos]


def main() -> int:
    fee = FeeModel.from_yaml()
    gate = load_promo1_gate()
    cfg = yaml.safe_load(Path("configs/strategies/research/defensive_rotation.yaml").read_text())
    universe, cash = list(cfg["universe"]), cfg["cash_proxy"]
    basket = list(cfg["defensive_basket"])

    series = {}
    for sym in universe:
        bars, _ev = fetch_verified(sym, START, END)
        series[sym] = precompute(sym, bars)
    cal = series["SPY"].days
    windows = walk_forward_windows(cal)
    print(f"门槛: {gate} 窗口: {len(windows)} 防御篮子: {basket}", flush=True)

    results = {}
    for name, block in cfg["candidates"].items():
        grid = build_grid(block, basket)
        oos_d, oos_e, chosen = [], [], []
        carry = CAPITAL_USD
        for t_start, t_end, v_start, v_end in windows:
            train = []
            for p in grid:
                r = simulate_s1(series, universe, cash, p, start=t_start, end=t_end,
                                sleeve_usd=CAPITAL_USD, fee=fee, calendar=cal)
                train.append((p, metrics(r.equity_days, r.equity)))
            best_p, _bm, dd_ok = pick_best(train)
            v = simulate_s1(series, universe, cash, best_p, start=v_start, end=v_end,
                            sleeve_usd=carry, fee=fee, calendar=cal)
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
              f"过门 {results[name]['promo1']['passed']}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research_report.json").write_text(json.dumps(
        {"round": "DROT 动态防御轮动", "gate": gate,
         "period": [START.isoformat(), END.isoformat()], "floor_reference": FLOOR,
         "defensive_basket": basket,
         "caveats": ["防御资产也须 T-1 >SMA200 才入选,否则退现金(该期防御预算闲置)",
                     "IEF/TLT/GLD 2014 前已上市,防御端无幸存者偏差",
                     "SEC/CAT 费保守高估占位"],
         "results": results}, ensure_ascii=False, indent=2, default=str))
    print("\n=== DROT 汇总(样本外) ===")
    for k, v in results.items():
        beats = (v["oos"].get("monthly_mean_net_pct", -999) > FLOOR["monthly_pct"]
                 and v["oos"].get("max_drawdown_pct", 999) < FLOOR["dd_pct"])
        print(k, json.dumps(v["oos"], ensure_ascii=False),
              "过门:", v["promo1"]["passed"], "| 全面超保底线:", beats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
