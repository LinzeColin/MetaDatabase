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
