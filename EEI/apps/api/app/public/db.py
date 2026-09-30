"""只读连接池。

三道互相独立的只读保险：
1. 连接角色应是 ``eei_reader``（只授 SELECT，见 apps/api/deploy/readonly_role.sql）；建连时校验，
   角色在任何 public 表上有写权限就拒绝服务（EEI_REQUIRE_READ_ONLY_ROLE=0 可关，仅限本地调试）；
2. 会话级 ``default_transaction_read_only=on``，事务级 ``READ ONLY``；
3. 语句超时、空闲事务超时，慢查询和泄漏的事务不会拖住共用的 Postgres。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg

from .settings import PublicSettings

log = logging.getLogger("eei.public.db")

WRITE_PRIVILEGE_SQL = """
    SELECT COALESCE(bool_or(has_table_privilege(current_user, c.oid,
                                                'INSERT,UPDATE,DELETE,TRUNCATE')), false)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
"""

_IDLE_PROBE_AFTER_SECONDS = 5.0
_MAX_CONNECTION_AGE_SECONDS = 900.0


class DatabaseUnavailable(RuntimeError):
    """数据库连不上、连接池用尽或角色不合规；路由层统一翻成 503。"""


class RoleNotReadOnly(DatabaseUnavailable):
    pass


@dataclass
class _Slot:
    conn: psycopg.Connection
    created_at: float
    released_at: float


class PublicDatabase:
    def __init__(self, settings: PublicSettings) -> None:
        self._settings = settings
        self._idle: queue.LifoQueue[_Slot] = queue.LifoQueue()
        self._sem = threading.BoundedSemaphore(settings.db_pool_size)
        self._closed = False

    # -- 建连 -----------------------------------------------------------------
    def _connect(self) -> psycopg.Connection:
        dsn = self._settings.database_url
        if not dsn:
            raise DatabaseUnavailable("DATABASE_URL is not configured")
        options = (
            "-c default_transaction_read_only=on"
            f" -c statement_timeout={self._settings.statement_timeout_ms}"
            " -c idle_in_transaction_session_timeout=30000"
            " -c lock_timeout=2000"
            " -c timezone=UTC"
        )
        try:
            conn = psycopg.connect(
                dsn,
                connect_timeout=5,
                options=options,
                application_name="eei-api",
                autocommit=False,
            )
        except psycopg.Error as exc:
            name = exc.__class__.__name__
            raise DatabaseUnavailable(f"database connection failed: {name}") from exc
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        try:
            if self._settings.require_read_only_role:
                writable = conn.execute(WRITE_PRIVILEGE_SQL).fetchone()[0]
                conn.rollback()
                if writable:
                    raise RoleNotReadOnly(
                        "database role has write privileges; connect as eei_reader"
                        " (apps/api/deploy/readonly_role.sql)"
                    )
        except BaseException:
            conn.close()
            raise
        return conn

    def _take(self) -> _Slot:
        now = time.monotonic()
        while True:
            try:
                slot = self._idle.get_nowait()
            except queue.Empty:
                return _Slot(self._connect(), now, now)
            stale = now - slot.created_at > _MAX_CONNECTION_AGE_SECONDS
            if not stale and now - slot.released_at > _IDLE_PROBE_AFTER_SECONDS:
                try:
                    slot.conn.execute("SELECT 1")
                    slot.conn.rollback()
                except psycopg.Error:
                    stale = True
            if stale or slot.conn.closed or slot.conn.broken:
                self._discard(slot)
                continue
            return slot

    @staticmethod
    def _discard(slot: _Slot) -> None:
        try:
            slot.conn.close()
        except psycopg.Error:
            pass

    # -- 对外 -----------------------------------------------------------------
    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        if self._closed:
            raise DatabaseUnavailable("database pool is closed")
        if not self._sem.acquire(timeout=self._settings.db_acquire_timeout_seconds):
            raise DatabaseUnavailable("database pool exhausted")
        slot: _Slot | None = None
        try:
            slot = self._take()
            yield slot.conn
        except psycopg.OperationalError as exc:
            if slot is not None:
                self._discard(slot)
                slot = None
            raise DatabaseUnavailable(f"database error: {exc.__class__.__name__}") from exc
        finally:
            if slot is not None:
                try:
                    slot.conn.rollback()
                    slot.released_at = time.monotonic()
                    if slot.conn.closed or slot.conn.broken:
                        raise psycopg.OperationalError("broken connection")
                    self._idle.put(slot)
                except psycopg.Error:
                    self._discard(slot)
            self._sem.release()

    def health(self) -> dict[str, object]:
        """给 /health 用：连得上、读得了、角色只读。"""
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1").fetchone()
                writable = conn.execute(WRITE_PRIVILEGE_SQL).fetchone()[0]
        except DatabaseUnavailable as exc:
            return {"ok": False, "detail": str(exc), "read_only_role": None}
        return {"ok": True, "detail": "postgresql ready", "read_only_role": not writable}

    def close(self) -> None:
        self._closed = True
        while True:
            try:
                self._discard(self._idle.get_nowait())
            except queue.Empty:
                return
