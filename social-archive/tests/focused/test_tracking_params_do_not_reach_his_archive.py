r"""存进他档案馆的地址，不该拖着一条埋点尾巴（2026-08-13）。

## 撞见它的经过

读他生产库量出来的：**193 条内容里 129 条带查询串**——

    bilibili 100 条 `spm_id_from`   （"你是从哪儿点进来的"，纯埋点）
    douyin    28 条 `source`        （值形如 `Baiduspider-sdc`）
    xiaohongshu 1 条 `xsec_token`   （**这个是签名，不能丢**）

而 `canonicalize_url` 那张去追踪参数的表里只有 `utm_*` / `fbclid` / `gclid`
——**全是西方站的**，国内这几家一个都不认。

**后果不只是链接难看**：他库里 `www.bilibili.com/video/BV1oMgZ6EETu/`
**存了两行**，就因为两次点进去的 `spm_id_from` 不一样。
去掉查询串之后那两条会收敛成同一条。

## 为什么是白名单

黑名单要穷举所有埋点参数名——**开放集合，永远补不全**，换个平台就漏一批
（今天已经在另一处栽过：按主机／路径拉黑名单挡埋点，连错三版）。
白名单只要回答「这条地址的身份需要哪些参数」，**那是个封闭问题**：
视频地址的身份全在 path 里，一个查询参数都不需要。

**小红书是刻意的例外**：`xsec_token` 是那条链接的签名，去掉就打不开了。
所以这个测试**两个方向都钉**——该丢的丢掉，该留的必须留住。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.utils import canonicalize_url  # noqa: E402

# 左边这些形状**取自他生产库里真实存着的地址**，不是我编的。
DROPS = [
    ("https://www.bilibili.com/video/BV1oMgZ6EETu/?spm_id_from=333.1387.homepage.video_card.click",
     "https://www.bilibili.com/video/BV1oMgZ6EETu/"),
    ("https://www.douyin.com/video/7584040037701733683?source=Baiduspider-sdc",
     "https://www.douyin.com/video/7584040037701733683"),
    ("https://www.douyin.com/note/7669691260433370074?source=Baiduspider-sdc&x=1",
     "https://www.douyin.com/note/7669691260433370074"),
]


@pytest.mark.parametrize("raw,want", DROPS)
def test_埋点参数不进档案馆(raw: str, want: str) -> None:
    assert canonicalize_url(raw) == want, (
        "存进他档案馆的地址还拖着埋点尾巴——他导出到 Obsidian 的链接里就会有它，"
        "而且同一条内容会因为埋点不同存成两行。")


def test_小红书那个签名必须留住() -> None:
    """**反方向**：白名单写过头就会把能打开的链接改坏。"""
    got = canonicalize_url(
        "https://www.xiaohongshu.com/explore/abc?xsec_token=TOK&xsec_source=pc_feed&spm=x")
    assert "xsec_token=TOK" in got, "把 xsec_token 丢了——那条链接就打不开了"
    assert "xsec_source=pc_feed" in got
    assert "spm=" not in got, "spm 是埋点，该丢"


def test_两个只差埋点的地址收敛成同一条() -> None:
    """他库里那对重复（`BV1oMgZ6EETu` 两行）就是这么来的。"""
    a = canonicalize_url("https://www.bilibili.com/video/BV1oMgZ6EETu/?spm_id_from=333.1")
    b = canonicalize_url("https://www.bilibili.com/video/BV1oMgZ6EETu/?spm_id_from=999.9")
    assert a == b == "https://www.bilibili.com/video/BV1oMgZ6EETu/"


def test_没登记的站不许乱动它的参数() -> None:
    """**没查过的站不猜。** 只丢公认的那几个西方埋点，别的原样留着——
    替一个没读过的站决定"哪些参数属于身份"，猜错就把链接改坏了。"""
    got = canonicalize_url("https://example.com/a?utm_source=x&id=7&ref=abc")
    assert "id=7" in got and "ref=abc" in got, "没登记的站，参数不该被丢"
    assert "utm_source" not in got
