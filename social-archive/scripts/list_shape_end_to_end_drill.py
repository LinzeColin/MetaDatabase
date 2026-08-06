#!/usr/bin/env python3
"""不知道接口地址，也能从页面自己发的响应里把收藏读出来（v0.0.0.21）。

## 它验的是哪一条

小红书 / 抖音 / 快手的主路径是「扩展读取页面和列表」。它们的接口带签名，
所以**不去调**——只看页面自己发出的响应（签名由页面自己做，我们不碰）。

挡住这条路的一直是「要先知道那个请求的 URL 前缀」，而正当来源被定义成
**Owner 去收藏页按一次诊断按钮**。他说过「不要让我和你重复地反攻」。

现在改成：观察器不带前缀装上（只收本域），收下之后按**形状**认出哪个是列表。
这个演练验的就是这一整条在真浏览器里通不通。

## 怎么在没有真账号的情况下验

和 B 站那个演练同一招：`--host-resolver-rules` 把 `*.xiaohongshu.com`
指到本机的假站上。假站的收藏页会像真页面那样，**在加载时打好几个 XHR**：

    /api/log          埋点
    /api/config       配置
    /api/user         用户信息
    /api/homefeed     推荐流（**有数组、长度也够，但元素带不出 id**——最容易误认的那个）
    /api/collect/page 真正的收藏列表

扩展一行代码都不用改，它以为对面是小红书。

## 它不证明什么

**不证明真小红书的响应长这样。** 那要 Owner 自己的登录态，只能发生在他的浏览器里。
这里证明的是：不知道地址也能装上观察器、能收到页面自己的响应、
能从一堆噪声里认出列表、能把它变成可入库的条目——
而且**认错推荐流这件事不会发生**（那才是最贵的错：把首页推荐当成他的收藏）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import websockets

ROOT = Path(__file__).resolve().parents[1]
EXT_SRC = ROOT / "apps/browser-extension"
FAKE_PORT = 8443
DEBUG_PORT = 9379

NOTES = [{"note_id": f"n{i}", "display_title": f"第 {i} 条收藏",
          "user": {"nickname": f"作者{i}"}, "create_time": 1700000000 + i}
         for i in range(1, 8)]

# 收藏页加载时会打的那几个请求。**噪声必须真实**——
# 只放一个真列表的话，这个演练证明不了「不会认错」。
ROUTES = {
    "/api/log": {"ok": 1},
    "/api/config": {"flags": {"a": 1, "b": 2, "c": 3, "d": 4}},
    "/api/user": {"user": {"id": 1, "nickname": "我"}},
    # 推荐流：有数组、长度够，但元素带不出 id
    "/api/homefeed": {"data": [{"banner": f"b{i}", "img": f"u{i}"} for i in range(6)]},
    "/api/collect/page": {"data": {"notes": NOTES}},
}

PAGE = """<!doctype html><meta charset=utf-8><title>收藏</title>
<h1>我的收藏</h1>
<script>
// 像真收藏页那样打好几个请求。
// **两批**：一批在解析时就发（埋点常这样），一批在"水合"之后发——
// 真实的 SPA（小红书/抖音/快手都是）列表请求属于后者。
// 两批都放，才验得出观察器到底赶得上哪一批。
["/api/log"].forEach(p => fetch(p).then(r => r.json()).catch(() => {}));
setTimeout(() => {
  ["/api/config","/api/user","/api/homefeed","/api/collect/page"]
    .forEach(p => fetch(p).then(r => r.json()).catch(() => {}));
}, 400);
</script>"""


class _Fake(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ROUTES:
            body = json.dumps(ROUTES[path], ensure_ascii=False).encode()
            kind = "application/json"
        else:
            body = PAGE.encode()
            kind = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)



FAKE_API_PORT = 8765
received: dict = {"accounts": [], "batches": [], "runs": {}}


class _Api(BaseHTTPRequestHandler):
    """假档案馆。只实现「连接账号 → 建账号 → 收批次」这条链用得到的。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        return

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"status": "ok", "version": "0.0.0.21"})
        elif path == "/v1/accounts":
            self._json(200, {"items": received["accounts"], "supported_platforms": [
                {"platform": "xiaohongshu", "relations": ["favorite"],
                 "sync_supported": True, "not_syncable_reason": "",
                 "server_handled": False, "connect_supported": True}]})
        elif path == "/v1/sync-runs":
            self._json(200, {"items": [{"id": k, "source_account_id": "acct-1", **v}
                                       for k, v in received["runs"].items()]})
        elif path.startswith("/v1/sync-runs/"):
            self._json(200, received["runs"].get(path.rsplit("/", 1)[-1], {"status": "running"}))
        elif path in ("/v1/extension/bootstrap", "/v1/credentials"):
            self._json(200, {"destinations": [], "items": []})
        else:
            self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if path == "/v1/accounts/connect/start":
            self._json(202, {"connection_ref": "ref-abcdef123456", "platform": "xiaohongshu",
                             "state": "authorizing", "auth_method": "browser_session",
                             "next_action_zh": "请在平台页面登录",
                             "supported_relations": ["favorite"]})
        elif path.endswith("/complete"):
            received["accounts"].append({"id": "acct-1", "platform": "xiaohongshu",
                                         "connection_state": "connected",
                                         "external_account_id": body.get("external_account_id"),
                                         "display_name": body.get("display_name"),
                                         "metadata": body.get("metadata") or {}})
            received["runs"]["run-1"] = {"status": "running", "sync_run_id": "run-1"}
            self._json(201, {"account_id": "acct-1", "first_sync": {"sync_run_id": "run-1"}})
        elif path.endswith("/sync"):
            received["runs"]["run-1"] = {"status": "running", "sync_run_id": "run-1"}
            self._json(202, {"sync_run_id": "run-1"})
        elif "/batches" in path:
            received["batches"].append(body)
            received["runs"]["run-1"] = {"status": "completed", "sync_run_id": "run-1"}
            self._json(202, {"accepted": len(body.get("items") or [])})
        else:
            self._json(404, {"detail": "not found"})


