from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountConnectRequest, AccountSyncRequest, CaptureRequest, SyncBatchRequest
from social_archive.registry import ConnectorRegistry


def test_connect_once_then_ingest_full_collection(settings, store, service):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="xiaohongshu",
        auth_method="browser_session",
        display_name="我的小红书",
        relation_types=["favorite", "like"],
    ))
    assert start.state == "authorizing"
    assert start.connection_ref.startswith("conn_")
    account_id = coordinator.complete_connection(
        platform="xiaohongshu",
        auth_method="browser_session",
        connection_ref=start.connection_ref,
        external_account_id="owner-xhs-1",
        display_name="我的小红书",
        auto_sync_enabled=True,
        sync_interval_minutes=360,
        metadata={"source": "chrome"},
        verified=True,
    )
    run = coordinator.start_sync(account_id, AccountSyncRequest(mode="first_full", relation_types=["favorite"], trigger_type="first_connect"))
    result = coordinator.ingest_batch(run["sync_run_id"], SyncBatchRequest(
        relation_type="favorite",
        collection_key="tech",
        collection_name="技术收藏",
        completeness="complete",
        has_more=False,
        known_anchor="note-2",
        items=[
            CaptureRequest(
                platform="xiaohongshu",
                url="https://www.xiaohongshu.com/explore/note-1",
                external_content_id="note-1",
                relation_type="favorite",
                relation_observed_at="2026-08-02T10:00:00Z",
                title="第一条",
                text="回转窑动态测量和现场校准",
                topic="机械制造",
                keywords=["回转窑", "测量"],
            ),
            CaptureRequest(
                platform="xiaohongshu",
                url="https://www.xiaohongshu.com/explore/note-2",
                external_content_id="note-2",
                relation_type="favorite",
                relation_observed_at="2026-08-02T11:00:00Z",
                title="第二条",
                text="Agent 工作流",
                topic="AI与技术",
                keywords=["Agent", "工作流"],
            ),
        ],
    ))
    assert result["status"] == "completed"
    assert result["accepted"] == 2
    table = store.list_library_table(platform="xiaohongshu", sort_by="time", sort_dir="desc")
    assert table["total"] == 2
    assert table["items"][0]["title"] == "第二条"
    assert table["items"][0]["topic"] == "AI与技术"
    assert table["items"][0]["keywords"] == ["Agent", "工作流"]
    account = store.list_source_accounts()[0]
    assert account["connection_state"] == "connected"
    assert account["content_count"] == 2


def test_partial_batch_never_closes_existing_relation(settings, store, service):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    account_id = store.upsert_source_account(
        platform="reddit", external_account_id="u1", display_name="u1", auth_method="oauth",
        auth_handle_ref="conn_existing", connection_state="connected",
    )
    service.capture(CaptureRequest(
        platform="reddit", url="https://www.reddit.com/r/a/comments/one", external_content_id="one",
        relation_type="saved", source_account_id="u1", title="existing",
    ))
    run = coordinator.start_sync(account_id, AccountSyncRequest(mode="incremental", relation_types=["saved"]))
    coordinator.ingest_batch(run["sync_run_id"], SyncBatchRequest(
        relation_type="saved", completeness="partial", has_more=False, items=[]
    ))
    with store.connection() as con:
        row = con.execute("SELECT status,missing_complete_scan_count FROM user_relation").fetchone()
    assert row["status"] == "active"
    assert row["missing_complete_scan_count"] == 0
