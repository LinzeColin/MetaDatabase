from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from signal_lattice_v19.market import FixtureProvider, MoomooReadOnlyProvider
from signal_lattice_v19.models import Candidate


ROOT = Path(__file__).resolve().parents[1]


def candidate() -> Candidate:
    return Candidate(
        provider_code="AU.SPY",
        public_code="SPY",
        name="SPY",
        market="AU",
        currency="AUD",
        bucket_id="us_broad",
        bucket_name="美国宽基",
        risk_tier=1,
    )


class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        for index, row in enumerate(self.rows):
            yield index, row


class _Quote:
    calls: list[tuple[str, str]] = []

    def __init__(self, **_):
        pass

    def get_stock_basicinfo(self, market, stock_type=None):
        self.calls.append((market, stock_type))
        suffix = "ETF" if stock_type == "ETF" else "STOCK"
        return 0, _Frame([{"code": f"{market}.{suffix}", "name": f"{market} {suffix}"}])

    def close(self):
        pass


class _Market:
    AU = "AU"
    US = "US"
    HK = "HK"


class _SecurityType:
    ETF = "ETF"
    STOCK = "STOCK"


class MarketProviderTests(unittest.TestCase):
    def test_fixture_retains_source_as_of_separately_from_observed_at(self):
        provider = FixtureProvider(ROOT / "fixtures")
        observed_at = datetime(2026, 8, 14, 0, 0, 1, tzinfo=timezone.utc)

        snapshot = provider.snapshot([candidate()], observed_at, include_history=True)

        self.assertEqual(snapshot[0].quote_time, "2026-08-13T16:00:00+00:00")
        self.assertEqual(snapshot[0].metadata["source_as_of"], "2026-08-13T16:00:00+00:00")
        self.assertEqual(snapshot[0].metadata["observed_at"], "2026-08-14T00:00:01+00:00")

    def test_moomoo_catalog_requests_both_etfs_and_stocks(self):
        _Quote.calls = []
        provider = MoomooReadOnlyProvider()
        sdk = (_Quote, 0, object(), object(), _Market, _SecurityType)

        with patch.object(MoomooReadOnlyProvider, "_sdk", return_value=sdk):
            catalog = provider.catalog()

        self.assertEqual(len(catalog), 6)
        self.assertEqual({row["metadata"]["asset_class"] for row in catalog}, {"ETF", "STOCK"})
        self.assertEqual({security_type for _, security_type in _Quote.calls}, {"ETF", "STOCK"})


if __name__ == "__main__":
    unittest.main()
