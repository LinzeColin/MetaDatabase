r"""从零到能用，整条链走一遍——走 HTTP，不是只调函数（2026-08-10）。

Owner：「从零测试能不能用，你自己先测试一下」。

我在**真镜像**上跑通了这条链（空库 → 连接 → 同步 → 有内容 → 删除 → 清空
→ 重连 → 再同步）。这条判据把它固化下来，走的是真路由：

    POST /v1/accounts/connect/start
    POST /v1/accounts/connect/{platform}/complete
    POST /v1/sync-runs/{id}/batches
    GET  /v1/library
    POST /v1/accounts/{id}/forget

★ 写那个真机脚本时我第一版把完成连接的地址写成了
`/v1/accounts/douyin/complete`（少了 `connect/`），整段静默走空。
**只测函数是发现不了这个的**——所以这条判据必须打路由。
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

TOKEN = "zero-drill-token"


def _client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
        "SOCIAL_ARCHIVE_API_TOKEN": TOKEN,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api
    importlib.reload(api)
    return TestClient(api.app)


HEAD = {"Authorization": f"Bearer {TOKEN}"}


def _connect(client, platform: str = "douyin") -> dict:
    started = client.post("/v1/accounts/connect/start", headers=HEAD,
                          json={"platform": platform, "auth_method": "browser_session"})
    assert started.status_code in (200, 202), started.text
    done = client.post(f"/v1/accounts/connect/{platform}/complete", headers=HEAD, json={
        "connection_ref": started.json()["connection_ref"],
        "external_account_id": "owner", "display_name": "抖音", "verified": True,
        "metadata": {"auth_method": "browser_session"}})
    assert done.status_code == 201, done.text
    return done.json()


def _terminal_batch(client, run_id: str, *, external: str = "769") -> dict:
    got = client.post(f"/v1/sync-runs/{run_id}/batches", headers=HEAD, json={
        "relation_type": "favorite", "scope_type": "relation",
        "completeness": "complete", "has_more": False,
        "items": [{"platform": "douyin",
                   "url": f"https://www.douyin.com/video/{external}",
                   "external_content_id": external, "relation_type": "favorite",
                   "title": "2.0万真正的一次性她来了真正的一次性她来了",
                   "author_name": "26.6万"}]})
    assert got.status_code == 202, got.text
    return got.json()


def test_the_whole_chain_from_an_empty_archive(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    assert client.get("/v1/library", headers=HEAD).json()["total"] == 0, "起点不是空的"

    connected = _connect(client)
    run_id = connected["first_sync"]["sync_run_id"]
    assert connected["state"] == "connected", connected

    batch = _terminal_batch(client, run_id)
    assert batch["status"] == "completed", (
        f"送完收藏的终批之后 run 还是 {batch['status']}——他会看到圈一直转")

    run = client.get(f"/v1/sync-runs/{run_id}", headers=HEAD).json()
    assert run["imported_count"] == 1, (
        f"界面会说「已导入 {run['imported_count']} 条」，而实际进了 1 条")

    library = client.get("/v1/library", headers=HEAD).json()
    assert library["total"] == 1, library
    item = library["items"][0]
    assert item["title"] == "真正的一次性她来了", item["title"]
    assert not item.get("author_name"), f"点赞数当成了作者：{item.get('author_name')}"

    forgotten = client.post(f"/v1/accounts/{connected['account_id']}/forget", headers=HEAD)
    assert forgotten.status_code == 200, forgotten.text
    assert forgotten.json()["removed_content"] == 1, forgotten.json()

    assert client.get("/v1/library", headers=HEAD).json()["total"] == 0, "没删干净"

    again = _connect(client)
    batch_again = _terminal_batch(client, again["first_sync"]["sync_run_id"])
    assert batch_again["status"] == "completed", "删完重连之后同步跑不完了"
    assert client.get("/v1/library", headers=HEAD).json()["total"] == 1, "重新同步没把内容带回来"


def test_forgetting_an_unknown_account_is_404(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    assert client.post("/v1/accounts/acct_nope/forget", headers=HEAD).status_code == 404


def test_the_complete_route_really_needs_the_connect_prefix(tmp_path, monkeypatch) -> None:
    """★ 我第一版把它写成 `/v1/accounts/douyin/complete`，整段静默走空。"""
    client = _client(tmp_path, monkeypatch)
    assert client.post("/v1/accounts/douyin/complete", headers=HEAD, json={}).status_code == 404
