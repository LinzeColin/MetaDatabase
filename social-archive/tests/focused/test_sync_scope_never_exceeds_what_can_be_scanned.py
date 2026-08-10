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

服务端那份由扩展那份**生成**（`scripts/generate_scannable_relations.py`），
不再手抄第二份：这个仓当天已经因为「两份词典必然漂开」修过三处
（失败文案、归档状态、回执键名）。

**第一版是 import 时去读那个 .js，它会让镜像里的 API 起不来**
（`parents[2]` 在仓里是仓根，在 site-packages 里是 `/usr/local/lib/python3.12`）。
所以改成生成物；漂开由下面 `test_the_generated_module_is_in_sync` 打红。
"""

from __future__ import annotations

import re
import subprocess
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


def test_the_server_list_matches_the_extension_catalog() -> None:
    """**钉的是「两边一致」，不是某个函数叫什么名字。**（2026-08-10 改）

    上一版断言 `"_load_scannable_relations" in source`——钉的是实现的名字。
    真源改成生成式之后（那个函数没了，因为 import 时读仓相对路径会让
    镜像里的 API 起不来），这条就红了，而**功能一点没坏**。
    这个仓栽在「陈旧的字面断言」上不止一次。

    现在直接比行为：服务端手上那份，必须逐字等于扩展那份解析出来的。
    """
    text = (ROOT / "apps/browser-extension/content/platform-catalog.js").read_text(encoding="utf-8")
    block = re.search(r"const SCANNABLE_RELATIONS = Object\.freeze\(\{(.*?)\n  \}\);", text, re.S)
    assert block, "platform-catalog.js 里找不到 SCANNABLE_RELATIONS 块——判据在空扫"
    from_js = {platform: tuple(re.findall(r'"([a-z_]+)"', items))
               for platform, items in re.findall(
                   r"(\w+):\s*Object\.freeze\(\[(.*?)\]\)", block.group(1), re.S)}
    assert from_js, "解析出 0 个平台——这不是「没有」，是解析坏了"
    assert dict(SCANNABLE_RELATIONS) == from_js, (
        "服务端那份和扩展那份漂开了——服务端会把扩展不扫的关系列进同步范围，"
        "那一路永远等不到终批，整次 run 不收敛（他生产上 20 次同步 0 次 completed 就是这个）。\n"
        "跑 `python3 scripts/generate_scannable_relations.py --apply` 重新生成。")


def test_the_generated_module_is_in_sync() -> None:
    """生成物落后于真源时，那条重新生成的命令要**当场给出来**。

    这个仓有过「错误提示指向一个不存在的出口」——所以这里连命令一起验。
    """
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_scannable_relations.py")],
        capture_output=True, text=True, check=False)
    assert done.returncode == 0, (
        "scannable_relations.py 和 platform-catalog.js 漂开了：\n"
        + done.stdout + done.stderr)
