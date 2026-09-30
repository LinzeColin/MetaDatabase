"""实时层（每 60 秒）：读研究产物 -> 批量报价 -> 时效门 -> 中枢 -> 记分簿 -> 报告。网络一律替身。"""

import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from signal_lattice.ledger import Ledger
from signal_lattice.live_config import LiveSettings
from signal_lattice.live_runtime import BENCHMARK_SYMBOL, LiveEngine, LiveStore
from signal_lattice.marketdata.base import MarketDataError
from signal_lattice.marketdata.models import Bar, Quote
from signal_lattice.serialization import strict_json_dumps
from hub_fixtures import COMMERCIAL, EVENT, filler, record, sec_link, seed_shadow_evidence, standard_pool, write_research_dir

SESSION = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)          # 美东 11:00，开市
AFTER_CLOSE = datetime(2026, 9, 30, 20, 10, tzinfo=timezone.utc)     # 美东 16:10，已收盘


def weekdays(end: str, n: int):
    days, d = [], date.fromisoformat(end)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


class FakeGateway:
    """报价按需构造；日线按代码给。fetch_bars 记录被要求刷新的次数。"""

    def __init__(self, now, *, price=10.0, missing=(), stale=(), nan=(), bars=None, fail_quotes=False):
        self.now, self.price, self.missing, self.stale, self.nan = now, price, set(missing), set(stale), set(nan)
        self.bars, self.fail_quotes = bars or {}, fail_quotes
        self.quote_calls = 0
        self.bar_calls = []
        self.last_bar_quality = {}

    def fetch_quotes(self, instruments):
        self.quote_calls += 1
        if self.fail_quotes:
            return {}, ["SINA_QUOTE:HTTP_REQUEST_FAILED"]
        out = {}
        for item in instruments:
            if item.symbol in self.missing:
                continue
            source = self.now - timedelta(seconds=20) if item.symbol not in self.stale else self.now - timedelta(days=9)
            price = math.nan if item.symbol in self.nan else self.price
            out[item.symbol] = Quote(item.symbol, price, "USD", item.timezone, "sina_quote", source, self.now)
        return out, []

    def fetch_bars(self, item, *, refresh=False):
        self.bar_calls.append((item.symbol, refresh))
        if item.symbol not in self.bars:
            raise MarketDataError("BARS_MISSING:%s" % item.symbol)
        return self.bars[item.symbol]


def make_bars(symbol, days, start=10.0, daily=0.0, volume=2_000_000.0):
    price, out = start, []
    for day in days:
        out.append(Bar(symbol, day, price, price, price, price, volume, "America/New_York", "fixture", datetime(2026, 9, 30, tzinfo=timezone.utc)))
        price *= 1.0 + daily
    return out


class EngineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.research = self.root / "research"
        write_research_dir(self.research, standard_pool())
        base = LiveSettings.from_env(Path(__file__).resolve().parents[1])
        self.settings = replace(base, state_dir=self.root / "state", research_dir=self.research, backtest_dir=self.root / "bt")
        # 规则自证门默认要有证据才放行建议：这里让前向证据 (b) 达标（8 条已结算的影子候选、命中 8/8），
        # 这些测试要验的是实时层的建议流程；自证门本身的测试在 test_proof_gate.py。
        seed_shadow_evidence(self.settings.state_dir / "ledger.sqlite")

    def engine(self, gateway):
        engine = LiveEngine(self.settings)
        engine.gateway = gateway
        return engine


