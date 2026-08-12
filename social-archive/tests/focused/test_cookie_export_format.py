"""Cookie 导出格式（v0.0.0.7 / T06）。

任务包把格式列为 **frozen_fact**，原文：

  「Cookie 文件必须无 `#HttpOnly_` 前缀、会话 cookie 的 expiry 写 0。
    已实测 gallery-dl 1.32.9 与 yt-dlp 2026.7.4 都能完整读取；
    标准库 MozillaCookieJar 会静默丢弃，任何用它的适配器必须传
    ignore_discard=True, ignore_expires=True。」

这个文件把那段话变成可执行判据。**它值得单独存在**，因为格式错了的表现是
「文件生成成功、上传成功、界面显示已连接，然后取数是 0」——
一个看起来哪儿都对、只有结果是空的失败。

⚠️ 上面那段 frozen_fact 里有**一个分句在本项目的运行环境上已不成立**：
「标准库 MozillaCookieJar 会静默丢弃」带 #HttpOnly_ 前缀的行 —— CPython 现在
显式处理该前缀（实测 3.13，生产镜像 3.12 同源）。详见 C-T06-03 与
test_mozillacookiejar_reads_our_format_completely 的说明。
**产品结论没变**（仍然不输出前缀），变的只是理由。
frozen_fact 的另一半（会话 cookie expiry 写 0、适配器要传两个 ignore）实测仍成立。
"""

from __future__ import annotations

import http.cookiejar
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "apps/browser-extension/cookie-export.js"

# chrome.cookies.getAll() 的真实形状：httpOnly 的会话 cookie（登录态几乎都长这样）、
# 带过期时间的普通 cookie、hostOnly 的 cookie
CHROME_COOKIES = [
    {"domain": ".x.com", "hostOnly": False, "path": "/", "secure": True,
     "httpOnly": True, "name": "auth_token", "value": "rincewind42luggage"},
    {"domain": ".x.com", "hostOnly": False, "path": "/", "secure": True,
     "httpOnly": False, "name": "ct0", "value": "twoflower99tourist",
     "expirationDate": 1893456000.5},
    {"domain": "x.com", "hostOnly": True, "path": "/i", "secure": False,
     "httpOnly": True, "name": "kdt", "value": "granny88weatherwax"},
]


def _run_node(body: str) -> object:
    script = f"const M = require({json.dumps(str(EXPORT))});\n{body}"
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return json.loads(completed.stdout)


def _serialize(cookies: list[dict]) -> str:
    return _run_node(
        f"const rows = {json.dumps(cookies)};\n"
        "console.log(JSON.stringify('# Netscape HTTP Cookie File\\n' + "
        "rows.map(M.netscapeLine).join('\\n') + '\\n'));"
    )


def test_no_httponly_prefix_is_emitted() -> None:
    """frozen_fact 第一条。加了前缀 = 生成一个「格式正确但登录不上」的文件。"""
    text = _serialize(CHROME_COOKIES)
    assert "#HttpOnly_" not in text, (
        "导出的 cookies.txt 里出现了 curl 风格的 #HttpOnly_ 前缀。"
        "那样的行以 # 开头，会被当成注释丢掉——而登录态几乎全在 httpOnly cookie 里。"
    )
    # 三条都要在，一条都不能因为 httpOnly 被过滤掉
    for name in ("auth_token", "ct0", "kdt"):
        assert f"\t{name}\t" in text, f"{name} 没有出现在导出结果里"


def test_session_cookies_get_expiry_zero() -> None:
    """frozen_fact 第二条。没有 expirationDate 的是会话 cookie，expiry 必须写 0。"""
    text = _serialize(CHROME_COOKIES)
    rows = {
        line.split("\t")[5]: line.split("\t")
        for line in text.splitlines() if line.count("\t") >= 6
    }
    assert rows["auth_token"][4] == "0", "会话 cookie 的 expiry 不是 0"
    assert rows["kdt"][4] == "0"
    # 有过期时间的要向下取整，不能带小数——第 5 列必须是纯整数
    assert rows["ct0"][4] == "1893456000", "带过期时间的 cookie 没有取整"


def test_seven_tab_separated_columns_in_the_documented_order() -> None:
    text = _serialize(CHROME_COOKIES)
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        assert len(parts) == 7, f"列数不是 7：{len(parts)}"
        assert parts[1] in {"TRUE", "FALSE"}
        assert parts[3] in {"TRUE", "FALSE"}
        assert parts[4].isdigit(), "expiry 必须是纯数字"
    assert text.startswith("# Netscape HTTP Cookie File\n"), "yt-dlp 会校验首行"


