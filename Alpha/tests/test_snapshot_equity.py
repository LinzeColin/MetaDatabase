"""净值快照:已冻结本金时只按本系统账本算(R4 账目隔离),取不到价不编造点位,顺带记行情源健康。"""

import json
from datetime import datetime, timezone

import pytest

import scripts.snapshot_equity as snap
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.live_cycle import build_live_cycle

TUE = datetime(2026, 9, 29, 14, 15, tzinfo=timezone.utc)      # 周二 10:15 ET


class Quotes:
    def __init__(self, prices, broken=False):
        self.prices, self.broken = prices, broken
        self.asked = []

    def snapshots(self, symbols):
        self.asked.append(list(symbols))
        if self.broken:
            raise ConnectionError("行情源不可达")
        return {s: {"price": self.prices[s], "at": "x"} for s in symbols if s in self.prices}


def history(rt):
    return json.loads((rt / "equity_history.json").read_text())


def feed(rt):
    return json.loads((rt / "facts" / "quote_feed.json").read_text())


@pytest.fixture
def traded(shadow_env, tmp_path, make_clock, make_market):
    """影子盘跑两拍:买入 QQQ×4 并回灌入账(带手续费)。"""
    factory = create_session_factory(init_engine())
    clock = make_clock(TUE)
    cycle = build_live_cycle(factory=factory, kill_switch=KillSwitch(tmp_path / "KS"),
                             quotes=make_market(clock), now_fn=clock)
    cycle()
    clock.advance(seconds=30)
    assert cycle()["fills"] == 1
    return shadow_env, OrderStore(factory).own_book()


def test_shadow_equity_from_own_ledger_only(traded, monkeypatch):
    """净值 = 冻结本金 + 自有现金流(含费)+ 持仓×行情;把 owner 的钱写进 env,结果不变。"""
    rt, book = traded
    assert book.net == {"QQQ": 4}
    for key, val in (("ALPHA_REAL_POWER_USD", "99999"), ("ALPHA_ACCOUNT_CASH_USD", "88888")):
        monkeypatch.setenv(key, val)
    quotes = Quotes({"QQQ": 410.0})
    assert snap.main(quotes=quotes, fx=(0.65, True), now=TUE) == 0
    [pt] = history(rt)
    expected_usd = 1950.0 + book.cash_flow_usd + 4 * 410.0
    assert abs(pt["equity_usd"] - expected_usd) < 0.01
    assert abs(pt["cash_usd"] - (1950.0 + book.cash_flow_usd)) < 0.01 and pt["position_usd"] == 1640.0
    assert abs(pt["equity_aud"] - (3000 + (expected_usd - 1950.0) / 0.65)) < 0.01
    assert pt["baseline_aud"] == 3000.0
    assert quotes.asked == [["QQQ"]]
    assert feed(rt)["consecutive_failures"] == 0 and feed(rt)["last_ok_at"]


def test_empty_book_probes_spy_and_records_baseline(shadow_env):
    (shadow_env / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": "2026-09-01T00:00:00+00:00"}))
    quotes = Quotes({"SPY": 500.0})
    assert snap.main(quotes=quotes, fx=(0.65, True), now=TUE) == 0
    assert quotes.asked == [["SPY"]]
    assert history(shadow_env)[0]["equity_aud"] == 3000.0


def test_held_symbol_unpriced_records_no_point_and_counts_failure(traded):
    rt, _ = traded
    assert snap.main(quotes=Quotes({}, broken=True), fx=(0.65, True), now=TUE) == 0
    assert not (rt / "equity_history.json").exists()             # 不编造点位
    assert snap.main(quotes=Quotes({}), fx=(0.65, True), now=TUE) == 0
    assert feed(rt)["consecutive_failures"] == 2
    assert snap.main(quotes=Quotes({"QQQ": 400.0}), fx=(0.65, True), now=TUE) == 0
    assert feed(rt)["consecutive_failures"] == 0 and len(history(rt)) == 1
