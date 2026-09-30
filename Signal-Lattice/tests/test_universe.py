"""候选池硬门：市值 3 亿～100 亿美元、价格 ≥3、20 日成交额中位数 ≥300 万；ETF 与超大盘必须为 0。"""

from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from signal_lattice import universe as U
from signal_lattice.marketdata.base import MarketDataError
from signal_lattice.marketdata.models import Bar

NASDAQ = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAAP|Pacer Barings CLO Market Flex ETF|G|N|N|100|Y|N
ACME|Acme Robotics, Inc. - Common Stock|Q|N|N|100|N|N
ADSX|Foo Holdings - American Depositary Shares, each representing two ordinary shares|S|N|N|100|N|N
SPCA|Foo Acquisition Corp. - Class A Ordinary Shares|G|N|N|100|N|N
SPCB|Bar Acquisition II Corp - Class A Ordinary Shares|G|N|N|100|N|N
WRNT|Foo Acquisition Corp. - Warrants|G|N|N|100|N|N
WRTX|Baz Corp - Warrants each exercisable for one share|G|N|N|100|N|N
PREF|Baz Corp - 7% Series A Cumulative Preferred Stock|G|N|N|100|N|N
NTST|Nasdaq Test Stock|Q|Y|N|100|N|N
UNTS|Qux Corp - Units, each consisting of one share and one right|G|N|N|100|N|N
FUND|Nuveen Municipal Income Fund - Common Shares|G|N|N|100|N|N
NXSH|Some NextShares Fund|G|N|N|100|N|Y
File Creation Time: 0930202606:00|||||||
"""
OTHER = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRN|Barnwell Industries, Inc. Common Stock|A|BRN|N|100|N|BRN
IWM|iShares Russell 2000 ETF|P|IWM|Y|100|N|IWM
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
AAPL2|Big Corp Common Stock|N|AAPL2|N|100|N|AAPL2
BF.B|Brown Forman Inc Class B Common Stock|N|BF.B|N|100|N|BF.B
ABR$D|Arbor Realty 6.375% Series D Cumulative Redeemable Preferred Stock|N|ABRpD|N|100|N|ABR-D
OTHR|Cboe Listed Thing Common Stock|Z|OTHR|N|100|N|OTHR
TSTN|NYSE Test Stk Common Stock|N|TSTN|N|100|Y|TSTN
ZZZ|Zed Corp Common Stock|N|ZZZ|N|100|N|ZZZ
File Creation Time: 0930202606:00||||||
"""

NOW = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)  # 纽约 16:00，当日 Bar 视为已收盘


def make_bars(symbol, close=10.0, volume=500_000, n=25, last=date(2026, 9, 30)):
    rows = []
    for i in range(n):
        day = last - timedelta(days=n - 1 - i)
        rows.append(Bar(symbol, day, close, close, close, close, volume, "America/New_York", "t", NOW))
    return rows


def sec_row(cik, name="X Corp"):
    return {"cik": cik, "name": name, "ticker": "X", "exchange": "Nasdaq"}


def shares_rec(cik, shares, end="2026-08-01", concept="dei:EntityCommonStockSharesOutstanding"):
    return U.SharesRecord(cik, shares, end, "0000000000-26-000001", concept)


def quote(symbol, price, cap=None):
    return U.SinaQuote(symbol, price, cap, None, None)


def run(symbols_prices_shares, bars=None, sina_cap=None):
    """symbols_prices_shares: {symbol: (price, shares)}；返回 (entries, funnel)。"""
    listings, sec, shares, quotes = [], {}, {}, {}
    for i, (symbol, (price, sh)) in enumerate(symbols_prices_shares.items(), start=1):
        listings.append(U.Listing(symbol, symbol + " Common Stock", "Nasdaq"))
        sec[symbol] = sec_row(i, symbol)
        shares[i] = shares_rec(i, sh)
        quotes[symbol] = quote(symbol, price, (sina_cap or {}).get(symbol))
    fetch = (lambda listing: bars[listing.symbol]) if bars else (lambda listing: make_bars(listing.symbol))
    return U.select_universe(listings, sec, shares, quotes, fetch, NOW, workers=2)


class HardGateConstantsTests(unittest.TestCase):
    def test_gates_are_pinned(self):
        self.assertEqual(U.MIN_MARKET_CAP_USD, 300_000_000)
        self.assertEqual(U.MAX_MARKET_CAP_USD, 10_000_000_000)
        self.assertEqual(U.MIN_PRICE_USD, 3.0)
        self.assertEqual(U.MIN_MEDIAN_DOLLAR_VOLUME_USD, 3_000_000)
        self.assertEqual(U.DOLLAR_VOLUME_WINDOW_DAYS, 20)
        self.assertEqual(U.CAP_CROSSCHECK_TOLERANCE, 0.20)
        self.assertEqual(U.RULES["min_market_cap_usd"], 3e8)
        self.assertEqual(U.RULES["max_market_cap_usd"], 1e10)


class SymbolDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.result = U.parse_symbol_directories(NASDAQ, OTHER)
        self.kept = {l.symbol: l for l in self.result.listings}

    def test_only_common_stocks_survive(self):
        self.assertEqual(set(self.kept), {"ACME", "BRN", "AAPL2", "ZZZ"})

    def test_etfs_are_excluded_and_recorded(self):
        self.assertEqual(self.result.etf_symbols, {"AAAP", "IWM", "SPY", "NXSH"})
        for etf in self.result.etf_symbols:
            self.assertNotIn(etf, self.kept)

    def test_each_kind_of_non_common_security_is_rejected_for_the_right_reason(self):
        ex = self.result.excluded
        self.assertEqual(ex["TEST_ISSUE"], 2)
        self.assertEqual(ex["SYMBOL_SUFFIX"], 2)   # BF.B、ABR$D
        self.assertEqual(ex["EXCHANGE_NOT_NYSE_NASDAQ_AMEX"], 1)
        self.assertEqual(ex["DEPOSITARY"], 1)
        self.assertEqual(ex["SPAC"], 2)
        self.assertEqual(ex["WARRANT"], 2)
        self.assertEqual(ex["PREFERRED"], 1)
        self.assertEqual(ex["UNIT"], 1)
        self.assertEqual(ex["FUND"], 1)

    def test_exchange_mapping_and_tencent_suffix(self):
        self.assertEqual(self.kept["ACME"].exchange, "Nasdaq")
        self.assertEqual(self.kept["BRN"].exchange, "NYSE American")
        self.assertEqual(self.kept["ZZZ"].exchange, "NYSE")
        self.assertEqual({e: U.TENCENT_SUFFIX[e] for e in ("Nasdaq", "NYSE", "NYSE American")},
                         {"Nasdaq": "OQ", "NYSE": "N", "NYSE American": "AM"})

    def test_file_creation_time_is_recorded(self):
        self.assertEqual(self.result.file_times["nasdaqlisted"], "0930202606:00")


class MarketCapGateTests(unittest.TestCase):
    def test_cap_boundaries(self):
        entries, funnel = run({
            "LOW": (10.0, 29_999_999),      # 2.99999990e8 < 3e8
            "MIN": (10.0, 30_000_000),      # 恰好 3 亿：含
            "MAX": (10.0, 1_000_000_000),   # 恰好 100 亿：含
            "OVER": (10.0, 1_000_000_001),  # 超大盘
            "MID": (10.0, 200_000_000),
        })
        self.assertEqual([e["symbol"] for e in entries], ["MAX", "MID", "MIN"])
        self.assertEqual(funnel["CAP_BELOW_MIN"], 1)
        self.assertEqual(funnel["CAP_ABOVE_MAX"], 1)

    def test_market_cap_is_sec_shares_times_price_not_sina_cap(self):
        entries, _ = run({"AAA": (10.0, 50_000_000)}, sina_cap={"AAA": 999_999_999_999})
        self.assertEqual(entries[0]["market_cap_usd"], 500_000_000)
        self.assertEqual(entries[0]["sina_market_cap_usd"], 999_999_999_999)
        self.assertIn("SINA_CAP_MISMATCH", entries[0]["flags"])

    def test_sina_cap_within_tolerance_is_not_flagged(self):
        entries, _ = run({"AAA": (10.0, 50_000_000)}, sina_cap={"AAA": 590_000_000})  # 差 18%
        self.assertEqual(entries[0]["flags"], [])
        entries, _ = run({"AAA": (10.0, 50_000_000)}, sina_cap={"AAA": 610_000_000})  # 差 22%
        self.assertEqual(entries[0]["flags"], ["SINA_CAP_MISMATCH"])

    def test_price_floor(self):
        entries, funnel = run({"CHEAP": (2.99, 200_000_000), "OK": (3.0, 200_000_000)})
        self.assertEqual([e["symbol"] for e in entries], ["OK"])
        self.assertEqual(funnel["PRICE_BELOW_MIN"], 1)

    def test_missing_quote_or_shares_excludes(self):
        listings = [U.Listing("NOQ", "n", "Nasdaq"), U.Listing("NOS", "n", "Nasdaq")]
        sec = {"NOQ": sec_row(1), "NOS": sec_row(2)}
        entries, funnel = U.select_universe(listings, sec, {1: shares_rec(1, 5e7)}, {"NOS": quote("NOS", 10)},
                                            lambda l: make_bars(l.symbol), NOW)
        self.assertEqual(entries, [])
        self.assertEqual((funnel["NO_SINA_QUOTE"], funnel["NO_SEC_SHARES"]), (1, 1))

    def test_symbol_not_in_sec_is_dropped(self):
        entries, funnel = U.select_universe([U.Listing("GHOST", "g", "Nasdaq")], {}, {}, {}, lambda l: [], NOW)
        self.assertEqual((entries, funnel["NOT_IN_SEC_TICKERS"]), ([], 1))

    def test_stale_sec_shares_rejected(self):
        listings = [U.Listing("OLD", "o", "Nasdaq")]
        entries, funnel = U.select_universe(
            listings, {"OLD": sec_row(1)}, {1: shares_rec(1, 5e7, end="2025-01-01")}, {"OLD": quote("OLD", 10)},
            lambda l: make_bars(l.symbol), NOW)
        self.assertEqual((entries, funnel["SEC_SHARES_STALE"]), ([], 1))

    def test_fallback_shares_need_sina_confirmation(self):
        listings = [U.Listing("CLA", "c", "Nasdaq"), U.Listing("CLB", "c", "Nasdaq")]
        sec = {"CLA": sec_row(1), "CLB": sec_row(2)}
        gaap = "us-gaap:CommonStockSharesOutstanding"
        shares = {1: shares_rec(1, 5e7, concept=gaap), 2: shares_rec(2, 5e7, concept=gaap)}
        quotes = {"CLA": quote("CLA", 10, 5.1e8), "CLB": quote("CLB", 10, 5e9)}  # CLB：只有一个类别的股数
        entries, funnel = U.select_universe(listings, sec, shares, quotes, lambda l: make_bars(l.symbol), NOW)
        self.assertEqual([e["symbol"] for e in entries], ["CLA"])
        self.assertEqual(funnel["SHARES_FALLBACK_UNCONFIRMED"], 1)


