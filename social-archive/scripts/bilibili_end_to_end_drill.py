#!/usr/bin/env python3
"""从「连接账号」到「档案馆里有条目」，在真 Chrome 里整条跑一遍（v0.0.0.7 / G3）。

## 为什么还要这一个

`bilibili_acquisition_drill.py` 打的是**真接口**，证明「我们对 B 站接口的理解对」。
但它是在 Node 里跑纯函数，证明不了扩展那一整条链：

    点「连接账号」→ 开标签页 → 注入读取器 → 带登录态读 → 确认身份 →
    建账号 → 排首次同步 → 分批上传 → 档案馆里真的有条目

这条链上任何一环断了，Owner 那边的表现都是同一句「不能用」。
而 2026-08-06 查出来的那一环就是**倒数第二环之前**：`verifyPendingPlatform`
对所有浏览器路平台一律回 `LOGIN_PROOF_UNAVAILABLE`——
**账号根本建不起来，取数路做得再好也没人调它。**

## 这个演练怎么做到不用真账号

Chrome 的 `--host-resolver-rules` 把 `*.bilibili.com` 指到本机的假站上，
配 `--ignore-certificate-errors` 收自签证书。于是**扩展里一行代码都不用改**：
它以为自己在跟 B 站说话，实际对面是这个脚本起的固定装置。

这样被真正验到的东西包括：真实的 `chrome.scripting.executeScript` 注入、
真实的跨子域**带凭据** fetch（假站照抄了 B 站的 CORS 响应头）、
真实的消息通道、真实的账号建立与批次上传。

## 它不证明什么

1. **不证明 B 站真的会那样回。** 那是另一个演练的事（打真接口那个）。
   两个合起来才是完整的：一个验「我们理解对不对」，一个验「链子通不通」。
2. **不验权限授予那一下。** `chrome.permissions.request` 需要用户手势，
   演练点不了那个弹窗。所以这里把扩展**复制一份**、把 bilibili 从
   `optional_host_permissions` 挪进 `host_permissions` 再加载。
   也就是说：这个演练验的是「权限有了之后，链子通不通」。
   权限那一下由 Owner 在设置页点「连接账号」时给。
3. 一次性 profile，跑完删；不碰 Owner 的 profile，不碰生产。

## 验的是哪一份扩展

默认是仓里的 `apps/browser-extension/`。**但 Owner 装的不是它**，
他装的是下载页发的那个 zip 解开之后的东西。这个仓栽过一次一模一样的：
「47 道门全在验暂存目录，从没人打开过最终那个 zip」——改成回读自验证之后，
第一次跑就抓到 283 个中文名乱码。

所以每次部署之后**至少跑一次真包**：

    ssh linze-ovh 'curl -s -o /tmp/e.zip http://127.0.0.1:18765/downloads/social-archive-extension.zip'
    scp linze-ovh:/tmp/e.zip /tmp/ && unzip -q /tmp/e.zip -d /tmp/unpacked
    python3 scripts/bilibili_end_to_end_drill.py --ext-dir /tmp/unpacked

2026-08-06 v0.0.0.16 这样跑过一次：24 个文件、manifest 0.0.0.16、
整条链 PASS（连接 → 确认登录 → 同步 → 3 条入库 → 设置页显示已连接）。
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
from urllib.parse import parse_qs, urlparse

import websockets

ROOT = Path(__file__).resolve().parents[1]
EXT_SRC = ROOT / "apps/browser-extension"
FAKE_BILI_PORT = 8443
FAKE_API_PORT = 8765
DEBUG_PORT = 9377

# 假的收藏夹内容。两个收藏夹、共 3 条，条数都对得上 → 应当读成 complete。
FOLDERS = [
    {"id": 111, "title": "学习", "media_count": 2},
    {"id": 222, "title": "音乐", "media_count": 1},
]
ITEMS = {
    "111": [
        {"id": 9001, "bvid": "BV1aaaaaaaaa", "title": "第一条", "intro": "简介一",
         "cover": "https://i0.hdslb.com/a.jpg", "upper": {"name": "作者甲"},
         "pubtime": 1700000000, "fav_time": 1700000100,
         # **故意放一个 App 深链**：真实响应里 link 就是这个样子，
         # 入库的网址必须由 bvid 拼，不能用它。
         "link": "bilibili://video/9001"},
        {"id": 9002, "bvid": "BV1bbbbbbbbb", "title": "第二条", "intro": "简介二",
         "cover": "https://i0.hdslb.com/b.jpg", "upper": {"name": "作者乙"},
         "pubtime": 1700000200, "fav_time": 1700000300,
         "link": "bilibili://video/9002"},
    ],
    "222": [
        {"id": 9003, "bvid": "BV1cccccccccc", "title": "第三条", "intro": "简介三",
         "cover": "https://i0.hdslb.com/c.jpg", "upper": {"name": "作者丙"},
         "pubtime": 1700000400, "fav_time": 1700000500,
         "link": "bilibili://video/9003"},
    ],
}

received: dict = {"batches": [], "accounts": [], "sync_runs": {}, "requests": []}


class _Bili(BaseHTTPRequestHandler):
    """假 B 站。**CORS 响应头照抄真站实测到的那三行**，否则带凭据的读会被浏览器拦掉。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        return

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        origin = self.headers.get("Origin") or "https://www.bilibili.com"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # 实测（2026-08-06）真站回的就是这两行：回显 Origin + 允许带凭据。
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        received["requests"].append(parsed.path)
        if parsed.path == "/x/web-interface/nav":
            self._json({"code": 0, "message": "0", "data": {
                "isLogin": True, "mid": 1919810, "uname": "测试账号"}})
            return
        if parsed.path == "/x/v3/fav/folder/created/list-all":
            self._json({"code": 0, "message": "OK",
                        "data": {"count": len(FOLDERS), "list": FOLDERS}})
            return
        if parsed.path == "/x/v3/fav/resource/list":
            media_id = (query.get("media_id") or ["0"])[0]
            page = int((query.get("pn") or ["1"])[0])
            size = int((query.get("ps") or ["20"])[0])
            everything = ITEMS.get(media_id, [])
            chunk = everything[(page - 1) * size: page * size]
            title = next((f["title"] for f in FOLDERS if str(f["id"]) == media_id), "夹")
            self._json({"code": 0, "message": "OK", "data": {
                "info": {"title": title, "media_count": len(everything)},
                "medias": chunk,
                "has_more": page * size < len(everything)}})
            return
        # 任何 bilibili 页面：给一个最小 HTML，标签页要能 complete
        body = b"<!doctype html><meta charset=utf-8><title>B</title><h1>bilibili</h1>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Api(BaseHTTPRequestHandler):
    """假档案馆。只实现这条链用得到的那几个端点。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        return

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"status": "ok", "version": "0.0.0.7"})
            return
        if path == "/v1/accounts":
            self._json(200, {
                "items": received["accounts"],
                # **照生产的形状给全九个平台**，不是只给 bilibili。
                # 只给一个的话，弹窗里那几句照事实清单重写的话会算出
                # 「只有哔哩哔哩」——看着像产品说错了，其实是夹具不全。
                "supported_platforms": (
                    [{"platform": "bilibili", "relations": ["favorite"],
                      "sync_supported": True, "not_syncable_reason": "",
                      "server_handled": False, "connect_supported": True},
                     {"platform": "generic-web", "relations": ["bookmark"],
                      "sync_supported": True, "not_syncable_reason": "",
                      "server_handled": False, "connect_supported": True}]
                    + [{"platform": name, "relations": ["favorite"],
                        "sync_supported": False,
                        "not_syncable_reason": "本版本还不能自动读取。现在可以：点插件的「保存到我的档案馆」。",
                        "server_handled": name in ("x", "reddit", "instagram"),
                        "connect_supported": name in ("x", "reddit", "instagram", "youtube")}
                       for name in ("xiaohongshu", "douyin", "kuaishou",
                                    "x", "reddit", "instagram", "youtube")]),
            })
            return
        # **列表要放在详情前面判。** `enqueueAccountSync` 进门第一件事就是
        # `listSyncRuns()` → GET /v1/sync-runs?limit=200；第一版只实现了
        # `/v1/sync-runs/{id}`，于是列表落到 404，而 shared.js 把 404 翻成
        # 「这个功能在当前版本还不可用。」——一句和真实原因毫无关系的话。
        # 设置页进门要同时拿这几样；**任何一样 404，整页的卡片都会退成「未连接」**
        # （options.js 的 Promise.all 一挂就走 catch，accounts 被清空）。
        # 第一版只实现了 /v1/accounts，于是卡片一直显示未连接——
        # 看起来像产品缺陷，其实是这个假服务端缺件。
        if path == "/v1/extension/bootstrap":
            self._json(200, {"destinations": [], "endpoint": "", "version": "0.0.0.13"})
            return
        if path == "/v1/credentials":
            self._json(200, {"items": []})
            return
        if path == "/v1/sync-runs":
            self._json(200, {"items": [
                {"id": run_id, "source_account_id": "acct-1", **payload}
                for run_id, payload in received["sync_runs"].items()]})
            return
        if path.startswith("/v1/sync-runs/"):
            run_id = path.rsplit("/", 1)[-1]
            self._json(200, received["sync_runs"].get(run_id, {"status": "running"}))
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if path == "/v1/accounts/connect/start":
            self._json(202, {"connection_ref": "ref-abcdef123456", "platform": "bilibili",
                             "state": "authorizing", "auth_method": "browser_session",
                             "next_action_zh": "请在平台页面登录", "supported_relations": ["favorite"]})
            return
        if path == "/v1/accounts/connect/bilibili/complete":
            received["accounts"].append({
                # **connection_state 不能少。** 少了它设置页那张卡会一直显示「未连接」，
                # 而账号其实已经建好了——那样演练验的就不是连上之后的样子。
                "id": "acct-1", "platform": "bilibili", "connection_state": "connected",
                "content_count": 3, "last_sync_at": "2026-08-06T00:00:00Z",
                "external_account_id": body.get("external_account_id"),
                "display_name": body.get("display_name"),
                "metadata": body.get("metadata") or {},
            })
            received["sync_runs"]["run-1"] = {"status": "running", "sync_run_id": "run-1"}
            self._json(201, {"account_id": "acct-1", "first_sync": {"sync_run_id": "run-1"}})
            return
        if path.endswith("/sync") and path.startswith("/v1/accounts/"):
            received["sync_runs"]["run-1"] = {"status": "running", "sync_run_id": "run-1"}
            self._json(202, {"sync_run_id": "run-1", "relation_scope": body.get("relation_types")})
            return
        if "/batches" in path:
            received["batches"].append(body)
            received["sync_runs"]["run-1"] = {"status": "completed", "sync_run_id": "run-1"}
            self._json(202, {"accepted": len(body.get("items") or [])})
            return
        self._json(404, {"detail": "not found"})


def _serve(handler, port: int, context: ssl.SSLContext | None = None):
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    if context:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _make_cert(folder: Path) -> ssl.SSLContext:
    cert, key = folder / "cert.pem", folder / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=bilibili.com",
         "-addext", "subjectAltName=DNS:bilibili.com,DNS:*.bilibili.com"],
        check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    return context


def _stage_extension(folder: Path, source: Path = EXT_SRC) -> Path:
    """复制一份扩展，把 bilibili 的 host 权限**从可选挪成必需**。

    理由写在文件头：演练点不了 `chrome.permissions.request` 的弹窗。
    只动 manifest 的这一处，其余代码原样——验的还是真代码。
    """
    staged = folder / "extension"
    shutil.copytree(source, staged)
    manifest_path = staged / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # **整张 optional 表一起挪，不要只挑名字里带 bilibili 的那几条。**
    #
    # 第一版是 `if "bilibili" in p`，于是漏掉了 `https://b23.tv/*` —— 而
    # shared.js 的 PLATFORM_RULES 里 bilibili 的 patterns 是
    # ["https://*.bilibili.com/*", "https://b23.tv/*"] 两条。
    # `chrome.permissions.contains` 要求**全部**命中才回 true，少一条就回 false，
    # 于是它照样掉进 permissions.request，照样抛「必须在用户手势期间调用」。
    # 少挪一条短链域名，整条演练就卡在第一步——而报出来的错完全指向另一个方向。
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
  const out = {};
  const snapshot = async () => (await chrome.tabs.query({})).map(
    t => ({ id: t.id, url: t.url, active: t.active }));
  await SA.setConfig({ endpoint: "http://127.0.0.1:%(api)d", token: "drill-token" });
  // ① 点「连接账号」那一下
  out.connect = await connectPlatform("bilibili");
  // 等标签页把假 B 站页面加载完
  await new Promise(r => setTimeout(r, 2500));
  // ② 点「我已登录，继续」那一下 —— 这一步以前一律回 LOGIN_PROOF_UNAVAILABLE
  out.verify = await verifyPendingPlatform("bilibili");

  // **同步开始之前，把用户"正在看的那一页"摆出来。**
  // 定时同步每 6 小时跑一次，跑的时候他多半正在看别的东西。
  const mine = await chrome.tabs.create({ url: "about:blank", active: true });
  await new Promise(r => setTimeout(r, 800));
  out.tabs_before = await snapshot();
  out.my_tab_id = mine.id;

  // ③ 同步 —— **走队列，不走捷径**。
  //
  // 之前这里直接调 syncAccountById，注释写着「免得等闹钟」。
  // 那样跳过了整整一段：连接成功后 enqueueAccountSync 有没有真的把任务入队、
  // 周期闹钟有没有真的排上、processSyncQueue 会不会真的把它取出来跑。
  // 那一段断了的话，他点完「我已登录，继续」会看到「正在后台读取你的收藏夹」，
  // **然后什么都不会发生**——而这正是这个项目反复栽的「看着接上了」。
  out.queue_before = await getSyncQueue();
  const alarm = await chrome.alarms.get(SYNC_QUEUE_ALARM);
  out.alarm_scheduled = Boolean(alarm);
  out.alarm_period_minutes = alarm ? alarm.periodInMinutes : null;
  try {
    // 闹钟处理器里跑的就是这一个函数（background.js: onAlarm → processSyncQueue）。
    // 直接调它，等于把那 30 秒快进掉，而链路一段都没少。
    out.sync = await processSyncQueue();
  } catch (error) {
    out.sync = { error: String(error && error.message || error),
                 failureCode: error && error.failureCode || null };
  }
  out.queue_after = await getSyncQueue();
  await new Promise(r => setTimeout(r, 500));
  out.tabs_after = await snapshot();
  const after = out.tabs_after.find(t => t.active);
  out.still_looking_at_my_tab = Boolean(after && after.id === mine.id);
  out.tabs_created_by_sync = out.tabs_after.length - out.tabs_before.length;
  return JSON.stringify(out);
})()
"""



