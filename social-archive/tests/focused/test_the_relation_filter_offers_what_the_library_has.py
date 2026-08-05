"""关系筛选写死了四个，而 Owner 最大的那一组不在里面（v0.0.0.7 / T15）。

## 实测出来的

2026-08-06 对着生产（193 条真实内容）逐个量：

    筛选里有的：  收藏 46   点赞 69   书签 **0**   稍后再看 1
    筛选里没有的：**观看历史 71**（193 条里的 37%，最大的一组）
                  保存 5     手动保存 2

**Owner 筛不出自己最大的那一堆**，而筛选里摆着一个 0 条的「书签」。

主题那个筛选早就是照 facet 重建的（`renderTopicOptions`），
**关系这个一直没跟上**——它是纯静态 HTML，没有任何代码去重建它，
服务端也从来没出过 relations 这个 facet。

## 补的是什么

服务端 facets 加 `relations`（和 platforms / topics 同一个查询形状）；
界面加 `renderRelationOptions()` 照它重建；index.html 里只留「全部关系」。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.focused.test_library_api import _library_client

ROOT = Path(__file__).resolve().parents[2]


def test_the_server_reports_which_relations_exist(tmp_path, monkeypatch) -> None:
    """**facet 要按真实数据出，而且带条数。**"""
    client = _library_client(tmp_path, monkeypatch)
    for index, relation in enumerate(("history", "history", "like")):
        response = client.post('/v1/captures', json={
            'platform': 'bilibili', 'url': f'https://b.test/{index}', 'title': f'第{index}条',
            'relation_type': relation, 'requested_levels': ['L0'],
        })
        assert response.status_code == 202, response.text

    facets = client.get('/v1/library').json()['facets']
    assert "relations" in facets, "**facets 里没有 relations**——界面就没法照数据重建那个筛选"
    counts = {row["relation"]: row["count"] for row in facets["relations"]}
    assert counts.get("history") == 2 and counts.get("like") == 1, counts


def test_the_filter_is_not_hard_coded_in_the_page() -> None:
    """**写死的会骗人。** index.html 里只许留「全部关系」。

    这条钉的是「别再写回去」：写死的那四个里有一个 0 条、
    而最大的一组不在其中——那份名单不是从数据来的，就必然和数据对不上。
    """
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    block = re.search(r'<select id="relationFilter">(.*?)</select>', html, re.S)
    assert block, "关系筛选找不到了——判据的射程失效，先修判据"
    values = re.findall(r'value="([^"]*)"', block.group(1))
    assert values == ["all"], f"关系筛选里又写死了选项：{values}"


def test_the_page_rebuilds_it_from_the_facet() -> None:
    """光删掉写死的还不够——得有人照数据把它填上。"""
    app = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert "function renderRelationOptions" in app, "没有重建关系筛选的函数"
    assert "state.facets.relations" in app, "重建时没有去读 relations 这个 facet"
    # **定义了不等于被调到。** 少了这条，把调用删掉判据照样绿。
    calls = len(re.findall(r"renderRelationOptions\(\)", app))
    assert calls >= 2, f"renderRelationOptions 只出现 {calls} 次——定义了却没人调"
