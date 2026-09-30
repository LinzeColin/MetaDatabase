"""影子盘模拟券商:成交价/费用/拒单条件/幂等/重启恢复,以及整条影子链不 import 券商 SDK。"""

import ast
import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from backend.app.adapters.brokers.base import BrokerError, SystemMode
from backend.app.adapters.brokers.sim_broker import SimBroker
from backend.app.backtest.fees import FeeModel
from backend.app.domain.models import Execution, SimOrder
from backend.app.domain.state_machine import OrderState
from backend.app.execution.gateway import ExecutionGateway
from backend.app.execution.lease import LeaseManager
from backend.app.marketdata.yahoo_live import LiveQuote, QuoteUnavailable
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore
from backend.app.workers.live_cycle import _backfill

UTC = timezone.utc
NOW = datetime(2026, 7, 21, 14, 45, tzinfo=UTC)      # 周二 10:45 ET,常规时段内
FEES = FeeModel.from_yaml()


class Quotes:
    def __init__(self, price=100.0, ts=None, fail=False):
        self.price, self.ts, self.fail = price, ts, fail

    def get_quote(self, sym):
        if self.fail:
            raise QuoteUnavailable(sym)
        return LiveQuote(symbol=sym, price=self.price,
                         ts_utc=self.ts or NOW - timedelta(seconds=1))


def make(tmp_path, quotes=None, now=NOW, capital=1950.0, name="sim"):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / f'{name}.sqlite'}"))
    sim = SimBroker(factory, quotes=quotes or Quotes(), fee_model=FEES,
                    start_capital_usd=capital, now_fn=lambda: now)
    return sim, factory


def place(sim, *, side="BUY", qty=3, limit="100.10", remark="S1-k1", env="LOCAL",
          order_type="LIMIT"):
    return sim.place_order(symbol="SPY", side=side, quantity=qty, order_type=order_type,
                           limit_price=None if limit is None else Decimal(limit),
                           trd_env=env, remark=remark)


def rows(factory):
    with factory() as s:
        return list(s.scalars(select(SimOrder).order_by(SimOrder.created_at)))


def test_fill_at_quote_plus_slippage_capped_by_limit(tmp_path):
    """买价 = 报价×(1+5bp) 向上取整到分且不高于限价;卖单对称(向下取整且不低于限价)。"""
    assert FEES.slippage_bps == 5.0
    sim, factory = make(tmp_path, Quotes(price=100.0))
    place(sim, qty=3, limit="100.10", remark="S1-b1")
    assert rows(factory)[-1].fill_price == Decimal("100.05")      # 100×1.0005
    place(sim, qty=1, limit="100.02", remark="S1-b2")
    assert rows(factory)[-1].fill_price == Decimal("100.02")      # 限价封顶
    place(sim, side="SELL", qty=1, limit="99.90", remark="S1-s1")
    assert rows(factory)[-1].fill_price == Decimal("99.95")       # 100×0.9995
    place(sim, side="SELL", qty=1, limit="99.98", remark="S1-s2")
    assert rows(factory)[-1].fill_price == Decimal("99.98")       # 限价托底
    assert FEES.slipped_price("BUY", 91.53) == 91.58              # 91.575765 向上
    assert FEES.slipped_price("SELL", 91.53) == 91.48             # 91.484235 向下


def test_fees_from_fee_model(tmp_path):
    """deal.fees = FeeModel.order_cost_usd(side, qty, fill);卖单含 SEC 估值。"""
    sim, _ = make(tmp_path, Quotes(price=100.0))
    place(sim, qty=3, remark="S1-b")
    place(sim, side="SELL", qty=2, limit="99.90", remark="S1-s")
    deals = {d["broker_order_id"]: d for d in sim.poll_deals()}
    orders = {o["remark"]: o for o in sim.poll_orders()}
    buy = deals[orders["S1-b"]["broker_order_id"]]
    sell = deals[orders["S1-s"]["broker_order_id"]]
    assert float(buy["fees"]) == FEES.order_cost_usd(side="BUY", quantity=3, price=100.05)
    assert float(sell["fees"]) == FEES.order_cost_usd(side="SELL", quantity=2, price=99.95)
    assert float(sell["fees"]) > FEES.commission_usd_per_order + FEES.cat_fee_per_share * 2
    expected_cash = (Decimal("1950") - Decimal("100.05") * 3 - buy["fees"]
                     + Decimal("99.95") * 2 - sell["fees"])
    assert sim.cash() == expected_cash and sim.positions() == {"SPY": 1}
    assert sim.get_funds() == {"cash": float(expected_cash), "power": float(expected_cash)}


@pytest.mark.parametrize("case,now,ts,code", [
    ("年龄 6 秒", NOW, NOW - timedelta(seconds=6), "QUOTE_STALE"),
    ("未来时间戳", NOW, NOW + timedelta(seconds=2), "QUOTE_STALE"),
    ("16:05 ET", datetime(2026, 7, 21, 20, 5, tzinfo=UTC),
     datetime(2026, 7, 21, 20, 4, 59, tzinfo=UTC), "OUTSIDE_SESSION"),
    ("前一交易日", NOW, NOW - timedelta(days=1), "QUOTE_STALE"),
    ("周末", datetime(2026, 7, 25, 14, 45, tzinfo=UTC),
     datetime(2026, 7, 25, 14, 44, 59, tzinfo=UTC), "OUTSIDE_SESSION"),
    ("盘前报价", NOW, datetime(2026, 7, 21, 13, 0, tzinfo=UTC), "OUTSIDE_SESSION"),
])
def test_refuses_stale_future_offsession_prevday_quote(tmp_path, case, now, ts, code):
    sim, factory = make(tmp_path, Quotes(ts=ts), now=now)
    with pytest.raises(BrokerError) as ei:
        place(sim)
    assert ei.value.raw_code == code, case
    [row] = rows(factory)
    assert row.status == "FAILED" and row.reason.startswith(code)
    assert sim.poll_deals() == [] and sim.cash() == Decimal("1950")


