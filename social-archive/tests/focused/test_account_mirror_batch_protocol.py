from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountConnectRequest, AccountSyncRequest, CaptureRequest, SyncBatchRequest
from social_archive.registry import ConnectorRegistry


def _connected(settings, store, service, platform="xiaohongshu", external="owner"):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform=platform,
        auth_method="browser_session",
        relation_types=["favorite", "like"] if platform == "xiaohongshu" else [],
    ))
    account_id = coordinator.complete_connection(
        platform=platform,
        auth_method="browser_session",
        connection_ref=start.connection_ref,
        external_account_id=external,
        display_name="测试账号",
        auto_sync_enabled=True,
        sync_interval_minutes=360,
        metadata={"source": "focused-test"},
        verified=True,
    )
    return coordinator, account_id


def _item(external_id, relation="favorite", collection="tech"):
    return CaptureRequest(
        platform="xiaohongshu",
        url=f"https://www.xiaohongshu.com/explore/{external_id}",
        external_content_id=external_id,
        relation_type=relation,
        collection_key=collection,
        title=external_id,
    )


def test_chunked_collection_waits_for_relation_final_and_keeps_all_pages(settings, store, service):
    coordinator, account_id = _connected(settings, store, service)
    run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["favorite"], trigger_type="first_connect"
    ))
    run_id = run["sync_run_id"]

    first = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", batch_index=0, batch_count=2,
        collection_key="tech", completeness="partial", has_more=True,
        items=[_item("note-1"), _item("note-2")],
    ))
    assert first["status"] == "scanning"

    second = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", batch_index=1, batch_count=2,
        collection_key="tech", completeness="complete", has_more=False,
        items=[_item("note-3")],
    ))
    assert second["status"] == "scanning"

    final = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", completeness="complete", has_more=False,
        items=[],
    ))
    assert final["status"] == "completed"
    seen = store.list_sync_seen_relation_ids(sync_run_id=run_id, relation_type="favorite", collection_key="tech")
    assert len(seen) == 3
    assert store.get_sync_run(run_id)["status"] == "completed"


def test_multi_relation_run_does_not_finish_after_first_relation(settings, store, service):
    coordinator, account_id = _connected(settings, store, service)
    run_id = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["favorite", "like"], trigger_type="first_connect"
    ))["sync_run_id"]

    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", collection_key="", completeness="partial",
        items=[_item("fav-1", "favorite", "")],
    ))
    first_final = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", completeness="complete", items=[]
    ))
    assert first_final["status"] == "scanning"
    assert store.get_sync_run(run_id)["status"] == "scanning"

    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="like", scope_type="collection", completeness="partial",
        items=[_item("like-1", "like", "")],
    ))
    second_final = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="like", scope_type="relation", completeness="complete", items=[]
    ))
    assert second_final["status"] == "completed"


def test_partial_relation_never_triggers_absence_closure(settings, store, service):
    coordinator, account_id = _connected(settings, store, service)
    service.capture(_item("old", "favorite", "tech").model_copy(update={"source_account_id": "owner"}))
    run_id = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="incremental", relation_types=["favorite"], trigger_type="manual"
    ))["sync_run_id"]
    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", completeness="partial",
        failure_code="SCROLL_END_UNCONFIRMED", items=[]
    ))
    with store.connection() as con:
        row = con.execute("SELECT status,missing_complete_scan_count FROM user_relation").fetchone()
    assert row["status"] == "active"
    assert row["missing_complete_scan_count"] == 0
