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


# **两种批次形状都要验。**
#
# `per_collection=True`  —— v0.0.0.9 起扩展真正发的那种：按收藏夹分批，
#                          每批带自己的 collection_key + collection_name + 终批。
#                          分批之前收藏夹的名字整个丢在地上（服务端建收藏夹记录的
#                          条件是 `if batch.collection_name:`）。
# `per_collection=False` —— 分批之前那种：一整批、批次级 key 为空，
#                          全靠服务端那行 `batch.collection_key or item.collection_key`
#                          兜底。**这条路仍然要成立**：cursor 里没有收藏夹清单时
#                          （比如只有一个默认收藏夹）就会走它。
SHAPES = (True, False)


def _one_sync(coordinator, account_id, folders: dict[str, list[str]],
              *, per_collection: bool = True, send_external_id: bool = True) -> str:
    """跑一次完整同步，批次形状照抄 sendBrowserScopeBatches 真正发出去的那种。"""
    run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="incremental", relation_types=["favorite"], trigger_type="manual"))["sync_run_id"]
    names = {"111": "学习", "222": "音乐"}
    if per_collection:
        for collection, bvids in folders.items():
            coordinator.ingest_batch(run, SyncBatchRequest(
                relation_type="favorite", scope_type="collection",
                collection_key=collection, collection_name=names[collection],
                # **外部 id 必须是媒体 id，不能让它默认成名字。**
                # 服务端 `external = external_collection_id or name`，
                # 而库里 join 用的是 r.collection_key（媒体 id）——不给就永远对不上。
                external_collection_id=collection if send_external_id else None,
                items=[_bilibili_item(bvid, collection) for bvid in bvids],
                completeness="partial", batch_index=0, batch_count=1, has_more=False))
            # 收藏夹级终批
            coordinator.ingest_batch(run, SyncBatchRequest(
                relation_type="favorite", scope_type="collection",
                collection_key=collection, collection_name=names[collection],
                external_collection_id=collection if send_external_id else None,
                items=[], completeness="complete", batch_index=1, batch_count=2,
                has_more=False))
    else:
        items = [_bilibili_item(bvid, collection)
                 for collection, bvids in folders.items() for bvid in bvids]
        coordinator.ingest_batch(run, SyncBatchRequest(
            relation_type="favorite", scope_type="collection", collection_key="",
            items=items, completeness="partial", batch_index=0, batch_count=2,
            has_more=False))
    # 关系级终批：这一条才让"消失检测"跑起来
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


@pytest.mark.parametrize("per_collection", SHAPES)
def test_the_first_sync_files_every_item_under_its_own_folder(
        settings, store, service, per_collection) -> None:
    """条目挂到自己的收藏夹上，而不是批次那个空的 collection_key。

    挂错的话消失检测就会在错误的桶里比对——那是下面两条判据的前提。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS, per_collection=per_collection)
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


@pytest.mark.parametrize("per_collection", SHAPES)
def test_syncing_twice_with_the_same_favourites_loses_nothing(
        settings, store, service, per_collection) -> None:
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
    _one_sync(coordinator, account_id, FOLDERS, per_collection=per_collection)
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}
    _one_sync(coordinator, account_id, FOLDERS, per_collection=per_collection)
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}, (
        "**第二次同步把收藏弄丢了**——它们一直在，只是批次和条目的收藏夹归属对不上"
    )
    # 再来一次，确保不是"第二次刚好还没到两次缺席"
    _one_sync(coordinator, account_id, FOLDERS, per_collection=per_collection)
    assert _active(store) == {"BV1aaaaaaaaa", "BV1bbbbbbbbb", "BV1cccccccccc"}


@pytest.mark.parametrize("per_collection", SHAPES)
def test_a_real_unfavourite_does_close_after_two_complete_scans(
        settings, store, service, per_collection) -> None:
    """反过来也要成立：**真的取消收藏了，要认出来。**

    只验"什么都不关"是不够的——一个永远不关的实现同样能过上面那条，
    而它意味着取消收藏永远不会反映到档案馆里。
    两次完整扫描才关闭，是刻意的：一次读漏不该销账。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS, per_collection=per_collection)
    shorter = {"111": ["BV1aaaaaaaaa"], "222": ["BV1cccccccccc"]}   # 取消了 BV1bbbbbbbbb
    _one_sync(coordinator, account_id, shorter, per_collection=per_collection)
    assert "BV1bbbbbbbbb" in _active(store), "**一次缺席就销账了**——读漏一次就会丢数据"
    _one_sync(coordinator, account_id, shorter, per_collection=per_collection)
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


