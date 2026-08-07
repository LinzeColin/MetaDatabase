import sqlite3

from social_archive.db import RuntimeStore
from social_archive.models import CaptureRequest

def test_job_claim_and_finish(store):
    jid=store.enqueue_job('download_l3',{'content_id':'c','page_url':'https://www.wikipedia.org','media_urls':[]},'generic')
    row=store.claim_job('tester');assert row and row['id']==jid
    store.finish_job(jid,success=True);assert store.get_job(jid)['status']=='done'

def test_complete_scan_requires_two_absences(service,store):
    r=service.capture(CaptureRequest(platform='reddit',url='https://reddit.com/r/a/comments/1',relation_type='saved',requested_levels=['L0','L1']))
    store.apply_complete_scan('reddit',set(),relation_type='saved');assert store.get_content(r.content_id)['relations'][0]['status']=='active'
    store.apply_complete_scan('reddit',set(),relation_type='saved');assert store.get_content(r.content_id)['relations'][0]['status']=='closed'


def test_account_mirror_schema_migrates_a_legacy_source_account(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE source_account (
            id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_account_id TEXT,
            display_name TEXT, auth_ref TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(platform, external_account_id)
        )""")
    RuntimeStore(path).initialize()
    with sqlite3.connect(path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(source_account)")}
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"connection_state", "auth_handle_ref", "last_sync_at", "metadata_json"} <= columns
    assert {"sync_run", "sync_checkpoint", "sync_seen_relation", "sync_run_scope"} <= tables


def test_table_schema_migrates_legacy_relation_before_indexes(tmp_path):
    path = tmp_path / "legacy-table.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE source_account (
            id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_account_id TEXT,
            display_name TEXT, auth_ref TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(platform, external_account_id)
        )""")
        con.execute("""CREATE TABLE content (
            id TEXT PRIMARY KEY, platform TEXT NOT NULL, external_content_id TEXT,
            canonical_url TEXT NOT NULL, content_type TEXT NOT NULL DEFAULT 'unknown',
            title TEXT, author_name TEXT, published_at TEXT, first_observed_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL, availability TEXT NOT NULL DEFAULT 'observed',
            metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(platform, external_content_id),
            UNIQUE(platform, canonical_url)
        )""")
        con.execute("""CREATE TABLE user_relation (
            id TEXT PRIMARY KEY, source_account_id TEXT, content_id TEXT NOT NULL,
            relation_type TEXT NOT NULL, collection_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active', first_observed_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL, missing_complete_scan_count INTEGER NOT NULL DEFAULT 0,
            closed_at TEXT, UNIQUE(source_account_id, content_id, relation_type, collection_key)
        )""")
        con.execute(
            "INSERT INTO content VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("c1", "generic-web", "one", "https://example.com/one", "unknown", "one", None, None,
             "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", "observed", "{}"),
        )
        con.execute(
            "INSERT INTO user_relation VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("r1", None, "c1", "bookmark", "", "active", "2026-08-01T00:00:00Z",
             "2026-08-01T00:00:00Z", 0, None),
        )
    RuntimeStore(path).initialize()
    with sqlite3.connect(path) as con:
        relation_columns = {row[1] for row in con.execute("PRAGMA table_info(user_relation)")}
        content_columns = {row[1] for row in con.execute("PRAGMA table_info(content)")}
        relation_time = con.execute("SELECT relation_observed_at FROM user_relation WHERE id='r1'").fetchone()[0]
    assert {"relation_observed_at", "external_relation_id", "last_sync_run_id"} <= relation_columns
    assert {"summary", "language", "media_count", "last_synced_at"} <= content_columns
    assert relation_time == "2026-08-01T00:00:00Z"


