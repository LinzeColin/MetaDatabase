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


def _painter() -> str:
    """app.js 里现算那句话的那一段。"""
    app = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    code = "\n".join(l for l in app.splitlines() if not l.lstrip().startswith("//"))
    assert "function paintSyncModalCopy" in code, (
        "找不到现算同步中心正文的那个函数——判据的射程失效，先修判据"
    )
    body = code.split("function paintSyncModalCopy", 1)[1]
    return body[: body.index("function openSyncModal")]


def test_the_header_is_not_a_second_capability_list() -> None:
    """**这句话必须现算，不能写死在 HTML 里。**

    v0.0.0.22 之前它是硬编码的：「本版本**只有 Chrome 书签**能自动读取；
    其余平台的自动读取还没接上」。写下时是对的，v0.0.0.21 起就成了假话
    （那时已经 5 个平台能同步，现在 7 个），而**他打开这个弹窗第一眼看到的就是它**。

    原来这条判据只要求抬头里带一句限定语——硬编码那句**带着限定语**，
    所以它一直是绿的。限定语不是重点，**名单会不会跟着能力声明走**才是。
    """
    header = _sync_centre_header()
    for hardcoded in ("Chrome 书签", "小红书", "抖音", "B站", "快手", "Reddit", "Instagram"):
        assert hardcoded not in header, (
            f"同步中心的抬头里又写死了平台名「{hardcoded}」：{header[:140]}\n"
            "——它会在下一次加平台时开始骗人。改成从 state.platformSupport 现算"
        )
    assert "state.platformSupport" in _painter(), (
        "那句话不是从能力声明现算的——它会再漂一次"
    )


def test_it_still_says_what_the_other_platforms_can_do() -> None:
    """能同步的说清楚之后，**剩下那些也要给一句现在能做什么**。

    只列"能自动同步的是 A、B、C"，他会以为别的平台这个软件不管。
    """
    cannot = sorted(set(PLATFORM_RELATIONS) - set(SYNCABLE_NOW))
    if not cannot:
        # 哪天全都接上了，这条判据自己会告诉你该改这句话了。
        return
    painter = _painter()
    assert "一条条保存" in painter or "逐条保存" in painter, (
        f"**{len(cannot)}/{len(PLATFORM_RELATIONS)} 个平台还不能自动同步**（{cannot}），"
        "而现算的那句话没告诉他这些平台现在能做什么"
    )


def test_the_names_it_prints_come_from_the_capability_declaration() -> None:
    """**别一边写「能自动同步的是 X」，一边 X 自己做不到。**

    现算之后这条不再靠人核对：名单是从 sync_supported 过滤出来的，
    而 sync_supported 来自服务端的 SYNCABLE_NOW。这条钉住那条过滤仍在。
    """
    painter = _painter()
    assert "sync_supported" in painter, (
        "名单不是按 sync_supported 过滤的——那它随时可能列出一个同步不了的平台"
    )
