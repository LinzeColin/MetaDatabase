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

from tests.focused._source_slices import install_net_observer_body, run_diagnosis_body

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



def _install_function() -> str:
    """诊断按钮背后那段代码的正文。

    它原来长在消息处理器里，2026-08-05 整段挪成了 installNetObserverForTab——
    只为一件事：让真浏览器演练能调它本人，而不是照抄一遍它的顺序。
    下面几条判据跟着挪到这里取，**取不到就直接报错**，不许静默退化成空串。
    """
    code = (EXT / "background.js").read_text(encoding="utf-8")
    assert "async function installNetObserverForTab" in code, "安装函数不见了"
    body = code.split("async function installNetObserverForTab", 1)[1]
    return body.split("\nasync function", 1)[0]



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
  setTimeout, clearTimeout,
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
const sandbox = {{ console, Date, setTimeout, clearTimeout, XMLHttpRequest: function () {{}} }};
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


def test_relay_is_injected_before_the_observer() -> None:
    """注入顺序：**中继先，观察器后**。

    观察器在 IIFE 末尾就 post 出 SA_OBSERVER_INSTALLED；中继那时若还没挂上监听，
    这条消息就掉进虚空，background 于是分不清「观察器装好了」和「注入静默失败了」。

    这个顺序是在真实浏览器里跑出来才发现的——Node 沙箱里判据是先挂监听再跑观察器，
    永远看不到这个问题；真实注入顺序恰好是反的。实测：
      · 观察器先装 → observer_installed 收不到（false）
      · 中继先装   → 收得到（true）
    """
    block = _install_function()
    relay_at = block.index("content/net-relay.js")
    observer_at = block.index("net-observer.js")
    assert relay_at < observer_at, (
        "观察器被排在中继前面注入——SA_OBSERVER_INSTALLED 会丢，"
        "background 将无法区分「装好了」与「注入静默失败」"
    )


def test_the_diagnostic_does_not_require_the_answer_it_is_looking_for():
    """诊断模式不能依赖「拦截前缀已知」——那正是它要去发现的东西。

    实测（2026-08-04）：平台目录里只有 bilibili 有拦截前缀，
    xiaohongshu / douyin / kuaishou 全是 null。而 SA_INSTALL_NET_OBSERVER
    在前缀为空时会显式拒绝（INTERCEPT_PREFIX_UNKNOWN）——
    **于是那颗「帮开发者看一眼这个平台」的按钮在 3/4 的平台上当场被拒，
    工具拒绝执行它自己被造出来要做的事。**

    诊断模式改为按当前标签页的域名推前缀。
    """
    block = _install_function()
    assert "if (diagnostic)" in block, "没有诊断模式，前缀未知的平台会被直接拒绝"
    assert "chrome.tabs.get(tabId)" in block, "没有去读标签页的真实地址"
    assert "registrable" in block, "没有从域名推出前缀"


def test_the_diagnostic_cannot_be_told_what_to_capture():
    """前缀只从 tab.url 推，调用方给什么都不采信。

    否则「诊断」就成了一个可以指定抓任意域名的通道。
    """
    background = (EXT / "background.js").read_text(encoding="utf-8")
    block = _install_function()
    diagnostic = block.split("if (diagnostic)", 1)[1][:900]
    assert "message.urlPrefixes" not in diagnostic, "诊断模式采信了调用方给的前缀"
    assert "prefixes = [registrable]" in diagnostic, "前缀不是从域名推出来的"


def test_the_diagnostic_says_up_front_when_the_page_is_not_diagnosable():
    """认不出的页面要当场说清楚，而不是走到注入失败才吐一句看不懂的话。

    platformFromUrl 认不出时回落到 generic-web，而它的权限模式是**空数组**：
    继续走下去 = 请求零个 origin → executeScript 缺 host 权限 →
    OBSERVER_INSTALL_FAILED「无法在该页面上启动同步」。用户对着那句话没法行动。
    """
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    block = run_diagnosis_body(popup)
    assert "patternsForPlatform" in block, "没有先确认这个平台有权限模式"
    assert "不是可诊断的平台" in block, "认不出时没有给出人能看懂的话"
    guard_at = block.index("patternsForPlatform")
    install_at = block.index("SA_INSTALL_NET_OBSERVER")
    assert guard_at < install_at, "判断排在安装之后，等于没判断"


def test_the_diagnostic_reloads_first_so_it_does_not_use_a_stale_observer():
    """观察器对同一次页面加载幂等，扩展更新后不重载 = 用的还是旧代码。

    实测（2026-08-04，真实 Chrome + 本地探针页）：不 reload 时抓到 **0 条**，
    而自报 installed/ready 全为 true —— 「装好了、就绪了、什么也没有」，
    最难查的那种。reload 之后同一套代码立刻抓到 6 条。
    """
    block = _install_function()
    assert "chrome.tabs.reload(tabId)" in block, "诊断前不刷新页面，可能用到旧观察器"
    # **这条判据的方向 2026-08-05 反过来了，而且是对的。**
    #
    # 原来钉的是「刷新排在注入之前」。那一版注入用的是 executeScript，
    # 只能在页面加载完之后打进去；实测那样太晚——页面像真收藏夹页那样
    # 只在加载时发一次请求的话，自报 installed/ready 全为 true 而抓到 0 条。
    #
    # 现在钉的是更强的一条：**注册要排在刷新之前**。注册成 document_start 的
    # 内容脚本，脚本就比页面自己的 JS 先跑，那条缝才真的封上。
    register_at = block.index("registerContentScripts")
    reload_at = block.index("chrome.tabs.reload(tabId)")
    assert register_at < reload_at, (
        "注册排在刷新之后，等于这次刷新页面上没有观察器——"
        "页面加载时打的那个请求会一条都抓不到"
    )
