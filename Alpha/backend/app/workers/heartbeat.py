"""Worker 心跳读写。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import WorkerHeartbeat


class HeartbeatStore:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._sessions = session_factory
        self._now = now_fn

    def beat(self, worker_name: str, *, status: str = "RUNNING", detail: str = "") -> None:
        with self._sessions() as session, session.begin():
            row = session.get(WorkerHeartbeat, worker_name)
            if row is None:
                session.add(WorkerHeartbeat(worker_name=worker_name, beat_at=self._now(),
                                            status=status, detail=detail))
            else:
                row.beat_at = self._now()
                row.status = status
                row.detail = detail

    def age_seconds(self, worker_name: str) -> Optional[float]:
        with self._sessions() as session:
            row = session.get(WorkerHeartbeat, worker_name)
            if row is None:
                return None
            beat = row.beat_at if row.beat_at.tzinfo else row.beat_at.replace(tzinfo=timezone.utc)
            return (self._now() - beat).total_seconds()

    def snapshot(self) -> dict[str, dict]:
        with self._sessions() as session:
            rows = session.query(WorkerHeartbeat).all()
            return {
                r.worker_name: {
                    "beat_at": (r.beat_at if r.beat_at.tzinfo else r.beat_at.replace(tzinfo=timezone.utc)).isoformat(),
                    "status": r.status,
                    "detail": r.detail,
                }
                for r in rows
            }
