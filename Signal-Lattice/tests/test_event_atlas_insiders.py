"""例行买入者剔除、历史不足单独计、10b5-1/小额/卖出不算、as_of 之后的申报不可见。"""

from __future__ import annotations

import unittest

from _event_fixtures import add_buy, add_p_history, form4_xml, txn, wrap_submission

from signal_lattice.evidence.eventstore import EventStore
from signal_lattice.evidence.insiders import (
    OPPORTUNISTIC, ROUTINE, UNCLASSIFIABLE, classify_buy, classified_buys, ingest_form4_payload, opportunistic_summary,
)

OWNER = 900001


def store_with_owner(first_filed="2015-01-05"):
    store = EventStore(":memory:")
    store.touch_owner_first([(OWNER, first_filed)], "test")
    store.commit()
    return store


class ClassificationTests(unittest.TestCase):
    def test_same_month_bought_in_each_of_last_three_years_is_routine(self):
        store = store_with_owner()
        add_p_history(store, OWNER, [(2023, 8), (2024, 8), (2025, 8)])
        self.assertEqual(classify_buy(store, OWNER, "2026-08-10", "2026-08-12"), ROUTINE)

    def test_missing_one_of_the_three_years_is_opportunistic(self):
        store = store_with_owner()
        add_p_history(store, OWNER, [(2023, 8), (2025, 8)])
        self.assertEqual(classify_buy(store, OWNER, "2026-08-10", "2026-08-12"), OPPORTUNISTIC)

    def test_other_months_do_not_make_a_routine_buyer(self):
        store = store_with_owner()
        add_p_history(store, OWNER, [(2023, 3), (2024, 3), (2025, 3), (2023, 9), (2024, 9), (2025, 9)])
        self.assertEqual(classify_buy(store, OWNER, "2026-08-10", "2026-08-12"), OPPORTUNISTIC)

    def test_less_than_three_years_of_history_is_unclassifiable_not_opportunistic(self):
        store = store_with_owner(first_filed="2024-05-01")
        add_p_history(store, OWNER, [(2024, 8), (2025, 8)])
        self.assertEqual(classify_buy(store, OWNER, "2026-08-10", "2026-08-12"), UNCLASSIFIABLE)

    def test_unknown_owner_is_unclassifiable(self):
        self.assertEqual(classify_buy(EventStore(":memory:"), 424242, "2026-08-10", "2026-08-12"), UNCLASSIFIABLE)

    def test_history_boundary_month_counts(self):
        # 第一次出现在往前第 3 年的同月月底之前 = 历史够了；晚一天就不够
        enough = store_with_owner(first_filed="2023-08-31")
        self.assertEqual(classify_buy(enough, OWNER, "2026-08-10", "2026-08-12"), OPPORTUNISTIC)
        short = store_with_owner(first_filed="2023-09-01")
        self.assertEqual(classify_buy(short, OWNER, "2026-08-10", "2026-08-12"), UNCLASSIFIABLE)

    def test_history_filed_after_the_purchase_is_not_visible(self):
        store = store_with_owner()
        add_p_history(store, OWNER, [(2023, 8), (2024, 8), (2025, 8)], filed_lag_days=3)
        # 把 2025-08 那笔的申报日挪到购买申报之后：当时看不到它，就不是例行
        store.db.execute("UPDATE insider_p SET filed = '2026-09-30' WHERE trade_date = '2025-08-15'")
        store.commit()
        self.assertEqual(classify_buy(store, OWNER, "2026-08-10", "2026-08-12"), OPPORTUNISTIC)


