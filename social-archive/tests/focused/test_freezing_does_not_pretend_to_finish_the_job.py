"""固化写进去了，不等于同步就能用（v0.0.0.7 / T09 / T10）。

2026-08-05 实测：全仓只有 background.js 的 installNetObserverForTab 读那张
拦截前缀表，而**唯一的调用方是弹窗的诊断按钮**（diagnostic=true）——
那条路进门第一件事就是把读到的前缀整个覆盖掉，改用当前页域名推出来的。
没有任何地方以 diagnostic=false 调它。

也就是说：**今天固化一个前缀，不会改变任何可观察的行为。**

这不是缺陷，是 T10/T11 还没做。但**工具不能让人误以为做完了**——
「写进去了」和「能同步了」之间隔着一整格，而这个项目一整天都在修
「两头都对，中间没接上」。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_freeze_tool_says_nothing_consumes_the_prefix_yet() -> None:
    script = (ROOT / "scripts/freeze_intercept_prefix.py").read_text(encoding="utf-8")
    assert "还没有任何东西会去用它" in script, (
        "固化脚本的提醒把人引向「重打包、装上、跑一次同步」——"
        "而根本没有同步路径会用这个前缀，那句提醒会让人白忙一场"
    )
    assert "T10/T11" in script, "没有指明缺的是哪一格"


def test_the_claim_is_still_true_only_one_reader_and_it_is_diagnostic_only() -> None:
    """这条判据钉的是**上面那句话此刻仍然成立**。

    哪天有人把同步接上了，它会红——那时该做的是去改文案，而不是删判据。
    """
    readers = []
    for relative in ("apps/browser-extension/background.js",
                     "apps/browser-extension/popup.js",
                     "apps/browser-extension/options.js"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if "interceptPrefixes" in text:
            readers.append(relative)
    assert readers == ["apps/browser-extension/background.js"], (
        f"读那张前缀表的地方变了：{readers}——固化脚本与交接表里那句话要跟着改"
    )
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    assert "diagnostic: false" not in background and "diagnostic:false" not in background, (
        "有人开始以 diagnostic=false 调安装了——"
        "那说明同步真的要用这个前缀了，固化脚本的提醒和交接表都该更新"
    )
