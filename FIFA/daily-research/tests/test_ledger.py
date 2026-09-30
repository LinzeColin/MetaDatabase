import unittest
from datetime import datetime, timezone

from fifa_daily import ledger


def dt(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


KW = dict(comp="en.1", day="2026-10-10", kickoff_utc="2026-10-10T14:00Z", home="a", away="b", home_name="A",
          away_name="B", p=[0.5, 0.3, 0.2], p_base=[0.45, 0.27, 0.28], lam=[1.5, 1.0], model="m")


class LedgerTests(unittest.TestCase):
    def test_prediction_refreshed_until_kickoff_then_frozen(self):
        led = {}
        ledger.upsert_prediction(led, mid="m1", now=dt("2026-10-01T00:00Z"), **KW)
        first = led["entries"]["m1"]["first_predicted_at"]
        ledger.upsert_prediction(led, mid="m1", now=dt("2026-10-05T00:00Z"), **{**KW, "p": [0.6, 0.25, 0.15]})
        self.assertEqual(led["entries"]["m1"]["p"][0], 0.6)
        self.assertEqual(led["entries"]["m1"]["first_predicted_at"], first)
        ledger.settle(led, {}, dt("2026-10-10T15:00Z"))  # 开球后冻结
        self.assertTrue(led["entries"]["m1"]["frozen"])
        ledger.upsert_prediction(led, mid="m1", now=dt("2026-10-10T16:00Z"), **{**KW, "p": [0.9, 0.05, 0.05]})
        self.assertEqual(led["entries"]["m1"]["p"][0], 0.6)  # 冻结后不许改

    def test_no_hindsight_for_matches_first_seen_after_kickoff(self):
        led = {}
        ledger.upsert_prediction(led, mid="late", now=dt("2026-10-10T20:00Z"), **KW)
        self.assertNotIn("late", led.get("entries", {}))

    def test_settle_scores_once(self):
        led = {}
        ledger.upsert_prediction(led, mid="m1", now=dt("2026-10-01T00:00Z"), **KW)
        n = ledger.settle(led, {"m1": (2, 0)}, dt("2026-10-11T00:00Z"))
        self.assertEqual(n, 1)
        sc = led["entries"]["m1"]["score"]
        self.assertTrue(sc["hit"])
        self.assertAlmostEqual(sc["logloss"], 0.6931, places=3)
        self.assertEqual(ledger.settle(led, {"m1": (0, 3)}, dt("2026-10-12T00:00Z")), 0)  # 已打分不重打
        s = ledger.summary(led)
        self.assertEqual((s["n"], s["pending"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
