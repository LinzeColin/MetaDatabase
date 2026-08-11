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
    """**要防的是"碰生产"，不是"起进程"。**

    这条原来把 `subprocess` 整个禁掉，当作"不碰真实环境"的代理。
    代价是这个演练**不能自己起 Chrome**——它要求人先手工开一个带调试端口的
    浏览器，否则只抛一句 `Connection refused`，看起来像它坏了。
    而它在 DRILLS.md 里归在"改到那条路时"跑：**跑不起来的那一刻，
    正是没人再管它的那一刻**。

    起一个临时 profile 的本地 Chrome 不是碰真实环境——其余每个演练都这么做。
    所以改成禁真正该禁的：生产主机、生产域名、ssh。
    """
    code = DRILL.read_text(encoding="utf-8")
    assert "不真的同步任何东西" in code and "不联网" in code, "边界没写清楚"
    for forbidden in ("social-archive-api.linzezhang.com", "social-archive.linzezhang.com",
                      "linze-ovh", "ssh ", "docker "):
        assert forbidden not in code, f"演练脚本里出现了 {forbidden}——它不该碰真实环境"
    if "subprocess" in code:
        # 允许起 Chrome，但**必须是一次性的 profile**：用他日常那个
        # profile 跑演练会动到他真实的扩展、登录态和书签。
        assert "--user-data-dir" in code, "起了进程却没给一次性 profile"
        assert "tempfile" in code, "profile 不是临时目录——会动到他日常那个"
        assert "shutil.rmtree" in code, "临时 profile 跑完没收掉"
