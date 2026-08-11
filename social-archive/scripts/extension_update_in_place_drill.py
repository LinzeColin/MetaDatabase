#!/usr/bin/env python3
"""在原文件夹里覆盖再重载：ID 变不变、版本更不更新、**已配对的凭据还在不在**。

## 为什么单开这一个

`extension_install_page_drill.py` 的开头写着这么一段：

    未打包扩展的 ID 由**文件夹路径**决定。实测：
        同一个文件夹装两次 → ID 相同
        在原文件夹里换掉文件再重新载入 → ID 不变、版本更新、**已存的凭据还在**

**那段话是散文，没有任何演练做过这件事。** 而它同时出现在安装页上、
使用说明里、以及我给 Owner 的每一条更新指引里——他下一步要做的就是它。

万一覆盖+重载会把已配对的凭据弄丢，他更新完就得从头再配一遍；
而那句「凭据还在」会让他以为是别的地方坏了。

这个仓有过一模一样的账：RUNBOOK 里 58 条只落成 12 件检查器，
四分之三停在散文态，其中一条写过五次却从没有人用。

## 它怎么验

1. 起 Chrome，从文件夹 F 装一个**改成旧版本号**的扩展
2. 往 `chrome.storage` 里写一份配置（endpoint + token），模拟他已经配对过
3. **在同一个 F 里覆盖成发布包那一份**（这就是他要做的那一下）
4. 对同一个 F 再 `Extensions.loadUnpacked` —— Chrome 对未打包扩展当作重载
5. 逐条量：ID 一样吗、版本更新了吗、那份配置还在吗

## 它不证明什么

不证明他手上那个文件夹在 Finder 里覆盖的体验（那是他做的事）。
这里证明的是**覆盖之后 Chrome 这一侧会怎样**——而那正是那三句承诺的内容。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import list_shape_end_to_end_drill as shape          # noqa: E402  复用 rpc 工厂

ZIP = ROOT / "dist" / "social-archive-extension.zip"
DEBUG_PORT = 9383
OLD_VERSION = "0.0.0.1"


async def _worker_rpc(base: str, extension_id: str):
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    workers = [t for t in targets if t.get("type") == "service_worker"
               and extension_id in t.get("url", "")]
    if not workers:
        return None, None
    ws = await websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None)
    rpc = await shape._rpc_factory(ws)                      # noqa: SLF001
    await rpc("Runtime.enable")
    return ws, rpc


async def _evaluate(rpc, expression: str) -> dict:
    got = await rpc("Runtime.evaluate", {
        "expression": expression, "awaitPromise": True,
        "returnByValue": True, "timeout": 15000})
    payload = got.get("result", {})
    if payload.get("exceptionDetails"):
        return {"drill_error": str(payload["exceptionDetails"])[:200]}
    return json.loads(payload["result"]["value"])


async def run(chrome: str) -> int:
    if not ZIP.is_file():
        print(json.dumps({"status": "FAIL", "error_code": "PACKAGE_MISSING"},
                         ensure_ascii=False, indent=2))
        return 2
    workspace = Path(tempfile.mkdtemp(prefix="sa-update-"))
    folder = workspace / "extension"                        # **他那个文件夹**
    problems: list[str] = []
    before: dict = {}
    after: dict = {}

    with zipfile.ZipFile(ZIP) as archive:
        archive.extractall(folder)
    shipped_version = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["version"]
    # 先把它改成旧版本，好让"更新"这件事有东西可量
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = OLD_VERSION
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    process = subprocess.Popen(
        [chrome, f"--user-data-dir={workspace / 'profile'}",
         f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run",
         *([] if __import__("os").environ.get("SA_DRILL_HEADED") else ["--headless=new"]),   # Owner 不该被弹窗打断；调试设 SA_DRILL_HEADED=1
         "--no-default-browser-check", "--disable-sync", "--disable-background-networking",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                               # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 2

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await shape._rpc_factory(ws)              # noqa: SLF001
            loaded = await rpc("Extensions.loadUnpacked", {"path": str(folder)})
            first_id = loaded.get("result", {}).get("id") or ""
        if not first_id:
            problems.append("第一次就装不上，后面没得比")
        else:
            await asyncio.sleep(3)
            ws, rpc = await _worker_rpc(base, first_id)
            if not rpc:
                problems.append("装上了但 service worker 起不来")
            else:
                # **模拟他已经配对过**：往扩展自己的存储里写一份配置。
                before = await _evaluate(rpc, '''(async () => {
                    await chrome.storage.local.set({ endpoint: "https://drill.example",
                                                     token: "drill-token-abc" });
                    const got = await chrome.storage.local.get(["endpoint", "token"]);
                    return JSON.stringify({ version: chrome.runtime.getManifest().version,
                                            id: chrome.runtime.id, stored: got });
                })()''')
                await ws.close()

            # **他要做的那一下**：在同一个文件夹里覆盖成新的那一份。
            with zipfile.ZipFile(ZIP) as archive:
                archive.extractall(folder)

            async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
                rpc = await shape._rpc_factory(ws)          # noqa: SLF001
                reloaded = await rpc("Extensions.loadUnpacked", {"path": str(folder)})
                second_id = reloaded.get("result", {}).get("id") or ""
            await asyncio.sleep(3)
            ws, rpc = await _worker_rpc(base, second_id or first_id)
            if rpc:
                after = await _evaluate(rpc, '''(async () => {
                    const got = await chrome.storage.local.get(["endpoint", "token"]);
                    return JSON.stringify({ version: chrome.runtime.getManifest().version,
                                            id: chrome.runtime.id, stored: got });
                })()''')
                await ws.close()
            else:
                problems.append("覆盖重载之后 service worker 起不来——**他的插件会直接坏掉**")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(workspace, ignore_errors=True)

    if before and after:
        if before.get("id") != after.get("id"):
            problems.append(
                f"**ID 变了**（{before.get('id')} → {after.get('id')}）——"
                "那等于装了第二个插件，已连的东西全留在旧的那个上。"
                "而安装页、使用说明和我给他的每一条更新指引都写着「ID 不变」")
        if after.get("version") != shipped_version:
            problems.append(
                f"**覆盖之后版本没更新**（还是 {after.get('version')}，"
                f"发布包是 {shipped_version}）——他做完那几下，什么也没变")
        kept = (after.get("stored") or {})
        if kept.get("token") != "drill-token-abc" or kept.get("endpoint") != "https://drill.example":
            problems.append(
                f"**已配对的凭据没保住**：{kept}——他更新完要从头再配一遍，"
                "而那三处都写着「凭据还在」")
    elif not problems:
        problems.append(f"没量到东西：before={before} after={after}——这不是通过")

    report = {
        "status": "PASS" if not problems else "FAIL",
        "shipped_version": shipped_version,
        "before_overwrite": before,
        "after_overwrite": after,
        "problems": problems,
        "message_zh": ("在原文件夹里覆盖再重载：ID 不变、版本更新、已配对的凭据还在。"
                       if not problems else
                       "**那三句写在安装页和使用说明里的承诺，至少有一句不成立。**"),
        "what_this_does_not_prove": (
            "不证明他在 Finder 里覆盖文件夹的体验（那是他做的事）。"
            "这里证明的是覆盖之后 Chrome 这一侧会怎样——而那正是那三句承诺的内容。"),
    }
    out = ROOT / "evidence/G3/UPDATE_IN_PLACE.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="验「覆盖再重载」那三句承诺")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
