"""中枢回测：规则重放与线上是同一份代码、成交/成本、安慰剂、样本外窗口 < 6 不公布数字。"""

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from signal_lattice import hub
from signal_lattice.backtest import hub_backtest as H
from hub_fixtures import BOTTLENECK, COMMERCIAL, EVENT, filler, pool_entry, record, sec_link


def trading_days(start, n):
    days, d = [], date.fromisoformat(start)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


class FakeBars:
    def __init__(self, table):
        self.table = table

    def load(self, symbol):
        return self.table.get(symbol)


def series(days, start, daily, volume=5_000_000.0):
    price, rows = start, []
    for day in days:
        rows.append((day, price, volume))
        price *= 1 + daily
    return rows


DAYS = trading_days("2025-01-02", 260)
MONTH_ENDS = H.month_ends(DAYS, "2025-01-01", "2025-12-31")


def make_pack(day, *, alpha_event="PASS", placebo_event="ABSTAIN", alpha_rank=True, others=20):
    """一个月末：ALPHA（事件航图 alpha_event + 商业机会排序支持）；placebo_event 是「事件后移 60 日」时 ALPHA 的事件航图结论。"""
    tail = "%s" % day.replace("-", "")
    a_evt = sec_link("0000000001-25-%06d" % (int(tail) % 1_000_000), cik=1, date=day)
    a_com = sec_link("0000000002-25-%06d" % (int(tail) % 1_000_000), cik=1, supports="x", date=day)

    def event_rows(status):
        rows = [record("ALPHA", status, label={"PASS": "POSITIVE_EVENT", "FAILED": "DILUTION_VETO"}.get(status, "NO_QUALIFYING_EVENT"),
                       score=70.0 if status == "PASS" else 0.0, links=[a_evt] if status != "ABSTAIN" else [])]
        return rows + [record("Z%02d" % i, "ABSTAIN", score=0.0) for i in range(others)]

    commercial = [record("ALPHA", "ABSTAIN", label="SCREEN_FLAG", score=90.0 if alpha_rank else 1.0, links=[a_com])] + filler("C", others, base=50.0)
    pool = [pool_entry("ALPHA", cap=1.5e9, dollar_volume=8e6, price=10.0)] + [pool_entry("Z%02d" % i, cap=1.5e9) for i in range(others)] + \
           [pool_entry("C%02d" % i, cap=1.5e9) for i in range(others)]
    for entry in pool:
        entry["market_cap_usd"] = 1.5e9
    return {"as_of": day, "shifted_as_of": DAYS[max(0, DAYS.index(day) - 60)], "pool": pool,
            "records": {EVENT: event_rows(alpha_event), COMMERCIAL: commercial, BOTTLENECK: filler("B", others, base=30.0)},
            "placebo_event_atlas": event_rows(placebo_event)}


def bars_table(alpha_daily=0.010, iwm_daily=0.001, other_daily=0.001):
    table = {"IWM": series(DAYS, 200.0, iwm_daily, 5e9), "ALPHA": series(DAYS, 10.0, alpha_daily)}
    for prefix in ("Z", "C"):
        for i in range(21):
            table["%s%02d" % (prefix, i)] = series(DAYS, 10.0, other_daily)
    return FakeBars(table)


