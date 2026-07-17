"""订单状态机纯函数实现。

逐字对应任务包 specs/ORDER_STATE_MACHINE.md 第 1 节状态集:

    INTENT_CREATED -> RISK_APPROVED | RISK_REJECTED(终)
    RISK_APPROVED -> SUBMITTING
    SUBMITTING -> SUBMITTED | SUBMIT_FAILED(终, 幂等键保留)
    SUBMITTED -> ACCEPTED | REJECTED(终)
    ACCEPTED -> PARTIALLY_FILLED -> FILLED(终)
    ACCEPTED -> FILLED(终)
    ACCEPTED|PARTIALLY_FILLED -> CANCEL_REQUESTED -> CANCELLED(终, 可带部分成交)
    ACCEPTED|PARTIALLY_FILLED -> EXPIRED(终)
    任意状态 收到无法解释的券商事件 -> UNKNOWN_RECONCILIATION_REQUIRED

规范之外的迁移一律非法:拒绝写入、记审计、标记 UNKNOWN_RECONCILIATION_REQUIRED、停新单
(停新单语义 = 存在未关闭对账批次,见 store 层)。本模块保持纯函数,便于手工复算。
"""

from __future__ import annotations

from enum import Enum


class OrderState(str, Enum):
    INTENT_CREATED = "INTENT_CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    SUBMIT_FAILED = "SUBMIT_FAILED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN_RECONCILIATION_REQUIRED = "UNKNOWN_RECONCILIATION_REQUIRED"


#: 终态。SUBMIT_FAILED 虽为终态但幂等键保留(store 层强制幂等键永不复用,严于规范下限)。
TERMINAL_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.RISK_REJECTED,
        OrderState.SUBMIT_FAILED,
        OrderState.REJECTED,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    }
)

#: 合法迁移表(不含「任意状态 -> UNKNOWN_RECONCILIATION_REQUIRED」,该迁移单列处理)。
#: PARTIALLY_FILLED -> PARTIALLY_FILLED 允许:多笔部分成交折叠为自环。
_LEGAL: dict[OrderState, frozenset[OrderState]] = {
    OrderState.INTENT_CREATED: frozenset({OrderState.RISK_APPROVED, OrderState.RISK_REJECTED}),
    OrderState.RISK_APPROVED: frozenset({OrderState.SUBMITTING}),
    OrderState.SUBMITTING: frozenset({OrderState.SUBMITTED, OrderState.SUBMIT_FAILED}),
    OrderState.SUBMITTED: frozenset({OrderState.ACCEPTED, OrderState.REJECTED}),
    OrderState.ACCEPTED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.EXPIRED,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.EXPIRED,
        }
    ),
    OrderState.CANCEL_REQUESTED: frozenset({OrderState.CANCELLED}),
    OrderState.RISK_REJECTED: frozenset(),
    OrderState.SUBMIT_FAILED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.EXPIRED: frozenset(),
    OrderState.UNKNOWN_RECONCILIATION_REQUIRED: frozenset(),
}


class IllegalTransitionError(Exception):
    """非法状态迁移。调用方必须:拒绝写入、记审计、标记 UNKNOWN、开对账批次(停新单)。"""

    def __init__(self, current: OrderState, attempted: OrderState) -> None:
        self.current = current
        self.attempted = attempted
        super().__init__(f"非法迁移: {current.value} -> {attempted.value}")


def is_terminal(state: OrderState) -> bool:
    return state in TERMINAL_STATES


def legal_next_states(state: OrderState) -> frozenset[OrderState]:
    return _LEGAL[state]


def is_legal(current: OrderState, nxt: OrderState) -> bool:
    """UNKNOWN_RECONCILIATION_REQUIRED 可自任意状态进入(规范第 1 节末行);
    其余迁移必须命中合法迁移表。"""
    if nxt is OrderState.UNKNOWN_RECONCILIATION_REQUIRED:
        return True
    return nxt in _LEGAL[current]


def assert_transition(current: OrderState, nxt: OrderState) -> OrderState:
    if not is_legal(current, nxt):
        raise IllegalTransitionError(current, nxt)
    return nxt
