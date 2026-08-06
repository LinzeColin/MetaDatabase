#!/usr/bin/env python3
"""在真 Chrome 里把「拦截 → 读懂」整条链走一遍（v0.0.0.7 / T08）。

## 为什么非做不可

Owner 只需要动一次手：装好插件，打开收藏夹页，点一下诊断。
那一下背后是这么一条链——

    刷新页面 → 注入中继(ISOLATED) → 注入观察器(MAIN) → 下发前缀
      → 页面自己发请求 → 观察器抄走响应 → 中继转回 background
      → 缓冲区 → 服务端解析成条目

**这条链一次都没有整条跑过。** 每一环单独验过：解析器有判据，
服务端接口打得通，插件装得上、三个全局都在。但「每一环都对」
和「串起来能出条目」是两件事——这个项目今天已经在这个差别上栽过两次
（藏了按钮而队列照抢标签页；静态判据说守卫在导航之前而实测抢了 2 下）。

如果链是断的，Owner 点完那一下什么也拿不到，**而他那一下已经用掉了**。

## 为什么不去真站点

去不了，也不该去。所以在**回环地址**上重建同一条链：
本地起一个假收藏夹页 + 假接口，返回真实形状的响应体，
拿**生产同一个解析器**去读抓回来的字节。

用 127.0.0.1:8765 是因为插件在装的时候就拿到了这个域的权限
（manifest 的 host_permissions 里写着），不需要任何人点授权框。

## 它证明什么、不证明什么

证明：注入进得去、两个世界的消息通得了、**相对地址抓得到**、
      抓回来的字节**生产解析器读得懂并能数出条目**。
不证明：B 站真实响应就是这个形状（形状取自 2026-08-04 那次真实抓包的记录），
      也不证明 Owner 机器上的权限/策略与这里相同。

## 边界

· 全程不联网、不碰生产、不碰 Owner 的 profile（一次性 profile，跑完删）。
· 反例先行：换一个绝对匹配不上的前缀，必须抓到 0 条。
  抓不到 0 条说明这个演练**根本不是在量它自称在量的东西**。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_archive.platform_payloads import parse_bilibili_favlist  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from drill_extension_dir import resolve_ext_dir  # noqa: E402

HERE = Path(__file__).resolve().parent
PORT = 8765
FAV_PATH = "/x/v3/fav/resource/list"

# 形状取自 2026-08-04 那次真实抓包记录：code/message/ttl/data.medias，
# 条目上带 id/title/bvid/type/intro/cover/upper。**不要凭印象改这个形状**——
# 它是解析器判据的同一份底。
FAKE_FAVLIST = {
    "code": 0,
    "message": "0",
    "ttl": 1,
    "data": {
        "info": {"id": 1, "title": "演练用收藏夹", "media_count": 2},
        "medias": [
            {"id": 111, "bvid": "BV1drill001", "type": 2, "title": "回环演练条目一",
             "intro": "这条只存在于本机", "cover": "http://127.0.0.1/1.jpg",
             "upper": {"name": "演练"}, "pubtime": 1700000000},
            {"id": 222, "bvid": "BV1drill002", "type": 2, "title": "回环演练条目二",
             "intro": "", "cover": "http://127.0.0.1/2.jpg",
             "upper": {"name": "演练"}, "pubtime": 1700000001},
        ],
        "has_more": False,
    },
}

# **这个页面在加载时各发一次，然后就不发了。**
#
# 第一版写的是 setInterval 每 700ms 发一次——那样演练一定会 PASS，
# 因为观察器无论多晚装上都还能等到下一轮。**真实收藏夹页不是这样的**：
# 收藏列表那个请求是页面加载时打的，打完就没有了。
# 一个比现实宽容的假页面，测出来的绿是假绿。
#
# 两种写法各一次：
#   相对地址  —— 平台调自己接口的常规写法，也是 absolute() 那个补丁要保的路
#   绝对地址  —— 补丁之前唯一能匹配上的写法，用来对照
PAGE = f"""<!doctype html><meta charset="utf-8"><title>回环演练收藏夹</title>
<body><p>这个页面在加载时发一次请求，之后不再发——和真实收藏夹页一样。</p><script>
fetch("{FAV_PATH}?rel=1&pn=1").then(r => r.json()).catch(() => {{}});
fetch("http://127.0.0.1:{PORT}{FAV_PATH}?abs=1&pn=1").then(r => r.json()).catch(() => {{}});
</script></body>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith(FAV_PATH):
            body = json.dumps(FAKE_FAVLIST, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            body = PAGE.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:      # 别把演练日志刷满终端
        return


# **调的是诊断按钮背后那个函数本人**，不是照抄一遍它的顺序。
# 抄件和正本一分叉，演练就会在正本坏掉的时候继续绿。
#
# 平台传 generic-web 而不是 bilibili，**不是为了绕开授权，是因为绕不开**：
# requestPlatformPermission 会弹一个原生授权框，CDP 点不到它。
# 第一版想直接把 SA.requestPlatformPermission 换掉——SA 是 Object.freeze 的，
# 赋值是个静默空操作，演练当场如实报回「没有获得读取 B 站页面的授权」。
#
# 换成 generic-web 之后走的是**同一条链**：它没有权限模式，
# requestPlatformPermission 的 `if (!origins.length) return true` 直接放行；
# 而前缀本来就是从**标签页自己的域名**推的，与平台无关。
# 没被这个演练覆盖的只剩「向用户要平台授权」那一步——那一步本来也自动化不了。
#
# 只在反例里替换 chrome.tabs.get，用来把推出来的前缀弄成一个匹配不上的，替换完立刻还原。
PROBE = r"""
(async (config) => {
  const tabs = await chrome.tabs.query({ url: config.pageUrl + "*" });
  if (!tabs.length) return JSON.stringify({ error: "没有找到演练页面的标签页" });
  const tabId = tabs[0].id;

  const realGet = chrome.tabs.get;
  if (config.bogusHost) {
    chrome.tabs.get = async (id) => {
      const tab = await realGet.call(chrome.tabs, id);
      return { ...tab, url: config.bogusHost };
    };
  }

  // **这里故意不清缓冲区。** 清是产品自己该做的事——
  // 探针替它清，就等于把「连按两次诊断会不会串味」这个问题藏起来。
  let installed = null, installError = null;
  try {
    installed = await installNetObserverForTab({
      platform: "generic-web", tabId, diagnostic: true,
    });
  } catch (e) { installError = e && e.message; }

  await new Promise(r => setTimeout(r, 2000));
  const captures = netCaptureBuffer.map(c => ({ url: c.url, status: c.status, body: c.body }));
  const selfReport = observerStateByTab.get(tabId) || null;
  chrome.tabs.get = realGet;
  return JSON.stringify({ captures, selfReport, tabId, installed, installError });
})(%s)
"""


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


async def _evaluate(base: str, extension_id: str, expression: str):
    targets = json.loads(urllib.request.urlopen(base + "/json", timeout=5).read())
    workers = [t for t in targets if t["type"] == "service_worker" and extension_id in t["url"]]
    if not workers:
        return {"error": "service worker 没起来"}
    async with websockets.connect(workers[0]["webSocketDebuggerUrl"], max_size=None) as ws:
        rpc = await _rpc_factory(ws)
        await rpc("Runtime.enable")
        result = await rpc("Runtime.evaluate",
                           {"expression": expression, "awaitPromise": True, "returnByValue": True})
        payload = result.get("result", {})
        if payload.get("exceptionDetails"):
            return {"error": str(payload["exceptionDetails"])[:400]}
        return json.loads(payload["result"]["value"])


async def run(chrome_binary: str, ext_dir: str, keep_going: bool) -> int:
    page_url = f"http://127.0.0.1:{PORT}/favlist"
    server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = Path(tempfile.mkdtemp(prefix="sa-capture-profile-"))
    process = subprocess.Popen(
        [chrome_binary, f"--user-data-dir={profile}", "--remote-debugging-port=9344",
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--disable-background-networking", "--no-service-autorun",
         "--password-store=basic", "--use-mock-keychain", page_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = "http://127.0.0.1:9344"
    try:
        for _ in range(40):
            try:
                version = json.loads(urllib.request.urlopen(base + "/json/version", timeout=2).read())
                break
            except Exception:                       # noqa: BLE001 —— 等它起来，不关心具体是哪种连不上
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

        def probe(bogus_host=None):
            return PROBE % json.dumps({"pageUrl": page_url, "bogusHost": bogus_host})

        real = await _evaluate(base, extension_id, probe())
        # **连按两次。** 第二次抓到的条数必须和第一次一样，不能翻倍——
        # 缓冲区若不清，第二次会把第一次的响应一起数进去。
        again = await _evaluate(base, extension_id, probe())
        # **反例**：让它以为这个标签页在别的域名上，于是推出来的前缀绝对匹配不上。
        # 反例还抓到东西 = 这个演练量的不是它自称在量的东西。
        counter = await _evaluate(base, extension_id, probe("http://这个域名不存在.invalid/x"))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    problems: list[str] = []
    for name, measured in (("正例", real), ("反例", counter)):
        if measured.get("error"):
            problems.append(f"{name}探针出错：{measured['error']}")
    if problems:
        print(json.dumps({"status": "FAIL", "problems": problems}, ensure_ascii=False))
        return 4

    captures = real.get("captures") or []
    report = real.get("selfReport") or {}
    if not report.get("installed") or not report.get("ready"):
        problems.append(f"观察器自报没装好或没就绪：{report}")
    if report.get("prefixCount") != 1:
        problems.append(f"下发的前缀条数没到观察器手里：{report}")
    if real.get("installError"):
        problems.append(f"安装那一步抛了：{real['installError']}")
    elif not (real.get("installed") or {}).get("ok"):
        problems.append(f"安装那一步自己就说没成：{real.get('installed')}")
    if not captures:
        problems.append("整条链一条都没抓到——这正是 Owner 会遇到的那种「点完什么也没有」")

    relative = [c for c in captures if "rel=1" in c["url"]]
    absolute = [c for c in captures if "abs=1" in c["url"]]
    if not relative:
        problems.append("**相对地址一条都没抓到**——absolute() 那个补丁没生效，"
                        "而相对地址正是平台调自己接口的常规写法")
    if not absolute:
        problems.append("绝对地址一条都没抓到")

    # 「拦到了」和「读得懂」是两件事：拿生产同一个解析器去读抓回来的字节。
    parsed_items = 0
    parse_error = None
    if captures:
        try:
            # 解析器返回的是 `(条目, 还有下一页)` 两元组。
            # **这里差点写成 len(整个返回值)** —— 那永远等于 2，
            # 而 2 正是这次期望的条目数：条目为空也会绿。必须先解包。
            items, _has_more = parse_bilibili_favlist(captures[0]["body"])
            parsed_items = len(items)
        except Exception as exc:                    # noqa: BLE001 —— 什么原因读不懂都要如实报出来
            parse_error = f"{type(exc).__name__}: {exc}"
    if parse_error:
        problems.append(f"抓到了却读不懂：{parse_error}")
    elif captures and parsed_items != 2:
        problems.append(f"读出来的条目数不对：{parsed_items}，应为 2")

    first_count = len(captures)
    second_count = len(again.get("captures") or [])
    if again.get("error"):
        problems.append(f"第二次诊断出错：{again['error']}")
    elif second_count != first_count:
        problems.append(
            f"连按两次诊断，第一次抓到 {first_count} 条、第二次 {second_count} 条——"
            "缓冲区没清干净，上一次的响应被算进了这一次"
        )
    if counter.get("captures"):
        problems.append(
            f"反例也抓到了 {len(counter['captures'])} 条——"
            "这个演练根本不是在量前缀匹配，它测不出真问题"
        )

    # ---- 最后一段：把这次真抓到的地址，走一遍 T09 的固化 ----
    #
    # freeze_intercept_prefix.py 到今天为止只被验过「拒绝」那几条路——
    # 成功那条一次都没跑过。**而它成功那条正是 Owner 按完诊断之后要走的路。**
    # 这里补上：拿**这次真浏览器抓到、且生产解析器读得懂**的那个地址，
    # 造一份和弹窗上报格式一致的报告，跑一次固化，写进一份**临时**目录副本。
    freeze: dict[str, Any] = {"ran": False}
    if parsed_items and captures:
        with tempfile.TemporaryDirectory(prefix="sa-freeze-") as work:
            # **别叫 report。** 上面已经有一个 report 是观察器的自报状态，
            # 重名会把它顶掉——第一版就是这么把 PosixPath 塞进了最终输出。
            report_path = Path(work) / "extension-diagnostics.jsonl"
            report_path.write_text(json.dumps({
                "at": "drill", "platform": "bilibili",
                "page_url": page_url,
                "urls": [c["url"] for c in captures],
                "readable_urls": [captures[0]["url"]],
                "capture_count": len(captures), "readable_count": 1,
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            catalog = Path(work) / "platform-catalog.js"
            catalog.write_text(
                "const INTERCEPT_PREFIXES = Object.freeze({\n"
                "    bilibili: Object.freeze([\"unset\"]),\n"
                "    xiaohongshu: null,\n"
                "  });\n", encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(HERE / "freeze_intercept_prefix.py"),
                 "--platform", "bilibili", "--report", str(report_path),
                 "--apply", "--catalog", str(catalog)],
                capture_output=True, text=True, check=False)
            written = catalog.read_text(encoding="utf-8")
            freeze = {
                "ran": True, "exit_code": run.returncode,
                "stdout": run.stdout.strip()[-260:],
                "catalog_now_says": next(
                    (l.strip() for l in written.splitlines() if "bilibili:" in l), ""),
            }
        if run.returncode != 0:
            problems.append(f"固化那一步失败：{run.stdout.strip()[-160:]}")
        elif FAV_PATH not in freeze["catalog_now_says"]:
            problems.append(f"固化写进去的不是这次抓到的那个地址：{freeze['catalog_now_says']}")

    print(json.dumps({
        "status": "PASS" if not problems else "FAIL",
        "extension_id": extension_id,
        "observer_self_report": report,
        "captured": len(captures),
        "captured_relative_url": len(relative),
        "captured_absolute_url": len(absolute),
        "parsed_items_from_first_capture": parsed_items,
        "captured_on_a_second_press": second_count,
        "counter_example_captured": len(counter.get("captures") or []),
        "froze_the_prefix_from_what_was_captured": freeze,
        "problems": problems,
    }, ensure_ascii=False))
    return 0 if not problems or keep_going else 4


def main() -> int:
    parser = argparse.ArgumentParser(description="在真 Chrome 里走一遍拦截→读懂整条链")
    parser.add_argument("--ext-dir", default=None,
                        help="解压好的扩展目录；不给就用 dist 里的发布包")
    parser.add_argument("--chrome",
                        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    parser.add_argument("--report-only", action="store_true",
                        help="照常输出但不用退出码判失败（排查时用）")
    args = parser.parse_args()
    # 没给 --ext-dir 就用发布包：要先打包再解压才跑得动的演练，
    # 就是没人跑的演练；默认用发布包还顺带让它验的是他真正下载的那一份。
    args.ext_dir = resolve_ext_dir(args.ext_dir)
    if not Path(args.ext_dir).is_dir():
        print(json.dumps({"status": "FAIL", "error_code": "EXT_DIR_MISSING",
                          "detail": args.ext_dir}, ensure_ascii=False))
        return 2
    if not Path(args.chrome).exists():
        print(json.dumps({"status": "FAIL", "error_code": "CHROME_MISSING",
                          "detail": args.chrome}, ensure_ascii=False))
        return 2
    return asyncio.run(run(args.chrome, str(Path(args.ext_dir).resolve()), args.report_only))


if __name__ == "__main__":
    sys.exit(main())