class CalendarTests(unittest.TestCase):
    def test_month_ends_are_the_last_trading_day_of_each_month(self):
        self.assertEqual(MONTH_ENDS[0], "2025-01-31")
        self.assertEqual(len(MONTH_ENDS), 12)
        self.assertTrue(all(d in DAYS for d in MONTH_ENDS))

    def test_shifting_trading_days(self):
        self.assertEqual(H.shift_trading_days(DAYS, DAYS[70], -60), DAYS[10])
        self.assertIsNone(H.shift_trading_days(DAYS, DAYS[5], -60))
        self.assertIsNone(H.shift_trading_days(DAYS, "1999-01-01", 1))

    def test_pool_at_reapplies_the_thresholds_on_that_days_prices(self):
        days = trading_days("2025-01-02", 80)
        entries = [{"symbol": "OK", "shares_outstanding": 1e8}, {"symbol": "CHEAP", "shares_outstanding": 1e8},
                   {"symbol": "THIN", "shares_outstanding": 1e8}, {"symbol": "HUGE", "shares_outstanding": 1e9},
                   {"symbol": "SHORT", "shares_outstanding": 1e8}, {"symbol": "DEAD", "shares_outstanding": 1e8}]
        store = FakeBars({"OK": series(days, 10.0, 0, 1e6), "CHEAP": series(days, 2.0, 0, 1e7), "THIN": series(days, 10.0, 0, 1e4),
                          "HUGE": series(days, 10.0, 0, 1e6), "SHORT": series(days[:30], 10.0, 0, 1e6), "DEAD": series(days[:40], 10.0, 0, 1e6)})
        pool = H.pool_at(entries, store, days[-1])
        self.assertEqual([e["symbol"] for e in pool], ["OK"])
        self.assertAlmostEqual(pool[0]["market_cap_usd"], 1e9)
        self.assertAlmostEqual(pool[0]["median_dollar_volume_20d_usd"], 1e7)

    def test_pool_at_only_sees_bars_up_to_that_day(self):
        days = trading_days("2025-01-02", 120)
        store = FakeBars({"X": series(days, 10.0, 0.0, 1e6)[:100] + [(d, 1000.0, 1e6) for d in days[100:]]})   # 之后暴涨
        early = H.pool_at([{"symbol": "X", "shares_outstanding": 1e8}], store, days[99])
        self.assertEqual(len(early), 1)                                                                           # 当天仍是 10 美元
        late = H.pool_at([{"symbol": "X", "shares_outstanding": 1e8}], store, days[110])
        self.assertEqual(late, [])                                                                                 # 涨到 1000 美元 -> 市值出区间


class CostAndTradeTests(unittest.TestCase):
    def test_cost_tiers_by_dollar_volume_and_round_trip_is_two_sides_plus_fixed(self):
        self.assertEqual([H._cost_bps_per_side(v) for v in (6e7, 2e7, 5e6, 1e6, None)], [10.0, 25.0, 50.0, 80.0, 80.0])
        self.assertGreater(H.round_trip_cost(5e6, 10.0), 2 * 50.0 / 1e4)                # 再加固定费用
        self.assertLess(H.round_trip_cost(6e7, 10.0), H.round_trip_cost(5e6, 10.0))

    def test_entry_is_the_next_trading_day_close_and_the_exit_horizon_later(self):
        rows = series(DAYS, 10.0, 0.01)
        result = H.trade_return(rows, DAYS, DAYS[50], 20, 1e7)
        self.assertEqual((result["entry_day"], result["exit_day"]), (DAYS[51], DAYS[71]))
        self.assertAlmostEqual(result["gross"], 1.01 ** 20 - 1, places=6)
        self.assertAlmostEqual(result["net"], result["gross"] - result["cost"])
        self.assertGreater(result["cost"], 0)

    def test_an_unmatured_horizon_or_missing_prices_give_none(self):
        rows = series(DAYS, 10.0, 0.01)
        self.assertIsNone(H.trade_return(rows, DAYS, DAYS[-5], 20, 1e7))
        self.assertIsNone(H.trade_return(rows[:60], DAYS, DAYS[50], 20, 1e7))

    def test_control_is_reproducible_uses_the_same_tier_and_pays_costs_too(self):
        bars = bars_table()
        pool = make_pack(MONTH_ENDS[2])["pool"]
        a = H.control_return(pool, bars, DAYS, MONTH_ENDS[2], 20, "ALPHA", 1.5e9)
        b = H.control_return(list(reversed(pool)), bars, DAYS, MONTH_ENDS[2], 20, "ALPHA", 1.5e9)
        self.assertEqual(a, b)
        self.assertGreater(a["draws"], 10)
        gross = 1.001 ** 20 - 1
        self.assertLess(a["net"], gross)                                              # 扣了成本