class LiquidityGateTests(unittest.TestCase):
    def test_median_dollar_volume_threshold(self):
        # 10 美元 × 30 万股 = 300 万美元：恰好过线（含）
        entries, funnel = run({"EDGE": (10.0, 50_000_000), "THIN": (10.0, 50_000_000)},
                              bars={"EDGE": make_bars("EDGE", 10.0, 300_000), "THIN": make_bars("THIN", 10.0, 299_999)})
        self.assertEqual([e["symbol"] for e in entries], ["EDGE"])
        self.assertEqual(funnel["DOLLAR_VOLUME_BELOW_MIN"], 1)

    def test_median_not_mean(self):
        bars = make_bars("SPK", 10.0, 100_000)  # 每天 100 万美元
        bars[-1] = Bar("SPK", bars[-1].day, 10, 10, 10, 10, 500_000_000, "America/New_York", "t", NOW)  # 一天爆量
        entries, funnel = run({"SPK": (10.0, 50_000_000)}, bars={"SPK": bars})
        self.assertEqual(entries, [])
        self.assertEqual(funnel["DOLLAR_VOLUME_BELOW_MIN"], 1)

    def test_window_is_last_20_completed_bars(self):
        self.assertEqual(U.median_dollar_volume(make_bars("W", 10.0, 1_000_000, n=19)), None)
        old_thin = make_bars("W", 10.0, 1, n=5, last=date(2026, 8, 1)) + make_bars("W", 10.0, 1_000_000, n=20)
        self.assertEqual(U.median_dollar_volume(old_thin), 10_000_000)

    def test_intraday_partial_bar_is_dropped(self):
        intraday = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)  # 纽约 11:00，今天的 Bar 未收完
        bars = make_bars("P", 10.0, 500_000, n=22, last=date(2026, 9, 30))
        self.assertEqual(U.completed_bars(bars, intraday)[-1].day, date(2026, 9, 29))
        self.assertEqual(U.completed_bars(bars, NOW)[-1].day, date(2026, 9, 30))

    def test_missing_short_or_stale_bars_exclude(self):
        listings = [U.Listing(s, s, "Nasdaq") for s in ("NOB", "SHORT", "STALE")]
        sec = {s: sec_row(i) for i, s in enumerate(("NOB", "SHORT", "STALE"), 1)}
        shares = {i: shares_rec(i, 5e7) for i in (1, 2, 3)}
        quotes = {s: quote(s, 10) for s in ("NOB", "SHORT", "STALE")}

        def fetch(listing):
            if listing.symbol == "NOB":
                raise MarketDataError("nope")
            if listing.symbol == "SHORT":
                return make_bars("SHORT", n=10)
            return make_bars("STALE", last=date(2026, 9, 1))

        entries, funnel = U.select_universe(listings, sec, shares, quotes, fetch, NOW)
        self.assertEqual(entries, [])
        self.assertEqual((funnel["NO_BARS"], funnel["BARS_INSUFFICIENT"], funnel["BARS_STALE"]), (1, 1, 1))


