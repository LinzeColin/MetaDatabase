"""global-equity-lead-lag-atlas 分支：会话对齐、证据门与方向。

行情为种子固定的合成序列（本环境无法访问新浪/腾讯录制真实日线）。每个用例把
一种关系「种」进序列，再断言分支按 GELA 的门给出或拒绝方向。
"""

from __future__ import annotations

import math
import random
import unittest
from datetime import date, timedelta

from signal_lattice.branches.lead_lag import BRANCH_ID, evaluate_lead_lag_verdicts, paired_samples
from signal_lattice.branches.runtime import DECISION_INPUT_SYMBOLS, build_branch_report
from signal_lattice.live_config import default_universe
from signal_lattice.marketdata.models import Bar


def weekdays(count: int, start: date = date(2024, 1, 2)) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def series(symbol: str, days: list[date], returns: list[float]) -> list[Bar]:
    close = 100.0
    bars = []
    for day, value in zip(days, returns):
        close *= math.exp(value)
        bars.append(Bar(symbol, day, close, close * 1.01, close * 0.99, close, 1.0, "UTC", "synthetic", None))  # type: ignore[arg-type]
    return bars


def market(n: int, *, beta: float, same_day: bool = False, seed: int = 7, last_source: float | None = None) -> dict[str, list[Bar]]:
    rng = random.Random(seed)
    days = weekdays(n)
    source = [rng.gauss(0, 0.01) for _ in range(n)]
    if last_source is not None:
        source[-1] = last_source
    targets = {}
    for symbol in ("sh000300", "hk02800"):
        noise = [rng.gauss(0, 0.004) for _ in range(n)]
        # same_day=False：目标第 d 日收益由美股第 d-1 日（亚洲开盘前最后一个收盘）驱动。
        driver = source if same_day else [0.0] + source[:-1]
        targets[symbol] = series(symbol, days, [beta * a + b for a, b in zip(driver, noise)])
    return {"usSPY": series("usSPY", days, source), **targets}


def by_symbol(verdicts, symbol):
    return next(item for item in verdicts if item.symbol == symbol)


class LeadLagBranchTests(unittest.TestCase):
    def test_planted_previous_us_session_relation_is_confirmed_and_gives_direction(self):
        # 美股最后一个收盘（d 日 16:00 纽约）晚于目标 d 日开盘，属于尚未被使用的新信息。
        for last, expected in ((0.02, "看涨"), (-0.02, "看跌")):
            data = market(300, beta=0.6, last_source=last)
            verdict = by_symbol(evaluate_lead_lag_verdicts(data), "sh000300")
            self.assertEqual(verdict.evidence["status"], "CONFIRMED", verdict.evidence["failure_reasons"])
            self.assertTrue(verdict.evidence["source_session_is_new_information"])
            self.assertEqual(verdict.direction, expected)
            self.assertEqual(verdict.weight, 1.0)
            self.assertGreater(verdict.evidence["slope"], 0.4)
            self.assertGreater(verdict.evidence["oos_mse_improvement"], 0.0)
            self.assertGreater(verdict.confidence, 0.5)

    def test_same_calendar_day_relation_is_not_visible_before_asia_open(self):
        # 美股 d 日收盘晚于亚洲 d 日收盘；若分支误用同日美股收益（前视），这里会被“确认”。
        data = market(300, beta=0.6, same_day=True)
        verdict = by_symbol(evaluate_lead_lag_verdicts(data), "sh000300")
        self.assertNotEqual(verdict.evidence["status"], "CONFIRMED")
        self.assertEqual(verdict.weight, 0.0)
        self.assertEqual(verdict.participation_status, "EVIDENCE_GATE_NOT_PASSED")

    def test_alignment_uses_last_source_close_strictly_before_target_open(self):
        data = market(10, beta=0.0)
        x, _y, days = paired_samples(data["usSPY"], data["sh000300"], "sh000300")
        source_returns = [math.log(b.close / a.close) for a, b in zip(data["usSPY"], data["usSPY"][1:])]
        # 目标第 2 个会话（index 1）对齐美股第 1 个会话，其收益无前值 -> 从目标 index 2 开始配对。
        self.assertEqual(days[0], data["sh000300"][2].day.isoformat())
        self.assertAlmostEqual(x[0], source_returns[0])

    def test_independent_markets_do_not_pass_the_evidence_gate(self):
        verdict = by_symbol(evaluate_lead_lag_verdicts(market(300, beta=0.0)), "hk02800")
        self.assertEqual(verdict.direction, "中性")
        self.assertEqual(verdict.weight, 0.0)
        self.assertTrue(verdict.evidence["failure_reasons"])

    def test_short_history_is_sample_insufficient(self):
        verdict = by_symbol(evaluate_lead_lag_verdicts(market(40, beta=0.6)), "sh000300")
        self.assertEqual(verdict.participation_status, "SAMPLE_INSUFFICIENT")
        self.assertEqual(verdict.weight, 0.0)

    def test_stale_source_session_gives_no_direction(self):
        # 去掉美股最后一根：最新美股收盘早于目标最后一个会话开盘，已被那个会话用过。
        data = market(300, beta=0.6)
        data["usSPY"] = data["usSPY"][:-1]
        verdict = by_symbol(evaluate_lead_lag_verdicts(data), "sh000300")
        self.assertEqual(verdict.evidence["status"], "CONFIRMED")
        self.assertEqual(verdict.participation_status, "NO_FRESH_SOURCE_SESSION")
        self.assertEqual(verdict.weight, 0.0)

    def test_branch_is_part_of_the_report_and_targets_are_decision_inputs(self):
        data = market(300, beta=0.6)
        report = build_branch_report(default_universe(), data)
        ids = {item["branch_id"] for item in report["branches"] if item["implemented"]}
        self.assertIn(BRANCH_ID, ids)
        self.assertTrue({"usSPY", "sh000300", "hk02800"} <= DECISION_INPUT_SYMBOLS)
        others = [item for item in report["branches"] if item["branch_id"] == BRANCH_ID and item["symbol"] == "hk00700"]
        self.assertEqual(others[0]["participation_status"], "OUT_OF_STRATEGY_UNIVERSE")


if __name__ == "__main__":
    unittest.main()
