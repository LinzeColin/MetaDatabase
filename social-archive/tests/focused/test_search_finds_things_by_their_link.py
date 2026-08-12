"""搜索框承诺了「或链接」，而链接此前根本搜不到（v0.0.0.7 / T15）。

## 实测出来的

`apps/pwa/index.html` 那个搜索框写着：

    搜索标题、内容、关键词、作者或链接

而 `content_fts` 只索引 **title / author_name / body / tags**，**没有 url**。
2026-08-06 对着生产（193 条真实内容）量了一遍：

    bilibili     → 31 条   （标题里出现的那些）
    http         →  0 条
    com          →  0 条
    BV           →  0 条
    douyin       →  0 条

**这 193 条的链接里每一条都含 `http` 和 `com`。** 也就是说：粘一个网址进去
永远找不到东西，而界面明明白白承诺了能搜链接。

对一个档案馆来说，「我记得那个链接长什么样」恰恰是最常见的找法之一
（B 站的 BV 号、小红书的 note id 都在链接里）。

## 改法

给查询加一条 `c.canonical_url LIKE ?`，与 FTS 之间是 **OR**。
不动 FTS 的表结构——那要重建索引、动生产数据。

（第一版我写的是 `c.url`。**content 表里那一列叫 `canonical_url`**，
跑判据当场 `no such column: c.url`。列名是猜的，判据不是。）

## 这条判据走的是哪条路

`/v1/library` 走 `db.list_library_table`；`db.list_library` 是 `/v1/search`
那条**没有任何调用方**的旧接口。两处都改了，而**这条判据只覆盖前者**——
反例第一次没红就是因为我拿后者去改：改了一条谁也走不到的代码，判据当然不动。
（后者的那份留着是为了两处别再漂开，不是因为它被人用。）
"""

from __future__ import annotations

from tests.focused.test_library_api import _library_client


def _capture(client, url: str, title: str):
    response = client.post('/v1/captures', json={
        'platform': 'generic-web', 'url': url, 'title': title,
        'relation_type': 'manual_save', 'requested_levels': ['L0'],
    })
    assert response.status_code == 202, response.text
    return response.json()['content_id']


def test_a_url_fragment_finds_the_item(tmp_path, monkeypatch) -> None:
    """粘链接里的一段进去，要能找到那一条。"""
    client = _library_client(tmp_path, monkeypatch)
    wanted = _capture(client, 'https://www.bilibili.com/video/BV1zz411Q7Yg', '标题里完全没有那串号')
    _capture(client, 'https://example.test/other/thing', '另一条')

    for fragment in ("BV1zz411Q7Yg", "bilibili.com/video", "BV1zz"):
        found = client.get(f'/v1/library?q={fragment}').json()['items']
        assert [item['id'] for item in found] == [wanted], (
            f"用链接里的「{fragment}」找不到那一条——而搜索框写着「或链接」"
        )


def test_the_placeholder_still_promises_links(tmp_path, monkeypatch) -> None:
    """**判据和承诺得绑在一起。**

    哪天有人把「或链接」从搜索框里拿掉，上面那条就该跟着重新想一遍
    （而不是继续守着一个已经没人承诺的行为）。反过来更要紧：
    承诺还在，行为就必须在。
    """
    from pathlib import Path
    index = (Path(__file__).resolve().parents[2] / "apps/pwa/index.html").read_text(encoding="utf-8")
    assert "或链接" in index, (
        "搜索框不再承诺「链接」了——那么上面那条判据要重新想一遍："
        "是功能撤了，还是文案写漏了？"
    )


def test_searching_still_narrows_things_down(tmp_path, monkeypatch) -> None:
    """**别把「能搜链接」修成「什么都搜得到」。**

    加了 URL 那一路之后，一个不该命中的词仍然必须命中 0 条。
    少了这条，把查询整个短路成「永远为真」也能让上面那条绿。
    """
    client = _library_client(tmp_path, monkeypatch)
    _capture(client, 'https://www.bilibili.com/video/BV1zz411Q7Yg', '标题甲')
    assert client.get('/v1/library?q=zzzz-nothing-matches-this').json()['items'] == []
