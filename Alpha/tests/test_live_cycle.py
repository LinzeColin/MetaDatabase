"""070 实盘循环:纯函数与桥的确定性行为(真机端到端以部署机联调留痕为准)。"""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backend.app.adapters.brokers.moomoo_trade_bridge import SimulateTradingClient
from backend.app.domain.state_machine import OrderState
from backend.app.workers.live_cycle import (
    BROKER_STATUS_MAP, _ensure_lease, in_eval_window, plan_rebalance,
    quote_age_seconds, rank_allows,
)

ET = ZoneInfo("America/New_York")
RET_OK, RET_ERROR = 0, -1


# ---------- 纯函数 ----------

def test_eval_window_tuesday_only():
    tue_in = datetime(2026, 7, 21, 10, 15, tzinfo=ET)     # 周二 10:15 ET(开盘后45m)
    tue_early = datetime(2026, 7, 21, 9, 45, tzinfo=ET)   # 开盘后15m,窗口外
    mon = datetime(2026, 7, 20, 10, 15, tzinfo=ET)        # 周一
    assert in_eval_window(tue_in) is True
    assert in_eval_window(tue_early) is False
    assert in_eval_window(mon) is False


def test_rank_allows_only_forward():
    assert rank_allows(OrderState.SUBMITTING, "ACCEPTED") is True
    assert rank_allows(OrderState.ACCEPTED, "ACCEPTED") is False    # 重复回灌被闸
    assert rank_allows(OrderState.FILLED, "CANCELLED") is False     # 终态不动
    assert rank_allows(OrderState.PARTIALLY_FILLED, "CANCELLED") is True
    assert rank_allows(OrderState.SUBMITTED, "SUBMITTED") is False


def test_broker_status_map_covers_terminal():
    assert BROKER_STATUS_MAP["FILLED_ALL"] is None      # 成交走 on_fill
    assert BROKER_STATUS_MAP["CANCELLED_ALL"] == "CANCELLED"
    assert BROKER_STATUS_MAP["SUBMIT_FAILED"] == "REJECTED"


def test_plan_rebalance_sells_first_integer_threshold():
    plan = plan_rebalance(
        {"SPY": 0.8, "GLD": 0.2},
        positions={"QQQ": 3, "GLD": 1},
        prices={"SPY": 500.0, "GLD": 250.0, "QQQ": 400.0},
        capital_usd=1980.0, threshold_pct=5.0)
    # QQQ 全卖(1200 USD > 99 阈值);SPY 买 int(1584/500)=3;GLD 目标 int(396/250)=1 已持有→无单
    assert plan[0] == ("SELL", "QQQ", 3)
    assert ("BUY", "SPY", 3) in plan
    assert all(sym != "GLD" for _, sym, _ in plan)


def test_plan_rebalance_skips_below_threshold_and_unaffordable():
    plan = plan_rebalance({"SPY": 1.0}, positions={}, prices={"SPY": 5000.0},
                          capital_usd=1980.0, threshold_pct=5.0)
    assert plan == []   # 一股都买不起 → 目标 0 → 无单


def test_ensure_lease_reacquires_on_expiry_but_fails_closed_when_held():
    class Expired:
        def __init__(self):
            self.acquired = 0

        def renew(self):
            raise RuntimeError("过期")

        def acquire(self):
            self.acquired += 1

    lz = Expired()
    _ensure_lease(lz)
    assert lz.acquired == 1   # 过期 → 接管

    class HeldByOther(Expired):
        def acquire(self):
            raise RuntimeError("他人有效持有")

    with pytest.raises(RuntimeError):
        _ensure_lease(HeldByOther())   # 真被接管 → 失败关闭


def test_quote_age_parses_et():
    now = datetime(2026, 7, 21, 14, 30, 5, tzinfo=timezone.utc)  # = 10:30:05 ET
    age = quote_age_seconds("2026-07-21 10:30:00", now)
    assert age is not None and 4 <= age <= 6
    assert quote_age_seconds("garbage", now) is None


# ---------- SIMULATE 交易桥(假 SDK) ----------

