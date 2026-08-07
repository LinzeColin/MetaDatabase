#!/usr/bin/env python3
"""弹窗那一屏，在三种状态下分别说什么（2026-08-07）。

## 为什么单挑这一屏

它是他点插件图标看到的第一样东西。而 2026-08-07 读生产才看清他的实况：
三个账号躺在库里（小红书「我」/ 抖音「我的」/ B 站），全是 `disconnected`，
8/3 那晚它们真的自动同步进来过 260 条。

**而这一屏对他说的是：**

    还没有连接平台账号
    连接一次账号后自动全量导入，不需要逐条点击。
    [连接第一个账号]

三句里两句是假的（他连过、也不是"第一个"），而且把他唯一要做的那件事
——重连一次——整个盖掉了。这和 v0.0.0.14 那次「小红书、抖音、B站、快手
的收藏列表现在还读不了」写死在页面上是同一族：**这一屏说的话不随他的状态走。**

## 它怎么验

真 Chrome、装**发布包原样解出来的那一份**、喂一个假档案馆，
逐个状态打开 popup.html 读回那三句话：

    从没连过     → 「还没有连接平台账号」+「连接第一个账号」
    连过后来断了 → 「N 个账号已断开」+ 内容还在 +「重新连接账号」
    连着         → 「N 个账号 · M 条内容」

**三种都要验。** 只验断开那一种的话，一个把所有状态都写成「已断开」的
实现也能过——那种实现对新用户是错的。

假 API 必须跑在 **8765**：manifest 的 host_permissions 里只给了这个端口。
（第一版我随手用了 8791，请求被 Chrome 挡掉，弹窗落进 catch 显示
「私人档案馆尚未连接」——**根本没走到要验的那条分支**，而它看起来只是"没通过"。）

    python3 scripts/popup_states_drill.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "dist" / "social-archive-extension.zip"
EVIDENCE = ROOT / "evidence" / "G2" / "POPUP_STATES.json"
# **必须是 8765**：manifest 的 host_permissions 只给了这个端口。
PORT = 8765
DEBUG_PORT = 9396

_state: dict = {"accounts": []}

# POPUP_STATE_FIXTURE：这不是平台表，是**造三个账号**用的夹具。
# 这个演练验的是三种状态下那三句话，和平台是谁无关；列全九个只会让它更慢，
# 不会多验到任何东西。
SUPPORT = [{"platform": p, "relations": ["favorite"], "sync_supported": True,
            "connect_supported": True}
           for p in ("xiaohongshu", "douyin", "bilibili")]  # POPUP_STATE_FIXTURE


def _accounts(connection_state: str) -> list[dict]:
    return [
        {"id": f"acct-{index}", "platform": platform, "display_name": name,
         "connection_state": connection_state, "content_count": count,
         "auto_sync_enabled": connection_state == "connected"}
        # POPUP_STATE_FIXTURE：照抄他生产库里那三个账号的形状（平台/显示名/条数），
        # 好让读回来的那句话就是他会看到的那句。
        for index, (platform, name, count) in enumerate(  # POPUP_STATE_FIXTURE
            [("xiaohongshu", "我", 1), ("douyin", "我的", 86), ("bilibili", "B站账号", 103)])  # POPUP_STATE_FIXTURE
    ]


class _Api(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:                 # noqa: A003
        return

    def _json(self, code: int, body: dict) -> None:
        blob = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self) -> None:                             # noqa: N802
        path = self.path.split("?")[0]
        if path == "/health":
            return self._json(200, {"status": "ok", "version": "0.0.0.22",
                                    "minimum_extension_version": "0.0.0.9",
                                    "worker": {"alive": True, "ever_seen": True}})
        if path == "/v1/accounts":
            return self._json(200, {"items": _state["accounts"],
                                    "supported_platforms": SUPPORT})
        return self._json(200, {"items": []})


async def _rpc_factory(ws):
    counter = {"n": 0}

    async def rpc(method, params=None):
        counter["n"] += 1
        await ws.send(json.dumps({"id": counter["n"], "method": method, "params": params or {}}))
        while True:
            got = json.loads(await ws.recv())
            if got.get("id") == counter["n"]:
                return got
    return rpc


READ = r"""JSON.stringify({
  title: (document.getElementById('summaryTitle')||{}).textContent||'',
  copy: (document.getElementById('summaryCopy')||{}).textContent||'',
  button: (document.getElementById('primarySyncLabel')||{}).textContent||'',
  // **账号卡片那一行才是印「103 条 · 尚未同步」的地方**——同一行里自相矛盾。
  // 只读顶上那三句的话，这处永远验不到。
  accounts: ((document.getElementById('accountList')||{}).innerText||'')
              .replace(/\s+/g, ' ').slice(0, 200)
})"""


async def run(chrome: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING"},
                         ensure_ascii=False))
        return 2
    workspace = Path(tempfile.mkdtemp(prefix="sa-popup-states-"))
    unpacked = workspace / "extension"
    with zipfile.ZipFile(ZIP) as archive:
        archive.extractall(unpacked)

    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    headless = [] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync", *headless,
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    measured: dict = {}
    problems: list[str] = []
    try:
        for _ in range(40):
            try:
                version = json.loads(
                    urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                             # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"},
                             ensure_ascii=False))
            return 2

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            extension_id = (await rpc("Extensions.loadUnpacked", {"path": str(unpacked)})
                            ).get("result", {}).get("id") or ""
        if not extension_id:
            problems.append("Chrome 装不上这个包")
        else:
            await asyncio.sleep(3)
            workers = [t for t in json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
                       if t.get("type") == "service_worker" and extension_id in t.get("url", "")]
            if not workers:
                problems.append("装上了，但 service worker 起不来")
            else:
                async with websockets.connect(workers[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await _rpc_factory(ws)
                    await rpc("Runtime.enable")
                    await rpc("Runtime.evaluate", {
                        "expression": f'SA.setConfig({{endpoint:"http://127.0.0.1:{PORT}",'
                                      f' token:"drill"}})',
                        "awaitPromise": True, "returnByValue": True})

                for label, accounts in (("从没连过", []),
                                        ("连过后来断了", _accounts("disconnected")),
                                        ("连着", _accounts("connected"))):
                    _state["accounts"] = accounts
                    url = f"chrome-extension://{extension_id}/popup.html"
                    seen = {item.get("id") for item in json.loads(
                        urllib.request.urlopen(base + "/json", timeout=5).read())}
                    urllib.request.urlopen(urllib.request.Request(
                        base + "/json/new?" + url, method="PUT"), timeout=10).read()
                    pages: list = []
                    for _ in range(20):
                        await asyncio.sleep(0.5)
                        pages = [t for t in json.loads(
                            urllib.request.urlopen(base + "/json", timeout=5).read())
                            if t.get("type") == "page" and "popup.html" in t.get("url", "")
                            and t.get("id") not in seen]
                        if pages:
                            break
                    if not pages:
                        problems.append(f"{label}：弹窗没打开")
                        continue
                    async with websockets.connect(pages[0]["webSocketDebuggerUrl"],
                                                  max_size=None) as ws:
                        rpc = await _rpc_factory(ws)
                        await rpc("Runtime.enable")
                        await asyncio.sleep(3)
                        got = await rpc("Runtime.evaluate",
                                        {"expression": READ, "returnByValue": True})
                        measured[label] = json.loads(got["result"]["result"]["value"])
                    urllib.request.urlopen(urllib.request.Request(
                        base + "/json/close/" + pages[0]["id"]), timeout=10).read()
                    await asyncio.sleep(0.5)
    finally:
        server.shutdown()
        process.terminate()
        shutil.rmtree(workspace, ignore_errors=True)

    fresh = measured.get("从没连过") or {}
    stale = measured.get("连过后来断了") or {}
    live = measured.get("连着") or {}
    if not (fresh and stale and live):
        problems.append("**三种状态没量全**——这不是通过。")
    else:
        if "第一个" not in fresh.get("button", ""):
            problems.append(f"从没连过时主按钮不是「连接第一个账号」：{fresh.get('button')!r}")
        # **这一条是这个演练存在的理由。**
        if "第一个" in stale.get("button", "") or "还没有连接" in stale.get("title", ""):
            problems.append(
                f"**连过、后来断了，却还在说「{stale.get('title')}」/「{stale.get('button')}」**"
                "——他连过三个账号，这两句对他都是假的，"
                "而且把「重连一次就恢复」这条唯一要做的事盖掉了")
        if "一条都没少" not in stale.get("copy", ""):
            problems.append(
                f"断开这一屏没说清内容还在：{stale.get('copy')!r}——"
                "「未连接」很容易被读成「我的收藏没了」")
        if stale.get("title") == fresh.get("title") or live.get("title") == stale.get("title"):
            problems.append("**三种状态里有两种说同一句话**——那就等于没分状态")
        # **账号卡片不许自相矛盾。**
        cards = stale.get("accounts", "")
        if "尚未同步" in cards and "条" in cards:
            problems.append(
                f"**账号卡片印着「N 条 · 尚未同步」**：{cards[:80]!r}——"
                "同一行里自相矛盾（`last_sync_at` 只在完全跑完时才写，"
                "而他那几次跑完了、进了 102 条、结局是 partial）")
        # **账号卡片上不许出现英文状态 id。**
        # `statusName[current] || current` 那种兜底会安静地把内部值印给用户；
        # 少一个键就漏一个词，而它不出声。这条通用地挡住，不只挡 disconnected。
        RAW_STATES = ("disconnected", "connected", "degraded", "authorizing", "queued",
                      "discovering", "scanning", "normalizing", "artifacting",
                      "exporting", "completed", "partial", "failed",
                      "blocked_environment", "paused", "cancelled")
        for reading in (stale, live):
            leaked = [name for name in RAW_STATES if name in reading.get("accounts", "")]
            if leaked:
                problems.append(
                    f"**账号卡片上印着英文状态**：{leaked}——"
                    "他看到的是内部值，不是人话")
        if "条内容" not in live.get("title", ""):
            problems.append(f"连着的时候不报条数：{live.get('title')!r}")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "measured_in_real_chrome": measured,
        "problems": problems,
        "why_zh": ("弹窗是他点插件图标看到的第一屏。三种状态各说各的话，"
                   "**只验一种的话，一个把所有状态都写成同一句的实现也能过**。"),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def main() -> int:
    chrome = os.environ.get("SA_CHROME") or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not Path(chrome).exists():
        print(json.dumps({"status": "FAIL", "error_code": "CHROME_MISSING"},
                         ensure_ascii=False))
        return 2
    return asyncio.run(run(chrome))


if __name__ == "__main__":
    sys.exit(main())
