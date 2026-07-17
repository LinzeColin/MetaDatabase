"""券商中立基础契约(specs/MOOMOO_ADAPTER_CONTRACT.md 第 2、3、4 节)。

只定义数据形状、错误分类与模式映射;不含任何网络调用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class SystemMode(str, Enum):
    DISABLED = "DISABLED"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    MICRO_LIVE = "MICRO_LIVE"
    HALTED = "HALTED"


class TrdEnv(str, Enum):
    SIMULATE = "SIMULATE"
    REAL = "REAL"
    NONE = "NONE"  # 不建交易上下文


#: 契约第 3 节环境映射:系统模式 -> (TrdEnv, 是否允许建可下单上下文)
MODE_TO_TRD_ENV: dict[SystemMode, tuple[TrdEnv, bool]] = {
    SystemMode.DISABLED: (TrdEnv.NONE, False),
    SystemMode.PAPER: (TrdEnv.SIMULATE, True),
    SystemMode.SHADOW: (TrdEnv.NONE, False),   # 仅行情+账户只读
    SystemMode.MICRO_LIVE: (TrdEnv.REAL, True),  # 十一门禁全过后
    SystemMode.HALTED: (TrdEnv.NONE, False),   # 仅允许撤单与查询(撤单走已有会话)
}


class BrokerErrorKind(str, Enum):
    RETRYABLE_NETWORK = "RETRYABLE_NETWORK"
    REJECTED_BY_BROKER = "REJECTED_BY_BROKER"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN = "UNKNOWN"  # 一律失败关闭并触发对账


class BrokerError(Exception):
    def __init__(self, kind: BrokerErrorKind, message: str, raw_code: Optional[str] = None) -> None:
        self.kind = kind
        self.raw_code = raw_code
        super().__init__(f"[{kind.value}] {message} (raw={raw_code})")


class AccountMismatchError(Exception):
    """acc_id 与环境预期不符:立即失败关闭,禁止任何后续调用。"""


@dataclass(frozen=True)
class Health:
    opend_connected: bool
    quote_connected: bool
    trade_unlocked: bool
    checked_at: datetime


@dataclass(frozen=True)
class Account:
    acc_id: str
    currency: str
    status: str  # ACTIVE / RESTRICTED / ...
    trd_env: str
    account_type: str = ""


@dataclass(frozen=True)
class Funds:
    currency: str
    cash: Decimal
    buying_power: Decimal
    total_assets: Decimal
    as_of: datetime


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    cost_price: Decimal
    market_value: Decimal
    currency: str
    as_of: datetime


@dataclass(frozen=True)
class OpenOrderInfo:
    broker_order_id: str
    symbol: str
    side: str
    quantity: int
    filled_quantity: int
    price: Optional[Decimal]
    status: str
    submitted_at: datetime
    remark: str = ""  # 幂等键回传通道(可靠性待真机核验)


@dataclass(frozen=True)
class FillInfo:
    broker_execution_id: str
    broker_order_id: str
    symbol: str
    side: str
    quantity: int
    price: Decimal
    executed_at: datetime


@dataclass(frozen=True)
class QuotePermission:
    market: str
    level: str
    ok: bool


@dataclass(frozen=True)
class ProbeEvidence:
    """辖区能力探针输出(契约第 4.5 条):三项全绿才可开 REAL 买入。"""

    acc_id: str
    account_status: str
    trd_permissions: list[str] = field(default_factory=list)
    quote_permissions: list[QuotePermission] = field(default_factory=list)
    probed_at: Optional[datetime] = None