class FakeTradeCtx:
    def __init__(self):
        self.placed = []

    def place_order(self, **kw):
        self.placed.append(kw)
        return RET_OK, pd.DataFrame([{"order_id": "SIM123"}])

    def order_list_query(self, trd_env, acc_id):
        return RET_OK, pd.DataFrame([
            {"order_id": "SIM123", "remark": "S1-2026-07-21-SPY-BUY-3",
             "order_status": "SUBMITTED", "create_time": "2026-07-21 10:31:00"},
            {"order_id": "SIM124", "remark": "", "order_status": "SUBMITTED",
             "create_time": "2026-07-21 10:32:00"},
        ])

    def deal_list_query(self, trd_env, acc_id):
        return RET_OK, pd.DataFrame([
            {"deal_id": "DL1", "order_id": "SIM123", "qty": 3, "price": 500.05,
             "create_time": "2026-07-21 10:33:00"},
        ])

    def get_acc_list(self):
        return RET_OK, pd.DataFrame([{"acc_id": 138648, "trd_env": "SIMULATE"}])

    def close(self):
        pass


class FakeSDK:
    RET_OK = RET_OK

    class TrdMarket:
        US = "US"

    class SecurityFirm:
        FUTUAU = "FUTUAU"

    class TrdSide:
        BUY, SELL = "BUY", "SELL"

    class OrderType:
        NORMAL = "NORMAL"

    class TrdEnv:
        SIMULATE, REAL = "SIMULATE", "REAL"

    class ModifyOrderOp:
        NORMAL, CANCEL = "NORMAL", "CANCEL"

    def __init__(self):
        self.ctx = FakeTradeCtx()

    def OpenSecTradeContext(self, **kw):
        assert kw["security_firm"] == "FUTUAU"
        return self.ctx


def bridge():
    return SimulateTradingClient(FakeSDK(), acc_id="138648")


def test_bridge_rejects_real_env_structurally():
    with pytest.raises(PermissionError):
        bridge().place_order(symbol="SPY", side="BUY", quantity=1, order_type="LIMIT",
                             limit_price=Decimal("500"), trd_env="REAL", remark="k")


def test_bridge_limit_only():
    with pytest.raises(ValueError):
        bridge().place_order(symbol="SPY", side="BUY", quantity=1, order_type="MARKET",
                             limit_price=None, trd_env="SIMULATE", remark="k")


def test_bridge_place_and_maps():
    b = bridge()
    ack = b.place_order(symbol="SPY", side="BUY", quantity=3, order_type="LIMIT",
                        limit_price=Decimal("500.5"), trd_env="SIMULATE", remark="S1-x")
    assert ack == {"broker_order_id": "SIM123"}
    placed = b._trade().placed[0]
    assert placed["code"] == "US.SPY" and placed["qty"] == 3
    assert placed["trd_env"] == "SIMULATE" and placed["remark"] == "S1-x"
    assert b.open_orders_by_remark() == {"S1-2026-07-21-SPY-BUY-3": "SIM123"}
    deals = b.poll_deals()
    assert deals[0]["broker_execution_id"] == "DL1" and deals[0]["quantity"] == 3
    assert b.unlock() is None and b.healthy() is True


def test_plan_rebalance_slices_orders_above_single_cap():
    """实机 2026-07-21 复现:QQQ 2股一笔 2172 澳元撞 1800 单笔线 → 切成 1+1。"""
    plan = plan_rebalance({"QQQ": 0.8}, positions={}, prices={"QQQ": 705.91},
                          capital_usd=1980.0, threshold_pct=5.0,
                          single_order_cap_usd=1131.0)   # ≈1800AUD×0.97/1.5385
    assert plan == [("BUY", "QQQ", 1), ("BUY", "QQQ", 1)]


def test_plan_rebalance_no_slice_when_under_cap():
    plan = plan_rebalance({"GLD": 0.2}, positions={}, prices={"GLD": 372.3},
                          capital_usd=1980.0, threshold_pct=5.0,
                          single_order_cap_usd=1131.0)
    assert plan == [("BUY", "GLD", 1)]


