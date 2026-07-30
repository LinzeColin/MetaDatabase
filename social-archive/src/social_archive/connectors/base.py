from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

GateState = Literal["pass", "fail", "unknown", "not_required"]


class ConnectorError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class ConnectorResult:
    connector_id: str
    run_id: str
    status: Literal["success", "partial", "failed", "blocked_environment", "degraded"]
    observations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    scan_receipt: dict[str, Any] = field(default_factory=lambda: {"completeness": "unknown", "item_count": 0})
    errors: list[dict[str, Any]] = field(default_factory=list)


class SourceConnector(Protocol):
    connector_id: str
    display_name: str

    def health(self) -> dict[str, Any]: ...
    def capture(self, payload: dict[str, Any]) -> ConnectorResult: ...
