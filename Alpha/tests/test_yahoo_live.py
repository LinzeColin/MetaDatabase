"""Yahoo 实时行情源:时间戳约定、失败省略、日线复权且不写缓存、实盘超时上限(全部假 JSON,不联网)。"""

from datetime import datetime, timezone

import pytest

from backend.app.backtest import data_sources
from backend.app.marketdata.yahoo_live import (
    DAILY_RETRIES, DAILY_TIMEOUT_SECONDS, QuoteUnavailable, YahooQuoteSource,
)
from backend.app.workers.live_cycle import quote_age_seconds

T0 = 1784730600          # 2026-07-22 14:30:00 UTC = 10:30:00 ET


def meta_json(sym, price, t):
    return {"chart": {"result": [{"meta": {"symbol": sym, "regularMarketPrice": price,
                                           "regularMarketTime": t}}], "error": None}}


def test_snapshot_time_roundtrips_quote_age():
    calls = []

    def fetch(url, **kw):
        calls.append((url, kw))
        return meta_json("SPY", 612.34, T0)

    src = YahooQuoteSource(fetch_json=fetch)
    snap = src.get_snapshot(["SPY"])
    assert snap["SPY"]["price"] == 612.34
    assert snap["SPY"]["update_time"] == "2026-07-22 10:30:00"          # 美东无时区
    now = datetime.fromtimestamp(T0 + 3, tz=timezone.utc)
    assert quote_age_seconds(snap["SPY"]["update_time"], now) == 3.0
    assert "interval=1m" in calls[0][0] and calls[0][1] == {"timeout": 8, "retries": 2}
    src.get_quote("SPY")
    src.get_quote("SPY")
    assert len(calls) == 3, "报价不缓存:快照 1 次 + 报价 2 次 = 3 次新请求"


def test_snapshot_omits_failed_symbols_never_raises():
    def fetch(url, **kw):
        sym = url.split("/chart/")[1].split("?")[0]
        if sym == "BIL":
            raise ConnectionError("假网络故障")
        if sym == "IEF":
            return meta_json("IEF", 0.0, T0)            # 价格非正
        if sym == "GLD":
            return meta_json("GDX", 50.0, T0)           # 代码不符
        return meta_json(sym, 100.0, T0)

    src = YahooQuoteSource(fetch_json=fetch)
    assert set(src.get_snapshot(["SPY", "BIL", "IEF", "GLD", "QQQ"])) == {"SPY", "QQQ"}
    for sym in ("BIL", "IEF", "GLD"):
        with pytest.raises(QuoteUnavailable):
            src.get_quote(sym)
    assert set(src.snapshots(["SPY", "BIL"])) == {"SPY"}


def _daily_json():
    ts = [1784640600, 1784727000, 1784813400]          # 07-21/22/23 13:30 UTC
    return {"chart": {"result": [{
        "timestamp": ts,
        "indicators": {"quote": [{"open": [10.0, 11.0, 12.0], "high": [10.5, 11.5, 12.5],
                                  "low": [9.5, 10.5, 11.5], "close": [10.0, 11.0, 12.0]}],
                       "adjclose": [{"adjclose": [9.0, 11.0, 12.0]}]}}]}}


def test_daily_bars_adjusted_and_no_cache_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)          # 回测缓存目录是相对路径:在空目录里跑,便于断言没写
    monkeypatch.setattr(data_sources, "_http_json", lambda url, **kw: _daily_json())
    bars = YahooQuoteSource().get_daily_bars("SPY", "2026-07-01", "2026-07-23")
    assert [b["day"] for b in bars] == ["2026-07-21", "2026-07-22", "2026-07-23"]
    assert bars[0]["close"] == 9.0 and bars[0]["open"] == pytest.approx(9.0)   # 系数 0.9
    assert bars[0]["high"] == pytest.approx(9.45)
    assert bars[2]["close"] == 12.0
    assert not (tmp_path / "data").exists(), "实盘日线不得读写回测缓存"
    assert YahooQuoteSource().daily_closes("SPY", "2026-07-01", "2026-07-23")[-1] == ("2026-07-23", 12.0)


def test_daily_timeout_bounded(monkeypatch):
    """实盘日线:timeout=10、retries=1(6 标的最坏约 1 分钟,不撞 300 秒看门狗)。"""
    seen = {}

    def fake(url, **kw):
        seen.update(kw)
        return _daily_json()

    monkeypatch.setattr(data_sources, "_http_json", fake)
    YahooQuoteSource().get_daily_bars("SPY", "2026-07-01", "2026-07-23")
    assert seen == {"timeout": 10, "retries": 1}
    assert (DAILY_TIMEOUT_SECONDS, DAILY_RETRIES) == (10, 1)
    assert (data_sources.YahooDailySource().timeout, data_sources.YahooDailySource().retries) == (30, 3)
