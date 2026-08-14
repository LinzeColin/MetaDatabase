"""service worker 里不许有裸的 `chrome.permissions.request`（2026-08-10）。

## 这条不变量是他那次停摆换来的

2026-08-04，Owner 的自动同步全停了，生产库里最后一次同步的错误码是
`PLATFORM_PERMISSION_MISSING`。根因是一条浏览器的硬规矩：

    chrome.permissions.request 要求「在一次用户手势期间调用」，
    而 MV3 的 service worker 里**永远没有手势**——**即使这个权限刚刚被授予过**。

2026-08-06 的修法是给主机权限加「先 contains 再 request」
（`shared.js` 的 `requestPlatformPermission`），2026-08-07 又把授权那一下
挪进页面（连接面板 / 账号页的 `grantWhatConnectNeeds`）。

**而 background.js 里的三个申请点只改了一个。** 另外两处一直是裸的：

    connectChromeBookmarks           bookmarks   裸 request、**没有 catch**
    connectPlatformSessionByCookies  cookies     裸 request、有 catch

后果分别是：

  · Chrome 书签 —— 他在面板上点「连接账号」、在弹框里点了「允许」，
    消息发到 background，第一行就抛，面板把那句**英文**原样显示给他。
    而 Chrome 书签正是产品在「一个都同步不动」时推荐他去连的那一个。
  · 登录状态托管 —— 不抛，但必然回 false，于是产品对他说
    「没有获得授权」，**把责任推回给一个明明点过「允许」的人**。

一条都没有判据抓到：1266 条测试里那个假 `chrome` 把
`permissions.request` 桩成了 `async () => true`——**夹具把用户必须自己挣的
那一下直接给了**，于是测试看到的是一个在真浏览器里不可能发生的成功。

## 这里钉三件事

1. `background.js` 里一个 `chrome.permissions.request` 都不许有。
2. 它仍然要 `contains`（只是不许 request）——不然「删干净」也能过。
3. `shared.js` 里那两个帮手，每一个 request 前面都得有 contains。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from js_source import code_only                              # noqa: E402

EXT = ROOT / "apps/browser-extension"

# 有用户手势的上下文：它们是**页面**，`chrome.permissions.request` 在那儿是对的写法。
PAGE_CONTEXTS = {"options.js", "popup.js", "connect-frame.js", "sidepanel.js"}
# 两个上下文都会加载它；里面的 request 必须被 contains 挡在后面。
SHARED = "shared.js"

pytestmark = pytest.mark.skipif(not EXT.is_dir(), reason="扩展目录不存在")


def _js_files() -> list[Path]:
    return sorted(p for p in EXT.rglob("*.js"))


def _code(path: Path) -> str:
    """**只留代码**，整行注释剔掉。

    第一版是我自己抄的一份：`bridge.js` 里一整段解释「内容脚本里根本没有
    permissions API」的注释被判成了违规。同一天 `check_no_mechanism_is_
    unreachable.py` 也栽在同一件事上（注释里的 sendMessage 被当成真发送）。
    抄成三份的那天三份会各自漂，所以统一走 `scripts/js_source.py`。
    """
    return code_only(path)


def test_the_service_worker_has_no_bare_permission_request() -> None:
    background = _code(EXT / "background.js")
    assert "chrome.permissions.request" not in background, (
        "background.js 里又出现了 `chrome.permissions.request`。"
        "service worker 里没有用户手势，它一定抛 "
        "'This function must be called during a user gesture'——**即使权限刚被授予过**。"
        "改用 `SA.ensurePermission({...})`（先 contains 再 request，并且收住异常）")


def test_it_still_checks_permissions_instead_of_just_deleting_the_call() -> None:
    """**「删干净」不算修好。**

    只删掉 request、不做 contains，等于闭着眼睛往下走：
    没授权时读书签会抛一句更难懂的话。
    """
    background = _code(EXT / "background.js")
    assert "chrome.permissions.contains" in background, (
        "background.js 连 contains 都没有了——那不是修好，是把检查删了")
    assert "SA.ensurePermission" in background, (
        "两个申请点没有走 shared.js 那个帮手")


def test_every_request_in_shared_is_guarded_by_a_contains() -> None:
    """`shared.js` 两个上下文都会加载，里面的 request 必须先问 contains。"""
    lines = _code(EXT / SHARED).splitlines()
    hits = [i for i, line in enumerate(lines) if "chrome.permissions.request" in line]
    assert hits, "shared.js 里一个 request 都没有——这条判据在空扫"
    for index in hits:
        window = "\n".join(lines[max(0, index - 12):index])
        assert "chrome.permissions.contains" in window, (
            f"shared.js:{index + 1} 的 request 前面 12 行内没有 contains："
            f"{lines[index].strip()!r}——service worker 里它会直接抛")


def test_only_page_contexts_may_ask_the_user_directly() -> None:
    """**清单是豁免，不是名单。** 新加的文件默认不许直接 request。"""
    offenders = sorted(
        path.name for path in _js_files()
        if "chrome.permissions.request" in _code(path)
        and path.name not in PAGE_CONTEXTS | {SHARED})
    assert offenders == [], (
        f"这些文件直接调了 chrome.permissions.request：{offenders}。"
        "只有页面（有用户手势）才可以；别的地方走 SA.ensurePermission")


def test_the_measured_evidence_backing_this_rule_is_still_there() -> None:
    """**这条规则建在一次真测量上，不是建在我的推理上。**

    `shipped_package_drill.py` 在真 Chrome 里、用他真正下载的那个包，
    在 service worker 里调了三次 request，三次都抛。那份测量要一直在。
    """
    import json

    data = json.loads((ROOT / "evidence/G3/SHIPPED_PACKAGE.json").read_text(encoding="utf-8"))
    measured = data.get("permission_request_from_service_worker") or {}
    assert set(measured) >= {"bookmarks", "cookies", "host"}, measured
    for name, value in measured.items():
        threw = str((value or {}).get("threw") if isinstance(value, dict) else value)
        assert "user gesture" in threw, (
            f"service worker 里 {name} 这次**没有**抛手势错误：{value!r}——"
            "要么 Chrome 改了行为（那这条规则要重估），要么这次测量没跑到")


def test_the_panel_still_asks_in_the_page_before_messaging_the_worker() -> None:
    """另一半：页面那一下不能丢。两边都在，这条路才通。"""
    panel = (EXT / "connect-frame.js").read_text(encoding="utf-8")
    grant = panel.index("async function grantWhatConnectNeeds")
    send = panel.index('type: "SA_ACCOUNT_CONNECT"')
    assert grant < send, "面板变成了先发消息再要权限——手势就是在这一步丢的"
    assert re.search(r'permissions\.push\("bookmarks"\)', panel), (
        "面板不再为 Chrome 书签要 bookmarks 了——那 background 那边永远等不到")
