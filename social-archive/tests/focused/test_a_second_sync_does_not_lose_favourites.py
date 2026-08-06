"""再同步一次，不许把已有的收藏判成"他取消了"（v0.0.0.9 / G1 · INV-REVERSIBLE）。

## 为什么单开一个

B 站那条取数路（G1）发批次的形状和别的连接器**不一样**：

    批次级 collection_key = ""        ← 一次读完全部收藏夹，批次不属于某一个
    每个条目自带 collection_key       ← "111" / "222"，各归各的收藏夹

而"消失检测"（`apply_complete_scan`）是**按 collection_key 分桶**关闭的：
一次 complete 扫描里，某个桶里没被看见的关系记一次缺席，连续两次就 status='closed'。

服务端那一行 `collection_key = batch.collection_key or item.collection_key or ""`
把两边统一起来：**存进库用哪个 key，记"看见了"就用哪个 key**。

⚠️ **我第一版在这里写错过一个理由，留着当记录。**
当时写的是「批次说 ""、条目挂在 "111"，两边对不上，第二次同步就把 "111"
整桶关掉」。拿反例一验就知道不对：把那个 fallback 拿掉之后，
**红的是"条目挂错了收藏夹"那条，而不是"第二次同步丢数据"那条**——
因为存储和"看见了"用的是同一个变量，它们不可能朝相反方向偏。
一个说得通、也确实指向真代码、但机制是错的理由。

真正会丢数据的是另外两条，下面各有一条判据守着：
  · 只缺席一次就销账 —— 那样读漏一次（网络抖动、翻页卡住）就会丢东西
  · 没读完（partial）也销账 —— 那样一次失败的同步能清空一个收藏夹
还有一条是**结构上**安全的，也验一遍免得以后被改掉：
手动保存的条目没有 source_account_id，而销账只在某个账号的范围内进行。
"""

from __future__ import annotations

import pytest

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import (
    AccountConnectRequest,
    AccountSyncRequest,
    CaptureRequest,
    SyncBatchRequest,
)
from social_archive.registry import ConnectorRegistry

# B 站真实形状：两个收藏夹，三条视频。和端到端演练里那份固定装置一致。
FOLDERS = {"111": ["BV1aaaaaaaaa", "BV1bbbbbbbbb"], "222": ["BV1cccccccccc"]}


def _bilibili_item(bvid: str, collection: str) -> CaptureRequest:
    """**条目自带 collection_key，批次不带**——这就是 B 站那条路的形状。"""
    return CaptureRequest(
        platform="bilibili",
        url=f"https://www.bilibili.com/video/{bvid}",
        external_content_id=bvid,
        relation_type="favorite",
        collection_key=collection,
        title=bvid,
    )


def _connect(settings, store, service):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="bilibili", auth_method="browser_session", relation_types=["favorite"]))
    account_id = coordinator.complete_connection(
        platform="bilibili", auth_method="browser_session",
        connection_ref=start.connection_ref, external_account_id="1919810",
        display_name="B站 · 测试账号", auto_sync_enabled=True,
        sync_interval_minutes=360, metadata={"verified_by": "bilibili_nav_api"}, verified=True)
    return coordinator, account_id


def _one_sync(coordinator, account_id, folders: dict[str, list[str]]) -> str:
    """跑一次完整同步，批次形状照抄 sendBrowserScopeBatches 真正发出去的那种。"""
    run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="incremental", relation_types=["favorite"], trigger_type="manual"))["sync_run_id"]
    items = [_bilibili_item(bvid, collection)
             for collection, bvids in folders.items() for bvid in bvids]
    # ① 条目批次：scope_type=collection，**批次级 collection_key 是空的**
    coordinator.ingest_batch(run, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", collection_key="",
        items=items, completeness="partial", batch_index=0, batch_count=2, has_more=False))
    # ② 关系级终批：这一条才让"消失检测"跑起来
    coordinator.ingest_batch(run, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", collection_key="",
        items=[], completeness="complete", batch_index=1, batch_count=2, has_more=False))
    return run


def _active(store) -> set[str]:
    with store.connection() as con:
        rows = con.execute(
            """SELECT c.external_content_id AS eid
               FROM user_relation r JOIN content c ON c.id = r.content_id
               WHERE r.status='active' AND c.platform='bilibili' AND r.relation_type='favorite'"""
        ).fetchall()
    return {str(row["eid"]) for row in rows}


