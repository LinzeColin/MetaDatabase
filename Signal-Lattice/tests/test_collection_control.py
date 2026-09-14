from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import LiveEngine, LiveStore
from signal_lattice.marketdata.base import CollectionBudgetExceeded


class CollectionControlTests(unittest.TestCase):
    @staticmethod
    def _settings(root: Path) -> LiveSettings:
        item = default_universe()[0]
        return LiveSettings(
            state_dir=root / "state", web_dir=root, host="127.0.0.1", port=0, loop_seconds=60,
            quote_max_age_seconds=180, bar_max_age_days=7, public_url="http://example.test",
            sina_quote_url="http://unused/", sina_us_kline_url="http://unused/us/{symbol}",
            sina_cn_kline_url="http://unused/cn/{symbol}", tencent_quote_url="http://unused/",
            tencent_kline_url="http://unused/{kind}/{symbol}", eastmoney_fund_url="http://unused/{code}",
            universe=[item],
        )

    def test_runtime_report_exposes_actual_provider_request_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            now = datetime(2026, 9, 14, 1, tzinfo=timezone.utc)
            engine = LiveEngine(self._settings(Path(temporary)))

            class Gateway:
                last_bar_quality = {}

                def fetch(self, instruments):
                    engine.store.record_provider_request("sina_quote", now)
                    return {}, {}, []

            engine.gateway = Gateway()
            report = engine.run_once(now)

            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            accounting = report["collection_request_accounting"]
            self.assertEqual(accounting["daily_provider_request_count"], 1)
            self.assertEqual(accounting["provider_request_counts"]["sina_quote"], {"total": 1, "daily": 1})

    def test_provider_counts_persist_by_provider_and_are_reportable(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = LiveStore(Path(temporary))
            now = datetime(2026, 9, 14, 1, tzinfo=timezone.utc)

            self.assertTrue(store.begin_collection_round(now)["allowed"])
            store.record_provider_request("sina_quote", now)
            store.record_provider_request("sina_quote", now)
            store.record_provider_request("tencent_daily", now)
            store.finish_collection_round(now, succeeded=True)

            accounting = store.collection_accounting(now)
            persisted = (Path(temporary) / "collection_accounting.json").read_text(encoding="utf-8")
            self.assertIn('"sina_quote"', persisted)
            self.assertEqual(accounting["daily_provider_request_count"], 3)
            self.assertEqual(accounting["total_provider_request_count"], 3)
            self.assertEqual(accounting["provider_request_counts"]["sina_quote"], {"total": 2, "daily": 2})
            self.assertEqual(accounting["provider_request_counts"]["tencent_daily"], {"total": 1, "daily": 1})
            self.assertEqual(accounting["active_round_request_count"], 0)

    def test_round_and_daily_budgets_prevent_another_http_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = LiveStore(Path(temporary))
            now = datetime(2026, 9, 14, 1, tzinfo=timezone.utc)

            with patch("signal_lattice.live_runtime.MAX_PROVIDER_REQUESTS_PER_ROUND", 2):
                self.assertTrue(store.begin_collection_round(now)["allowed"])
                store.record_provider_request("sina_quote", now)
                store.record_provider_request("sina_quote", now)
                with self.assertRaisesRegex(CollectionBudgetExceeded, "COLLECTION_ROUND_REQUEST_BUDGET_EXHAUSTED"):
                    store.record_provider_request("sina_quote", now)

            accounting = store.collection_accounting(now)
            self.assertEqual(accounting["daily_provider_request_count"], 2)
            self.assertEqual(accounting["status"], "ROUND_REQUEST_BUDGET_EXHAUSTED")

            with patch("signal_lattice.live_runtime.MAX_PROVIDER_REQUESTS_PER_DAY", 2):
                self.assertFalse(store.begin_collection_round(now)["allowed"])
                self.assertEqual(store.collection_accounting(now)["status"], "DAILY_REQUEST_BUDGET_EXHAUSTED")

    def test_three_consecutive_failed_rounds_back_off_exponentially(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = LiveStore(Path(temporary))
            first = datetime(2026, 9, 14, 1, tzinfo=timezone.utc)
            for offset in range(3):
                now = first + timedelta(seconds=offset * 60)
                self.assertTrue(store.begin_collection_round(now)["allowed"])
                store.finish_collection_round(now, succeeded=False)

            accounting = store.collection_accounting(first + timedelta(seconds=120))
            self.assertEqual(accounting["consecutive_failure_count"], 3)
            self.assertEqual(accounting["status"], "BACKING_OFF")
            self.assertEqual(accounting["next_attempt_at"], "2026-09-14T01:03:00+00:00")
            blocked = store.begin_collection_round(first + timedelta(seconds=150))
            self.assertFalse(blocked["allowed"])
            self.assertEqual(blocked["reason"], "COLLECTION_BACKING_OFF")
            self.assertEqual(store.collection_accounting(first + timedelta(seconds=150))["total_round_count"], 3)


if __name__ == "__main__":
    unittest.main()