class ReplayTests(unittest.TestCase):
    def test_the_replay_uses_the_live_rule_pass_plus_rank_support_gives_the_pick(self):
        decided = H.decide_month(make_pack(MONTH_ENDS[2]))
        self.assertEqual(decided["pick"]["symbol"], "ALPHA")
        self.assertAlmostEqual(decided["pick"]["support_total"], 1.3)
        self.assertEqual({b for b, _ in decided["pick"]["branches"]}, {EVENT, COMMERCIAL})
        self.assertTrue(all(u.startswith("https://www.sec.gov/") for u in decided["pick"]["sources"]))

    def test_without_the_rank_support_or_with_a_dilution_failure_nothing_qualifies(self):
        self.assertIsNone(H.decide_month(make_pack(MONTH_ENDS[2], alpha_rank=False))["pick"])
        self.assertIsNone(H.decide_month(make_pack(MONTH_ENDS[2], alpha_event="FAILED"))["pick"])

    def test_placebo_uses_the_shifted_event_records_and_leaves_everything_else_alone(self):
        pack = make_pack(MONTH_ENDS[2], alpha_event="PASS", placebo_event="ABSTAIN")
        self.assertIsNotNone(H.decide_month(pack)["pick"])
        self.assertIsNone(H.decide_month(pack, placebo=True)["pick"])
        pack = make_pack(MONTH_ENDS[2], alpha_event="ABSTAIN", placebo_event="PASS")
        self.assertIsNone(H.decide_month(pack)["pick"])
        self.assertEqual(H.decide_month(pack, placebo=True)["pick"]["symbol"], "ALPHA")

    def test_liquidity_gate_uses_that_days_dollar_volume(self):
        pack = make_pack(MONTH_ENDS[2])
        pack["pool"][0]["median_dollar_volume_20d_usd"] = 1e6
        self.assertIsNone(H.decide_month(pack)["pick"])


class EvaluateTests(unittest.TestCase):
    def packs(self, n_pick):
        out = []
        for i, day in enumerate(MONTH_ENDS[:9]):
            out.append(make_pack(day, alpha_event="PASS" if i < n_pick else "ABSTAIN", placebo_event="ABSTAIN"))
        return out

    def test_windows_count_months_with_a_matured_pick_and_placebo_finds_nothing(self):
        result = H.evaluate(self.packs(7), bars_table(), DAYS)
        actual, placebo = result["summary"]["actual"], result["summary"]["placebo"]
        self.assertEqual(actual["months_with_pick"], 7)
        self.assertEqual(actual["pick_20"]["windows"], 7)
        self.assertEqual(placebo["months_with_pick"], 0)
        self.assertEqual(placebo["pick_20"]["excess_vs_iwm"], {"n": 0})

    def test_excess_is_net_of_costs_and_beats_iwm_when_the_pick_outruns_it(self):
        result = H.evaluate(self.packs(7), bars_table(alpha_daily=0.010, iwm_daily=0.001), DAYS)
        month = result["months"][0]
        outcome = month["actual"]["pick"]["outcomes"]["20"]
        self.assertGreater(outcome["excess_vs_iwm"], 0.15)
        self.assertLess(outcome["net"], outcome["gross"])
        self.assertAlmostEqual(outcome["excess_vs_iwm"], outcome["net"] - outcome["iwm_net"])
        self.assertIsNotNone(outcome["excess_vs_control"])
        self.assertGreater(month["actual"]["pick"]["capacity_usd_per_day"], 0)
        stats = result["summary"]["actual"]["pick_20"]["excess_vs_iwm"]
        self.assertEqual(stats["hit_rate"], 1.0)

    def test_a_losing_pick_is_counted_as_a_miss_not_dropped(self):
        result = H.evaluate(self.packs(7), bars_table(alpha_daily=-0.01), DAYS)
        stats = result["summary"]["actual"]["pick_20"]["excess_vs_iwm"]
        self.assertEqual(stats["hit_rate"], 0.0)
        self.assertLess(stats["worst"], 0)

    def test_the_placebo_can_be_run_against_the_same_bars_when_events_do_exist(self):
        packs = [make_pack(d, alpha_event="ABSTAIN", placebo_event="PASS") for d in MONTH_ENDS[:9]]
        result = H.evaluate(packs, bars_table(), DAYS)
        self.assertEqual(result["summary"]["actual"]["months_with_pick"], 0)
        self.assertEqual(result["summary"]["placebo"]["months_with_pick"], 9)

    def test_the_last_months_are_not_matured_and_are_not_counted_as_windows(self):
        packs = [make_pack(d) for d in (DAYS[-10], DAYS[-30], DAYS[100])]
        result = H.evaluate(packs, bars_table(), DAYS)
        self.assertIsNone(result["months"][0]["actual"]["pick"]["outcomes"]["20"])
        self.assertEqual(result["summary"]["actual"]["pick_20"]["windows"], 2)          # DAYS[-10] 离数据末尾不到 21 个交易日，没成熟


