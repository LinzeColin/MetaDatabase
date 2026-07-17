#!/usr/bin/env python3
"""BLEND 轮:冠军(周频资产类动量)× 因子月轮 双 sleeve 分仓,晋级口径。

两 sleeve 各自滚动前推逐窗重训(各用各的网格),各自独立复利,不跨 sleeve
再平衡(与生产组合层同一近似,如实声明)。训练与验证用同一 sleeve 资金量——
3000 AUD 拆仓后的整股可行性(skipped_infeasible)是本轮一等公民产出。
"""

from __future__ import annotations

import itertools
import json
import math
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    S1Params, load_promo1_gate, metrics, monthly_returns, pick_best, precompute,
    promo1_verdict, simulate_s1, walk_forward_windows,
)

START, END = date(2014, 1, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
FLOOR = {"name": "S1_GOLD_BLEND(生产保底线)", "monthly_pct": 0.662, "dd_pct": 13.07}
SPLITS = [(0.5, 0.5), (0.6, 0.4), (0.4, 0.6)]
OUT = Path("reports/backtest/research_BLEND_2026-07-18")


def champion_grid(cfg: dict) -> list[S1Params]:
    g = cfg["review_grid"]
    combos = itertools.product(
        [tuple(w) for w in g["weights_allowed"]], g["top_n_allowed"],
        g["target_vol_allowed"], g["rebalance_threshold_allowed"],
        g["high_proximity_allowed"], g["defensive_weight_allowed"])
    return [S1Params(weights=w, top_n=n, target_vol=float(v),
                     rebalance_threshold_pct=float(r), eval_frequency="weekly",
                     high_proximity=float(p), defensive_symbol="GLD",
                     defensive_weight=float(dw))
            for w, n, v, r, p, dw in combos]


def factor_grid(block: dict) -> list[S1Params]:
    g = block["grid"]
    combos = itertools.product(
        [tuple(w) for w in g["weights_allowed"]], g["top_n_allowed"],
        g["target_vol_allowed"], g["rebalance_threshold_allowed"],
        g["high_proximity_allowed"], g["defensive_symbol_allowed"],
        g["defensive_weight_allowed"])
    return [S1Params(weights=w, top_n=n, target_vol=float(v),
                     rebalance_threshold_pct=float(r),
                     eval_frequency=block["eval_frequency"],
                     high_proximity=(float(p) if p else None),
                     defensive_symbol=ds, defensive_weight=float(dw))
            for w, n, v, r, p, ds, dw in combos]


def run_sleeve(series, universe, cash, grid, cal, windows, sleeve_usd, fee):
    oos_d, oos_e = [], []
    carry = sleeve_usd
    skipped = 0
    for t_start, t_end, v_start, v_end in windows:
        train = []
        for p in grid:
            r = simulate_s1(series, universe, cash, p, start=t_start, end=t_end,
                            sleeve_usd=sleeve_usd, fee=fee, calendar=cal)
            train.append((p, metrics(r.equity_days, r.equity)))
        best_p, _bm, _ok = pick_best(train)
        v = simulate_s1(series, universe, cash, best_p, start=v_start, end=v_end,
                        sleeve_usd=carry, fee=fee, calendar=cal)
        if v.equity:
            oos_d.extend(v.equity_days); oos_e.extend(v.equity); carry = v.equity[-1]
        skipped += v.skipped_infeasible
    return oos_d, oos_e, skipped


def pearson(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return cov / (va * vb) if va > 0 and vb > 0 else 0.0


def main() -> int:
    fee = FeeModel.from_yaml()
    gate = load_promo1_gate()
    champ_cfg = yaml.safe_load(Path("configs/strategies/s1_gold_blend.yaml").read_text())
    fac_cfg = yaml.safe_load(Path("configs/strategies/research/factor_rotation.yaml").read_text())
    champ_uni, champ_cash = list(champ_cfg["universe"]), champ_cfg["cash_proxy"]
    fac_uni, fac_cash = list(fac_cfg["universe"]), fac_cfg["cash_proxy"]

    series = {}
    for sym in sorted(set(champ_uni) | set(fac_uni)):
        bars, _ev = fetch_verified(sym, START, END)
        series[sym] = precompute(sym, bars)
    cal = series["SPY"].days
    windows = walk_forward_windows(cal)
    g_champ = champion_grid(champ_cfg)
    g_fac = factor_grid(fac_cfg["candidates"]["FAC_GOLD_MONTHLY"])
    print(f"门槛 {gate} 窗口 {len(windows)} 冠军网格 {len(g_champ)} 因子网格 {len(g_fac)}", flush=True)

    results = {}
    for w1, w2 in SPLITS:
        label = f"冠军{int(w1*100)}/因子{int(w2*100)}"
        d1, e1, k1 = run_sleeve(series, champ_uni, champ_cash, g_champ, cal, windows,
                                CAPITAL_USD * w1, fee)
        d2, e2, k2 = run_sleeve(series, fac_uni, fac_cash, g_fac, cal, windows,
                                CAPITAL_USD * w2, fee)
        # 相邻验证窗共享边界交易日:同日按「后窗值」去重(数值本就相同),
        # 再只对两 sleeve 共同交易日求和——严禁把边界日加两遍造出假回撤。
        m1 = {d: v for d, v in zip(d1, e1)}
        m2 = {d: v for d, v in zip(d2, e2)}
        days = sorted(set(m1) & set(m2))
        dropped = len(set(m1) ^ set(m2))
        if dropped:
            print(f"   [{label}] 两 sleeve 非共同交易日 {dropped} 天,已剔除", flush=True)
        eq = [m1[d] + m2[d] for d in days]
        m = metrics(days, eq)
        sd1 = sorted(m1)
        sd2 = sorted(m2)
        r1 = [r for _, r in monthly_returns(sd1, [m1[d] for d in sd1])]
        r2 = [r for _, r in monthly_returns(sd2, [m2[d] for d in sd2])]
        corr = round(pearson(r1, r2), 3)
        results[label] = {"oos": m, "sleeve_monthly_corr": corr,
                          "skipped_infeasible": {"champion": k1, "factor": k2},
                          "promo1": promo1_verdict(m, **gate)}
        print(f"{label}: 月均 {m.get('monthly_mean_net_pct')}% 回撤 {m.get('max_drawdown_pct')}% "
              f"相关 {corr} 买不起跳过 冠军{k1}/因子{k2} 过门 {results[label]['promo1']['passed']}",
              flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research_report.json").write_text(json.dumps(
        {"round": "BLEND 双结构分仓", "gate": gate,
         "period": [START.isoformat(), END.isoformat()],
         "floor_reference": FLOOR, "splits": SPLITS,
         "method": "两 sleeve 各自逐窗重训、独立复利、不跨 sleeve 再平衡(声明近似);"
                   "训练=验证同 sleeve 资金量,整股可行性如实计数",
         "results": results}, ensure_ascii=False, indent=2, default=str))
    print("\n=== BLEND 汇总(样本外) ===")
    for k, v in results.items():
        beats = (v["oos"].get("monthly_mean_net_pct", -999) > FLOOR["monthly_pct"]
                 and v["oos"].get("max_drawdown_pct", 999) < FLOOR["dd_pct"])
        print(k, json.dumps(v["oos"], ensure_ascii=False), "| 相关", v["sleeve_monthly_corr"],
              "| 全面超保底线:", beats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
