#!/usr/bin/env python3
"""界面上写死的「哪些平台能干什么」（v0.0.0.15）。

## 为什么有这道门

2026-08-06 一天之内，**同一个缺陷在三处被逐个撞见**，每次都是我打开那个
真实界面看一眼才发现的——判据全绿、演练全绿、发布门全绿：

  1. 设置页那张卡：「收藏夹、稍后再看、历史、点赞」——这一版只读收藏夹
  2. 资料库的收藏夹列：显示媒体 id 而不是名字（另一类，但同一个根）
  3. 插件弹窗：「小红书、抖音、**B站**、快手的收藏列表现在还读不了」
     ——B 站已经读得了两个版本

三处的写法完全一样：**一句写死的散文，说的却是「哪些平台能干什么」**。
而那件事是会变的——每接通一个平台就变一次，而散文不会有人想起去改。

第三次之后不能再靠"下次记得看一眼"。这道门把那个形状变成可检的：
**用户看得见的文案里，一句话同时点名三个以上平台、又在谈能力，就要报出来。**

## 判据

在用户看得见的文件里找**字符串字面量**（不是数据结构的键），满足：

  · 点名 ≥3 个平台（小红书 / 抖音 / 快手 / B站 / 哔哩哔哩 / X / Reddit /
    Instagram / YouTube / Chrome 书签 / 普通网页）
  · 且含有能力词（能同步 / 读不了 / 可自动 / 支持 / 还不能 / 收藏列表 …）

命中的必须改成**照服务端下发的 `supported_platforms` 现算**，
或者写进 ALLOWED 并说清它为什么不会过期。

## 它抓不到什么

- **只点名一两个平台的句子**。三个是为了避开正常的举例（「比如小红书」）。
  代价是漏报，但一条把正常举例也报红的门会被直接关掉。
- 数据结构（`platformOrder` 那种 id 列表、`PLATFORM_RULES` 那种 id→名字表）。
  它们本来就该写死——那是**名字**，不是**能力**。
- 服务端的事实清单（`NOT_SYNCABLE_YET`）。**它就是真源**，不在扫描范围里。
- **写死的「关系」清单**，比如设置页那句「收藏夹、稍后再看、历史、点赞」。
  那一句里一个平台名都没有，这道门看不见它。那是同一个病的另一半，
  由 `tests/focused/test_the_card_only_promises_what_it_reads.py` 盯着
  （它拿 SCANNABLE_RELATIONS 逐项对）。**两道合起来才盖住这一类。**
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 用户看得见的地方。服务端的事实清单不在这里——它是真源。
SURFACES = (
    "apps/browser-extension/popup.html",
    "apps/browser-extension/popup.js",
    "apps/browser-extension/options.html",
    "apps/browser-extension/options.js",
    "apps/browser-extension/sidepanel.html",
    "apps/browser-extension/sidepanel.js",
    "apps/pwa/index.html",
    "apps/pwa/app.js",
    "apps/pwa/extension-install.html",
    "docs/使用说明.md",
)

PLATFORM_NAMES = ("小红书", "抖音", "快手", "哔哩哔哩", "B站",
                  "Reddit", "Instagram", "YouTube", "Chrome 书签", "普通网页")
CAPABILITY_WORDS = ("能同步", "可自动", "自动同步", "读不了", "还不能", "不支持",
                    "收藏列表", "支持的平台", "都能", "均可")

# 允许写死的地方，每条写清**它为什么不会过期**。
ALLOWED: dict[str, str] = {
    # 使用说明里那张「哪些能自动/哪些手动」的表是逐平台一行的 Markdown 表格，
    # 而 check_the_guide_matches_the_product.py 会拿它和 SYNCABLE_NOW 逐项对，
    # 对不上就红。**它有专门的判据盯着，不是没人管的散文。**
    "docs/使用说明.md": "有 check_the_guide_matches_the_product.py 逐项核对",
}


def _literals(text: str, suffix: str) -> list[tuple[int, str]]:
    """取出可能显示给用户的文本片段。

    JS/HTML 里取引号字面量与标签之间的文字；Markdown 整行都算。
    """
    found: list[tuple[int, str]] = []
    if suffix == ".md":
        return [(index + 1, line) for index, line in enumerate(text.splitlines())]
    for match in re.finditer(r'"([^"\n]{8,400})"|\'([^\'\n]{8,400})\'|`([^`\n]{8,400})`', text):
        chunk = match.group(1) or match.group(2) or match.group(3) or ""
        found.append((text.count("\n", 0, match.start()) + 1, chunk))
    # **HTML 正文：先把标签剥掉，再按行看。**
    #
    # 第一版用的是 `>([^<>{}\n]{8,400})<`，要求正文和它前面那个 `>` 在同一行。
    # 而真正出问题的那句话恰恰不是——它写成：
    #
    #     <p style="...">
    #       小红书、抖音、B站、快手的收藏列表现在还读不了——缺的是<strong>…
    #
    # `>` 后面紧跟换行，于是**那一版把它整句漏掉了**。
    # 反例验出来的：把那句写死的话放回去，判据照样 PASS。
    if suffix in (".html", ".htm"):
        stripped = re.sub(r"<[^>]+>", " ", text)
        for index, line in enumerate(stripped.splitlines()):
            if line.strip():
                found.append((index + 1, line))
    return found


# 排他措辞：这类句子在宣布一份**会随版本变的名单**，写死必然过期。
# 和举例（「比如小红书」）形状完全不同，所以不受"至少三个平台"那条下限约束。
EXCLUSIVE_WORDS = ("只有", "仅有", "仅支持", "只支持", "其余平台", "其他平台都", "都还不能", "均不支持")


def main() -> int:
    hits: list[dict] = []
    scanned = 0
    for name in SURFACES:
        path = ROOT / name
        if not path.is_file():
            continue
        scanned += 1
        if name in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, chunk in _literals(text, path.suffix):
            named = [word for word in PLATFORM_NAMES if word in chunk]
            # **排他句：点名一个也要抓**（v0.0.0.22）。
            #
            # 下面那条「至少三个平台」的下限是对的——它避开正常举例
            # （「比如小红书」）。但它漏掉了另一种形状：
            #
            #     「本版本**只有 Chrome 书签**能自动读取；其余平台还没接上」
            #
            # 这句写死在账号同步中心的正文里，v0.0.0.21 起就是假话（那时已经
            # 5 个平台能同步，现在 7 个），而**他打开那个弹窗第一眼看到的就是它**。
            # 只点名一个，所以三个那条下限从设计上就漏。
            #
            # 排他句和举例长得完全不一样：举例是「比如 X」，排他是「只有 X 能」
            # 或「都不能」。按这个形状抓，不必降低那条下限。
            if any(word in chunk for word in EXCLUSIVE_WORDS) and named:
                hits.append({
                    "where": f"{name}:{line_no}",
                    "platforms": sorted(set(named)),
                    "capability_words": [w for w in EXCLUSIVE_WORDS if w in chunk],
                    "why": "**排他句**：它宣布「只有这些能」或「其余都不能」，"
                           "而那份名单会随版本变。这种句子必须现算，不能写死",
                    "text": chunk.strip()[:140],
                })
                continue
            # 「哔哩哔哩」与「B站」指同一个平台，别把它数成两个
            distinct = {("bilibili" if word in ("哔哩哔哩", "B站") else word)
                        for word in named}
            if len(distinct) < 3:
                continue
            said = [word for word in CAPABILITY_WORDS if word in chunk]
            if not said:
                continue
            hits.append({
                "where": f"{name}:{line_no}",
                "platforms": sorted(distinct),
                "capability_words": said,
                "text": chunk.strip()[:140],
            })

    # **一个文件都没扫到 = 这道门失效了**，不是"干净"。
    if scanned < 5:
        print(json.dumps({"status": "FAIL", "error_code": "SCOPE_LOOKS_WRONG",
                          "scanned": scanned,
                          "message_zh": "扫到的界面文件太少——**这不是通过**，是射程失效了。"},
                         ensure_ascii=False, indent=2))
        return 4

    print(json.dumps({
        "status": "PASS" if not hits else "FAIL",
        "surfaces_scanned": scanned,
        "allowed": ALLOWED,
        "hardcoded_claims": hits,
        "message_zh": (
            "界面上没有写死的「哪些平台能干什么」。"
            if not hits else
            "**界面上有写死的平台能力说明**——它会在下一次接通平台时变成假话，"
            "而没有任何东西会提醒你去改它。改成照服务端下发的 supported_platforms 现算，"
            "或写进 ALLOWED 并说清它为什么不会过期。"),
        "what_this_does_not_prove": (
            "只抓一句话里点名三个以上平台的。点名一两个的漏得掉——"
            "三个这个下限是为了避开正常举例（「比如小红书」），"
            "一条把举例也报红的门会被直接关掉。"),
    }, ensure_ascii=False, indent=2))
    return 0 if not hits else 4


if __name__ == "__main__":
    sys.exit(main())
