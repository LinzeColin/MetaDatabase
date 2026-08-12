#!/usr/bin/env python3
r"""使用说明里的每一步，都得有一个演练真的走过它（2026-08-12）。

## 这一条守的是 Owner 验收标准的第 2 条

    「一份普通人照着做得完的使用说明：装插件 → 连账号 → 看见条目，
      每一步都指得出点哪儿。说明里写的每一步都必须被判据验过真的存在。」

已经有 `check_the_guide_matches_the_product.py` 在守前半句——它把说明里
每一处「按钮名」拿到九个界面文件里去找，找不到就红。实测有牙：
往说明里塞一句「点右上角的『一键导入全部历史』」，它当场打红并点名。

**而它只回答「这颗按钮存在吗」，不回答「这一步有人走过吗」。**
按钮个个都在、而那一串连起来走不通，是这个仓栽过的另一种跟头
（「单步命令都验过≠链条走得通」）。

## 它怎么验

把说明里每一个步骤小标题抽出来，要求**每一个都登记了一个真的在跑的演练**。

- 说明里新加一节而没人认领 → **红**。这是它的主要用途：
  登记表自己不会告诉你它少了谁，所以反过来从实况映射回登记表。
- 登记的脚本不在磁盘上 → **红**（改名／删掉之后这里会失去依附，
  要大声失效，不许安静放行）。

## 它不保证什么

- **不保证那个演练真的覆盖了那一步的每个细节。** 它保证的是「这一步有主人」，
  不是「这一步被验穷尽了」。谁认领了，谁的注释里要说清覆盖到哪。
- 不查步骤顺序、不查语气。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "使用说明.md"

# 每一节由谁走过。**值是脚本名，必须真的在 scripts/ 下。**
#
# 登记的时候要问自己一句：那个脚本真的会做这一步吗？
# 「名字听起来像」不算——我登记之前逐个打开看过它 note()/断言里写的是什么。
OWNED_BY = {
    "第 1 步：装插件":
        ("extension_install_page_drill.py",
         "它在真 Chrome 里装一次那个包，并验安装页把「下载」和后续那几步画出来"),
    "第 2 步：打开资料库":
        ("pwa_render_drill.py",
         "它在真 Chrome 里打开资料库那一页，读回 DOM——包括「连接新账号」那个弹窗"),
    # 键要和标题**一字不差**（连那个括号里的补充一起）。我第一次少抄了括号，
    # 这道门当场报「这一节没人走过」，反向那条又报「登记了而说明里没有」——
    # 两头一起指同一处，正是它该有的样子。
    "第 3 步：连一个账号（**就在资料库这一页上，不跳走**）":
        ("from_zero_drill.py",
         "它从空库开始：能开始连 → 连接完成拿到账号和首同步 → 库里看得见它"),
    "想自动同步的：点「立即同步」":
        ("from_zero_drill.py",
         "同一个演练里验了「连上之后它自己会跑（auto_sync 开着）」和重连后恢复"),
    "想手动存某一条：点插件图标 → 「保存当前页面」":
        ("extension_save_page_drill.py",
         "它真去点那颗「保存当前页面」，并回读那一条进没进档案馆"),
    "把东西拿进 Obsidian（或者随便拿走）":
        ("check_his_markdown_export_still_works.py",
         "它在生产上真下载一次 markdown.zip 并逐份检查；"
         "他本机那一份由 check_his_obsidian_vault_is_intact.py 接着验"),
    "按收藏夹看":
        ("list_shape_end_to_end_drill.py",
         "它按收藏夹/关系类型走一遍列表形状，验分组读得出来"),
}

STEP_HEADING = re.compile(r"^###\s+(.+?)\s*$", re.M)


def main() -> int:
    if not GUIDE.is_file():
        print(json.dumps({"status": "FAIL", "why": f"{GUIDE} 不在——判据失去依附，不是通过"},
                         ensure_ascii=False))
        return 4

    text = GUIDE.read_text(encoding="utf-8")
    headings = [h.strip() for h in STEP_HEADING.findall(text)]
    problems: list[str] = []

    if not headings:
        problems.append("**说明里一个步骤小标题都没抽到**——正则多半失效了，这不是通过")

    for heading in headings:
        owner = OWNED_BY.get(heading)
        if owner is None:
            problems.append(
                f"说明里这一节没人走过：「{heading}」"
                " —— 给它登记一个真的在跑的演练，或者说清为什么这一节不需要"
            )
            continue
        script, _why = owner
        if not (ROOT / "scripts" / script).is_file():
            problems.append(
                f"「{heading}」登记的是 {script}，而 scripts/ 下没有这个文件"
                " —— 脚本改名或删了，这一步现在没人走"
            )

    # 反向：登记表里有、而说明里已经没有的，也要说出来（免得越积越多没人清）
    stale = sorted(set(OWNED_BY) - set(headings))

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "guide": str(GUIDE.relative_to(ROOT)),
        "steps_in_the_guide": len(headings),
        "steps_with_an_owner": sum(1 for h in headings if h in OWNED_BY),
        "headings": headings,
        "registered_but_no_longer_in_the_guide": stale,
        "problems": problems,
        "message_zh": ("使用说明里的每一步都有一个演练走过它。" if not problems
                       else "有步骤没人走过——见 problems。"),
        "what_this_does_not_prove":
            "不保证那个演练把这一步验穷尽了，只保证这一步有主人。",
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
