#!/usr/bin/env python3
"""Owner 按下那颗诊断按钮之后，两件最容易骗人的事（v0.0.0.7 / T08）。

一是**缓冲区满了丢哪一条**——丢错方向就等于什么都没抓到；
二是**那一按到底存没存**——读懂了不等于进了档案馆。
两件事失败的样子都一样：界面报着好看的数字，实际什么也没有。

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

## 第二段：那一按到底存没存

`/v1/extension/captures/parse` **只把响应读成条目，不落库**——回来的 items
在后台只被数了个数（`items += …length`），条目本身丢掉了。
而报给用户的原话曾经是「共 60 条收藏。」：他按了一下、看到自己的收藏被认出来，
合理的理解就是「进去了」。**然后资料库里一条都没有。**

这不是 bug，是这条路的本分——诊断按钮的目的是**找出该盯哪个地址**，
让它真的入库是 T10（还差一条非诊断的安装路）。但**话要说准**。

所以起一个假档案馆，让 parse 一律回「读懂了 2 条」，然后按一次，断言：

  · `imported` 是 0（这条路本来就不入库，报成别的数就是又一次「看着像存了」）
  · 那句话里**必须出现「还没有进」**——只报「共 60 条收藏」就是在骗人

## 边界

· 一次性 profile，跑完删；不联网、不碰生产、不碰任何真实平台。
· 假档案馆不解析真实字节，它只负责「回一个成功的形状」。
  这里验的是**后台怎么向用户转述**，不是解析器对不对。
· 观察器有没有装上、抄得对不对，那是别的演练的事。
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

OVERFLOW = 5          # 比上限多发这么多条
PORT = 9361
API_PORT = 8765       # 假档案馆：扩展装好就有这个域的权限

# 「读懂了」和「存下来了」是两件事。假服务端一律回「读懂了两条」，
# 于是那一按会报「共 60 条收藏」——**而它一条都没存**。要验的就是它有没有说这句实话。
PARSE_REPLY = {
    "ok": True, "platform": "bilibili", "failure_code": None,
    "message_zh": "读懂了 2 条。", "has_more": False,
    "items": [{"external_id": "a", "title": "条目一", "url": "https://example.invalid/a"},
              {"external_id": "b", "title": "条目二", "url": "https://example.invalid/b"}],
}


class _Api(BaseHTTPRequestHandler):
    """只回一个端点：把抓到的响应「读成条目」。**它不落库，真服务端也不落。**"""

    def log_message(self, *args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        body = json.dumps(PARSE_REPLY, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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


# 从设置页发。**不能从 service worker 自己发**——MV3 里 sendMessage 不会
# 投递给发送方自己的 onMessage，那样一条都到不了，而结果看起来像「缓冲区是空的」。
CONFIGURE = """
(async () => {
  await chrome.storage.local.set({ endpoint: "http://127.0.0.1:%d", token: "fixture-token" });
  const c = await SA.getConfig();
  return JSON.stringify({ endpoint: c.endpoint, hasToken: !!c.token });
})()
""" % API_PORT

PARSE = """
(async () => {
  const r = await chrome.runtime.sendMessage({ type: "SA_PARSE_NET_CAPTURES", platform: "bilibili" });
  return JSON.stringify(r || {});
})()
"""

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
    api = ThreadingHTTPServer(("127.0.0.1", API_PORT), _Api)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={PORT}",
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{PORT}"
    sent: dict = {}
    measured: dict = {}
    parsed: dict = {}
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

        worker = find("service_worker", extension_id)
        if worker:
            async with websockets.connect(worker["webSocketDebuggerUrl"], max_size=None) as ws:
                rpc = await _rpc_factory(ws)
                await rpc("Runtime.enable")
                await rpc("Runtime.evaluate",
                          {"expression": CONFIGURE, "returnByValue": True, "awaitPromise": True})

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

        # **第二段：那一按到底有没有把东西存下来。**
        page = find("page", "options.html")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            result = await rpc("Runtime.evaluate",
                               {"expression": PARSE, "returnByValue": True, "awaitPromise": True})
            payload = result.get("result", {})
            if not payload.get("exceptionDetails"):
                parsed = json.loads(payload["result"]["value"])
    finally:
        api.shutdown()
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

    # ---- 那一按到底存没存 ----
    #
    # /v1/extension/captures/parse **只把响应读成条目，不落库**。回来的 items
    # 在后台只被数了个数，条目本身丢掉了。而报给用户的原话是「共 N 条收藏。」——
    # 他按了一下、看到自己的收藏被认出来了，合理的理解就是「进去了」。
    # **然后资料库里一条都没有。** 这一段验的就是它有没有把这句实话说出来。
    said = str(parsed.get("message_zh") or "")
    if not parsed:
        problems.append("**SA_PARSE_NET_CAPTURES 没回话**——存没存这一段什么都没验到")
    elif not parsed.get("items"):
        problems.append(f"假服务端回了条目，后台却报 0 条：{said[:80]}")
    else:
        if parsed.get("imported") != 0:
            problems.append(
                f"imported 不是 0（{parsed.get('imported')}）——"
                "**这条路本来就不入库**，报成别的数就是又一次「看着像存了」")
        if "还没有进" not in said:
            problems.append(
                f"**它说了「共 {parsed.get('items')} 条收藏」却没说这些东西还没进档案馆**："
                f"{said[:110]}")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "sent": sent,
        "buffer": measured,
        "that_one_press": {"items": parsed.get("items"), "imported": parsed.get("imported"),
                           "message_zh": (parsed.get("message_zh") or "")[:160]},
        "problems": problems,
        "what_this_does_not_prove": (
            "验两件事：缓冲区满了丢哪一条、那一按怎么向用户转述。"
            "**不验解析对不对**（假档案馆只回一个成功的形状），"
            "也不验观察器有没有按时装上——那是 T08 别的演练的事。"
        ),
    }, ensure_ascii=False))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验缓冲区满了之后丢的是新的、留的是早的")
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
