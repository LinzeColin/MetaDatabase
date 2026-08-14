from __future__ import annotations

import unittest
from datetime import date, timedelta

from signal_lattice_v19.metrics import absolute_metrics, relative_path
from signal_lattice_v19.models import Candidate


def candidate(code: str, daily_growth: float, volatility_bump: float = 0.0) -> Candidate:
    start = date(2026, 1, 1)
    value = 100.0
    bars = []
    for index in range(140):
        value *= 1.0 + daily_growth + (volatility_bump if index % 2 == 0 else -volatility_bump)
        bars.append({"time": str(start + timedelta(days=index)), "close": value})
    return Candidate(
        provider_code=code,
        public_code=code.split(".")[-1],
        name=code,
        market="AU",
        currency="AUD",
        bucket_id="us_broad",
        bucket_name="美国宽基",
        risk_tier=1,
        platform_verified=True,
        price=value,
        bars=bars,
        liquidity_score=1.0,
    )


class MetricsTests(unittest.TestCase):
    def test_absolute_windows_and_drawdown(self):
        item = candidate("AU.A", 0.001)
        metrics = absolute_metrics(item)
        self.assertGreater(metrics.returns_pct["20"], 1.5)
        self.assertGreater(metrics.returns_pct["60"], metrics.returns_pct["20"])
        self.assertEqual(metrics.max_drawdown_pct["60"], 0.0)

    def test_relative_pressure_is_below_point_estimate(self):
        incumbent = candidate("AU.SPY", 0.0005)
        challenger = candidate("AU.X", 0.0010, 0.002)
        point, lower = relative_path(challenger, incumbent, 60)
        self.assertIsNotNone(point)
        self.assertIsNotNone(lower)
        self.assertLess(lower, point)


if __name__ == "__main__":
    unittest.main()
