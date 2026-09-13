from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from signal_lattice.backtest.fees import FeeModel
from signal_lattice.backtest.pipeline import (
    S1Params,
    load_promo1_gate,
    precompute,
    promo1_verdict,
    simulate_s1,
    walk_forward_windows,
)
from signal_lattice.backtest.runner import (
    MIN_OOS_WINDOWS_FOR_PROFITABILITY,
    S1_LIVE_TO_ALPHA,
    profitability_status,
    run_backtest,
    sample_sufficiency,
)
from signal_lattice.live_config import default_universe
from signal_lattice.marketdata.models import Bar


def business_days(start: date, count: int) -> list[date]:
    result: list[date] = []
    cursor = start
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor += timedelta(days=1)
    return result


def fixed_bars(symbol: str, *, slope: float, count: int = 360) -> list[Bar]:
    rows = []
    for index, day in enumerate(business_days(date(2018, 1, 2), count)):
        close = 100.0 + index * slope
        rows.append(
            Bar(
                symbol=symbol,
                day=day,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1.0,
                exchange_timezone="UTC",
                source="fixed_fixture",
                observed_at=datetime.now(timezone.utc),
            )
        )
    return rows


class BacktestTests(unittest.TestCase):
    def test_walk_forward_only_returns_complete_non_overlapping_test_windows(self):
        calendar = business_days(date(2017, 1, 2), 1_500)
        windows = walk_forward_windows(calendar)

        self.assertGreaterEqual(len(windows), 2)
        for train_start, train_end, test_start, test_end in windows:
            self.assertLess(train_start, train_end)
            self.assertLess(train_end, test_start)
            self.assertLess(test_start, test_end)
        for (_, _, _, previous_test_end), (_, _, next_test_start, _) in zip(windows, windows[1:]):
            self.assertLess(previous_test_end, next_test_start)

    def test_fee_model_reduces_fixed_series_equity(self):
        bars_by_symbol = {
            alpha: fixed_bars(alpha, slope=index + 0.1)
            for index, alpha in enumerate(S1_LIVE_TO_ALPHA.values())
        }
        series = {symbol: precompute(symbol, bars) for symbol, bars in bars_by_symbol.items()}
        calendar = series["SPY"].days
        params = S1Params(top_n=1, target_vol=999.0, rebalance_threshold_pct=0.0)
        frictionless = FeeModel(0.0, 0.0, 0.0, False)
        charged = FeeModel(9.99, 0.0, 0.0, False)
        plain = simulate_s1(
            series, list(S1_LIVE_TO_ALPHA.values()), "BIL", params,
            start=calendar[0], end=calendar[-1], sleeve_usd=10_000.0,
            fee=frictionless, calendar=calendar,
        )
        paid = simulate_s1(
            series, list(S1_LIVE_TO_ALPHA.values()), "BIL", params,
            start=calendar[0], end=calendar[-1], sleeve_usd=10_000.0,
            fee=charged, calendar=calendar,
        )

        self.assertGreater(paid.fees_usd, 0.0)
        self.assertEqual(plain.fees_usd, 0.0)
        self.assertLess(paid.equity[-1], plain.equity[-1])

    def test_insufficient_history_exits_with_explicit_n_over_m_and_persists_no_numbers(self):
        bars = {"usSPY": fixed_bars("usSPY", slope=0.2, count=360)}
        with tempfile.TemporaryDirectory() as directory:
            report = run_backtest(default_universe(), bars, state_dir=Path(directory))
            s1 = report["branches"]["s1_momentum"]
            self.assertEqual(report["status"], "SAMPLE_INSUFFICIENT")
            self.assertEqual(s1["status"], "SAMPLE_INSUFFICIENT")
            self.assertTrue(s1["sample_status"].startswith("样本不足 0/2"))
            self.assertNotIn("stitched", s1)
            stored = json.loads((Path(directory) / "backtest" / "contribution_samples.json").read_text())
            self.assertEqual(stored["sample_count"], 0)

    def test_runner_records_one_contribution_per_branch_and_complete_test_window(self):
        bars = {
            "us" + alpha: fixed_bars("us" + alpha, slope=index + 0.2, count=1_500)
            for index, alpha in enumerate(S1_LIVE_TO_ALPHA.values())
        }
        report = run_backtest(default_universe(), bars)

        self.assertEqual(report["status"], "OOS_READY")
        for branch in report["branches"].values():
            self.assertEqual(branch["status"], "OOS_READY")
            self.assertEqual(len(branch["contributions"]), branch["walk_forward"]["windows"])
            self.assertEqual(
                [sample["window_label"] for sample in branch["contributions"]],
                [window["window_label"] for window in branch["windows"]],
            )
            self.assertTrue(
                {
                    "branch_id", "period_start", "period_end", "symbol",
                    "branch_return", "benchmark_return", "excess_return",
                    "risk_adjusted_excess", "window_label",
                }.issubset(branch["contributions"][0])
            )

    def test_profitability_gate_hides_returns_but_keeps_directional_research_eligible(self):
        branches = {
            "s1_momentum": {
                "status": "OOS_READY",
                "contributions": [{}] * 4,
                "stitched": {"excess_return_pct": 5.4753},
            },
            "s2_meanrev": {
                "status": "OOS_READY",
                "contributions": [{}] * MIN_OOS_WINDOWS_FOR_PROFITABILITY,
                "stitched": {"excess_return_pct": -78.56},
            },
        }

        status = profitability_status(branches)
        self.assertEqual(status, "OOS_HISTORY_INSUFFICIENT: 4/6")
        self.assertEqual(sample_sufficiency(branches), "OOS_HISTORY_INSUFFICIENT: 4/6")
        self.assertNotIn("5.4753", status)
        self.assertNotIn("-78.56", status)
        self.assertEqual(branches["s1_momentum"]["status"], "OOS_READY")

    def test_promo1_verdict_uses_alpha_configured_thresholds_inclusively(self):
        gate = load_promo1_gate()
        passed = promo1_verdict(
            {"years": 3.0, "monthly_mean_net_pct": 0.6, "max_drawdown_pct": 30.0},
            **gate,
        )
        failed = promo1_verdict(
            {"years": 3.0, "monthly_mean_net_pct": 0.599, "max_drawdown_pct": 30.0},
            **gate,
        )

        self.assertTrue(passed["passed"])
        self.assertFalse(failed["passed"])
        self.assertTrue(failed["years_ok"])
        self.assertFalse(failed["monthly_return_ok"])
        self.assertTrue(failed["drawdown_ok"])


