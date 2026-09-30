"""业务健康判据(R3:心跳只证明进程在转,判据必须绑业务产出)。全部注入时钟与假行情,不联网。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.adapters.brokers.base import BrokerError
from backend.app.adapters.brokers.sim_broker import SimBroker
from backend.app.backtest.fees import FeeModel
from backend.app.domain.models import SimOrder
from backend.app.health import evaluate_health
from backend.app.notify.outbox import AlertBook
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.live_cycle import build_live_cycle

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
TUE = datetime(2026, 9, 29, 14, 15, tzinfo=UTC)      # 周二 10:15 ET


class FakeHeartbeats:
    def __init__(self, **workers):
        self.workers = workers

    def snapshot(self):
        return {n: {"beat_at": NOW.isoformat(), "status": "RUNNING", "detail": d}
                for n, d in self.workers.items()}


@pytest.fixture
def env(shadow_env, tmp_path):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'alpha.sqlite'}"))
    return shadow_env, factory


def item(items, prefix):
    return next(i for i in items if i.key.split(":")[0] == prefix)


def health(factory, *, now=NOW, hb=None, alerts=None):
    return evaluate_health(session_factory=factory, heartbeats=hb, kill_switch=None,
                           now=now, alerts=alerts)


def test_equity_snapshot_46min_red(env):
    rt, factory = env
    for minutes, red in ((46, True), (44, False)):
        (rt / "equity_history.json").write_text(json.dumps(
            [{"at": (NOW - timedelta(minutes=minutes)).isoformat(), "equity_aud": 3000}]))
        assert item(health(factory), "equity_stale").bad is red, minutes


def test_quote_feed_3_failures_red_and_no_sim_fill(env):
    """行情源连续失败 3 次判红;同期模拟券商取不到行情,不产生任何成交。"""
    rt, factory = env
    (rt / "facts").mkdir()
    feed = rt / "facts" / "quote_feed.json"
    feed.write_text(json.dumps({"consecutive_failures": 2, "last_error": "超时"}))
    assert item(health(factory), "quote_feed").bad is False
    feed.write_text(json.dumps({"consecutive_failures": 3, "last_error": "超时"}))
    assert item(health(factory), "quote_feed").bad is True

    class Down:
        def get_quote(self, sym):
            from backend.app.marketdata.yahoo_live import QuoteUnavailable
            raise QuoteUnavailable(sym)

    sim = SimBroker(factory, quotes=Down(), fee_model=FeeModel.from_yaml(),
                    start_capital_usd=1950.0, now_fn=lambda: TUE)
    from decimal import Decimal
    with pytest.raises(BrokerError):
        sim.place_order(symbol="SPY", side="BUY", quantity=1, order_type="LIMIT",
                        limit_price=Decimal("300"), trd_env="LOCAL", remark="S1-x")
    with factory() as s:
        assert [r.status for r in s.scalars(select(SimOrder))] == ["FAILED"]
    assert sim.positions() == {} and float(sim.cash()) == 1950.0


def test_blocked_over_10min_red(env):
    _, factory = env
    hb = FakeHeartbeats(**{"trading-worker": "{'status': 'BLOCKED_ON_FEED', 'retrying': True}"})
    alerts = AlertBook(factory, now_fn=lambda: NOW)
    assert item(health(factory, hb=hb, alerts=alerts), "blocked").red is False   # 刚开始空转
    alerts.observe("blocked:trading-worker", True, hold_seconds=600)             # 状态簿记下起点
    later = NOW + timedelta(minutes=11)
    alerts_later = AlertBook(factory, now_fn=lambda: later)
    assert item(health(factory, now=later, hb=hb, alerts=alerts_later), "blocked").red is True
    soon = NOW + timedelta(minutes=5)
    assert item(health(factory, now=soon, hb=hb, alerts=alerts_later), "blocked").red is False


def test_eval_blocked_when_plan_but_no_submit(env):
    """完成记录里计划非空而 submitted=0(风控/行情全拒)判 eval_blocked——抓「0 单」。"""
    rt, factory = env
    rec = {"date": "2026-09-29", "completed_at": "2026-09-29T14:20:00+00:00",
           "plan": ["BUY QQQx4"], "submitted": 0, "rejected": 1, "skipped": 0,
           "reject_rules": ["RULE_MARKET_DATA_STALE"], "skip_reasons": []}
    (rt / "last_eval_result.json").write_text(json.dumps(rec))
    it = item(health(factory), "eval_blocked")
    assert it.bad is True and "RULE_MARKET_DATA_STALE" in it.detail
    rec.update(plan=[], submitted=0, rejected=0, reject_rules=[])
    (rt / "last_eval_result.json").write_text(json.dumps(rec))
    assert item(health(factory), "eval_blocked").bad is False        # 无需调仓不是被拦


def test_mode_drift_red(env):
    """心跳报 MICRO_LIVE 而配置是 SHADOW:自动升级会直接落到这一条。"""
    _, factory = env
    bad = FakeHeartbeats(**{"trading-worker": "{'mode': 'MICRO_LIVE'}"})
    it = item(health(factory, hb=bad), "mode_drift")
    assert it.bad is True and "MICRO_LIVE" in it.detail
    ok = FakeHeartbeats(**{"trading-worker": "{'mode': 'SHADOW'}"})
    assert item(health(factory, hb=ok), "mode_drift").bad is False


def test_shadow_ledger_mismatch_red(env, tmp_path, make_clock, make_market):
    """簿里有成交而账本超过 2 分钟未入账判红;下一拍回灌对齐后变绿。"""
    rt, factory = env
    clock = make_clock(TUE)
    market = make_market(clock)
    cycle = build_live_cycle(factory=factory, kill_switch=KillSwitch(tmp_path / "KS"),
                             quotes=market, now_fn=clock)
    assert cycle()["submitted"] == 1
    assert item(health(factory, now=clock.t), "ledger_mismatch").bad is False   # 刚成交,还在宽限内
    clock.advance(minutes=3)
    it = item(health(factory, now=clock.t), "ledger_mismatch")
    assert it.bad is True and "未入账" in it.detail
    assert cycle()["fills"] == 1
    assert item(health(factory, now=clock.t), "ledger_mismatch").bad is False
