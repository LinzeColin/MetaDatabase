r"""同步范围不许超过扩展真会去扫的那些（2026-08-10）。

## 它修的是「他从来没有过一次 completed」

Owner 生产库：**20 次同步，0 次 completed**（partial 16 / failed 3 / cancelled 1），
最常见的错误码是 `RELATION_SCOPE_UNCONFIRMED`（8 次）。

逐条查 `sync_run_scope`：

    douyin      favorite  partial      douyin      like         partial
    bilibili    favorite  failed       bilibili    watch_later  failed
    xiaohongshu favorite  partial      xiaohongshu like         partial

**每一次都声明了扩展根本不会扫的关系，而没有一条 scope 收敛成 complete。**

根因：`_scannable_relations` 原来 =「这个平台**允许**出现的关系」减去 `manual_save`。
而 `_relations` 自己的文档串就写着「**用于校验批次，不是同步范围**」。
扩展只扫 `SCANNABLE_RELATIONS`（抖音/小红书/快手/B站都只有 `favorite`），
于是 scope 里多出来的那些**永远等不到终批**——
account_sync.py 自己的注释早写过那种后果：
「点了同步，条目都进来了，圈还一直在转」。

而 `account_sync.py:131` 那句注释写着「由 platform-catalog.js 的
SCANNABLE_RELATIONS 限定扫描范围」——**服务端从来没读过那个文件。**

## 修法

服务端**直接读扩展那一份**（`_load_scannable_relations`），不再抄第二份：
这个仓当天已经因为「两份词典必然漂开」修过三处（失败文案、归档状态、回执键名）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.account_sync import (  # noqa: E402
    SCANNABLE_RELATIONS,
    AccountSyncCoordinator,
)


def test_the_catalog_was_really_parsed() -> None:
    """反空扫：解析出 0 个平台时，下面每条都会白过。"""
    assert len(SCANNABLE_RELATIONS) >= 5, f"只解析出 {SCANNABLE_RELATIONS}——解析坏了"
    assert SCANNABLE_RELATIONS.get("douyin") == ("favorite",), SCANNABLE_RELATIONS
    assert SCANNABLE_RELATIONS.get("bilibili") == ("favorite",), SCANNABLE_RELATIONS


def test_scope_never_exceeds_what_the_extension_scans() -> None:
    for platform, scannable in SCANNABLE_RELATIONS.items():
        scope = AccountSyncCoordinator._scannable_relations(platform)
        extra = [item for item in scope if item not in scannable]
        assert not extra, (
            f"{platform} 的同步范围里有扩展不会扫的关系 {extra}——"
            f"那几条永远等不到终批，这次 run 永远不收敛（他 20 次同步 0 次 completed 就是这个）")


def test_his_two_platforms_are_favorite_only() -> None:
    """他实际连过的那两个：抖音与 B 站，本版本只扫收藏。"""
    assert AccountSyncCoordinator._scannable_relations("douyin") == ["favorite"]
    assert AccountSyncCoordinator._scannable_relations("bilibili") == ["favorite"]


def test_a_platform_outside_the_catalog_keeps_its_allowed_list() -> None:
    """不在那张表里的（服务端取数那条路）不受影响——它不走扩展。"""
    assert "x" not in SCANNABLE_RELATIONS
    assert AccountSyncCoordinator._scannable_relations("x") == ["bookmark", "like"]


def test_the_comment_that_claimed_this_is_now_true() -> None:
    """那句注释说「由 platform-catalog.js 限定」——现在它得真的读那个文件。"""
    source = (ROOT / "src/social_archive/account_sync.py").read_text(encoding="utf-8")
    assert "platform-catalog.js" in source
    assert "_load_scannable_relations" in source, (
        "服务端又不读扩展那份清单了——注释会重新变成一句假话")
