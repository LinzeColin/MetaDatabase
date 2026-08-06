#!/usr/bin/env python3
"""使用说明里写的每一步，产品里真的有吗（v0.0.0.7 / G4）。

## 为什么要有

Owner 2026-08-06 要的是「操作简单、满足要求的一个软件」加一份使用说明。
写一份说明很容易；**难的是它三个月后还是真的。**

这个仓里已经有过一模一样的教训：`CONNECT_IS_CLICKABLE_TODAY` 里写过一句
很详细的「点插件图标 → 设置 → 找到 YouTube → 点连接账号」，
**然后发现没有任何界面读那个字段**——那句话写完就是隐形的。
一份没人核对的说明书是同一类东西：写的时候是对的，改一次代码就开始骗人，
而**读它的人是 Owner，他没有别的办法发现自己被骗了。**

所以这道门把说明书当成判据来跑：文案、地址、平台清单，逐条回代码里查。

## 四类判据

1. **按钮文案**：说明里用「」引的每个按钮名，必须在对应的界面文件里真的出现。
2. **平台清单**：说明里那张「能自动 / 要手动」的表，必须和服务端
   SYNCABLE_NOW / NOT_SYNCABLE_YET 一字不差——**这张表最容易过期**，
   因为每接通一个平台都得改它。
3. **页面地址**：说明里出现的每个本产品地址，必须是真实路由。
4. **禁止承诺**：说明里不许出现"即将支持""敬请期待"这类话。
   这份文档的定位是「现在能做什么」，写计划就会变成上面说的那种骗人。

## 它不保证什么

不检查语气好不好、步骤顺不顺。**只保证它说的每件事都真的存在。**
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GUIDE = ROOT / "docs/使用说明.md"

# 所有会被用户看到的界面文件。说明里引的每一句界面文案都要在这里面找得到。
UI_FILES = (
    "apps/browser-extension/options.js",
    "apps/browser-extension/options.html",
    "apps/browser-extension/popup.js",
    "apps/browser-extension/popup.html",
    "apps/browser-extension/sidepanel.js",
    "apps/browser-extension/sidepanel.html",
    "apps/pwa/app.js",
    "apps/pwa/index.html",
    "apps/pwa/extension-install.html",
)

# **不是我们界面上的字**，逐条写清它是谁的。
#
# 这张表是**豁免**，不是清单——判据的默认答案是「引号里的东西必须在界面上找得到」。
# 第一版反了：先列一张"已知按钮"表，只查表里那几个。
# 于是把说明里的「连接账号」改成「一键连接全部平台」（界面上根本没有这颗按钮）
# **判据照样绿**——它不认识这个名字，就当它不是按钮跳过了。
# 一道只查自己已经知道的东西的门，挡不住任何新写进来的错。
NOT_OUR_UI = {
    "文稿": "macOS 的 Documents 文件夹",
    "下载": "macOS 的 Downloads 文件夹",
    "是否替换": "macOS 覆盖文件时自己弹的对话框",
    "重新加载": "chrome://extensions 上 Chrome 自己的按钮",
    "开发者模式": "chrome://extensions 上 Chrome 自己的开关",
    "加载已解压的扩展程序": "chrome://extensions 上 Chrome 自己的按钮",
    "···": "插件弹窗右上角那个图标，不是文字按钮",
    # 下面几条是**转述**页面上的话，不是逐字引用界面文案
    "你装的是旧版": "转述安装页在版本不符时显示的那句",
    "还没登录": "转述连接 B 站时那句提示",
    "同步完成": "转述同步结果",
    "能自动": "说明里那张表的表头用字",
    "手动保存": "同上",
}

# 说明里出现的本产品地址 → 它必须真的能打开
ROUTES = {
    "/extension-install": ["src/social_archive/api.py"],
}

FORBIDDEN = ("即将支持", "敬请期待", "正在开发", "后续版本将", "很快就会")



def _ui_text(path) -> str:
    """读界面文件，**把整行注释剔掉**。

    2026-08-06：我把悬浮按钮从「保存到我的档案馆」改名成「保存当前页面」，
    同时在旁边写了一段注释解释为什么改。两道文案判据**都照样绿**——
    因为旧名字还活在那段注释里，而语料是整份文件原样拼起来的。
    也就是说：**只要我在注释里提过那个词，它就永远"还在界面上"。**
    这个仓被自己的散文骗到已经是第六次了。

    只剔**整行**注释，不碰行内的 `//`：manifest 里的
    `"https://*.bilibili.com/*"` 和各种网址都含 `//`，
    上一次用非锚定的正则去剔，直接吃掉了真代码。
    """
    kept = []
    block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if block:
            if "*/" in stripped:
                block = False
            continue
        if stripped.startswith("/*"):
            block = "*/" not in stripped
            continue
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("<!--"):
            continue
        kept.append(line)
    return "\n".join(kept)

def main() -> int:
    from social_archive.account_sync import NOT_SYNCABLE_YET, PLATFORM_LABELS, SYNCABLE_NOW

    if not GUIDE.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "GUIDE_MISSING",
                          "path": str(GUIDE.relative_to(ROOT))}, ensure_ascii=False, indent=2))
        return 2
    text = GUIDE.read_text(encoding="utf-8")
    problems: list[str] = []

    # ① 按钮文案：说明里提到的，界面上必须真有
    quoted = set(re.findall(r"「([^」]{1,40})」", text))
    blob = "\n".join(_ui_text(ROOT / name)
                     for name in UI_FILES if (ROOT / name).is_file())
    checked_buttons = 0
    for label in sorted(quoted):
        if label in NOT_OUR_UI:
            continue
        checked_buttons += 1
        if label not in blob:
            problems.append(
                f"说明里让他点「{label}」，而**九个界面文件里一个都没有这个字样**"
                "——他会在界面上找不到它。要么改说明，要么这确实不是我们的界面文案，"
                "那就写进 NOT_OUR_UI 并说清它是谁的")
    # **一个都没查到 = 这道门失效了**，不是"通过了"。
    if checked_buttons < 5:
        problems.append(f"只核对到 {checked_buttons} 处界面文案——**这不是通过**，"
                        "是说明书的写法变了、这道门够不着它了")

    # ② 平台清单：能自动的必须恰好是 SYNCABLE_NOW
    #    说明里那张表用「✅ 能」和「❌ 手动保存」标，逐行读出来。
    claimed_auto: set[str] = set()
    claimed_manual: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|") or "✅" not in line and "❌" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        (claimed_auto if "✅" in cells[1] else claimed_manual).add(cells[0])
    # 说明里用的是给人看的名字（B站 / 小红书），换算回内部 id
    by_label = {label: platform for platform, label in PLATFORM_LABELS.items()}
    by_label["Chrome 书签"] = "generic-web"
    unknown = sorted(name for name in claimed_auto | claimed_manual if name not in by_label)
    if unknown:
        problems.append(f"说明里的平台名对不上产品里的任何平台：{unknown}")
    auto_ids = {by_label[n] for n in claimed_auto if n in by_label}
    manual_ids = {by_label[n] for n in claimed_manual if n in by_label}
    if auto_ids != set(SYNCABLE_NOW):
        problems.append(
            f"**说明里说能自动同步的和产品不一致**：说明写 {sorted(auto_ids)}，"
            f"产品是 {sorted(SYNCABLE_NOW)}。他会去点一颗不存在的按钮，"
            "或者错过一个其实已经能用的平台")
    missing_manual = sorted(set(NOT_SYNCABLE_YET) - manual_ids)
    if missing_manual:
        problems.append(f"这些平台产品里说「还不能自动」，说明里却没提：{missing_manual}")

    # ③ 地址：说明里写的路由必须真的存在
    for route, homes in ROUTES.items():
        if route not in text:
            continue
        found = any(route in (ROOT / home).read_text(encoding="utf-8")
                    for home in homes if (ROOT / home).is_file())
        if not found:
            problems.append(f"说明让他打开 {route}，而服务端没有这条路由")

    # ④ 不许写计划
    for word in FORBIDDEN:
        if word in text:
            problems.append(f"说明里出现了「{word}」——这份文档只写现在能做什么，"
                            "写计划会让它开始骗人")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "task": "G4",
        "guide": str(GUIDE.relative_to(ROOT)),
        "buttons_checked": checked_buttons,
        "claimed_auto": sorted(auto_ids),
        "product_auto": sorted(SYNCABLE_NOW),
        "claimed_manual": sorted(manual_ids),
        "problems": problems,
        "message_zh": ("使用说明里写的每一步，产品里都真的有。"
                       if not problems else
                       "**使用说明和产品对不上**——照着做会卡住，而他没有别的办法发现。"),
        "what_this_does_not_prove": "不检查步骤顺不顺、语气好不好，只保证说的每件事都存在。",
    }
    out = ROOT / "evidence/G4/USER_GUIDE_VERIFIED.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
