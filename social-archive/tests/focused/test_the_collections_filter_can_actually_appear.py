"""说明书答应的那个「收藏夹」筛选，在他的数据上得真的出得来（2026-08-07）。

## 怎么发现的

从他生产库里读真实形状（只读）。`platform_collection` 有 3 行——**是 8/3–8/4
那几次真同步写进去的**，名字是「收藏」「合集和系列」，说明写入这条路是通的。

但三行的 `external_collection_id` **全是 NULL**。而分面那条 SQL 是

    JOIN platform_collection pc ON … pc.external_collection_id = r.collection_key

两边来自**两个不同的字段**：关系存 `batch.collection_key`，登记存
`batch.external_collection_id`，而扩展从来不发后者（模型默认 None）。
当场量：那条 JOIN 在他 193 条上匹配 **0 条**。

而 `docs/使用说明.md` 写着

    B 站连上之后，资料库上方会多出一个**「收藏夹」筛选**

**按原来的写法，那一栏在他数据上永远不会出现。** 判据全绿、接口也没错——
错的是两个字段被当成了同一个身份，而没有任何判据把它们对起来。

## 夹具用他真实的那把 key

`bilibili:/3493091105311656/favlist`（他库里 30 条 favorite 挂在这把 key 下）。
不另编一个更干净的——**夹具比原文干净就等于没测**，这个仓栽过五次。
"""

from __future__ import annotations

from pathlib import Path

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import (AccountConnectRequest, AccountSyncRequest,
                                   CaptureRequest, SyncBatchRequest)
from social_archive.registry import ConnectorRegistry

ROOT = Path(__file__).resolve().parents[2]

# 他生产库里真实的那把 key 和那个名字（2026-08-07 只读量得）。
REAL_KEY = "bilibili:/3493091105311656/favlist"
REAL_NAME = "收藏"


def _ingest(settings, store, service, *, external_collection_id=None):
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="bilibili", auth_method="browser_session", relation_types=["favorite"]))
    account_id = coordinator.complete_connection(
        platform="bilibili", auth_method="browser_session",
        connection_ref=start.connection_ref, external_account_id="owner",
        display_name="B站", auto_sync_enabled=True, sync_interval_minutes=360,
        metadata={"source": "focused-test"}, verified=True)
    run_id = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["favorite"],
        trigger_type="first_connect"))["sync_run_id"]
    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", batch_index=0, batch_count=1,
        collection_key=REAL_KEY, collection_name=REAL_NAME,
        external_collection_id=external_collection_id,
        completeness="complete", has_more=False,
        items=[CaptureRequest(
            platform="bilibili", url="https://www.bilibili.com/video/BV1xx",
            external_content_id="BV1xx", relation_type="favorite",
            collection_key=REAL_KEY, title="一条真收藏")]))
    return account_id


def _collections(store) -> list[dict]:
    return store.list_library_table(limit=1)["facets"].get("collections", [])


def test_the_guide_still_promises_the_filter() -> None:
    """**判据守的是一句承诺，那句话得还在。**

    改了承诺就要一起改这里，别让判据守着一句已经不存在的话。
    """
    guide = (ROOT / "docs/使用说明.md").read_text(encoding="utf-8")
    assert "「收藏夹」筛选" in guide, "说明书里那句承诺被改了或删了"
    assert "里面是你自己给收藏夹起的那些名字" in guide


def test_a_real_bilibili_favlist_shows_up_in_the_filter(settings, store, service) -> None:
    """**他连上之后那一栏必须真的出得来。**

    扩展只发 collection_key + collection_name（真实情况），不发
    external_collection_id。登记要退回 collection_key，否则分面永远匹配不上。
    """
    _ingest(settings, store, service)
    collections = _collections(store)
    assert collections, (
        "分面里一个收藏夹都没有——**说明书答应他会多出一栏「收藏夹」筛选，"
        "而那一栏整个是藏着的**。登记用的 id 和关系用的 key 对不上就会这样。")
    keys = {row["key"]: row.get("label") for row in collections}
    assert REAL_KEY in keys, f"他真实那把 key 没进分面：{list(keys)}"
    assert keys[REAL_KEY] == REAL_NAME, (
        f"下拉框里显示的是 {keys[REAL_KEY]!r}，不是他给收藏夹起的名字 {REAL_NAME!r}——"
        "说明书答应的是「你自己给收藏夹起的那些名字，不是一串数字」")


def test_a_platform_supplied_id_still_wins(settings, store, service) -> None:
    """平台自己给了 id 就用它——退回 collection_key 只是兜底，不是覆盖。

    **反向也要测**：兜底写成无条件覆盖的话，将来平台给了真 id 反而会被踩掉。
    """
    _ingest(settings, store, service, external_collection_id=REAL_KEY)
    keys = {row["key"] for row in _collections(store)}
    assert REAL_KEY in keys, keys


def test_a_batch_with_no_name_registers_nothing(settings, store, service) -> None:
    """**说不出名字的不进筛选框。**

    这是 2026-08-06 已经定过的界线：他库里有 70 条挂在一串 100 字的页面文案下
    （已删的 v0.0.0.6 抓取器留下的），那种 key 端给用户就是噪音。
    这条判据防的是我这次的兜底把那道界线一起拆掉。
    """
    coordinator = AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))
    start = coordinator.connect_start(AccountConnectRequest(
        platform="bilibili", auth_method="browser_session", relation_types=["favorite"]))
    account_id = coordinator.complete_connection(
        platform="bilibili", auth_method="browser_session",
        connection_ref=start.connection_ref, external_account_id="owner",
        display_name="B站", auto_sync_enabled=True, sync_interval_minutes=360,
        metadata={}, verified=True)
    run_id = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", relation_types=["favorite"],
        trigger_type="first_connect"))["sync_run_id"]
    junk = "综合视频直播专栏 更多筛选 清空历史批量管理全部时长10分钟以下"
    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", batch_index=0, batch_count=1,
        collection_key=junk, completeness="complete", has_more=False,
        items=[CaptureRequest(
            platform="bilibili", url="https://www.bilibili.com/video/BV2yy",
            external_content_id="BV2yy", relation_type="favorite",
            collection_key=junk, title="历史里的一条")]))
    assert _collections(store) == [], (
        "没有名字的 key 进了筛选框——他会在下拉框里看到一串页面文案")
