"""测试公共件:全程离线(非回环连接直接抛错)+ 影子盘假行情与可推进时钟。"""

from __future__ import annotations

import socket
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

ET = ZoneInfo("America/New_York")


def _loopback(host) -> bool:
    h = "" if host is None else str(host)
    return h in ("", "localhost", "::1") or h.startswith("127.")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """测试不许联网:非回环地址的连接与域名解析一律抛错(行情/SMTP 全用假件)。"""
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _loopback(address[0]):
            raise OSError(f"测试禁止联网: {address}")
        return real_connect(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _loopback(host):
            raise socket.gaierror(f"测试禁止联网: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


class Clock:
    """注入时钟:每次读取前进 step(默认 30 毫秒,满足券商频控的最小间隔),可整段推进。"""

    def __init__(self, start: datetime, step: timedelta = timedelta(milliseconds=30)) -> None:
        self.t = start
        self.step = step

    def __call__(self) -> datetime:
        self.t += self.step
        return self.t

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)

    def set(self, t: datetime) -> None:
        self.t = t


#: 默认行情:QQQ 最强上升;SPY 次之;其余缓跌(低于 SMA200,不合格)
DEFAULT_SLOPES = {"SPY": 0.001, "EFA": -0.0005, "QQQ": 0.002, "GLD": -0.0005, "IEF": -0.0005}
DEFAULT_PRICES = {"SPY": 300.0, "EFA": 80.0, "QQQ": 400.0, "GLD": 250.0, "IEF": 95.0, "BIL": 91.5}


class FakeMarket:
    """交易循环读协议的假件:get_quote / get_snapshot / get_daily_bars。

    日线 = 截至时钟当天(含当天未收盘那根)的 n 个工作日,按日增长率回推;
    报价时间戳 = 时钟当前时刻 - lag 秒。
    """

    def __init__(self, clock: Clock, *, n_days: int = 320) -> None:
        self.clock = clock
        self.slopes = dict(DEFAULT_SLOPES)
        self.prices = dict(DEFAULT_PRICES)
        self.snapshot_lag = 1.0
        self.quote_lag = 1.0
        self.fail_daily = False
        self.today_close: dict[str, float] = {}
        self.n_days = n_days

    def get_quote(self, sym):
        from backend.app.marketdata.yahoo_live import LiveQuote, QuoteUnavailable
        if sym not in self.prices:
            raise QuoteUnavailable(sym)
        return LiveQuote(symbol=sym, price=self.prices[sym],
                         ts_utc=self.clock.t - timedelta(seconds=self.quote_lag))

    def get_snapshot(self, symbols):
        stamp = (self.clock.t - timedelta(seconds=self.snapshot_lag)).astimezone(ET)
        return {s: {"price": self.prices[s], "update_time": stamp.strftime("%Y-%m-%d %H:%M:%S")}
                for s in symbols if s in self.prices}

    def get_daily_bars(self, sym, start, end):
        if self.fail_daily:
            raise ConnectionError("假日线源故障")
        days: list[date] = []
        d = self.clock.t.astimezone(ET).date()
        while len(days) < self.n_days:
            if d.weekday() < 5:
                days.append(d)
            d -= timedelta(days=1)
        days.reverse()
        g, p = self.slopes.get(sym, 0.0), self.prices[sym]
        rows = []
        for i, day in enumerate(days):
            close = p / (1 + g) ** (len(days) - 1 - i)
            if i == len(days) - 1 and sym in self.today_close:
                close = self.today_close[sym]
            rows.append({"day": day.isoformat(), "open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close})
        return rows


@pytest.fixture
def make_market():
    return FakeMarket


@pytest.fixture
def make_clock():
    return Clock


@pytest.fixture
def shadow_env(tmp_path, monkeypatch):
    """影子盘运行环境:独立运行目录/库/刹车文件,清掉券商与实盘相关键。返回运行目录。"""
    from backend.app.workers.shadow_cycle import FORBIDDEN_ENV

    rt = tmp_path / "rt"
    rt.mkdir()
    monkeypatch.setenv("ALPHA_MODE", "SHADOW")
    monkeypatch.setenv("ALPHA_RUNTIME_DIR", str(rt))
    monkeypatch.setenv("ALPHA_DATABASE_URL", f"sqlite:///{tmp_path / 'alpha.sqlite'}")
    monkeypatch.setenv("ALPHA_KILL_SWITCH_PATH", str(rt / "KILL_SWITCH"))
    for key in FORBIDDEN_ENV + ("LIVE_TRADING_ENABLED", "ALPHA_ALERT_WEBHOOK"):
        monkeypatch.delenv(key, raising=False)
    return rt
