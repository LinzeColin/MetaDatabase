r"""「去授权」必须出现在他真正打开的那一屏（2026-08-18）。

## 它修的是什么

v0.0.0.106 我把「缺授权」标记加进了 `connect-frame.js` —— 插件自己那个面板。
而 Owner 点「管理账号」打开的是**资料库自己的账号同步中心**（`app.js` 的
`renderSyncTable`）。两个不同的面板。他的原话：**「没有需要我授权的地方」**。

改到对的那一屏之后还错了第二次：那一支放在 `partial/failed → 重试` 的
**后面**，而他三个账号都停在 partial，于是永远先拿到「重试」——
**而缺授权时重试必然又失败**（同步那一刻没有用户手势，
`chrome.permissions.request` 一定抛）。这正是这个文件自己写过的那条禁忌：
不给一个点下去必然失败的按钮。

## 这道判据钉三件事

1. 同步中心那张表里有「去授权」这条分支
2. 它排在 partial/failed 那一支**前面**（否则永远走不到）
3. 查授权状态的那个函数**有人调**（这个仓最贵的病是「建好了没接上」）
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"


def _code() -> str:
    text = APP.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("//"))


def test_同步中心那张表里有去授权() -> None:
    code = _code()
    assert "data-open-connect-panel" in code, (
        "同步中心没有「去授权」按钮——他点「管理账号」打开的正是这一屏，"
        "而缺授权时那里必须有一颗他点得到的按钮。")
    assert "platformPermissions" in code, "没有读授权状态，那颗按钮不可能按需出现"


def test_去授权要排在重试前面() -> None:
    """**顺序就是可达性。**

    他三个账号都停在 partial；只要「重试」那一支在前面，
    缺授权这一支就永远走不到——我上一版就是这么写的，真 Chrome 里一眼看见。
    """
    code = _code()
    grant = code.find("platformPermissions?.[account.platform] === false")
    retry = code.find('["partial", "failed"].includes(status)')
    assert grant != -1, "找不到缺授权那一支"
    assert retry != -1, "找不到 partial/failed 那一支——这道判据的前提变了"
    assert grant < retry, (
        "缺授权那一支排在 partial/failed 之后——他三个账号都停在 partial，"
        "于是永远先拿到「重试」，而缺授权时重试必然再失败一次。")


def test_查授权那个函数有人调() -> None:
    """定义了没人调 = 没做。这个仓最贵的那个形状。"""
    code = _code()
    calls = len(re.findall(r"refreshPlatformPermissions\(\)", code))
    assert calls >= 2, (
        f"refreshPlatformPermissions 只出现 {calls} 次（定义算一次）——"
        "没有任何地方调它，那张表永远拿不到授权状态。")


def test_网页这侧不许自己调_permissions_api() -> None:
    """网页里没有 `chrome.permissions`，必须经桥去问 background。

    直接写 `chrome.permissions.contains` 会静默抛，然后 catch 掉，
    表现为「永远查不到授权状态」——看起来和「授权都给了」一模一样。
    """
    code = _code()
    assert "chrome.permissions" not in code, (
        "app.js 里出现了 chrome.permissions——网页这侧根本没有这个 API")
    assert "SA_PLATFORM_PERMISSIONS" in code, "没有经桥去问 background"
