from __future__ import annotations

import unittest
from datetime import date, timedelta

from signal_lattice_v19.backtest import EpisodeRow, PriceRow, run_walk_forward


class BacktestTests(unittest.TestCase):
    def test_walk_forward_uses_next_bar_costs_and_gate(self):
        start = date(2025, 1, 1)
        prices = []
        value = 100.0
        for index in range(180):
            value *= 1.001
            prices.append(PriceRow(start + timedelta(days=index), "AU.SPY", value))
        episodes = [EpisodeRow(start - timedelta(days=1), "AU.SPY")]
        result = run_walk_forward(
            prices, episodes, benchmark_symbol="AU.SPY",
            cash_rate_annual_pct=4.0, switch_cost_pct=0.16,
        )
        self.assertEqual(result["status"], "EXECUTED")
        self.assertEqual(result["gate_status"], "PASS")
        self.assertGreaterEqual(result["observations"], 120)
        self.assertEqual(result["profitability_claim"], "BACKTEST_GATE_ONLY")
        self.assertIn("不代表未来收益", result["warning"])

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
