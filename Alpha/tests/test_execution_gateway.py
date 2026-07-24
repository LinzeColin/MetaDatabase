"""ALPHA-LIVE-035:执行网关——SIMULATE 端到端、竞态、恢复、门禁封锁、频控。"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.adapters.brokers.base import SystemMode
from backend.app.domain.state_machine import OrderState
from backend.app.execution.gates import sha256_of_file, validate_authorization
from backend.app.execution.gateway import ExecutionGateway, GateBlockedError, LeaseLostError
from backend.app.execution.lease import LeaseManager
from backend.app.execution.ratelimit import (
    BrokerRateLimiter,
    BusinessRateLimiter,
    RateLimitExceededError,
)
from backend.app.risk.engine import RiskContext
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore

UTC = timezone.utc
NOW = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


class FakeTradingClient:
    """假交易会话:可编排「回调先于返回」竞态;记录全部调用。"""

    def __init__(self):
        self.place_calls = []
        self.cancel_calls = []
        self.modify_calls = []
        self.unlock_calls = 0
        self.callback_before_return = None  # (gateway 注入后设置)
        self.broker_open_orders: dict[str, str] = {}
        self._seq = 0

    def place_order(self, **kw):
        self._seq += 1
        broker_id = f"MM{self._seq:04d}"
        self.place_calls.append({**kw, "broker_order_id": broker_id})
        if self.callback_before_return is not None:
            self.callback_before_return(kw["remark"], broker_id)  # 回调先于同步返回
        return {"broker_order_id": broker_id}

    def modify_order(self, broker_order_id, **kw):
        self.modify_calls.append((broker_order_id, kw))
        return {"broker_order_id": broker_order_id}

    def cancel_order(self, broker_order_id):
        self.cancel_calls.append(broker_order_id)
        return {"broker_order_id": broker_order_id}

    def unlock(self):
        self.unlock_calls += 1

    def healthy(self):
        return True

    def open_orders_by_remark(self):
        return dict(self.broker_open_orders)


def make_env(tmp_path, mode=SystemMode.PAPER, now=NOW, **gw_over):
    engine = init_engine(f"sqlite:///{tmp_path / 'gw.sqlite'}")
    factory = create_session_factory(engine)
    store = OrderStore(factory)
    client = FakeTradingClient()
    lease = LeaseManager(factory, holder_id="worker-1", now_fn=lambda: now)
    lease.acquire()
    gw = ExecutionGateway(
        store=store, client=client, lease=lease, mode=mode,
        now_fn=lambda: now,
        business_limiter=BusinessRateLimiter(store, now_fn=lambda: now),
        broker_limiter=BrokerRateLimiter(now_fn=_ticking(now)),
        **gw_over,
    )
    return gw, store, client, factory


def _ticking(start):
    state = {"t": start}

    def now():
        state["t"] = state["t"] + timedelta(seconds=1)
        return state["t"]

    return now


def ok_risk(**over):
    kw = dict(
        side="BUY", symbol="SPY", market="US_ETF", quantity=3,
        price_usd=Decimal("100"), fx_usd_aud=Decimal("1"), now=NOW,
        quote_age_seconds=1.0, jurisdiction_verdict="ALLOW",
    )
    kw.update(over)
    return RiskContext(**kw)


def submit(gw, key="k1", **over):
    return gw.submit_intent(
        idempotency_key=key, symbol="SPY", side="BUY", quantity=3,
        currency="USD", strategy_source="S1_MOMENTUM_ROTATION",
        limit_price=Decimal("100.00"), risk_ctx=over.pop("risk_ctx", ok_risk()), **over,
    )


# ---------- SIMULATE 端到端 ----------

def test_simulate_full_lifecycle(tmp_path):
    gw, store, client, _ = make_env(tmp_path)
    order_id = submit(gw)
    assert client.place_calls[0]["trd_env"] == "SIMULATE"
    assert client.place_calls[0]["remark"] == "k1"          # 幂等键经 remark 承载
    assert store.get_state(order_id) is OrderState.SUBMITTED

    gw.on_order_event(idempotency_key="k1", broker_order_id="MM0001", status="ACCEPTED")
    gw.on_fill(idempotency_key="k1", quantity=1, price=Decimal("99.99"), broker_execution_id="E1")
    gw.on_fill(idempotency_key="k1", quantity=2, price=Decimal("100.01"), broker_execution_id="E2")
    assert store.get_state(order_id) is OrderState.FILLED
    fold = [e["to_state"] for e in store.list_events(order_id) if e["to_state"]]
    assert fold == ["INTENT_CREATED", "RISK_APPROVED", "SUBMITTING", "SUBMITTED",
                    "ACCEPTED", "PARTIALLY_FILLED", "FILLED"]
    assert client.unlock_calls == 0  # SIMULATE 永不解锁


def test_cancel_flow_with_partial_fill(tmp_path):
    gw, store, client, _ = make_env(tmp_path)
    order_id = submit(gw)
    gw.on_order_event(idempotency_key="k1", broker_order_id="MM0001", status="ACCEPTED")
    gw.on_fill(idempotency_key="k1", quantity=1, price=Decimal("99.99"))
    gw.request_cancel(order_id)
    assert client.cancel_calls == ["MM0001"]
    gw.on_order_event(idempotency_key="k1", broker_order_id="MM0001", status="CANCELLED")
    assert store.get_state(order_id) is OrderState.CANCELLED  # 终,带部分成交


def test_risk_rejection_stops_before_broker(tmp_path):
    gw, store, client, _ = make_env(tmp_path)
    order_id = submit(gw, risk_ctx=ok_risk(quantity=40))  # 4000 > 3000
    assert store.get_state(order_id) is OrderState.RISK_REJECTED
    assert client.place_calls == []                       # 从未触碰券商


# ---------- 回调先于返回 ----------

def test_callback_before_sync_return_race(tmp_path):
    gw, store, client, _ = make_env(tmp_path)

    def race(remark, broker_id):
        gw.on_order_event(idempotency_key=remark, broker_order_id=broker_id, status="ACCEPTED")
        gw.on_fill(idempotency_key=remark, quantity=3, price=Decimal("100.00"))

    client.callback_before_return = race
    order_id = submit(gw)
    assert store.get_state(order_id) is OrderState.FILLED
    events = store.list_events(order_id)
    types = [e["event_type"] for e in events]
    assert "BROKER_SYNC_ACK_LATE" in types                 # 晚到回执只补录,不回退
    assert any(e["backfilled"] for e in events)            # 补写中间态有标记
    assert len(client.place_calls) == 1                    # 只有一条券商指令


# ---------- 重启恢复:绝不重复提交 ----------

def test_recovery_adopts_when_broker_has_order(tmp_path):
    gw, store, client, _ = make_env(tmp_path)
    order_id = store.create_intent(idempotency_key="crash-1", symbol="SPY", side="BUY",
                                   quantity=3, currency="USD", strategy_source="S1")
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    client.broker_open_orders = {"crash-1": "MM9999"}      # 券商侧其实已收到

    report = gw.recover_in_flight()
    assert report["adopted"] == [order_id]
    assert store.get_state(order_id) is OrderState.SUBMITTED
    assert client.place_calls == []                        # 恢复期间零提交


def test_recovery_marks_submit_failed_when_broker_missing(tmp_path):
    gw, store, client, _ = make_env(tmp_path)
    order_id = store.create_intent(idempotency_key="crash-2", symbol="SPY", side="BUY",
                                   quantity=3, currency="USD", strategy_source="S1")
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")

    report = gw.recover_in_flight()
    assert report["submit_failed"] == [order_id]
    assert store.get_state(order_id) is OrderState.SUBMIT_FAILED
    assert store.idempotency_key_available("crash-2") is False  # 幂等键保留
    assert client.place_calls == []


# ---------- REAL 路径:十一门禁完全封锁 ----------

def test_real_path_blocked_by_default_and_never_unlocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 无授权文件/无配置的裸环境
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/trading_governor_policy.yaml").write_text("x: 1\n")
    (tmp_path / "configs/strategy_promotion.yaml").write_text("y: 1\n")
    gw, store, client, _ = make_env(tmp_path, mode=SystemMode.MICRO_LIVE)
    with pytest.raises(GateBlockedError) as ei:
        submit(gw)
    failures = set(ei.value.report.failures)
    assert "GATE_01_ENV_FLAG" in failures                  # 环境开关默认关
    assert "GATE_02_PRESIGNED_AUTHORIZATION" in failures   # 无预签授权
    assert client.place_calls == []                        # 券商零调用
    assert client.unlock_calls == 0                        # 永不解锁
    order_id = store.find_order_by_idempotency_key("k1")
    events = store.list_events(order_id)
    blocked = next(e for e in events if e["event_type"] == "GATE_BLOCKED_REAL")
    assert "GATE_01_ENV_FLAG" in blocked["payload"]["failures"]  # 封锁留审计


def test_disabled_and_shadow_modes_cannot_trade(tmp_path):
    for mode in (SystemMode.DISABLED, SystemMode.SHADOW, SystemMode.HALTED):
        gw, _, client, _ = make_env(tmp_path, mode=mode)
        with pytest.raises(GateBlockedError):
            submit(gw, key=f"mode-{mode.value}")
        assert client.place_calls == []


def test_eleven_gates_all_green_allows_real(tmp_path, monkeypatch):
    """全绿路径:证明封锁是门禁所致而非死路——同时验证 unlock 只在此时发生。"""
    policy = tmp_path / "policy.yaml"
    promo = tmp_path / "promo.yaml"
    policy.write_text("policy: live-mvp\n")
    promo.write_text("promo: v1\n")
    auth = {
        "authorization_id": "AUTH-TEST-1", "owner": "Linze", "mode": "MICRO_LIVE",
        "capital": {"currency": "AUD", "max_managed_gross_exposure": 3000,
                    "fat_finger_max_single_order_ratio": 0.9, "max_orders_per_hour": 5,
                    "max_open_positions": None},
        "markets": ["US_STOCK", "US_ETF"],
        "promotion_conditions": {"strategy_promotion_config_hash": sha256_of_file(promo),
                                 "auto_activate_on_all_green": True},
        "valid_from": "2026-07-01T00:00:00+00:00", "valid_until": "2026-09-30T00:00:00+00:00",
        "policy_hash": sha256_of_file(policy),
        "owner_signature": "Linze 亲签测试短语", "signed_at": "2026-07-17T10:00:00+00:00",
    }
    auth_path = tmp_path / "LIVE_AUTHORIZATION.json"
    auth_path.write_text(json.dumps(auth, ensure_ascii=False))

    gw, store, client, factory = make_env(
        tmp_path, mode=SystemMode.MICRO_LIVE,
        policy_path=str(policy), promotion_config_path=str(promo),
        authorization_path=str(auth_path),
        env_reader={"LIVE_TRADING_ENABLED": "1"}.get,
    )
    # 辖区 ALLOW 证据落库
    from backend.app.adapters.brokers.base import ProbeEvidence, QuotePermission
    from backend.app.adapters.brokers.probe import run_probe_and_persist

    run_probe_and_persist(
        ProbeEvidence(acc_id="281756", account_status="ACTIVE", trd_permissions=["US_STOCK"],
                      quote_permissions=[QuotePermission("US", "LV1", True)], probed_at=NOW),
        factory, account_principal="owner", location="AU",
    )
    order_id = submit(gw)
    assert store.get_state(order_id) is OrderState.SUBMITTED
    assert client.place_calls[0]["trd_env"] == "REAL"
    assert client.unlock_calls == 1                        # 解锁仅发生在全绿 REAL


def test_authorization_validator_rejects_tampering(tmp_path):
    policy = tmp_path / "p.yaml"; policy.write_text("a: 1\n")
    promo = tmp_path / "q.yaml"; promo.write_text("b: 1\n")
    good = {
        "authorization_id": "A", "owner": "Linze", "mode": "MICRO_LIVE",
        "capital": {"currency": "AUD", "max_managed_gross_exposure": 3000,
                    "fat_finger_max_single_order_ratio": 0.9, "max_orders_per_hour": 5},
        "markets": ["US_STOCK"],
        "promotion_conditions": {"strategy_promotion_config_hash": sha256_of_file(promo),
                                 "auto_activate_on_all_green": True},
        "valid_from": "2026-07-01T00:00:00+00:00", "valid_until": "2026-09-30T00:00:00+00:00",
        "policy_hash": sha256_of_file(policy),
        "owner_signature": "sig", "signed_at": "2026-07-17T10:00:00+00:00",
    }
    f = tmp_path / "auth.json"

    f.write_text(json.dumps(good))
    ok, _ = validate_authorization(f, policy_path=policy, promotion_config_path=promo, now=NOW)
    assert ok

    for corrupt, why in [
        ({**good, "capital": {**good["capital"], "max_managed_gross_exposure": 5000}}, "资金越权"),
        ({**good, "markets": ["HK_STOCK"]}, "市场越权"),
        ({**good, "policy_hash": "deadbeef"}, "政策被改"),
        ({**good, "valid_until": "2026-07-16T00:00:00+00:00"}, "已过期"),
        ({**good, "owner": "别人"}, "非 owner"),
    ]:
        f.write_text(json.dumps(corrupt))
        ok, reasons = validate_authorization(f, policy_path=policy, promotion_config_path=promo, now=NOW)
        assert not ok, why
        assert reasons


# ---------- 频控与租约 ----------

def test_business_rate_limit_blocks_sixth_order(tmp_path):
    # 业务限速以事件表真实时间戳计数:限速器时钟必须与事件时钟同源(真实 UTC)
    gw, store, client, _ = make_env(tmp_path)
    gw._biz_limit = BusinessRateLimiter(store)  # noqa: SLF001 - 换回真实时钟
    for i in range(5):
        submit(gw, key=f"rl-{i}")
    with pytest.raises(RateLimitExceededError):
        submit(gw, key="rl-5")
    assert len(client.place_calls) == 5
    blocked_id = store.find_order_by_idempotency_key("rl-5")
    types = [e["event_type"] for e in store.list_events(blocked_id)]
    assert "RATE_LIMIT_BLOCKED" in types                   # 触顶即拒并审计


def test_lease_lost_blocks_submission(tmp_path):
    gw, store, client, factory = make_env(tmp_path)
    thief = LeaseManager(factory, holder_id="worker-2",
                         now_fn=lambda: NOW + timedelta(seconds=120))  # 原租约已过期
    thief.acquire()
    with pytest.raises(LeaseLostError):
        submit(gw, key="lease-1")
    assert client.place_calls == []