class SnapshotTests(unittest.TestCase):
    def build(self, extra_symbol=False):
        prices = {"AAA": (10.0, 50_000_000), "BBB": (20.0, 100_000_000)}
        if extra_symbol:
            prices["CCC"] = (5.0, 90_000_000)
        entries, funnel = run(prices)
        return U.build_snapshot(entries, funnel, {"quotes": "sina"}, NOW), entries

    def test_snapshot_verifies_with_zero_etf_and_zero_out_of_range(self):
        snapshot, _ = self.build()
        report = U.verify_snapshot(snapshot, etf_symbols={"IWM", "SPY"})
        self.assertEqual((report["etf_count"], report["mega_cap_count"], report["below_min_cap_count"],
                          report["below_min_price_count"], report["below_min_liquidity_count"]), (0, 0, 0, 0, 0))
        self.assertEqual(report["total"], 2)
        self.assertEqual(sum(report["buckets"].values()), 2)

    def test_verify_recomputes_and_catches_a_bad_entry(self):
        snapshot, _ = self.build()
        snapshot["entries"].append({**snapshot["entries"][0], "symbol": "SPY", "shares_outstanding": 9e9,
                                    "market_cap_usd": 1.0})  # 派生值写假也逃不掉
        report = U.verify_snapshot(snapshot, etf_symbols={"SPY"})
        self.assertEqual((report["etf_count"], report["mega_cap_count"]), (1, 1))

    def test_entries_carry_required_fields(self):
        snapshot, entries = self.build()
        for key in ("symbol", "cik", "market_cap_usd", "price_usd", "median_dollar_volume_20d_usd",
                    "price_source_time", "shares_as_of", "shares_accession", "last_bar_day"):
            self.assertIn(key, entries[0])

    def test_hash_is_content_addressed_and_stable(self):
        a, _ = self.build()
        b, _ = self.build()
        c, _ = self.build(extra_symbol=True)
        self.assertEqual(a["content_sha256"], b["content_sha256"])
        self.assertNotEqual(a["content_sha256"], c["content_sha256"])
        later = U.build_snapshot(a["entries"], Counter(a["funnel"]), {"quotes": "sina"}, NOW + timedelta(hours=3))
        self.assertEqual(later["content_sha256"], a["content_sha256"])  # 生成时刻不进 hash

    def test_write_is_immutable(self):
        snapshot, _ = self.build()
        with tempfile.TemporaryDirectory() as tmp:
            path = U.write_snapshot(snapshot, Path(tmp))
            self.assertRegex(path.name, r"^universe-2026-09-30-[0-9a-f]{12}\.json$")
            self.assertEqual(json.loads(path.read_text("utf-8"))["content_sha256"], snapshot["content_sha256"])
            before = path.read_bytes()
            self.assertEqual(U.write_snapshot(snapshot, Path(tmp)), path)  # 同内容重写是空操作
            self.assertEqual(path.read_bytes(), before)
            path.write_text(json.dumps({**snapshot, "content_sha256": "0" * 64}), "utf-8")
            with self.assertRaises(FileExistsError):
                U.write_snapshot(snapshot, Path(tmp))  # 已有同名但内容不同：拒绝覆盖


class SinaParseTests(unittest.TestCase):
    def test_parse_gb_fields(self):
        fields = ["CorVel Corp", "74.4700", "0.85", "2026-09-30 15:59:38", "0.63", "73.38", "74.49", "73.33", "79.43",
                  "44.83", "129936", "215203", "3761969042", "2.15", "34.64", "0", "0", "0", "0", "50516571"]
        raw = ('var hq_str_gb_crvl="%s";\nvar hq_str_gb_brk.b="";\nvar hq_str_gb_bad="Bad,0,0";\n' % ",".join(fields)).encode("gbk")
        quotes = U.parse_sina_quotes(raw)
        self.assertEqual(set(quotes), {"CRVL"})
        q = quotes["CRVL"]
        self.assertEqual((q.price, q.market_cap, q.shares), (74.47, 3761969042.0, 50516571.0))
        self.assertEqual(q.source_time.isoformat(), "2026-09-30T15:59:38+08:00")

    def test_instant_periods_walk_back_across_year(self):
        self.assertEqual(U.recent_instant_periods(date(2026, 2, 10), 3), ["CY2026Q1I", "CY2025Q4I", "CY2025Q3I"])


if __name__ == "__main__":
    unittest.main()
