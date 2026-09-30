"""影子盘模拟券商(TrdEnv.LOCAL):按当次新取的真实行情在本机撮合,不连任何券商。

语义 = 「可成交限价 IOC」:要么当即全部成交,要么拒——不挂单、不部分成交(比真券商保守)。
place_order 判定顺序(任一不满足即拒;除环境不符外,拒绝一律**先写 FAILED 行记原因**再抛错):
  LOCAL 环境 -> 幂等(remark 已存在)-> 仅 LIMIT -> 取新行情 -> 时段/同日/年龄 0..阈值秒
  -> 滑点成交价并受限价封顶 -> 费用 -> 现金足够 / 不卖空 -> 同一事务落 FILLED_ALL。
订单簿与账本同一 SQLite:下单后、回灌前重启,簿里的行照样能被恢复与回灌。
本文件不 import 任何券商 SDK。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters.brokers.base import BrokerError, BrokerErrorKind, TrdEnv
from backend.app.backtest.fees import FeeModel
from backend.app.domain.models import SimOrder
from backend.app.marketdata.guard import DEFAULT_FRESHNESS_THRESHOLD_SECONDS
from backend.app.workers.live_cycle import ET, market_open_now

FILLED = "FILLED_ALL"
FAILED = "FAILED"


class SimBroker:
    TRD_ENV = TrdEnv.LOCAL.value

    def __init__(self, session_factory: sessionmaker[Session], *, quotes, fee_model: FeeModel,
                 start_capital_usd: float, now_fn: Callable[[], datetime],
                 max_quote_age_seconds: float = DEFAULT_FRESHNESS_THRESHOLD_SECONDS) -> None:
        self._sessions = session_factory
        self._quotes = quotes
        self._fees = fee_model
        self._start = Decimal(str(start_capital_usd))
        self._now = now_fn
        self._max_age = float(max_quote_age_seconds)

    # ---------- 下单 ----------

    def place_order(self, *, symbol: str, side: str, quantity: int, order_type: str,
                    limit_price: Optional[Decimal], trd_env: str, remark: str) -> dict:
        if trd_env != self.TRD_ENV:
            raise BrokerError(BrokerErrorKind.REJECTED_BY_BROKER,
                              f"模拟券商只接 LOCAL,收到 {trd_env}", raw_code="ENV_NOT_LOCAL")
        with self._sessions() as session:
            prior = session.scalar(select(SimOrder).where(SimOrder.remark == remark))
        if prior is not None:
            if prior.status == FILLED:
                return {"broker_order_id": prior.sim_order_id}
            raise BrokerError(BrokerErrorKind.REJECTED_BY_BROKER, prior.reason,
                              raw_code=prior.reason.split(":", 1)[0])

        row = SimOrder(sim_order_id=f"SIM-{uuid.uuid4().hex[:12]}", remark=remark,
                       symbol=symbol, side=side, quantity=int(quantity),
                       limit_price=limit_price, status=FAILED,
                       slippage_bps=self._fees.slippage_bps, created_at=self._now())

        if order_type != "LIMIT" or limit_price is None:
            return self._reject(row, "ORDER_TYPE_UNSUPPORTED", f"只接限价单,收到 {order_type}")
        try:
            q = self._quotes.get_quote(symbol)
        except Exception as exc:
            return self._reject(row, "QUOTE_UNAVAILABLE", f"{type(exc).__name__}: {exc}")
        row.quote_price = Decimal(str(q.price))
        row.quote_time = q.ts_utc

        now = self._now()
        now_et, ts_et = now.astimezone(ET), q.ts_utc.astimezone(ET)
        age = (now - q.ts_utc).total_seconds()
        if not market_open_now(now_et):
            return self._reject(row, "OUTSIDE_SESSION", f"当前 {now_et:%a %H:%M} ET 不在常规时段")
        if ts_et.date() != now_et.date():
            return self._reject(row, "QUOTE_STALE", f"行情时间 {ts_et:%Y-%m-%d %H:%M:%S} ET 不是今天")
        if not market_open_now(ts_et):
            return self._reject(row, "OUTSIDE_SESSION", f"行情时间 {ts_et:%H:%M:%S} ET 不在常规时段")
        if not (0.0 <= age <= self._max_age):
            return self._reject(row, "QUOTE_STALE", f"行情年龄 {age:.1f} 秒,阈值 {self._max_age:g} 秒")

        limit = Decimal(str(limit_price))
        quote = Decimal(str(q.price))
        fill = Decimal(str(self._fees.slipped_price(side, q.price)))
        if side == "BUY":
            if quote > limit:
                return self._reject(row, "LIMIT_NOT_MARKETABLE", f"买价 {quote} 高于限价 {limit}")
            fill = min(fill, limit)
        else:
            if quote < limit:
                return self._reject(row, "LIMIT_NOT_MARKETABLE", f"卖价 {quote} 低于限价 {limit}")
            fill = max(fill, limit)
        fees = Decimal(str(self._fees.order_cost_usd(side=side, quantity=int(quantity),
                                                      price=float(fill))))
        row.fill_price, row.fees = fill, fees

        if side == "BUY":
            cash = self.cash()
            if fill * quantity + fees > cash:
                return self._reject(row, "INSUFFICIENT_CASH",
                                    f"需 {fill * quantity + fees:.2f},可用 {cash:.2f}")
        elif quantity > self.positions().get(symbol, 0):
            return self._reject(row, "NO_POSITION", f"卖 {quantity} 股超过持仓(不卖空)")

        row.status = FILLED
        with self._sessions() as session, session.begin():
            session.add(row)
        return {"broker_order_id": row.sim_order_id}

    def _reject(self, row: SimOrder, code: str, detail: str) -> dict:
        row.status = FAILED
        row.reason = f"{code}: {detail}"
        with self._sessions() as session, session.begin():
            session.add(row)
        raise BrokerError(BrokerErrorKind.REJECTED_BY_BROKER, row.reason, raw_code=code)

    # ---------- 券商侧真相(只由 FILLED_ALL 行推导) ----------

    def _filled(self) -> list[SimOrder]:
        with self._sessions() as session:
            return list(session.scalars(
                select(SimOrder).where(SimOrder.status == FILLED).order_by(SimOrder.created_at)))

    def cash(self) -> Decimal:
        c = self._start
        for r in self._filled():
            notional = r.fill_price * r.quantity
            c += (notional if r.side == "SELL" else -notional) - r.fees
        return c

    def positions(self) -> dict[str, int]:
        net: dict[str, int] = {}
        for r in self._filled():
            net[r.symbol] = net.get(r.symbol, 0) + (r.quantity if r.side == "BUY" else -r.quantity)
        return {s: q for s, q in net.items() if q}

    def get_funds(self, acc_id: str = "") -> dict:
        c = float(self.cash())
        return {"cash": c, "power": c}

    def poll_orders(self) -> list[dict]:
        return [{"remark": r.remark, "broker_order_id": r.sim_order_id, "status": FILLED,
                 "dealt_qty": r.quantity, "dealt_avg_price": float(r.fill_price)}
                for r in self._filled()]

    def poll_deals(self) -> list[dict]:
        return [{"broker_execution_id": f"DEAL-{r.sim_order_id}",
                 "broker_order_id": r.sim_order_id, "quantity": r.quantity,
                 "price": r.fill_price, "fees": r.fees}
                for r in self._filled()]

    def open_orders_by_remark(self) -> dict[str, str]:
        return {r.remark: r.sim_order_id for r in self._filled()}

    # ---------- 其余交易会话门面 ----------

    def modify_order(self, broker_order_id: str, *, quantity: int,
                     limit_price: Optional[Decimal]) -> dict:
        raise BrokerError(BrokerErrorKind.REJECTED_BY_BROKER, "影子盘无挂单")

    def cancel_order(self, broker_order_id: str) -> dict:
        raise BrokerError(BrokerErrorKind.REJECTED_BY_BROKER, "影子盘无挂单")

    def unlock(self) -> None:
        return None

    def healthy(self) -> bool:
        try:
            with self._sessions() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
