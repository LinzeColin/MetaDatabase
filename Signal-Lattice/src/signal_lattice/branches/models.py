"""分支结论的稳定数据合同。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BranchVerdict:
    """一个分支对一个标的的确定性结论。

    ``weight`` 与 ``participation_status`` 是 Stage 2 的审计字段：未实现、
    策略范围外、样本不足或尚未满足策略前置条件的结论都不会参与汇总。
    """

    branch_id: str
    symbol: str
    direction: str
    confidence: float
    evidence: dict[str, Any]
    counter_evidence: str
    invalidation: str
    window_used: int
    implemented: bool
    weight: float
    participation_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
