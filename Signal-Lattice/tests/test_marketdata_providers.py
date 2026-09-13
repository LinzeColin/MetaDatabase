"""四个真实 provider 的解析与 V2 诚实门。网络调用在本测试中一律替身化。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import LiveEngine
from signal_lattice.marketdata.base import DiskCache, MarketDataError
from signal_lattice.marketdata.eastmoney import EastMoneyFundProvider
from signal_lattice.marketdata.models import Bar, Quote
from signal_lattice.marketdata.sina import SinaKlineProvider, SinaQuoteProvider
from signal_lattice.marketdata.tencent import TencentKlineProvider, TencentQuoteProvider


class SequenceClient:
    """夹具客户端：每次 provider 拉取都留下精确调用次数。"""

    def __init__(self, payloads: list[bytes]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, object]] = []

    def get(self, url: str, headers=None) -> bytes:
        self.calls.append((url, headers))
        return self.payloads.pop(0)


class ProviderParsingTests(unittest.TestCase):
    def setUp(self):
        self.items = default_universe()

    def test_sina_gbk_uses_market_specific_live_price_fields(self):
        raw = (
            'hq_str_hk00700="TENCENT,腾讯控股,419.400,425.600,430.800,419.400,428.400,2.800,0.658,..."\n'
            'hq_str_hk02800="TRACKER FUND,盈富基金,25.360,25.580,25.480,25.200,25.420,-0.160,-0.625,..."\n'
            'hq_str_sh600000="浦发银行,9.350,9.350,9.260,9.350,9.220,9.250,9.260,65327293,..."\n'
            'hq_str_gb_spy="SPDR标普500 ETF,764.2900,0.85,2026-09-12 09:45:58,6.4600,764.7200,..."\n'
        ).encode("gbk")
        quotes = SinaQuoteProvider.parse(raw, self.items, datetime(2026, 9, 12, tzinfo=timezone.utc))
        self.assertEqual(quotes["usSPY"].price, 764.29)
        self.assertEqual(quotes["sh600000"].price, 9.260)
        self.assertEqual(quotes["hk00700"].price, 428.400)
        self.assertEqual(quotes["hk02800"].price, 25.420)
        self.assertEqual(quotes["usSPY"].source_time.date().isoformat(), "2026-09-12")

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

    def test_daily_parsers_reject_nonfinite_ohlcv(self):
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
        self.assertEqual(len(SinaKlineProvider.parse(sina, us_spy)), 2)
        self.assertEqual(len(TencentKlineProvider.parse(tencent, sh300)), 2)
        self.assertEqual(len(EastMoneyFundProvider.parse(eastmoney, fund)), 2)

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

    def test_fresh_market_is_data_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self._settings(Path(temporary))
            now = datetime.now(timezone.utc)
            class Gateway:
                def fetch(self, instruments):
                    quotes = {item.symbol: Quote(item.symbol, 1.0, "USD", item.timezone, "test", now, now)
                              for item in instruments if item.realtime_quote}
                    bars = {item.symbol: [Bar(item.symbol, now.date(), 1, 1, 1, 1, 1, item.timezone, "test", now)]
                            for item in instruments}
                    return quotes, bars, []
            engine = LiveEngine(settings)
            engine.gateway = Gateway()
            self.assertEqual(engine.run_once()["state"], "DATA_READY")

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


if __name__ == "__main__":
    unittest.main()
