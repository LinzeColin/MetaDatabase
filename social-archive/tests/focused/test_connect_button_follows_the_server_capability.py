"""决定「给不给连接按钮」的界面，必须读服务端那个能力标志（2026-08-07）。

## 这次栽的样子

X / YouTube 在服务端是 `connect_supported: true`（它们走 Cookie 托管，
是非国内平台，不违反「国内平台 Cookie 不出浏览器」），background 里那条
连接路是通的，服务端下发的原因文案里还白纸黑字写着
**「点这张卡片上的『连接账号』」**——

**而连接面板对它们一颗按钮都不画。** 他会照着那句话去找，然后找不到。

真因：面板拿 `sync_supported` 当「连不连得上」用。而**不能自动同步 ≠
不能连接**——api.py 里那段注释早就写明了这件事，还写明了上一次是怎么栽的
（「把 x / instagram 移出 SYNCABLE_NOW 之后，界面顺手把它们的连接按钮也
一起藏了」）。**同一个坑，换了个界面又踩一次。**

## 为什么已有的门拦不住

`check_no_mechanism_is_unreachable.py` 查的是「每个 SA_* 消息有没有发送方」。
`SA_ACCOUNT_CONNECT` **有**发送方（那 7 个可同步的平台在发），所以它满意。
而 X / YouTube 永远走不到那里——**门看的是消息，不是平台**。

「有某个界面读了这个字段」也拦不住：`options.js` 和 `app.js` 早就读了
`connect_supported`，**只有他真正用的那块面板没读**。

所以这条判据落在更细的地方：**凡是自己发起连接的界面，都必须读
`connect_supported`**。演练那一侧还有一条端到端的对账
（服务端说能连的平台数 vs 面板画出的按钮数），两条一起守。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "apps/browser-extension"


def _files_that_start_a_connection() -> list[Path]:
    """自己发起连接的界面——**不是「提到连接」的界面**。

    判据是「发出 SA_ACCOUNT_CONNECT」：那是真的在替用户按下去。
    background.js 是接收方不是发起方，排除掉。
    """
    found = []
    for path in sorted(UI.glob("*.js")):
        if path.name == "background.js":
            continue
        text = path.read_text(encoding="utf-8")
        if 'type: "SA_ACCOUNT_CONNECT"' in text or "'SA_ACCOUNT_CONNECT'" in text:
            found.append(path)
    return found


def test_there_are_such_files() -> None:
    """**先证明这条判据看得见东西。** 数到 0 个界面的判据永远是绿的。"""
    found = _files_that_start_a_connection()
    assert found, "一个发起连接的界面都没数到——这条判据瞎了"
    assert any(p.name == "connect-frame.js" for p in found), (
        "连接面板不在名单里——而它正是 Owner 真正会点的那一块")


def test_each_reads_the_server_capability_flag() -> None:
    for path in _files_that_start_a_connection():
        text = path.read_text(encoding="utf-8")
        assert "connect_supported" in text, (
            f"**{path.name} 自己发起连接，却不读 `connect_supported`。**\n"
            "它多半在拿 `sync_supported` 当「连不连得上」用——"
            "而不能自动同步 ≠ 不能连接（X / YouTube 走 Cookie 托管）。\n"
            "后果：服务端说能连、文案叫他点，而界面一颗按钮都不画。")


def test_the_server_still_advertises_it_separately() -> None:
    """**两边都要在。** 服务端哪天不再下发这个标志，上面那条就成了空判据。

    这正是「判据绿了但指错了文件」那一类的反面：判据看的字段消失了，
    它不会红，它会**永远绿**。
    """
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert '"connect_supported"' in api, "服务端不再下发 connect_supported 了"
    assert "CUSTODIAL_PLATFORMS" in api, (
        "connect_supported 不再看托管平台表了——X / YouTube 会重新变成"
        "「连不了」，而它们其实连得上")
