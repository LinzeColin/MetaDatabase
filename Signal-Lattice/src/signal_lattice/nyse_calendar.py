"""纽约证券交易所（NYSE）交易日历：标准库实现，不联网。

整日休市（10 个）：元旦、马丁·路德·金日（1 月第 3 个周一）、总统日（2 月第 3 个周一）、耶稣受难日（复活节前的周五）、
阵亡将士纪念日（5 月最后一个周一）、六月节（6-19，2022 起）、独立日（7-4）、劳动节（9 月第 1 个周一）、
感恩节（11 月第 4 个周四）、圣诞节（12-25）。
顺延规则：假日落在周六 -> 前一个周五休市；落在周日 -> 后一个周一休市。
唯一例外：元旦落在周六时 NYSE 不把休市挪到前一年的最后一个周五（NYSE Rule 7.2）。
半日市（13:00 收盘）：独立日前一交易日（7-3，且它是周一到周四的交易日）、感恩节次日、圣诞前夜（12-24，且它是周一到周四的交易日）。

不含临时休市（国葬、飓风、灾难等）：那种日子行情源不会推进，由实时层的陈旧度判据抓住。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Dict, Optional
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")

OPEN_TIME = time(9, 30)
REGULAR_CLOSE = time(16, 0)
HALF_DAY_CLOSE = time(13, 0)
JUNETEENTH_FIRST_YEAR = 2022


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def easter_sunday(year: int) -> date:
    """复活节（格里高利历，匿名算法）。"""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(day: date) -> Optional[date]:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


@lru_cache(maxsize=64)
def _holidays(year: int) -> Dict[date, str]:
    found: Dict[date, str] = {}
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:                       # 元旦落在周六：不顺延
        found[_observed(new_year)] = "New Year's Day"
    found[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    found[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    found[easter_sunday(year) - timedelta(days=2)] = "Good Friday"
    found[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= JUNETEENTH_FIRST_YEAR:
        found[_observed(date(year, 6, 19))] = "Juneteenth"
    fourth = date(year, 7, 4)
    found[_observed(fourth)] = "Independence Day" if fourth.weekday() < 5 else "Independence Day (observed)"
    found[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    found[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    christmas = date(year, 12, 25)
    found[_observed(christmas)] = "Christmas Day" if christmas.weekday() < 5 else "Christmas Day (observed)"
    return found


def holidays(year: int) -> Dict[date, str]:
    """某年落在该年内的整日休市日（含顺延后的日期）。"""
    return {day: name for day, name in _holidays(year).items() if day.year == year}


def holiday_name(day: date) -> Optional[str]:
    # 顺延可能跨年：下一年的元旦落在周日 -> 那年的周一（同一年内）；上一年圣诞/元旦不会顺延进本年，故只查本年。
    return _holidays(day.year).get(day)


HOLIDAY_ZH = {"New Year's Day": "元旦", "Martin Luther King Jr. Day": "马丁·路德·金日", "Washington's Birthday": "总统日",
              "Good Friday": "耶稣受难日", "Memorial Day": "阵亡将士纪念日", "Juneteenth": "六月节", "Independence Day": "独立日",
              "Independence Day (observed)": "独立日（顺延休市）", "Labor Day": "劳动节", "Thanksgiving Day": "感恩节",
              "Christmas Day": "圣诞节", "Christmas Day (observed)": "圣诞节（顺延休市）"}


def holiday_zh(day: date) -> Optional[str]:
    name = holiday_name(day)
    return None if name is None else HOLIDAY_ZH.get(name, name)


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and holiday_name(day) is None


def is_half_day(day: date) -> bool:
    if not is_trading_day(day):
        return False
    if day.month == 11 and day.weekday() == 4 and (day - timedelta(days=1)) == _nth_weekday(day.year, 11, 3, 4):
        return True                                   # 感恩节次日
    if day.month == 7 and day.day == 3 and day.weekday() <= 3:
        return True                                   # 独立日前一交易日（7-4 是周二到周五）
    if day.month == 12 and day.day == 24 and day.weekday() <= 3:
        return True                                   # 圣诞前夜（12-25 是周二到周五）
    return False


def close_time(day: date) -> Optional[time]:
    """当日收盘时刻（美东）；休市日为 None。"""
    if not is_trading_day(day):
        return None
    return HALF_DAY_CLOSE if is_half_day(day) else REGULAR_CLOSE


def previous_trading_day(day: date) -> date:
    """严格早于 day 的最近一个交易日。"""
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def next_trading_day(day: date) -> date:
    """严格晚于 day 的最近一个交易日。"""
    cursor = day + timedelta(days=1)
    while not is_trading_day(cursor):
        cursor += timedelta(days=1)
    return cursor


def last_trading_day_on_or_before(day: date) -> date:
    return day if is_trading_day(day) else previous_trading_day(day)


def closed_full_days_between(start: datetime, end: datetime) -> int:
    """start 与 end 之间（美东日期，两端各自所在的那一天不算）整天休市的天数：周末与假日。
    用来把「研究快照多久没确认」从墙钟换成交易日口径——申报和研究只在交易日产生新内容。"""
    first, last = start.astimezone(NEW_YORK).date(), end.astimezone(NEW_YORK).date()
    count, cursor = 0, first + timedelta(days=1)
    while cursor < last:
        if not is_trading_day(cursor):
            count += 1
        cursor += timedelta(days=1)
    return count


def last_closed_session_day(now: datetime) -> date:
    """截至 now 已经收盘的最近一个交易日（美东）。盘中（含当天 13:00/16:00 之前）的当天不算已收盘。"""
    local = now.astimezone(NEW_YORK)
    today_close = close_time(local.date())
    if today_close is not None and local.time() >= today_close:
        return local.date()
    return previous_trading_day(local.date())
