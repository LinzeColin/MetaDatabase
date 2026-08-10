#!/usr/bin/env python3
"""「删除并清空」那颗按钮，**在真 Chrome 里画出来了、点得动、真发出请求**（2026-08-11）。

## 为什么不是「测试都过了」就够

判据验的是 `apps/pwa/app.js` 这个**仓里的文件**。而 0.0.0.29 那次实测证明了
仓里对不等于他浏览器里对：公网那份 `app.js` 是 137559 字节的旧文件
（容器里 140335、`cf-cache-status: HIT`、`age: 3794`），**里面没有这颗按钮**。

所以这个演练取的不是磁盘上那份，是**从公开域名按浏览器的走法取回来的那份**：

    GET /                       ← 首页（实测 cf-cache-status: DYNAMIC，不缓存）
    从 HTML 里读出 ?v= 那几个键，逐个 GET 回来

然后把这几份字节喂给真 Chrome。**验的是他真会拿到的那些字节。**

## 三件事，缺一件都不算这颗按钮能用

1. **画出来**：已连接的账号那一行上有它；
2. **点得动且拦得住误点**：名字打错 → 一个请求都不发，并说清差在哪；
3. **打对了名字 → 真发 `POST /v1/accounts/{id}/forget`**，界面照服务端的回话说。

## 边界（这个演练不证明什么）

接口是假的——它不证明服务端真把数据删干净了（那件事由
`test_he_can_delete_an_account_and_start_over.py` 和从零那一轮在真镜像上验）。
它证明的是**这颗按钮到得了他手上、按得下去、按下去会发生什么**。

## 无头

`--headless=new`。Owner 说过「为什么你永远都要不停开了又关我的浏览器」——
演练不许抢屏幕。调试时设 `SA_DRILL_HEADED=1`。
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
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
PORT = 8771
DEBUG_PORT = 9371
DEFAULT_ORIGIN = "https://social-archive-api.linzezhang.com"

# 夹具照他生产库里的实况：三个国内平台，抖音那个有 86 条。
ACCOUNTS = {
    "items": [
        {"id": "acct_douyin", "platform": "douyin", "display_name": "抖音",
         "connection_state": "connected", "auto_sync_enabled": True, "content_count": 86},
        {"id": "acct_bili", "platform": "bilibili", "display_name": "B站",
         "connection_state": "disconnected", "auto_sync_enabled": False, "content_count": 103},
    ],
    "supported_platforms": ["bilibili", "douyin", "kuaishou", "xiaohongshu",
                            "generic-web", "instagram", "reddit", "x", "youtube"],
}

FAKE: dict[str, dict] = {
    "/v1/auth/me": {"id": "user_1", "email": "owner@example.com", "display_name": "Owner"},
    "/v1/accounts": ACCOUNTS,
    "/v1/sync-runs": {"items": []},
    "/v1/status": {"connectors": [], "destinations": []},
    "/v1/library": {"items": [], "total": 0, "facets": {}},
}

# 页面真发出去的写请求。**「按钮点了没反应」和「按钮根本没画出来」长得一样**，
# 这份清单是分开它们的唯一办法。
posted: list[dict] = []
assets: dict[str, tuple[bytes, str]] = {}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        return

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        posted.append({"path": path, "body": raw.decode("utf-8", "replace")[:200]})
        if path.endswith("/forget"):
            self._send(200, json.dumps({
                "status": "ok", "deleted_content": 86, "kept_shared_content": 0,
                "message_zh": "已删除「抖音」，连同它带进来的 86 条内容。",
            }, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        self._send(200, b"{}", "application/json")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        for prefix, payload in FAKE.items():
            if path == prefix or path.startswith(prefix + "/"):
                self._send(200, json.dumps(payload, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
        if path.startswith("/v1/"):
            self._send(200, b'{"items": []}', "application/json")
            return
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        if name.startswith("assets/"):
            name = name[len("assets/"):]
        if name in assets:
            body, kind = assets[name]
            self._send(200, body, kind)
            return
        self._send(404, b"not found", "text/plain")


def fetch_front_end_the_way_a_browser_would(origin: str) -> dict:
    """按浏览器的走法从公开域名取：先首页，再按首页里那几个键取资源。

    **不加任何绕缓存的参数**——加了就等于验了一条他走不到的路。
    """
    def get(url: str) -> tuple[bytes, dict]:
        request = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(), dict(response.headers)

    html, html_headers = get(origin + "/")
    text = html.decode("utf-8")
    refs = re.findall(r"""(?:src|href)=["'](/assets/[^"']+)""", text)
    stamps = sorted({m.group(1) for m in re.finditer(r"""\?v=([^"'\s>]+)""", text)})
    assets["index.html"] = (html, "text/html; charset=utf-8")
    fetched = []
    for ref in refs:
        name = ref.split("?")[0][len("/assets/"):]
        body, headers = get(origin + ref)
        kind = ("application/javascript" if name.endswith(".js")
                else "text/css" if name.endswith(".css")
                else "image/svg+xml" if name.endswith(".svg")
                else "application/json")
        assets[name] = (body, kind)
        fetched.append({"url": ref, "bytes": len(body),
                        "cf_cache_status": headers.get("cf-cache-status", ""),
                        "age": headers.get("age", "")})
    return {"origin": origin, "index_bytes": len(html),
            "index_cf_cache_status": html_headers.get("cf-cache-status", ""),
            "stamps_in_index": stamps, "assets": fetched}


READ_BUTTON = r"""
(() => {
  const rows = [...document.querySelectorAll("#syncTableBody tr")];
  const buttons = [...document.querySelectorAll("[data-forget-account]")];
  return JSON.stringify({
    rowCount: rows.length,
    rowsText: rows.map(r => (r.innerText || "").replace(/\s+/g, " | ").slice(0, 160)),
    forgetButtons: buttons.map(b => ({
      label: (b.textContent || "").trim(),
      accountId: b.dataset.forgetAccount,
    })),
    errors: (window.__drillErrors || []).slice(0, 4),
  });
})()
"""

# 打开同步中心那一屏（按钮在那儿），并把 prompt/alert 换成受控的。
OPEN_CENTRE = r"""
(() => {
  window.__drillErrors = window.__drillErrors || [];
  document.getElementById("openSync")?.click();
  document.getElementById("emptyConnectAccount")?.click();
  document.querySelector("[data-open-sync]")?.click();
  return document.querySelectorAll("[data-forget-account]").length;
})()
"""


def click_with_prompt(answer: str) -> str:
    """点那颗按钮，并让 `prompt` 返回指定的答案。"""
    return (
        "(async () => {"
        "  const original = window.prompt;"
        f" window.prompt = () => {json.dumps(answer)};"
        "  const button = document.querySelector('[data-forget-account]');"
        "  if (!button) return JSON.stringify({clicked: false});"
        "  button.click();"
        "  await new Promise(r => setTimeout(r, 1200));"
        "  window.prompt = original;"
        "  const toasts = [...document.querySelectorAll('.toast, #toastStack *')]"
        "    .map(t => (t.textContent || '').trim()).filter(Boolean);"
        "  return JSON.stringify({clicked: true, toasts: toasts.slice(0, 4),"
        "    buttonLabel: (button.textContent || '').trim()});"
        "})()"
    )


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


async def run(chrome: str, origin: str) -> int:
    try:
        supply = fetch_front_end_the_way_a_browser_would(origin)
    except Exception as error:                                   # noqa: BLE001
        print(json.dumps({"status": "FAIL", "error_code": "ORIGIN_UNREACHABLE",
                          "origin": origin, "detail": str(error)[:200]}, ensure_ascii=False))
        return 3
    if "app.js" not in assets:
        print(json.dumps({"status": "FAIL", "error_code": "APP_SCRIPT_NEVER_SERVED",
                          "supply": supply,
                          "message_zh": "首页没有引到 app.js——这是夹具/取法的问题，不是产品缺陷"},
                         ensure_ascii=False))
        return 3

    profile = Path(tempfile.mkdtemp(prefix="sa-forget-profile-"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         *([] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]),
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--password-store=basic",
         "--use-mock-keychain", f"http://127.0.0.1:{PORT}/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    measured: dict = {}
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(base + "/json/version", timeout=2).read()
                break
            except Exception:                                     # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 4
        await asyncio.sleep(3)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page" and f"127.0.0.1:{PORT}" in t["url"]]
        if not pages:
            print(json.dumps({"status": "FAIL", "error_code": "PAGE_NOT_OPEN"}, ensure_ascii=False))
            return 4
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            await rpc("Page.enable")
            await rpc("Page.addScriptToEvaluateOnNewDocument", {"source": COLLECT_ERRORS})
            await rpc("Page.reload", {"ignoreCache": True})
            await asyncio.sleep(4)

            async def evaluate(expression: str):
                got = await rpc("Runtime.evaluate", {
                    "expression": expression, "returnByValue": True, "awaitPromise": True})
                payload = got.get("result", {})
                if payload.get("exceptionDetails"):
                    return {"_exception": str(payload["exceptionDetails"])[:300]}
                return json.loads(payload["result"]["value"])

            await rpc("Runtime.evaluate", {"expression": OPEN_CENTRE, "returnByValue": True})
            await asyncio.sleep(1.5)
            measured["rendered"] = await evaluate(READ_BUTTON)

            posted.clear()
            measured["wrong_name"] = await evaluate(click_with_prompt("打错了"))
            measured["wrong_name_requests"] = list(posted)

            posted.clear()
            measured["right_name"] = await evaluate(click_with_prompt("抖音"))
            measured["right_name_requests"] = list(posted)
    finally:
        process.terminate()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    rendered = measured.get("rendered", {})
    buttons = rendered.get("forgetButtons", [])
    problems: list[str] = []
    if not buttons:
        problems.append("真 Chrome 里一颗「删除并清空」都没画出来——他点不到它")
    elif not all(b.get("label") == "删除并清空" for b in buttons):
        problems.append(f"按钮上的字不是「删除并清空」：{[b.get('label') for b in buttons]}")
    if measured.get("wrong_name_requests"):
        problems.append(f"名字打错了它还是发了请求：{measured['wrong_name_requests']}")
    if not any("没有删除" in t for t in measured.get("wrong_name", {}).get("toasts", [])):
        problems.append("名字打错时没有告诉他差在哪")
    right = measured.get("right_name_requests", [])
    if not any(r["path"].endswith("/forget") for r in right):
        problems.append(f"名字打对了却没有发 forget 请求：{right}")
    if not any("已删除" in t for t in measured.get("right_name", {}).get("toasts", [])):
        problems.append("删完没有把服务端那句话说给他听")
    if rendered.get("errors"):
        problems.append(f"页面报错：{rendered['errors']}")

    result = {
        "status": "FAIL" if problems else "PASS",
        "what_this_proves": "他打得到的那个域名下发的那份前端，在真 Chrome 里画出了"
                            "「删除并清空」，误点拦得住，打对名字会真发 POST …/forget",
        "what_this_does_not_prove": "接口是假的——服务端删干净没有由从零那一轮在真镜像上验",
        "supply_from_production": supply,
        "measured": measured,
        "problems": problems,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="真 Chrome 里验「删除并清空」这颗按钮")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--origin", default=DEFAULT_ORIGIN,
                        help="从哪里取前端；默认是他打得到的那个公开域名")
    args = parser.parse_args()
    if not Path(args.chrome).exists():
        print(json.dumps({"status": "FAIL", "error_code": "CHROME_MISSING",
                          "chrome": args.chrome}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, args.origin))


if __name__ == "__main__":
    sys.exit(main())
