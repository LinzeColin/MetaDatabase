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

★ **别拿这套夹具去点「连接账号」。**（2026-08-11 试过一次，卡住了）
`connectAccount()` 第一步是 `await ensureExtensionReady()`，而这里**没有装扩展**——
那个 await 不返回，`Runtime.evaluate` 就一直等，整个脚本挂住。
这不是产品缺陷，是这套夹具的射程之外：连账号那条路要真扩展 + 真授权框。
它由 `bilibili_end_to_end_drill.py` 管（真 Chrome + 真发布包，
「从连接账号到档案馆里真的出现条目」），每次部署都跑。

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
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
# 装的是**发布包**（跑前按当前源码重打一次），不是源码目录。
#
# ★ 这一行被我自己的一次「按两个锚点切掉整段」的替换误删过，
#   演练当场 NameError，而我是从**部署日志**发现的。
#   补回来时又踩第二下：`.replace()` 的锚点已经不存在了，
#   替换成了空操作而脚本照样打印「放回去了」——
#   **无声的 no-op 和成功长得一模一样**。现在改完必须 assert 落地。
EXTENSION_ZIP = ROOT / "dist/social-archive-extension.zip"
# **必须是 8765。**（2026-08-11）
# 扩展的 host_permissions 里只有 `http://127.0.0.1:8765/*` 这一个本机源，
# 换个端口内容脚本就注不进去、页面永远认不出插件——
# 这个演练此前用 8771，于是**所有以「插件装着」为前提的界面它一屏都走不到**
# （「下一步」那张卡永远停在「第 1 步：安装浏览器插件」，
# 点「连接账号」则挂在 ensureExtensionReady 上不返回）。
PORT = 8765
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
    # **形状要和服务端下发的一样**：一个对象数组，不是一串平台名。
    # 我第一版给的是字符串数组，于是「第 3 步」那张卡渲染成
    # 「本版本能自动同步的是：undefined。」——**夹具的错**，
    # 但那句话要是真出现在他屏幕上就是产品的错，所以下面单独断言不许有 undefined。
    #
    # **九个平台一个都不能少，写在同一个字面量里。**
    # 我第二版把它拆成两段推导式（能同步的 7 个 + 不能的 2 个），
    # check_every_platform_table_is_complete.py 立刻报「这张表里没有 x / youtube」
    # ——它按字面量逐张查，拆开就成了两张各自不全的表。那道门是对的：
    # 平台表漏一个，用户看到的就是内部 id、空白，或者一个根本不存在的按钮。
    "supported_platforms": [
        {"platform": "bilibili", "sync_supported": True, "connect_supported": True},
        {"platform": "douyin", "sync_supported": True, "connect_supported": True},
        {"platform": "kuaishou", "sync_supported": True, "connect_supported": True},
        {"platform": "xiaohongshu", "sync_supported": True, "connect_supported": True},
        {"platform": "generic-web", "sync_supported": True, "connect_supported": True},
        {"platform": "instagram", "sync_supported": True, "connect_supported": True},
        {"platform": "reddit", "sync_supported": True, "connect_supported": True},
        {"platform": "x", "sync_supported": False, "connect_supported": True,
         "not_syncable_reason": "本版本还不能自动同步这个平台。"},
        {"platform": "youtube", "sync_supported": False, "connect_supported": True,
         "not_syncable_reason": "本版本还不能自动同步这个平台。"},
    ],
}

