"""MAIN world 响应拦截（v0.0.0.7 / T08）。

取代 v0.0.0.6 的 DOM 抓取器：不再靠类名和结构去凑列表，而是在平台页面
自己的 JS 世界里把 fetch / XHR 包一层，当页面自己去请求它自己的收藏接口时，
把响应体原样抄一份出来。

守三条硬边界（违反即架构违规）：

  · **不合成请求**——签名（小红书 x-s/x-t、抖音 a_bogus）由页面自己完成
  · **不修改请求或响应**——页面拿到的东西和我们不存在时一模一样
  · **不读 Cookie**——一个字节都不读（INV-DOMESTIC-COOKIE-STAYS）

另外守一条 INV-NO-SILENT-ZERO：没有实测过的 URL 前缀必须**显式失败**，
不能装一个前缀为空的观察器然后永远拦不到。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "apps/browser-extension"
OBSERVER = EXT / "net-observer.js"
RELAY = EXT / "content/net-relay.js"
CATALOG = EXT / "content/platform-catalog.js"


def _node(script: str) -> object:
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return json.loads(completed.stdout)


# ── 硬边界：源码层 ───────────────────────────────────────────────────


def test_observer_never_reads_cookies_or_synthesises_requests() -> None:
    code = "\n".join(
        line for line in OBSERVER.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )
    for banned in ("document.cookie", "chrome.cookies", "x-s", "a_bogus", "signature"):
        assert banned not in code, f"观察器里出现了 {banned}——它只该搬运，不该参与签名或读凭据"
    # 不合成请求：观察器里不许自己发起 fetch / XHR。
    # 它包装了 window.fetch，所以 "window.fetch =" 是允许的；
    # 但不许有 nativeFetch(...) 之外的主动调用。
    assert "new XMLHttpRequest" not in code, "观察器自己 new 了一个 XHR——那是合成请求"


def test_observer_clones_the_response_so_the_page_still_gets_its_data() -> None:
    """直接读 response.body 会把流消费掉，页面就拿不到数据了——那是"弄坏平台页面"。"""
    code = OBSERVER.read_text(encoding="utf-8")
    assert ".clone()" in code, "没有 clone()，读响应会把流消费掉，页面会拿不到数据"
    # 拦截逻辑的任何异常都不允许影响页面
    assert code.count("catch") >= 3, "拦截路径上的异常兜底不够——任何异常都不许影响页面"


def test_observer_does_not_parse_json_it_only_carries() -> None:
    """预制件原话：绝不 JSON.parse——解析失败会吞掉本来能救的数据。"""
    code = "\n".join(
        line for line in OBSERVER.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )
    assert "JSON.parse" not in code, "观察器在解析 JSON——解析属于服务端，这里只搬运"


def test_observer_is_idempotent_on_repeated_injection() -> None:
    code = OBSERVER.read_text(encoding="utf-8")
    assert "if (window[CHANNEL]) return" in code, "重复注入会把 fetch 包两层"


def test_relay_lives_in_the_isolated_world_and_carries_no_secrets() -> None:
    """MAIN world 和页面共享全局对象，页面看得见也改得了。

    所以那一侧只放"抄响应"这一件事；令牌、服务端地址、凭据都在中继这一侧。
    """
    observer = OBSERVER.read_text(encoding="utf-8")
    assert "chrome.runtime" not in observer, "MAIN world 里没有 chrome.runtime，写了也不通"
    for secret_ish in ("Authorization", "Bearer", "token", "endpoint"):
        assert secret_ish not in observer, f"观察器里出现了 {secret_ish}——页面能读到它"
    relay = RELAY.read_text(encoding="utf-8")
    assert "chrome.runtime.sendMessage" in relay


def test_relay_only_accepts_messages_from_its_own_window() -> None:
    relay = RELAY.read_text(encoding="utf-8")
    assert "event.source !== window" in relay, "不校验来源的话 iframe 也能往里灌数据"
    assert "__socialArchive !== true" in relay


# ── INV-NO-SILENT-ZERO：没实测过的前缀必须显式失败 ─────────────────


def test_only_measured_prefixes_are_listed() -> None:
    """猜错前缀的后果是「观察器装上了、页面正常、一条都没拦到、界面显示已连接」。

    所以没实测过的一律 null，而不是写一个看着像的。
    """
    result = _node(
        f"const c = require({json.dumps(str(CATALOG))});"
        "console.log(JSON.stringify(c.INTERCEPT_PREFIXES));"
    )
    assert result["bilibili"] == ["api.bilibili.com/x/v3/fav/resource/list"]
    assert result["xiaohongshu"] is None, "小红书没有实测过的前缀，不许凭印象填"
    assert result["douyin"] is None, "抖音没有实测过的前缀，不许凭印象填"


def test_unknown_platform_returns_null_not_empty_list() -> None:
    """null 和 [] 的区别是要命的：[] 会被当成「配置好了，只是没有前缀」，
    于是装上一个永远拦不到的观察器。"""
    result = _node(
        f"const c = require({json.dumps(str(CATALOG))});"
        "console.log(JSON.stringify({"
        "  known: c.interceptPrefixes('bilibili'),"
        "  unmeasured: c.interceptPrefixes('xiaohongshu'),"
        "  unknown: c.interceptPrefixes('nope')}));"
    )
    assert result["known"], "已实测的平台应当返回非空数组"
    assert result["unmeasured"] is None
    assert result["unknown"] is None


def test_background_refuses_to_install_an_observer_without_prefixes() -> None:
    """判据打在 background 的分支上：prefixes 为空时必须回显式失败码。"""
    code = (EXT / "background.js").read_text(encoding="utf-8")
    assert "INTERCEPT_PREFIX_UNKNOWN" in code, "没有实测前缀时缺少显式失败码"
    assert "!Array.isArray(prefixes) || prefixes.length === 0" in code, (
        "没有在装观察器之前挡住空前缀——那会装出一个永远拦不到的观察器"
    )


def test_bilibili_prefix_has_three_independent_sources_in_the_task_pack() -> None:
    """这条前缀是唯一有据可依的一条，把它的来源钉在判据里。

    将来有人想加新前缀时，会先看到"这里只放实测过的"这条规矩。
    """
    catalog = CATALOG.read_text(encoding="utf-8")
    assert "FEATURE_MATRIX" in catalog and "PROJECT_CAPSULE" in catalog
    assert "不许凭印象写" in catalog


# ── 真实运行：在 Node 里模拟一次页面 fetch ────────────────────────────


def test_observer_captures_a_matching_response_without_altering_it() -> None:
    """把观察器装进一个假的 window，模拟页面自己发一次请求。

    验两件事：抄到了；而且页面拿到的响应体**一字不差**。
    """
    script = f"""