def test_a_platform_block_is_not_revived_by_the_next_sync(store) -> None:
    """**结构性失败不许被自动入队复活。**

    2026-08-07 在 Owner 生产库里量到：32 个 download_l3 挂着
    MEDIA_BLOCKED_BY_PLATFORM，attempt_count 全是 6。不是重试策略的问题
    （那个码本来就 retryable=False），是**每 6 小时一次同步会重新 capture
    同一条抖音内容 → 同一个 job id → 失败复活那条把它捞回来**。

    32 条 × 每天 4 次同步 ≈ 每天 128 次对抖音 CDN 的无效请求，**永远不停**。
    """
    payload = {"content_id": "c1", "page_url": "https://www.douyin.com/note/1",
               "media_urls": ["https://img.example/a.jpg"]}
    job_id = store.enqueue_job("download_l3", payload, "douyin")
    store.claim_job("drill")
    store.finish_job(job_id, success=False, error_code="MEDIA_BLOCKED_BY_PLATFORM",
                     error_message="http error 403", retryable=False)
    assert store.get_job(job_id)["status"] == "failed"

    # 下一次同步又把同一条内容排一遍
    again = store.enqueue_job("download_l3", payload, "douyin")
    assert again == job_id, "同一件事应该还是同一个 job id"
    assert store.get_job(job_id)["status"] == "failed", (
        "**平台挡住的活儿被下一次同步复活了**——它会一直对着平台打注定失败的请求"
    )


def test_a_failure_on_our_side_is_still_revived(store) -> None:
    """**别为了修上面那条，把原来那条修法弄没了。**

    失败复活本来是为了解决另一个真问题：导出实现修好之后重排 83 条，
    4 条纹丝不动——它们早先失败过，之后每次 enqueue 都被 IGNORE 掉。
    成因在我们这边的失败，仍然要能被重新请求。
    """
    payload = {"content_id": "c2", "destination_id": "markdown"}
    job_id = store.enqueue_job("export_destination", payload, "markdown")
    store.claim_job("drill")
    store.finish_job(job_id, success=False, error_code="DESTINATION_WRITE_FAILED",
                     error_message="磁盘满了", retryable=False)
    assert store.get_job(job_id)["status"] == "failed"
    assert store.enqueue_job("export_destination", payload, "markdown") == job_id
    assert store.get_job(job_id)["status"] == "queued", (
        "成因在我们这边的失败没被复活——修好之后他重排也不会跑"
    )


def test_there_is_an_explicit_way_to_requeue_a_structural_failure(store) -> None:
    """换了下载器之后要能重排——但**必须有人明确调它**，不是顺带发生的。"""
    payload = {"content_id": "c3", "page_url": "https://www.douyin.com/note/3", "media_urls": []}
    job_id = store.enqueue_job("download_l3", payload, "douyin")
    store.claim_job("drill")
    store.finish_job(job_id, success=False, error_code="MEDIA_BLOCKED_BY_PLATFORM",
                     error_message="http error 403", retryable=False)
    assert store.force_requeue_failed_job(job_id) is True
    assert store.get_job(job_id)["status"] == "queued"


def test_a_blocked_video_is_not_called_a_complete_archive(service, store):
    """**「完整」不许盖住"视频没存下来"。**

    2026-08-07 量他生产库：193 条全标着「完整」，而任务表里有 33 个
    download_l3 是 failed（`MEDIA_BLOCKED_BY_PLATFORM`——B 站/抖音把下载挡了）。
    那 33 条有正文、没有视频，而这一列对他说「完整」——**他会以为视频存下来了**。

    正文那几个 artifact 确实是 complete 的，所以旧的判断（有一个 complete
    就叫完整）在字面上不假，**在意思上是假的**。
    """
    captured = service.capture(CaptureRequest(
        platform="bilibili", url="https://www.bilibili.com/video/BV1x",
        relation_type="favorite", requested_levels=["L0", "L1"]))
    content_id = captured.content_id
    with store.connection() as con:
        con.execute(
            "INSERT INTO artifact(id,content_id,archive_level,artifact_type,sha256,"
            "byte_size,created_at,status)"
            " VALUES('art_blocked_test',?,'L0','metadata','deadbeef',1,datetime('now'),'complete')",
            (content_id,))
    before = [row for row in store.list_library_table(limit=50)["items"] if row["id"] == content_id]
    assert before and before[0]["archive_status"] == "完整", "正常情况下就该是完整"

    store.enqueue_job("download_l3", {"content_id": content_id, "platform": "bilibili",
                                      "page_url": "https://www.bilibili.com/video/BV1x",
                                      "media_urls": []}, "generic")
    with store.connection() as con:
        con.execute("UPDATE job SET status='failed',last_error_code='MEDIA_BLOCKED_BY_PLATFORM'"
                    " WHERE job_type='download_l3'")
    after = [row for row in store.list_library_table(limit=50)["items"] if row["id"] == content_id]
    assert after and after[0]["archive_status"] == "视频没存下", (
        f"视频被平台挡了，这一列还说「{after[0]['archive_status']}」——他会以为视频存下来了")
