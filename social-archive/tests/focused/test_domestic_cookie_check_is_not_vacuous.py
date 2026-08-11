"""「国内平台 Cookie 有没有到过服务器」那条检查，喂它坏形状必须变红（2026-08-07）。

说明书里最重的那一句：

    国内平台（B站、小红书、抖音、快手）的登录信息**永远不离开浏览器**，
    这一条是写死在代码里的。

仓里为 INV-DOMESTIC-COOKIE-STAYS 立过好几道门——**全在扫代码**。
代码对不对，和他那台服务器上此刻有没有，是两个问题。今天第一次去他生产库
真数：`platform_credential` **0 行**，承诺成立。

一条永远说 PASS 的检查等于没有，所以这里逐条证明它会红。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_no_domestic_cookie_reached_the_server.py"

_spec = importlib.util.spec_from_file_location("_domestic_cookie_check", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_domestic_cookie_check"] = _module
_spec.loader.exec_module(_module)
judge = _module.judge


def test_an_empty_table_is_the_promise_holding() -> None:
    """**正例必须是绿的**——他生产上现在就是这个形状（0 行）。"""
    problems, measured = judge([], table_seen=True)
    assert problems == [], problems
    assert measured["domestic_rows"] == 0
    assert set(measured["domestic_platforms"]) == {"xiaohongshu", "douyin", "bilibili", "kuaishou"}


def test_one_domestic_row_is_a_failure() -> None:
    """一行就够——这条不变量没有「少量可以接受」。"""
    problems, measured = judge([{"platform": "xiaohongshu"}], table_seen=True)
    assert any("永远不离开浏览器" in p for p in problems), problems
    assert any("xiaohongshu" in p for p in problems), problems
    assert measured["domestic_rows"] == 1


def test_a_western_platform_row_is_not_a_violation() -> None:
    """**别把不相干的也拖下水。**

    西方三源的取数在服务端跑，托管它们的凭据是**有意的设计**，
    不是违规。混为一谈会让这道门被当成噪音绕过去。
    """
    problems, measured = judge([{"platform": "reddit"}, {"platform": "x"}], table_seen=True)
    assert problems == [], problems
    assert measured["credential_rows_total"] == 2
    assert measured["domestic_rows"] == 0


def test_case_does_not_help_you_slip_through() -> None:
    problems, _ = judge([{"platform": "BiliBili"}], table_seen=True)
    assert problems, "大小写换一下就绕过去了"


def test_an_unreadable_table_is_not_a_pass() -> None:
    """**读不到就是不知道，不知道不能读成「没有」。**

    空默认值吞掉「不知道」，这个仓栽过很多次；最坏的一次吞掉的是对照基准本身。
    """
    problems, measured = judge([], table_seen=False)
    assert any("读不到" in p for p in problems), problems
    assert measured["table_readable"] is False


def test_the_platform_list_comes_from_the_one_source() -> None:
    """清单不许抄——抄的那份会和 credentials.py 分家，而分家那天没人知道。"""
    from social_archive.credentials import DOMESTIC_PLATFORMS

    source = SCRIPT.read_text(encoding="utf-8")
    assert "from social_archive.credentials import DOMESTIC_PLATFORMS" in source
    for name in ("xiaohongshu", "douyin", "bilibili", "kuaishou"):
        assert f'"{name}"' not in source.split('"""', 2)[-1], (
            f"{name} 被写死在判据里了——清单要从 credentials.py 取")
    assert len(DOMESTIC_PLATFORMS) == 4


def test_the_guide_sentence_this_guards_still_exists() -> None:
    guide = (ROOT / "docs/使用说明.md").read_text(encoding="utf-8")
    assert "永远不离开浏览器" in guide, "说明书那句承诺被改了——这条判据也要跟着改"


def test_the_deploy_treats_it_as_a_gate_not_a_readout() -> None:
    """**判据要有调用方，而且要是对的那一档。**

    其余三条生产侧检查（同步实况／产品说的话／三份副本）都是播报，
    带着 `||` 兜住；这一条必须能让部署当场停下——它答的是
    「最硬的那条承诺破了没有」，不是「他那份数据长什么样」。
    """
    text = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert "check_no_domestic_cookie_reached_the_server.py" in text, "部署没调它"
    # **别只看那一行**：`|| fail` 在续行上，只取「下一行」会取到行尾那个反斜杠——
    # 我第一版就是这么写的，判据自己红了。看紧随其后的那一段。
    after = text.split("check_no_domestic_cookie_reached_the_server.py", 1)[1][:400]
    assert "|| fail" in after, (
        f"它被接成了播报而不是门：{after.splitlines()[:3]}——"
        "国内平台的 Cookie 出现在服务器上，应当拦住发布")
    assert "|| printf" not in after.split("|| fail", 1)[0], "它被 printf 兜住了"
    # **绕行口要在，而且要喊出来**：没法绕的硬闸会逼人去改判据，那更坏。
    assert "SA_ALLOW_DOMESTIC_CREDENTIAL_ON_SERVER" in text
    assert "⚠️" in text.split("SA_ALLOW_DOMESTIC_CREDENTIAL_ON_SERVER", 2)[2][:400]


def test_it_runs_before_anything_is_shipped() -> None:
    """生产库的这个状态和本次部署无关——**破了就不该接着发别的东西**。"""
    text = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    gate = text.index("check_no_domestic_cookie_reached_the_server.py")
    sync = text.index('step "2) 同步源码"')
    build = text.index('step "5) 构建并上线"')
    assert gate < sync < build, "这道硬闸排在同步／上线之后了"

