r"""扩展那条路上，一次同步真的会跑完（2026-08-10）。

## 这条判据补的是一个缺口，不是一个 bug

Owner 生产库：**20 次同步，0 次 completed**。根因已经修了
（服务端声明的 `relation_scope` 超出扩展会扫的范围，多出来那几档永远等不到终批）。

但**「修好了」这件事当时没有任何判据能证明**：

  · `tests/focused/test_sync_scope_never_exceeds_what_can_be_scanned.py`
    证的是「范围不超」——那是**必要条件**，不是「跑得完」。
  · `test_reddit_connector.py` / `test_x_connector.py` 里那两条
    `status == "completed"` 走的是**服务端连接器**那条路，
    而不收敛的是**扩展**那条路。
  · `list_shape_end_to_end_drill.py` 里的 `"status": "completed"`
    是它自己那个**假服务器**回的常量——它证明的是扩展会读这个字段，
    不是服务端会算出这个字段。

所以这里直接走扩展的协议：服务端起 run → 扩展按 `relation_scope` 送终批
→ run 必须变成 `completed`。

## 反例在同一个文件里

`test_the_old_scope_would_never_have_finished` 把范围恢复成修复前那样
（`favorite` + `like`），同样送完 `favorite` 的终批——run **不会**是 completed。
那就是他这二十次的形状。
"""

from __future__ import annotations

from social_archive import account_sync as _sync
from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountSyncRequest, CaptureRequest, SyncBatchRequest


def _account(store):
    return store.upsert_source_account(
        platform="douyin",
        external_account_id="owner",
        display_name="抖音账号",
        auth_method="browser_session",
        auth_handle_ref="ext_douyin_fixture",
        connection_state="connected",
    )


def _favourite_terminal_batch() -> SyncBatchRequest:
    """扩展扫完收藏夹之后送的那一批：`completeness=complete` 且 `has_more=False`。"""
    return SyncBatchRequest(
        relation_type="favorite",
        items=[CaptureRequest(
            platform="douyin",
            url="https://www.douyin.com/video/7669728491277851091",
            external_content_id="7669728491277851091",
            relation_type="favorite",
            title="一条收藏",
        )],
        scope_type="relation",
        completeness="complete",
        has_more=False,
    )


def test_the_server_only_asks_for_what_the_extension_scans(settings, store, service) -> None:
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(
        _account(store),
        AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    run = store.get_sync_run(started["sync_run_id"])
    # `_decode_sync_run` 会把 `relation_scope_json` 解成 `relation_scope`（已是 list）
    assert run["relation_scope"] == ["favorite"], (
        "服务端又把扩展不扫的关系列进范围了——那几档永远等不到终批")


def test_a_douyin_run_actually_reaches_completed(settings, store, service) -> None:
    """**这才是他要的那件事**：点了同步，圈会停。"""
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(
        _account(store),
        AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    coordinator.ingest_batch(started["sync_run_id"], _favourite_terminal_batch())
    run = store.get_sync_run(started["sync_run_id"])
    assert run["status"] == "completed", (
        f"送完收藏的终批之后 run 还是 {run['status']}——"
        "他生产上 20 次同步 0 次 completed 就是这个形状（界面上是「圈一直转」）")


def test_the_old_scope_would_never_have_finished(settings, store, service, monkeypatch) -> None:
    """**反例。** 把范围恢复成修复前那样，同一批终批送进去，它就是收不了尾。

    不立这一条的话，上面那条可能只是「协议本来就这样」，
    证明不了那个修复真的起了作用。
    """
    monkeypatch.setitem(_sync.SCANNABLE_RELATIONS, "douyin", ("favorite", "like"))
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(
        _account(store),
        AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    assert store.get_sync_run(started["sync_run_id"])["relation_scope"] \
        == ["favorite", "like"], "反例没有生效——那下面这条断言就没有意义"
    coordinator.ingest_batch(started["sync_run_id"], _favourite_terminal_batch())
    run = store.get_sync_run(started["sync_run_id"])
    assert run["status"] != "completed", (
        "修复前的范围竟然也能收敛？那说明上面那条判据钉错了东西")


def test_the_counts_it_shows_him_match_what_really_landed(settings, store, service) -> None:
    """**「已导入 0 条」而库里多了一条，就是产品对他的数据说假话。**（2026-08-10）

    真制品上实测出来的：走真 HTTP 送一批收藏的终批，
    batch 回执写着 `accepted: 1`、库里 `total = 1`，而这次 run 报

        discovered_count 0 / imported_count 0 / duplicate_count 0 / failed_count 0

    根因：计数只在 `scope_type == "collection"` 那一支加，
    而**抖音/小红书/快手没有收藏夹分组，扩展送的就是 relation 批次**——
    那条路上一次都不加。他连的两个平台里，抖音正好走这条。
    """
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    started = coordinator.start_sync(
        _account(store),
        AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    coordinator.ingest_batch(started["sync_run_id"], _favourite_terminal_batch())
    run = store.get_sync_run(started["sync_run_id"])
    landed = store.list_library_table(platform="douyin")["total"]
    assert landed == 1, f"这一批根本没进库（{landed} 条），下面的断言就没意义"
    assert run["imported_count"] == landed, (
        f"界面会告诉他「已导入 {run['imported_count']} 条」，而库里实际进了 {landed} 条")
    assert run["discovered_count"] == 1, (
        f"发现数是 {run['discovered_count']}，而这一批送来了 1 条")
