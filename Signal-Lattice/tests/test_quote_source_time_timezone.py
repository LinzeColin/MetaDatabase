"""报价来源时间必须由 provider 按自己的发布约定盖时区，运行时不许替它猜。

线上事故（2026-09-14）：新浪把所有市场的报价时间都写成北京时间，美股也不例外。
运行时按标的所在交易所的时区去理解这个字段，美股整整偏 12 小时（冬令时 13 小时），
于是 source_time 永远「超前」，QUOTE_SOURCE_CLOCK_AHEAD 打满 8 个美股 ETF，
数据门 fail-closed，整站长期不出结论。

偏差方向随北京当天时刻翻转——北京上午misread 成过去、北京下午misread 成未来——
所以白天看着一切正常，傍晚才炸。只在一个时刻验证是发现不了的。

腾讯的约定不同：它写的是交易所本地时间（美股 16:00:01 正是收盘）。两家必须
分别处理，不能共用一套假设。
"""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from signal_lattice.live_config import default_universe
from signal_lattice.marketdata.sina import SinaQuoteProvider
from signal_lattice.marketdata.tencent import TencentQuoteProvider

# 2026-09-14 从 hq.sinajs.cn 抓到的真实一行。新浪在同一行里给了两个时间：
# 第 3 字段 "2026-09-14 18:53:42"（北京）和后面的 "Sep 14 06:53AM EDT"（纽约），
# 指的是同一瞬间。这正好把「哪个才是对的」钉死在测试里。
SINA_US_PAYLOAD = (
    'var hq_str_gb_spy="SPDR标普500 ETF,764.2900,0.85,2026-09-14 18:53:42,6.4600,'
    "764.7200,766.3800,763.6000,779.3700,627.3770,45512741,38964488,806197637937,"
    "0.00,--,0.00,0.00,0.00,0.00,1054832116,0,759.2600,-0.65,-4.94,"
    'Sep 14 06:53AM EDT,Sep 11 04:00PM EDT,757.8300,237614,1,2026";'
).encode("gbk")

# 腾讯没有配置美股（tencent_symbol=None），它实际覆盖的是 A 股与港股，
# 写的是交易所本地时间（A 股 15:00 收盘、美股 16:00 收盘都对得上）。
TENCENT_CN_PAYLOAD = (
    'v_sh600000="1~浦发银行~600000~9.40~9.38~9.39~123456~0~0~9.40~100~9.39~200~'
    '0~0~0~0~0~0~20260914150000~0.02~0.21~9.45~9.35~9.40~123456~115987~0~0";'
).encode("gbk")

# 用真实资产池里的 usSPY，避免测试里的标的定义和生产漂移。
US_SPY = next(item for item in default_universe() if item.symbol == "usSPY")

# 新浪那一行自报的纽约时间：Sep 14 06:53AM EDT。
EXPECTED_NEW_YORK = datetime(2026, 9, 14, 6, 53, 42, tzinfo=ZoneInfo("America/New_York"))


class SinaPublishesBeijingTime(unittest.TestCase):
    def setUp(self):
        observed = datetime(2026, 9, 14, 10, 53, 45, tzinfo=timezone.utc)
        self.quote = SinaQuoteProvider.parse(SINA_US_PAYLOAD, [US_SPY], observed_at=observed)["usSPY"]

    def test_source_time_is_timezone_aware(self):
        self.assertIsNotNone(self.quote.source_time.tzinfo, "provider 必须自己盖时区")

    def test_the_beijing_string_resolves_to_the_new_york_time_sina_itself_prints(self):
        self.assertEqual(self.quote.source_time, EXPECTED_NEW_YORK)

    def test_source_time_is_not_ahead_of_the_exchange_clock(self):
        exchange_now = datetime(2026, 9, 14, 6, 54, tzinfo=ZoneInfo("America/New_York"))
        self.assertLessEqual(self.quote.source_time, exchange_now, "来源时间超前交易所时钟就会整站阻断")

    def test_the_error_this_replaces_was_exactly_twelve_hours(self):
        wrong = self.quote.source_time.replace(tzinfo=None).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        naive_beijing = datetime(2026, 9, 14, 18, 53, 42)
        mistaken = naive_beijing.replace(tzinfo=ZoneInfo("America/New_York"))
        drift = (mistaken - self.quote.source_time).total_seconds() / 3600
        self.assertEqual(round(drift), 12, "这就是线上那 12 小时")
        del wrong


class TencentPublishesExchangeLocalTime(unittest.TestCase):
    def test_source_time_is_aware_and_read_as_exchange_local(self):
        observed = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc)
        cn = next(item for item in default_universe() if item.symbol == "sh600000")
        quote = TencentQuoteProvider.parse(TENCENT_CN_PAYLOAD, [cn], observed_at=observed)["sh600000"]
        self.assertIsNotNone(quote.source_time.tzinfo)
        self.assertEqual(
            quote.source_time,
            datetime(2026, 9, 14, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )


class ProvidersNeverReturnNaiveSourceTimes(unittest.TestCase):
    def test_both_providers_stamp_a_timezone(self):
        observed = datetime(2026, 9, 14, 10, 53, 45, tzinfo=timezone.utc)
        for name, quote in (
            ("sina", SinaQuoteProvider.parse(SINA_US_PAYLOAD, [US_SPY], observed_at=observed)["usSPY"]),
            (
                "tencent",
                TencentQuoteProvider.parse(
                    TENCENT_CN_PAYLOAD,
                    [next(item for item in default_universe() if item.symbol == "sh600000")],
                    observed_at=observed,
                )["sh600000"],
            ),
        ):
            with self.subTest(provider=name):
                self.assertIsNotNone(quote.source_time.tzinfo)


class BackoffStaysProportionate(unittest.TestCase):
    def test_a_failing_upstream_never_blanks_the_page_for_an_hour(self):
        from signal_lattice.live_runtime import COLLECTION_BACKOFF_MAX_SECONDS

        self.assertLessEqual(
            COLLECTION_BACKOFF_MAX_SECONDS,
            10 * 60,
            "退避上限过长会把一次上游抖动放大成长时间不出结论",
        )


if __name__ == "__main__":
    unittest.main()
