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
    # **闭合读的是 completeness 那一列，不是 status。**
    #
    # 这两个可以不一致：批次里带了 errors 时 status 仍是 completed，而
    # completeness 会被降级成 partial（account_sync.py 里
    # `if errors and effective_completeness == "complete"` 那一段）。
    # 而「取消收藏后要从档案馆里消失」这件事，走的是 completeness。
    #
    # 2026-08-07 查他生产库：20 次同步**没有一次 completeness=complete**，
    # 于是缺席闭合从来没跑过。那些是 v0.0.0.6 的遗留记录，但当时没有任何
    # 判据说得出「今天这版跑完一次会不会 complete」——只断言 status
    # 的判据答不了这个问题。
    assert store.get_sync_run(run_id)["completeness"] == "complete", (
        "**跑完了却不算完整** —— 缺席闭合永远不会发生，"
        "他在平台上取消的收藏会永远留在档案馆里")


def test_multi_relation_run_does_not_finish_after_first_relation(settings, store, service, monkeypatch):
    # **不变量是协议层面的**：多关系的 run 不许在第一个关系完成后就结束。
    # 2026-08-10 起同步范围改成读扩展的 SCANNABLE_RELATIONS（抖音/B站/小红书
    # 现在都只有 favorite），于是这个场景本身不再是「多关系」。
    # 把范围显式声明出来，让这条不变量不绑死在目录当下支持什么上。
    from social_archive import account_sync as _sync
    monkeypatch.setitem(_sync.SCANNABLE_RELATIONS, "xiaohongshu", ("favorite", "like"))
    monkeypatch.setitem(_sync.SCANNABLE_RELATIONS, "douyin", ("favorite", "like"))
    monkeypatch.setitem(_sync.SCANNABLE_RELATIONS, "bilibili", ("favorite", "like"))
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
