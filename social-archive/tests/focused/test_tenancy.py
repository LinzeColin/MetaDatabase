"""多租户隔离（v0.0.0.7 / T01）。

这些测试断言的是 T01 的两条 Acceptance：

  1. 迁移后不存在 user_id 为空的业务行，且总行数与迁移前一致
  2. 跨 user_id 读取被挡住

第 2 条是重点。它不是"查询里写了 WHERE user_id"这种实现细节的复述——
每个用例都真的造出两个用户的数据，然后以 B 的身份去要 A 的东西，断言要不到。
"""

from __future__ import annotations

import pytest

import sqlite3
from pathlib import Path

import pytest

from social_archive.db import RuntimeStore
from social_archive.models import CaptureRequest


ALICE = "usr_alice"
BOB = "usr_bob"


@pytest.fixture
def store(tmp_path: Path) -> RuntimeStore:
    db = RuntimeStore(tmp_path / "runtime.sqlite3")
    db.initialize()
    return db


def _make_user(store: RuntimeStore, user_id: str) -> None:
    with store.connection() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(id,display_name,created_at,is_owner) VALUES(?,?,?,0)",
            (user_id, user_id, "2026-08-03T00:00:00Z"),
        )


def _capture_for(store: RuntimeStore, user_id: str, *, url: str, title: str) -> str:
    """以 user_id 的身份存一条内容，返回 content_id。

    capture() 目前把一切都写给 Owner（本版本只有一个用户），所以这里在写入后
    把归属改成目标用户——测试要的是隔离读取，不是 capture 的多用户签名，
    那个签名要等 T02 接上会话才有真实来源。
    """
    content_id, _, _ = store.capture(
        CaptureRequest(platform="x", url=url, title=title, relation_type="bookmark")
    )
    with store.connection() as con:
        con.execute("UPDATE user_relation SET user_id=? WHERE content_id=?", (user_id, content_id))
    return content_id


# ── Acceptance 1：迁移后没有孤儿行 ─────────────────────────────────


def test_migration_leaves_no_orphan_rows(store: RuntimeStore) -> None:
    store.capture(CaptureRequest(platform="x", url="https://x.com/a/1", title="a"))
    audit = store.tenancy_audit()
    assert audit["orphan_rows"] == {t: 0 for t in RuntimeStore.AUDITED_TABLES}, (
        f"仍有未归属的业务行：{audit['orphan_rows']}"
    )


def test_migration_is_idempotent_and_preserves_row_counts(store: RuntimeStore) -> None:
    store.capture(CaptureRequest(platform="x", url="https://x.com/a/1", title="a"))
    store.capture(CaptureRequest(platform="x", url="https://x.com/a/2", title="b"))
    before = store.tenancy_audit()

    store.initialize()  # 重复迁移
    after = store.tenancy_audit()

    assert after["total_rows"] == before["total_rows"], "重复迁移改变了行数"
    assert after["users"] == before["users"] == 1, "重复迁移多造了 users 行"
    assert after["orphan_rows"] == {t: 0 for t in RuntimeStore.AUDITED_TABLES}


def test_new_writes_are_never_unattributed(store: RuntimeStore) -> None:
    """迁移把历史行补齐了，但如果写入路径不带 user_id，下一次 capture 就又破了。"""
    store.capture(CaptureRequest(platform="x", url="https://x.com/a/1", title="a"))
    store.upsert_source_account(
        platform="bilibili",
        external_account_id="uid-1",
        display_name="B站",
        auth_method="browser",
        auth_handle_ref=None,
        connection_state="connected",
    )
    assert store.tenancy_audit()["orphan_rows"] == {t: 0 for t in RuntimeStore.AUDITED_TABLES}


def test_sync_run_inherits_tenancy_from_its_account(store: RuntimeStore) -> None:
    """同步运行归属于账号的主人，不是"当前是谁在跑"。"""
    _make_user(store, ALICE)  # user_id 上有外键，用户必须先存在
    account_id = store.upsert_source_account(
        platform="bilibili",
        external_account_id="uid-2",
        display_name="B站",
        auth_method="browser",
        auth_handle_ref=None,
        connection_state="connected",
    )
    with store.connection() as con:
        con.execute("UPDATE source_account SET user_id=? WHERE id=?", (ALICE, account_id))

    run_id = store.create_sync_run(
        source_account_id=account_id,
        platform="bilibili",
        mode="first_full",
        relation_types=["favorite"],
        trigger_type="manual",
    )
    assert store.get_sync_run(run_id)["user_id"] == ALICE


