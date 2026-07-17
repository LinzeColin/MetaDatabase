"""回测全量运行器:数据核验 -> 滚动前推寻优 -> OOS 拼接 -> PROMO-1 判定 -> 报告落盘。"""

from __future__ import annotations

import json
import hashlib
from datetime import date
from pathlib import Path

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
    s1_grid,
    s2_grid,
    simulate_s1,
    simulate_s2,
    walk_forward_windows,
)

DEFAULT_AUD_USD = 0.66  # 保守常数换算(报告声明;实盘用带时间戳汇率)


def run_full(
    *,
    start: date,
    end: date,
    capital_aud: float = 3000.0,
    aud_usd: float = DEFAULT_AUD_USD,
    out_dir: str | Path = "reports/backtest",
    use_cache: bool = True,
) -> dict:
    s1_cfg = yaml.safe_load(Path("configs/strategies/s1_momentum.yaml").read_text())
    s2_cfg = yaml.safe_load(Path("configs/strategies/s2_meanrev.yaml").read_text())
    alloc = yaml.safe_load(Path("configs/portfolio.yaml").read_text())["base_allocation"]
    fee = FeeModel.from_yaml()

    universe = list(s1_cfg["universe"])
    s2_universe = list(s2_cfg["universe"]["core"])
    all_symbols = sorted(set(universe) | set(s2_universe))

    bars_map, evidence = {}, []
    for sym in all_symbols:
        bars, ev = fetch_verified(sym, start, end, use_cache=use_cache)
        bars_map[sym] = bars
        evidence.append(ev)

    series = {sym: precompute(sym, bars) for sym, bars in bars_map.items()}
    calendar = series[universe[0]].days

    capital_usd = capital_aud * aud_usd
    s1_sleeve = capital_usd * float(alloc["S1_MOMENTUM_ROTATION"])
    s2_sleeve = capital_usd * float(alloc["S2_OVERSOLD_REBOUND"])

    windows = walk_forward_windows(calendar)
    if not windows:
        raise RuntimeError("历史不足以构成任何 训练2年/验证6个月 窗口")

    # ---- S1 走网格 ----
    s1_params_grid = s1_grid(s1_cfg["review_grid"])
    s1_oos_days: list[date] = []
    s1_oos_equity: list[float] = []
    s1_windows_report = []
    s1_carry = s1_sleeve
    for t_start, t_end, v_start, v_end in windows:
        train_scores = []
        for p in s1_params_grid:
            r = simulate_s1(series, universe, s1_cfg["cash_proxy"], p,
                            start=t_start, end=t_end, sleeve_usd=s1_sleeve,
                            fee=fee, calendar=calendar)
            train_scores.append((p, metrics(r.equity_days, r.equity)))
        best_p, best_m, dd_ok = pick_best(train_scores)
        v = simulate_s1(series, universe, s1_cfg["cash_proxy"], best_p,
                        start=v_start, end=v_end, sleeve_usd=s1_carry,
                        fee=fee, calendar=calendar)
        if v.equity:
            s1_oos_days.extend(v.equity_days)
            s1_oos_equity.extend(v.equity)
            s1_carry = v.equity[-1]
        s1_windows_report.append({
            "train": [t_start.isoformat(), t_end.isoformat()],
            "validate": [v_start.isoformat(), v_end.isoformat()],
            "chosen": vars(best_p) | {"weights": list(best_p.weights)},
            "train_metrics": best_m, "train_dd_constraint_met": dd_ok,
            "validate_metrics": metrics(v.equity_days, v.equity),
            "validate_orders": v.orders, "validate_fees_usd": round(v.fees_usd, 2),
            "validate_skipped_infeasible": v.skipped_infeasible,
        })

    # ---- S2 走网格 ----
    s2_params_grid = s2_grid(s2_cfg["review_grid"])
    s2_oos_days: list[date] = []
    s2_oos_equity: list[float] = []
    s2_windows_report = []
    s2_carry = s2_sleeve
    s2_trades = s2_wins = s2_skipped = 0
    for t_start, t_end, v_start, v_end in windows:
        train_scores = []
        for p in s2_params_grid:
            r = simulate_s2(series, s2_universe, p, start=t_start, end=t_end,
                            sleeve_usd=s2_sleeve, fee=fee, calendar=calendar)
            train_scores.append((p, metrics(r.equity_days, r.equity)))
        best_p, best_m, dd_ok = pick_best(train_scores)
        v = simulate_s2(series, s2_universe, best_p, start=v_start, end=v_end,
                        sleeve_usd=s2_carry, fee=fee, calendar=calendar)
        if v.equity:
            s2_oos_days.extend(v.equity_days)
            s2_oos_equity.extend(v.equity)
            s2_carry = v.equity[-1]
        s2_trades += v.trades
        s2_wins += v.wins
        s2_skipped += v.skipped_infeasible
        s2_windows_report.append({
            "train": [t_start.isoformat(), t_end.isoformat()],
            "validate": [v_start.isoformat(), v_end.isoformat()],
            "chosen": vars(best_p),
            "train_metrics": best_m, "train_dd_constraint_met": dd_ok,
            "validate_metrics": metrics(v.equity_days, v.equity),
            "validate_trades": v.trades, "validate_skipped_infeasible": v.skipped_infeasible,
        })

    # ---- 组合(各 sleeve 独立复利相加) ----
    s2_by_day = dict(zip(s2_oos_days, s2_oos_equity))
    combo_days, combo_equity = [], []
    for d, e1 in zip(s1_oos_days, s1_oos_equity):
        e2 = s2_by_day.get(d)
        if e2 is not None:
            combo_days.append(d)
            combo_equity.append(e1 + e2)

    s1_m = metrics(s1_oos_days, s1_oos_equity)
    s2_m = metrics(s2_oos_days, s2_oos_equity)
    combo_m = metrics(combo_days, combo_equity)
    from backend.app.backtest.pipeline import load_promo1_gate

    verdict = promo1_verdict(combo_m, **load_promo1_gate())

    report = {
        "generated_for": "ALPHA-LIVE-050 PROMO-1",
        "period": [start.isoformat(), end.isoformat()],
        "capital": {"aud": capital_aud, "usd_at_fx": round(capital_usd, 2), "aud_usd_fx": aud_usd,
                    "s1_sleeve_usd": round(s1_sleeve, 2), "s2_sleeve_usd": round(s2_sleeve, 2)},
        "fees": {"commission_usd_per_order": fee.commission_usd_per_order,
                 "sec_fee_rate_on_sell": fee.sec_fee_rate_on_sell,
                 "cat_fee_per_share": fee.cat_fee_per_share,
                 "note": "SEC/CAT 为保守高估占位,待部署期按官方当期费率核验(fees.yaml 注明)"},
        "data_evidence": evidence,
        "walk_forward": {"train_months": 24, "validate_months": 6, "windows": len(windows)},
        "s1": {"oos_metrics": s1_m, "windows": s1_windows_report},
        "s2": {"oos_metrics": s2_m, "windows": s2_windows_report,
               "oos_trades": s2_trades, "oos_wins": s2_wins,
               "oos_skipped_infeasible": s2_skipped,
               "note": "skipped_infeasible = 3000 AUD 整股约束下买不起一股而跳过的信号数"},
        "combined": {"oos_metrics": combo_m, "promo1": verdict},
        "approximations": [
            "S1 周二收盘成交、信号用截至周一数据;S2 入场限价当日最低触及才成交",
            "止损按触发日收盘、获利/超时按次日收盘(保守方向)",
            "sleeve 间不再平衡(月度评审职责,本版不模拟)",
            "复权 OHLC 按 adj_close/close 系数缩放;AUD/USD 用常数 0.66(实盘用实时汇率)",
        ],
    }
    out = Path(out_dir) / f"{end.isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    (out / "report.json").write_text(text)
    report["report_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    (out / "report_hash.txt").write_text(report["report_sha256"] + "\n")
    return report
