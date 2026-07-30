import importlib,os
from fastapi.testclient import TestClient

def test_api_capture_and_library(tmp_path,monkeypatch):
    root=tmp_path/'data';pwa=tmp_path/'pwa';pwa.mkdir();(pwa/'index.html').write_text('ok')
    monkeypatch.setenv('SOCIAL_ARCHIVE_DATA_ROOT',str(root));monkeypatch.setenv('SOCIAL_ARCHIVE_RUNTIME_DB',str(root/'db.sqlite'));monkeypatch.setenv('SOCIAL_ARCHIVE_STAGING_ROOT',str(root/'staging'));monkeypatch.setenv('SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT',str(root/'private'));monkeypatch.setenv('SOCIAL_ARCHIVE_WATCH_ROOT',str(root/'import'));monkeypatch.setenv('SOCIAL_ARCHIVE_PWA_ROOT',str(pwa))
    import social_archive.api as api;importlib.reload(api);client=TestClient(api.app)
    r=client.post('/v1/captures',json={'platform':'generic-web','url':'https://www.wikipedia.org/a','relation_type':'manual_save','requested_levels':['L0','L1']});assert r.status_code==202
    assert client.get('/v1/library').json()['items'][0]['title'] is None
