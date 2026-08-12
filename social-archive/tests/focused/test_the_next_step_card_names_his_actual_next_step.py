"""那张「下一步」卡片，对他说的必须是他真正的下一步（2026-08-10）。

这张卡片的规则写在它自己的注释里：

    按顺序找到**第一个**没做完的事，只显示它；全做完就什么也不显示。
    不排优先级、不并列、不给第二个选项——多给一个选择就是多一次犹豫。

Owner 此刻：装着 v0.0.0.22（高于下限 v0.0.0.9，所以 `compatible` 为真），
三个账号全断开。按原来的顺序他命中的是「第 3 步：连接一个能同步的来源」，
那颗按钮是 `openConnectPanel() || openSyncModal()`。

**而他那份插件拿不到连接面板**（v0.0.0.22 的 manifest 里
`web_accessible_resources` 是 null，握手回复里没有 `connectFrameUrl`）。
于是他被送进同步中心，再点一次「重新连接」，才被 `connectAccount` 告知
「你装的是旧版」。**卡片说的不是他的下一步，而这张卡存在的全部理由就是说那件事。**

判的是**能力**不是版本号：`connectAccount` 那道拦截也是看面板拿不拿得到
（`openConnectPanel()` 返回 false），两处同一个依据。版本号会随发布漂，
「有没有那一页」不会。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"

pytestmark = pytest.mark.skipif(not APP.is_file(), reason="app.js 不存在")


def _code() -> str:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from js_source import code_only

    return code_only(APP)


def test_a_stale_plugin_is_named_as_the_next_step() -> None:
    code = _code()
    start = code.find("function renderNextStep(")
    assert start >= 0, "renderNextStep 没了——这条判据在空扫"
    block = code[start:code.find("\n  async function refreshEverything", start)]
    assert "connectFrameUrl" in block, (
        "「下一步」那张卡不看连接面板拿不拿得到——"
        "装着旧插件的人会被指去「连接一个能同步的来源」，"
        "而那颗按钮在他那儿打不开面板")


def test_it_comes_before_the_connect_step() -> None:
    """顺序就是这张卡的全部语义：**第一个**没做完的事。"""
    code = _code()
    start = code.find("function renderNextStep(")
    block = code[start:code.find("\n  async function refreshEverything", start)]
    stale = block.find("connectFrameUrl")
    connect = block.find("连接一个能同步的来源")
    assert stale >= 0 and connect >= 0, "两步至少有一步找不到了"
    assert stale < connect, (
        "更新插件那一步排在连接来源之后——他会先被指去点一颗打不开的按钮")


def test_it_does_not_tell_him_he_already_meets_the_bar() -> None:
    """**不许说「至少需要 v<下限>」。**

    他装的是 v0.0.0.22，下限是 v0.0.0.9。22 比 9 大，那句话等于告诉他不用动。
    安装页上同一句话 2026-08-10 已经修过一次（`paintUpdate` 对两个调用方
    说同一句），这里是同一种病的另一处。
    """
    code = _code()
    start = code.find("function renderNextStep(")
    block = code[start:code.find("\n  async function refreshEverything", start)]
    index = block.find("connectFrameUrl")
    window = block[index:index + 900]
    assert "至少需要" not in window, (
        f"对高于下限的人说「至少需要」，等于告诉他不用动：{window[:220]}")
    assert "连接账号要更新之后才成" in window, (
        f"没说清为什么要更新（不是版本太低，是连接账号要最新的）：{window[:220]}")
