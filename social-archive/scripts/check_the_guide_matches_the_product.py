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
    # **给人看的句子有一半不在 apps/ 里。**（2026-08-13）
    #
    # 这个仓的规矩是「界面不自己造句，用服务端下发的 message_zh」——那些句子
    # 住在这本冻结词典里（失败文案、同步结果、备份停了那一句…）。
    # 少了它，说明书引用一句**服务端下发**的话就会被判成「界面上没有」，
    # 而那句话他明明看得见。隔壁 check_docs_match_the_ui.py 同一天同一个补法。
    "src/social_archive/failure_copy.py",
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
    # **同上，也是他桌面上的一个文件。**（2026-08-10）
    # 「同步到 Obsidian」是全部内容；这个只补收藏那一档（抖音/B站/小红书/快手
    # 都只有收藏能自动扫）。两个都由 scripts/refresh_desktop_launcher.py 落盘，
    # 判据在 test_the_desktop_launcher_follows_the_host.py。
    "只补收藏到 Obsidian.command": "他桌面上的一个双击文件，不是网页按钮",
    "补": "上一行那个文件名里被强调的一个字，不是按钮",
    "你库里现在：观看历史 70 · 点赞 69 · 收藏 46 · 已保存 5 · 手动存的 2 · 稍后再看 1":
        "那个双击文件跑完打在终端里的一行，不是网页文案",
    # **不是网页上的按钮，是他桌面上的一个文件。**（2026-08-10）
    # 服务器够不着他的电脑、浏览器写不了任意本地路径——把内容送进他自己的
    # Obsidian 库那一跳只能在他机器上跑。他说过没有技术基础，所以做成双击。
    # 源文件在 scripts/「同步到 Obsidian.command」，判据在
    # test_pipefail_does_not_kill_the_sync_script.py 里钉着它存在且失败时会说话。
    "同步到 Obsidian.command": "他桌面上那个双击就能跑的文件，不是网页按钮",
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

COPIES_EVIDENCE = ROOT / "evidence/G5/THREE_COPIES_TODAY.json"


