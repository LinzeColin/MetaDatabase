"""守住「保存当前页真的发出去了」这个演练（v0.0.0.7 / T08）。

扩展 25 种消息里 9 种没判据，其中 `SA_CAPTURE_ACTIVE` 是**产品最主要的动作**。
它此前只有源码层断言（「background.js 里有 captureActive」），
**没有任何东西验过按下去之后字节真的到了服务端**。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL = (ROOT / "scripts/extension_save_page_drill.py").read_text(encoding="utf-8")


def test_it_really_calls_the_product_function() -> None:
    """不是重写一遍逻辑，是**真调 captureActive**。

    重写一遍等于验我自己写的那份，产品坏了它照样绿。
    """
    assert "captureActive({ mode:" in DRILL, "没有真调那个函数"
    assert "Extensions.loadUnpacked" in DRILL, "没把扩展真装进浏览器"


def test_it_checks_what_was_sent_not_just_that_something_was() -> None:
    """**只看「有没有发」的话，发一个空壳也算过。**"""
    assert "title_made_it" in DRILL
    assert "PAGE_TITLE not in body_text" in DRILL, "没有核对发出去的是不是这一页"


def test_an_empty_inbox_is_a_failure_not_a_pass() -> None:
    """一个请求都没收到，和「发成功了」长得完全不同——必须红。"""
    assert "一个请求都没收到" in DRILL
    assert "if not received:" in DRILL


def test_it_never_touches_production_or_a_real_platform() -> None:
    assert "127.0.0.1" in DRILL
    for forbidden in ("linze-ovh", "/opt/social-archive", "bilibili.com", "youtube.com"):
        assert forbidden not in DRILL, f"演练里出现了它不该碰的东西：{forbidden}"


def test_it_leaves_nothing_behind() -> None:
    assert 'tempfile.mkdtemp(prefix="sa-save-profile-")' in DRILL, "没用一次性 profile"
    assert "shutil.rmtree(profile" in DRILL, "profile 没删"
    assert "server.shutdown()" in DRILL, "假服务器没关"


def test_it_says_what_it_does_not_prove() -> None:
    """假服务器不落库、不归档、不投递——**别让它冒充端到端验收**。"""
    assert "what_this_does_not_prove" in DRILL
    assert "不落库" in DRILL
