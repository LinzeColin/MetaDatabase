"""十实体 ORM 模型 + 订单事件溯源表(ALPHA-LIVE-010)。

字段口径逐条对应 machine/facts/data_contract.yaml;金额一律 Decimal 文本列
(SQLite 浮点不可信),数量为整数股(MVP 仅美股整股)。
本地开发/测试用 SQLite,生产 PostgreSQL——只经 SQLAlchemy 方言差异,模型不变。

设计裁定(留痕):
- BrokerOrder 本地主键 order_id 在 SUBMITTING 之前就存在;券商单号 broker_order_id
  唯一列,回报按「broker_order_id 或幂等键」安全合并(data_contract data_flow 语义)。
- 幂等键全局唯一且永不复用,严于规范「非终态拒绝」下限(fail-closed 方向)。
- 非法迁移的审计记录写入 order_events(event_type=ILLEGAL_TRANSITION_REJECTED),
  同时状态标记 UNKNOWN_RECONCILIATION_REQUIRED 并开对账批次;
  「停新单」= 存在 OPEN 状态的 ReconciliationRun(对账未清 -> 下单资格 = 无)。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class DecimalText(TypeDecorator):
    """金额列:以精确十进制字符串落库,进出均为 Decimal。"""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Optional[Decimal | str | int], dialect: Any) -> Optional[str]:
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value: Optional[str], dialect: Any) -> Optional[Decimal]:
        if value is None:
            return None
        return Decimal(value)


class Base(DeclarativeBase):
    pass


class OrderIntent(Base):
    """订单意图:幂等键、标的、方向、数量、限价、币种、策略来源、创建时间。"""

    __tablename__ = "order_intents"

    intent_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("intent"))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY / SELL
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="LIMIT")
    limit_price: Mapped[Optional[Decimal]] = mapped_column(DecimalText, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy_source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RiskDecision(Base):
    """风控裁定:关联意图、允许/拒绝、触发规则、裁定时敞口快照。"""

    __tablename__ = "risk_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("risk"))
    intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.intent_id"), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    triggered_rules: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON 数组
    exposure_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON 对象
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class BrokerOrder(Base):
    """券商订单:当前态 = order_events 折叠结果(事件溯源恒真规则)。"""

    __tablename__ = "broker_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("order"))
    intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.intent_id"), unique=True, nullable=False)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    state: Mapped[str] = mapped_column(String(48), nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_fill_price: Mapped[Optional[Decimal]] = mapped_column(DecimalText, nullable=True)
    last_broker_update_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", order_by="OrderEvent.event_seq")


class OrderEvent(Base):
    """订单事件溯源(含非法迁移审计):每次迁移原子追加,当前态为折叠结果。"""

    __tablename__ = "order_events"

    event_seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("broker_orders.order_id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    broker_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    broker_sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    backfilled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 补写中间态标记
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    order: Mapped[BrokerOrder] = relationship(back_populates="events")


class Execution(Base):
    """成交记录:关联券商订单、成交数量、成交价、费用、成交时间。"""

    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("exec"))
    order_id: Mapped[str] = mapped_column(ForeignKey("broker_orders.order_id"), nullable=False, index=True)
    broker_execution_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    fees: Mapped[Decimal] = mapped_column(DecimalText, nullable=False, default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PositionSnapshot(Base):
    """持仓快照:标的、数量、成本、市值、来源=券商、快照时间。"""

    __tablename__ = "position_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pos"))
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    market_value: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="broker")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CapitalAuthorization(Base):
    """资金授权:总敞口上限、单笔上限、币种、市场白名单、policy hash、生效与失效时间。"""

    __tablename__ = "capital_authorizations"

    authorization_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("auth"))
    max_gross_exposure: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    max_single_order: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    market_whitelist: Mapped[str] = mapped_column(Text, nullable=False)  # JSON 数组
    policy_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class JurisdictionCapability(Base):
    """辖区能力记录:账户主体、所在地、接口可用性、买入权限、证据来源、判定结果。"""

    __tablename__ = "jurisdiction_capabilities"

    capability_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("juris"))
    account_principal: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False)
    api_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    buy_permission: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_source: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)  # ALLOW / DENY
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ShadowOrder(Base):
    """影子订单:不进订单状态机(永无券商事件),供 3 日报告对比。"""

    __tablename__ = "shadow_orders"

    shadow_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("shadow"))
    intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.intent_id"), nullable=False, index=True)
    hypothetical_limit_price: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    hypothetical_fill_price: Mapped[Optional[Decimal]] = mapped_column(DecimalText, nullable=True)
    hypothetical_fees: Mapped[Decimal] = mapped_column(DecimalText, nullable=False, default=Decimal("0"))
    viability_divergence: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class OutboxEvent(Base):
    """发件箱事件:事件类型、载荷、投递状态、投递时间(事务发件箱,不丢不重)。"""

    __tablename__ = "outbox_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("outbox"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ExecutionLeaseRow(Base):
    """执行租约(基础设施表,不属十实体):单写者纪律的持久化载体。

    同名租约至多一行;持有者到期未续即可被接管。执行网关无租约不得提交任何订单。
    """

    __tablename__ = "execution_leases"

    lease_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    holder_id: Mapped[str] = mapped_column(String(128), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    renewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReconciliationRun(Base):
    """对账批次:触发原因、差异数、处理结果、完成时间。OPEN 批次存在 = 停新单。"""

    __tablename__ = "reconciliation_runs"

    recon_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("recon"))
    trigger_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    differences_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")  # OPEN / CLOSED
    resolution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
