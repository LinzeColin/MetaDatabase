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
    filtered = client.get('/v1/library?platform=generic-web&relation=bookmark').json()['items']
    # One card carries every relation it was saved under, so the row exposes a
    # de-duplicated `relations` list rather than a single `relation_type`.
    assert [item['id'] for item in filtered] == [content_id]
    assert 'bookmark' in filtered[0]['relations']
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
    # Same one-card-many-relations projection: `relations` and `collections`
    # replace the singular relation_type/collection_key on a library row.
    assert [item['id'] for item in filtered] == [content_id]
    assert 'bookmark' in filtered[0]['relations'] and 'research' in filtered[0]['collections']
    assert [item['id'] for item in client.get('/v1/library?q=research').json()['items']] == [content_id]

    observed_day = filtered[0]['last_observed_at'][:10]
    same_day_scope = client.get(
        f'/v1/library?platform=generic-web&relation=bookmark&collection=research&observed_from={observed_day}&observed_to={observed_day}'
    ).json()['items']
    assert [item['id'] for item in same_day_scope] == [content_id]
    assert client.get('/v1/library?observed_from=9999-01-01').json()['items'] == []
    assert client.get('/v1/library?observed_from=not-a-date').status_code == 422
