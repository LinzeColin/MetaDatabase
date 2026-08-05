#!/usr/bin/env python3
"""档案馆页面上，那两段话真的显示出来了吗（v0.0.0.7 / T11）。

## 为什么补这个

2026-08-05 修了两处「界面不显示服务端说的话」：
覆盖差额（「还有 192 条从来没送到这里」）和八条隐私说明（东西去了哪、钥匙在谁手里）。

两处都核到**字段进了接口负载、两个界面的源码都读它**为止，
然后在证据里如实写了一句：**没有在真浏览器里看见它们渲染出来**。

那句话是诚实的，但挂着不查就是留给下一个人踩。这个演练把它查了。

## 它怎么验

起一个假档案馆：静态文件直接喂 `apps/pwa/`，接口按最小形状回假数据
（`/v1/auth/me` 通了才不会被登录墙挡住）。然后用真 Chrome 打开，
**把渲染出来的 DOM 读回来**，看那两段话在不在卡片里。

## 结果（2026-08-05）

四句全部在真 Chrome 的 DOM 里读到了，`.privacy-note` 也在，
连「把没送过去的 192 条补上」那颗按钮一起画了出来。**那句诚实的话可以撤了。**

反面也验过：把 app.js 里三处渲染分别改坏（不画隐私说明 / 不画覆盖 /
把差额那一句的读取换成一个不存在的字段），这个演练三次全红，
而且每次点的都是被改坏的那一处。改完即刻还原。

## 它第一次跑是红的，而那是**我的夹具错了**

第一版按 URL 去磁盘上找 `apps/pwa/assets/app.js`——那个目录不存在。
真服务端是把 `apps/pwa/` 整个平挂在 `/assets` 下的（api.py:1215）。
主脚本 404，页面一个接口都没请求，报出来却只有一句「0 张卡都没渲染」。

**「界面没画出来」和「界面根本没跑起来」长得一模一样。**
差点据此说产品有毛病。所以现在多了两样东西：`endpoints_asked`
记下页面问了哪几个接口，以及 `APP_SCRIPT_NEVER_SERVED` 这个单独的出口——
主脚本没送出去时它明说是夹具的问题，不混进产品缺陷里。

## 边界

· 一次性 profile，跑完删；只连 127.0.0.1；不碰生产、不碰任何真实账号。
· 假数据是**最小形状**，不是真实数据。它证明的是「这一段会被画出来」，
  不是「画出来的数是对的」。
· 夹具里 `last_message_zh` 和 `next_action_zh` 都填了差额那句（服务端两处都写）。
  所以它验不出「服务端只写了其中一个」那种回归——那条钉在
  `tests/focused/test_a_gap_in_coverage_is_not_reported_as_fine.py`（两个字段各断言一次）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
PWA = ROOT / "apps/pwa"
PORT = 8765

COVERAGE = "已送到这里 1 / 193 条。"
GAP = "**还有 192 条从来没送到这里。**"
PRIVACY = "开锁用的令牌只存在你的服务器上，插件拿不到。"

FAKE: dict[str, object] = {
    "/v1/auth/me": {"user_id": "fixture", "display_name": "夹具用户"},
    "/v1/auth/providers": {"items": []},
    "/v1/accounts": {"items": []},
    "/v1/sync-runs": {"items": []},
    "/v1/destinations": {"items": [{
        "destination_id": "obsidian", "display_name": "Obsidian", "state": "connected",
        "enabled": True, "configured": True, "authorized": True, "automatic": True,
        "exported_count": 1, "content_total": 193,
        "coverage_zh": COVERAGE,
        "last_message_zh": GAP,
        "next_action_zh": GAP,
        "privacy_note_zh": PRIVACY,
        "capabilities": {}, "last_checked_at": "2026-08-05T00:00:00Z",
    }]},
    "/v1/library": {"items": [], "total": 0},
    "/v1/status": {"connectors": [], "destinations": []},
}


# 页面到底问了哪几个接口。**「一张卡都没有」和「压根没走到那一步」长得一样**，
# 这份清单是分开它们的唯一办法。
asked: list[str] = []
served: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        return

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path.startswith("/v1/"):
            asked.append(path)
        for prefix, payload in FAKE.items():
            if path == prefix or path.startswith(prefix + "/"):
                self._send(200, json.dumps(payload, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
        if path.startswith("/v1/"):
            self._send(200, b'{"items": []}', "application/json")
            return
        # **真服务端把 apps/pwa/ 整个挂在 /assets 下**（api.py:1215
        # `app.mount("/assets", StaticFiles(directory=pwa_root))`），目录是平的。
        # 第一版照着 URL 去找 apps/pwa/assets/app.js，**整个脚本 404**，
        # 于是页面一个接口都没请求——报出来却只是一句「0 张卡」。
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        if name.startswith("assets/"):
            name = name[len("assets/"):]
        target = PWA / name
        if target.is_file():
            served.append(name)
        if not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        kind = ("text/html; charset=utf-8" if target.suffix == ".html"
                else "text/css" if target.suffix == ".css"
                else "application/javascript" if target.suffix == ".js"
                else "application/octet-stream")
        self._send(200, target.read_bytes(), kind)


async def _rpc_factory(ws):
    counter = {"n": 0}

    async def rpc(method, params=None):
        counter["n"] += 1
        ident = counter["n"]
        await ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await ws.recv())
            if message.get("id") == ident:
                return message

    return rpc


COLLECT_ERRORS = r"""
window.__drillErrors = [];
window.addEventListener("error", e => window.__drillErrors.push(
  "error: " + (e.message || "") + " @" + (e.filename || "").split("/").pop() + ":" + e.lineno));
