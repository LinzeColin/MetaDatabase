"""ALPHA-LIVE-060 故障注入:断网/券商重启/进程被杀/时钟漂移/重复回调。

全部针对真实网关+存储+监督代码,断言故障后系统往「停」而非「乱」的方向倒下:
失败关闭、绝不重复提交、非法状态隔离、心跳丢失触发杀开关。
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.adapters.brokers.base import SystemMode
from backend.app.domain.state_machine import OrderState
from backend.app.execution.gateway import ExecutionGateway
from backend.app.execution.lease import LeaseManager
from backend.app.execution.ratelimit import BrokerRateLimiter, BusinessRateLimiter
from backend.app.notify.outbox import Outbox
from backend.app.risk.engine import RiskContext
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.supervisor import Supervisor

UTC = timezone.utc
NOW = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


class ControllableBroker:
    """可编排故障的假交易会话:断网、拒单、回调乱序、成交重复。"""

    def __init__(self):
        self.mode = "ok"
        self.place_calls = []
        self.broker_open_orders = {}
        self._seq = 0
        self.callback = None

    def place_order(self, **kw):
        if self.mode == "network_down":
            raise ConnectionError("网络中断")
        if self.mode == "broker_restart":
            raise ConnectionError("OpenD 重启中")
        self._seq += 1
        bid = f"MM{self._seq:04d}"
        self.place_calls.append({**kw, "broker_order_id": bid})
        if self.callback:
            self.callback(kw["remark"], bid)
        return {"broker_order_id": bid}

    def modify_order(self, broker_order_id, **kw):
        return {"broker_order_id": broker_order_id}

    def cancel_order(self, broker_order_id):
        return {"broker_order_id": broker_order_id}

    def unlock(self):
        pass

    def healthy(self):
        return self.mode == "ok"

    def open_orders_by_remark(self):
        return dict(self.broker_open_orders)


def build(tmp_path, now=NOW):
    engine = init_engine(f"sqlite:///{tmp_path / 'fault.sqlite'}")
    factory = create_session_factory(engine)
    store = OrderStore(factory)
    broker = ControllableBroker()
    lease = LeaseManager(factory, holder_id="w1", now_fn=lambda: now)
    lease.acquire()
    gw = ExecutionGateway(
        store=store, client=broker, lease=lease, mode=SystemMode.PAPER, now_fn=lambda: now,
        business_limiter=BusinessRateLimiter(store), broker_limiter=BrokerRateLimiter(now_fn=lambda: now),
    )
    return gw, store, broker, factory


def ok_risk(**over):
    kw = dict(side="BUY", symbol="SPY", market="US_ETF", quantity=3, price_usd=Decimal("100"),
              fx_usd_aud=Decimal("1"), now=NOW, quote_age_seconds=1.0, jurisdiction_verdict="ALLOW")
    kw.update(over)
    return RiskContext(**kw)


def submit(gw, key="k1", risk=None):
    return gw.submit_intent(idempotency_key=key, symbol="SPY", side="BUY", quantity=3,
                            currency="USD", strategy_source="S1_GOLD_BLEND",
                            limit_price=Decimal("100"), risk_ctx=risk or ok_risk())


# ---------- 断网 ----------

def test_network_loss_during_submit_fails_closed(tmp_path):
    gw, store, broker, _ = build(tmp_path)
    broker.mode = "network_down"
    with pytest.raises(ConnectionError):
        submit(gw, "net-1")
    order_id = store.find_order_by_idempotency_key("net-1")
    assert store.get_state(order_id) is OrderState.SUBMIT_FAILED  # 失败关闭,不悬挂
    assert store.idempotency_key_available("net-1") is False       # 幂等键保留


# ---------- 券商重启 + 恢复 ----------

def test_broker_restart_then_recovery_no_double_submit(tmp_path):
    gw, store, broker, _ = build(tmp_path)
    broker.mode = "broker_restart"
    with pytest.raises(ConnectionError):
        submit(gw, "restart-1")
    order_id = store.find_order_by_idempotency_key("restart-1")
    assert store.get_state(order_id) is OrderState.SUBMIT_FAILED

    # OpenD 恢复:恢复流程核对券商侧无此单 -> 保持 SUBMIT_FAILED,绝不重发
    broker.mode = "ok"
    report = gw.recover_in_flight()
    assert order_id not in report["adopted"]
    assert len(broker.place_calls) == 0                            # 零真实提交


def test_broker_restart_with_order_already_live_adopts(tmp_path):
    gw, store, broker, _ = build(tmp_path)
    order_id = store.create_intent(idempotency_key="live-1", symbol="SPY", side="BUY",
                                   quantity=3, currency="USD", strategy_source="S1_GOLD_BLEND")
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    broker.broker_open_orders = {"live-1": "MM7777"}               # 券商侧其实收到了
    report = gw.recover_in_flight()
    assert report["adopted"] == [order_id]
    assert store.get_state(order_id) is OrderState.SUBMITTED
    assert len(broker.place_calls) == 0                            # 恢复=归位,不重发


# ---------- 进程被杀 + 重启恢复 ----------

def test_process_kill_midflight_recovers_from_db(tmp_path):
    # 第一进程:提交到 SUBMITTING 后「被杀」(丢弃网关对象,不清库)
    gw1, store, broker, factory = build(tmp_path)
    order_id = store.create_intent(idempotency_key="kill-1", symbol="SPY", side="BUY",
                                   quantity=3, currency="USD", strategy_source="S1_GOLD_BLEND")
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    del gw1  # 模拟进程被杀

    # 第二进程:同库重建网关,恢复
    broker2 = ControllableBroker()
    lease2 = LeaseManager(factory, holder_id="w2", now_fn=lambda: NOW + timedelta(seconds=60))
    lease2.acquire()
    gw2 = ExecutionGateway(store=store, client=broker2, lease=lease2, mode=SystemMode.PAPER,
                           now_fn=lambda: NOW + timedelta(seconds=60))
    report = gw2.recover_in_flight()
    assert order_id in report["submit_failed"]                    # 券商无此单 -> 失败关闭
    assert store.get_state(order_id) is OrderState.SUBMIT_FAILED


# ---------- 时钟漂移 ----------

def test_clock_drift_future_quote_blocks_new_orders(tmp_path):
    from backend.app.risk.engine import evaluate

    gw, store, broker, _ = build(tmp_path)
    # 行情时间戳来自「未来」(时钟漂移):新鲜度守卫按不可信处理 -> 拒单
    v = evaluate(ok_risk(quote_age_seconds=-3.0))
    assert "RULE_MARKET_DATA_STALE" in v.triggered_rules
    assert v.allowed is False


def test_clock_drift_lease_expiry_prevents_stale_writer(tmp_path):
    gw, store, broker, factory = build(tmp_path)
    # 老进程时钟落后,租约实际已过期;新进程接管后老进程提交必须被挡
    thief = LeaseManager(factory, holder_id="w-new", now_fn=lambda: NOW + timedelta(seconds=120))
    thief.acquire()
    from backend.app.execution.gateway import LeaseLostError

    with pytest.raises(LeaseLostError):
        submit(gw, "drift-1")
    assert len(broker.place_calls) == 0


# ---------- 重复回调 ----------

def test_duplicate_fill_callbacks_idempotent(tmp_path):
    gw, store, broker, _ = build(tmp_path)
    order_id = submit(gw, "dup-1")
    gw.on_order_event(idempotency_key="dup-1", broker_order_id="MM0001", status="ACCEPTED")
    # 同一笔成交回调重复到达三次:数量不得叠加超卖
    for _ in range(3):
        gw.on_fill(idempotency_key="dup-1", quantity=3, price=Decimal("100"),
                   broker_execution_id="E-SAME")
    state = store.get_state(order_id)
    # 首次 3 股即 FILLED;后续重复回调触发非法迁移隔离(FILLED 后再来成交)
    assert state in (OrderState.FILLED, OrderState.UNKNOWN_RECONCILIATION_REQUIRED)
    # 无论哪种,系统都停在安全态:要么已完成,要么标记待对账停新单
    if state is OrderState.UNKNOWN_RECONCILIATION_REQUIRED:
        assert store.halt_new_orders() is True


def test_duplicate_order_event_out_of_order(tmp_path):
    gw, store, broker, _ = build(tmp_path)
    order_id = submit(gw, "ooo-1")
    # 乱序:先到 ACCEPTED,再迟到一个重复 SUBMITTED
    gw.on_order_event(idempotency_key="ooo-1", broker_order_id="MM0001", status="ACCEPTED")
    gw.on_order_event(idempotency_key="ooo-1", broker_order_id="MM0001", status="SUBMITTED")
    # 迟到的 SUBMITTED 是非法迁移(ACCEPTED->SUBMITTED),被隔离
    assert store.get_state(order_id) is OrderState.UNKNOWN_RECONCILIATION_REQUIRED
    assert store.halt_new_orders() is True


# ---------- 监督进程:心跳丢失自愈 ----------

def test_supervisor_kills_switch_on_heartbeat_loss(tmp_path):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'sup.sqlite'}"))
    clock = {"t": NOW}
    hb = HeartbeatStore(factory, now_fn=lambda: clock["t"])
    ob = Outbox(factory, now_fn=lambda: clock["t"])
    ks = KillSwitch(tmp_path / "KS")
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=ks,
                     expected_workers=("trading-worker",))
    hb.beat("trading-worker")
    clock["t"] = NOW + timedelta(seconds=200)  # 心跳停摆
    report = sup.check_once()
    assert ks.active()                          # 失败关闭:杀开关拍下
    assert ob.pending_count() == 1              # 告警入队
    assert "trading-worker" in report.stale