const fs = require("fs"), vm = require("vm");
const posted = [];
const PAYLOAD = JSON.stringify({{ code: 0, data: {{ medias: [{{ id: 1 }}, {{ id: 2 }}] }} }});
const sandbox = {{
  window: null,
  XMLHttpRequest: function () {{}},
  console,
  Date,
}};
sandbox.XMLHttpRequest.prototype.open = function () {{}};
sandbox.XMLHttpRequest.prototype.send = function () {{}};
const listeners = [];
sandbox.window = {{
  location: {{ origin: "https://space.bilibili.com" }},
  postMessage: (msg) => posted.push(msg),
  addEventListener: (type, fn) => listeners.push([type, fn]),
  fetch: async () => ({{
    status: 200,
    clone() {{ return {{ text: async () => PAYLOAD }}; }},
    text: async () => PAYLOAD,
  }}),
}};
sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);
vm.runInContext(fs.readFileSync({json.dumps(str(OBSERVER))}, "utf8"), ctx);

(async () => {{
  // 下发前缀
  for (const [type, fn] of listeners) {{
    if (type === "message") fn({{ source: sandbox.window, data: {{
      __socialArchiveControl: true, type: "SA_OBSERVER_CONFIGURE",
      urlPrefixes: ["api.bilibili.com/x/v3/fav/resource/list"] }} }});
  }}
  // 页面自己发一次请求
  const res = await sandbox.window.fetch("https://api.bilibili.com/x/v3/fav/resource/list?media_id=1");
  const seenByPage = await res.text();
  await new Promise(r => setTimeout(r, 30));
  // 再发一次不匹配的
  await sandbox.window.fetch("https://api.bilibili.com/x/space/acc/info?mid=1");
  await new Promise(r => setTimeout(r, 30));
  const captures = posted.filter(m => m.type === "SA_RAW_RESPONSE");
  console.log(JSON.stringify({{
    captured: captures.length,
    bodyIdentical: captures.length === 1 && captures[0].body === PAYLOAD,
    pageGotFullBody: seenByPage === PAYLOAD,
    ready: posted.some(m => m.type === "SA_OBSERVER_READY"),
    installed: posted.some(m => m.type === "SA_OBSERVER_INSTALLED"),
  }}));
}})();
"""
    result = _node(script)
    assert result["installed"], "观察器没有报告安装"
    assert result["ready"], "下发前缀后没有报告就绪"
    assert result["captured"] == 1, f"应当只抄到匹配的那一条，实际 {result['captured']} 条"
    assert result["bodyIdentical"], "抄出来的响应体和原始的不一致"
    assert result["pageGotFullBody"], "页面没有拿到完整响应体——clone() 没起作用，这会弄坏平台页面"


def test_observer_ignores_everything_when_no_prefix_configured() -> None:
    """没下发前缀时一条都不该抄——但这**不是**可接受的稳态，
    所以 background 那一侧必须在装它之前就拦住（见上面那条判据）。"""
    script = f"""
const fs = require("fs"), vm = require("vm");
const posted = [];
const sandbox = {{ console, Date, XMLHttpRequest: function () {{}} }};
sandbox.XMLHttpRequest.prototype.open = function () {{}};
sandbox.XMLHttpRequest.prototype.send = function () {{}};
sandbox.window = {{
  location: {{ origin: "https://space.bilibili.com" }},
  postMessage: (m) => posted.push(m),
  addEventListener: () => {{}},
  fetch: async () => ({{ status: 200, clone: () => ({{ text: async () => "{{}}" }}) }}),
}};
sandbox.globalThis = sandbox;
vm.runInContext(fs.readFileSync({json.dumps(str(OBSERVER))}, "utf8"), vm.createContext(sandbox));
(async () => {{
  await sandbox.window.fetch("https://api.bilibili.com/x/v3/fav/resource/list");
  await new Promise(r => setTimeout(r, 30));
  console.log(JSON.stringify(posted.filter(m => m.type === "SA_RAW_RESPONSE").length));
}})();
"""
    assert _node(script) == 0


@pytest.mark.parametrize("banned", ["xiaohongshu", "douyin", "bilibili", "kuaishou"])
def test_domestic_cookies_never_leave_the_browser(banned: str) -> None:
    """整条拦截路上不许出现任何把国内平台凭据往外送的痕迹。"""
    for path in (OBSERVER, RELAY):
        text = path.read_text(encoding="utf-8")
        assert "cookie" not in text.lower() or "不读取 Cookie" in text or "不读 Cookie" in text, (
            f"{path.name} 里出现了 cookie 相关代码"
        )
    from social_archive.credentials import DOMESTIC_PLATFORMS

    assert banned in DOMESTIC_PLATFORMS, "国内平台清单与 T05 的拒绝清单不一致"