def test_makeup_eval_window_any_weekday():
    """补评估窗口判定:开盘后 60-120 分钟(任意交易日)——由 makeup 文件触发的形状。"""
    wed = datetime(2026, 7, 22, 10, 45, tzinfo=ET)   # 周三 10:45 ET,窗口内
    assert in_eval_window(wed) is False               # 正常节拍仍然只认周二
    minute = wed.hour * 60 + wed.minute
    assert (9 * 60 + 60) <= minute <= (9 * 60 + 120)  # 但补评估窗口覆盖它


# ---------- 080:模式解析与 REAL 桥红线 ----------

def test_resolve_mode_fail_closed_matrix():
    from backend.app.adapters.brokers.base import SystemMode
    from backend.app.workers.live_cycle import resolve_mode

    assert resolve_mode("PAPER", "SIMULATE", live_flag="0",
                        auth_ok=False, auth_reasons=[]) is SystemMode.PAPER
    with pytest.raises(RuntimeError):   # PAPER 绑真实账户 = 拒
        resolve_mode("PAPER", "REAL", live_flag="0", auth_ok=True, auth_reasons=[])
    with pytest.raises(RuntimeError):   # MICRO_LIVE 绑模拟账户 = 拒
        resolve_mode("MICRO_LIVE", "SIMULATE", live_flag="1", auth_ok=True, auth_reasons=[])
    with pytest.raises(RuntimeError):   # 总开关 0 = 拒
        resolve_mode("MICRO_LIVE", "REAL", live_flag="0", auth_ok=True, auth_reasons=[])
    with pytest.raises(RuntimeError):   # 授权无效 = 拒
        resolve_mode("MICRO_LIVE", "REAL", live_flag="1", auth_ok=False, auth_reasons=["x"])
    assert resolve_mode("MICRO_LIVE", "REAL", live_flag="1",
                        auth_ok=True, auth_reasons=[]) is SystemMode.MICRO_LIVE


def test_real_bridge_rejects_simulate_and_unlock_needs_password(monkeypatch):
    from backend.app.adapters.brokers.moomoo_trade_bridge import RealTradingClient

    b = RealTradingClient(FakeSDK(), acc_id="284008280622194851")
    with pytest.raises(PermissionError):
        b.place_order(symbol="SPY", side="BUY", quantity=1, order_type="LIMIT",
                      limit_price=Decimal("500"), trd_env="SIMULATE", remark="k")
    monkeypatch.delenv("MOOMOO_UNLOCK_PASSWORD", raising=False)
    with pytest.raises(PermissionError):
        b.unlock()   # 无解锁密码 = 失败关闭


def test_prepare_authorization_schema_valid(tmp_path, monkeypatch):
    """生成器产物必须一次通过 validate_authorization(在仓库根目录取真实配置哈希)。"""
    import scripts.prepare_live_authorization as pa
    from backend.app.execution.gates import validate_authorization
    from datetime import datetime, timezone
    import json as _json

    signed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    auth = pa.build("我确认授权(测试短语)", 14, signed_at)
    p = tmp_path / "AUTH.json"
    p.write_text(_json.dumps(auth, ensure_ascii=False))
    ok, reasons = validate_authorization(
        p, policy_path="configs/trading_governor_policy.yaml",
        promotion_config_path="configs/strategy_promotion.yaml",
        now=datetime.now(timezone.utc))
    assert ok, reasons


# ---------- 券商路径行为不变(影子盘修正不外溢) ----------

class _PaperClient:
    """券商模拟盘形态的假交易会话(无 TRD_ENV=LOCAL)。"""

    def __init__(self, orders=(), deals=()):
        self.orders, self.deals, self.place_calls = list(orders), list(deals), []

    def place_order(self, **kw):
        self.place_calls.append(kw)
        return {"broker_order_id": f"MM{len(self.place_calls)}"}

    def poll_orders(self):
        return self.orders

    def poll_deals(self):
        return self.deals

    def open_orders_by_remark(self):
        return {}

    def unlock(self):
        pass

    def healthy(self):
        return True


