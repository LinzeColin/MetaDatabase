"""四个真实 provider 的解析与 V2 诚实门。网络调用在本测试中一律替身化。"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import LiveEngine, MarketGateway
from signal_lattice.marketdata.base import DiskCache, MarketDataError
from signal_lattice.marketdata.eastmoney import EastMoneyFundProvider
from signal_lattice.marketdata.models import Bar, BarQualityIssue, Quote
from signal_lattice.marketdata.sina import SinaKlineProvider, SinaQuoteProvider
from signal_lattice.marketdata.tencent import TencentKlineProvider, TencentQuoteProvider


class SequenceClient:
    """夹具客户端：每次 provider 拉取都留下精确调用次数。"""

    def __init__(self, payloads: list[bytes]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, object]] = []

    def get(self, url: str, headers=None, *, provider=None) -> bytes:
        self.calls.append((url, headers, provider))
        return self.payloads.pop(0)


class ProviderParsingTests(unittest.TestCase):
    def setUp(self):
        self.items = default_universe()

    def test_sina_gbk_uses_market_specific_live_price_fields(self):
        raw = (
            'hq_str_hk00700="TENCENT,腾讯控股,419.400,425.600,430.800,419.400,428.400,2.800,0.658,...,2026/09/11,16:09"\n'
            'hq_str_hk02800="TRACKER FUND,盈富基金,25.360,25.580,25.480,25.200,25.420,-0.160,-0.625,...,2026/09/12,09:45:58,..."\n'
            'hq_str_sh600000="浦发银行,9.350,9.350,9.260,9.350,9.220,9.250,9.260,65327293,...,2026-09-12,09:45:58,..."\n'
            'hq_str_gb_spy="SPDR标普500 ETF,764.2900,0.85,2026-09-12 09:45:58,6.4600,764.7200,..."\n'
        ).encode("gbk")
        quotes = SinaQuoteProvider.parse(raw, self.items, datetime(2026, 9, 12, tzinfo=timezone.utc))
        self.assertEqual(quotes["usSPY"].price, 764.29)
        self.assertEqual(quotes["sh600000"].price, 9.260)
        self.assertEqual(quotes["hk00700"].price, 428.400)
        self.assertEqual(quotes["hk02800"].price, 25.420)
        self.assertTrue(all(quote.source_time is not None for quote in quotes.values()))
        self.assertEqual(quotes["usSPY"].source_time.isoformat(), "2026-09-12T09:45:58")
        self.assertEqual(quotes["sh600000"].source_time.isoformat(), "2026-09-12T09:45:58")
        self.assertEqual(quotes["hk00700"].source_time.isoformat(), "2026-09-11T16:09:00")

    def test_tencent_quote_without_source_time_remains_unqualified(self):
        raw = 'v_hk00700="100~腾讯控股~00700~428.400~425.600~2.800~0.658~0~0~0.00~0.00";'.encode("gbk")

        quotes = TencentQuoteProvider.parse(raw, self.items)

        self.assertIsNone(quotes["hk00700"].source_time)

    def test_tencent_quote_strips_each_response_line(self):
        raw = (
            'v_sh000300="51~沪深300~000300~4568.630~4556.370~12.260~0.269~447446~2044000~0.00~0.00";\n'
            'v_sh600000="1~浦发银行~600000~9.260~9.350~-0.090~-0.963~65327293~604950000~0.00~0.00";\n'
            'v_sh510300="1~沪深300ETF~510300~4.038~4.020~0.018~0.448~164814810~664900000~0.00~0.00";\n'
            'v_hk02800="100~盈富基金~02800~25.420~25.580~-0.160~-0.625~0~0~0.00~0.00";\n'
            'v_hk00700="100~腾讯控股~00700~428.400~425.600~2.800~0.658~0~0~0.00~0.00";'
        ).encode("gbk")
        quotes = TencentQuoteProvider.parse(raw, self.items)
        self.assertEqual(set(quotes), {"sh000300", "sh600000", "sh510300", "hk02800", "hk00700"})
        self.assertEqual(quotes["sh600000"].price, 9.260)
        self.assertEqual(quotes["hk00700"].price, 428.400)
        self.assertTrue(all(quote.source_time is None for quote in quotes.values()))

    def test_sina_us_daily_jsonp_unwraps_strings_and_sorts(self):
        payload = (
            "/*<script>location.href='//sina.com';</script>*/var _=(["
            '{"d":"2026-09-10","o":"763.30","h":"765.13","l":"761.45","c":"762.82","v":"43211111","a":"32968000000"},'
            '{"d":"2026-09-11","o":"764.72","h":"766.38","l":"763.60","c":"764.29","v":"45512741","a":"34803000000"}'
            "]);"
        ).encode("utf-8")
        item = next(item for item in self.items if item.symbol == "usSPY")
        bars = SinaKlineProvider.parse(payload, item)
        self.assertEqual([bar.day.isoformat() for bar in bars], ["2026-09-10", "2026-09-11"])
        self.assertEqual(bars[-1].close, 764.29)
        self.assertIsInstance(bars[-1].open, float)
        self.assertIsInstance(bars[-1].volume, float)
        self.assertEqual(bars[-1].source, "sina_us_daily")

    def test_tencent_kline_falls_back_to_day_for_index(self):
        payload = b'{"code":0,"data":{"sh000300":{"day":[["2026-09-11","4556.370","4568.630","4575.000","4540.000","447446"],["2025-05-26","3800.000","3810.000","3820.000","3790.000","200000"]]}}}'
        item = next(item for item in self.items if item.symbol == "sh000300")
        bars = TencentKlineProvider.parse(payload, item)
        self.assertEqual([bar.day.isoformat() for bar in bars], ["2025-05-26", "2026-09-11"])
        self.assertEqual(bars[-1].close, 4568.630)
        self.assertEqual(bars[-1].source, "tencent_daily")

    def test_eastmoney_fund_net_worth(self):
        raw = b'var Data_netWorthTrend = [{"x":1726099200000,"y":1.23},{"x":1726185600000,"y":1.25}];'
        item = next(item for item in self.items if item.symbol == "fund110022")
        bars = EastMoneyFundProvider.parse(raw, item)
        self.assertEqual(bars[-1].close, 1.25)
        self.assertEqual(bars[-1].source, "eastmoney_fund_nav")

    def test_quote_parsers_reject_nan_and_infinity(self):
        sina = 'hq_str_gb_spy="SPDR,NaN,0,2026-09-12 09:45:58";'.encode("gbk")
        tencent = 'v_sh600000="1~浦发银行~600000~Infinity~9.350";'.encode("gbk")

        self.assertNotIn("usSPY", SinaQuoteProvider.parse(sina, self.items))
        self.assertNotIn("sh600000", TencentQuoteProvider.parse(tencent, self.items))

    def test_tencent_quote_non_gbk_response_is_market_data_error(self):
        with self.assertRaisesRegex(MarketDataError, "TENCENT_QUOTE_DECODE_FAILED"):
            TencentQuoteProvider.parse(b"\xff\xfe", self.items)

    def test_daily_parsers_drop_nonfinite_ohlcv_and_record_violations(self):
        sina = (
            "var _=(["
            '{"d":"2026-09-01","o":"NaN","h":"2","l":"1","c":"1","v":"1"},'
            '{"d":"2026-09-02","o":"1","h":"Infinity","l":"1","c":"1","v":"1"},'
            '{"d":"2026-09-03","o":"1","h":"2","l":"-Infinity","c":"1","v":"1"},'
            '{"d":"2026-09-04","o":"1","h":"2","l":"1","c":"NaN","v":"1"},'
            '{"d":"2026-09-05","o":"1","h":"2","l":"1","c":"1","v":"Infinity"},'
            '{"d":"2026-09-06","o":"1","h":"2","l":"1","c":"1","v":"1"},'
            '{"d":"2026-09-07","o":"2","h":"3","l":"1","c":"2","v":"1"}]);'
        ).encode("utf-8")
        tencent = (
            '{"code":0,"data":{"sh000300":{"day":['
            '["2026-09-01","NaN","1","2","1","1"],'
            '["2026-09-02","1","1","Infinity","1","1"],'
            '["2026-09-03","1","1","2","-Infinity","1"],'
            '["2026-09-04","1","NaN","2","1","1"],'
            '["2026-09-05","1","1","2","1","Infinity"],'
            '["2026-09-06","1","1","2","1","1"],'
            '["2026-09-07","2","2","3","1","1"]]}}}'
        ).encode("utf-8")
        eastmoney = (
            'var Data_netWorthTrend = ['
            '{"x":1726099200000,"y":NaN},'
            '{"x":1726185600000,"y":1.23},'
            '{"x":1726272000000,"y":1.25}];'
        ).encode("utf-8")

        us_spy = next(item for item in self.items if item.symbol == "usSPY")
        sh300 = next(item for item in self.items if item.symbol == "sh000300")
        fund = next(item for item in self.items if item.symbol == "fund110022")
        cases = [
            (SinaKlineProvider.parse, sina, us_spy, 5),
            (TencentKlineProvider.parse, tencent, sh300, 5),
            (EastMoneyFundProvider.parse, eastmoney, fund, 1),
        ]
        for parser, payload, instrument, expected_drops in cases:
            with self.subTest(provider=parser.__qualname__):
                issues: list[BarQualityIssue] = []
                bars = parser(payload, instrument, quality_issues=issues)
                self.assertEqual(len(bars), 2)
                self.assertEqual(len(issues), expected_drops)
                self.assertTrue(all(issue.violations for issue in issues))

    def test_daily_parsers_classify_structural_conversion_and_ohlcv_issues(self):
        sina = (
            'var _=(["row",{"d":"2026-09-01"},'
            '{"d":"2026-09-02","o":"bad","h":"2","l":"1","c":"1","v":"1"},'
            '{"d":"2026-09-03","o":"1","h":"2","l":"3","c":"1","v":"1"},'
            '{"d":"2026-09-04","o":"1","h":"2","l":"1","c":"1","v":"1"},'
            '{"d":"2026-09-05","o":"2","h":"3","l":"1","c":"2","v":"1"}]);'
        ).encode("utf-8")
        tencent = json.dumps({"code": 0, "data": {"sh000300": {"day": [
            ["too-short"],
            ["2026-09-02", "bad", "1", "2", "1", "1"],
            ["2026-09-03", "1", "3", "2", "1", "1"],
            ["2026-09-04", "1", "1", "2", "1", "1"],
            ["2026-09-05", "2", "2", "3", "1", "1"],
        ]}}}).encode("utf-8")
        eastmoney = (
            'var Data_netWorthTrend = ["row",{"x":"bad","y":1.2},'
            '{"x":1726099200000,"y":-1.2},{"x":1726185600000,"y":1.23},'
            '{"x":1726272000000,"y":1.25}];'
        ).encode("utf-8")
        cases = [
            (SinaKlineProvider.parse, sina, next(item for item in self.items if item.symbol == "usSPY")),
            (TencentKlineProvider.parse, tencent, next(item for item in self.items if item.symbol == "sh000300")),
            (EastMoneyFundProvider.parse, eastmoney, next(item for item in self.items if item.symbol == "fund110022")),
        ]
        for parser, payload, instrument in cases:
            with self.subTest(provider=parser.__qualname__):
                issues: list[BarQualityIssue] = []
                bars = parser(payload, instrument, quality_issues=issues)
                self.assertEqual(len(bars), 2)
                self.assertEqual(
                    {issue.issue_type for issue in issues},
                    {"STRUCTURAL", "CONVERSION", "OHLCV_VIOLATION"},
                )

    def test_bar_semantic_validator_rejects_incoherent_ohlcv(self):
        observed_at = datetime(2026, 9, 12, tzinfo=timezone.utc)
        baseline = dict(
            symbol="fixture", day=observed_at.date(), open=10.0, high=12.0, low=8.0,
            close=11.0, volume=1.0, exchange_timezone="UTC", source="fixture", observed_at=observed_at,
        )
        self.assertTrue(Bar(**baseline).has_valid_ohlcv())
        for changes in (
            {"low": 13.0},
            {"close": 13.0},
            {"close": 7.0},
            {"open": 0.0},
            {"volume": -1.0},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(Bar(**{**baseline, **changes}).has_valid_ohlcv())

    def test_daily_providers_drop_isolated_semantic_errors_from_new_and_cached_payloads(self):
        cases = [
            (
                "sina",
                next(item for item in self.items if item.symbol == "usSPY"),
                "sina_us_bars_usspy",
                lambda client, cache: SinaKlineProvider(client, cache, us_endpoint="https://fixture/{symbol}"),
                b'var _=([{"d":"2026-09-09","o":"1","h":"2","l":"1","c":"1","v":"1"},{"d":"2026-09-10","o":"1","h":"2","l":"3","c":"1","v":"1"},{"d":"2026-09-11","o":"2","h":"3","l":"1","c":"2","v":"1"}]);',
            ),
            (
                "tencent",
                next(item for item in self.items if item.symbol == "sh000300"),
                "bars_sh000300",
                lambda client, cache: TencentKlineProvider(client, cache, endpoint="https://fixture/{kind}/{symbol}"),
                b'{"code":0,"data":{"sh000300":{"day":[["2026-09-09","1","1","2","1","1"],["2026-09-10","1","3","2","1","-1"],["2026-09-11","2","2","3","1","1"]]}}}',
            ),
            (
                "eastmoney",
                next(item for item in self.items if item.symbol == "fund110022"),
                "fund_fund110022",
                lambda client, cache: EastMoneyFundProvider(client, cache, endpoint="https://fixture/{code}"),
                b'var Data_netWorthTrend = [{"x":1726012800000,"y":1.20},{"x":1726099200000,"y":-1.23},{"x":1726185600000,"y":1.25}];',
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for name, instrument, key, provider_factory, invalid_payload in cases:
                with self.subTest(provider=name):
                    new_cache = DiskCache(Path(directory) / (name + "-new"))
                    provider = provider_factory(SequenceClient([invalid_payload]), new_cache)
                    bars = provider.fetch(instrument)
                    self.assertEqual(len(bars), 2)
                    self.assertEqual(len(provider.last_quality_issues), 1)
                    self.assertEqual(new_cache.load(key, 60), invalid_payload)

                    cached_provider = provider_factory(SequenceClient([]), new_cache)
                    cached_bars = cached_provider.fetch(instrument)
                    self.assertEqual(len(cached_bars), 2)
                    self.assertEqual(len(cached_provider.last_quality_issues), 1)

    def test_daily_providers_refetch_once_after_invalid_cached_payload(self):
        cases = [
            (
                "sina",
                next(item for item in self.items if item.symbol == "usSPY"),
                "sina_us_bars_usspy",
                lambda client, cache: SinaKlineProvider(client, cache, us_endpoint="https://fixture/{symbol}"),
                b'var _=([{"d":"2026-09-10","o":"1","h":"2","l":"1","c":"1","v":"1"},{"d":"2026-09-11","o":"2","h":"3","l":"1","c":"2","v":"1"}]);',
            ),
            (
                "tencent",
                next(item for item in self.items if item.symbol == "sh000300"),
                "bars_sh000300",
                lambda client, cache: TencentKlineProvider(client, cache, endpoint="https://fixture/{kind}/{symbol}"),
                b'{"code":0,"data":{"sh000300":{"day":[["2026-09-10","1","1","2","1","1"],["2026-09-11","2","2","3","1","1"]]}}}',
            ),
            (
                "eastmoney",
                next(item for item in self.items if item.symbol == "fund110022"),
                "fund_fund110022",
                lambda client, cache: EastMoneyFundProvider(client, cache, endpoint="https://fixture/{code}"),
                b'var Data_netWorthTrend = [{"x":1726099200000,"y":1.23},{"x":1726185600000,"y":1.25}];',
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for name, instrument, key, provider_factory, valid_payload in cases:
                with self.subTest(provider=name):
                    cache = DiskCache(Path(directory) / name)
                    cache.save(key, b"<html>temporary upstream response</html>")
                    client = SequenceClient([valid_payload])
                    bars = provider_factory(client, cache).fetch(instrument)

                    self.assertEqual(len(bars), 2)
                    self.assertEqual(len(client.calls), 1)
                    self.assertEqual(cache.load(key, 60), valid_payload)

    def test_daily_providers_only_cache_payloads_that_parse(self):
        cases = [
            (
                "sina",
                next(item for item in self.items if item.symbol == "usSPY"),
                "sina_us_bars_usspy",
                lambda client, cache: SinaKlineProvider(client, cache, us_endpoint="https://fixture/{symbol}"),
            ),
            (
                "tencent",
                next(item for item in self.items if item.symbol == "sh000300"),
                "bars_sh000300",
                lambda client, cache: TencentKlineProvider(client, cache, endpoint="https://fixture/{kind}/{symbol}"),
            ),
            (
                "eastmoney",
                next(item for item in self.items if item.symbol == "fund110022"),
                "fund_fund110022",
                lambda client, cache: EastMoneyFundProvider(client, cache, endpoint="https://fixture/{code}"),
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for name, instrument, key, provider_factory in cases:
                with self.subTest(provider=name):
                    cache = DiskCache(Path(directory) / name)
                    client = SequenceClient([b"<html>HTTP 200 anti-bot page</html>"])

                    with self.assertRaises(MarketDataError):
                        provider_factory(client, cache).fetch(instrument)

                    self.assertEqual(len(client.calls), 1)
                    self.assertIsNone(cache.load(key, 60))


class HonestFreshnessGateTests(unittest.TestCase):
    def _settings(self, root: Path) -> LiveSettings:
        return LiveSettings(
            state_dir=root / "state", web_dir=root, host="127.0.0.1", port=0, loop_seconds=60,
            quote_max_age_seconds=180, bar_max_age_days=7, public_url="http://example.test",
            sina_quote_url="http://unused/", sina_us_kline_url="http://unused/us/{symbol}",
            sina_cn_kline_url="http://unused/cn/{symbol}", tencent_quote_url="http://unused/",
            tencent_kline_url="http://unused/{kind}/{symbol}",
            eastmoney_fund_url="http://unused/{code}", universe=default_universe(),
        )

    @staticmethod
    def _valid_bars(item, end_day, count: int, observed_at: datetime):
        days = []
        cursor = end_day
        while len(days) < count:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor -= timedelta(days=1)
        return [
            Bar(item.symbol, day, 1, 1, 1, 1, 1, item.timezone, "fixture", observed_at)
            for day in reversed(days)
        ]

    def test_distant_single_invalid_bar_is_dropped_reported_and_does_not_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            exchange_day = now.astimezone(ZoneInfo(us_spy.timezone)).date()
            bars = {"usSPY": self._valid_bars(us_spy, exchange_day, 300, now)}
            issue = BarQualityIssue(
                "usSPY", datetime(2015, 3, 30).date(), "sina_us_daily", ("LOW_ABOVE_OPEN_OR_CLOSE",),
            )
            quality = engine._bar_quality_report(bars, {"usSPY": [issue]})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(findings, [])
            self.assertEqual(quality["usSPY"]["status"], "DROPPED_INVALID_BARS")
            self.assertEqual(quality["usSPY"]["dropped_invalid_bar_count"], 1)
            self.assertEqual(quality["usSPY"]["samples"][0]["day"], "2015-03-30")
            self.assertEqual(quality["usSPY"]["samples"][0]["violations"], ["LOW_ABOVE_OPEN_OR_CLOSE"])

    def test_recent_invalid_bar_blocks_its_symbol(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            exchange_day = now.astimezone(ZoneInfo(us_spy.timezone)).date()
            bars = {"usSPY": self._valid_bars(us_spy, exchange_day - timedelta(days=1), 300, now)}
            quality = engine._bar_quality_report(bars, {"usSPY": [BarQualityIssue(
                "usSPY", exchange_day, "sina_us_daily", ("LOW_ABOVE_OPEN_OR_CLOSE",),
            )]})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertIn("BAR_INVALID_OHLCV_RECENT_DECISION_WINDOW:usSPY", findings)
            self.assertEqual(quality["usSPY"]["status"], "BLOCKED")

    def test_excessive_invalid_bar_count_blocks_its_symbol(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            exchange_day = now.astimezone(ZoneInfo(us_spy.timezone)).date()
            bars = {"usSPY": self._valid_bars(us_spy, exchange_day, 1_000, now)}
            issues = [BarQualityIssue(
                "usSPY", datetime(2010, 1, offset + 1).date(), "sina_us_daily", ("VOLUME_NEGATIVE",),
            ) for offset in range(4)]
            quality = engine._bar_quality_report(bars, {"usSPY": issues})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertIn("BAR_INVALID_OHLCV_COUNT_THRESHOLD:usSPY", findings)
            self.assertNotIn("BAR_INVALID_OHLCV_RATIO_THRESHOLD:usSPY", findings)

    def test_structural_rows_count_toward_the_same_quality_thresholds(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            exchange_day = now.astimezone(ZoneInfo(us_spy.timezone)).date()
            bars = {"usSPY": self._valid_bars(us_spy, exchange_day, 1_000, now)}
            issues = [
                BarQualityIssue(
                    "usSPY", None, "sina_us_daily", ("ROW_NOT_OBJECT",), "STRUCTURAL",
                )
                for _ in range(4)
            ]
            quality = engine._bar_quality_report(bars, {"usSPY": issues})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(quality["usSPY"]["issue_counts_by_type"], {"STRUCTURAL": 4})
            self.assertEqual(quality["usSPY"]["samples"][0]["day"], None)
            self.assertIn("BAR_INVALID_OHLCV_COUNT_THRESHOLD:usSPY", findings)
            self.assertIn("BAR_INVALID_OHLCV_RECENT_DECISION_WINDOW:usSPY", findings)

    def test_only_rejected_structural_rows_remain_auditable_and_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            issues = [
                BarQualityIssue("usSPY", None, "sina_us_daily", ("ROW_NOT_OBJECT",), "STRUCTURAL"),
                BarQualityIssue("usSPY", None, "sina_us_daily", ("FIELD_CONVERSION_FAILED",), "CONVERSION"),
            ]

            quality = engine._bar_quality_report({}, {"usSPY": issues})
            findings = engine._validate(now, {}, {}, [], quality)

            self.assertEqual(quality["usSPY"]["accepted_bar_count"], 0)
            self.assertEqual(quality["usSPY"]["dropped_invalid_bar_ratio"], 1.0)
            self.assertEqual(
                quality["usSPY"]["issue_counts_by_type"],
                {"CONVERSION": 1, "STRUCTURAL": 1},
            )
            self.assertIn("BAR_MISSING:usSPY", findings)
            self.assertIn("BAR_INVALID_OHLCV_NO_ACCEPTED_BARS:usSPY", findings)

    def test_spring_festival_six_business_day_gap_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            csi_300 = next(item for item in settings.universe if item.symbol == "sh000300")
            settings = replace(settings, universe=[csi_300])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            complete = self._valid_bars(csi_300, now.astimezone(ZoneInfo(csi_300.timezone)).date(), 1_000, now)
            spring_festival_gap = {
                datetime(2026, 2, day).date()
                for day in (16, 17, 18, 19, 20, 23)
            }
            bars = {csi_300.symbol: [bar for bar in complete if bar.day not in spring_festival_gap]}
            quality = engine._bar_quality_report(bars, {})
            quotes = {csi_300.symbol: Quote(csi_300.symbol, 1.0, "CNY", csi_300.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(quality[csi_300.symbol]["status"], "ACCEPTED")
            self.assertEqual(quality[csi_300.symbol]["effective_start_day"], complete[0].day.isoformat())
            self.assertEqual(quality[csi_300.symbol]["trimmed_bar_count"], 0)
            self.assertIsNone(quality[csi_300.symbol]["trim_reason"])
            self.assertEqual(findings, [])

    def test_distant_1646_business_day_gap_trims_without_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            end_day = now.astimezone(ZoneInfo(us_spy.timezone)).date()
            complete = self._valid_bars(us_spy, end_day, 4_000, now)
            bars = {"usSPY": complete[:500] + complete[2_146:]}
            quality = engine._bar_quality_report(bars, {})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(quality["usSPY"]["status"], "TRIMMED_HISTORICAL_SEGMENT")
            self.assertEqual(quality["usSPY"]["effective_start_day"], complete[2_146].day.isoformat())
            self.assertEqual(quality["usSPY"]["trimmed_bar_count"], 500)
            self.assertEqual(
                quality["usSPY"]["trim_reason"],
                "HISTORICAL_GAP_%s_TO_%s" % (complete[499].day.isoformat(), complete[2_146].day.isoformat()),
            )
            self.assertEqual(quality["usSPY"]["trim_gap_business_days"], 1_646)
            self.assertEqual(findings, [])

    def test_trimmed_segment_without_required_walk_forward_windows_blocks_with_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            complete = self._valid_bars(us_spy, now.astimezone(ZoneInfo(us_spy.timezone)).date(), 500, now)
            bars = {"usSPY": complete[:50] + complete[68:]}
            quality = engine._bar_quality_report(bars, {})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(quality["usSPY"]["effective_bar_count"], 432)
            self.assertEqual(quality["usSPY"]["status"], "BLOCKED")
            self.assertEqual(quality["usSPY"]["available_complete_walk_forward_windows"], 0)
            self.assertEqual(quality["usSPY"]["required_complete_walk_forward_windows"], 2)
            self.assertEqual(len(findings), 1)
            self.assertIn("可用段 432 条 / 需要 2 个完整 walk-forward 窗口（当前 0）", findings[0])

    def test_four_business_day_gap_keeps_full_history_usable(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            complete = self._valid_bars(us_spy, now.astimezone(ZoneInfo(us_spy.timezone)).date(), 1_000, now)
            bars = {"usSPY": complete[:200] + complete[204:]}
            quality = engine._bar_quality_report(bars, {})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(quality["usSPY"]["status"], "ACCEPTED")
            self.assertEqual(quality["usSPY"]["effective_start_day"], complete[0].day.isoformat())
            self.assertEqual(quality["usSPY"]["trimmed_bar_count"], 0)
            self.assertIsNone(quality["usSPY"]["trim_reason"])
            self.assertEqual(findings, [])

    def test_eighteen_business_day_gap_trims_and_reports_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            complete = self._valid_bars(us_spy, now.astimezone(ZoneInfo(us_spy.timezone)).date(), 1_800, now)
            bars = {"usSPY": complete[:150] + complete[168:]}
            quality = engine._bar_quality_report(bars, {})
            quotes = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)}

            findings = engine._validate(now, quotes, bars, [], quality)

            self.assertEqual(quality["usSPY"]["status"], "TRIMMED_HISTORICAL_SEGMENT")
            self.assertEqual(quality["usSPY"]["effective_start_day"], complete[168].day.isoformat())
            self.assertEqual(quality["usSPY"]["trimmed_bar_count"], 150)
            self.assertEqual(quality["usSPY"]["trim_gap_business_days"], 18)
            self.assertEqual(
                quality["usSPY"]["trim_reason"],
                "HISTORICAL_GAP_%s_TO_%s" % (complete[149].day.isoformat(), complete[168].day.isoformat()),
            )
            self.assertEqual(findings, [])

    def test_gateway_keeps_timestamped_sina_primary_over_tencent_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            gateway = MarketGateway(replace(settings, universe=[hk]))
            observed_at = datetime(2026, 9, 11, 8, tzinfo=timezone.utc)

            class Sina:
                def fetch(self, instruments):
                    return {"hk00700": Quote("hk00700", 411.0, "HKD", hk.timezone, "sina_quote", datetime(2026, 9, 11, 16, 9), observed_at)}

            class Tencent:
                calls = 0

                def fetch(self, instruments):
                    self.calls += 1
                    raise AssertionError("timestamped primary must prevent backup fetch")

            class Bars:
                last_quality_issues: list[BarQualityIssue] = []

                def fetch(self, instrument):
                    return [Bar("hk00700", datetime(2026, 9, 11).date(), 1, 1, 1, 1, 1, hk.timezone, "fixture", observed_at)]

            gateway.sina = Sina()
            gateway.tencent_quote = Tencent()
            gateway.tencent_bars = Bars()
            quotes, _bars, errors = gateway.fetch([hk])

            self.assertEqual(errors, [])
            self.assertEqual(quotes["hk00700"].source, "sina_quote")
            self.assertEqual(gateway.tencent_quote.calls, 0)

    def test_stale_bar_is_system_blocked_without_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            now = datetime.now(timezone.utc)
            class Gateway:
                def fetch(self, instruments):
                    quotes = {item.symbol: Quote(item.symbol, 1.0, "USD", item.timezone, "test", now, now)
                              for item in instruments if item.realtime_quote}
                    bars = {item.symbol: [Bar(item.symbol, (now - timedelta(days=40)).date(), 1, 1, 1, 1, 1, item.timezone, "test", now)]
                            for item in instruments}
                    return quotes, bars, []
            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            report = engine.run_once()
            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            self.assertIsNone(report["decision"]["action"])
            self.assertEqual(report["message"], "数据链路不完整，不出结论")
            self.assertTrue(any(item.startswith("BAR_STALE:") for item in report["freshness_findings"]))

    def test_future_bar_is_system_blocked_without_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            now = datetime.now(timezone.utc)

            class Gateway:
                def fetch(self, instruments):
                    quotes = {
                        item.symbol: Quote(item.symbol, 1.0, "USD", item.timezone, "test", now, now)
                        for item in instruments if item.realtime_quote
                    }
                    bars = {
                        item.symbol: [
                            Bar(
                                item.symbol,
                                now.astimezone(ZoneInfo(item.timezone)).date() + timedelta(days=30),
                                1, 1, 1, 1, 1, item.timezone, "test", now,
                            ),
                            Bar(
                                item.symbol,
                                now.astimezone(ZoneInfo(item.timezone)).date(),
                                1, 1, 1, 1, 1, item.timezone, "test", now,
                            ),
                        ]
                        for item in instruments
                    }
                    return quotes, bars, []

            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            report = engine.run_once()

            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            self.assertIsNone(report["decision"]["action"])
            self.assertTrue(any(item.startswith("BAR_FUTURE_DATE:usSPY:") for item in report["freshness_findings"]))

    def test_future_bar_uses_each_instrument_exchange_day(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            sh300 = next(item for item in settings.universe if item.symbol == "sh000300")
            settings = replace(settings, universe=[us_spy, sh300])
            now = datetime(2026, 1, 2, 1, tzinfo=timezone.utc)
            engine = LiveEngine(settings)
            quotes = {
                item.symbol: Quote(item.symbol, 1.0, "USD", item.timezone, "test", now, now)
                for item in settings.universe
            }
            bars = {
                "usSPY": [Bar("usSPY", datetime(2026, 1, 2).date(), 1, 1, 1, 1, 1, us_spy.timezone, "test", now)],
                "sh000300": [Bar("sh000300", datetime(2026, 1, 2).date(), 1, 1, 1, 1, 1, sh300.timezone, "test", now)],
            }

            findings = engine._validate(now, quotes, bars, [])

            self.assertIn("BAR_FUTURE_DATE:usSPY:2026-01-02:2026-01-01", findings)
            self.assertNotIn("BAR_FUTURE_DATE:sh000300:2026-01-02:2026-01-02", findings)

    def test_future_quote_source_time_is_system_blocked_by_exchange_day(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            now = datetime(2026, 1, 2, 1, tzinfo=timezone.utc)
            engine = LiveEngine(settings)
            quotes = {
                "usSPY": Quote(
                    "usSPY", 1.0, "USD", us_spy.timezone, "test",
                    datetime(2026, 1, 2, 9, 30), now,
                )
            }
            bars = {
                "usSPY": [Bar(
                    "usSPY", datetime(2026, 1, 1).date(), 1, 1, 1, 1, 1,
                    us_spy.timezone, "test", now,
                )]
            }

            findings = engine._validate(now, quotes, bars, [])

            self.assertTrue(any(item.startswith("QUOTE_SOURCE_CLOCK_AHEAD:usSPY:") for item in findings))

    def test_future_bars_from_new_and_cached_daily_provider_paths_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            items = default_universe()
            cases = [
                (
                    "sina",
                    next(item for item in items if item.symbol == "usSPY"),
                    "sina_us_bars_usspy",
                    lambda client, cache: SinaKlineProvider(client, cache, us_endpoint="https://fixture/{symbol}"),
                    lambda first, second: (
                        "var _=(["
                        f'{{"d":"{first}","o":"1","h":"2","l":"1","c":"1","v":"1"}},'
                        f'{{"d":"{second}","o":"2","h":"3","l":"1","c":"2","v":"1"}}]);'
                    ).encode("utf-8"),
                ),
                (
                    "tencent",
                    next(item for item in items if item.symbol == "sh000300"),
                    "bars_sh000300",
                    lambda client, cache: TencentKlineProvider(client, cache, endpoint="https://fixture/{kind}/{symbol}"),
                    lambda first, second: json.dumps({
                        "code": 0,
                        "data": {
                            "sh000300": {
                                "day": [
                                    [first.isoformat(), "1", "1", "2", "1", "1"],
                                    [second.isoformat(), "2", "2", "3", "1", "1"],
                                ]
                            }
                        },
                    }).encode("utf-8"),
                ),
                (
                    "eastmoney",
                    next(item for item in items if item.symbol == "fund110022"),
                    "fund_fund110022",
                    lambda client, cache: EastMoneyFundProvider(client, cache, endpoint="https://fixture/{code}"),
                    lambda first, second: (
                        "var Data_netWorthTrend = ["
                        f'{{"x":{int(datetime(first.year, first.month, first.day, tzinfo=timezone.utc).timestamp() * 1000)},"y":1.23}},'
                        f'{{"x":{int(datetime(second.year, second.month, second.day, tzinfo=timezone.utc).timestamp() * 1000)},"y":1.25}}];'
                    ).encode("utf-8"),
                ),
            ]
            for name, instrument, key, provider_factory, payload_factory in cases:
                with self.subTest(provider=name):
                    exchange_today = now.astimezone(ZoneInfo(instrument.timezone)).date()
                    future_day = exchange_today + timedelta(days=30)
                    payload = payload_factory(future_day - timedelta(days=1), future_day)
                    cache = DiskCache(root / name)
                    fresh_client = SequenceClient([payload])
                    fresh_bars = provider_factory(fresh_client, cache).fetch(instrument)
                    cached_client = SequenceClient([])
                    cached_bars = provider_factory(cached_client, cache).fetch(instrument)
                    settings = replace(self._settings(root / name), universe=[instrument])
                    engine = LiveEngine(settings)
                    quotes = {
                        instrument.symbol: Quote(
                            instrument.symbol, 1.0, "USD", instrument.timezone, "test", now, now,
                        )
                    } if instrument.realtime_quote else {}
                    expected = "BAR_FUTURE_DATE:%s:%s:%s" % (
                        instrument.symbol, future_day.isoformat(), exchange_today.isoformat(),
                    )

                    self.assertEqual(len(fresh_client.calls), 1)
                    self.assertEqual(cached_client.calls, [])
                    self.assertIn(expected, engine._validate(now, quotes, {instrument.symbol: fresh_bars}, []))
                    self.assertIn(expected, engine._validate(now, quotes, {instrument.symbol: cached_bars}, []))

    def test_fresh_market_is_data_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            now = datetime.now(timezone.utc)
            class Gateway:
                def fetch(self, instruments):
                    quotes = {item.symbol: Quote(item.symbol, 1.0, "USD", item.timezone, "test", now, now)
                              for item in instruments if item.realtime_quote}
                    bars = {item.symbol: [Bar(item.symbol, now.astimezone(ZoneInfo(item.timezone)).date() - timedelta(days=1), 1, 1, 1, 1, 1, item.timezone, "test", now)]
                            for item in instruments}
                    return quotes, bars, []
            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            report = engine.run_once()
            self.assertEqual(report["state"], "DATA_READY")
            self.assertEqual(
                set(report["quote_freshness"]),
                {item.symbol for item in settings.universe if item.realtime_quote},
            )
            self.assertEqual(report["quote_freshness"]["hk00700"]["declared_feed_delay_minutes"], 25)
            self.assertIn("observed_lag_minutes", report["quote_freshness"]["hk00700"])
            self.assertIn("last_advance_at", report["quote_freshness"]["hk00700"])
            self.assertIn("stalled_minutes", report["quote_freshness"]["hk00700"])

    def test_open_market_excludes_current_daily_bar_before_backtest(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            settings = replace(settings, universe=[hk])
            now = datetime(2026, 9, 14, 2, 25, tzinfo=timezone.utc)
            previous_close = datetime(2026, 9, 11).date()
            current_session = now.astimezone(ZoneInfo(hk.timezone)).date()

            class Gateway:
                last_bar_quality: dict[str, list[BarQualityIssue]] = {}

                def fetch(self, instruments):
                    return (
                        {
                            hk.symbol: Quote(
                                hk.symbol, 1.0, "HKD", hk.timezone, "fixture",
                                datetime(2026, 9, 14, 10, 24), now,
                            )
                        },
                        {
                            hk.symbol: [
                                Bar(hk.symbol, previous_close, 1, 1, 1, 1, 1, hk.timezone, "fixture", now),
                                Bar(hk.symbol, current_session, 2, 2, 2, 2, 2, hk.timezone, "fixture", now),
                            ]
                        },
                        [],
                    )

            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            with patch("signal_lattice.live_runtime.run_backtest", return_value={"status": "PASS"}) as backtest:
                with patch("signal_lattice.live_runtime.build_branch_report", return_value={"branches": []}):
                    report = engine.run_once(now)

            used_bars = backtest.call_args.args[1][hk.symbol]
            self.assertEqual(report["state"], "DATA_READY")
            self.assertEqual([bar.day for bar in used_bars], [previous_close])
            self.assertEqual(report["bar_sources"][hk.symbol]["latest_day"], previous_close.isoformat())
            self.assertEqual(report["bar_completion"][hk.symbol]["last_used_day"], previous_close.isoformat())
            self.assertTrue(report["bar_completion"][hk.symbol]["session_complete"])
            self.assertEqual(report["bar_completion"][hk.symbol]["excluded_intraday_bar_count"], 1)
            self.assertEqual(report["bar_completion"][hk.symbol]["last_used_bar_date"], previous_close.isoformat())
            self.assertTrue(report["bar_completion"][hk.symbol]["last_used_bar_is_closed"])
            self.assertEqual(report["bar_completion"][hk.symbol]["excluded_current_session_bar_count"], 1)
            self.assertEqual(report["bar_completion"][hk.symbol]["basis"], "TRADING_DAY_IN_PROGRESS_EXCLUDE_EXCHANGE_TODAY")

    def test_backtest_receives_only_the_effective_contiguous_segment(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            now = datetime(2026, 9, 13, 14, tzinfo=timezone.utc)
            complete = self._valid_bars(
                us_spy,
                now.astimezone(ZoneInfo(us_spy.timezone)).date(),
                1_800,
                now,
            )
            source_bars = complete[:150] + complete[168:]

            class Gateway:
                last_bar_quality: dict[str, list[BarQualityIssue]] = {}

                def fetch(self, instruments):
                    return (
                        {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", now, now)},
                        {"usSPY": source_bars},
                        [],
                    )

            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            with patch("signal_lattice.live_runtime.run_backtest", return_value={"status": "PASS"}) as backtest:
                with patch("signal_lattice.live_runtime.build_branch_report", return_value={"branches": []}):
                    report = engine.run_once(now)

            used_bars = backtest.call_args.args[1]["usSPY"]
            effective_start = complete[168].day
            self.assertEqual(report["state"], "DATA_READY")
            self.assertEqual(report["bar_quality"]["usSPY"]["effective_start_day"], effective_start.isoformat())
            self.assertEqual(min(bar.day for bar in used_bars), effective_start)
            self.assertTrue(all(bar.day >= effective_start for bar in used_bars))
            self.assertEqual(report["bar_sources"]["usSPY"]["earliest_day"], effective_start.isoformat())

    def test_weekend_friday_source_time_is_fresh_under_closed_market_rule(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
            bars = {
                "usSPY": [Bar(
                    "usSPY", datetime(2026, 9, 11).date(), 1, 1, 1, 1, 1,
                    us_spy.timezone, "fixture", now,
                )]
            }
            quote = Quote(
                "usSPY", 1.0, "USD", us_spy.timezone, "fixture", datetime(2026, 9, 11, 9, 30), now,
            )

            freshness = engine._quote_freshness(us_spy, quote, now)
            findings = engine._validate(now, {"usSPY": quote}, bars, [], quote_freshness={"usSPY": freshness})

            self.assertEqual(findings, [])
            self.assertEqual(freshness["market_state"], "CLOSED")
            self.assertEqual(freshness["basis"], "MARKET_CLOSED_RECENT_TRADING_DAY_APPROXIMATION")

    def test_missing_or_open_market_stale_quote_source_time_is_system_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            us_spy = next(item for item in settings.universe if item.symbol == "usSPY")
            settings = replace(settings, universe=[us_spy])
            engine = LiveEngine(settings)
            now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
            bars = {
                "usSPY": [Bar(
                    "usSPY", now.astimezone(ZoneInfo(us_spy.timezone)).date(), 1, 1, 1, 1, 1,
                    us_spy.timezone, "fixture", now,
                )]
            }
            missing = {"usSPY": Quote("usSPY", 1.0, "USD", us_spy.timezone, "fixture", None, now)}
            stale = {
                "usSPY": Quote(
                    "usSPY", 1.0, "USD", us_spy.timezone, "fixture",
                    now - timedelta(seconds=settings.quote_max_age_seconds * 3), now,
                )
            }

            self.assertIn("QUOTE_SOURCE_TIME_MISSING:usSPY:fixture", engine._validate(now, missing, bars, []))
            self.assertIn("QUOTE_SOURCE_STALE:usSPY", engine._validate(now, stale, bars, []))
            self.assertEqual(
                engine._quote_freshness(us_spy, stale["usSPY"], now)["basis"],
                "MARKET_OPEN_DECLARED_FEED_DELAY_PLUS_TTL",
            )

    def test_declared_feed_delay_allows_hk_22_minutes_and_blocks_hk_35_or_cn_5(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            cn = next(item for item in settings.universe if item.symbol == "sh000300")
            now = datetime(2026, 9, 14, 1, 33, tzinfo=timezone.utc)

            def bars_for(item):
                return {
                    item.symbol: [Bar(
                        item.symbol,
                        now.astimezone(ZoneInfo(item.timezone)).date(),
                        1, 1, 1, 1, 1, item.timezone, "fixture", now,
                    )]
                }

            hk_engine = LiveEngine(replace(settings, universe=[hk]))
            hk_local_now = now.astimezone(ZoneInfo(hk.timezone)).replace(tzinfo=None)
            hk_within_delay = Quote(
                hk.symbol, 1.0, "HKD", hk.timezone, "fixture",
                hk_local_now - timedelta(minutes=22), now,
            )
            hk_freshness = hk_engine._quote_freshness(hk, hk_within_delay, now)
            self.assertEqual(hk_freshness["status"], "FRESH")
            self.assertEqual(hk_freshness["declared_feed_delay_minutes"], 25)
            self.assertEqual(hk_freshness["observed_lag_minutes"], 22.0)
            self.assertEqual(hk_freshness["allowed_source_age_seconds"], 28 * 60)
            self.assertEqual(
                hk_engine._validate(
                    now, {hk.symbol: hk_within_delay}, bars_for(hk), [],
                    quote_freshness={hk.symbol: hk_freshness},
                ),
                [],
            )

            hk_overdue = Quote(
                hk.symbol, 1.0, "HKD", hk.timezone, "fixture",
                hk_local_now - timedelta(minutes=35), now,
            )
            self.assertEqual(hk_engine._quote_freshness(hk, hk_overdue, now)["status"], "SOURCE_TIME_STALE")
            self.assertIn(
                "QUOTE_SOURCE_STALE:hk00700",
                hk_engine._validate(now, {hk.symbol: hk_overdue}, bars_for(hk), []),
            )

            cn_engine = LiveEngine(replace(settings, universe=[cn]))
            cn_local_now = now.astimezone(ZoneInfo(cn.timezone)).replace(tzinfo=None)
            cn_overdue = Quote(
                cn.symbol, 1.0, "CNY", cn.timezone, "fixture",
                cn_local_now - timedelta(minutes=5), now,
            )
            cn_freshness = cn_engine._quote_freshness(cn, cn_overdue, now)
            self.assertEqual(cn_freshness["declared_feed_delay_minutes"], 0)
            self.assertEqual(cn_freshness["status"], "SOURCE_TIME_STALE")
            self.assertIn(
                "QUOTE_SOURCE_STALE:sh000300",
                cn_engine._validate(
                    now, {cn.symbol: cn_overdue}, bars_for(cn), [],
                    quote_freshness={cn.symbol: cn_freshness},
                ),
            )

    def test_hk_sampled_opening_spike_blocks_then_block_updates_remain_fresh(self):
        """复现 2026-09-14 的 12 分钟、90 秒间隔港股实测中正常的分块推进。"""
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            engine = LiveEngine(replace(settings, universe=[hk]))
            samples = [
                (datetime(2026, 9, 14, 1, 49, 34, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 20)),
                (datetime(2026, 9, 14, 1, 51, 4, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 31)),
                (datetime(2026, 9, 14, 1, 52, 35, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 31)),
                (datetime(2026, 9, 14, 1, 54, 6, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 35)),
                (datetime(2026, 9, 14, 1, 55, 37, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 35)),
                (datetime(2026, 9, 14, 1, 57, 8, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 35)),
                (datetime(2026, 9, 14, 1, 58, 38, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 35)),
                (datetime(2026, 9, 14, 2, 0, 9, tzinfo=timezone.utc), datetime(2026, 9, 14, 9, 39)),
            ]

            opening_observed_at, opening_source_time = samples[0]
            opening_quote = Quote(
                hk.symbol, 1.0, "HKD", hk.timezone, "fixture", opening_source_time, opening_observed_at,
            )
            self.assertEqual(
                engine._quote_freshness(hk, opening_quote, opening_observed_at)["status"],
                "SOURCE_TIME_STALE",
            )

            for observed_at, source_time in samples[1:]:
                quote = Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source_time, observed_at)
                freshness = engine._quote_freshness(hk, quote, observed_at)
                self.assertEqual(freshness["status"], "FRESH")
                self.assertEqual(freshness["advance_status"], "ADVANCING_OR_WITHIN_GRACE")

            self.assertTrue((settings.state_dir / "quote_progress.json").is_file())

    def test_hk_source_stalled_for_twelve_minutes_blocks_inside_absolute_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            settings = replace(settings, universe=[hk])
            first_observed_at = datetime(2026, 9, 14, 1, 55, tzinfo=timezone.utc)
            source_time = datetime(2026, 9, 14, 9, 40)
            first_engine = LiveEngine(settings)
            first_quote = Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source_time, first_observed_at)
            self.assertEqual(first_engine._quote_freshness(hk, first_quote, first_observed_at)["status"], "FRESH")

            stalled_observed_at = first_observed_at + timedelta(minutes=12)
            engine = LiveEngine(settings)
            stalled_quote = Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source_time, stalled_observed_at)
            freshness = engine._quote_freshness(hk, stalled_quote, stalled_observed_at)
            bars = {
                hk.symbol: [Bar(
                    hk.symbol, stalled_observed_at.astimezone(ZoneInfo(hk.timezone)).date(),
                    1, 1, 1, 1, 1, hk.timezone, "fixture", stalled_observed_at,
                )]
            }

            self.assertEqual(freshness["status"], "FEED_STALLED")
            self.assertEqual(freshness["advance_status"], "FEED_STALLED")
            self.assertEqual(freshness["stalled_minutes"], 12.0)
            self.assertLess(freshness["observed_lag_minutes"], 28.0)
            self.assertIn(
                "QUOTE_FEED_STALLED:hk00700",
                engine._validate(
                    stalled_observed_at, {hk.symbol: stalled_quote}, bars, [],
                    quote_freshness={hk.symbol: freshness},
                ),
            )

    def test_hk_absolute_lag_of_thirty_five_minutes_blocks_as_source_stale(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            settings = replace(settings, universe=[hk])
            engine = LiveEngine(settings)
            observed_at = datetime(2026, 9, 14, 2, 0, tzinfo=timezone.utc)
            quote = Quote(
                hk.symbol, 1.0, "HKD", hk.timezone, "fixture",
                datetime(2026, 9, 14, 9, 25), observed_at,
            )
            freshness = engine._quote_freshness(hk, quote, observed_at)
            bars = {
                hk.symbol: [Bar(
                    hk.symbol, observed_at.astimezone(ZoneInfo(hk.timezone)).date(),
                    1, 1, 1, 1, 1, hk.timezone, "fixture", observed_at,
                )]
            }

            self.assertEqual(freshness["status"], "SOURCE_TIME_STALE")
            self.assertEqual(freshness["advance_status"], "ADVANCING_OR_WITHIN_GRACE")
            self.assertIn(
                "QUOTE_SOURCE_STALE:hk00700",
                engine._validate(observed_at, {hk.symbol: quote}, bars, [], quote_freshness={hk.symbol: freshness}),
            )

    def test_closed_hk_market_does_not_apply_source_advance_stall_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            hk = next(item for item in settings.universe if item.symbol == "hk00700")
            settings = replace(settings, universe=[hk])
            engine = LiveEngine(settings)
            source_time = datetime(2026, 9, 14, 9, 40)
            open_observed_at = datetime(2026, 9, 14, 1, 55, tzinfo=timezone.utc)
            engine._quote_freshness(
                hk,
                Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source_time, open_observed_at),
                open_observed_at,
            )
            # 16:30 HKT，港股最后一个时段（13:00-16:00）已结束，是真正的收市。
            # 原值 04:15 UTC = 12:15 HKT 落在午休里，午休不是收市。
            closed_observed_at = datetime(2026, 9, 14, 8, 30, tzinfo=timezone.utc)
            quote = Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source_time, closed_observed_at)
            freshness = engine._quote_freshness(hk, quote, closed_observed_at)
            bars = {
                hk.symbol: [Bar(
                    hk.symbol, closed_observed_at.astimezone(ZoneInfo(hk.timezone)).date(),
                    1, 1, 1, 1, 1, hk.timezone, "fixture", closed_observed_at,
                )]
            }

            self.assertEqual(freshness["market_state"], "CLOSED")
            self.assertEqual(freshness["advance_status"], "NOT_APPLICABLE_MARKET_CLOSED")
            self.assertIsNone(freshness["stalled_minutes"])
            self.assertNotIn(
                "QUOTE_FEED_STALLED:hk00700",
                engine._validate(
                    closed_observed_at, {hk.symbol: quote}, bars, [], quote_freshness={hk.symbol: freshness},
                ),
            )

    def test_semantically_invalid_runtime_bar_is_system_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            # run_once() 取的是真实墙钟，所以固定 fixture 的 now 并不能钉住引擎。
            # 这条测的是 OHLCV 语义校验本身，与当天开休市无关：把 bar 落在一个
            # 已经结束的交易日（2026-09-11 周五），断言就不再随运行时刻变化。
            # 原先用 now.date() 的写法在盘中、午休和开盘前会走到不同分支。
            now = datetime.now(timezone.utc)
            completed_day = date(2026, 9, 11)

            class Gateway:
                def fetch(self, instruments):
                    quotes = {
                        item.symbol: Quote(item.symbol, 1.0, "USD", item.timezone, "fixture", now, now)
                        for item in instruments if item.realtime_quote
                    }
                    bars = {
                        item.symbol: [Bar(
                            item.symbol, completed_day, 1, 1, 1, 1, 1,
                            item.timezone, "fixture", now,
                        )]
                        for item in instruments
                    }
                    bars["usSPY"] = [Bar(
                        "usSPY", completed_day, 1, 1, 2, 1, 1,
                        next(item.timezone for item in instruments if item.symbol == "usSPY"), "fixture", now,
                    )]
                    return quotes, bars, []

            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            report = engine.run_once()

            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            self.assertIn("BAR_INVALID_OHLCV:usSPY", report["freshness_findings"])

    def test_nonfinite_runtime_quote_is_system_blocked_and_never_serialized(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            now = datetime.now(timezone.utc)

            class Gateway:
                def fetch(self, instruments):
                    quotes = {
                        item.symbol: Quote(
                            item.symbol,
                            float("nan") if item.symbol == "usSPY" else 1.0,
                            "USD",
                            item.timezone,
                            "test",
                            now,
                            now,
                        )
                        for item in instruments if item.realtime_quote
                    }
                    bars = {
                        item.symbol: [Bar(item.symbol, now.date(), 1, 1, 1, 1, 1, item.timezone, "test", now)]
                        for item in instruments
                    }
                    return quotes, bars, []

            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            report = engine.run_once()
            persisted = json.loads((settings.state_dir / "latest.json").read_text(encoding="utf-8"))

            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            self.assertEqual(persisted["state"], "SYSTEM_BLOCKED")
            self.assertNotIn("usSPY", report["quotes"])
            self.assertIn("QUOTE_NONFINITE:usSPY", report["freshness_findings"])

    def test_unexpected_runtime_failure_replaces_previous_ready_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            engine = LiveEngine(settings)
            now = datetime.now(timezone.utc)
            engine.store.save({
                "state": "DATA_READY",
                "generated_at": now.isoformat(),
                "decision": {"state": "LONG", "action": "研究观察"},
            })

            class ExplodingGateway:
                def fetch(self, instruments):
                    raise RuntimeError("fixture runtime failure")

            engine.gateway = ExplodingGateway()
            report = engine.run_once()
            persisted = engine.store.latest()

            self.assertEqual(report["state"], "SYSTEM_BLOCKED")
            self.assertEqual(report["blocked_reason"], "UNEXPECTED_RUNTIME_FAILURE")
            self.assertEqual(persisted["state"], "SYSTEM_BLOCKED")
            self.assertEqual(persisted["blocked_reason"], "UNEXPECTED_RUNTIME_FAILURE")
            self.assertIsNone(persisted["decision"]["action"])


if __name__ == "__main__":
    unittest.main()