class PublicationGateTests(unittest.TestCase):
    def report(self, n_pick):
        packs = [make_pack(day, alpha_event="PASS" if i < n_pick else "ABSTAIN") for i, day in enumerate(MONTH_ENDS[:9])]
        result = H.evaluate(packs, bars_table(alpha_daily=0.01), DAYS)
        return H.build_report(result, snapshot_sha256="f" * 64, start="2025-01-31", end="2025-09-30", dates=MONTH_ENDS[:9])

    def test_below_six_windows_nothing_numeric_is_public_and_the_reason_is_written(self):
        report = self.report(5)
        self.assertEqual((report["oos_windows"], report["published"]), (5, False))
        public = json.dumps(report["public"], ensure_ascii=False)
        self.assertIn("OOS_HISTORY_INSUFFICIENT: 5/6", public)
        self.assertIn("样本外窗口 5 < 6", report["public"]["why_not_published"])
        self.assertNotIn("stitched", public)
        self.assertNotIn("excess", public)
        self.assertNotIn("hit_rate", public)
        rendered = H.render_summary(report)
        self.assertIn("不公布收益数字", rendered)
        self.assertIn("为什么不公布", rendered)

    def test_the_private_report_still_holds_the_full_numbers_for_internal_review(self):
        report = self.report(5)
        self.assertGreater(report["summary"]["actual"]["pick_20"]["excess_vs_iwm"]["mean"], 0)
        self.assertTrue(report["months"][0]["actual"]["pick"]["outcomes"]["20"])

    def test_at_six_windows_the_numbers_go_public_together_with_the_placebo(self):
        report = self.report(6)
        self.assertEqual((report["oos_windows"], report["published"]), (6, True))
        branch = report["public"]["branches"]["hub"]
        self.assertEqual(branch["profitability_evidence"], "SUFFICIENT")
        self.assertIn("stitched", branch)
        self.assertIn("placebo_pick_20", branch["stitched"])
        self.assertIsNone(report["public"]["why_not_published"])

    def test_the_report_records_the_rule_binding_and_its_validity_days_for_the_proof_gate(self):
        """缺陷 #1：报告里记录它对应的规则版本与参数 sha256，规则自证门读取时核对；35 天有效期。"""
        params = {b: {"params_version": "7", "params_sha256": "e" * 64} for b in hub.BACKTEST_BOUND_BRANCHES}
        binding = hub.rule_binding(params)
        packs = [make_pack(day, alpha_event="PASS") for day in MONTH_ENDS[:9]]
        result = H.evaluate(packs, bars_table(alpha_daily=0.01), DAYS)
        report = H.build_report(result, snapshot_sha256="f" * 64, start="2025-01-31", end="2025-09-30", dates=MONTH_ENDS[:9], binding=binding)
        self.assertEqual(report["binding"], binding)
        self.assertEqual(report["valid_days"], 35)
        now = datetime.now(timezone.utc)
        self.assertTrue(hub.proof_gate(report, None, expected_binding=binding, now=now)["backtest"]["usable"])
        changed = hub.rule_binding({**params, "equity-event-atlas": {"params_version": "7", "params_sha256": "f" * 64}})
        self.assertFalse(hub.proof_gate(report, None, expected_binding=changed, now=now)["backtest"]["usable"])
        unbound = H.build_report(result, snapshot_sha256="f" * 64, start="2025-01-31", end="2025-09-30", dates=MONTH_ENDS[:9])
        self.assertIsNone(unbound["binding"])
        self.assertFalse(hub.proof_gate(unbound, None, expected_binding=binding, now=now)["backtest"]["usable"])

    def test_the_assumptions_are_part_of_the_report(self):
        report = self.report(5)
        text = "\n".join(report["assumptions"])
        for word in ("幸存者偏差", "股势前瞻", "成本按 20 日成交额", "前复权", "安慰剂"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
