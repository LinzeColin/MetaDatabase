from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

WriteRouteMode = Literal["forbidden", "hidden"]


def _int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return max(int(raw), minimum)


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PublicSettings:
    """公开数据面的全部运行参数，只来自环境变量。没有任何写入开关——写入面不在这个入口里。"""

    database_url: str | None = None
    # 连接池大小：每个请求占一条连接，Postgres 只有 max_connections=20 且与 refresh/watch 共用。
    db_pool_size: int = 4
    db_acquire_timeout_seconds: float = 5.0
    # 单条语句上限；explore 在 hops=2 下的每条语句都远小于它，慢查询宁可失败也不拖住整台机器。
    statement_timeout_ms: int = 8000
    # 启动/建连时校验所连角色不可写（eei_reader）；置 0 只为在本地用属主账号调试。
    require_read_only_role: bool = True
    # 写入类路由的应答方式：forbidden=403（默认，明说被关了）；hidden=404（像没有这条路由）。
    write_route_mode: WriteRouteMode = "forbidden"
    # 全量发布门扫描（发布数、按天曲线、家族构成）的缓存时长；explore 等请求式查询永远现算。
    surface_stats_ttl_seconds: int = 1800
    # 便宜的脉搏部分（事件日曲线、来源新鲜度、数据截至）的缓存时长。
    pulse_ttl_seconds: int = 120
    build_sha: str = "unbound"
    build_time: str | None = None
    deploy_id: str | None = None
    cors_allow_origin: str = "*"


def get_public_settings() -> PublicSettings:
    mode = os.getenv("EEI_WRITE_ROUTE_MODE", "forbidden").strip().lower()
    if mode not in {"forbidden", "hidden"}:
        raise ValueError("EEI_WRITE_ROUTE_MODE must be forbidden or hidden")
    return PublicSettings(
        database_url=os.getenv("DATABASE_URL") or None,
        db_pool_size=_int("EEI_DB_POOL_SIZE", PublicSettings.db_pool_size),
        db_acquire_timeout_seconds=float(
            os.getenv("EEI_DB_ACQUIRE_TIMEOUT_SECONDS", PublicSettings.db_acquire_timeout_seconds)
        ),
        statement_timeout_ms=_int(
            "EEI_DB_STATEMENT_TIMEOUT_MS", PublicSettings.statement_timeout_ms
        ),
        require_read_only_role=_flag("EEI_REQUIRE_READ_ONLY_ROLE", True),
        write_route_mode=mode,  # type: ignore[arg-type]
        surface_stats_ttl_seconds=_int(
            "EEI_SURFACE_STATS_TTL_SECONDS", PublicSettings.surface_stats_ttl_seconds, minimum=5
        ),
        pulse_ttl_seconds=_int(
            "EEI_PULSE_TTL_SECONDS", PublicSettings.pulse_ttl_seconds, minimum=1
        ),
        build_sha=os.getenv("EEI_BUILD_SHA", "unbound") or "unbound",
        build_time=os.getenv("EEI_BUILD_TIME") or None,
        deploy_id=os.getenv("EEI_DEPLOY_ID") or None,
        cors_allow_origin=os.getenv("EEI_PUBLIC_CORS_ORIGIN", "*") or "*",
    )
