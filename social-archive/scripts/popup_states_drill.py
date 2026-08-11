#!/usr/bin/env python3
"""弹窗那一屏，在三种状态下分别说什么（2026-08-07）。

## 为什么单挑这一屏

它是他点插件图标看到的第一样东西。而 2026-08-07 读生产才看清他的实况：
三个账号躺在库里（小红书「我」/ 抖音「我的」/ B 站），全是 `disconnected`，
8/3 那晚它们真的自动同步进来过 260 条。

**而这一屏对他说的是：**

    还没有连接平台账号
    连接一次账号后自动全量导入，不需要逐条点击。
    [连接第一个账号]

三句里两句是假的（他连过、也不是"第一个"），而且把他唯一要做的那件事
——重连一次——整个盖掉了。这和 v0.0.0.14 那次「小红书、抖音、B站、快手
的收藏列表现在还读不了」写死在页面上是同一族：**这一屏说的话不随他的状态走。**

## 它怎么验

真 Chrome、装**发布包原样解出来的那一份**、喂一个假档案馆，
逐个状态打开 popup.html 读回那三句话：

    从没连过     → 「还没有连接平台账号」+「连接第一个账号」
    连过后来断了 → 「N 个账号已断开」+ 内容还在 +「重新连接账号」
    连着         → 「N 个账号 · M 条内容」

**三种都要验。** 只验断开那一种的话，一个把所有状态都写成「已断开」的
实现也能过——那种实现对新用户是错的。

假 API 必须跑在 **8765**：manifest 的 host_permissions 里只给了这个端口。
（第一版我随手用了 8791，请求被 Chrome 挡掉，弹窗落进 catch 显示
「私人档案馆尚未连接」——**根本没走到要验的那条分支**，而它看起来只是"没通过"。）

    python3 scripts/popup_states_drill.py
## 它**也**读设置页那一屏（2026-08-11，中间查错了三次，记在这里）

同一天我在 `apps/pwa/app.js` 和 `apps/browser-extension/options.js` 各修了一处
「断开的账号也给一颗『立即同步』」。给这一处补真 DOM 证据时，反例连着三次不红，
每一次我都先怀疑产品，而三次全是**演练自己的毛病**：

1. 等待条件写成「等到有卡片」——9 张卡从一开始就在，读到的是账号加载**之前**
   的 DOM，正例反例同时为绿；
2. 假档案馆少了 `/v1/extension/bootstrap`，`checkService()` 不过就把 accounts
   清空并 return，那一屏永远是「从没连过」的样子；
3. ★ 最后一个也是最贵的：**这个演练装的是 `dist/social-archive-extension.zip`，
   不是源码目录**。我改了 `options.js` 却没重打包，于是"正例"和"反例"跑的是
   同一份旧代码——两次输出当然一模一样。

重打包之后 A/B 立刻分开了：

    改之前   小红书/抖音/B站  按钮 = ["立即同步", "断开连接"]   ← 点下去 422
    改之后   小红书/抖音/B站  按钮 = ["连接账号"]

所以这个演练现在**自己先重打包**（`build_extension_package.py`），
再验设置页那三张卡。

"""

from __future__ import annotations

import asyncio
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _drill_port  # noqa: E402

import websockets

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "dist" / "social-archive-extension.zip"
EVIDENCE = ROOT / "evidence" / "G2" / "POPUP_STATES.json"
# **必须是 8765**：manifest 的 host_permissions 只给了这个端口。
PORT = 8765
DEBUG_PORT = 9396

_state: dict = {"accounts": []}

# POPUP_STATE_FIXTURE：这不是平台表，是**造三个账号**用的夹具。
# 这个演练验的是三种状态下那三句话，和平台是谁无关；列全九个只会让它更慢，
# 不会多验到任何东西。
SUPPORT = [{"platform": p, "relations": ["favorite"], "sync_supported": True,
            "connect_supported": True}
           for p in ("xiaohongshu", "douyin", "bilibili")]  # POPUP_STATE_FIXTURE


def _accounts(connection_state: str) -> list[dict]:
    return [
        {"id": f"acct-{index}", "platform": platform, "display_name": name,
         "connection_state": connection_state, "content_count": count,
         "auto_sync_enabled": connection_state == "connected"}
        # POPUP_STATE_FIXTURE：照抄他生产库里那三个账号的形状（平台/显示名/条数），
        # 好让读回来的那句话就是他会看到的那句。
        for index, (platform, name, count) in enumerate(  # POPUP_STATE_FIXTURE
            [("xiaohongshu", "我", 1), ("douyin", "我的", 86), ("bilibili", "B站账号", 103)])  # POPUP_STATE_FIXTURE
    ]


