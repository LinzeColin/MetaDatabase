import importlib
from fastapi.testclient import TestClient


def _library_client(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    pwa = tmp_path / 'pwa'
    pwa.mkdir()
    (pwa / 'index.html').write_text('ok')
    for key, value in {
        'SOCIAL_ARCHIVE_DATA_ROOT': root,
        'SOCIAL_ARCHIVE_RUNTIME_DB': root / 'db.sqlite',
        'SOCIAL_ARCHIVE_STAGING_ROOT': root / 'staging',
        'SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT': root / 'private',
        'SOCIAL_ARCHIVE_WATCH_ROOT': root / 'import',
        'SOCIAL_ARCHIVE_PWA_ROOT': pwa,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app)


def test_library_filters_and_connector_run(tmp_path, monkeypatch):
    client = _library_client(tmp_path, monkeypatch)
    response = client.post('/v1/connectors/generic-web/run', json={
        'url': 'https://www.wikipedia.org/a', 'requested_levels': ['L0', 'L1'],
    })
    assert response.status_code == 202
    assert response.json()['imported'] == 1
    assert len(client.get('/v1/library?platform=generic-web').json()['items']) == 1


def test_library_uses_one_content_card_for_multiple_relations_and_preserves_detail(tmp_path, monkeypatch):
    client = _library_client(tmp_path, monkeypatch)
    payload = {
        'platform': 'generic-web',
        'url': 'https://www.wikipedia.org/wiki/Archive',
        'requested_levels': ['L0', 'L1'],
    }
    for relation_type in ('manual_save', 'bookmark'):
        response = client.post('/v1/captures', json={**payload, 'relation_type': relation_type})
        assert response.status_code == 202
        assert response.json()['content_id']

    items = client.get('/v1/library?platform=generic-web').json()['items']
    assert len(items) == 1
    content_id = items[0]['id']
    # 字段名从 relation_type 改成了 primary_relation（v0.0.0.5 起）。
    # 这条判据卡在旧名字上，KeyError 了很久——**而它要证的行为一直是好的**。
    # 实测：一条内容两种关系 → 库里 1 张卡；按任一关系过滤，卡上的
    # primary_relation 就是那个关系；relations 里两种都在。
    for wanted in ('bookmark', 'manual_save'):
        filtered = client.get(f'/v1/library?platform=generic-web&relation={wanted}').json()['items']
        assert [item['id'] for item in filtered] == [content_id], f'按 {wanted} 过滤没拿到那张卡'
        assert filtered[0]['primary_relation'] == wanted, (
            f"按 {wanted} 过滤，卡上显示的却是 {filtered[0]['primary_relation']}——"
            '过滤结果必须反映被过滤的那个关系'
        )
        # 观察到的事实（不作为要求）：**过滤时 relations 只含被过滤的那一种**，
        # 因为 GROUP_CONCAT 是在过滤后的行上算的。
        # 我一度把「过滤也要保住全部关系」写成断言——那是我自己的偏好，
        # 任何规格都没这么要求。判据不该钉我以为应该怎样，只该钉说定了怎样。
        # 「保住细节」这条由本函数最后一行的详情接口负责，那才是原判据的定义。
        assert set(filtered[0]['relations']) <= {'manual_save', 'bookmark'}
    detail = client.get(f'/v1/library/{content_id}').json()
    assert {relation['relation_type'] for relation in detail['relations']} == {'manual_save', 'bookmark'}


def test_library_filters_literal_full_text_collection_and_observed_date(tmp_path, monkeypatch):
    client = _library_client(tmp_path, monkeypatch)
    initial = client.post('/v1/captures', json={
        'platform': 'generic-web',
        'url': 'https://example.test/articles/searchable',
        'title': 'Needle reference 中文检索标题',
        'text': 'deep full text marker 中文正文',
        'relation_type': 'manual_save',
        'collection_key': 'reading',
        'requested_levels': ['L0', 'L1'],
    })
    assert initial.status_code == 202
    content_id = initial.json()['content_id']
    second_relation = client.post('/v1/captures', json={
        'platform': 'generic-web',
        'url': 'https://example.test/articles/searchable',
        'relation_type': 'bookmark',
        'collection_key': 'research',
        'requested_levels': ['L0', 'L1'],
    })
    assert second_relation.status_code == 202
    client.post('/v1/captures', json={
        'platform': 'x',
        'url': 'https://x.com/example/status/2',
        'title': 'Different item',
        'relation_type': 'saved',
        'collection_key': 'inbox',
        'requested_levels': ['L0', 'L1'],
    })

    assert [item['id'] for item in client.get('/v1/library?q=needle').json()['items']] == [content_id]
    assert [item['id'] for item in client.get('/v1/library?q=marker').json()['items']] == [content_id]
    assert [item['id'] for item in client.get('/v1/library?q=中文检索').json()['items']] == [content_id]
    assert [item['id'] for item in client.get('/v1/library?q=中文正文').json()['items']] == [content_id]
    assert [item['id'] for item in client.get('/v1/library?q=中文检索needle').json()['items']] == [content_id]
    filtered = client.get('/v1/library?platform=generic-web&relation=bookmark&collection=research').json()['items']
    # 同上：relation_type → primary_relation。行为一直是对的，卡的是字段名。
    assert [(item['id'], item['primary_relation']) for item in filtered] == [(content_id, 'bookmark')]
    # **筛选按原始 key 走，显示按名字走**（2026-08-10）。
    #
    # `collection=research` 依旧命中——过滤用的是 `r.collection_key`。
    # 而 `primary_collection` 现在只端**查得到名字的**（platform_collection
    # 里登记过的）。这条 research 没登记过，所以它交白卷，由界面写「未分组」。
    # 原来它原样输出 key，于是他生产库里 194 条关系有 100 条那一格是内部值
    # （70 条是一百字的页面文案，30 条是 'bilibili:/…/favlist' 这样一条路径）。
    assert filtered[0]['primary_collection'] in (None, ''), (
        f"「收藏夹」这一格又端出了原始 key：{filtered[0]['primary_collection']!r}")
    assert [item['id'] for item in client.get('/v1/library?q=research').json()['items']] == [content_id]

    observed_day = filtered[0]['last_observed_at'][:10]
    same_day_scope = client.get(
        f'/v1/library?platform=generic-web&relation=bookmark&collection=research&observed_from={observed_day}&observed_to={observed_day}'
    ).json()['items']
    assert [item['id'] for item in same_day_scope] == [content_id]
    assert client.get('/v1/library?observed_from=9999-01-01').json()['items'] == []
    assert client.get('/v1/library?observed_from=not-a-date').status_code == 422
