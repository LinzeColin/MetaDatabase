"""用 CDP 把未打包扩展装进一个一次性 Chrome，并驱动它（v0.0.0.7）。

## 为什么需要它

T02 / T04 / T06 / T08 的验收都要求「扩展真的装进浏览器」。
我一度判定那只能由 Owner 手动做，理由是：
  · chrome://extensions 进不去（browser MCP 的 navigate 强制加 https 前缀）
  · --load-extension 自 Chrome 137 起停用（本机 150 实测确认：静默忽略，登记扩展数 0）

**漏了第三条路：CDP 的 Extensions.loadUnpacked。** 一条命令就装上了。
教训：测掉两条路之后就停了搜索，没有把 CDP 的能力也核一遍。

## 怎么用

    # 1. 起一个一次性 profile 的 Chrome（绝不碰 Owner 的真实 profile）
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --user-data-dir=/tmp/sa-test-profile --remote-debugging-port=9334 \
      --no-first-run --disable-sync --disable-background-networking \
      --no-service-autorun --password-store=basic --use-mock-keychain about:blank &

    # 2. 装扩展
    python3 -c "import asyncio,sys; sys.path.insert(0,'scripts'); \
      from cdp_extension_harness import load_unpacked; asyncio.run(load_unpacked())"

## 两个坑

  · **一定要 --disable-sync**：不加的话那个临时 profile 会自动登录 Owner 的账号、
    同步安装他所有扩展、并逐个弹出安装引导页。实测踩到过。
  · **MV3 的 service worker 闲置约 30 秒就休眠**，休眠后 CDP 找不到它的 target。
    wake_sw() 通过重载扩展页面制造事件把它叫醒。

## 用户手势

chrome.permissions.request 必须在用户手势中调用。**CDP 的
Input.dispatchMouseEvent 算真实手势**——所以点真按钮能过，而直接调
connectChromeBookmarks() 会被拒。也就是说这个 harness 走的是产品自己的
授权路径，不是绕过它。
"""

import asyncio, json, urllib.request, websockets
EXT_ID = "lekffndnojcjmclidamcmmanfhbbbddh"
BASE = "http://127.0.0.1:9334"

def targets():
    return json.load(urllib.request.urlopen(BASE + "/json"))

def open_tab(url):
    """新开一个标签页并**真的导航过去**。

    坑：`PUT /json/new?url=...` 只会建出一个 about:blank，不会导航——
    对 chrome-extension:// 和 https:// 都是如此。必须再用 Page.navigate。
    """
    raw = urllib.request.urlopen(
        urllib.request.Request(BASE + "/json/new", method="PUT")).read()
    tab = json.loads(raw)
    import asyncio
    import websockets

    async def _go():
        async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=None) as ws:
            c = Conn(ws)
            await c.rpc("Page.enable")
            await c.rpc("Page.navigate", {"url": url})
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_go())
        return tab
    raise RuntimeError("open_tab 需要在同步上下文调用；异步里请直接用 Page.navigate")


async def open_tab_async(url):
    """异步版：建标签页并导航，返回 target 描述。"""
    import websockets
    tab = json.loads(urllib.request.urlopen(
        urllib.request.Request(BASE + "/json/new", method="PUT")).read())
    async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=None) as ws:
        c = Conn(ws)
        await c.rpc("Page.enable")
        await c.rpc("Page.navigate", {"url": url})
    return tab

async def wake_sw(tries=6):
    """MV3 的 service worker 会闲置休眠。开一次扩展页面把它叫醒。"""
    for _ in range(tries):
        sw = [t for t in targets() if t.get("type") == "service_worker" and EXT_ID in t.get("url", "")]
        if sw:
            return sw[0]
        pages = [t for t in targets() if t.get("type") == "page" and EXT_ID in t.get("url", "")]
        if not pages:
            open_tab(f"chrome-extension://{EXT_ID}/options.html")
        await asyncio.sleep(2)
    raise RuntimeError("service worker 叫不醒")

class Conn:
    def __init__(self, ws): self.ws, self.n = ws, 0
    async def rpc(self, method, params=None):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        while True:
            r = json.loads(await self.ws.recv())
            if r.get("id") == self.n:
                return r
    async def ev(self, expr, awaitp=True):
        r = await self.rpc("Runtime.evaluate",
                           {"expression": expr, "awaitPromise": awaitp, "returnByValue": True})
        res = r.get("result", {})
        if res.get("exceptionDetails"):
            return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:200]
        return res.get("result", {}).get("value")


async def load_unpacked(ext_path: str | None = None) -> str:
    """把扩展装进正在跑的调试实例，返回扩展 ID。"""
    import pathlib
    import websockets

    ext = ext_path or str(pathlib.Path(__file__).resolve().parents[1] / "apps/browser-extension")
    ws_url = json.load(urllib.request.urlopen(BASE + "/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=None) as ws:
        c = Conn(ws)
        r = await c.rpc("Extensions.loadUnpacked", {"path": ext})
        if "error" in r:
            raise RuntimeError(r["error"])
        return r["result"]["id"]
