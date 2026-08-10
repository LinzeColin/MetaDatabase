r"""抖音标题里的「互动数 + 文案 + 文案」要在显示前修掉（2026-08-10）。

## 他看到的是什么

Owner 打开 Obsidian，抖音那 86 条长这样：

    1029找卖萌办校园卡不后悔#校园卡找卖萌办校园卡不后悔#校园卡
    2456你的失望不仅莫名其妙还有点冒犯…你的失望不仅莫名其妙还有点冒犯…
    2.0万真正的一次性她来了真正的一次性她来了

生产实测 86 条：**54 条带互动数前缀，47 条文案整段重复两遍。**

## 只修能自证的那一档

去掉纯数字前缀之后，剩下的部分**左右两半完全相同**——这既修了重复，
也证明了那个数字是独立的一段。其余 39 条一个字都不碰。

**不动存下来的数据**，只在显示时修（改坏正文这个仓栽过两次）。
Markdown 导出与资料库那张表**用同一个函数**——两处各修各的必然漂开，
这个仓当天已经因为「同一件事两处不同答案」修过三回。

## 前缀不许用贪婪正则去猜

第一版写 `^\d+(?:\.\d+)?(?:万|w)?`，在

    9326岁 感谢命运 感谢爱 #狮子座 #happybirthday26岁 感谢命运 感谢爱 …

上把 `9326` 一起吃了（真前缀是 `93`，文案以 `26岁` 开头），那一条就漏了。
**这个 bug 是「先出提案后落盘」看出来的**——它当时躺在提案的「不改」那一列里。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.utils import clean_display_title  # noqa: E402


@pytest.mark.parametrize(("raw", "want"), [
    # 生产库里的真样本（2026-08-10 抽的）
    ("1029找卖萌办校园卡不后悔#校园卡找卖萌办校园卡不后悔#校园卡",
     "找卖萌办校园卡不后悔#校园卡"),
    ("2.0万真正的一次性她来了真正的一次性她来了", "真正的一次性她来了"),
    ("65you are，my salvation.#氛围感you are，my salvation.#氛围感",
     "you are，my salvation.#氛围感"),
    # ★ 贪婪正则漏掉的那一条：真前缀是 93，文案以 26岁 开头
    ("9326岁 感谢命运 感谢爱 #狮子座26岁 感谢命运 感谢爱 #狮子座",
     "26岁 感谢命运 感谢爱 #狮子座"),
    # 没有前缀、只有重复
    ("真正的一次性她来了真正的一次性她来了", "真正的一次性她来了"),
    # ★ 六个字的重复：门槛原来写 `half > 3`，把它漏了。
    #   全库量过：放到 >= 3 只多修这一条，不误伤别的。
    ("503小黑丝小黑丝", "小黑丝"),
])
def test_a_doubled_title_is_repaired(raw: str, want: str) -> None:
    assert clean_display_title(raw) == want


@pytest.mark.parametrize("raw", [
    # 本来就正常的，一个字都不许动（都是生产库里的真标题）
    "抖音精选电脑版 - 抖音旗下优质视频平台",
    "你什么时候会放弃一个亿#心理学 #成长充电站 @DOU+小助手",
    "雪山下的原始小村落，只有本地人才能开车进来，门票加坐车200块到底值不值得来 #旅行推荐官",
    "物主代词变动带动的动词变格#俄语变格 #俄语动词 #俄语学习材料#走遍俄罗斯 #俄语学习",
])
def test_a_normal_title_is_left_alone(raw: str) -> None:
    assert clean_display_title(raw) == raw


def test_short_repeats_are_not_mangled() -> None:
    """**别把正常的叠词当成重复。** 「哈哈」「加油加油」这种要留着。"""
    for raw in ("哈哈", "加油加油", "好好", "看看"):
        assert clean_display_title(raw) == raw


def test_both_surfaces_use_the_same_function() -> None:
    """两处各修各的必然漂开——这个仓当天已经栽过三回。"""
    for name in ("src/social_archive/destinations.py", "src/social_archive/db.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "clean_display_title" in text, (
            f"{name} 没有用那个共用函数——Markdown 与资料库会给出不同的标题")


@pytest.mark.parametrize("raw", ["646", "186", "6.6万", "4.4万", " 2.0万 "])
def test_a_title_that_is_only_a_count_becomes_empty(raw: str) -> None:
    """**整个标题就是一个互动数 = 文案根本没抓到。**

    他库里有 4 条这样的（646 / 186 / 6.6万 / 4.4万）。返回空字符串，
    让调用方落到已有的兜底上——用链接尾巴认人
    （`douyin.com/video/7669771030182253002`），比给他看一个 646 强。
    """
    assert clean_display_title(raw) == ""


def test_a_title_that_starts_with_a_count_but_has_text_is_kept() -> None:
    """**只有数字**才算没标题；数字后面还有字的不许当成空。"""
    assert clean_display_title("2.2万厂二代卖掉父亲的公司") == "2.2万厂二代卖掉父亲的公司"
