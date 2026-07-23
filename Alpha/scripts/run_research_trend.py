#!/usr/bin/env python3
"""R5 多资产趋势跟随:同口径滚动前推(双源核验、真费用、整股、样本外如实)。

owner 2026-07-24 裁定:现役 0.662%/月不足以实盘("不如买债券")。本轮回答一个
问题:跨资产趋势家族能不能在回撤 <=15% 内把样本外月均推得显著更高;
能=出候选给 owner 裁定,不能=如实报告"这个家族也不行"。绝不粉饰。
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
    S1Params, load_promo1_gate, metrics, pick_best, precompute, promo1_verdict,
    simulate_s1, walk_forward_windows,
)

START, END = date(2010, 3, 1), date(2026, 7, 16)
CAPITAL_USD = 3000 * 0.66
OUT = Path(os.environ.get("ALPHA_RESEARCH_OUT", "reports/backtest/research_TREND_2026-07-24"))


def build_grid(block: dict) -> list[S1Params]:
    g = block["grid"]
    prox = g.get("high_proximity_allowed", [None])
    brakes = g.get("dd_brake_allowed", [None])
    combos = itertools.product(
        [tuple(w) for w in g["weights_allowed"]],
        g["top_n_allowed"], g["target_vol_allowed"], g["rebalance_threshold_allowed"],
        prox, brakes,
    )
    out = []
    for w, n, v, r, p, b in combos:
        soft, hard = (b if b else (None, None))
        out.append(S1Params(weights=w, top_n=n, target_vol=float(v),
                            rebalance_threshold_pct=float(r),
                            eval_frequency=block["eval_frequency"],
                            high_proximity=(float(p) if p else None),
                            dd_soft_pct=(float(soft) if soft else None),
                            dd_hard_pct=(float(hard) if hard else None)))
    return out


def main() -> int:
    fee = FeeModel.from_yaml()
    gate = load_promo1_gate()
    # 研究侧回撤容忍可由 owner 裁定放宽(2026-07-24:15% -> 30%);生产门槛文件不动
    dd_cap = float(os.environ.get("ALPHA_RESEARCH_DD_CAP", gate["gate_dd_pct"]))
    gate = {**gate, "gate_dd_pct": dd_cap}
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "configs/strategies/research/trend_multi_asset.yaml"
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    universe, cash = list(cfg["universe"]), cfg["cash_proxy"]
    proxy_map = cfg.get("signal_proxy", {}) or {}

    bars_map = {}
    for sym in sorted(set(universe) | {cash} | set(proxy_map.values())):
        bars, ev = fetch_verified(sym, START, END)
        bars_map[sym] = bars
        print(f"数据 {sym}: {len(bars)} 根(双源核验)", flush=True)
    series = {s: precompute(s, b) for s, b in bars_map.items()}
    signal_series = {sym: series[proxy] for sym, proxy in proxy_map.items()} or None
    cal = series[universe[0]].days
    windows = walk_forward_windows(cal)
    print(f"门槛: {gate} 窗口: {len(windows)}", flush=True)

    results = {}
    for ef in cfg["review_grid"].get("eval_frequency_allowed", ["weekly"]):
        name = f"TREND_{ef}"
        grid = build_grid({"eval_frequency": ef, "grid": cfg["review_grid"]})
        oos_d, oos_e, chosen = [], [], []
        carry = CAPITAL_USD
        for t_start, t_end, v_start, v_end in windows:
            train = []
            for p in grid:
                r = simulate_s1(series, universe, cash, p, start=t_start, end=t_end,
                                sleeve_usd=CAPITAL_USD, fee=fee, calendar=cal,
                                signal_series=signal_series)
                train.append((p, metrics(r.equity_days, r.equity)))
            best_p, _bm, dd_ok = pick_best(train, dd_cap=dd_cap)
            v = simulate_s1(series, universe, cash, best_p, start=v_start, end=v_end,
                            sleeve_usd=carry, fee=fee, calendar=cal,
                            signal_series=signal_series)
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
        {"round": "R5 多资产趋势跟随", "gate": gate,
         "period": [START.isoformat(), END.isoformat()],
         "benchmarks": {"现役": "0.662%/月 @ 13.07%", "门A": "0.894%/月 @ 18.98%",
                        "无风险参照": "约 0.4%/月(债券/定存口径,owner 2026-07-24 提出)"},
         "results": results}, ensure_ascii=False, indent=2, default=str))
    print("\n=== R5 汇总(样本外) ===")
    for k, v in results.items():
        print(k, json.dumps(v["oos"], ensure_ascii=False), "过门:", v["promo1"]["passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
