"""事件研究：入场不抢跑、超额收益相对基准、去重、三分位概率、样本不足不出概率。"""

from __future__ import annotations

import copy
import random
import unittest
from datetime import date, timedelta

from signal_lattice.branches import event_study
from signal_lattice.branches.event_atlas import load_params


def make_days(n, start=date(2025, 1, 2)):
    days, cursor = [], start
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


DAYS = make_days(300)
BENCH = (DAYS, [100.0 + 0.1 * i for i in range(300)])


def series(daily_return, start=50.0):
    closes, price = [], start
    for _ in DAYS:
        closes.append(price)
        price *= 1 + daily_return
    return (DAYS, closes)


class MathTests(unittest.TestCase):
    def test_wilson_interval_brackets_the_estimate(self):
        low, high = event_study.wilson_interval(40, 100, 0.90)
        self.assertLess(low, 0.40)
        self.assertGreater(high, 0.40)
        self.assertEqual(event_study.wilson_interval(0, 0, 0.9), (0.0, 1.0))

    def test_quantile(self):
        self.assertEqual(event_study.quantile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertAlmostEqual(event_study.quantile([0, 10], 0.25), 2.5)

    def test_entry_is_strictly_after_the_filing_day(self):
        self.assertEqual(event_study.entry_index(DAYS, DAYS[10]), 11)      # 申报当日收盘不可用
        self.assertEqual(event_study.entry_index(DAYS, "2025-01-04"), 2)   # 周末申报 -> 下周一
        self.assertIsNone(event_study.entry_index(DAYS, DAYS[-1]))

    def test_excess_return_is_stock_minus_benchmark(self):
        stock = (DAYS, [100.0 * 1.001 ** i for i in range(300)])
        value = event_study.excess_return(stock, BENCH, 10, 20)
        stock_ret = 1.001 ** 20 - 1
        bench_ret = BENCH[1][30] / BENCH[1][10] - 1
        self.assertAlmostEqual(value, stock_ret - bench_ret, places=9)
        self.assertIsNone(event_study.excess_return(stock, BENCH, 290, 20))   # 持有期没走完，不算

    def test_missing_benchmark_day_gives_none_not_a_guess(self):
        thin = (DAYS[:15] + DAYS[16:], BENCH[1][:15] + BENCH[1][16:])
        self.assertIsNone(event_study.excess_return((DAYS, BENCH[1]), thin, 5, 10))


class DedupeTests(unittest.TestCase):
    def test_same_company_same_kind_inside_gap_is_dropped(self):
        events = [{"event_id": "a", "cik": 1, "symbol": "X", "kind": "K", "published_date": DAYS[10]},
                  {"event_id": "b", "cik": 1, "symbol": "X", "kind": "K", "published_date": DAYS[15]},
                  {"event_id": "c", "cik": 1, "symbol": "X", "kind": "K", "published_date": DAYS[40]},
                  {"event_id": "d", "cik": 1, "symbol": "X", "kind": "OTHER", "published_date": DAYS[12]}]
        kept = event_study.dedupe(events, {"X": DAYS}, 20)
        self.assertEqual([e["event_id"] for e in kept], ["a", "d", "c"])


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.params = copy.deepcopy(dict(load_params()))
        self.params["study"]["control_samples"] = 2000
        rng = random.Random(7)
        # 60 家公司：日收益服从同一分布的随机游走（对照）；带「好事件」的 40 家事件后额外 +8%
        self.bars, self.events = {}, []
        for i in range(60):
            closes, price = [], 50.0
            boost_at = 80 + i
            for index in range(300):
                closes.append(price)
                step = rng.gauss(0.0004, 0.012)
                if i < 40 and index == boost_at + 1:
                    step += 0.08
                price *= 1 + step
            symbol = "S%02d" % i
            self.bars[symbol] = (DAYS, closes)
            if i < 40:
                self.events.append({"event_id": "good:%d" % i, "cik": i, "symbol": symbol, "kind": "GOOD",
                                    "published_date": DAYS[boost_at]})
            if i < 5:
                self.events.append({"event_id": "few:%d" % i, "cik": i, "symbol": symbol, "kind": "FEW",
                                    "published_date": DAYS[100]})

    def test_good_event_class_tilts_bullish_and_carries_sample_size_and_confidence(self):
        result = event_study.study(self.events, self.bars, BENCH, self.params, (DAYS[0], DAYS[-1]))
        block = result["GOOD"]["horizons"]["20"]
        self.assertEqual(block["status"], "OK")
        self.assertEqual(block["n"], 40)
        self.assertEqual(block["confidence"], "LOW")                  # 30 <= n < 100
        probability = block["probability"]
        self.assertAlmostEqual(sum(probability.values()), 1.0, places=9)
        self.assertGreater(probability["bull"], 0.6)
        for name, (low, high) in block["probability_interval"].items():
            self.assertLessEqual(low, probability[name])
            self.assertGreaterEqual(high, probability[name])
        for scenario in block["scenario_range"].values():
            self.assertLessEqual(scenario["low"], scenario["mid"])
            self.assertLessEqual(scenario["mid"], scenario["high"])
        self.assertTrue(any("幸存者" in text for text in result["GOOD"]["limitations"]))

    def test_small_sample_gets_no_probability(self):
        result = event_study.study(self.events, self.bars, BENCH, self.params, (DAYS[0], DAYS[-1]))
        block = result["FEW"]["horizons"]["20"]
        self.assertEqual(block["status"], event_study.INSUFFICIENT)
        self.assertNotIn("probability", block)
        self.assertEqual(block["n"], 5)

    def test_events_too_recent_for_the_horizon_are_not_counted(self):
        late = [{"event_id": "late:%d" % i, "cik": i, "symbol": "S%02d" % i, "kind": "LATE",
                 "published_date": DAYS[-30]} for i in range(60)]
        result = event_study.study(late, self.bars, BENCH, self.params, (DAYS[0], DAYS[-1]))
        self.assertEqual(result["LATE"]["horizons"]["20"]["n"], 60)
        self.assertEqual(result["LATE"]["horizons"]["60"]["n"], 0)
        self.assertEqual(result["LATE"]["horizons"]["60"]["status"], event_study.INSUFFICIENT)


if __name__ == "__main__":
    unittest.main()
