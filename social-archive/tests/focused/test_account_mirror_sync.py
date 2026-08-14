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


def test_reconnecting_adopts_the_existing_account_instead_of_forking(settings, store, service) -> None:
    """**同一个平台再连一次，不许开第二个账号。**

    2026-08-07 在 Owner 生产库里量到的形状：他三个账号的 external_account_id
    是**主页地址**（上一代取数路留下的），

        douyin  https://www.douyin.com/user/self?from_nav=1   85 条

    而按形状读那条路认不出他是谁（只读收藏页，不去主页），完成连接时报的是
    固定的 "browser-session"。两者对不上 → **重连新建一行**：
    他的 85 条留在旧账号下面，新卡片上写着 0 条。
    数据没丢，但他看到的是"东西没了"。
    """
    from social_archive.account_sync import UNIDENTIFIED_BROWSER_ACCOUNT, AccountSyncCoordinator
    from social_archive.registry import ConnectorRegistry

    old_id = store.upsert_source_account(
        platform="douyin",
        external_account_id="https://www.douyin.com/user/self?from_nav=1",
        display_name="我的",
        auth_method="browser_session",
        auth_handle_ref="conn_legacy_fixture",
        connection_state="disconnected",
    )
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="douyin", auth_method="browser_session", display_name="抖音账号",
        relation_types=["favorite"]))
    new_id = coordinator.complete_connection(
        platform="douyin", auth_method="browser_session",
        connection_ref=start.connection_ref,
        external_account_id=UNIDENTIFIED_BROWSER_ACCOUNT,
        display_name="抖音账号", auto_sync_enabled=True, sync_interval_minutes=360,
        metadata={}, verified=True)

    assert new_id == old_id, (
        "**重连开出了第二个抖音账号**——他原来的条目留在旧账号下面，"
        "新卡片上会写着 0 条，看起来像东西没了"
    )
    with store.connection() as con:
        rows = con.execute("SELECT external_account_id FROM source_account WHERE platform='douyin'").fetchall()
    assert len(rows) == 1, f"抖音有 {len(rows)} 个账号行：{[dict(r) for r in rows]}"
    assert rows[0]["external_account_id"] == "https://www.douyin.com/user/self?from_nav=1", (
        "沿用的不是旧的那个外部 id——user_relation.source_account_id 是从它推出来的，"
        "换掉等于把已有条目和账号的关系割断"
    )


def test_a_first_ever_connect_still_creates_the_account(settings, store, service) -> None:
    """**别为了认领把"第一次连接"弄没了。**"""
    from social_archive.account_sync import UNIDENTIFIED_BROWSER_ACCOUNT, AccountSyncCoordinator
    from social_archive.registry import ConnectorRegistry

    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="kuaishou", auth_method="browser_session", display_name="快手账号",
        relation_types=["favorite"]))
    account_id = coordinator.complete_connection(
        platform="kuaishou", auth_method="browser_session",
        connection_ref=start.connection_ref,
        external_account_id=UNIDENTIFIED_BROWSER_ACCOUNT,
        display_name="快手账号", auto_sync_enabled=True, sync_interval_minutes=360,
        metadata={}, verified=True)
    assert account_id
    account = store.get_source_account(account_id, include_handle=True)
    assert account["external_account_id"] == UNIDENTIFIED_BROWSER_ACCOUNT
