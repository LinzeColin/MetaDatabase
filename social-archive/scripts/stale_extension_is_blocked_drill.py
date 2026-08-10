#!/usr/bin/env python3
"""他手上那个旧插件点「连接账号」，页面到底拦不拦得住。

## 为什么单开这一个

Owner 下一步要做的第一个动作就是这个：他装的是旧插件，打开资料库、点「连接账号」。

旧插件把权限申请放在 service worker 里，而那里**任何权限都要不到**
（实测三种全抛 user gesture）——授权框根本不会弹，点完什么也不会发生。
**那正是他这些天一直撞到的那堵墙。** 2026-08-10 在 `connectAccount` 里加了拦截：
拿不到连接面板就当场说清「你装的是旧版」并打开更新说明。

**而这条路只有单元测试走过。** 验收第 3 条写着「源码层通过、单元测试通过都不算数」。
`grep -l outdated scripts/*_drill.py` 是空的——十六个演练没有一个走过它。

## 旧插件不由我捏

`git show 043088a7b:./apps/browser-extension/` —— **v0.0.0.22，连接面板出现之前
的最后一版真实构建**（`web_accessible_resources: null`，握手回复里没有
`connectFrameUrl`）。生产今天之前跑的是 0.0.0.23，他手上那份就在这一档附近。

手捏一个"旧插件"等于自己写夹具再自己验它。这个仓栽过五次
（「夹具比原文干净就等于没测」），最坏一次自测八条全绿而真实的那份一条都匹配不到。

## 两个方向都要跑

只跑旧版会得到一个**红得凑巧**的结论——切错位置的判据照样能在两个状态间给出
不同答案。所以：

  · 旧版 → 必须被拦：toast 说「旧版」，且**真的开出一个 /extension-install 标签页**
  · 新版（他要装的那个发布包）→ 必须不拦：连接面板就地打开，没有那条 toast

两边有一边不对，整条演练就是 FAIL。

## 它不证明什么

**不是打生产。** 生产那一页在 Cloudflare Access 后面（实测 302），无头 Chrome
拿不到他的身份，也不该去绕。这里起的是本地一台服务器，**送的是 `apps/pwa/`
里那几个真文件**——而部署第 9 步已经逐字节证明了「仓 = 主机 = 镜像」，
所以被测的这份页面代码就是线上跑的那份。

接口是打桩的，但桩里那三个账号是 2026-08-10 从他生产库里量来的真实状态：
三个全部 disconnected、自动同步全关，193 条内容一条没少（见 `HIS_ACCOUNTS`）。

不证明他点完之后连接**成功**——那要他自己在浏览器里选「允许」。
这里证明的只有一件事：**旧插件不会让他再撞一次那堵墙。**
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import list_shape_end_to_end_drill as shape          # noqa: E402  复用 rpc 工厂

# **不洗环境的话 `cwd=ROOT` 是没有用的**——git 钩子塞的 GIT_DIR 压过 cwd，
# 子进程会去问**那个**仓。这条演练靠 git 取那份真实旧构建，被劫持就等于
# 从别的仓里取了一份"旧插件"出来验，而它照样会绿。
# 唯一出处在 social_archive.git_env，全仓由
# check_git_calls_cannot_be_hijacked_by_hooks.py 拦着——它就是这么抓到我的。
sys.path.insert(0, str(ROOT / "src"))
from social_archive.git_env import clean_git_env      # noqa: E402

PWA = ROOT / "apps/pwa"
ZIP = ROOT / "dist" / "social-archive-extension.zip"
PORT = 8765                     # **两版 manifest 本来就注入这个口，旧构建因此一个字节都不用动**
DEBUG_PORT = 9385
# **v0.0.0.22：连接面板出现之前的最后一版真实构建。**
# 引入连接面板的是 132d6038d「连接账号就地完成，不再跳去插件的账号页」，
# 这是它的父提交。改这个常量之前先确认新值那一版真的没有 connectFrameUrl。
OLD_COMMIT = "043088a7b"

# 桩数据里这三个账号是 2026-08-10 从他生产库量来的：三个全 disconnected、
# 自动同步全关，193 条内容一条没少。**夹具不许比真实情况干净。**
HIS_ACCOUNTS = [
    # HIS_ACCOUNTS_FIXTURE：**不是平台表**，是他生产库里那三个账号的形状。
    # 这条演练验的是"点连接账号会怎样"，和平台是谁无关；列全九个不多验任何东西，
    # 反而会让这份夹具比他的真实处境干净——而那正是这个仓栽过五次的地方。
    {"id": "acct_bili", "platform": "bilibili", "display_name": "B站",
     "connection_state": "disconnected", "auto_sync_enabled": False,
     "last_sync_at": "", "content_count": 103},
    {"id": "acct_douyin", "platform": "douyin", "display_name": "抖音",
     "connection_state": "disconnected", "auto_sync_enabled": False,
     "last_sync_at": "", "content_count": 86},
    {"id": "acct_xhs", "platform": "xiaohongshu", "display_name": "小红书",
     "connection_state": "disconnected", "auto_sync_enabled": False,
     "last_sync_at": "", "content_count": 1},
]

FAKE: dict[str, object] = {
    "/health": {"status": "ok", "project": "Social Archive", "version": "0.0.0.24",
                "minimum_extension_version": "0.0.0.9",
                "worker": {"ever_seen": True, "alive": True,
                           "last_seen_at": "2026-08-10T00:00:00Z", "seconds_since": 1.0,
                           "note": ""}},
    "/v1/auth/me": {"user_id": "drill", "display_name": "演练用户"},
    "/v1/auth/providers": {"items": []},
    "/v1/accounts": {"items": HIS_ACCOUNTS, "supported_platforms": [
        {"platform": "bilibili", "relations": ["favorite"], "sync_supported": True,
         "not_syncable_reason": "", "server_handled": False, "connect_supported": True},
    ]},
    "/v1/sync-runs": {"items": []},
    "/v1/destinations": {"items": []},
    "/v1/library": {"items": [], "total": 193,
                    "facets": {"platforms": [], "relations": [], "topics": [],
                               "collections": []}},
    "/v1/storage/status": {"l3_allowed": True, "message_zh": ""},
    "/v1/status": {"connectors": [], "destinations": []},
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        return

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:                        # noqa: N802
        # `ensureExtensionReady` 在没配对时会来要一枚令牌。演练里扩展是预先配好的，
        # 走不到这儿；真走到了也要给个像样的应答，否则会红在一个和本题无关的地方。
        self._send(200, json.dumps({"token": "drill-token"}).encode(), "application/json")

    def do_GET(self) -> None:                         # noqa: N802
        path = self.path.split("?")[0]
        for prefix, payload in FAKE.items():
            if path == prefix or path.startswith(prefix + "/"):
                self._send(200, json.dumps(payload, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
                return
        if path.startswith("/v1/"):
            self._send(200, b'{"items": []}', "application/json")
            return
        # **他点完会开一个 /extension-install，送的必须是那一页本尊。**
        #
        # 第一版这里回的是一句自己编的 `<h1>更新说明</h1>`，于是演练只证明了
        # "开出来一个标签页"——**而把人送到一页叫他重新安装（而不是覆盖原文件夹）
        # 的说明上，害处和不送一样大**：换个地方装，Chrome 给新 ID，
        # 他就同时装了两份，已连好的账号留在旧的那一份上。
        if path == "/extension-install":
            page = PWA / "extension-install.html"
            self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            return
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        if name == "guide":
            name = "guide.html"
        if name.startswith("assets/"):
            name = name[len("assets/"):]
        target = PWA / name
        if not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        kind = ("text/html; charset=utf-8" if target.suffix == ".html"
                else "text/css" if target.suffix == ".css"
                else "application/javascript" if target.suffix == ".js"
                else "application/octet-stream")
        self._send(200, target.read_bytes(), kind)


def _materialize_old(workspace: Path) -> Path:
    """把 git 里那一版**原样**取出来——不改一个字节。"""
    folder = workspace / "old-extension"
    folder.mkdir(parents=True)
    listing = subprocess.run(
        ["git", "ls-tree", "--name-only", OLD_COMMIT, "apps/browser-extension/"],
        cwd=ROOT, env=clean_git_env(), capture_output=True,
        text=True, check=True).stdout.split()
    for entry in listing:
        # content/ 是目录，单独展开
        blobs = [entry]
        if not Path(entry).suffix:
            blobs = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", OLD_COMMIT, entry + "/"],
                cwd=ROOT, env=clean_git_env(),
                capture_output=True, text=True, check=True).stdout.split()
        for blob in blobs:
            data = subprocess.run(["git", "show", f"{OLD_COMMIT}:./{blob}"],
                                  cwd=ROOT, env=clean_git_env(),
                                  capture_output=True, check=True).stdout
            out = folder / Path(blob).relative_to("apps/browser-extension")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    return folder


async def _worker_rpc(base: str, extension_id: str):
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    workers = [t for t in targets if t.get("type") == "service_worker"
               and extension_id in t.get("url", "")]
    if not workers:
        return None, None
    ws = await websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None)
    rpc = await shape._rpc_factory(ws)                # noqa: SLF001
    await rpc("Runtime.enable")
    return ws, rpc


async def _one_case(chrome: str, folder: Path, label: str, debug_port: int) -> dict:
    """装一份扩展、开资料库、点「连接账号」，把发生的事原样带回来。"""
    profile = Path(tempfile.mkdtemp(prefix=f"sa-stale-{label}-"))
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}",
         f"--remote-debugging-port={debug_port}", "--no-first-run",
         *([] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]),
         "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{debug_port}"
    result: dict = {"case": label, "extension_version": "", "toasts": [],
                    "install_tab_opened": False, "install_page_text": "",
                    "connect_panel_open": False, "dialog": "", "error": ""}
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                          # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            result["error"] = "CHROME_NOT_UP"
            return result

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await shape._rpc_factory(ws)         # noqa: SLF001
            loaded = await rpc("Extensions.loadUnpacked", {"path": str(folder)})
            extension_id = loaded.get("result", {}).get("id") or ""
        if not extension_id:
            result["error"] = "EXTENSION_NOT_LOADED"
            return result
        await asyncio.sleep(3)

        # **先把它配好**，否则页面会卡在「还没配对」那一支——那是另一道门，不是本题。
        ws, rpc = await _worker_rpc(base, extension_id)
        if not rpc:
            result["error"] = "SERVICE_WORKER_DOWN"
            return result
        got = await rpc("Runtime.evaluate", {"expression": f'''(async () => {{
            const cfg = {{ endpoint: "http://127.0.0.1:{PORT}", token: "drill-token" }};
            if (globalThis.SA && typeof SA.setConfig === "function") await SA.setConfig(cfg);
            else await chrome.storage.local.set(cfg);
            return chrome.runtime.getManifest().version;
        }})()''', "awaitPromise": True, "returnByValue": True, "timeout": 15000})
        result["extension_version"] = got.get("result", {}).get("result", {}).get("value", "")
        await ws.close()

        # 开资料库那一页
        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await shape._rpc_factory(ws)         # noqa: SLF001
            await rpc("Target.createTarget", {"url": f"http://127.0.0.1:{PORT}/"})
        await asyncio.sleep(6)

        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page" and f"127.0.0.1:{PORT}/" in t["url"]]
        if not pages:
            result["error"] = "LIBRARY_PAGE_NOT_OPEN"
            return result
        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as page:
            prpc = await shape._rpc_factory(page)      # noqa: SLF001
            await prpc("Runtime.enable")
            # **confirm() 会把无头 Chrome 卡死**，而且它弹出来本身就说明走错了分支
            # （那是「没检测到插件」/「版本低于下限」两支，不是本题要验的「旧版拦截」）。
            # 就地把它换掉：确定、可读，不依赖 CDP 的事件订阅。
            await prpc("Runtime.evaluate", {"expression": '''(() => {
                window.__saDialogs = [];
                window.confirm = message => { window.__saDialogs.push(String(message)); return false; };
                return "ok";
            })()''', "returnByValue": True})

            # 等账号表画出来（连接按钮就在里面）
            for _ in range(20):
                probe = await prpc("Runtime.evaluate", {
                    "expression": 'document.querySelectorAll("[data-connect-platform]").length',
                    "returnByValue": True})
                if int(probe.get("result", {}).get("result", {}).get("value") or 0) > 0:
                    break
                await asyncio.sleep(0.5)

            # **真的点下去**，带用户手势——权限申请那条路只在有手势时才成立。
            click = await prpc("Runtime.evaluate", {"expression": '''(() => {
                const button = document.querySelector('[data-connect-platform="bilibili"]')
                             || document.querySelector('[data-connect-platform]');
                if (!button) return JSON.stringify({ clicked: false });
                button.click();
                return JSON.stringify({ clicked: true, label: button.textContent });
            })()''', "returnByValue": True, "userGesture": True, "timeout": 15000})
            clicked = json.loads(click.get("result", {}).get("result", {}).get("value") or "{}")
            if not clicked.get("clicked"):
                result["error"] = "CONNECT_BUTTON_NOT_FOUND"
                return result
            await asyncio.sleep(3)

            read = await prpc("Runtime.evaluate", {"expression": '''(() => {
                const stack = document.getElementById("toastStack");
                const toasts = stack ? [...stack.children].map(node => node.textContent) : [];
                const backdrop = document.getElementById("connectModalBackdrop");
                // **openModal 加的是 `open` 类**（app.js: classList.add("open")）。
                // 第一版写的是「没有 hidden 类且 display 不是 none」——那个条件
                // 在这一页上恒真，于是两边都报"面板开着"，正例假绿。
                const open = !!backdrop && backdrop.classList.contains("open");
                return JSON.stringify({ toasts, open, dialogs: window.__saDialogs || [] });
            })()''', "returnByValue": True})
            seen = json.loads(read.get("result", {}).get("result", {}).get("value") or "{}")
            result["toasts"] = seen.get("toasts", [])
            result["connect_panel_open"] = bool(seen.get("open"))
            dialogs = seen.get("dialogs") or []
            result["dialog"] = str(dialogs[0])[:120] if dialogs else ""

        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        install = [t for t in targets if "/extension-install" in t.get("url", "")]
        result["install_tab_opened"] = bool(install)
        # **开出来说了什么，和开没开一样重要。** 送他去一页叫他"重新安装"
        # 而不是"覆盖原文件夹"，后果是他同时装两份、已连的账号留在旧的那一份上。
        if install:
            await asyncio.sleep(2)                    # 那一页要跑一下自检才换标题
            async with websockets.connect(install[0]["webSocketDebuggerUrl"],
                                          max_size=None) as tab:
                trpc = await shape._rpc_factory(tab)  # noqa: SLF001
                await trpc("Runtime.enable")
                text = await trpc("Runtime.evaluate", {
                    "expression": "document.body.innerText",
                    "returnByValue": True, "timeout": 10000})
                result["install_page_text"] = str(
                    text.get("result", {}).get("result", {}).get("value") or "")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)
    return result


async def run(chrome: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING"}, ensure_ascii=False))
        return 2
    workspace = Path(tempfile.mkdtemp(prefix="sa-stale-ws-"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    problems: list[str] = []
    try:
        old = _materialize_old(workspace)
        new = workspace / "new-extension"
        with zipfile.ZipFile(ZIP) as archive:
            archive.extractall(new)

        stale = await _one_case(chrome, old, "old", DEBUG_PORT)
        fresh = await _one_case(chrome, new, "new", DEBUG_PORT + 1)
    finally:
        server.shutdown()
        shutil.rmtree(workspace, ignore_errors=True)

    # ---- 旧版：必须被拦住，而且必须真的把更新说明开出来 ----
    if stale.get("error"):
        problems.append(f"旧版这一侧没跑起来（{stale['error']}）——**这不是通过**")
    else:
        said = " ".join(stale.get("toasts") or [])
        if "旧版" not in said:
            problems.append(
                f"**旧插件点「连接账号」，页面没说他装的是旧版**：{said or '（一条提示都没有）'}"
                "——他会以为点了没反应，而那正是他这些天一直撞的那堵墙")
        if not stale.get("install_tab_opened"):
            problems.append(
                "**没有把更新说明打开**——只说「你装的是旧版」而不给去处，"
                "等于让他自己去找；`window.open(\"/extension-install\")` 那一行没生效")
        else:
            # **那一页得叫他「覆盖原文件夹」，不能叫他重新装一个。**
            # 换个地方装 → Chrome 给新 ID → 他同时装两份 → 已连好的账号
            # 留在旧的那一份上，而界面看起来一切正常。
            page = stale.get("install_page_text") or ""
            if "覆盖进你原来那个插件文件夹" not in page:
                problems.append(
                    "更新说明开出来了，**但没告诉他要覆盖进原来那个文件夹**："
                    f"{page[:160] or '（读不到那一页的正文）'}——"
                    "他会新建一个文件夹装，于是同时装两份，已连的账号留在旧的那份上")
            if "你装的是旧版" not in page:
                problems.append(
                    "更新说明没认出他装的是旧版（标题没换）——"
                    f"他看到的是一页教人从头安装的说明：{page[:120]}")
            # **不许在同一页上说反话。**（2026-08-10 真 Chrome 里读回整页才看见的）
            #
            # 他装的是 v0.0.0.22，下限是 v0.0.0.9。标题说「你装的是旧版」，
            # 而紧接着第一段原来写的是「资料库至少需要 v0.0.0.9」——
            # 22 比 9 大，那句话等于告诉他不用动。他要么以为这页坏了，要么就不动。
            #
            # 根因是 `paintUpdate()` 对两个调用方说同一句话，而只有
            # 「低于下限」那一支该那么说。判据只盯 JSON、漏掉用户读的散文，这个仓栽过。
            minimum = FAKE["/health"]["minimum_extension_version"]       # 0.0.0.9
            if f"至少需要 v{minimum}" in page or f"至少</strong>需要 <strong>v{minimum}" in page:
                problems.append(
                    f"**那一页同时说了两句相反的话**：标题「你装的是旧版」，"
                    f"正文却说「至少需要 v{minimum}」——而他装的是 "
                    f"v{stale.get('extension_version')}，比它大。"
                    "算术摆在他眼前，他会以为这页坏了或者不用动")
            if "连接账号要更新之后才成" not in page:
                problems.append(
                    "那一页没说清**为什么**要更新（不是版本太低，是连接账号要最新的）——"
                    f"他读到的理由对不上他的处境：{page[:160]}")
        if stale.get("dialog"):
            problems.append(
                f"旧版这一侧弹了对话框「{stale['dialog']}」——那说明走的是"
                "「没检测到插件」或「版本低于下限」，**不是本题要验的那一支**")

    # ---- 新版：必须**不**被拦 ----
    # 只跑上面那一半会得到一个红得凑巧的结论：切错位置的判据照样能给出不同答案。
    if fresh.get("error"):
        problems.append(f"新版这一侧没跑起来（{fresh['error']}）——正例不绿，反例的红就不算数")
    else:
        said = " ".join(fresh.get("toasts") or [])
        if "旧版" in said:
            problems.append(
                f"**发布包自己也被当成旧版拦下来了**：{said}——"
                "那他更新完还是连不上，等于这一版白发")
        if not fresh.get("connect_panel_open"):
            problems.append(
                f"新版点完连接面板没打开（toast={said or '无'}）——"
                "「就地连接」这件事没成立，他还是得跳走")
        if fresh.get("install_tab_opened"):
            problems.append("新版也被送去了更新说明——它就是最新的那一版")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "old_build_commit": OLD_COMMIT,
        "old": stale,
        "new": fresh,
        "problems": problems,
        "message_zh": ("旧插件点「连接账号」会被当场拦住并送去更新说明；"
                       "发布包不被拦，连接面板就地打开。"
                       if not problems else
                       "**他下一步要做的那个动作，这条路上至少有一处不成立。**"),
        "what_this_does_not_prove": (
            "不是打生产：生产那一页在 Cloudflare Access 后面（实测 302），"
            "无头 Chrome 拿不到他的身份，也不该去绕。这里送的是 apps/pwa/ 里那几个真文件，"
            "而部署第 9 步已逐字节证明「仓 = 主机 = 镜像」。"
            "也不证明他点完之后连接**成功**——那要他自己在浏览器里选「允许」。"),
    }
    out = ROOT / "evidence/G3/STALE_EXTENSION_IS_BLOCKED.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="旧插件点「连接账号」拦不拦得住")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
