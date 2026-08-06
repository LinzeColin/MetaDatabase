#!/usr/bin/env python3
"""界面承诺的同步能力，和代码里真有的实现，对得上吗（v0.0.0.7 / G2）。

## 为什么单开一道

Owner 2026-08-06 之前撞到的那件事，根子是**同一件事在四个地方各说各的**：

    服务端  SYNCABLE_NOW            —— 「这个平台能同步」
    服务端  NOT_SYNCABLE_YET        —— 「这个平台还不能，原因是…」
    扩展    acquireRelationItems()  —— 取数路到底做没做出来
    扩展    SCANNABLE_RELATIONS     —— 这一版真的会去枚举哪些关系

任意两处漂开，用户看到的都是同一种东西：**一颗结构上不可能成功的按钮**。
他的原话是「点击同步不就是自动刷新全部同步吗，怎么实际功能和显示文字还不一样」。

单元测试守着其中几条，但那是按平台一个个写死的。这道门反过来：
**枚举所有平台，逐个把四处对一遍**，谁都不许被漏掉。

## 五条判据

1. 每个平台必须**恰好**在 SYNCABLE_NOW / NOT_SYNCABLE_YET 之一里
   （两边都在 → 卡片上会同时出现「立即同步」和「本版本还不能」）。
2. 在 SYNCABLE_NOW 里 → `acquireRelationItems` 里必须真有它的分支，
   或者它有服务端连接器。否则点下去必然掉进那个 throw。
3. 不在 SYNCABLE_NOW 里 → 必须有一句写给人看的原因，
   且要给出**现在真的能做的那个动作**。
4. SCANNABLE_RELATIONS 里的关系必须是该平台声明过的关系的子集。
5. 声明能同步的平台，**扫描范围不能是空的**。

## 它不保证什么

只看静态的四张表对不对得上。**「那条取数路真的读得回东西」不在这里**——
那是 bilibili_acquisition_drill.py（打真接口）和 bilibili_end_to_end_drill.py
（真 Chrome 里跑整条链）的事。这道门只防「说的和写的不一样」。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BACKGROUND = ROOT / "apps/browser-extension/background.js"
CATALOG = ROOT / "apps/browser-extension/content/platform-catalog.js"


def _braced_body(js: str, name: str) -> str:
    """数括号取函数体。先跳过参数表，否则会撞上解构参数。"""
    start = js.index(f"function {name}")
    paren = js.index("(", start)
    depth = 0
    for index in range(paren, len(js)):
        if js[index] == "(":
            depth += 1
        elif js[index] == ")":
            depth -= 1
            if depth == 0:
                paren = index
                break
    opening = js.index("{", paren)
    depth = 0
    for index in range(opening, len(js)):
        if js[index] == "{":
            depth += 1
        elif js[index] == "}":
            depth -= 1
            if depth == 0:
                return js[opening: index + 1]
    raise ValueError(f"{name} 的花括号没有闭合")


def _scannable() -> dict[str, list[str]]:
    """从 platform-catalog.js 里读 SCANNABLE_RELATIONS。"""
    text = CATALOG.read_text(encoding="utf-8")
    block = text.split("const SCANNABLE_RELATIONS = Object.freeze({", 1)[1].split("});", 1)[0]
    out: dict[str, list[str]] = {}
    for line in block.splitlines():
        found = re.match(r'\s*([a-z0-9-]+):\s*Object\.freeze\(\[([^\]]*)\]\)', line)
        if found:
            out[found.group(1)] = re.findall(r'"([^"]+)"', found.group(2))
    return out


def main() -> int:
    from social_archive.account_sync import (
        NOT_SYNCABLE_YET,
        PLATFORM_RELATIONS,
        SERVER_ACCOUNT_CONNECTORS,
        SYNCABLE_NOW,
    )

    background = BACKGROUND.read_text(encoding="utf-8")
    seam = _braced_body(background, "acquireRelationItems")
    # **取数路不止一条。** 第一版只看 acquireRelationItems，于是把
    # `generic-web`（Chrome 书签）报成「没有实现」——而它走的是
    # `syncAccountById` 里的专用分支 syncChromeBookmarks()，
    # 那条路 T04 实测 62 条全量跑通，是这个产品里最早能用的一条。
    # 一道把唯一跑通过的平台判成坏的门，会被人直接关掉。
    router = _braced_body(background, "syncAccountById")
    # 第四条（v0.0.0.21）：按形状认页面自己发的列表。缝隙里不出现平台名——
    # 它查 SHAPE_READ_PLATFORMS，所以得去那张表里看。
    shape_block = re.search(
        r"const SHAPE_READ_PLATFORMS = Object\.freeze\(\{(.*?)\}\);", background, re.S)
    shape_platforms = (set(re.findall(r"^\s*([a-z0-9-]+):", shape_block.group(1), re.M))
                       if shape_block else set())
    scannable = _scannable()
    problems: list[dict] = []

    for platform in sorted(PLATFORM_RELATIONS):
        syncable = platform in SYNCABLE_NOW
        explained = platform in NOT_SYNCABLE_YET
        if syncable and explained:
            problems.append({"platform": platform, "problem":
                             "同时出现在「能同步」和「还不能同步」两张表里——"
                             "卡片上会同时画出「立即同步」和「本版本还不能自动读取」"})
        if not syncable and not explained:
            problems.append({"platform": platform, "problem":
                             "两张表都没有它——界面画「立即同步」而原因是空串，"
                             "点下去什么也不会发生，也没有一句话解释"})
        if syncable:
            # 三条合法的取数路，命中任意一条就算接上了：
            #   ① 浏览器取数缝隙 acquireRelationItems 的分支（B 站走这条）
            #   ② syncAccountById 里的专用分支（Chrome 书签走这条）
            #   ③ 服务端连接器（x / reddit / instagram 走这条）
            wired = (f'"{platform}"' in seam
                     or f'"{platform}"' in router
                     or platform in SERVER_ACCOUNT_CONNECTORS
                     or platform in shape_platforms)
            if not wired:
                problems.append({"platform": platform, "problem":
                                 "声明能同步，但三条取数路都没有它——"
                                 "acquireRelationItems 里没分支、syncAccountById 里没专用路、"
                                 "SHAPE_READ_PLATFORMS 里没有它、服务端也没连接器。"
                                 "点下去必然掉进那个 throw"})
            relations = scannable.get(platform, PLATFORM_RELATIONS.get(platform, []))
            if not relations:
                problems.append({"platform": platform, "problem":
                                 "声明能同步，扫描范围却是空的——那次同步永远收敛不了"})
        if not syncable and explained:
            reason = NOT_SYNCABLE_YET[platform]
            if "现在可以" not in reason:
                problems.append({"platform": platform, "problem":
                                 "只说了不能，没说现在真的能做什么"})

    for platform, relations in scannable.items():
        declared = set(PLATFORM_RELATIONS.get(platform, []))
        extra = sorted(set(relations) - declared)
        if extra:
            problems.append({"platform": platform, "problem":
                             f"扫描范围里有这个平台没声明过的关系：{extra}"})

    report = {
        "status": "PASS" if not problems else "FAIL",
        "platforms_checked": len(PLATFORM_RELATIONS),
        "syncable_now": sorted(SYNCABLE_NOW),
        "scannable_relations": scannable,
        "server_handled": sorted(SERVER_ACCOUNT_CONNECTORS),
        "problems": problems,
        "message_zh": ("界面承诺的和代码里有的，逐个平台对上了。"
                       if not problems else
                       "**有平台的承诺和实现对不上**——用户会点到一颗不可能成功的按钮。"),
        "what_this_does_not_prove": (
            "只对四张静态表。「那条取数路真的读得回东西」由 "
            "bilibili_acquisition_drill.py（打真接口）与 "
            "bilibili_end_to_end_drill.py（真 Chrome 跑整条链）去证。"
        ),
    }
    out = ROOT / "evidence/G2/SYNCABLE_MATCHES_REALITY.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
