"""装了两份插件时，这一页不能只看见先答的那一份（2026-08-10）。

## 说明书早就警告过这件事

    换个地方装，Chrome 会给它一个新的插件 ID，等于你同时装了两个插件，
    而已经连好的账号留在旧的那个上。

而这一页的握手是**拿到第一个应答就摘掉监听器**：

    if (…data.requestId !== requestId) return;
    clearTimeout(timer); window.removeEventListener("message", onMessage);

两份都会应答，只有先答的那份被看见，另一份完全隐形。后果有两种，
都不是"少显示一条信息"：

  · 旧的那份先答 → 这一页**一直**说「请更新插件」，他更新完还是那个数。
    这正是 `bump_version.py` 文件头写的「**无限来回弹**」。
  · 连接账号落到哪一份上**不确定** → 落到旧的那份，他会再撞一次
    今天刚修掉的那堵墙（service worker 里要不到权限），而界面看起来一切正常。

两份能分得开：`connectFrameUrl` 是 `chrome-extension://<插件ID>/connect-frame.html`，
两份 ID 不同。

## 这里钉三件事

1. 探测要**收齐一小段时间内的应答**，不是第一个。
2. 有两份时报**最新那一份**的版本（否则旧的先答就把人卡在更新循环里），
   但把「装了两份」这件事本身说出来。
3. 有两份时**先别连**——落到哪一份是不确定的。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"
BRIDGE = ROOT / "apps/browser-extension/bridge.js"

pytestmark = pytest.mark.skipif(not APP.is_file(), reason="app.js 不存在")


def _fn(name: str, text: str) -> str:
    start = text.index(f"function {name}(")
    return text[start:start + 1800]


def test_the_probe_collects_every_reply_not_just_the_first() -> None:
    text = APP.read_text(encoding="utf-8")
    assert "function pingExtensions(" in text, (
        "没有收齐应答的探测函数——只取第一个应答，第二份插件就是隐形的")
    body = _fn("pingExtensions", text)
    assert "replies.push" in body, f"探测没有把每个应答都收下来：{body[:300]}"
    assert "removeEventListener" in body and "resolve(replies)" in body, body[:300]


def test_the_status_reports_the_newest_copy_but_names_the_duplicate() -> None:
    """**只报最新的**会让他以为一切正常；**只报重复**又会把能用的情况也挡了。"""
    body = _fn("refreshExtensionStatus", APP.read_text(encoding="utf-8"))
    assert "compareVersions" in body, (
        "没有在多个应答里挑最新的——旧的那份先答就会把他卡在「请更新插件」的循环里")
    assert "duplicateExtensionIds" in body, "没有把「装了两份」这件事记下来"


def test_connecting_stops_when_two_copies_answer() -> None:
    """**落到哪一份是不确定的**，所以先别连。"""
    body = _fn("connectAccount", APP.read_text(encoding="utf-8"))
    assert "duplicateExtensionIds" in body, (
        "连接那一步没有看「装了几份」——连到旧的那份上，他会再撞一次"
        "今天刚修掉的那堵墙，而界面看起来一切正常")
    assert "chrome://extensions" in body, (
        "拦住了却没说去哪儿删——这个仓的规矩是「做不到不是罪，做不到却说不清才是」")
    assert "一条都不会少" in body, "没说清删掉一份不会丢内容——「未连接」很容易被读成「我的收藏没了」"


def test_the_bridge_still_sends_something_that_tells_two_copies_apart() -> None:
    """**钉住前提**：分辨靠的是 connectFrameUrl 里的插件 ID。"""
    bridge = BRIDGE.read_text(encoding="utf-8")
    assert re.search(r'connectFrameUrl:\s*chrome\.runtime\.getURL\(', bridge), (
        "bridge 不再回 connectFrameUrl 了——那就没有办法分辨两份插件")