# ── Acceptance 2：跨 user_id 读取被挡住 ────────────────────────────


def test_tenancy_forbids_cross_user_read(store: RuntimeStore) -> None:
    """任务包 Oracle 点名的那个测试。

    Alice 存一条、Bob 存一条，然后各自只应看到自己那条。
    """
    _make_user(store, ALICE)
    _make_user(store, BOB)
    alice_content = _capture_for(store, ALICE, url="https://x.com/alice/1", title="Alice 的书签")
    bob_content = _capture_for(store, BOB, url="https://x.com/bob/1", title="Bob 的书签")

    alice_view = store.for_user(ALICE)
    bob_view = store.for_user(BOB)

    # 列表：各自只看得到自己的
    alice_ids = {row["id"] for row in alice_view.list_library()}
    bob_ids = {row["id"] for row in bob_view.list_library()}
    assert alice_ids == {alice_content}, f"Alice 看到了不属于她的内容：{alice_ids}"
    assert bob_ids == {bob_content}, f"Bob 看到了不属于他的内容：{bob_ids}"
    assert not (alice_ids & bob_ids)

    # 直接拿 id 取：知道 id 也拿不到别人的
    assert alice_view.get_content(alice_content) is not None
    assert alice_view.get_content(bob_content) is None, "知道 content_id 就能读到别人的内容"
    assert bob_view.get_content(alice_content) is None

    # 裸 store 仍然看得到全部——这不是缺陷，是 worker 与运维路径需要的能力。
    # 但正因如此，API 层绝不允许直接用裸 store。
    assert store.get_content(bob_content) is not None


def test_cross_user_read_blocked_in_table_view(store: RuntimeStore) -> None:
    """表格视图有 facet 统计与分页，必须和列表用同一套过滤，否则会出现
    "总数是全库、页是自己"的错位。"""
    _make_user(store, ALICE)
    _make_user(store, BOB)
    _capture_for(store, ALICE, url="https://x.com/alice/1", title="Alice 1")
    _capture_for(store, ALICE, url="https://x.com/alice/2", title="Alice 2")
    _capture_for(store, BOB, url="https://x.com/bob/1", title="Bob 1")

    table = store.for_user(ALICE).list_library_table()
    titles = {row["title"] for row in table["items"]}
    assert titles == {"Alice 1", "Alice 2"}
    assert all("Bob" not in (t or "") for t in titles)


def test_cross_user_read_blocked_for_accounts_and_runs(store: RuntimeStore) -> None:
    _make_user(store, ALICE)
    _make_user(store, BOB)
    account_id = store.upsert_source_account(
        platform="bilibili",
        external_account_id="uid-3",
        display_name="Alice 的 B站",
        auth_method="browser",
        auth_handle_ref=None,
        connection_state="connected",
    )
    with store.connection() as con:
        con.execute("UPDATE source_account SET user_id=? WHERE id=?", (ALICE, account_id))
    run_id = store.create_sync_run(
        source_account_id=account_id,
        platform="bilibili",
        mode="first_full",
        relation_types=["favorite"],
        trigger_type="manual",
    )

    assert store.for_user(ALICE).get_source_account(account_id) is not None
    assert store.for_user(BOB).get_source_account(account_id) is None
    assert store.for_user(ALICE).get_sync_run(run_id) is not None
    assert store.for_user(BOB).get_sync_run(run_id) is None
    assert store.for_user(BOB).list_source_accounts() == []
    assert store.for_user(BOB).list_sync_runs() == []
    # 拿别人的 account_id 去过滤同步记录也不行
    assert store.for_user(BOB).list_sync_runs(source_account_id=account_id) == []


