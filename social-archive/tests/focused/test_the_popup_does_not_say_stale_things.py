"""弹窗里那几句「哪些平台能同步」不许是写死的（v0.0.0.14）。

2026-08-06 **第一次在真 Chrome 里打开弹窗**（此前只有一个 Playwright 的假
popup harness），读回来三句话，其中一句是：

    小红书、抖音、B站、快手的收藏列表现在还读不了

**而 B 站已经读得了两个版本。** 那句话写死在 popup.html 里，
接上 B 站的时候没有任何东西提醒我去改它。

同一页上还有两处同样的毛病：
  · 「连接与管理账号」下面列着八个平台，像是八个都连得上
  · 手动保存被收在一个写着「备用」的折叠面板里——**而九个平台里七个
    只能靠它存东西**，那不是备用，那是唯一的路

三处现在都照服务端下发的 `supported_platforms` 现算。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POPUP_HTML = ROOT / "apps/browser-extension/popup.html"
POPUP_JS = ROOT / "apps/browser-extension/popup.js"


def _code(text: str) -> str:
    without_blocks = re.sub(r"(?m)^[ \t]*/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(line for line in without_blocks.splitlines()
                     if not line.lstrip().startswith("//"))


def test_the_popup_never_hardcodes_which_platforms_can_sync() -> None:
    """写死的那句话是怎么过期的：它提到了具体平台名。"""
    html = POPUP_HTML.read_text(encoding="utf-8")
    # 诊断面板那句话现在由 JS 填，HTML 里只留一个占位
    stale = re.search(r"小红书、抖音、B站、快手的收藏列表现在还读不了", html)
    assert stale is None, "**弹窗里还写死着「B站…读不了」**——它已经读得了"
    for marker in ("manageAccountsHint", "diagnoseWhy", "saveSummary"):
        assert marker in html, f"{marker} 没有挂上 id，JS 改不到它"


def test_the_popup_recomputes_that_copy_from_the_server() -> None:
    code = _code(POPUP_JS.read_text(encoding="utf-8"))
    assert "supported_platforms" in code, (
        "**弹窗把服务端下发的能力表扔掉了**——那几句话只能写死，然后过期"
    )
    assert "renderPlatformCopy" in code, "没有照能力表重写那几句话"
    # 读不到能力表时必须保持原样，不能把界面清成空白
    assert "if (!support.length) return;" in code, (
        "服务读不到时会把那几句话清空——宁可保持写死的那份，也不要一片空白"
    )


def test_manual_save_is_not_called_a_fallback() -> None:
    """九个平台里七个只能手动保存，那不是「备用」。"""
    html = POPUP_HTML.read_text(encoding="utf-8")
    assert "备用：保存当前页面" not in html, (
        "手动保存还叫「备用」——而七个平台只能靠它存东西"
    )
    assert 'id="savePage"' in html, "保存按钮不见了"


def test_the_save_panel_opens_when_it_is_the_only_way() -> None:
    """当前这一页不能自动同步时，保存面板要默认展开。

    ⚠️ **这条只验源码里那个分支存在且判据正确**，没有在浏览器里验开合。
    原因：弹窗读的是「当前活动标签页」，而演练把 popup.html 当成一个普通
    标签页打开，活动标签页就是它自己（普通网页、可同步），
    永远走不到那个分支。真实场景是他在小红书页面上点插件图标。
    """
    code = _code(POPUP_JS.read_text(encoding="utf-8"))
    assert "openSavePanelWhenItIsTheOnlyWay" in code
    assert "sync_supported === false" in code, (
        "展开条件不是「这个平台不能自动同步」——那它开合的依据就是别的东西"
    )
    assert "if (!support) return;" in code, (
        "能力表读不到时会凭猜改变界面——宁可保持原样"
    )


def test_it_tells_apart_never_connected_from_disconnected() -> None:
    """**「一个都没连过」和「连过、后来断了」是两回事。**

    2026-08-07 读生产才看清 Owner 的实况：三个账号躺在库里
    （小红书「我」/ 抖音「我的」/ B 站），全是 `disconnected`，
    而 8/3 那晚它们真的自动同步进来过 260 条。

    而弹窗对他说的是：

        还没有连接平台账号
        连接一次账号后自动全量导入，不需要逐条点击。
        [连接第一个账号]

    **三句里两句对他是假的**，而且把他唯一要做的那件事——重连一次——盖掉了。
    这和写死「B 站读不了」是同一族：**这一屏说的话不随他的状态走。**

    还要说一句东西都在：断开不清空内容（db.py「只断连接，不删内容」），
    而「未连接」很容易被读成「我的收藏没了」。
    """
    code = _code(POPUP_JS.read_text(encoding="utf-8"))
    assert "accounts.length > 0" in code or "everConnected" in code, (
        "弹窗没有区分「从没连过」和「连过后来断了」——"
        "他有三个断开的账号，却会被告知「还没有连接平台账号」")
    assert "重新连接账号" in code, (
        "断开状态下的主按钮还是「连接第一个账号」——**对他是假的**，"
        "而且把「重连一次就恢复」这条唯一要做的事盖掉了")
    assert "一条都没少" in code, (
        "没有说清内容还在。「未连接」很容易被读成「我的收藏没了」，"
        "而断开只是不再自动跑，一条都不删")
