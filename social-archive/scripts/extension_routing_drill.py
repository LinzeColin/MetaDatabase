#!/usr/bin/env python3
"""在真 Chrome 里验一次扩展的同步分流（v0.0.0.7 / T14）。

## 为什么这件事只能在真浏览器里验

判据能钉住**文本顺序**（守卫写在导航之前、先问能不能再问谁来干），
钉不住运行时到底走了哪条路。这一天里正是这个差别吃过两次亏：

  · 「藏了按钮」的判据全绿，而队列每分钟照样抢用户的标签页
  · 静态判据说 x 的守卫在导航之前，而实测 x 一次抢了 2 下标签页

所以这个演练测的是**计数**：三条出口各被走了几次，
`chrome.tabs.update` 被碰了几次。

## 它验什么

  1. Chrome 书签仍然直达 syncChromeBookmarks，**一个标签页都不碰**
     ——那是唯一真能用的一条路，改分流最怕把它带坏
  2. 服务端说同步不了的平台被当场拒绝，**不掉进服务端那条同样干不成的路**
     ——证明「先问能不能同步、再问谁来干」的顺序生效

## 怎么用

    # 先起一个一次性 profile 的 Chrome（绝不碰 Owner 的 profile）
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
      --user-data-dir=/tmp/sa-routing-profile --remote-debugging-port=9343 \\
      --no-first-run --disable-sync --disable-background-networking \\
      --no-service-autorun --password-store=basic --use-mock-keychain about:blank &

    python3 scripts/extension_routing_drill.py --ext-dir <解压好的扩展目录>

## 边界

· 只替换 service worker 里的三条出口做计数，**不真的同步任何东西**。
· 不联网：/v1/accounts 被替换成一个固定的能力表。
· 跑完什么都不改——扩展、生产、Owner 的 profile 一律不碰。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
import time
import sys
import urllib.request
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from drill_extension_dir import resolve_ext_dir  # noqa: E402

PROBE = r"""
(async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    items: [
      { id: "acc_web", platform: "generic-web", external_account_id: "chrome-bookmarks", connection_state: "connected" },
      { id: "acc_x",   platform: "x",           external_account_id: "someone",          connection_state: "connected" }
    ],
    supported_platforms: [
      { platform: "generic-web", sync_supported: true,  server_handled: false },
      { platform: "x",           sync_supported: false, server_handled: true  }
    ],
  }), { status: 200, headers: { "Content-Type": "application/json" } });

  const calls = { bookmarks: 0, server: 0, browser: 0, tabs: 0 };
  const realBookmarks = syncChromeBookmarks;
  const realServer = startServerSideSync;
  const realBrowser = runBrowserAccountSync;
  const realUpdate = chrome.tabs.update;
  syncChromeBookmarks = async () => { calls.bookmarks += 1; return { ok: true, state: "queued" }; };
  startServerSideSync = async () => { calls.server += 1; return { ok: true, state: "queued" }; };
  runBrowserAccountSync = async () => { calls.browser += 1; return { ok: true }; };
  chrome.tabs.update = async (...a) => { calls.tabs += 1; return realUpdate.apply(chrome.tabs, a); };

  let webError = null, blockedError = null;
  try { await syncAccountById("acc_web", { triggerType: "manual" }); } catch (e) { webError = e && e.message; }
  const afterBookmarks = { ...calls };
  try { await syncAccountById("acc_x", { triggerType: "manual" }); } catch (e) { blockedError = e && e.message; }

  syncChromeBookmarks = realBookmarks; startServerSideSync = realServer;
  runBrowserAccountSync = realBrowser; chrome.tabs.update = realUpdate; globalThis.fetch = realFetch;
  return JSON.stringify({ afterBookmarks, total: calls, webError, blockedError });
})()
"""


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


async def run(base: str, ext_dir: str) -> int:
    version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=5).read())
    async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await _rpc_factory(ws)
        loaded = await rpc("Extensions.loadUnpacked", {"path": ext_dir})
        if "error" in loaded:
            print(json.dumps({"status": "FAIL", "error_code": "LOAD_UNPACKED_FAILED",
                              "detail": loaded["error"]}, ensure_ascii=False))
            return 4
        extension_id = loaded["result"]["id"]

    await asyncio.sleep(3)
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    workers = [t for t in targets if t["type"] == "service_worker" and extension_id in t["url"]]
    if not workers:
        print(json.dumps({"status": "FAIL", "error_code": "SERVICE_WORKER_ASLEEP",
                          "message": "service worker 没起来——先打开一次扩展页把它叫醒"}, ensure_ascii=False))
        return 4

    async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await _rpc_factory(ws)
        await rpc("Runtime.enable")
        result = await rpc("Runtime.evaluate",
                           {"expression": PROBE, "awaitPromise": True, "returnByValue": True})
        payload = result.get("result", {})
        if payload.get("exceptionDetails"):
            print(json.dumps({"status": "FAIL", "error_code": "PROBE_THREW",
                              "detail": str(payload["exceptionDetails"])[:400]}, ensure_ascii=False))
            return 4
        measured = json.loads(payload["result"]["value"])

    problems = []
    after = measured["afterBookmarks"]
    if after != {"bookmarks": 1, "server": 0, "browser": 0, "tabs": 0}:
        problems.append(f"Chrome 书签没有直达书签路，或碰了标签页：{after}")
    if measured["webError"]:
        problems.append(f"Chrome 书签那条路抛了：{measured['webError']}")
    if not measured["blockedError"]:
        problems.append("同步不了的平台**没有被拒绝**")
    total = measured["total"]
    if total["server"] or total["browser"] or total["tabs"]:
        problems.append(f"同步不了的平台掉进了别的路：{total}")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "extension_id": extension_id,
        "after_bookmarks": after,
        "total_calls": total,
        "blocked_message": measured["blockedError"],
        "problems": problems,
    }, ensure_ascii=False))
    return 0 if not problems else 4


def _reachable(base: str) -> bool:
    try:
        urllib.request.urlopen(base + "/json/version", timeout=2).read()
        return True
    except Exception:                                       # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="在真 Chrome 里验一次扩展的同步分流")
    parser.add_argument("--ext-dir", default=None,
                        help="解压好的扩展目录；不给就用 dist 里的发布包")
    parser.add_argument("--cdp", default="http://127.0.0.1:9343")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    # 没给 --ext-dir 就用发布包：要先打包再解压才跑得动的演练，
    # 就是没人跑的演练；默认用发布包还顺带让它验的是他真正下载的那一份。
    args.ext_dir = resolve_ext_dir(args.ext_dir)
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING",
                          "detail": args.ext_dir}, ensure_ascii=False))
        return 2
    base = args.cdp.rstrip("/")
    # **自己起 Chrome。**
    #
    # 这个演练原来要求你先手工开一个带 --remote-debugging-port 的浏览器，
    # 否则只会抛一句 `URLError: Connection refused`——看起来像它坏了。
    # 而 DRILLS.md 把它归在「改到那条路时」跑，也就是说**跑不起来的那一刻
    # 正是没人再管它的那一刻**。这个仓刚查过一遍：15 个演练，调用方 0。
    # 跑不起来的演练和没有演练是一回事。
    process = None
    workspace = None
    if not _reachable(base):
        port = base.rsplit(":", 1)[-1]
        workspace = tempfile.mkdtemp(prefix="sa-routing-")
        process = subprocess.Popen(
            [args.chrome, f"--user-data-dir={workspace}/profile",
             f"--remote-debugging-port={port}", "--no-first-run",
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
             "--no-default-browser-check", "--disable-sync",
             "--disable-background-networking", "--password-store=basic",
             "--use-mock-keychain", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if _reachable(base):
                break
            time.sleep(0.5)
        else:
            process.terminate()
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP",
                              "detail": f"起不来，也连不上 {base}"}, ensure_ascii=False))
            return 2
    try:
        return asyncio.run(run(base, str(Path(args.ext_dir).resolve())))
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        if workspace:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
