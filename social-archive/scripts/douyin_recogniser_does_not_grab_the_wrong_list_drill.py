#!/usr/bin/env python3
r"""真抖音页面上，形状识别器会不会认错东西（2026-08-12）。

## 为什么补这一个

说明书现在请他做的第一件事是**重连抖音、跑一遍完整同步**。那条路靠
`list-shape.js` 的形状识别器：它把页面发出的所有响应收下来，
**按形状**认出哪个是收藏列表——不需要先知道地址。

「按形状认」有一个明显的风险：**认错。** 抖音一个页面会发十几个请求，
里面不止一个数组（热搜榜、推荐流、通知列表…）。认错了的后果不是"没数据"，
而是**把热搜当成他的收藏存进档案馆**——那比什么都不做坏得多。

而在这个演练之前，抖音那一路只在**我自己编的那份响应**上验过
（`list_shape_end_to_end_drill` 的 `_douyin()`，它自己的文件头写着
「不证明真站的响应长这样」）。**编的夹具里只有一个数组，当然不会认错。**

## 它怎么验

真 Chrome 打开一个**公开的**抖音视频页（不带登录态），把 `net-observer.js`
注进 MAIN world 收下页面自己发的响应，然后把这些**真响应**喂给
`list-shape.js` 里那个真识别器。

判据是**否定式**的：没登录时页面根本不会返回收藏列表，
所以识别器**必须说"没认出来"**。它要是从热搜或推荐流里"认出"了一个列表，
那就是会把别人的内容当成他的收藏——当场打红。

实测（2026-08-12）：收下 16 条真响应（`aweme/v1/web/*` 那一族），
识别器回 `LIST_SHAPE_NOT_RECOGNISED`。**它没有乱抓。**

## 四个平台各撞一遍（2026-08-12 实测）

同一个识别器给四家都用，所以这一族缺陷不是抖音独有的：

    douyin       31 条真响应   修好后不再乱认   正对照成立
    xiaohongshu  13 条真响应   不乱认           正对照成立
    instagram    18 条真响应   不乱认           正对照成立
    reddit       **一条都没抓到** —— 无头 Chrome 打不开它的公开页

**reddit 那一行是「没量到」，不是「通过」。** 它退出 4 并明说抓不到，
不许被读成第四个平台也验过了。

**试过一条路，行不通，记在这里免得下一个人再走一遍**：无头 Chrome 的 UA 里
自报 `HeadlessChrome`，而 `curl` 拿普通 Chrome 的 UA 打 reddit 是 200——
看起来加个 `--user-agent` 就能过。实测**反而更糟**：

    带真实 UA    douyin 0 条、reddit 0 条
    不带（现状） douyin 59 / 23 / 36 条、reddit 0 条

**它没救回 reddit，还把本来好好的抖音打坏了**，所以撤了。

**然后去查了 reddit 到底给了无头 Chrome 什么**，答案是一屏人机验证：

    title    "Reddit - Prove your humanity"
    body     「We're committed to safety and security. But not for bots.
              Complete the challenge below and let us know you're a real person.」

**所以这不是「我还没试够」，是这条路只能靠过验证码，而那件事不做。**
reddit 这一行就此定性：**自动化里量不到，别再试了**。

真要给 reddit 这条路留证据，只有两种正当办法：
Owner 自己在有头浏览器里跑一次；或者等哪天有一个不设人机验证的公开页面。
在那之前它一直是「没量到」——不是缺陷，也不是通过。

## 它不证明什么

- **不证明登录之后认得出他的收藏。** 那要他的登录态，只能发生在他的浏览器里。
  这个演练证的是另一半：**认不出的时候不会瞎认**。
- 抓不到响应时（网络/风控）**明说是没量到，不算通过**。
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
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "apps" / "browser-extension" / "net-observer.js"
LIST_SHAPE = ROOT / "apps" / "browser-extension" / "content" / "list-shape.js"
# 他库里一条真实的公开抖音视频页。**不带登录态**——这正是这个演练要的状态。
# 每个平台一个**公开**页面（不带登录态）。这一族缺陷不是抖音独有的——
# 同一个识别器给小红书/Reddit/Instagram 也用，所以逐个都要撞一遍。
PAGES = {
    # RECOGNISER_REAL_PAGES：只放真走形状识别这条路的四家。
    # X 走服务端连接器、YouTube 本版不自动读——给它们列一个公开页，
    # 只会造出「这两家也验过了」的假象。
    "douyin": "https://www.douyin.com/video/7324133995774594331",
    "xiaohongshu": "https://www.xiaohongshu.com/explore",
    "reddit": "https://www.reddit.com/r/popular/",
    "instagram": "https://www.instagram.com/explore/",
}
PAGE = PAGES["douyin"]
DEBUG_PORT = 9418

COLLECTOR = """
window.__saSeen = [];
window.addEventListener("message", event => {
  const d = event.data;
  if (d && d.__socialArchive && d.type === "SA_RAW_RESPONSE")
    // **字段名必须是 text**：`recogniseList` 读的是 `capture.text`。
    // 第一版写成 body，于是每一条都被判「不是 JSON」——识别器什么也没看见，
    // 而它照样回「没认出来」。那次 PASS 是空转，正对照才戳穿。
    window.__saSeen.push({url: d.url || "", status: d.status,
                          text: String(d.body || "").slice(0, 300000)});
});
"""


async def _rpc_factory(ws):
    counter = {"n": 0}

    async def rpc(method, params=None):
        counter["n"] += 1
        await ws.send(json.dumps({"id": counter["n"], "method": method,
                                  "params": params or {}}))
        while True:
            got = json.loads(await ws.recv())
            if got.get("id") == counter["n"]:
                return got
    return rpc


async def capture(chrome: str, wait: float) -> list[dict]:
    profile = Path(tempfile.mkdtemp(prefix="sa-douyin-recog-"))
    headless = [] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         *headless, "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{DEBUG_PORT}"
    try:
        target = None
        for _ in range(40):
            await asyncio.sleep(0.5)
            try:
                targets = json.loads(urllib.request.urlopen(base + "/json", timeout=3).read())
            except Exception:                                    # noqa: BLE001
                continue
            pages = [item for item in targets if item.get("type") == "page"]
            if pages:
                target = pages[0]
                break
        if not target:
            return []
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            rpc = await _rpc_factory(ws)
            await rpc("Page.enable")
            await rpc("Runtime.enable")
            await rpc("Page.addScriptToEvaluateOnNewDocument",
                      {"source": COLLECTOR + OBSERVER.read_text(encoding="utf-8")})
            await rpc("Page.navigate", {"url": PAGE})
            await asyncio.sleep(wait)
            # catch-all 前缀：把页面发出的**全部**响应放出来，正是识别器要面对的输入。
            await rpc("Runtime.evaluate", {"expression": (
                'window.postMessage({__socialArchiveControl:true,'
                'type:"SA_OBSERVER_CONFIGURE",urlPrefixes:["http"]},'
                ' window.location.origin)'), "returnByValue": True})
            await asyncio.sleep(3)
            got = await rpc("Runtime.evaluate", {
                "expression": "JSON.stringify(window.__saSeen || [])",
                "returnByValue": True})
            payload = got.get("result", {})
            if payload.get("exceptionDetails"):
                return []
            return json.loads(payload["result"]["value"])
    finally:
        process.terminate()
        shutil.rmtree(profile, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="真抖音页面上识别器会不会认错")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--wait", type=float, default=14.0)
    parser.add_argument("--platform", default="douyin", choices=sorted(PAGES))
    args = parser.parse_args()
    global PAGE
    PAGE = PAGES[args.platform]

    captures = asyncio.run(capture(args.chrome, args.wait))
    problems: list[str] = []
    if not captures:
        # **抓不到就明说没量到。** 报「识别器没认错」而其实一条输入都没有，
        # 是这个仓最常见的那种假绿。
        # **状态要和这句话一致。**（2026-08-13）
        #
        # 原来这里 status 是 `FAIL`，而同一段话写着「这是没量到，不是通过」——
        # 一个读起来是"没通过"，一个说的是"没量到"。两者差别很大：
        # 没通过要去修产品，没量到要去换通道。reddit 每次都走这一支
        # （它给无头 Chrome 的是一屏人机验证），于是这条演练对它**永远报 FAIL**，
        # 而 DRILLS.md 里写的是「那一行永远是没量到」。**同一件事两个说法。**
        print(json.dumps({
            "status": "BLOCKED_CHANNEL", "error_code": "NOTHING_CAPTURED",
            "message_zh": ("一条真响应都没收到（网络或风控）——**这是没量到，不是通过**，"
                           "也不是产品坏了。换一条够得着的通道再跑。"),
            "what_this_does_not_prove": "既不证明识别器会乱抓，也不证明它不会。",
        }, ensure_ascii=False, indent=2))
        return 0

    node = shutil.which("node")
    if not node:
        print(json.dumps({"status": "SKIPPED", "why": "这台机器上没有 node"},
                         ensure_ascii=False))
        return 0
    script = f"""
      const api = require({json.dumps(str(LIST_SHAPE))});
      const captures = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
      const got = api.recogniseList(captures);
      // **正对照**：同一批真响应，外加一条长得像收藏列表的。
      // 识别器必须认出这一条——认不出说明我喂的输入它根本读不懂，
      // 那么上面那个「没认出来」什么也不证明。
      const planted = JSON.parse(process.argv[2]);
      const withPlanted = api.recogniseList(captures.concat([planted]));
      // **返回的是 {{ok, best:{{url,path,items,stats}}, candidates, rejected}}**。
      // 第一版读的是 got.url / got.items —— 两个都不存在，于是它「认出了什么」
      // 一直显示为空，我据此写下的判断也就没有依据。
      const best = got && got.best;
      console.log(JSON.stringify({{
        ok: !!(got && got.ok),
        reason: (got && got.failureCode) || "",
        chosen_url: best ? String(best.url).slice(0, 120) : "",
        chosen_path: best ? String(best.path) : "",
        chosen_count: best && best.items ? best.items.length : 0,
        candidates: (got && got.candidates ? got.candidates : []).slice(0, 4)
          .map(c => ({{url: String(c.url).slice(0, 90), path: String(c.path),
                      n: c.items ? c.items.length : 0}})),
        control_recognised_the_planted_list: !!(withPlanted && withPlanted.ok) }}));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as handle:
        json.dump(captures, handle, ensure_ascii=False)
        blob = handle.name
    planted = json.dumps({
        "url": "https://www.douyin.com/aweme/v1/web/aweme/listcollection/", "status": 200,
        "text": json.dumps({"status_code": 0, "has_more": 0, "aweme_list": [
            {"aweme_id": f"70{i}", "desc": f"第 {i} 条", "author": {"nickname": "某人"},
             "share_url": f"https://www.douyin.com/video/70{i}"} for i in range(7)]},
            ensure_ascii=False)}, ensure_ascii=False)
    done = subprocess.run([node, "-e", script, blob, planted],
                          capture_output=True, text=True, timeout=120)
    Path(blob).unlink(missing_ok=True)
    if done.returncode != 0:
        print(json.dumps({"status": "FAIL", "error_code": "RECOGNISER_CRASHED",
                          "detail": (done.stdout + done.stderr)[-400:]}, ensure_ascii=False))
        return 4
    verdict = json.loads(done.stdout.strip().splitlines()[-1])

    if not verdict.get("control_recognised_the_planted_list"):
        problems.append(
            "**正对照不成立**：往真响应里混进一条长得像收藏列表的，识别器也没认出来"
            "——说明它读不懂我喂的这批输入，那么「没认出来」什么都不证明（空转）")
    if verdict.get("ok"):
        problems.append(
            f"**没登录却认出了一个列表**："
            f"{verdict.get('chosen_url', '')[:90]} 的 {verdict.get('chosen_path')}，"
            f"{verdict.get('chosen_count')} 条——那不是他的收藏，"
            "认错的后果是把别人的内容当成他的存进档案馆")

    # **这一跑到底见没见到一个"内容流"。**（2026-08-13）
    #
    # 之前这里一律说「它不会从热搜或推荐流里乱抓」——**而有的平台压根没让我们
    # 看见热搜或推荐流**。小红书实测：无头 Chrome 被风控挡下，落在
    # `/website-login/error`，收到的 14 条真响应全是 `as.xiaohongshu.com/api/sec/*`
    # 和 `apm-fe.xiaohongshu.com/api/data`——**安全与埋点接口，一条内容都没有**。
    # 识别器在一张没有列表的页面上"没乱抓"，**说明不了它面对真列表时也不乱抓**。
    #
    # 正对照仍然成立（塞一个像列表的进去，它认得出来），所以这不是空转；
    # 但**那句话要收窄到证据的边界内**。
    # **数「有几个列表形状的候选」，不数「哪个主机发的」。**（2026-08-13）
    #
    # 我今天在这个数上连错两版：
    #   一版只按路径挑埋点 → 抖音报「52 条全带内容」，而其中 25 条是
    #     `mcs.zijieapi.com`、5 条是 `mon.zijieapi.com`，全是字节的埋点；
    #   二版补上主机名 → 抖音 17，而 instagram 又报「17 条全带内容」，
    #     其中 9 条是 `/ajax/bulk-route-definitions/`、3 条是 `/ajax/bz`（埋点）、
    #     1 条 bootloader，**真内容只有 3 条 `/api/graphql`**。
    # **按主机/路径拉黑名单是打地鼠**，每换一个平台就漏一批。
    #
    # 换个问法就稳了：**这一跑里，有几个"长得像列表"的负载摆在识别器面前？**
    # 埋点响应里那种 11 个对象的数组**也算**——它正是最该被拒的那种诱惑，
    # 识别器把它拒掉恰恰是这条演练要证的事。
    # 这个数只要 ≥1，「它没乱抓」这句话就有内容；等于 0 才是没量到。
    def _list_shaped(payload, depth=0) -> int:
        if depth > 6:
            return 0
        if isinstance(payload, list):
            here = 1 if len(payload) >= 3 and isinstance(payload[0], dict) else 0
            return here + sum(_list_shaped(v, depth + 1) for v in payload[:3])
        if isinstance(payload, dict):
            return sum(_list_shaped(v, depth + 1) for v in payload.values())
        return 0

    content_like = []
    for capture_item in captures:
        try:
            parsed = json.loads(capture_item.get("text") or "")
        except (ValueError, TypeError):
            continue
        if _list_shaped(parsed):
            content_like.append(capture_item)
    saw_a_feed = len(content_like) > 0
    # **面前一个候选都没有，就不是"过了"，是"没量到"。**（2026-08-13）
    #
    # 正对照仍然证明识别器活着，但这条演练要证的是「面对诱惑不乱抓」——
    # 没有诱惑就没有考题。报 PASS 会让部署日志把这一维记成验过了。
    print(json.dumps({
        "status": ("FAIL" if problems
                   else "PASS" if saw_a_feed else "BLOCKED_CHANNEL"),
        "page": PAGE,
        "real_responses_fed_to_the_recogniser": len(captures),
        # **收到几条 ≠ 有几个列表摆在它面前。** 分开数，别让「14 条真响应」
        # 读起来像「它顶住了 14 次诱惑」——那 14 条可能一个数组都没有。
        "list_shaped_payloads": len(content_like),
        "faced_a_list_shaped_candidate": saw_a_feed,
        "sample_urls": [str(c.get("url"))[:88] for c in captures[:8]],
        "verdict": verdict,
        "problems": problems,
        "message_zh": (
            "识别器认错了——见 problems。" if problems else
            ("没登录时识别器明说没认出来——**它不会从热搜或推荐流里乱抓**。"
             if saw_a_feed else
             "**这一跑里一个「长得像列表」的负载都没有**（多半被挡在了登录或风控页）。"
             "识别器面前根本没有诱惑，所以「它没乱抓」这句话是空的——"
             "结论只到「识别器还活着、正对照认得出塞进去的那个列表」为止。")),
        "what_this_does_not_prove":
            ("不证明登录之后认得出他的收藏（那要他的登录态）。这里证的是另一半："
             "认不出的时候不会瞎认。"
             if saw_a_feed else
             "**这一跑连推荐流都没见到**，所以它既不证明会乱抓、也不证明不会乱抓；"
             "只证明识别器本身没坏（正对照认出了塞进去的那个列表）。"),
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
