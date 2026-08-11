r"""同一条内容再同步一次，作者和发布时间会被补上（2026-08-11）。

## 这条判据回答的是他的一个真问题

今天量了他生产库（只读只数数）：

    193 条 · **有作者的 36** · **有发布时间的 2** · 有标题的 187
    metadata_json 里也没有留着这两样（0 条）——不是显示层丢的，是当初就没取到

那 193 条是 2026-08-03 用老代码取的。现在的取数路两样都带
（`list_shape_end_to_end_drill` 对 title/author_name/published_at 都有断言，
抖音那一档今天刚跑通）。于是他的问题变成：

> **重新同步会修好已经存在的那些，还是只对新条目有效？**

答案决定他该「重连就好」还是「删掉重来」——后者才需要那颗「删除并清空」。

## 实测（真镜像，0.0.0.41）

    第一次同步（老代码的样子：不带作者、不带发布时间）
        author = null · published_at = null
    重新连接、再同步一次（这次带上两样）
        author = "雪瑜" · published_at = "2026-08-03T08:51:24Z" · 总条目仍是 1

**会补上，而且不会变成两条。** 所以他重连就够了，不用删。

这条判据把那个行为钉住：以后谁把 upsert 改成「已存在就跳过」，
他那 157 条「未知作者」就永远修不好了，而**没有任何别的判据会红**。
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

TOKEN = "backfill-drill-token"
HEAD = {"Authorization": f"Bearer {TOKEN}"}


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


def _connect(client) -> str:
    started = client.post("/v1/accounts/connect/start", headers=HEAD,
                          json={"platform": "douyin", "auth_method": "browser_session"})
    assert started.status_code in (200, 202), started.text
    done = client.post("/v1/accounts/connect/douyin/complete", headers=HEAD, json={
        "connection_ref": started.json()["connection_ref"],
        "external_account_id": "owner", "display_name": "抖音", "verified": True,
        "metadata": {"auth_method": "browser_session"}})
    assert done.status_code == 201, done.text
    return done.json()["first_sync"]["sync_run_id"]


def _send(client, run_id: str, **extra) -> None:
    item = {"platform": "douyin", "url": "https://www.douyin.com/video/999",
            "external_content_id": "999", "relation_type": "favorite",
            "title": "同一条内容", **extra}
    got = client.post(f"/v1/sync-runs/{run_id}/batches", headers=HEAD, json={
        "relation_type": "favorite", "scope_type": "relation",
        "completeness": "complete", "has_more": False, "items": [item]})
    assert got.status_code == 202, got.text


def test_a_second_sync_backfills_author_and_published_at(tmp_path, monkeypatch) -> None:
    """**他 193 条里 157 条没有作者、191 条没有发布时间。** 重连能不能修好它们。"""
    client = _client(tmp_path, monkeypatch)

    _send(client, _connect(client))                      # 老代码的样子：两样都没有
    before = client.get("/v1/library", headers=HEAD).json()["items"][0]
    assert not before.get("author_name"), before
    assert not before.get("published_at"), before

    _send(client, _connect(client),                      # 现在的取数路：两样都带
          author_name="雪瑜", published_at="2026-08-03T08:51:24Z")
    after = client.get("/v1/library", headers=HEAD).json()
    assert after["total"] == 1, f"补一次变成了 {after['total']} 条——重复了"
    item = after["items"][0]
    assert item.get("author_name") == "雪瑜", (
        f"重新同步没把作者补上：{item.get('author_name')!r}——"
        "那他那 157 条「未知作者」就只能靠删掉重来")
    assert str(item.get("published_at", "")).startswith("2026-08-03"), (
        f"重新同步没把发布时间补上：{item.get('published_at')!r}")


def test_a_second_sync_does_not_wipe_what_it_no_longer_carries(tmp_path, monkeypatch) -> None:
    """**反方向：补得上，不等于可以擦掉。**

    要是后来某一次同步取不到作者（平台改了字段、页面没加载全），
    不该把已经存下的那个作者清成 null——那是拿一次失败去覆盖一次成功。
    """
    client = _client(tmp_path, monkeypatch)
    _send(client, _connect(client), author_name="雪瑜",
          published_at="2026-08-03T08:51:24Z")
    _send(client, _connect(client))                      # 这一次两样都没带
    item = client.get("/v1/library", headers=HEAD).json()["items"][0]
    assert item.get("author_name") == "雪瑜", (
        f"一次没取到作者，就把已经存下的擦掉了：{item.get('author_name')!r}")
    assert str(item.get("published_at", "")).startswith("2026-08-03"), (
        f"发布时间被擦掉了：{item.get('published_at')!r}")
