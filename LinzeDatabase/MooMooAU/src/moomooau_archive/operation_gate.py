"""Machine-enforced capacity and Kill Criterion gate for sensitive operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from .capacity import CapacityAssessment, CapacityDemand, CapacityPolicy
from .kill_switch import KillImpact

_T = TypeVar("_T")


class OperationGateError(RuntimeError):
    """An operation is disabled by observed capacity or an active Kill Criterion."""


class SensitiveOperation(StrEnum):
    PRODUCTION_RUN = "PRODUCTION_RUN"
    REMOTE_READ = "REMOTE_READ"
    RAW_WRITE = "RAW_WRITE"
    PROCESSED_WRITE = "PROCESSED_WRITE"
    M3 = "M3"
    TIMELINE_WRITE = "TIMELINE_WRITE"
    MODEL_USE = "MODEL_USE"
    BACKFILL = "BACKFILL"


@dataclass(frozen=True, slots=True)
class GateAuthorization:
    operation: SensitiveOperation
    capacity_reason_codes: tuple[str, ...]
    active_kill_id: str | None


_KILL_FLAG = {
    SensitiveOperation.PRODUCTION_RUN: "production_enabled",
    SensitiveOperation.REMOTE_READ: "production_enabled",
    SensitiveOperation.RAW_WRITE: "raw_enabled",
    SensitiveOperation.PROCESSED_WRITE: "processed_enabled",
    SensitiveOperation.M3: "m3_enabled",
    SensitiveOperation.TIMELINE_WRITE: "timeline_enabled",
    SensitiveOperation.MODEL_USE: "model_enabled",
    SensitiveOperation.BACKFILL: "backfill_enabled",
}
_CAPACITY_GATED = frozenset(
    {
        SensitiveOperation.PRODUCTION_RUN,
        SensitiveOperation.RAW_WRITE,
        SensitiveOperation.PROCESSED_WRITE,
        SensitiveOperation.M3,
        SensitiveOperation.TIMELINE_WRITE,
        SensitiveOperation.BACKFILL,
    }
)
_PROJECTED_WRITES = frozenset(
    {
        SensitiveOperation.RAW_WRITE,
        SensitiveOperation.PROCESSED_WRITE,
        SensitiveOperation.TIMELINE_WRITE,
        SensitiveOperation.BACKFILL,
    }
)


class OperationalGate:
    """Authorize immediately before a callable can create external side effects."""

    def __init__(
        self,
        capacity: CapacityAssessment,
        *,
        kill_impact: KillImpact | None = None,
    ) -> None:
        self._capacity = capacity
        self._kill_impact = kill_impact
        self._consumed_capacity = CapacityDemand()

    @property
    def consumed_capacity(self) -> CapacityDemand:
        return self._consumed_capacity

    def preflight(self, operation: SensitiveOperation) -> GateAuthorization:
        return self._authorize(operation, None, require_projection=False)

    def authorize(
        self,
        operation: SensitiveOperation,
        *,
        demand: CapacityDemand | None = None,
    ) -> GateAuthorization:
        return self._authorize(operation, demand, require_projection=True)

    def _authorize(
        self,
        operation: SensitiveOperation,
        demand: CapacityDemand | None,
        *,
        require_projection: bool,
    ) -> GateAuthorization:
        if not isinstance(operation, SensitiveOperation):
            raise OperationGateError("sensitive operation is invalid")
        if self._kill_impact is not None and not getattr(
            self._kill_impact,
            _KILL_FLAG[operation],
        ):
            raise OperationGateError(
                f"{operation.value} blocked by {self._kill_impact.kill_id.value}"
            )
        if operation in _CAPACITY_GATED and not self._capacity.write_allowed:
            raise OperationGateError(f"{operation.value} blocked by fail-closed capacity")
        if operation is SensitiveOperation.BACKFILL and not self._capacity.backfill_allowed:
            raise OperationGateError("BACKFILL blocked outside GREEN capacity")
        if demand is not None and operation not in _PROJECTED_WRITES:
            raise OperationGateError("capacity demand is not valid for this operation")
        if require_projection and operation in _PROJECTED_WRITES:
            if demand is None or demand.is_empty:
                raise OperationGateError(
                    f"{operation.value} blocked without prospective capacity demand"
                )
            snapshot = self._capacity.observed_snapshot
            limits = self._capacity.limits
            if snapshot is None or limits is None:
                raise OperationGateError(
                    f"{operation.value} blocked without capacity observation context"
                )
            combined = self._consumed_capacity.combine(demand)
            projected = CapacityPolicy().evaluate(snapshot, limits, combined)
            if not projected.write_allowed:
                raise OperationGateError(
                    f"{operation.value} blocked by projected fail-closed capacity"
                )
            if operation is SensitiveOperation.BACKFILL and not projected.backfill_allowed:
                raise OperationGateError("BACKFILL blocked by projected non-GREEN capacity")
        return GateAuthorization(
            operation,
            self._capacity.reason_codes,
            self._kill_impact.kill_id.value if self._kill_impact is not None else None,
        )

    def execute(
        self,
        operation: SensitiveOperation,
        action: Callable[[], _T],
        *,
        demand: CapacityDemand | None = None,
    ) -> _T:
        self.authorize(operation, demand=demand)
        if operation in _PROJECTED_WRITES:
            if demand is None:
                raise OperationGateError("prospective capacity demand disappeared")
            # Reserve before invoking the callback and never refund on an exception: a remote
            # response can be uncertain after partial persistence.
            self._consumed_capacity = self._consumed_capacity.combine(demand)
        return action()
