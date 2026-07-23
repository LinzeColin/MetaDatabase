"""数据库引擎与会话工厂。

本地开发/测试:SQLite(文件或内存);生产:PostgreSQL(DATABASE_URL 环境变量,040 部署时配置)。
凭据永不进 Git:连接串只从环境读取,默认值为本地 SQLite 相对路径。
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import Base

DEFAULT_SQLITE_PATH = "runtime/alpha_live.sqlite"


def init_engine(url: str | None = None, echo: bool = False) -> Engine:
    """创建引擎并建表。url 缺省时读 ALPHA_DATABASE_URL,再缺省用本地 SQLite。"""
    resolved = url or os.environ.get("ALPHA_DATABASE_URL")
    if not resolved:
        # 07-23 事故教训:环境损坏时曾静默降级到空本地库——实盘模式下这会
        # 丢失幂等键与持仓记忆,可能重复下单,必须失败关闭而不是降级。
        if os.environ.get("ALPHA_MODE", "").upper() == "MICRO_LIVE":
            raise RuntimeError("实盘模式必须显式配置数据库地址,拒绝降级到本地库(失败关闭)")
        Path(DEFAULT_SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
        resolved = f"sqlite:///{DEFAULT_SQLITE_PATH}"
    engine = create_engine(resolved, echo=echo, future=True)
    if engine.dialect.name == "sqlite":
        # SQLite 外键默认关闭;交易域必须强制引用完整性。
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover - 驱动回调
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(engine)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
