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

def _flat(prefix: str, n: int, base: int) -> list[dict]:
    """字段摊平的条目（小红书那种）。"""
    return [{"note_id": f"{prefix}{i}", "display_title": f"{prefix} 第 {i} 条",
             "user": {"nickname": f"作者{i}"}, "create_time": base + i,
             # 封面：真实条目都带，而按形状读此前一个媒体地址都不取——
             # 他打开资料库看到的是一排纯文字。
             "cover": {"url_default": f"https://img.example/{prefix}{i}.webp"}}
            for i in range(1, n + 1)]


def _reddit(prefix: str, n: int, base: int) -> dict:
    """Reddit 的形状：**id 藏在 `children[].data` 里**，条目自带相对 permalink。"""
    return {"kind": "Listing", "data": {"after": None, "children": [
        {"kind": "t3", "data": {"id": f"{prefix}{i}", "title": f"{prefix} 帖子 {i}",
                                "author": f"u{i}", "created_utc": base + i,
                                "permalink": f"/r/sub/comments/{prefix}{i}/t/",
                                # 真实帖子带这个；键路径里有 preview/image，
                                # 而取封面认的就是键名不是平台。
                                "preview": {"images": [{"source": {
                                    "url": f"https://preview.redd.it/{prefix}{i}.jpg"}}]}}}
        for i in range(1, n + 1)]}}


def _instagram(prefix: str, n: int, base: int) -> dict:
    """Instagram 的形状：**id 藏在 `items[].media` 里**，网址要用短码 `code`。"""
    return {"items": [
        {"media": {"pk": f"31234{i}", "id": f"31234{i}_9", "code": f"C{prefix}{i}xYz",
                   "taken_at": base + i, "caption": {"text": f"{prefix} 说明 {i}"},
                   "user": {"username": f"u{i}", "full_name": f"名字{i}"},
                   # 真实条目一定有这个
                   "image_versions2": {"candidates": [
                       {"url": f"https://scontent.example/{prefix}{i}.jpg"}]}}}
        for i in range(1, n + 1)]}


# 一条路，四家平台，**四种响应形状**。
#
# 加 Reddit / Instagram 不是为了凑数：拿它们真实的形状一试，第一版**三家全灭**
# （X 也一样），理由都是「0% 的元素带得出 id」——因为 id 不在元素身上，在壳里。
# 而这个缺陷同时伤着已经上线的小红书（标题作者取不到，全存成 null）。
# 所以这张表的用处是**逼着这条路在不止一种形状上成立**。
# 追踪剂：只有这条链会碰到的一个 Cookie。名字和值都取得足够特别，
# 出现在服务端收到的任何地方都不可能是巧合。
COOKIE_NAME = "sa_drill_domestic_session"
COOKIE_VALUE = "DOMESTIC-COOKIE-MUST-NOT-LEAVE-7f3a91"

ITEM_COUNT = 7
PLATFORMS: dict[str, dict] = {
    "xiaohongshu": {
        "domain": "xiaohongshu.com", "favourite_path": "/user/profile",
        "feed_route": "/api/homefeed", "list_route": "/api/collect/page",
        "feed": {"data": {"items": _flat("rec", 6, 1800000000)}},
        "list": {"data": {"notes": _flat("n", ITEM_COUNT, 1700000000)}},
        "url_prefix": "https://www.xiaohongshu.com/explore/", "derived_by": "id_template",
    },
    "reddit": {
        "domain": "reddit.com", "favourite_path": "/user/me/saved",
        "feed_route": "/svc/best", "list_route": "/svc/saved",
        "feed": _reddit("rec", 6, 1800000000), "list": _reddit("n", ITEM_COUNT, 1700000000),
        "url_prefix": "https://www.reddit.com/r/sub/comments/", "derived_by": "relative_link",
    },
    "instagram": {
        "domain": "instagram.com", "favourite_path": "/your_activity/saved",
        "feed_route": "/api/v1/feed/timeline", "list_route": "/api/v1/collections/saved",
        "feed": _instagram("rec", 6, 1800000000),
        "list": _instagram("n", ITEM_COUNT, 1700000000),
        "url_prefix": "https://www.instagram.com/p/C", "derived_by": "slug_template",
    },
}

# 关系名各家不同：国内三家是「收藏」，Reddit / Instagram 都叫 saved。
RELATIONS = {"xiaohongshu": "favorite", "reddit": "saved", "instagram": "saved"}

