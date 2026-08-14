r"""资料库那张表里的作者，不能是点赞数（2026-08-10）。

## 怎么发现的

把 0.0.0.27 那个真镜像跑起来，按扩展的协议送一条抖音收藏进去，再读
`GET /v1/library`：

    标题  '真正的一次性她来了'      ← 已经修干净了
    作者  '26.6万'                  ← **还是点赞数**

同一天我给导出的 Markdown 接上了 `clean_display_author`，**却漏了这一侧**。
他打开资料库看到的就是「作者：26.6万」。

「同一件事两处各修各的，漏一处就等于没修」——这个仓当天为这个形状修过四回。

## 钉什么

`list_library_table` 出来的每一行：作者要么是能自证的真名，要么是空，
**不许是纯数字（含 `6.6万` / `4.4w` 这种）**。
只清能自证的那一档：`收藏`/`我的` 这种页面文字机器分不出，保持原样。
"""

from __future__ import annotations

import re

import pytest

from social_archive.models import CaptureRequest

COUNT = re.compile(r"^\d+(?:\.\d+)?(?:万|w)?$")


def _capture(service, title: str, author: str, external: str) -> None:
    service.capture(CaptureRequest(
        platform="douyin",
        url=f"https://www.douyin.com/video/{external}",
        external_content_id=external,
        relation_type="favorite",
        title=title,
        author_name=author,
    ))


def test_a_like_count_never_reaches_the_table_as_an_author(service, store) -> None:
    _capture(service, "2.0万真正的一次性她来了真正的一次性她来了", "26.6万", "769")
    rows = store.list_library_table(platform="douyin")["items"]
    assert rows, "一条都没进库，下面的断言就没意义"
    authors = [row.get("author_name") for row in rows]
    offenders = [a for a in authors if a and COUNT.match(str(a))]
    assert not offenders, (
        f"资料库那张表把点赞数当成了作者：{offenders}——他打开页面看到的就是这个")


def test_a_real_name_survives(service, store) -> None:
    _capture(service, "一条正常的", "雪瑜", "770")
    rows = store.list_library_table(platform="douyin")["items"]
    assert any(row.get("author_name") == "雪瑜" for row in rows), (
        f"真名被误清了：{[r.get('author_name') for r in rows]}")


@pytest.mark.parametrize("author", ["收藏", "我的"])
def test_page_furniture_is_left_alone(service, store, author: str) -> None:
    """**只清能自证的那一档。** 机器分不出「收藏」和「收藏家」，分不出就不动。"""
    _capture(service, "标题", author, f"77{len(author)}9")
    rows = store.list_library_table(platform="douyin")["items"]
    assert any(row.get("author_name") == author for row in rows), (
        f"把页面文字也清掉了，而它可能是真名的一部分：{[r.get('author_name') for r in rows]}")


def test_the_table_and_the_markdown_agree(service, store) -> None:
    """**两处必须同一个答案。** 漏一处就等于没修。"""
    from social_archive.utils import clean_display_author
    _capture(service, "标题", "26.6万", "7711")
    rows = store.list_library_table(platform="douyin")["items"]
    row = next(r for r in rows if r.get("external_content_id") == "7711")
    assert row.get("author_name") == (clean_display_author("26.6万") or None)
