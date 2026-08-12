r"""抓重了的标题要还原，而正当标题一个字都不许动（2026-08-12）。

夹具里的每一条都是**从生产库里原样抄出来的**，不是我编的——包括那两条
「看着像坏的、其实是好的」。我自己写的第一版判据就被它们中的一条骗过去：
`老布探险原创的…#老布探险` 开头结尾都是「老布探险」，按「结尾 4 个字和开头
一样就算重复」会被砍掉一截标签。真正重复的那些后一遍占 50%，它只占 6%。
"""

from __future__ import annotations

import pytest

from social_archive.models import CaptureRequest
from social_archive.title_repair import undouble_title

# 生产库原文（`select title from content`），抓重了的。
SCRAPED_TWICE = [
    ("23.0万极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd"
     "极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd",
     "极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd"),
    ("2.2万厂二代卖掉父亲的公司，未必是一代不如一代 "
     "厂二代卖掉父亲的公司，未必是一代不如一代",
     "厂二代卖掉父亲的公司，未必是一代不如一代"),
    ("9.1万一滴一滴刺痛我的心～ #梦的翅膀受了伤群舞来了#和平精英"
     "一滴一滴刺痛我的心～ #梦的翅膀受了伤群舞来了#和平精英",
     "一滴一滴刺痛我的心～ #梦的翅膀受了伤群舞来了#和平精英"),
    ("26.6万(｡･ω･｡)ﾉ(｡･ω･｡)ﾉ", "(｡･ω･｡)ﾉ"),
    ("26.1万谁敢点开这个bgm谁敢点开这个bgm", "谁敢点开这个bgm"),
    ("2.0万真正的一次性她来了真正的一次性她来了", "真正的一次性她来了"),
    ("1.2万依旧二选一 #丝袜推荐#微胖依旧二选一 #丝袜推荐#微胖", "依旧二选一 #丝袜推荐#微胖"),
    ("7.7万懵一天萌一天⌯罒 ᗜ 罒⌯ #手势舞懵一天萌一天⌯罒 ᗜ 罒⌯ #手势舞",
     "懵一天萌一天⌯罒 ᗜ 罒⌯ #手势舞"),
]

# 生产库原文，**是好标题**，一个字都不许动。
MUST_NOT_TOUCH = [
    # 以计数开头，但「14万亿」是他要说的话。按「以计数开头就砍」会剩下「亿巨额放水…」。
    "14万亿巨额放水+50万亿存款到期，微观体感寒冷，钱到底去哪了？",
    # 开头和结尾都是「老布探险」，那是标签不是重复——我第一版判据栽在这条上。
    "老布探险原创的烈马等高线皮肤，私人订制将是老布探险的优势之一😁"
    " #烈马bronco #越野改装 #汽车贴膜 #老布探险",
    # 纯计数，正文根本没抓到——这一条修不了（要他的抖音登录态），但也不许瞎改。
    "6.6万",
    "4.4万",
]


@pytest.mark.parametrize(("stored", "real"), SCRAPED_TWICE)
def test_the_second_copy_and_the_view_count_both_come_off(stored: str, real: str) -> None:
    assert undouble_title(stored) == real


@pytest.mark.parametrize("title", MUST_NOT_TOUCH)
def test_a_real_title_survives_untouched(title: str) -> None:
    assert undouble_title(title) == title


def test_the_fixtures_are_not_all_the_same_shape() -> None:
    """防空转：上面两组要是塌成同一种形状，两个测试就都是白跑的。

    坏的那组必须真的变短，好的那组必须真的没变——各自成立还不够，
    还得确认两组在同一把判据下走的是**不同**的分支。
    """
    assert all(len(undouble_title(bad)) < len(bad) for bad, _ in SCRAPED_TWICE)
    assert all(undouble_title(good) == good for good in MUST_NOT_TOUCH)
    # 好的那组里必须有以计数开头的，否则「先看重复再看前缀」这条顺序没被测到。
    assert any(t[0].isdigit() for t in MUST_NOT_TOUCH)


def test_the_repair_happens_at_the_door_not_only_in_the_database() -> None:
    """存量修好了不算完——下一次抖音同步会照原样再写一遍。

    所以判据要摆在 `CaptureRequest` 上：取数侧再送一次抓重的标题，
    进库之前就已经是真标题了。
    """
    stored, real = SCRAPED_TWICE[0]
    request = CaptureRequest(platform="douyin", url="https://www.douyin.com/video/7", title=stored)
    assert request.title == real


def test_the_other_title_gate_still_nulls_a_playback_timestamp() -> None:
    """两条 title 判据摆在一起，不许互相吃掉——`06:26/12:57` 仍然要被置空。"""
    request = CaptureRequest(platform="bilibili", url="https://www.bilibili.com/video/BV1",
                             title="06:26/12:57")
    assert request.title is None