def test_include_subdomains_tracks_hostonly() -> None:
    text = _serialize(CHROME_COOKIES)
    rows = {line.split("\t")[5]: line.split("\t") for line in text.splitlines() if line.count("\t") >= 6}
    assert rows["auth_token"][1] == "TRUE", "非 hostOnly 的 cookie 应当 includeSubdomains=TRUE"
    assert rows["kdt"][1] == "FALSE", "hostOnly 的 cookie 应当 includeSubdomains=FALSE"


def test_mozillacookiejar_reads_our_format_completely(tmp_path: Path) -> None:
    """我们生成的格式必须能被标准库完整读出来——一条不少。

    ⚠️ 冲突 C-T06-03（实测证伪任务包 frozen_fact 的一个分句）

    frozen_fact 原文说「标准库 MozillaCookieJar 会静默丢弃」带 `#HttpOnly_`
    前缀的行。**在本项目实际运行的 Python 上不成立**：CPython 的
    http.cookiejar 里有一段显式处理该前缀的代码（源码注释原话
    "the line is prepended with #HttpOnly_"），3.13 实测两条都能读出来，
    生产镜像的 3.12 同源。

    **产品结论不变**：仍然不输出 `#HttpOnly_` 前缀。理由从"标准库会丢"
    换成"不带前缀在新旧解析器上都能读，带前缀只在新的上能读"——
    不加前缀是严格更兼容的那一边，而真正的消费者
    （gallery-dl 1.32.9 / yt-dlp 2026.7.4）本来就是按不带前缀实测过的。

    所以这条判据守的是**我们的输出**，不再去断言标准库会不会丢。
    """
    good = tmp_path / "good.txt"
    good.write_text(_serialize(CHROME_COOKIES), encoding="utf-8")
    jar = http.cookiejar.MozillaCookieJar(str(good))
    jar.load(ignore_discard=True, ignore_expires=True)
    names = {cookie.name for cookie in jar}
    assert names == {"auth_token", "ct0", "kdt"}, f"我们的格式没被完整读出来：{names}"
    # 登录态那条必须带对域和路径，不然请求时不会被带上
    auth = next(c for c in jar if c.name == "auth_token")
    assert auth.domain == ".x.com" and auth.path == "/" and auth.secure


def test_stdlib_httponly_handling_is_pinned_so_the_stale_claim_gets_rechecked() -> None:
    """把 C-T06-03 的实测结论钉住。

    如果哪天标准库改回"静默丢弃"，这条会红，提醒下一个人：
    frozen_fact 那句话在那个版本上又成立了，别按现在的注释去理解。
    """
    import inspect

    source = inspect.getsource(http.cookiejar.MozillaCookieJar)
    assert "HttpOnly" in source, (
        "标准库不再显式处理 #HttpOnly_ 前缀——任务包 frozen_fact 的那句话"
        "在当前 Python 上可能又成立了，请重新核对 C-T06-03"
    )


def test_session_cookies_are_dropped_without_ignore_discard(tmp_path: Path) -> None:
    """frozen_fact 的后半句：任何用 MozillaCookieJar 的适配器必须传两个 ignore。"""
    path = tmp_path / "session.txt"
    path.write_text(_serialize(CHROME_COOKIES), encoding="utf-8")
    jar = http.cookiejar.MozillaCookieJar(str(path))
    jar.load()  # 故意不传 ignore_discard / ignore_expires
    names = {cookie.name for cookie in jar}
    assert "auth_token" not in names, (
        "不传 ignore_discard 时会话 cookie 居然还在——那 frozen_fact 的后半句就该重写"
    )


def test_domestic_platforms_are_refused_before_any_cookie_is_read() -> None:
    """国内平台在导出层就被挡住，连 chrome.cookies.getAll 都不会调用。"""
    result = _run_node(
        "(async () => { const out = {};"
        "for (const p of ['xiaohongshu','douyin','bilibili','kuaishou']) {"
        "  try { await M.exportPlatformSession(p); out[p] = 'NOT_BLOCKED'; }"
        "  catch (e) { out[p] = e.code; } }"
        "console.log(JSON.stringify(out)); })();"
    )
    assert result == {p: "PLATFORM_FORBIDDEN" for p in
                      ("xiaohongshu", "douyin", "bilibili", "kuaishou")}


