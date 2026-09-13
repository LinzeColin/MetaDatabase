"""固定 verdict 夹具验证汇总中枢的诚实门与确定性裁决。"""

from __future__ import annotations

import unittest

from signal_lattice.aggregate import (
    NEUTRAL_WATCH_CONFIDENCE_THRESHOLD,
    aggregate_symbol_verdicts,
    blocked_aggregate_report,
    build_aggregate_report,
)
from signal_lattice.branches.models import BranchVerdict


def verdict(
    branch_id: str,
    symbol: str,
    direction: str,
    confidence: float,
    weight: float,
    participation_status: str = "COLD_START_ELIGIBLE",
    implemented: bool = True,
) -> BranchVerdict:
    return BranchVerdict(
        branch_id=branch_id,
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        evidence={},
        counter_evidence=f"{branch_id} 的反证",
        invalidation=f"{branch_id} 的失效条件",
        window_used=252,
        implemented=implemented,
        weight=weight,
        participation_status=participation_status,
    )


class AggregateTests(unittest.TestCase):
    def test_weighted_vote_confidence_and_exclusion_are_recomputable(self):
        inputs = [
            verdict("bull", "AAA", "看涨", 0.8, 2.0),
            verdict("bear", "AAA", "看跌", 0.2, 0.5),
            verdict("neutral", "AAA", "中性", 0.4, 0.5),
            verdict("pending", "AAA", "中性", 0.9, 0.0, "EXCLUDED_PENDING_BACKTEST"),
        ]

        result = aggregate_symbol_verdicts("AAA", inputs)

        self.assertEqual(result["direction"], "看涨")
        self.assertEqual(result["tie_breaker"], "UNIQUE_WEIGHTED_WINNER")
        self.assertAlmostEqual(result["confidence"], (0.8 * 2.0 + 0.2 * 0.5 + 0.4 * 0.5) / 3.0)
        self.assertAlmostEqual(result["direction_vote_share"], 2.0 / 3.0)
        self.assertAlmostEqual(result["conviction"], result["confidence"] * result["direction_vote_share"])
        self.assertEqual(result["participating_branch_count"], 3)
        self.assertEqual(result["excluded_branch_count"], 1)
        self.assertEqual(result["excluded_branches"][0]["branch_id"], "pending")
        self.assertIn("尚未通过回测推广门", result["excluded_branches"][0]["reason"])

        decision = build_aggregate_report(["AAA"], inputs)["decision"]
        self.assertEqual(decision["state"], "DIRECTIONAL_CONCLUSION")
        self.assertEqual(decision["action"], "看涨")
        self.assertEqual(decision["primary_symbol"], "AAA")
        self.assertAlmostEqual(decision["conviction"], result["conviction"])
        self.assertTrue(decision["rationale"])
        self.assertTrue(decision["internal_coordination"])

    def test_equal_directional_votes_resolve_to_neutral_independent_of_input_order(self):
        inputs = [
            verdict("bull", "AAA", "看涨", 0.8, 1.0),
            verdict("bear", "AAA", "看跌", 0.2, 1.0),
        ]

        forward = aggregate_symbol_verdicts("AAA", inputs)
        reversed_result = aggregate_symbol_verdicts("AAA", list(reversed(inputs)))

        self.assertEqual(forward["direction"], "中性")
        self.assertEqual(forward["tie_breaker"], "TIED_HIGHEST_WEIGHT_RESOLVED_TO_NEUTRAL")
        self.assertEqual(forward["direction"], reversed_result["direction"])
        self.assertAlmostEqual(forward["confidence"], reversed_result["confidence"])
        self.assertAlmostEqual(forward["direction_vote_share"], 0.5)

    def test_neutral_watch_threshold_has_a_strict_boundary(self):
        lower = build_aggregate_report(
            ["AAA"],
            [verdict("neutral", "AAA", "中性", NEUTRAL_WATCH_CONFIDENCE_THRESHOLD - 0.01, 1.0)],
        )["decision"]
        boundary = build_aggregate_report(
            ["AAA"],
            [verdict("neutral", "AAA", "中性", NEUTRAL_WATCH_CONFIDENCE_THRESHOLD, 1.0)],
        )["decision"]

        self.assertEqual(lower["state"], "NEUTRAL_LOW_CONVICTION")
        self.assertEqual(lower["action"], "观望")
        self.assertEqual(boundary["state"], "NEUTRAL_CONSENSUS")
        self.assertEqual(boundary["action"], "观望")

    def test_no_eligible_branch_lists_every_exclusion_reason(self):
        report = build_aggregate_report(
            ["AAA"],
            [
                verdict("unimplemented", "AAA", "不适用", 0.0, 0.0, "UNIMPLEMENTED", False),
                verdict("pending", "AAA", "中性", 0.9, 0.0, "EXCLUDED_PENDING_BACKTEST"),
            ],
        )

        decision = report["decision"]
        self.assertEqual(decision["state"], "NO_ELIGIBLE_BRANCH")
        self.assertIsNone(decision["action"])
        self.assertEqual({item["branch_id"] for item in decision["excluded_branches"]}, {"unimplemented", "pending"})
        self.assertIn("分支尚未实现", decision["rationale"])
        self.assertIn("尚未通过回测推广门", decision["rationale"])

    def test_system_blocked_refuses_action_before_branch_calculation(self):
        report = blocked_aggregate_report()

        self.assertEqual(report["decision"]["state"], "SYSTEM_BLOCKED")
        self.assertIsNone(report["decision"]["action"])
        self.assertEqual(report["aggregate"], [])


if __name__ == "__main__":
    unittest.main()
