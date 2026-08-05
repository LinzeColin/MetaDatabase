"""守住「四张表接上了吗」这个演练本身（v0.0.0.7 / T06）。

它存在的理由：2026-08-05 接入 youtube 时我两次宣布「封住了」，两次都错，
**两次都是宣布完成之后才发现的**。一个平台散在四张表里，靠人对表总会漏一张。

## 这份判据自己也返修过一次

第一版全是 grep 源码：断言某句话在不在文件里。其中一条盯的是
「国内平台的 Cookie 必须永不出浏览器」——**而后来我给那段加注释时，
把这句话原样写进了注释**。于是那条判据变成：只要注释还在就绿，
整个分支删光也绿。今天已经在别处栽过好几次的同一种病。

所以现在判定被搬成了纯函数 `judge()`，下面这些判据**直接喂它一份假的
测量结果，看它红不红**。那是反例，不是 grep。
"""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts/extension_platform_wiring_drill.py"
DRILL = _PATH.read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("_wiring_drill", _PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
judge = _module.judge

DECOY = "https://mail.google.com/mail/u/0/"


def _measured(**overrides):
    """一份**四张表都接对了**的测量结果；每个反例只改坏其中一处。

    只改一处很重要：第一次写这些反例时我同时改了两处，
    结果 judge 报的是先撞上的那一处，而我以为验的是后一处。
    """
    base = dict(
        detected="youtube",
        permissionPatterns=["https://*.youtube.com/*"],
        label="YouTube",
        relations=["watch_later"],
        relationUrls=["https://www.youtube.com/playlist?list=WL"],
        custodyAllowed=True,
        custodyForbidden=False,
        decoyDetected=None,
    )
    base.update(overrides)
    return base


def test_a_correctly_wired_platform_passes() -> None:
    """先确认它**会绿**——一个永远报错的判据抓不出任何东西。"""
    assert judge(_measured(), "youtube", DECOY, "yes") == []


def test_it_asks_the_runtime_not_the_source_files() -> None:
    """对表的活儿判据已经做了；这个演练的价值在于**问真运行时**。

    它要是退回去读源码，就和已有判据重复，也就再抓不到「第三张表」那种漏。
    """
    assert "Extensions.loadUnpacked" in DRILL, "没有把扩展真的装进浏览器"
    assert "Runtime.evaluate" in DRILL, "没有在运行时里求值"
    assert "SAPlatformCatalog" in DRILL and "SACookieExport" in DRILL, (
        "没有同时问目录与 Cookie 导出——那正是漏掉的第三张表所在"
    )


def test_it_catches_a_label_that_fell_back_to_the_internal_id() -> None:
    """**中文名退回内部 id，正是第三张表缺席时的症状。**

    youtube 当时就是这样：shared.js 里有了，platform-catalog 里没有，
    platformLabel 原样返回「youtube」，而界面上多处直接显示它。
    """
    problems = judge(_measured(label="youtube"), "youtube", DECOY, "yes")
    assert any("退回了内部 id" in p for p in problems), problems
    assert judge(_measured(label=None), "youtube", DECOY, "yes"), "连空的都放过去了"


def test_domestic_cookies_in_the_allowlist_is_caught() -> None:
    """**这是硬边界：国内平台的 Cookie 永不出浏览器。**

    错的方向只有一个方向验得到——只验「该托管的在不在白名单」的话，
    「国内平台混进白名单」这种最严重的错反而抓不到。
    """
    problems = judge(_measured(detected="bilibili", custodyAllowed=True, custodyForbidden=True),
                     "bilibili", DECOY, "forbidden")
    assert any("不该能托管 Cookie" in p for p in problems), problems

    missing = judge(_measured(detected="bilibili", custodyAllowed=False, custodyForbidden=False),
                    "bilibili", DECOY, "forbidden")
    assert any("永不出浏览器" in p for p in missing), missing


def test_custody_has_three_states_not_two() -> None:
    """**「还没做」不等于「禁止」。**

    第一版只有 yes/no，于是 reddit 被判 FAIL，理由还是
    「国内平台的 Cookie 必须永不出浏览器」——reddit 根本不是国内平台。
    演练指错原因，比不报还糟：会让人去改一个没坏的东西。
    """
    # reddit：两张表都没有它，这是对的，不该报错。
    assert judge(_measured(detected="reddit", custodyAllowed=False, custodyForbidden=False),
                 "reddit", DECOY, "not-yet") == []

    # 而「还没做」却被塞进禁止名单，是拿硬边界那张表表达别的意思。
    misused = judge(_measured(detected="reddit", custodyAllowed=False, custodyForbidden=True),
                    "reddit", DECOY, "not-yet")
    assert any("别用它表达" in p for p in misused), misused

    # 三种状态必须都能表达；少一种就退回到「拿禁止名单当待办清单」。
    assert '"yes", "forbidden", "not-yet"' in DRILL, "命令行没有把三种状态开出来"


def test_it_checks_for_misdetection() -> None:
    """误伤检查：一个不该被认成这个平台的地址。

    youtube 要 google.com 的权限，而 Gmail 绝不能被认成 YouTube——
    「要这个域的权限」与「按这个域认平台」是两件事。
    """
    problems = judge(_measured(decoyDetected="youtube"), "youtube", DECOY, "yes")
    assert any("误伤" in p for p in problems), problems


def test_it_catches_a_relation_with_no_real_url() -> None:
    """目录里声明了关系类型，却没有能打开的地址——等于界面上一个死按钮。"""
    assert judge(_measured(relationUrls=[None]), "youtube", DECOY, "yes"), "关系没地址也放过"
    assert judge(_measured(relations=[], relationUrls=[]), "youtube", DECOY, "yes"), "没关系也放过"


def test_it_leaves_nothing_behind_and_never_touches_production() -> None:
    assert "tempfile.mkdtemp(prefix=\"sa-wiring-profile-\")" in DRILL, "没用一次性 profile"
    assert "shutil.rmtree(profile" in DRILL, "profile 没删"
    assert "process.terminate()" in DRILL, "测试用 Chrome 没关"
    for forbidden in ("linze-ovh", "/opt/social-archive", "social-archive.linzezhang.com"):
        assert forbidden not in DRILL, f"演练里出现了生产的东西：{forbidden}"


def test_it_can_also_check_the_options_page_card() -> None:
    """**service worker 那四张表全绿，设置页仍可能没有那张卡。**

    2026-08-05 就是这样：youtube 在检测/权限/中文名/关系地址四处都接上了，
    这个演练全绿，而 `options.js` 的 platformOrder 里一个 youtube 都没有——
    设置页不出卡片，「连接账号」按钮不存在，交接里让 Owner 做的第二件事做不了。

    service worker 看不见设置页（另一个文件、另一个执行环境），
    所以必须真把 options.html 开起来数卡片。
    """
    assert "--expect-connect-card" in DRILL, "没有能力去核那张卡"
    assert "options.html" in DRILL, "没有真去打开设置页"
    assert "account-card" in DRILL, "没有真去数卡片"
    assert "没有卡就没有" in DRILL, "卡片缺席时没有把后果说出来"


def test_the_card_check_looks_for_a_connect_button_not_just_the_card() -> None:
    """卡片在、按钮不在，一样点不动——两件事都要看。"""
    assert '"连接" in text for text in card.get("buttons"' in DRILL, (
        "只看了卡片在不在，没看上面有没有连接按钮"
    )
