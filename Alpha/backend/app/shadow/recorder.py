"""影子记录器(ALPHA-LIVE-035,状态机规范第 4 节)。

ShadowOrder 不进订单状态机(永无券商事件):记录「若实盘会发出的订单」的
假想限价、假想成交(保守规则:限价单只有当日最低价 <= 限价才算成交,
成交价 = 限价——绝不占乐观便宜)、与 Paper 实际成交的差异,供 3 日报告对比。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import ShadowOrder


class ShadowRecorder:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def record_decision(
        self,
        *,
        intent_id: str,
        hypothetical_limit_price: Decimal,
        estimated_fees: Decimal,
        rationale: Optional[dict] = None,
    ) -> str:
        """每个 Paper 决策并行落一条影子单(同一意图重复记录 = 违规,直接拒)。"""
        with self._sessions() as session, session.begin():
            existing = session.scalar(select(ShadowOrder).where(ShadowOrder.intent_id == intent_id))
            if existing is not None:
                raise ValueError(f"影子单已存在(必须一一对应): {intent_id}")
            row = ShadowOrder(
                intent_id=intent_id,
                hypothetical_limit_price=hypothetical_limit_price,
                hypothetical_fees=estimated_fees,
                viability_divergence=json.dumps({"rationale": rationale or {}}, ensure_ascii=False, default=str),
            )
            session.add(row)
            session.flush()
            return row.shadow_id

    def settle_hypothetical(
        self,
        *,
        intent_id: str,
        day_low: Decimal,
        day_high: Decimal,
    ) -> Optional[Decimal]:
        """保守假想成交:买单仅当 日内最低 <= 限价 才算成交,成交价=限价。

        (卖出方向对称:日内最高 >= 限价才成交;由调用方按方向换参传入。)
        返回假想成交价;未成交返回 None 并留痕。
        """
        with self._sessions() as session, session.begin():
            row = session.scalar(select(ShadowOrder).where(ShadowOrder.intent_id == intent_id))
            if row is None:
                raise KeyError(intent_id)
            limit_price = row.hypothetical_limit_price
            fill_price = limit_price if day_low <= limit_price else None
            row.hypothetical_fill_price = fill_price
            div = json.loads(row.viability_divergence)
            div["settle"] = {
                "day_low": str(day_low),
                "day_high": str(day_high),
                "filled": fill_price is not None,
            }
            row.viability_divergence = json.dumps(div, ensure_ascii=False)
            return fill_price

    def record_paper_divergence(
        self,
        *,
        intent_id: str,
        paper_fill_price: Optional[Decimal],
        paper_filled_quantity: int,
    ) -> dict:
        """登记 Paper 实际成交与影子假想的差异(3 日报告的对比原料)。"""
        with self._sessions() as session, session.begin():
            row = session.scalar(select(ShadowOrder).where(ShadowOrder.intent_id == intent_id))
            if row is None:
                raise KeyError(intent_id)
            div = json.loads(row.viability_divergence)
            shadow_fill = row.hypothetical_fill_price
            divergence = {
                "paper_fill_price": str(paper_fill_price) if paper_fill_price is not None else None,
                "paper_filled_quantity": paper_filled_quantity,
                "shadow_fill_price": str(shadow_fill) if shadow_fill is not None else None,
                "both_filled": paper_fill_price is not None and shadow_fill is not None,
                "price_gap": (
                    str(paper_fill_price - shadow_fill)
                    if paper_fill_price is not None and shadow_fill is not None
                    else None
                ),
            }
            div["paper_divergence"] = divergence
            row.viability_divergence = json.dumps(div, ensure_ascii=False)
            return divergence

    def count(self) -> int:
        with self._sessions() as session:
            return len(session.scalars(select(ShadowOrder)).all())

    def by_intent(self, intent_id: str) -> Optional[dict]:
        with self._sessions() as session:
            row = session.scalar(select(ShadowOrder).where(ShadowOrder.intent_id == intent_id))
            if row is None:
                return None
            return {
                "shadow_id": row.shadow_id,
                "intent_id": row.intent_id,
                "hypothetical_limit_price": row.hypothetical_limit_price,
                "hypothetical_fill_price": row.hypothetical_fill_price,
                "divergence": json.loads(row.viability_divergence),
            }
