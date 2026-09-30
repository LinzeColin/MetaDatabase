"""NYSE 交易日历（标准库实现）：假日与顺延规则、半日市、以及实时层拿它判断开休市/收盘/陈旧度。

缺陷 #4：以前只看「周一到周五 9:30-16:00」，感恩节（2026-11-26）美东 10:00 被当成开市，
昨天的报价就被判 SOURCE_TIME_STALE，页面写「行情源全部取不到数据」。
"""

import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from signal_lattice import hub
from signal_lattice import nyse_calendar as N
from signal_lattice.live_config import LiveSettings
from signal_lattice.live_runtime import (LiveEngine, _in_intraday_break, _market_is_open, _trading_day_is_complete,
                                         _trading_seconds_between, us_instrument)
from signal_lattice.marketdata.models import Quote
from hub_fixtures import build_view, standard_pool, write_research_dir
from test_live_engine import FakeGateway

NY = ZoneInfo("America/New_York")


def ny(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=NY)


class HolidayRuleTests(unittest.TestCase):
    def test_2026_full_year_matches_the_published_nyse_schedule(self):
        expected = {date(2026, 1, 1): "New Year's Day", date(2026, 1, 19): "Martin Luther King Jr. Day", date(2026, 2, 16): "Washington's Birthday",
                    date(2026, 4, 3): "Good Friday", date(2026, 5, 25): "Memorial Day", date(2026, 6, 19): "Juneteenth",
                    date(2026, 7, 3): "Independence Day (observed)", date(2026, 9, 7): "Labor Day", date(2026, 11, 26): "Thanksgiving Day",
                    date(2026, 12, 25): "Christmas Day"}
        self.assertEqual(N.holidays(2026), expected)

    def test_2025_and_2027_shift_rules(self):
        h25, h27 = N.holidays(2025), N.holidays(2027)
        self.assertIn(date(2025, 4, 18), h25)                       # 耶稣受难日（复活节 4-20）
        self.assertIn(date(2025, 7, 4), h25)                        # 周五
        self.assertNotIn(date(2025, 6, 20), h25)
        self.assertIn(date(2027, 12, 24), h27)                      # 圣诞节周六 -> 周五休市
        self.assertIn(date(2027, 7, 5), h27)                        # 独立日周日 -> 周一休市
        self.assertIn(date(2027, 6, 18), h27)                       # 六月节周六 -> 周五休市
        self.assertIn(date(2027, 3, 26), h27)                       # 耶稣受难日（复活节 3-28）

    def test_new_years_day_on_a_saturday_does_not_close_the_friday_before(self):
        self.assertTrue(N.is_trading_day(date(2021, 12, 31)))       # 2022-01-01 是周六：NYSE 不顺延到前一个周五
        self.assertNotIn(date(2021, 12, 31), N.holidays(2021))
        self.assertIn(date(2023, 1, 2), N.holidays(2023))           # 周日 -> 周一

    def test_weekends_and_holidays_are_not_trading_days(self):
        self.assertFalse(N.is_trading_day(date(2026, 9, 26)))
        self.assertFalse(N.is_trading_day(date(2026, 11, 26)))
        self.assertTrue(N.is_trading_day(date(2026, 11, 25)))
        self.assertTrue(N.is_trading_day(date(2026, 11, 27)))

    def test_half_days_close_at_1300(self):
        self.assertEqual(N.close_time(date(2026, 11, 27)), time(13, 0))     # 感恩节次日
        self.assertEqual(N.close_time(date(2026, 12, 24)), time(13, 0))     # 圣诞前夜
        self.assertEqual(N.close_time(date(2025, 7, 3)), time(13, 0))       # 独立日前一交易日（7-4 是周五）
        self.assertEqual(N.close_time(date(2024, 7, 3)), time(13, 0))
        self.assertEqual(N.close_time(date(2026, 11, 25)), time(16, 0))
        self.assertEqual(N.close_time(date(2026, 7, 2)), time(16, 0))       # 2026-07-03 整天休市，7-2 是整日
        self.assertEqual(N.close_time(date(2021, 12, 24)), None)            # 圣诞节周六 -> 12-24 休市
        self.assertIsNone(N.close_time(date(2026, 11, 26)))                 # 休市日没有收盘时间

    def test_previous_and_next_trading_day_skip_holidays(self):
        self.assertEqual(N.previous_trading_day(date(2026, 11, 27)), date(2026, 11, 25))
        self.assertEqual(N.next_trading_day(date(2026, 11, 25)), date(2026, 11, 27))
        self.assertEqual(N.previous_trading_day(date(2026, 9, 28)), date(2026, 9, 25))