def _cert(folder: Path) -> ssl.SSLContext:
    cert, key = folder / "c.pem", folder / "k.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=xiaohongshu.com",
                    "-addext", "subjectAltName=DNS:xiaohongshu.com,DNS:*.xiaohongshu.com"],
                   check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    return context


def _stage(folder: Path) -> Path:
    staged = folder / "extension"
    shutil.copytree(EXT_SRC, staged)
    manifest_path = staged / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    optional = manifest.get("optional_host_permissions", [])
    manifest["host_permissions"] = sorted(set(manifest.get("host_permissions", [])) | set(optional))
    manifest["optional_host_permissions"] = []
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return staged


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


JOURNEY = r"""
(async () => {
  await SA.setConfig({ endpoint: "http://127.0.0.1:%(api)d", token: "drill" });
  const out0 = {};
  // **他真正会走的那条路**：点「连接账号」→ 点「我已登录，继续」
  out0.connect = await connectPlatform("xiaohongshu");
  await new Promise(r => setTimeout(r, 2500));
  out0.verify = await verifyPendingPlatform("xiaohongshu");
  // 连接成功会把首次同步排进队列。**走真队列**（闹钟处理器跑的就是这个函数），
  // 而不是直接调同步——那样会跳过"任务到底有没有被排上"这一整段。
  out0.queued = (await getSyncQueue()).length;
  try {
    out0.sync = await processSyncQueue();
  } catch (error) {
    out0.sync = { error: String(error && error.message || error) };
  }
  const tab = await chrome.tabs.create({ url: "https://www.xiaohongshu.com/user/profile",
                                         active: false });
  await new Promise(r => setTimeout(r, 2500));
  let out = {};
  // 先单独看装载这一步说了什么——0 条抓到时，是没装上还是装晚了，
  // 这两者的下一步完全不同。
  out.install = await installNetObserverForTab({ platform: "xiaohongshu",
                                                 tabId: tab.id, shapeMode: true });
  await new Promise(r => setTimeout(r, 6000));
  out.afterInstall = netCaptureBuffer.length;
  try {
    out.result = await acquireRelationItems({ tabId: tab.id, platform: "xiaohongshu",
                                              relation: "favorite" });
  } catch (error) {
    out.error = { message: String(error && error.message || error),
                  failureCode: error && error.failureCode || null,
                  detail: error && error.detail || null };
  }
  out.captured = netCaptureBuffer.length;
  out.capturedUrls = netCaptureBuffer.map(c => c.url);
  Object.assign(out, out0);
  return JSON.stringify(out);
})()
"""


