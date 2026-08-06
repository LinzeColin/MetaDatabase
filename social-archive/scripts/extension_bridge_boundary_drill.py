#!/usr/bin/env python3
"""档案馆页面能给扩展令牌，**但不能改它往哪儿发**（v0.0.0.7 / T03）。

## 这条边界是什么

配对走的是「零门槛」那条路：已登录的档案馆页面用自己的会话换一个长期令牌，
通过 bridge 直接交给扩展，用户一个字符都不用输入。

代价是**页面能对扩展说话**。background.js 里那条规则写得很清楚：

    服务地址取扩展自己的托管配置，不接受页面下发——
    页面能改端点就等于任何拿到桥的页面都能把上行改到别处去。

而 bridge.js 里记着：原先真有一条 `SA_CONFIGURE → SA_WEB_BRIDGE_CONFIGURE`
的转发在做那件事，**已整条删除**。删的理由不是没人用，是它和上面那条规则冲突。

## 为什么要真跑一遍

判据里此前只有一句源码断言：「PWA 里有 postToExtension("SA_ADOPT_TOKEN"」。
**没有任何东西验过「页面塞一个 endpoint 进来会怎样」。**
而这正是那条被删掉的转发曾经打开的口子——源码删干净了，
不等于同一件事换个字段名做不到。

## 它怎么验

假档案馆页面（127.0.0.1:8765，manifest 里就写着这个源）向扩展发一条
`SA_ADOPT_TOKEN`，**同时夹带一个指向别处的 endpoint**。然后回头问扩展：

  · 令牌收了吗？          —— 该收（零门槛那条路要能走通）
  · 端点被改了吗？        —— **绝不能改**

## 边界

· 一次性 profile，跑完删；只连 127.0.0.1；不碰生产、不碰任何真实平台。
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
HONEST_ENDPOINT = f"http://127.0.0.1:{PORT}"
# 页面会试图把上行改到这里。**它必须失败。**
ATTACKER_ENDPOINT = "http://127.0.0.1:9999"

# 同源的那个地址：真档案馆页面发的就长这样，**必须收**。
SAME_ORIGIN_LIBRARY = f"{HONEST_ENDPOINT}/library"

PAGE_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><title>假档案馆</title></head>
<body><script>
  // 档案馆页面替扩展取到令牌之后就是这么交过去的（见 apps/pwa/app.js）。
  window.postMessage({
    source: "social-archive-web",
    type: "SA_ADOPT_TOKEN",
    token: "fixture-token-from-page",
    endpoint: "__LIB__",
    libraryUrl: "__LIB__"
  }, location.origin);
</script></body></html>"""

# 两个用例都要跑：
#   · 异源  —— **必须退回扩展自己那份**（这条是边界）
#   · 同源  —— **必须收下**（少了这条，把 libraryUrl 整个忽略掉也能过，
#              那是把边界修成了「功能没了」）
CASES = (("cross_origin", ATTACKER_ENDPOINT, False),
         ("same_origin", SAME_ORIGIN_LIBRARY, True))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        return

    offered = ATTACKER_ENDPOINT      # 由 run() 在每个用例前改写

    def do_GET(self) -> None:  # noqa: N802
        body = PAGE_TEMPLATE.replace("__LIB__", _Handler.offered).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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


SEED = """
(async () => {
  await chrome.storage.local.set({ endpoint: "%s", token: "" });
  const c = await SA.getConfig();
  return JSON.stringify({ endpoint: c.endpoint, token: c.token });
})()
""" % HONEST_ENDPOINT

READ = """
(async () => {
  const c = await SA.getConfig();
  return JSON.stringify({ endpoint: c.endpoint, tokenLen: (c.token || "").length,
                          libraryUrl: c.libraryUrl || "" });
})()
"""


async def run_case(chrome: str, ext_dir: str, offered: str) -> dict:
    _Handler.offered = offered
    profile = Path(tempfile.mkdtemp(prefix="sa-bridge-profile-"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", "--remote-debugging-port=9357",
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9357"
    before = after = None
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

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": ext_dir})
            if "error" in loaded:
                print(json.dumps({"status": "FAIL", "error_code": "LOAD_UNPACKED_FAILED"},
                                 ensure_ascii=False))
                return 4
            extension_id = loaded["result"]["id"]
        await asyncio.sleep(2.5)

        def worker():
            targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
            found = [t for t in targets if t["type"] == "service_worker" and extension_id in t["url"]]
            return found[0] if found else None

        target = worker()
        if not target:
            print(json.dumps({"status": "FAIL", "error_code": "SERVICE_WORKER_ASLEEP"},
                             ensure_ascii=False))
            return 4
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            seeded = await rpc("Runtime.evaluate",
                               {"expression": SEED, "returnByValue": True, "awaitPromise": True})
            before = json.loads(seeded["result"]["result"]["value"])

        # 现在打开那个页面——它一加载就会朝扩展喊话
        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Target.createTarget", {"url": f"http://127.0.0.1:{PORT}/"})
        await asyncio.sleep(3)

        target = worker()
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            read = await rpc("Runtime.evaluate",
                             {"expression": READ, "returnByValue": True, "awaitPromise": True})
            after = json.loads(read["result"]["result"]["value"])
    finally:
        server.shutdown()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    return {"before": before, "after": after}


def main() -> int:
    parser = argparse.ArgumentParser(description="验档案馆页面改不动扩展的服务地址")
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
    ext = str(Path(args.ext_dir).resolve())

    problems: list[str] = []
    measured: dict = {}
    for name, offered, should_accept in CASES:
        result = asyncio.run(run_case(args.chrome, ext, offered))
        after = result.get("after") or {}
        measured[name] = {"offered": offered, "endpoint_after": after.get("endpoint"),
                          "library_after": after.get("libraryUrl"),
                          "token_adopted": bool(after.get("tokenLen"))}
        # **端点那条永远不能松。**
        if after.get("endpoint") != HONEST_ENDPOINT:
            problems.append(
                f"[{name}] **页面改掉了扩展的服务地址**："
                f"{HONEST_ENDPOINT} → {after.get('endpoint')}")
        # 零门槛那条路本身要走得通，否则「没被改」证明不了任何事。
        if not after.get("tokenLen"):
            problems.append(f"[{name}] **令牌没被采纳**——配对路没走通，这时候别的结论都不算数")
        if should_accept and after.get("libraryUrl") != offered:
            problems.append(
                f"[{name}] 同源的 libraryUrl 被拒了（{after.get('libraryUrl')}）——"
                "**边界修成了「功能没了」**：真档案馆页面发的就是同源地址")
        if not should_accept and after.get("libraryUrl") == offered:
            problems.append(
                f"[{name}] **异源的 libraryUrl 被收下了**：{offered}。"
                "「打开档案馆」那颗按钮会把用户送到别人那儿。")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "cases": measured,
        "problems": problems,
        "what_this_does_not_prove": (
            "只验了「页面能不能改端点 / 改档案馆地址」这两条。桥还能收别的消息，"
            "那些没在这里验。"
        ),
    }, ensure_ascii=False))
    return 0 if not problems else 4


def _unused_main() -> int:

    parser = argparse.ArgumentParser(description="验档案馆页面改不动扩展的服务地址")
    parser.add_argument("--ext-dir", default=None,
                        help="解压好的扩展目录；不给就用 dist 里的发布包")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING"}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, str(Path(args.ext_dir).resolve())))


if __name__ == "__main__":
    sys.exit(main())
