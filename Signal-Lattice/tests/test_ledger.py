"""前向记分簿：只追加、随机对照可复现、20/60 日结算、样本不足不出数字。"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_lattice import ledger as L
from signal_lattice.costs import BENCHMARK_DOLLAR_VOLUME, round_trip_cost

# 结算要求出场日相对 now 已收盘（缺陷 #3）。这里的合成日历（90 个工作日）一直走到 2027 年 1 月，所以「现在」放在它之后。
T0 = datetime(2027, 3, 1, 21, 0, tzinfo=timezone.utc)


def calendar(start="2026-09-01", n=90):
    days, d = [], datetime.fromisoformat(start)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.date().isoformat())
        d += timedelta(days=1)
    return days


def bars(days, start_price, daily):
    price, out = start_price, []
    for day in days:
        out.append((day, round(price, 6)))
        price *= 1.0 + daily
    return out


def recommendation(symbol="ALPHA", cap=1.2e9, branches=(("equity-event-atlas", "PASS", 1.0), ("stock-commercial-opportunities", "RANK", 0.3))):
    return {"state": "RECOMMENDATION", "action": "研究跟进（看多）", "action_code": "RESEARCH_FOLLOW_LONG", "primary_symbol": symbol,
            "primary_name": symbol + " Inc", "market_cap_usd": cap, "watchlist": [{"symbol": "BETA"}],
            "support": {"total": 1.3, "branches": [{"branch_id": b, "kind": k, "weighted": w} for b, k, w in branches]},
            "data_chain": {"snapshot_sha256": "a" * 64}}


NO_ACTION = {"state": "NO_ACTION", "action": None, "action_code": "NO_ACTION", "primary_symbol": None, "watchlist": [{"symbol": "BETA"}],
             "data_chain": {"snapshot_sha256": "a" * 64}}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = L.Ledger(Path(self._tmp.name) / "ledger.sqlite")
        self.addCleanup(self.ledger.close)
        self.days = calendar()


class AppendOnlyTests(Base):
    def test_update_and_delete_are_refused_by_the_database_itself(self):
        iwm, stock = bars(self.days, 200.0, 0.001), bars(self.days, 10.0, 0.004)
        self.ledger.record_day(self.days[0], recommendation(), close_price=10.0, iwm_close=200.0, now=T0)
        self.ledger.settle_due({"ALPHA": stock}.get, iwm, T0)
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM settlement").fetchone()[0], 2)      # 两张表里都有行，触发器才会触发
        for statement in ("UPDATE daily_record SET close_price = 1", "DELETE FROM daily_record",
                          "UPDATE settlement SET hit = 0", "DELETE FROM settlement"):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError) as raised:
                self.ledger.db.execute(statement)
            self.assertIn("append-only", str(raised.exception))

    def test_one_row_per_trading_day_and_the_first_record_wins(self):
        self.assertTrue(self.ledger.record_day(self.days[0], recommendation("ALPHA"), close_price=10.0, iwm_close=200.0, now=T0))
        self.assertFalse(self.ledger.record_day(self.days[0], recommendation("OTHER"), close_price=99.0, iwm_close=1.0, now=T0))
        row = self.ledger.db.execute("SELECT symbol, close_price FROM daily_record").fetchone()
        self.assertEqual((row["symbol"], row["close_price"]), ("ALPHA", 10.0))

    def test_no_action_days_record_the_watchlist_and_iwm_but_no_stock_price(self):
        self.ledger.record_day(self.days[0], NO_ACTION, close_price=None, iwm_close=200.0, now=T0)
        row = self.ledger.db.execute("SELECT * FROM daily_record").fetchone()
        self.assertEqual(row["decision_state"], "NO_ACTION")
        self.assertIsNone(row["symbol"])
        self.assertEqual(json.loads(row["watchlist_json"]), [{"symbol": "BETA"}])
        self.assertEqual(row["iwm_close"], 200.0)

    def test_a_recommendation_without_a_close_price_is_refused_no_invented_prices(self):
        with self.assertRaises(ValueError):
            self.ledger.record_day(self.days[0], recommendation(), close_price=None, iwm_close=200.0, now=T0)
        with self.assertRaises(ValueError):
            self.ledger.record_day(self.days[0], {"state": "SYSTEM_BLOCKED"}, close_price=None, iwm_close=200.0, now=T0)

    def test_decision_supporters_are_stored_for_the_branch_hit_rates(self):
        self.ledger.record_day(self.days[0], recommendation(), close_price=10.0, iwm_close=200.0, now=T0)
        stored = json.loads(self.ledger.db.execute("SELECT supporters_json FROM daily_record").fetchone()[0])
        self.assertEqual([s["branch_id"] for s in stored], ["equity-event-atlas", "stock-commercial-opportunities"])


class ControlTests(unittest.TestCase):
    POOL = [{"symbol": "S%03d" % i, "market_cap_usd": cap} for i, cap in enumerate([5e8] * 30 + [1.5e9] * 30 + [3e9] * 30)]

    def test_the_tier_bands(self):
        self.assertEqual([L.cap_tier(x) for x in (3e8, 9.9e8, 1e9, 1.99e9, 2e9, 5e9)],
                         ["3-10亿美元", "3-10亿美元", "10-20亿美元", "10-20亿美元", "20-50亿美元", "20-50亿美元"])
        self.assertIsNone(L.cap_tier(2e8))
        self.assertIsNone(L.cap_tier(None))

    def test_same_day_same_pool_gives_the_same_control_and_it_is_in_the_same_tier(self):
        a = L.draw_control("2026-10-01", "ALPHA", 1.5e9, self.POOL)
        b = L.draw_control("2026-10-01", "ALPHA", 1.5e9, list(reversed(self.POOL)))
        self.assertEqual(a, b)
        self.assertEqual(a["tier"], "10-20亿美元")
        self.assertEqual(L.cap_tier(next(e for e in self.POOL if e["symbol"] == a["symbol"])["market_cap_usd"]), a["tier"])
        self.assertEqual(a["pool_size"], 30)

    def test_different_days_draw_differently_and_the_pick_itself_is_excluded(self):
        picks = {L.draw_control("2026-10-%02d" % d, "S030", 1.5e9, self.POOL)["symbol"] for d in range(1, 21)}
        self.assertGreater(len(picks), 3)
        self.assertNotIn("S030", picks)

    def test_unavailable_prices_move_on_to_the_next_seeded_name(self):
        first = L.draw_control("2026-10-01", "ALPHA", 1.5e9, self.POOL)
        second = L.draw_control("2026-10-01", "ALPHA", 1.5e9, self.POOL, has_close=lambda s: s != first["symbol"])
        self.assertNotEqual(first["symbol"], second["symbol"])
        self.assertEqual(second["attempt"], 1)
        self.assertIsNone(L.draw_control("2026-10-01", "ALPHA", 1.5e9, self.POOL, has_close=lambda s: False))

    def test_a_cap_outside_the_bands_has_no_control(self):
        self.assertIsNone(L.draw_control("2026-10-01", "ALPHA", 9e9, self.POOL))


class SettlementTests(Base):
    def setUp(self):
        super().setUp()
        self.iwm = bars(self.days, 200.0, 0.001)
        self.stock = bars(self.days, 10.0, 0.004)
        self.control = bars(self.days, 20.0, 0.002)
        self.book = {"ALPHA": self.stock, "CTRL": self.control}
        self.day0 = self.days[5]
        self.ledger.record_day(self.day0, recommendation(), close_price=dict(self.stock)[self.day0], iwm_close=dict(self.iwm)[self.day0],
                               control={"symbol": "CTRL", "tier": "10-20亿美元", "seed": "s", "pool_size": 3, "pool_sha": "p"},
                               control_close=dict(self.control)[self.day0], now=T0)

    def test_nothing_settles_before_20_trading_days(self):
        early = self.iwm[: 5 + 20]                                            # 只到第 19 个交易日
        self.assertEqual(self.ledger.settle_due(self.book.get, early, T0), [])

    def test_20_day_settlement_computes_excess_vs_iwm_and_vs_the_control(self):
        # 口径与回测对齐：决策日 d 的下一个交易日收盘入场（days[6]），再持有 20 个交易日（出场 days[26]），每条腿都扣成本模型的往返成本。
        done = self.ledger.settle_due(self.book.get, self.iwm[: 5 + 22], T0)
        self.assertEqual([(d["horizon"], d["entry_day"], d["exit_day"]) for d in done], [(20, self.days[6], self.days[26])])
        row = self.ledger.db.execute("SELECT * FROM settlement WHERE horizon = 20").fetchone()
        entry, exit_ = self.days[6], self.days[26]
        stock = dict(self.stock)[exit_] / dict(self.stock)[entry] - 1
        iwm = dict(self.iwm)[exit_] / dict(self.iwm)[entry] - 1
        control = dict(self.control)[exit_] / dict(self.control)[entry] - 1
        stock_cost = round_trip_cost(None, dict(self.stock)[entry])                 # 记录时没给成交额：按最差一档
        iwm_cost = round_trip_cost(BENCHMARK_DOLLAR_VOLUME, dict(self.iwm)[entry])
        control_cost = round_trip_cost(None, dict(self.control)[entry])
        self.assertAlmostEqual(row["stock_return"], stock)
        self.assertAlmostEqual(row["stock_cost"], stock_cost)
        self.assertAlmostEqual(row["excess_vs_iwm"], (stock - stock_cost) - (iwm - iwm_cost))
        self.assertAlmostEqual(row["excess_vs_control"], (stock - stock_cost) - (control - control_cost))
        self.assertEqual(row["entry_day"], entry)
        self.assertEqual(row["hit"], 1)
        self.assertIsNone(row["brier"])                                       # 当时没有概率，不编 Brier

    def test_60_day_settles_later_and_settlement_is_idempotent(self):
        self.ledger.settle_due(self.book.get, self.iwm[: 5 + 22], T0)
        self.assertEqual(self.ledger.settle_due(self.book.get, self.iwm[: 5 + 22], T0), [])      # 不重复结算
        done = self.ledger.settle_due(self.book.get, self.iwm, T0)
        self.assertEqual([d["horizon"] for d in done], [60])
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM settlement").fetchone()[0], 2)

    def test_a_losing_recommendation_is_kept_and_counts_as_a_miss(self):
        losing = {"ALPHA": bars(self.days, 10.0, -0.01), "CTRL": self.control}
        self.ledger.db.close()
        other = L.Ledger(Path(self._tmp.name) / "second.sqlite")
        self.addCleanup(other.close)
        other.record_day(self.day0, recommendation(), close_price=dict(losing["ALPHA"])[self.day0], iwm_close=dict(self.iwm)[self.day0], now=T0)
        other.settle_due(losing.get, self.iwm, T0)
        row = other.db.execute("SELECT * FROM settlement WHERE horizon = 20").fetchone()
        self.assertLess(row["excess_vs_iwm"], 0)
        self.assertEqual(row["hit"], 0)
        self.assertLess(row["stock_return"], 0)

    def test_missing_exit_price_skips_the_settlement_instead_of_estimating(self):
        self.assertEqual(self.ledger.settle_due({"ALPHA": self.stock[:10], "CTRL": self.control}.get, self.iwm, T0), [])
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM settlement").fetchone()[0], 0)

    def test_brier_is_computed_only_when_the_recommendation_carried_a_probability(self):
        other = L.Ledger(Path(self._tmp.name) / "brier.sqlite")
        self.addCleanup(other.close)
        other.record_day(self.day0, recommendation(), close_price=dict(self.stock)[self.day0], iwm_close=dict(self.iwm)[self.day0], now=T0, probability=0.7)
        other.settle_due(self.book.get, self.iwm[: 5 + 22], T0)
        self.assertAlmostEqual(other.db.execute("SELECT brier FROM settlement").fetchone()[0], (0.7 - 1.0) ** 2)

    def test_the_calendar_comes_from_iwm_so_holidays_do_not_count(self):
        with_holiday = [d for d in self.iwm if d[0] != self.days[10]]           # IWM 那天没有日线（休市）
        self.assertEqual(L.trading_days_after(with_holiday, self.day0, 5), self.days[11])

    def test_branch_hit_stats_count_only_supporting_branches(self):
        self.ledger.settle_due(self.book.get, self.iwm[: 5 + 22], T0)
        stats = self.ledger.branch_hit_stats(20)
        self.assertEqual(stats["equity-event-atlas"], {"n": 1, "hits": 1})
        self.assertEqual(stats["stock-commercial-opportunities"], {"n": 1, "hits": 1})
        self.assertNotIn("bottleneck-serenity-skill", stats)


class SettlementNeedsAClosedExitDayTests(Base):
    """缺陷 #3：盘中那一根日线只有半天，不能当出场收盘价。settle_due 要求出场日已经收盘。"""

    def setUp(self):
        super().setUp()
        self.iwm = bars(self.days, 200.0, 0.001)
        self.stock = bars(self.days, 10.0, 0.004)
        self.day0 = self.days[5]
        self.ledger.record_day(self.day0, recommendation(), close_price=dict(self.stock)[self.day0], iwm_close=dict(self.iwm)[self.day0], now=T0)
        self.exit_day = self.days[26]                                              # 2026-10-07

    def test_at_eleven_in_the_morning_on_the_exit_day_nothing_settles(self):
        intraday = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)                # 美东 11:00
        self.assertEqual(self.ledger.settle_due({"ALPHA": self.stock}.get, self.iwm[: 5 + 22], intraday), [])
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM settlement").fetchone()[0], 0)

    def test_after_the_close_the_same_bars_settle(self):
        before = datetime(2026, 10, 7, 19, 59, tzinfo=timezone.utc)                 # 美东 15:59
        after = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)                   # 美东 16:00
        self.assertEqual(self.ledger.settle_due({"ALPHA": self.stock}.get, self.iwm[: 5 + 22], before), [])
        self.assertEqual([d["exit_day"] for d in self.ledger.settle_due({"ALPHA": self.stock}.get, self.iwm[: 5 + 22], after)], [self.exit_day])

    def test_the_day_after_thanksgiving_closes_at_one_so_two_pm_settles(self):
        ledger_days = [d for d in calendar(start="2026-10-01", n=60) if d not in ("2026-11-26",)]
        iwm, stock = bars(ledger_days, 200.0, 0.001), bars(ledger_days, 10.0, 0.004)
        record_day = ledger_days[ledger_days.index("2026-11-27") - 21]              # 入场 +1，出场 +21 = 11-27（半日市）
        self.ledger.record_day(record_day, recommendation("HALF"), close_price=dict(stock)[record_day], iwm_close=dict(iwm)[record_day], now=T0)
        book = {"HALF": stock}.get
        self.assertEqual(self.ledger.settle_due(book, iwm[: ledger_days.index("2026-11-27") + 1], datetime(2026, 11, 27, 17, 30, tzinfo=timezone.utc)), [])   # 12:30
        done = self.ledger.settle_due(book, iwm[: ledger_days.index("2026-11-27") + 1], datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc))                      # 14:00
        self.assertEqual([d["exit_day"] for d in done if d["symbol"] == "HALF" and d["horizon"] == 20], ["2026-11-27"])