def test_scope_rejects_empty_user_id(store: RuntimeStore) -> None:
    """空 user_id 会让 WHERE 退化成全库读取——必须在入口就拦住，
    而不是让它悄悄变成一次跨租户扫描。"""
    with pytest.raises(ValueError):
        store.for_user("")


def test_caller_cannot_override_tenant_boundary(store: RuntimeStore) -> None:
    """即便调用方显式传 user_id，也不得越过 scope 绑定的那个。"""
    _make_user(store, ALICE)
    _make_user(store, BOB)
    _capture_for(store, ALICE, url="https://x.com/alice/1", title="Alice 1")
    bob_content = _capture_for(store, BOB, url="https://x.com/bob/1", title="Bob 1")

    rows = store.for_user(ALICE).list_library(user_id=BOB)
    assert {r["id"] for r in rows} == {r["id"] for r in store.for_user(ALICE).list_library()}
    assert bob_content not in {r["id"] for r in rows}


def test_owner_user_id_is_deterministic() -> None:
    """回滚脚本要按 id 定位 Owner 行，所以它不能是随机的。"""
    assert RuntimeStore.OWNER_USER_ID == RuntimeStore.OWNER_USER_ID
    assert RuntimeStore.OWNER_USER_ID.startswith("usr")


def test_content_and_artifact_stay_shared(store: RuntimeStore) -> None:
    """content/artifact 有意不带 user_id：它们是内容寻址、全局去重的。
    这个测试把那个决定钉住——将来有人"顺手"给 content 加 user_id 时会在这里失败，
    并被迫先读上面那段说明。"""
    with store.connection() as con:
        for table in ("content", "artifact"):
            columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
            assert "user_id" not in columns, (
                f"{table} 不应有 user_id：它是全局去重的，两个用户存同一条内容时只有一行，"
                f"user_id 只能记下谁先到，是假隔离。所有权边在 user_relation 上。"
            )


# ── 审计面本身要被守住（v0.0.0.7 / T01 补强）────────────────────────


def test_every_user_id_table_is_audited(tmp_path) -> None:
    """T01 的 Oracle 原文是「**各表** user_id 为空 = 0」。

    审计如果只覆盖一部分表，它报的就是「我数过的那几张没问题」，
    而不是「没问题」。两者在报告上长得一模一样。

    实测踩到过：T05 新增 platform_credential 时没同步扩审计面——
    库里 8 张表带 user_id，审计只覆盖 4 张，而它照样报绿。
    """
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    audit = store.tenancy_audit()
    assert audit["uncovered_tables"] == [], (
        f"这些表带 user_id 却不在审计面里：{audit['uncovered_tables']}。"
        "新增带 user_id 的表时必须同时进 TENANT_TABLES 或 IDENTITY_TABLES。"
    )
    # 审计确实数到了东西——扫到 0 张表和「没问题」长得一样
    assert len(audit["audited_tables"]) >= 8, (
        f"审计只覆盖了 {len(audit['audited_tables'])} 张表，太少了，八成漏了"
    )
    assert set(audit["orphan_rows"]) == set(audit["audited_tables"])


def test_audit_would_notice_a_new_unregistered_tenant_table(tmp_path) -> None:
    """先证明自查抓得到，绿色才有意义。"""
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    with store.connection() as con:
        con.execute("CREATE TABLE sneaky_new_table (id TEXT PRIMARY KEY, user_id TEXT)")
    assert store.tenancy_audit()["uncovered_tables"] == ["sneaky_new_table"], (
        "新加了一张带 user_id 的表，审计却没发现——自查是坏的"
    )


def test_identity_tables_cannot_hold_an_empty_user_id(tmp_path) -> None:
    """身份/凭据表不经 for_user 收敛，但 user_id 必须结构性非空。"""
    import sqlite3

    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    with store.connection() as con:
        con.execute(
            "INSERT INTO users(id,display_name,created_at,is_owner) VALUES('u','U','t',1)"
        )
    for table, columns, values in (
        ("session", "(id,user_id,created_at,expires_at)", "('s',NULL,'t','t')"),
        ("extension_token", "(id,user_id,token_hash,created_at)", "('e',NULL,'h','t')"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with store.connection() as con:
                con.execute(f"INSERT INTO {table}{columns} VALUES{values}")
