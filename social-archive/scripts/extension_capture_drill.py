#!/usr/bin/env python3
"""在真 Chrome 里把「拦截 → 读懂」整条链走一遍（v0.0.0.7 / T08）。

## 为什么非做不可

Owner 只需要动一次手：装好插件，打开收藏夹页，点一下诊断。
那一下背后是这么一条链——

    刷新页面 → 注入中继(ISOLATED) → 注入观察器(MAIN) → 下发前缀
      → 页面自己发请求 → 观察器抄走响应 → 中继转回 background
      → 缓冲区 → 服务端解析成条目

**这条链一次都没有整条跑过。** 每一环单独验过：解析器有判据，
服务端接口打得通，插件装得上、三个全局都在。但「每一环都对」
和「串起来能出条目」是两件事——这个项目今天已经在这个差别上栽过两次
（藏了按钮而队列照抢标签页；静态判据说守卫在导航之前而实测抢了 2 下）。

如果链是断的，Owner 点完那一下什么也拿不到，**而他那一下已经用掉了**。

## 为什么不去真站点

去不了，也不该去。所以在**回环地址**上重建同一条链：
本地起一个假收藏夹页 + 假接口，返回真实形状的响应体，
拿**生产同一个解析器**去读抓回来的字节。

用 127.0.0.1:8765 是因为插件在装的时候就拿到了这个域的权限
（manifest 的 host_permissions 里写着），不需要任何人点授权框。

## 它证明什么、不证明什么

证明：注入进得去、两个世界的消息通得了、**相对地址抓得到**、
      抓回来的字节**生产解析器读得懂并能数出条目**。
不证明：B 站真实响应就是这个形状（形状取自 2026-08-04 那次真实抓包的记录），
      也不证明 Owner 机器上的权限/策略与这里相同。

## 边界

· 全程不联网、不碰生产、不碰 Owner 的 profile（一次性 profile，跑完删）。
· 反例先行：换一个绝对匹配不上的前缀，必须抓到 0 条。
  抓不到 0 条说明这个演练**根本不是在量它自称在量的东西**。
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
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_archive.platform_payloads import parse_bilibili_favlist  # noqa: E402

PORT = 8765
FAV_PATH = "/x/v3/fav/resource/list"

# 形状取自 2026-08-04 那次真实抓包记录：code/message/ttl/data.medias，
# 条目上带 id/title/bvid/type/intro/cover/upper。**不要凭印象改这个形状**——
# 它是解析器判据的同一份底。
FAKE_FAVLIST = {
    "code": 0,
    "message": "0",
    "ttl": 1,
    "data": {
        "info": {"id": 1, "title": "演练用收藏夹", "media_count": 2},
        "medias": [
            {"id": 111, "bvid": "BV1drill001", "type": 2, "title": "回环演练条目一",
             "intro": "这条只存在于本机", "cover": "http://127.0.0.1/1.jpg",
             "upper": {"name": "演练"}, "pubtime": 1700000000},
            {"id": 222, "bvid": "BV1drill002", "type": 2, "title": "回环演练条目二",
             "intro": "", "cover": "http://127.0.0.1/2.jpg",
             "upper": {"name": "演练"}, "pubtime": 1700000001},
        ],
        "has_more": False,
    },
}

# 页面故意用两种写法各发一次：
#   相对地址  —— 平台调自己接口的常规写法，也是 absolute() 那个补丁要保的路
#   绝对地址  —— 补丁之前唯一能匹配上的写法，用来对照
PAGE = f"""<!doctype html><meta charset="utf-8"><title>回环演练收藏夹</title>
<body><p>这个页面只发请求，不做别的。</p><script>
setInterval(() => {{
  fetch("{FAV_PATH}?rel=1&pn=1").then(r => r.json()).catch(() => {{}});
  fetch("http://127.0.0.1:{PORT}{FAV_PATH}?abs=1&pn=1").then(r => r.json()).catch(() => {{}});
}}, 700);
</script></body>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith(FAV_PATH):
            body = json.dumps(FAKE_FAVLIST, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            body = PAGE.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:      # 别把演练日志刷满终端
        return


PROBE = r"""
(async (config) => {
  const tabs = await chrome.tabs.query({ url: config.pageUrl + "*" });
  if (!tabs.length) return JSON.stringify({ error: "没有找到演练页面的标签页" });
  const tabId = tabs[0].id;

  // 与诊断按钮走**完全相同**的顺序：刷新 → 中继 → 观察器 → 下发前缀。
  // 顺序是这条链最脆的地方（先装观察器会丢掉 INSTALLED），所以照抄，不简化。
  observerStateByTab.delete(tabId);
  netCaptureBuffer.length = 0;
  await chrome.tabs.reload(tabId);
  await new Promise(r => setTimeout(r, 1500));
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content/net-relay.js"] });
  await chrome.scripting.executeScript({ target: { tabId }, world: "MAIN", files: ["net-observer.js"] });
  await chrome.tabs.sendMessage(tabId, { type: "SA_OBSERVER_CONFIGURE", urlPrefixes: config.prefixes });

  await new Promise(r => setTimeout(r, 3500));
  const captures = netCaptureBuffer.map(c => ({ url: c.url, status: c.status, body: c.body }));
  const selfReport = observerStateByTab.get(tabId) || null;
  netCaptureBuffer.length = 0;
  return JSON.stringify({ captures, selfReport, tabId });
})(%s)
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


async def _evaluate(base: str, extension_id: str, expression: str):
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    workers = [t for t in targets if t["type"] == "service_worker" and extension_id in t["url"]]
    if not workers:
        return {"error": "service worker 没起来"}
    async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await _rpc_factory(ws)
        await rpc("Runtime.enable")
        result = await rpc("Runtime.evaluate",
                           {"expression": expression, "awaitPromise": True, "returnByValue": True})
        payload = result.get("result", {})
        if payload.get("exceptionDetails"):
            return {"error": str(payload["exceptionDetails"])[:400]}
        return json.loads(payload["result"]["value"])


async def run(chrome_binary: str, ext_dir: str, keep_going: bool) -> int:
    page_url = f"http://127.0.0.1:{PORT}/favlist"
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = Path(tempfile.mkdtemp(prefix="sa-capture-profile-"))
    process = subprocess.Popen(
        [chrome_binary, f"--user-data-dir={profile}", "--remote-debugging-port=9344",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", page_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = "http://127.0.0.1:9344"
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001 —— 等它起来，不关心具体是哪种连不上
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 4

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": ext_dir})
            if "error" in loaded:
                print(json.dumps({"status": "FAIL", "error_code": "LOAD_UNPACKED_FAILED",
                                  "detail": loaded["error"]}, ensure_ascii=False))
                return 4
            extension_id = loaded["result"]["id"]
        await asyncio.sleep(3)

        def probe(prefixes):
            return PROBE % json.dumps({"pageUrl": page_url, "prefixes": prefixes})

        real = await _evaluate(base, extension_id, probe([FAV_PATH]))
        # **反例先行**：换一个绝不会出现的前缀，必须抓到 0 条。
        # 抓不到 0 条 = 这个演练量的不是它自称在量的东西。
        counter = await _evaluate(base, extension_id, probe(["/绝不会出现的接口路径"]))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    problems: list[str] = []
    for name, measured in (("正例", real), ("反例", counter)):
        if measured.get("error"):
            problems.append(f"{name}探针出错：{measured['error']}")
    if problems:
        print(json.dumps({"status": "FAIL", "problems": problems}, ensure_ascii=False))
        return 4

    captures = real.get("captures") or []
    report = real.get("selfReport") or {}
    if not report.get("installed") or not report.get("ready"):
        problems.append(f"观察器自报没装好或没就绪：{report}")
    if report.get("prefixCount") != 1:
        problems.append(f"下发的前缀条数没到观察器手里：{report}")
    if not captures:
        problems.append("整条链一条都没抓到——这正是 Owner 会遇到的那种「点完什么也没有」")

    relative = [c for c in captures if "rel=1" in c["url"]]
    absolute = [c for c in captures if "abs=1" in c["url"]]
    if not relative:
        problems.append("**相对地址一条都没抓到**——absolute() 那个补丁没生效，"
                        "而相对地址正是平台调自己接口的常规写法")
    if not absolute:
        problems.append("绝对地址一条都没抓到")

    # 「拦到了」和「读得懂」是两件事：拿生产同一个解析器去读抓回来的字节。
    parsed_items = 0
    parse_error = None
    if captures:
        try:
            # 解析器返回的是 `(条目, 还有下一页)` 两元组。
            # **这里差点写成 len(整个返回值)** —— 那永远等于 2，
            # 而 2 正是这次期望的条目数：条目为空也会绿。必须先解包。
            items, _has_more = parse_bilibili_favlist(captures[0]["body"])
            parsed_items = len(items)
        except Exception as exc:                    # noqa: BLE001 —— 什么原因读不懂都要如实报出来
            parse_error = f"{type(exc).__name__}: {exc}"
    if parse_error:
        problems.append(f"抓到了却读不懂：{parse_error}")
    elif captures and parsed_items != 2:
        problems.append(f"读出来的条目数不对：{parsed_items}，应为 2")

    if counter.get("captures"):
        problems.append(
            f"反例也抓到了 {len(counter['captures'])} 条——"
            "这个演练根本不是在量前缀匹配，它测不出真问题"
        )

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "extension_id": extension_id,
        "observer_self_report": report,
        "captured": len(captures),
        "captured_relative_url": len(relative),
        "captured_absolute_url": len(absolute),
        "parsed_items_from_first_capture": parsed_items,
        "counter_example_captured": len(counter.get("captures") or []),
        "problems": problems,
    }, ensure_ascii=False))
    return 0 if not problems or keep_going else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="在真 Chrome 里走一遍拦截→读懂整条链")
    parser.add_argument("--ext-dir", required=True, help="解压好的扩展目录")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--report-only", action="store_true",
                        help="照常输出但不用退出码判失败（排查时用）")
    args = parser.parse_args()
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING",
                          "detail": args.ext_dir}, ensure_ascii=False))
        return 2
    if not Path(args.chrome).exists():
        print(json.dumps({"status": "FAIL", "error_code": "CHROME_MISSING",
                          "detail": args.chrome}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, str(Path(args.ext_dir).resolve()), args.report_only))


if __name__ == "__main__":
    sys.exit(main())
