#!/usr/bin/env python3
"""「保存当前页」那一下，真的把东西送到档案馆了吗（v0.0.0.7 / T08）。

## 为什么补这个

2026-08-05 数了一遍扩展的消息类型：25 种，判据里没出现过的 9 种。
其中一种是 `SA_CAPTURE_ACTIVE`——**产品最主要的那个动作**：
Owner 在任意页面点一下「保存到我的档案馆」。

它此前只有源码层的断言（「background.js 里有 captureActive 这个函数」），
**没有任何东西验过按下去之后字节真的到了服务端**。

## 它怎么验

在 127.0.0.1:8765 起一个假档案馆（扩展装的时候就拿到了这个域的权限）：

  · `GET /page`        —— 一个有标题、有正文的普通页面
  · `POST /v1/captures` —— 记下收到的请求体，回 202

然后把扩展装进一次性 profile 的真 Chrome，配好服务地址与令牌，
打开那个页面，**在 service worker 里真调一次 `captureActive`**，
最后回头看假服务器收到了什么。

## 它不是什么

不是端到端验收：假服务器不落库、不归档、不投递。它只回答一个问题——
**那一下有没有把这一页的东西发出去，发出去的是不是这一页。**

## 边界

· 一次性 profile，跑完删；不碰 Owner 的 profile、不碰生产。
· 只连 127.0.0.1；不访问任何真实平台。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from drill_extension_dir import resolve_ext_dir  # noqa: E402

PORT = 8765
PAGE_PATH = "/page"
PAGE_TITLE = "存档演练用的一页"
PAGE_BODY = "这一段正文只在这台机器上，用来确认发出去的是这一页而不是别的。"
received: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # 静音
        return

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith(PAGE_PATH):
            html = (f"<!doctype html><html><head><meta charset='utf-8'>"
                    f"<title>{PAGE_TITLE}</title></head>"
                    f"<body><article><h1>{PAGE_TITLE}</h1>"
                    f"<p>{PAGE_BODY}</p></article></body></html>")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._send(404, b"{}", "application/json")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {"__unparsable__": raw[:200].decode("utf-8", "replace")}
        received.append({"path": self.path, "body": body})
        self._send(202, json.dumps({"ok": True, "id": "cap_fixture"}).encode(), "application/json")


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


# **键名要照 shared.js 的 DEFAULT_CONFIG 写。**
# 第一版按 `saServiceUrl` / `saExtensionToken` 猜，captureActive 回了一句
# 「扩展尚未授权或令牌已失效」——那是**产品做对了**（没授权就不往外发），
# 是我的配置压根没落到它读的那几个键上。真正的键是 endpoint / token。
CONFIGURE = """
(async () => {
  await chrome.storage.local.set({
    endpoint: "http://127.0.0.1:%d",
    token: "fixture-token",
    destinationIds: ["social_archive"],
    onboardingComplete: true,
  });
  const config = await SA.getConfig();
  return JSON.stringify({ endpoint: config.endpoint, hasToken: !!config.token });
})()
""" % PORT

SAVE = """
(async () => {
  const tabs = await chrome.tabs.query({});
  const tab = tabs.find(t => (t.url || "").includes("%s"));
  if (!tab) return JSON.stringify({ error: "NO_TAB" });
  try {
    const result = await captureActive({ mode: "page" }, tab);
    return JSON.stringify({ ok: true, result: result });
  } catch (error) {
    return JSON.stringify({ ok: false, threw: String(error).slice(0, 300) });
  }
})()
""" % PAGE_PATH


async def run(chrome: str, ext_dir: str) -> int:
    profile = Path(tempfile.mkdtemp(prefix="sa-save-profile-"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", "--remote-debugging-port=9355",
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9355"
    report: dict = {}
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001 —— 等它起来
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 4

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": ext_dir})
            if "error" in loaded:
                print(json.dumps({"status": "FAIL", "error_code": "LOAD_UNPACKED_FAILED",
                                  "detail": str(loaded["error"])[:200]}, ensure_ascii=False))
                return 4
            extension_id = loaded["result"]["id"]
            await rpc("Target.createTarget", {"url": f"http://127.0.0.1:{PORT}{PAGE_PATH}"})
        await asyncio.sleep(3)

        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        workers = [t for t in targets if t["type"] == "service_worker" and extension_id in t["url"]]
        if not workers:
            print(json.dumps({"status": "FAIL", "error_code": "SERVICE_WORKER_ASLEEP"},
                             ensure_ascii=False))
            return 4
        async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            configured = await rpc("Runtime.evaluate",
                                   {"expression": CONFIGURE, "returnByValue": True,
                                    "awaitPromise": True})
            report["configured"] = configured.get("result", {}).get("result", {}).get("value")
            saved = await rpc("Runtime.evaluate",
                              {"expression": SAVE, "returnByValue": True, "awaitPromise": True})
            payload = saved.get("result", {})
            if payload.get("exceptionDetails"):
                report["save"] = {"threw": str(payload["exceptionDetails"])[:300]}
            else:
                report["save"] = json.loads(payload["result"]["value"])
        await asyncio.sleep(1.5)
    finally:
        server.shutdown()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    problems: list[str] = []
    if not received:
        problems.append("**假档案馆一个请求都没收到**——那一下什么都没发出去")
    posted = [r for r in received if "/v1/captures" in r["path"]]
    if received and not posted:
        problems.append(f"发了请求，但没有一个打到 /v1/captures：{[r['path'] for r in received]}")
    # **发出去的得是这一页。** 只看「有没有发」的话，发一个空壳也算过。
    body_text = json.dumps(posted[0]["body"], ensure_ascii=False) if posted else ""
    if posted and PAGE_TITLE not in body_text:
        problems.append(f"发出去了，但里面没有这一页的标题——发的可能是别的东西：{body_text[:200]}")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "requests_received": [r["path"] for r in received],
        "posted_to_captures": len(posted),
        "title_made_it": bool(posted) and PAGE_TITLE in body_text,
        "worker_said": report.get("save"),
        "problems": problems,
        "what_this_does_not_prove": (
            "假档案馆不落库、不归档、不投递。这只回答一个问题："
            "**那一下有没有把这一页发出去，发出去的是不是这一页。**"
        ),
    }, ensure_ascii=False))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验「保存当前页」真的把这一页发到了档案馆")
    parser.add_argument("--ext-dir", default=None,
                        help="解压好的扩展目录；不给就用 dist 里的发布包")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    # 没给 --ext-dir 就用发布包：要先打包再解压才跑得动的演练，
    # 就是没人跑的演练；默认用发布包还顺带让它验的是他真正下载的那一份。
    args.ext_dir = resolve_ext_dir(args.ext_dir)
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING"}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, str(Path(args.ext_dir).resolve())))


if __name__ == "__main__":
    sys.exit(main())