class ForwardEvidenceIndependenceTests(unittest.TestCase):
    """缺陷 #2：前向证据只数独立样本（不同标的、20 日窗口不重叠）；口径与回测一致（次日收盘入场、扣成本）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = L.Ledger(Path(self._tmp.name) / "ledger.sqlite")
        self.addCleanup(self.ledger.close)
        self.days = calendar(start="2025-01-02", n=400)
        self.iwm = bars(self.days, 200.0, 0.0)
        self.up_10_percent_per_window = (1.1) ** (1 / 20) - 1

    def shadow(self, symbol, day_index, book):
        day = self.days[day_index]
        decision = {"state": "NO_ACTION", "watchlist": [], "data_chain": {"snapshot_sha256": "a" * 64},
                    "shadow_candidate": {"symbol": symbol, "name": symbol, "market_cap_usd": 1.2e9, "support_branches": []}}
        self.ledger.record_shadow(day, decision, close_price=dict(book[symbol])[day], iwm_close=200.0, now=T0, dollar_volume=8e6)

    def settle(self, book):
        return self.ledger.settle_shadow_due(book.get, self.iwm, T0)

    def test_eight_consecutive_days_of_one_stock_are_one_sample_not_eight(self):
        book = {"ABCD": bars(self.days, 10.0, self.up_10_percent_per_window)}
        for i in range(8):
            self.shadow("ABCD", 30 + i, book)
        self.assertEqual(len([d for d in self.settle(book) if d["horizon"] == 20]), 8)         # 八条都结算了……
        evidence = self.ledger.forward_evidence(20)
        self.assertEqual(evidence["settled"], 1)                                                # ……但只算一个独立样本
        self.assertEqual(evidence["hits"], 1)
        detail = self.ledger.forward_evidence_overlap(20)
        self.assertEqual((detail["raw_settled"], detail["independent_settled"], detail["excluded_not_independent"]), (8, 1, 7))
        from signal_lattice import hub
        gate = hub.proof_gate(None, {**evidence, **detail})
        self.assertFalse(gate["open"])
        self.assertFalse(gate["forward"]["sufficient"])

    def test_different_stocks_whose_holding_windows_overlap_still_count_once(self):
        book = {"S%d" % i: bars(self.days, 10.0, self.up_10_percent_per_window) for i in range(8)}
        for i in range(8):
            self.shadow("S%d" % i, 30 + i, book)                                                # 每天换一只，但窗口叠在一起
        self.settle(book)
        self.assertEqual(self.ledger.forward_evidence(20)["settled"], 1)

    def test_windows_that_do_not_overlap_on_different_stocks_all_count(self):
        book = {"S%d" % i: bars(self.days, 10.0, self.up_10_percent_per_window) for i in range(8)}
        for i in range(8):
            self.shadow("S%d" % i, 10 + 25 * i, book)                                           # 相隔 25 个交易日：窗口 [d+1, d+21] 互不相交
        self.settle(book)
        evidence = self.ledger.forward_evidence(20)
        self.assertEqual((evidence["settled"], evidence["hits"], evidence["shadow_settled"], evidence["formal_settled"]), (8, 8, 8, 0))
        self.assertGreater(evidence["mean_excess"], 0.05)

    def test_the_same_stock_twice_far_apart_counts_once(self):
        book = {"ABCD": bars(self.days, 10.0, self.up_10_percent_per_window)}
        self.shadow("ABCD", 10, book)
        self.shadow("ABCD", 60, book)
        self.settle(book)
        self.assertEqual(self.ledger.forward_evidence(20)["settled"], 1)

    def test_the_forward_return_is_net_of_the_same_cost_model_the_backtest_charges(self):
        book = {"ABCD": bars(self.days, 10.0, self.up_10_percent_per_window)}
        self.shadow("ABCD", 30, book)
        self.settle(book)
        row = self.ledger.db.execute("SELECT * FROM shadow_settlement WHERE horizon = 20").fetchone()
        gross = row["stock_return"]
        self.assertAlmostEqual(gross, 0.1, places=6)
        self.assertAlmostEqual(row["stock_cost"], round_trip_cost(8e6, row["entry_close"]))
        self.assertAlmostEqual(row["excess_vs_iwm"], (gross - row["stock_cost"]) - (0.0 - row["iwm_cost"]))
        self.assertLess(row["excess_vs_iwm"], gross)                                            # 扣了成本
        self.assertEqual(row["entry_day"], self.days[31])                                       # 决策日 d 的下一个交易日入场

    def test_rows_settled_under_the_old_caliber_never_count_as_forward_evidence(self):
        with self.ledger.db:
            self.ledger.db.execute("INSERT INTO shadow_record (trading_day, recorded_at, symbol, decision_json, supporters_json, close_price, iwm_close) "
                                   "VALUES ('2025-02-03','x','OLD','{}','[]',10,200)")
            self.ledger.db.execute("INSERT INTO shadow_settlement (record_id, horizon, exit_day, settled_at, exit_close, iwm_exit_close, stock_return, "
                                   "iwm_return, excess_vs_iwm, hit) VALUES (1,20,'2025-03-03','x',11,200,0.1,0,0.1,1)")
        self.assertEqual(self.ledger.forward_evidence(20)["settled"], 0)


class SummaryTests(Base):
    def fill(self, n_settled, *, win=True):
        """n 个不同交易日的建议，全部结算 20 日。win=False 时亏损。"""
        iwm = bars(self.days, 200.0, 0.0)
        book = {}
        for i in range(n_settled):
            symbol = "S%02d" % i
            book[symbol] = bars(self.days, 10.0, 0.01 if win else -0.01)
            self.ledger.record_day(self.days[i], recommendation(symbol), close_price=dict(book[symbol])[self.days[i]],
                                   iwm_close=200.0, now=T0)
        self.ledger.settle_due(book.get, iwm, T0)

    def test_fewer_than_8_settled_says_insufficient_and_contains_no_numbers_at_all(self):
        self.fill(7)
        summary = self.ledger.summary()
        self.assertEqual(summary["sample_status"], "SAMPLE_INSUFFICIENT")
        self.assertIn("样本不足，暂不下结论", summary["message"])
        text = json.dumps(summary, ensure_ascii=False)
        for forbidden in ("hit_rate", "mean_excess", "median_excess", "worst_excess", "excess_vs_iwm_20", "brier_mean"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(summary["settled"]["20"], 7)
        self.assertTrue(all("excess_vs_iwm_20" not in r for r in summary["recent"]))

    def test_at_8_settled_the_summary_publishes_everything_including_losses(self):
        self.days = calendar(n=50)                                              # 日历只到第 50 天：60 日结算还不可能
        self.fill(8, win=False)
        summary = self.ledger.summary()
        self.assertEqual(summary["sample_status"], "SUFFICIENT")
        block = summary["horizons"]["20"]
        self.assertEqual(block["hit_rate"], 0.0)
        self.assertLess(block["mean_excess_vs_iwm"], 0)
        self.assertLess(block["worst_excess_vs_iwm"], 0)
        self.assertLess(summary["recent"][0]["excess_vs_iwm_20"], 0)
        self.assertEqual(summary["horizons"]["60"]["status"], "SAMPLE_INSUFFICIENT")     # 60 日还没到 8 条

    def test_empty_ledger_is_honest_about_having_no_history(self):
        summary = self.ledger.summary()
        self.assertEqual((summary["recorded_days"], summary["sample_status"]), (0, "SAMPLE_INSUFFICIENT"))
        self.assertFalse(summary["backfilled"])
        self.assertTrue(summary["append_only"])


if __name__ == "__main__":
    unittest.main()