class _Api(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:                 # noqa: A003
        return

    def _json(self, code: int, body: dict) -> None:
        blob = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self) -> None:                             # noqa: N802
        path = self.path.split("?")[0]
        if path == "/health":
            return self._json(200, {"status": "ok", "version": "0.0.0.22",
                                    "minimum_extension_version": "0.0.0.9",
                                    "worker": {"alive": True, "ever_seen": True}})
        if path == "/v1/accounts":
            return self._json(200, {"items": _state["accounts"],
                                    "supported_platforms": SUPPORT})
        # **同步记录照他生产库里的形状给。**（2026-08-10）
        #
        # 原来这里一律回 `{"items": []}`，于是侧边栏的 `everRan = runs.length > 0`
        # 永远是 false——**那一支从来没被走到过**，我给它写的自洽断言
        # 用反例一试就露馅：把 `everRan` 改成恒 false，输出一个字都不变。
        #
        # 他生产库里 20 次同步：partial 16 / failed 3 / cancelled 1，
        # **completed 是 0**。所以这里给一条 partial：有记录、但没有一次"完成"。
        # 侧边栏该说的是「现在没有正在跑的同步」，不是「还没有同步过」。
        if path == "/v1/sync-runs":
            return self._json(200, {"items": [{
                "id": "sync_partial", "source_account_id": "acct_bili",
                "platform": "bilibili", "status": "partial",
                "imported_count": 30, "discovered_count": 30,
                "updated_at": "2026-08-10T02:30:00Z",
                "message_zh": "", "action_zh": "", "outcome": "incomplete",
            }]})
        return self._json(200, {"items": []})


# 设置页那三张卡（他点「连接与管理账号」看到的那一屏）。
# **状态在 `.state` 上，不是 `.account-status`**——选择器写错过一次。
# 「这张卡有没有账号」看 `<small>` 里的显示名：修好之后有账号和没账号的卡
# 按钮是一样的（都只有「连接账号」），光看按钮分不出来，正对照会永远不成立。
OPTIONS_CARDS = r"""
(() => {
  const cards = [...document.querySelectorAll(".account-card")].map(c => ({
    title: c.querySelector(".account-title strong")?.textContent || "",
    who: (c.querySelector(".account-title small")?.textContent || "").trim(),
    buttons: [...c.querySelectorAll(".card-button")].map(b => (b.textContent || "").trim()),
  }));
  const mine = cards.filter(c => ["小红书", "抖音", "B站"].includes(c.title));
  return JSON.stringify({
    total: cards.length,
    cards: mine,
    with_an_account: mine.filter(c => c.who).length,
  });
})()
"""


async def _rpc_factory(ws):
    counter = {"n": 0}

    async def rpc(method, params=None):
        counter["n"] += 1
        await ws.send(json.dumps({"id": counter["n"], "method": method, "params": params or {}}))
        while True:
            got = json.loads(await ws.recv())
            if got.get("id") == counter["n"]:
                return got
    return rpc


READ = r"""JSON.stringify({
  title: (document.getElementById('summaryTitle')||{}).textContent||'',
  copy: (document.getElementById('summaryCopy')||{}).textContent||'',
  button: (document.getElementById('primarySyncLabel')||{}).textContent||'',
  // **账号卡片那一行才是印「103 条 · 尚未同步」的地方**——同一行里自相矛盾。
  // 只读顶上那三句的话，这处永远验不到。
  accounts: ((document.getElementById('accountList')||{}).innerText||'')
              .replace(/\s+/g, ' ').slice(0, 200)
})"""


