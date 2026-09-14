"""复盘瞬间不得误判行情过期；跨日冻结仍必须被抓住。

2026-09-14 05:03 UTC（13:03 HKT，港股午休后复盘）生产实际发生：
QUOTE_SOURCE_STALE:hk00700 / hk02800 连续 4 次，触发采集退避，公网翻 SYSTEM_BLOCKED。

原因是用墙钟衡量陈旧度。港股申报延迟 25 分钟，13:00 复盘时能拿到的最新来源时间
必然还是午休前的 11:35，墙钟差 85 分钟，远超「延迟 25 分 + TTL 180 秒」。
这会在每个有午休的市场、每个交易日的复盘时刻各误报一次。

改为按交易时间衡量：只数落在交易时段内的秒数。复盘瞬间交易时间差恰好等于申报延迟，
判新鲜；若复盘 5 分钟后来源时间仍不推进，交易时间累计超限，才判过期。
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import (
    LiveEngine,
    _current_session_elapsed_seconds,
    _trading_seconds_between,
)
from signal_lattice.marketdata.models import Quote

DAY = date(2026, 9, 14)


def _instrument(symbol):
    return next(item for item in default_universe() if item.symbol == symbol)


def _local(item, hour, minute):
    return datetime(DAY.year, DAY.month, DAY.day, hour, minute, tzinfo=ZoneInfo(item.timezone))


class TradingSecondsTests(unittest.TestCase):
    def test_lunch_break_is_not_counted(self):
        hk = _instrument("hk00700")
        # 11:35 → 13:00 之间只有 11:35-12:00 属于交易时段
        self.assertEqual(_trading_seconds_between(hk, _local(hk, 11, 35), _local(hk, 13, 0)), 25 * 60)

    def test_pre_open_time_is_not_counted(self):
        hk = _instrument("hk00700")
        self.assertEqual(_trading_seconds_between(hk, _local(hk, 8, 0), _local(hk, 9, 45)), 15 * 60)

    def test_within_one_session_equals_wall_clock(self):
        hk = _instrument("hk00700")
        self.assertEqual(_trading_seconds_between(hk, _local(hk, 10, 0), _local(hk, 10, 30)), 30 * 60)

    def test_overnight_accumulates_full_sessions(self):
        hk = _instrument("hk00700")
        yesterday_close = _local(hk, 16, 0) - timedelta(days=1)
        # 昨天收盘 → 今天 13:10：今日上午 150 分钟 + 下午 10 分钟
        self.assertEqual(_trading_seconds_between(hk, yesterday_close, _local(hk, 13, 10)), (150 + 10) * 60)

    def test_session_elapsed_resets_each_session(self):
        hk = _instrument("hk00700")
        self.assertEqual(_current_session_elapsed_seconds(hk, _local(hk, 9, 33)), 3 * 60)
        self.assertEqual(_current_session_elapsed_seconds(hk, _local(hk, 13, 5)), 5 * 60)
        self.assertIsNone(_current_session_elapsed_seconds(hk, _local(hk, 12, 30)))


class ReopenFreshnessTests(unittest.TestCase):
    @staticmethod
    def _engine(state_dir, item):
        base = LiveSettings.from_env(Path(".").resolve())
        return LiveEngine(LiveSettings(**{**base.__dict__, "state_dir": Path(state_dir), "universe": [item]}))

    def _status(self, item, source_hour, source_minute, now_hour, now_minute):
        source = _local(item, source_hour, source_minute).replace(tzinfo=None)
        now = _local(item, now_hour, now_minute)
        with TemporaryDirectory() as temp:
            engine = self._engine(temp, item)
            quote = Quote(item.symbol, 1.0, "HKD", item.timezone, "fixture", source, now.astimezone(timezone.utc))
            return engine._quote_freshness(item, quote, now.astimezone(timezone.utc))

    def test_reopen_with_pre_break_source_is_fresh(self):
        """13:00 复盘，来源时间 11:35（= 申报延迟）——不得判过期。"""
        hk = _instrument("hk00700")
        result = self._status(hk, 11, 35, 13, 0)
        self.assertEqual(result["status"], "FRESH", result)
        self.assertEqual(result["trading_age_seconds"], 25 * 60)
        self.assertGreater(result["observed_lag_minutes"], 80.0)

    def test_still_frozen_after_reopen_is_stale(self):
        """复盘 5 分钟后来源时间仍是 11:35——交易时间已 30 分钟，必须判过期。"""
        hk = _instrument("hk00700")
        result = self._status(hk, 11, 35, 13, 5)
        self.assertEqual(result["status"], "SOURCE_TIME_STALE", result)
        self.assertEqual(result["trading_age_seconds"], 30 * 60)

    def test_during_break_with_pre_break_source_is_fresh_and_no_stall_check(self):
        hk = _instrument("hk00700")
        result = self._status(hk, 11, 35, 12, 30)
        self.assertEqual(result["status"], "FRESH", result)
        self.assertEqual(result["advance_status"], "NOT_REQUIRED_INTRADAY_BREAK")

    def test_previous_day_source_is_stale_once_session_outruns_declared_delay(self):
        """交易时间口径抓不住「冻在昨收」时，跨日判据必须接住。"""
        hk = _instrument("hk00700")
        source = (_local(hk, 16, 0) - timedelta(days=1)).replace(tzinfo=None)
        now = _local(hk, 10, 0)  # 开盘已 30 分钟 > 申报延迟 25 分钟
        with TemporaryDirectory() as temp:
            engine = self._engine(temp, hk)
            quote = Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source, now.astimezone(timezone.utc))
            result = engine._quote_freshness(hk, quote, now.astimezone(timezone.utc))
        self.assertEqual(result["status"], "SOURCE_TIME_STALE", result)
        self.assertEqual(result["stale_reason"], "SOURCE_FROM_PREVIOUS_EXCHANGE_DAY_AFTER_DECLARED_DELAY")

    def test_previous_day_source_is_allowed_within_the_declared_delay_window(self):
        """开盘头 25 分钟里行情本就只有盘前数据，昨收时间戳是合法的。"""
        hk = _instrument("hk00700")
        source = (_local(hk, 16, 0) - timedelta(days=1)).replace(tzinfo=None)
        now = _local(hk, 9, 40)  # 开盘才 10 分钟 < 申报延迟 25 分钟
        with TemporaryDirectory() as temp:
            engine = self._engine(temp, hk)
            quote = Quote(hk.symbol, 1.0, "HKD", hk.timezone, "fixture", source, now.astimezone(timezone.utc))
            result = engine._quote_freshness(hk, quote, now.astimezone(timezone.utc))
        self.assertNotEqual(result.get("stale_reason"), "SOURCE_FROM_PREVIOUS_EXCHANGE_DAY_AFTER_DECLARED_DELAY")

    def test_cn_reopen_with_zero_declared_delay(self):
        """A 股申报延迟为 0：13:00 复盘时来源 11:30 的交易时间差为 0，判新鲜。"""
        cn = _instrument("sh000300")
        result = self._status(cn, 11, 30, 13, 0)
        self.assertEqual(result["status"], "FRESH", result)
        self.assertEqual(result["trading_age_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