def test_allowed_platforms_are_exactly_the_three_western_sources() -> None:
    result = _run_node("console.log(JSON.stringify(Object.keys(M.ALLOWED_PLATFORMS).sort()));")
    assert result == ["instagram", "x", "youtube"]


def test_export_module_never_logs_a_cookie_value() -> None:
    """硬边界之三。判据打在源码上——一个 console 都不该有。"""
    text = EXPORT.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*"))
    )
    assert "console." not in code, "cookie 导出模块里出现了 console 输出"


def test_not_logged_in_is_distinct_from_permission_denied() -> None:
    """任务包 suggested_path：未登录返回 NOT_LOGGED_IN，不要返回空字符串。

    这两件事的下一步不一样——一个要用户去登录，一个要用户去授权。
    合并成同一个错误码，用户会照着错的提示忙半天。
    """
    text = EXPORT.read_text(encoding="utf-8")
    for code in ("NOT_LOGGED_IN", "PERMISSION_DENIED", "PLATFORM_FORBIDDEN"):
        assert code in text
    result = _run_node(
        "globalThis.chrome = { cookies: { getAll: async () => [] } };"
        "(async () => { try { await M.exportPlatformSession('x'); console.log(JSON.stringify('NOT_BLOCKED')); }"
        " catch (e) { console.log(JSON.stringify(e.code)); } })();"
    )
    assert result == "NOT_LOGGED_IN", "读到 0 条 cookie 时没有报 NOT_LOGGED_IN"


def test_cookies_permission_is_optional_not_baseline() -> None:
    """装插件时不该一上来就要读 Cookie 的权力，只在点「连接」那一刻才要。"""
    manifest = json.loads((ROOT / "apps/browser-extension/manifest.json").read_text(encoding="utf-8"))
    assert "cookies" not in manifest.get("permissions", [])
    assert "cookies" in manifest.get("optional_permissions", [])
    hosts = " ".join(manifest.get("optional_host_permissions", []))
    for domain in ("x.com", "instagram.com", "youtube.com", "google.com"):
        assert domain in hosts, f"{domain} 不在可选 host 权限里，导出会拿不到 cookie"


@pytest.mark.parametrize("domestic", ["xiaohongshu.com", "douyin.com", "bilibili.com", "kuaishou.com"])
def test_domestic_domains_never_appear_in_the_allowed_table(domestic: str) -> None:
    text = EXPORT.read_text(encoding="utf-8")
    allowed_block = text.split("ALLOWED_PLATFORMS", 1)[1].split("FORBIDDEN_PLATFORMS", 1)[0]
    assert domestic not in allowed_block


def test_the_ui_actually_routes_western_sources_to_cookie_custody() -> None:
    """T06 的机制必须**从界面够得着**。

    实测踩到过：SA_CONNECT_PLATFORM_SESSION 建好了，却没有任何界面通向它——
    background 的 connectPlatform() 把 x/instagram/youtube 一律送去
    connectBrowserPlatform（DOM 抓取时代的老路），而那条路在 T03 之后
    只会回 LOGIN_PROOF_UNAVAILABLE。也就是说点「连接 X」永远连不上，
    而 T06 整套 Cookie 托管代码一行都不会被执行。

    这是「写了但没接上」的第二次（第一次是失败文案词典没有生产调用方）。
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "connectPlatformSessionByCookies" in background, "西方三源没有接到 Cookie 托管入口"
    block = background.split("async function connectPlatform(", 1)[1].split("\n}", 1)[0]
    assert "SACookieExport" in block, (
        "connectPlatform 没有按平台分流——西方三源会掉进 browser_session 老路"
    )
    # 老路仍要保留给未来的国内平台，但不能再吞掉西方三源
    assert "connectBrowserPlatform" in block


def test_cookie_platforms_and_catalog_do_not_disagree() -> None:
    """分流依据是 SACookieExport.ALLOWED_PLATFORMS，它必须与服务端托管清单一致。"""
    from social_archive.credentials import CUSTODIAL_PLATFORMS

    export = EXPORT.read_text(encoding="utf-8")
    block = export.split("ALLOWED_PLATFORMS", 1)[1].split("FORBIDDEN_PLATFORMS", 1)[0]
    for name in CUSTODIAL_PLATFORMS:
        assert f"{name}:" in block, f"扩展的可导出清单缺 {name}，服务端却收它"