PLATFORM = "xiaohongshu"
RELATION = RELATIONS[PLATFORM]
SPEC = PLATFORMS[PLATFORM]
ROUTES: dict[str, dict] = {}


def _routes(spec: dict) -> dict:
    """收藏页加载时会打的那几个请求。**噪声必须真实**——
    只放一个真列表的话，这个演练证明不了「不会认错」。

    推荐流用的是**和收藏列表一模一样的形状**（真实情况就是这样）。
    原来这里写的是只有 banner 的假数据，识别器当然认不上，
    于是「在发现页上跑」这个错看起来无害——而真实情况下它会被认成列表，
    **把首页推荐当成他的收藏导进档案馆**。
    """
    return {
        "/api/log": {"ok": 1},
        "/api/config": {"flags": {"a": 1, "b": 2, "c": 3, "d": 4}},
        "/api/user": {"user": {"id": 1, "nickname": "我"}},
        spec["feed_route"]: spec["feed"],
        spec["list_route"]: spec["list"],
    }

def _page(paths: list[str]) -> str:
    """页面在加载时打哪些请求，**按它是哪一页决定**。

    这一条是被一个真缺陷逼出来的：原来假站对任何路径都返回同一个页面
    （都会打 /api/collect/page），于是「连接时打开的是发现页而不是收藏页」
    这个错**被固定装置完全掩盖**——夹具是我编的，它当然对我有利。
    """
    listed = ",".join(f'"{item}"' for item in paths)
    return ("<!doctype html><meta charset=utf-8><title>页</title><h1>页</h1>\n"
            "<script>\n"
            # **种一个特征 Cookie，当追踪剂。**
            #
            # 安装页上写着「小红书、抖音、B站、快手的 Cookie 一步都不会离开
            # 你的浏览器」。守着这句的判据全是**源码层面**的（表里有没有、
            # 会不会打日志）——而他读到的是一句**运行时**的承诺。
            # 这里在页面上种一个只有这条链会碰到的值，跑完整条链之后
            # 翻检服务端收到的每一个字节：出现一次就算这句话是假的。
            f'document.cookie = "{COOKIE_NAME}={COOKIE_VALUE}; path=/";\n'

            '["/api/log"].forEach(p => fetch(p).then(r => r.json()).catch(() => {}));\n'
            f"setTimeout(() => {{ [{listed}]\n"
            "  .forEach(p => fetch(p).then(r => r.json()).catch(() => {})); }, 400);\n"
            "</script>")


# **发现页**：只有推荐流，没有收藏列表。真实的首页就是这样。
# **收藏页**：这里才发收藏列表。两页都发推荐流——收藏页上两者并存，
# 而它们形状一样，这正是那条破平局规则要顶住的场面。
EXPLORE_PAGE = ""
FAVOURITE_PAGE = ""


