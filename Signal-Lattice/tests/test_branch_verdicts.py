from __future__ import annotations

import unittest
from datetime import date, timedelta

from signal_lattice.branches.runtime import build_branch_report, evaluate_s1_verdicts, evaluate_s2_verdicts
from signal_lattice.live_config import default_universe
from signal_lattice.marketdata.models import Bar


def bars(symbol: str, close_values: list[float]) -> list[Bar]:
    start = date(2025, 1, 2)
    return [
        Bar(
            symbol=symbol,
            day=start + timedelta(days=index),
            open=close,
            high=close + 5.0,
            low=close,
            close=close,
            volume=1.0,
            exchange_timezone="UTC",
            source="fixed_fixture",
            observed_at=None,  # type: ignore[arg-type]
        )
        for index, close in enumerate(close_values)
    ]


class BranchVerdictTests(unittest.TestCase):
    def test_s1_bullish_direction_and_confidence_are_recomputable(self):
        gradients = {
            "usSPY": 1.0,
            "usQQQ": 0.8,
            "usIWM": 0.6,
            "usEFA": 0.5,
            "usEEM": 0.4,
            "usGLD": 0.3,
            "usTLT": 0.2,
            "usBIL": 0.1,
        }
        verdicts = evaluate_s1_verdicts({
            symbol: bars(symbol, [100.0 + index * gradient for index in range(260)])
            for symbol, gradient in gradients.items()
        })
        verdict = next(item for item in verdicts if item.symbol == "usSPY")

        evidence = verdict.evidence
        weighted_abs_return = 0.4 * abs(evidence["r63"]) + 0.3 * abs(evidence["r126"]) + 0.3 * abs(evidence["r252"])
        expected = min(
            1.0,
            (
                abs(evidence["momentum_score"]) / weighted_abs_return
                + abs(evidence["close"] - evidence["sma200"]) / evidence["close"]
                + evidence["position_scalar"]
            )
            / 3.0,
        )
        self.assertEqual(verdict.direction, "看涨")
        self.assertAlmostEqual(verdict.confidence, expected)
        self.assertEqual(verdict.window_used, 260)
        self.assertEqual(verdict.weight, 1.0)

    def test_s2_entry_direction_and_confidence_are_recomputable(self):
        close_values = [100.0 + index * 0.4 for index in range(197)] + [170.0, 165.0, 162.0]
        verdicts = evaluate_s2_verdicts({"usSPY": bars("usSPY", close_values)})
        verdict = next(item for item in verdicts if item.symbol == "usSPY")

        evidence = verdict.evidence
        expected = sum(
            evidence[key]
            for key in ("rsi_component", "ibs_component", "trend_component", "volatility_component")
        ) / 4.0
        self.assertEqual(verdict.direction, "看涨")
        self.assertAlmostEqual(verdict.confidence, expected)
        self.assertEqual(verdict.participation_status, "EXCLUDED_PENDING_BACKTEST")
        self.assertEqual(verdict.weight, 0.0)

    def test_s2_only_enters_aggregation_after_passed_promotion(self):
        close_values = [100.0 + index * 0.4 for index in range(197)] + [170.0, 165.0, 162.0]
        failed = evaluate_s2_verdicts(
            {"usSPY": bars("usSPY", close_values)},
            {"passed": False, "reason": "PROMO-1 未通过：月均净收益差 0.100 个百分点"},
        )[0]
        passed = evaluate_s2_verdicts(
            {"usSPY": bars("usSPY", close_values)},
            {"passed": True, "reason": "PROMO-1 通过"},
        )[0]

        self.assertEqual(failed.participation_status, "EXCLUDED_PENDING_BACKTEST")
        self.assertEqual(failed.weight, 0.0)
        self.assertIn("月均净收益差 0.100 个百分点", failed.counter_evidence)
        self.assertEqual(passed.participation_status, "COLD_START_ELIGIBLE")
        self.assertEqual(passed.weight, 1.0)

    def test_unimplemented_skill_branches_are_explicit_and_never_weighted(self):
        report = build_branch_report(default_universe(), {"usSPY": bars("usSPY", [100.0] * 260)})
        unimplemented = [item for item in report["branches"] if item["implemented"] is False]

        self.assertEqual({item["branch_id"] for item in unimplemented}, {
            "stock-commercial-opportunities",
            "bottleneck-serenity-skill",
            "equity-foresight-signal",
            "global-equity-lead-lag-atlas",
            "equity-event-atlas",
            "serenity-skill",
        })
        self.assertTrue(unimplemented)
        self.assertTrue(all(item["direction"] == "不适用" for item in unimplemented))
        self.assertTrue(all(item["weight"] == 0.0 for item in unimplemented))


if __name__ == "__main__":
    unittest.main()
