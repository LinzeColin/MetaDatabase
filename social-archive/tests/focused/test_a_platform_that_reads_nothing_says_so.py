r"""登记成「一条都读不了」的平台，卡片上要说话，不能留一片空白（2026-08-10）。

## 怎么发现的：把生产下发的包装进真 Chrome，把连接页整段读出来

    Y
    YouTube
    未连接
    未连接
              ← **这一行是空的**（别的平台这里写着「收藏夹」/「已保存」）
    连接账号

我今天把 youtube 在 `SCANNABLE_RELATIONS` 里登记成 `Object.freeze([])`
（它的取数路没做；**不登记的话**服务端会按 PLATFORM_RELATIONS 下发
`['watch_later','playlist']`，扩展一条都不会扫，那次 run 永远等不到终批）。
于是 `scannableSummary` 返回空串，卡片就空着——**是我自己造的**。

验收第 1 条要的是「做不到自动的平台，界面必须当场说清」。
**空白不是说清**，它读起来像加载失败。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = ROOT / "apps/browser-extension/options.js"


def _node(expression: str):
    done = subprocess.run(
        ["node", "-e", f'const c=require("./apps/browser-extension/content/platform-catalog.js");'
                       f'console.log(JSON.stringify({expression}))'],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


REGISTERED = _node("Object.keys(c.SCANNABLE_RELATIONS)")


def test_there_is_a_platform_registered_as_reading_nothing() -> None:
    """反空扫：没有「登记成空」的平台，下面那条就白过。"""
    empty = [p for p in REGISTERED if not _node(f"c.scannableRelations({p!r})")]
    assert empty, "没有任何平台登记成空——这条判据在空扫（youtube 应该是）"


@pytest.mark.parametrize("platform", REGISTERED)
def test_every_registered_platform_says_something_on_its_card(platform: str) -> None:
    """卡片上那一行要么写它会读什么，要么写它读不了——不许空着。"""
    summary = _node(f"c.scannableSummary({platform!r})")
    if summary:
        return
    code = "\n".join(line for line in OPTIONS.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    assert "本版还不能自动读" in code, (
        f"{platform} 的扫描范围是空的，而卡片上没有兜底文案——"
        "他看到的是一片空白，那读起来像加载失败，不像「这一版读不了」")


def test_the_fallback_sits_on_the_scannable_branch() -> None:
    """**兜底要挂在 `scannableSummary` 那一支上。**

    挂错地方（比如挂在 relationCopy 那一支）时，登记过的空平台照样空着——
    而那正是要修的那一档。
    """
    code = "\n".join(line for line in OPTIONS.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    at = code.index("scannableSummary(platform)")
    tail = code[at:at + 220]
    assert "本版还不能自动读" in tail, (
        "兜底没挂在 scannableSummary 那一支上：\n" + tail[:200])
