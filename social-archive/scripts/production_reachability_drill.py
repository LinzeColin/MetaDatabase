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
  try {
    const data = await SA.api("/v1/library?limit=1");
    out.api_call = "resolved";
    out.api_keys = Object.keys(data || {}).slice(0, 8);
    const preview = JSON.stringify(data).slice(0, 120);
    out.api_looks_like_a_web_page = preview.includes("<html") || preview.includes("<!DOCTYPE");
    out.api_items = Array.isArray(data && data.items) ? data.items.length : null;
  } catch (error) {
    out.api_call = "threw";
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


async def run(chrome: str, token: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING",
                          "message_zh": "发布包不存在——先跑 scripts/build_extension_package.py"},
                         ensure_ascii=False, indent=2))
        return 2

    workspace = Path(tempfile.mkdtemp(prefix="sa-production-"))
    unpacked = workspace / "extension"
    with zipfile.ZipFile(ZIP) as archive:
        archive.extractall(unpacked)

    # **注意这里没有 --host-resolver-rules。** 这正是它和其余演练的唯一区别：
    # 域名要真的解析到他那台服务器，中间要真的经过 Cloudflare。
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync",
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
