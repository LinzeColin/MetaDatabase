"""交易域模型：订单状态机与十实体(ALPHA-LIVE-010)。

权威规范:任务包 specs/ORDER_STATE_MACHINE.md 与 machine/facts/data_contract.yaml。
本包只含纯领域逻辑与 ORM 模型,不做任何 I/O、不触券商接口。
"""

from backend.app.domain.state_machine import (
    IllegalTransitionError,
    OrderState,
    TERMINAL_STATES,
    assert_transition,
    is_terminal,
    legal_next_states,
)

__all__ = [
    "IllegalTransitionError",
    "OrderState",
    "TERMINAL_STATES",
    "assert_transition",
    "is_terminal",
    "legal_next_states",
]
