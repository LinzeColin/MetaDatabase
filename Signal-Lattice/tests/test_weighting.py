"""固定贡献度夹具验证 Stage 3 Hedge 权重与诚实样本门。"""

from __future__ import annotations

import math
import json
import tempfile
import unittest
from pathlib import Path

from signal_lattice.weighting import (
    HEDGE_LEARNING_RATE,
    MIN_CONTRIBUTION_SAMPLES,
    WEIGHT_CAP,
    WEIGHT_FLOOR,
    build_weighting_from_state,
    calculate_contribution_weights,
)


def contribution(branch_id: str, index: int, *, risk_adjusted: float | None, excess: float = 0.0) -> dict:
    return {
        "branch_id": branch_id,
        "period_start": f"202{index}-01-01",
        "period_end": f"202{index}-06-30",
        "window_label": f"WF-{index:02d}",
        "symbol": "usSPY",
        "branch_return": excess,
        "benchmark_return": 0.0,
        "excess_return": excess,
        "risk_adjusted_excess": risk_adjusted,
    }


def by_branch(result: dict) -> dict[str, dict]:
    return {item["branch_id"]: item for item in result["branches"]}


class ContributionWeightTests(unittest.TestCase):
    def test_hedge_update_is_recomputable_from_fixed_samples(self):
        samples = [
            contribution(branch_id, index, risk_adjusted=value)
            for index in range(MIN_CONTRIBUTION_SAMPLES)
            for branch_id, value in (("positive", 0.2), ("negative", -0.2))
        ]

        result = calculate_contribution_weights(
            samples,
            branch_ids=["positive", "negative"],
            eligible_branch_ids=["positive", "negative"],
        )
        items = by_branch(result)
        expected_positive = math.exp(HEDGE_LEARNING_RATE * 1.6) / (
            math.exp(HEDGE_LEARNING_RATE * 1.6) + math.exp(-HEDGE_LEARNING_RATE * 1.6)
        )

        self.assertEqual(result["weight_mode"], "CONTRIBUTION_WEIGHTED")
        self.assertAlmostEqual(items["positive"]["weight"], expected_positive)
        self.assertAlmostEqual(items["negative"]["weight"], 1.0 - expected_positive)
        self.assertEqual(len(items["positive"]["weight_trajectory"]), MIN_CONTRIBUTION_SAMPLES)
        self.assertAlmostEqual(items["positive"]["weight_trajectory"][0]["start_weight"], 0.5)
        self.assertAlmostEqual(items["positive"]["weight_trajectory"][-1]["end_weight"], expected_positive)

    def test_floor_cap_and_persistent_negative_contribution_are_explicit(self):
        samples = [
            contribution(branch_id, index, risk_adjusted=value)
            for index in range(MIN_CONTRIBUTION_SAMPLES)
            for branch_id, value in (("leader", 100.0), ("flat", 0.0), ("laggard", -100.0))
        ]

        result = calculate_contribution_weights(
            samples,
            branch_ids=["leader", "flat", "laggard"],
            eligible_branch_ids=["leader", "flat", "laggard"],
        )
        items = by_branch(result)

        self.assertAlmostEqual(items["leader"]["weight"], WEIGHT_CAP)
        self.assertAlmostEqual(items["laggard"]["weight"], WEIGHT_FLOOR)
        self.assertGreater(items["laggard"]["weight"], 0.0)
        self.assertLess(items["laggard"]["weight"], items["flat"]["weight"])
        self.assertEqual(items["laggard"]["negative_contribution_status"], "PERSISTENT_NEGATIVE_CONTRIBUTION_AT_FLOOR")
        self.assertEqual(items["laggard"]["negative_contribution_message"], "持续负贡献，已压至下限。")

    def test_missing_risk_adjusted_excess_uses_excess_return_and_discloses_it(self):
        samples = [contribution("fallback", 0, risk_adjusted=None, excess=0.1)] + [
            contribution("fallback", index, risk_adjusted=0.1)
            for index in range(1, MIN_CONTRIBUTION_SAMPLES)
        ]

        result = calculate_contribution_weights(
            samples,
            branch_ids=["fallback"],
            eligible_branch_ids=["fallback"],
        )
        item = by_branch(result)["fallback"]

        self.assertEqual(item["metric_source"], "MIXED_RISK_ADJUSTED_EXCESS_AND_EXCESS_RETURN_FALLBACK")
        self.assertEqual(item["metric_source_counts"]["excess_return_fallback"], 1)
        self.assertAlmostEqual(item["cumulative_risk_adjusted_excess"], 0.7)
        self.assertAlmostEqual(item["cumulative_update_contribution"], 0.8)

    def test_all_insufficient_branches_remain_cold_start_equal(self):
        samples = [
            contribution(branch_id, index, risk_adjusted=value)
            for index in range(MIN_CONTRIBUTION_SAMPLES - 1)
            for branch_id, value in (("a", 2.0), ("b", -2.0))
        ]

        result = calculate_contribution_weights(
            samples,
            branch_ids=["a", "b"],
            eligible_branch_ids=["a", "b"],
        )
        items = by_branch(result)

        self.assertEqual(result["weight_mode"], "COLD_START_EQUAL")
        self.assertEqual(result["weight_sample_count"], 2 * (MIN_CONTRIBUTION_SAMPLES - 1))
        self.assertAlmostEqual(items["a"]["weight"], 0.5)
        self.assertAlmostEqual(items["b"]["weight"], 0.5)
        self.assertEqual(items["a"]["weight_status"], "INSUFFICIENT_CONTRIBUTION_SAMPLES: 7/8")

    def test_insufficient_branch_keeps_its_cold_start_share_when_others_update(self):
        samples = [
            contribution(branch_id, index, risk_adjusted=value)
            for index in range(MIN_CONTRIBUTION_SAMPLES)
            for branch_id, value in (("positive", 0.1), ("negative", -0.1))
        ] + [
            contribution("insufficient", index, risk_adjusted=0.0)
            for index in range(MIN_CONTRIBUTION_SAMPLES - 1)
        ]

        result = calculate_contribution_weights(
            samples,
            branch_ids=["positive", "negative", "insufficient"],
            eligible_branch_ids=["positive", "negative", "insufficient"],
        )
        items = by_branch(result)

        self.assertEqual(result["weight_mode"], "CONTRIBUTION_WEIGHTED")
        self.assertAlmostEqual(items["insufficient"]["weight"], 1.0 / 3.0)
        self.assertEqual(items["insufficient"]["weight_status"], "INSUFFICIENT_CONTRIBUTION_SAMPLES: 7/8")
        self.assertAlmostEqual(items["positive"]["weight"] + items["negative"]["weight"], 2.0 / 3.0)

    def test_state_file_is_the_weighting_source(self):
        samples = [
            contribution("a", index, risk_adjusted=0.1)
            for index in range(MIN_CONTRIBUTION_SAMPLES)
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "backtest"
            target.mkdir()
            (target / "contribution_samples.json").write_text(
                json.dumps({"sample_count": len(samples), "samples": samples}),
                encoding="utf-8",
            )
            result = build_weighting_from_state(
                root,
                branch_ids=["a"],
                eligible_branch_ids=["a"],
            )

        self.assertEqual(result["source"]["status"], "CONTRIBUTION_SAMPLES_LOADED")
        self.assertEqual(result["source"]["loaded_sample_count"], MIN_CONTRIBUTION_SAMPLES)
        self.assertEqual(result["weight_sample_count"], MIN_CONTRIBUTION_SAMPLES)

    def test_excluded_branch_does_not_make_current_real_input_dynamic(self):
        samples = [
            contribution("s1_momentum", index, risk_adjusted=0.5)
            for index in range(4)
        ] + [
            contribution("s2_meanrev", index, risk_adjusted=-0.5)
            for index in range(10)
        ]

        result = calculate_contribution_weights(
            samples,
            branch_ids=["s1_momentum", "s2_meanrev"],
            eligible_branch_ids=["s1_momentum"],
            branch_participation={
                "s1_momentum": "COLD_START_ELIGIBLE",
                "s2_meanrev": "EXCLUDED_PENDING_BACKTEST",
            },
        )
        items = by_branch(result)

        self.assertEqual(result["weight_mode"], "COLD_START_EQUAL")
        self.assertEqual(result["weight_sample_count"], 4)
        self.assertEqual(items["s1_momentum"]["weight_status"], "INSUFFICIENT_CONTRIBUTION_SAMPLES: 4/8")
        self.assertEqual(items["s2_meanrev"]["weight"], 0.0)
        self.assertEqual(items["s2_meanrev"]["weight_status"], "EXCLUDED_BY_BRANCH_GATE:EXCLUDED_PENDING_BACKTEST")


if __name__ == "__main__":
    unittest.main()
