"""前向记分簿：只追加、随机对照可复现、20/60 日结算、样本不足不出数字。"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_lattice import ledger as L

T0 = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)


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
        done = self.ledger.settle_due(self.book.get, self.iwm[: 5 + 21], T0)
        self.assertEqual([(d["horizon"], d["exit_day"]) for d in done], [(20, self.days[25])])
        row = self.ledger.db.execute("SELECT * FROM settlement WHERE horizon = 20").fetchone()
        stock = dict(self.stock)[self.days[25]] / dict(self.stock)[self.day0] - 1
        iwm = dict(self.iwm)[self.days[25]] / dict(self.iwm)[self.day0] - 1
        control = dict(self.control)[self.days[25]] / dict(self.control)[self.day0] - 1
        self.assertAlmostEqual(row["stock_return"], stock)
        self.assertAlmostEqual(row["excess_vs_iwm"], stock - iwm)
        self.assertAlmostEqual(row["excess_vs_control"], stock - control)
        self.assertEqual(row["hit"], 1)
        self.assertIsNone(row["brier"])                                       # 当时没有概率，不编 Brier

    def test_60_day_settles_later_and_settlement_is_idempotent(self):
        self.ledger.settle_due(self.book.get, self.iwm[: 5 + 21], T0)
        self.assertEqual(self.ledger.settle_due(self.book.get, self.iwm[: 5 + 21], T0), [])      # 不重复结算
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
        other.settle_due(self.book.get, self.iwm[: 5 + 21], T0)
        self.assertAlmostEqual(other.db.execute("SELECT brier FROM settlement").fetchone()[0], (0.7 - 1.0) ** 2)

    def test_the_calendar_comes_from_iwm_so_holidays_do_not_count(self):
        with_holiday = [d for d in self.iwm if d[0] != self.days[10]]           # IWM 那天没有日线（休市）
        self.assertEqual(L.trading_days_after(with_holiday, self.day0, 5), self.days[11])

    def test_branch_hit_stats_count_only_supporting_branches(self):
        self.ledger.settle_due(self.book.get, self.iwm[: 5 + 21], T0)
        stats = self.ledger.branch_hit_stats(20)
        self.assertEqual(stats["equity-event-atlas"], {"n": 1, "hits": 1})
        self.assertEqual(stats["stock-commercial-opportunities"], {"n": 1, "hits": 1})
        self.assertNotIn("bottleneck-serenity-skill", stats)


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