FAKE: dict[str, dict] = {
    # **`/health` 不能少。** 它不在 /v1/ 下，假服务端会 404 它，
    # 于是 `loadHealth()` 抛错、右上角徽章变成「私人档案馆暂时不可用」——
    # 那是**夹具的毛病**，而它看起来和一个真缺陷一模一样。
    "/health": {"status": "ok", "version": "0.0.0.0", "minimum_extension_version": "0.0.0.0",
                "worker": {"ever_seen": True, "alive": True}},
    "/v1/storage/status": {"status": "ok", "replicas": []},
    "/v1/auth/me": {"id": "user_1", "email": "owner@example.com", "display_name": "Owner"},
    "/v1/accounts": ACCOUNTS,
    "/v1/sync-runs": {"items": []},
    "/v1/status": {"connectors": [], "destinations": []},
    "/v1/library": {"items": [], "total": 0, "facets": {}},
    "/v1/extension/bootstrap": {"status": "ok", "paired": True},
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
    // 他照说明书第 3 步要点的就是这张卡。**正对照**：卡片停在第 1/2 步
    // 说明插件没被认出来，那这条断言就是空转，不许当通过。
    nextStep: ((document.getElementById("nextStep") || {}).innerText || "")
      .replace(/\s+/g, " ").slice(0, 260),
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

    # **按当前源码重打一次包再装。**（stale-artifacts-from-my-machine-leak-into-the-build）
    build = subprocess.run([sys.executable, str(ROOT / "scripts/build_extension_package.py")],
                           cwd=ROOT, capture_output=True, text=True, check=False)
    if build.returncode != 0:
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_BUILD_FAILED",
                          "detail": (build.stdout + build.stderr)[-400:]}, ensure_ascii=False))
        return 3
    profile = Path(tempfile.mkdtemp(prefix="sa-forget-profile-"))
    unpacked = profile.parent / (profile.name + "-ext")
    with zipfile.ZipFile(EXTENSION_ZIP) as archive:
        archive.extractall(unpacked)
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
        # 装发布包，并把它和假档案馆配上对。
        version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=5).read())
        extension_id = ""
        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            got = await rpc("Extensions.loadUnpacked", {"path": str(unpacked)})
            extension_id = (got.get("result") or {}).get("id", "")
        for _ in range(20):
            workers = [x for x in json.loads(
                urllib.request.urlopen(base + "/json", timeout=5).read())
                if x.get("type") == "service_worker" and extension_id in x.get("url", "")]
            if workers:
                async with websockets.connect(workers[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await _rpc_factory(ws)
                    await rpc("Runtime.enable")
                    await rpc("Runtime.evaluate", {
                        "expression": f'SA.setConfig({{endpoint:"http://127.0.0.1:{PORT}",'
                                      f' token:"drill"}})',
                        "awaitPromise": True, "returnByValue": True})
                break
            await asyncio.sleep(0.5)
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

            # ── 第二遍：把账号全设成 disconnected，重载，再读那张卡 ──
            # 这正是 Owner 现在的状态（三个账号全断开），
            # 也正是《使用说明》第 3 步描述的那一屏。
            FAKE["/v1/accounts"] = {
                "items": [{**item, "connection_state": "disconnected",
                           "auto_sync_enabled": False}
                          for item in ACCOUNTS["items"]],
                "supported_platforms": ACCOUNTS["supported_platforms"],
            }
            await rpc("Page.reload", {"ignoreCache": True})
            await asyncio.sleep(4)
            measured["all_disconnected"] = await evaluate(READ_BUTTON)
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
    # **正对照**：卡片停在第 1/2 步 = 这一页没认出插件，
    # 那么所有「以插件装着为前提」的断言都是空转，不许当通过。
    step = rendered.get("nextStep", "")
    if "第 1 步" in step or "第 2 步" in step:
        problems.append(
            f"「下一步」那张卡停在 {step[:40]!r}——**插件没被这一页认出来**。"
            "多半是端口不在 host_permissions 里（只能是 127.0.0.1:8765），"
            "或者没和假档案馆配对。这是演练的问题，不是产品的——"
            "而它会让下面那些断言变成空转")
    # 这个夹具里抖音是**连着**的，所以这一屏该到第 4 步（同步一次）。
    elif "第 4 步" not in step:
        problems.append(f"有一个已连接的可同步账号时，这张卡该是第 4 步，实际是：{step[:120]!r}")
    # **第二遍：全断开**——他现在就是这个状态，也正是说明书第 3 步描述的那一屏。
    disconnected_step = measured.get("all_disconnected", {}).get("nextStep", "")
    if "undefined" in disconnected_step or "[object" in disconnected_step:
        problems.append(f"那张卡上出现了 undefined/[object：{disconnected_step[:140]!r}"
                        "——他会在屏幕上读到这个词")
    if "第 3 步" not in disconnected_step or "去连接" not in disconnected_step:
        problems.append(
            f"一个账号都没连着时，他照说明书第 3 步该看到的那张卡不对："
            f"{disconnected_step[:140]!r}——说明书写的是"
            "「资料库上会有一张卡片让你『去连接』」")

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
