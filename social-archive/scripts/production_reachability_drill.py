#!/usr/bin/env python3
"""他的插件，够得着生产吗（2026-08-07）。

## 为什么非要单独有这一个

仓里十四个真 Chrome 演练，**没有一个碰过真生产**。它们全都带着

    --host-resolver-rules=MAP social-archive.linzezhang.com 127.0.0.1:<假端口>

把档案馆域名指到本机的假服务器上。那是对的——演练要可重复、要能造各种
边界情况。但它意味着一件事：**「插件能不能连上他那台真服务器」从来没被验过。**

而验收条件第 4 条写的正是「不拿本地结果冒充线上结果」。

## 它答的是一个具体的问题

装上发布包 → **用插件自己配置的那个端点** → 用真令牌调 `/v1/library`，
看它到底拿到什么。不需要任何人登录：插件的后台请求本来就没有浏览器会话
（跨源 fetch 默认不带 Cookie），这里量的正是那条路。

**端点绝不能由探针指定。** 第一版我写死成资料库域名
`social-archive.linzezhang.com`——那个在 Cloudflare Access 后面，于是量出
「插件够不着生产」，我差点就那么报了。插件真正用的是 runtime-config.json 里的
api 域名，根本不是那一个。**我量的是一个他那边不存在的配置。**
资料库域名现在留作**负对照**：它必须是不通的，否则这条探针连"挡住"都认不出来。

## 令牌

从生产主机现取，**只存在于内存和发给 Chrome 的那条 CDP 消息里**：
不落盘、不进证据文件、不打印。证据里只记「拿到没拿到」。

    python3 scripts/production_reachability_drill.py
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "dist" / "social-archive-extension.zip"
DOWNLOAD_URL = ("https://social-archive-api.linzezhang.com"
                "/downloads/social-archive-extension.zip")
DEBUG_PORT = 9384
# 资料库（PWA）那个域名在 Cloudflare Access 后面——**它是负对照，不是端点**。
LIBRARY_HOST = "https://social-archive.linzezhang.com"
EVIDENCE = ROOT / "evidence" / "G5" / "PRODUCTION_REACHABLE_FROM_EXTENSION.json"

_spec = importlib.util.spec_from_file_location(
    "_shape_for_production", ROOT / "scripts/list_shape_end_to_end_drill.py")
shape = importlib.util.module_from_spec(_spec)
sys.modules["_shape_for_production"] = shape
_spec.loader.exec_module(shape)

# **探针里出现的 %(token)s 是唯一一处密钥。** 它不进证据、不进标准输出。
PROBE = r"""
(async () => {
  const out = {};
  // **端点用插件自己的默认值，不许由探针指定。**
  //
  // 第一版我把端点写死成资料库那个域名（social-archive.linzezhang.com），
  // 它在 Cloudflare Access 后面，于是量出「插件够不着生产」并且我差点就那么报了。
  // 而插件的默认端点是 runtime-config.json 里的 **api 域名**，根本不是那一个。
  // **我量的是一个他那边不存在的配置。**
  const existing = await SA.getConfig();
  out.endpoint_the_extension_itself_uses = existing.endpoint;
  await SA.setConfig({ endpoint: existing.endpoint, token: "%(token)s" });

  // ① 插件自己的那层封装——他那边真正走的就是这一条
  const started = Date.now();
  try {
    // **用插件的真实默认超时（15s），不许为了让演练变绿而放宽。**
    // 他遇到的就是那个值；放宽等于换一个他那边不存在的配置来测。
    const data = await SA.api("/v1/library?limit=1");
    out.api_ms = Date.now() - started;
    out.api_call = "resolved";
    out.api_keys = Object.keys(data || {}).slice(0, 8);
    const preview = JSON.stringify(data).slice(0, 120);
    out.api_looks_like_a_web_page = preview.includes("<html") || preview.includes("<!DOCTYPE");
    out.api_items = Array.isArray(data && data.items) ? data.items.length : null;
  } catch (error) {
    out.api_call = "threw";
    out.api_ms = Date.now() - started;
    out.api_message = String(error && error.message).slice(0, 200);
    out.api_status = (error && error.status) || null;
  }

  // ② 权限到底有没有（`Failed to fetch` 也可能只是没授权）
  try {
    out.has_host_permission = await chrome.permissions.contains(
      { origins: [existing.endpoint + "/*"] });
  } catch (error) { out.has_host_permission = "问不出来：" + String(error).slice(0, 80); }

  // ③ 跟随重定向的裸 fetch
  try {
    const response = await fetch(existing.endpoint + "/v1/library");
    out.raw_status = response.status;
    out.raw_redirected = response.redirected;
    out.raw_final_host = new URL(response.url).host;
    out.raw_body_head = (await response.text()).slice(0, 60).replace(/\s+/g, " ");
  } catch (error) {
    out.raw_error = String(error).slice(0, 200);
  }

  // ④ **不跟随重定向**——把「网络不通」和「跳到一个插件没权限的域名」分开。
  //    这两件事在 `Failed to fetch` 这一个字符串下长得一模一样，
  //    而它们的下一步完全不同。
  try {
    const manual = await fetch(existing.endpoint + "/v1/library", { redirect: "manual" });
    out.manual_type = manual.type;
    out.manual_status = manual.status;
  } catch (error) {
    out.manual_error = String(error).slice(0, 200);
  }

  // ⑤ 同域名的另一条路，确认不是单条路由的问题
  try {
    const health = await fetch(existing.endpoint + "/health", { redirect: "manual" });
    out.health_type = health.type;
    out.health_status = health.status;
  } catch (error) {
    out.health_error = String(error).slice(0, 160);
  }
  // ⑥ **负对照**：资料库域名在 Cloudflare Access 后面，这一条必须是不通的。
  //    没有它，一条永远说"通"的探针也能让上面全绿。
  try {
    const blocked = await fetch("%(blocked)s/v1/library", { redirect: "manual" });
    out.control_blocked_host_type = blocked.type;
    out.control_blocked_host_status = blocked.status;
  } catch (error) {
    out.control_blocked_host_error = String(error).slice(0, 120);
  }
  return JSON.stringify(out);
})()
"""


async def _open_connect_panel(base: str, extension_id: str,
                              press: str | None = None) -> dict:
    """把连接面板对着**真生产**打开，看它画出什么。

    面板启动就调 `/v1/accounts`；调不通它会显示「读不到可连接的来源」。
    所以这一页正好回答验收条件第 1 条的两半：

      · **有没有一颗结构上不可能成功的按钮**——能画出按钮，说明服务端
        确实报了这个平台可同步；
      · **做不到自动的平台有没有当场说清**——`sync_supported === false` 的
        要照列，只是不画按钮，旁边带服务端给的原因。**不显示不等于说清。**

    面板本来是嵌在资料库页里的 iframe，这里单开一页：`parent` 就是它自己，
    那句 postMessage 落空，不影响渲染。资料库页在 Cloudflare Access 后面，
    单开面板正好绕过「要人登录」，而量到的恰恰是插件那一侧。
    """
    url = f"chrome-extension://{extension_id}/connect-frame.html"
    # **快照要在建页之前取。** 取在之后的话，新建的那一页自己就在"已见过"里，
    # 于是永远被过滤掉，报「连接面板没打开」——一条自己把自己挡住的判据。
    seen_before = {item.get("id") for item in
                   json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())}
    urllib.request.urlopen(urllib.request.Request(
        base + "/json/new?" + url, method="PUT"), timeout=10).read()
    # **定死的等待会变成假失败。** 上一次就报了「连接面板没打开」，
    # 而它只是没在 3 秒里出现。轮询到出现为止，超时了再说打不开。
    pages: list = []
    for _ in range(20):
        await asyncio.sleep(0.5)
        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        pages = [item for item in targets if item.get("type") == "page"
                 and "connect-frame.html" in item.get("url", "")
                 and item.get("id") not in seen_before]
        if pages:
            break
    if not pages:
        return {"drill_error": "连接面板没打开（等了 10 秒）"}
    async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await shape._rpc_factory(ws)
        await rpc("Runtime.enable")
        await asyncio.sleep(2)                       # 等它把 /v1/accounts 拉回来
        got = await rpc("Runtime.evaluate", {
            "expression": r"""JSON.stringify((() => {
              const rows = Array.from(document.querySelectorAll("#list li"));
              const text = document.body.innerText || "";
              return {
                rows: rows.length,
                buttons: rows.map(li => {
                  const button = li.querySelector("button");
                  return {
                    name: (li.querySelector(".name") || {}).textContent || "",
                    state: (li.querySelector(".state") || {}).textContent || "",
                    button: button ? button.textContent : null,
                    // **没有按钮的那一行，必须自己带着原因。**
                    // 只数「列出来了几行」是查不出「列了但没说为什么」的。
                    own_text: (li.innerText || "").replace(/\s+/g, " ").trim(),
                  };
                }),
                says_it_cannot_read_sources: text.includes("读不到可连接的来源"),
                says_nothing_syncs: text.includes("本版本还没有能自动同步的来源"),
                manual_only_mentioned: text.includes("只能手动"),
                body_head: text.slice(0, 200).replace(/\s+/g, " "),
              };
            })())""",
            "returnByValue": True, "timeout": 20000})
        payload = got.get("result", {})
        if payload.get("exceptionDetails"):
            return {"drill_error": str(payload["exceptionDetails"])[:200]}
        panel = json.loads(payload["result"]["value"])

        # **真按一次那颗按钮。** 画出来了不等于按得动——验收条件第 1 条写的是
        # 「绝不给一颗结构上不可能成功的按钮」，而这个项目最贵的一个缺陷正是
        # 这种：`chrome.permissions.request` 在 service worker 里**结构上不可能**
        # 成功，于是每颗按钮在全新安装上都是死的，而所有判据都绿。
        #
        # 挑 Chrome 书签：它不需要任何平台登录，也不托管任何 Cookie。
        # **权限框弹出来就停在那儿**（没人去点），所以这一按**不会往他的档案馆
        # 写任何东西**——没有授权就不会同步。这是有意的：验的是"按得动"，
        # 不是"同步完了"，而后者会往他的真库里塞测试数据。
        #
        # 三种结局要分开，它们的下一步完全不同：
        #   prompted  → 弹框起来了 = 结构上走得通（**这就是要的信号**）
        #   said_no   → 当场回了"没有获得需要的授权" = 请求根本没弹出来
        #   errored   → 报了别的错
        if press is None:
            return panel
        clicked = await rpc("Runtime.evaluate", {
            "expression": (r"""(async () => {
              // **一次只按一颗，按完这一页就关掉。**
              //
              // 2026-08-07 第一版在同一页里连按 7 颗，结果：前两颗停在
              // 「正在连接…」，后五颗当场回「还没有获得需要的授权」，
              // 看起来像五个平台的按钮全是死的——**而那是我自己造出来的**：
              // Chrome 一次只允许一个权限框，前面的框没人点，后面的请求就被直接拒。
              // 用户不会连按 7 颗。差点把一条自伤报成产品缺陷。
              const rows = Array.from(document.querySelectorAll("#list li"))
                .filter(li => li.querySelector("button"));
              const li = rows.find(row =>
                ((row.querySelector(".name") || {}).textContent || "").trim() === "%(press)s");
              if (!li) return JSON.stringify({ skipped: "面板里没有这一行：%(press)s" });
              const button = li.querySelector("button");
              const before = button.textContent;
              button.click();
              await new Promise(r => setTimeout(r, 3000));
              const box = document.querySelector("#note");
              return JSON.stringify({ pressed: [{
                name: "%(press)s", before,
                after: button.textContent,
                disabled: button.disabled,
                note: (box ? box.innerText : "**页面里没有 #note**")
                        .replace(/\s+/g, " ").slice(0, 120),
              }] });
            })()""" % {"press": press}),
            "userGesture": True, "awaitPromise": True,
            "returnByValue": True, "timeout": 30000})
        pressed_payload = clicked.get("result", {})
        if pressed_payload.get("exceptionDetails"):
            panel["press"] = {"drill_error": str(pressed_payload["exceptionDetails"])[:200]}
        else:
            panel["press"] = json.loads(pressed_payload["result"]["value"])
    # **关掉这张页。** 那个没人点的权限框跟着它走——不关的话，
    # 下一个平台的请求会被 Chrome 直接拒，看起来像那个平台的按钮是死的。
    urllib.request.urlopen(urllib.request.Request(
        base + "/json/close/" + pages[0]["id"], method="GET"), timeout=10).read()
    await asyncio.sleep(1)
    return panel


async def run(chrome: str, token: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING",
                          "message_zh": "发布包不存在——先跑 scripts/build_extension_package.py"},
                         ensure_ascii=False, indent=2))
        return 2

    workspace = Path(tempfile.mkdtemp(prefix="sa-production-"))
    unpacked = workspace / "extension"

    # **解的是他下载到的那一份，不是我本地打的那一份。**
    #
    # 2026-08-07 之前这里解 `dist/social-archive-extension.zip`——我这台机器上
    # 刚打出来的那个。那和「他点下载拿到什么」是两件事，而这个演练的题目
    # 恰恰是后者。今天两者 sha256 一致（45d11d14…），但**一致是要量出来的，
    # 不是假定的**：哪天部署漏了一步，本地这份照样是新的。
    downloaded = workspace / "downloaded.zip"
    served_sha = local_sha = ""
    try:
        # **要带浏览器 UA。** 2026-08-07 实测：默认的 `Python-urllib/3.x`
        # 被 Cloudflare 直接 403，换成浏览器 UA 就 200。
        # 他用 Chrome 点下载不受影响，但**任何脚本去取这个包都会被挡**——
        # 包括这个演练。第一次跑就报「下载不到他那份包」，
        # 而包本身是好好的。
        request = urllib.request.Request(
            DOWNLOAD_URL, headers={"User-Agent": "Mozilla/5.0 (drill)"})
        with urllib.request.urlopen(request, timeout=90) as response:
            downloaded.write_bytes(response.read())
        served_sha = hashlib.sha256(downloaded.read_bytes()).hexdigest()
        source = downloaded
    except Exception as error:                       # noqa: BLE001
        problems_early = f"下载不到他那份包（{DOWNLOAD_URL}）：{str(error)[:120]}"
        source = ZIP
    else:
        problems_early = ""
    if ZIP.is_file():
        local_sha = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as archive:
        archive.extractall(unpacked)

    # **注意这里没有 --host-resolver-rules。** 这正是它和其余演练的唯一区别：
    # 域名要真的解析到他那台服务器，中间要真的经过 Cloudflare。
    # **无头。** 2026-08-07 Owner 说：「为什么你永远都要不停开了又关关了又开
    # 我的浏览器」——13 个演练每个都起一个**可见的** Chrome，一次部署跑 15 个，
    # 就是十五次抢他的屏幕，而我调试时还会连跑好几遍。
    # 这些演练一个都不需要人看着，弹出来纯粹是我没加这个开关。
    # 要看着调试时设 SA_DRILL_HEADED=1。
    headless = [] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync",
         *headless,
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    measured: dict = {}
    problems: list[str] = [problems_early] if problems_early else []
    if served_sha and local_sha and served_sha != local_sha:
        problems.append(
            f"**他下载到的包和仓里刚打的不是同一个**（下载 {served_sha[:16]}，"
            f"本地 {local_sha[:16]}）——发出去的不是这一版代码。")
    try:
        for _ in range(40):
            try:
                version = json.loads(
                    urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"},
                             ensure_ascii=False))
            return 2

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await shape._rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": str(unpacked)})
            extension_id = loaded.get("result", {}).get("id") or ""
        if not extension_id:
            problems.append("Chrome 装不上这个包")
        else:
            await asyncio.sleep(3)
            targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
            workers = [t for t in targets if t.get("type") == "service_worker"
                       and extension_id in t.get("url", "")]
            if not workers:
                problems.append("装上了，但 service worker 起不来")
            else:
                async with websockets.connect(workers[0]["webSocketDebuggerUrl"],
                                              max_size=None) as ws:
                    rpc = await shape._rpc_factory(ws)
                    await rpc("Runtime.enable")
                    got = await rpc("Runtime.evaluate", {
                        "expression": PROBE % {"blocked": LIBRARY_HOST, "token": token},
                        "awaitPromise": True, "returnByValue": True, "timeout": 60000})
                    payload = got.get("result", {})
                    if payload.get("exceptionDetails"):
                        problems.append(f"探针跑炸了：{str(payload['exceptionDetails'])[:200]}")
                    else:
                        measured = json.loads(payload["result"]["value"])
            if measured:
                # 第一趟：只看面板画出什么，不按任何按钮。
                panel = await _open_connect_panel(base, extension_id)
                # 之后每颗按钮**各开一张新面板页**，按完就关。
                # 同一页里连按会互相打架：Chrome 一次只允许一个权限框。
                everyone = [row["name"] for row in panel.get("buttons", [])
                            if row.get("button")]
                presses = []
                for name in everyone:
                    one = await _open_connect_panel(base, extension_id, press=name)
                    presses.extend((one.get("press") or {}).get("pressed", [])
                                   or [{"name": name, "drill_error": str(one.get("press"))[:120]}])
                panel["press"] = {"pressed": presses}
                measured["connect_panel"] = panel
    finally:
        process.terminate()
        shutil.rmtree(workspace, ignore_errors=True)

    # **判读。** 「调用没抛异常」不等于「通了」——这正是最危险的那种失败：
    # 跟随重定向落在登录页上，HTTP 200，`response.ok` 为真，
    # 于是插件把**一整页 HTML** 当成 API 的返回值收下，界面既不报错也没有数据。
    if measured.get("api_call") == "resolved" and measured.get("api_looks_like_a_web_page"):
        problems.append(
            "**插件收到的是一张网页，不是数据**——请求被挡在 Cloudflare Access 前面，"
            "跟着 302 落到登录页，HTTP 200，于是插件当成成功。"
            "界面会既不报错也没有条目。")
    elif measured.get("api_call") == "resolved" and measured.get("api_items") is None:
        problems.append("调用没抛异常，但返回里没有 items——插件读不到条目。")
    if measured.get("raw_redirected") and "linzezhang.com" not in str(
            measured.get("raw_final_host", "")):
        problems.append(
            f"请求被重定向到了 {measured.get('raw_final_host')}——**它到不了你的服务**。")
    if measured.get("api_call") == "threw":
        # **把两种「Failed to fetch」分开。** 它们在同一个字符串下长得一样，
        # 下一步却完全不同：一个要改 Cloudflare 的策略，一个要查网络。
        if measured.get("has_host_permission") is False:
            problems.append("插件没有这个域名的权限——`host_permissions` 里少了它。")
        elif measured.get("manual_status") in (301, 302, 303, 307, 308) \
                or measured.get("manual_type") == "opaqueredirect":
            problems.append(
                "**网络是通的，是那道 302 把它打断的**：服务在 Cloudflare Access 后面，"
                "请求被 302 到 cloudflareaccess.com——而那个域名不在插件的权限里，"
                f"于是 Chrome 直接掐断（{measured.get('api_message')}）。"
                "**插件带的 Bearer 令牌根本到不了应用**，因为 Access 在应用之前就拦了。")
        else:
            problems.append(
                f"插件调不通生产：{measured.get('api_message')}"
                f"（裸 fetch：{measured.get('raw_error') or measured.get('raw_status')}）")
    if not measured:
        problems.append("**一个数都没量到**——这不是通过。")

    # **面板对着真生产画出什么。** 验收条件第 1 条的两半都在这里。
    panel = measured.get("connect_panel") or {}
    if measured and not panel:
        problems.append("连接面板那一段没量到——**这不是通过**。")
    elif panel.get("drill_error"):
        problems.append(f"连接面板打不开：{panel['drill_error']}")
    else:
        if panel.get("says_it_cannot_read_sources"):
            problems.append(
                "**面板显示「读不到可连接的来源」**——他打开就是这一句，"
                "一颗按钮都没有。")
        if panel.get("says_nothing_syncs"):
            problems.append("**面板说「本版本还没有能自动同步的来源」**——"
                            "服务端一个可同步平台都没报。")
        actionable = [row for row in panel.get("buttons", []) if row.get("button")]
        if not actionable:
            problems.append("**面板里一颗能点的按钮都没有**——"
                            f"画了 {panel.get('rows')} 行，没有一行带按钮。")
        for row in panel.get("buttons", []):
            if row.get("name", "").islower() and "_" in row.get("name", ""):
                problems.append(f"**按钮上写的是平台 id 不是名字**：{row['name']}")
            # **「列出来了」不等于「说清了」。** 验收条件第 1 条要的是
            # 「做不到自动的平台，界面必须**当场说清**这个只能手动保存」——
            # 一行只有名字、没有原因，和不显示一样让人卡住。
            if not row.get("button"):
                name = row.get("name", "")
                explanation = row.get("own_text", "").replace(name, "").strip()
                if len(explanation) < 8:
                    problems.append(
                        f"**{name} 不能自动同步，却没说为什么**（那一行只有"
                        f"「{row.get('own_text', '')[:40]}」）——列出来不等于说清。")

        # **按下去走不走得通。** 画出来了不等于按得动。
        press = panel.get("press") or {}
        if press.get("drill_error"):
            problems.append(f"按按钮那一步跑炸了：{press['drill_error']}")
        elif press.get("skipped"):
            problems.append(f"没能按到那颗按钮：{press['skipped']}")
        else:
            for one in press.get("pressed", []):
                name, note = one.get("name", "?"), one.get("note", "")
                if "还没有获得需要的授权" in note and one.get("after") != "正在连接…":
                    problems.append(
                        f"**{name}：按下去当场回「还没有获得需要的授权」**——"
                        "权限框根本没弹出来。这正是 service worker 里 "
                        "chrome.permissions.request 结构上不可能成功那个缺陷的形状："
                        "每颗按钮在全新安装上都是死的。")
                elif one.get("after") != "正在连接…":
                    problems.append(
                        f"**{name}：按下去之后按钮变成了「{one.get('after')}」**"
                        f"（提示：{note[:60]}）——它没有停在等授权那一步。")
            if not press.get("pressed"):
                problems.append("**一颗按钮都没按到**——这不是通过。")
    # **负对照要被判，不能只被量。**
    #
    # 资料库域名在 Cloudflare Access 后面，从插件里访问必然被 302 打断
    # （`opaqueredirect`，或者直接抛）。**这一条要是也"通"了，
    # 说明这条探针根本分辨不出「挡住了」和「没挡住」**——那么它给出的
    # 「通了」也就不值钱。宁可报失败，也不要一条永远说通的探针。
    control_type = measured.get("control_blocked_host_type")
    control_blocked = (control_type == "opaqueredirect"
                       or bool(measured.get("control_blocked_host_error")))
    if measured and not control_blocked:
        problems.append(
            f"**负对照没被挡住**（{control_type}）——"
            "资料库域名在 Cloudflare Access 后面，从插件里本该访问不到。"
            "它都通了，说明这条探针分辨不出通与不通，**上面那个「通了」不作数**。")

    status = "PASS" if not problems and measured.get("api_items") is not None else "FAIL"
    if status == "FAIL" and not problems:
        problems.append("判为不通过，但没说出是哪一条——**这条判读本身有缺口**。")
    report = {
        "status": status,
        "endpoint": measured.get("endpoint_the_extension_itself_uses"),
        "token_supplied": bool(token),          # **只记有没有，不记是什么**
        "package_he_would_download": {
            "url": DOWNLOAD_URL,
            "sha256": served_sha[:16] or "（没下到）",
            "same_as_repo_build": bool(served_sha) and served_sha == local_sha,
        },
        "measured_in_real_chrome": measured,
        "problems": problems,
        "what_this_answers_zh": (
            "装上发布包、用**插件自己配置的端点**、拿真令牌调 /v1/library，"
            "**插件到底拿到什么**。其余十四个演练都把这个域名映射到本机假服务器，"
            "所以这条路此前从没被走过。负对照是资料库域名（在 Access 后面），它必须不通。"),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


def main() -> int:
    chrome = os.environ.get("SA_CHROME") or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not Path(chrome).exists():
        print(json.dumps({"status": "FAIL", "error_code": "CHROME_MISSING",
                          "message_zh": f"找不到 Chrome：{chrome}"}, ensure_ascii=False))
        return 2
    # 令牌从生产主机现取，不落盘。
    host = os.environ.get("SOCIAL_ARCHIVE_DEPLOY_HOST", "linze-ovh")
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         "sudo cat /opt/social-archive/runtime/secrets/social_archive_api_token"],
        capture_output=True, text=True, check=False)
    token = done.stdout.strip()
    if not token:
        print(json.dumps({"status": "FAIL", "error_code": "TOKEN_UNREADABLE",
                          "message_zh": "取不到生产令牌——**这不是通过**"},
                         ensure_ascii=False))
        return 2
    return asyncio.run(run(chrome, token))


if __name__ == "__main__":
    sys.exit(main())
