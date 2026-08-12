#!/usr/bin/env python3
r"""插件答得慢的时候，这一页还认不认得出它（2026-08-13）。

## 为什么需要这个

资料库那一页判「装没装插件」，靠的是 `postMessage(SA_PING)` 之后收到
`SA_PONG`。这个结论很贵：`detected: false` 会让「去连接」当场弹出

    还没有检测到 Social Archive 浏览器插件……要现在打开安装说明吗？

**把一个插件装得好好的人送去装插件。**

而原来它只凭一个 **400 毫秒**的窗口下这个结论。实测（真 Chrome、同一份
v0.0.0.69 发布包、同一次点击）：三次里有一次那一窗收不到，换 5 秒窗口
再探就答上了——插件一直在，只是那一窗没赶上。

代价是实打实的：`stale_extension_is_blocked_drill` 因此三次掐断部署，
而它报出来的那句话是「就地连接这件事没成立，他还是得跳走」——**听起来
像产品缺陷**，我照着查了四轮，四轮都查偏（两次当"读早了"、一次当
service worker 睡着、一次把诊断挂错了地方）。

## 它怎么验

不装真插件——**装一个答得慢的假插件**，慢多少由这个脚本说了算。
真插件的延迟是随机的，拿它当夹具就等于把判据建在抛硬币上。

    快答（100 毫秒）   → 必须认出来      （原来就该过，防止改坏快路）
    慢答（1500 毫秒）  → **必须认出来**  （这就是这次修的那一条）
    完全不答           → **必须认不出来**（反例：别为了让上面两条绿，
                                          把这一页改成"永远说装着了"）

第三条不是凑数：把「一窗没答就重试」写过头，最容易的错法就是让它
永远认为装着了——那样真没装的人会卡在一个永远连不上的按钮上。
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
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import websockets  # noqa: E402

import _drill_port  # noqa: E402
import list_shape_end_to_end_drill as shape  # noqa: E402
import stale_extension_is_blocked_drill as stale  # noqa: E402

PORT = stale.PORT
DEBUG_PORT = 9412

# 假插件：收到 SA_PING，等 delayMs 再照 bridge.js 的形状回一条 SA_PONG。
FAKE_BRIDGE = """(() => {
  window.__fakeBridgeDelay = %d;
  window.addEventListener("message", event => {
    const data = event.data || {};
    if (event.source !== window || data.source !== "social-archive-web"
        || data.type !== "SA_PING") return;
    setTimeout(() => {
      window.postMessage({
        source: "social-archive-extension", type: "SA_PONG",
        requestId: data.requestId, detected: true, paired: true,
        version: "0.0.0.69",
        connectFrameUrl: "chrome-extension://fakefakefakefakefakefakefakefake/connect-frame.html",
      }, location.origin);
    }, window.__fakeBridgeDelay);
  });
  return "installed";
})()"""

# 不给页面加任何测试钩子——**按他真会按的那颗按钮，读他真会看到的那句话**。
# 加个 `window.__saRefresh…` 之类的出口，验的就成了「夹具够不够得着」，
# 而不是「他点下去会怎样」。
ARM = """(() => { window.__saDialogs = [];
  window.confirm = message => { window.__saDialogs.push(String(message)); return false; };
  return "armed"; })()"""

CLICK = """(() => {
  const button = document.querySelector('[data-connect-platform="bilibili"]')
               || document.querySelector('[data-connect-platform]');
  if (!button) return JSON.stringify({ clicked: false });
  button.click();
  return JSON.stringify({ clicked: true });
})()"""

READ = """(() => JSON.stringify({ dialogs: window.__saDialogs || [] }))()"""


NOT_DETECTED = "还没有检测到"


async def _one(prpc, delay_ms: int | None) -> dict:
    """装一个延迟 delay_ms 的假插件，点「连接」，读这一页对他说的话。

    **`detected` 是从他看到的那句话反推的**，不是从内部状态读的：
    弹出「还没有检测到…」就是没认出来，没弹就是认出来了。
    """
    await prpc("Page.enable")
    await prpc("Page.reload", {"ignoreCache": True})
    # **等页面真的重载完，再装假插件——而且装完要回读。**（2026-08-13）
    #
    # 第一版是 `reload` 之后睡 3 秒就装。那是个竞态：重载没走完时，
    # `Runtime.evaluate` 落在**旧的执行上下文**里，紧接着的导航把它整个丢掉，
    # 于是假插件根本没装上，而脚本以为装上了。
    # 实测代价：反例那一轮 `fast_100ms` 报了 False——一个和被测代码
    # 毫无关系的假红。**我正在修一个抖动的演练，差点自己再交一个抖的。**
    for _ in range(40):
        ready = await prpc("Runtime.evaluate", {
            "expression": '(document.readyState === "complete") && !!document.getElementById("toastStack")',
            "returnByValue": True})
        if ready.get("result", {}).get("result", {}).get("value") is True:
            break
        await asyncio.sleep(0.5)
    for _ in range(10):
        await prpc("Runtime.evaluate", {"expression": ARM, "returnByValue": True})
        if delay_ms is not None:
            await prpc("Runtime.evaluate",
                       {"expression": FAKE_BRIDGE % delay_ms, "returnByValue": True})
        # 回读：装没装上以**页面里读得到**为准，不以「我发过那条命令」为准。
        back = await prpc("Runtime.evaluate", {
            "expression": "JSON.stringify({ armed: Array.isArray(window.__saDialogs),"
                          " delay: window.__fakeBridgeDelay ?? null })",
            "returnByValue": True})
        state = json.loads(back.get("result", {}).get("result", {}).get("value") or "{}")
        if state.get("armed") and state.get("delay") == delay_ms:
            break
        await asyncio.sleep(0.5)
    else:
        return {"detected": None, "error": "FIXTURE_NOT_INSTALLED"}
    for _ in range(20):
        probe = await prpc("Runtime.evaluate", {
            "expression": 'document.querySelectorAll("[data-connect-platform]").length',
            "returnByValue": True})
        if int(probe.get("result", {}).get("result", {}).get("value") or 0) > 0:
            break
        await asyncio.sleep(0.5)
    click = await prpc("Runtime.evaluate",
                       {"expression": CLICK, "returnByValue": True,
                        "userGesture": True, "timeout": 20000})
    clicked = json.loads(click.get("result", {}).get("result", {}).get("value") or "{}")
    if not clicked.get("clicked"):
        return {"detected": None, "error": "CONNECT_BUTTON_NOT_FOUND"}
    # 重试那条路最坏要走满 5 秒，等够它再读，不然读到的是"还没弹"。
    dialogs: list = []
    for _ in range(28):
        await asyncio.sleep(0.5)
        got = await prpc("Runtime.evaluate", {"expression": READ, "returnByValue": True})
        dialogs = (json.loads(got.get("result", {}).get("result", {}).get("value")
                              or "{}").get("dialogs") or [])
        if dialogs:
            break
    said_missing = any(NOT_DETECTED in str(d) for d in dialogs)
    return {"detected": not said_missing,
            "dialogs": [str(d)[:60] for d in dialogs]}


async def run(chrome: str) -> int:
    _drill_port.require_free(PORT, drill=Path(__file__).name)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), stale._Handler)  # noqa: SLF001
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = Path(tempfile.mkdtemp(prefix="sa-slowext-"))
    process = subprocess.Popen(
        [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={DEBUG_PORT}",
         "--no-first-run",
         # 开关只能往「看得见」那一侧拨：默认无头，要看时才设 SA_DRILL_HEADED。
         # 反过来的开关迟早会被谁设上，然后他的屏幕又开始被抢。
         *([] if os.environ.get("SA_DRILL_HEADED") else ["--headless=new"]),
         "--no-default-browser-check",
         "--disable-sync", "--disable-background-networking", "--password-store=basic",
         "--use-mock-keychain", f"http://127.0.0.1:{PORT}/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cases: dict[str, dict] = {}
    problems: list[str] = []
    try:
        for _ in range(40):
            try:
                version = json.loads(
                    urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version",
                                           timeout=2).read())
                break
            except Exception:                                     # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            print(json.dumps({"status": "FAIL", "error_code": "CHROME_NOT_UP"},
                             ensure_ascii=False))
            return 2
        await asyncio.sleep(4)
        targets = json.loads(
            urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5).read())
        pages = [t for t in targets if t["type"] == "page" and f"127.0.0.1:{PORT}" in t["url"]]
        if not pages:
            print(json.dumps({"status": "FAIL", "error_code": "PAGE_NOT_OPEN"},
                             ensure_ascii=False))
            return 2

        async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None) as page:
            prpc = await shape._rpc_factory(page)                 # noqa: SLF001
            await prpc("Runtime.enable")
            cases["fast_100ms"] = await _one(prpc, 100)
            cases["slow_1500ms"] = await _one(prpc, 1500)
            cases["absent"] = await _one(prpc, None)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    if cases["fast_100ms"].get("detected") is not True:
        problems.append("答得快的插件都没认出来——这一页的探测整个是坏的，"
                        "后面两条的结论都不用看了")
    if cases["slow_1500ms"].get("detected") is not True:
        problems.append("**答得慢就当没装**：1500 毫秒才回的插件被判成没装，"
                        "他会被送去装一个已经装着的插件（这正是本次要修的那条）")
    if cases["absent"].get("detected") is not False:
        problems.append("**真没装也说装着了**：没有任何应答时仍报 detected——"
                        "重试写过头了，没装的人会卡在一个永远连不上的按钮上")

    payload = {
        "status": "PASS" if not problems else "FAIL",
        "cases": cases,
        "problems": problems,
        "message_zh": ("答得快、答得慢都认得出，完全不答时如实说没装。"
                       if not problems else "这一页对「装没装插件」的判断有问题。"),
        "what_this_does_not_prove": (
            "用的是假插件，只验这一页**等得够不够久**这一件事；"
            "不证明真插件在他机器上一定答得上，那是 stale_extension 那个演练的事。"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="插件答得慢时这一页还认不认得出")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    return asyncio.run(run(args.chrome))


if __name__ == "__main__":
    sys.exit(main())