class SessionHelperTests(unittest.TestCase):
    US = us_instrument("X", "X", None)

    def test_thanksgiving_at_ten_is_closed_not_open(self):
        self.assertFalse(_market_is_open(self.US, ny(2026, 11, 26, 10)))
        self.assertTrue(_trading_day_is_complete(self.US, ny(2026, 11, 26, 10)))       # 没有当日 bar 要排除

    def test_the_half_day_after_thanksgiving_closes_at_one(self):
        self.assertTrue(_market_is_open(self.US, ny(2026, 11, 27, 12, 59)))
        self.assertFalse(_market_is_open(self.US, ny(2026, 11, 27, 13, 0)))
        self.assertFalse(_trading_day_is_complete(self.US, ny(2026, 11, 27, 12, 59)))
        self.assertTrue(_trading_day_is_complete(self.US, ny(2026, 11, 27, 14, 0)))    # 14:00 已收盘

    def test_a_normal_day_still_closes_at_four(self):
        self.assertTrue(_market_is_open(self.US, ny(2026, 11, 25, 15, 59)))
        self.assertFalse(_trading_day_is_complete(self.US, ny(2026, 11, 25, 15, 59)))
        self.assertTrue(_trading_day_is_complete(self.US, ny(2026, 11, 25, 16, 0)))
        self.assertFalse(_in_intraday_break(self.US, ny(2026, 11, 27, 14, 0)))

    def test_trading_seconds_skip_the_holiday_and_use_the_half_day_close(self):
        # 周三收盘 -> 周五 13:00：周四整天休市，周五只有 9:30-13:00 = 3.5 小时
        self.assertEqual(_trading_seconds_between(self.US, ny(2026, 11, 25, 16, 0), ny(2026, 11, 27, 13, 0)), 3.5 * 3600)
        self.assertEqual(_trading_seconds_between(self.US, ny(2026, 11, 25, 16, 0), ny(2026, 11, 27, 16, 0)), 3.5 * 3600)


class ThanksgivingQuoteTests(unittest.TestCase):
    """页面层面：休市日的报价用「上一个收盘」判断，不是被判过期。"""

    @staticmethod
    def engine(state_dir):
        base = LiveSettings.from_env(Path(".").resolve())
        return LiveEngine(replace(base, state_dir=Path(state_dir)))

    def freshness(self, now, source):
        item = us_instrument("ABCD", "ABCD Inc", "Nasdaq")
        with TemporaryDirectory() as temp:
            quote = Quote("ABCD", 10.0, "USD", item.timezone, "sina_quote", source, now.astimezone(timezone.utc))
            return self.engine(temp)._quote_freshness(item, quote, now.astimezone(timezone.utc))

    def test_thanksgiving_morning_with_yesterdays_close_is_fresh_and_says_closed(self):
        report = self.freshness(ny(2026, 11, 26, 10), ny(2026, 11, 25, 16, 0))
        self.assertEqual(report["status"], "FRESH")
        self.assertEqual(report["market_state"], "CLOSED")
        self.assertNotEqual(report["status"], "SOURCE_TIME_STALE")

    def test_the_day_after_thanksgiving_at_two_pm_the_market_has_closed(self):
        report = self.freshness(ny(2026, 11, 27, 14), ny(2026, 11, 27, 12, 58))
        self.assertEqual(report["market_state"], "CLOSED")
        self.assertEqual(report["status"], "FRESH")

    def test_a_normal_open_day_still_catches_a_quote_frozen_at_yesterdays_close(self):
        report = self.freshness(ny(2026, 11, 25, 10), ny(2026, 11, 24, 16, 0))
        self.assertEqual((report["market_state"], report["status"]), ("OPEN", "SOURCE_TIME_STALE"))