def _paper_deps(tmp_path, client, read_client, now_fn):
    from pathlib import Path

    from backend.app.adapters.brokers.base import SystemMode
    from backend.app.execution.gateway import ExecutionGateway
    from backend.app.execution.lease import LeaseManager
    from backend.app.shadow.recorder import ShadowRecorder
    from backend.app.store.db import create_session_factory, init_engine
    from backend.app.store.orders import OrderStore
    from backend.app.strategies.s1_momentum import load_s1_config
    from backend.app.workers.killswitch import KillSwitch
    from backend.app.workers.live_cycle import LiveCycleDeps

    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'paper.sqlite'}"))
    store = OrderStore(factory)
    lease = LeaseManager(factory, holder_id="w", now_fn=now_fn)
    lease.acquire()
    gw = ExecutionGateway(store=store, client=client, lease=lease, mode=SystemMode.PAPER,
                          now_fn=now_fn)
    return LiveCycleDeps(
        read_client=read_client, trade_client=client, store=store, gateway=gw,
        shadow=ShadowRecorder(factory), lease=lease, kill_switch=KillSwitch(tmp_path / "KS"),
        cfg=load_s1_config("configs/strategies/s1_gem_plus.yaml"), capital_usd=1950.0,
        fx_usd_aud=Decimal("1.538462"), marker_path=Path(tmp_path / "rt" / "last_s1_eval.txt"),
        fee_estimate=lambda side, qty, px: 0.99, mode="PAPER", now_fn=now_fn)


def test_paper_path_jurisdiction_still_deny(tmp_path, monkeypatch, make_clock, make_market):
    """PAPER 且无辖区探针记录:买单仍被 RULE_JURISDICTION_DENY 拒(ALLOW 只属于 SHADOW)。"""
    from backend.app.workers.live_cycle import run_live_cycle

    monkeypatch.setenv("ALPHA_RUNTIME_DIR", str(tmp_path / "rt"))
    clock = make_clock(datetime(2026, 7, 21, 14, 15, tzinfo=timezone.utc))
    client = _PaperClient()
    d = _paper_deps(tmp_path, client, make_market(clock), clock)
    r = run_live_cycle(d)
    assert r["plan"] == ["BUY QQQx4"] and r["rejected"] == 1 and r["submitted"] == 0
    order_id = d.store.find_order_by_idempotency_key("S1-2026-07-21-QQQ-BUY-4")
    assert "RULE_JURISDICTION_DENY" in d.store.get_risk_rules(order_id)
    assert client.place_calls == []


def test_broker_deal_without_fees_records_zero(tmp_path):
    """券商成交明细不带 fees 字段时如实入账 0(券商路径行为不变);带 fees 时透传。"""
    from types import SimpleNamespace

    from sqlalchemy import select

    from backend.app.domain.models import Execution
    from backend.app.workers.live_cycle import _backfill

    now = datetime(2026, 7, 21, 14, 45, tzinfo=timezone.utc)
    client = _PaperClient()
    d = _paper_deps(tmp_path, client, None, lambda: now)
    for key, broker_id in (("S1-a", "MM1"), ("S1-b", "MM2")):
        oid = d.store.create_intent(idempotency_key=key, symbol="SPY", side="BUY", quantity=3,
                                    currency="USD", strategy_source="S1",
                                    limit_price=Decimal("100"))
        d.store.record_risk_decision(oid, allowed=True)
        d.store.apply_transition(oid, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
        d.store.apply_transition(oid, OrderState.SUBMITTED, event_type="ACK",
                                 broker_order_id=broker_id)
    client.orders = [{"remark": "S1-a", "broker_order_id": "MM1", "status": "FILLED_ALL"},
                     {"remark": "S1-b", "broker_order_id": "MM2", "status": "FILLED_ALL"}]
    client.deals = [{"broker_execution_id": "D1", "broker_order_id": "MM1",
                     "quantity": 3, "price": 100.0},
                    {"broker_execution_id": "D2", "broker_order_id": "MM2",
                     "quantity": 3, "price": 100.0, "fees": "1.23"}]
    _backfill(SimpleNamespace(trade_client=client, store=d.store, gateway=d.gateway),
              {"backfilled": 0, "fills": 0})
    with d.store._sessions() as s:  # noqa: SLF001
        fees = {e.broker_execution_id: e.fees for e in s.scalars(select(Execution))}
    assert fees == {"D1": Decimal("0"), "D2": Decimal("1.23")}
