r"""能自动同步的平台，说明书那张表里一个都不许漏（2026-08-13）。

## 已有的门只挡了一个方向

`test_the_guide_does_not_promise_relations_nobody_scans.py` 挡的是**过度承诺**：
说明书说会读的关系，产品必须真会去扫。

**反过来那一侧没人管。** 一个平台进了 `SYNCABLE_NOW`（产品能自动读它了），
而说明书那张「现在能自动同步的」表没跟着加一行——不会有任何判据红，
而他**永远不会知道那个平台可以连**。

后果落在验收第 1 条上：「至少一个真实平台的收藏能自动读进档案馆」。
产品支持了、界面上也画得出按钮，而他照着说明书做，根本不会去点它。
这和「给一颗点不动的按钮」是同一件事的两半——一半是给了不能用的，
一半是能用的没告诉他。

## 判据

`SYNCABLE_NOW` 里每一个平台，它的中文名（或下面登记过的别名）
必须出现在那张表里。

## 别名为什么要显式登记

`generic-web` 的内部标签是「通用网页」，而说明书写的是「**Chrome 书签**」——
**说明书那个说法是对的**：他连的就是 Chrome 书签，「通用网页」对他没有意义。
所以这里认两种写法，但**必须写在这张表里、说得出理由**，
不能靠"包含任意一个词就算过"那种松判据糊过去。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.account_sync import PLATFORM_LABELS, SYNCABLE_NOW  # noqa: E402

GUIDE = ROOT / "docs/使用说明.md"
HEADING = "现在能自动同步的"

# 平台键 → 说明书里**也可以**用的别名，以及为什么。
ALIASES = {
    # 他连的就是 Chrome 书签；「通用网页」是内部说法，对他没有意义。
    "generic-web": ("Chrome 书签",),
}


def _the_table() -> str:
    """取「现在能自动同步的」那张表——到下一个空行分隔的段落为止。"""
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(HEADING)
    rows = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith("|"):
            rows.append(line)
        elif rows and not line.strip():
            break
    return "\n".join(rows)


def test_the_table_was_really_found() -> None:
    """**先证明这把尺子量得到东西。**

    标题改一个字、表格换成别的写法，`_the_table()` 就会返回一小段甚至空串，
    然后下面每一条都空过——一个永远不会红的判据比没有判据更糟。
    """
    table = _the_table()
    assert table.count("\n") >= 3, f"只取到 {table.count(chr(10))+1} 行，多半没取到那张表"
    assert "B站" in table, f"取到的这段里没有 B 站，取错地方了：{table[:120]}"


@pytest.mark.parametrize("platform", sorted(SYNCABLE_NOW))
def test_每个能同步的平台说明书都写了(platform: str) -> None:
    table = _the_table()
    names = (PLATFORM_LABELS.get(platform, platform),) + ALIASES.get(platform, ())
    assert any(name in table for name in names), (
        f"`SYNCABLE_NOW` 里有 {platform}（产品能自动读它），"
        f"而说明书「{HEADING}」那张表里找不到 {' / '.join(names)}。\n"
        f"**他照着说明书做就不会去连它**——产品支持了等于没支持。\n"
        f"要么给那张表加一行，要么（名字不一样时）在本文件 ALIASES 里登记并写下理由。")
