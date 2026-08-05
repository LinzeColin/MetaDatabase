#!/usr/bin/env python3
"""缓冲区满了之后丢哪一条——**丢错方向就等于什么都没抓到**（v0.0.0.7 / T08）。

## 这条性质为什么要紧

观察器把页面的原始响应抄回来，经 `SA_NET_CAPTURE` 送到后台，缓冲区上限 200 条。
满了之后丢谁，决定了整个产品还能不能用：

  · 收藏列表那个请求是**页面加载时打的**，它永远在最早的那几条里。
  · 后面涌进来的是心跳、埋点、图片信息——噪声。

所以满了要**丢新的、留早的**（`pop()`）。原来写的是 `shift()`，丢最早的，
方向正好反了：专门丢掉唯一有用的那一条，而且**丢得悄无声息**——
用户看到的是「拦到 200 条，0 条读得懂」。

## 为什么非要真跑一遍

这件事此前只写在 background.js 的一段注释里。**注释不是判据**：
把 `pop()` 改回 `shift()`，注释照样在那儿，没有任何东西会红。
（本轮已经栽过四次「判据钉在注释上」，这是第五次同类的坑，只不过还没踩。）

而且它也不能只在 Node 里搭个假对象验——要验的是**真扩展在真 Chrome 里
收到第 201 条消息时的行为**，包括那条消息真的走完了 onMessage 这一路。

## 它怎么验

装进一次性 profile 的真 Chrome，打开扩展自己的设置页（那是另一个扩展上下文，
从它发 `chrome.runtime.sendMessage` 才会触发 service worker 的 onMessage；
**从 service worker 自己发是不会触发自己的**）。连发 205 条可分辨的消息，
然后回 service worker 里读缓冲区：

  · 还剩 200 条（上限守住了）
  · **第一条还在**（最早的留下了）
  · **最后 5 条都不在**（新来的被丢了）
  · 丢弃计数正好是 5（丢了多少条要说得出来，不能悄悄丢）

顺带验空 body 那条：`{ok:false, ignored:true}`，且不占缓冲区。

## 边界

· 一次性 profile，跑完删；不联网、不碰生产、不碰任何真实平台。
· 只验缓冲区这一段。观察器有没有装上、抄得对不对，那是别的演练的事。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import websockets

OVERFLOW = 5          # 比上限多发这么多条
PORT = 9361


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


# 从设置页发。**不能从 service worker 自己发**——MV3 里 sendMessage 不会
# 投递给发送方自己的 onMessage，那样一条都到不了，而结果看起来像「缓冲区是空的」。
SEND = """
(async () => {
  const limit = %d, extra = %d;
  let replies = 0, empties = 0;
  for (let i = 0; i < limit + extra; i++) {
    const r = await chrome.runtime.sendMessage({
      type: "SA_NET_CAPTURE",
      url: "https://example.invalid/req-" + i,
      status: 200,
      body: "BODY-" + i,
      capturedAt: "2026-08-05T00:00:00Z",
    });
    if (r && r.ok) replies++;
  }
  // 空 body 那条：该被忽略，且不占位置
  const empty = await chrome.runtime.sendMessage({
    type: "SA_NET_CAPTURE", url: "https://example.invalid/empty", status: 200, body: "",
  });
  if (empty && empty.ignored) empties++;
  return JSON.stringify({ sent: limit + extra, accepted: replies, emptyIgnored: empties });
})()
"""

READ = """
(() => {
  const bodies = netCaptureBuffer.map(item => item.body);
  return JSON.stringify({
    limit: NET_CAPTURE_LIMIT,
    length: netCaptureBuffer.length,
    first: bodies[0] || null,
    last: bodies[bodies.length - 1] || null,
    dropped: netCapturesDropped,
    hasEmptyUrl: netCaptureBuffer.some(i => (i.url || "").endsWith("/empty")),
  });
})()
"""


async def run(chrome: str, ext_dir: str) -> int:
    profile = Path(tempfile.mkdtemp(prefix="sa-buffer-profile-"))
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={PORT}",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{PORT}"
    sent: dict = {}
    measured: dict = {}
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
            await rpc("Target.createTarget",
                      {"url": f"chrome-extension://{extension_id}/options.html"})
        await asyncio.sleep(3)

        def find(kind: str, needle: str):
            targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
            hits = [t for t in targets if t["type"] == kind and needle in t["url"]]
            return hits[0] if hits else None

        page = find("page", "options.html")
        if not page:
            print(json.dumps({"status": "FAIL", "error_code": "OPTIONS_PAGE_NOT_OPEN"},
                             ensure_ascii=False))
            return 4
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            result = await rpc("Runtime.evaluate",
                               {"expression": SEND % (200, OVERFLOW),
                                "returnByValue": True, "awaitPromise": True})
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                print(json.dumps({"status": "FAIL", "error_code": "SEND_THREW",
                                  "detail": str(payload["exceptionDetails"])[:300]},
                                 ensure_ascii=False))
                return 4
            sent = json.loads(payload["result"]["value"])

        worker = find("service_worker", extension_id)
        if not worker:
            print(json.dumps({"status": "FAIL", "error_code": "SERVICE_WORKER_ASLEEP"},
                             ensure_ascii=False))
            return 4
        async with websockets.connect(worker["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            result = await rpc("Runtime.evaluate", {"expression": READ, "returnByValue": True})
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                print(json.dumps({"status": "FAIL", "error_code": "READ_THREW",
                                  "detail": str(payload["exceptionDetails"])[:300]},
                                 ensure_ascii=False))
                return 4
            measured = json.loads(payload["result"]["value"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    limit = measured.get("limit")
    problems: list[str] = []
    if not sent.get("accepted"):
        # **一条都没到的话，下面每一条结论都不算数。**
        problems.append("**一条 SA_NET_CAPTURE 都没被后台收下**——这时候「缓冲区是对的」什么也不证明")
    if measured.get("length") != limit:
        problems.append(f"缓冲区没停在上限：{measured.get('length')} ≠ {limit}")
    if measured.get("first") != "BODY-0":
        problems.append(
            f"**最早的那条不见了**（现在第一条是 {measured.get('first')}）——"
            "收藏列表那个请求永远在最早的几条里，丢它等于「拦到 200 条，0 条读得懂」")
    newest = f"BODY-{limit + OVERFLOW - 1}" if isinstance(limit, int) else None
    if measured.get("last") == newest:
        problems.append(f"**最新的那条留下来了**（{newest}）——方向反了，丢的是早的")
    if measured.get("dropped") != OVERFLOW:
        problems.append(
            f"丢弃计数不对：{measured.get('dropped')} ≠ {OVERFLOW}——"
            "**丢了多少要说得出来**，悄悄丢正是这条缺陷当初的样子")
    if not sent.get("emptyIgnored"):
        problems.append("空 body 没被忽略")
    if measured.get("hasEmptyUrl"):
        problems.append("空 body 那条占了缓冲区位置")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "sent": sent,
        "buffer": measured,
        "problems": problems,
        "what_this_does_not_prove": (
            "只验缓冲区满了之后丢哪一条。观察器有没有装上、抄回来的内容对不对，"
            "那是 T08 别的演练的事。"
        ),
    }, ensure_ascii=False))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验缓冲区满了之后丢的是新的、留的是早的")
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
