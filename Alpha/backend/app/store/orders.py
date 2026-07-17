"""订单存取服务:事件溯源折叠 + 幂等 + 非法迁移处置(ALPHA-LIVE-010)。

恒真规则(specs/ORDER_STATE_MACHINE.md 第 2 节)在本层落地:
1. 非法迁移:拒绝写入目标态、记审计事件、状态标记 UNKNOWN_RECONCILIATION_REQUIRED、
   开 OPEN 对账批次(=停新单),然后抛 IllegalTransitionError 给调用方。
2. 每次迁移原子写入 order_events;BrokerOrder.state 是事件折叠结果,同一事务内更新。
3. 幂等键全局唯一且永不复用(严于「非终态拒绝」下限):重复键直接拒绝,
   保证同一幂等键至多产生一条券商指令。
4. 回调乱序:事件带券商时间戳+序号;早到的成交回调允许经补写中间态(backfilled=True)
   直接推进到 PARTIALLY_FILLED / FILLED。
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import (
    BrokerOrder,
    Execution,
    OrderEvent,
    OrderIntent,
    ReconciliationRun,
    RiskDecision,
)
from backend.app.domain.state_machine import (
    IllegalTransitionError,
    OrderState,
    assert_transition,
)


class DuplicateIdempotencyKeyError(Exception):
    """幂等键已被占用:同一键至多一条券商指令,重复意图直接拒绝。"""


class OrderStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    # ---------- 意图与风控 ----------

    def create_intent(
        self,
        *,
        idempotency_key: str,
        symbol: str,
        side: str,
        quantity: int,
        currency: str,
        strategy_source: str,
        order_type: str = "LIMIT",
        limit_price: Optional[Decimal] = None,
    ) -> str:
        """落库意图 + 初始 BrokerOrder(INTENT_CREATED)。返回 order_id。"""
        with self._sessions() as session, session.begin():
            existing = session.scalar(
                select(OrderIntent).where(OrderIntent.idempotency_key == idempotency_key)
            )
            if existing is not None:
                raise DuplicateIdempotencyKeyError(
                    f"幂等键已占用(永不复用): {idempotency_key}"
                )
            intent = OrderIntent(
                idempotency_key=idempotency_key,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                currency=currency,
                strategy_source=strategy_source,
            )
            session.add(intent)
            session.flush()
            order = BrokerOrder(intent_id=intent.intent_id, state=OrderState.INTENT_CREATED.value)
            session.add(order)
            session.flush()
            session.add(
                OrderEvent(
                    order_id=order.order_id,
                    event_type="INTENT_CREATED",
                    from_state=None,
                    to_state=OrderState.INTENT_CREATED.value,
                    payload=json.dumps({"idempotency_key": idempotency_key}, ensure_ascii=False),
                )
            )
            try:
                session.flush()
            except IntegrityError as exc:  # 并发竞态下唯一约束兜底
                raise DuplicateIdempotencyKeyError(
                    f"幂等键已占用(唯一约束): {idempotency_key}"
                ) from exc
            return order.order_id

    def record_risk_decision(
        self,
        order_id: str,
        *,
        allowed: bool,
        triggered_rules: list[str] | None = None,
        exposure_snapshot: dict | None = None,
    ) -> str:
        """写 RiskDecision 并原子迁移到 RISK_APPROVED / RISK_REJECTED。"""
        to_state = OrderState.RISK_APPROVED if allowed else OrderState.RISK_REJECTED
        with self._sessions() as session, session.begin():
            order = self._locked_order(session, order_id)
            decision = RiskDecision(
                intent_id=order.intent_id,
                allowed=allowed,
                triggered_rules=json.dumps(triggered_rules or [], ensure_ascii=False),
                exposure_snapshot=json.dumps(exposure_snapshot or {}, ensure_ascii=False),
            )
            session.add(decision)
            self._fold(session, order, to_state, event_type="RISK_DECISION")
            session.flush()
            return decision.decision_id

    # ---------- 状态迁移(事件折叠) ----------

    def apply_transition(
        self,
        order_id: str,
        to_state: OrderState,
        *,
        event_type: str,
        broker_order_id: Optional[str] = None,
        broker_timestamp: Optional[datetime] = None,
        broker_sequence: Optional[int] = None,
        payload: Optional[dict] = None,
        backfilled: bool = False,
    ) -> OrderState:
        """通用迁移入口。非法迁移按恒真规则 1 处置后重抛。"""
        with self._sessions() as session, session.begin():
            order = self._locked_order(session, order_id)
            current = OrderState(order.state)
            try:
                assert_transition(current, to_state)
            except IllegalTransitionError:
                # 目标态拒绝写入:先干净退出本事务(回滚),再用独立事务落隔离记录。
                illegal = IllegalTransitionError(current, to_state)
                session.rollback()
                self._quarantine(order_id, attempted=to_state, source_event=event_type, payload=payload)
                raise illegal from None
            if broker_order_id is not None:
                order.broker_order_id = broker_order_id
            if broker_timestamp is not None:
                order.last_broker_update_at = broker_timestamp
            self._fold(
                session,
                order,
                to_state,
                event_type=event_type,
                broker_timestamp=broker_timestamp,
                broker_sequence=broker_sequence,
                payload=payload,
                backfilled=backfilled,
            )
            return to_state

    def apply_fill_event(
        self,
        order_id: str,
        *,
        quantity: int,
        price: Decimal,
        fees: Decimal = Decimal("0"),
        broker_execution_id: Optional[str] = None,
        broker_timestamp: Optional[datetime] = None,
        broker_sequence: Optional[int] = None,
        executed_at: Optional[datetime] = None,
    ) -> OrderState:
        """成交回调安全合并。

        「回调先于返回」:若当前仍在 SUBMITTING/SUBMITTED,按规范补写中间态
        (SUBMITTED、ACCEPTED,backfilled=True)后再推进成交态;
        其余状态按合法迁移表裁定,不可解释的组合走非法迁移处置。
        """
        with self._sessions() as session, session.begin():
            order = self._locked_order(session, order_id)
            current = OrderState(order.state)

            backfill_chain: list[OrderState] = []
            if current is OrderState.SUBMITTING:
                backfill_chain = [OrderState.SUBMITTED, OrderState.ACCEPTED]
            elif current is OrderState.SUBMITTED:
                backfill_chain = [OrderState.ACCEPTED]

            intent = session.get(OrderIntent, order.intent_id)
            assert intent is not None
            total_after = order.filled_quantity + quantity
            target = (
                OrderState.FILLED if total_after >= intent.quantity else OrderState.PARTIALLY_FILLED
            )

            # 先裁定整条链的合法性,再落库(拒绝写入半截链)。
            probe = current
            try:
                for mid in backfill_chain:
                    probe = assert_transition(probe, mid)
                probe = assert_transition(probe, target)
            except IllegalTransitionError:
                illegal = IllegalTransitionError(current, target)
                session.rollback()
                self._quarantine(
                    order_id,
                    attempted=target,
                    source_event="BROKER_FILL",
                    payload={"quantity": quantity, "price": str(price)},
                )
                raise illegal from None

            for mid in backfill_chain:
                self._fold(
                    session,
                    order,
                    mid,
                    event_type="BACKFILLED_INTERMEDIATE",
                    broker_timestamp=broker_timestamp,
                    broker_sequence=broker_sequence,
                    backfilled=True,
                )

            prior_notional = (order.avg_fill_price or Decimal("0")) * order.filled_quantity
            new_notional = prior_notional + price * quantity
            order.filled_quantity = total_after
            order.avg_fill_price = (
                new_notional / total_after if total_after else None
            )
            if broker_timestamp is not None:
                order.last_broker_update_at = broker_timestamp
            session.add(
                Execution(
                    order_id=order.order_id,
                    broker_execution_id=broker_execution_id,
                    quantity=quantity,
                    price=price,
                    fees=fees,
                    executed_at=executed_at or broker_timestamp or order.created_at,
                )
            )
            self._fold(
                session,
                order,
                target,
                event_type="BROKER_FILL",
                broker_timestamp=broker_timestamp,
                broker_sequence=broker_sequence,
                payload={"quantity": quantity, "price": str(price), "fees": str(fees)},
            )
            return target

    def mark_unknown(self, order_id: str, *, reason: str) -> None:
        """无法解释的券商事件:任意状态 -> UNKNOWN_RECONCILIATION_REQUIRED + 开对账。"""
        with self._sessions() as session, session.begin():
            order = self._locked_order(session, order_id)
            self._fold(
                session,
                order,
                OrderState.UNKNOWN_RECONCILIATION_REQUIRED,
                event_type="UNEXPLAINED_BROKER_EVENT",
                payload={"reason": reason},
            )
            self._open_reconciliation(session, f"unexplained_broker_event:{order_id}")

    # ---------- 查询 ----------

    def get_state(self, order_id: str) -> OrderState:
        with self._sessions() as session:
            order = session.get(BrokerOrder, order_id)
            if order is None:
                raise KeyError(order_id)
            return OrderState(order.state)

    def list_events(self, order_id: str) -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(OrderEvent.event_seq)
            ).all()
            return [
                {
                    "event_seq": r.event_seq,
                    "event_type": r.event_type,
                    "from_state": r.from_state,
                    "to_state": r.to_state,
                    "backfilled": r.backfilled,
                    "payload": json.loads(r.payload),
                }
                for r in rows
            ]

    def halt_new_orders(self) -> bool:
        """对账未清 -> 下单资格 = 无。"""
        with self._sessions() as session:
            open_run = session.scalar(
                select(ReconciliationRun).where(ReconciliationRun.status == "OPEN").limit(1)
            )
            return open_run is not None

    def idempotency_key_available(self, key: str) -> bool:
        with self._sessions() as session:
            hit = session.scalar(select(OrderIntent).where(OrderIntent.idempotency_key == key))
            return hit is None

    # ---------- 内部 ----------

    @staticmethod
    def _locked_order(session: Session, order_id: str) -> BrokerOrder:
        # SQLite 靠库级写锁;PostgreSQL 下 with_for_update 行级锁,方言自动降级。
        order = session.get(BrokerOrder, order_id, with_for_update=True)
        if order is None:
            raise KeyError(order_id)
        return order

    @staticmethod
    def _fold(
        session: Session,
        order: BrokerOrder,
        to_state: OrderState,
        *,
        event_type: str,
        broker_timestamp: Optional[datetime] = None,
        broker_sequence: Optional[int] = None,
        payload: Optional[dict] = None,
        backfilled: bool = False,
    ) -> None:
        from_state = order.state
        order.state = to_state.value
        session.add(
            OrderEvent(
                order_id=order.order_id,
                event_type=event_type,
                from_state=from_state,
                to_state=to_state.value,
                broker_timestamp=broker_timestamp,
                broker_sequence=broker_sequence,
                backfilled=backfilled,
                payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
            )
        )
        session.flush()

    def _quarantine(
        self,
        order_id: str,
        *,
        attempted: OrderState,
        source_event: str,
        payload: Optional[dict],
    ) -> None:
        """恒真规则 1:审计 + UNKNOWN 标记 + 开对账批次(停新单)。

        独立事务提交——主操作的回滚不得吞掉隔离记录,否则非法事件就消失无痕了。
        目标态永不写入;原状态(含终态)保留在事件溯源里,由对账器按券商真相恢复。
        """
        with self._sessions() as session, session.begin():
            order = self._locked_order(session, order_id)
            current = OrderState(order.state)
            session.add(
                OrderEvent(
                    order_id=order.order_id,
                    event_type="ILLEGAL_TRANSITION_REJECTED",
                    from_state=current.value,
                    to_state=None,
                    payload=json.dumps(
                        {"attempted": attempted.value, "source_event": source_event, **(payload or {})},
                        ensure_ascii=False,
                        default=str,
                    ),
                )
            )
            self._fold(
                session,
                order,
                OrderState.UNKNOWN_RECONCILIATION_REQUIRED,
                event_type="ILLEGAL_TRANSITION_QUARANTINE",
            )
            self._open_reconciliation(session, f"illegal_transition:{order.order_id}")

    @staticmethod
    def _open_reconciliation(session: Session, reason: str) -> None:
        session.add(ReconciliationRun(trigger_reason=reason, differences_count=1))
