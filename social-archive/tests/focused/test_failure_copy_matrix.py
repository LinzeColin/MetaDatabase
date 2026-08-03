"""零不得沉默（v0.0.0.7 / T14）。

INV-NO-SILENT-ZERO：任何一次同步为 0 条时，界面都说得出为什么。

判据分三组：

  1. 文案与 `01_PRODUCT/ZERO_BARRIER_UX.md` 的冻结词典**逐字**一致
  2. 人为注入四种失败，各自给出对应的中文句子
  3. 库里不允许存在「imported=0 且 failure_code 为空」的同步运行
"""

from __future__ import annotations

from pathlib import Path

import pytest

from social_archive.failure_copy import (
    COPY_BY_CODE,
    NOTHING_NEW,
    describe_sync_outcome,
    resolve,
)

ROOT = Path(__file__).resolve().parents[2]

# 逐字照抄任务包 01_PRODUCT/ZERO_BARRIER_UX.md「错误文案词典（冻结）」的右列。
# 这里重抄一遍是**故意**的：词典是产品合同，改代码时如果顺手改了句子，
# 这份独立副本会立刻报红，而不是跟着一起变。
FROZEN = {
    "CREDENTIAL_EXPIRED": "<平台> 的登录状态过期了。[ 重新连接 ]",
    "NOT_LOGGED_IN": "没有在浏览器里找到 <平台> 的登录状态。请先在浏览器里登录 <平台>，然后点 [ 重试 ]",
    "REDDIT_NOT_AUTHORIZED": "Reddit 需要单独授权一次。[ 去授权 ]",
    "TAB_CLOSED": "<平台> 同步中断了，因为标签页被关掉。[ 继续 ]",
    "RATE_LIMITED": "<平台> 请求太频繁，已自动放慢。已经收到的 <N> 条都保住了，稍后会自动继续。",
    "SERVER_UNREACHABLE": "暂时连不上服务器。你的数据没有丢，[ 重试 ]",
    "DISK_QUOTA": "存储空间快满了，已经暂停下载媒体文件，文字和链接还在正常保存。",
}


def test_dictionary_matches_the_frozen_product_copy_verbatim() -> None:
    assert set(COPY_BY_CODE) == set(FROZEN), "词典条目与冻结词典不一致"
    for code, sentence in FROZEN.items():
        assert COPY_BY_CODE[code].template == sentence, f"{code} 的文案被改动了"


def test_frozen_copy_is_still_what_the_task_pack_says() -> None:
    """判据自己的自检：如果产品文档在仓里，就直接对照它，不只对照我抄的副本。

    抄写本身可能抄错——这条把「我抄的」和「文档写的」对起来。
    文档不在仓里时跳过，并说清楚是跳过而不是通过。
    """
    doc = ROOT / "docs" / "ZERO_BARRIER_UX.md"
    if not doc.is_file():
        pytest.skip("仓内没有 ZERO_BARRIER_UX.md（它在任务包里），本条只能对照代码内副本")
    text = doc.read_text(encoding="utf-8")
    for sentence in FROZEN.values():
        assert sentence in text, f"文档里找不到这句：{sentence}"


# ── 任务包点名的四种失败 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario,code,expected",
    [
        ("凭据过期", "CREDENTIAL_EXPIRED", "X 的登录状态过期了。[ 重新连接 ]"),
        ("未登录", "NOT_LOGGED_IN",
         "没有在浏览器里找到 X 的登录状态。请先在浏览器里登录 X，然后点 [ 重试 ]"),
        ("标签页关闭", "TAB_CLOSED", "X 同步中断了，因为标签页被关掉。[ 继续 ]"),
        ("服务端不可达", "SERVER_UNREACHABLE", "暂时连不上服务器。你的数据没有丢，[ 重试 ]"),
    ],
)
def test_injected_failure_renders_the_dictionary_sentence(
    scenario: str, code: str, expected: str
) -> None:
    outcome = describe_sync_outcome(imported=0, failure_code=code, platform_label="X")
    assert outcome["message_zh"] == expected, f"{scenario} 的文案不对"
    assert outcome["outcome"] == "failed"
    # 界面上不许出现英文错误码
    assert code not in str(outcome["message_zh"])


def test_no_english_error_code_or_stack_leaks_into_any_message() -> None:
    for code in COPY_BY_CODE:
        rendered = describe_sync_outcome(
            imported=0, failure_code=code, platform_label="B站"
        )["message_zh"]
        assert code not in rendered
        for leak in ("Traceback", "Error", "Exception", "None", "null"):
            assert leak not in rendered, f"{code} 的文案里漏出了 {leak}"


# ── 「没有新增」与「失败」是两种显示 ──────────────────────────────────


def test_nothing_new_is_not_shown_as_a_failure() -> None:
    """两者都是 0 条，但一个是好事一个是坏事。混成一句用户永远分不清该不该重试。"""
    nothing = describe_sync_outcome(imported=0, failure_code=None, status="completed")
    assert nothing["outcome"] == "nothing_new"
    assert nothing["message_zh"] == NOTHING_NEW.template
    assert nothing["action_zh"] is None, "「没有新增」不该给重试按钮"

    failed = describe_sync_outcome(imported=0, failure_code="TAB_CLOSED", platform_label="B站")
    assert failed["outcome"] == "failed"
    assert failed["message_zh"] != nothing["message_zh"]


def test_imported_count_is_reported_when_something_came_in() -> None:
    assert describe_sync_outcome(imported=7, failure_code=None)["message_zh"] == "新增 7 条。"


# ── 静默的零本身要被点名 ─────────────────────────────────────────────


