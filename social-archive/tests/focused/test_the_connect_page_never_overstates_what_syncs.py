r"""连接页那张卡片，不许说产品其实不会去读的关系（2026-08-12）。

## 它的形状

`options.js` 里有一张 `relationCopy`——「这个平台会读哪几类」的**兜底文案**。
真正显示时的逻辑是：

    平台在 SCANNABLE_RELATIONS 里登记过  → 用 scannableSummary()（真源）
    没登记过                             → 落到 relationCopy（写死的字符串）

2026-08-12 查生产时发现 `x` 那一项写着「书签、点赞」，而 X 在 `NOT_SYNCABLE_YET`
里、本版一条都读不了——**他打开连接页会以为这两样会自动进来**。已改成实话。

## 为什么留着 relationCopy 里那些「用不到」的条目

bilibili / 小红书 / 抖音 那几项仍写着旧话（「收藏夹、稍后再看、历史、点赞」），
但它们**登记过**，所以永远走不到 relationCopy。删掉它们会带来另一个风险：
哪天有人把某个平台从 SCANNABLE_RELATIONS 里摘掉，`relationCopy[platform]`
就是 `undefined`，卡片上会印出「undefined」。

所以两条都钉住：**没登记的平台必须有一句兜底**，
而且那句兜底**不许把不能同步的说成能同步**。

## 我试过一个更「干净」的改法，被判据拦下了

想把 `x` 也在 `SCANNABLE_RELATIONS` 里登记成空（youtube / kuaishou 就是这么做的），
这样卡片自动说「本版还不能自动读」。`test_sync_scope_is_reachable` 当场打红，
理由写在它自己的注释里：**X 走服务端连接器，点下去当场报「零费用门未确认」；
清空范围会把它变成 YouTube 那种「永远转」的形态**。快速失败带原因可以，永远转不行。
所以只改文案，不动登记。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.account_sync import NOT_SYNCABLE_YET  # noqa: E402
from social_archive.scannable_relations import SCANNABLE_RELATIONS  # noqa: E402

OPTIONS = ROOT / "apps/browser-extension/options.js"

# 读起来像「这一类会被自动读进来」的说法。
PROMISE_WORDS = ("收藏夹", "收藏", "点赞", "书签", "稍后再看", "历史",
                 "Saved", "Upvoted", "播放列表", "稍后观看")


def _relation_copy() -> dict[str, str]:
    """把 options.js 里那张兜底表读出来。"""
    text = OPTIONS.read_text(encoding="utf-8")
    start = text.index("const relationCopy")
    block = text[start:text.index("};", start)]
    # 只取形如 `key:"值"` / `"key":"值"` 的项；注释行整行跳过。
    body = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("//"))
    return {k.strip('"'): v for k, v in re.findall(r'([\"\w\-]+)\s*:\s*"([^"]*)"', body)}


def test_the_table_is_actually_parsed() -> None:
    """**正例**：解析不到就等于这条判据在空转。"""
    copy = _relation_copy()
    assert len(copy) >= 5, f"只解析到 {len(copy)} 项——那张表的写法八成变了：{copy}"


def test_every_unregistered_platform_still_has_a_fallback_line() -> None:
    """没登记的平台必须有一句兜底，否则卡片上会印出 `undefined`。"""
    copy = _relation_copy()
    for platform in ("generic-web", "x"):
        if platform in SCANNABLE_RELATIONS:
            continue
        assert copy.get(platform), f"{platform} 没登记又没有兜底文案——卡片会印 undefined"


def test_a_platform_that_cannot_sync_is_not_described_as_if_it_does() -> None:
    """不能同步的平台，兜底文案里不许出现「会读这几类」的说法。

    `x` 就是踩过这个的：写着「书签、点赞」，而它一条都读不了。
    """
    copy = _relation_copy()
    for platform in sorted(NOT_SYNCABLE_YET):
        if platform in SCANNABLE_RELATIONS:
            continue          # 登记过的走 scannableSummary，不看这张表
        line = copy.get(platform, "")
        if not line:
            continue
        hit = [w for w in PROMISE_WORDS if w in line]
        assert not hit, (
            f"{platform} 在 NOT_SYNCABLE_YET 里（本版读不了），"
            f"而连接页兜底文案写着「{line}」——里面的 {hit} 读起来像会自动读进来")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
