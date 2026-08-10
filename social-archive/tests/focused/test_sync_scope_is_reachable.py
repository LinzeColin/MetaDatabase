"""同步范围里不能有「永远等不到终批」的关系类型（v0.0.0.7 / T04 回归）。

## 这条判据是被真实浏览器逼出来的

本机一次性 Chrome、Owner 真实书签、点真按钮，实测结果：

    62 条全部入库 ✓
    运行状态永远停在 scanning ✗

原因：`POST /v1/accounts/{id}/connect` 起首次同步时**没传 relation_types**
（api.py：`AccountSyncRequest(mode="first_full", trigger_type="first_connect")`），
于是范围取了平台的全部关系 `['bookmark', 'manual_save']`。
而扩展只会送 `bookmark` 的终批——`manual_save` 那一路永远等不到，
run 永远不收敛。

界面上就是：**点了同步，东西都进来了，圈还一直在转。**

这是 v0.0.0.6 就有的（在 origin/main 上逐字相同），不是这次改出来的。
"""

from __future__ import annotations

import pytest

from social_archive.account_sync import (
    NON_SCANNABLE_RELATIONS,
    NOT_SYNCABLE_YET,
    PLATFORM_RELATIONS,
    SYNCABLE_NOW,
    AccountSyncCoordinator,
)


def test_manual_save_is_allowed_but_never_scanned() -> None:
    """两件事都要成立：手动存能进库（允许），同步不去枚举它（不可枚举）。"""
    assert "manual_save" in PLATFORM_RELATIONS["generic-web"], (
        "把 manual_save 从允许列表里删掉会让手动收藏被拒——那是另一个更糟的 bug"
    )
    assert "manual_save" in NON_SCANNABLE_RELATIONS
    scope = AccountSyncCoordinator._scannable_relations("generic-web")
    assert scope == ["bookmark"], f"同步范围里还留着枚举不出来的关系：{scope}"


@pytest.mark.parametrize("platform", sorted(PLATFORM_RELATIONS))
def test_every_platform_default_scope_is_reachable(platform: str) -> None:
    """穷举所有平台：默认同步范围里不许出现不可枚举的关系类型。

    只修 generic-web 是不够的——将来给别的平台加一个 manual_save
    这类关系，同样会让那个平台的 run 永远不收敛。
    """
    scope = AccountSyncCoordinator._scannable_relations(platform)
    leaked = [item for item in scope if item in NON_SCANNABLE_RELATIONS]
    assert not leaked, (
        f"{platform} 的默认同步范围里有枚举不出来的关系 {leaked}——"
        "那一路永远等不到终批，这次 run 会永远停在 scanning"
    )
    # **「空」对同步不了的平台是正确答案，不是缺陷。**（2026-08-10 改）
    #
    # 上一版是无条件 `assert scope`。而 YouTube 的取数路本版没有做，
    # 它在 SCANNABLE_RELATIONS 里登记成空正是为了让 start_sync 当场拒绝
    # ——不登记的话服务端会下发 ['watch_later','playlist']，
    # 扩展一条都不会扫，那次 run 永远等不到终批。
    #
    # 所以这里要分两档：能同步的不许被清空；不能同步的必须是空，
    # **而且必须已经在 NOT_SYNCABLE_YET 里有一句给人看的原因**
    # ——空而没有原因，界面上就是一片什么都不说的空白。
    # **X 是第三种，不能和 YouTube 用同一把尺子。**
    # 两个都不在 SYNCABLE_NOW 里，但失败形态不同：
    #   · YouTube 走扩展，而扩展没有它的取数路 → 会**永远转**（等不到终批）
    #   · X 走服务端连接器，点下去**当场报**「零费用门未确认」（铁律 7）
    # 快速失败带一句原因是可以接受的；永远转不行。
    # 所以 X 的范围保持非空，由连接器自己收敛。
    if platform in SYNCABLE_NOW:
        assert scope, f"{platform} 在「现在就能同步」表里，同步范围却被清空了"
    elif platform == "x":
        assert scope, "X 走服务端连接器那条路，范围不该是空的（它会当场报错，不是永远转）"
        assert NOT_SYNCABLE_YET.get(platform), "X 不能同步，却没有一句给人看的原因"
    else:
        assert not scope, (
            f"{platform} 界面上不给同步，服务端却仍下发 {scope}——"
            "扩展不会去扫，那次 run 永远不收敛（他抖音那二十次就是这个）")
        assert NOT_SYNCABLE_YET.get(platform), (
            f"{platform} 同步范围是空的，却没有一句话说明为什么——"
            "他看到的会是一片空白，那看起来像加载失败")


def test_explicitly_requesting_a_non_scannable_relation_does_not_stick() -> None:
    """就算调用方明确点名要 manual_save，也不能把它放进同步范围。

    否则一个手滑的调用方就能造出一个永远不收敛的 run。
    """
    scope = AccountSyncCoordinator._scannable_relations("generic-web", ["bookmark", "manual_save"])
    assert scope == ["bookmark"]


def test_validation_still_accepts_manual_save() -> None:
    """校验用的 _relations **不受影响**——否则手动收藏会被 422 拒掉。"""
    allowed = AccountSyncCoordinator._relations("generic-web")
    assert "manual_save" in allowed, "批次校验也把 manual_save 排除了，手动收藏会被拒"
    assert "bookmark" in allowed


# ── 卡住不动的运行 ──────────────────────────────────────────────────