def test_the_library_shows_folder_names_not_media_ids(settings, store, service) -> None:
    """库里要显示「学习」「音乐」，不是「111」「222」（v0.0.0.10）。

    这条链上有三个环节，缺一个他就只能看到一串数字：

      1. 扩展要按收藏夹分批，并带上 collection_name **和** external_collection_id
         （不带后者，服务端会拿名字当外部 id，而关系上存的是媒体 id，永远对不上）
      2. 服务端要建 platform_collection 记录（条件是 `if batch.collection_name:`）
      3. 库的查询要 join 回去把名字取出来

    第 3 步以前根本不存在：那一列直接拼 `r.collection_key`，**却叫 collection_names**
    ——一个名字撒谎的列，读代码的人会以为已经处理过了。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS, per_collection=True)

    table = store.list_library_table(limit=50, offset=0)
    names = {name for row in table["items"] for name in (row.get("collections") or [])}
    assert names == {"学习", "音乐"}, (
        f"库里显示的是 {sorted(names)} —— 他要看的是收藏夹的名字，不是媒体 id"
    )

    # 分面：他得先看得到有哪些收藏夹，才谈得上按收藏夹筛
    facets = {row["label"]: row for row in table["facets"]["collections"]}
    assert set(facets) == {"学习", "音乐"}, f"收藏夹分面不对：{sorted(facets)}"
    assert facets["学习"]["count"] == 2 and facets["音乐"]["count"] == 1
    # **筛选用的 key 必须是库里真正存的那个**，不是显示名——否则点了筛不出东西
    assert facets["学习"]["key"] == "111"

    filtered = store.list_library_table(limit=50, offset=0, collection="111")
    assert {row["title"] for row in filtered["items"]} == {"BV1aaaaaaaaa", "BV1bbbbbbbbb"}, (
        "按收藏夹筛出来的不对——分面给的 key 和查询用的 key 对不上"
    )


def test_a_folder_we_cannot_name_is_not_shown_on_the_row_either(settings, store, service) -> None:
    """说不出名字的收藏夹，**表格那一格也不许显示**。

    中间有一版写的是「查不到名字就退回 key，至少还能分组」。
    对着生产一读就知道那句话站不住：他库里 100 条带着 v0.0.0.6 抓取器留下的 key，
    其中一个是一百字的页面文案（'综合视频直播专栏 更多筛选 清空历史…'）。
    那种东西出现在「收藏夹」这一格里，比显示「未分组」糟得多。

    **而我第一次只修了筛选框，没修表格那一格。**同一个缺陷的第二处：
    这个项目已经在「同一道门在两处布局给出相反结论」上栽过，
    所以这条判据和上面那条筛选框的判据必须一起存在。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS, per_collection=False)
    table = store.list_library_table(limit=50, offset=0)
    names = {name for row in table["items"] for name in (row.get("collections") or [])}
    assert names == set(), (
        f"说不出名字的 key 出现在了条目上：{sorted(names)}"
        "——界面会把它直接画进「收藏夹」那一格"
    )
    assert table["facets"]["collections"] == [], "筛选框那边也不该有"


