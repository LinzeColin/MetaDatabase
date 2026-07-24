"""外部包 3 个 persona 候选 vs 现役精调,同尺连续复盘 + 逐笔账本 PK。

同一引擎 / 同一真实资金(3000 AUD × 0.65 = 1950 USD)/ 同一费用 / 同一窗口(2015-2026,
满 252 日预热后公平起点)跑四条固定规则:
  现役  = 五腿双动量精调 [0.2,0.4,0.4] Top-1
  PD1   = 共识动量 Governor(三模型投票→仓位;simulate_consensus)
  PD2   = 固定 alpha + 独立风险预算(现役规则 + 目标年化波动 10% 缩仓)
  PD3   = 五腿七三防守混合(70% 五腿 sleeve + 30% GLD/TLT/IEF 动态防守)

诚实口径同 replay_fixed_rule_ledger:固定规则连续复盘,非动态 WFO;数据 2014 起晚于报告
2010;整股 @1950 美元真实颗粒度;PD2 残余仓在现金(≈BIL,零息近似,如实标注)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.backtest.data_sources import fetch_verified
from backend.app.backtest.fees import FeeModel
from backend.app.backtest.pipeline import (
    ConsensusModel, S1Params, ledger_metrics, precompute, simulate_consensus, simulate_s1,
)

UNIVERSE = ["SPY", "EFA", "QQQ", "GLD", "IEF"]
CASH = "BIL"
EXTRA = ["TLT"]  # PD3 防守篮子需要
CAPITAL_USD = 3000.0 * 0.65
WARMUP = 252

CONSENSUS_MODELS = [
    ConsensusModel("momentum_12m", (0.0, 0.0, 1.0)),
    ConsensusModel("momentum_balanced", (0.3, 0.3, 0.4)),
    ConsensusModel("momentum_fine_fixed", (0.2, 0.4, 0.4)),
]


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "reports/backtest/replay_persona")
    out_dir.mkdir(parents=True, exist_ok=True)

    series = {}
    for sym in UNIVERSE + [CASH] + EXTRA:
        bars, _ = fetch_verified(sym, "2014-01-01", "2026-07-16", use_cache=True)
        series[sym] = precompute(sym, bars)
    calendar = sorted(series["SPY"].index_by_day)
    start, end = calendar[WARMUP], calendar[-1]
    fee = FeeModel.from_yaml("configs/fees.yaml")

    def run_s1(params):
        return simulate_s1(series, UNIVERSE, CASH, params, start=start, end=end,
                           sleeve_usd=CAPITAL_USD, fee=fee, calendar=calendar)

    runs = {
        "现役·五腿精调[0.2,0.4,0.4]": run_s1(
            S1Params(weights=(0.2, 0.4, 0.4), top_n=1, target_vol=999.0,
                     rebalance_threshold_pct=5.0)),
        "PD1·共识动量Governor": simulate_consensus(
            series, UNIVERSE, CASH, CONSENSUS_MODELS, start=start, end=end,
            sleeve_usd=CAPITAL_USD, fee=fee, calendar=calendar, rebalance_threshold_pct=5.0),
        "PD2·固定alpha+波动预算10%": run_s1(
            S1Params(weights=(0.2, 0.4, 0.4), top_n=1, target_vol=10.0,
                     rebalance_threshold_pct=5.0)),
        "PD3·五腿七三防守混合": run_s1(
            S1Params(weights=(0.2, 0.4, 0.4), top_n=1, target_vol=999.0,
                     rebalance_threshold_pct=5.0, defensive_weight=0.30,
                     defensive_basket=("GLD", "TLT", "IEF"))),
    }

    report = {"window": [start.isoformat(), end.isoformat()],
              "capital_usd": round(CAPITAL_USD, 2), "warmup_days": WARMUP,
              "note": "persona候选 vs 现役,固定规则连续复盘同尺;PD2残余仓在现金(≈BIL零息近似)",
              "results": {}}
    for name, res in runs.items():
        m = ledger_metrics(res.equity_days, res.equity, res.fills)
        m["orders"] = res.orders
        m["fees_usd"] = round(res.fees_usd, 2)
        m["skipped_infeasible"] = res.skipped_infeasible
        report["results"][name] = m
    (out_dir / "replay_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str))

    print(f"\n{'策略':<28}{'月数':>5}{'总收益%':>9}{'月均%':>7}{'最大回撤%':>9}"
          f"{'修复天':>7}{'逐笔盈亏比':>9}{'逐笔胜率%':>9}{'往返':>6}")
    for name, m in report["results"].items():
        rec = m.get("max_dd_recovery_days")
        rec_s = "OPEN" if rec is None else str(rec)
        plr = m.get("per_trade_pl_ratio")
        plr_s = "∞" if plr == float("inf") else (f"{plr:.2f}" if plr is not None else "-")
        print(f"{name:<28}{m.get('months',0):>5}{m.get('total_return_pct',0):>9.2f}"
              f"{m.get('monthly_mean_net_pct',0):>7.3f}{m.get('max_drawdown_pct',0):>9.2f}"
              f"{rec_s:>7}{plr_s:>9}{m.get('per_trade_win_rate_pct') or 0:>9.1f}"
              f"{m.get('round_trips',0):>6}")
    print(f"\n报告 → {out_dir / 'replay_report.json'}")


if __name__ == "__main__":
    main()
