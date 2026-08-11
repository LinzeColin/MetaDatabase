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


def test_cancelling_a_sync_keeps_what_already_landed(tmp_path, monkeypatch) -> None:
    """他点「取消」时那个框答应他：**「已经导入的内容会保留」**（2026-08-11）。

    仓里关于取消的判据验的是**状态机**（queued → paused → cancelled、
    取消之后不许 resume）。**而那句对他说的承诺没有人验过**——
    取消如果把这一轮已经入库的条目一并回滚，界面还是会说「已经导入的内容会保留」，
    他不会发现少了什么。

    这条走真路由：送一批（非终批，run 还活着）→ 确认库里有了 →
    `POST /v1/sync-runs/{id}/control {"action":"cancel"}` → 那条内容必须还在。
    """
    client = _client(tmp_path, monkeypatch)
    connected = _connect(client)
    run_id = connected["first_sync"]["sync_run_id"]

    # **非终批**：has_more=True，这一轮还没跑完——正是他会去点「取消」的时刻。
    partial = client.post(f"/v1/sync-runs/{run_id}/batches", headers=HEAD, json={
        "relation_type": "favorite", "scope_type": "relation",
        "completeness": "partial", "has_more": True,
        "items": [{"platform": "douyin",
                   "url": "https://www.douyin.com/video/770",
                   "external_content_id": "770", "relation_type": "favorite",
                   "title": "取消之前进来的那一条"}]})
    assert partial.status_code == 202, partial.text
    assert client.get("/v1/library", headers=HEAD).json()["total"] == 1, "这一批没进库"

    # **先量，别猜。** 送完一批之后这个 run 是 `partial`，而 `cancel` 只在
    # queued/scanning/…/paused 里允许——也就是说这时候界面本来也不给「取消」
    # （行内那条链只对那几个进行中的状态画暂停/取消），**没有点不动的按钮**。
    #
    # 他真会点「取消」的时刻是扫描还在跑的时候。那个状态由扩展那侧的进度上报
    # 推进，TestClient 造不出来——所以这里直接把 run 摆到 `scanning`，
    # 再走**真的控制路由**。摆状态用的是编排层自己那条更新，不是绕过业务。
    status_after_batch = client.get(f"/v1/sync-runs/{run_id}", headers=HEAD).json()["status"]
    assert status_after_batch == "partial", status_after_batch
    import social_archive.api as api
    api.store.update_sync_run(run_id, status="scanning")

    cancelled = client.post(f"/v1/sync-runs/{run_id}/control", headers=HEAD,
                            json={"action": "cancel"})
    assert cancelled.status_code == 200, cancelled.text
    assert client.get(f"/v1/sync-runs/{run_id}", headers=HEAD).json()["status"] == "cancelled"

    library = client.get("/v1/library", headers=HEAD).json()
    assert library["total"] == 1, (
        f"取消之后库里只剩 {library['total']} 条——"
        "而那个确认框答应他「已经导入的内容会保留」")
    assert library["items"][0]["title"] == "取消之前进来的那一条", library["items"][0]