def test_a_named_folder_shows_on_both_the_row_and_the_filter(settings, store, service) -> None:
    """反过来：**名字知道的时候，两处都要有。**

    只验"说不出名字的不显示"是不够的——一个"什么都不显示"的实现同样能过，
    而那意味着收藏夹这个功能整个是死的。
    """
    coordinator, account_id = _connect(settings, store, service)
    _one_sync(coordinator, account_id, FOLDERS, per_collection=True)
    table = store.list_library_table(limit=50, offset=0)
    names = {name for row in table["items"] for name in (row.get("collections") or [])}
    assert names == {"学习", "音乐"}, f"条目那一格没有显示收藏夹名字：{sorted(names)}"
    labels = {row["label"] for row in table["facets"]["collections"]}
    assert labels == {"学习", "音乐"}, f"筛选框里没有：{sorted(labels)}"


def test_a_folder_we_cannot_name_is_not_offered_as_a_filter(settings, store, service) -> None:
    """说不出名字的 key 不许进筛选框（v0.0.0.11）。

    2026-08-06 对着**生产**量出来的：他库里 193 条中有 100 条带着 v0.0.0.6
    那个 DOM 抓取器留下的 collection_key，而那个抓取器正是因为不可靠才被删掉的。
    它留下的长这样：

        '综合视频直播专栏 更多筛选 清空历史批量管理全部时长10分钟以下…'   70 条

    分面第一版照单全收，于是**一串 100 字的页面文案会出现在他的筛选下拉框里**。
    判据全绿、接口也没错——错的是把说不出名字的 key 当成收藏夹端给用户。

    我第一次只修了筛选框，**条目那一格照旧把 key 画出来**——同一个缺陷的第二处。
    两处现在用同一条规矩：说得出名字才显示。
    """
    coordinator, account_id = _connect(settings, store, service)
    # per_collection=False：批次不带 collection_name → 没有 platform_collection 记录
    _one_sync(coordinator, account_id, FOLDERS, per_collection=False)
    table = store.list_library_table(limit=50, offset=0)
    assert table["facets"]["collections"] == [], (
        "**说不出名字的收藏夹进了筛选框** —— 他会在下拉里看到一串没头没尾的字符串"
    )
    # 条目那一格也一样不许显示——见下面那条判据的说明。
    names = {name for row in table["items"] for name in (row.get("collections") or [])}
    assert names == set(), f"说不出名字的 key 出现在了条目上：{sorted(names)}"


# ---------------------------------------------------------------------------
# **他库里真实的那 194 条**（2026-08-06 从生产只读量到的形状）
#
#   bilibili  history      收藏夹key 是抓页面抓进来的一大段界面文字      70 条
#   douyin    like         空                                          69 条
#   bilibili  favorite     bilibili:/3493091105311656/favlist           30 条
#   douyin    favorite     空                                          16 条
#
# 这些是**旧那条 DOM 抓取路**留下的，key 的写法和现在这条路完全不同
# （现在 B 站用媒体 id 当 key，抖音走按形状读、只报 partial）。
#
# 他的三个账号现在都是「未连接」。**他一旦重连，第一次同步会怎样，
# 是这个产品眼下唯一会让他真损失东西的地方**——而上面那些判据用的都是
# 我编的干净形状，谁也没拿他真实的那份试过。
# ---------------------------------------------------------------------------

HIS_SHAPE = [
    ("bilibili", "favorite", "bilibili:/3493091105311656/favlist", "BVold1"),
    ("bilibili", "favorite", "bilibili:/3493091105311656/favlist", "BVold2"),
    ("bilibili", "history", "综合视频直播专栏 更多筛选 清空历史批量管理全部时长", "BVold3"),
    ("douyin", "like", "", "dyold1"),
    ("douyin", "favorite", "", "dyold2"),
]


