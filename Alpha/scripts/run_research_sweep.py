#!/usr/bin/env python3
"""策略结构改造循环 R1 扫描(2026-07-17,owner 裁定维持 5%/月门槛)。

对研究候选(S3 行业轮动 / S1R 宽网格 / S2B 低价池)做与生产判定同口径的
滚动前推:双源核验数据、含费用、整股约束、训练2年/验证6个月、网格内选优。
样本外结果如实输出——达标/不达标都直接写明。
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

from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    S1Params,
    S2Params,
    metrics,
    pick_best,
    precompute,
    promo1_verdict,
    s2_grid,
    simulate_s1,
    simulate_s2,
    walk_forward_windows,
)

START, END = date(2014, 1, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
OUT = Path("reports/backtest/research_R1_2026-07-17")


def momentum_grid(review_grid: dict) -> list[S1Params]:
    combos = itertools.product(
        [tuple(w) for w in review_grid["weights_allowed"]],
        review_grid["top_n_allowed"],
        review_grid["target_vol_allowed"],
        review_grid["rebalance_threshold_allowed"],
    )
    return [S1Params(weights=w, top_n=n, target_vol=float(v), rebalance_threshold_pct=float(r))
            for w, n, v, r in combos]


def walk_forward_momentum(series, universe, cash, grid, windows, calendar, sleeve, fee):
    oos_days, oos_eq, chosen = [], [], []
    carry = sleeve
    for t_start, t_end, v_start, v_end in windows:
        train = [(p, metrics(*_sim_eq(series, universe, cash, p, t_start, t_end, sleeve, fee, calendar)))
                 for p in grid]
        best_p, best_m, dd_ok = pick_best(train)
        d, e = _sim_eq(series, universe, cash, best_p, v_start, v_end, carry, fee, calendar)
        if e:
            oos_days.extend(d)
            oos_eq.extend(e)
            carry = e[-1]
        chosen.append({"validate": [v_start.isoformat(), v_end.isoformat()],
                       "params": vars(best_p) | {"weights": list(best_p.weights)},
                       "dd_ok": dd_ok, "val": metrics(d, e)})
    return oos_days, oos_eq, chosen


def _sim_eq(series, universe, cash, p, start, end, sleeve, fee, calendar):
    r = simulate_s1(series, universe, cash, p, start=start, end=end,
                    sleeve_usd=sleeve, fee=fee, calendar=calendar)
    return r.equity_days, r.equity


def walk_forward_meanrev(series, universe, grid, windows, calendar, sleeve, fee):
    oos_days, oos_eq, chosen = [], [], []
    carry = sleeve
    trades = wins = skipped = 0
    for t_start, t_end, v_start, v_end in windows:
        train = []
        for p in grid:
            r = simulate_s2(series, universe, p, start=t_start, end=t_end,
                            sleeve_usd=sleeve, fee=fee, calendar=calendar)
            train.append((p, metrics(r.equity_days, r.equity)))
        best_p, best_m, dd_ok = pick_best(train)
        v = simulate_s2(series, universe, best_p, start=v_start, end=v_end,
                        sleeve_usd=carry, fee=fee, calendar=calendar)
        if v.equity:
            oos_days.extend(v.equity_days)
            oos_eq.extend(v.equity)
            carry = v.equity[-1]
        trades += v.trades; wins += v.wins; skipped += v.skipped_infeasible
        chosen.append({"validate": [v_start.isoformat(), v_end.isoformat()],
                       "params": vars(best_p), "dd_ok": dd_ok,
                       "val": metrics(v.equity_days, v.equity)})
    return oos_days, oos_eq, chosen, {"trades": trades, "wins": wins, "skipped_infeasible": skipped}


def main() -> int:
    fee = FeeModel.from_yaml()
    s3 = yaml.safe_load(Path("configs/strategies/research/s3_sector_momentum.yaml").read_text())
    s1r = yaml.safe_load(Path("configs/strategies/research/s1r_momentum_wide.yaml").read_text())
    s2b = yaml.safe_load(Path("configs/strategies/research/s2b_meanrev_affordable.yaml").read_text())

    symbols = sorted(set(s3["universe"]) | set(s1r["universe"]) | set(s2b["universe"]["core"]))
    bars_map, evidence = {}, []
    for sym in symbols:
        bars, ev = fetch_verified(sym, START, END)
        bars_map[sym] = bars
        evidence.append({"symbol": sym, "rows": ev["primary"]["rows"],
                         "cross_overlap": ev["cross_check"]["overlap_days"],
                         "warnings": len(ev["integrity_warnings"])})
        print(f"数据核验 {sym}: {ev['primary']['rows']} 行, 交叉 {ev['cross_check']['overlap_days']} 日", flush=True)

    series = {s: precompute(s, b) for s, b in bars_map.items()}
    results = {}

    # 各候选独立全额资金口径(比较用)+ 80/20 组合口径
    for key, cfg in (("S3_SECTOR", s3), ("S1R_WIDE", s1r)):
        cal = series[cfg["universe"][0]].days
        windows = walk_forward_windows(cal)
        grid = momentum_grid(cfg["review_grid"])
        d, e, chosen = walk_forward_momentum(
            series, list(cfg["universe"]), cfg["cash_proxy"], grid, windows, cal, CAPITAL_USD, fee)
        m = metrics(d, e)
        results[key] = {"oos": m, "promo1": promo1_verdict(m), "grid_size": len(grid),
                        "windows": chosen}
        print(f"{key}: 月均 {m.get('monthly_mean_net_pct')}% 回撤 {m.get('max_drawdown_pct')}%", flush=True)

    cal = series[s2b["universe"]["core"][0]].days
    windows = walk_forward_windows(cal)
    d, e, chosen, stats = walk_forward_meanrev(
        series, list(s2b["universe"]["core"]), s2_grid(s2b["review_grid"]),
        windows, cal, CAPITAL_USD * 0.2, fee)
    m2 = metrics(d, e)
    results["S2B_AFFORDABLE"] = {"oos": m2, "promo1": promo1_verdict(m2),
                                 "stats": stats, "windows": chosen}
    print(f"S2B: 月均 {m2.get('monthly_mean_net_pct')}% 交易 {stats['trades']} 笔 跳过 {stats['skipped_infeasible']}", flush=True)

    report = {
        "round": "R1", "generated": "2026-07-17",
        "owner_directive": "维持 5%/月门槛;改造策略结构持续推进(decision_log 2026-07-17)",
        "period": [START.isoformat(), END.isoformat()],
        "discipline": "双源核验/含费用/整股/训练2年验证6个月/网格内选优/样本外如实",
        "data_evidence": evidence,
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print("\n=== R1 汇总(样本外) ===")
    for k, v in results.items():
        print(k, json.dumps(v["oos"], ensure_ascii=False), "PROMO-1:", v["promo1"]["passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