async def run(chrome: str) -> int:
    workspace = Path(tempfile.mkdtemp(prefix="sa-shape-"))
    problems: list[str] = []
    measured: dict = {}
    context = _cert(workspace)
    staged = _stage(workspace)
    server = ThreadingHTTPServer(("127.0.0.1", FAKE_PORT), _Fake)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    api_server = ThreadingHTTPServer(("127.0.0.1", FAKE_API_PORT), _Api)
    threading.Thread(target=api_server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--password-store=basic", "--use-mock-keychain",
         f"--host-resolver-rules=MAP *xiaohongshu.com 127.0.0.1:{FAKE_PORT}",
         "--ignore-certificate-errors", "--allow-insecure-localhost", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 2
        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": str(staged)})
            extension_id = loaded.get("result", {}).get("id") or ""
        await asyncio.sleep(3)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        workers = [t for t in targets if t.get("type") == "service_worker"
                   and extension_id in t.get("url", "")]
        if not workers:
            print(json.dumps({"status": "FAIL", "error_code": "NO_SERVICE_WORKER"},
                             ensure_ascii=False))
            return 2
        async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            got = await rpc("Runtime.evaluate", {"expression": JOURNEY % {"api": FAKE_API_PORT}, "userGesture": True,
                                                 "awaitPromise": True, "returnByValue": True,
                                                 "timeout": 90000})
            payload = got.get("result", {})
            if payload.get("exceptionDetails"):
                problems.append(f"整条链跑炸了：{str(payload['exceptionDetails'])[:300]}")
            else:
                measured = json.loads(payload["result"]["value"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        api_server.shutdown()
        shutil.rmtree(workspace, ignore_errors=True)

    if measured.get("error"):
        problems.append(f"没读出来：{measured['error'].get('failureCode')} / "
                        f"{measured['error'].get('message')}")
    result = measured.get("result") or {}
    items = result.get("items") or []
    if measured.get("captured", 0) == 0:
        problems.append("**一条响应都没抓到**——观察器没装上，或者装得太晚")
    if len(items) != len(NOTES):
        problems.append(f"读到 {len(items)} 条，页面上有 {len(NOTES)} 条")
    bad = [i.get("url") for i in items
           if not str(i.get("url", "")).startswith("https://www.xiaohongshu.com/explore/")]
    if bad:
        problems.append(f"有条目的网址不对：{bad[:3]}")
    # **最贵的那个错：把推荐流当成他的收藏。**
    matched = str((result.get("cursor") or {}).get("matched_url") or "")
    if "homefeed" in matched:
        problems.append("**把推荐流当成收藏列表了**——那会把首页推荐存进他的档案馆")
    if matched and "collect" not in matched:
        problems.append(f"认出来的不是收藏那一条：{matched}")
    if result.get("completeness") == "complete":
        problems.append("**报了 complete**——页面只发了滚动到的那一批，"
                        "报完整会让消失检测把没滚到的当成他取消了收藏")

    verify = measured.get("verify") or {}
    if not verify.get("ok"):
        problems.append(f"**「我已登录，继续」这一步没成**：{verify.get('failureCode')} / "
                        f"{verify.get('error')}——账号建不起来，可同步就是空话")
    account = (received["accounts"] or [{}])[0]
    if not account:
        problems.append("**档案馆里没建起账号**")
    blob = json.dumps(account.get("metadata") or {}, ensure_ascii=False).lower()
    for word in ("cookie", "token", "password"):
        if word in blob:
            problems.append(f"账号元数据里出现了 {word}")
    landed = [item for batch in received["batches"] for item in (batch.get("items") or [])]
    if len(landed) != len(NOTES):
        problems.append(f"档案馆只收到 {len(landed)} 条，页面上有 {len(NOTES)} 条")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "connect": measured.get("connect"),
        "verify": verify,
        "account_created": account,
        "items_landed": len(landed),
        "install": measured.get("install"),
        "captured_right_after_install": measured.get("afterInstall"),
        "captured_responses": measured.get("captured"),
        "captured_urls": measured.get("capturedUrls"),
        "recognised": matched,
        "matched_path": (result.get("cursor") or {}).get("matched_path"),
        "items": len(items),
        "sample_urls": [i.get("url") for i in items[:3]],
        "completeness": result.get("completeness"),
        "failure_code": result.get("failureCode"),
        "problems": problems,
        "what_this_does_not_prove": (
            "**不证明真小红书的响应长这样**——那要 Owner 自己的登录态，"
            "只能发生在他的浏览器里。这里证明的是：不知道接口地址也能装上观察器、"
            "能收到页面自己的响应、能从噪声里认出列表、能变成可入库的条目，"
            "而且不会把推荐流认成收藏。"),
    }
    out = ROOT / "evidence/G1/LIST_SHAPE_END_TO_END.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验「不知道地址也能读出收藏」这条路")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
