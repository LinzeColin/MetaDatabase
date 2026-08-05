#!/usr/bin/env python3
"""装着旧插件的人，能不能靠这一页把它更新掉（v0.0.0.7 / T02）。

## 为什么有这个

2026-08-06 Owner 的原话：

    「在首页点『去更新』后可以跳转页面到 /extension-install，
      但是不能真的更新插件版本，整个软件完全不能使用」

查下来这一页上三处都坏了：

1. **整页没有一个字讲怎么更新。** 从头到尾是首次安装的四步；
   照着做只会用「加载已解压的扩展程序」再装一次，得到**第二个插件**。
2. **检测只问「插件在不在」，不问「版本对不对」。** 于是旧插件也会应答，
   页面说「✓ 已检测到插件，正在把你送回首页」——回到首页又说「去更新」。
   **一个死循环。**
3. **「返回 Social Archive」指向 `/home`，而那个地址回 404。**

而 `app.js` 里 `ensureExtensionReady()` 在版本不符时直接 `return false`——
**同步、保存、连接全被挡住**。所以「整个软件完全不能使用」不是夸张。

## 更新到底该怎么做（实测出来的，不是猜的）

未打包扩展的 ID 由**文件夹路径**决定。实测：

    同一个文件夹装两次 → ID 相同
    换一个文件夹装     → ID 不同
    在原文件夹里换掉文件再重新载入 → ID 不变、版本更新、**已存的凭据还在**

所以正确做法是「**在原文件夹里覆盖，再点重新加载**」，而不是换个地方重装。
换地方 = 两个插件 + 凭据留在旧的那个上。这段话现在写在页面里。

## 这个演练验什么

起一个假档案馆（页面 + `/health` 回一个可控的版本号），用真 Chrome 打开这一页：

  · **没装插件**      → 该显示首次安装四步，不显示更新那段
  · **装了、版本对**   → 该变绿并跳回 "/"
  · **装了、版本不对** → 该显示**更新那一段**，并且**不许跳走**

第三种正是 Owner 撞上的那一种。

## 边界

· 一次性 profile，跑完删；只连 127.0.0.1；不碰生产。
· 只验这一页的行为。真去 Chrome 里覆盖文件夹、点重新加载那几下是人做的，
  演练替不了——但上面那三行 ID 实测已经把「该怎么做」钉死了。
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
DEBUG_PORT = 9375

served_version = {"value": "0.0.0.7"}


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
        if path == "/health":
            self._send(200, json.dumps({"status": "ok", "version": served_version["value"]}).encode(),
                       "application/json")
            return
        name = {"/": "index.html", "": "index.html",
                "/extension-install": "extension-install.html"}.get(path, path.lstrip("/"))
        if name.startswith("assets/"):
            name = name[len("assets/"):]
        target = PWA / name
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


READ = r"""
(() => JSON.stringify({
  url: location.pathname,
  headline: (document.getElementById("headline") || {}).textContent || "",
  detect: (document.getElementById("detectText") || {}).textContent || "",
  updateShown: !(document.getElementById("updateBlock") || {}).hidden,
  installShown: !(document.getElementById("installSteps") || {}).hidden,
  // 「返回」按钮指到哪儿——它曾经指向一个 404
  backHref: (document.querySelector(".button.secondary") || {}).getAttribute
              ? document.querySelector(".button.secondary").getAttribute("href") : "",
  saysHowToUpdate: (document.body.innerText || "").includes("覆盖进你原来那个插件文件夹"),
  warnsAboutSecondCopy: (document.body.innerText || "").includes("新的插件 ID"),
}))()
"""


async def _case(chrome: str, ext_dir: str | None, version: str) -> dict:
    served_version["value"] = version
    profile = Path(tempfile.mkdtemp(prefix="sa-install-page-"))
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--password-store=basic",
         "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    measured: dict = {}
    try:
        for _ in range(40):
            try:
                version_info = json.loads(
                    urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            return {"error": "CHROME_NOT_UP"}
        async with websockets.connect(version_info["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            if ext_dir:
                loaded = await rpc("Extensions.loadUnpacked", {"path": ext_dir})
                if "error" in loaded:
                    return {"error": "LOAD_UNPACKED_FAILED"}
                await asyncio.sleep(2)
            await rpc("Target.createTarget",
                      {"url": f"http://127.0.0.1:{PORT}/extension-install"})
        # 留足时间：检测每 1.5 秒一轮，跳转还有 1.5 秒延时
        await asyncio.sleep(7)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page" and f"127.0.0.1:{PORT}" in t["url"]]
        if not pages:
            return {"error": "PAGE_NOT_OPEN"}
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            result = await rpc("Runtime.evaluate", {"expression": READ, "returnByValue": True})
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                return {"error": str(payload["exceptionDetails"])[:200]}
            measured = json.loads(payload["result"]["value"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)
    return measured


async def run(chrome: str, ext_dir: str) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    problems: list[str] = []
    report: dict = {}
    try:
        installed = json.loads((Path(ext_dir) / "manifest.json").read_text(encoding="utf-8"))["version"]

        no_ext = await _case(chrome, None, installed)
        report["没装插件"] = no_ext
        if no_ext.get("error"):
            problems.append(f"「没装插件」那一趟没跑成：{no_ext['error']}")
        else:
            if not no_ext.get("installShown"):
                problems.append("**没装插件时不显示安装四步**")
            if no_ext.get("updateShown"):
                problems.append("没装插件却在讲怎么更新")
            if no_ext.get("backHref") != "/":
                problems.append(f"「返回」按钮指向 {no_ext.get('backHref')!r}——它曾经指向 /home 而那是 404")

        same = await _case(chrome, ext_dir, installed)
        report["装了且版本对"] = same
        if same.get("error"):
            problems.append(f"「版本对」那一趟没跑成：{same['error']}")
        elif same.get("url") != "/":
            problems.append(f"版本对上了却没有把人送回资料库（还停在 {same.get('url')}）")

        stale = await _case(chrome, ext_dir, "9.9.9.9")
        report["装了但版本旧"] = stale
        if stale.get("error"):
            problems.append(f"「版本旧」那一趟没跑成：{stale['error']}")
        else:
            # **这一趟是 Owner 撞上的那一种。**
            if stale.get("url") == "/":
                problems.append(
                    "**版本不符却把人送回了资料库**——回去之后首页还是叫他「去更新」，"
                    "这就是那个来回弹的死循环")
            if not stale.get("updateShown"):
                problems.append("**版本不符时不显示更新说明**——这一页从头到尾只讲首次安装")
            if not stale.get("saysHowToUpdate"):
                problems.append("更新说明里没有那句「覆盖进你原来那个插件文件夹」——那是唯一正确的做法")
            if not stale.get("warnsAboutSecondCopy"):
                problems.append("没有警告「换个文件夹装会变成第二个插件」——实测 ID 会变、凭据会留在旧的那个上")
    finally:
        server.shutdown()

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "cases": report,
        "problems": problems,
        "what_this_does_not_prove": (
            "只验这一页的行为。真去 Chrome 里覆盖文件夹、点重新加载那几下是人做的，"
            "演练替不了；但「覆盖再重载」这条路本身另有实测（ID 不变、版本更新、凭据还在）。"
        ),
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验安装页对「已装旧版」的人真的管用")
    parser.add_argument("--ext-dir", required=True)
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING"}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, str(Path(args.ext_dir).resolve())))


if __name__ == "__main__":
    sys.exit(main())
