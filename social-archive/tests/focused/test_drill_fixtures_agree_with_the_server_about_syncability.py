r"""演练夹具说「这个平台能不能同步」，必须和服务端说的一样（2026-08-13）。

## 它修的是什么

`bilibili_end_to_end_drill.py` 的夹具里写着一句注释：**「照生产的形状给全九个平台」**。
而它是**手抄**的，抄完就漂了：`xiaohongshu` / `douyin` / `instagram` / `reddit`
四家被写成 `sync_supported: False`，而服务端那行是

    "sync_supported": platform in SYNCABLE_NOW          # api.py

`SYNCABLE_NOW` 早就含着这四家（2026-08-13 从生产实测：bilibili、douyin、
generic-web、instagram、reddit、xiaohongshu）。

**后果不是「夹具不够全」，是方向反了。** 那个演练一直在验「这四家只能手动保存」
那一屏，而他在生产上看到的是**能同步**那一屏——他真会看到的那一屏，
反而一次都没被走过。这正是验收条件里「绝不给一颗结构上不可能成功的按钮」
所在的那段界面，却拿着一份和生产相反的事实在验。

## 它怎么钉

不查「有没有写」，查**写的和服务端算的一不一样**。夹具里每一处
`platform: X` + `sync_supported: Y`（Python 和 JS 两种写法都认），
Y 必须等于 `X in SYNCABLE_NOW`。

夹具**可以**只列一部分平台——列了才查，没列不管。查的是**列了的别写反**。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.account_sync import SYNCABLE_NOW  # noqa: E402

SCRIPTS = ROOT / "scripts"

# Python: "platform": "bilibili", … "sync_supported": True
# JS:      platform: "bilibili",  … sync_supported: true
_PAIR = re.compile(
    r"""["']?platform["']?\s*:\s*["'](?P<platform>[a-z\-]+)["']"""
    r"""(?P<between>.{0,240}?)"""
    r"""["']?sync_supported["']?\s*:\s*(?P<value>True|False|true|false)""",
    re.S,
)


def _fixture_claims() -> list[tuple[Path, str, bool]]:
    claims: list[tuple[Path, str, bool]] = []
    for path in sorted(SCRIPTS.glob("*.py")) + sorted(SCRIPTS.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        if "sync_supported" not in text:
            continue
        for match in _PAIR.finditer(text):
            # 中间夹着另一个 platform 的话，这两半不属于同一条记录。
            if "platform" in match.group("between"):
                continue
            claims.append((path, match.group("platform"),
                           match.group("value").lower() == "true"))
    return claims


def test_the_scan_actually_finds_fixtures() -> None:
    """**先证明这把尺子量得到东西。**

    正则一旦写偏（键名换了引号、换了缩进），这个文件会一条都扫不到，
    然后三条断言全部空过——一个永远不会红的判据比没有判据更糟。
    """
    claims = _fixture_claims()
    assert len(claims) >= 6, f"只扫到 {len(claims)} 条平台声明，正则大概率没匹配上"
    assert {c[1] for c in claims} >= {"bilibili", "x"}, \
        f"扫到的平台不对：{sorted({c[1] for c in claims})}"


@pytest.mark.parametrize("path,platform,claimed", _fixture_claims(),
                         ids=lambda v: str(v)[-40:] if isinstance(v, Path) else str(v))
def test_每条夹具声明都和服务端一致(path: Path, platform: str, claimed: bool) -> None:
    truth = platform in SYNCABLE_NOW
    assert claimed is truth, (
        f"{path.name} 说 {platform} 的 sync_supported={claimed}，"
        f"而服务端算出来是 {truth}（api.py: `platform in SYNCABLE_NOW`）。\n"
        f"**夹具和服务端说反了，演练就会去验一屏他看不到的界面。**\n"
        f"别在夹具里改这个数——改成照 SYNCABLE_NOW 现算，"
        f"见 bilibili_end_to_end_drill._supported_platforms_like_production()。")