# 设置页上 B 站那张卡到底长什么样。**只读，不点任何东西。**
OPTIONS_PROBE = r"""
(() => {
  const grid = document.getElementById("accountGrid");
  const cards = [...(grid ? grid.querySelectorAll(".account-card, .card, [data-platform]") : [])];
  const text = (grid && grid.innerText) || "";
  const bili = cards.find(el => (el.innerText || "").includes("B站")
                             || (el.innerText || "").includes("哔哩"));
  return JSON.stringify({
    gridExists: Boolean(grid),
    cardCount: cards.length,
    mentionsBilibili: text.includes("B站") || text.includes("哔哩"),
    biliCardText: bili ? (bili.innerText || "").replace(/\s+/g, " ").slice(0, 200) : "",
    biliButtons: bili ? [...bili.querySelectorAll("button")].map(b => (b.textContent || "").trim()) : [],
    // 已连接的账号上该有「立即同步」；未连接的该有「连接账号」
    anyConnectButton: text.includes("连接账号"),
    anySyncButton: text.includes("立即同步"),
  });
})()
"""

# 弹窗（点插件图标看到的那个）。使用说明里两次指到它，而它从来没在真 Chrome 里
# 被打开过——只有一个 Playwright 的假 popup harness。**只读，不点。**
POPUP_PROBE = r"""
(() => {
  const text = (document.body.innerText || "").replace(/\s+/g, " ");
  const get = id => document.getElementById(id);
  return JSON.stringify({
    hasSettingsButton: Boolean(get("settings")),
    hasSaveButton: Boolean(get("savePage")),
    hasOpenLibrary: Boolean(get("openLibrary")),
    manageAccountsHint: (get("manageAccountsHint") || {}).textContent || "",
    saveSummary: (get("saveSummary") || {}).textContent || "",
    diagnoseWhy: (get("diagnoseWhy") || {}).textContent || "",
    // 「保存当前页面」是不是藏在一个收起来的 details 里
    saveIsCollapsed: (() => {
      const b = get("savePage");
      const d = b && b.closest("details");
      return Boolean(d && !d.open);
    })(),
    mentionsBilibiliCannotRead: text.includes("B站的收藏列表现在还读不了")
      || /小红书、抖音、B站/.test(text),
  });
})()
"""

