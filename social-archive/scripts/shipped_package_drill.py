#!/usr/bin/env python3
"""加载 **Owner 真正下载的那个 zip**，一个字节都不改（v0.0.0.22 / G3）。

## 为什么必须单开这一个

仓里有十个真 Chrome 演练，**每一个都调 `Extensions.loadUnpacked`
加载源码目录**，而且每一个在加载前都先做这件事：

    manifest["host_permissions"] = host_permissions | optional_host_permissions
    manifest["optional_host_permissions"] = []

那是为了跑得顺——不弹权限框。代价是：**他真正装的那一份，
这些权限是「可选、未授予」的状态，而那个状态从来没有被任何演练走过。**

真实 manifest 里，**每一个平台的域名都在 optional_host_permissions 里**——
xiaohongshu、douyin、kuaishou、bilibili、reddit、instagram、x、youtube，
一个不例外（`host_permissions` 里只有档案馆自己那两个域名和本机回环）。而 background.js 里
`chrome.permissions.request` 只为 `bookmarks` 和 Cookie 托管调过——
浏览器读取那条路（connectBrowserPlatform / acquireByListShape）
**一次都没有申请过它需要的主机权限**。

这个仓有过一模一样的教训：47 道门全在验暂存目录，**没人打开过最终那个 zip**，
改成回读自验证后第一次跑就抓到 283 个乱码，藏了十八轮。

## 它验什么

1. zip 解出来能不能被 Chrome 装上（manifest 有没有指向没打进包的文件）
2. 装上之后 service worker 起不起得来，关键模块在不在
3. **那些主机权限现在到底有没有**——这才是重点
4. 在**没有授予**的状态下走一次读取，看它是**说得出话**还是**默默失败**

第 4 条是判据的核心。做不到不是罪；**做不到却不说**才是。

## 它不证明什么

不证明真平台的响应长什么样（那要他的登录态）。
这里只回答一个问题：**他装上的那一份，和我一直在测的那一份，是不是同一个东西。**
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
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import list_shape_end_to_end_drill as shape          # noqa: E402  复用假站与证书

ZIP = ROOT / "dist" / "social-archive-extension.zip"
DEBUG_PORT = 9381

PROBE = r"""
(async () => {
  const out = { modules: {}, permissions: {}, manifest: {} };
  // 指向假档案馆，好让连接面板问得出「有哪些来源可连」。
  await SA.setConfig({ endpoint: "http://127.0.0.1:%(api)d", token: "drill" });
  const manifest = chrome.runtime.getManifest();
  out.manifest = { version: manifest.version,
                   host: manifest.host_permissions || [],
                   optionalHost: (manifest.optional_host_permissions || []).length };
  // 关键模块在不在（打包漏文件时，这里会是 false 而不是报错）
  out.modules.listShape = typeof globalThis.SAListShape?.recogniseList === "function";
  // **名字要照抄导出表，不能凭印象写。** 第一版把 platformCatalogEntry 写成
  // platformSpec、又跑到 service worker 里去找 SABilibiliReader（它是注入到
  // B 站页面里跑的，本来就不在这儿），于是报了两条「包里缺文件」的假缺陷。
  // 判据的盲区被我当成产品的缺陷——这个仓有记录。
  out.modules.catalog   = typeof globalThis.SAPlatformCatalog?.platformCatalogEntry === "function";
  out.modules.cookies   = typeof globalThis.SACookieExport?.ALLOWED_PLATFORMS === "object";
  // **重点：他装上之后，这些域名到底有没有权限。**
  for (const origin of ["https://*.xiaohongshu.com/*", "https://*.reddit.com/*",
                        "https://*.instagram.com/*", "https://*.bilibili.com/*"]) {
    out.permissions[origin] = await chrome.permissions.contains({ origins: [origin] })
      .catch(() => "查不了");
  }
  // 在**没有授予**的状态下走一次真实读取，看它说什么
  // **按他真实的顺序走：先连接。** 主机权限是在「连接账号」那一步申请的
  // （connectBrowserPlatform → SA.requestPlatformPermission）。
  // 第一版探针跳过连接直接读，于是量到「权限全无」就以为没人申请——
  // 其实是我自己没走那一步。
  // **先把机制本身量清楚，别从产品代码去推。**
  //
  // 问题不是"连接小红书失败"，是"service worker 里到底能不能申请权限"。
  // 三个申请点都在 background 里：主机权限（浏览器读取）、bookmarks（Chrome 书签）、
  // cookies（登录状态托管）。如果机制本身不行，那就是三处一起坏，
  // 而 Chrome 书签是我一直说"实测跑通"的那一个。
  for (const [name, request] of [["bookmarks", { permissions: ["bookmarks"] }],
                                 ["cookies", { permissions: ["cookies"] }],
                                 ["host", { origins: ["https://*.xiaohongshu.com/*"] }]]) {
    try { out[`gesture_${name}`] = await chrome.permissions.request(request); }
    catch (error) { out[`gesture_${name}`] = { threw: String(error && error.message || error) }; }
  }
  try { out.connect = await connectPlatform("xiaohongshu"); }
  catch (error) { out.connect = { threw: String(error && error.message || error) }; }
  for (const origin of ["https://*.xiaohongshu.com/*"]) {
    out.permissions[`${origin} (连接之后)`] =
      await chrome.permissions.contains({ origins: [origin] }).catch(() => "查不了");
  }
  const tab = await chrome.tabs.create({ url: "https://www.xiaohongshu.com/user/profile",
                                         active: false });
  await new Promise(r => setTimeout(r, 2500));
  try {
    out.install = await installNetObserverForTab({ platform: "xiaohongshu",
                                                   tabId: tab.id, shapeMode: true });
  } catch (error) {
    out.install = { threw: String(error && error.message || error) };
  }
  try {
    out.acquire = await acquireRelationItems({ tabId: tab.id, platform: "xiaohongshu",
                                               relation: "favorite" });
  } catch (error) {
    out.acquire = { threw: String(error && error.message || error),
                    failureCode: error && error.failureCode || null };
  }
  return JSON.stringify(out);
})()
"""


LIBRARY_HTML = """<!doctype html><meta charset=utf-8><title>假资料库</title>
<h1>资料库</h1>
<iframe id="f" src="chrome-extension://%(ext)s/connect-frame.html"
        style="width:520px;height:320px;border:0"></iframe>"""

# 扩展 id 要装上之后才知道，而假站在那之前就起来了——用一个盒子传。
LIBRARY_PAGE = {"html": ""}


class _FakeWithLibrary(shape._Fake):                        # noqa: SLF001
    """假站同时扮演两个角色：平台站，和**档案馆自己的站**。

    「不跳页」那条路必须在档案馆的域名下验：面板能不能被嵌进来，
    取决于 manifest 里 web_accessible_resources 的 matches 是否放行那个域。
    在别的域名下试等于没试。
    """

    def do_GET(self) -> None:                               # noqa: N802
        host = (self.headers.get("Host") or "").split(":")[0]
        if host.endswith("linzezhang.com"):
            path = urlparse(self.path).path
            # **上真的那一份资料库**，不是我手写的一页。
            # 手写的那页只能证明"iframe 能加载"；他抱怨的是**导航**——
            # 「去连接」那颗按钮到底会不会把面板开出来，只有真页面答得了。
            served = {"/": ROOT / "apps/pwa/index.html",
                      "/index.html": ROOT / "apps/pwa/index.html",
                      "/assets/app.js": ROOT / "apps/pwa/app.js",
                      "/assets/styles.css": ROOT / "apps/pwa/styles.css"}.get(path)
            if served and served.is_file():
                kind = "text/html; charset=utf-8" if served.suffix == ".html" else (
                    "text/javascript; charset=utf-8" if served.suffix == ".js" else "text/css")
                body = served.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # **/health 要像样。** 徽章那句话是照它画的；回 `{}` 的话
            # 走的是"需要连接"那一支，而要验的正是"已连接"那一支上
            # 有没有把插件版本显示出来。
            if path == "/health":
                body = json.dumps({
                    "status": "ok", "version": "0.0.0.22",
                    "minimum_extension_version": "0.0.0.9",
                    "worker": {"ever_seen": True, "alive": True},
                }).encode("utf-8")
            else:
                body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


async def _open_library(base: str, extension_id: str) -> dict:
    """**在档案馆自己的域名下**打开一页，把连接面板嵌进去。

    这是「不跳页」那条路的要害：面板必须是扩展页面（授权框只能在那儿弹），
    同时必须能被资料库嵌进来（manifest 的 web_accessible_resources 只对
    档案馆那两个域放行）。这两条只要有一条不成立，他就还得跳走。
    """
    urllib.request.urlopen(urllib.request.Request(
        base + "/json/new?https://social-archive.linzezhang.com/", method="PUT"),
        timeout=10).read()
    await asyncio.sleep(4)
    # **按他真会走的那一下来**：在资料库上点「连接第一个账号」。
    # 这一步答的是导航那个问题——面板会不会被打开，而不是"iframe 能不能加载"。
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    pages = [item for item in targets if item.get("type") == "page"
             and "linzezhang.com" in item.get("url", "")]
    clicked: dict = {"tried": False}
    if pages:
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await shape._rpc_factory(ws)
            await rpc("Runtime.enable")
            got = await rpc("Runtime.evaluate", {
                "expression": '(async () => { const b = document.getElementById("emptyConnectAccount");'
                              ' if (!b) return JSON.stringify({ tried: false, why: "找不到那颗按钮" });'
                              ' b.click(); await new Promise(r => setTimeout(r, 2500));'
                              # **连上之后资料库那张表要被重读**，否则他连上了
                              # 却一条新内容都看不到（首次同步要几秒，而那张表没人重读）。
                              # 这里数 /v1/contents 被打了几次：面板报 connected 之后必须再打。
                              ' window.__saContentHits = 0;'
                              ' const realFetch = window.fetch;'
                              ' window.fetch = (...a) => { try {'
                              '   if (String(a[0]).includes("/v1/library")) window.__saContentHits++;'
                              ' } catch (_) {} return realFetch(...a); };'
                              ' window.postMessage({ source: "social-archive-connect-frame",'
                              '   type: "connected", platform: "xiaohongshu", state: "connected" }, "*");'
                              ' await new Promise(r => setTimeout(r, 4200));'
                              ' const back = document.getElementById("connectModalBackdrop");'
                              ' const frame = document.getElementById("connectFrame");'
                              # **徽章上读不读得出插件版本。**
                              # 他说「不能用」时我要的第一件事就是"你装的是哪一版"，
                              # 而我这一整天都在猜它。现在指着这一行让他读给我——
                              # 所以这一行必须真的在那儿。
                              ' const badge = (document.getElementById("serviceBadge")'
                              '   || {}).textContent || "";'
                              ' return JSON.stringify({ tried: true, badge,'
                              ' panelOpen: !!back && back.classList.contains("open"),'
                              ' frameSrc: (frame && frame.getAttribute("src") || "").slice(0, 40),'
                              ' contentReloads: window.__saContentHits || 0,'
                              ' syncStillOpen: !!document.getElementById("syncModalBackdrop")'
                              '   && document.getElementById("syncModalBackdrop").classList.contains("open") }); })()',
                "userGesture": True, "awaitPromise": True, "returnByValue": True, "timeout": 20000})
            payload = got.get("result", {})
            if not payload.get("exceptionDetails"):
                clicked = json.loads(payload["result"]["value"])
    await asyncio.sleep(2)
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    frames = [item for item in targets
              if extension_id in item.get("url", "") and "connect-frame" in item.get("url", "")]
    if not frames:
        pages = [item.get("url", "")[:80] for item in targets if item.get("type") == "page"]
        return {"embedded": False, "click": clicked,
                "why": "连接面板没有作为 iframe 加载出来——他还是得跳去插件的账号页",
                "targets": [item.get("url", "")[:80] for item in targets
                            if item.get("type") == "page"][:6]}
    async with websockets.connect(frames[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await shape._rpc_factory(ws)
        await rpc("Runtime.enable")
        # **认不出时那段诊断有没有真的显示出来。**
        # 插件早就算好并放在返回值的 diagnosis 里，而在这之前**没有任何界面读它**——
        # 他只看到「没认出你的收藏列表」，我要的东西谁也拿不到，又是一轮来回。
        # **造一次"认不出"，看那段诊断真的填进去没有。**
        # 只看"这块地方存不存在"抓不到我刚修的那种 bug（诊断没挂到 error 上，
        # 于是它永远是空的）。这里把 sendMessage 换成必定失败的一版，
        # 点一下按钮，再读那块地方的字。
        shown = await rpc("Runtime.evaluate", {
            "expression": '(async () => {'
                          ' const box = document.getElementById("diagnosis");'
                          ' if (!box) return JSON.stringify({ hasBox: false });'
                          # **权限那一步也要绕开**：`permissions.request` 会弹一个
                          # 没人去点的框，于是点击永远卡在那儿，根本走不到我要验的
                          # 那一步。第一版忘了这个，演练红了——**而且红在错的理由上**。
                          ' const hadContains = chrome.permissions.contains;'
                          ' chrome.permissions.contains = async () => true;'
                          ' const real = chrome.runtime.sendMessage;'
                          ' chrome.runtime.sendMessage = async (msg) =>'
                          '   msg && msg.type === "SA_ACCOUNT_CONNECT"'
                          '     ? { ok: false, error: "没能在这个页面上认出你的收藏列表。",'
                          '         diagnosis: { captured: 5, rejected: ['
                          '           { url: "https://p.example.com/api/log", why: "不是 JSON" },'
                          '           { url: "https://p.example.com/api/feed", why: "只有 20% 的元素在同一个位置带得出 id" } ] } }'
                          '     : real(msg);'
                          ' const button = document.querySelector("button");'
                          ' if (!button) return JSON.stringify({ hasBox: true, clicked: false });'
                          ' button.click();'
                          ' await new Promise(r => setTimeout(r, 1200));'
                          # **诊断要在第一次点击之后就记下来**：第二次点击走的是
                          # 成功路径，它会（正确地）把诊断清空，之后再读就是空的。
                          ' const shownAfterFail = !box.hidden;'
                          ' const textAfterFail = (box.textContent || "").slice(0, 160);'
                          # **第二种结局也要验**：自动认不出登录态时，
                          # 「我已登录，继续」必须就地长出来。之前它只在插件的账号页上，
                          # 面板上没有——而我在说明里把这一步写成了一条路。
                          ' chrome.runtime.sendMessage = async (msg) =>'
                          '   msg && msg.type === "SA_ACCOUNT_CONNECT"'
                          '     ? { ok: true, state: "authorizing", message: "请先在平台页面登录" }'
                          '     : real(msg);'
                          ' button.click();'
                          ' await new Promise(r => setTimeout(r, 1200));'
                          ' const verify = document.querySelector("[data-verify]");'
                          ' chrome.runtime.sendMessage = real;'
                          ' chrome.permissions.contains = hadContains;'
                          # **做不到自动的平台要照列并说清**（验收标准第 1 条）。
                          # 上一版是直接不显示——他打开面板找 X 一行都没有，
                          # 不知道是不支持还是自己没找对地方。**不显示不等于说清。**
                          ' const manual = document.querySelector("li.manual");'
                          ' return JSON.stringify({ hasBox: true, clicked: true,'
                          '   manualRow: manual ? (manual.textContent || "").slice(0, 80) : "",'
                          '   diagnosisShown: shownAfterFail, diagnosisText: textAfterFail,'
                          '   verifyButton: verify ? verify.textContent : "" });'
                          ' })()',
            "userGesture": True, "awaitPromise": True, "returnByValue": True, "timeout": 15000})
        diagnosis_box = json.loads(
            (shown.get("result", {}).get("result", {}) or {}).get("value") or '{"hasBox": false}')
        got = await rpc("Runtime.evaluate", {
            "expression": 'JSON.stringify({ api: typeof chrome?.permissions?.request,'
                          ' hasButton: !!document.querySelector("button"),'
                          ' text: (document.body.innerText || "").slice(0, 120) })',
            "returnByValue": True, "timeout": 10000})
        payload = got.get("result", {})
        if payload.get("exceptionDetails"):
            return {"embedded": True, "why": str(payload["exceptionDetails"])[:200]}
        detail = json.loads(payload["result"]["value"])
        return {"embedded": True, **detail, "click": clicked, **diagnosis_box}


async def _open_options(base: str, extension_id: str) -> dict:
    """打开扩展自己的 options 页，在**那里**试一次权限申请。"""
    url = f"chrome-extension://{extension_id}/options.html"
    urllib.request.urlopen(urllib.request.Request(
        base + "/json/new?" + url, method="PUT"), timeout=10).read()
    await asyncio.sleep(2)
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    pages = [item for item in targets
             if item.get("type") == "page" and extension_id in item.get("url", "")]
    if not pages:
        return {"drill_error": "options 页没打开"}
    async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await shape._rpc_factory(ws)
        await rpc("Runtime.enable")
        # 先确认这个页面上下文本身是活的——不然下面超时了分不清是
        # 「弹框没人点」还是「页面压根没打开」。
        alive = await rpc("Runtime.evaluate", {
            "expression": 'JSON.stringify({ hasApi: typeof chrome?.permissions?.request })',
            "returnByValue": True, "timeout": 10000})
        probe = json.loads(alive.get("result", {}).get("result", {}).get("value") or "{}")
        if probe.get("hasApi") != "function":
            return {"drill_error": f"options 页里没有 permissions API：{probe}"}
        # **弹框一旦弹出来就没人去点**，所以用竞速把三种结局分开：
        #   threw    → 结构上走不通（修法不成立）
        #   returned → 直接有了答案（权限本来就有，或被直接拒）
        #   prompted → 弹框弹出来了，等着人点——**这就是修法成立的信号**
        got = await rpc("Runtime.evaluate", {
            "expression": '(async () => JSON.stringify(await Promise.race(['
                          'chrome.permissions.request({ origins: ["https://*.xiaohongshu.com/*"] })'
                          '.then(ok => ({ returned: ok }))'
                          '.catch(e => ({ threw: String(e && e.message || e) })), '
                          'new Promise(r => setTimeout(() => r({ prompted: true }), 5000))'
                          '])))()',
            "userGesture": True, "awaitPromise": True, "returnByValue": True, "timeout": 20000})
        payload = got.get("result", {})
        if payload.get("exceptionDetails"):
            return {"drill_error": str(payload["exceptionDetails"])[:200]}
        return json.loads(payload["result"]["value"])


async def run(chrome: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING",
                          "path": str(ZIP.relative_to(ROOT)),
                          "message_zh": "发布包不存在——先跑 scripts/build_extension_package.py"},
                         ensure_ascii=False, indent=2))
        return 2
    # **包比源码旧的时候，这个演练会安安静静地测一个不存在的版本。**
    #
    # 第一次跑就撞上了：我刚改完 background.js，演练照样绿——
    # 因为它解的是上一次打的包。一个「专门验最终产物」的演练，
    # 却可能验的是**上一版**的最终产物，那比没有更糟。
    newest_source = max(path.stat().st_mtime for path in
                        (ROOT / "apps/browser-extension").rglob("*") if path.is_file())
    problems: list[str] = []
    if newest_source > ZIP.stat().st_mtime:
        problems.append("**发布包比源码旧**——这次量的是上一版的包，"
                        "结论对当前代码不成立。先跑 scripts/build_extension_package.py")
    workspace = Path(tempfile.mkdtemp(prefix="sa-shipped-"))
    measured: dict = {}

    # **原样解包，一个字节都不改。** 这正是它和其余十个演练的区别。
    unpacked = workspace / "extension"
    with zipfile.ZipFile(ZIP) as archive:
        archive.extractall(unpacked)

    # manifest 里点名的文件，包里必须真有（打包漏文件时 Chrome 会直接拒装）
    manifest = json.loads((unpacked / "manifest.json").read_text(encoding="utf-8"))
    referenced: list[str] = []
    for key in ("background",):
        value = manifest.get(key) or {}
        if isinstance(value, dict) and value.get("service_worker"):
            referenced.append(value["service_worker"])
    for entry in manifest.get("content_scripts", []) or []:
        referenced.extend(entry.get("js", []) or [])
    for entry in (manifest.get("web_accessible_resources") or []):
        referenced.extend(entry.get("resources", []) or [])
    for key in ("action", "side_panel", "options_page", "options_ui"):
        value = manifest.get(key)
        if isinstance(value, dict):
            for sub in ("default_popup", "default_path", "page"):
                if value.get(sub):
                    referenced.append(value[sub])
        elif isinstance(value, str):
            referenced.append(value)
    missing = sorted({name for name in referenced
                      if "*" not in name and not (unpacked / name).is_file()})
    if missing:
        problems.append(f"**manifest 指着包里没有的文件**：{missing}——Chrome 会直接拒装")

    shape.PLATFORM = "xiaohongshu"
    shape.RELATION = "favorite"
    shape.SPEC = shape.PLATFORMS["xiaohongshu"]
    shape.ROUTES = shape._routes(shape.SPEC)
    shape.EXPLORE_PAGE, shape.FAVOURITE_PAGE = shape._pages(shape.SPEC)
    context = shape._cert(workspace)
    server = ThreadingHTTPServer(("127.0.0.1", shape.FAKE_PORT), _FakeWithLibrary)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # **假档案馆**：面板要调 /v1/accounts 才知道该画哪些按钮。
    # 不起它的话，面板永远停在「读不到可连接的来源」——那等于没验过它工作。
    shape.received["accounts"].clear()
    api_server = ThreadingHTTPServer(("127.0.0.1", shape.FAKE_API_PORT), shape._Api)
    threading.Thread(target=api_server.serve_forever, daemon=True).start()

    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--password-store=basic", "--use-mock-keychain",
         "--host-resolver-rules=MAP *xiaohongshu.com 127.0.0.1:"
         f"{shape.FAKE_PORT},MAP social-archive.linzezhang.com 127.0.0.1:{shape.FAKE_PORT}",
         "--ignore-certificate-errors", "--allow-insecure-localhost", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    load_error = ""
    measured_page: dict = {}
    measured_frame: dict = {}
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
            rpc = await shape._rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": str(unpacked)})
            extension_id = loaded.get("result", {}).get("id") or ""
            if not extension_id:
                load_error = str(loaded)[:400]
        if not extension_id:
            problems.append(f"**Chrome 装不上这个包**：{load_error}")
        else:
            await asyncio.sleep(3)
            targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
            workers = [t for t in targets if t.get("type") == "service_worker"
                       and extension_id in t.get("url", "")]
            if not workers:
                problems.append("**装上了，但 service worker 起不来**——"
                                "包里少了它依赖的文件，或者哪一份有语法错")
            else:
                async with websockets.connect(workers[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await shape._rpc_factory(ws)
                    await rpc("Runtime.enable")
                    got = await rpc("Runtime.evaluate",
                                    {"expression": PROBE % {"api": shape.FAKE_API_PORT},
                                     "userGesture": True,
                                     "awaitPromise": True, "returnByValue": True,
                                     "timeout": 60000})
                    payload = got.get("result", {})
                    if payload.get("exceptionDetails"):
                        problems.append(f"探针跑炸了：{str(payload['exceptionDetails'])[:300]}")
                    else:
                        measured = json.loads(payload["result"]["value"])
                # **同一个 API，换个地方调，看还抛不抛。**
                #
                # 修法是把权限申请从 service worker 挪到扩展自己的页面。
                # 这一段就是那个修法的证据：在 options 页里调 permissions.request，
                # 它**不许再抛 user gesture**。返回 false 可以（弹框没人点），
                # 抛异常不行——抛异常等于这条路结构上走不通。
                #
                # **必须放在 worker 那一段之后**：打开 options 页会让 worker 的
                # 调试目标失效，先开页面的话上面整段会以 HTTP 500 收场。
                try:
                    measured_page = await asyncio.wait_for(
                        _open_options(base, extension_id), timeout=40)
                except Exception as error:                  # noqa: BLE001
                    measured_page = {"drill_error": str(error)[:200]}
                # **不跳页那条路**：连接面板能不能被资料库嵌进去。
                LIBRARY_PAGE["html"] = LIBRARY_HTML % {"ext": extension_id}
                try:
                    measured_frame = await asyncio.wait_for(
                        _open_library(base, extension_id), timeout=40)
                except Exception as error:                  # noqa: BLE001
                    measured_frame = {"drill_error": str(error)[:200]}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        api_server.shutdown()
        shutil.rmtree(workspace, ignore_errors=True)

    for name, present in (measured.get("modules") or {}).items():
        if not present:
            problems.append(f"**包里缺 {name} 那一份**——它在源码目录里有，在他下载的包里没有")
    if measured.get("manifest", {}).get("version") != (ROOT / "VERSION").read_text(encoding="utf-8").strip():
        problems.append(f"包里的版本是 {measured.get('manifest', {}).get('version')}，"
                        f"而仓是 {(ROOT / 'VERSION').read_text(encoding='utf-8').strip()}"
                        "——他下载到的是旧包")

    # **修法必须被证明，而且"没量到"不算通过。**
    #
    # 第一版只在 threw 里含 "gesture" 时才报问题——于是 drill_error（页面没打开、
    # 超时）会安安静静地过去。这个仓栽在"空默认值吞掉不知道"上不止一次：
    # `[]`/`{}`/没测到，都会被读成"没问题"。
    if "gesture" in str(measured_page.get("threw", "")).lower():
        problems.append(
            "**在扩展自己的页面里申请权限也抛 user gesture**："
            f"{measured_page.get('threw')}——那说明把申请挪到页面里这个修法不成立，"
            "得另想办法，而不是让那颗按钮继续画在那儿")
    elif not (measured_page.get("prompted") or "returned" in measured_page):
        problems.append(
            f"**没量到扩展页面里的权限申请到底会怎样**：{json.dumps(measured_page, ensure_ascii=False)}"
            "——这不是通过，是这一段没跑成。修法有没有效仍然不知道")
    # **不跳页那条路必须被证明**，而且"没量到"不算通过。
    if not measured_frame.get("embedded"):
        problems.append(
            f"**连接面板没能嵌进资料库**：{json.dumps(measured_frame, ensure_ascii=False)[:220]}"
            "——那他每次连账号还是得跳去插件的账号页，"
            "而那正是他说的「几个页面乱七八糟的跳来跳去」")
    elif "**" in str(measured_frame.get("text") or ""):
        # HTML 里没有 Markdown。星号原样显示出来是**用户看得见的**缺陷，
        # 而它只在真的把那一页渲染出来之后才看得到——判据读源码是读不出的。
        problems.append(
            f"**面板上有没被渲染的 Markdown 星号**：{measured_frame.get('text')[:80]}"
            "——HTML 里 ** 不是加粗，是两个星号")
    elif not str(measured_frame.get("text") or "").strip():
        # **一片空白不算通过。** 面板打不开时也要说得出为什么。
        problems.append("**面板嵌进去了，但整页是空的**——他会以为软件坏了")
    elif not (measured_frame.get("click") or {}).get("panelOpen"):
        # **导航那一下也要验。** 「面板能加载」和「他点那颗按钮面板会打开」
        # 是两件事，而他抱怨的正是后者。这里点的是真资料库页上那颗
        # 「连接第一个账号」，不是我手写的一页。
        problems.append(
            f"**在资料库上点「连接第一个账号」没把面板打开**："
            f"{json.dumps(measured_frame.get('click'), ensure_ascii=False)}"
            "——他还是得自己找路")
    elif "插件 v" not in str((measured_frame.get("click") or {}).get("badge") or ""):
        # **我在使用说明里指着这一行让他读。**
        #
        # 「顶上会写 …·插件 v0.0.0.22，两个数字一样就说明更新成功了」——
        # 那一行不在的话，我就是又一次指着一个不存在的东西
        # （今天已经三次：保存按钮的名字、面板上的「我已登录，继续」、
        #   同步中心那句话）。所以它必须每次发布都被真的读一遍。
        problems.append(
            f"**徽章上读不出插件版本**：{(measured_frame.get('click') or {}).get('badge')!r}"
            "——而使用说明里正指着这一行让他判断有没有更新成功")
    elif not (measured_frame.get("click") or {}).get("contentReloads"):
        # 面板报"连上了"之后，资料库那张表必须被重读——否则他连上了
        # 却一条新内容都看不到，会以为没成。
        problems.append(
            "**连上之后资料库那张表没有被重读**——他连上了却看不到任何新条目，"
            "而首次同步要几秒钟才落库")
    elif (measured_frame.get("click") or {}).get("syncStillOpen"):
        # 两个弹窗叠着还是"乱"：他分不清该看哪一层。
        problems.append("**连接面板打开时账号同步中心还开着**——两层弹窗叠在一起")
    elif not measured_frame.get("hasBox"):
        problems.append("**面板上没有放诊断的地方**——认不出收藏列表时他只看得到"
                        "一句「没认出」，而为什么认不出谁也拿不到，又要来回一轮")
    elif measured_frame.get("clicked") and not measured_frame.get("diagnosisShown"):
        # **有地方 ≠ 填得进去。** 我第一版就是诊断没挂到 error 上，
        # 那块地方一直在、一直是空的——只验"存不存在"根本抓不到。
        problems.append(
            f"**造了一次认不出，诊断那块地方还是空的**：{measured_frame.get('diagnosisText')!r}"
            "——他手上仍然只有一句「没认出」")
    elif measured_frame.get("clicked") and "不是 JSON" not in str(measured_frame.get("diagnosisText") or ""):
        problems.append(
            f"**诊断显示出来了，但内容对不上**：{measured_frame.get('diagnosisText')!r}")
    elif measured_frame.get("clicked") and "保存当前页面" not in str(measured_frame.get("manualRow") or ""):
        problems.append(
            f"**只能手动保存的平台没有照列并说清**：{measured_frame.get('manualRow')!r}"
            "——他打开面板找不到它，不知道是不支持还是自己没找对地方")
    elif measured_frame.get("clicked") and "我已登录" not in str(measured_frame.get("verifyButton") or ""):
        # **第二种结局不许是死路。** 自动认不出登录态时（他还没在那个平台登录），
        # 下一步必须就在这一页上；否则他登录完回到面板，手里只有一颗
        # 「连接账号」，再点一次就是从头再来。
        problems.append(
            f"**自动认不出登录态时，面板上没有长出「我已登录，继续」**："
            f"{measured_frame.get('verifyButton')!r}——他登录完回来没有下一步")
    elif not measured_frame.get("hasButton"):
        # **只证明它加载了还不够，要看见它画出按钮。**
        # 面板画不出按钮时用户面对的就是一片说明文字加一句错误——
        # 那和"跳去别的页面"一样，还是连不上。
        problems.append(
            f"**面板加载了，但一颗按钮都没画出来**：{measured_frame.get('text')}"
            "——他在这一页上无从下手")
    elif measured_frame.get("api") != "function":
        problems.append(
            f"**面板嵌进去了，但里面没有权限 API**：{json.dumps(measured_frame, ensure_ascii=False)[:220]}"
            "——那颗按钮点下去弹不出授权框，等于白嵌")
    granted = measured.get("permissions") or {}
    # **这里不判对错，只判「说不说得出来」。**
    #
    # 权限没授予是事实，不是缺陷（Chrome 的可选权限本来就该按需申请）。
    # 缺陷是：没授予**而且不说**——那会变成"点了同步，什么也没发生"。
    acquire = measured.get("acquire") or {}
    ungranted = [origin for origin, ok in granted.items() if ok is False]
    if ungranted:
        code = acquire.get("failureCode") or ""
        if not code and not acquire.get("threw"):
            problems.append(
                f"**这些域名没有权限：{ungranted}，而读取那一步既没报错也没说原因**"
                f"——他会看到「点了同步，什么也没发生」。返回的是："
                f"{json.dumps(acquire, ensure_ascii=False)[:300]}")
        elif code and code != "PLATFORM_PERMISSION_MISSING":
            # **说得出话还不够，得说对。**
            #
            # 没有主机权限时 `chrome.tabs.get()` 读不到 url，于是代码算出空域名、
            # 回一句「读不出当前页面的域名」。那把人指向「是不是页面没打开」，
            # 而真因是授权没给，下一步是重新点一次「连接账号」。
            # 这个仓自己写过：**指错原因的 BLOCKED 不算 BLOCKED。**
            problems.append(
                f"**没权限，而报出来的原因是 {code}**："
                f"{acquire.get('threw') or acquire.get('error')}——"
                "那句话把他指向错的地方。真因是主机授权没给")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "package": str(ZIP.relative_to(ROOT)),
        "package_sha256_prefix": __import__("hashlib").sha256(ZIP.read_bytes()).hexdigest()[:16],
        "manifest": measured.get("manifest"),
        "modules_present": measured.get("modules"),
        "host_permission_granted_on_a_fresh_install": granted,
        # **连接那一步说了什么，必须留在证据里。**
        #
        # 主机权限是在这一步申请的。而 MV3 里 `chrome.permissions.request`
        # 要求「在一次用户手势期间调用」——service worker 处理消息时**手势还在不在**，
        # 是个必须量、不能推的问题。量不到就会变成：他点了「连接账号」，
        # 什么框都没弹，然后每次同步都失败。
        "connect_said": measured.get("connect"),
        # 在 service worker 里直接申请权限会怎样——三种权限各量一次
        # 同一个 API 在扩展页面里调——**这是修法的证据**
        "permission_request_from_extension_page": measured_page,
        # 嵌在资料库里的连接面板——**「不跳页」靠它成立**
        "connect_panel_embedded_in_library": measured_frame,
        "permission_request_from_service_worker": {
            name: measured.get(f"gesture_{name}") for name in ("bookmarks", "cookies", "host")},
        "install_said": measured.get("install"),
        "acquire_said": acquire,
        "manifest_files_missing_from_package": missing,
        "problems": problems,
        "message_zh": ("他下载的那个包和我一直在测的是同一个东西，"
                       "而且权限不足时它说得出话。" if not problems else
                       "**他装上的那一份和我测的那一份不是同一回事。**"),
        "what_this_does_not_prove": (
            "不证明真平台的响应长什么样——那要 Owner 的登录态。"
            "这里只回答：他装上的那一份，和我一直在测的那一份，是不是同一个东西。"),
    }
    out = ROOT / "evidence/G3/SHIPPED_PACKAGE.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验他真正下载的那个 zip")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
