"""筛不出任何东西的下拉框，就不该摆在那儿（2026-08-10）。

## 规则本来就有，只是只落在一处

`renderCollectionOptions` 里写得很清楚：

    藏起来是有意的：绝大多数平台本来就没有收藏夹的概念，永远显示一个
    只有「全部收藏夹」一项的下拉框，是在界面上摆一个点了没用的东西。

**而「主题分类」那一栏没跟上。** 2026-08-10 去生产库里数：

    content_classification 190 条，`topic` **全部是「未分类」**

于是他打开资料库看到的是一个两项的下拉框——「全部主题」和「未分类」，
两项选出来是同一批 190 条。这一栏此前已经骗过他一次：index.html 里写死过
五个主题（AI与技术/商业与投资/机械制造/学习研究/生活方式），
**各返回 0 条**，而真实唯一的「未分类」不在名单里。

一个选项分不出两堆东西。少于两个可选值就藏起来——和收藏夹同一条规矩。

**真的渲染出来是 `pwa_render_drill.py` 验的**（夹具里 topics 就是生产那个
形状：只有「未分类」一个）。这里钉的是规则本身别再只落一半。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"
INDEX = ROOT / "apps/pwa/index.html"

pytestmark = pytest.mark.skipif(not APP.is_file(), reason="app.js 不存在")


def _fn(name: str) -> str:
    text = APP.read_text(encoding="utf-8")
    start = text.index(f"function {name}(")
    return text[start:start + 1200]


def test_the_collection_filter_still_hides_itself_when_useless() -> None:
    """**正例先立住**：这条规矩本来就在收藏夹那一栏上。"""
    body = _fn("renderCollectionOptions")
    assert "collectionField" in body and "hidden" in body, body[:300]


def test_the_topic_filter_hides_itself_too() -> None:
    """同一条规矩，另一栏。"""
    body = _fn("renderTopicOptions")
    assert "topicField" in body, (
        "「主题分类」那一栏没有可藏的容器——他库里 190 条主题全是「未分类」，"
        "那个下拉框两项选出来是同一批东西")
    assert "hidden" in body, (
        "renderTopicOptions 里没有把那一栏藏起来的分支")


def test_the_topic_field_has_something_to_hide() -> None:
    """**容器得真的存在**，不然上一条判据是在对一个拼错的 id 说话。"""
    assert 'id="topicField"' in INDEX.read_text(encoding="utf-8"), (
        "index.html 里没有 topicField 这个容器——app.js 藏的是一个不存在的东西")


def test_the_boundary_is_stated_not_quietly_widened() -> None:
    """**说清这条规矩现在管到哪儿。**

    只管「主题」和「收藏夹」两栏，因为它们是**量出来的**：
    生产上 topic 190 条全是「未分类」，collections 分面是空的。

    关系／归档状态／时间范围三栏**没有纳入**：他库里关系有 6 种、归档状态有
    2 种，都真的分得出东西；时间范围是固定档位。把规矩顺手推广到它们身上，
    就是拿一个没量过的假设去改他天天在用的导航——这个仓在「样例撑不起全称
    判断」上栽过。哪天真出现「只剩一种关系」，再拿那时的数据来说话。
    """
    body = _fn("renderRelationOptions")
    assert "relationField" not in body, (
        "关系那一栏也被纳入了这条规矩——那需要先量：他库里到底有几种关系。"
        "现在是 6 种，规矩用不上；要改就先拿数据说话")


def test_one_option_is_not_a_filter() -> None:
    """判据要认的是「少于两个」，不是「一个都没有」。

    只有「未分类」一项时，下拉框仍旧是摆设——他点哪一项都是同一批 190 条。
    """
    body = _fn("renderTopicOptions")
    assert ("length < 2" in body or "length <= 1" in body), (
        f"藏的条件不是「少于两个可选值」：{body[:400]}——"
        "只有一个主题时那个框照样是摆设")