if __name__ == "__main__":
    unittest.main()


class EmptyTestWindowTests(unittest.TestCase):
    """回归：test 窗口模拟不出任何可评价交易日时，不得崩溃，也不得按零收益并入。

    真实行情下（usSPY 6460 条日线）曾触发 runner.py 的
    `period_start=test.equity_days[0]` -> IndexError，整个 run_once() 崩溃，
    生产上等于服务不可用。正确行为是把该窗口判为无效样本剔除并记账。
    """

    def _run(self, equity_days_per_window):
        from signal_lattice.backtest import runner as R

        calls = {"n": 0}

        class FakeResult:
            def __init__(self, days):
                self.equity_days = list(days)
                self.equity = [100.0 + i for i in range(len(days))]
                self.fills = []
                self.orders = 0
                self.fees_usd = 0.0
                self.skipped_infeasible = 0

        def simulate(params, start, end, sleeve):
            # train 调用给非空序列，test 调用按夹具给定
            if calls["n"] % 2 == 0:
                calls["n"] += 1
                return FakeResult(business_days(date(2020, 1, 1), 30))
            idx = calls["n"] // 2
            calls["n"] += 1
            return FakeResult(equity_days_per_window[idx])

        all_days = business_days(date(2020, 1, 1), 1500)

        class FakeSeries:
            index_by_day = {day: i for i, day in enumerate(all_days)}
            closes = [100.0 + i * 0.1 for i in range(len(all_days))]

        windows = [
            (date(2020, 1, 1), date(2021, 12, 31), date(2022, 1, 1), date(2022, 6, 30)),
            (date(2022, 7, 1), date(2024, 6, 30), date(2024, 7, 1), date(2024, 12, 31)),
        ]
        return R._choose_and_simulate(
            calendar=business_days(date(2020, 1, 1), 500),
            windows=windows,
            parameter_grid=[S1Params()],
            simulate=simulate,
            benchmark_series=FakeSeries(),
            branch_id="s1_momentum",
            symbol="usSPY",
            capital_usd=1000.0,
        )

    def test_empty_test_window_is_excluded_not_crashed_and_not_counted(self):
        days = business_days(date(2022, 1, 3), 20)
        reports, _, _, _, _, contributions, evaluable = self._run([[], days])
        # 不崩溃
        self.assertEqual(len(reports), 2)
        # 空窗口被标记为无效并带原因
        empty = [r for r in reports if r.get("test_evaluable") is False]
        self.assertEqual(len(empty), 1)
        self.assertIn("无可评价交易日", empty[0]["excluded_reason"])
        # 空窗口不产生贡献度样本，也不计入可评价窗口数
        self.assertEqual(len(contributions), 1)
        self.assertEqual(evaluable, 1)
        # 空窗口不得被当成零收益样本混进来
        self.assertTrue(all(c.period_start is not None for c in contributions))