class SessionRunTests(EngineCase):
    def test_a_full_round_publishes_the_recommendation_with_every_section(self):
        gateway = FakeGateway(SESSION)
        report = self.engine(gateway).run_once(SESSION)
        self.assertEqual(report["state"], "DATA_READY")
        self.assertEqual(report["decision"]["state"], "RECOMMENDATION")
        self.assertEqual(report["decision"]["primary_symbol"], "ALPHA")
        self.assertEqual(report["decision"]["action_code"], "RESEARCH_FOLLOW_LONG")
        self.assertEqual(gateway.quote_calls, 1)                                        # 候选 + IWM 一次批量取完
        self.assertEqual({r["branch_id"] for r in report["receipts"]},
                         {"equity-event-atlas", "bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-foresight-signal",
                          "global-equity-lead-lag-atlas"})
        for receipt in report["receipts"]:
            self.assertEqual(set(receipt["verdict_counts"]), {"PASS", "ABSTAIN", "FAILED"})
            self.assertTrue(receipt["snapshot_hash"])
        self.assertIn(BENCHMARK_SYMBOL, report["quotes"])
        self.assertTrue(report["candidates"])
        self.assertEqual(report["candidates"][0]["rank"], 1)
        self.assertEqual(report["data_cutoff"], "2026-09-29")
        self.assertEqual(report["research"]["research_max_age_hours"], 36.0)
        self.assertEqual(report["ledger"]["sample_status"], "SAMPLE_INSUFFICIENT")
        self.assertEqual(report["contribution_weights"]["weight_mode"], "COLD_START_EQUAL")
        self.assertEqual(report["backtest"]["status"], "NOT_RUN")
        self.assertFalse(report["automatic_trading"])
        strict_json_dumps(report)                                                       # 严格 JSON：没有 NaN / Infinity

    def test_the_published_conditions_are_persisted_and_the_report_is_on_disk(self):
        engine = self.engine(FakeGateway(SESSION))
        engine.run_once(SESSION)
        state = json.loads((self.settings.state_dir / "hub_state.json").read_text())
        self.assertEqual(state["published"]["ALPHA"]["status"], "ACTIVE")
        self.assertEqual(LiveStore(self.settings.state_dir).latest()["decision"]["primary_symbol"], "ALPHA")
        again = engine.run_once(SESSION + timedelta(minutes=1))
        self.assertEqual(again["decision"]["invalidation"]["published_at"], state["published"]["ALPHA"]["published_at"])

    def test_a_stale_candidate_quote_degrades_that_candidate_not_the_product(self):
        report = self.engine(FakeGateway(SESSION, stale=["ALPHA"])).run_once(SESSION)
        self.assertEqual(report["state"], "DATA_READY")
        self.assertIn("ALPHA", report["degraded_symbols"])
        self.assertNotIn("ALPHA", report["quotes"])                                    # 过期报价不当作当前价格展示
        self.assertNotEqual(report["decision"].get("primary_symbol"), "ALPHA")
        alpha = next(c for c in report["candidates"] if c["symbol"] == "ALPHA")
        self.assertFalse(alpha["gates"]["quote"]["ok"])
        self.assertIsNone(alpha["price"])

    def test_a_nonfinite_quote_is_quarantined_and_never_serialized(self):
        report = self.engine(FakeGateway(SESSION, nan=["ALPHA"])).run_once(SESSION)
        self.assertEqual(report["state"], "DATA_READY")
        self.assertIn("QUOTE_NONFINITE:ALPHA", report["freshness_findings"])
        self.assertNotIn("NaN", (self.settings.state_dir / "latest.json").read_text())

    def test_all_quotes_missing_blocks_and_counts_as_a_collection_failure(self):
        engine = self.engine(FakeGateway(SESSION, fail_quotes=True))
        report = engine.run_once(SESSION)
        self.assertEqual(report["state"], "SYSTEM_BLOCKED")
        self.assertEqual(report["decision"]["blocked_reason"], "MARKET_DATA_UNAVAILABLE")
        self.assertIsNone(report["decision"]["action"])
        self.assertEqual(report["collection_request_accounting"]["consecutive_failure_count"], 1)
        self.assertIn("SINA_QUOTE:HTTP_REQUEST_FAILED", report["freshness_findings"])

    def test_stale_research_blocks_before_any_request_goes_out(self):
        write_research_dir(self.research, standard_pool(), generated_at=SESSION - timedelta(hours=40))
        gateway = FakeGateway(SESSION)
        report = self.engine(gateway).run_once(SESSION)
        self.assertEqual(report["state"], "SYSTEM_BLOCKED")
        self.assertEqual(report["decision"]["blocked_reason"], "RESEARCH_SNAPSHOT_STALE")
        self.assertEqual(gateway.quote_calls, 0)
        self.assertEqual(report["collection_request_accounting"]["consecutive_failure_count"], 0)     # 研究层的问题不让行情源退避
        self.assertEqual(report["message"], report["decision"]["message"])

    def test_missing_research_directory_blocks_with_a_plain_message(self):
        settings = replace(self.settings, research_dir=self.root / "nowhere")
        engine = LiveEngine(settings)
        engine.gateway = FakeGateway(SESSION)
        report = engine.run_once(SESSION)
        self.assertEqual(report["state"], "SYSTEM_BLOCKED")
        self.assertIn("研究层还没有产出", report["message"])

    def test_unexpected_failure_replaces_the_previous_ready_report(self):
        engine = self.engine(FakeGateway(SESSION))
        self.assertEqual(engine.run_once(SESSION)["state"], "DATA_READY")

        class Boom(FakeGateway):
            def fetch_quotes(self, instruments):
                raise RuntimeError("boom")

        engine.gateway = Boom(SESSION)
        report = engine.run_once(SESSION + timedelta(minutes=1))
        self.assertEqual(report["state"], "SYSTEM_BLOCKED")
        self.assertEqual(report["blocked_reason"], "UNEXPECTED_RUNTIME_FAILURE")
        self.assertEqual(LiveStore(self.settings.state_dir).latest()["state"], "SYSTEM_BLOCKED")

    def test_live_daily_bars_drive_the_liquidity_gate(self):
        days = weekdays("2026-09-29", 30)
        thin = {s: make_bars(s, days, volume=1_000.0) for s in ("ALPHA", "BETA")}          # 1 万美元/天
        report = self.engine(FakeGateway(SESSION, bars=thin)).run_once(SESSION)
        self.assertEqual(report["decision"]["state"], "NO_ACTION")
        alpha = next(c for c in report["candidates"] if c["symbol"] == "ALPHA")
        self.assertIn("流动性", alpha["gate_summary"])
        liquid = {s: make_bars(s, days, volume=5_000_000.0) for s in ("ALPHA", "BETA")}
        report = self.engine(FakeGateway(SESSION, bars=liquid)).run_once(SESSION + timedelta(minutes=1))
        self.assertEqual(report["decision"]["state"], "RECOMMENDATION")
        self.assertEqual(report["decision"]["gates"]["liquidity"]["source"], "live_daily_bars")

    def test_intraday_bar_of_today_is_not_used_as_a_close(self):
        engine = self.engine(FakeGateway(SESSION))
        days = weekdays("2026-09-30", 3)
        bars = make_bars("X", days)
        self.assertEqual([b.day for b in engine._completed_us_closes(bars, SESSION)], days[:2])
        self.assertEqual([b.day for b in engine._completed_us_closes(bars, AFTER_CLOSE)], days)

    def test_the_round_budget_covers_a_full_batch_of_quotes_plus_a_few_bar_requests(self):
        from signal_lattice.live_runtime import MAX_PROVIDER_REQUESTS_PER_DAY, MAX_PROVIDER_REQUESTS_PER_ROUND
        self.assertGreaterEqual(MAX_PROVIDER_REQUESTS_PER_DAY, 1440 + 300)
        self.assertGreaterEqual(MAX_PROVIDER_REQUESTS_PER_ROUND, 20)


