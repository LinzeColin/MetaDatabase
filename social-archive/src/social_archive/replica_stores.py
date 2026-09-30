"""哪些远端副本算「必须有」——OCI 退役后这个集合不再写死三个。

## 为什么有这个文件

制品原来必须在 R2、OCI、GitHub 三处都验过才算 `complete`。OCI 账号 2026-09-30 已过期
（Owner：「以后没有 OCI」），**只要 OCI 还在这个集合里，任何新制品都永远到不了
`complete`**：

    2026-09-05 15:57 之后进来的 4,704 个制品全部卡在 `staged`
    → `list_completed_content_bundles()` 只认 complete → 私有库事实不再同步
    → `backup.py` 报「没有已验证的完成态事实」
    → 三条备份链同时红

所以必须让「必须有的副本」是一个**可配置的集合**，而不是散落在八个脚本里的字面量。

## 怎么配

环境变量 `SOCIAL_ARCHIVE_REPLICA_STORES`，逗号分隔，按副本链顺序写：

    未设置 / 空          →  r2,oci,github   （老行为，测试默认用它）
    r2,github            →  OCI 退役后的生产配置（`.env.example` 与 `/etc/social-archive/social-archive.env`）

规则（写错就直接报错，**不静默兜底**）：
· 只认 r2、oci、github；`r2` 与 `github` 必须在；不许重复。
· 副本链顺序固定 r2 → oci → github：GitHub 只接收「前面的副本都已验证」的密文。
"""

from __future__ import annotations

import os

ENV_NAME = "SOCIAL_ARCHIVE_REPLICA_STORES"
CANONICAL_ORDER: tuple[str, ...] = ("r2", "oci", "github")


class ReplicaStoresConfigError(ValueError):
    """`SOCIAL_ARCHIVE_REPLICA_STORES` 写错了。"""


def parse_replica_stores(raw: str | None) -> tuple[str, ...]:
    text = (raw or "").strip()
    if not text:
        return CANONICAL_ORDER
    items = [part.strip().lower() for part in text.split(",") if part.strip()]
    if len(set(items)) != len(items):
        raise ReplicaStoresConfigError(f"{ENV_NAME} 含重复项：{raw!r}")
    unknown = [item for item in items if item not in CANONICAL_ORDER]
    if unknown:
        raise ReplicaStoresConfigError(f"{ENV_NAME} 含不认识的副本目标 {unknown}（只认 {list(CANONICAL_ORDER)}）")
    for mandatory in ("r2", "github"):
        if mandatory not in items:
            raise ReplicaStoresConfigError(f"{ENV_NAME} 必须包含 {mandatory}：{raw!r}")
    return tuple(store for store in CANONICAL_ORDER if store in items)


def replica_stores() -> tuple[str, ...]:
    """必须有的副本目标，副本链顺序。每次调用现读环境，不缓存（测试与生产都靠它换配置）。"""
    return parse_replica_stores(os.getenv(ENV_NAME))


def oci_enabled() -> bool:
    return "oci" in replica_stores()


def stores_before_github() -> tuple[str, ...]:
    """GitHub 之前的副本目标——GitHub 只接收这些都已验证的密文。"""
    return tuple(store for store in replica_stores() if store != "github")
