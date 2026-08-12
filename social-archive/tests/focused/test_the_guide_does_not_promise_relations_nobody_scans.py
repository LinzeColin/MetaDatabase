r"""说明书那张「会自动读什么」的表，不许写产品其实不会去读的关系（2026-08-12）。

## 撞见它的经过

说明书 B 站那一行长期写着「收藏夹、稍后再看、**浏览历史**、**点赞** 都会读进来」，
2026-08-12 我按 Owner 的裁定停掉历史，顺手把它改成「收藏夹 / 稍后再看 / 点赞」。
**两版都在过度承诺。** 查生产才发现：

    PLATFORM_RELATIONS["bilibili"]   = favorite, watch_later, like   ← 只是「允许存在」
    SCANNABLE_RELATIONS["bilibili"]  = ("favorite",)                 ← 扩展真会去枚举的

也就是说自动同步**只读收藏夹**。稍后再看和点赞能挂在库里（手动存的、
早期版本留下的），但没有任何一次同步会去枚举它们。

而且他库里那些点赞**是抖音的**——B 站一条点赞都没有。

## 为什么已有的那道门看不见

`check_the_guide_matches_the_product.py` 查的是「说明里点名的平台/按钮/数字
在不在产品里」。**它不比对「说明说会读哪几类关系」和「产品真会扫哪几类」**——
这两句话可以各自成立而合起来是假的。

## 判据

把那张表里每一行提到的关系词翻成关系键，要求它是该平台
`SCANNABLE_RELATIONS` 的子集。多说一个字都算过度承诺。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.scannable_relations import SCANNABLE_RELATIONS  # noqa: E402

GUIDE = ROOT / "docs/使用说明.md"

# 说明书里会出现的关系说法 → 关系键。**只放会被读者理解成「自动读这个」的词**。
RELATION_WORDS = {
    "收藏夹": "favorite",
    "稍后再看": "watch_later",
    "点赞": "like",
    "浏览历史": "history",
    "观看历史": "history",
}
# 表里的平台名 → 平台键。
#
# **Chrome 书签（generic-web）故意不在这里**：它根本不走 SCANNABLE_RELATIONS
# 那条路——`background.js` 直接发 `relation_types: ["bookmark"]`，
# 而 `SCANNABLE_RELATIONS.get("generic-web")` 是 `None`。
# 拿一个空集合去卡它，只会把一行正确的话打红。
# 这是**有意留白，不是漏了**；哪天书签也走同一条路，再把它加进来。
PLATFORM_WORDS = {"B站": "bilibili", "小红书": "xiaohongshu", "抖音": "douyin",
                  "快手": "kuaishou", "Reddit": "reddit", "Instagram": "instagram"}


def _auto_read_rows() -> list[tuple[str, str]]:
    """取「会自动读什么」那张表的每一行 →（平台名, 那一格的话）。"""
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("| 平台 | 会自动读什么 |")
    end = text.index("\n\n", start)
    rows = []
    for line in text[start:end].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] in ("平台", "---"):
            continue
        rows.append((cells[0], cells[1]))
    return rows


def test_the_table_is_actually_found() -> None:
    """**正例**：解析不到就等于这条判据在空转，而空转会一路绿。"""
    rows = _auto_read_rows()
    assert len(rows) >= 3, f"只解析到 {len(rows)} 行——那张表的格式八成变了"


@pytest.mark.parametrize("platform_word,platform_key", sorted(PLATFORM_WORDS.items()))
def test_no_row_promises_a_relation_that_is_never_scanned(
    platform_word: str, platform_key: str
) -> None:
    """说明里写会自动读的关系，必须真的在扫描范围里。"""
    scannable = set(SCANNABLE_RELATIONS.get(platform_key, ()))
    for name, promise in _auto_read_rows():
        if platform_word not in name:
            continue
        # **只看第一个括号之前那段。**
        #
        # 括号里放的是澄清（「不再采浏览历史」「稍后再看和点赞本来就没在自动读」），
        # 那些句子**恰恰是在说不读**，把它们算成承诺就会把一行正确的话打红。
        # 我第一版用两条 `re.sub` 去掐那些否定短语，结果掐掉「本来就没在自动读」
        # 之后剩下「稍后再看和点赞」，判据在**正确的说明书上**就红了——
        # 逐条掐关键词永远掐不干净，按结构切才对。
        cleaned = re.split(r"[（(]", promise, maxsplit=1)[0]
        for word, relation in RELATION_WORDS.items():
            if word in cleaned and relation not in scannable:
                pytest.fail(
                    f"说明书说 {platform_word} 会自动读「{word}」，而 "
                    f"SCANNABLE_RELATIONS[{platform_key}]={sorted(scannable)} 里没有 "
                    f"{relation}——**同步一次都不会去枚举它**，这是过度承诺")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
