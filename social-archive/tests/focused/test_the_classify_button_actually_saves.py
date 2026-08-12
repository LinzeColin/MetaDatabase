"""「批量修改分类」那颗按钮，按下去从来没成功过（v0.0.0.7 / T15）。

## 实测出来的

`apps/pwa/app.js` 的分类表单提交时打的是：

    POST /v1/library/classify

而 **api.py 里根本没有这条路由**。`/v1/library` 下只有
`GET /v1/library`、`GET /v1/library/{id}`、`POST /v1/library/{id}/export`、
`GET /v1/library/{id}/markdown` 四条。

2026-08-06 实测：这个请求回 **405 Method Not Allowed**。
用户选中若干条、填好主题、点「保存到 N 条内容」，得到的是一句英文报错。

**它是怎么被找到的**：上一条证据里我写了一句局限——「批量修改分类那条手动路没验」。
挂着不查就是留给下一个人踩，所以顺手查了。

## 补的是什么

存储层此前也没有「改已入库内容的分类」这个方法——分类只在 capture 那条路上写过。
所以补了三样：`RuntimeStore.reclassify_content`、`ClassifyRequest`、以及路由。

与 capture 那条路上的写入**故意不同**：那边是「有就覆盖、没有就保留」
（自动来的不该抹掉人填过的），**这里是人亲手填的，就照他说的写**，
包括把主题改回「未分类」；source 记 manual、confidence 记 1.0。
"""

from __future__ import annotations

from tests.focused.test_library_api import _library_client


def _capture(client, url: str, title: str) -> str:
    response = client.post('/v1/captures', json={
        'platform': 'generic-web', 'url': url, 'title': title,
        'relation_type': 'manual_save', 'requested_levels': ['L0'],
    })
    assert response.status_code == 202, response.text
    return response.json()['content_id']


def test_the_button_saves_and_the_library_shows_it(tmp_path, monkeypatch) -> None:
    """**整条路走通**：改完之后，资料库按那个主题筛得出来。"""
    client = _library_client(tmp_path, monkeypatch)
    first = _capture(client, 'https://example.test/a', '甲')
    second = _capture(client, 'https://example.test/b', '乙')

    saved = client.post('/v1/library/classify', json={
        'content_ids': [first, second], 'topic': 'AI与技术', 'keywords': ['Agent', '自动化'],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['updated'] == 2

    listed = client.get('/v1/library?topic=AI与技术').json()
    assert listed['total'] == 2, "改完分类之后按那个主题筛不出来"
    assert {item['topic'] for item in listed['items']} == {'AI与技术'}
    assert set(listed['items'][0]['keywords']) == {'Agent', '自动化'}


def test_ids_that_are_not_in_the_library_are_reported_not_swallowed(tmp_path, monkeypatch) -> None:
    """**点名了几条、真改了几条，要分开报。**

    选中的内容里若有已经不在库里的，报一句「都改好了」就是又一次「看着成了」。
    """
    client = _library_client(tmp_path, monkeypatch)
    real = _capture(client, 'https://example.test/a', '甲')

    response = client.post('/v1/library/classify', json={
        'content_ids': [real, 'nope-not-here'], 'topic': '学习研究', 'keywords': [],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['requested'] == 2 and body['updated'] == 1
    assert body['missing'] == ['nope-not-here']
    assert '另有 1 条不在库里' in body['message_zh']


def test_all_ids_missing_is_an_error_not_a_quiet_success(tmp_path, monkeypatch) -> None:
    """一条都没改到，就不能回 200。"""
    client = _library_client(tmp_path, monkeypatch)
    response = client.post('/v1/library/classify', json={
        'content_ids': ['nope'], 'topic': '生活方式', 'keywords': [],
    })
    assert response.status_code == 404, response.text


def test_a_person_can_set_it_back_to_unclassified(tmp_path, monkeypatch) -> None:
    """**人说改回「未分类」，就得真的改回去。**

    capture 那条路上的写法是「未分类不覆盖已有主题」——那对自动来的是对的，
    对人亲手填的是错的。少了这条判据，把这里也写成那种 CASE WHEN 就没人发现。
    """
    client = _library_client(tmp_path, monkeypatch)
    content_id = _capture(client, 'https://example.test/a', '甲')
    client.post('/v1/library/classify', json={
        'content_ids': [content_id], 'topic': '机械制造', 'keywords': ['CNC']})
    client.post('/v1/library/classify', json={
        'content_ids': [content_id], 'topic': '未分类', 'keywords': []})

    item = client.get('/v1/library').json()['items'][0]
    assert item['topic'] == '未分类', "人把它改回未分类，而它还挂着上一次的主题"
    assert item['keywords'] == [], "关键词也该跟着清掉"