def _seed_his_library(store, service, account_id: str) -> None:
    """**必须种在同一个账号的范围里**，否则这些判据是空的。

    第一版我把内部账号 id 传进 capture，而销账用的是
    `stable_id("acct", platform, external_account_id)`——两边算出来的
    账号范围不一样，于是那些行**靠账号隔离幸免**，和分桶一点关系没有。
    反证当场戳穿：把分桶整个去掉，这两条判据照样绿。
    """
    external = store.get_source_account(account_id, include_handle=True)["external_account_id"]
    for platform, relation, collection, ident in HIS_SHAPE:
        service.capture(CaptureRequest(
            platform=platform,
            url=f"https://example.invalid/{platform}/{ident}",
            external_content_id=ident,
            relation_type=relation,
            collection_key=collection,
            source_account_id=external,
            title=ident,
        ))


def _statuses(store) -> dict[str, str]:
    with store.connection() as con:
        return {row[0]: row[1] for row in con.execute(
            "SELECT c.external_content_id, r.status FROM user_relation r "
            "JOIN content c ON c.id=r.content_id")}


def test_reconnecting_never_closes_the_rows_the_old_scraper_left(
    settings, store, service
) -> None:
    """**他重连之后，那 194 条一条都不许被判成「取消收藏」。**

    旧那条路留下的 collection_key 和现在这条路产出的完全不是一套写法
    （`bilibili:/…/favlist` vs 媒体 id）。销账是**按 collection_key 分桶**的，
    所以新扫描扫的是新桶、碰不到旧桶——这条判据就是把这件事钉死，
    免得哪天有人"顺手统一一下 key"，把他两年的收藏一次销掉。
    """
    coordinator, account_id = _connect(settings, store, service)
    _seed_his_library(store, service, account_id)
    before = _statuses(store)
    assert len(before) >= len(HIS_SHAPE)

    # 重连后的第一次同步：只读收藏夹，而且是**新写法的 key**（媒体 id）
    _one_sync(coordinator, account_id, FOLDERS)
    _one_sync(coordinator, account_id, FOLDERS)          # 连着两次，凑满销账门槛

    after = _statuses(store)
    lost = sorted(ident for ident, status in after.items()
                  if status != "active" and ident in {row[3] for row in HIS_SHAPE})
    assert not lost, (
        f"**重连之后把他原来的条目销账了**：{lost}——"
        "旧 key 和新 key 不是一套写法，销账按 key 分桶，不该碰得到它们"
    )
    for ident in {row[3] for row in HIS_SHAPE}:
        assert after.get(ident) == "active", f"{ident} 不见了或被关掉了：{after.get(ident)}"


def _registered(store, account_id) -> set[str]:
    return store.list_registered_collections(
        platform="bilibili",
        external_account_id=store.get_source_account(
            account_id, include_handle=True)["external_account_id"],
        relation_type="favorite")


def test_only_the_new_folders_get_registered_never_the_old_key(
    settings, store, service
) -> None:
    """**销账的射程 = 登记过的收藏夹。这条判据盯的就是那个射程。**（2026-08-07）

    `list_registered_collections` 的文档写着：他那 30 条挂在
    `bilibili:/3493091105311656/favlist` 下的收藏，是靠**从没被登记过**活着的——
    登记过的收藏夹才会被判成「变空」而整桶销账。

    上面那条判据只看「有没有被销账」，看不见**射程本身有没有被放大**。
    今天差点就放大了：我一度在服务端加了「没给 external_collection_id 就退回
    collection_key」的兜底（起因是他生产上三行登记的外部 id 全是 NULL）。
    量清楚之后撤了——那三行是 8/3–8/4 的历史遗留，扩展从 v0.0.0.11 起就一直
    显式发那个 id；兜底对真实客户端是死代码，却会把旧 key 也拉进登记范围。

    所以这里直接量射程：新收藏夹必须在里面（否则筛选栏不出现），
    旧 key 必须不在（否则他 30 条收藏会被两次同步关掉）。
    """
    coordinator, account_id = _connect(settings, store, service)
    _seed_his_library(store, service, account_id)
    _one_sync(coordinator, account_id, FOLDERS)

    registered = _registered(store, account_id)
    assert registered >= set(FOLDERS), (
        f"新收藏夹没登记上：{registered}——那么资料库上方那一栏「收藏夹」筛选不会出现")
    assert "bilibili:/3493091105311656/favlist" not in registered, (
        f"旧那条抓取路留下的 key 被登记成了收藏夹：{registered}——"
        "登记过就可能被判成「变空」，他那 30 条旧收藏会被两次同步关掉")


