#!/usr/bin/env python3
r"""走「按形状读列表」那条路的平台，有没有一个演练真走过（2026-08-11）。

## 这道门是被一个隐形缺口逼出来的

两张表在两个文件里，从来没有任何东西把它们对过：

    apps/browser-extension/background.js   SHAPE_READ_PLATFORMS
        小红书 / **抖音** / **快手** / Reddit / Instagram   ← 生产上真走这条路的
    scripts/list_shape_end_to_end_drill.py PLATFORMS
        小红书 / Reddit / Instagram                        ← 有夹具、真被走过的

**抖音和快手在生产上走这条路，而这条路对它们一次都没被走过。**
他生产库里最大的那个账号正是抖音（86 条），8/4 那次同步的错误码是
`BROWSER_SCAN_FAILED`——恰好就是这条路上的失败。

`check_sync_promises_match_reality.py` 查的是「四张表说的话一不一致」，
它的文件头自己写着：「『那条取数路真的读得回东西』不在这里」。
那件事此前只有 B 站有人管（两个 bilibili 演练），别的平台一个都没有。

## 判据

`SHAPE_READ_PLATFORMS` 里的每个平台，要么在演练的 `PLATFORMS` 里有夹具，
要么在下面 `EXEMPT` 里有一条**写明理由**的豁免。默认答案是「必须有夹具」。

## 豁免不是白名单

`EXEMPT` 里每条都要说清「为什么现在不能有夹具」，而且理由必须是
「我拿不到这个事实」，不能是「还没做」。
编一份自己想当然的夹具比没有更坏：它要么给假绿，要么给假红——
而假红会把人推去改产品来迁就一份编造的响应
（`fixtures-cleaner-than-the-real-thing` 的反面）。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKGROUND = ROOT / "apps/browser-extension/background.js"
DRILL = ROOT / "scripts/list_shape_end_to_end_drill.py"

EXEMPT: dict[str, str] = {
    "kuaishou": (
        "快手真实响应的字段名我核实不了（要 Owner 的登录态）。写过一份夹具"
        "（feeds[].photoId/caption/userName），跑出来 7 条里 3 条丢作者——"
        "因为 userName 不在 list-shape.js 的 AUTHOR_KEYS 里（那张表里是 user_name）。"
        "顺着那个『失败』改产品，就是拿我自己编的夹具去改生产代码。停在这里，"
        "缺口记录在案。**要解掉它，需要一份真实的快手收藏响应的字段名。**"
    ),
}


def shape_read_platforms() -> list[str]:
    text = BACKGROUND.read_text(encoding="utf-8")
    marker = "const SHAPE_READ_PLATFORMS = Object.freeze({"
    assert marker in text, "background.js 里找不到 SHAPE_READ_PLATFORMS——判据失去依附"
    block = text[text.index(marker): text.index("});", text.index(marker))]
    block = "\n".join(line for line in block.splitlines()
                      if not line.lstrip().startswith("//"))
    return sorted({m.group(1) for m in re.finditer(r"^\s{2}([a-z-]+):\s*\"", block, re.M)})


def drill_platforms() -> list[str]:
    spec = importlib.util.spec_from_file_location("list_shape_drill_under_check", DRILL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return sorted(module.PLATFORMS)


def main() -> int:
    production = shape_read_platforms()
    covered = drill_platforms()
    assert production, "一个平台都没解析到——正则跟不上那张表了"
    problems = []
    for platform in production:
        if platform in covered or platform in EXEMPT:
            continue
        problems.append(
            f"{platform} 在生产上走「按形状读」这条路，而演练里没有它的夹具，"
            "也没有写明理由的豁免——**这条路对它一次都没被走过**")
    stale = sorted(set(EXEMPT) - set(production))
    if stale:
        problems.append(f"豁免里还留着已经不走这条路的平台：{stale}——豁免要跟着表收")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "shape_read_in_production": production,
        "covered_by_a_drill": [p for p in production if p in covered],
        "exempt_with_a_reason": {p: EXEMPT[p] for p in production if p in EXEMPT},
        "problems": problems,
        "what_this_does_not_prove":
            "只保证「有演练走过这条路」。不保证真站的响应长成夹具那样——"
            "那句边界写在演练自己的文件头里，这道门不替它作保。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
