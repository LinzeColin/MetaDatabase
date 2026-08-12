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

# **不走「按形状读」那条路、但同样声明「现在同步得动」的平台**，
# 各自的证据在哪个演练里。这张表存在的理由和上面那条一样：
# `SYNCABLE_NOW` 是「现在点下去会成功」的事实清单，
# **清单上的每一项都得有人真的走过一次**，不能只有一张表说它行。
#
# ★ 往这张表里写之前，**去翻那个演练的报告**，确认它真的验了这件事。
# 我第一版把 generic-web 写进来，理由写的是「shipped_package_drill 覆盖了它」——
# 翻报告才发现那条只证明了「没授权时那句话说得对」，不是「读得到书签」。
# 一张写高了的证据表，比没有这张表更坏：它会让缺口看起来是绿的。
OTHER_PATHS: dict[str, str] = {
    # 打真接口 + 真 Chrome 里跑整条链，两个演练。
    "bilibili": "bilibili_acquisition_drill.py（打真接口）+ bilibili_end_to_end_drill.py（真 Chrome 整条链）",
}

EXEMPT: dict[str, str] = {
    # **Chrome 书签：路由和失败文案都验过了，"真的读到书签"没有。**（2026-08-11）
    #
    # 我第一版把它写进上面那张证据表，说 shipped_package_drill 覆盖了它。
    # 去翻那份报告才发现自己写高了：
    #
    #   connect_bookmarks_said = {ok:false, state:"unauthorized",
    #     error:"还没有获得读取 Chrome 书签的授权。请在连接面板上再点一次「连接账号」…"}
    #
    # 它证明的是**没授权时那句话说得对**（不是把一句英文甩给他），
    # 不是「授权之后书签真的读得进来」。extension_routing_drill 那边则把
    # `syncChromeBookmarks` 整个桩掉了，只验路由走对没有。
    #
    # 而权限那一下要用户手势，演练点不了那个原生弹窗——
    # 此前十个演练是把可选权限提成必给权限绕过去的，
    # 那正是 `harness-grants-what-users-must-earn` 记着的那个坑。
    # 台账里也写着：那 62 条书签只存在于演练里，他的库里根本没有 generic-web 账号。
    #
    # **要解掉它：需要 Owner 在真 Chrome 里点一次「连接账号」并选「允许」。**
    "generic-web": (
        "Chrome 书签：路由（extension_routing_drill，syncChromeBookmarks 被桩掉）"
        "和未授权时的文案（shipped_package_drill 的 connect_bookmarks_said）都验过了，"
        "**「授权之后书签真的读得进来」没有**——那一下要用户手势，演练点不了原生弹窗。"
        "要解掉它：Owner 在真 Chrome 里点一次「连接账号」并选「允许」。"
    ),
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


def syncable_now() -> list[str]:
    """服务端声明「现在真的同步得动」的平台——事实清单，不是愿景清单。"""
    text = (ROOT / "src/social_archive/account_sync.py").read_text(encoding="utf-8")
    marker = "SYNCABLE_NOW: frozenset[str] = frozenset({"
    assert marker in text, "account_sync.py 里找不到 SYNCABLE_NOW——判据失去依附"
    block = text[text.index(marker): text.index("})", text.index(marker))]
    block = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))
    return sorted(set(re.findall(r'"([a-z-]+)"', block)))


def main() -> int:
    production = shape_read_platforms()
    covered = drill_platforms()
    claimed = syncable_now()
    assert production, "一个平台都没解析到——正则跟不上那张表了"
    assert claimed, "SYNCABLE_NOW 解析成空——判据会静静放行所有平台"
    problems = []
    for platform in production:
        if platform in covered or platform in EXEMPT:
            continue
        problems.append(
            f"{platform} 在生产上走「按形状读」这条路，而演练里没有它的夹具，"
            "也没有写明理由的豁免——**这条路对它一次都没被走过**")
    # **更根本的一条**：凡是声明「现在同步得动」的，都得有人真走过一次。
    # 上面那条只管走「按形状读」的；服务端连接器、书签那条路同样要有证据。
    for platform in claimed:
        if platform in covered or platform in EXEMPT or platform in OTHER_PATHS:
            continue
        problems.append(
            f"{platform} 在 SYNCABLE_NOW 里（也就是对他承诺「点下去会成功」），"
            "而没有任何演练走过它的取数路，也没有写明理由的豁免")
    stale_other = sorted(set(OTHER_PATHS) - set(claimed))
    if stale_other:
        problems.append(f"证据表里留着已经不在 SYNCABLE_NOW 里的平台：{stale_other}")
    # **豁免过期 = 两张表里都没有它了。**
    # 第一版只减了「按形状读」那一张，于是 generic-web（它的缺口是在
    # SYNCABLE_NOW 那一侧）被判成过期豁免——判据自己切窄了一档。
    stale = sorted(set(EXEMPT) - set(production) - set(claimed))
    if stale:
        problems.append(f"豁免里还留着两张表都不再有的平台：{stale}——豁免要跟着表收")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "shape_read_in_production": production,
        "syncable_now": claimed,
        "evidence_for_other_paths": {p: OTHER_PATHS[p] for p in claimed if p in OTHER_PATHS},
        "covered_by_a_drill": [p for p in production if p in covered],
        # **两张表的豁免都要列出来。** 第一版只列了「按形状读」那一张里的，
        # 于是 generic-web 的缺口存在、门却不显示它——
        # 这道门存在的全部意义就是让缺口看得见，报告里不显示等于白建。
        "exempt_with_a_reason": {p: EXEMPT[p]
                                 for p in sorted(set(production) | set(claimed))
                                 if p in EXEMPT},
        "problems": problems,
        "what_this_does_not_prove":
            "只保证「有演练走过这条路」。不保证真站的响应长成夹具那样——"
            "那句边界写在演练自己的文件头里，这道门不替它作保。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
