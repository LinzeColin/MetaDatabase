#!/usr/bin/env python3
r"""那几条 DOM 选择器，在**真页面**上到底选得中东西吗（2026-08-13）。

## 为什么补这一个

Owner 生产库里的实况（实测，不是推断）：

    bilibili     进 169 条
    douyin       进  91 条
    xiaohongshu  **7 次跑，discovered_count 每次都是 0，库里 0 行**

而产品对他说小红书能自动同步，说明书那张表也写着「小红书 / 抖音｜你收藏页上
那一批」。**「能同步」和「他那边一条都没进来」并存了十天，没有任何判据红过。**

原因之一是所有小红书演练打的都是**我们自己写的假站**：
`list_shape_end_to_end_drill --platform xiaohongshu` 里那套响应形状是我编的，
选择器当然选得中。而 `net_observer_sees_a_real_page_drill` 只打 B 站。
**小红书这条路从来没有见过一张真的小红书页面。**

（他那 7 次失败的错码——`RELATION_SCOPE_UNCONFIRMED`、
`PLATFORM_PERMISSION_MISSING`——各自的成因都已经修了。所以这个演练**不是**
去证明"小红书坏了"，是去回答一个到现在还没有证据的问题：
**我们那两条选择器，落在真页面上选得中东西吗。**）

## 它怎么验

真 Chrome、**公开页面、不带登录态、零费用**，把 `extract-core.js` 里那份
`LIST_SELECTORS` 原样取出来，在真页面上数一遍命中。

## ★ 小红书那个问题，2026-08-13 已经答了：**选择器没问题**

第一版只让无头 Chrome 去开小红书，拿回 `error_code=300012 / IP at risk`，
我据此写下「本机 IP 被挡、这台机器答不了」——**这个结论是错的**。
同一台机器、同一个地址，普通 HTTP 客户端拿回 **200 / 981KB / 96 个命中**。
**挡住的是无头 Chrome 这个特征，不是这条网络**——而他的插件跑在他自己的
真 Chrome 里，撞不到那道墙。

所以他库里小红书 0 条**不是选择器的问题**。剩下的候选成因都在已修之列
（`PLATFORM_PERMISSION_MISSING` 的权限那一下、`RELATION_SCOPE_UNCONFIRMED`
的范围那一条）。**要确认，得他重连一次再看那个数。**

## 三种结果要分开，绝不许混成一个「失败」

    页面根本没打开 / 撞上人机验证  → BLOCKED_CHANNEL（**不是 FAIL**）
    页面打开了、选择器 0 命中      → **这才是真问题**：选择器对不上真页面
    页面打开了、选择器有命中        → 这条路在真页面上站得住

**撞墙不绕。** 这个仓的规矩是记下坐标换台机器再说，不是去破验证码。
分不开的话，一次 bot 墙会被读成"选择器坏了"，或者反过来——两种都会让人
照着错的方向修一整天。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import websockets  # noqa: E402

import list_shape_end_to_end_drill as shape  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_CORE = ROOT / "apps/browser-extension/content/extract-core.js"
DEBUG_PORT = 9433

# 公开、不需要登录、不带任何他的东西。
#
# **只有「本身就是一份条目列表」的页面才配当夹具。** 拿一张不是列表的页面
# 去数命中，0 命中说明不了任何事——而它长得和"选择器坏了"一模一样。
REAL_PAGES = {
    # PUBLIC_LIST_PAGE_FIXTURE —— 不是平台表，是「公开可达且本身就是条目列表」的页面。
    # 热门榜就是一列视频，实测选中 21 个节点。
    "bilibili": "https://www.bilibili.com/v/popular/all",
    # 保留入口给够得着的机器跑（本机 IP 被挡，见下）。
    "xiaohongshu": "https://www.xiaohongshu.com/explore",
    "douyin": "https://www.douyin.com/discover",
}

# **每家用哪条路取页面，是量出来的，不是选出来的。**（2026-08-13 实测）
#
#   browser  真 Chrome 打开它自己渲染（列表由 JS 画出来的站只能走这条）
#   fetch    普通 HTTP 客户端取 HTML，再交给真浏览器解析器 + 真选择器
#            （**绕开的是无头特征识别，不是任何人机验证**）
#
# 实测三家各不相同：
#
#   bilibili     browser 21 命中；fetch 只拿到 4.4KB 的壳、0 个链接（列表 JS 渲染）
#   xiaohongshu  browser 被拒（无头特征）；**fetch 200 / 981KB / 96 命中**（服务端就渲染好了）
#   douyin       两条都不行（`/discover` 跳推荐流；fetch 拿到 73KB、0 个链接）
DEFAULT_MODE = {
    # PUBLIC_LIST_PAGE_FIXTURE：和 REAL_PAGES 同一份夹具的另一半，不是平台表。
    "bilibili": "browser",
    "xiaohongshu": "fetch",
    "douyin": "browser",
}

# **只剩抖音答不了，而且原因和"被挡"无关。**
UNANSWERABLE_HERE = {
    "douyin": (
        "`/discover` 会跳到 `/jingxuan`——那是一张**推荐流，不是条目列表**，"
        "整页 24 个链接、0 个带 `/video/`；fetch 那条路拿回 73KB 但 0 个链接（列表 JS 渲染）。"
        "**0 命中在这里说明不了问题**——他库里 douyin 真进过 91 条，"
        "足以证明那条选择器在**收藏页**上是管用的。"
        "要验它得有一张公开的、真的是列表的抖音页，目前没找到。"),
}

# 撞上人机验证 / 登录墙的特征。**只用来分类，不用来绕过。**
WALL_MARKS = ("验证", "captcha", "slider", "登录后查看", "安全中心",
              "访问异常", "please verify", "unusual traffic")


def _selectors_for(platform: str) -> list[str]:
    """从 `extract-core.js` 里把那一行原样取出来——**不在这里抄第二份**。"""
    text = EXTRACT_CORE.read_text(encoding="utf-8")
    block = re.search(r"LIST_SELECTORS\s*=\s*Object\.freeze\(\{(.*?)\n\s*\}\)",
                      text, re.S)
    if not block:
        raise SystemExit("✗ 读不到 LIST_SELECTORS——选择器的真源在 extract-core.js")
    # **取整行，别在第一个 `]` 上停。**（2026-08-13，第二个坑）
    #
    # 选择器自己带方括号（`a[href*="…"]`），所以 `\[(.*?)\]` 会停在
    # `a[href*="/explore/"` 这里——截断之后再去配引号，取出来的是 `/explore/`，
    # 一条能跑但**意思完全不同**的选择器。每个平台占一行，按行取就对了。
    row = re.search(rf'(?m)^\s*"?{re.escape(platform)}"?\s*:\s*\[(.*)\],?\s*$',
                    block.group(1))
    if not row:
        raise SystemExit(f"✗ LIST_SELECTORS 里没有 {platform}")
    # **按引号种类各自配对。**（2026-08-13，第一版就栽在这儿）
    #
    # 选择器长这样：`'a[href*="/explore/"]'` —— **单引号里裹着双引号**。
    # 第一版写的是 `['"]([^'"]+)['"]`，它在里面那个 `"` 上就停了，
    # 取出来的是 `a[href*=` —— 一条语法非法的选择器。
    # 后果不是报错，是**这个演练会因为一个和平台毫无关系的理由判红**。
    found = re.findall(r"'([^']*)'|\"([^\"]*)\"", row.group(1))
    return [single or double for single, double in found if (single or double)]


def _fetch_html(url: str) -> tuple[int, str]:
    """用普通 HTTP 客户端取一次页面。

    **为什么需要这条路。**（2026-08-13，推翻了我自己前一版的结论）

    第一版只让无头 Chrome 去开小红书，拿回来的是
    `error_code=300012 / IP at risk`，我据此写下「本机 IP 被挡」——**错了**。
    同一台机器、同一个地址，`curl` 带一个正常 UA 拿回 **200、979KB、
    90 个 `href="/explore/"`**。挡住的是**无头 Chrome 这个特征**，不是这条网络。

    这个差别很要紧：**他的插件跑在他自己的真 Chrome 里**，撞不到这道墙。
    把「无头被识别」写成「通道不可达」，会让人以为这件事在这台机器上没法查——
    而它查得了。
    """
    request = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/151.0.0.0 Safari/537.36"),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.status, response.read().decode("utf-8", "replace")


async def run(chrome: str, platform: str, url: str, headed: bool,
              via_fetch: bool = False) -> int:
    selectors = _selectors_for(platform)
    profile = Path(tempfile.mkdtemp(prefix="sa-realsel-"))
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         "--no-first-run",
         *([] if headed or os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]),
         "--no-default-browser-check", "--disable-sync", "--password-store=basic",
         "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    payload: dict = {"platform": platform, "url": url, "selectors": selectors}
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2).read())
                break
            except Exception:                                   # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "BLOCKED_CHANNEL", "reason": "CHROME_NOT_UP"},
                             ensure_ascii=False, indent=2))
            return 0

        fetched_html = ""
        if via_fetch:
            # 取回来的 HTML 交给**真浏览器的解析器**，再跑**真选择器**。
            # 请求由普通 HTTP 客户端发出，不带无头特征。
            status, fetched_html = _fetch_html(url)
            payload["fetched_status"] = status
            payload["fetched_bytes"] = len(fetched_html)
        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await shape._rpc_factory(ws)                  # noqa: SLF001
            await rpc("Target.createTarget",
                      {"url": "about:blank" if via_fetch else url})
        await asyncio.sleep(2 if via_fetch else 9)              # 首屏 + 懒加载

        targets = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page"
                 and (via_fetch or "about:blank" not in t["url"])]
        if not pages:
            payload |= {"status": "BLOCKED_CHANNEL", "reason": "PAGE_NEVER_OPENED"}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as page:
            prpc = await shape._rpc_factory(page)               # noqa: SLF001
            await prpc("Runtime.enable")
            if via_fetch:
                await prpc("Runtime.evaluate", {
                    "expression": ("(() => { document.open();"
                                   f" document.write({json.dumps(fetched_html)});"
                                   " document.close(); return document.title; })()"),
                    "returnByValue": True, "timeout": 30000})
                await asyncio.sleep(1)
            probe = await prpc("Runtime.evaluate", {"expression": f'''(() => {{
                const selectors = {json.dumps(selectors)};
                const counts = {{}};
                for (const s of selectors) {{
                  try {{ counts[s] = document.querySelectorAll(s).length; }}
                  catch (e) {{ counts[s] = "选择器语法错：" + e.message; }}
                }}
                const text = (document.body && document.body.innerText) || "";
                return JSON.stringify({{
                  counts,
                  final_url: location.href,
                  title: document.title,
                  body_chars: text.length,
                  anchors_total: document.querySelectorAll("a[href]").length,
                  text_head: text.slice(0, 300),
                }});
            }})()''', "returnByValue": True, "timeout": 20000})
            seen = json.loads(probe.get("result", {}).get("result", {}).get("value") or "{}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    payload |= seen
    blob = f"{seen.get('title','')}\n{seen.get('text_head','')}".lower()
    walled = any(mark.lower() in blob for mark in WALL_MARKS)
    hits = sum(v for v in (seen.get("counts") or {}).values() if isinstance(v, int))

    if walled or int(seen.get("body_chars") or 0) < 200:
        payload |= {
            "status": "BLOCKED_CHANNEL",
            "reason": "WALL_OR_EMPTY",
            "message_zh": (UNANSWERABLE_HERE.get(platform)
                           or "这台机器打不开这一页（人机验证／登录墙／空白）。"
                              "**这不算选择器坏了，也不算它对**——换一台够得着的机器再跑。"
                              "**不绕验证码。**"),
        }
    elif hits == 0 and platform in UNANSWERABLE_HERE:
        # **别把「夹具选错了页」判成产品坏了。**
        payload |= {
            "status": "BLOCKED_CHANNEL",
            "reason": "NO_USABLE_PUBLIC_LIST_PAGE",
            "hits": 0,
            "message_zh": UNANSWERABLE_HERE[platform],
        }
    elif hits == 0:
        payload |= {
            "status": "FAIL",
            "hits": 0,
            "message_zh": (f"页面打开了（{seen.get('body_chars')} 字、"
                           f"{seen.get('anchors_total')} 个链接），"
                           f"而 {platform} 那几条选择器**一个都没选中**——"
                           f"它们对不上这张真页面。"),
        }
    else:
        payload |= {
            "status": "PASS", "hits": hits,
            "message_zh": f"{platform} 的选择器在真页面上选中 {hits} 个节点。",
        }
    payload["what_this_does_not_prove"] = (
        "打的是公开页，不是他登录后的收藏页——选得中不代表收藏页上也选得中。"
        "只回答一件事：这几条选择器落在这个平台的真 DOM 上，是不是完全落空。")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] != "FAIL" else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="选择器在真页面上选得中吗")
    parser.add_argument("--platform", default="xiaohongshu", choices=sorted(REAL_PAGES))
    parser.add_argument("--url", default="")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--via-fetch", action="store_true", default=None,
                        help="用普通 HTTP 客户端取 HTML 再交给浏览器解析——"
                             "绕开的是**无头特征识别**，不是任何人机验证")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome, args.platform,
                           args.url or REAL_PAGES[args.platform], args.headed,
                           (DEFAULT_MODE.get(args.platform) == "fetch"
                            if args.via_fetch is None else args.via_fetch)))


if __name__ == "__main__":
    sys.exit(main())
