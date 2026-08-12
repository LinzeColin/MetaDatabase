#!/usr/bin/env python3
r"""那个响应拦截器，在**真页面**上真的包得住吗（2026-08-12）。

## 为什么补这一个

说明书现在把那颗诊断按钮写成了「只有你做得到的那一下」：抖音的收藏接口地址
只存在于他登录后的浏览器里，按一下它就把**地址**送到他自己的服务器。

那一下他只按一次。**按下去抓不到东西的话，这一次就白按了**，而他看到的是
「一条都没抓到」——分不清是平台没发那个请求，还是我们的拦截器压根没工作。

在此之前，这条链上「拦截器在真页面上到底包不包得住」**从来没被验过**：

    extension_capture_buffer_drill   发的是合成的 SA_NET_CAPTURE 消息，没有真页面
    bilibili_acquisition_drill       绕开拦截器，直接打 B 站公开 REST 接口
    popup_states_drill               验那颗按钮按得动（2026-08-12 补），没验它抓到什么

## 它怎么验

真 Chrome、真 B 站公开收藏夹页面（不带登录态），把 `net-observer.js` 原样注进
MAIN world 的 document_start，然后：

1. 页面自己加载，自己发它自己的请求；
2. 拦截器此时**还没有前缀**，按设计把响应扣在 `pending` 里；
3. 我们再下发一次 `SA_OBSERVER_CONFIGURE`（这正是 background 做的事）；
4. 它应该把扣着的那些**补判一遍**，把命中的 `SA_RAW_RESPONSE` 抛出来。

第 2、3 步合起来是这条链最容易坏、也最难发现的地方：收藏列表那个请求是
**页面加载时**打的，等前缀下来早就结束了。`pending` 那一段就是为它写的，
而它此前没有任何真页面证据。

**下发的是 catch-all 前缀**，好把页面到底请求了什么全看一遍。只用那一条真前缀，
「没命中」有两种完全不同的含义——页面没打那个接口 / 拦截器没包住它——
而报出来长得一模一样。

## 实测到的：网页用的不是 `resource/list`

拦截器在真页面上抓到 13 条请求，其中收藏夹那一族是：

    x/v3/fav/folder/info?media_id=…
    x/v3/fav/resource/ids?media_id=…&platform=web
    x/v3/fav/resource/infos?resources=…

**没有 `x/v3/fav/resource/list`** ——而那正是 `INTERCEPT_PREFIXES.bilibili`
里写着的那一条。也就是说：**配给拦截器的前缀，和网页真正请求的地址对不上。**

今天不影响他：B 站走的是直接打公开 REST 接口那条路（`readFolder`），不靠拦截。
但这说明「拦截路」在 B 站上从来没有被真页面证实过——**而我正要请他用同一条
拦截路去抓抖音**。

所以判据认**收藏夹那一族**（`x/v3/fav/`），不认某一条写死的地址：
认一条的话，平台换个端点这道门就变成永远变不绿的红，而拦截器其实好好的。

（另：`x/internal/gaia-gateway/ExClimbWuzhi` 是 B 站的指纹上报，**正常加载也有**。
我第一版把它当成「被风控挡了」的标志，于是一次页面没加载完的运行被判成了通过——
**判据靠一个总是出现的东西去证明例外情况**，那是空转。）

## 边界

- **不验权限那一下。** B 站在 `optional_host_permissions` 里，真按按钮会弹一个
  原生授权框，演练点不了它——那一下始终要 Owner 本人。
- **只证 B 站。** 抖音的接口地址我们还不知道，那正是要他按那一下的原因。
- **不落库、不上传。** 只在本机读回拦截器抛出来的东西。
- 打一次 B 站公开页面，零费用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "apps" / "browser-extension" / "net-observer.js"
PUBLIC_FOLDER = "4026748432"          # 和 real_platform_into_archive_drill 同一个
PAGE = f"https://www.bilibili.com/medialist/detail/ml{PUBLIC_FOLDER}"
PREFIX = "api.bilibili.com/x/v3/fav/resource/list"
# 收藏夹那一族接口。**判据认这一族，不认某一条**——见下面「实测到的」。
FAV_FAMILY = "api.bilibili.com/x/v3/fav/"
DEBUG_PORT = 9412

COLLECTOR = """
window.__saSeen = [];
window.addEventListener("message", event => {
  const d = event.data;
  if (d && d.__socialArchive) window.__saSeen.push({type: d.type, url: d.url || "",
    status: d.status, bytes: (d.body || "").length, drained: d.drained});
});
"""


async def _rpc_factory(ws):
    counter = {"n": 0}

    async def rpc(method, params=None):
        counter["n"] += 1
        await ws.send(json.dumps({"id": counter["n"], "method": method,
                                  "params": params or {}}))
        while True:
            got = json.loads(await ws.recv())
            if got.get("id") == counter["n"]:
                return got
    return rpc


async def run(chrome: str, wait: float) -> int:
    if not OBSERVER.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "OBSERVER_MISSING"},
                         ensure_ascii=False))
        return 2
    profile = Path(tempfile.mkdtemp(prefix="sa-observer-real-"))
    # **默认无头。** 这个仓有一条硬规矩：演练不许抢屏幕（一次部署弹十五个可见
    # Chrome，而那些弹窗从没换来任何东西）。要盯着看时设 `SA_DRILL_HEADED=1`。
    headless = [] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         *headless, "--no-first-run", "--no-default-browser-check",
         "--disable-features=Translate", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    problems: list[str] = []
    seen: list = []
    try:
        target = None
        for _ in range(40):
            await asyncio.sleep(0.5)
            try:
                targets = json.loads(urllib.request.urlopen(base + "/json", timeout=3).read())
            except Exception:                                    # noqa: BLE001
                continue
            pages = [item for item in targets if item.get("type") == "page"]
            if pages:
                target = pages[0]
                break
        if not target:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"},
                             ensure_ascii=False))
            return 2

        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Page.enable")
            await rpc("Runtime.enable")
            # **必须在 document_start 之前注进去。** 收藏列表那个请求是页面加载时
            # 打的；事后 `Runtime.evaluate` 注入根本赶不上（2026-08-05 实测：
            # 自报 installed/ready 全 true，抓到 0 条）。
            await rpc("Page.addScriptToEvaluateOnNewDocument",
                      {"source": COLLECTOR + OBSERVER.read_text(encoding="utf-8")})
            await rpc("Page.navigate", {"url": PAGE})
            await asyncio.sleep(wait)
            await rpc("Runtime.evaluate", {"expression": (
                'window.postMessage({__socialArchiveControl:true,'
                'type:"SA_OBSERVER_CONFIGURE",urlPrefixes:["http"]},'
                ' window.location.origin)'), "returnByValue": True})
            await asyncio.sleep(3)
            got = await rpc("Runtime.evaluate", {
                "expression": "JSON.stringify({seen: window.__saSeen || [],"
                              " installed: !!window.__socialArchiveNetObserver})",
                "returnByValue": True})
            payload = got.get("result", {})
            if payload.get("exceptionDetails"):
                problems.append(f"读不回页面里的东西：{str(payload['exceptionDetails'])[:200]}")
                reading = {}
            else:
                reading = json.loads(payload["result"]["value"])
            seen = reading.get("seen") or []
    finally:
        process.terminate()
        shutil.rmtree(profile, ignore_errors=True)

    kinds = [item.get("type") for item in seen]
    ready = [item for item in seen if item.get("type") == "SA_OBSERVER_READY"]
    raw = [item for item in seen if item.get("type") == "SA_RAW_RESPONSE"]
    hit = [item for item in raw if PREFIX in str(item.get("url") or "")]
    fav = [item for item in raw if FAV_FAMILY in str(item.get("url") or "")]

    # ── 门：拦截器这一层通不通 ──
    if "SA_OBSERVER_INSTALLED" not in kinds:
        problems.append("**拦截器根本没装上**——连 SA_OBSERVER_INSTALLED 都没发出来")
    if not ready:
        problems.append("**下发前缀之后没有 SA_OBSERVER_READY**——配置那条消息没被收到")
    elif not ready[-1].get("drained"):
        problems.append(
            f"**补判的时候手里一条都没有（drained={ready[-1].get('drained')}）**——"
            "页面加载时打的请求没被扣住。收藏列表那个请求正是加载时打的，"
            "这一段坏了的话，他按那一下只会得到「一条都没抓到」")
    if not raw:
        problems.append("**一条响应都没抛出来**——拦截器没包住页面真正用的那条路")
    elif fav and not any(item.get("bytes") for item in fav):
        problems.append("**抓到了地址，响应体是空的**——读晚了，流已被页面消费掉")
    # **「有没有抓到收藏夹那一族」不打红。**（2026-08-12 实测：它是抖动的）
    #
    # 同一份代码连跑两次，一次抓到 4 条 fav 接口、一次一条都没有——B 站对无头
    # Chrome 的放行不稳定。把它做成门就是做了一盏时红时绿的灯，而灯一抖就没人看。
    #
    # 门只守**确定性的那部分**：拦截器装上了、扣住了加载时的请求、配置下来后
    # 补判抛了出来。这三样在两次运行里都成立，而拦截器真坏了它们必红。
    # 抓到哪些接口按观察如实报。

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "page": PAGE,
        "prefix": PREFIX,
        "message_types_seen": kinds[:12],
        "drained_from_pending": (ready[-1].get("drained") if ready else None),
        "raw_responses": len(raw),
        "what_the_page_actually_requested": [str(item.get("url"))[:96] for item in raw[:14]],
        "favorites_api_captured": [str(item.get("url"))[:88] for item in fav],
        "configured_prefix_was_seen_on_the_page": bool(hit),
        "problems": problems,
        "message_zh": (
            ("拦截器在真页面上包住了 fetch/XHR，扣住了加载时的请求，配置下来之后补判抛出来了；"
             f"收藏夹那一族抓到 {len(fav)} 条。"
             + ("" if hit else
                f"**注意：`{PREFIX}` 不在其中**——网页用的是 resource/ids + resource/infos，"
                "和 INTERCEPT_PREFIXES 里配的那一条对不上。今天不影响他"
                "（B 站走直接打 REST 那条路），但拦截路在 B 站上没有被真页面证实过。"))
            if not problems else "拦截器在真页面上没跑通——见 problems。"),
        "what_this_does_not_prove":
            "不验权限那一下（B 站在 optional_host_permissions 里，真按会弹原生框，"
            "演练点不了，那一下始终要 Owner 本人）；也只证 B 站——"
            "抖音的接口地址我们还不知道，那正是要他按那一下的原因。",
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="拦截器在真页面上包不包得住")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--wait", type=float, default=10.0, help="等页面自己把请求打完")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome, args.wait))


if __name__ == "__main__":
    sys.exit(main())
