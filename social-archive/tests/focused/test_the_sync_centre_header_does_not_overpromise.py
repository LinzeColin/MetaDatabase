"""同步中心的抬头，不许承诺一件九个平台里八个做不到的事（v0.0.0.7 / T15）。

## 实测出来的

「账号同步中心」的抬头原话是：

    连接一次账号，自动全量导入收藏、点赞、书签和收藏夹；后续仅同步新增内容。

而 `account_sync.SYNCABLE_NOW` 里**只有 `generic-web` 一个**——
2026-08-06 对着生产问 `/v1/accounts`，九个平台里
`sync_supported` 为真的也只有它。Owner 已连的三个（B站/抖音/小红书）全是 False。

旁边那颗「同步全部账号」按钮**是诚实的**：它只数真的同步得动的，
一个都没有时会说「已连接的账号在本版本都还不能自动同步」。
**抬头没跟上。** 于是用户先读到一句承诺，按下去才知道做不到。

这和目的地那张面板的做法正相反——那里的抬头写着
「这里只显示真实连接状态。配置存在不等于连接成功。」

## 判据

只要还有平台不能自动同步，抬头就必须带上限定语。
限定语里点名的那个平台，必须真的在 `SYNCABLE_NOW` 里——
**不能一边写着「只有 X 能」，一边 X 自己也做不到**。
"""

from __future__ import annotations

import re
from pathlib import Path

from social_archive.account_sync import PLATFORM_RELATIONS, SYNCABLE_NOW

ROOT = Path(__file__).resolve().parents[2]


def _sync_centre_header() -> str:
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    block = re.search(r'id="syncModalTitle">.*?</p>', html, re.S)
    assert block, "同步中心的抬头找不到了——判据的射程失效，先修判据"
    return block.group(0)


def test_the_header_says_so_while_most_platforms_cannot_sync() -> None:
    cannot = sorted(set(PLATFORM_RELATIONS) - set(SYNCABLE_NOW))
    if not cannot:
        # 哪天全都接上了，这条判据自己会告诉你该改抬头了。
        return
    header = _sync_centre_header()
    assert "还没接上" in header or "还不能" in header, (
        f"**{len(cannot)}/{len(PLATFORM_RELATIONS)} 个平台还不能自动同步**"
        f"（{cannot}），而同步中心的抬头一句限定语都没有：\n  {header[:120]}"
    )


def test_the_platform_it_names_can_actually_sync() -> None:
    """**别一边写「只有 X 能」，一边 X 自己也做不到。**

    抬头点名了「Chrome 书签」，对应 SYNCABLE_NOW 里的 generic-web。
    这条把那句话和那张表绑在一起。
    """
    header = _sync_centre_header()
    if "Chrome 书签" in header:
        assert "generic-web" in SYNCABLE_NOW, (
            "抬头说只有 Chrome 书签能自动读取，而 generic-web 不在 SYNCABLE_NOW 里"
        )