def test_zero_without_a_reason_is_called_out_not_dressed_up_as_success() -> None:
    """这是 INV-NO-SILENT-ZERO 的核心判据。

    0 条、没有失败码、也没跑完——这正是 v0.0.0.6 的形状。
    它必须显示成「产品的问题」，而不是含糊过去或伪装成成功。
    """
    outcome = describe_sync_outcome(imported=0, failure_code=None, status="scanning")
    assert outcome["outcome"] == "unexplained_zero"
    assert outcome["failure_code"] == "UNEXPLAINED_ZERO"
    assert "我们没能记录下原因" in str(outcome["message_zh"])
    assert "这是产品的问题" in str(outcome["message_zh"])
    assert outcome["action_zh"] == "重试"


def test_internal_codes_are_aliased_into_dictionary_sentences() -> None:
    """代码里的失败码比词典细，但界面上只许出现词典里的句子。"""
    for internal, expect_code in (
        ("ACQUISITION_PATH_NOT_INSTALLED", "SERVER_UNREACHABLE"),
        ("LOGIN_PROOF_UNAVAILABLE", "NOT_LOGGED_IN"),
        ("PERMISSION_DENIED", "NOT_LOGGED_IN"),
        ("MIRROR_TAB_CLOSED", "TAB_CLOSED"),
    ):
        resolved = resolve(internal)
        assert resolved is not None, f"{internal} 没有映射到词典"
        assert resolved.code == expect_code
        rendered = describe_sync_outcome(
            imported=0, failure_code=internal, platform_label="小红书"
        )["message_zh"]
        assert rendered == COPY_BY_CODE[expect_code].render(platform_label="小红书")


def test_unknown_code_does_not_silently_become_success() -> None:
    outcome = describe_sync_outcome(imported=0, failure_code="SOMETHING_NEW_NOBODY_MAPPED")
    assert outcome["outcome"] == "unexplained_zero", (
        "没见过的失败码被当成了成功——那正是静默的零"
    )


def test_rate_limited_keeps_what_was_already_collected() -> None:
    """限速不是失败，且必须把「已经收到的都保住了」说出来。"""
    outcome = describe_sync_outcome(imported=0, failure_code="RATE_LIMITED", platform_label="B站")
    assert outcome["outcome"] == "informational"
    assert "都保住了" in str(outcome["message_zh"])


def test_platform_placeholder_never_leaks_when_label_is_missing() -> None:
    """没传平台名时不能把 `<平台>` 这个占位符直接显示给用户。"""
    for code in COPY_BY_CODE:
        rendered = describe_sync_outcome(imported=0, failure_code=code)["message_zh"]
        assert "<平台>" not in str(rendered), f"{code} 把占位符漏给了界面"
        assert "<N>" not in str(rendered)


# ── 库层审计：不允许存在没有原因的零 ────────────────────────────────


def _store(tmp_path: Path):
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    with store.connection() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(id,display_name,created_at,is_owner) "
            "VALUES('usr_owner','Owner','2026-01-01T00:00:00Z',1)"
        )
        con.execute(
            "INSERT INTO source_account(id,user_id,platform,auth_method,display_name,"
            "external_account_id,connection_state,created_at,updated_at) "
            "VALUES('acct','usr_owner','x','browser_session','X','me','connected','t','t')"
        )
    return store


def _insert_run(store, run_id: str, status: str, imported: int, code: str | None) -> None:
    with store.connection() as con:
        con.execute(
            """INSERT INTO sync_run(id,user_id,source_account_id,platform,mode,status,
                                    imported_count,updated_at,last_error_code)
               VALUES(?,'usr_owner','acct','x','first_full',?,?,'2026-01-01T00:00:00Z',?)""",
            (run_id, status, imported, code),
        )


def test_audit_finds_a_terminal_zero_with_no_reason(tmp_path: Path) -> None:
    """先证明审计抓得到，再谈它报绿有没有意义。"""
    store = _store(tmp_path)
    _insert_run(store, "run_bad", "failed", 0, None)
    _insert_run(store, "run_bad2", "partial", 0, "   ")  # 空白字符串也算没有原因
    found = {row["id"] for row in store.unexplained_zero_runs()}
    assert found == {"run_bad", "run_bad2"}, f"审计没抓到静默的零：{found}"


def test_audit_does_not_flag_nothing_new_or_explained_failures(tmp_path: Path) -> None:
    """三种都不该被报：

    · completed + 0 条 —— 「已经是最新的」，是好事
    · failed + 有失败码 —— 说得出原因
    · partial + 有内容进来 —— 不是零
    """
    store = _store(tmp_path)
    _insert_run(store, "run_nothing_new", "completed", 0, None)
    _insert_run(store, "run_explained", "failed", 0, "TAB_CLOSED")
    _insert_run(store, "run_partial_with_items", "partial", 5, None)
    assert store.unexplained_zero_runs() == []


def test_every_audited_row_can_be_turned_into_a_chinese_sentence(tmp_path: Path) -> None:
    """审计抓到之后，界面必须仍然说得出话——不能只在日志里留个 ID。"""
    store = _store(tmp_path)
    _insert_run(store, "run_bad", "failed", 0, None)
    for row in store.unexplained_zero_runs():
        outcome = describe_sync_outcome(
            imported=int(row["imported_count"]),
            failure_code=row["last_error_code"],
            status=str(row["status"]),
            platform_label="X",
        )
        assert outcome["outcome"] == "unexplained_zero"
        assert str(outcome["message_zh"]).strip()
        assert "<" not in str(outcome["message_zh"])