def test_the_first_sync_files_every_item_under_its_own_folder(settings, store, service) -> None:
    """条目挂到自己的收藏夹上，而不是批次那个空的 collection_key。

    挂错的话消失检测就会在错误的桶里比对——那是下面两条判据的前提。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS)
    with store.connection() as con:
        rows = con.execute(
            """SELECT c.external_content_id AS eid, r.collection_key AS ck
               FROM user_relation r JOIN content c ON c.id = r.content_id
               WHERE c.platform='bilibili'"""
        ).fetchall()
    filed = {str(row["eid"]): str(row["ck"]) for row in rows}
    assert filed == {"BV1aaaaaaaaa": "111", "BV1bbbbbbbbb": "111", "BV1cccccccccc": "222"}, (
        "条目没有挂到自己的收藏夹上——消失检测会在错误的桶里比对"
    )


def test_syncing_twice_with_the_same_favourites_loses_nothing(settings, store, service) -> None:
    """**同一批收藏同步两次，一条都不许少。**

    自动同步每 6 小时一次，也就是说这条路每天要走四遍。任何"每次都记一次缺席"
    的偏差，两次之内就会把收藏清空——而每次同步都报 complete、没有任何失败码，
    界面上只是东西越来越少。

    这一条**不指明某一种成因**（模块头记了我第一版指错成因的经过）：
    它守的是那个结果本身——重复同步不许改变已有收藏的状态。
    单靠它是不够的，一个"永远不销账"的实现同样能过；
    所以下一条反过来验"该销账时真的销"。**两条一起才有意义。**
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS)
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}
    _one_sync(coordinator, account_id, FOLDERS)
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}, (
        "**第二次同步把收藏弄丢了**——它们一直在，只是批次和条目的收藏夹归属对不上"
    )
    # 再来一次，确保不是"第二次刚好还没到两次缺席"
    _one_sync(coordinator, account_id, FOLDERS)
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}


def test_a_real_unfavourite_does_close_after_two_complete_scans(settings, store, service) -> None:
    """反过来也要成立：**真的取消收藏了，要认出来。**

    只验"什么都不关"是不够的——一个永远不关的实现同样能过上面那条，
    而它意味着取消收藏永远不会反映到档案馆里。
    两次完整扫描才关闭，是刻意的：一次读漏不该销账。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS)
    shorter = {"111": ["BV1aaaaaaaaa"], "222": ["BV1cccccccccc"]}   # 取消了 BV1bbbbbbbbb
    _one_sync(coordinator, account_id, shorter)
    assert "BV1bbbbbbbbb" in _active(store), "**一次缺席就销账了**——读漏一次就会丢数据"
    _one_sync(coordinator, account_id, shorter)
    assert "BV1bbbbbbbbb" not in _active(store), (
        "连续两次完整扫描都没看见它，却还留着——取消收藏永远不会反映出来"
    )
    # **别的收藏夹不许被牵连。**
    assert _active(store) == {"BV1aaaaaaaaa", "BV1cccccccccc"}


def test_a_partial_scan_never_closes_anything(settings, store, service) -> None:
    """没读完的那次不许销账。

    B 站那条路会在条数对不上、翻页卡住、超出页数上限时报 partial。
    partial 还销账的话，一次网络抖动就能让他丢掉一整个收藏夹。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS)
    run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="incremental", relation_types=["favorite"], trigger_type="manual"))["sync_run_id"]
    # 一条都没读到，而且明说没读完
    coordinator.ingest_batch(run, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", collection_key="", items=[],
        completeness="partial", batch_index=0, batch_count=1, has_more=False,
        failure_code="BILIBILI_COUNT_MISMATCH"))
    coordinator.ingest_batch(run, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", collection_key="", items=[],
        completeness="partial", batch_index=1, batch_count=2, has_more=False,
        failure_code="BILIBILI_COUNT_MISMATCH"))
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}, (
        "**没读完的那次也销账了**——一次网络抖动就能让他丢掉一整个收藏夹"
    )


def test_manual_saves_are_never_closed_by_an_automatic_sync(settings, store, service) -> None:
    """**他手动存的那些，自动同步一条都不许动。**

    这条最要紧：九个平台里有七个**只能**手动保存，那是他仅有的数据。
    自动同步跑的是「这个账号的这个关系范围」，而手动保存的条目
    没有 source_account_id——`apply_complete_scan` 的 WHERE 里
    `COALESCE(r.source_account_id,'')=?` 把它们排除在外。

    这是**结构上**的安全，不是巧合；但正因为是结构上的，
    以后有人给手动保存补上 source_account_id 时不会想到这里。
    所以钉一条判据：连跑三次报 complete 的同步，手动存的那条必须还在。
    """
    coordinator, account_id = _connect(settings, store, service)
    manual = service.capture(CaptureRequest(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1manualsave",
        external_content_id="BV1manualsave",
        # 手动保存走的就是这个默认关系
        relation_type="manual_save",
        title="我自己存的",
    ))
    assert manual.relation_id
    for _ in range(3):
        _one_sync(coordinator, account_id, FOLDERS)
    with store.connection() as con:
        row = con.execute(
            """SELECT r.status FROM user_relation r JOIN content c ON c.id=r.content_id
               WHERE c.external_content_id='BV1manualsave'"""
        ).fetchone()
    assert row is not None, "手动保存的那条不见了"
    assert row["status"] == "active", (
        "**自动同步把他手动存的那条销账了** —— 七个平台只能手动保存，那是他仅有的数据"
    )