def test_a_client_that_omits_the_id_widens_nothing(
    settings, store, service
) -> None:
    """**客户端不给外部 id，服务端不猜——射程不许因此变大。**

    这条和上一条是一对：上一条保证「该在的在」，这条保证「不该在的不会被猜进来」。
    """
    coordinator, account_id = _connect(settings, store, service)
    _seed_his_library(store, service, account_id)
    _one_sync(coordinator, account_id, FOLDERS, send_external_id=False)
    _one_sync(coordinator, account_id, FOLDERS, send_external_id=False)

    after = _statuses(store)
    lost = sorted(ident for ident, status in after.items()
                  if status != "active" and ident in {row[3] for row in HIS_SHAPE})
    assert not lost, f"**他原来的条目被销账了**：{lost}"
    assert _registered(store, account_id) == set(), (
        "客户端没给外部 id，服务端却自己猜了一个登记上——**销账的射程被放大了**")


def test_a_relation_nobody_scans_is_never_closed(settings, store, service) -> None:
    """**没人扫的关系类型不许被销账。**

    他有 69 条抖音「点赞」和 71 条 B 站「历史」。
    这两种关系**这一版根本没有取数路**（SCANNABLE_RELATIONS 里只有收藏），
    所以一次同步永远不会"看见"它们。要是销账不按关系类型分桶，
    这 140 条会在两次同步之后集体消失——而他完全不知道为什么。
    """
    coordinator, account_id = _connect(settings, store, service)
    _seed_his_library(store, service, account_id)
    _one_sync(coordinator, account_id, FOLDERS)
    _one_sync(coordinator, account_id, FOLDERS)
    after = _statuses(store)
    for ident, relation in (("dyold1", "like"), ("BVold3", "history")):
        assert after.get(ident) == "active", (
            f"「{relation}」这一版根本没人扫，却被销账了（{ident} → {after.get(ident)}）"
        )


def test_a_feed_page_is_refused_instead_of_saved_as_one_item() -> None:
    """**信息流不是一条内容**（v0.0.0.22）。

    2026-08-06 在 Owner 生产库里量到三行：

        https://www.bilibili.com/            标题「哔哩哔哩 (゜-゜)つロ 干杯~」
        https://www.douyin.com/jingxuan      标题「抖音精选电脑版…」
        https://www.xiaohongshu.com/explore  标题「肯德基为什么总想下架吮指原味鸡？」

    最后那条最坏：标题取自页面上**第一条笔记**，看起来像一条真内容，
    半年后点开却是信息流——那时他已经想不起来当初想存哪一条。

    护栏不靠平台特例：`CONTENT_ID_PATTERNS` 本来就写着每个平台的内容 id
    在 URL 里长什么样。这条判据钉住它真的被用在了保存那一步。
    """
    from pathlib import Path

    background = (Path(__file__).resolve().parents[2]
                  / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    body = background.split("async function captureActive", 1)[1].split("\nasync function", 1)[0]
    assert "CONTENT_ID_PATTERNS" in body, (
        "保存那一步没有用内容 id 的 URL 规则——信息流会被当成一条内容存下来"
    )
    assert "PAGE_IS_A_FEED_NOT_AN_ITEM" in body
    # **只拦整页保存**：列表模式本来就是一次读一批，不该被这条挡住。
    guard = body.split("PAGE_IS_A_FEED_NOT_AN_ITEM", 1)[0]
    assert 'message.mode === "page"' in guard, "这条护栏把列表读取也挡住了"
