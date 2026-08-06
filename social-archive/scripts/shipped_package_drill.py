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

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import list_shape_end_to_end_drill as shape          # noqa: E402  复用假站与证书

ZIP = ROOT / "dist" / "social-archive-extension.zip"
DEBUG_PORT = 9381

PROBE = r"""
(async () => {
  const out = { modules: {}, permissions: {}, manifest: {} };
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
    server = ThreadingHTTPServer(("127.0.0.1", shape.FAKE_PORT), shape._Fake)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--password-store=basic", "--use-mock-keychain",
         f"--host-resolver-rules=MAP *xiaohongshu.com 127.0.0.1:{shape.FAKE_PORT}",
         "--ignore-certificate-errors", "--allow-insecure-localhost", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    load_error = ""
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
                                    {"expression": PROBE, "userGesture": True,
                                     "awaitPromise": True, "returnByValue": True,
                                     "timeout": 60000})
                    payload = got.get("result", {})
                    if payload.get("exceptionDetails"):
                        problems.append(f"探针跑炸了：{str(payload['exceptionDetails'])[:300]}")
                    else:
                        measured = json.loads(payload["result"]["value"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        shutil.rmtree(workspace, ignore_errors=True)

    for name, present in (measured.get("modules") or {}).items():
        if not present:
            problems.append(f"**包里缺 {name} 那一份**——它在源码目录里有，在他下载的包里没有")
    if measured.get("manifest", {}).get("version") != (ROOT / "VERSION").read_text(encoding="utf-8").strip():
        problems.append(f"包里的版本是 {measured.get('manifest', {}).get('version')}，"
                        f"而仓是 {(ROOT / 'VERSION').read_text(encoding='utf-8').strip()}"
                        "——他下载到的是旧包")

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