def _pages(spec: dict) -> tuple[str, str]:
    common = ["/api/config", "/api/user", spec["feed_route"]]
    return _page(common), _page([*common, spec["list_route"]])


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
            # 只有收藏页发收藏列表；其余（含首页/发现页）都不发
            page = FAVOURITE_PAGE if SPEC["favourite_path"] in path else EXPLORE_PAGE
            body = page.encode()
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
                {"platform": PLATFORM, "relations": [RELATION],
                 "sync_supported": True, "not_syncable_reason": "",
                 "server_handled": False, "connect_supported": True},
                # **只能手动保存的那一类也要下发**：连接面板要照列它们并写清原因，
                # 而不是把它们藏起来（Owner 验收标准第 1 条）。
                {"platform": "x", "relations": ["bookmark"],
                 "sync_supported": False,
                 "not_syncable_reason": "本版本还不能自动读取 X 的书签。"
                                        "现在可以：在浏览器里打开任意一条推文，点插件的「保存当前页面」。",
                 "server_handled": True, "connect_supported": False}]})
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
            self._json(202, {"connection_ref": "ref-abcdef123456", "platform": PLATFORM,
                             "state": "authorizing", "auth_method": "browser_session",
                             "next_action_zh": "请在平台页面登录",
                             "supported_relations": [RELATION]})
        elif path.endswith("/complete"):
            received["accounts"].append({"id": "acct-1", "platform": PLATFORM,
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
                    "-subj", f"/CN={SPEC['domain']}",
                    "-addext",
                    f"subjectAltName=DNS:{SPEC['domain']},DNS:*.{SPEC['domain']}"],
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
    # **cookies 权限也授上。**
    #
    # 不授的话 `chrome.cookies` 根本不存在，那条「这条链碰没碰过 Cookie」的
    # 观测就是**空过**——监视器无事可包，计数永远是 0。我第一版就是这么空过的。
    # 授上之后它对应的是真实情况：他为 Instagram 授过 cookies，
    # 而国内平台那条链**在有能力读的前提下仍然一次都不读**，那才叫承诺成立。
    manifest["permissions"] = sorted(set(manifest.get("permissions", []))
                                     | set(manifest.get("optional_permissions", [])))
    manifest["optional_permissions"] = []
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
  // **监视 chrome.cookies：这条链碰它一次都不许。**
  //
  // 安装页上写着「小红书、抖音、B站、快手的 Cookie 一步都不会离开你的浏览器」。
  // 守着这句的判据全是源码层面的（表里有没有、会不会打日志），
  // 而他读到的是一句**运行时**的承诺。这里把整个 chrome.cookies 换成计数器，
  // 跑完整条链再看计数——**碰过就是碰过**，源码怎么写不重要。
  //
  // （光在页面上种一个 Cookie 当追踪剂是不够的：取数那一段跑在
  //  service worker 里，那里 `document` 根本不存在，种什么都带不出去，
  //  于是那种"反证"永远不会红——我第一版就是这么空过一次。）
  const cookieCalls = [];
  if (chrome.cookies) {
    for (const name of ["get", "getAll", "getAllCookieStores", "set", "remove"]) {
      const real = chrome.cookies[name];
      if (typeof real !== "function") continue;
      chrome.cookies[name] = (...args) => {
        cookieCalls.push({ fn: name, arg: JSON.stringify(args[0] || {}).slice(0, 120) });
        return real.apply(chrome.cookies, args);
      };
    }
  }
  const out0 = {};
  // **他真正会走的那条路**：点「连接账号」→ 点「我已登录，继续」
  out0.connect = await connectPlatform("%(platform)s");
  await new Promise(r => setTimeout(r, 2500));
  out0.verify = await verifyPendingPlatform("%(platform)s");
  // 连接成功会把首次同步排进队列。**走真队列**（闹钟处理器跑的就是这个函数），
  // 而不是直接调同步——那样会跳过"任务到底有没有被排上"这一整段。
  out0.queued = (await getSyncQueue()).length;
  try {
    out0.sync = await processSyncQueue();
  } catch (error) {
    out0.sync = { error: String(error && error.message || error) };
  }
  const tab = await chrome.tabs.create({ url: "%(favourite)s", active: false });
  await new Promise(r => setTimeout(r, 2500));
  let out = {};
  // 先单独看装载这一步说了什么——0 条抓到时，是没装上还是装晚了，
  // 这两者的下一步完全不同。
  out.install = await installNetObserverForTab({ platform: "%(platform)s",
                                                 tabId: tab.id, shapeMode: true });
  await new Promise(r => setTimeout(r, 6000));
  out.afterInstall = netCaptureBuffer.length;
  try {
    out.result = await acquireRelationItems({ tabId: tab.id, platform: "%(platform)s",
                                              relation: "%(relation)s" });
  } catch (error) {
    out.error = { message: String(error && error.message || error),
                  failureCode: error && error.failureCode || null,
                  detail: error && error.detail || null };
  }
  out.cookieCalls = cookieCalls;
  out.cookiesApiPresent = Boolean(chrome.cookies);
  out.captured = netCaptureBuffer.length;
  out.capturedUrls = netCaptureBuffer.map(c => c.url);
  Object.assign(out, out0);
  return JSON.stringify(out);
})()
"""


async def run(chrome: str, platform: str) -> int:
    global PLATFORM, RELATION, SPEC, ROUTES, EXPLORE_PAGE, FAVOURITE_PAGE
    PLATFORM = platform
    RELATION = RELATIONS[platform]
    SPEC = PLATFORMS[platform]
    ROUTES = _routes(SPEC)
    EXPLORE_PAGE, FAVOURITE_PAGE = _pages(SPEC)
    received["accounts"].clear(); received["batches"].clear(); received["runs"].clear()
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
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
         "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--password-store=basic", "--use-mock-keychain",
         f"--host-resolver-rules=MAP *{SPEC['domain']} 127.0.0.1:{FAKE_PORT}",
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
            got = await rpc("Runtime.evaluate", {"expression": JOURNEY % {
                "api": FAKE_API_PORT, "platform": PLATFORM, "relation": RELATION,
                "favourite": f"https://www.{SPEC['domain']}{SPEC['favourite_path']}"},
                "userGesture": True,
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
    if len(items) != ITEM_COUNT:
        problems.append(f"读到 {len(items)} 条，页面上有 {ITEM_COUNT} 条")
    bad = [i.get("url") for i in items
           if not str(i.get("url", "")).startswith(SPEC["url_prefix"])]
    if bad:
        problems.append(f"有条目的网址不对：{bad[:3]}")
    # **网址是取来的还是拼来的，要对得上预期。**
    # Reddit 的条目自带 permalink，就必须走 relative_link；如果它悄悄退回
    # id_template，那批网址就是我拼的、一条都没被数据证实过——
    # 而两种情况下 `items` 的条数完全一样，光数数看不出来。
    ways = sorted({str((i.get("raw_metadata") or {}).get("derived_by")) for i in items})
    if ways != [SPEC["derived_by"]]:
        problems.append(f"网址的来路不对：预期全是 {SPEC['derived_by']}，实际是 {ways}")
    # 标题和作者**必须真的取到**。这两个字段取不到时条目照样入库，
    # 只是全成了 null——2026-08-06 之前小红书就是这样，而所有判据全绿。
    missing = [i.get("url") for i in items if not i.get("title") or not i.get("author_name")]
    if missing:
        problems.append(f"有条目丢了标题或作者（会静默存成 null）：{missing[:3]}")
    # **最贵的那个错：把推荐流当成他的收藏。**
    matched = str((result.get("cursor") or {}).get("matched_url") or "")
    if "homefeed" in matched:
        problems.append("**把推荐流当成收藏列表了**——那会把首页推荐存进他的档案馆")
    if matched and not matched.endswith(SPEC["list_route"]):
        problems.append(f"认出来的不是收藏那一条：{matched}")
    if result.get("completeness") == "complete":
        problems.append("**报了 complete**——页面只发了滚动到的那一批，"
                        "报完整会让消失检测把没滚到的当成他取消了收藏")

    # **一次点击就该完事**（v0.0.0.22）。
    #
    # Owner：「几个页面乱七八糟的跳来跳去非常乱」——而这正是他自己定的铁律第 4 条。
    # 连接现在会在后台轮询确认登录态，成了就直接连上；只有自动认不出来时，
    # 才把平台页翻到前台并要他点「我已登录，继续」。
    #
    # 所以这里认两种结局，**但都必须真的连上**：
    #   · 连接自己就完成了（state=connected）——正常路，他只点了一次
    #   · 连接仍在等确认，而后面那次显式确认成功——他还没登录时的退路
    # 两种都不成立才叫失败。
    connect = measured.get("connect") or {}
    verify = measured.get("verify") or {}
    if not (connect.get("state") == "connected" or verify.get("ok")):
        problems.append(
            f"**连不上**：连接说 {json.dumps(connect, ensure_ascii=False)[:160]}；"
            f"确认说 {verify.get('failureCode')} / {verify.get('error')}"
            "——账号建不起来，可同步就是空话")
    # **别把「跳走了」当成成功。** 自动认出来的那条路上，
    # 连接返回时状态必须已经是 connected；否则他就得再点一次、再跳一次。
    if connect.get("state") == "authorizing" and verify.get("ok"):
        problems.append("连接没能自动确认，退回到了「我已登录，继续」那条路——"
                        "在这个夹具里页面本来就是已登录状态，说明自动确认那几轮没起作用")
    account = (received["accounts"] or [{}])[0]
    if not account:
        problems.append("**档案馆里没建起账号**")
    blob = json.dumps(account.get("metadata") or {}, ensure_ascii=False).lower()
    for word in ("cookie", "token", "password"):
        if word in blob:
            problems.append(f"账号元数据里出现了 {word}")
    landed = [item for batch in received["batches"] for item in (batch.get("items") or [])]
    # **绝不许把首页推荐当成他的收藏。**
    polluted = [i.get("url") for i in landed if "rec" in str(i.get("url", ""))]
    if polluted:
        problems.append(f"**把发现页的推荐当成收藏导进来了**：{polluted[:3]}"
                        "——连接时打开的必须是收藏页，不是发现页")
    # **封面要一路落到档案馆**，不是只在扩展里取到就算。
    without_media = [item.get("url") for item in landed if not (item.get("media_urls") or [])]
    if without_media:
        problems.append(
            f"**有条目没带上封面**：{without_media[:3]}——他打开资料库看到的是一排纯文字，"
            "而 CaptureRequest 一直支持 media_urls、批次协议也一直透传，缺的只是取数那一步")
    # **发布时间要一路落到档案馆。**
    #
    # 2026-08-07 量他生产库：193 条里只有 2 条有 published_at。B 站那条路
    # 取了（bilibili-reader.js:129 的 `media.pubtime`），而**形状识别这条路
    # 把时间只用于打分、没写进条目**——抖音/小红书/快手/Reddit/Instagram
    # 五个平台的发布时间全丢了。键早就在 TIME_KEYS 里，值就在假响应的
    # `create_time` 上，缺的只是把它放进 items.push 那一步。
    #
    # 和 media_urls 那条是同一族：**扩展取到了 ≠ 落进了档案馆。**
    without_time = [item.get("url") for item in landed if not item.get("published_at")]
    if without_time:
        problems.append(
            f"**有条目没带上发布时间**：{without_time[:3]}——他表格里那一列会是空的，"
            "而假响应里 create_time 就在那儿")
    bad_time = [item.get("published_at") for item in landed
                if item.get("published_at") and not str(item["published_at"]).startswith("20")]
    if bad_time:
        problems.append(f"**发布时间不像日期**：{bad_time[:3]}——宁可空着也不许印错的")
    if len(landed) != ITEM_COUNT:
        problems.append(f"档案馆只收到 {len(landed)} 条，页面上有 {ITEM_COUNT} 条")

    # **翻检服务端收到的每一个字节。**
    #
    # 不只是批次：账号、回执、游标、诊断——凡是这条链送出去的，全在 received 里。
    leaked = json.dumps(received, ensure_ascii=False)
    # **碰没碰过 chrome.cookies**——这是那句承诺真正的机制。
    cookie_calls = measured.get("cookieCalls")
    if cookie_calls is None:
        problems.append("**没量到这条链有没有碰 chrome.cookies**——这不是通过，是没测到")
    elif not measured.get("cookiesApiPresent"):
        # **不是"没碰"，是"根本没能力碰"。** 两者都算承诺成立，但**说法不一样**，
        # 而空过的那种会让这条观测永远绿——所以这里明说它没测到什么。
        problems.append("**这一趟里 chrome.cookies 根本不存在**（cookies 权限没授上），"
                        "于是「碰没碰过」这条什么也没验到——夹具要把它授上才算测过")
    elif cookie_calls:
        problems.append(
            f"**这条链读了浏览器的 Cookie**：{cookie_calls[:3]}——"
            "安装页上写着国内平台的 Cookie 一步都不会离开浏览器"
            "（INV-DOMESTIC-COOKIE-STAYS）")
    for needle, what in ((COOKIE_VALUE, "Cookie 的值"), (COOKIE_NAME, "Cookie 的名字")):
        if needle in leaked:
            problems.append(
                f"**{what}离开了浏览器**——它出现在服务端收到的数据里。"
                "安装页上写着「小红书、抖音、B站、快手的 Cookie 一步都不会离开你的浏览器」，"
                "那句话就是假的（INV-DOMESTIC-COOKIE-STAYS）")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "platform": PLATFORM,
        # 这条链送到服务端的总字节数，以及追踪剂在不在里面
        "bytes_sent_to_archive": len(leaked),
        # 两条独立的证据：**碰没碰过 cookies API**（机制），
        # 以及**追踪剂在不在送出去的字节里**（结果）。
        "chrome_cookies_calls": measured.get("cookieCalls"),
        "cookies_api_was_available": measured.get("cookiesApiPresent"),
        "domestic_cookie_stayed_in_browser": COOKIE_VALUE not in leaked and COOKIE_NAME not in leaked,
        "relation": RELATION,
        "response_shape": SPEC["derived_by"],
        "url_derived_by": ways if items else [],
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
    suffix = "" if PLATFORM == "xiaohongshu" else f"_{PLATFORM}"
    out = ROOT / f"evidence/G1/LIST_SHAPE_END_TO_END{suffix}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验「不知道地址也能读出收藏」这条路")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--platform", default="xiaohongshu", choices=sorted(PLATFORMS))
    args = parser.parse_args()
    return asyncio.run(run(args.chrome, args.platform))


if __name__ == "__main__":
    sys.exit(main())
