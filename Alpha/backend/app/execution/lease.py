"""单写者执行租约(ALPHA-LIVE-035)。

同名租约同一时刻至多一个持有者;到期未续可被接管。
执行网关每次提交前必须验证租约仍在手;拿不到租约 = 不提交(失败关闭)。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import ExecutionLeaseRow

DEFAULT_LEASE_NAME = "alpha-execution-gateway"
DEFAULT_TTL_SECONDS = 30


class LeaseUnavailableError(Exception):
    """租约被他人有效持有。"""


class LeaseManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        holder_id: str,
        lease_name: str = DEFAULT_LEASE_NAME,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._sessions = session_factory
        self.holder_id = holder_id
        self.lease_name = lease_name
        self._ttl = timedelta(seconds=ttl_seconds)
        self._now = now_fn

    def acquire(self) -> None:
        """取得或接管租约;他人有效持有时抛 LeaseUnavailableError。"""
        now = self._now()
        with self._sessions() as session, session.begin():
            row = session.get(ExecutionLeaseRow, self.lease_name, with_for_update=True)
            if row is None:
                session.add(
                    ExecutionLeaseRow(
                        lease_name=self.lease_name,
                        holder_id=self.holder_id,
                        acquired_at=now,
                        expires_at=now + self._ttl,
                        renewed_at=now,
                    )
                )
                return
            expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if row.holder_id != self.holder_id and expires > now:
                raise LeaseUnavailableError(
                    f"租约 {self.lease_name} 由 {row.holder_id} 持有至 {row.expires_at}"
                )
            row.holder_id = self.holder_id
            row.acquired_at = now
            row.expires_at = now + self._ttl
            row.renewed_at = now

    def renew(self) -> None:
        now = self._now()
        with self._sessions() as session, session.begin():
            row = session.get(ExecutionLeaseRow, self.lease_name, with_for_update=True)
            if row is None or row.holder_id != self.holder_id:
                raise LeaseUnavailableError("续约失败:租约不存在或已被接管")
            expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if expires <= now:
                raise LeaseUnavailableError("续约失败:租约已过期(可能已被接管)")
            row.expires_at = now + self._ttl
            row.renewed_at = now

    def held(self) -> bool:
        """当前是否仍有效持有(提交前必查)。"""
        now = self._now()
        with self._sessions() as session:
            row = session.get(ExecutionLeaseRow, self.lease_name)
            if row is None or row.holder_id != self.holder_id:
                return False
            expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            return expires > now

    def release(self) -> None:
        with self._sessions() as session, session.begin():
            row = session.get(ExecutionLeaseRow, self.lease_name, with_for_update=True)
            if row is not None and row.holder_id == self.holder_id:
                session.delete(row)

    def current_holder(self) -> Optional[str]:
        with self._sessions() as session:
            row = session.get(ExecutionLeaseRow, self.lease_name)
            return row.holder_id if row else None