def test_refuses_non_local_env_market_order_missing_quote(tmp_path):
    sim, factory = make(tmp_path)
    for env in ("SIMULATE", "REAL"):
        with pytest.raises(BrokerError) as ei:
            place(sim, env=env, remark=f"S1-{env}")
        assert ei.value.raw_code == "ENV_NOT_LOCAL"
    with pytest.raises(BrokerError) as ei:
        place(sim, order_type="MARKET", limit=None, remark="S1-mkt")
    assert ei.value.raw_code == "ORDER_TYPE_UNSUPPORTED"
    sim2, factory2 = make(tmp_path, Quotes(fail=True), name="noquote")
    with pytest.raises(BrokerError) as ei:
        place(sim2, remark="S1-nq")
    assert ei.value.raw_code == "QUOTE_UNAVAILABLE"
    assert [r.status for r in rows(factory2)] == ["FAILED"]
    assert sim.poll_deals() == [] and sim2.poll_deals() == []


def test_limit_not_marketable(tmp_path):
    sim, _ = make(tmp_path, Quotes(price=100.0))
    with pytest.raises(BrokerError) as ei:
        place(sim, limit="99.99", remark="S1-lo")
    assert ei.value.raw_code == "LIMIT_NOT_MARKETABLE"


def test_insufficient_cash_and_no_short(tmp_path):
    sim, _ = make(tmp_path, Quotes(price=100.0), capital=250.0)
    with pytest.raises(BrokerError) as ei:
        place(sim, qty=3, remark="S1-big")                 # 300.15+费用 > 250
    assert ei.value.raw_code == "INSUFFICIENT_CASH"
    place(sim, qty=2, remark="S1-ok")
    with pytest.raises(BrokerError) as ei:
        place(sim, side="SELL", qty=3, limit="99.90", remark="S1-short")
    assert ei.value.raw_code == "NO_POSITION"
    assert sim.positions() == {"SPY": 2}


def test_idempotent_remark(tmp_path):
    """同一 remark 调两次:同一单号、簿里 1 行、现金只扣一次;失败的键原样再拒。"""
    sim, factory = make(tmp_path)
    a = place(sim, remark="S1-same")
    cash = sim.cash()
    b = place(sim, remark="S1-same")
    assert a == b and len(rows(factory)) == 1 and sim.cash() == cash
    stale, _ = make(tmp_path, Quotes(ts=NOW - timedelta(seconds=9)), name="stale")
    for _ in range(2):
        with pytest.raises(BrokerError) as ei:
            place(stale, remark="S1-bad")
        assert ei.value.raw_code == "QUOTE_STALE"


def test_book_survives_restart_and_recovery_adopts(tmp_path):
    """模拟券商已成交、网关还没收到回执就崩溃:重启后恢复认领,下一拍入账,成交恰好 1 笔。"""
    sim, factory = make(tmp_path)
    store = OrderStore(factory)
    key = "S1-2026-07-21-SPY-BUY-3"
    order_id = store.create_intent(idempotency_key=key, symbol="SPY", side="BUY", quantity=3,
                                   currency="USD", strategy_source="S1",
                                   limit_price=Decimal("100.10"))
    store.record_risk_decision(order_id, allowed=True)
    store.apply_transition(order_id, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
    place(sim, remark=key)                         # 券商侧已成交 …… 随即进程崩溃

    sim2 = SimBroker(factory, quotes=Quotes(), fee_model=FEES, start_capital_usd=1950.0,
                     now_fn=lambda: NOW)           # 重启:新实例
    assert [d["quantity"] for d in sim2.poll_deals()] == [3]
    lease = LeaseManager(factory, holder_id="w", now_fn=lambda: NOW)
    lease.acquire()
    gw = ExecutionGateway(store=store, client=sim2, lease=lease, mode=SystemMode.SHADOW,
                          now_fn=lambda: NOW)
    assert gw.recover_in_flight()["adopted"] == [order_id]
    assert store.get_state(order_id) is OrderState.SUBMITTED
    d = SimpleNamespace(trade_client=sim2, store=store, gateway=gw)
    for _ in range(2):                             # 连续两拍回灌:幂等
        _backfill(d, {"backfilled": 0, "fills": 0})
    assert store.get_state(order_id) is OrderState.FILLED
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Execution)) == 1
        assert s.scalar(select(Execution.fees)) > 0
    assert store.net_positions() == sim2.positions() == {"SPY": 3}


def test_module_imports_no_moomoo():
    """AST 扫描:影子链四个文件不 import 任何 moomoo 模块。"""
    root = pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"
    files = ["adapters/brokers/sim_broker.py", "marketdata/yahoo_live.py",
             "workers/shadow_cycle.py", "wiring.py"]
    for rel in files:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        bad = [n for n in names if n.startswith("moomoo") or "adapters.brokers.moomoo" in n]
        assert not bad, f"{rel} import 了券商 SDK: {bad}"