class LedgerIntegrationTests(EngineCase):
    def bars_through(self, end, n=40, ends_at=None):
        days = weekdays(end, n)
        return days, {s: make_bars(s, days, daily=0.004, volume=5_000_000.0) for s in ("ALPHA", "BETA", BENCHMARK_SYMBOL, *[f"E{i:02d}" for i in range(20)],
                                                                                      *[f"C{i:02d}" for i in range(20)], *[f"B{i:02d}" for i in range(20)])}

    def test_nothing_is_recorded_before_the_close(self):
        days, bars = self.bars_through("2026-09-30")
        report = self.engine(FakeGateway(SESSION, bars=bars)).run_once(SESSION)
        self.assertEqual(report["ledger"]["recorded_days"], 0)

    def test_after_the_close_one_row_is_recorded_once_with_stock_iwm_and_a_reproducible_control(self):
        days, bars = self.bars_through("2026-09-30")
        engine = self.engine(FakeGateway(AFTER_CLOSE, bars=bars))
        report = engine.run_once(AFTER_CLOSE)
        self.assertEqual(report["ledger"]["recorded_days"], 1)
        self.assertEqual(report["ledger"]["last_run"]["recorded"], True)
        ledger = Ledger(self.settings.state_dir / "ledger.sqlite")
        try:
            row = ledger.db.execute("SELECT * FROM daily_record").fetchone()
            self.assertEqual((row["trading_day"], row["decision_state"], row["symbol"]), ("2026-09-30", "RECOMMENDATION", "ALPHA"))
            self.assertAlmostEqual(row["close_price"], bars["ALPHA"][-1].close)
            self.assertAlmostEqual(row["iwm_close"], bars[BENCHMARK_SYMBOL][-1].close)
            self.assertIsNotNone(row["watchlist_json"])
            control = row["control_symbol"]
        finally:
            ledger.close()
        again = engine.run_once(AFTER_CLOSE + timedelta(minutes=1))
        self.assertEqual(again["ledger"]["recorded_days"], 1)                             # 同一天不重复记
        self.assertEqual(self.recorded_control(), control)

    def recorded_control(self):
        ledger = Ledger(self.settings.state_dir / "ledger.sqlite")
        try:
            return ledger.db.execute("SELECT control_symbol FROM daily_record").fetchone()[0]
        finally:
            ledger.close()

    def test_no_row_is_written_when_the_days_bar_is_not_published_yet_and_it_retries(self):
        days, bars = self.bars_through("2026-09-29")                                       # 缺 9-30 这根
        engine = self.engine(FakeGateway(AFTER_CLOSE, bars=bars))
        report = engine.run_once(AFTER_CLOSE)
        self.assertEqual(report["ledger"]["recorded_days"], 0)
        self.assertIn("error", report["ledger"]["last_run"])
        days, bars = self.bars_through("2026-09-30")
        retry_time = AFTER_CLOSE + timedelta(minutes=16)
        engine.gateway = FakeGateway(retry_time, bars=bars)
        # 缺陷 #8：当日 bar 没出来时按 15 分钟一次重试（以前每分钟都刷新请求），所以重试要等到 15 分钟之后
        self.assertEqual(engine.run_once(retry_time)["ledger"]["recorded_days"], 1)

    def test_while_todays_bar_is_late_the_ledger_retries_every_fifteen_minutes_not_every_minute(self):
        """缺陷 #8：当日 bar 迟迟不出，以前每分钟都删缓存、重新请求。现在 15 分钟一次，直到次日开盘前。"""
        days, late = self.bars_through("2026-09-29")
        gateway = FakeGateway(AFTER_CLOSE, bars=late)
        engine = self.engine(gateway)
        first = engine.run_once(AFTER_CLOSE)
        refreshes = lambda: len([call for call in gateway.bar_calls if call[1]])
        first_refreshes = refreshes()
        self.assertGreater(first_refreshes, 0)
        self.assertIn("error", first["ledger"]["last_run"])
        for minute in (1, 2, 7, 14):
            gateway.now = AFTER_CLOSE + timedelta(minutes=minute)
            again = engine.run_once(AFTER_CLOSE + timedelta(minutes=minute))
            self.assertEqual(refreshes(), first_refreshes, "第 %d 分钟不该再刷新请求" % minute)
            self.assertIn("deferred_until", again["ledger"]["last_run"])
        gateway.now = AFTER_CLOSE + timedelta(minutes=16)
        engine.run_once(AFTER_CLOSE + timedelta(minutes=16))
        self.assertGreater(refreshes(), first_refreshes)                      # 15 分钟到了，重试一次
        after_midnight = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)      # 美东 1 日 01:00：仍在次日开盘之前，9-30 还能补记
        days, full = self.bars_through("2026-09-30")
        engine.gateway = FakeGateway(after_midnight, bars=full)
        self.assertEqual(engine.run_once(after_midnight)["ledger"]["recorded_days"], 1)

    def test_a_late_night_run_after_the_next_open_no_longer_backfills_yesterday(self):
        next_morning = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)      # 美东 10-01 10:00，10-01 已开市
        days, bars = self.bars_through("2026-09-30")
        engine = self.engine(FakeGateway(next_morning, bars=bars))
        self.assertEqual(engine.run_once(next_morning)["ledger"]["recorded_days"], 0)

    def test_an_intraday_run_never_settles_with_the_half_day_bar_of_today(self):
        """缺陷 #3：美东 11:00 盘中运行，出场日正好是今天时，不得用今天那根盘中半天的 bar 结算。"""
        days, bars = self.bars_through("2026-09-30", n=60)              # 含今天（9-30）那根
        ledger = Ledger(self.settings.state_dir / "ledger.sqlite")
        try:
            decision = {"state": "RECOMMENDATION", "primary_symbol": "ALPHA", "primary_name": "ALPHA Inc", "market_cap_usd": 1.2e9, "watchlist": [],
                        "support": {"branches": []}, "data_chain": {"snapshot_sha256": "a" * 64}}
            day0 = days[-22].isoformat()                                # 入场 days[-21]，第 20 个交易日出场 = days[-1] = 今天
            ledger.record_day(day0, decision, close_price=dict((b.day.isoformat(), b.close) for b in bars["ALPHA"])[day0],
                              iwm_close=dict((b.day.isoformat(), b.close) for b in bars[BENCHMARK_SYMBOL])[day0], now=SESSION - timedelta(days=40))
        finally:
            ledger.close()
        during = self.engine(FakeGateway(SESSION, bars=bars)).run_once(SESSION)           # 美东 11:00
        self.assertEqual(during["ledger"]["settled"]["20"], 0)
        self.assertEqual(during["ledger"]["last_run"]["settled"], [])
        after = self.engine(FakeGateway(AFTER_CLOSE, bars=bars)).run_once(AFTER_CLOSE)      # 美东 16:10：今天已收盘
        self.assertEqual(after["ledger"]["settled"]["20"], 1)
        self.assertEqual(after["ledger"]["last_run"]["settled"][0]["exit_day"], "2026-09-30")

    def test_a_broken_ledger_never_withdraws_the_conclusion(self):
        engine = self.engine(FakeGateway(AFTER_CLOSE, bars={}))                             # 没有任何日线
        report = engine.run_once(AFTER_CLOSE)
        self.assertEqual(report["state"], "DATA_READY")
        self.assertEqual(report["decision"]["state"], "RECOMMENDATION")
        self.assertEqual(report["ledger"]["recorded_days"], 0)

    def test_a_no_action_day_is_recorded_with_iwm_only(self):
        write_research_dir(self.research, standard_pool(), statuses={COMMERCIAL: "ABSTAIN"})
        days, bars = self.bars_through("2026-09-30")
        report = self.engine(FakeGateway(AFTER_CLOSE, bars=bars)).run_once(AFTER_CLOSE)
        self.assertEqual(report["decision"]["state"], "NO_ACTION")
        self.assertEqual(report["ledger"]["no_action_days"], 1)

    def test_twenty_trading_days_later_the_recommendation_is_settled_and_still_says_insufficient(self):
        days, bars = self.bars_through("2026-09-30", n=60)
        self.engine(FakeGateway(AFTER_CLOSE, bars=bars)).run_once(AFTER_CLOSE)
        later_days = weekdays("2026-11-04", 60)
        later_bars = {s: make_bars(s, later_days, daily=0.004, volume=5_000_000.0) for s in bars}
        # 让 9-30 之后的日历再走 21 个交易日
        extended = {s: [b for b in later_bars[s]] for s in later_bars}
        write_research_dir(self.research, standard_pool(), generated_at=datetime(2026, 11, 4, 19, tzinfo=timezone.utc))
        later = datetime(2026, 11, 4, 21, tzinfo=timezone.utc)
        report = self.engine(FakeGateway(later, bars=extended)).run_once(later)
        self.assertEqual(report["ledger"]["settled"]["20"], 1)
        self.assertEqual(report["ledger"]["sample_status"], "SAMPLE_INSUFFICIENT")        # 只有 1 条 < 8
        # 正式记分簿本身不含数字。（setUp 为了让自证门达标，另外种了 8 条已结算的影子候选，它们在 ledger["shadow"] 里，样本已够，自然有数字。）
        self.assertNotIn("hit_rate", json.dumps({k: v for k, v in report["ledger"].items() if k != "shadow"}))


if __name__ == "__main__":
    unittest.main()
