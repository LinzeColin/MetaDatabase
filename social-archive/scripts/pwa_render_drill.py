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
    "/v1/library": {"items": [], "total": 0,
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
  collectionOptions: [...(document.getElementById("collectionFilter")?.options || [])]
    .map(o => ({ value: o.value, text: o.textContent })),
    relationOptions: [...(document.getElementById("relationFilter")?.options || [])]
                       .map(o => o.value + "=" + o.textContent),
    cardCount: cards.length,
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
    topics = list(measured.get("topicOptions") or [])
    if topics and "未分类" not in topics:
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
        "privacy_note_class_present": measured.get("hasPrivacyClass"),
        "problems": problems,
        # **量到的东西要印出来。** 不印的话，"通过了"和"根本没量"长得一样——
        # 我自己就先按一个不存在的键去读，读出 null 还以为是没量到。
        "guide_page": guide_reading,
        "all_accounts_disconnected": disconnected_reading,
        "rendered_text": text[:400],
        # 同步中心那句限定语，**照原样印出来**：它是这次要亲眼看见的东西之一。
        "sync_centre_header": str(measured.get("syncHeader") or "").replace("\n", " ")[:200],
        "topic_options": measured.get("topicOptions"),
        "relation_options": measured.get("relationOptions"),
        "service_badge": measured.get("serviceBadge"),
        "collection_filter_hidden": measured.get("collectionFieldHidden"),
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
