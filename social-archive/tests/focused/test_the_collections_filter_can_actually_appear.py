"""说明书答应的那个「收藏夹」筛选，在他的数据上得真的出得来（2026-08-07）。

## 怎么查的，以及我错在哪

从他生产库只读读真实形状：`platform_collection` 有 3 行（8/3–8/4 那几次真同步
写的，名字是「收藏」「合集和系列」），但 `external_collection_id` **三行全是
NULL**；而分面那条 SQL 是

    JOIN platform_collection pc ON … pc.external_collection_id = r.collection_key

当场量：那条 JOIN 在他 193 条上匹配 **0 条**。而 `docs/使用说明.md` 写着
「B 站连上之后，资料库上方会多出一个「收藏夹」筛选」。

**我第一版据此断定「扩展从来不发 external_collection_id」，并在服务端加了
「没给就退回 collection_key」的兜底。那句断定是错的**——扩展在 v0.0.0.11
（8f32ef76）就已经显式发它了，现在凡是发 `collection_name` 的批次都同时发。
他生产上那三行 NULL 是 8/3–8/4 的历史遗留，不是当前行为。

我是怎么把自己绕进去的：数「扩展发不发这个字段」时，剥块注释用了
`re.sub(r"/\\*.*?\\*/", " ")`——**它把多行注释压成一个空格，后面每个行号都平移
了**，我按错的行号去读源码，读到的是另一个函数。保行数地重剥才看见那两行。

兜底已撤掉。它对真实客户端是死代码，却有真代价：**登记过的收藏夹才可能被判成
「变空」**（见 `list_registered_collections`），兜底会放大登记范围，而他那 30 条
挂在旧 key `bilibili:/3493091105311656/favlist` 下的收藏正是靠「没登记过」活着的。

## 所以这里守的是客户端那条不变量

**发收藏夹名字，就必须一起发 id。** 那两行在 background.js 里，删掉任何一行，
筛选栏就在他数据上永远不出现——而在此之前没有任何判据会红。

夹具用他真实的那把 key 和名字，不另编一个更干净的——夹具比原文干净就等于没测。
"""

from __future__ import annotations

from pathlib import Path

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import (AccountConnectRequest, AccountSyncRequest,
                                   CaptureRequest, SyncBatchRequest)
from social_archive.registry import ConnectorRegistry

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = ROOT / "apps/browser-extension/background.js"

# 他生产库里真实的那把 key 和那个名字（2026-08-07 只读量得）。
REAL_KEY = "bilibili:/3493091105311656/favlist"
REAL_NAME = "收藏"


def _strip_js_comments_keeping_lines(text: str) -> list[str]:
    """剥注释但**保住行数**。

    压掉换行会让后面每个行号都是错的——今天就是这么把自己绕进去的。
    """
    out: list[str] = []
    in_block = False
    for line in text.splitlines():
        kept, i = "", 0
        while i < len(line):
            if in_block:
                end = line.find("*/", i)
                if end < 0:
                    i = len(line)
                    break
                in_block = False
                i = end + 2
                continue
            if line.startswith("//", i):
                break
            if line.startswith("/*", i):
                in_block = True
                i += 2
                continue
            kept += line[i]
            i += 1
        out.append(kept)
    return out


def _start(settings, store, service):
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
    return coordinator, run_id


def _ingest(settings, store, service, *, external_collection_id):
    coordinator, run_id = _start(settings, store, service)
    coordinator.ingest_batch(run_id, SyncBatchRequest(
        relation_type="favorite", scope_type="collection", batch_index=0, batch_count=1,
        collection_key=REAL_KEY, collection_name=REAL_NAME,
        external_collection_id=external_collection_id,
        completeness="complete", has_more=False,
        items=[CaptureRequest(
            platform="bilibili", url="https://www.bilibili.com/video/BV1xx",
            external_content_id="BV1xx", relation_type="favorite",
            collection_key=REAL_KEY, title="一条真收藏")]))


def _collections(store) -> list[dict]:
    return store.list_library_table(limit=1)["facets"].get("collections", [])


