#!/usr/bin/env python3
"""建好了，但没有任何东西调得到它（v0.0.0.22 / G2）。

## 这一类已经栽过五次

每一次的样子都一样：机制是对的、代码是通的、测试是绿的，
**而用户点不到它**，所以它等于不存在。

    T06  SA_CONNECT_PLATFORM_SESSION 建在 background 里，没有界面通向它
         → 「连接 X」掉进另一条只会回 LOGIN_PROOF_UNAVAILABLE 的老路
    2026-08-05  registry 里写了很详细的 CONNECT_IS_CLICKABLE_TODAY 文案
         → **没有任何界面读那个字段**，写完就是隐形的
    2026-08-05  YouTube 在插件四张表里都接上了，options.js 三张表一个字没有
         → 设置页根本不给它出卡片，交接里让 Owner 做的第二件事做不了
    v0.0.0.21   服务端加了 outdated 字段
         → 没有一处读它
    v0.0.0.22   Instagram 的连接按钮被 Cookie 托管吃掉
         → 今天能跑通的那条路够不着（这道门就是这次立的）

写测试防不住：**要防的恰恰是"我没想到要为它写测试"**。
所以反过来枚举——把每个顶层函数和每种消息都列出来，逐个问「谁调它」。

## 它查什么

    1. background.js / options.js 里每个顶层函数，除定义处外**至少被提到一次**
    2. background.js 里每个 `SA_*` 消息类型，**在界面侧至少有一个发送方**
    3. 界面侧发出的每个 `SA_*` 消息，background 里**至少有一个处理分支**

第 3 条和第 2 条不是同一条：一个是"造了没人用"，一个是"用了没人接"。
两种都出过。

## 它不保证什么

只看名字有没有被提到，**不看那条路真的跑得通**——那是演练的事
（list_shape_end_to_end_drill.py 之类真在 Chrome 里跑的那些）。
这道门只防最便宜也最常犯的那种：**根本没接线**。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "apps/browser-extension"
BACKGROUND = EXT / "background.js"
# 界面侧 = **除 background.js 外的一切**，不是一张写死的名单。
#
# 第一版写死了四个文件名，当场报了五条误报：真正的发送方在
# net-relay.js（内容脚本）、bridge.js（网页桥）和 PWA 的安装页里。
# 「按一张我记得的名单去统计」正是这个仓反复吃亏的那种做法——
# 判据自己第一版也常错，所以这里改成枚举，不靠记性。
SENDER_GLOBS = ["apps/browser-extension/**/*.js", "apps/browser-extension/*.html",
                "apps/pwa/*.js", "apps/pwa/*.html"]

# 定义了但确实不该有调用方的：入口点、被 chrome.* 直接回调的。
# **每加一个都要写清为什么**，否则这道门会被逐条豁免到失效。
EXEMPT = {
    # service worker 的生命周期回调由浏览器直接调，代码里搜不到调用方
    "onInstalled", "onStartup", "onAlarm",
}


def _top_level_functions(text: str) -> dict[str, int]:
    """顶层函数（含 `async function`），返回 {名字: 定义所在行}。"""
    found: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^\s{0,2}(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", line)
        if match:
            found.setdefault(match.group(1), number)
    return found


def _uses(text: str, name: str) -> int:
    """名字在整份文件里出现几次（含定义处）。"""
    return len(re.findall(rf"\b{re.escape(name)}\b", text))


def main() -> int:
    problems: list[dict] = []
    background = BACKGROUND.read_text(encoding="utf-8")
    senders = sorted({path for pattern in SENDER_GLOBS for path in ROOT.glob(pattern)
                      if path.is_file() and path != BACKGROUND})
    frontend_text = "\n".join(path.read_text(encoding="utf-8") for path in senders)
    ui_text = (EXT / "options.js").read_text(encoding="utf-8")

    # ---- 1. 没人调的函数 -------------------------------------------------
    for source, text in (("background.js", background), ("options.js", ui_text)):
        for name, line in _top_level_functions(text).items():
            if name in EXEMPT:
                continue
            # 定义处算一次；只出现一次 = 谁也没调它
            if _uses(text, name) <= 1:
                problems.append({
                    "kind": "函数没人调", "where": f"{source}:{line}", "name": name,
                    "problem": f"`{name}()` 定义了，但整份文件里再没出现过第二次——"
                               "它是通的、是对的，而**没有任何东西调得到它**",
                })

    # ---- 2. 造了没人用的消息 --------------------------------------------
    # background 里 `message?.type === "SA_X"` 的分支
    handled = set(re.findall(r'message\?\.type\s*===\s*"(SA_[A-Z_]+)"', background))
    # **发消息不等于发给 background。**
    #
    # 第一版把所有 `type: "SA_*"` 都当成发给 background，于是报了五条误报：
    # SA_RAW_RESPONSE / SA_OBSERVER_READY 这些是 MAIN 世界和 ISOLATED 世界之间的
    # window.postMessage（观察器→中继），SA_PING 是网页桥自己接自己发的。
    # 它们本来就不该有 background 分支。
    #
    # 所以分两个集合：`sent` 是"任何地方提到要发它"（用来判断 background 的分支
    # 有没有人用），`to_background` 只数**真的走 chrome.runtime.sendMessage 的**
    # （用来判断有没有发给一个不存在的分支）。
    sent = set(re.findall(r'type\s*:\s*"(SA_[A-Z_]+)"', frontend_text))
    to_background: set[str] = set()
    for call in re.finditer(r"chrome\.runtime\.sendMessage\s*\(", frontend_text):
        window = frontend_text[call.end(): call.end() + 200]
        found = re.search(r'type\s*:\s*"(SA_[A-Z_]+)"', window)
        if found:
            to_background.add(found.group(1))
    # background 自己也会给内容脚本发消息，那些不算界面调用
    for name in sorted(handled - sent):
        problems.append({
            "kind": "消息没人发", "where": "background.js", "name": name,
            "problem": f"background 接得住 `{name}`，而**界面上没有任何地方发它**——"
                       "那套机制从用户那边够不着",
        })
    # ---- 3. 用了没人接的消息 --------------------------------------------
    for name in sorted(to_background - handled):
        problems.append({
            "kind": "消息没人接", "where": "界面", "name": name,
            "problem": f"界面会发 `{name}`，而 background 里**没有对应的分支**——"
                       "那颗按钮点下去什么也不会发生",
        })

    report = {
        "status": "PASS" if not problems else "FAIL",
        "functions_checked": len(_top_level_functions(background)) + len(_top_level_functions(ui_text)),
        "senders_scanned": [str(path.relative_to(ROOT)) for path in senders],
        "message_types_handled": sorted(handled),
        "message_types_sent": sorted(sent),
        "message_types_sent_to_background": sorted(to_background),
        "problems": problems,
        "message_zh": ("每个机制都有调得到它的路。" if not problems else
                       "**有机制建好了却够不着**——它是通的、是对的，而用户点不到。"),
        "what_this_does_not_prove": (
            "只看名字有没有被提到，不看那条路真的跑得通——那是演练的事。"
            "这道门只防最便宜也最常犯的那种：根本没接线。"),
    }
    out = ROOT / "evidence/G2/NO_MECHANISM_IS_UNREACHABLE.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
