r"""他要能把一个账号连同内容删干净，然后从零再走一遍（2026-08-10）。

Owner 的原话：「账号内存删除，增加删除按钮，从零测试能不能用」。

## 为什么「断开」不够

`DELETE /v1/accounts/{id}` 是「别再替我去取了」，**内容一条不动**——
那是对的默认（归档的意义就是东西留下来）。但要确认这套东西到底能不能用，
就得清干净、从零走一遍：不然重连之后**分不清「同步真的跑了」还是「本来就有」**。

## 只删只属于它的内容

`content` 是共享的（同一条可以被两个账号同时收藏），账号关系挂在 `user_relation`。
删掉这个账号的关系之后，只删那些**一条关系都不剩**的内容；
别的账号还留着的一条都不碰，并如实报出留了几条、为什么。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from social_archive.account_sync import AccountSyncCoordinator
from social_archive.models import AccountSyncRequest, CaptureRequest, SyncBatchRequest

ROOT = Path(__file__).resolve().parents[2]


def _account(store, platform: str, external: str = "owner") -> str:
    return store.upsert_source_account(
        platform=platform, external_account_id=external, display_name=platform,
        auth_method="browser_session", auth_handle_ref=f"ref_{platform}_{external}",
        connection_state="connected")


def _sync_one(settings, store, service, account_id: str, external: str) -> str:
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    run = coordinator.start_sync(account_id, AccountSyncRequest(
        mode="first_full", trigger_type="first_connect"))["sync_run_id"]
    coordinator.ingest_batch(run, SyncBatchRequest(
        relation_type="favorite", scope_type="relation", completeness="complete", has_more=False,
        items=[CaptureRequest(platform="douyin",
                              url=f"https://www.douyin.com/video/{external}",
                              external_content_id=external, relation_type="favorite",
                              title=f"内容 {external}")]))
    return run


def test_deleting_an_account_really_empties_it(settings, store, service) -> None:
    account_id = _account(store, "douyin")
    _sync_one(settings, store, service, account_id, "111")
    assert store.list_library_table(platform="douyin")["total"] == 1

    result = store.forget_source_account(account_id)
    assert result["found"] and result["removed_content"] == 1, result
    assert result["removed_sync_runs"] == 1, result
    assert store.list_library_table(platform="douyin")["total"] == 0, "内容没删干净"
    assert store.get_source_account(account_id) is None, "账号还在"


def test_content_another_account_also_saved_is_kept(settings, store, service) -> None:
    """**只删只属于它的。** 别的账号也存过的那一条要留着，并如实说明。"""
    first = _account(store, "douyin", "owner-a")
    second = _account(store, "douyin", "owner-b")
    _sync_one(settings, store, service, first, "222")
    _sync_one(settings, store, service, second, "222")     # 同一条内容
    assert store.list_library_table(platform="douyin")["total"] == 1

    result = store.forget_source_account(first)
    assert result["removed_content"] == 0, result
    assert result["kept_content_shared_with_other_accounts"] == 1, result
    assert store.list_library_table(platform="douyin")["total"] == 1, "把别人也存的那条删了"


def test_from_zero_again_after_deleting(settings, store, service) -> None:
    """**从零再走一遍**——这正是他要这颗按钮的原因。"""
    account_id = _account(store, "douyin")
    _sync_one(settings, store, service, account_id, "333")
    store.forget_source_account(account_id)
    assert store.list_library_table(platform="douyin")["total"] == 0

    again = _account(store, "douyin")
    run = _sync_one(settings, store, service, again, "333")
    assert store.get_sync_run(run)["status"] == "completed", "重连之后同步跑不完"
    assert store.list_library_table(platform="douyin")["total"] == 1, "重新同步没把内容带回来"


def test_deleting_a_missing_account_is_not_silently_ok(store) -> None:
    assert store.forget_source_account("cnt_does_not_exist") == {"found": False}


@pytest.mark.parametrize("piece", [
    'data-forget-account',                 # 按钮在
    'forgetAccount(button.dataset.forgetAccount',   # 绑上了
    '/forget',                             # 打的是新路由
    '把平台名字打一遍',                      # 不可逆，要二次确认
])
def test_the_button_exists_and_is_wired(piece: str) -> None:
    """**建好了没接上**——这个仓栽过六次以上。"""
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert piece in app_js, f"界面上缺这一环：{piece}"


def _referencing(target: str) -> list[str]:
    """从 schema 里数出「谁引用了 target」——不靠记忆。"""
    import re
    sql = (ROOT / "src/social_archive/sql/runtime_schema.sql").read_text(encoding="utf-8")
    return sorted(name for name, body in
                  re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", sql, re.S)
                  if f"REFERENCES {target}" in body)


def test_the_schema_really_has_these_references() -> None:
    """反空扫：一条外键都没数到的话，下面那条会白过。"""
    assert len(_referencing("content(id)")) >= 4
    assert len(_referencing("source_account(id)")) >= 4
    assert len(_referencing("sync_run(id)")) >= 2


@pytest.mark.parametrize(
    "table",
    _referencing("content(id)") + _referencing("source_account(id)") + _referencing("sync_run(id)"))
def test_the_purge_covers_every_table_that_points_at_what_it_deletes(table: str) -> None:
    """**外键把我拦了两次**（第一次漏了几张引用 content 的，第二次漏了
    `sync_seen_relation`）。教训不是「再多想一张」，是**照着 schema 数**。

    这条判据就是那份清单：以后谁新加一张引用这三者的表，而删除逻辑没跟上，
    这里当场红——而不是等他点删除、看到
    `sqlite3.IntegrityError: FOREIGN KEY constraint failed`。
    """
    import inspect
    from social_archive.db import RuntimeStore
    body = inspect.getsource(RuntimeStore.forget_source_account)
    assert table in body, (
        f"`{table}` 引用了要被删掉的行，而 forget_source_account 没清它——"
        "他点「删除并清空」会撞上外键错误")