window.addEventListener("unhandledrejection", e => window.__drillErrors.push(
  "rejected: " + String((e.reason && (e.reason.stack || e.reason.message)) || e.reason).slice(0, 260)));
"""

READ_DOM = r"""
(() => {
  const cards = [...document.querySelectorAll(".destination-live-card")];
  return JSON.stringify({
    _bodyStart: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 220),
    _modalBodyExists: !!document.getElementById("destinationsModalBody"),
    _modalBodyHtmlLen: (document.getElementById("destinationsModalBody") || {}).innerHTML?.length ?? -1,
    _errors: (window.__drillErrors || []).slice(0, 4),
    cardCount: cards.length,
    // 整张卡的可见文字——那两段话必须在里面
    text: cards.map(c => c.innerText).join("\n---\n").slice(0, 1200),
    hasPrivacyClass: !!document.querySelector(".destination-live-card .privacy-note"),
  });
})()
"""


async def run(chrome: str) -> int:
    if not (PWA / "index.html").is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PWA_MISSING"}, ensure_ascii=False))
        return 2
    profile = Path(tempfile.mkdtemp(prefix="sa-pwa-profile-"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", "--remote-debugging-port=9359",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--password-store=basic",
         "--use-mock-keychain", f"http://127.0.0.1:{PORT}/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9359"
    measured: dict = {}
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 4
        await asyncio.sleep(4)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page" and f"127.0.0.1:{PORT}" in t["url"]]
        if not pages:
            print(json.dumps({"status": "FAIL", "error_code": "PAGE_NOT_OPEN"}, ensure_ascii=False))
            return 4
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            await rpc("Page.enable")
            # 报错收集器必须在页面脚本之前装上，所以走 addScriptToEvaluateOnNewDocument + 重载。
            await rpc("Page.addScriptToEvaluateOnNewDocument", {"source": COLLECT_ERRORS})
            await rpc("Page.reload", {"ignoreCache": True})
            await asyncio.sleep(4)
            result = await rpc("Runtime.evaluate", {"expression": READ_DOM, "returnByValue": True})
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                measured = {"error": str(payload["exceptionDetails"])[:300]}
            else:
                measured = json.loads(payload["result"]["value"])
    finally:
        server.shutdown()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    text = str(measured.get("text") or "")
    problems: list[str] = []
    if "app.js" not in served:
        # **这不是「界面没画」，是「界面根本没跑」。** 两者报成同一句话，
        # 就会把自己的夹具错读成产品缺陷——这一条就是那次误读换来的。
        print(json.dumps({"status": "FAIL", "error_code": "APP_SCRIPT_NEVER_SERVED",
                          "served": served, "endpoints_asked": asked,
                          "message_zh": "页面主脚本一次都没被请求到——**这不是通过也不是产品缺陷**，"
                                        "是这个假服务端没把它喂出去。"}, ensure_ascii=False))
        return 4
    if not measured.get("cardCount"):
        problems.append("**一张目的地卡片都没渲染出来**——那这次什么都没验到")
    if COVERAGE not in text:
        problems.append(f"覆盖那一句没显示：{COVERAGE}")
    if "还有 192 条从来没送到这里" not in text:
        problems.append("**差额那句没显示**——服务端说了实话，界面照旧报平安")
    if PRIVACY not in text:
        problems.append("**隐私说明没显示**——八条写了没人看，正是它当初的毛病")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "cards_rendered": measured.get("cardCount"),
        "privacy_note_class_present": measured.get("hasPrivacyClass"),
        "problems": problems,
        "rendered_text": text[:400],
        # **失败时必须说清页面当时在干什么。** 只报一句「0 张卡」而不说
        # 页面报了什么错，下一个人还得把这一段重新查一遍。
        "page_said": {key.lstrip("_"): value for key, value in sorted(measured.items())
                      if key.startswith("_")},
        "endpoints_asked": asked,
        "what_this_does_not_prove": (
            "假数据是最小形状。这证明「这一段会被画出来」，不证明「画出来的数是对的」。"
        ),
    }, ensure_ascii=False))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验档案馆页面真的把那两段话画出来了")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
