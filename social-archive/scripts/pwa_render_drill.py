#!/usr/bin/env python3
"""档案馆页面上，那两段话真的显示出来了吗（v0.0.0.7 / T11）。

## 为什么补这个

2026-08-05 修了两处「界面不显示服务端说的话」：
覆盖差额（「还有 192 条从来没送到这里」）和八条隐私说明（东西去了哪、钥匙在谁手里）。

两处都核到**字段进了接口负载、两个界面的源码都读它**为止，
然后在证据里如实写了一句：**没有在真浏览器里看见它们渲染出来**。

那句话是诚实的，但挂着不查就是留给下一个人踩。这个演练把它查了。

## 它怎么验

起一个假档案馆：静态文件直接喂 `apps/pwa/`，接口按最小形状回假数据
（`/v1/auth/me` 通了才不会被登录墙挡住）。然后用真 Chrome 打开，
**把渲染出来的 DOM 读回来**，看那两段话在不在卡片里。

## 结果（2026-08-05）

四句全部在真 Chrome 的 DOM 里读到了，`.privacy-note` 也在，
连「把没送过去的 192 条补上」那颗按钮一起画了出来。**那句诚实的话可以撤了。**

反面也验过：把 app.js 里三处渲染分别改坏（不画隐私说明 / 不画覆盖 /
把差额那一句的读取换成一个不存在的字段），这个演练三次全红，
而且每次点的都是被改坏的那一处。改完即刻还原。

## 它第一次跑是红的，而那是**我的夹具错了**

第一版按 URL 去磁盘上找 `apps/pwa/assets/app.js`——那个目录不存在。
真服务端是把 `apps/pwa/` 整个平挂在 `/assets` 下的（api.py:1215）。
主脚本 404，页面一个接口都没请求，报出来却只有一句「0 张卡都没渲染」。

**「界面没画出来」和「界面根本没跑起来」长得一模一样。**
差点据此说产品有毛病。所以现在多了两样东西：`endpoints_asked`
记下页面问了哪几个接口，以及 `APP_SCRIPT_NEVER_SERVED` 这个单独的出口——
主脚本没送出去时它明说是夹具的问题，不混进产品缺陷里。

## 边界

· 一次性 profile，跑完删；只连 127.0.0.1；不碰生产、不碰任何真实账号。
· 假数据是**最小形状**，不是真实数据。它证明的是「这一段会被画出来」，
  不是「画出来的数是对的」。
· 夹具里 `last_message_zh` 和 `next_action_zh` 都填了差额那句（服务端两处都写）。
  所以它验不出「服务端只写了其中一个」那种回归——那条钉在
  `tests/focused/test_a_gap_in_coverage_is_not_reported_as_fine.py`（两个字段各断言一次）。
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

ROOT = Path(__file__).resolve().parents[1]
PWA = ROOT / "apps/pwa"
PORT = 8765

# 同步中心的抬头（2026-08-06）：它此前承诺「自动全量导入」，
# 而九个平台里八个不能自动同步。改成照实说之后，**同样要亲眼看见它画出来**——
# 那句话是静态 HTML，但「在文件里」和「在页面上」是两件事，这一整天都在拆这个。
# 同步中心那段话现在是**照接口现算的**，不再是写死的一句。
# 所以这里不再断言某一句字面，而是断言：
#   · 它把接口说能同步的那些点了名（B站）
#   · 它没有写死的排他句（那种句子一加平台就变成假话）
SYNC_HEADER_MUST_NAME = "B站"
SYNC_HEADER_MUST_NOT_SAY = ("只有 Chrome 书签", "其余平台的自动读取还没接上")

COVERAGE = "已送到这里 1 / 193 条。"
GAP = "**还有 192 条从来没送到这里。**"
PRIVACY = "开锁用的令牌只存在你的服务器上，插件拿不到。"

FAKE: dict[str, object] = {
    # PWA_RENDER_FIXTURE：这一整块是**假接口的响应夹具**，不是平台表。
    # 里面出现哪几个平台只取决于"这一屏要验什么"，列全九个不会多验到任何东西。
    # /health 夹具（v0.0.0.18）。**worker 故意设成挂了**——
    # 这一栏存在的全部意义就是那种情况下界面说什么。
    # 设成活着的话，这条断言永远走不到它要验的那一支。
    "/health": {"status": "ok", "project": "Social Archive", "version": "9.9.9.9",
                "worker": {"ever_seen": True, "alive": False,
                           "last_seen_at": "2026-08-06T00:00:00Z",
                           "seconds_since": 9999.0,
                           "note": "worker 已经 9999 秒没动过——后台任务不会有人处理，"
                                   "而接口本身照样是好的。"}},
    "/v1/auth/me": {"user_id": "fixture", "display_name": "夹具用户"},
    "/v1/auth/providers": {"items": []},
    # **能同步的平台由接口下发**：同步中心那段话是照它现算的。
    # 以前那段话写死在 index.html 里（「本版本只有 Chrome 书签能自动读取」），
    # v0.0.0.21 起就成了假话——所以这里要给它真东西去算。
    "/v1/accounts": {"items": [], "supported_platforms": [
        {"platform": "bilibili", "relations": ["favorite"], "sync_supported": True,
         "not_syncable_reason": "", "server_handled": False, "connect_supported": True},
        {"platform": "x", "relations": ["bookmark"], "sync_supported": False,
         "not_syncable_reason": "本版本还不能自动读取 X 的书签。现在可以：在浏览器里打开任意一条推文，点插件的「保存当前页面」。",
         "server_handled": True, "connect_supported": False},
    ]},
    "/v1/sync-runs": {"items": []},
    "/v1/destinations": {"items": [{
        "destination_id": "obsidian", "display_name": "Obsidian", "state": "connected",
        "enabled": True, "configured": True, "authorized": True, "automatic": True,
        "exported_count": 1, "content_total": 193,
        "coverage_zh": COVERAGE,
        "last_message_zh": GAP,
        "next_action_zh": GAP,
        "privacy_note_zh": PRIVACY,
        "capabilities": {}, "last_checked_at": "2026-08-05T00:00:00Z",
    }]},
    # facets 带上一个真实形状的主题：**下拉框是照它重建的**，
    # 而 index.html 里写死的那五个（AI与技术/商业与投资/…）只是初始占位。
    # 2026-08-06 对着生产量过：那五个各返回 0 条，而 facets 里唯一的
    # 「未分类」是 193 条——静态那份从头到尾没有一个能选出东西来。
    # **夹具里必须有一条"没有标题"的**：Owner 库里 193 条有 6 条是这样
    # （archive_status 是「完整」，title 是空的）。没有它，那条兜底永远验不到。
    "/v1/library": {"items": [
        {"id": "cnt_no_title", "platform": "douyin", "title": "",
         "canonical_url": "https://www.douyin.com/video/7584040037701733683?source=Baidu",
         "archive_status": "视频没存下", "primary_relation": "favorite",
         "relations": ["favorite"], "collections": [], "export_destinations": [],
         "media_count": 0, "artifact_count": 0},
    ], "total": 1,
                    "facets": {"platforms": [],
                               # 关系 facet：**「观看历史」此前不在写死的四个里**，
                               # 而它是 Owner 库里最大的一组（193 条里 71 条）。
                               "relations": [{"relation": "history", "count": 71},
                                             {"relation": "favorite", "count": 46},
                                             {"relation": "saved", "count": 5}],
                               "topics": [{"topic": "未分类", "count": 193}],
                               # 收藏夹分面（v0.0.0.10）。key 是库里存的媒体 id，
                               # label 是给人看的名字——**筛选必须用 key**，
                               # 用 label 去筛什么都筛不出来。
                               "collections": [{"key": "111", "label": "学习", "count": 2},
                                               {"key": "222", "label": "音乐", "count": 1}]}},
    "/v1/status": {"connectors": [], "destinations": []},
}


# 页面到底问了哪几个接口。**「一张卡都没有」和「压根没走到那一步」长得一样**，
# 这份清单是分开它们的唯一办法。
asked: list[str] = []
served: list[str] = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        return

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path.startswith("/v1/"):
            asked.append(path)
        for prefix, payload in FAKE.items():
            if path == prefix or path.startswith(prefix + "/"):
                self._send(200, json.dumps(payload, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
        if path.startswith("/v1/"):
            self._send(200, b'{"items": []}', "application/json")
            return
        # **真服务端把 apps/pwa/ 整个挂在 /assets 下**（api.py:1215
        # `app.mount("/assets", StaticFiles(directory=pwa_root))`），目录是平的。
        # 第一版照着 URL 去找 apps/pwa/assets/app.js，**整个脚本 404**，
        # 于是页面一个接口都没请求——报出来却只是一句「0 张卡」。
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        # 真服务端有一条 `/guide` 路由（api.py），映到 guide.html。
        # **假服务端要跟着映**，否则这里 404 而生产上是好的——
        # 那种差异会让演练验的是一个他那边不存在的形状。
        if name == "guide":
            name = "guide.html"
        if name.startswith("assets/"):
            name = name[len("assets/"):]
        target = PWA / name
        if target.is_file():
            served.append(name)
        if not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        kind = ("text/html; charset=utf-8" if target.suffix == ".html"
                else "text/css" if target.suffix == ".css"
                else "application/javascript" if target.suffix == ".js"
                else "application/octet-stream")
        self._send(200, target.read_bytes(), kind)


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

READ_DOM = r"""
(() => {
  const cards = [...document.querySelectorAll(".destination-live-card")];
  return JSON.stringify({
    _bodyStart: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 220),
    _modalBodyExists: !!document.getElementById("destinationsModalBody"),
    _modalBodyHtmlLen: (document.getElementById("destinationsModalBody") || {}).innerHTML?.length ?? -1,
    _errors: (window.__drillErrors || []).slice(0, 4),
    // **先打开同步中心再读**：那段话是打开时现算的（paintSyncModalCopy）。
    // 不打开就读，读到的是 index.html 里那个占位句——而判据会以为它没渲染。
    syncHeader: (() => {
      try { document.getElementById("emptyConnectAccount")?.click(); } catch (_) {}
      return (document.getElementById("syncModalCopy")?.innerText
              || document.getElementById("syncModalTitle")?.parentElement?.innerText || "");
    })(),
    topicOptions: [...(document.getElementById("topicFilter")?.options || [])].map(o => o.value),
  serviceBadge: (document.getElementById("serviceBadge") || {}).textContent || "",
  serviceBadgeClass: (document.getElementById("serviceBadge") || {}).className || "",
  collectionFieldHidden: Boolean(document.getElementById("collectionField")?.hidden),
  // 主题那一栏（2026-08-10）。夹具里 topics 只有「未分类」一个——
  // **那正是他生产库里的形状**（190 条 topic 全是它）。一个选项分不出两堆东西。
  topicFieldHidden: Boolean(document.getElementById("topicField")?.hidden),
  collectionOptions: [...(document.getElementById("collectionFilter")?.options || [])]
    .map(o => ({ value: o.value, text: o.textContent })),
    relationOptions: [...(document.getElementById("relationFilter")?.options || [])]
                       .map(o => o.value + "=" + o.textContent),
    cardCount: cards.length,
    // **内容条目的标题原样取回来。**
    //
    // 上面那个 `cards` 是 `.destination-live-card`（目的地卡片），
    // 不是内容——我第一版拿它去验标题，读回来的是「Obsidian」，
    // 反例当然不会红。**判据指错了对象。** 内容在 #tableBody 的行里。
    itemRowsRaw: [...document.querySelectorAll("#tableBody tr")]
      .map(row => (row.innerText || "").replace(/\s+/g, " | ").slice(0, 140)),
    // 整张卡的可见文字——那两段话必须在里面
    text: cards.map(c => c.innerText).join("\n---\n").slice(0, 1200),
    hasPrivacyClass: !!document.querySelector(".destination-live-card .privacy-note"),
  });
})()
"""


async def run(chrome: str) -> int:
    if not (PWA / "index.html").is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PWA_MISSING"}, ensure_ascii=False))
        return 2
    profile = Path(tempfile.mkdtemp(prefix="sa-pwa-profile-"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", "--remote-debugging-port=9359",
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--password-store=basic",
         "--use-mock-keychain", f"http://127.0.0.1:{PORT}/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9359"
    measured: dict = {}
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
        await asyncio.sleep(4)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page" and f"127.0.0.1:{PORT}" in t["url"]]
        if not pages:
            print(json.dumps({"status": "FAIL", "error_code": "PAGE_NOT_OPEN"}, ensure_ascii=False))
            return 4
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            await rpc("Page.enable")
            # 报错收集器必须在页面脚本之前装上，所以走 addScriptToEvaluateOnNewDocument + 重载。
            await rpc("Page.addScriptToEvaluateOnNewDocument", {"source": COLLECT_ERRORS})
            await rpc("Page.reload", {"ignoreCache": True})
            await asyncio.sleep(4)
            result = await rpc("Runtime.evaluate", {"expression": READ_DOM, "returnByValue": True})
            guide_reading = None
            disconnected_reading = None
            reconnected_reading = None
            running_reading = None
            finished_reading = None
            never_completed_reading = None
            drawer_reading = None
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                measured = {"error": str(payload["exceptionDetails"])[:300]}
            else:
                measured = json.loads(payload["result"]["value"])

            # **第二遍：三个账号全断开。**
            #
            # 2026-08-07 读生产看到的 Owner 实况：三个账号全是 disconnected，
            # 而 8/3 那晚它们真的自动同步进来过 260 条。这一屏当时对他说的是
            # 「0 个账号已连接 · 首次同步尚未开始」——**后半句直接和他的数据矛盾**。
            #
            # 夹具默认是"一个账号都没有"，走的是另一条路；不换一遍就永远验不到
            # 他真正会看到的那一屏。
            FAKE["/v1/accounts"] = {                      # noqa: PLW2901
                "items": [
                    {"id": f"acct-{i}", "platform": platform, "display_name": name,
                     "connection_state": "disconnected", "content_count": count,
                     "auto_sync_enabled": False}
                    for i, (platform, name, count) in enumerate(  # POPUP_STATE_FIXTURE
                        [("xiaohongshu", "我", 1), ("douyin", "我的", 86),
                         ("bilibili", "B站账号", 103)])],
                "supported_platforms": FAKE["/v1/accounts"]["supported_platforms"],
            }
            await rpc("Page.reload", {"ignoreCache": True})
            await asyncio.sleep(4)
            got = await rpc("Runtime.evaluate", {"expression": r"""
              JSON.stringify({
                count: (document.getElementById("connectedAccountCount")||{}).textContent||"",
                summary: (document.getElementById("syncSummaryText")||{}).textContent||"",
              })""", "returnByValue": True})
            disconnected_reading = json.loads(got["result"]["result"]["value"])

            # **他重新连上账号的那一刻，顶部那一条会说什么。**（2026-08-10）
            #
            # 那一整段只在「有账号连着」时才走到，所以他一连成功就会撞上它。
            # 而它挑的是全量历史里的失败 run——Owner 库里躺着 8 月 3–4 号那三次
            # `status=failed`，错误码 `SYNC_RUN_ABANDONED` 在 PWA 本地词典里
            # **查不到**，于是落到兜底那句「没有取到任何内容…没能记录下原因」。
            # 两句都假：那批 run 入过库，原因也记着，服务端还把正确的一句
            # （message_zh）一起下发了。
            #
            # 判据在源码层已经有一道（test_the_top_line_uses_the_sentence_the_server_computed），
            # 但**源码层通过不算数**——这里要看那一行真渲染成什么。
            FAKE["/v1/accounts"] = {                      # PWA_RENDER_FIXTURE
                "items": [{"id": "acct_bili", "platform": "bilibili",
                           "display_name": "B站", "connection_state": "connected",
                           "auto_sync_enabled": True, "last_sync_at": "",
                           "content_count": 103}],
                "supported_platforms": FAKE["/v1/accounts"]["supported_platforms"],
            }
            FAKE["/v1/sync-runs"] = {"items": [{
                "id": "sync_old", "source_account_id": "acct_bili",
                "platform": "bilibili", "status": "failed",
                "last_error_code": "SYNC_RUN_ABANDONED",
                "imported_count": 35, "discovered_count": 35,
                "updated_at": "2026-08-04T08:06:00Z",
                # 服务端算好的那一句，照 failure_copy.py 的原话。
                "message_zh": "这次同步卡住了，没有正常结束。你已经取到的内容都还在。",
                "action_zh": "重试", "outcome": "incomplete",
            }]}
            await rpc("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
            await asyncio.sleep(3)
            got = await rpc("Runtime.evaluate", {"expression": r"""
              JSON.stringify({
                strip: (document.getElementById("syncSummaryText") || {}).textContent || "",
                head: (document.getElementById("connectedAccountCount") || {}).textContent || "",
              })""", "returnByValue": True})
            reconnect_payload = got.get("result", {})
            reconnected_reading = ({"error": str(reconnect_payload["exceptionDetails"])[:200]}
                                   if reconnect_payload.get("exceptionDetails")
                                   else json.loads(reconnect_payload["result"]["value"]))

            # **他重连之后、第一次完整同步之前那一屏。**（2026-08-10）
            #
            # 他从来没有过一次 completed（生产 20 次同步：partial 16 / failed 3 /
            # cancelled 1），而 `last_sync_at` 只在完整跑完时才写——所以那个字段
            # 对他永远是空的。这一支于是落到
            #     state.total ? 「已存下的内容都在…」 : 「首次同步尚未开始」
            # 而 `state.total` 是 loadLibrary 设的，顶部那一条却是
            # loadAccountsAndDestinations 画的，**画的时候它还是 0**。
            FAKE["/v1/accounts"]["items"][0]["connection_state"] = "connected"
            FAKE["/v1/accounts"]["items"][0]["last_sync_at"] = ""
            FAKE["/v1/sync-runs"] = {"items": [{
                "id": "sync_partial", "source_account_id": "acct_bili",
                "platform": "bilibili", "status": "partial",
                "last_error_code": "", "imported_count": 30, "discovered_count": 30,
                "updated_at": "2026-08-10T02:30:00Z",
                "message_zh": "", "action_zh": "", "outcome": "incomplete",
            }]}
            await rpc("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
            await asyncio.sleep(3)
            got = await rpc("Runtime.evaluate", {"expression": r"""
              JSON.stringify({
                strip: (document.getElementById("syncSummaryText") || {}).textContent || "",
                rows: document.querySelectorAll("#tableBody tr").length,
              })""", "returnByValue": True})
            never_completed_payload = got.get("result", {})
            never_completed_reading = (
                {"error": str(never_completed_payload["exceptionDetails"])[:200]}
                if never_completed_payload.get("exceptionDetails")
                else json.loads(never_completed_payload["result"]["value"]))

            # **同步跑起来的那一刻、和跑完之后，这一条说什么。**（2026-08-10）
            #
            # 整条 B 站链有演练（bilibili_end_to_end_drill），但它验的是**数据**：
            # mid 是不是真的、条目落没落库、终批 complete、没多开标签页。
            # 而资料库这一页在同步进行中/完成后说的那句话，**从没被渲染出来读过**——
            # 今天四处缺陷全出在"没人读渲染出来的字"这一类上。
            FAKE["/v1/sync-runs"] = {"items": [{
                "id": "sync_live", "source_account_id": "acct_bili",
                "platform": "bilibili", "status": "scanning",
                "imported_count": 12, "discovered_count": 30,
                "updated_at": "2026-08-10T02:40:00Z",
                "message_zh": "", "action_zh": "", "outcome": "running",
            }]}
            await rpc("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
            await asyncio.sleep(3)
            got = await rpc("Runtime.evaluate", {"expression": r"""
              JSON.stringify({
                strip: (document.getElementById("syncSummaryText") || {}).textContent || "",
                head: (document.getElementById("connectedAccountCount") || {}).textContent || "",
              })""", "returnByValue": True})
            running_payload = got.get("result", {})
            running_reading = ({"error": str(running_payload["exceptionDetails"])[:200]}
                               if running_payload.get("exceptionDetails")
                               else json.loads(running_payload["result"]["value"]))

            # 跑完之后：**完整跑完才会写 last_sync_at**（account_sync.py 里那两处
            # UPDATE 都挂在 final_status == "completed" 上）。这里给它一个，
            # 看那一条会不会改口说「最近同步 …」。
            FAKE["/v1/accounts"]["items"][0]["last_sync_at"] = "2026-08-10T02:45:00Z"
            FAKE["/v1/sync-runs"] = {"items": [{
                "id": "sync_done", "source_account_id": "acct_bili",
                "platform": "bilibili", "status": "completed",
                "imported_count": 30, "discovered_count": 30,
                "updated_at": "2026-08-10T02:45:00Z",
                "message_zh": "新增 30 条。", "action_zh": "", "outcome": "ok",
            }]}
            await rpc("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
            await asyncio.sleep(3)
            got = await rpc("Runtime.evaluate", {"expression": r"""
              JSON.stringify({
                strip: (document.getElementById("syncSummaryText") || {}).textContent || "",
                head: (document.getElementById("connectedAccountCount") || {}).textContent || "",
              })""", "returnByValue": True})
            done_payload = got.get("result", {})
            finished_reading = ({"error": str(done_payload["exceptionDetails"])[:200]}
                                if done_payload.get("exceptionDetails")
                                else json.loads(done_payload["result"]["value"]))

            # **他点开一条内容来读的那一屏。**（2026-08-10）
            #
            # `grep -rn drawer scripts/*_drill.py` 当时是空的——**看见条目之后
            # 最可能做的那一下，从没在真浏览器里被打开过**。而今天五处缺陷
            # 全出在"没人读渲染出来的字"这一类上。
            #
            # 夹具那一条是**没有标题**的（Owner 库里 193 条有 6 条这样）：
            # 表格那一侧用链接尾巴兜底，抽屉这一侧要跟着，不能是一片空白。
            got = await rpc("Runtime.evaluate", {"expression": r"""(() => {
                const row = document.querySelector("#tableBody tr[data-row-id]");
                if (!row) return JSON.stringify({ opened: false, why: "表里一行都没有" });
                // **列表那一格先读，再点开抽屉。** 他先看到的是列表；
                // 两处调同一个 archiveLabel()，但"同一个函数"不等于两处都渲染对——
                // 这个仓今天反复栽在"由构造保证"上。
                const cell = row.querySelector(".col-archive");
                const listArchive = cell ? cell.textContent.trim() : "";
                row.click();
                const pick = id => (document.getElementById(id) || {}).textContent || "";
                const backdrop = document.getElementById("drawerBackdrop");
                return JSON.stringify({
                  opened: !!backdrop && backdrop.classList.contains("open"),
                  listArchive,
                  title: pick("drawerHeaderTitle"),
                  meta: pick("drawerHeaderMeta"),
                  body: pick("drawerContent").replace(/\s+/g, " ").slice(0, 300),
                });
            })()""", "returnByValue": True, "userGesture": True})
            drawer_payload = got.get("result", {})
            drawer_reading = ({"error": str(drawer_payload["exceptionDetails"])[:200]}
                              if drawer_payload.get("exceptionDetails")
                              else json.loads(drawer_payload["result"]["value"]))

            # **顺路把使用说明那一页也打开看一眼。**
            #
            # 2026-08-07 之前那份说明躺在 git 工作树里，他打不开——每次要装、
            # 要连都是我在聊天里现敲步骤。现在有了 `/guide`，就得有东西证明
            # 它**在浏览器里真的渲染出来了**，而不只是"文件生成了、判据绿了"。
            # 尤其要看横向溢出：里面有两张表，表一旦撑破就没法读。
            await rpc("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/guide"})
            await asyncio.sleep(2)
            got = await rpc("Runtime.evaluate", {"expression": r"""
              JSON.stringify({
                h1: (document.querySelector("h1") || {}).textContent || "",
                sections: document.querySelectorAll("h2").length,
                tables: document.querySelectorAll("table").length,
                text_length: (document.body.innerText || "").length,
                overflows_sideways:
                  document.documentElement.scrollWidth > window.innerWidth + 1,
                back_link: (document.querySelector("a.back") || {}).getAttribute
                  ? document.querySelector("a.back").getAttribute("href") : null,
                leftover_markdown: /\*\*|^\s*\|/m.test(document.body.innerText || ""),
              })""", "returnByValue": True})
            guide_payload = got.get("result", {})
            guide_reading = ({"error": str(guide_payload["exceptionDetails"])[:200]}
                             if guide_payload.get("exceptionDetails")
                             else json.loads(guide_payload["result"]["value"]))
    finally:
        server.shutdown()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    text = str(measured.get("text") or "")
    problems: list[str] = []
    if "app.js" not in served:
        # **这不是「界面没画」，是「界面根本没跑」。** 两者报成同一句话，
        # 就会把自己的夹具错读成产品缺陷——这一条就是那次误读换来的。
        print(json.dumps({"status": "FAIL", "error_code": "APP_SCRIPT_NEVER_SERVED",
                          "served": served, "endpoints_asked": asked,
                          "message_zh": "页面主脚本一次都没被请求到——**这不是通过也不是产品缺陷**，"
                                        "是这个假服务端没把它喂出去。"}, ensure_ascii=False))
        return 4
    # **没有标题的那条，卡片上要能认得出是哪一条。**
    #
    # 2026-08-07 把他生产库 193 条全拉下来看：6 条 title 是空的，
    # 而 archive_status 是「完整」。原来兜底成一句固定的「无标题内容」——
    # 六张卡片长得一模一样，他要么全点开，要么当它们不存在。
    rows_raw = measured.get("itemRowsRaw") or []
    if rows_raw and any("无标题内容" in row for row in rows_raw):
        problems.append(
            "**没有标题的条目显示成「无标题内容」**——他库里有 6 条是这样，"
            "六行长得一模一样，他分不出哪行是哪条。用链接的尾巴认人。")
    if rows_raw and not any("douyin.com/video/7584040037701733683" in row for row in rows_raw):
        problems.append(
            f"没有标题的那条，行里认不出是哪一条：{rows_raw!r}")
    if not measured.get("cardCount"):
        problems.append("**一张目的地卡片都没渲染出来**——那这次什么都没验到")
    if COVERAGE not in text:
        problems.append(f"覆盖那一句没显示：{COVERAGE}")
    if "还有 192 条从来没送到这里" not in text:
        problems.append("**差额那句没显示**——服务端说了实话，界面照旧报平安")
    if PRIVACY not in text:
        problems.append("**隐私说明没显示**——八条写了没人看，正是它当初的毛病")
    relations = list(measured.get("relationOptions") or [])
    if relations and not any(r.startswith("history=") for r in relations):
        problems.append(f"**关系筛选没有照数据重建**：{relations}——夹具里最大的一组是 history")
    if any("观看历史" not in r for r in relations if r.startswith("history=")):
        problems.append("关系筛选里 history 没有显示成中文")
    # **这条 2026-08-10 加了前提，而不是删掉。**
    #
    # 它原来要求「主题下拉必须含有夹具里那个主题」，防的是 index.html 里写死
    # 五个各返回 0 条的假主题。那件事仍然要防。
    # 但夹具（＝生产的形状）里只有「未分类」一个主题，而**一个选项分不出两堆
    # 东西**——那一栏现在整个藏起来，下拉里就只剩 'all'。
    # 两条规矩不冲突：**有两个以上主题时照数据重建；不足两个时整栏藏起来。**
    # 差点把这条老判据直接删掉——它挡的是另一件事，删了那件事就没人管了。
    topics = list(measured.get("topicOptions") or [])
    hidden = measured.get("topicFieldHidden")
    if hidden is None:
        problems.append("**没量到主题那一栏藏没藏**——这不是通过，是这一段没跑到")
    elif not hidden and topics and "未分类" not in topics:
        problems.append(f"**主题下拉没有照数据重建**：{topics}——夹具里只有「未分类」")
    stale = [x for x in topics if x in ("AI与技术", "商业与投资", "机械制造", "学习研究", "生活方式")]
    if stale:
        problems.append(f"**下拉里还留着写死的假主题**：{stale}。生产实测它们各返回 0 条。")
    # 后台没在跑时，那颗徽章不许还说「已连接」（v0.0.0.18）。
    # 夹具把 worker 设成挂了，所以这里必须看到那句新话。
    badge = str(measured.get("serviceBadge") or "")
    if "已连接" in badge:
        problems.append(f"**后台没在跑，徽章还说「{badge}」**"
                        "——他点同步、任务排队、什么都不发生，而界面说一切正常")
    if "后台没在跑" not in badge:
        problems.append(f"徽章没说后台没在跑：{badge!r}")

    # 主题筛选（2026-08-10）。夹具里只有「未分类」一个主题——**生产就是这个形状**，
    # 190 条 topic 全是它。那一栏必须藏起来：两项选出来是同一批东西，
    # 摆在那儿就是一个点了没用的下拉框（和收藏夹同一条规矩）。
    #
    # **条件里要带上"到底有几个主题"。** 第一版写成「不是 hidden 就报」，
    # 于是我拿两个主题的夹具去验反例时，它照样喊「只有一个主题」——
    # 一条不看数量的规则，把该显示的那种情况也判死了。反例把它逼出来了。
    real_topics = [t for t in (measured.get("topicOptions") or []) if t != "all"]
    if measured.get("topicFieldHidden") is False and len(real_topics) < 2:
        problems.append(
            f"**分不出两堆东西，那个下拉框还摆在那儿**：{measured.get('topicOptions')}——"
            "「全部主题」和唯一那一项选出来是同一批，他点哪一项都一样")
    if measured.get("topicFieldHidden") is True and len(real_topics) >= 2:
        problems.append(
            f"**有 {len(real_topics)} 个主题却把那一栏藏了**：{real_topics}——"
            "该藏的是分不出东西的那种，不是所有情况")

    # 收藏夹筛选（v0.0.0.10）。夹具里有两个收藏夹，那一栏就该露出来并照数据重建。
    if measured.get("collectionFieldHidden"):
        problems.append("**有收藏夹却没有显示那一栏**——他看不到自己有哪些收藏夹，也就无从按收藏夹看")
    options = measured.get("collectionOptions") or []
    values = [item.get("value") for item in options]
    if values[:1] != ["all"] or sorted(values[1:]) != ["111", "222"]:
        problems.append(f"**收藏夹筛选没有照数据重建**：{values}")
    texts = " ".join(str(item.get("text") or "") for item in options)
    if "学习" not in texts or "音乐" not in texts:
        problems.append(f"**下拉里显示的不是收藏夹的名字**：{texts!r}——他看到的会是一串媒体 id")
    # **筛选值必须是 key，不是显示名。** 拿名字去筛，点了什么都筛不出来。
    if any(str(item.get("value")) in ("学习", "音乐") for item in options):
        problems.append("收藏夹筛选的取值用了显示名——库里存的是媒体 id，这样筛不出东西")
    header = str(measured.get("syncHeader") or "")
    for forbidden in SYNC_HEADER_MUST_NOT_SAY:
        if forbidden in header:
            problems.append(
                f"**同步中心的抬头里有写死的排他句**：「{forbidden}」——"
                "那种句子一加平台就变成假话，而它是他打开那一页第一眼看到的")
    if SYNC_HEADER_MUST_NAME not in header:
        problems.append(
            f"**同步中心的抬头没照接口点名能同步的平台**（找不到「{SYNC_HEADER_MUST_NAME}」）："
            f"{header[:120]!r}——那段话是照 /v1/accounts 现算的，"
            "算不出来说明它又退回成一句写死的话，或者根本没渲染")

    # 三个账号全断开那一屏
    if not disconnected_reading:
        problems.append("**「三个账号全断开」那一屏没量到**——这不是通过。")
    else:
        summary = disconnected_reading.get("summary", "")
        if "首次同步尚未开始" in summary:
            problems.append(
                "**账号断开、库里有内容，界面却说「首次同步尚未开始」**——"
                "那直接和他的数据矛盾（他库里 193 条，8/3 真的同步过）")
        if "一条都没少" not in summary:
            problems.append(
                f"断开那一屏没说清内容还在：{summary!r}——"
                "「未连接」很容易被读成「我的收藏没了」")
        if "重新连接" not in summary:
            problems.append(f"断开那一屏没说下一步该干什么：{summary!r}")
        count_line = disconnected_reading.get("count", "")
        if "个账号已断开" in summary and "个账号已断开" in count_line:
            problems.append(
                "首行和正文都在说「N 个账号已断开」——**重复会挤掉真正要说的话**")
        if "已连接" in count_line and count_line.startswith("0"):
            problems.append(
                f"首行还是「{count_line}」——真话，但对他没用："
                "他有三个账号躺在那儿，这一行该说的是那件事")

    # 他重新连上之后那一屏（2026-08-10）
    if not reconnected_reading:
        problems.append("**「刚重新连上」那一屏没量到**——这不是通过。")
    elif reconnected_reading.get("error"):
        problems.append(f"「刚重新连上」那一屏读失败：{reconnected_reading['error']}")
    else:
        strip = reconnected_reading.get("strip", "")
        if "没能记录下原因" in strip or "没有取到任何内容" in strip:
            problems.append(
                f"**他刚连成功，顶部就对他说了两句假话**：{strip!r}——"
                "那批 run 入过库（35 条），原因也记在 last_error_code 里，"
                "服务端还把正确的一句（message_zh）一起发过来了，是这一页自己丢掉的")
        if "这次同步卡住了" not in strip:
            problems.append(
                f"顶部没用服务端算好的那句话：{strip!r}——"
                "本地词典少了他真撞到过的三个码，绕过 runSentence 就会漏")

    # 重连之后、第一次完整同步之前（2026-08-10）
    if not never_completed_reading or never_completed_reading.get("error"):
        problems.append(f"**「重连后还没完整同步过」那一屏没量到**：{never_completed_reading}")
    else:
        strip = never_completed_reading.get("strip", "")
        rows = never_completed_reading.get("rows", 0)
        if "首次同步尚未开始" in strip:
            problems.append(
                f"**表里有 {rows} 行，顶部却说「首次同步尚未开始」**：{strip!r}——"
                "他从来没有过一次 completed，last_sync_at 对他永远是空的；"
                "这一条读的 state.total 是 loadLibrary 设的，而画它的时候还没设")
        if "已存下的内容都在" not in strip:
            problems.append(
                f"没说清东西还在：{strip!r}——"
                "他刚重连、还没跑完一次完整同步，这一屏该说的就是这件事")

    # 同步跑起来的那一刻（2026-08-10）
    if not running_reading or running_reading.get("error"):
        problems.append(f"**「同步进行中」那一屏没量到**：{running_reading}——这不是通过。")
    else:
        strip = running_reading.get("strip", "")
        if "正在运行" not in strip or "已导入" not in strip:
            problems.append(
                f"同步跑起来了，顶部却不说进度：{strip!r}——"
                "他点完「连接」最想知道的就是「它动没动」")
        if "12/30" not in strip:
            problems.append(
                f"进度不是接口给的那个数：{strip!r}（喂进去的是 imported=12 / discovered=30）——"
                "写死或算错的进度比没有进度更坏")

    # 跑完之后（2026-08-10）
    if not finished_reading or finished_reading.get("error"):
        problems.append(f"**「同步完成后」那一屏没量到**：{finished_reading}——这不是通过。")
    else:
        strip = finished_reading.get("strip", "")
        # **这一条是有来历的**：`last_sync_at` 只在完整跑完时才写，
        # 而实际发生过的是"跑完了、导进来 102 条、结局却是 partial"，
        # 于是那个字段永远是空的，这一句就永远说「首次同步尚未开始」——
        # **Owner 库里 193 条，它还这么说。** 现在给了 last_sync_at，
        # 它必须改口。
        if "首次同步尚未开始" in strip:
            problems.append(
                f"同步完整跑完了，顶部还在说「首次同步尚未开始」：{strip!r}——"
                "这直接和他的数据矛盾")
        if "最近同步" not in strip:
            problems.append(
                f"跑完了却不说什么时候跑的：{strip!r}——"
                "「上一次是什么时候」是他判断「要不要再点一次」的唯一依据")

    # 他点开一条来读的那一屏（2026-08-10）
    if not drawer_reading or drawer_reading.get("error"):
        problems.append(f"**抽屉那一屏没量到**：{drawer_reading}——这不是通过。")
    elif not drawer_reading.get("opened"):
        problems.append(f"点了一行，抽屉没打开：{drawer_reading}")
    else:
        title = drawer_reading.get("title", "")
        body = drawer_reading.get("body", "")
        if not title.strip():
            problems.append(
                "**没有标题的那条，抽屉标题是空的**——表格那一侧用链接尾巴兜底了，"
                "抽屉这一侧要跟着；他库里 193 条有 6 条没有标题")
        # **服务端说「视频没存下」，界面不许改口说「需要处理」。**
        #
        # 夹具这一条就是他那 33 条的状态（生产实测：193 条里 33 条是它）。
        # 上一版 archiveLabel 只认三个值，其余落到「需要处理」——一句听起来
        # 「你该去做点什么」的话，而平台挡了下载，他做不了任何事。
        # 说明书里还写着「资料库那一列会写『视频没存下』」。
        if "需要处理" in body:
            problems.append(
                f"**服务端说「视频没存下」，抽屉改口说「需要处理」**：{body[:160]!r}——"
                "他做不了任何事，而这句话在催他做事；说明书承诺的也是前一个词")
        if "视频没存下" not in body:
            problems.append(
                f"抽屉没把归档状态照实说出来：{body[:160]!r}")
        # **列表那一格也要说同一句话**——他先看到的是它，点开才是抽屉。
        listing = drawer_reading.get("listArchive", "")
        if listing != "视频没存下":
            problems.append(
                f"列表那一格写的是 {listing!r}，而服务端说的是「视频没存下」——"
                "说明书答应的也是后者（「资料库那一列会写『视频没存下』」）")

    # 使用说明那一页
    if guide_reading is None:
        problems.append("**使用说明那一页没量到**——这不是通过。")
    elif guide_reading.get("error"):
        problems.append(f"使用说明那一页读不了：{guide_reading['error']}")
    else:
        if not guide_reading.get("h1"):
            problems.append("**使用说明那一页是空的**——他点「怎么用」会看到一片白")
        if guide_reading.get("sections", 0) < 4:
            problems.append(
                f"使用说明只渲染出 {guide_reading.get('sections')} 个小节——"
                "那份说明有六节，少了说明转换掉了东西")
        if guide_reading.get("overflows_sideways"):
            problems.append("**使用说明那一页横向溢出**——里面那两张表撑破了，手机上没法读")
        if guide_reading.get("leftover_markdown"):
            problems.append("**使用说明那一页上有没转干净的 markdown**（`**` 或表格行）")
        if guide_reading.get("back_link") != "/":
            problems.append(f"使用说明那一页回不去资料库（返回链接={guide_reading.get('back_link')!r}）")
    measured["guide_page"] = guide_reading

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "cards_rendered": measured.get("cardCount"),
        # **量到的要印出来**：不印的话「通过了」和「根本没量」长得一样。
        "item_rows_raw": measured.get("itemRowsRaw"),
        "privacy_note_class_present": measured.get("hasPrivacyClass"),
        "problems": problems,
        # **量到的东西要印出来。** 不印的话，"通过了"和"根本没量"长得一样——
        # 我自己就先按一个不存在的键去读，读出 null 还以为是没量到。
        "guide_page": guide_reading,
        "all_accounts_disconnected": disconnected_reading,
        "just_reconnected": reconnected_reading,
        "never_completed": never_completed_reading,
        "detail_drawer": drawer_reading,
        "while_syncing": running_reading,
        "after_sync_finished": finished_reading,
        "rendered_text": text[:400],
        # 同步中心那句限定语，**照原样印出来**：它是这次要亲眼看见的东西之一。
        "sync_centre_header": str(measured.get("syncHeader") or "").replace("\n", " ")[:200],
        "topic_options": measured.get("topicOptions"),
        "relation_options": measured.get("relationOptions"),
        "service_badge": measured.get("serviceBadge"),
        "collection_filter_hidden": measured.get("collectionFieldHidden"),
        # **两个数一起印**：藏没藏，和下拉里到底有什么。只印结论的话，
        # 「藏起来了」会盖住「其实它该显示却没数据」这种情况。
        "topic_filter_hidden": measured.get("topicFieldHidden"),
        "collection_options": measured.get("collectionOptions"),
        # **失败时必须说清页面当时在干什么。** 只报一句「0 张卡」而不说
        # 页面报了什么错，下一个人还得把这一段重新查一遍。
        "page_said": {key.lstrip("_"): value for key, value in sorted(measured.items())
                      if key.startswith("_")},
        "endpoints_asked": asked,
        "what_this_does_not_prove": (
            "假数据是最小形状。这证明「这一段会被画出来」，不证明「画出来的数是对的」。"
        ),
    }, ensure_ascii=False))

    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验档案馆页面真的把那两段话画出来了")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