def _copies_confirmed_today() -> int | None:
    """最近一次真去核对时，几家云端**够得着**（`None` = 没数到）。

    这份证据由 `check_the_three_copies_are_really_there.py` 在每次部署的
    第 8.9 步写下。**读不到就返回 None，不返回 0**——0 会被下面那条规则
    读成「一份都没有」，而真相是「没数到」。这个仓栽在
    「空默认值吞掉不知道」上不止一次。
    """
    try:
        data = json.loads(COPIES_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = (data.get("measured") or {}).get("copies_confirmed_today")
    return value if isinstance(value, int) else None


def judge_prose(text: str, periods: set[int], copies_confirmed: int | None) -> list[str]:
    """说明书正文里那几条**纯文本**规则——单独拿出来，好喂它坏句子证明它会红。

    ⑤⑥⑦⑧ 全是「说明书替产品／替他的数据说话」这一类。它们原先埋在
    `main()` 里、直接从磁盘读那一份文件，于是**没有任何办法喂一句坏话给它**：
    ⑥ 从 2026-08-07 建起来到今天，一次都没有被打红过。
    这个仓的教训写得很清楚——判据没有调用方、或者只有一个永远是绿的调用方，
    就不算做完。

    参数都从外面传进来（闹钟周期、实测到的副本份数），是为了同一个理由：
    判据要能在测试里被喂任意状态。
    """
    problems: list[str] = []

    # ⑤ **说明里的时间间隔，必须和代码里那个闹钟一致**（2026-08-07）。
    #
    # 「之后每 6 小时自己跑一次」出现在正文和那张图里各一次。改一次
    # `periodInMinutes`，这两句就开始骗人——而前面四条规则一个都碰不到它们：
    # 它们查的是按钮名、平台表、路由、禁用词。
    stated = {int(h) for h in re.findall(r"每\s*(\d+)\s*小时", text)}
    if not periods:
        problems.append("读不出扩展里那个自动同步闹钟的周期——**这不是通过，是没数到**")
    elif stated and {p // 60 for p in periods} != stated:
        problems.append(
            f"说明写「每 {sorted(stated)} 小时」，而扩展里的闹钟是 {sorted(periods)} 分钟"
            f"（{sorted(p // 60 for p in periods)} 小时）——他会按错的节奏等")

    # ⑥ **不许把他库里的实数写死在散文里**（2026-08-07）。
    #
    # 原来写着「实测你库里 193 条有 33 条是这样」。写的当天是真的，
    # 而他一同步就成了假的——**说明书开始对他的数据说错话，而他没有别的办法
    # 发现**。这个仓栽过同形的一次：判据盯着 JSON，漏了用户真正读的那段散文。
    # 数量该由资料库现算着显示，散文只说「有这类条目」。
    frozen = re.findall(r"(?:你)?库里[^。\n]{0,12}?(\d+)\s*条", text)
    if frozen:
        problems.append(
            f"说明里写死了他库里的条数：{frozen}——**同步一次就成假话**。"
            "改成「看资料库那一列的实数」，别在散文里冻一个会过期的数字")

    # ⑦ **不许断言「他库里没有 X」**（2026-08-10）。
    #
    # ⑥ 只挡住了写死的**数**。同一天漏掉的是没有数字的那一半：平台表里
    # Chrome 书签那行写着「你库里目前没有这个来源的账号」。
    # 这一句比 ⑥ 挡的那种更糟——**让它变成假话的，正是他照着这份说明
    # 走完第 3 步那一刻**：说明书自己教他做的事，把说明书自己变成了假的。
    # 而它当时已经跟着 guide.html 上了生产，他随时能读到。
    #
    # 方向是不对称的，所以这条规则只挡一边：这个产品只往库里加
    # （断开也不清空内容——db.py `disconnect_source_account`「只断连接，不删内容」），
    # 所以「有」是稳的，「没有」自带过期时间。
    #
    # 只认「库里 + 否定」这一种形状，不去泛化：像
    # 「（还没有任何内容时，中间那颗按钮也是它）」那种**条件句**说的是界面行为，
    # 不是对他数据的断言，误伤它会逼人把判据关掉。
    denied = re.findall(r"(?:你)?库里[^。\n]{0,10}?(?:没有|还没|尚未)[^。\n]{0,24}", text)
    if denied:
        problems.append(
            f"说明里断言他库里**没有**某样东西：{denied}——这个产品只往库里加，"
            "「没有」自带过期时间，而让它过期的往往正是他照着说明做成了那一刻。"
            "改成只说证据来自哪里，别替他的库此刻是什么样下结论")

    # ⑧ **说明书写的副本份数，必须等于实测确认到的份数**（2026-08-10）。
    #
    # 原来写的是「你自己的服务器上，加密存三份」。而 8.9 那道播报从建起来
    # 那天起，每一次都报 **2/3**（github 那份够不着），并且自己就写着
    # 「在把这一句改掉、或者把够不着的那份修好之前，那句话是超售的」——
    # **没有任何东西逼那句话跟着改**，于是它超售了好几天。
    #
    # 两个方向都算错：多说了他会以为自己更安全；少说了他会以为保护更弱。
    # 数不到不是通过。
    claimed = [int(m) for m in re.findall(r"能确认拿得回来的是\s*(\d+)\s*处", text)]
    if not claimed:
        problems.append(
            "说明里读不出「今天能确认拿得回来的是 N 处」这句话——**这不是通过，是没数到**。"
            "备份份数是他最没办法自己核实的一句，必须以这个句式写，好让判据能盯住它")
    elif copies_confirmed is None:
        problems.append(
            f"说明里写着能拿回 {claimed} 处，而 {COPIES_EVIDENCE.name} 里读不出实测份数"
            "——**这不是通过，是没数到**。跑一次部署第 8.9 步把它刷新出来")
    elif set(claimed) != {copies_confirmed}:
        direction = "超售" if max(claimed) > copies_confirmed else "少说了"
        problems.append(
            f"说明写能拿回 {claimed} 处，而最近一次真去核对确认到的是 "
            f"{copies_confirmed} 处——**{direction}**。"
            "备份是他唯一没办法自己核实的一件事，这一句只能等于实测数")

    return problems


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
    # ①bis **在不在那个界面上**，不只是"在不在某个界面上"（v0.0.0.22）。
    #
    # 上面那条只问「九个界面文件里有没有这个词」。它漏掉的是**指错界面**，
    # 而这一类我已经犯了两次：
    #
    #   · 说明里让他「点插件的『保存到我的档案馆』」——那个名字确实存在，
    #     但它在网页右下角那颗悬浮按钮上，不在插件弹窗里。他打开弹窗找不到。
    #   · 说明里让他「回到面板上点『我已登录，继续』」——那颗按钮当时只在
    #     插件的账号页上，**面板上根本没有**。他登录完回来没有下一步。
    #
    # 两次都是判据全绿。所以这里按**章节**收紧：说明第 3 步整节都写着
    # 「就在资料库这一页上」，那么这一节里点名的每个按钮，
    # 都必须在那一页真正渲染的东西里找得到——连接面板。
    STEP_SURFACES = {
        # 第 3 步真正会经过的界面：资料库那一页 → 嵌进去的连接面板 →
        # （备选入口）插件弹窗。**只列这三处**——列多了这条判据就退化成
        # 上面那条「九个文件里有没有」，一次也抓不到指错界面。
        "第 3 步": (
            ["apps/pwa/index.html", "apps/pwa/app.js",
             "apps/browser-extension/connect-frame.html",
             "apps/browser-extension/connect-frame.js",
             "apps/browser-extension/popup.html", "apps/browser-extension/popup.js"],
            "第 3 步只经过资料库、连接面板和插件弹窗这三处",
        ),
        # 手动保存那一节整节写着「点插件图标 → …」，那就得在**插件弹窗**里。
        # 这一节正是第一次犯错的地方：说明写「点插件的『保存到我的档案馆』」，
        # 而那个名字在网页右下角那颗悬浮按钮上，弹窗里没有。
        "想手动存某一条": (
            ["apps/browser-extension/popup.html", "apps/browser-extension/popup.js"],
            "这一节写的是「点插件图标 → …」，那就得在插件弹窗里找得到",
        ),
    }
    for heading, (files, why) in STEP_SURFACES.items():
        chunk = ""
        for part in text.split("### ")[1:]:
            if part.startswith(heading):
                chunk = part.split("\n### ")[0]
                break
        if not chunk:
            problems.append(f"说明里找不到「{heading}」那一节——这道门的射程失效了")
            continue
        surface = "\n".join(_ui_text(ROOT / name) for name in files if (ROOT / name).is_file())
        if not surface:
            problems.append(f"「{heading}」指向的界面文件一个都不存在：{files}")
            continue
        for label in sorted(set(re.findall(r"「([^」]{1,20})」", chunk))):
            if label in NOT_OUR_UI or label not in blob:
                continue          # 不是界面词、或上面那条已经报过了
            if label not in surface:
                problems.append(
                    f"「{heading}」让他点「{label}」，而**那个界面上没有这个按钮**"
                    f"（{why}）。它在别处存在，所以上面那条查不出来——"
                    "他会按着说明在那一页上找一颗不存在的按钮")

    # ①ter **服务端写给用户看的话，也要按同一把尺量**（v0.0.0.22）。
    #
    # 这道门一直只量 docs/使用说明.md。而平台卡片上那句「本版本还不能自动读取…
    # 现在可以：…点插件的「X」」是**服务端下发的**（NOT_SYNCABLE_YET），
    # 界面直接显示它——判据一次都没看过它。
    #
    # 历史上那次就出在这里：那句话写着「点插件的『保存到我的档案馆』」，
    # 而插件弹窗上那颗叫「保存当前页面」；「保存到我的档案馆」是网页右下角
    # 那颗悬浮按钮。**他打开弹窗会找不到。** 说明书那边一直是对的，
    # 所以这道门一直绿。
    from social_archive.registry import CONNECT_IS_CLICKABLE_TODAY  # noqa: PLC0415
    server_copy = dict(NOT_SYNCABLE_YET)
    server_copy.update({f"registry:{k}": v for k, v in
                        (CONNECT_IS_CLICKABLE_TODAY or {}).items()})
    for where, sentence in server_copy.items():
        for label in sorted(set(re.findall(r"「([^」]{1,20})」", str(sentence)))):
            if label in NOT_OUR_UI:
                continue
            checked_buttons += 1
            # 「点插件的「X」」——那就必须在插件弹窗里
            surface_files = (["apps/browser-extension/popup.html",
                              "apps/browser-extension/popup.js"]
                             if "点插件的" in str(sentence) else UI_FILES)
            surface = "\n".join(_ui_text(ROOT / name) for name in surface_files
                                if (ROOT / name).is_file())
            if label not in surface:
                problems.append(
                    f"服务端给「{where}」写的那句话让他点「{label}」，"
                    f"而**{'插件弹窗' if '点插件的' in str(sentence) else '界面'}上没有这个按钮**"
                    "——这句话会原样显示在平台卡片上，他照着找会找不到")

    # ④ **说「实测」的，必须真有打过真接口的证据**（v0.0.0.22）。
    #
    # 说明书那张表里 Chrome 书签那一行写着「实测 62 条全量入库」——
    # 而那 62 条**只存在于演练里**：2026-08-06 去生产上查，他库里根本没有
    # 这个来源的账号。同一句过度声称我当天在代码注释和判据里都更正了，
    # **唯独说明书没跟上**，而说明书恰恰是他会读的那一份。
    #
    # 判据不看措辞好坏，只做一件事：把"实测"这个词和**证据文件里的
    # live_probe_ran** 绑起来——那个字段的意思就是"真的打过接口"，
    # 而不是"机制在假站上跑通了"。
    import glob as _glob
    import pathlib as _pathlib

    live_probed: set[str] = set()
    for path in sorted(_glob.glob(str(ROOT / "evidence" / "**" / "*.json"), recursive=True)):
        try:
            data = json.loads(_pathlib.Path(path).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("status") == "PASS" and data.get("live_probe_ran") is True:
            # 平台名可能在字段里，也可能在文件名里（BILIBILI_ACQUISITION.json）
            named = str(data.get("platform") or "")
            if named:
                live_probed.add(named.lower())
            stem = _pathlib.Path(path).stem.lower()
            for candidate in PLATFORM_LABELS:
                if candidate.replace("-", "_") in stem:
                    live_probed.add(candidate)
    # **说明书里的叫法和代码里的标签不是一套。**
    #
    # 第一版直接拿 PLATFORM_LABELS 去匹配，于是那一行
    # 「| Chrome 书签 | ✅ 能 | 实测 62 条全量入库 |」一个也没命中——
    # generic-web 在代码里叫「通用网页」。反证当场戳穿：把那句假话放回去，
    # 判据照样绿。**判据认不出的名字，等于它没在看那一行。**
    GUIDE_ALIASES = {"generic-web": ("Chrome 书签", "通用网页")}
    for line in text.splitlines():
        if "实测" not in line or not line.strip().startswith("|"):
            continue
        # **按单元格精确比**，不按"包含"：标签里有一个单字母的 X，
        # 用包含匹配会把任何带 X 的行都算成 X 那一行。
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        for platform, label in PLATFORM_LABELS.items():
            names = set(GUIDE_ALIASES.get(platform, ())) | {label}
            if not (names & set(cells)):
                continue
            if platform not in live_probed:
                problems.append(
                    f"说明书里给「{label}」写了「实测」，而**没有一份证据文件说打过真接口**"
                    f"（live_probe_ran=true 的只有 {sorted(live_probed) or '一个都没有'}）。"
                    "机制在假站上跑通不叫实测——他读到「实测」会以为"
                    "这条路在他自己的数据上验过")

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

    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    periods = {int(m) for m in re.findall(
        r'"sa-account-sync",\s*\{\s*periodInMinutes:\s*(\d+)', background)}
    stated = {int(h) for h in re.findall(r"每\s*(\d+)\s*小时", text)}
    copies_confirmed = _copies_confirmed_today()
    problems.extend(judge_prose(text, periods, copies_confirmed))

    report = {
        "status": "PASS" if not problems else "FAIL",
        "task": "G4",
        "sync_period_minutes": sorted(periods),
        "sync_hours_stated_in_guide": sorted(stated),
        # **两个数都印出来**，别只印结论。只印「一致」的话，
        # 哪天两边一起漂到同一个错数上，报告仍然是一句「一致」。
        "backup_copies_confirmed_today": copies_confirmed,
        "backup_copies_stated_in_guide": [
            int(m) for m in re.findall(r"能确认拿得回来的是\s*(\d+)\s*处", text)],
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
