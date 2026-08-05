#!/usr/bin/env python3
"""在真 Chrome 里问一遍：这个平台**四张表**都接上了吗（v0.0.0.7 / T06）。

## 为什么不靠对表

2026-08-05 给 youtube 接入口时，我两次宣布「封住了」，两次都错：

  · 先说「开 B 站时顺手连一下」——**硬边界禁止**（国内平台的 Cookie 不出浏览器）
  · 再说「两个方向都封住了」——**漏了第三张表**（content/platform-catalog.js），
    于是 platformLabel("youtube") 原样返回内部 id

**两次都是宣布完成之后才发现的。** 一个平台散在四张表里
（shared.js 的 PLATFORM_RULES、platform-catalog.js 的 PLATFORMS、
cookie-export.js 的 ALLOWED/FORBIDDEN、以及服务端那几张），
靠人去对，总会漏掉一张。

所以这个演练不对表：**把下发的那个 ZIP 装进真 Chrome，在 service worker 里
一次问完**。四张表在真运行时里说的话必须一致。

## 用法

    python3 scripts/extension_platform_wiring_drill.py --ext-dir <解压好的扩展目录> \\
        --platform youtube --sample-url https://www.youtube.com/playlist?list=WL

    # 期望这个平台**不能**托管 Cookie（国内四平台）时：
    ... --platform bilibili --sample-url https://space.bilibili.com/1/favlist --expect-custody forbidden

## 边界

· 一次性 profile，跑完删；不碰 Owner 的 profile、不联网、不碰生产。
· 只读：问的全是已加载模块的常量与纯函数，不触发任何连接或同步。
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
from pathlib import Path

import websockets

PROBE = r"""
(config => {
  const out = {};
  const rule = SA.platformFromUrl(config.sampleUrl);
  out.detected = rule && rule.id;
  out.permissionPatterns = SA.patternsForPlatform(config.platform) || [];
  out.label = globalThis.SAPlatformCatalog?.platformLabel?.(config.platform);
  out.relations = globalThis.SAPlatformCatalog?.platformCatalogEntry?.(config.platform)?.relations || [];
  out.relationUrls = out.relations.map(r =>
    globalThis.SAPlatformCatalog?.relationUrl?.(config.platform, r));
  out.custodyAllowed = !!globalThis.SACookieExport?.ALLOWED_PLATFORMS?.[config.platform];
  out.custodyForbidden = !!globalThis.SACookieExport?.FORBIDDEN_PLATFORMS?.has?.(config.platform);
  // 误伤检查：一个**不该**被认成这个平台的地址
  out.decoyDetected = (SA.platformFromUrl(config.decoyUrl) || {}).id;
  return JSON.stringify(out);
})(%s)
"""


def judge(measured: dict, platform: str, decoy_url: str, expect_custody: str) -> list[str]:
    """**只判定，不碰浏览器。**

    搬出来是因为守它的判据原本全是 grep 源码。其中一条断言
    「国内平台的 Cookie 必须永不出浏览器」这句话在不在文件里——
    而我刚给这段加的注释里**也有这句话**，于是即便把整个分支删掉，
    那条判据照样是绿的。这就是今天已经栽过好几次的「判据钉在注释上」。

    判定单独成函数之后，判据可以直接喂它一个假的 measured 看它红不红——
    那是反例，不是 grep。
    """
    problems = []
    if measured["detected"] != platform:
        problems.append(f"那个地址没有被认成 {platform}，而是 {measured['detected']}")
    if not measured["permissionPatterns"]:
        problems.append("没有权限模式——连不上，也读不了那个站点")
    # **中文名退回内部 id，正是第三张表缺席的症状。**
    if not measured["label"] or measured["label"] == platform:
        problems.append(f"中文名退回了内部 id（{measured['label']!r}）——"
                        "platform-catalog 里多半没有它，用户会看到这个词")
    if not measured["relations"]:
        problems.append("目录里没有声明任何关系类型")
    if any(not str(u or "").startswith("https://") for u in measured["relationUrls"]):
        problems.append(f"有关系类型没有对应的 https 地址：{measured['relationUrls']}")
    # **托管有三种状态，不是两种。**
    #
    # 第一版只有 yes/no，于是 reddit 被判 FAIL，理由还是
    # 「国内平台的 Cookie 必须永不出浏览器」——**而 reddit 根本不是国内平台**。
    # 那是我自己的演练在指错原因，和今天早上在 T13 里修的是同一种病。
    #
    #   yes        白名单里有、禁止名单里没有        —— x / instagram / youtube
    #   forbidden  禁止名单里有、白名单里没有        —— 国内四平台，硬边界
    #   not-yet    两张表都没有                      —— 支持这个平台，但托管还没做
    if expect_custody == "yes":
        if not measured["custodyAllowed"]:
            problems.append("Cookie 导出白名单里没有它——连接会走不通")
        if measured["custodyForbidden"]:
            problems.append("它同时出现在禁止名单里，两张表自相矛盾")
    elif expect_custody == "forbidden":
        if measured["custodyAllowed"]:
            problems.append("**它不该能托管 Cookie，而白名单里有它**")
        if not measured["custodyForbidden"]:
            problems.append("它不在禁止名单里——国内平台的 Cookie 必须永不出浏览器，"
                            "这条硬边界要靠那张表兜住")
    else:   # not-yet
        if measured["custodyAllowed"]:
            problems.append("说好托管还没做，白名单里却有它")
        if measured["custodyForbidden"]:
            problems.append("它被放进了禁止名单——那张表是给「Cookie 永不出浏览器」的"
                            "国内平台留的，别用它表达「还没做」")
    if measured["decoyDetected"] == platform:
        problems.append(f"误伤：{decoy_url} 也被认成了 {platform}")
    return problems


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


async def run(chrome: str, ext_dir: str, platform: str, sample_url: str,
              decoy_url: str, expect_custody: str) -> int:
    profile = Path(tempfile.mkdtemp(prefix="sa-wiring-profile-"))
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", "--remote-debugging-port=9348",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:9348"
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001 —— 等它起来
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"}, ensure_ascii=False))
            return 4

        async with websockets.connect(version["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            loaded = await rpc("Extensions.loadUnpacked", {"path": ext_dir})
            if "error" in loaded:
                print(json.dumps({"status": "FAIL", "error_code": "LOAD_UNPACKED_FAILED",
                                  "detail": loaded["error"]}, ensure_ascii=False))
                return 4
            extension_id = loaded["result"]["id"]
        await asyncio.sleep(3)

        targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
        workers = [t for t in targets if t["type"] == "service_worker" and extension_id in t["url"]]
        if not workers:
            print(json.dumps({"status": "FAIL", "error_code": "SERVICE_WORKER_ASLEEP"},
                             ensure_ascii=False))
            return 4
        async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Runtime.enable")
            expression = PROBE % json.dumps(
                {"platform": platform, "sampleUrl": sample_url, "decoyUrl": decoy_url})
            result = await rpc("Runtime.evaluate", {"expression": expression, "returnByValue": True})
            payload = result.get("result", {})
            if payload.get("exceptionDetails"):
                print(json.dumps({"status": "FAIL", "error_code": "PROBE_THREW",
                                  "detail": str(payload["exceptionDetails"])[:300]},
                                 ensure_ascii=False))
                return 4
            measured = json.loads(payload["result"]["value"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)

    problems = judge(measured, platform, decoy_url, expect_custody)

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "platform": platform,
        "measured": measured,
        "problems": problems,
    }, ensure_ascii=False))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="在真 Chrome 里问一遍这个平台四张表都接上了吗")
    parser.add_argument("--ext-dir", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--sample-url", required=True, help="这个平台的一个真实页面地址")
    parser.add_argument("--decoy-url", default="https://mail.google.com/mail/u/0/",
                        help="一个**不该**被认成这个平台的地址")
    parser.add_argument("--expect-custody", choices=("yes", "forbidden", "not-yet"),
                        default="yes",
                        help="yes=白名单里有；forbidden=国内平台硬边界；not-yet=两张表都没有")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING"}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, str(Path(args.ext_dir).resolve()), args.platform,
                           args.sample_url, args.decoy_url, args.expect_custody))


if __name__ == "__main__":
    sys.exit(main())
