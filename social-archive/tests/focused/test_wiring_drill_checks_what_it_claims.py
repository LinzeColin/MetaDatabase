"""守住「四张表接上了吗」这个演练本身（v0.0.0.7 / T06）。

它存在的理由：2026-08-05 接入 youtube 时我两次宣布「封住了」，两次都错，
**两次都是宣布完成之后才发现的**。一个平台散在四张表里，靠人对表总会漏一张。

所以这些判据钉的是：它必须真去问运行时、必须能失败、必须两个方向都验
（该能托管的 / 该不能托管的）、并且跑完什么都不留下。
"""

from pathlib import Path

DRILL = (Path(__file__).resolve().parents[2]
         / "scripts/extension_platform_wiring_drill.py").read_text(encoding="utf-8")


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
    assert 'measured["label"] == platform' in DRILL, (
        "不检查中文名是否退回内部 id——那种漏它就抓不到"
    )


def test_it_verifies_both_directions_of_custody() -> None:
    """该能托管的要在白名单里，该不能的要在禁止名单里。

    只验一个方向的话，「国内平台的 Cookie 混进白名单」这种最严重的错
    反而抓不到——那是条硬边界。
    """
    assert "--expect-custody" in DRILL, "不能表达「这个平台不该托管」"
    assert "它不该能托管 Cookie" in DRILL, "反方向没有断言"
    assert "国内平台的 Cookie 必须永不出浏览器" in DRILL, "禁止名单那一侧没有断言"


def test_it_checks_for_misdetection() -> None:
    """误伤检查：一个不该被认成这个平台的地址。

    youtube 要 google.com 的权限，而 Gmail 绝不能被认成 YouTube——
    「要这个域的权限」与「按这个域认平台」是两件事。
    """
    assert "decoyUrl" in DRILL and "误伤" in DRILL, "没有反例地址，认错了也发现不了"


def test_it_leaves_nothing_behind_and_never_touches_production() -> None:
    assert "tempfile.mkdtemp(prefix=\"sa-wiring-profile-\")" in DRILL, "没用一次性 profile"
    assert "shutil.rmtree(profile" in DRILL, "profile 没删"
    assert "process.terminate()" in DRILL, "测试用 Chrome 没关"
    for forbidden in ("linze-ovh", "/opt/social-archive", "social-archive.linzezhang.com"):
        assert forbidden not in DRILL, f"演练里出现了生产的东西：{forbidden}"
