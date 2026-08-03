import pytest

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


DOMESTIC_ACCOUNT_CASES = (
    ("xiaohongshu", "favorite"),
    ("douyin", "favorite"),
    ("kuaishou", "favorite"),
    ("bilibili", "favorite"),
)

DOMESTIC_URL_PREFIXES = {
    "xiaohongshu": "https://www.xiaohongshu.com/explore/",
    "douyin": "https://www.douyin.com/video/",
    "kuaishou": "https://www.kuaishou.com/short-video/",
    "bilibili": "https://www.bilibili.com/video/",
}


def _domestic_item(platform, external_id, relation):
    return CaptureRequest(
        platform=platform,
        url=f"{DOMESTIC_URL_PREFIXES[platform]}{external_id}",
        external_content_id=external_id,
        relation_type=relation,
        collection_key="fixture",
        title=f"{platform}-{external_id}",
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


@pytest.mark.parametrize(("platform", "relation"), DOMESTIC_ACCOUNT_CASES)
def test_each_domestic_platform_fixture_connects_first_full_then_incremental(
    settings, store, service, platform, relation
):
    coordinator, account_id = _connected(settings, store, service, platform=platform, external=f"owner-{platform}")
    first_run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=[relation], trigger_type="first_connect"
    ))
    assert first_run["mode"] == "first_full"

    coordinator.ingest_batch(first_run["sync_run_id"], SyncBatchRequest(
        relation_type=relation, scope_type="collection", collection_key="fixture",
        collection_name="Stage 2 Fixture", completeness="partial", has_more=False,
        items=[_domestic_item(platform, f"{platform}-first", relation)],
    ))
    first_complete = coordinator.ingest_batch(first_run["sync_run_id"], SyncBatchRequest(
        relation_type=relation, scope_type="relation", completeness="complete", has_more=False, items=[]
    ))
    assert first_complete["status"] == "completed"
    assert store.get_source_account(account_id)["last_sync_at"]

    incremental_run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="incremental", relation_types=[relation], trigger_type="manual"
    ))
    assert incremental_run["mode"] == "incremental"
    coordinator.ingest_batch(incremental_run["sync_run_id"], SyncBatchRequest(
        relation_type=relation, scope_type="collection", collection_key="fixture",
        collection_name="Stage 2 Fixture", completeness="partial", has_more=False,
        items=[_domestic_item(platform, f"{platform}-incremental", relation)],
    ))
    incremental_complete = coordinator.ingest_batch(incremental_run["sync_run_id"], SyncBatchRequest(
        relation_type=relation, scope_type="relation", completeness="complete", has_more=False, items=[]
    ))
    assert incremental_complete["status"] == "completed"
    assert store.list_library_table(platform=platform, sort_by="time", sort_dir="desc")["total"] == 2


def test_paused_run_rejects_late_batch_until_resumed(settings, store, service):
    coordinator, account_id = _connected(settings, store, service)
    run_id = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["favorite"], trigger_type="first_connect"
    ))["sync_run_id"]

    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", collection_key="tech",
        completeness="partial", has_more=True, cursor={"page": 1}, items=[_item("before-pause")],
    ))
    before_pause = store.get_sync_run(run_id)
    assert before_pause["status"] == "scanning"
    assert store.control_sync_run(run_id, "pause") is True

    with pytest.raises(ValueError, match="同步已暂停"):
        coordinator.ingest_batch(run_id, SyncBatchRequest(
            relation_type="favorite", scope_type="collection", collection_key="tech",
            completeness="partial", has_more=False, cursor={"page": 2}, items=[_item("late-batch")],
        ))

    paused = store.get_sync_run(run_id)
    assert paused["status"] == "paused"
    assert paused["imported_count"] == before_pause["imported_count"]
    assert store.list_sync_seen_relation_ids(
        sync_run_id=run_id, relation_type="favorite", collection_key="tech"
    )

    assert store.control_sync_run(run_id, "resume") is True
    assert store.get_sync_run(run_id)["status"] == "queued"
    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", collection_key="tech",
        completeness="partial", has_more=False, cursor={"page": 2}, items=[_item("after-resume")],
    ))
    final = coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", completeness="complete", has_more=False, items=[]
    ))
    assert final["status"] == "completed"
    assert len(store.list_sync_seen_relation_ids(
        sync_run_id=run_id, relation_type="favorite", collection_key="tech"
    )) == 2


def test_batch_accepts_the_item_shape_the_browser_mirror_actually_sends():
    # CaptureRequest forbids unknown fields. The browser account mirror labels
    # every scanned item with its collection_name, which the model did not
    # declare, so the server answered 422 and the entire batch was discarded --
    # items were discovered and sent, then thrown away at the door, which is
    # exactly the "sync always reports 0" symptom.
    from social_archive.models import SyncBatchRequest

    batch = SyncBatchRequest.model_validate({
        "relation_type": "favorite",
        "scope_type": "collection",
        "collection_key": "默认收藏夹",
        "collection_name": "默认收藏夹",
        "completeness": "partial",
        "items": [{
            "platform": "xiaohongshu",
            "url": "https://www.xiaohongshu.com/explore/abc123",
            "relation_type": "favorite",
            "relation_observed_at": "2026-08-03T10:00:00Z",
            "collection_key": "默认收藏夹",
            "collection_name": "默认收藏夹",
            "title": "标题",
            "media_urls": [],
            "raw_metadata": {"capture_source": "browser_account_mirror"},
            "requested_levels": ["L0", "L1", "L3"],
            "destination_ids": ["social_archive"],
        }],
    })
    assert len(batch.items) == 1
    assert batch.items[0].collection_name == "默认收藏夹"
    # A genuinely unknown field must still be rejected.
    import pytest
    with pytest.raises(Exception):
        SyncBatchRequest.model_validate({
            "relation_type": "favorite",
            "items": [{"platform": "xiaohongshu", "url": "https://www.xiaohongshu.com/explore/x", "not_a_real_field": 1}],
        })
