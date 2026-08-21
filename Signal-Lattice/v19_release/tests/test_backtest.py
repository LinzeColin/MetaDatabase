from __future__ import annotations

import unittest
from datetime import date, timedelta

from signal_lattice_v19.backtest import EpisodeRow, PriceRow, run_walk_forward


class BacktestTests(unittest.TestCase):
    def test_walk_forward_uses_next_bar_costs_and_gate(self):
        start = date(2025, 1, 1)
        prices = []
        candidate_value = 100.0
        benchmark_value = 100.0
        for index in range(180):
            candidate_value *= 1.002
            benchmark_value *= 1.001
            day = start + timedelta(days=index)
            prices.append(PriceRow(day, "AU.CAND", candidate_value))
            prices.append(PriceRow(day, "AU.SPY", benchmark_value))
        episodes = [EpisodeRow(start - timedelta(days=1), "AU.CAND")]
        result = run_walk_forward(
            prices, episodes, benchmark_symbol="AU.SPY",
            cash_rate_annual_pct=4.0, switch_cost_pct=0.16,
        )
        self.assertEqual(result["status"], "EXECUTED")
        self.assertEqual(result["gate_status"], "PASS")
        self.assertGreaterEqual(result["observations"], 120)
        self.assertEqual(result["profitability_claim"], "BACKTEST_GATE_ONLY")
        self.assertIn("不代表未来收益", result["warning"])

    def test_same_benchmark_symbol_fails_after_strategy_costs(self):
        start = date(2025, 1, 1)
        value = 100.0
        prices = []
        for index in range(180):
            value *= 1.001
            prices.append(PriceRow(start + timedelta(days=index), "AU.SPY", value))
        result = run_walk_forward(
            prices, [EpisodeRow(start - timedelta(days=1), "AU.SPY")],
            benchmark_symbol="AU.SPY", cash_rate_annual_pct=4.0, switch_cost_pct=1.16,
        )
        self.assertEqual(result["gate_status"], "FAIL")
        self.assertLess(result["strategy_net_return_pct"], result["benchmark_net_return_pct"])
        self.assertIn("扣费后未超过可比宽基", result["reasons"])

    def test_short_history_cannot_pass(self):
        start = date(2026, 1, 1)
        prices = [PriceRow(start + timedelta(days=i), "AU.SPY", 100.0 + i) for i in range(50)]
        result = run_walk_forward(
            prices, [EpisodeRow(start - timedelta(days=1), "AU.SPY")],
            benchmark_symbol="AU.SPY", cash_rate_annual_pct=4.0, switch_cost_pct=0.16,
        )
        self.assertEqual(result["gate_status"], "FAIL")
        self.assertIn("少于120个真实前向交易日观测", result["reasons"])
        self.assertEqual(result["profitability_claim"], "NOT_ISSUED")


if __name__ == "__main__":
    unittest.main()
