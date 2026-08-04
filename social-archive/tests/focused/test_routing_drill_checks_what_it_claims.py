"""那个真浏览器演练脚本，判据要盯住它自己（v0.0.0.7 / T14）。

演练脚本不进发布门（它要一台 Chrome），所以没人替它把关。
而**一个报 PASS 却什么都没验的演练，比没有演练更糟**——
这一天里已经撞过两次「报成功而事情没发生」：
恢复报 target_written 而目录是空的；systemd 报 success 而跑的是旧 unit。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "scripts/extension_routing_drill.py"


def _code() -> str:
    return "\n".join(
        line for line in DRILL.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_it_counts_all_three_exits_and_the_tabs() -> None:
    """只数「书签路走了没有」不够——还要证明**别的路一次都没走**。"""
    code = _code()
    for exit_name in ("syncChromeBookmarks", "startServerSideSync", "runBrowserAccountSync"):
        assert exit_name in code, f"没有给 {exit_name} 挂计数器"
    assert "chrome.tabs.update" in code, "没有数标签页被碰了几次——那正是 Owner 抱怨的那件事"


def test_it_fails_when_the_wrong_path_is_taken() -> None:
    """判据必须能红。只打印不判定的演练等于没有。"""
    code = _code()
    assert '"bookmarks": 1, "server": 0, "browser": 0, "tabs": 0' in code, "没有钉住期望的计数"
    assert 'if not measured["blockedError"]' in code, "同步不了的平台没被拒绝时不报错"
    assert 'return 0 if not problems else 4' in code, "无论结果都退 0——那样它永远 PASS"


def test_it_restores_everything_it_replaced() -> None:
    """替换了 service worker 里的函数，跑完必须放回去，否则那个浏览器实例就废了。"""
    code = _code()
    for restored in ("realBookmarks", "realServer", "realBrowser", "realUpdate", "realFetch"):
        assert code.count(restored) >= 2, f"{restored} 换了没换回来"


def test_it_does_not_touch_the_real_world() -> None:
    code = DRILL.read_text(encoding="utf-8")
    assert "不真的同步任何东西" in code and "不联网" in code, "边界没写清楚"
    for forbidden in ("social-archive-api.linzezhang.com", "linze-ovh", "subprocess"):
        assert forbidden not in code, f"演练脚本里出现了 {forbidden}——它不该碰真实环境"