async def run(chrome: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING"},
                         ensure_ascii=False))
        return 2
    workspace = Path(tempfile.mkdtemp(prefix="sa-popup-states-"))
    # **先按当前源码重打一次包。**（2026-08-11）
    # 这个演练装的是 dist 里那个 zip，不是源码目录。不重打就会验到一份旧代码——
    # 实测代价：改了 options.js 之后正例反例跑的是同一份包，两次输出一模一样，
    # 我据此写下「反例不红，说明还有一层分支没弄清」，而那句话是错的。
    build = subprocess.run([sys.executable, str(ROOT / "scripts/build_extension_package.py")],
                           cwd=ROOT, capture_output=True, text=True, check=False)
    if build.returncode != 0:
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_BUILD_FAILED",
                          "detail": (build.stdout + build.stderr)[-500:]}, ensure_ascii=False))
        return 2
    unpacked = workspace / "extension"
    with zipfile.ZipFile(ZIP) as archive:
        archive.extractall(unpacked)

    # 端口被上一个演练占着时**说人话**，别抛 traceback 让上游只看到 NO_JSON。
    _drill_port.require_free(PORT, drill=Path(__file__).name)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    headless = [] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync", *headless,
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    measured: dict = {}
    problems: list[str] = []
    try:
        for _ in range(40):
            try:
                version = json.loads(
                    urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                             # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"},
                             ensure_ascii=False))
            return 2

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            extension_id = (await rpc("Extensions.loadUnpacked", {"path": str(unpacked)})
                            ).get("result", {}).get("id") or ""
        if not extension_id:
            problems.append("Chrome 装不上这个包")
        else:
            await asyncio.sleep(3)
            workers = [t for t in json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
                       if t.get("type") == "service_worker" and extension_id in t.get("url", "")]
            if not workers:
                problems.append("装上了，但 service worker 起不来")
            else:
                async with websockets.connect(workers[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await _rpc_factory(ws)
                    await rpc("Runtime.enable")
                    await rpc("Runtime.evaluate", {
                        "expression": f'SA.setConfig({{endpoint:"http://127.0.0.1:{PORT}",'
                                      f' token:"drill"}})',
                        "awaitPromise": True, "returnByValue": True})

                for label, accounts in (("从没连过", []),
                                        ("连过后来断了", _accounts("disconnected")),
                                        ("连着", _accounts("connected"))):
                    _state["accounts"] = accounts
                    url = f"chrome-extension://{extension_id}/popup.html"
                    seen = {item.get("id") for item in json.loads(
                        urllib.request.urlopen(base + "/json", timeout=5).read())}
                    urllib.request.urlopen(urllib.request.Request(
                        base + "/json/new?" + url, method="PUT"), timeout=10).read()
                    pages: list = []
                    for _ in range(20):
                        await asyncio.sleep(0.5)
                        pages = [t for t in json.loads(
                            urllib.request.urlopen(base + "/json", timeout=5).read())
                            if t.get("type") == "page" and "popup.html" in t.get("url", "")
                            and t.get("id") not in seen]
                        if pages:
                            break
                    if not pages:
                        problems.append(f"{label}：弹窗没打开")
                        continue
                    async with websockets.connect(pages[0]["webSocketDebuggerUrl"],
                                                  max_size=None) as ws:
                        rpc = await _rpc_factory(ws)
                        await rpc("Runtime.enable")
                        await asyncio.sleep(3)
                        got = await rpc("Runtime.evaluate",
                                        {"expression": READ, "returnByValue": True})
                        measured[label] = json.loads(got["result"]["result"]["value"])
                    if label == "连过后来断了":
                        # ── **设置页那一屏也得跟着走**（2026-08-11）──
                        #
                        # 同一个缺陷有两份：资料库那侧和扩展设置页那侧。
                        # 我先只修了资料库那侧，而这道门的另一处判据文件头里
                        # 早就写着「两个界面各有一份」。所以这里也读一遍。
                        options_url = f"chrome-extension://{extension_id}/options.html"
                        seen2 = {item.get("id") for item in json.loads(
                            urllib.request.urlopen(base + "/json", timeout=5).read())}
                        urllib.request.urlopen(urllib.request.Request(
                            base + "/json/new?" + options_url, method="PUT"), timeout=10).read()
                        opt_pages: list = []
                        for _ in range(20):
                            await asyncio.sleep(0.5)
                            opt_pages = [x for x in json.loads(
                                urllib.request.urlopen(base + "/json", timeout=5).read())
                                if x.get("type") == "page"
                                and "options.html" in x.get("url", "")
                                and x.get("id") not in seen2]
                            if opt_pages:
                                break
                        if not opt_pages:
                            problems.append("断开状态：设置页没打开")
                        else:
                            cards: dict = {}
                            async with websockets.connect(
                                    opt_pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
                                rpc = await _rpc_factory(ws)
                                await rpc("Runtime.enable")
                                # **等账号出现，不是等卡片出现**——卡片一开始就有 9 张。
                                for _ in range(20):
                                    got = await rpc("Runtime.evaluate", {
                                        "expression": OPTIONS_CARDS, "returnByValue": True})
                                    value = got["result"].get("result", {}).get("value")
                                    cards = json.loads(value) if value else {}
                                    if cards.get("with_an_account"):
                                        break
                                    await asyncio.sleep(1)
                            measured["断开时的设置页"] = cards
                            if not cards.get("with_an_account"):
                                # 正对照不成立 = 这一屏没被真的走到，下面全是空转。
                                problems.append(
                                    "断开状态：设置页 20 秒内三张卡上一个账号都没出现"
                                    "——这一屏没被真的走到，下面的断言是空转，**不算通过**")
                            else:
                                bad = [c["title"] for c in cards.get("cards", [])
                                       if "立即同步" in c["buttons"]]
                                if bad:
                                    problems.append(
                                        f"断开的账号在设置页上还摆着「立即同步」：{bad}"
                                        "——点下去服务端回 422「账号尚未连接，请先完成授权」")
                                lost = [c["title"] for c in cards.get("cards", [])
                                        if not any("连接" in b for b in c["buttons"])]
                                if lost:
                                    problems.append(
                                        f"断开的账号在设置页上没有「连接账号」：{lost}——他没有出路")

                    if label == "连着":
                        # ── 「同步进度」那颗按钮真的打得开侧边栏吗（2026-08-10）──
                        #
                        # `chrome.sidePanel.open()` 和 `permissions.request` 是同一条
                        # 规矩：要用户手势，**而手势不跨 sendMessage**。原来这颗按钮
                        # 是把事情发给 background 去做，在真 Chrome 里量到 service
                        # worker 处理带手势发出的消息时照样抛
                        # 「may only be called in response to a user gesture」。
                        #
                        # **判据不能看「弹窗关掉了没有」**：修复前那种写法是
                        # `.then(() => window.close())`，background 抛没抛它都关，
                        # 于是反例和正例都会报「开了」——我第一版就是这么写的。
                        # 唯一算数的信号是 **sidepanel.html 这个 target 出没出现**。
                        async with websockets.connect(pages[0]["webSocketDebuggerUrl"],
                                                      max_size=None) as ws:
                            rpc = await _rpc_factory(ws)
                            await rpc("Runtime.enable")
                            await rpc("Runtime.evaluate", {
                                "expression": 'document.getElementById("taskCenter")?.click()',
                                "userGesture": True, "returnByValue": True, "timeout": 8000})
                        await asyncio.sleep(2.5)
                        targets = json.loads(
                            urllib.request.urlopen(base + "/json", timeout=5).read())
                        panels = [t for t in targets if "sidepanel.html" in (t.get("url") or "")]
                        opened = [t.get("url") for t in panels]
                        # **开出来说了什么，和开没开一样重要。**（2026-08-10）
                        #
                        # 此前只确认「sidepanel.html 这个 target 出没出现」——
                        # 而这一屏是他点插件图标里的「同步进度」看到的东西，
                        # **里面的字一次都没被读过**。同一天在资料库那边，
                        # 「一屏从没被渲染过」这条线索连出了四处缺陷。
                        panel_text = ""
                        if panels:
                            async with websockets.connect(panels[0]["webSocketDebuggerUrl"],
                                                          max_size=None) as pws:
                                prpc = await _rpc_factory(pws)
                                await prpc("Runtime.enable")
                                got = await prpc("Runtime.evaluate", {
                                    "expression": "document.body.innerText.replace(/\\s+/g,' ').trim().slice(0,300)",
                                    "returnByValue": True, "timeout": 8000})
                                panel_text = str(got.get("result", {})
                                                 .get("result", {}).get("value") or "")
                        measured["同步进度按钮"] = {"sidepanel_targets": opened,
                                                   "panel_text": panel_text}
                    for target in json.loads(
                            urllib.request.urlopen(base + "/json", timeout=5).read()):
                        if target.get("id") == pages[0]["id"]:
                            urllib.request.urlopen(urllib.request.Request(
                                base + "/json/close/" + pages[0]["id"]), timeout=10).read()
                    await asyncio.sleep(0.5)
    finally:
        server.shutdown()
        process.terminate()
        shutil.rmtree(workspace, ignore_errors=True)

    fresh = measured.get("从没连过") or {}
    stale = measured.get("连过后来断了") or {}
    live = measured.get("连着") or {}
    if not (fresh and stale and live):
        problems.append("**三种状态没量全**——这不是通过。")
    else:
        if "第一个" not in fresh.get("button", ""):
            problems.append(f"从没连过时主按钮不是「连接第一个账号」：{fresh.get('button')!r}")
        # **这一条是这个演练存在的理由。**
        if "第一个" in stale.get("button", "") or "还没有连接" in stale.get("title", ""):
            problems.append(
                f"**连过、后来断了，却还在说「{stale.get('title')}」/「{stale.get('button')}」**"
                "——他连过三个账号，这两句对他都是假的，"
                "而且把「重连一次就恢复」这条唯一要做的事盖掉了")
        if "一条都没少" not in stale.get("copy", ""):
            problems.append(
                f"断开这一屏没说清内容还在：{stale.get('copy')!r}——"
                "「未连接」很容易被读成「我的收藏没了」")
        # **那个数只数得到挂在账号名下的那些，话就不能说成"你存的全部"。**（2026-08-10）
        #
        # 2026-08-10 量生产：三个账号的 content_count 是 101 / 85 / 0，
        # 加起来 186，**而资料库那一页显示 193**（差的 7 条是手存的网页
        # 和几条没挂账号的 saved）。原话「已经存下的 186 条内容一条都没少」
        # 于是让他在两屏之间看到两个数——而这句话的全部理由就是
        # 让他别以为东西丢了。资料库那一侧早就不带数字了。
        if "已经存下的" in stale.get("copy", ""):
            problems.append(
                f"那句话说成了「你存的全部」：{stale.get('copy')!r}——"
                "它加的只是各账号名下的条数（手存的网页、没挂账号的都不算），"
                "和资料库那一页的总数对不上")
        if stale.get("title") == fresh.get("title") or live.get("title") == stale.get("title"):
            problems.append("**三种状态里有两种说同一句话**——那就等于没分状态")
        # **账号卡片不许自相矛盾。**
        cards = stale.get("accounts", "")
        if "尚未同步" in cards and "条" in cards:
            problems.append(
                f"**账号卡片印着「N 条 · 尚未同步」**：{cards[:80]!r}——"
                "同一行里自相矛盾（`last_sync_at` 只在完全跑完时才写，"
                "而他那几次跑完了、进了 102 条、结局是 partial）")
        # **账号卡片上不许出现英文状态 id。**
        # `statusName[current] || current` 那种兜底会安静地把内部值印给用户；
        # 少一个键就漏一个词，而它不出声。这条通用地挡住，不只挡 disconnected。
        RAW_STATES = ("disconnected", "connected", "degraded", "authorizing", "queued",
                      "discovering", "scanning", "normalizing", "artifacting",
                      "exporting", "completed", "partial", "failed",
                      "blocked_environment", "paused", "cancelled")
        for reading in (stale, live):
            leaked = [name for name in RAW_STATES if name in reading.get("accounts", "")]
            if leaked:
                problems.append(
                    f"**账号卡片上印着英文状态**：{leaked}——"
                    "他看到的是内部值，不是人话")
        if "条内容" not in live.get("title", ""):
            problems.append(f"连着的时候不报条数：{live.get('title')!r}")
        # **「同步进度」那颗按钮真的打得开侧边栏吗。**「没量到」不算通过。
        panel = measured.get("同步进度按钮")
        if panel is None:
            problems.append("**没量到「同步进度」那颗按钮会怎样**——这不是通过，是没跑到")
        elif panel.get("panel_text") is None or panel.get("panel_text") == "":
            problems.append(
                "**侧边栏开出来了，却读不到里面的字**——这不是通过，是没量到")
        elif "还没有同步过" in (panel.get("panel_text") or ""):
            # **自洽**：说「还没有同步过」的同时，三个计数必须都是 0。
            # 这一屏 2026-08-06 栽过一次同形的：上面写着「1 已完成」，
            # 下面还在教他去连接账号。当时修了文案，而**没有人读过这一屏**
            # ——2026-08-10 才第一次把它的正文读回来。
            problems.append(
                "侧边栏说「还没有同步过」，而夹具里明明有一次同步记录（partial）："
                f"{panel.get('panel_text')[:120]!r}——他生产库里 20 次同步、"
                "completed 是 0，这一支正是他会走到的那一支")
        elif not panel.get("sidepanel_targets"):
            problems.append(
                "**点「同步进度」没打开侧边栏**——`chrome.sidePanel.open()` 要用户手势，"
                "而手势不跨 sendMessage。把它交给 background 就是这个结果，"
                "而且弹窗照样会关掉，所以他看到的是「点了没反应」")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "measured_in_real_chrome": measured,
        "problems": problems,
        "why_zh": ("弹窗是他点插件图标看到的第一屏。三种状态各说各的话，"
                   "**只验一种的话，一个把所有状态都写成同一句的实现也能过**。"),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def main() -> int:
    chrome = os.environ.get("SA_CHROME") or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not Path(chrome).exists():
        print(json.dumps({"status": "FAIL", "error_code": "CHROME_MISSING"},
                         ensure_ascii=False))
        return 2
    return asyncio.run(run(chrome))


if __name__ == "__main__":
    sys.exit(main())
