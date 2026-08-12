"""侧边栏必须在**有手势的那一页**里开，不能交给 service worker（2026-08-10）。

## 同一条规矩的第二处

刚修完 `chrome.permissions.request`（service worker 里没有用户手势，
所以裸调必抛）之后，顺着「还有哪些 API 要手势」翻，
`chrome.sidePanel.open()` 是第二处，而它的路径一模一样：

    popup.js  点「同步进度／任务中心」
      → chrome.runtime.sendMessage({ type: "SA_OPEN_TASK_CENTER" })
      → background.js 里 chrome.sidePanel.open({ windowId })

**在真 Chrome 里量了三次**（探针加载的是发布 zip 里那个扩展本身）：

    service worker 里直接调                        抛「`sidePanel.open()` may only be
                                                   called in response to a user gesture.」
    service worker 处理**带手势发出的消息**时调      照样抛 —— Chrome 不特判 onMessage
    在页面里调（中间还隔一次 await 拿 windowId）     ok

对照组：同一个 service worker 里 `sidePanel.setPanelBehavior()`（不需要手势）
是成功的——所以不是无头浏览器不支持侧边栏，就是手势这一条。

而 popup 那两处 `await chrome.runtime.sendMessage(...)` 之后**直接
`window.close()`，连返回值都不看**——所以他看到的是「点了没反应」。
背景里那个 listener 出错时回的是 `{ok:false, error:"…"}`，没有任何人读。

## 这里钉什么

1. popup 自己调 `chrome.sidePanel.open`（那一页有手势）。
2. background 里不许再有 `SA_OPEN_TASK_CENTER` 这个消息类型
   ——它一旦回来，就意味着又把这件事推回了没有手势的那一侧。
3. background 里 `chrome.sidePanel.open` 只剩键盘快捷键那一处。

**说清没验的那一半**：`chrome.commands.onCommand`（快捷键）那一处**没有量过**
——探针没法从外面按下一个真快捷键。它是既有代码，不是这次引入的；
出错时外层 catch 会把插件图标标红，不会静默。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from js_source import code_only                              # noqa: E402

EXT = ROOT / "apps/browser-extension"

pytestmark = pytest.mark.skipif(not EXT.is_dir(), reason="扩展目录不存在")


def _code(path: Path) -> str:
    """只留代码，整行注释剔掉。**注释里提一句不算调用**——
    这份判据自己就是靠上面那段注释在说明为什么删掉 SA_OPEN_TASK_CENTER。"""
    return code_only(path)


def test_the_popup_opens_the_side_panel_itself() -> None:
    """**手势在这一页上，调用就得在这一页上。**"""
    popup = _code(EXT / "popup.js")
    assert "chrome.sidePanel.open" in popup, (
        "popup 不再自己开侧边栏了——一旦把它推回 service worker，"
        "`sidePanel.open()` 会抛「may only be called in response to a user gesture」，"
        "而 popup 关掉之后他只会看到「点了没反应」")


def test_the_popup_no_longer_delegates_it_to_the_worker() -> None:
    popup = _code(EXT / "popup.js")
    assert "SA_OPEN_TASK_CENTER" not in popup, (
        "popup 又在用消息把开侧边栏这件事交给 background 了——手势不跨 sendMessage")


def test_the_worker_has_no_task_center_message_left() -> None:
    """**没有发送方的消息类型要删掉。**

    留着它等于给下一个人一条看起来能用、实际结构上走不通的路。
    """
    background = _code(EXT / "background.js")
    assert "SA_OPEN_TASK_CENTER" not in background, (
        "background 里那个 SA_OPEN_TASK_CENTER 分支还在——它调 sidePanel.open，"
        "而在 service worker 里那一句必抛")


def test_the_only_side_panel_open_left_in_the_worker_is_the_keyboard_command() -> None:
    """键盘快捷键那一处留着（Chrome 把 onCommand 当成手势），**但只剩它一处**。"""
    lines = _code(EXT / "background.js").splitlines()
    hits = [i for i, line in enumerate(lines) if "chrome.sidePanel.open" in line]
    assert len(hits) == 1, (
        f"background 里有 {len(hits)} 处 chrome.sidePanel.open（行号 "
        f"{[i + 1 for i in hits]}）——除了 chrome.commands.onCommand 那一处，"
        "service worker 里没有别的地方能拿到手势")
    before = "\n".join(lines[max(0, hits[0] - 30):hits[0]])
    assert "chrome.commands.onCommand" in before, (
        "剩下那一处不在 chrome.commands.onCommand 里——那它拿不到手势")


def test_the_popup_does_not_close_before_it_knows_it_worked() -> None:
    """**失败要看得见。** 原来是 `.then(() => window.close())`，不看返回值。"""
    popup = _code(EXT / "popup.js")
    index = popup.find("chrome.sidePanel.open")
    assert index >= 0, "popup 里没有 chrome.sidePanel.open——先看上面那条判据"
    after = popup[index:index + 400]
    assert "catch" in after, (
        "开侧边栏没有 catch——打不开时 popup 直接关掉，他看到的还是「点了没反应」")
