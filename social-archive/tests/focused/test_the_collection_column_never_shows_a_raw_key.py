"""资料库那一列「收藏夹」，不许把内部 key 端给他看（2026-08-10）。

## 这是一个「修了一半」

`list_library_table` 里 `collection_names` 那一列 2026-08-07 已经改过了，
注释写得很清楚，连反例都点了名：

    **只取查得到名字的。** 中间那一版写的是"查不到就退回 key"……
    他库里 100 条带着 v0.0.0.6 抓取器留下的 key，其中一个是一百字的页面文案
    （'综合视频直播专栏 更多筛选 清空历史…'）。那种东西出现在「收藏夹」
    这一格里，比显示「未分组」糟得多。

**而界面读的不是那一列。** `apps/pwa/app.js`：

    collection: item.primary_collection || collections.join("、") || "未分组"

`primary_collection` 排在最前面，而它一直是 `r.collection_key` 原样输出。
于是那句注释里说"比显示未分组糟得多"的东西，此刻就在他的屏幕上。

2026-08-10 去他生产库里数，194 条关系里：

    70 条  bilibili / history   key = '综合视频直播专栏 更多筛选 清空历史批量管理…'（一百字页面文案）
    30 条  bilibili / favorite  key = 'bilibili:/3493091105311656/favlist'（一条路径）

**100/194 那一格是内部值。** 一道判据都没红——判据盯的是 `collection_names`，
而用户看的是 `primary_collection`。

## 规矩只有一条

说得出名字（`platform_collection` 里登记过）就显示名字；说不出就交白卷，
让界面去写「未分组」。**两个界面对同一件事必须给同一个答案。**
"""

from __future__ import annotations

from social_archive.models import CaptureRequest
from social_archive.utils import stable_id

# 他生产库里那两条，逐字抄过来。**夹具不许比真东西干净**——
# 自己编一个 'foo' 当 key，这条判据什么也证不了。
REAL_HISTORY_KEY = (
    "综合视频直播专栏 更多筛选 清空历史批量管理全部时长10分钟以下10-30分钟"
    "30-60分钟60分钟以上全部时间今天昨天近一周开始日期至结束日期全部设备PC手机平板TV")
REAL_FAVLIST_KEY = "bilibili:/3493091105311656/favlist"


def _account(store) -> str:
    """`platform_collection` 有外键指向 `source_account`——先把账号建出来。"""
    return store.upsert_source_account(
        platform="bilibili", external_account_id="b1", display_name="B站账号",
        auth_method="browser_session", auth_handle_ref=None, connection_state="connected")


def _capture(service, url: str, external: str, collection_key: str, relation: str = "favorite"):
    service.capture(CaptureRequest(
        platform="bilibili", url=url, external_content_id=external,
        relation_type=relation, source_account_id="b1",
        collection_key=collection_key,
        relation_observed_at="2026-08-01T10:00:00Z", title=external))


def test_a_hundred_character_page_blurb_never_reaches_the_column(store, service) -> None:
    """**说不出名字就交白卷。** 界面自己会写「未分组」。"""
    _capture(service, "https://www.bilibili.com/video/BV1A", "BV1A",
             REAL_HISTORY_KEY, relation="history")
    shown = store.list_library_table(platform="bilibili")["items"][0]["primary_collection"]
    assert not shown, (
        f"「收藏夹」这一格端出了内部 key：{str(shown)[:60]!r}…——"
        "那是一段页面文案，不是收藏夹名字。说不出名字就该留空，由界面写「未分组」")


def test_a_path_shaped_key_is_not_a_name_either(store, service) -> None:
    """路径也是内部值。他不会管自己的收藏夹叫 `bilibili:/…/favlist`。"""
    _capture(service, "https://www.bilibili.com/video/BV1B", "BV1B", REAL_FAVLIST_KEY)
    shown = store.list_library_table(platform="bilibili")["items"][0]["primary_collection"]
    assert not shown, f"「收藏夹」这一格端出了路径：{shown!r}"


def test_a_registered_collection_still_shows_its_name(store, service) -> None:
    """**正例必须是绿的。**

    一个"永远返回空"的实现同样是坏的——那样他连自己的收藏夹都分不出来。
    只有登记过的（走同步批次那条路会登记）才显示，显示的是名字。
    """
    _account(store)
    store.upsert_platform_collection(
        source_account_id=stable_id("acct", "bilibili", "b1"),
        relation_type="favorite", name="学习", external_collection_id="col-study")
    _capture(service, "https://www.bilibili.com/video/BV1C", "BV1C", "col-study")
    shown = store.list_library_table(platform="bilibili")["items"][0]["primary_collection"]
    assert shown == "学习", (
        f"登记过名字的收藏夹显示成了 {shown!r}——"
        "这条判据要是只会说「空」，那它把好实现和坏实现一起判死了")


def test_the_two_columns_agree(store, service) -> None:
    """**两个界面对同一件事必须给同一个答案。**

    `primary_collection`（表格那一格）和 `collections`（详情里那一串）
    出自同一个问题。它们分家过一次，代价是修了一个、另一个继续错。
    """
    _account(store)
    store.upsert_platform_collection(
        source_account_id=stable_id("acct", "bilibili", "b1"),
        relation_type="favorite", name="音乐", external_collection_id="col-music")
    _capture(service, "https://www.bilibili.com/video/BV1D", "BV1D", "col-music")
    _capture(service, "https://www.bilibili.com/video/BV1E", "BV1E", REAL_HISTORY_KEY,
             relation="history")
    for item in store.list_library_table(platform="bilibili")["items"]:
        primary = item["primary_collection"] or ""
        joined = "、".join(item["collections"])
        assert primary == joined, (
            f"同一条内容，表格那一格说 {primary!r}，详情那一串说 {joined!r}")


def test_the_ui_prefers_this_field_so_fixing_the_other_one_was_not_enough() -> None:
    """**钉住"为什么这条判据存在"**：界面读的是 primary_collection。

    2026-08-07 修的是 `collection_names`（→ 接口里的 `collections`），
    而 app.js 把 `primary_collection` 排在它前面。修了一半等于没修。
    """
    from pathlib import Path

    app = (Path(__file__).resolve().parents[2] / "apps/pwa/app.js").read_text(encoding="utf-8")
    line = next(l for l in app.splitlines() if "collection: item.primary_collection" in l)
    assert line.index("primary_collection") < line.index("collections.join"), (
        "界面不再优先读 primary_collection 了——那这条判据的理由要重写")