def test_a_queued_run_is_not_reported_as_a_product_defect() -> None:
    """刚排上队的同步不能被说成「这是产品的问题」。

    这条是从真实浏览器里看出来的：点完连接、run 还在 queued 时，
    界面显示的是「这次没有取到任何内容…这是产品的问题，请重试一次」。
    用户刚点完就被告知产品坏了，而它其实只是还没开始跑。
    """
    from social_archive.failure_copy import IN_PROGRESS_STATES, describe_sync_outcome

    for state in sorted(IN_PROGRESS_STATES):
        out = describe_sync_outcome(imported=0, failure_code=None, status=state)
        assert out["outcome"] == "in_progress", f"{state} 被判成了 {out['outcome']}"
        assert "产品的问题" not in out["message_zh"], f"{state} 仍在说产品坏了"
        assert out["failure_code"] is None


def test_silencing_in_progress_did_not_silence_real_silent_zeros() -> None:
    """把「在跑」改成不报错，**不能**顺手把真正的静默的零也放过去。"""
    from social_archive.failure_copy import describe_sync_outcome

    # 终态、0 条、没有失败码 —— 这才是必须被抓住的那一种
    out = describe_sync_outcome(imported=0, failure_code=None, status="partial")
    assert out["outcome"] == "unexplained_zero"
    assert out["failure_code"] == "UNEXPLAINED_ZERO"


def test_stalled_runs_are_detectable_since_the_copy_no_longer_screams() -> None:
    """在跑的状态不再报警了，那"永远在跑"就必须有别的东西抓得到。

    否则这次改动等于把唯一的信号关掉。
    """
    import tempfile
    from pathlib import Path

    from social_archive.db import RuntimeStore

    with tempfile.TemporaryDirectory() as tmp:
        store = RuntimeStore(Path(tmp) / "t.db")
        store.initialize()
        assert hasattr(store, "stalled_active_runs"), "没有任何东西抓「卡住不动」"
        # 新库里什么都没有
        assert store.stalled_active_runs() == []
        # 用生产接口造数据，不手搓 INSERT——手搓会绕过外键和默认值，
        # 测出来的东西和真实库里的不是一回事。
        account = store.upsert_source_account(
            platform="generic-web", external_account_id="chrome-bookmarks",
            display_name="Chrome 书签", auth_method="chrome_bookmarks",
            auth_handle_ref=None, connection_state="connected",
        )
        ids = {}
        for name, status in (("stuck", "scanning"), ("fresh", "scanning"), ("done", "completed")):
            ids[name] = store.create_sync_run(
                source_account_id=account, platform="generic-web", mode="first_full",
                relation_types=["bookmark"], trigger_type="manual",
            )
            store.update_sync_run(ids[name], status=status)
        with store.connection() as con:
            # 把 stuck 和 done 的时间往回拨 40 分钟
            for name in ("stuck", "done"):
                con.execute("UPDATE sync_run SET updated_at=datetime('now','-40 minutes') WHERE id=?",
                            (ids[name],))
        stalled = [row["id"] for row in store.stalled_active_runs(stale_after_seconds=1800)]
        assert stalled == [ids["stuck"]], (
            f"抓到的是 {stalled}——应该只有那条卡了 40 分钟的 scanning："
            f"刚动过的({ids['fresh']})和已收尾的({ids['done']})都不算"
        )


def test_a_run_that_has_been_in_progress_all_day_stops_saying_please_wait() -> None:
    """「正在同步，请稍候。」说一次是对的，说一整天就是骗人。

    界面读的是 /v1/sync-runs，不是 /v1/status —— 后者根本没有客户端在读。
    所以卡住这件事必须在这一句里说出来，挂在 status 上只够运维查。
    """
    from datetime import UTC, datetime, timedelta

    from social_archive.failure_copy import describe_sync_outcome

    fresh = describe_sync_outcome(
        imported=0, failure_code=None, status="scanning",
        updated_at=datetime.now(UTC).isoformat(),
    )
    assert fresh["outcome"] == "in_progress"
    assert fresh["message_zh"] == "正在同步，请稍候。"

    stuck = describe_sync_outcome(
        imported=0, failure_code=None, status="scanning",
        updated_at=(datetime.now(UTC) - timedelta(hours=6)).isoformat(),
    )
    assert stuck["outcome"] == "stalled", "卡了六小时还在说「请稍候」"
    assert "卡住" in stuck["message_zh"]
    assert stuck["action_zh"] == "重试"
    # 不能吓唬人说数据没了
    assert "你已经取到的内容都还在" in stuck["message_zh"]


def test_a_missing_or_broken_timestamp_does_not_mark_everything_stalled() -> None:
    """时间戳缺失/格式坏掉时，不能把正常运行一律判成卡住。"""
    from social_archive.failure_copy import describe_sync_outcome

    for stamp in ("", None, "不是时间"):
        row = describe_sync_outcome(
            imported=0, failure_code=None, status="queued", updated_at=stamp,
        )
        assert row["outcome"] == "in_progress", f"updated_at={stamp!r} 被判成了 {row['outcome']}"


def test_both_uis_can_actually_show_the_stalled_sentence() -> None:
    """卡住这件事要真的出现在界面上，不能只存在于接口回包里。

    这条判据的由来：`_explain_sync_run` 只往行里塞 outcome/message_zh，
    **不写 last_error_code**。而 PWA 原来只在 `run.last_error_code` 有值时
    才渲染那一行说明——于是卡住的运行在 PWA 上什么都不显示。
    又是「修了一半」：服务端算出来了，用户看不见。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    pwa = (root / "apps/pwa/app.js").read_text(encoding="utf-8")
    side = (root / "apps/browser-extension/sidepanel.js").read_text(encoding="utf-8")

    assert 'run.outcome === "stalled"' in pwa, (
        "PWA 只认 last_error_code；卡住的运行没有失败码，界面上就什么都不说"
    )
    assert "run.message_zh" in side, "侧边栏没有用服务端算好的那句话"
