"""守住抓取演练本身（v0.0.0.7 / T08）。

演练脚本自己也会腐坏，而它腐坏的方式最阴：**永远 PASS**。
那比没有演练更坏——没有演练时人知道自己没验过。

这些判据守四件事：它必须能失败、它必须照抄诊断的顺序、
它必须真去读抓到的字节、它必须什么都不留下。
"""

from pathlib import Path

DRILL = (Path(__file__).resolve().parents[2] / "scripts/extension_capture_drill.py").read_text(
    encoding="utf-8"
)


def test_the_drill_can_fail() -> None:
    """反例：换一个绝不会出现的前缀，必须抓到 0 条。

    没有这一步的话，「抓到 8 条」既可能是前缀匹配对了，
    也可能是观察器把所有请求都抓了——两者看起来一模一样。
    """
    assert "绝不会出现的接口路径" in DRILL, "反例不见了——这个演练从此只会 PASS"
    assert 'counter.get("captures")' in DRILL, "反例抓到的条数没有被判据用上"


def test_the_drill_copies_the_diagnostic_order() -> None:
    """顺序是这条链最脆的地方，演练必须照抄，不能简化。

    先装观察器再装中继会丢掉 SA_OBSERVER_INSTALLED（观察器在 IIFE 末尾就发了它）；
    不刷新页面则新观察器会被幂等守卫直接挡回去，表现为「装好了、就绪了、什么也没有」。
    两者都是实测撞出来的，演练把顺序写错就再也测不到它们。
    """
    order = [DRILL.index(step) for step in (
        "chrome.tabs.reload", "content/net-relay.js", "net-observer.js", "SA_OBSERVER_CONFIGURE",
    )]
    assert order == sorted(order), "演练里的注入顺序和诊断按钮不一致，它测的就不是同一条链"


def test_the_drill_actually_reads_the_captured_bytes() -> None:
    """「拦到了」和「读得懂」是两件事。

    并且必须**解包**解析器的返回值——它返回 `(条目, 还有下一页)`，
    `len(整个返回值)` 永远等于 2，而 2 正是期望的条目数：条目为空也会绿。
    这个坑在写演练的当天就踩了一次。
    """
    assert "parse_bilibili_favlist" in DRILL, "演练没有去读抓到的字节，只数了条数"
    assert "len(parse_bilibili_favlist(" not in DRILL, (
        "又数成了两元组的长度——那永远是 2，抓到空条目也会绿"
    )
    assert "items, _has_more = parse_bilibili_favlist" in DRILL, "解析器的返回值没有解包"


def test_the_drill_leaves_nothing_behind() -> None:
    for cleanup, why in (
        ("shutil.rmtree(profile", "一次性 profile 没删"),
        ("process.terminate()", "测试用 Chrome 没关"),
        ("server.shutdown()", "本地假站没关，端口会一直被占着"),
    ):
        assert cleanup in DRILL, why


def test_the_drill_never_reaches_a_real_platform() -> None:
    """回环演练一旦真去连平台，它就不再是演练了。"""
    for forbidden in ("bilibili.com", "xiaohongshu.com", "douyin.com", "x.com"):
        assert forbidden not in DRILL, f"演练里出现了真实平台域名：{forbidden}"
    assert "127.0.0.1" in DRILL