class AggregationTests(unittest.TestCase):
    def build(self):
        store = store_with_owner()
        add_buy(store, "A-1", OWNER, amount=100_000)                         # 机会型
        add_buy(store, "A-2", 900002, amount=80_000)                          # 历史不足 -> 无法分类
        store.touch_owner_first([(900002, "2025-06-01")], "test")
        add_buy(store, "A-3", 900003, amount=60_000)                          # 例行
        store.touch_owner_first([(900003, "2010-01-01")], "test")
        add_p_history(store, 900003, [(2023, 8), (2024, 8), (2025, 8)])
        add_buy(store, "A-4", 900004, amount=90_000, plan=1)                  # 10b5-1
        add_buy(store, "A-5", 900005, amount=10_000)                          # 小额
        store.commit()
        return store

    def test_buckets_and_exclusions(self):
        store = self.build()
        summary = opportunistic_summary(store, 1234567, "2026-09-01", 90, market_cap_usd=1e9)
        self.assertEqual(summary["counts"], {"opportunistic": 1, "routine": 1, "unclassifiable": 1})
        self.assertEqual(summary["excluded"], {"PLAN_10B5_1": 1, "BELOW_MIN_AMOUNT": 1})
        self.assertEqual(summary["opportunistic_insiders"], 1)
        self.assertEqual(summary["opportunistic_amount_usd"], 100_000)
        self.assertAlmostEqual(summary["pct_of_market_cap"], 1e-4)

    def test_routine_and_unclassifiable_are_not_counted_as_opportunistic_money(self):
        summary = opportunistic_summary(self.build(), 1234567, "2026-09-01", 90, market_cap_usd=1e9)
        self.assertNotIn(80_000, [b["amount_usd"] for b in summary["buys"]])
        self.assertNotIn(60_000, [b["amount_usd"] for b in summary["buys"]])

    def test_filings_after_as_of_are_invisible(self):
        store = self.build()
        before = opportunistic_summary(store, 1234567, "2026-08-11", 90, market_cap_usd=1e9)
        self.assertEqual(before["opportunistic_insiders"], 0)            # A-1 是 08-12 申报的
        self.assertEqual(before["counts"], {"opportunistic": 0, "routine": 0, "unclassifiable": 0})
        after = opportunistic_summary(store, 1234567, "2026-08-12", 90, market_cap_usd=1e9)
        self.assertEqual(after["opportunistic_insiders"], 1)

    def test_window_is_ninety_days_of_filing_date(self):
        store = store_with_owner()
        add_buy(store, "OLD", OWNER, filed="2026-05-01", first_trade="2026-04-28")
        self.assertEqual(opportunistic_summary(store, 1234567, "2026-07-30", 90)["opportunistic_insiders"], 1)
        self.assertEqual(opportunistic_summary(store, 1234567, "2026-08-15", 90)["opportunistic_insiders"], 0)

    def test_joint_filing_counts_as_one_buyer_and_one_amount(self):
        store = store_with_owner()
        for owner in (OWNER, 900007, 900008):
            store.touch_owner_first([(owner, "2010-01-01")], "test")
            add_buy(store, "JOINT-1", owner, amount=100_000)
        summary = opportunistic_summary(store, 1234567, "2026-09-01", 90, market_cap_usd=1e9)
        self.assertEqual(summary["opportunistic_insiders"], 1)
        self.assertEqual(summary["opportunistic_amount_usd"], 100_000)
        self.assertEqual(summary["counts"]["opportunistic"], 1)

    def test_same_price_same_day_many_buyers_is_offering_participation_not_open_market(self):
        store = store_with_owner()
        rows = []
        for index in range(5):
            owner = 910000 + index
            store.touch_owner_first([(owner, "2010-01-01")], "test")
            add_buy(store, "IPO-%d" % index, owner, amount=100_000)
            rows.append(("IPO-%d" % index, owner, 1234567, "2026-08-10", "2026-08-12", 10000.0, 10.0))
        store.add_insider_p(rows, "test")
        store.commit()
        plain = opportunistic_summary(store, 1234567, "2026-09-01", 90, market_cap_usd=1e9)
        guarded = opportunistic_summary(store, 1234567, "2026-09-01", 90, market_cap_usd=1e9, offering_like_min_buyers=4)
        self.assertEqual(plain["opportunistic_insiders"], 5)
        self.assertEqual(guarded["opportunistic_insiders"], 0)
        self.assertEqual(guarded["excluded"], {"OFFERING_LIKE": 5})

    def test_sale_never_reaches_the_store(self):
        store = store_with_owner()
        payload = wrap_submission(form4_xml([txn("S", shares=50_000, price=40.0, ad="D")])).encode()
        ingest_form4_payload(store, payload, "S-1", "2026-08-12", "now")
        rows, _ = classified_buys(store, "2026-09-01", issuer_cik=1234567)
        self.assertEqual(rows, [])

    def test_end_to_end_from_raw_xml(self):
        store = store_with_owner()
        payload = wrap_submission(form4_xml([txn("P", shares=2000, price=30.0)])).encode()
        ingest_form4_payload(store, payload, "E-1", "2026-08-12", "now")
        summary = opportunistic_summary(store, 1234567, "2026-08-20", 90, market_cap_usd=6e8)
        self.assertEqual(summary["opportunistic_insiders"], 1)
        self.assertEqual(summary["opportunistic_amount_usd"], 60_000.0)


if __name__ == "__main__":
    unittest.main()