async def run(chrome: str, ext_src: Path = EXT_SRC) -> int:
    workspace = Path(tempfile.mkdtemp(prefix="sa-bili-e2e-"))
    profile = workspace / "profile"
    problems: list[str] = []
    measured: dict = {}
    context = _make_cert(workspace)
    staged = _stage_extension(workspace, ext_src)
    bili = _serve(_Bili, FAKE_BILI_PORT, context)
    api = _serve(_Api, FAKE_API_PORT)
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--password-store=basic", "--use-mock-keychain",
         # 把 B 站指到本机的假站上。扩展代码一行没改，它以为对面是真的。
         f"--host-resolver-rules=MAP *bilibili.com 127.0.0.1:{FAKE_BILI_PORT}",
         "--ignore-certificate-errors", "--allow-insecure-localhost",
         "about:blank"],
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
            if "error" in loaded:
                print(json.dumps({"status": "FAIL", "error_code": "LOAD_UNPACKED_FAILED",
                                  "detail": str(loaded)[:300]}, ensure_ascii=False))
                return 2
            extension_id = loaded.get("result", {}).get("id") or ""
        await asyncio.sleep(3)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        # **必须按扩展 ID 挑。** Chrome 自己带的组件扩展也有 service worker
        # （实测这台机器上是 fignfifoniblkonapihmkfakmlgkbkcf），
        # 直接取 workers[0] 会连到它，然后报一句 "SA is not defined" ——
        # 那不是我们的代码坏了，是连错了人。仓里其它六个演练都是这么挑的，
        # 只有这个新写的漏了。
        workers = [t for t in targets
                   if t.get("type") == "service_worker" and extension_id in t.get("url", "")]
        if not workers:
            print(json.dumps({"status": "FAIL", "error_code": "NO_SERVICE_WORKER"},
                             ensure_ascii=False))
            return 2
        async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            result = await rpc("Runtime.evaluate", {
                "expression": JOURNEY % {"api": FAKE_API_PORT},
                # **必须带用户手势。** `chrome.permissions.request` 即便权限已经
                # 在 host_permissions 里给全了，仍然要求「在一次用户手势期间调用」，
                # 否则直接抛 "This function must be called during a user gesture"。
                # CDP 的 userGesture 就是替这一下手势签名的；它不会绕过授权，
                # 只是让一个**已经授予**的权限请求能立即返回 true。
                "userGesture": True,
                "awaitPromise": True, "returnByValue": True, "timeout": 90000})
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                problems.append(f"整条链跑炸了：{str(payload['exceptionDetails'])[:300]}")
            else:
                measured = json.loads(payload["result"]["value"])

        # ── 设置页那张卡片（v0.0.0.13）。
        #
        # 上面那一段是在 service worker 里直接调 connectPlatform / verifyPendingPlatform，
        # **它绕过了 Owner 真正会走的那条路**：打开设置页 → 找到 B 站那张卡 → 点按钮。
        # 使用说明第 3 步指的就是这张卡，而它从来没有在真浏览器里被看过一眼：
        # 卡片出不出来、按钮上写什么，全靠读 options.js 推。
        # 这个项目在「那张卡根本不出现，于是交接里让他做的事做不了」上栽过一次。
        if not problems:
            await asyncio.sleep(1)
            async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
                rpc = await _rpc_factory(ws)
                await rpc("Target.createTarget",
                          {"url": f"chrome-extension://{extension_id}/options.html"})
            await asyncio.sleep(4)
            targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
            pages = [t for t in targets if t.get("type") == "page"
                     and "options.html" in t.get("url", "")]
            if not pages:
                problems.append("设置页打不开——使用说明第 3 步指的就是它")
            else:
                async with websockets.connect(pages[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await _rpc_factory(ws)
                    await rpc("Runtime.enable")
                    card = await rpc("Runtime.evaluate", {
                        "expression": OPTIONS_PROBE, "returnByValue": True, "timeout": 20000})
                    value = card.get("result", {}).get("result", {}).get("value")
                    measured["options_card"] = json.loads(value) if value else {"error": "空"}
            # 弹窗那一页
            async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
                rpc = await _rpc_factory(ws)
                await rpc("Target.createTarget",
                          {"url": f"chrome-extension://{extension_id}/popup.html"})
            await asyncio.sleep(4)
            targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
            popups = [t for t in targets if t.get("type") == "page"
                      and "popup.html" in t.get("url", "")]
            if popups:
                async with websockets.connect(popups[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await _rpc_factory(ws)
                    await rpc("Runtime.enable")
                    got = await rpc("Runtime.evaluate", {
                        "expression": POPUP_PROBE, "returnByValue": True, "timeout": 20000})
                    value = got.get("result", {}).get("result", {}).get("value")
                    measured["popup"] = json.loads(value) if value else {"error": "空"}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        bili.shutdown()
        api.shutdown()
        shutil.rmtree(workspace, ignore_errors=True)

    verify = measured.get("verify") or {}
    if not verify.get("ok"):
        problems.append(
            f"**「我已登录，继续」这一步没成**：{verify.get('failureCode')} / {verify.get('error')}"
            "——账号建不起来，后面整条都跑不了")
    if verify.get("failureCode") == "LOGIN_PROOF_UNAVAILABLE":
        problems.append("还是那句 LOGIN_PROOF_UNAVAILABLE —— 登录态确认根本没接上")

    account = (received["accounts"] or [{}])[0]
    if account.get("external_account_id") != "1919810":
        problems.append(f"账号标识不是 B 站的 mid（拿到 {account.get('external_account_id')!r}）"
                        "——换个昵称就会变成另一个账号")
    blob = json.dumps(account.get("metadata") or {}, ensure_ascii=False).lower()
    for word in ("cookie", "token", "password", "auth_header", "sessdata"):
        if word in blob:
            problems.append(f"**账号元数据里出现了 {word}** —— 那会进运行日志")

    items = [item for batch in received["batches"] for item in (batch.get("items") or [])]
    if len(items) != 3:
        problems.append(f"档案馆只收到 {len(items)} 条，应该是 3 条")
    bad = [i.get("url") for i in items
           if not str(i.get("url", "")).startswith("https://www.bilibili.com/video/BV")]
    if bad:
        problems.append(f"**有条目的网址不是能打开的网址**：{bad[:3]}"
                        "——多半是拿 media.link 那个 bilibili:// 深链当网址用了")
    if len({i.get("collection_key") for i in items}) != 2:
        problems.append("条目没有正确归到两个收藏夹上")
    finals = [b for b in received["batches"] if b.get("scope_type") == "relation"]
    if not finals:
        problems.append("没有发出关系级终批 —— 这次同步永远收敛不了")
    elif finals[-1].get("completeness") != "complete":
        problems.append(f"终批不是 complete：{finals[-1].get('completeness')} / "
                        f"{finals[-1].get('failure_code')}")
    # 扫描范围必须只有 favorite：B 站声明四种关系，另外三种没有取数路
    scoped = [b.get("relation_type") for b in received["batches"]]
    if set(scoped) - {"favorite"}:
        problems.append(f"扫描范围超出了本版本能读的关系：{sorted(set(scoped))}")

    # **定时同步不许抢他正在看的那一页。**
    #
    # 这条是 2026-08-06 读代码看出来、再用这个演练量实的：
    # runBrowserAccountSync 建标签页用的是 `active: true`，
    # navigateMirrorTab 又用 `chrome.tabs.update(tabId, { url, active: true })`
    # 把它导航到收藏夹页并切到前台。自动同步每 6 小时一次——
    # **等于每 6 小时抢一次他的屏幕**，而他什么都没点。
    #
    # 取数改成调接口之后，那次导航连必要性都没有了：我们只需要一个
    # bilibili 源的标签页，不需要它停在收藏夹页上，更不需要它在前台。
    if measured.get("still_looking_at_my_tab") is False:
        active = next((t for t in (measured.get("tabs_after") or []) if t.get("active")), {})
        problems.append(
            f"**同步把他正在看的那一页抢走了**（跳到 {str(active.get('url'))[:60]!r}）"
            "——定时同步每 6 小时跑一次，他什么都没点")
    if (measured.get("tabs_created_by_sync") or 0) > 0:
        problems.append(f"同步凭空开了 {measured['tabs_created_by_sync']} 个标签页")

    # **首次同步是不是真的被排上了。**
    # 他点完「我已登录，继续」看到的是「正在后台读取你的收藏夹」——
    # 这句话背后必须真有一个任务在队列里、且有闹钟会来取它。
    if not measured.get("queue_before"):
        problems.append("**连接成功后队列是空的** —— 界面说「正在后台读取」，"
                        "而其实没有任何任务被排上，他会一直等下去")
    if not measured.get("alarm_scheduled"):
        problems.append("**没有排上周期闹钟** —— MV3 里 worker 随时会被杀，"
                        "没有闹钟就没有任何东西会再来唤醒队列")
    if measured.get("queue_after"):
        problems.append(f"跑完之后队列里还剩 {len(measured['queue_after'])} 个任务没被取走")

    # 设置页那张卡：Owner 真正会点的地方
    card = measured.get("options_card") or {}
    if card and not card.get("error"):
        if not card.get("gridExists"):
            problems.append("**设置页上根本没有账号卡片区**——使用说明第 3 步无从做起")
        if not card.get("mentionsBilibili"):
            problems.append("**设置页上没有 B 站那张卡**——他找不到可以点的地方"
                            f"（卡片数 {card.get('cardCount')}）")
        buttons = card.get("biliButtons") or []
        if not card.get("anySyncButton") and "立即同步" not in buttons:
            problems.append(f"已连接的 B 站账号上没有「立即同步」按钮：{buttons}")
        # **卡片不许承诺这一版不会读的东西。**
        # 原来那张写死的散文表给 B 站写的是「收藏夹、稍后再看、历史、点赞」，
        # 而这一版只读收藏夹——他点「连接账号」时以为四样都会同步。
        text = str(card.get("biliCardText") or "")
        over = [word for word in ("稍后再看", "观看历史", "点赞") if word in text]
        if over:
            problems.append(f"**卡片承诺了这一版不会读的东西**：{over}（卡片原文：{text[:80]}）")

    # 弹窗：使用说明里两次指到它
    popup = measured.get("popup") or {}
    if popup and not popup.get("error"):
        if not popup.get("hasSettingsButton"):
            problems.append("弹窗上没有那颗「···」——使用说明第 3 步从这里进设置页")
        if not popup.get("hasSaveButton"):
            problems.append("**弹窗上没有「保存当前页面」**——七个平台只能靠它存东西")
        if popup.get("mentionsBilibiliCannotRead"):
            problems.append("**弹窗还在说 B 站的收藏列表读不了**——它已经读得了两个版本了")
        hint = str(popup.get("manageAccountsHint") or "")
        if "可自动同步" not in hint:
            problems.append(f"「连接与管理账号」那句没有照事实清单重写：{hint[:60]!r}")

    # **收藏夹的名字要真的送到服务端。**
    # 服务端建收藏夹记录的条件是 `if batch.collection_name:`——批次不带名字，
    # platform_collection 一行都不会建，「学习」「音乐」这些名字读到了却被丢在地上，
    # 库里只剩 collection_key="111" 这种媒体 id，他根本认不出那是哪个收藏夹。
    named = {b.get("collection_key"): b.get("collection_name")
             for b in received["batches"] if b.get("collection_key")}
    expected_names = {str(f["id"]): f["title"] for f in FOLDERS}
    if named != expected_names:
        problems.append(f"**收藏夹的名字没送到**：收到 {named}，应当是 {expected_names}"
                        "——他在库里只会看到一串媒体 id")
    # 每个收藏夹都该有自己的终批，否则单个收藏夹的完整性没有回执
    finals_by_collection = {b.get("collection_key") for b in received["batches"]
                            if b.get("collection_key") and not (b.get("items") or [])}
    if finals_by_collection != set(expected_names):
        problems.append(f"有收藏夹没有自己的终批：{sorted(set(expected_names) - finals_by_collection)}")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "task": "G3",
        "journey": measured,
        "account_created": account,
        "items_received": len(items),
        "item_urls": [i.get("url") for i in items],
        "collections": sorted({i.get("collection_key") for i in items}),
        "batches": [{"relation": b.get("relation_type"), "scope": b.get("scope_type"),
                     "items": len(b.get("items") or []), "completeness": b.get("completeness"),
                     "failure_code": b.get("failure_code")} for b in received["batches"]],
        "bilibili_endpoints_called": sorted(set(received["requests"])),
        "problems": problems,
        "what_this_does_not_prove": (
            "对面是本机固定装置，不是真 B 站——「B 站真的会那样回」由 "
            "bilibili_acquisition_drill.py 打真接口去证。"
            "另外**没有验权限授予那一下**：演练点不了 chrome.permissions.request 的弹窗，"
            "所以加载前把 bilibili 的 host 权限从可选挪成了必需。"
            "那一下由 Owner 在设置页点「连接账号」时给。"
        ),
    }
    out_path = ROOT / "evidence/G3/END_TO_END_RUN.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="B 站：从连接账号到档案馆里有条目，整条跑一遍")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    # **他真正拿到的是下载页发的那个 zip，不是仓里的源码目录。**
    # 这个仓已经栽过一次「47 道门全在验暂存目录，从没人打开过最终那个 zip」——
    # 改成回读自验证之后第一次跑就抓到 283 个中文名乱码。
    parser.add_argument("--ext-dir", default=None,
                        help="用这个目录当扩展（默认是仓里的源码目录）。"
                             "把生产下发的 zip 解开指到这里，验的才是他真正装的那份。")
    args = parser.parse_args()
    source = Path(args.ext_dir).resolve() if args.ext_dir else EXT_SRC
    if not source.is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING",
                          "path": str(source)}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, source))


if __name__ == "__main__":
    sys.exit(main())