def test_the_guide_still_promises_the_filter() -> None:
    """**判据守的是一句承诺，那句话得还在。**"""
    guide = (ROOT / "docs/使用说明.md").read_text(encoding="utf-8")
    assert "「收藏夹」筛选" in guide, "说明书里那句承诺被改了或删了"
    assert "里面是你自己给收藏夹起的那些名字" in guide


def test_the_extension_always_sends_the_id_next_to_the_name() -> None:
    """**这是真正会坏的地方。**

    删掉 background.js 里那句 `external_collection_id: group.key`，服务端会拿
    「名字」当外部 id（`external = external_collection_id or name`），而关系上
    存的是媒体 id——两边永远对不上，筛选栏在他数据上永远不出现，
    而在这条判据之前**没有任何判据会红**。

    规则是推导出来的、不抄清单：凡是发 `collection_name:` 的那一批，
    附近必须也发 `external_collection_id:`。
    """
    lines = _strip_js_comments_keeping_lines(BACKGROUND.read_text(encoding="utf-8"))
    names = [i for i, line in enumerate(lines, 1) if "collection_name:" in line]
    ids = {i for i, line in enumerate(lines, 1) if "external_collection_id:" in line}
    assert names, "一处发 collection_name 的地方都没找到——这条判据在空扫"
    orphans = [n for n in names if not any(abs(n - i) <= 12 for i in ids)]
    assert not orphans, (
        f"background.js:{orphans} 发了收藏夹名字，却没在同一批里发 "
        "external_collection_id——服务端会拿名字当外部 id，"
        "而关系上存的是媒体 id，两边永远对不上：**他那一栏「收藏夹」筛选不会出现**")


def test_a_real_bilibili_favlist_shows_up_in_the_filter(settings, store, service) -> None:
    """**按扩展真正发出去的形状**跑一遍，那一栏必须出得来，显示的是名字。"""
    _ingest(settings, store, service, external_collection_id=REAL_KEY)
    collections = _collections(store)
    assert collections, (
        "分面里一个收藏夹都没有——说明书答应他会多出一栏「收藏夹」筛选，"
        "而那一栏整个是藏着的")
    keys = {row["key"]: row.get("label") for row in collections}
    assert REAL_KEY in keys, f"他真实那把 key 没进分面：{list(keys)}"
    assert keys[REAL_KEY] == REAL_NAME, (
        f"下拉框里显示的是 {keys[REAL_KEY]!r}，不是他给收藏夹起的名字 {REAL_NAME!r}——"
        "说明书答应的是「你自己给收藏夹起的那些名字，不是一串数字」")


def test_the_server_does_not_guess_the_id(settings, store, service) -> None:
    """**客户端不给 id，服务端就不登记——不猜。**

    猜一个出来是有代价的：登记过的收藏夹才可能被判成「变空」而整桶销账
    （`list_registered_collections` 的文档写着这条），而他有 30 条挂在旧 key
    下面，正是靠「没登记过」活着的。宁可那一栏不出现，也不要把销账的射程放大。
    """
    _ingest(settings, store, service, external_collection_id=None)
    keys = {row["key"] for row in _collections(store)}
    assert REAL_KEY not in keys, (
        f"服务端替客户端猜了外部 id：{keys}——**登记范围一放大，"
        "旧 key 就可能被当成「变空的收藏夹」，他 30 条收藏会被两次同步关掉**")


def test_a_batch_with_no_name_registers_nothing(settings, store, service) -> None:
    """**说不出名字的不进筛选框。**

    这是 2026-08-06 定过的界线：他库里有 70 条挂在一串 100 字的页面文案下
    （已删的 v0.0.0.6 抓取器留下的），那种 key 端给用户就是噪音。

    老实说一句：这条界线目前**由 schema 兜着**（`platform_collection.name`
    是 NOT NULL），把 `if batch.collection_name:` 改掉会撞 IntegrityError 而不是
    撞这条断言。这条守的是将来有人塞一个占位名字进来的情形。
    """
    coordinator, run_id = _start(settings, store, service)
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