class ResearchAgeTests(unittest.TestCase):
    """研究快照过期（36 小时）：周末与美股假日之间没有新申报，不算「变旧」。"""

    def block(self, generated, now):
        view = build_view(standard_pool(), generated_at=generated.astimezone(timezone.utc))
        return hub.system_block(view, now.astimezone(timezone.utc))

    def test_thanksgiving_does_not_make_wednesdays_snapshot_stale_on_friday_afternoon(self):
        self.assertIsNone(self.block(ny(2026, 11, 25, 16), ny(2026, 11, 27, 14)))        # 墙钟 46 小时，扣掉整天休市的周四 = 22

    def test_a_snapshot_from_before_the_holiday_is_still_caught_when_it_is_really_old(self):
        blocked = self.block(ny(2026, 11, 23, 16), ny(2026, 11, 27, 14))                 # 周一的快照，周五还没更新：70 小时
        self.assertEqual(blocked["blocked_reason"], "RESEARCH_SNAPSHOT_STALE")

    def test_an_ordinary_stale_snapshot_is_unchanged(self):
        self.assertEqual(self.block(ny(2026, 9, 28, 9), ny(2026, 9, 30, 10))["blocked_reason"], "RESEARCH_SNAPSHOT_STALE")
        self.assertIsNone(self.block(ny(2026, 9, 29, 10), ny(2026, 9, 30, 11)))

    def test_the_report_keeps_both_ages(self):
        view = build_view(standard_pool(), generated_at=ny(2026, 11, 25, 16).astimezone(timezone.utc))
        chain = hub.data_chain(view, ny(2026, 11, 27, 14).astimezone(timezone.utc))
        self.assertEqual((chain["research_age_hours"], chain["research_age_trading_hours"]), (46.0, 22.0))


class HolidayRunTests(unittest.TestCase):
    """整轮运行：感恩节当天不是「行情源全部取不到数据」，页面读得到「休市（感恩节）」。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def run_at(self, now, source):
        research = self.root / "research"
        write_research_dir(research, standard_pool(), generated_at=now - timedelta(hours=1))
        base = LiveSettings.from_env(Path(__file__).resolve().parents[1])
        settings = replace(base, state_dir=self.root / "state", research_dir=research, backtest_dir=self.root / "bt")
        gateway = FakeGateway(now)
        original = gateway.fetch_quotes

        def quotes(instruments):
            found, errors = original(instruments)
            return {s: Quote(s, q.price, q.currency, q.exchange_timezone, q.source, source, q.observed_at) for s, q in found.items()}, errors

        gateway.fetch_quotes = quotes
        engine = LiveEngine(settings)
        engine.gateway = gateway
        return engine.run_once(now)

    def test_thanksgiving_morning_is_not_blocked_and_the_page_data_says_the_market_is_closed(self):
        now = ny(2026, 11, 26, 10).astimezone(timezone.utc)
        report = self.run_at(now, ny(2026, 11, 25, 16, 0))
        self.assertEqual(report["state"], "DATA_READY")
        self.assertNotEqual(report["decision"].get("blocked_reason"), "MARKET_DATA_UNAVAILABLE")
        self.assertNotIn("SOURCE_TIME_STALE:ALPHA", report["freshness_findings"])
        self.assertEqual(report["us_market"]["state"], "CLOSED")
        self.assertEqual(report["us_market"]["reason"], "HOLIDAY")
        self.assertIn("感恩节", report["us_market"]["text"])
        self.assertEqual(report["quote_freshness"]["ALPHA"]["status"], "FRESH")

    def test_the_friday_after_thanksgiving_at_two_pm_reads_as_closed_after_a_half_day(self):
        now = ny(2026, 11, 27, 14).astimezone(timezone.utc)
        report = self.run_at(now, ny(2026, 11, 27, 12, 58))
        self.assertEqual((report["us_market"]["state"], report["us_market"]["reason"]), ("CLOSED", "AFTER_CLOSE"))
        self.assertIn("13:00", report["us_market"]["text"])
        self.assertEqual(report["state"], "DATA_READY")

    def test_a_normal_session_says_open(self):
        now = ny(2026, 11, 25, 11).astimezone(timezone.utc)
        report = self.run_at(now, ny(2026, 11, 25, 10, 59))
        self.assertEqual((report["us_market"]["state"], report["us_market"]["reason"]), ("OPEN", "SESSION"))


if __name__ == "__main__":
    unittest.main()
