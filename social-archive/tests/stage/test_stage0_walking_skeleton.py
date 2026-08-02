from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountConnectRequest, AccountSyncRequest, CaptureRequest, SyncBatchRequest
from social_archive.registry import ConnectorRegistry


def test_stage0_account_mirror_walking_skeleton(settings, store, service):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="generic-web",
        auth_method="chrome_bookmarks",
        display_name="Chrome 书签",
        relation_types=["bookmark"],
    ))
    account_id = coordinator.complete_connection(
        platform="generic-web",
        auth_method="chrome_bookmarks",
        connection_ref=start.connection_ref,
        external_account_id="chrome-bookmarks",
        display_name="Chrome 书签",
        auto_sync_enabled=True,
        sync_interval_minutes=360,
        metadata={"permission": "bookmarks"},
        verified=True,
    )
    run_id = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["bookmark"], trigger_type="first_connect"
    ))["sync_run_id"]
    result = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="bookmark",
        scope_type="relation",
        completeness="complete",
        has_more=False,
        items=[CaptureRequest(
            platform="generic-web",
            url="https://www.wikipedia.org/walk",
            external_content_id="bookmark-1",
            source_account_id="chrome-bookmarks",
            relation_type="bookmark",
            relation_observed_at="2026-08-02T10:00:00Z",
            title="Walking Skeleton",
            text="账号授权后批量导入并在表格资料库显示",
            topic="产品验收",
            keywords=["账号同步", "表格"],
        )],
    ))
    assert result["status"] == "completed"
    table = store.list_library_table(
        platform="generic-web",
        relation="bookmark",
        sort_by="time",
        sort_dir="desc",
    )
    assert table["total"] == 1
    assert table["items"][0]["title"] == "Walking Skeleton"
    assert table["items"][0]["topic"] == "产品验收"
    assert table["items"][0]["keywords"] == ["账号同步", "表格"]
