"""日内休息时段不得被当成收市。

2026-09-14 12:23 HKT（港股午休）的灰度实测：系统报 market_state=CLOSED、
session_complete=true、last_used_bar_is_closed=true，把只含上午半场的当日 bar
当成收盘日线喂进了全部指标与回测；同时报价新鲜度退回收市口径，允许 4 个自然日
的陈旧报价在这一小时内通过。

根因是同一个谓词被用来回答两个不同的问题：「此刻是否在交易时段内」与
「交易日是否已经结束」。午休两者答案相反。
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from signal_lattice.live_config import LiveSettings, default_universe
from signal_lattice.live_runtime import (
    LiveEngine,
    _in_intraday_break,
    _intraday_break_started_at,
    _market_is_open,
    _trading_day_is_complete,
)
from signal_lattice.marketdata.models import Bar

MONDAY = date(2026, 9, 14)


def _instrument(symbol):
    return next(item for item in default_universe() if item.symbol == symbol)


def _at(item, hour, minute):
    return datetime(MONDAY.year, MONDAY.month, MONDAY.day, hour, minute, tzinfo=ZoneInfo(item.timezone))


class TradingDayPredicateTests(unittest.TestCase):
    def test_hk_lunch_break_is_neither_open_nor_day_complete(self):
        hk = _instrument("hk00700")
        noon = _at(hk, 12, 23)
        self.assertFalse(_market_is_open(hk, noon))
        self.assertTrue(_in_intraday_break(hk, noon))
        self.assertFalse(_trading_day_is_complete(hk, noon), "午休不等于交易日结束")

    def test_cn_lunch_break_is_neither_open_nor_day_complete(self):
        cn = _instrument("sh000300")
        noon = _at(cn, 12, 0)
        self.assertFalse(_market_is_open(cn, noon))
        self.assertTrue(_in_intraday_break(cn, noon))
        self.assertFalse(_trading_day_is_complete(cn, noon))

    def test_before_open_is_not_day_complete(self):
        hk = _instrument("hk00700")
        self.assertFalse(_trading_day_is_complete(hk, _at(hk, 9, 0)))
        self.assertFalse(_in_intraday_break(hk, _at(hk, 9, 0)))

    def test_after_last_session_is_day_complete(self):
        for symbol, hour in (("hk00700", 16), ("sh000300", 15), ("usSPY", 16)):
            item = _instrument(symbol)
            self.assertTrue(_trading_day_is_complete(item, _at(item, hour, 30)), symbol)
            self.assertFalse(_in_intraday_break(item, _at(item, hour, 30)), symbol)

    def test_us_session_has_no_break(self):
        us = _instrument("usSPY")
        self.assertTrue(_market_is_open(us, _at(us, 12, 0)))
        self.assertFalse(_in_intraday_break(us, _at(us, 12, 0)))

    def test_break_start_is_the_previous_session_close(self):
        hk = _instrument("hk00700")
        started = _intraday_break_started_at(hk, _at(hk, 12, 23))
        self.assertEqual((started.hour, started.minute), (12, 0))
        self.assertIsNone(_intraday_break_started_at(hk, _at(hk, 14, 0)))


class BarCompletionDuringBreakTests(unittest.TestCase):
    @staticmethod
    def _engine(state_dir):
        base = LiveSettings.from_env(Path(".").resolve())
        return LiveEngine(LiveSettings(**{**base.__dict__, "state_dir": Path(state_dir)}))

    def _run(self, symbol, hour, minute):
        item = _instrument(symbol)
        def bar(day, price):
            return Bar(
                symbol=symbol,
                day=day,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1.0,
                exchange_timezone=item.timezone,
                source="fixture",
                observed_at=datetime(MONDAY.year, MONDAY.month, MONDAY.day, tzinfo=timezone.utc),
            )

        series = [bar(MONDAY - timedelta(days=3), 1.0), bar(MONDAY, 2.0)]
        with TemporaryDirectory() as temp:
            engine = self._engine(temp)
            now = _at(item, hour, minute).astimezone(timezone.utc)
            completed, report = engine._completed_daily_bars({symbol: series}, now)
        return completed[symbol], report[symbol]

    def test_todays_bar_is_excluded_during_the_lunch_break(self):
        usable, report = self._run("hk00700", 12, 23)
        self.assertEqual([bar.day for bar in usable], [MONDAY - timedelta(days=3)])
        self.assertEqual(report["market_state"], "INTRADAY_BREAK")
        self.assertFalse(report["trading_day_complete"])
        self.assertEqual(report["excluded_current_session_bar_count"], 1)
        self.assertTrue(report["last_used_bar_is_closed"])
        self.assertEqual(report["last_used_bar_date"], (MONDAY - timedelta(days=3)).isoformat())

    def test_todays_bar_is_used_after_the_close(self):
        usable, report = self._run("hk00700", 16, 30)
        self.assertEqual([bar.day for bar in usable][-1], MONDAY)
        self.assertEqual(report["market_state"], "CLOSED")
        self.assertTrue(report["trading_day_complete"])
        self.assertEqual(report["excluded_current_session_bar_count"], 0)
        self.assertEqual(report["last_used_bar_date"], MONDAY.isoformat())

    def test_todays_bar_is_excluded_mid_session(self):
        usable, report = self._run("hk00700", 10, 0)
        self.assertEqual([bar.day for bar in usable], [MONDAY - timedelta(days=3)])
        self.assertEqual(report["market_state"], "OPEN")
        self.assertFalse(report["trading_day_complete"])


if __name__ == "__main__":
    unittest.main()
